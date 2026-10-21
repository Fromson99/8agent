"""Explicit development reset + bounded insert-only load of the existing ZIP.

Uses the maintained generation/projection/encoding contracts. Normal loading
does not read existing bodies. Only an uncertain last transaction is reconciled.
Count confirmation is intentionally NOT called full-content verification.
"""
import base64
import hashlib
import json
from pathlib import Path
import time
import zlib

from semantic_runtime import oracle_dp_io as io, oracle_dp_assets as assets, oracle_query_catalog as q
from . import oracle_full_package as full, oracle_query_package as transport
from . import oracle_migration as migration, oracle_query_publish as projection
from .oracle_transfer_progress import tracking, report, check
from .oracle_import_stop import guard

REVISION = 'oracle-clean-import-preserve-controls-v1'
ROWS = 100
BYTES = 512*1024
MAX_ROW = 8*1024**2
# Only these fixed tables may be cleared; child tables precede their parents.
TABLES = (q.ROW, q.RELEASE, assets.PART_TABLE, assets.RELEASE_TABLE,
          'SIDDA.LEGAL_SRC_BLOCK_PAYLOAD_A', 'SIDDA.LEGAL_SRC_SOURCE_UNIT_A', 'SIDDA.LEGAL_SRC_DOCUMENT_A')
QUERY_COLS = ('RELEASE_ID','KIND','ROW_ID','DOCUMENT_ID','LOOKUP_ID','OWNER_ID','TARGET_ID','ROW_SHA256','VALUE_JSON')
PART_COLS = ('ASSET_SHA256','PART_NO','RAW_BYTES','PART_SHA256','DATA_B64')


def table_counts(sql):
    rows = sql.query(' UNION ALL '.join(
        f"SELECT '{t}' AS TABLE_NAME,COUNT(*) AS N FROM {t}" for t in TABLES), limit=len(TABLES))
    result = {r['TABLE_NAME']: r['N'] for r in rows}
    if len(rows) != len(TABLES) or set(result) != set(TABLES) or any(type(n) is not int or n < 0 for n in result.values()):
        raise io.DPError('CLEAN_COUNTS: malformed count response')
    return result


def schema(sql):
    io.check_source_tables(sql)
    result = projection.schema(sql, create=False, allow_missing_lookup_indexes=True)
    if result['status'] != 'READY':
        raise io.DPError('CLEAN_SCHEMA: '+str(result['missing']))
    for table, columns in [(assets.PART_TABLE, PART_COLS),
                           (assets.RELEASE_TABLE, ('RELEASE_ID','DATASET_VERSION','RELEASE_JSON'))]:
        sql.query(f'SELECT {",".join(columns)} FROM {table} WHERE 1=0')
        keys = sql.query('SELECT k.COLUMN_NAME,k.POSITION,c.STATUS,c.VALIDATED FROM ALL_CONSTRAINTS c '
            'JOIN ALL_CONS_COLUMNS k ON k.OWNER=c.OWNER AND k.CONSTRAINT_NAME=c.CONSTRAINT_NAME '
            "WHERE c.OWNER='SIDDA' AND c.CONSTRAINT_TYPE='P' AND c.TABLE_NAME=:table_name ORDER BY k.POSITION",
            [('table_name',table.split('.')[1],'VARCHAR2')],limit=10)
        expected = ('ASSET_SHA256','PART_NO') if table==assets.PART_TABLE else ('RELEASE_ID',)
        if keys != [{'COLUMN_NAME':c,'POSITION':i,'STATUS':'ENABLED','VALIDATED':'VALIDATED'}
                    for i,c in enumerate(expected,1)]:
            raise io.DPError('CLEAN_ASSET_PK: enabled validated key required')
    names = ','.join("'"+t.split('.')[1]+"'" for t in TABLES)
    # The known ACTIVE FK is checked by projection.schema and must remain empty.
    # Other external references/triggers may not expand the seven-table scope.
    outside = sql.query("SELECT c.OWNER,c.TABLE_NAME FROM ALL_CONSTRAINTS c JOIN ALL_CONSTRAINTS p "
        "ON p.OWNER=c.R_OWNER AND p.CONSTRAINT_NAME=c.R_CONSTRAINT_NAME "
        f"WHERE c.CONSTRAINT_TYPE='R' AND c.STATUS='ENABLED' AND p.OWNER='SIDDA' AND p.TABLE_NAME IN ({names}) "
        f"AND (c.OWNER<>'SIDDA' OR c.TABLE_NAME NOT IN ({names})) "
        "AND NOT (c.OWNER='SIDDA' AND c.TABLE_NAME='LEGAL_RAG_QUERY_ACTIVE_A' "
        "AND p.TABLE_NAME='LEGAL_RAG_QUERY_RELEASE_A')", limit=100)
    triggers = sql.query("SELECT OWNER,TABLE_NAME,TRIGGER_NAME FROM ALL_TRIGGERS "
        f"WHERE TABLE_OWNER='SIDDA' AND TABLE_NAME IN ({names}) AND STATUS='ENABLED'", limit=100)
    if outside or triggers:
        raise io.DPError('CLEAN_SCHEMA_SIDE_EFFECT: external foreign key or enabled trigger; inspect before reset')
    return result


def batches(rows):
    batch, size = [], 0
    for row in rows:
        n = len(io.canonical(row).encode())
        if n > MAX_ROW:
            raise io.DPError('CLEAN_ROW_SIZE: single row exceeds 8MiB; preserve input, no truncation')
        if batch and (len(batch) >= ROWS or size+n > BYTES):
            check()
            yield batch
            batch, size = [], 0
        batch.append(row); size += n
    if batch:
        yield batch


def insert_sql(table, columns, kinds, rows, *, verify_only=False):
    if table not in TABLES or not rows or len(rows) > ROWS:
        raise io.DPError('CLEAN_WRITE_SCOPE')
    statements = ['DECLARE n NUMBER; BEGIN'] if verify_only else ['BEGIN ']
    binds = []
    for i, row in enumerate(rows):
        if set(row) != set(columns):
            raise io.DPError('CLEAN_COLUMNS')
        expressions = {}
        for j, (col, kind) in enumerate(zip(columns, kinds)):
            value = row[col]
            if value is None:
                expressions[col] = 'NULL'
            elif kind == 'CLOB' and value == '':
                expressions[col] = 'EMPTY_CLOB()'
            else:
                name = f'r{i}_{j}'
                expressions[col] = ':'+name
                binds.append((name, value, kind))
        if verify_only:
            same = []
            for col, kind in zip(columns, kinds):
                v, expr = row[col], expressions[col]
                same.append(f'{col} IS NULL' if v is None else
                    f'{col} IS NOT NULL AND DBMS_LOB.GETLENGTH({col})=0' if kind == 'CLOB' and v == '' else
                    f'DBMS_LOB.GETLENGTH({col})={io.units(v)} AND DBMS_LOB.COMPARE({col},{expr})=0' if kind == 'CLOB' else
                    f'UTL_RAW.CAST_TO_RAW({col})=UTL_RAW.CAST_TO_RAW({expr})' if kind == 'VARCHAR2' else f'{col}={expr}')
            statements += [f'SELECT COUNT(*) INTO n FROM {table} WHERE '+' AND '.join(same)+';',
                "IF n<>1 THEN RAISE_APPLICATION_ERROR(-20061,'CLEAN_RECOVERY_CONFLICT'); END IF;"]
        else:
            statements.append(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join(expressions[c] for c in columns)});')
    statements.append('COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
    return '\n'.join(statements), binds


def existing(sql, table, keys, rows, kinds_by_col):
    clauses, binds = [], []
    for i, row in enumerate(rows):
        terms = []
        for j, col in enumerate(keys):
            name = f'k{i}_{j}'
            terms.append(f'{col}=:{name}')
            binds.append((name, row[col], kinds_by_col[col]))
        clauses.append(f'SELECT {i} AS I,COUNT(*) AS N FROM {table} WHERE '+' AND '.join(terms))
    result = sql.query(' UNION ALL '.join(clauses), binds, limit=len(rows))
    values = {r['I']: r['N'] for r in result}
    if (len(result) != len(rows) or set(values) != set(range(len(rows))) or
            any(type(n) is not int or n not in (0, 1) for n in values.values())):
        raise io.DPError('CLEAN_RECOVERY_KEYS')
    if all(n == 0 for n in values.values()): return False
    if all(n == 1 for n in values.values()): return True
    raise io.DPError('CLEAN_PARTIAL_BATCH: unexpected partial transaction; no automatic overwrite')


def source_rows(root, kind, version):
    db = migration.source_open(root/'store.sqlite')
    try:
        cursor = None
        while batch := migration.source_batch(db, kind, version, cursor):
            yield from batch
            cursor = [batch[-1][c] for c in io.KEYS[kind] if c != 'DATASET_VERSION']
    finally:
        db.close()


def part_rows(root, items):
    seen = set()
    for asset in items:
        if asset['sha256'] in seen: continue
        seen.add(asset['sha256'])
        with assets.checked_path(root, asset['path']).open('rb') as f:
            for number in range(asset['parts']):
                check()
                raw = f.read(assets.PART_BYTES)
                if len(raw) != min(assets.PART_BYTES, asset['bytes']-number*assets.PART_BYTES):
                    raise io.DPError('CLEAN_ASSET_LENGTH')
                yield dict(zip(PART_COLS, [asset['sha256'], number, len(raw), hashlib.sha256(raw).hexdigest(),
                                          base64.b64encode(zlib.compress(raw, 6)).decode()]))


def query_rows(root, plan):
    observed = {}
    for relative in plan['projection_order']:
        for row in projection.projected_rows(root/relative, relative, plan['source']):
            if io.digest({k:v for k,v in row.items() if k != 'sha256'}) != row['sha256']:
                raise io.DPError('CLEAN_QUERY_RECORD_HASH')
            item = observed.setdefault(row['kind'], {'rows':0,'chain':'0'*64})
            item['rows'] += 1
            item['chain'] = io.digest([item['chain'],row['row_id'],row['sha256']])
            yield dict(zip(QUERY_COLS, [plan['query_id'], row['kind'], row['row_id'], row['document_id'],
                row['lookup_id'], row['owner_id'], row['target_id'], row['sha256'], q.json_body(row['value'])]))
    expected = {k:{'rows':v['rows'],'chain':v['chain']} for k,v in plan['query']['tables'].items() if v['rows']}
    if observed != expected:
        raise io.DPError('CLEAN_QUERY_PLAN_CHANGED: projection differs from pre-reset plan')


def _load(sql, directory, state, save, phase, table, columns, kinds, keys, rows, expected, tick):
    progress = state['phases'].setdefault(phase, {'rows': 0, 'chain': '0'*64, 'complete': False})
    if progress['complete']: return
    report(phase, rows_added=progress['rows'], rows_total=expected)
    consumed, chain = 0, '0'*64
    saved_rows = progress['rows']
    # Only the local deterministic prefix is replayed on resume. No database reads.
    def remaining():
        nonlocal consumed, chain
        for row in rows:
            tick()
            if consumed < saved_rows:
                chain = io.digest([chain, row]); consumed += 1
                if consumed == saved_rows and chain != progress['chain']:
                    raise io.DPError('CLEAN_RESUME_CHAIN: local prefix changed')
                continue
            yield row
    for batch in batches(remaining()):
        tick()
        marker = {'phase': phase, 'start': consumed, 'rows': len(batch), 'sha256': io.digest(batch)}
        pending = state.get('pending')
        if pending and pending != marker:
            raise io.DPError('CLEAN_PENDING_BINDING: keep original code/input/batch sizing')
        known_present = False
        if pending:
            known_present = existing(sql, table, keys, batch, dict(zip(columns, kinds)))
            if known_present:
                statement, binds = insert_sql(table, columns, kinds, batch, verify_only=True)
                sql.request(statement, binds, write=True)
                transport.event(directory, 'UNCERTAIN_BATCH_RECONCILED', phase=phase, rows=len(batch))
        if not known_present:
            state['pending'] = marker; save()
            statement, binds = insert_sql(table, columns, kinds, batch)
            sql.request(statement, binds, write=True)
        for row in batch:
            chain = io.digest([chain, row])
        consumed += len(batch)
        progress.update(rows=consumed, chain=chain)
        state['pending'] = None; save()
        report(rows_added=consumed, rows_total=expected)
        transport.event(directory, 'BATCH_COMMITTED', phase=phase, rows=consumed, total=expected, sql_calls=sql.calls)
    if consumed != expected or consumed < saved_rows:
        raise io.DPError('CLEAN_SOURCE_COUNT: projected rows differ from plan')
    progress['complete'] = True; save()


def _plan(root, info, sql, target):
    report('PLAN_SOURCE')
    _, manifest, items, _, selected = full.immutable_inputs(root)
    source = transport.offline_source(root, manifest, items, selected, check)
    report('PLAN_QUERY')
    _, paths, tables = projection.describe(root, source)
    query = transport.query_manifest(root, source, paths, tables, items)
    old = table_counts(sql)
    unique = {a['sha256']: a for a in items}
    expected = {t: 0 for t in TABLES}
    expected.update({'SIDDA.'+io.TABLES[k]: n for k,n in info['source_counts'].items()})
    expected[assets.PART_TABLE] = sum(a['parts'] for a in unique.values())
    expected[assets.RELEASE_TABLE] = expected[q.RELEASE] = 1
    expected[q.ROW] = sum(t['rows'] for t in tables.values())
    return {'target': target, 'before_counts': old, 'expected_counts': expected,
            'source': source, 'source_id': io.digest(source), 'query': query, 'query_id': io.digest(query),
            'projection_order': list(paths)}


def run(client, work, *, target_binding, action='plan', seconds=21600):
    if action not in {'plan','replace','resume','status'}:
        raise io.DPError('CLEAN_ACTION: plan / replace / resume / status')
    if not 1 <= seconds <= 21600: raise io.DPError('CLEAN_BUDGET: 1..21600 seconds')
    work = Path(work).resolve(strict=True)
    logs = work/'oracle-clean-r1'
    # Holding both old and new locks prevents concurrent restart through existing entrypoints.
    with guard(work), transport.job(logs), tracking(logs, lambda s,**kw:transport.event(logs,s,**kw)) as telemetry:
        telemetry.deadline = time.time()+seconds
        report('INPUT_HASH_CHECK')
        root, info = full.verify_restored(work/'restored')
        previous = work/'oracle-import-r3/full-state.json'
        if previous.exists():
            old_target = transport.bounded_json(previous).get('identity', {}).get('target')
            if old_target != target_binding:
                raise io.DPError('CLEAN_PRIOR_TARGET: connection differs from the original migration')
        from . import oracle_query_dataiku, oracle_import_stop, oracle_query_navigation_publish
        from semantic_runtime import navigation_match, structure_navigation, inherited_navigation
        code = {m.__name__:io.file_sha(m.__file__) for m in
                (full, transport, migration, projection, io, assets, q, oracle_query_dataiku,
                 oracle_import_stop, oracle_query_navigation_publish, navigation_match,
                 structure_navigation, inherited_navigation)}
        identity = {'target': target_binding, 'data': io.digest(info), 'generation': str(root),
                    'code': io.file_sha(__file__), 'dependencies':code, 'revision': REVISION}
        receipt = logs/'state.json'
        state = transport.bounded_json(receipt) if receipt.exists() else {
            'identity': identity, 'deadline': time.time()+7*86400, 'status': 'NEW', 'phases': {}, 'pending': None}
        if state['identity'] != identity: raise io.DPError('CLEAN_BINDING: input/code/target changed')
        telemetry.deadline = min(telemetry.deadline, state['deadline'])
        def save(): io.atomic_json(receipt, state)
        signatures = {name:migration.signature(work/'restored'/name) for name in info['files']}
        last_tick = [0.0]
        def tick():
            if time.monotonic()-last_tick[0] < 1:
                return
            check(); transport.resources(logs)
            if any(migration.signature(work/'restored'/name)!=value for name,value in signatures.items()):
                raise io.DPError('CLEAN_INPUT_CHANGED: immutable ZIP input changed during load')
            last_tick[0] = time.monotonic()
        save()
        sql = io.SQL(client, journal=logs/'calls.jsonl', binding=io.digest(identity),
                     seconds=max(0,telemetry.deadline-time.time()), progress=telemetry if hasattr(telemetry,'sql') else None)
        try:
            report('SCHEMA_CHECK')
            shape = schema(sql)
            active = sql.query(f'SELECT CHANNEL,RELEASE_ID,REVISION FROM {q.ACTIVE} ORDER BY CHANNEL',limit=100)
            if active and action != 'status':
                if action == 'plan':
                    return {'status':'ACTIVE_IN_USE_NO_CHANGES','active':active,
                            'delete_tables':list(TABLES),'active_modified':False,'state_modified':False,
                            'note':'An active release exists. Data replacement is blocked; no rows were deleted.'}
                raise io.DPError('CLEAN_ACTIVE_IN_USE: preserve ACTIVE; cannot reset its data while a release is selected')
            plan_path = logs/'plan.json'
            if 'plan_sha256' not in state:
                if action != 'plan': raise io.DPError('CLEAN_PLAN_FIRST')
                plan = _plan(root, info, sql, target_binding)
                if plan_path.exists():
                    if transport.bounded_json(plan_path) != plan:
                        raise io.DPError('CLEAN_PLAN_FILE_CONFLICT: preserve prior plan')
                else:
                    io.atomic_json(plan_path, plan)
                state['plan_sha256'] = io.file_sha(plan_path)
                state['status'] = 'PLANNED'; save()
            if io.file_sha(plan_path) != state['plan_sha256']:
                raise io.DPError('CLEAN_PLAN_HASH: saved plan changed')
            plan = transport.bounded_json(plan_path)
            if action == 'plan':
                return {'status':'CLEAN_PLAN_READY','before_counts':plan['before_counts'],
                        'after_counts':plan['expected_counts'],'delete_tables':list(TABLES),
                        'active_modified':False,'state_modified':False,
                        'full_body_readback':False,'deferred_indexes':shape['deferred_indexes'],
                        'note':'replace deletes all versions in these seven SIDDA data tables. ACTIVE and STATE are preserved.'}
            if action == 'status':
                counts = table_counts(sql)
                return {'status':state['status'],'phases':state['phases'],'pending':state['pending'],
                        'counts':counts,'result':state.get('result'), 'full_body_readback':False}
            if not state.get('reset_complete'):
                if action != 'replace': raise io.DPError('CLEAN_RESET_FIRST: explicit replace action required')
                report('CLEAR_SEVEN_DATA_TABLES')
                before = table_counts(sql)
                uncertain = state.get('reset_pending', False)
                if uncertain:
                    # A server-side JDBC DELETE may outlive a killed notebook.
                    # Never infer its cancellation from an empty/count-only read.
                    raise io.DPError('CLEAN_RESET_UNCONFIRMED: do not repeat DELETE; resolve the original Dataiku/Oracle transaction first')
                else:
                    if before != plan['before_counts']:
                        raise io.DPError('CLEAN_PLAN_TARGET_CHANGED: table counts changed before reset')
                    state['reset_pending'] = True; save()
                    statements = ['DECLARE n NUMBER; BEGIN',
                                  f'LOCK TABLE {q.ACTIVE} IN EXCLUSIVE MODE NOWAIT;',
                                  f'SELECT COUNT(*) INTO n FROM {q.ACTIVE};',
                                  "IF n<>0 THEN RAISE_APPLICATION_ERROR(-20062,'CLEAN_ACTIVE_IN_USE'); END IF;"]
                    for table in TABLES:
                        statements.append(f'LOCK TABLE {table} IN EXCLUSIVE MODE NOWAIT;')
                    statements.extend(f'DELETE FROM {table};' for table in TABLES)
                    statements.append('COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
                    try:
                        sql.request('\n'.join(statements), write=True)
                    except io.DPError as exc:
                        # These two errors arise only in this block's pre-delete guards.
                        if 'ORA-00054' in str(exc) or 'ORA-20062' in str(exc):
                            state['reset_pending'] = False
                            state['reset_rejected'] = str(exc); save()
                        raise
                    if any(table_counts(sql).values()): raise io.DPError('CLEAN_RESET_NOT_EMPTY')
                    state['reset_complete'] = True; state['reset_pending'] = False; save()
                transport.event(logs,'SEVEN_DATA_TABLES_CLEARED',counts=plan['before_counts'])
            # Once reset is confirmed, replace is idempotent resume, never another DELETE.
            state['status'] = 'LOADING'; save()
            for kind in io.TABLES:
                cols = io.COLUMNS[kind]
                kinds = ['CLOB' if c in io.CLOBS else 'NUMBER' if c=='JSON_TEXT_ELIDED' else 'VARCHAR2' for c in cols]
                _load(sql,logs,state,save,kind,'SIDDA.'+io.TABLES[kind],cols,kinds,io.KEYS[kind],
                      source_rows(root,kind,info['dataset_version']),info['source_counts'][kind],tick)
            _load(sql,logs,state,save,'assets',assets.PART_TABLE,PART_COLS,
                  ['VARCHAR2','NUMBER','NUMBER','VARCHAR2','CLOB'],PART_COLS[:2],
                  part_rows(root,plan['source']['assets']),plan['expected_counts'][assets.PART_TABLE],tick)
            _load(sql,logs,state,save,'query',q.ROW,QUERY_COLS,['VARCHAR2']*8+['CLOB'],QUERY_COLS[:3],
                  query_rows(root,plan),plan['expected_counts'][q.ROW],tick)
            report('COUNTS_BEFORE_RELEASE')
            counts = table_counts(sql)
            for table in TABLES:
                if table not in (assets.RELEASE_TABLE,q.RELEASE) and counts[table] != plan['expected_counts'][table]:
                    raise io.DPError('CLEAN_COUNT_MISMATCH: '+table)
            # Check actual kind counts too; no body downloads.
            kinds = sql.query(f'SELECT KIND,COUNT(*) AS N FROM {q.ROW} GROUP BY KIND',
                              limit=max(1,len(plan['query']['tables'])))
            actual = {r['KIND']:r['N'] for r in kinds}
            expected = {k:v['rows'] for k,v in plan['query']['tables'].items() if v['rows']}
            if len(actual)!=len(kinds) or actual!=expected: raise io.DPError('CLEAN_KIND_COUNT')
            report('FINAL_INPUT_HASH_CHECK'); full.verify_restored(work/'restored'); tick()
            source_release = {'RELEASE_ID':plan['source_id'],'DATASET_VERSION':info['dataset_version'],
                              'RELEASE_JSON':q.json_body(plan['source'])}
            _load(sql,logs,state,save,'source_release',assets.RELEASE_TABLE,tuple(source_release),
                  ['VARCHAR2','VARCHAR2','CLOB'],('RELEASE_ID',),iter([source_release]),1,tick)
            query_release = {'RELEASE_ID':plan['query_id'],'MANIFEST_JSON':q.json_body(plan['query'])}
            _load(sql,logs,state,save,'query_release',q.RELEASE,tuple(query_release),
                  ['VARCHAR2','CLOB'],('RELEASE_ID',),iter([query_release]),1,tick)
            if table_counts(sql) != plan['expected_counts']: raise io.DPError('CLEAN_FINAL_COUNTS')
            # The two small manifests remain fully readable/validated for downstream consumers.
            if assets.get_release(sql,plan['source_id']) != plan['source'] or q.read_release(sql,plan['query_id']) != plan['query']:
                raise io.DPError('CLEAN_RELEASE_READBACK')
            result = {'status':'CLEAN_LOAD_COUNTS_CONFIRMED','counts':plan['expected_counts'],
                      'source_release_id':plan['source_id'],'query_release_id':plan['query_id'],
                      'full_body_readback':False,'active_modified':False,'state_modified':False,
                      'serving_switched':False,'deferred_indexes':shape['deferred_indexes']}
            state.update(status='COMPLETE',result=result); save()
            transport.event(logs,'CLEAN_LOAD_COUNTS_CONFIRMED',counts=result['counts'])
            return result
        except BaseException as exc:
            state.update(status='PAUSED' if isinstance(exc,io.BudgetPause) else
                         'INTERRUPTED' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'FAILED',
                         error=str(exc) if isinstance(exc,io.DPError) else type(exc).__name__)
            save()
            raise
