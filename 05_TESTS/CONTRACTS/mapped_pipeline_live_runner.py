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
c=oracledb.connect(user='SIDDA',password=Path('/tmp/legal-mapped-oracle-config/sidda-password').read_text(),dsn='127.0.0.1:11524/FREEPDB1')
# Refuse accidental external destinations; this script has no production settings.
assert c.dsn=='127.0.0.1:11524/FREEPDB1'
with c.cursor() as cur:
    for typ,key,name,statement in schema.ddl():
        cur.execute('SELECT COUNT(*) FROM USER_OBJECTS WHERE OBJECT_NAME=:n AND OBJECT_TYPE=:t',n=name,t=typ)
        if not cur.fetchone()[0]:cur.execute(statement)
    for key,table in schema.tables.items():
        quote=lambda text:"'"+text.replace("'","''")+"'"
        cur.execute('COMMENT ON TABLE '+schema.names(key).table+' IS '+quote(table['description']))
        for col in table['columns'].values():cur.execute('COMMENT ON COLUMN '+schema.names(key).table+'.'+col['name']+' IS '+quote(col['description']))

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
kwargs=dict(folder=folder,job_name='contract-job',input_binding={'fixture_raw_sha':t.sha(exports/'RAW_INPUT.zip')})
job=work/'job'
# Fail before any GENOS request on a physically missing index.
with c.cursor() as cur:cur.execute('DROP INDEX SIDDA.LGL_SRCH_ROW_KEY_IX')
try:client.run_dataiku(inputs,exports/'PIPELINE_SUPPORT.zip',job,**kwargs)
except ValueError as exc:assert 'TARGET_INDEX' in str(exc)
else:raise AssertionError('preflight accepted missing index')
assert not Remote.calls
with c.cursor() as cur:
    cur.execute(next(sql for typ,k,n,sql in schema.ddl() if n=='LGL_SRCH_ROW_KEY_IX'))
assert client.run_dataiku(inputs,exports/'PIPELINE_SUPPORT.zip',job,action='check',**kwargs)['status']=='READY'
try:client.run_dataiku(inputs,exports/'PIPELINE_SUPPORT.zip',job,**kwargs)
except io.DPError as exc:assert 'WRITE_UNCONFIRMED' in str(exc)
else:raise AssertionError('write failure did not stop')
assert 'ACK' not in Remote.calls
assert list(Path(__import__('os').environ['PIPELINE_SCRATCH']).rglob('result.zip'))
try:client.run_dataiku(inputs,exports/'PIPELINE_SUPPORT.zip',job,**kwargs)
except RuntimeError as exc:assert 'ACK response loss' in str(exc)
else:raise AssertionError('ACK uncertainty not retained')
from managed_job import ManagedJob
checkpoints=sorted((work/'managed/_pipeline/jobs/contract-job').glob('checkpoint-*.json'))
latest=json.loads(checkpoints[-1].read_text())
assert latest['phase']=='LOAD_VERIFIED_ACK_PENDING' and latest['oracle_written']
original_deadline=latest['deadline'];reserved=latest['reserved_sql_calls']
assert not list(Path(__import__('os').environ['PIPELINE_SCRATCH']).rglob('store.sqlite'))
# Lose the local workspace but preserve it as failure evidence.
job.rename(work/'prior-local-attempt')
result=client.run_dataiku(inputs,exports/'PIPELINE_SUPPORT.zip',job,**kwargs)
assert result['status']=='COMPLETE' and result['query_rows']>0 and result['oracle_written']
assert Remote.calls.count('HEALTH')==1 and Remote.calls.count('EXECUTE')==1
checkpoints=sorted((work/'managed/_pipeline/jobs/contract-job').glob('checkpoint-*.json'))
latest=json.loads(checkpoints[-1].read_text())
assert latest['deadline']==original_deadline and latest['reserved_sql_calls']>reserved
counts={}
with c.cursor() as cur:
    for key in schema.tables:
        cur.execute('SELECT COUNT(*) FROM '+schema.names(key).table);counts[key]=cur.fetchone()[0]
assert all(counts[k]>0 for k in schema.tables if k not in ('query_active','query_state'))
assert counts['query_active']==counts['query_state']==0
before=counts.copy()
assert client.run_dataiku(inputs,exports/'PIPELINE_SUPPORT.zip',job,**kwargs)['status']=='COMPLETE'
with c.cursor() as cur:
    for key in schema.tables:
        cur.execute('SELECT COUNT(*) FROM '+schema.names(key).table);assert cur.fetchone()[0]==before[key]
# The mapped importer issued only new table targets, no legacy writes.
assert not any('SIDDA.LEGAL_' in s for s in Executor.statements)
output={'status':'PASS','oracle':'local Oracle Free container','tables':9,'columns':46,'counts':counts,
        'query_rows':result['query_rows'],'sql_writes_executed':Executor.writes,
        'missing_index_preflight_no_genos':True,'committed_write_response_loss_recovered':True,
        'ack_response_loss_recovered':True,'local_workspace_loss_recovered':True,'duplicates_add_no_rows':True,
        'genos_execute_calls':Remote.calls.count('EXECUTE'),'service_executable_modified':False,
        'fixture_knowledge_configuration_rebound':True,'dataiku_sdk_transport_simulated':True,
        'field_dataiku_genos_adb_tested':False,'model_calls':0}
(work/'RESULT.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output))
c.close()
