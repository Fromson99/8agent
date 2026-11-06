from pathlib import Path
from zipfile import ZipFile
import hashlib,json,re,secrets,subprocess,sys,traceback
from types import SimpleNamespace
from datetime import datetime,timezone
import oracledb
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/20261105-agent-gold-layer'
BUILD=json.loads((OUT/'BUILD.json').read_text())
checks=[]
def check(name,ok,detail=None):
    if not ok: raise AssertionError(name+': '+str(detail))
    checks.append({'name':name,'passed':True,**({'detail':detail} if detail is not None else {})})
info=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
assert info['Config']['Labels']['a8.task']=='legal-mapped-20261023' and info['State']['Running']
ep=info['HostConfig']['PortBindings']['1521/tcp'];assert len(ep)==1 and ep[0]['HostIp']=='127.0.0.1'
pw=dict(x.split('=',1) for x in info['Config']['Env'])['ORACLE_PASSWORD']
db=oracledb.connect(user='system',password=pw,dsn='127.0.0.1:'+ep[0]['HostPort']+'/FREEPDB1');db.call_timeout=20000
owner='A8_AGSQL_'+secrets.token_hex(5).upper();created=False
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
result={'environment':'isolated schema in existing loopback-only local Oracle; Dataiku and GENOS not contacted','sql_owner_substitution_for_test':owner,'oracle_version':db.version,'checks':checks,'status':'RUNNING'}
def execute(sql,binds=None):
    with db.cursor() as c:
        c.execute(sql,binds or {})
        if c.description:
            names=[x[0] for x in c.description]
            return [{k:(v.read() if hasattr(v,'read') else v) for k,v in zip(names,row)} for row in c]
        return []
def isolated(s):return s.replace('SIDDA.',owner+'.').replace("'SIDDA'","'"+owner+"'")
def objects():
    return execute("SELECT OWNER,OBJECT_NAME,OBJECT_TYPE,OBJECT_ID,DATA_OBJECT_ID,STATUS FROM DBA_OBJECTS WHERE OWNER IN ('SIDDA','A8_GR12_CM1208') ORDER BY OWNER,OBJECT_NAME,OBJECT_TYPE")
try:
    before=objects()
    with ZipFile(OUT/'AGENT_GOLD_SQL_20261105_R1.zip') as z:
        check('zip_only_14_plain_sql_files',len(z.namelist())==14 and all(n.endswith('.sql') and '/' not in n for n in z.namelist()))
        sqls={n:z.read(n).decode() for n in z.namelist()}
    check('exact_sql_files_and_txt',all(hashlib.sha256(v.encode()).hexdigest()==BUILD['sql_files'][n] and v in (OUT/'AGENT_GOLD_SQL_RUN_R1.txt').read_text() for n,v in sqls.items()))
    ddls=[s for n,s in sorted(sqls.items()) if '_CREATE_' in n]
    check('only_four_agent_tables_seven_indexes',len(ddls)==11 and sum(s.startswith('CREATE TABLE ') for s in ddls)==4 and sum(s.startswith('CREATE INDEX ') for s in ddls)==7 and all(re.match(r'CREATE (TABLE|INDEX) SIDDA\.LGL_(?:AGT_|EXEC_ST_|AR0)',s) for s in ddls) and not any(re.search(r'\b(?:DROP|ALTER|TRUNCATE|GRANT|INSERT|UPDATE|DELETE)\b',s) for s in ddls))
    execute('CREATE USER '+owner+' IDENTIFIED BY "'+secrets.token_hex(18)+'" QUOTA 30M ON USERS')
    created=True
    execute('CREATE TABLE '+owner+'.PROTECTED_GOLD (ID NUMBER PRIMARY KEY, BODY VARCHAR2(32))')
    execute("INSERT INTO "+owner+".PROTECTED_GOLD VALUES (1,'preserve-gold')")
    execute('CREATE TABLE '+owner+'.LGL_AGT_BODY_A (ID NUMBER PRIMARY KEY)')
    execute('INSERT INTO '+owner+'.LGL_AGT_BODY_A VALUES (1)');db.commit()
    pre=execute(isolated(sqls['00_CHECK_EXISTING.sql']))
    check('before_create_all_four_missing',len(pre)==4 and all(x['OBJECT_TYPE'] is None for x in pre))
    # Partial completion can resume with only remaining CREATE statements.
    for s in ddls[:2]:execute(isolated(s))
    partial=execute(isolated(sqls['12_VERIFY_TABLES.sql']))
    check('partial_creation_reported',sum(x['COLUMNS_RESULT']=='PASS' for x in partial)==2 and sum(x['COLUMNS_RESULT']=='FAIL' for x in partial)==2)
    for s in ddls[2:]:execute(isolated(s))
    final=execute(isolated(sqls['12_VERIFY_TABLES.sql']))
    check('exact_delivery_ddl_tables_and_pk',len(final)==4 and all(x['COLUMNS_RESULT']==x['PK_RESULT']=='PASS' for x in final) and sum(x['ACTUAL_COLUMNS'] for x in final)==26,final)
    indexes=execute(isolated(sqls['13_VERIFY_INDEXES.sql']))
    check('all_seven_indexes_valid',len({x['EXPECTED_INDEX'] for x in indexes})==7 and all(x['STATUS']=='VALID' and x['UNIQUENESS']=='NONUNIQUE' for x in indexes))
    for row in indexes:
        if row['EXPECTED_COLUMN'] in ('STRT_DTTM','CHG_DTTM'):
            assert row['COLUMN_EXPRESSION']=='SYS_EXTRACT_UTC("'+row['EXPECTED_COLUMN']+'")'
        else:assert row['ACTUAL_COLUMN']==row['EXPECTED_COLUMN'] and row['COLUMN_EXPRESSION'] is None
    check('index_columns_and_timestamp_expressions',True)
    sys.path.insert(0,str(ROOT/'02_BACKEND'))
    from semantic_runtime.oracle_agent_records import AgentRecords
    from semantic_runtime.oracle_dp_io import DPError
    from semantic_runtime.oracle_gold_mapping import GoldMapping
    mapping=GoldMapping.load(owner='SIDDS')
    roles={'body':'AGT_BODY','record':'AGT_REC','run':'AGT_RUN','state':'EXEC_ST'}
    check('current_gold_consumer_mapping_exact',dict(mapping.agent_tables)=={k:'SIDDA.'+BUILD['tables'][v]['name'] for k,v in roles.items()})
    class ActualSQL:
        client=SimpleNamespace(schema_map=SimpleNamespace(agent_tables={k:owner+'.'+BUILD['tables'][v]['name'] for k,v in roles.items()}))
        def query(self,statement,binds=(),limit=100):
            return execute(statement,{k:v for k,v,*_ in binds})
    record=AgentRecords(ActualSQL())
    check('original_agent_records_preflight',record.preflight()['user_columns']==26)
    execute('INSERT INTO '+owner+'.LGL_AGT_BODY_A_1 VALUES (:s,:b,0,:j)',{'s':'a'*64,'b':'b'*64,'j':'{"preserve":true}'});db.commit()
    for s in ddls:
        try:execute(isolated(s))
        except oracledb.DatabaseError as exc:assert exc.args[0].code==955
        else:raise AssertionError('Duplicate CREATE unexpectedly succeeded')
    check('duplicate_create_refused_existing_row_preserved',execute('SELECT COUNT(*) N FROM '+owner+'.LGL_AGT_BODY_A_1')[0]['N']==1)
    execute('ALTER TABLE '+owner+'.LGL_AGT_BODY_A_1 ADD EXTRA_COLUMN NUMBER')
    changed=execute(isolated(sqls['12_VERIFY_TABLES.sql']))
    check('verification_rejects_extra_column',next(x for x in changed if x['TABLE_NAME']=='LGL_AGT_BODY_A_1')['COLUMNS_RESULT']=='FAIL')
    try:record.preflight()
    except DPError as exc:assert str(exc).startswith('AGENT_SCHEMA:')
    else:raise AssertionError('Consumer accepted extra column')
    check('original_consumer_rejects_column_drift',True)
    execute('ALTER TABLE '+owner+'.LGL_AGT_BODY_A_1 DROP COLUMN EXTRA_COLUMN')
    execute('ALTER TABLE '+owner+'.LGL_AGT_BODY_A_1 MODIFY PART_JSON_CN NULL')
    changed=execute(isolated(sqls['12_VERIFY_TABLES.sql']))
    check('verification_rejects_nullability_drift',next(x for x in changed if x['TABLE_NAME']=='LGL_AGT_BODY_A_1')['COLUMNS_RESULT']=='FAIL')
    try:record.preflight()
    except DPError as exc:assert str(exc).startswith('AGENT_SCHEMA_TYPE:')
    else:raise AssertionError('Consumer accepted type drift')
    execute('ALTER TABLE '+owner+'.LGL_AGT_BODY_A_1 MODIFY PART_JSON_CN NOT NULL')
    execute('ALTER TABLE '+owner+'.LGL_AGT_BODY_A_1 DISABLE CONSTRAINT LGL_AR03_PK_A_1')
    changed=execute(isolated(sqls['12_VERIFY_TABLES.sql']))
    check('verification_rejects_disabled_pk',next(x for x in changed if x['TABLE_NAME']=='LGL_AGT_BODY_A_1')['PK_RESULT']=='FAIL')
    try:record.preflight()
    except DPError as exc:assert str(exc).startswith('AGENT_SCHEMA_PK:')
    else:raise AssertionError('Consumer accepted disabled PK')
    execute('ALTER TABLE '+owner+'.LGL_AGT_BODY_A_1 ENABLE CONSTRAINT LGL_AR03_PK_A_1')
    for rev,body in [(0,'{}'),(1,'not-json')]:
        try:execute('INSERT INTO '+owner+'.LGL_EXEC_ST_A_1 VALUES (:s,:k,:r,:h,:j)',{'s':'a'*64,'k':'test','r':rev,'h':'b'*64,'j':body})
        except oracledb.DatabaseError as exc:assert exc.args[0].code==2290
        else:raise AssertionError('State integrity constraint did not reject')
    check('state_revision_and_json_checks',True)
    check('final_original_consumer_pass_after_negative_tests',record.preflight()['tables']==4)
    check('gold_and_suffixless_objects_preserved',execute('SELECT BODY FROM '+owner+'.PROTECTED_GOLD')[0]['BODY']=='preserve-gold' and execute('SELECT COUNT(*) N FROM '+owner+'.LGL_AGT_BODY_A')[0]['N']==1)
    check('existing_local_schema_objects_unchanged',before==objects())
    result['status']='PASS'
except BaseException as exc:
    result['status']='FAIL';result['error_type']=type(exc).__name__;result['error']=str(exc)
    traceback.print_exc()
finally:
    if created:
        execute('DROP USER '+owner+' CASCADE')
        result['isolated_schema_removed']=not execute("SELECT USERNAME FROM DBA_USERS WHERE USERNAME='"+owner+"'")
    db.close()
    (AUDIT/('oracle-validation-'+stamp+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(checks),'oracle_version':result['oracle_version'],'isolated_schema_removed':result.get('isolated_schema_removed')},ensure_ascii=False))
if result['status']!='PASS':sys.exit(1)
