"""Observe the existing serving process without importing or warming cache pools.

No SQL, model calls, cache clearing, full dataset hashing, or source writes.
Query/scope fingerprints permit comparison without returning their contents.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time

REVISION = 'genos-cache-diagnostics-20261008-r1'
ENV_NAMES = (
    'GENOS_GENERATION', 'GENOS_DATA_ROOT', 'GENOS_RUNTIME_DIR', 'GENOS_STATE_DIR',
    'GENOS_RESIDENT_DATA', 'GENOS_RESIDENT_CACHE_MIB', 'GENOS_RESIDENT_CACHE_DIR',
    'GENOS_RUNTIME_CACHE_MIB', 'GENOS_RUNTIME_CACHE_ENTRIES', 'GENOS_AUTO_WARMUP',
    'GENOS_RAG_IMPLEMENTATION', 'GENOS_MAIN_MODE', 'TEAM_ID', 'AD_WORKSPACE',
)
MODULES = (
    'resident_data', 'runtime_cache', 'unit_fulltext', 'fulltext', 'term_index',
    'query_latency', 'document_agent', 'legal_agent.law_candidates',
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False).encode()).hexdigest()


def small_file(path):
    path = Path(path)
    try:
        if path.is_symlink():
            return {'status': 'SYMLINK_NOT_READ'}
        before = path.stat()
        if before.st_size > 4 * 1024 * 1024:
            return {'status': 'SIZE_LIMIT', 'bytes': before.st_size}
        raw = path.read_bytes()
        after = path.stat()
        unchanged = (before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        return {'status': 'READ' if unchanged else 'CHANGED_DURING_READ',
                'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    except OSError as exc:
        return {'status': 'UNAVAILABLE', 'errno': exc.errno}


def module_row(name, module):
    path = getattr(module, '__file__', None)
    return {'module': name, 'revision': getattr(module, 'REVISION', None),
            'path': str(path) if path else None,
            'disk_source': small_file(path) if path else {'status': 'NO_FILE'}}


def locked_snapshot(obj, callback):
    lock = getattr(obj, 'lock', None)
    if lock is None or not lock.acquire(timeout=0.05):
        return {'status': 'BUSY_OR_UNSUPPORTED'}
    try:
        return callback()
    finally:
        lock.release()


def resident_snapshot(pool):
    def read():
        entries = []
        for key, value in pool.entries.items():
            # ResidentPool key = absolute original path, file signature, expected SHA.
            entries.append({'path': key[0], 'dataset_bytes': key[1][2],
                            'source_signature': list(key[1]), 'expected_sha256': key[2],
                            'storage': value['storage']})
        return {'status': 'OBSERVED', 'effective_mode': pool.mode,
                'memory_budget_bytes': pool.max_memory_bytes,
                'memory_reserved_bytes': pool.memory_bytes, 'local_bytes': pool.local_bytes,
                'local_root': str(pool.local_root) if pool.local_root else None,
                'pending_builds': len(pool.pending), 'entry_count': len(entries),
                'entries': entries}
    result = locked_snapshot(pool, read)
    # Stat only after releasing the serving pool lock; never read large SQLite files.
    for row in result.get('entries', []):
        try:
            stat = Path(row['path']).stat()
            current = [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
            row['original_signature_unchanged'] = current == row['source_signature']
        except OSError as exc:
            row['original_stat_errno'] = exc.errno
    return result


def result_snapshot(cache):
    def read():
        rows = list(cache.entries.items())
        # Values are immutable after admission. ProcessCache lookup alone mutates LRU.
        return {'status': 'OBSERVED', 'budget_bytes': cache.max_bytes,
                'max_entries': cache.max_entries, 'bytes': cache.bytes,
                'entry_count': len(rows), 'evictions': cache.evictions,
                'pending_builds': len(cache.pending), '_rows': rows[-24:]}
    result = locked_snapshot(cache, read)
    matches = []
    kinds = {}
    for key, (value, size) in result.pop('_rows', []):
        kind = key[0] if isinstance(key, tuple) and key else 'unknown'
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == 'matches' and len(key) == 5:
            namespace, terms, scope, row_limit = key[1:]
            matches.append({'query_fingerprint': digest(list(terms)),
                            'term_count': len(terms), 'scope_fingerprint': digest(sorted(scope)),
                            'scope_count': len(scope), 'index_sha256': namespace[-2],
                            'row_limit': row_limit, 'overflow_marker': value is None,
                            'cached_bytes': size,
                            'match_count': None if value is None else sum(len(v) for v in value['hits'].values())})
    result.update(recent_entry_kinds=kinds, recent_matches=matches,
                  recent_entry_limit=24, lookup_hit_count='NOT_INSTRUMENTED',
                  rejected_entry_count='NOT_INSTRUMENTED')
    return result


def resources():
    result = {}
    for name in ('memory.max', 'memory.current', 'memory.events', 'cpu.max', 'cpu.stat'):
        try:
            result[name] = (Path('/sys/fs/cgroup') / name).read_text()[:4096].strip()
        except OSError:
            result[name] = None
    try:
        result['mem_available_kib'] = next(int(row.split()[1]) for row in
            Path('/proc/meminfo').read_text().splitlines() if row.startswith('MemAvailable:'))
    except (OSError, StopIteration, ValueError):
        result['mem_available_kib'] = None
    return result


def collect(service_globals):
    started = time.monotonic()
    root = Path(service_globals['_ROOT'])
    report = {'response_schema': REVISION, 'inspection_scope': 'existing-code-serving-process',
              'worker': {'worker_id': service_globals['_PROCESS_INSTANCE_ID'],
                         'worker_id_origin': 'service.py module-level uuid.uuid4().hex',
                         'pid': os.getpid(), 'hostname': socket.gethostname(),
                         'uid': os.getuid(), 'gid': os.getgid()},
              'warmup': dict(service_globals['_warmup']()['body']),
              'environment': {name: os.environ.get(name) for name in ENV_NAMES},
              'resources': resources(), 'code_root': str(root),
              'service_disk_source': small_file(service_globals['__file__']),
              'modules': [], 'resident_pools': [], 'result_caches': [],
              'limitations': ['Disk SHA identifies the file currently on disk, not pre-change in-memory code.',
                              'Retained entries prove retention, not an individual SQL lookup hit.',
                              'No query, source body, credential, SQL execution, or full dataset hash is returned.']}
    app = service_globals.get('_APP')
    pipeline = getattr(getattr(app, 'state', None), 'pipeline', None)
    store = getattr(pipeline, 'store', None)
    path = getattr(store, 'path', None)
    manifest = getattr(store, 'manifest', {}) or {}
    agent = getattr(pipeline, 'term_agent', None)
    profile = getattr(agent, 'profile', {}) or {}
    model = profile.get('model_binding', {}) or {}
    code_root = Path(getattr(getattr(pipeline, 'contracts', None), 'root', root))
    report['execution'] = {'profile_fingerprint': digest(profile) if profile else None,
                           'model_binding': {key: model.get(key) for key in
                                             ('provider', 'model', 'endpoint_identity', 'adapter_version')},
                           'max_output_tokens': profile.get('max_output_tokens')}
    report['selection'] = {'app_loaded': app is not None,
                           'generation_path': str(path) if path else None,
                           'generation_id': manifest.get('generation_id'),
                           'source_store_sha256': manifest.get('store_sha256'),
                           'generation_manifest': small_file(Path(path) / 'manifest.json') if path else None,
                           'index_bindings': {key: manifest.get(key) for key in ('navigation', 'fulltext')},
                           'profile_disk_source': small_file(code_root / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')}
    for name, module in list(sys.modules.items()):
        if not module or not any(name == 'semantic_runtime.' + suffix or
                (name.startswith('_lawrag_release_') and name.endswith('.' + suffix)) for suffix in MODULES):
            continue
        report['modules'].append(module_row(name, module))
        if name.endswith('.resident_data') and hasattr(module, 'POOL'):
            report['resident_pools'].append({'module': name, **resident_snapshot(module.POOL)})
        if name.endswith('.runtime_cache') and hasattr(module, 'CACHE'):
            report['result_caches'].append({'module': name, **result_snapshot(module.CACHE)})
    report['elapsed_ms'] = round((time.monotonic() - started) * 1000, 3)
    return report
