"""Bounded read-only SQLite samples and historical progress, never full COUNT."""
from collections import defaultdict
import gzip
import json
from pathlib import Path
import shutil
import sqlite3
import statistics
import time
from g19diag_common import canonical, error, identifier

CANDIDATES = {('navigation/navigation.sqlite', 'occurrence_keys'),
              ('glossary/dictionary.sqlite', 'entry_corpus_link'),
              ('glossary/dictionary.sqlite', 'entry_definition_link')}


def inventory(ctx):
    items = []
    for kind, spec in ctx['descriptor']['tables'].items():
        n = spec['rows']
        if type(n) is not int or n < 0: raise ValueError('PLANNED_ROWS')
        asset, table = spec.get('asset', ''), spec.get('table', '')
        items.append({'kind': kind, 'asset': asset, 'table': table, 'storage': spec.get('storage', 'derived'),
                      'rows': n, 'candidate': (asset, table) in CANDIDATES})
    return sorted(items, key=lambda i: (-i['rows'], i['kind']))


def sample_table(db, table, limit=32, seconds=2):
    identifier(table)
    started = time.perf_counter(); deadline = time.monotonic()+seconds
    db.set_progress_handler(lambda: int(time.monotonic() > deadline), 2000)
    try:
        query = 'SELECT * FROM "'+table+'" LIMIT '+str(int(limit))
        plans = [list(r) for r in db.execute('EXPLAIN QUERY PLAN '+query)]
        cursor = db.execute(query)
        columns = [d[0] for d in cursor.description]
        sizes, batch, binary = [], [], 0
        for row in cursor:
            value = {}
            for key, v in zip(columns, row):
                if isinstance(v, bytes):
                    binary += len(v); value[key] = {'binary_bytes': len(v)}
                else: value[key] = v
            raw = canonical(value).encode()
            if len(raw) > 1024**2: raise ValueError('SAMPLE_ROW_OVER_1MIB')
            sizes.append(len(raw)); batch.append(raw)
        scanned = time.perf_counter()-started
        raw = b'['+b','.join(batch)+b']'
        started = time.perf_counter(); zipped = gzip.compress(raw, compresslevel=6, mtime=0)
        compressed = time.perf_counter()-started
        return {'status': 'OK', 'sample_rows': len(sizes), 'read_and_json_seconds': scanned,
                'prefix_mean_json_bytes': statistics.mean(sizes) if sizes else None,
                'prefix_max_json_bytes': max(sizes) if sizes else None,
                'gzip_seconds': compressed, 'sample_json_bytes': len(raw), 'gzip_bytes': len(zipped),
                'binary_bytes_not_serialized': binary, 'sqlite_plan': plans,
                'scope': 'first rows, nonrandom; logical JSON only, not Oracle allocation or whole-table mean'}
    except Exception as exc:
        return {'status': 'UNMEASURED_OR_INTERRUPTED', 'error': error(exc)}
    finally:
        db.set_progress_handler(None, 0)


def local_samples(ctx, items, notify=lambda *a: None, seconds=90):
    end = time.monotonic()+seconds; result = []
    groups = defaultdict(list)
    for i in items:
        if i['table']: groups[i['asset']].append(i)
    # Original source tables are represented specially in the export manifest.
    groups.setdefault('store.sqlite', [])
    for asset, entries in groups.items():
        path = (Path(ctx['root'])/asset).resolve(strict=True)
        if Path(ctx['root']) not in path.parents: raise ValueError('ASSET_PATH')
        if time.monotonic() >= end:
            result.extend({'asset': asset, 'table': i['table'], 'status': 'BUDGET_UNMEASURED'} for i in entries)
            continue
        if any(Path(str(path)+s).exists() and Path(str(path)+s).stat().st_size for s in ('-wal', '-journal')):
            result.append({'asset': asset, 'status': 'MUTABLE_SOURCE_SKIPPED'}); continue
        before = path.stat()
        db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)
        try:
            db.execute('PRAGMA query_only=ON'); db.execute('PRAGMA cache_size=-4096')
            if asset == 'store.sqlite':
                entries = [{'table': r[0]} for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for i in entries:
                if time.monotonic() >= end:
                    result.append({'asset': asset, 'table': i['table'], 'status': 'BUDGET_UNMEASURED'}); continue
                notify('SQLite 작은 표본', asset+'/'+i['table'])
                value = sample_table(db, i['table'], seconds=min(2, end-time.monotonic()))
                result.append({'asset': asset, 'table': i['table'], **value})
        finally: db.close()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            for r in result:
                if r['asset'] == asset: r['status'] = 'SOURCE_CHANGED_SAMPLE_INVALID'
    return result


def historical_logs(folder):
    results = []
    # Log names/targets do not prove dataset identity: never merge into the live profile.
    for path in sorted(Path(folder).glob('*fresh1-*.log'), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
        groups = defaultdict(list)
        with path.open('rb') as stream: raw = stream.read(4*1024**2+1)
        partial = len(raw) > 4*1024**2
        for line in raw[:4*1024**2].splitlines():
            try: v = json.loads(line)
            except (ValueError, UnicodeError): continue
            if not isinstance(v, dict) or v.get('phase') not in ('LOAD', 'VERIFY'): continue
            if not isinstance(v.get('rows'), (int, float)) or not isinstance(v.get('elapsed_s'), (int, float)): continue
            key = (v['phase'], v.get('table', 'unknown')); seq = groups[key]
            if seq and v['rows'] < seq[-1]['rows']: groups[key] = seq = []
            if not seq or v['rows'] != seq[-1]['rows']: seq.append(v)
        for (phase, table), seq in groups.items():
            span = seq[-1]['elapsed_s']-seq[0]['elapsed_s']
            rates = [v['request_s'] for v in seq if isinstance(v.get('request_s'), (int, float))]
            results.append({'log': path.name, 'phase': phase, 'table': table, 'observations': len(seq),
                            'row_delta': seq[-1]['rows']-seq[0]['rows'], 'observed_seconds': span,
                            'rows_per_second': (seq[-1]['rows']-seq[0]['rows'])/span if span > 0 else None,
                            'observed_request_median_seconds': statistics.median(rates) if rates else None,
                            'log_truncated': partial, 'scope': 'historical observations; dataset binding unverified; not all batches'})
    return results


def resources(folder):
    disk = shutil.disk_usage(folder)
    value = {'disk_free_bytes': disk.free, 'disk_total_bytes': disk.total}
    if Path('/proc/meminfo').exists():
        mem = {s.split(':')[0]: int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines() if ':' in s}
        value.update({k: mem[k] for k in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree')})
    return value
