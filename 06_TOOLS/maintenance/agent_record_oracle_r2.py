"""Apply the reviewed compact Agent schema to the existing LOCAL SIDDA only.

No Gold DDL/DML, quota changes, runtime activation or legacy migration.
Oracle DDL commits independently. Every completed step is journalled; reruns
verify exact definitions before continuing. Verification uses synthetic rows
in a unique scope and removes only those rows after commit/readback checks.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import uuid
import zlib

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / '07_DOCS/REFERENCE/REPORTS/ORACLE_AGENT_RECORD_DESIGN_20261030_R2'
OUT = ROOT / '09_ARTIFACTS/AUDITS/20261030-agent-record-oracle-r2'
OWNER = 'SIDDA'
GOLD = 'A8_GR12_CM1208'
ACTIVE = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
STATE = 'LGL_EXEC_ST_A'
sys.dont_write_bytecode = True


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value).encode()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def file_hash(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')
        f.flush(); os.fsync(f.fileno())


def event(**value):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'events.jsonl').open('a') as f:
        f.write(canonical({'at': datetime.now(timezone.utc).isoformat(), **value}) + '\n')
        f.flush(); os.fsync(f.fileno())


def connection():
    # Reuse the existing local container identity/loopback guard. Never print env.
    spec = importlib.util.spec_from_file_location('_existing_local_admin', ROOT / '06_TOOLS/maintenance/publish_gold_ontology_samples.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    db = module.admin_connection()
    db.call_timeout = 15000
    with db.cursor() as c:
        c.execute("SELECT SYS_CONTEXT('USERENV','CON_NAME'),SYS_CONTEXT('USERENV','SESSION_USER') FROM DUAL")
        if c.fetchone() != ('FREEPDB1', 'SYSTEM'):
            db.close(); raise RuntimeError('Unexpected local Oracle identity')
        c.execute('ALTER SESSION SET DDL_LOCK_TIMEOUT=5')
    return db


def schema():
    value = load(DESIGN / 'schema_proposal.json')
    if value['revision'] != 'R2' or value['new_table_count'] != 3 or value['new_column_count'] != 21:
        raise RuntimeError('Expected reviewed compact R2')
    if value['existing_state']['name'] != STATE or value['gold_ddl_changes'] != 0:
        raise RuntimeError('Unexpected state/Gold contract')
    return value


def ddl_steps():
    text = re.sub(r'--[^\n]*', '', (DESIGN / 'agent_schema_review.sql').read_text())
    statements = [s.strip().replace('__AGENT_OWNER__', OWNER) for s in text.split(';') if s.strip()]
    result = []
    for statement in statements:
        match = re.match(r'CREATE (TABLE|INDEX) SIDDA\.([A-Z0-9_]+) ', statement)
        if not match or not match[2].startswith(('LGL_AGT_', 'LGL_AR0')):
            raise RuntimeError('Unreviewed DDL statement')
        result.append({'kind': match[1], 'name': match[2], 'sql': statement})
    if len(result) != 10:
        raise RuntimeError('Expected 3 CREATE TABLE and 7 CREATE INDEX')
    return result


def rows(db, sql, **binds):
    import oracledb
    with db.cursor() as c:
        times = {key: oracledb.DB_TYPE_TIMESTAMP_TZ for key, value in binds.items()
                 if isinstance(value, datetime) and value.tzinfo is not None}
        if times:
            c.setinputsizes(**times)
        c.execute(sql, binds)
        return [list(r) for r in c]


def shape(db, name):
    return rows(db, 'SELECT COLUMN_NAME,DATA_TYPE,DATA_LENGTH,DATA_PRECISION,DATA_SCALE,CHAR_USED,NULLABLE '
                'FROM DBA_TAB_COLUMNS WHERE OWNER=:owner AND TABLE_NAME=:name ORDER BY COLUMN_ID', owner=OWNER, name=name)


def assert_table(db, table):
    actual = shape(db, table['name'])
    if len(actual) != len(table['columns']):
        raise RuntimeError('Column count mismatch: ' + table['name'])
    for got, col in zip(actual, table['columns']):
        name, typ, size, precision, scale, char_used, nullable = got
        want = col['type']
        ok = name == col['name'] and nullable == ('Y' if col['nullable'] else 'N')
        if want.startswith('VARCHAR2('):
            ok = ok and typ == 'VARCHAR2' and size == int(re.search(r'\((\d+)', want)[1]) and char_used == 'B'
        elif want == 'NUMBER(18)':
            ok = ok and typ == 'NUMBER' and precision == 18 and scale == 0
        elif want == 'TIMESTAMP(6) WITH TIME ZONE':
            ok = ok and typ == want and scale == 6
        else:
            ok = ok and typ == want
        if not ok:
            raise RuntimeError('Column definition mismatch: ' + table['name'] + '.' + name)
    pk = rows(db, 'SELECT CC.COLUMN_NAME FROM DBA_CONSTRAINTS C JOIN DBA_CONS_COLUMNS CC '
              'ON C.OWNER=CC.OWNER AND C.CONSTRAINT_NAME=CC.CONSTRAINT_NAME '
              "WHERE C.OWNER=:owner AND C.TABLE_NAME=:name AND C.CONSTRAINT_TYPE='P' AND C.STATUS='ENABLED' ORDER BY CC.POSITION",
              owner=OWNER, name=table['name'])
    if [r[0] for r in pk] != table['pk']:
        raise RuntimeError('PK mismatch: ' + table['name'])


def assert_index(db, step):
    info = rows(db, 'SELECT TABLE_OWNER,TABLE_NAME,UNIQUENESS,STATUS FROM DBA_INDEXES WHERE OWNER=:owner AND INDEX_NAME=:name',
                owner=OWNER, name=step['name'])
    match = re.fullmatch(r'CREATE INDEX SIDDA\.[A-Z0-9_]+ ON SIDDA\.([A-Z0-9_]+) \(([^)]+)\)', step['sql'])
    want_cols = [s.strip() for s in match[2].split(',')]
    cols = rows(db, 'SELECT COLUMN_NAME FROM DBA_IND_COLUMNS WHERE INDEX_OWNER=:owner AND INDEX_NAME=:name ORDER BY COLUMN_POSITION',
                owner=OWNER, name=step['name'])
    expressions = dict((int(position), expression) for expression, position in rows(db,
        'SELECT COLUMN_EXPRESSION,COLUMN_POSITION FROM DBA_IND_EXPRESSIONS WHERE INDEX_OWNER=:owner AND INDEX_NAME=:name',
        owner=OWNER, name=step['name']))
    utc_columns = {col['name'] for t in schema()['tables'] if t['name'] == match[1]
                   for col in t['columns'] if col['type'] == 'TIMESTAMP(6) WITH TIME ZONE'}
    columns_match = len(cols) == len(want_cols)
    for position, (got, want) in enumerate(zip(cols, want_cols), 1):
        if position in expressions:
            columns_match = columns_match and want in utc_columns and expressions[position] == f'SYS_EXTRACT_UTC("{want}")'
        else:
            columns_match = columns_match and got[0] == want
    if info != [[OWNER, match[1], 'NONUNIQUE', 'VALID']] or not columns_match:
        raise RuntimeError('Index definition mismatch: ' + step['name'])


def protected_snapshot(db):
    mapping_pointer = ROOT / '08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/ACTIVE_MAPPING.json'
    mp = load(mapping_pointer)
    mapping_path = mapping_pointer.parent / mp['mapping_file']
    if file_hash(mapping_path) != mp['sha256']:
        raise RuntimeError('Gold mapping pointer hash differs')
    mapping = load(mapping_path)
    names = sorted(t['name'] for t in mapping['tables'].values())
    if len(names) != 13:
        raise RuntimeError('Expected 13 existing Gold tables')
    counts = {n: rows(db, f'SELECT COUNT(*) FROM {GOLD}.{n}')[0][0] for n in names}
    objects = rows(db, 'SELECT OBJECT_NAME,OBJECT_TYPE,OBJECT_ID,DATA_OBJECT_ID,STATUS FROM DBA_OBJECTS WHERE OWNER=:owner ORDER BY OBJECT_NAME,OBJECT_TYPE', owner=GOLD)
    state_hash = hashlib.sha256(); state_count = 0
    with db.cursor() as c:
        c.execute(f'SELECT SCOPE_HASH_VAL,ST_KEY_ID,CHG_SEQ_NO,ST_HASH_VAL,ST_JSON_CN FROM {OWNER}.{STATE} ORDER BY SCOPE_HASH_VAL,ST_KEY_ID')
        for row in c:
            values = [v.read() if hasattr(v, 'read') else v for v in row]
            state_hash.update(canonical(values).encode()); state_hash.update(b'\n'); state_count += 1
    return {'active_release_sha256': file_hash(ACTIVE), 'gold_mapping_pointer_sha256': file_hash(mapping_pointer),
            'gold_mapping_sha256': file_hash(mapping_path), 'gold_counts': counts, 'gold_objects': objects,
            'state_shape': shape(db, STATE), 'state_rows': state_count, 'state_content_sha256': state_hash.hexdigest()}


def capacity(db):
    return {'sidda_quota': rows(db, 'SELECT TABLESPACE_NAME,BYTES,MAX_BYTES FROM DBA_TS_QUOTAS WHERE USERNAME=:owner', owner=OWNER),
            'users_allocated_bytes': rows(db, "SELECT SUM(BYTES) FROM DBA_DATA_FILES WHERE TABLESPACE_NAME='USERS'")[0][0],
            'users_free_allocated_bytes': rows(db, "SELECT SUM(BYTES) FROM DBA_FREE_SPACE WHERE TABLESPACE_NAME='USERS'")[0][0]}


def plan():
    value = schema(); steps = ddl_steps()
    with connection() as db:
        assert_table(db, value['existing_state'])
        collisions = rows(db, "SELECT OBJECT_NAME,OBJECT_TYPE FROM DBA_OBJECTS WHERE OWNER=:owner AND (OBJECT_NAME LIKE 'LGL_AGT%' OR OBJECT_NAME LIKE 'LGL_AR0%')", owner=OWNER)
        if collisions:
            raise RuntimeError('New object names already exist; inspect prior application')
        before = protected_snapshot(db); space = capacity(db)
    plan_value = {'authorization': '실제 우리 오라클DB에 적용해볼수 있냐? ... 진행해봐',
                  'environment': 'existing loopback Docker Oracle FREEPDB1; not GENOS', 'owner': OWNER,
                  'ddl_sha256': file_hash(DESIGN / 'agent_schema_review.sql'),
                  'schema_sha256': file_hash(DESIGN / 'schema_proposal.json'),
                  'queries_sha256': file_hash(DESIGN / 'agent_query_review.sql'),
                  'runner_sha256': file_hash(__file__), 'steps': steps, 'protected_before': before,
                  'capacity_before': space, 'quota_change': False, 'runtime_activation': False,
                  'ddl_is_autocommitted': True, 'ninety_unit': 'pending clarification; existing quota sufficient, no increase used'}
    save('plan.json', plan_value)
    (OUT / 'apply.sql').write_text('-- LOCAL SIDDA only. Existing state and Gold unchanged.\n' + ';\n\n'.join(s['sql'] for s in steps) + ';\n')
    # Manual recovery only; never run automatically and never drop populated tables.
    (OUT / 'empty_tables_rollback_review.sql').write_text('-- REVIEW ONLY. Only after verifying all three NEW tables are empty and unused.\n' +
        '\n'.join(f'DROP TABLE {OWNER}.{t["name"]};' for t in reversed(value['tables'])) + '\n')
    print(canonical({'phase': 'PLAN', 'owner': OWNER, 'new_tables': 3, 'new_columns': 21, 'steps': len(steps), 'capacity': space}))


def check_pins(plan_value):
    for key, path in [('ddl_sha256', DESIGN / 'agent_schema_review.sql'), ('schema_sha256', DESIGN / 'schema_proposal.json'),
                      ('queries_sha256', DESIGN / 'agent_query_review.sql')]:
        if file_hash(path) != plan_value[key]:
            raise RuntimeError('Plan input changed: ' + key)
    runner_pin = plan_value['runner_sha256']
    for amendment_path in sorted(OUT.glob('runner-amendment-*.json')):
        amendment = load(amendment_path)
        if amendment['original_plan_sha256'] != file_hash(OUT / 'plan.json') or amendment['previous_runner_sha256'] != runner_pin:
            raise RuntimeError('Invalid runner amendment chain')
        runner_pin = amendment['new_runner_sha256']
    if file_hash(__file__) != runner_pin:
        raise RuntimeError('Runner changed without a recorded amendment')


def apply():
    p = load(OUT / 'plan.json'); check_pins(p); value = schema()
    with connection() as db:
        if protected_snapshot(db) != p['protected_before']:
            raise RuntimeError('Protected baseline changed; no further DDL')
        for step in p['steps']:
            existing = rows(db, 'SELECT OBJECT_TYPE FROM DBA_OBJECTS WHERE OWNER=:owner AND OBJECT_NAME=:name AND OBJECT_TYPE=:kind',
                            owner=OWNER, name=step['name'], kind=step['kind'])
            if not existing:
                event(phase='DDL_BEGIN', name=step['name'], sql_sha256=digest(step['sql'].encode()))
                try:
                    with db.cursor() as c:
                        c.execute(step['sql'])
                except Exception as exc:
                    event(phase='DDL_FAILED', name=step['name'], error_type=type(exc).__name__, error=str(exc))
                    raise
                event(phase='DDL_COMMITTED', name=step['name'])
            if step['kind'] == 'TABLE':
                assert_table(db, next(t for t in value['tables'] if t['name'] == step['name']))
            else:
                assert_index(db, step)
        after = protected_snapshot(db)
        if after != p['protected_before']:
            raise RuntimeError('Protected baseline differs after DDL')
        if (OUT / 'applied.json').exists():
            previous = load(OUT / 'applied.json')
            if previous['protected_after'] != after or previous['owner'] != OWNER:
                raise RuntimeError('Existing apply receipt differs')
            event(phase='APPLY_ALREADY_INSTALLED_VERIFIED', tables=3, ordinary_indexes=7)
            print(canonical({'phase': 'APPLY', 'status': 'ALREADY_INSTALLED_VERIFIED', 'tables': 3, 'columns': 21, 'new_ddl': 0}))
            return
        save('applied.json', {'status': 'LOCAL_SIDDA_3_TABLES_CREATED', 'owner': OWNER,
                             'new_tables': 3, 'new_columns': 21, 'ordinary_indexes': 7, 'primary_keys': 3,
                             'protected_after': after, 'capacity_after': capacity(db), 'all_step_definitions_verified': True})
    print(canonical({'phase': 'APPLY', 'tables': 3, 'columns': 21, 'indexes': 7, 'gold_and_existing_state_preserved': True}))


def query_templates():
    text = (DESIGN / 'agent_query_review.sql').read_text()
    blocks = re.split(r'(?m)^-- (Q\d\d):[^\n]*\n', text)
    result = {}
    for i in range(1, len(blocks), 2):
        sql = re.sub(r'--[^\n]*', '', blocks[i + 1]).strip().rstrip(';').replace('__AGENT_OWNER__', OWNER)
        result[blocks[i]] = sql
    if len(result) != 11:
        raise RuntimeError('Expected 11 SELECT templates')
    return result


def insert(db, table, fields):
    import oracledb
    if table not in {STATE, *[t['name'] for t in schema()['tables']]}:
        raise RuntimeError('Verification DML table outside Agent contract')
    with db.cursor() as c:
        sizes = {key: oracledb.DB_TYPE_CLOB for key in fields if key.endswith('_JSON_CN')}
        sizes.update({key: oracledb.DB_TYPE_TIMESTAMP_TZ for key in fields if key.endswith('_DTTM')})
        if sizes:
            c.setinputsizes(**sizes)
        c.execute(f'INSERT INTO {OWNER}.{table} (' + ','.join(fields) + ') VALUES (' + ','.join(':' + k for k in fields) + ')', fields)


def put_body(db, scope, raw, *, large=False):
    body_hash = digest(raw); size = 64 * 1024
    parts = [raw[i:i + size] for i in range(0, len(raw), size)] or [b'']
    for i, part in enumerate(parts, 1):
        compress = not large or i % 2 == 0
        stored = zlib.compress(part) if compress else part
        item = {'format': 'agent-body-part-v1', 'codec': 'ZLIB_BASE64' if compress else 'RAW_BASE64',
                'raw_bytes': len(part), 'raw_sha256': digest(part), 'stored_sha256': digest(stored),
                'data_base64': base64.b64encode(stored).decode()}
        insert(db, 'LGL_AGT_BODY_A', {'SCOPE_HASH_VAL': scope, 'BODY_HASH_VAL': body_hash, 'PART_SEQ_NO': i, 'PART_JSON_CN': canonical(item)})
    manifest = {'format': 'agent-body-manifest-v1', 'body_sha256': body_hash, 'total_bytes': len(raw), 'part_count': len(parts), 'layout_version': 1}
    insert(db, 'LGL_AGT_BODY_A', {'SCOPE_HASH_VAL': scope, 'BODY_HASH_VAL': body_hash, 'PART_SEQ_NO': 0, 'PART_JSON_CN': canonical(manifest)})
    return body_hash, manifest


def smoke():
    p = load(OUT / 'plan.json'); check_pins(p)
    if not (OUT / 'applied.json').exists():
        raise RuntimeError('Apply first')
    attempt = uuid.uuid4().hex
    scope = digest({'synthetic_schema_verification': attempt})
    event(phase='VERIFY_BEGIN', attempt=attempt, scope=scope, synthetic=True)
    tests = []; now = datetime.now(timezone.utc)
    ids = {k: digest({'attempt': attempt, 'key': k}) for k in ('run', 'child', 'session', 'request', 'entity', 'call', 'edge', 'endpoint', 'lookup', 'sent')}
    def check(name, ok, **detail):
        tests.append({'name': name, 'passed': bool(ok), **detail})
        if not ok:
            raise AssertionError(name)
    templates = query_templates()
    common = {'scope': scope, 'owner_key': ids['run'], 'session_key': ids['session'], 'request_key': ids['request'],
              'before_time': now + timedelta(minutes=1), 'before_run': 'f' * 64,
              'after_time': now - timedelta(days=1), 'after_run': '0' * 64, 'scan_cutoff': now + timedelta(minutes=1),
              'after_seq': 0, 'event_watermark': 2, 'page_limit': 50,
              'registered_kind': 'CASE_NODE', 'record_key': ids['entity'], 'after_revision': 0,
              'status': 'SCHEMA_TEST', 'call_status_key': ids['sent'], 'after_record': '0' * 64,
              'graph_owner_key': ids['run'], 'endpoint_key': ids['endpoint'], 'direction_kind': 'REF_OUT',
              'registered_index_kind': 'IX:TERM', 'lookup_key': ids['lookup'], 'after_owner': '0' * 64}
    def q(db, name, **extra):
        sql = templates[name]; values = {**common, **extra}
        names = set(re.findall(r':([a-z][a-z0-9_]*)', sql))
        return rows(db, sql, **{key: values[key] for key in names})
    def rec(db, kind, key, revision, order, body, lookup=None):
        insert(db, 'LGL_AGT_REC_A', {'SCOPE_HASH_VAL': scope, 'OWNER_KEY_HASH_VAL': ids['run'], 'REC_KIND_CD': kind,
               'REC_KEY_HASH_VAL': key, 'REC_REV_NO': revision, 'ORD_SEQ_NO': order, 'LOOKUP_HASH_VAL': lookup, 'BODY_HASH_VAL': body})
    def state_hash(revision, value):
        return digest({'scope_hash': scope, 'key': state_key, 'revision': revision, 'value': value})
    state_key = 'a1:req:' + ids['request']
    result = None
    try:
        with connection() as db:
            check('protected_before_smoke', protected_snapshot(db) == p['protected_before'])
            large_raw = canonical({'synthetic': True, 'text': ('원문\n따옴표"와 이모지🌱, 한글 좌표\r\n' * 18000),
                                   'reason': None, 'purpose': None, 'null_value': None, 'empty_string': '', 'leading_id': '0001'}).encode()
            large_hash, manifest = put_body(db, scope, large_raw, large=True)
            v1 = canonical({'synthetic': True, 'judgment': 'initial', 'reason': None, 'purpose': None}).encode()
            h1, _ = put_body(db, scope, v1)
            v2 = canonical({'synthetic': True, 'judgment': 'corrected', 'reason': None, 'purpose': None, 'previous_sha256': h1}).encode()
            h2, _ = put_body(db, scope, v2)
            for name, parent in [('run', None), ('child', ids['run'])]:
                insert(db, 'LGL_AGT_RUN_A', {'SCOPE_HASH_VAL': scope, 'RUN_KEY_HASH_VAL': ids[name], 'SESS_KEY_HASH_VAL': ids['session'],
                       'REQ_KEY_HASH_VAL': ids['request'], 'PRNT_RUN_KEY_HASH_VAL': parent, 'ST_CD': 'SCHEMA_TEST',
                       'STRT_DTTM': now, 'CHG_DTTM': now, 'BODY_HASH_VAL': h1})
            for seq in (1, 2):
                rec(db, 'EVENT', digest({'event': seq, 'attempt': attempt}), 1, seq, h1 if seq == 1 else h2)
            rec(db, 'CASE_NODE', ids['entity'], 1, 1, h1)
            rec(db, 'CASE_NODE', ids['entity'], 2, 2, h2)
            rec(db, 'CASE_NODE', ids['entity'], 0, 2, h2)
            rec(db, 'CALL', ids['call'], 1, 1, large_hash)
            rec(db, 'CALL', ids['call'], 0, 1, large_hash, ids['sent'])
            rec(db, 'REF', ids['edge'], 1, 1, h1)
            rec(db, 'REF_OUT', ids['edge'], 0, 1, h1, ids['endpoint'])
            rec(db, 'REF_IN', ids['edge'], 0, 1, h1, ids['endpoint'])
            rec(db, 'IX:TERM', ids['entity'], 0, 1, h2, ids['lookup'])
            state_value = {'synthetic': True, 'counter': 1, 'run_key': ids['run']}
            insert(db, STATE, {'SCOPE_HASH_VAL': scope, 'ST_KEY_ID': state_key, 'CHG_SEQ_NO': 1,
                              'ST_HASH_VAL': state_hash(1, state_value), 'ST_JSON_CN': canonical(state_value)})
            with connection() as observer:
                check('uncommitted_rows_invisible', q(observer, 'Q01') == [])
            db.commit()
            event(phase='VERIFY_SYNTHETIC_COMMITTED', attempt=attempt, scope=scope, raw_bytes=len(large_raw), parts=manifest['part_count'])
        with connection() as db:
            check('commit_visible_after_reconnect', len(q(db, 'Q01')) == 2)
            check('request_history_not_unique', len(q(db, 'Q02')) == 2)
            check('status_recovery_candidates', len(q(db, 'Q03')) == 2)
            first = q(db, 'Q04', page_limit=1)
            second = q(db, 'Q04', page_limit=1, after_seq=first[0][1])
            check('event_keyset_pages', [first[0][1], second[0][1]] == [1, 2] and not q(db, 'Q04', after_seq=2))
            check('judgment_revisions_preserved', [r[0] for r in q(db, 'Q05')] == [1, 2])
            check('current_call_status', len(q(db, 'Q06')) == 1)
            check('forward_reference', len(q(db, 'Q07')) == 1)
            check('reverse_reference', len(q(db, 'Q07', direction_kind='REF_IN')) == 1)
            check('current_judgment_points_to_revision2', q(db, 'Q08')[0][-1] == h2)
            check('registered_term_projection', len(q(db, 'Q09')) == 1)
            mf = q(db, 'Q10', body_hash=large_hash)[0][0]
            mf = json.loads(mf.read() if hasattr(mf, 'read') else mf)
            restored = bytearray(); after = 0; codecs = set()
            while True:
                page = q(db, 'Q11', body_hash=large_hash, after_part=after, manifest_part_count=mf['part_count'], page_limit=3)
                if not page:
                    break
                for seq, text in page:
                    item = json.loads(text.read() if hasattr(text, 'read') else text)
                    stored = base64.b64decode(item['data_base64'], validate=True)
                    if digest(stored) != item['stored_sha256']:
                        raise AssertionError('Stored part hash')
                    raw = zlib.decompress(stored) if item['codec'] == 'ZLIB_BASE64' else stored
                    if seq != after + 1 or len(raw) != item['raw_bytes'] or digest(raw) != item['raw_sha256']:
                        raise AssertionError('Raw part order/hash/bytes')
                    restored.extend(raw); after = seq; codecs.add(item['codec'])
            check('large_multibyte_body_exact', bytes(restored) == large_raw and after == mf['part_count'] and len(restored) == mf['total_bytes'] and digest(bytes(restored)) == mf['body_sha256'],
                  raw_bytes=len(restored), parts=after, codecs=sorted(codecs))
            decoded = json.loads(restored)
            check('null_empty_leading_id_preserved', decoded['null_value'] is None and decoded['empty_string'] == '' and decoded['leading_id'] == '0001' and decoded['reason'] is None and decoded['purpose'] is None)
            # Tests of physical constraints only; typed immutability/ACL is not installed.
            import oracledb
            try:
                rec(db, 'CASE_NODE', ids['entity'], 1, 1, h2)
            except oracledb.IntegrityError as exc:
                check('duplicate_pk_rejected', exc.args[0].code == 1)
            else:
                check('duplicate_pk_rejected', False)
            new_value = {**state_value, 'counter': 2}
            with db.cursor() as c:
                c.setinputsizes(body=oracledb.DB_TYPE_CLOB)
                c.execute(f'UPDATE {OWNER}.{STATE} SET CHG_SEQ_NO=2,ST_HASH_VAL=:sha,ST_JSON_CN=:body WHERE SCOPE_HASH_VAL=:scope AND ST_KEY_ID=:key AND CHG_SEQ_NO=1',
                          sha=state_hash(2, new_value), body=canonical(new_value), scope=scope, key=state_key)
                check('state_expected_revision_update', c.rowcount == 1)
                c.execute(f'UPDATE {OWNER}.{STATE} SET CHG_SEQ_NO=3 WHERE SCOPE_HASH_VAL=:scope AND ST_KEY_ID=:key AND CHG_SEQ_NO=1', scope=scope, key=state_key)
                check('stale_revision_changes_zero_rows', c.rowcount == 0)
            rec(db, 'EVENT', digest({'event': 3, 'attempt': attempt}), 1, 3, h2)
            db.rollback()
        with connection() as db:
            got = rows(db, f'SELECT CHG_SEQ_NO,ST_HASH_VAL FROM {OWNER}.{STATE} WHERE SCOPE_HASH_VAL=:scope AND ST_KEY_ID=:key', scope=scope, key=state_key)
            check('multi_table_rollback_after_reconnect', got == [[1, state_hash(1, state_value)]] and not q(db, 'Q04', after_seq=2, event_watermark=3))
            check('scope_predicate_isolates_fixture', q(db, 'Q01', scope=digest({'other_scope': attempt})) == [])
        result = {'status': 'LIVE_ORACLE_SCHEMA_CHECKS_PASSED', 'synthetic_scope': scope, 'attempt': attempt,
                  'tests': tests, 'query_templates_executed': 11, 'raw_body_bytes': len(large_raw), 'body_parts': manifest['part_count'],
                  'connection_user': 'SYSTEM (maintenance); application credentials/ACL not exercised',
                  'not_verified': ['runtime adapter', 'immutable typed record policy', 'application ACL', 'concurrent workers',
                                   'ORDS CLOB transport', 'real record migration', 'RAG E2E', 'performance benchmark', 'GENOS']}
    except Exception as exc:
        result = {'status': 'FAILED', 'attempt': attempt, 'synthetic_scope': scope, 'tests': tests, 'error_type': type(exc).__name__, 'error': str(exc)}
        raise
    finally:
        # Only this invocation's explicitly synthetic, uniquely scoped rows.
        # No original record or any other invocation's test scope is deleted.
        with connection() as db, db.cursor() as c:
            cleanup = {}
            for name in ['LGL_AGT_REC_A', 'LGL_AGT_RUN_A', STATE, 'LGL_AGT_BODY_A']:
                c.execute(f'DELETE FROM {OWNER}.{name} WHERE SCOPE_HASH_VAL=:scope', scope=scope)
                cleanup[name] = c.rowcount
            db.commit()
        event(phase='VERIFY_SYNTHETIC_CLEANED', attempt=attempt, scope=scope, deleted_own_synthetic_rows=cleanup)
        if result is not None:
            result['synthetic_cleanup_rows'] = cleanup
            with connection() as db:
                result['protected_after'] = protected_snapshot(db)
                result['protected_baseline_unchanged'] = result['protected_after'] == p['protected_before']
                result['new_table_counts_after_cleanup'] = {t['name']: rows(db, f'SELECT COUNT(*) FROM {OWNER}.{t["name"]}')[0][0] for t in schema()['tables']}
            save('verification-' + attempt + '.json', result)
            if not result['protected_baseline_unchanged']:
                raise RuntimeError('Protected baseline changed during verification')
    print(canonical({'phase': 'VERIFY', 'status': result['status'], 'checks': len(tests), 'raw_body_bytes': len(large_raw),
                     'body_parts': manifest['part_count'], 'new_table_counts_after_cleanup': result['new_table_counts_after_cleanup']}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['plan', 'apply', 'verify'])
    phase = parser.parse_args().phase
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'maintenance.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            {'plan': plan, 'apply': apply, 'verify': smoke}[phase]()
        except Exception as exc:
            event(phase=phase.upper() + '_FAILED', error_type=type(exc).__name__, error=str(exc))
            raise


if __name__ == '__main__':
    main()
