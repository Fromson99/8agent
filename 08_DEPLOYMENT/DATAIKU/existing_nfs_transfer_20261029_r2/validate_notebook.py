"""Local-only whole notebook regression with fake Dataiku/Oracle/network ports."""
import ast
import copy
import hashlib
import io as streams
import json
from json import loads
from pathlib import Path
import shutil
import re
import sys
import types
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=HERE.with_name('existing_nfs_transfer_20261029_r1')
generation, work=map(Path,sys.argv[1:]);work.mkdir()
sys.path.insert(0,str(ROOT/'05_TESTS/CONTRACTS'))


def extract(delivery, revision):
    root=work/('code-'+revision)
    archive='DATAIKU_EXISTING_NFS_CLIENT_20261029_'+revision.upper()+'.zip'
    with zipfile.ZipFile(delivery/archive) as z:z.extractall(root)
    sys.path[:0]=[str(root),str(root/'client'),str(root/'client/02_BACKEND')]
    return root,archive


r1root,r1name=extract(BASE,'r1')
sys.modules['dataiku']=types.SimpleNamespace()
from semantic_runtime.physical_mapping import SchemaMap
from semantic_runtime import oracle_dp_io as io, oracle_dp_assets as assets, oracle_query_catalog as q
from lawrag.pipeline import oracle_existing_nfs as nfs
import existing_client as c
# Load only boundary doubles, so test-module imports cannot substitute repo code.
for filename,names in [
    ('test_oracle_dp.py',{'substring','Oracle'}),
    ('test_oracle_dp_runtime.py',{'AssetOracle'}),
    ('test_oracle_query_catalog.py',{'Oracle'}),
    ('test_existing_nfs_mapped_recovery.py',{'MappedOracle'}),
]:
    source=(ROOT/'05_TESTS/CONTRACTS'/filename).read_text()
    for node in ast.parse(source).body:
        if isinstance(node,(ast.ClassDef,ast.FunctionDef)) and node.name in names:
            exec(compile(ast.get_source_segment(source,node),filename,'exec'),globals())
    if filename=='test_oracle_query_catalog.py':QueryOracle=Oracle


class Folder:
    def __init__(self):self.values={}
    def list_paths_in_partition(self):return ['/'+k for k in self.values]
    def get_download_stream(self,name):return streams.BytesIO(self.values[name.lstrip('/')])
    def upload_stream(self,name,stream):self.values[name.lstrip('/')]=stream.read()


remote=MappedOracle(SchemaMap.load(r1root/'client/physical_mapping.yaml'))
snapshot=nfs.Snapshot(generation,c.EXPECTED)
snapshot.info['generation']=c.GENERATION
snapshot.info['snapshot_sha256']=nfs.digest({k:v for k,v in snapshot.info.items() if k!='snapshot_sha256'})
landing,results=Folder(),Folder()
landing.values[r1name]=(BASE/r1name).read_bytes()
cfg=dict(landing='ehA8dpVm',connection='AIDP',raw='r',structured='s',load='l')
recipe=types.SimpleNamespace(get_settings=lambda:types.SimpleNamespace(get_code=lambda:'run_recipe('+repr('structure')+', '+repr(cfg)+')'))
project=types.SimpleNamespace(get_recipe=lambda name:recipe)
variables=dict(LEGAL_PIPELINE_SCRATCH=str(work),LEGAL_PIPELINE_URL='https://fixture.invalid/api',LEGAL_PIPELINE_TOKEN='synthetic-not-a-credential')
sdk=types.SimpleNamespace(default_project_key=lambda:'LEGAL_RAG',
    api_client=lambda:types.SimpleNamespace(get_project=lambda name:project),
    get_custom_variables=lambda:variables,Folder=lambda name:landing if name=='ehA8dpVm' else results,
    SQLExecutor2=lambda **kwargs:object())
sys.modules['dataiku']=sdk
calls=[]


def install_ports(client, old=False):
    from lawrag.pipeline.oracle_query_dataiku import DataikuClient
    def sql(self,method,path,json):
        assert self.schema_map.target_sha256==remote.schema_map.target_sha256
        if 'SYS_CONTEXT' in json['statementText']:
            return {'items':[{'resultSet':{'items':[dict(LOGIN_USER='FIXTURE',DB_NAME='LOCAL_TEST',SERVICE_NAME='LOCAL_TEST')],'hasMore':False,'offset':0}}]}
        if old and 'WHERE 1=0' in json['statementText']:
            return {'items':[{'resultSet':{'items':[],'hasMore':False,'offset':0}}]}
        return remote.request(method,path,json)
    DataikuClient.request=sql
    def wire(self,op,**fields):
        calls.append(op)
        if op=='EXISTING_NFS_INFO':return snapshot.info
        return snapshot.read(fields['snapshot_sha256'],fields['file'],fields['offset'])
    client.Wire.call=wire


def execute(delivery,filename,action):
    text=(delivery/filename).read_text().replace("ACTION = 'check'",'ACTION = '+repr(action))
    scope={};exec(compile(text,str(delivery/filename),'exec'),scope)
    return scope['NFS_RESULT']


install_ports(c,old=True)
oldtxt='DATAIKU_EXISTING_NFS_RUN.txt'
assert execute(BASE,oldtxt,'check')['status']=='NFS_READY_FOR_TRANSFER'
assert execute(BASE,oldtxt,'transfer')['status']=='NFS_RECEIVED_VERIFIED'
try:execute(BASE,oldtxt,'load')
except KeyError as exc:assert exc.args==('deferred_indexes',)
else:raise AssertionError('R1 field failure was not reproduced')
local=work/'legal-existing-nfs-20261029-r1'/c.JOB_NAME
oldbytes=(local/'oracle-import/full-state.json').read_bytes()
scope=c.Scope(results)
def latest(client):
    paths=sorted(p for p in scope.list_paths_in_partition() if '/checkpoint-' in p and p.endswith('.json'))
    return json.loads(scope.get_download_stream(paths[-1]).read())
before=latest(c)
assert before['phase']=='STOPPED' and before['last_error']['type']=='KeyError'
assert remote.source.writes==remote.query.writes==0
saved=dict(results.values)

# A stale notebook kernel must stop before issuing a request with cached R1 code.
r2name='DATAIKU_EXISTING_NFS_CLIENT_20261029_R2.zip'
landing.values[r2name]=(HERE/r2name).read_bytes()
newtxt='DATAIKU_EXISTING_NFS_RUN_R2.txt'
count=len(calls)
try:execute(HERE,newtxt,'load')
except RuntimeError as exc:assert 'Restart' in str(exc)
else:raise AssertionError('cached R1 modules accepted')
assert len(calls)==count

# Model a new kernel: unload packaged modules; durable folders stay unchanged.
for name,module in list(sys.modules.items()):
    path=getattr(module,'__file__',None)
    if path and str(Path(path)).startswith(str(r1root)):
        del sys.modules[name]
sys.path[:]=[p for p in sys.path if not p.startswith(str(r1root))]
r2root,_=extract(HERE,'r2')
import existing_client as c2
assert c2.CLIENT_REVISION=='existing-nfs-20261029-r2'
assert Path(c2.full.__file__).is_relative_to(r2root)
assert Path(c2.full.query_publish.__file__).is_relative_to(r2root)
assert hashlib.sha256(Path(c2.full.__file__).read_bytes()).hexdigest()==hashlib.sha256((ROOT/'02_BACKEND/lawrag/pipeline/oracle_full_package.py').read_bytes()).hexdigest()
install_ports(c2)
# Lose all local transfer files, preserving the managed-folder failed receipts.
shutil.rmtree(local)
assert execute(HERE,newtxt,'check')['status']=='NFS_READY_FOR_TRANSFER'
count=len(calls)
result=execute(HERE,newtxt,'load')
assert result['status']=='FULL_DATA_VERIFIED' and result['deferred_indexes']==[]
assert calls[count:]==['EXISTING_NFS_INFO']
after=latest(c2)
assert after['deadline']==before['deadline']
assert after['reserved_sql_calls']>before['reserved_sql_calls']
assert after['reserved_http_calls']>=before['reserved_http_calls']
assert after['oracle_r1_failure_blob']==before['oracle_receipt_blob']
assert (local/'oracle-import/full-state.json').read_bytes()==oldbytes
assert all(results.values[k]==v for k,v in saved.items())
newstate=json.loads((local/'oracle-import-r2/full-state.json').read_text())
assert newstate['deadline']==json.loads(oldbytes)['deadline']
assert newstate['prior_schema_calls']>0 and newstate['status']=='COMPLETE'
writes=remote.source.writes,remote.query.writes
assert not remote.query.active and not remote.query.states
assert execute(HERE,newtxt,'status')['phase']=='COMPLETE'
shutil.rmtree(local)
count=len(calls)
assert execute(HERE,newtxt,'load')==result
assert calls[count:]==['EXISTING_NFS_INFO']
assert writes==(remote.source.writes,remote.query.writes)
assert (local/'oracle-import/full-state.json').read_bytes()==oldbytes
assert all(results.values[k]==v for k,v in saved.items())
print('NATIVE_R2_NOTEBOOK_PASS')
