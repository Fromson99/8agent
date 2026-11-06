from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
import hashlib
import json
import secrets
import subprocess
import sys
import traceback
import oracledb

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
AUDIT = ROOT / '09_ARTIFACTS/AUDITS/20261105-agent-nosuffix-onequery'
AUDIT.mkdir(exist_ok=True)
raw = (OUT / 'SIDDA_AGENT_NO1_ONEQUERY_R2.sql').read_text()
info = json.loads(subprocess.check_output(['docker', 'inspect', 'a8-legal-mapped-20261023']))[0]
assert info['State']['Running'] and info['Config']['Labels']['a8.task'] == 'legal-mapped-20261023'
ports = info['HostConfig']['PortBindings']['1521/tcp']
assert len(ports) == 1 and ports[0]['HostIp'] == '127.0.0.1'
password = dict(x.split('=', 1) for x in info['Config']['Env'])['ORACLE_PASSWORD']
db = oracledb.connect(user='system', password=password, dsn='127.0.0.1:' + ports[0]['HostPort'] + '/FREEPDB1')
db.call_timeout = 20000
owner = 'A8_AGONCE_' + secrets.token_hex(5).upper()
created = False
checks = []
result = {'status': 'RUNNING', 'oracle_version': db.version, 'checks': checks,
          'sql_sha256': hashlib.sha256(raw.encode()).hexdigest(),
          'scope': 'Exact single SQL block; only SIDDA owner replaced with isolated local test owner.',
          'field_Dataiku_tested': False, 'field_Genos_tested': False}

def sql(text, binds=None):
    with db.cursor() as c:
        c.execute(text, binds or {})
        if not c.description:
            return []
        names = [x[0] for x in c.description]
        return [dict(zip(names, [v.read() if hasattr(v, 'read') else v for v in row])) for row in c]

def isolate(text):
    return text.replace('SIDDA.', owner + '.').replace("'SIDDA'", "'" + owner + "'")

def check(name, condition):
    assert condition, name
    checks.append({'name': name, 'passed': True})

def objects(target):
    return sql('SELECT OBJECT_NAME,OBJECT_TYPE,OBJECT_ID,DATA_OBJECT_ID,STATUS FROM DBA_OBJECTS '
               'WHERE OWNER=:o ORDER BY OBJECT_NAME,OBJECT_TYPE', {'o': target})

def refused(name, code):
    before = objects(owner)
    try:
        sql(isolate(raw))
    except oracledb.DatabaseError as exc:
        check(name, exc.args[0].code == code)
    else:
        raise AssertionError(name + ': invalid structure accepted')
    check(name + '_existing_objects_unchanged', before == objects(owner))

try:
    protected = {o: objects(o) for o in ('SIDDA', 'A8_GR12_CM1208')}
    sql('CREATE USER ' + owner + ' IDENTIFIED BY "' + secrets.token_hex(18) + '" QUOTA 30M ON USERS')
    created = True
    sql('CREATE TABLE ' + owner + '.LGL_AGT_BODY_A_1 (ID NUMBER PRIMARY KEY)')
    sql('INSERT INTO ' + owner + '.LGL_AGT_BODY_A_1 VALUES (1)')
    db.commit()
    sql(isolate(raw))
    verify = (ROOT / '08_DEPLOYMENT/DATAIKU/agent_layer_nosuffix_20261105_r1/package/12_VERIFY_TABLES.sql').read_text()
    rows = sql(isolate(verify))
    check('single_execute_creates_four_tables_26_columns_and_pks', len(rows) == 4 and
          all(r['COLUMNS_RESULT'] == r['PK_RESULT'] == 'PASS' for r in rows) and sum(r['ACTUAL_COLUMNS'] for r in rows) == 26)
    check('seven_secondary_indexes_created', sql('SELECT COUNT(*) N FROM ALL_INDEXES WHERE OWNER=:o '
          "AND UNIQUENESS='NONUNIQUE'", {'o': owner})[0]['N'] == 7)
    sys.path.insert(0, str(ROOT / '02_BACKEND'))
    from semantic_runtime.oracle_agent_records import AgentRecords
    class ActualSQL:
        client = SimpleNamespace(schema_map=SimpleNamespace(agent_tables={
            'body': owner + '.LGL_AGT_BODY_A', 'record': owner + '.LGL_AGT_REC_A',
            'run': owner + '.LGL_AGT_RUN_A', 'state': owner + '.LGL_EXEC_ST_A'}))
        def query(self, statement, binds=(), limit=100):
            return sql(statement, {k: v for k, v, *_ in binds})
    records = AgentRecords(ActualSQL())
    check('original_product_consumer_preflight_passes', records.preflight()['user_columns'] == 26)
    sql('INSERT INTO ' + owner + '.LGL_AGT_BODY_A VALUES (:s,:h,0,:j)',
        {'s': 'a' * 64, 'h': 'b' * 64, 'j': '{"preserve":true}'})
    db.commit()
    before = objects(owner)
    sql(isolate(raw))
    check('same_block_rerun_has_no_object_changes', before == objects(owner))
    check('existing_body_row_preserved', sql('SELECT COUNT(*) N FROM ' + owner + '.LGL_AGT_BODY_A')[0]['N'] == 1)
    sql('DROP TABLE ' + owner + '.LGL_AGT_RUN_A PURGE')
    sql(isolate(raw))
    check('partially_missing_run_table_and_indexes_recreated', records.preflight()['tables'] == 4)
    sql('ALTER TABLE ' + owner + '.LGL_AGT_BODY_A ADD EXTRA_COLUMN NUMBER')
    refused('extra_column_rejected', 20002)
    sql('ALTER TABLE ' + owner + '.LGL_AGT_BODY_A DROP COLUMN EXTRA_COLUMN')
    sql('ALTER TABLE ' + owner + '.LGL_AGT_BODY_A RENAME COLUMN PART_JSON_CN TO WRONG_COLUMN')
    refused('missing_column_rejected', 20003)
    sql('ALTER TABLE ' + owner + '.LGL_AGT_BODY_A RENAME COLUMN WRONG_COLUMN TO PART_JSON_CN')
    sql('ALTER TABLE ' + owner + '.LGL_EXEC_ST_A MODIFY ST_KEY_ID VARCHAR2(129 BYTE)')
    sql('DROP INDEX ' + owner + '.LGL_AR01_I2_A')
    refused('type_drift_stops_before_creating_missing_index', 20004)
    sql('ALTER TABLE ' + owner + '.LGL_EXEC_ST_A MODIFY ST_KEY_ID VARCHAR2(128 BYTE)')
    sql(isolate(raw))
    sql('ALTER TABLE ' + owner + '.LGL_AGT_BODY_A MODIFY PART_JSON_CN NULL')
    refused('nullability_drift_rejected', 20004)
    sql('ALTER TABLE ' + owner + '.LGL_AGT_BODY_A MODIFY PART_JSON_CN NOT NULL')
    sql('ALTER TABLE ' + owner + '.LGL_AGT_BODY_A DISABLE CONSTRAINT LGL_AR03_PK_A')
    refused('disabled_pk_rejected', 20005)
    sql('ALTER TABLE ' + owner + '.LGL_AGT_BODY_A ENABLE CONSTRAINT LGL_AR03_PK_A')
    sql('DROP INDEX ' + owner + '.LGL_AR01_I2_A')
    sql('CREATE INDEX ' + owner + '.LGL_AR01_I2_A ON ' + owner + '.LGL_AGT_RUN_A (REQ_KEY_HASH_VAL)')
    refused('wrong_existing_index_columns_rejected', 20008)
    sql('DROP INDEX ' + owner + '.LGL_AR01_I2_A')
    sql(isolate(raw))
    check('final_product_consumer_passes', records.preflight()['tables'] == 4)
    check('suffix1_table_and_data_untouched', sql('SELECT ID FROM ' + owner + '.LGL_AGT_BODY_A_1') == [{'ID': 1}])
    sql('DROP TABLE ' + owner + '.LGL_AGT_RUN_A PURGE')
    sql('CREATE VIEW ' + owner + '.LGL_AGT_RUN_A AS SELECT 1 ID FROM DUAL')
    refused('view_name_collision_rejected', 20001)
    check('existing_real_schema_objects_unchanged', protected == {o: objects(o) for o in protected})
    result['status'] = 'PASS_LOCAL'
except BaseException as exc:
    result.update(status='FAIL', error_type=type(exc).__name__, error=str(exc))
    traceback.print_exc()
finally:
    if created:
        sql('DROP USER ' + owner + ' CASCADE')
        result['test_schema_removed'] = not sql('SELECT USERNAME FROM DBA_USERS WHERE USERNAME=:o', {'o': owner})
    db.close()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    (AUDIT / ('validation-' + stamp + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': len(checks), 'test_schema_removed': result.get('test_schema_removed')}))
if result['status'] != 'PASS_LOCAL':
    sys.exit(1)
