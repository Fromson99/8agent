"""Fast operator plan/apply/rollback of filename-version search exclusions."""
import argparse
from collections import defaultdict
from contextlib import closing
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import sys
import unicodedata
import uuid

from semantic_runtime.contracts import digest, sha
from semantic_runtime.search_selection import VERSION, selection_path, file_state

DATE = re.compile(r'^(.*?)\s*\(([0-9]{8}|[0-9]{6})\)$')
COPY = re.compile(r'\s*\([1-9][0-9]{0,2}\)$')


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def atomic(path, raw):
    file_state(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def legacy_plan(generation):
    """Scan document metadata only. Do not load source bodies or hash large DBs.

    Runtime/gate still verify the original immutable database pins. A missing or
    ambiguous folder/date never authorizes excluding another document.
    """
    generation = Path(generation).resolve(strict=True)
    manifest_path = generation / 'manifest.json'
    manifest_hash = sha(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('schema_version') not in ('term-source-generation-v1', 'term-source-generation-v2'):
        raise ValueError('unsupported source generation')
    database = generation / 'store.sqlite'
    if Path(str(database)+'-wal').exists():
        raise ValueError('live WAL source database is not an immutable generation')
    before = file_state(database)
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)) as db:
        rows = list(db.execute("SELECT document_id,name,source_artifact_sha256,"
            "json_extract(json,'$.document_metadata'),json_extract(json,'$.origin'),"
            "json_extract(json,'$.document_category'),json_extract(json,'$.document_kind') "
            "FROM document ORDER BY document_id"))
        known = {r[0]: r for r in rows}
        if not rows: raise ValueError('source generation is empty')
        groups, memberships, warnings = defaultdict(list), defaultdict(list), []
        protected = set()
        for did, name, artifact, raw, origin_raw, category, kind in rows:
            metadata = json.loads(raw) if raw else {}
            metadata = metadata or {}
            origin = json.loads(origin_raw) if origin_raw else {}
            locations = [metadata, *metadata.get('aliases', [])]
            if not metadata.get('relative_path') and origin.get('status') == 'verified':
                if origin.get('source_artifact_sha256') != artifact:
                    raise ValueError('origin source hash mismatch')
                locations[0] = {**metadata, 'relative_path': origin.get('raw_relative_path')}
            seen = set()
            for location in locations:
                if not isinstance(location, dict):
                    protected.add(did); warnings.append({'document_id': did, 'reason': 'invalid_location'}); continue
                relative = location.get('relative_path')
                source = location.get('source_category') or metadata.get('source_category') or category
                if source is None:
                    source = {'internal_regulation': 'internal', 'internal_rule': 'internal',
                              'internal': 'internal'}.get(kind or metadata.get('kind'))
                if source is None and isinstance(relative, str) and relative.startswith('internal/'):
                    source = 'internal'
                if source != 'internal':
                    protected.add(did); continue
                if not isinstance(relative, str) or not relative or '\\' in relative:
                    protected.add(did); warnings.append({'document_id': did, 'reason': 'missing_relative_path'}); continue
                p = PurePosixPath(relative)
                if p.is_absolute() or '..' in p.parts:
                    protected.add(did); warnings.append({'document_id': did, 'reason': 'invalid_relative_path'}); continue
                if str(p) in seen: continue
                seen.add(str(p))
                stem = COPY.sub('', unicodedata.normalize('NFC', p.stem)).strip()
                match = DATE.fullmatch(stem)
                title, date, valid = stem, None, True
                if match:
                    title = match[1].strip(); date = match[2]
                    try:
                        if len(date) != 8: raise ValueError('short date')
                        datetime.strptime(date, '%Y%m%d')
                    except ValueError:
                        valid = False
                key = (str(p.parent), location.get('team') or metadata.get('team') or '',
                       location.get('raw_role') or metadata.get('raw_role') or 'body', title)
                item = {'document_id': did, 'path': str(p), 'date': date, 'valid': valid,
                        'source_artifact_sha256': artifact, 'format': p.suffix.lower()}
                groups[key].append(item); memberships[did].append(item)
        selected_groups, older = [], set()
        for key, items in sorted(groups.items()):
            if not any(x['date'] is not None for x in items): continue
            if any(not x['valid'] or x['date'] is None for x in items):
                warnings.append({'folder': key[0], 'title': key[-1], 'reason': 'ambiguous_or_invalid_date',
                                 'document_ids': sorted({x['document_id'] for x in items})})
                continue
            newest = max(x['date'] for x in items)
            winners = [x for x in items if x['date'] == newest]
            formats = defaultdict(set)
            for x in winners: formats[x['format']].add(x['source_artifact_sha256'])
            if any(len(v)>1 for v in formats.values()):
                warnings.append({'folder': key[0], 'title': key[-1], 'reason': 'conflicting_latest',
                                 'document_ids': sorted({x['document_id'] for x in items})}); continue
            if any(db.execute('SELECT 1 FROM source_block WHERE document_id=? LIMIT 1',
                              (x['document_id'],)).fetchone() is None for x in winners):
                warnings.append({'folder': key[0], 'title': key[-1], 'reason': 'latest_has_no_source_blocks'}); continue
            old = [x for x in items if x['date'] < newest]
            if not old: continue
            older.update((x['document_id'], x['path']) for x in old)
            selected_groups.append({'folder': key[0], 'team': key[1], 'role': key[2], 'title': key[3],
                'latest_date': newest, 'latest_document_ids': sorted({x['document_id'] for x in winners}),
                'older_document_ids': sorted({x['document_id'] for x in old})})
        excluded = []
        for did in sorted(memberships):
            old_locations = [x for x in memberships[did] if (did, x['path']) in older]
            if not old_locations: continue
            if did in protected or len(old_locations) != len(memberships[did]):
                warnings.append({'document_id': did, 'reason': 'shared_document_still_current_or_ambiguous'}); continue
            excluded.append({'document_id': did, 'source_artifact_sha256': known[did][2],
                             'paths': sorted(x['path'] for x in old_locations),
                             'reason': 'superseded_filename_version'})
    if before != file_state(database) or sha(manifest_path) != manifest_hash:
        raise ValueError('generation changed during metadata scan')
    return {'schema_version': VERSION, 'generation_path': str(generation),
            'generation_id': manifest['generation_id'], 'manifest_sha256': manifest_hash,
            'store_sha256': manifest['store_sha256'], 'metadata_sha256': digest(rows),
            'policy': 'same-folder-title-eight-digit-filename-date; preserve-ambiguous; not-effective-date',
            'excluded': excluded, 'groups': selected_groups, 'warnings': warnings,
            'counts': {'physical_documents': len(rows), 'excluded_documents': len(excluded),
                       'searchable_documents': len(rows)-len(excluded)},
            'source_database_modified': False, 'index_rebuilt': False, 'model_calls': 0}


def plan(generation, *, latest=False, exceptions=None):
    if not latest: return legacy_plan(generation)
    from semantic_runtime.filename_versions import inventory_generation, select, latest_marks, load_exceptions, DEFAULT_EXCEPTIONS
    generation = Path(generation).resolve(strict=True)
    path = Path(exceptions or DEFAULT_EXCEPTIONS).resolve(strict=True)
    config, config_hash = load_exceptions(path)
    rows, binding = inventory_generation(generation)
    events = []; selected = select(rows, config, events); marks = latest_marks(selected)
    if sha(path) != config_hash: raise ValueError('exceptions changed during planning')
    excluded = [dict(document_id=r['document_id'], source_artifact_sha256=r['source_artifact_sha256'],
                     reason='not_latest_selected', paths=[v['path'] for v in r['locations']]) for r in marks if not r['is_latest']]
    return {'schema_version': 'filename-search-selection-v2', 'generation_path': str(generation),
        'generation_id': binding['generation_id'], 'manifest_sha256': binding['manifest_sha256'],
        'store_sha256': binding['store_sha256_declared'], 'metadata_sha256': binding['metadata_sha256'],
        'policy': 'user-approved-retained-set-latest-v2', 'exceptions': {'path': str(path), 'sha256': config_hash, 'value': config},
        'excluded': excluded, 'latest_documents': marks, 'exception_results': events,
        'counts': {'physical_documents': binding['total_physical_documents'], 'internal_documents': len(marks),
            'excluded_documents': len(excluded), 'latest_internal_documents': len(marks)-len(excluded),
            'searchable_documents': binding['total_physical_documents']-len(excluded)},
        'source_database_modified': False, 'index_rebuilt': False, 'model_calls': 0}


def activate(value):
    generation = Path(value['generation_path'])
    from semantic_runtime.search_selection import runtime_binding
    if runtime_binding(generation)[0] != selection_path(generation):
        raise ValueError('code-bundled selection is active; update the DEV selection bundle and redeploy')
    if plan(generation, latest=value.get('schema_version') == 'filename-search-selection-v2',
            exceptions=value.get('exceptions', {}).get('path')) != value:
        raise ValueError('metadata/plan changed; create and inspect a fresh plan')
    target = selection_path(generation)
    file_state(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        raw = encode(value)
        previous = target.read_bytes() if target.exists() else None
        if previous == raw:
            return {'state': 'ALREADY_APPLIED', 'selection_sha256': digest(value), 'path': str(target)}
        receipt = target.parent / 'receipts' / (target.stem+'-'+uuid.uuid4().hex)
        receipt.mkdir(parents=True)
        if previous is not None: atomic(receipt/'before.json', previous)
        atomic(receipt/'after.json', raw)
        record = {'state': 'PREPARED', 'target': str(target), 'generation': str(generation),
                  'before_sha256': hashlib.sha256(previous).hexdigest() if previous is not None else None,
                  'after_sha256': hashlib.sha256(raw).hexdigest(), 'selection_sha256': digest(value)}
        atomic(receipt/'receipt.json', encode(record))
        try:
            atomic(target, raw)
            from semantic_runtime.storage import Store
            with closing(Store(generation, verify=False)) as store:
                if store.db.execute('SELECT count(*) FROM document').fetchone()[0] != value['counts']['searchable_documents']:
                    raise ValueError('visible document count mismatch')
                store.check_unchanged()
        except BaseException:
            if previous is None: target.unlink(missing_ok=True)
            else: atomic(target, previous)
            record['state'] = 'FAILED_RESTORED'; atomic(receipt/'receipt.json', encode(record))
            raise
        record['state'] = 'APPLIED_RESTART_REQUIRED'
        atomic(receipt/'receipt.json', encode(record))
        return {**record, 'receipt': str(receipt/'receipt.json'), 'counts': value['counts']}


def rollback(receipt_path):
    receipt_path = Path(receipt_path).resolve(strict=True)
    record = json.loads(receipt_path.read_text()); target = Path(record['target'])
    from semantic_runtime.search_selection import runtime_binding
    if runtime_binding(record['generation'])[0] != selection_path(record['generation']):
        raise ValueError('code-bundled selection is active; use its code deployment rollback')
    if target != selection_path(record['generation']): raise ValueError('receipt target mismatch')
    receipt_path.relative_to(target.parent/'receipts')
    with target.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = sha(target) if file_state(target) is not None else None
        if current == record['before_sha256']:
            record['state'] = 'RESTORED_RESTART_REQUIRED'
        elif current != record['after_sha256']:
            raise ValueError('selection changed since this receipt; rollback refused')
        else:
            if record['before_sha256'] is None: target.unlink()
            else:
                before = receipt_path.parent/'before.json'
                if sha(before) != record['before_sha256']: raise ValueError('rollback snapshot changed')
                atomic(target, before.read_bytes())
            record['state'] = 'RESTORED_RESTART_REQUIRED'
        atomic(receipt_path, encode(record))
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['plan', 'apply', 'status', 'rollback'])
    p.add_argument('--generation', type=Path)
    p.add_argument('--plan', type=Path)
    p.add_argument('--receipt', type=Path)
    p.add_argument('--latest', action='store_true', help='Apply approved R3 retained selection with latest marks')
    p.add_argument('--exceptions', type=Path)
    a = p.parse_args(argv)
    if a.action == 'rollback':
        if a.receipt is None: p.error('--receipt required')
        value = rollback(a.receipt)
    elif a.action == 'apply':
        if a.plan is None: p.error('--plan required')
        value = activate(json.loads(a.plan.read_text()))
    else:
        if a.generation is None: p.error('--generation required')
        if a.action == 'plan':
            value = plan(a.generation, latest=a.latest, exceptions=a.exceptions)
            if a.plan is None: p.error('--plan output required')
            raw = encode(value)
            if a.plan.exists() and a.plan.read_bytes() != raw:
                raise ValueError('plan already exists with different data; choose another plan path')
            atomic(a.plan, raw)
        else:
            from semantic_runtime.storage import Store
            with closing(Store(a.generation, verify=False)) as store:
                value = {'state': 'ACTIVE' if store.selection.value is not None else 'NOT_APPLIED',
                         'selection_sha256': store.selection.fingerprint,
                         'excluded_documents': len(store.selection.excluded),
                         'searchable_documents': store.db.execute('SELECT count(*) FROM document').fetchone()[0]}
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print('SEARCH_SELECTION_FAILED: '+str(exc), file=sys.stderr)
        raise SystemExit(1)
