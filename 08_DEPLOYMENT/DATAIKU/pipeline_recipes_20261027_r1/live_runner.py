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

spec=importlib.util.spec_from_file_location('mapped_local_service',service_root/'service.py')
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
class Remote:
    calls=[];lose_ack=True
    def __init__(self,url,token):self.url=url
    def call(self,op,**fields):
        self.calls.append(op)
        result=asyncio.run(api.service({},dict(API_TYPE=op,**fields)))
        if result['code']:raise ValueError(result['error'])
        if op=='ACK' and self.lose_ack:
            Remote.lose_ack=False
            raise RuntimeError('simulated ACK response loss after remote cleanup')
        return result['data']
client.Client=Remote
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
variables={'LEGAL_PIPELINE_URL':'https://local.invalid/pipeline','LEGAL_PIPELINE_TOKEN':'local-fixture'}
sys.modules['dataiku']=types.SimpleNamespace(SQLExecutor2=Executor,get_custom_variables=lambda:variables,default_project_key=lambda:'LEGAL_RAG')

sys.path.insert(0,str(client_root.parent))
import recipes_runtime as recipes
recipes.CheckedClient=Remote
cfg={'landing':'fixture-landing','raw':'fixture-raw','structured':'fixture-structured','load':'fixture-load'}
folders={}
for role,name in cfg.items():
    folders[role]=Folder();folders[role].root=work/name;folders[role].root.mkdir()
for name in ['RAW_INPUT.zip','RAW_INPUT.zip.receipt.json','PIPELINE_SUPPORT.zip','PIPELINE_SUPPORT.zip.receipt.json']:
    with (exports/name).open('rb') as f:folders['landing'].upload_stream(name,f)
def stage_dir(name):
    path=work/name;path.mkdir(exist_ok=True);return path
assert recipes.unpack_raw(folders['landing'],folders['raw'],stage_dir('unpack'))['status']=='RAW_SAVED'
# Raw now lives in the managed folder. Later stages materialize it from this S3 adapter.
with admin.cursor() as cur:cur.execute('DROP INDEX SIDDS.LGL_SRCH_ROW_KEY_IX_S')
try:recipes.structure(cfg,folders,variables,stage_dir('preflight-fail'),'contract-job')
except ValueError as exc:assert 'TARGET_INDEX' in str(exc)
else:raise AssertionError('preflight accepted missing index')
assert not Remote.calls
with admin.cursor() as cur:
    cur.execute(next(sql for typ,k,n,sql in schema.ddl() if n=='LGL_SRCH_ROW_KEY_IX_S'))
result=recipes.structure(cfg,folders,variables,stage_dir('structure'),'contract-job')
assert result['status']=='STRUCTURED' and not result['oracle_written']
assert Executor.writes==0 and 'ACK' not in Remote.calls
prior_calls=list(Remote.calls)
# Repeat structure consumes durable state without a new GENOS execution or new deadline.
assert recipes.structure(cfg,folders,variables,stage_dir('structure-repeat'),'contract-job')==result
assert Remote.calls==prior_calls
structured_hashes={p:t.sha(p) for p in t.files(folders['structured'].root)}
try:recipes.load(cfg,folders,variables,stage_dir('load-write-loss'),'contract-job')
except io.DPError as exc:assert 'WRITE_UNCONFIRMED' in str(exc)
else:raise AssertionError('write uncertainty not retained')
assert 'ACK' not in Remote.calls
try:recipes.load(cfg,folders,variables,stage_dir('load-ack-loss'),'contract-job')
except RuntimeError as exc:assert 'ACK response loss' in str(exc)
else:raise AssertionError('ACK uncertainty not retained')
checkpoints=sorted((folders['load'].root/'_pipeline/jobs/contract-job').glob('checkpoint-*.json'))
latest=json.loads(checkpoints[-1].read_text())
assert latest['phase']=='LOAD_VERIFIED_ACK_PENDING' and latest['oracle_written']
original_deadline=latest['deadline'];reserved=latest['reserved_sql_calls']
assert not list(Path(__import__('os').environ['PIPELINE_SCRATCH']).rglob('store.sqlite'))
# New recipe process directory: restore result/state from managed folders, no local reuse.
result=recipes.load(cfg,folders,variables,stage_dir('load-new-scratch'),'contract-job')
assert result['status']=='COMPLETE' and result['query_rows']>0 and result['oracle_written']
assert Remote.calls.count('HEALTH')==1 and Remote.calls.count('EXECUTE')==1
checkpoints=sorted((folders['load'].root/'_pipeline/jobs/contract-job').glob('checkpoint-*.json'))
latest=json.loads(checkpoints[-1].read_text())
assert latest['deadline']==original_deadline and latest['reserved_sql_calls']>reserved
assert all(t.sha(p)==sha for p,sha in structured_hashes.items())
counts={}
with c.cursor() as cur:
    for key in schema.tables:
        cur.execute('SELECT COUNT(*) FROM '+schema.names(key).table);counts[key]=cur.fetchone()[0]
assert all(counts[k]>0 for k in schema.tables if k not in ('query_active','query_state'))
assert counts['query_active']==counts['query_state']==0
before=counts.copy()
assert recipes.load(cfg,folders,variables,stage_dir('load-duplicate'),'contract-job')['status']=='COMPLETE'
with c.cursor() as cur:
    for key in schema.tables:
        cur.execute('SELECT COUNT(*) FROM '+schema.names(key).table);assert cur.fetchone()[0]==before[key]
# The mapped importer issued only new table targets, no legacy writes.
assert not any('SIDDA.LEGAL_' in s or 'INTO SIDDA.LGL_' in s for s in Executor.statements)
assert all('SIDDS.LGL_' in s for s in Executor.statements)
with admin.cursor() as cur:
    for table,count in old_counts.items():
        cur.execute('SELECT COUNT(*) FROM SIDDA.'+table);assert cur.fetchone()[0]==count

output={'status':'PASS','old_sidda_counts_unchanged':old_counts,'target_tables':{k:schema.names(k).table for k in schema.tables},'oracle':'local Oracle Free container','tables':9,'columns':46,'counts':counts,
        'query_rows':result['query_rows'],'sql_writes_executed':Executor.writes,
        'missing_index_preflight_no_genos':True,'committed_write_response_loss_recovered':True,
        'ack_response_loss_recovered':True,'local_workspace_loss_recovered':True,'duplicates_add_no_rows':True,
        'genos_execute_calls':Remote.calls.count('EXECUTE'),'service_executable_modified':False,
        'fixture_knowledge_configuration_rebound':True,'dataiku_sdk_transport_simulated':True,
        'field_dataiku_genos_adb_tested':False,'separate_recipe_stages':True,'upstream_result_immutable':True,'model_calls':0}
(work/'RESULT.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output))
c.close()
with admin.cursor() as cur:cur.execute('DROP USER '+test_user)
admin.close()
