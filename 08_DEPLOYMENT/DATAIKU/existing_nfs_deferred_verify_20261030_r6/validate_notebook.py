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
PREVIOUS=sys.argv[3]
R2=HERE.with_name({'r2':'existing_nfs_transfer_20261029_r2','r3':'existing_nfs_fast_20261030_r3','r4':'existing_nfs_continuous_20261030_r4','r5':'existing_nfs_bulk_verify_20261030_r5'}[PREVIOUS])
BASE=HERE.with_name('existing_nfs_transfer_20261029_r1')
generation, work=map(Path,sys.argv[1:3]);work.mkdir()
sys.path.insert(0,str(ROOT/'05_TESTS/CONTRACTS'))


def extract(delivery, revision):
    root=work/('code-'+revision)
    archive=next(delivery.glob('DATAIKU_EXISTING_NFS_CLIENT_*_'+revision.upper()+'.zip')).name
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
r2name=next(R2.glob('DATAIKU_EXISTING_NFS_CLIENT_*_'+PREVIOUS.upper()+'.zip')).name
landing.values[r2name]=(R2/r2name).read_bytes()
newtxt='DATAIKU_EXISTING_NFS_RUN_'+PREVIOUS.upper()+'.txt'
count=len(calls)
try:execute(R2,newtxt,'load')
except RuntimeError as exc:assert 'Restart' in str(exc)
else:raise AssertionError('cached R1 modules accepted')
assert len(calls)==count

# Model a new kernel: unload packaged modules; durable folders stay unchanged.
for name,module in list(sys.modules.items()):
    path=getattr(module,'__file__',None)
    if path and str(Path(path)).startswith(str(r1root)):
        del sys.modules[name]
sys.path[:]=[p for p in sys.path if not p.startswith(str(r1root))]
r2root,_=extract(R2,PREVIOUS)
import existing_client as c2
assert c2.CLIENT_REVISION=={'r2':'existing-nfs-20261029-r2','r3':'existing-nfs-20261030-r3','r4':'existing-nfs-20261030-r4','r5':'existing-nfs-20261030-r5'}[PREVIOUS]
assert Path(c2.full.__file__).is_relative_to(r2root)
assert Path(c2.full.query_publish.__file__).is_relative_to(r2root)
assert hashlib.sha256(Path(c2.full.__file__).read_bytes()).hexdigest()==('10b657b98b1a92ec0c17e56deb42c472fcfce6f794dbb3d2800b7bb999b2b47f' if PREVIOUS=='r5' else '6b0ece21e0294cf82b253d5ce525b4063cbb534bbe432790ecff3428e0c6cba0' if PREVIOUS=='r4' else '36e52b270f8b9f73b1bfdd92d60a742afcc04fed969bce98af828dda6e54d267')
install_ports(c2)
# Lose all local transfer files, preserving the managed-folder failed receipts.
shutil.rmtree(local)
assert execute(R2,newtxt,'check')['status']=='NFS_READY_FOR_TRANSFER'
# Stop R4/R5 after full source load but before separate verify; keep R2/R3 pending-write coverage.
from semantic_runtime import oracle_dp_io as io2
original=c2.full.migration.transfer
original_request=io2.SQL.request
armed=False
def pause(sql, statement, *args, **kwargs):
    global armed
    if armed: raise io2.BudgetPause('synthetic stop after source write')
    result=original_request(sql,statement,*args,**kwargs)
    if kwargs.get('write') and remote.schema_map.names('block_payload').table in statement: armed=True
    return result
def stop_verify(*args, **kwargs):
    if kwargs.get('action')=='verify': raise io2.BudgetPause('synthetic stop in separate verify')
    return original(*args,**kwargs)
if PREVIOUS in {'r4','r5'}: c2.full.migration.transfer=stop_verify
else: io2.SQL.request=pause
try:
    try:execute(R2,newtxt,'load')
    except io2.BudgetPause:pass
    else:raise AssertionError('expected previous-version pause')
finally:
    io2.SQL.request=original_request
    c2.full.migration.transfer=original
attempt=local/'oracle-import-r2'
full_before=json.loads((attempt/'full-state.json').read_text())
sourcepath=next(attempt.glob('source/*/state.json'))
source_before=json.loads(sourcepath.read_text())
assert full_before['status']=='PAUSED'
if PREVIOUS in {'r2','r3'}: assert source_before['pending']['kind']=='block_payload'
else: assert source_before['status']=='SOURCE_COMPLETE' and source_before['pending'] is None
assert source_before['tables']['document']['rows']>0
managed_before=latest(c2)
rows_before=copy.deepcopy(remote.source.data)
managed_saved=dict(results.values)
# Previously loaded R2 code must be rejected before NFS/Oracle work.
r3name='DATAIKU_EXISTING_NFS_CLIENT_20261030_R6.zip'
landing.values[r3name]=(HERE/r3name).read_bytes()
r3txt='DATAIKU_EXISTING_NFS_RUN_R6.txt'
count=len(calls)
try:execute(HERE,r3txt,'load')
except RuntimeError as exc:assert 'Restart' in str(exc)
else:raise AssertionError('cached R2 modules accepted')
assert len(calls)==count
for name,module in list(sys.modules.items()):
    path=getattr(module,'__file__',None)
    if path and str(Path(path)).startswith(str(r2root)):
        del sys.modules[name]
sys.path[:]=[p for p in sys.path if not p.startswith(str(r2root))]
r3root=work/'code-r3'
with zipfile.ZipFile(HERE/r3name) as z:z.extractall(r3root)
sys.path[:0]=[str(r3root),str(r3root/'client'),str(r3root/'client/02_BACKEND')]
import existing_client as c3
from semantic_runtime import oracle_dp_io as io
assert c3.CLIENT_REVISION=='existing-nfs-20261030-r6'
assert 'source_verify_batch_rows' in (r3root/'client/02_BACKEND/lawrag/pipeline/oracle_migration.py').read_text()
# Add only the new SELECT boundary interpreter; all importer checks remain real.
source=(HERE.with_name('existing_nfs_fast_20261030_r3')/'test_batch_read.py').read_text()
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='batch_response')
exec(compile(ast.get_source_segment(source,node),'batch-test-port','exec'),globals())
old_port=remote.source.request
original_source_port=old_port
def staged_asset_port(method,path,json):
    text=json['statementText']; b={x['name']:x['value'] for x in json.get('binds',[])}
    if text.startswith('DECLARE') and assets.PART_TABLE in text and 'IF n=0' in text:
        previous=remote.source.parts.get((b['a'],b['p']))
        if previous is not None:
            remote.source.calls.append(json)
            return {'items':[{'result':0}]} if previous==b else {'items':[{'errorCode':20002}]}
    return original_source_port(method,path,json)
old_port=staged_asset_port
batched_calls=[]
def batched_port(method,path,json):
    if ' AS CLOB_SLOT' in json['statementText']:
        batched_calls.append(json)
        return batch_response(old_port,method,path,json)
    return old_port(method,path,json)
remote.source.request=batched_port
install_ports(c3)
# Receipt restoration uses the preserved S3 blob and the same source bytes/inode.
shutil.rmtree(attempt)
assert execute(HERE,r3txt,'check')['status']=='NFS_READY_FOR_TRANSFER'
# Advance both clocks after the source SQL deadline has been constructed.
# This verifies >6h continuation without sleeping or running a real load.
import time as real_time
class Clock:
    offset=0
    def time(self):return real_time.time()+self.offset
    def monotonic(self):return real_time.monotonic()+self.offset
    def __getattr__(self,name):return getattr(real_time,name)
clock=Clock()
for module in list(sys.modules.values()):
    path=getattr(module,'__file__',None)
    if path and str(Path(path)).startswith(str(r3root)) and getattr(module,'time',None) is real_time:
        module.time=clock
old_request=io.SQL.request
elapsed_at=[]
def leap(sql,statement,*args,**kwargs):
    if '/source/' in str(sql.journal) and not elapsed_at:
        clock.offset=21601
        elapsed_at.append(str(sql.journal))
    return old_request(sql,statement,*args,**kwargs)
io.SQL.request=leap
# Load-only must not invoke any source or projected-row full readback.
from lawrag.pipeline import oracle_deferred_import as deferred
original_read=c3.full.migration.read_batch
original_verify=c3.full.query_publish._verify_batch
def forbidden(*args,**kwargs):raise AssertionError('full readback in load_only')
c3.full.migration.read_batch=forbidden
c3.full.query_publish._verify_batch=forbidden
try:
    # Lost write acknowledgement must stop once; explicit rerun reconciles exact content.
    remote.source.mode='after_timeout'
    try:execute(HERE,r3txt,'load_only')
    except io.DPError as exc: assert 'WRITE_UNCONFIRMED' in str(exc)
    else:raise AssertionError('source/asset write timeout was swallowed')
    assert not remote.source.releases and not remote.query.releases
    remote.query.fail_after_write=True
    try:execute(HERE,r3txt,'load_only')
    except io.DPError as exc: assert 'WRITE_UNCONFIRMED' in str(exc)
    else:raise AssertionError('query write timeout was swallowed')
    assert not remote.source.releases and not remote.query.releases
    loaded=execute(HERE,r3txt,'load_only')
    assert loaded['status']=='LOADED_UNVERIFIED'
    assert not remote.source.releases and not remote.query.releases
    assert remote.source.data and remote.source.parts and remote.query.rows
    assert execute(HERE,r3txt,'status')['phase']=='LOADED_UNVERIFIED'
    counts=remote.source.writes,remote.query.writes
    assert execute(HERE,r3txt,'load_only')['status']=='LOADED_UNVERIFIED'
    assert counts==(remote.source.writes,remote.query.writes)
finally:
    c3.full.migration.read_batch=original_read
    c3.full.query_publish._verify_batch=original_verify
    io.SQL.request=old_request
assert elapsed_at and clock.offset>21600
# Independent verifier detects missing/changed source, asset, row and undeclared extra row.
pristine=copy.deepcopy((remote.source.data,remote.source.parts,remote.query.rows))
for damage in ['source_missing','source_changed','asset_missing','asset_changed','query_missing','query_changed','extra_query']:
    remote.source.data,remote.source.parts,remote.query.rows=copy.deepcopy(pristine)
    if damage=='source_missing': remote.source.data['source_unit'].pop(next(iter(remote.source.data['source_unit'])))
    if damage=='source_changed': next(iter(remote.source.data['block_payload'].values()))['TEXT']='changed'
    if damage=='asset_missing': remote.source.parts.pop(next(iter(remote.source.parts)))
    if damage=='asset_changed': next(iter(remote.source.parts.values()))['s']='0'*64
    if damage=='query_missing': remote.query.rows.pop(next(iter(remote.query.rows)))
    if damage=='query_changed': next(iter(remote.query.rows.values())).update(VALUE='{}',N=2)
    if damage=='extra_query':
        key=next(iter(remote.query.rows));remote.query.rows[(key[0],'unlisted','0'*64)]=remote.query.rows[key]
    before_writes=remote.source.writes,remote.query.writes
    try:execute(HERE,r3txt,'verify')
    except io.DPError:pass
    else:raise AssertionError('corruption accepted: '+damage)
    assert before_writes==(remote.source.writes,remote.query.writes)
    assert not remote.source.releases and not remote.query.releases
remote.source.data,remote.source.parts,remote.query.rows=copy.deepcopy(pristine)
verify_actions=[]
original_transfer=c3.full.migration.transfer
def count_verify(*args,**kwargs):
    verify_actions.append(kwargs['action'])
    return original_transfer(*args,**kwargs)
c3.full.migration.transfer=count_verify
try: assert execute(HERE,r3txt,'verify')['status']=='FULL_DATA_VERIFIED'
finally:c3.full.migration.transfer=original_transfer
assert verify_actions==['verify'],verify_actions

source_after=json.loads(sourcepath.read_text())
full_after=json.loads((attempt/'full-state.json').read_text())
managed_after=latest(c3)
assert source_after['binding']==source_before['binding']
assert source_after['deadline']==source_before['deadline']
assert source_after['calls']>source_before['calls']
assert full_after['identity']==full_before['identity']
compat=full_after['compatible_executor']
assert compat['execution_code_sha256']==hashlib.sha256(Path(c3.full.__file__).read_bytes()).hexdigest()
assert compat['origin_code_sha256']==full_before['identity']['code']
raw=(attempt/compat['prior_receipt_file']).read_bytes()
assert hashlib.sha256(raw).hexdigest()==compat['prior_receipt_sha256']
assert json.loads(raw)==full_before
assert full_after['deadline']==full_before['deadline']
assert managed_after['deadline']==managed_before['deadline']
assert managed_after['reserved_sql_calls']>managed_before['reserved_sql_calls']
assert all(results.values[k]==v for k,v in managed_saved.items())
assert all(remote.source.data[k][key]==row for k,table in rows_before.items() for key,row in table.items())
assert source_after['pending'] is None
writes=remote.source.writes,remote.query.writes
assert execute(HERE,r3txt,'load')['status']=='FULL_DATA_VERIFIED'
assert writes==(remote.source.writes,remote.query.writes)
assert not remote.query.active and not remote.query.states
assert execute(HERE,r3txt,'status')['phase']=='COMPLETE'
assert (local/'oracle-import/full-state.json').read_bytes()==oldbytes
# The underlying full test fixture may have only short CLOBs; long-body batching
# is covered independently by the exact packaged read and mapped adapter tests.
print('NATIVE_R6_NOTEBOOK_PASS', PREVIOUS, 'ELAPSED_VIRTUAL_SECONDS=21601')
