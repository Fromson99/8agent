"""Resumable immutable source transfer using the already-connected GENOS ORDS client."""
from __future__ import annotations

from contextlib import closing
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from semantic_runtime.physical_mapping import names

from semantic_runtime.oracle_dp_io import (
    SQL, OWNER, TABLES, COLUMNS, KEYS, DPError, BudgetPause, atomic_json, canonical,
    digest, file_sha, validate_row, check_source_tables, insert_statement, read_batch, compare_batch,
)

SOURCE = '/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation/store.sqlite'
VERSION = 'oracle-source-migration-v1'
BATCH_ROWS = 20
BATCH_BYTES = 256 * 1024
CHAIN_START = '0' * 64


def signature(path):
    s = Path(path).stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def source_binding(source):
    path = Path(source).resolve(strict=True)
    manifest = path.parent / 'manifest.json'
    if path.is_symlink() or manifest.is_symlink():
        raise DPError('SOURCE_PATH: regular files required')
    raw = manifest.read_bytes(); value = json.loads(raw)
    if value.get('schema_version') != 'term-source-generation-v2':
        raise DPError('SOURCE_SCHEMA: compact source-v2 required')
    for suffix in ('-wal', '-journal'):
        side = Path(str(path) + suffix)
        if side.exists() and side.stat().st_size:
            raise DPError('SOURCE_MUTABLE: nonempty SQLite journal')
    return {'source_path': str(path), 'dataset_version': hashlib.sha256(raw).hexdigest(),
            'source_sha256': value['store_sha256'], 'source_signature': signature(path),
            'manifest_signature': signature(manifest), 'schema': VERSION, 'owner': OWNER, 'tables': TABLES}, value


def source_open(path):
    db = sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True, timeout=5)
    db.row_factory = sqlite3.Row; db.execute('PRAGMA query_only=ON')
    return db


def unchanged(binding):
    source = Path(binding['source_path'])
    if signature(source) != binding['source_signature'] or signature(source.parent / 'manifest.json') != binding['manifest_signature']:
        raise DPError('SOURCE_CHANGED: immutable input changed; no continuation')


def source_counts(db, manifest):
    actual = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if actual != set(TABLES):
        raise DPError('SOURCE_TABLES: expected exactly three physical source tables')
    counts = {}
    for kind in TABLES:
        columns = {r[1] for r in db.execute(f'PRAGMA table_info({kind})')}
        required = {'json' if c == 'SOURCE_JSON' else c.lower() for c in COLUMNS[kind] if c != 'DATASET_VERSION'}
        if columns != required:
            raise DPError('SOURCE_COLUMNS: source projection differs')
        counts[kind] = db.execute(f'SELECT COUNT(*) FROM {kind}').fetchone()[0]
        recorded = manifest['counts']['source_block' if kind == 'block_payload' else kind]
        if counts[kind] != recorded:
            raise DPError('SOURCE_COUNT: manifest differs from SQLite')
    return counts


def source_batch(db, kind, version, cursor=None, *, batch_rows=BATCH_ROWS):
    if type(batch_rows) is not int or not 1 <= batch_rows <= 100:
        raise DPError('SOURCE_BATCH_ROWS: expected integer 1..100')
    keys = [c.lower() for c in KEYS[kind] if c != 'DATASET_VERSION']
    where = f'WHERE ({",".join(keys)}) > ({",".join("?" for _ in keys)})' if cursor else ''
    statement = f'SELECT * FROM {kind} {where} ORDER BY {",".join(keys)} LIMIT {batch_rows}'
    result, size = [], 0
    for record in db.execute(statement, cursor or []):
        row = {c: version if c == 'DATASET_VERSION' else record['json' if c == 'SOURCE_JSON' else c.lower()] for c in COLUMNS[kind]}
        validate_row(kind, row)
        n = len(canonical(row).encode())
        if result and size + n > BATCH_BYTES:
            break
        result.append(row); size += n
    return result


def extend_chain(previous, rows):
    for row in rows:
        previous = digest([previous, row])
    return previous


def transfer(client, source=SOURCE, *, target_binding, directory, action='check',
             seconds=3600, max_calls=1000000, max_batches=None):
    if action not in ('check', 'run', 'verify'):
        raise DPError('ACTION: use check, run or verify')
    binding, manifest = source_binding(source)
    binding['target_binding'] = target_binding
    job_id = digest(binding)[:24]
    folder = Path(directory) / job_id; folder.mkdir(parents=True, exist_ok=True)
    receipt = folder / 'state.json'
    with (folder / 'job.lock').open('a') as lock:
        try: fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise DPError('IN_PROGRESS: this source/target migration is already running') from None
        state = json.loads(receipt.read_text()) if receipt.exists() else {
            'binding': binding, 'status': 'NEW', 'created_at': time.time(),
            'deadline': time.time() + 7 * 86400, 'tables': {}, 'attempts': 0}
        if state['binding'] != binding:
            raise DPError('STATE_BINDING: source/target changed')
        state['attempts'] += 1
        atomic_json(receipt, state)
        sql = SQL(client, journal=folder/'calls.jsonl', binding=target_binding,
                  seconds=max(0, min(seconds, state['deadline'] - time.time())), max_calls=max_calls)
        def status(value, **fields):
            state.update(status=value, **fields); atomic_json(receipt, state)
        print('DP_MIGRATION_RECEIPT=' + str(receipt.resolve()), flush=True)
        print('DATASET_VERSION=' + binding['dataset_version'], flush=True)
        try:
            check_source_tables(sql)
            with closing(source_open(binding['source_path'])) as db:
                counts = source_counts(db, manifest)
                print('SOURCE_COUNTS=' + canonical(counts), flush=True)
                unchanged(binding)
                if action == 'check':
                    sql.event('CHECKED', source_counts=counts)
                    return {'status': 'CHECKED_NO_WRITES', 'counts': counts, 'receipt': str(receipt),
                            'dataset_version': binding['dataset_version']}
                if not state.get('source_hash_verified'):
                    if file_sha(binding['source_path']) != binding['source_sha256']:
                        raise DPError('SOURCE_HASH: SQLite differs from generation manifest')
                    unchanged(binding); state['source_hash_verified'] = True; atomic_json(receipt, state)
                batches = 0
                batch_rows = getattr(client, 'source_verify_batch_rows', BATCH_ROWS) if action == 'verify' else BATCH_ROWS
                for kind in TABLES:
                    if action == 'verify':
                        progress = {'cursor': None, 'rows': 0, 'chain': CHAIN_START}
                    else:
                        progress = state['tables'].setdefault(kind, {'cursor': None, 'rows': 0, 'chain': CHAIN_START})
                    table_started = time.monotonic()
                    starting_rows = progress['rows']
                    while batch := source_batch(db, kind, binding['dataset_version'], progress['cursor'], batch_rows=batch_rows):
                        if max_batches is not None and batches >= max_batches:
                            raise BudgetPause('BATCH_PAUSED: explicit batch limit reached')
                        unchanged(binding)
                        found = read_batch(sql, kind, batch)
                        missing = compare_batch(kind, batch, found, require_all=False)
                        if missing:
                            if action == 'verify': raise DPError('VERIFY_MISSING: target lacks source rows')
                            status('WRITE_STARTED', pending={'kind': kind, 'batch_sha256': digest(batch), 'rows': len(batch)})
                            statement, binds = insert_statement(kind, batch, sql=sql)
                            sql.request(statement, binds, write=True)
                            compare_batch(kind, batch, read_batch(sql, kind, batch))
                        unchanged(binding)
                        progress['rows'] += len(batch)
                        progress['chain'] = extend_chain(progress['chain'], batch)
                        progress['cursor'] = [batch[-1][c] for c in KEYS[kind] if c != 'DATASET_VERSION']
                        batches += 1
                        if action != 'verify': status('RUNNING', pending=None)
                        sql.event('BATCH_VERIFIED', kind=kind, rows=progress['rows'], chain=progress['chain'], action=action)
                        if batches == 1 or batches % 20 == 0:
                            elapsed = max(time.monotonic() - table_started, 0.000001)
                            rate = (progress['rows'] - starting_rows) / elapsed
                            eta = max(0, counts[kind] - progress['rows']) / rate
                            print(f'{kind}: {progress["rows"]}/{counts[kind]} verified; SQL calls={sql.calls}; '
                                  f'rows_per_second={rate:.1f}; table_eta_seconds={eta:.0f}', flush=True)
                    physical=names(sql,kind,OWNER+'.'+TABLES[kind])
                    rows = sql.query(f'SELECT COUNT(*) AS N FROM {physical.table} WHERE {physical.c("DATASET_VERSION") }=:v',
                                     [('v', binding['dataset_version'], 'VARCHAR2')], limit=1)
                    if len(rows) != 1 or int(rows[0]['N']) != counts[kind] or progress['rows'] != counts[kind]:
                        raise DPError('TARGET_COUNT: missing/extra rows for the selected version')
                    previous = state['tables'].get(kind)
                    if action == 'verify' and previous and previous['chain'] != progress['chain']:
                        raise DPError('VERIFY_CHAIN: source content differs from recorded transfer')
                unchanged(binding)
                if file_sha(binding['source_path']) != binding['source_sha256']:
                    raise DPError('SOURCE_HASH: source changed during transfer')
                unchanged(binding)
                status('VERIFIED' if action == 'verify' else 'SOURCE_COMPLETE', counts=counts, pending=None,
                       completed_at=time.time(), calls=sql.calls)
                print('SOURCE_TRANSFER_VERIFIED=3/3', flush=True)
                print('전체 원문 이관 확인. 색인 게시와 DP 서빙 전환은 별도 단계입니다.', flush=True)
                return {'status': state['status'], 'counts': counts, 'receipt': str(receipt),
                        'dataset_version': binding['dataset_version']}
        except BudgetPause as exc:
            status('PAUSED', reason=str(exc), calls=sql.calls)
            print(str(exc), flush=True)
            return {'status': 'PAUSED', 'receipt': str(receipt), 'calls': sql.calls}
        except Exception as exc:
            message = str(exc) if isinstance(exc, DPError) else type(exc).__name__
            status('FAILED', failure={'at': time.time(), 'error': message}, calls=sql.calls)
            sql.event('MIGRATION_FAILED', error=message)
            raise DPError(message + '; checkpoint retained at ' + str(receipt)) from None


def from_notebook(desk, source=SOURCE, *, action='check', seconds=3600, max_batches=None):
    check = desk.require_connection()
    if desk.recovery_required:
        raise DPError('R6_RECOVERY: inspect the pre-existing R6 write hold before starting a new migration')
    # Reuse the authenticated SDK client. The migration has its own durable budgets/checkpoints;
    # the interactive screen-check 500-call/180-second limits are not changed or reset.
    client = check.client
    if getattr(client, 'deadline', None) is not None:
        raise DPError('R6_BUSY: another R6 cell is executing')
    return transfer(client, source, target_binding=desk.binding(),
                    directory=Path(desk.settings.get('log_dir') or './ords_notebook_logs')/'legal_full_migration',
                    action=action, seconds=seconds, max_batches=max_batches)
