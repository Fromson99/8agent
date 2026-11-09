"""Run DEV_E2E_TABLES_R1.txt in disposable local Oracle schemas.

SIDDS/SIDDA/BAIP04APP are replaced by three temporary users. The grantee
then runs the selected MAIN code (mapping preflight + Agent record writes)
with only the delivered object grants. No model, no field DB, no real schema.
"""
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
import hashlib
import json
import re
import secrets
import subprocess
import sys
import tempfile
import time
import traceback

import oracledb

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
active = json.loads((ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
manifest = json.loads((ROOT / active['manifest_path']).read_text())
code_root = ROOT / manifest['code_root']
sys.path.insert(0, str(code_root / '02_BACKEND'))
from semantic_runtime.oracle_agent_records import AgentRecords, RecordSQL  # noqa: E402
from semantic_runtime.oracle_development_mapping import DevelopmentMapping  # noqa: E402
from semantic_runtime.oracle_dp_io import digest  # noqa: E402

info = json.loads(subprocess.check_output(['docker', 'inspect', 'a8-legal-mapped-20261023']))[0]
assert info['State']['Running'] and info['Config']['Labels']['a8.task'] == 'legal-mapped-20261023'
ports = info['HostConfig']['PortBindings']['1521/tcp']
assert len(ports) == 1 and ports[0]['HostIp'] == '127.0.0.1'
dsn = '127.0.0.1:' + ports[0]['HostPort'] + '/FREEPDB1'
password = dict(v.split('=', 1) for v in info['Config']['Env'])['ORACLE_PASSWORD']
oracledb.defaults.fetch_lobs = False

tag = secrets.token_hex(3).upper()
silver, agent, grantee = 'A8_DS_' + tag, 'A8_DA_' + tag, 'A8_DG_' + tag
grantee_password = secrets.token_hex(20)
delivery = (OUT / 'DEV_E2E_TABLES_R1.txt').read_text()
checks = []
record = {'status': 'RUNNING', 'started_at': datetime.now(timezone.utc).isoformat(),
          'delivery_sha256': hashlib.sha256(delivery.encode()).hexdigest(),
          'selected_code_root': str(code_root.relative_to(ROOT)), 'release_id': active['release_id'],
          'owner_substitution_only': True, 'field_execution': False, 'external_models': 0, 'checks': checks}


def check(name, ok, detail=None):
    checks.append({'name': name, 'passed': bool(ok), **({'detail': detail} if detail is not None else {})})
    if not ok:
        raise AssertionError(name + ' ' + json.dumps(detail, ensure_ascii=False, default=str))


def sub(text):
    return (text.replace('SIDDS.', silver + '.').replace("'SIDDS'", "'" + silver + "'")
            .replace('SIDDA.', agent + '.').replace("'SIDDA'", "'" + agent + "'")
            .replace('BAIP04APP', grantee))


def rows(conn, text, binds=None):
    with conn.cursor() as c:
        c.execute(text, binds or {})
        if not c.description:
            return []
        names = [d[0] for d in c.description]
        return [dict(zip(names, r)) for r in c]


# Delivery shape: blocks introduced by "-- [ID]" comment lines, one statement each.
blocks = re.findall(r'^-- \[([A-Z]\d\d)\][^\n]*\n(.+?)(?=\n\n-- \[|\n*\Z)', delivery, flags=re.M | re.S)
ids = [b[0] for b in blocks]
check('statement_ids', ids == ['C00', *['S%02d' % i for i in range(1, 7)], *['A%02d' % i for i in range(1, 12)],
                               *['G%02d' % i for i in range(1, 19)], 'V01', 'V02'], ids)
check('no_semicolon_no_marker_ascii', ';' not in delivery and 'DKU_END' not in delivery and delivery.isascii())
check('one_line_per_statement', all('\n' not in s.strip() for _, s in blocks))
statement = dict(blocks)

mapping_raw = json.loads((code_root / '00_SYSTEM/ORACLE/development_g19_1.json').read_text())
admin = oracledb.connect(user='system', password=password, dsn=dsn)
admin.call_timeout = 30000
created = []
try:
    for user in (silver, agent):
        rows(admin, f'CREATE USER {user} NO AUTHENTICATION DEFAULT TABLESPACE USERS QUOTA 64M ON USERS')
        created.append(user)
    rows(admin, f'CREATE USER {grantee} IDENTIFIED BY "{grantee_password}"')
    created.append(grantee)
    rows(admin, f'GRANT CREATE SESSION TO {grantee}')

    # Stand-ins for objects that already exist in the dev DB (10 SIDDS + stage table).
    def ddl(owner, table):
        cols = []
        for c in table['columns'].values():
            typ = c['type'].replace('VECTOR(*,FLOAT32)', 'VECTOR(*, FLOAT32)')
            cols.append(c['name'] + ' ' + typ + (' NOT NULL' if c['required'] else ''))
        pk = [table['columns'][k]['name'] for k in table.get('primary_key', [])]
        tail = (', PRIMARY KEY (' + ', '.join(pk) + ')') if pk else ''
        return f"CREATE TABLE {owner}.{table['name']} ({', '.join(cols)}{tail})"
    existing = [k for k, t in mapping_raw['tables'].items() if t['owner'] == 'SIDDS']
    for key in existing:
        rows(admin, ddl(silver, mapping_raw['tables'][key]))
    rows(admin, f'CREATE TABLE {agent}.LGL_PIPE_RESULT_A (JOB_ID VARCHAR2(64 BYTE) NOT NULL PRIMARY KEY)')
    check('prerequisite_stand_ins', len(existing) == 10)

    before = rows(admin, sub(statement['C00']))
    check('c00_before_only_stage', [r['TABLE_NAME'] for r in before] == ['LGL_PIPE_RESULT_A'], before)
    for sid, text in blocks:
        if sid[0] in 'SAG':
            rows(admin, sub(text))
    after = rows(admin, sub(statement['C00']))
    check('c00_after_all_8', len(after) == 8, [r['TABLE_NAME'] for r in after])

    g = oracledb.connect(user=grantee, password=grantee_password, dsn=dsn)
    g.call_timeout = 30000
    v1 = {r['TABLE_NAME']: r['COLUMN_COUNT'] for r in rows(g, sub(statement['V01']))}
    check('v01_grantee_sees_columns', v1 == {'LGL_G19_ONTL_POST_S_1': 5, 'LGL_G19_ONTL_HEAD_S_1': 3,
          'LGL_G19_ONTL_ANC_S_1': 5, 'LGL_AGT_RUN_A': 9, 'LGL_AGT_REC_A': 8, 'LGL_AGT_BODY_A': 4,
          'LGL_EXEC_ST_A': 5}, v1)
    v2 = {r['TABLE_NAME']: r['PRIVILEGES'] for r in rows(g, sub(statement['V02']))}
    expected_privs = {**{mapping_raw['tables'][k]['name']: 'SELECT' for k in existing},
                      'LGL_G19_ONTL_POST_S_1': 'SELECT', 'LGL_G19_ONTL_HEAD_S_1': 'SELECT', 'LGL_G19_ONTL_ANC_S_1': 'SELECT',
                      'LGL_AGT_RUN_A': 'INSERT,SELECT,UPDATE', 'LGL_AGT_REC_A': 'DELETE,INSERT,SELECT',
                      'LGL_AGT_BODY_A': 'INSERT,SELECT', 'LGL_EXEC_ST_A': 'DELETE,INSERT,SELECT,UPDATE',
                      'LGL_PIPE_RESULT_A': 'INSERT,SELECT'}
    check('v02_grantee_privileges', v2 == expected_privs, v2)

    class Client:
        SQL_PATH = '/dev-e2e-validate'

        def __init__(self, conn, agent_tables):
            self.db = conn
            self.schema_map = SimpleNamespace(agent_tables=agent_tables)

        def request(self, method, path, json):
            types = {'CLOB': oracledb.DB_TYPE_CLOB, 'VARCHAR2': oracledb.DB_TYPE_VARCHAR, 'NUMBER': oracledb.DB_TYPE_NUMBER}
            try:
                with self.db.cursor() as c:
                    binds = json.get('binds', [])
                    c.setinputsizes(**{b['name']: types[b['data_type']] for b in binds})
                    c.execute(json['statementText'], {b['name']: b['value'] for b in binds})
                    if c.description is None:
                        return {'items': [{'result': c.rowcount}]}
                    names = [d[0] for d in c.description]
                    found = c.fetchmany(json['limit'] + 1)
                    value = lambda v: v.read() if isinstance(v, oracledb.LOB) else v  # noqa: E731
                    return {'items': [{'resultSet': {'offset': 0, 'hasMore': len(found) > json['limit'],
                            'items': [{k: value(v) for k, v in zip(names, r)} for r in found[:json['limit']]]}}]}
            except oracledb.DatabaseError as exc:
                return {'items': [{'errorCode': exc.args[0].code}]}

    # Mapping copy with the corrected Silver owner for the ontology tables.
    corrected = json.loads(json.dumps(mapping_raw))
    for key in ('ONTL_POST', 'ONTL_HEAD', 'ONTL_ANC'):
        corrected['tables'][key]['owner'] = 'SIDDS'
        corrected['tables'][key]['name'] = corrected['tables'][key]['name'].replace('_A_1', '_S_1')
    for t in corrected['tables'].values():
        t['owner'] = {'SIDDS': silver, 'SIDDA': agent}[t['owner']]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'development_g19_1.json'
        path.write_text(json.dumps(corrected, ensure_ascii=False))
        mapping = DevelopmentMapping.load(path)
    agent_tables = dict(mapping.agent_tables)
    client = Client(g, agent_tables)
    sql = RecordSQL(client, binding='dev-e2e-validate', deadline=time.monotonic() + 300, max_calls=2000)

    class Meta:
        def query(self, text, binds=(), limit=100):
            got = rows(g, text, {k: v for k, v, *_ in binds})
            assert len(got) <= limit
            return got
    pre = mapping.preflight(Meta())
    check('main_mapping_preflight_17_tables_as_grantee', pre['tables'] == 17, pre)

    store = AgentRecords(sql, namespace='dev-e2e-' + tag.lower())
    check('agent_preflight_as_grantee', store.preflight()['user_columns'] == 26)
    owner = digest('dev-e2e-owner')
    run = {'id': digest('run'), 'session': digest('session'), 'request': digest('request'), 'parent': None,
           'status': 'RUNNING', 'started': '2026-11-06 05:00:00.000000 +00:00'}
    raw = ('dev e2e body ' * 400).encode()
    row = {'key': digest('row'), 'kind': 'SQLROW:dev_e2e', 'order': 1, 'lookup': digest('lookup'),
           'body': hashlib.sha256(raw).hexdigest(), 'deleted': 0, 'owner': None}
    check('commit_insert_state_record_run_body', store.commit(owner, 0, {'step': 1}, [row], run=run, bodies=[raw]) == 1)
    run2 = {**run, 'status': 'COMPLETE'}
    check('commit_update_state_delete_record_merge_run',
          store.commit(owner, 1, {'step': 2}, [{**row, 'deleted': 1}], run=run2) == 2)
    check('state_read_back', store.state('a1:head:' + owner)['value'] == {'step': 2})
    check('body_read_back', store.body(hashlib.sha256(raw).hexdigest()) == raw)
    with store.lease({'dev': 'e2e'}):
        pass
    check('lease_insert_update_delete', True)
    got = rows(g, f"SELECT ST_CD FROM {agent}.LGL_AGT_RUN_A WHERE RUN_KEY_HASH_VAL=:r", {'r': run['id']})
    check('run_row_merged', got == [{'ST_CD': 'COMPLETE'}], got)
    g.close()
    record['status'] = 'PASS'
except BaseException as exc:
    record['status'] = 'FAIL'
    record['error'] = ''.join(traceback.format_exception_only(type(exc), exc)).strip()[:2000]
finally:
    for user in reversed(created):
        try:
            rows(admin, f'DROP USER {user} CASCADE')
        except oracledb.DatabaseError as exc:
            record.setdefault('cleanup_errors', []).append(str(exc)[:300])
    record['temporary_users_removed'] = not rows(
        admin, 'SELECT USERNAME FROM DBA_USERS WHERE USERNAME IN (:a,:b,:c)', {'a': silver, 'b': agent, 'c': grantee})
    record['oracle_version'] = admin.version
    admin.close()
    record['finished_at'] = datetime.now(timezone.utc).isoformat()
    (OUT / 'VALIDATION.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(record['status'], len([c for c in checks if c['passed']]), '/', len(checks), record.get('error', ''))
