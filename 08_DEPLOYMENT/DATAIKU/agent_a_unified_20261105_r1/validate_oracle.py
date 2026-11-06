"""Execute the delivered block only in disposable loopback Oracle schemas."""
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

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
AUDIT = ROOT / '09_ARTIFACTS/AUDITS/20261105-agent-a-unification'
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from semantic_runtime.oracle_agent_records import AgentRecords
from semantic_runtime.oracle_gold_mapping import GoldMapping
from semantic_runtime.oracle_dp_io import DPError

info = json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
assert info['State']['Running'] and info['Config']['Labels']['a8.task']=='legal-mapped-20261023'
ports = info['HostConfig']['PortBindings']['1521/tcp']
assert len(ports)==1 and ports[0]['HostIp']=='127.0.0.1'
dsn='127.0.0.1:'+ports[0]['HostPort']+'/FREEPDB1'
password=dict(v.split('=',1) for v in info['Config']['Env'])['ORACLE_PASSWORD']
admin=oracledb.connect(user='system',password=password,dsn=dsn)
admin.call_timeout=20000
oracledb.defaults.fetch_lobs=False
owner='A8_AGENTA_'+secrets.token_hex(4).upper()
user_password=secrets.token_hex(24)
created=False
conn=None
checks=[]
record={'status':'RUNNING','oracle_version':admin.version,'owner':owner,'checks':checks,
        'field_execution':False,'external_models':0,'owner_substitution_only':True}
build=json.loads((OUT/'BUILD.json').read_text())
block=(OUT/'AGENT_A_CREATE_ALL_R1.sql').read_text()
assert hashlib.sha256(block.encode()).hexdigest()==build['sql_sha256']
assert block==(OUT/'AGENT_A_CREATE_ALL_R1.txt').read_text()

def isolated(text):
    return text.replace('SIDDA.',owner+'.').replace("'SIDDA'","'"+owner+"'")

def query(connection, sql, binds=None):
    with connection.cursor() as c:
        c.execute(sql,binds or {})
        if not c.description:return []
        return [dict(zip([d[0] for d in c.description],row)) for row in c]

def run(sql,binds=None):return query(conn,sql,binds)
def check(name,condition):
    assert condition,name
    checks.append({'name':name,'passed':True})
def objects():
    return query(admin,"SELECT OWNER,OBJECT_NAME,OBJECT_TYPE,OBJECT_ID,DATA_OBJECT_ID,STATUS FROM DBA_OBJECTS WHERE OWNER IN ('SIDDA','A8_GR12_CM1208') ORDER BY OWNER,OBJECT_NAME,OBJECT_TYPE")
def reject(name, expected):
    try:run(isolated(block))
    except oracledb.DatabaseError as exc:
        assert exc.args[0].code==expected,(name,exc.args[0].code,str(exc))
    else:raise AssertionError(name+' accepted invalid schema')
    checks.append({'name':name,'passed':True})

try:
    original_objects=objects()
    query(admin,'CREATE USER '+owner+' IDENTIFIED BY "'+user_password+'" DEFAULT TABLESPACE USERS QUOTA 32M ON USERS')
    created=True
    query(admin,'GRANT CREATE SESSION,CREATE TABLE TO '+owner)
    conn=oracledb.connect(user=owner,password=user_password,dsn=dsn)
    conn.call_timeout=20000
    run('CREATE TABLE '+owner+'.PROTECTED_GOLD (ID NUMBER PRIMARY KEY, BODY VARCHAR2(32))')
    run("INSERT INTO "+owner+".PROTECTED_GOLD VALUES (1,'preserve-gold')")
    run('CREATE TABLE '+owner+'.LGL_AGT_BODY_A_1 (ID NUMBER PRIMARY KEY)')
    run('INSERT INTO '+owner+'.LGL_AGT_BODY_A_1 VALUES (9)')
    conn.commit()
    # Pre-existing incompatible A is refused before creating any of the other tables.
    run('CREATE TABLE '+owner+'.LGL_AGT_BODY_A (WRONG_COLUMN NUMBER)')
    reject('incompatible_existing_table_refused_before_ddl',20051)
    check('mismatch_did_not_create_remaining_tables',not run("SELECT TABLE_NAME FROM USER_TABLES WHERE TABLE_NAME IN ('LGL_AGT_REC_A','LGL_AGT_RUN_A','LGL_EXEC_ST_A')"))
    run('DROP TABLE '+owner+'.LGL_AGT_BODY_A PURGE')
    # Exact one-block execution, then rerun against existing objects.
    run(isolated(block))
    verification=run(isolated((OUT/'VERIFY_TABLES.sql').read_text()))
    check('single_block_created_four_exact_tables_and_pks',len(verification)==4 and all(r['COLUMNS_RESULT']==r['PK_RESULT']=='PASS' for r in verification) and sum(r['ACTUAL_COLUMNS'] for r in verification)==26)
    check('all_seven_indexes_created',run("SELECT COUNT(*) N FROM USER_INDEXES WHERE INDEX_NAME IN ("+','.join("'"+i['name']+"'" for i in build['indexes'])+") AND STATUS='VALID'")[0]['N']==7)
    run('INSERT INTO '+owner+'.LGL_AGT_BODY_A VALUES (:s,:b,0,:j)',{'s':'a'*64,'b':'b'*64,'j':'{"preserve":true}'})
    conn.commit()
    before_ids=run('SELECT OBJECT_NAME,OBJECT_TYPE,OBJECT_ID,DATA_OBJECT_ID FROM USER_OBJECTS ORDER BY OBJECT_NAME,OBJECT_TYPE')
    run(isolated(block))
    check('identical_rerun_keeps_object_ids_and_rows',before_ids==run('SELECT OBJECT_NAME,OBJECT_TYPE,OBJECT_ID,DATA_OBJECT_ID FROM USER_OBJECTS ORDER BY OBJECT_NAME,OBJECT_TYPE') and run('SELECT COUNT(*) N FROM '+owner+'.LGL_AGT_BODY_A')[0]['N']==1)
    # Simulate partial earlier execution by removing only a test index.
    idx=build['indexes'][-1]
    run('DROP INDEX '+owner+'.'+idx['name'])
    run(isolated(block))
    check('missing_index_resumed_without_table_recreation',run("SELECT COUNT(*) N FROM USER_INDEXES WHERE INDEX_NAME=:n",{'n':idx['name']})[0]['N']==1)
    mapping=GoldMapping.load(owner='APP_GOLD')
    actual_tables={k:v.replace('SIDDA.',owner+'.') for k,v in mapping.agent_tables.items()}
    class ActualSQL:
        client=SimpleNamespace(schema_map=SimpleNamespace(agent_tables=actual_tables))
        def query(self, statement, binds=(), limit=100):
            rows=run(statement,{k:v for k,v,*_ in binds})
            assert len(rows)<=limit
            return rows
    records=AgentRecords(ActualSQL())
    check('actual_gold_agent_consumer_preflight',records.preflight()['user_columns']==26)
    for change, undo, tag in [
        ('ADD EXTRA_COLUMN NUMBER','DROP COLUMN EXTRA_COLUMN','extra_column'),
        ('MODIFY PART_JSON_CN NULL','MODIFY PART_JSON_CN NOT NULL','nullability'),
        ('DISABLE CONSTRAINT LGL_AR03_PK_A','ENABLE CONSTRAINT LGL_AR03_PK_A','disabled_pk'),
    ]:
        run('ALTER TABLE '+owner+'.LGL_AGT_BODY_A '+change)
        reject('existing_'+tag+'_refused',20051)
        try:records.preflight()
        except DPError:pass
        else:raise AssertionError('runtime accepted '+tag)
        run('ALTER TABLE '+owner+'.LGL_AGT_BODY_A '+undo)
    # Same name on the wrong table, then wrong column order, must not be skipped.
    run('DROP INDEX '+owner+'.'+idx['name'])
    run('CREATE INDEX '+owner+'.'+idx['name']+' ON '+owner+'.PROTECTED_GOLD (BODY)')
    reject('same_index_name_wrong_table_refused',20053)
    run('DROP INDEX '+owner+'.'+idx['name'])
    run('CREATE INDEX '+owner+'.'+idx['name']+' ON '+owner+'.'+idx['table']+' ('+','.join(reversed(idx['columns']))+')')
    reject('same_index_name_wrong_columns_refused',20057)
    run('DROP INDEX '+owner+'.'+idx['name'])
    run(isolated(block))
    for rev,body in [(0,'{}'),(1,'not-json')]:
        try:run('INSERT INTO '+owner+'.LGL_EXEC_ST_A VALUES (:s,:k,:r,:h,:j)',{'s':'a'*64,'k':'test','r':rev,'h':'b'*64,'j':body})
        except oracledb.DatabaseError as exc:assert exc.args[0].code==2290
        else:raise AssertionError('state integrity constraint missing')
    check('new_state_revision_and_json_constraints_enforced',True)
    check('protected_gold_and_a1_rows_preserved',run('SELECT BODY FROM '+owner+'.PROTECTED_GOLD')[0]['BODY']=='preserve-gold' and run('SELECT ID FROM '+owner+'.LGL_AGT_BODY_A_1')[0]['ID']==9)
    check('final_runtime_preflight_after_negative_cases',records.preflight()['tables']==4)
    check('existing_real_local_schemas_unchanged',objects()==original_objects)
    record['status']='PASS'
except BaseException as exc:
    record.update(status='FAIL',error_type=type(exc).__name__,error=str(exc))
    traceback.print_exc()
finally:
    if conn:conn.close()
    if created:
        query(admin,'DROP USER '+owner+' CASCADE')
        record['temporary_schema_removed']=not query(admin,'SELECT USERNAME FROM DBA_USERS WHERE USERNAME=:n',{'n':owner})
    admin.close()
    record['sql_sha256']=build['sql_sha256']
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    (AUDIT/('oracle-'+stamp+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':record['status'],'checks':len(checks),'oracle_version':record['oracle_version'],'temporary_schema_removed':record.get('temporary_schema_removed')},ensure_ascii=False))
if record['status']!='PASS':sys.exit(1)
