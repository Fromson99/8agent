"""Transport a complete declared generation; reuse existing Oracle publishers.

Only data transport: no source mutation, DDL, activation or serving installation.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import time
import uuid
import zipfile

from semantic_runtime import oracle_dp_io as io, oracle_dp_assets as assets, oracle_query_catalog as q
from semantic_runtime.physical_mapping import names
from . import oracle_query_package as transport, oracle_migration as migration
from . import oracle_publish as source_publish, oracle_query_publish as query_publish
from .oracle_transfer_progress import report, check

FORMAT = 'oracle-full-generation-transport-v1'
RESTORED_FORMAT = 'oracle-existing-zip-generation-v1'
ARCHIVE = 'full-data.zip'
CHUNK_BYTES = transport.CHUNK_BYTES
bounded_json = transport.bounded_json
resources = transport.resources
immutable_inputs = transport.immutable_inputs


def inventory(generation):
    root, manifest, items, files, selected = immutable_inputs(generation)
    paths = {'generation/' + name: root / name for name in files}
    if selected is not None:
        paths['SEARCH_SELECTION/generation.json'] = root.parent / 'SEARCH_SELECTION' / (root.name + '.json')
    declared = {name: {'bytes': path.stat().st_size, 'sha256': io.file_sha(path)} for name, path in paths.items()}
    db = migration.source_open(root / 'store.sqlite')
    try: counts = migration.source_counts(db, manifest)
    finally: db.close()
    return root, paths, {'format': FORMAT, 'dataset_version': files['manifest.json'],
                         'source_counts': counts, 'files': declared,
                         'scope': 'all-declared-generation-data', 'asset_files': len(items)}


def _copy(source, target, *, folder, limit, tick=lambda: None):
    h = hashlib.sha256(); size = 0
    while block := source.read(min(1024**2, limit - size + 1)):
        tick(); resources(folder); size += len(block)
        if size > limit: raise io.DPError('FILE_SIZE: exceeds declaration')
        h.update(block)
        if target is not None: target.write(block)
    return {'bytes': size, 'sha256': h.hexdigest()}


def export(generation, output, *, seconds=21600, chunk_bytes=CHUNK_BYTES):
    if not 1 <= seconds <= 21600 or not 1 <= chunk_bytes <= CHUNK_BYTES:
        raise io.DPError('BUDGET: seconds 1..21600; part bytes 1..49000000')
    with transport.job(output) as folder:
        root, paths, manifest = inventory(generation)
        if folder.resolve().is_relative_to(root): raise io.DPError('OUTPUT_INSIDE_SOURCE')
        identity = {'generation': str(root), 'inventory': manifest, 'chunk_bytes': chunk_bytes,
                    'code': io.file_sha(__file__)}
        receipt = folder / 'export-state.json'
        state = bounded_json(receipt) if receipt.exists() else {'identity': identity, 'deadline': time.time()+7*86400}
        if state['identity'] != identity: raise io.DPError('EXPORT_BINDING: inputs/code changed')
        io.atomic_json(receipt, state)
        end = min(time.time()+seconds, state['deadline'])
        def tick():
            if time.time() >= end: raise io.BudgetPause('EXPORT_BUDGET: rerun same output; deadline retained')
        archive = folder / ARCHIVE
        if not archive.exists():
            temp = folder / (ARCHIVE+'.partial-'+uuid.uuid4().hex)
            with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
                for name, path in paths.items():
                    transport.event(folder, 'ARCHIVING', file=name)
                    with path.open('rb') as src, z.open(name, 'w', force_zip64=True) as dst:
                        actual = _copy(src, dst, folder=folder, limit=manifest['files'][name]['bytes'], tick=tick)
                    if actual != manifest['files'][name]: raise io.DPError('SOURCE_CHANGED: '+name)
            if inventory(root)[2] != manifest: raise io.DPError('SOURCE_CHANGED: inventory changed')
            temp.rename(archive)
        with zipfile.ZipFile(archive) as z:
            if sorted(z.namelist()) != sorted(paths): raise io.DPError('ZIP_MEMBERS')
            for name, item in manifest['files'].items():
                with z.open(name) as src:
                    if _copy(src, None, folder=folder, limit=item['bytes'], tick=tick) != item:
                        raise io.DPError('ZIP_HASH: '+name)
        download = folder / 'download'; download.mkdir(exist_ok=True)
        entries = []; total = hashlib.sha256()
        with archive.open('rb') as src:
            number = 0
            while src.tell() < archive.stat().st_size:
                tick(); number += 1; name = f'{ARCHIVE}.part{number:06d}'
                target = download / name; temp = folder / (name+'.partial-'+uuid.uuid4().hex)
                h = hashlib.sha256(); size = 0
                with temp.open('xb') as dst:
                    while size < chunk_bytes:
                        tick(); resources(folder)
                        block = src.read(min(1024**2, chunk_bytes-size))
                        if not block: break
                        dst.write(block); size += len(block); h.update(block); total.update(block)
                item = {'name': name, 'bytes': size, 'sha256': h.hexdigest()}
                if target.exists():
                    if target.stat().st_size != size or io.file_sha(target) != item['sha256']:
                        raise io.DPError('PART_CONFLICT: '+name)
                    temp.unlink()  # Verified regenerated duplicate only.
                else: temp.rename(target)
                entries.append(item); transport.event(folder, 'PART_SAVED', **item)
        if total.hexdigest() != io.file_sha(archive) or inventory(root)[2] != manifest:
            raise io.DPError('SOURCE_CHANGED: archive or original changed')
        value = {**manifest, 'archive': ARCHIVE, 'archive_bytes': archive.stat().st_size,
                 'archive_sha256': total.hexdigest(), 'parts': entries}
        io.atomic_json(download / 'parts-manifest.json', value)
        result = {'status': 'FULL_EXPORT_COMPLETE', 'download_dir': str(download.resolve()),
                  'parts': len(entries), 'archive_bytes': value['archive_bytes'],
                  'source_counts': manifest['source_counts'], 'dataset_version': manifest['dataset_version']}
        state.update(status='COMPLETE', result=result); io.atomic_json(receipt, state)
        return result


def validate_manifest(info):
    if info.get('format') != FORMAT or info.get('archive') != ARCHIVE: raise io.DPError('PART_FORMAT')
    q.pin(info['archive_sha256']); q.pin(info['dataset_version'])
    entries = info['parts']; files = info['files']
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100000: raise io.DPError('PART_LIST')
    if [e['name'] for e in entries] != [f'{ARCHIVE}.part{i:06d}' for i in range(1, len(entries)+1)]:
        raise io.DPError('PART_ORDER')
    for item in entries:
        q.pin(item['sha256'])
        if type(item['bytes']) is not int or not 0 < item['bytes'] <= CHUNK_BYTES: raise io.DPError('PART_SIZE')
    if sum(e['bytes'] for e in entries) != info['archive_bytes']: raise io.DPError('PART_SIZE')
    validate_files(files)


def validate_files(files):
    if not isinstance(files, dict) or not {'generation/manifest.json', 'generation/store.sqlite'} <= files.keys():
        raise io.DPError('FILE_LIST')
    for name, item in files.items():
        if assets.safe_relative(name) != name or not (name.startswith('generation/') or name == 'SEARCH_SELECTION/generation.json'):
            raise io.DPError('FILE_PATH')
        q.pin(item['sha256'])
        if type(item['bytes']) is not int or item['bytes'] < 0: raise io.DPError('FILE_SIZE')


def verify_restored(folder):
    folder = Path(folder).resolve(); info = bounded_json(folder / 'full-manifest.json')
    if info.get('format') == 'oracle-existing-nfs-generation-v1':
        from .oracle_existing_nfs import validate_info
        snapshot = info['nfs_snapshot']
        validate_info(snapshot, code_sha256=snapshot['code_sha256'], generation=snapshot['generation'])
        if (info['snapshot_sha256'] != snapshot['snapshot_sha256']
                or info['files'] != snapshot['files'] or info['dataset_version'] != snapshot['dataset_version']):
            raise io.DPError('NFS_RESTORE_BINDING')
        validate_files(info['files'])
    elif info.get('format') == RESTORED_FORMAT:
        validate_files(info['files']); q.pin(info['archive_sha256']); q.pin(info['data_manifest_sha256'])
        q.pin(info['dataset_version'])
    else:
        validate_manifest(info)
    for name, item in info['files'].items():
        path = assets.checked_path(folder, name)
        if not path.is_file() or path.stat().st_size != item['bytes'] or io.file_sha(path) != item['sha256']:
            raise io.DPError('RESTORE_HASH: '+name)
    root, _, actual = inventory(folder / 'generation')
    if any(actual[k] != info[k] for k in actual if k != 'format'): raise io.DPError('RESTORE_BINDING: declared generation differs')
    return root, info


def restore(parts, output):
    parts = Path(parts); info = bounded_json(parts / 'parts-manifest.json'); validate_manifest(info)
    if {p.name for p in parts.glob(ARCHIVE+'.part*')} != {e['name'] for e in info['parts']}:
        raise io.DPError('PART_SET: missing or extra parts')
    with transport.job(output) as folder:
        marker = folder / 'full-manifest.json'
        if marker.exists() and bounded_json(marker) != info: raise io.DPError('RESTORE_BINDING: different package')
        archive = folder / ARCHIVE
        needed = (0 if archive.exists() else info['archive_bytes']) + sum(
            item['bytes'] for name, item in info['files'].items() if not (folder/name).exists())
        if resources(folder) < needed+512*1024**2: raise io.BudgetPause('DISK_LOW: ZIP + generation + 512MiB required')
        temp = folder / (ARCHIVE+'.partial-'+uuid.uuid4().hex) if not archive.exists() else None
        dst = temp.open('xb') if temp else None; total = hashlib.sha256()
        try:
            for item in info['parts']:
                path = parts / item['name']
                if path.is_symlink() or not path.is_file() or path.stat().st_size != item['bytes']:
                    raise io.DPError('PART_SIZE: '+item['name'])
                h = hashlib.sha256()
                with path.open('rb') as src:
                    while block := src.read(1024**2):
                        resources(folder); h.update(block); total.update(block)
                        if dst is not None: dst.write(block)
                if h.hexdigest() != item['sha256']: raise io.DPError('PART_HASH: '+item['name'])
        finally:
            if dst is not None: dst.close()
        if total.hexdigest() != info['archive_sha256']: raise io.DPError('ZIP_HASH')
        if temp: temp.rename(archive)
        if archive.is_symlink() or io.file_sha(archive) != info['archive_sha256']: raise io.DPError('ZIP_HASH')
        with zipfile.ZipFile(archive) as z:
            if sorted(z.namelist()) != sorted(info['files']): raise io.DPError('ZIP_MEMBERS')
            for name, item in info['files'].items():
                path = assets.checked_path(folder, name); path.parent.mkdir(parents=True, exist_ok=True)
                if z.getinfo(name).file_size != item['bytes']: raise io.DPError('ZIP_SIZE')
                if path.exists():
                    if path.stat().st_size != item['bytes'] or io.file_sha(path) != item['sha256']:
                        raise io.DPError('RESTORE_CONFLICT: '+name)
                    continue
                temp = path.with_name(path.name+'.partial-'+uuid.uuid4().hex)
                with z.open(name) as src, temp.open('xb') as dst:
                    if _copy(src, dst, folder=folder, limit=item['bytes']) != item: raise io.DPError('FILE_HASH: '+name)
                temp.rename(path); transport.event(folder, 'FILE_RESTORED', file=name)
        io.atomic_json(marker, info)
        root, _ = verify_restored(folder)
        return str(root)


def _prior_schema_failure(directory, identity):
    """Carry a pinned pre-write schema failure forward; never reuse write stages."""
    with transport.job(directory) as logs:
        path = logs/'full-state.json'
        previous = bounded_json(path)
        old_identity = previous.get('identity', {})
        pinned_r2 = '641c45540ffb8d3e086bd8060e9cb556e3ae5ccf705d287fe4b5a5528c94c7e2'
        pinned_nfs_r1 = '935f47a47ade390103312f3b21cd2156e10571cf955ec351199dda16c761115d'
        schema = previous.get('schema_check', {})
        known_failure = (
            old_identity.get('code') == pinned_r2 and
            previous.get('error', '').startswith('QUERY_SCHEMA: ')
        ) or (
            old_identity.get('code') == pinned_nfs_r1 and previous.get('error') == 'KeyError' and
            schema.get('status') == 'READY' and schema.get('tables') == 4 and
            isinstance(schema.get('target_map_sha256'), str) and
            len(schema['target_map_sha256']) == 64 and 'deferred_indexes' not in schema
        )
        if (not known_failure or
                {k:v for k,v in old_identity.items() if k != 'code'} !=
                {k:v for k,v in identity.items() if k != 'code'} or
                previous.get('status') != 'FAILED' or previous.get('stages') != {} or
                previous.get('stage') is not None):
            raise io.DPError('IMPORT_UPGRADE: only a pinned pre-write schema failure is eligible')
        calls = 0
        with (logs/'schema.jsonl').open() as records:
            for line in records:
                row = json.loads(line)
                if row['binding'] != io.digest(old_identity) or row.get('write') is True:
                    raise io.DPError('IMPORT_UPGRADE: previous SQL binding/write differs')
                calls = max(calls, row['call'])
        if not calls or type(previous.get('deadline')) not in (int, float):
            raise io.DPError('IMPORT_UPGRADE: missing original budget evidence')
        return {'deadline': previous['deadline'], 'prior_schema_calls': calls,
                'prior_schema_failure': {'directory': str(Path(directory).resolve()),
                    'receipt_sha256': io.file_sha(path), 'identity': old_identity,
                    'error': previous['error']}}


def _import_identity(state, expected, logs):
    """Upgrade exact R2/R3/R4 lineage without resetting identity or SQL budgets."""
    original = state['identity']
    if original == expected:
        return expected
    r23 = '36e52b270f8b9f73b1bfdd92d60a742afcc04fed969bce98af828dda6e54d267'
    r4 = '6b0ece21e0294cf82b253d5ce525b4063cbb534bbe432790ecff3428e0c6cba0'
    if (not isinstance(original, dict) or original.get('code') not in {r23, r4} or
            {k:v for k,v in original.items() if k != 'code'} !=
            {k:v for k,v in expected.items() if k != 'code'}):
        raise io.DPError('IMPORT_BINDING: data/code/target changed')
    policy = 'existing-nfs-r5-native-source-verify-v1'
    record = state.get('compatible_executor')
    if record is not None:
        if not isinstance(record, dict) or record.get('origin_code_sha256') != original['code']:
            raise io.DPError('IMPORT_BINDING: compatible executor origin differs')
        if record.get('execution_code_sha256') == expected['code'] and record.get('policy') == policy:
            return original
        if not (original['code'] == r23 and record.get('execution_code_sha256') == r4 and
                record.get('policy') == 'existing-nfs-r4-remove-invocation-cap-v1'):
            raise io.DPError('IMPORT_BINDING: compatible executor record differs')
    receipt = logs / 'full-state.json'
    raw = receipt.read_bytes()
    receipt_sha = hashlib.sha256(raw).hexdigest()
    backup = logs / ('pre-r5-state-' + receipt_sha + '.json')
    if backup.exists():
        if backup.read_bytes() != raw:
            raise io.DPError('IMPORT_BINDING: pre-upgrade receipt differs')
    else:
        with backup.open('xb') as saved:
            saved.write(raw); saved.flush(); io.os.fsync(saved.fileno())
    if record is not None:
        state.setdefault('compatible_executor_history', []).append(record)
    state['compatible_executor'] = {
        'origin_code_sha256': original['code'],
        'execution_code_sha256': expected['code'], 'policy': policy,
        'prior_receipt_sha256': receipt_sha, 'prior_receipt_file': backup.name,
        'at': time.time(),
    }
    return original


def import_generation(client, folder, *, target_binding, directory, action='check', seconds=3600,
                      allow_missing_lookup_indexes=False, prior_schema_failure_directory=None):
    if action not in {'check', 'publish', 'status'}: raise io.DPError('ACTION: check / publish / status')
    if seconds is not None and (type(seconds) not in (int, float) or
                                not math.isfinite(seconds) or seconds < 1):
        raise io.DPError('BUDGET: seconds must be None or finite and >= 1')
    if type(allow_missing_lookup_indexes) is not bool:
        raise io.DPError('QUERY_INDEX_POLICY: expected a boolean')
    root, info = verify_restored(folder)
    with transport.job(directory) as logs:
        receipt = logs / 'full-state.json'
        identity = {'target': target_binding, 'data': io.digest(info), 'generation': str(root), 'code': io.file_sha(__file__)}
        state = bounded_json(receipt) if receipt.exists() else {'identity': identity, 'deadline': time.time()+7*86400, 'stages': {}}
        identity = _import_identity(state, identity, logs)
        if not receipt.exists() and prior_schema_failure_directory is not None:
            state.update(_prior_schema_failure(prior_schema_failure_directory, identity))
        io.atomic_json(receipt, state)
        end = state['deadline'] if seconds is None else min(time.time()+seconds, state['deadline'])
        def remaining():
            check()
            resources(logs)
            if time.time() >= end: raise io.BudgetPause('IMPORT_BUDGET: resume same action/directory')
            return end-time.time()
        def stage(name, callback):
            report('ORACLE_' + name.upper())
            transport.event(logs, 'STAGE_STARTED', stage=name); state['stage'] = name; io.atomic_json(receipt, state)
            result = callback()
            if result['status'] == 'PAUSED': raise io.BudgetPause('STAGE_PAUSED: '+name)
            state['stages'][name] = result; io.atomic_json(receipt, state)
            return result
        def source(action):
            return migration.transfer(client, root/'store.sqlite', target_binding=target_binding,
                                      directory=logs/'source', action=action, seconds=remaining())
        def sql(name):
            prior_calls = state.get('prior_schema_calls', 0) if name == 'schema' else 0
            return io.SQL(client, journal=logs/(name+'.jsonl'), binding=io.digest(identity),
                          max_calls=1000000-prior_calls, seconds=remaining())
        try:
            checked = sql('schema'); io.check_source_tables(checked)
            physical = getattr(client, 'schema_map', None)
            if physical:
                physical.preflight(checked, keys=['asset_part', 'source_release'])
            else:
                for table, columns in [(assets.PART_TABLE, 'ASSET_SHA256,PART_NO,RAW_BYTES,PART_SHA256,DATA_B64'),
                                       (assets.RELEASE_TABLE, 'RELEASE_ID,DATASET_VERSION,RELEASE_JSON')]:
                    checked.query(f'SELECT {columns} FROM {table} WHERE 1=0')
            schema = query_publish.schema(checked, create=False,
                                          allow_missing_lookup_indexes=allow_missing_lookup_indexes)
            if schema['status'] != 'READY': raise io.DPError('QUERY_SCHEMA: '+str(schema.get('missing')))
            state['schema_check'] = schema
            state['allow_missing_lookup_indexes'] = allow_missing_lookup_indexes
            io.atomic_json(receipt, state)
            if schema['deferred_indexes']:
                transport.event(logs, 'LOOKUP_INDEXES_DEFERRED', indexes=schema['deferred_indexes'])
            if action == 'check':
                return {'status': 'READY_FOR_FULL_IMPORT', 'source_counts': info['source_counts'], 'writes': False,
                        'deferred_indexes': schema['deferred_indexes']}
            if action == 'publish':
                if 'source' not in state['stages']: stage('source', lambda: source('run'))
                if 'verify' not in state['stages']: stage('verify', lambda: source('verify'))
                if 'assets' not in state['stages']:
                    stage('assets', lambda: source_publish.publish(client, source=root/'store.sqlite',
                          transfer_receipt=state['stages']['verify']['receipt'], target_binding=target_binding,
                          directory=logs/'assets', seconds=remaining()))
                if 'query' not in state['stages']:
                    stage('query', lambda: query_publish.publish(client, generation=root,
                          source_release_id=state['stages']['assets']['release_id'], target_binding=target_binding,
                          directory=logs/'query', seconds=remaining()))
            if not {'source', 'verify', 'assets', 'query'} <= state['stages'].keys():
                raise io.DPError('IMPORT_NOT_COMPLETE: publish first')
            # Complete status always rereads the real Oracle contents, never only a receipt.
            stage('final_source', lambda: source('verify'))
            read = sql('final_readback'); sid = state['stages']['assets']['release_id']
            root2, manifest, items, files, selected = immutable_inputs(root)
            expected_source = transport.offline_source(root2, manifest, items, selected, remaining)
            if assets.get_release(read, sid) != expected_source: raise io.DPError('SOURCE_RELEASE_READBACK')
            for item in items:
                h = hashlib.sha256(); size = 0
                for number in range(item['parts']):
                    raw = assets.get_part(read, item['sha256'], number)
                    if raw is None: raise io.DPError('ASSET_MISSING')
                    h.update(raw); size += len(raw)
                if h.hexdigest() != item['sha256'] or size != item['bytes']: raise io.DPError('ASSET_READBACK')
            manifest, paths, tables = query_publish.describe(root, expected_source)
            expected_query = transport.query_manifest(root, expected_source, paths, tables, items)
            rid = state['stages']['query']['release_id']
            if q.read_release(read, rid) != expected_query: raise io.DPError('QUERY_RELEASE_READBACK')
            total = 0
            for relative in paths:
                batch = []; size = 0
                for row in query_publish.projected_rows(root/relative, relative, expected_source):
                    n = len(q.json_body(row))
                    if batch and (len(batch) >= 20 or size+n > 4*1024**2):
                        query_publish._verify_batch(read, rid, batch); batch = []; size = 0
                    batch.append(row); size += n; total += 1
                query_publish._verify_batch(read, rid, batch) if batch else None
            row_names = names(read, 'query_row', q.ROW)
            count = read.query(f'SELECT COUNT(*) AS N FROM {row_names.table} WHERE {row_names.c("RELEASE_ID")}=:release', [('release', rid, 'VARCHAR2')], limit=1)
            if count != [{'N': total}]: raise io.DPError('QUERY_TOTAL_COUNT')
            verify_restored(folder)
            result = {'status': 'FULL_DATA_VERIFIED', 'source_release_id': sid, 'query_release_id': rid,
                      'source_counts': info['source_counts'], 'asset_files': len(items), 'query_rows': total,
                      'deferred_indexes': schema['deferred_indexes'],
                      'active_changed': False, 'state_migrated': False, 'serving_switched': False}
            state.update(status='COMPLETE', result=result); io.atomic_json(receipt, state)
            return result
        except BaseException as exc:
            state.update(status='PAUSED' if isinstance(exc, io.BudgetPause) else 'FAILED',
                         error=str(exc) if isinstance(exc, io.DPError) else type(exc).__name__)
            io.atomic_json(receipt, state); raise
