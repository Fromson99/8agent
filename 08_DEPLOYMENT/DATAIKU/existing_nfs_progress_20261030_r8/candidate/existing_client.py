"""DSS-owned transfer of existing generation bytes and maintained Oracle import."""
import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import socket
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from lawrag.pipeline import oracle_existing_nfs as nfs, oracle_full_package as full
from managed_job import ManagedJob, BudgetClient, bounded_read
import transport as t
import recipes_runtime as r
from updater import config
from lawrag.pipeline.oracle_transfer_progress import tracking, report, console_event
from projection_preflight import preflight

ROOT = Path(__file__).resolve().parent
EXPECTED = (ROOT / 'COMPUTE_CODE_SHA256.txt').read_text().strip()
GENERATION = '/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation'
JOB_NAME = 'financial-risk-success-20261005-schema-r2'
NAMESPACE = '_pipeline/existing-nfs-v1/'
CLIENT_REVISION = 'existing-nfs-20261030-r8'


class Scope:
    def __init__(self, folder):
        self.folder = folder
    def list_paths_in_partition(self):
        return ['/' + p.lstrip('/')[len(NAMESPACE):] for p in self.folder.list_paths_in_partition()
                if p.lstrip('/').startswith(NAMESPACE)]
    def get_download_stream(self, name):
        return self.folder.get_download_stream(NAMESPACE + name.lstrip('/'))
    def upload_stream(self, name, stream):
        return self.folder.upload_stream(NAMESPACE + name.lstrip('/'), stream)


class Wire:
    def __init__(self, url, token):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError('HTTPS_ENDPOINT_REQUIRED')
        self.url, self.token = url, token

    def call(self, operation, **fields):
        request = urllib.request.Request(self.url, method='POST',
            data=json.dumps({'API_TYPE': operation, 'code_sha256': EXPECTED, **fields}).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.token})
        try:
            with urllib.request.build_opener(r.NoRedirect()).open(request, timeout=120) as response:
                raw = bounded_read(response, 4 * nfs.CHUNK)
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise RuntimeError('NFS_HTTP_' + str(code)) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout):
            raise RuntimeError('NFS_NETWORK_UNCONFIRMED') from None
        try:
            value = json.loads(raw)
        except ValueError:
            raise ValueError('NFS_RESPONSE_JSON') from None
        if not isinstance(value, dict) or value.get('code') != 0:
            error = value.get('error') if isinstance(value, dict) else None
            if isinstance(error, str) and error.startswith('NFS_') and error.replace('_', '').isalnum():
                raise ValueError(error)
            raise ValueError('NFS_SERVER_REJECTED')
        if not isinstance(value.get('data'), dict):
            raise ValueError('NFS_RESPONSE_OBJECT')
        return value['data']


def request(store, wire, operation, **fields):
    # Only read operations. One retry owner; every physical attempt is reserved.
    if operation not in {'EXISTING_NFS_INFO', 'EXISTING_NFS_READ'}:
        raise ValueError('NFS_READ_ONLY_OPERATION')
    for attempt in range(3):
        if time.time() >= store.value['deadline']:
            raise ValueError('NFS_ORIGINAL_DEADLINE_EXHAUSTED')
        if not getattr(store, 'http_credit', 0):
            count = store.value.get('reserved_http_calls', 0)
            if count >= 1000000:
                raise ValueError('NFS_HTTP_BUDGET_EXHAUSTED')
            store.http_credit = min(64, 1000000 - count)
            store.value['reserved_http_calls'] = count + store.http_credit
            store.save()
        store.http_credit -= 1
        try:
            return wire.call(operation, **fields)
        except RuntimeError as exc:
            if str(exc) not in {'NFS_HTTP_502', 'NFS_HTTP_503', 'NFS_HTTP_504', 'NFS_NETWORK_UNCONFIRMED'}:
                raise
            failures = store.value.setdefault('read_failures', [])
            failures.append({'operation': operation, 'file': fields.get('file'), 'offset': fields.get('offset'),
                             'error': str(exc), 'attempt': attempt + 1, 'at': time.time()})
            # Preserve all failures in their immutable checkpoint; keep current state bounded.
            store.save()
            store.value['read_failures'] = failures[-20:]
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def put(folder, path, raw, known):
    if path not in known:
        folder.upload_stream(path, io.BytesIO(raw))
    with folder.get_download_stream(path) as stream:
        actual = bounded_read(stream, max(len(raw), 1))
    if actual != raw:
        raise ValueError('NFS_S3_OBJECT_CONFLICT')
    known.add(path)


def receive(store, wire, info, local):
    local = Path(local)
    local.mkdir(parents=True, exist_ok=True)
    known = {p.lstrip('/') for p in store.folder.list_paths_in_partition()}
    prefix = 'snapshots/' + info['snapshot_sha256'] + '/'
    put(store.folder, prefix + 'inventory.json', json.dumps(info, sort_keys=True).encode(), known)
    needed = sum(item['bytes'] for name, item in info['files'].items() if not (local / name).exists())
    if shutil.disk_usage(local).free < needed + 512 * nfs.CHUNK:
        raise ValueError('NFS_LOCAL_SPACE_REQUIRED')
    completed = 0
    for name, item in info['files'].items():
        report('RECEIVED_FILE_CHECK', file=name, bytes_total=item['bytes'])
        if time.time() >= store.value['deadline']:
            raise ValueError('NFS_ORIGINAL_DEADLINE_EXHAUSTED')
        target = local / name
        # Strict path handling matches the maintained Oracle importer.
        from semantic_runtime.oracle_dp_assets import checked_path
        target = checked_path(local, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.stat().st_size != item['bytes'] or t.sha(target) != item['sha256']:
                raise ValueError('NFS_LOCAL_FILE_CONFLICT')
            completed += item['bytes']
            continue
        partial = target.with_name(target.name + '.receive-partial')
        if partial.is_symlink():
            raise ValueError('NFS_LOCAL_SYMLINK')
        h, offset = hashlib.sha256(), 0
        file_key = hashlib.sha256(name.encode()).hexdigest()
        with partial.open('wb') as output:
            while offset < item['bytes']:
                if time.time() >= store.value['deadline']:
                    raise ValueError('NFS_ORIGINAL_DEADLINE_EXHAUSTED')
                key = prefix + 'chunks/' + file_key + '/' + str(offset).zfill(16)
                length = min(nfs.CHUNK, item['bytes'] - offset)
                if key + '.json' in known:
                    with store.folder.get_download_stream(key + '.json') as stream:
                        receipt = json.loads(bounded_read(stream, 2048))
                    with store.folder.get_download_stream(key + '.bin') as stream:
                        block = bounded_read(stream, nfs.CHUNK)
                else:
                    value = request(store, wire, 'EXISTING_NFS_READ', snapshot_sha256=info['snapshot_sha256'],
                                    file=name, offset=offset)
                    block = base64.b64decode(value['content'], validate=True)
                    if (value['snapshot_sha256'] != info['snapshot_sha256'] or value['file'] != name
                            or value['offset'] != offset or value['total_bytes'] != item['bytes']
                            or value['bytes'] != length or value['sha256'] != hashlib.sha256(block).hexdigest()):
                        raise ValueError('NFS_RESPONSE_BINDING')
                    receipt = {'file': name, 'offset': offset, 'bytes': len(block),
                               'sha256': hashlib.sha256(block).hexdigest()}
                    put(store.folder, key + '.bin', block, known)
                    put(store.folder, key + '.json', json.dumps(receipt, sort_keys=True).encode(), known)
                if receipt != {'file': name, 'offset': offset, 'bytes': length, 'sha256': hashlib.sha256(block).hexdigest()} or len(block) != length:
                    raise ValueError('NFS_SAVED_CHUNK_HASH')
                output.write(block); h.update(block); offset += len(block)
                report(bytes_done=offset, bytes_total=item['bytes'])
                if offset % (64 * nfs.CHUNK) == 0 or offset == item['bytes']:
                    print('NFS_RECEIVING', name, offset, '/', item['bytes'], flush=True)
        if h.hexdigest() != item['sha256']:
            raise ValueError('NFS_WHOLE_FILE_HASH')
        partial.replace(target)
        completed += item['bytes']
        store.value.update(phase='RECEIVING', last_completed_file=name, received_bytes=completed)
        store.save()
    record = nfs.finish_received(local, info)
    store.value.update(phase='RECEIVED_VERIFIED', received_bytes=completed,
                       source_counts=record['source_counts'], local_root=str(local))
    store.save()
    return record


def save_receipts(store, attempt, local):
    if not (attempt / 'full-state.json').exists():
        return
    archive = local / 'oracle-receipts.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(attempt.rglob('*')):
            if p.is_file() and p.suffix in {'.json', '.jsonl'}:
                z.write(p, str(p.relative_to(attempt)))
    store.value['oracle_receipt_blob'] = store.put_blob(archive)
    store.value['oracle_receipt_directory'] = attempt.name
    store.save()


def restore_receipts(store, local):
    current = store.value.get('oracle_receipt_directory', 'oracle-import')
    if current not in {'oracle-import', 'oracle-import-r2'}:
        raise ValueError('NFS_RECEIPT_DIRECTORY')
    for field, directory in [('oracle_r1_failure_blob', 'oracle-import'),
                             ('oracle_receipt_blob', current)]:
        attempt = local / directory
        if field not in store.value or (attempt / 'full-state.json').exists():
            continue
        blob_hash = store.value[field]['sha256']
        if not isinstance(blob_hash, str) or len(blob_hash) != 64 or any(c not in '0123456789abcdef' for c in blob_hash):
            raise ValueError('NFS_RECEIPT_HASH')
        archive = local / ('saved-' + field + '-' + blob_hash + '.zip')
        store.get_blob(store.value[field], archive)
        with zipfile.ZipFile(archive) as z:
            if len(z.namelist()) != len(set(z.namelist())):
                raise ValueError('NFS_RECEIPT_DUPLICATE')
            for name in z.namelist():
                nfs.relative(name)
                if not name.endswith(('.json', '.jsonl')):
                    raise ValueError('NFS_RECEIPT_MEMBER')
            z.extractall(attempt)
    if current == 'oracle-import' and 'oracle_receipt_blob' in store.value:
        # Preserve the failed R1 archive in addition to append-only checkpoints.
        store.value.setdefault('oracle_r1_failure_blob', store.value['oracle_receipt_blob'])
        store.save()


def run(action='check', *, clob_batch_size=32, native_clob=True, verify_batch_rows=100):
    import dataiku
    if type(clob_batch_size) is not int or clob_batch_size not in (1, 32):
        raise ValueError('CLOB_BATCH_SIZE: use 1 or 32')
    if type(native_clob) is not bool or type(verify_batch_rows) is not int or not 20 <= verify_batch_rows <= 100:
        raise ValueError('VERIFY_CONFIG: native_clob bool / verify_batch_rows integer 20..100')
    from lawrag.pipeline.oracle_query_dataiku import DataikuClient
    from semantic_runtime.physical_mapping import SchemaMap
    if action not in {'check', 'transfer', 'load', 'status', 'load_only', 'verify'}:
        raise ValueError('NFS_ACTION')
    if dataiku.default_project_key() != 'LEGAL_RAG':
        raise ValueError('LEGAL_RAG_PROJECT_REQUIRED')
    preflight(ROOT)
    project = dataiku.api_client().get_project('LEGAL_RAG')
    cfg = config(project.get_recipe('LEGAL_02_STRUCTURE_GENOS_R1').get_settings().get_code(), 'structure')
    variables = dataiku.get_custom_variables()
    if variables.get('LEGAL_ORACLE_CONNECTION', 'AIDP') != 'AIDP':
        raise ValueError('NFS_CONNECTION_CHANGED')
    schema = SchemaMap.load(ROOT / 'client/physical_mapping.yaml',
                            expected_sha256=t.read(ROOT / 'client/MAPPING_BINDING.json')['yaml_sha256'])
    oracle = DataikuClient(dataiku.SQLExecutor2(connection='AIDP'), 'AIDP', 'LEGAL_RAG', schema_map=schema)
    binding, _ = oracle.identity()
    wire = Wire(variables['LEGAL_PIPELINE_URL'], variables['LEGAL_PIPELINE_TOKEN'])
    identity = {'mode': nfs.PROTOCOL, 'generation': GENERATION, 'database': binding,
                'service_code': EXPECTED, 'url_sha256': hashlib.sha256(wire.url.encode()).hexdigest()}
    store = ManagedJob(Scope(dataiku.Folder(cfg['structured'])), JOB_NAME, identity)
    if action == 'status':
        result = {k: store.value.get(k) for k in ('phase', 'source_counts', 'received_bytes', 'load_result', 'last_error')}
        print(json.dumps(result, ensure_ascii=False, indent=2)); return result
    parent = Path(variables.get('LEGAL_PIPELINE_SCRATCH') or tempfile.gettempdir()).expanduser().resolve()
    if not parent.is_dir():
        raise ValueError('NFS_SCRATCH_DIRECTORY_REQUIRED')
    local = parent / 'legal-existing-nfs-20261029-r1' / JOB_NAME
    try:
        info = request(store, wire, 'EXISTING_NFS_INFO')
        nfs.validate_info(info, code_sha256=EXPECTED, generation=GENERATION)
        prior = store.value.get('snapshot_sha256')
        if prior and prior != info['snapshot_sha256']:
            raise ValueError('NFS_SNAPSHOT_CHANGED')
        store.value['snapshot_sha256'] = info['snapshot_sha256']; store.save()
        if action == 'check':
            from semantic_runtime import oracle_dp_io
            local.mkdir(parents=True, exist_ok=True)
            schema.preflight(oracle_dp_io.SQL(BudgetClient(oracle, store), journal=local/'schema-check.jsonl',
                                             binding=nfs.digest(identity),
                                             seconds=min(3600, max(1, store.value['deadline']-time.time()))))
            result = {'status': 'NFS_READY_FOR_TRANSFER', 'generation': GENERATION,
                      'manifest_sha256': info['dataset_version'], 'files': len(info['files']),
                      'bytes': sum(x['bytes'] for x in info['files'].values()),
                      'free_scratch_bytes': shutil.disk_usage(parent).free,
                      'oracle_written': False, 'rebuild': False}
        else:
            local.mkdir(parents=True, exist_ok=True)
            with tracking(local, lambda status, **fields: console_event(local,status,**fields)) as progress:
                progress.deadline = store.value['deadline']
                report('RECEIVED_INPUTS_CHECK')
                receive(store, wire, info, local)
            result = {'status': 'NFS_RECEIVED_VERIFIED', 'oracle_written': False,
                      'source_counts': store.value['source_counts']}
            if action in {'load', 'load_only', 'verify'}:
                restore_receipts(store, local)
                previous = local / 'oracle-import'
                attempt = local / 'oracle-import-r2'
                try:
                    budget = BudgetClient(oracle, store)
                    budget.source_clob_batch_size = clob_batch_size
                    budget.source_native_clob = native_clob
                    budget.source_verify_batch_rows = verify_batch_rows
                    print('CLOB_READ_BATCH_SIZE=' + str(clob_batch_size), flush=True)
                    print('SOURCE_NATIVE_CLOB=' + str(native_clob) + '; VERIFY_BATCH_ROWS=' + str(verify_batch_rows), flush=True)
                    print('LOAD_INVOCATION_CAP=NONE; ORIGINAL_JOB_DEADLINE=' + str(store.value['deadline']), flush=True)
                    attempt.mkdir(parents=True, exist_ok=True)
                    with tracking(attempt, lambda status, **fields: console_event(attempt,status,**fields)) as progress:
                        progress.deadline = store.value['deadline']
                        report('ORACLE_IMPORT_PREPARATION')
                        result = full.import_generation(budget, local, target_binding=binding,
                            directory=attempt, action='publish' if action == 'load' else action, seconds=None,
                            prior_schema_failure_directory=previous if (previous/'full-state.json').exists() else None)
                    if result['status'] != ('LOADED_UNVERIFIED' if action == 'load_only' else 'FULL_DATA_VERIFIED'):
                        raise ValueError('NFS_ORACLE_NOT_COMPLETE')
                    store.value.update(phase='LOADED_UNVERIFIED' if action == 'load_only' else 'COMPLETE', load_result=result)
                finally:
                    save_receipts(store, attempt, local)
        store.save()
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return result
    except BaseException as exc:
        store.value.update(phase='STOPPED', last_error={'type': type(exc).__name__, 'code': str(exc)[:160]})
        store.save()
        print('NFS_STOPPED: 수신 데이터와 이전 기록을 보존했습니다.', flush=True)
        raise
