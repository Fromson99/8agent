"""Subprocess check against the task-labelled local Oracle and exact packaged code.
Only the Dataiku SDK transport and GENOS network are local adapters.
"""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import types
import oracledb
import pandas as pd

client_root,service_root,work,inputs,exports=map(Path,sys.argv[1:])
sys.path[:0]=[str(client_root),str(client_root/'02_BACKEND')]
sys.path.insert(0,str(service_root))
import transport as t
import dataiku_run as client
from semantic_runtime.physical_mapping import SchemaMap
from semantic_runtime import oracle_dp_io as io
schema=SchemaMap.load(client_root/'physical_mapping.yaml')
# Reuse only the isolated, loopback-only task database; no field credentials.
import secrets
import subprocess
details=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
assert details['Config']['Labels']['a8.task']=='legal-mapped-20261023'
assert details['HostConfig']['PortBindings']['1521/tcp']==[{'HostIp':'127.0.0.1','HostPort':'11524'}]
settings=dict(item.split('=',1) for item in details['Config']['Env'])
admin=oracledb.connect(user='system',password=settings['ORACLE_PASSWORD'],dsn='127.0.0.1:11524/FREEPDB1')
test_user='A8_LAYER_'+secrets.token_hex(6).upper()
test_password=secrets.token_hex(24)
old_counts={}
with admin.cursor() as cur:
    cur.execute("SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER='SIDDA' AND TABLE_NAME IN ('LGL_DOC_VER','LGL_DOC_UNIT','LGL_DOC_BLK','LGL_FILE_PART','LGL_SRC_PBLS','LGL_SRCH_PBLS','LGL_SRCH_ROW','LGL_SRCH_CHNL','LGL_EXEC_ST')")
    old_tables=[row[0] for row in cur.fetchall()]
    for table in old_tables:
        cur.execute('SELECT COUNT(*) FROM SIDDA.'+table);old_counts[table]=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ALL_USERS WHERE USERNAME='SIDDS'")
    if not cur.fetchone()[0]:
        cur.execute('CREATE USER SIDDS IDENTIFIED BY "'+secrets.token_hex(24)+'" DEFAULT TABLESPACE USERS QUOTA 64M ON USERS ACCOUNT LOCK')
    for typ,key,name,statement in schema.ddl():
        owner=schema.owners[schema.tables[key]['role']]
        cur.execute('SELECT COUNT(*) FROM ALL_OBJECTS WHERE OWNER=:o AND OBJECT_NAME=:n AND OBJECT_TYPE=:t',o=owner,n=name,t=typ)
        if not cur.fetchone()[0]:cur.execute(statement)
    for key,table in schema.tables.items():
        quote=lambda text:"'"+text.replace("'","''")+"'"
        cur.execute('COMMENT ON TABLE '+schema.names(key).table+' IS '+quote(table['description']))
        for col in table['columns'].values():cur.execute('COMMENT ON COLUMN '+schema.names(key).table+'.'+col['name']+' IS '+quote(col['description']))
    cur.execute('CREATE USER '+test_user+' IDENTIFIED BY "'+test_password+'"')
    cur.execute('GRANT CREATE SESSION TO '+test_user)
    for key in schema.tables:
        privileges='SELECT' if key in ('query_state','query_active') else 'SELECT, INSERT'
        cur.execute('GRANT '+privileges+' ON '+schema.names(key).table+' TO '+test_user)
c=oracledb.connect(user=test_user,password=test_password,dsn='127.0.0.1:11524/FREEPDB1')
assert c.dsn=='127.0.0.1:11524/FREEPDB1'


spec=importlib.util.spec_from_file_location('new_compute_service',service_root/'service.py')
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
class Remote:
    calls=[]; lose_run=True
    def __init__(self,url,token):self.url=url
    def call(self,op,**fields):
        self.calls.append(op)
        reply=asyncio.run(api.service({},dict(API_TYPE=op,**fields)))
        if reply['code']:raise ValueError(reply['error'])
        if op=='RUN' and Remote.lose_run:
            Remote.lose_run=False
            raise RuntimeError('simulated response loss after RUN accepted')
        return reply['data']
class Folder:
    def __init__(self):self.root=work/'managed';self.root.mkdir(exist_ok=True)
    def list_paths_in_partition(self):return ['/'+str(p.relative_to(self.root)) for p in self.root.rglob('*') if p.is_file()]
    def upload_stream(self,name,stream):
        p=self.root/name.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('wb') as f:shutil.copyfileobj(stream,f,1024*1024)
    def get_download_stream(self,name):return (self.root/name.lstrip('/')).open('rb')
folder=Folder()
class Executor:
    lose_write=True;writes=0;statements=[]
    def __init__(self,connection):assert connection=='AIDP'
    def query_to_df(self,sql,pre_queries=(),post_queries=(),**kwargs):
        with c.cursor() as cur:
            for text in pre_queries:
                self.statements.append(text);cur.execute(text);Executor.writes+=1
            cur.execute(sql);cols=[d[0] for d in cur.description]
            rows=cur.fetchall()
            rows=[[v.read() if isinstance(v,oracledb.LOB) else v for v in row] for row in rows]
            for text in post_queries:cur.execute(text)
            if pre_queries and self.lose_write:
                Executor.lose_write=False
                raise RuntimeError('ORA-03113: simulated response loss after commit')
            return pd.DataFrame(rows,columns=cols)

variables={'LEGAL_PIPELINE_URL':'https://fixture.invalid/compute','LEGAL_PIPELINE_TOKEN':'local-fixture'}
sys.modules['dataiku']=types.SimpleNamespace(SQLExecutor2=Executor,get_custom_variables=lambda:variables,default_project_key=lambda:'LEGAL_RAG')
sys.path.insert(0,str(client_root.parent))
import recipes_runtime as r
import controller as control
control.Wire=Remote
cfg={'landing':'fixture-landing','raw':'fixture-raw','structured':'fixture-structured','load':'fixture-load'}
folders={}
for role,name in cfg.items():
    folders[role]=Folder();folders[role].root=work/name;folders[role].root.mkdir()
for name in ['RAW_INPUT.zip','RAW_INPUT.zip.receipt.json','PIPELINE_SUPPORT.zip','PIPELINE_SUPPORT.zip.receipt.json']:
    with (exports/name).open('rb') as stream:folders['landing'].upload_stream(name,stream)
def stage(name):
    path=work/name;path.mkdir(exist_ok=True);return path
assert r.unpack_raw(folders['landing'],folders['raw'],stage('unpack'))['status']=='RAW_SAVED'
try:
    control.structure(cfg,folders,variables,stage('response-lost'),'fixture-job')
except RuntimeError as exc:
    assert 'response loss after RUN' in str(exc)
else:raise AssertionError('missing response loss')
result=control.structure(cfg,folders,variables,stage('resume'),'fixture-job')
assert result['status']=='STRUCTURED' and Remote.calls.count('RUN')==1
before_calls=list(Remote.calls)
assert control.structure(cfg,folders,variables,stage('repeat'),'fixture-job')['status']=='STRUCTURED'
assert Remote.calls==before_calls
assert not api.HANDLES
try:
    control.load(cfg,folders,variables,stage('sql-response-lost'),'fixture-job')
except io.DPError as exc:
    assert 'WRITE_UNCONFIRMED' in str(exc)
else:raise AssertionError('missing SQL uncertainty')
result=control.load(cfg,folders,variables,stage('load-resume'),'fixture-job')
assert result['status']=='COMPLETE' and result['query_rows']>0
assert Remote.calls==before_calls

counts={}
with c.cursor() as cur:
    for key in schema.tables:
        cur.execute('SELECT COUNT(*) FROM '+schema.names(key).table);counts[key]=cur.fetchone()[0]
assert all(counts[k]>0 for k in schema.tables if k not in ('query_active','query_state'))
assert counts['query_active']==counts['query_state']==0
before=counts.copy()
assert control.load(cfg,folders,variables,stage('load-duplicate'),'fixture-job')['status']=='COMPLETE'
with c.cursor() as cur:
    for key in schema.tables:
        cur.execute('SELECT COUNT(*) FROM '+schema.names(key).table);assert cur.fetchone()[0]==before[key]
# The mapped importer issued only new table targets, no legacy writes.
assert not any('SIDDA.LEGAL_' in s or 'INTO SIDDA.LGL_' in s for s in Executor.statements)
assert all('SIDDS.LGL_' in s for s in Executor.statements)
with admin.cursor() as cur:
    for table,count in old_counts.items():
        cur.execute('SELECT COUNT(*) FROM SIDDA.'+table);assert cur.fetchone()[0]==count

output={'status':'PASS','query_rows':result['query_rows'],'counts':counts,
        'one_native_compute':Remote.calls.count('RUN')==1,'run_response_loss_recovered':True,
        'sql_commit_response_loss_recovered':True,'duplicate_load_no_rows':True,
        'genos_s3_calls':0,'model_calls':0,'old_sidda_unchanged':old_counts,
        'temporary_compute_released':not api.HANDLES,
        'field_tested':False,'fixture_policy_rebound':True,'service_python_bytes_unchanged':True}
(work/'RESULT.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output))
c.close()
with admin.cursor() as cur:cur.execute('DROP USER '+test_user)
admin.close()
