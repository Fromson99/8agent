"""Run the delivered R5 development cell on a disposable loopback Oracle schema."""
import io
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
from tempfile import TemporaryDirectory
import types
import zipfile

import oracledb
import pandas as pd

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE/'DATAIKU_GOLD_ONECLICK_PROD_20261105_R5.zip'
CELL = HERE/'DATAIKU_GOLD_DEV_VECTOR_3TABLES_R5.txt'
NAMES = ['TST_B003_LGL_VCTR_'+key+'_R5' for key in ('ITEM','POST','HEAD')]
result = {'sql_adapter':'Dataiku SDK substitute over real local Oracle', 'cases':{}}
data = json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
assert data['Config']['Labels']['a8.task']=='legal-mapped-20261023'
port, = data['HostConfig']['PortBindings']['1521/tcp']
assert port['HostIp']=='127.0.0.1'
dsn = '127.0.0.1:'+port['HostPort']+'/FREEPDB1'
admin_secret = next(pair.split('=',1)[1] for pair in data['Config']['Env'] if pair.startswith('ORACLE_PASSWORD='))
suffix = secrets.token_hex(4).upper()
owner, login = 'A8_V5O_'+suffix, 'A8_V5L_'+suffix
password = secrets.token_hex(24)
created = []
oracledb.defaults.fetch_lobs=False
code = CELL.read_text()
for old, new in [('ehA8dpVm','test-code'), ('AIDP','local-dev'), ('PIDD2APP',login), ('SIDDA',owner)]:
    assert code.count(repr(old)) == 1
    code=code.replace(repr(old),repr(new))


class Folder:
    def __init__(self, key):
        assert key=='test-code'

    def list_paths_in_partition(self):
        return ['/'+ARCHIVE.name]

    def get_download_stream(self, path):
        assert path=='/'+ARCHIVE.name
        return io.BytesIO(ARCHIVE.read_bytes())


class Executor:
    def __init__(self, connection):
        assert connection=='local-dev'

    def query_to_df(self, query, pre_queries=(), post_queries=(), **kwargs):
        global skip_after_commit
        with conn.cursor() as cur:
            for sql in pre_queries:
                assert not re.search(r'\b(?:ALTER|DROP|DELETE|UPDATE|TRUNCATE)\b',sql,re.I)
                if 'CREATE TABLE' in sql or 'CREATE INDEX' in sql:
                    assert any(' ON '+owner+'.'+n+' (' in sql or 'CREATE TABLE '+owner+'.'+n+' (' in sql for n in NAMES)
                else:
                    assert any('INSERT INTO '+owner+'.'+n+' (' in sql for n in NAMES)
                    dml.append(next(n for n in NAMES if 'INSERT INTO '+owner+'.'+n+' (' in sql))
                cur.execute(sql)
                if skip_after_commit and 'INSERT INTO '+owner+'.'+NAMES[0]+' (' in sql:
                    skip_after_commit=False
                    raise ConnectionError('TEST_LOST_ITEM_COMMIT_ACK')
            cur.execute(query)
            frame=pd.DataFrame(cur.fetchall(),columns=[d[0] for d in cur.description])
            for sql in post_queries:
                assert sql in ('COMMIT','ROLLBACK')
                cur.execute(sql)
            return frame


def invoke():
    ns={}
    exec(compile(code,'<delivered-dev-3-tables>','exec'),ns)
    return ns['RESULT']


def catalog():
    with admin.cursor() as cur:
        cur.execute("SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER=:1",[owner])
        return {n for (n,) in cur}


def count_rows():
    with admin.cursor() as cur:
        counts={}
        for name in sorted(catalog()):
            assert name in NAMES
            cur.execute('SELECT COUNT(*) FROM '+owner+'.'+name)
            counts[name] = cur.fetchone()[0]
        return counts


def configure_case(declaration, body='VARCHAR2(100 BYTE)'):
    # Fixture-only DDL. Drop only the three known tables in our newly allocated schema.
    with admin.cursor() as cur:
        for name in catalog():
            assert name in NAMES
            cur.execute('DROP TABLE '+owner+'.'+name+' PURGE')
        if declaration:
            cur.execute('CREATE TABLE '+owner+'.'+NAMES[0]+' ('
                        'VCTR_POST_ID VARCHAR2(100 BYTE) NOT NULL,VCTR_SCTN_ID VARCHAR2(100 BYTE) NOT NULL,'
                        'RGLT_DOC_ID VARCHAR2(100 BYTE) NOT NULL,BODY_UNIT_ID '+body+' NOT NULL,'
                        'VCTR_DTLS_IFMN_CTNT CLOB NOT NULL,EMBD_VCTR '+declaration+' NOT NULL,'
                        'PRIMARY KEY(VCTR_POST_ID,VCTR_SCTN_ID))')


def check_raw_r5(declaration):
    # Compare the production writer with the development cell's earlier dictionary guard.
    from prod_pipeline import Contract, connection
    from prod_config import target
    from vector_stage import rows_for, vector_sql
    db = connection({'params':{'ORACLE_CONNECTION':'local-dev'}})
    try:
        cfg = target({'TARGET_MODE':'GOLD','GOLD_OWNER':owner,'TABLE_NAMES':{'VCTR_ITEM':NAMES[0]}})
        with TemporaryDirectory() as directory:
            path=Path(directory)/'contract.json'
            path.write_text(json.dumps(cfg))
            contract=Contract(path)
        contract.preflight(db, 'VCTR_ITEM')
        item={'id':'test-raw', 'meta':{'document_id':'test-raw','source_id':'한'*33+'x'}}
        vector=[0.25,0.75,-1.75,2.25]*256
        sql,binds=vector_sql(contract,rows_for('raw-v5',[item],[vector]),1024)
        if declaration=='VECTOR(768,FLOAT32)':
            try:db.block(sql,binds,transaction_managed=True)
            except oracledb.DatabaseError as exc:
                assert exc.args[0].code==51803
                assert count_rows()=={NAMES[0]:0}
                return {'raw_R5_insert':'ORA-51803','rows':0}
            raise AssertionError('raw R5 wrote 1024 coordinates into a 768 column')
        db.block(sql,binds,transaction_managed=True)
        rows=db.query('SELECT VECTOR_DIMENSION_COUNT(EMBD_VCTR) AS DIM, VECTOR_DIMENSION_FORMAT(EMBD_VCTR) AS FMT,'
                      'VECTOR_SERIALIZE(EMBD_VCTR RETURNING CLOB) AS V FROM '+contract.table('VCTR_ITEM'))
        stored=json.loads(rows[0]['V'])
        assert len(rows)==1 and rows[0]['DIM']==1024 and rows[0]['FMT']=='INT8' and stored!=vector
        return {'raw_R5_insert':'STORED_AS_INT8','dimensions':1024,
                'input_first_four':vector[:4],'stored_first_four':stored[:4]}
    finally:
        db.close()


shim=types.ModuleType('dataiku'); shim.Folder=Folder; shim.SQLExecutor2=Executor
sys.modules['dataiku']=shim
skip_after_commit=False
dml=[]
with oracledb.connect(user='system',password=admin_secret,dsn=dsn) as admin:
    try:
        with admin.cursor() as cur:
            for user in (owner, login):
                cur.execute('CREATE USER '+user+' IDENTIFIED BY "'+password+'" DEFAULT TABLESPACE USERS QUOTA 24M ON USERS')
                created.append(user)
            cur.execute('GRANT CREATE SESSION, CREATE ANY TABLE, CREATE ANY INDEX, SELECT ANY TABLE, INSERT ANY TABLE TO '+login)
        with oracledb.connect(user=login,password=password,dsn=dsn) as conn:
            for decl in (None,'VECTOR(*,FLOAT32)','VECTOR(1024,FLOAT32)'):
                configure_case(decl)
                dml.clear()
                key=decl or 'VECTOR'
                if not decl:
                    skip_after_commit=True
                    try:invoke()
                    except ConnectionError as exc:assert 'TEST_LOST_ITEM_COMMIT_ACK' in str(exc)
                    else:raise AssertionError('ack loss not exercised')
                    assert count_rows()=={n:int(n==NAMES[0]) for n in NAMES}
                first=invoke()
                assert first['status']=='DEV_R5_VECTOR_3_TABLES_PASS'
                assert set(catalog())==set(NAMES) and count_rows()=={n:1 for n in NAMES}
                assert first['stored_id_bytes']==100 and first['coordinates_compared']==1024 and first['stored_format']=='FLOAT32'
                assert dml==NAMES
                second=invoke()
                assert set(second['actions'].values())=={'REUSED'} and dml==NAMES
                assert first['actions']['VCTR_POST']==first['actions']['VCTR_HEAD']=='INSERTED'
                result['cases'][key]={'first_or_resumed':first,'second_actions':second['actions'],'counts':count_rows()}
            for decl, body, error in [('VECTOR(768,FLOAT32)','VARCHAR2(100 BYTE)','DEV_VECTOR_DECLARATION_NOT_VERIFIED'),
                                      ('VECTOR(1024,INT8)','VARCHAR2(100 BYTE)','DEV_VECTOR_DECLARATION_NOT_VERIFIED'),
                                      ('VECTOR','VARCHAR2(50 BYTE)','TYPE_MISMATCH:'),
                                      ('VECTOR','VARCHAR2(100 CHAR)','TYPE_MISMATCH:')]:
                configure_case(decl,body)
                dml.clear()
                try:invoke()
                except RuntimeError as exc:
                    assert error in str(exc), exc
                    if error=='TYPE_MISMATCH:': assert 'BODY_UNIT_ID' in str(exc)
                    result['cases'][decl+' / '+body]={'observed_stop':str(exc),'test_row_writes':len(dml)}
                else:raise AssertionError('incompatible schema accepted')
                assert not dml and count_rows()=={NAMES[0]:0}
                if error=='DEV_VECTOR_DECLARATION_NOT_VERIFIED':
                    result['cases'][decl+' / '+body]['unguarded_local_R5']=check_raw_r5(decl)
    finally:
        with admin.cursor() as cur:
            for user in reversed(created):
                cur.execute('DROP USER '+user+' CASCADE')
result['lost_item_response_resumed_without_duplicate']=True
result['disposable_schemas_removed']=True
result['status']='PASS'
Path(sys.argv[1]).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
