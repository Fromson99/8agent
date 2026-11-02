"""Delivered R11 load -> delivered R12 full verification. Boundary doubles only."""
from pathlib import Path
import sys,json,copy,zipfile,hashlib,io as streams,types,subprocess
from unittest.mock import patch
REPO=Path(__file__).resolve().parents[3]
DELIVERY=REPO/'08_DEPLOYMENT/DATAIKU/existing_nfs_queued_kure_20261031_r12'
OLD=REPO/'08_DEPLOYMENT/DATAIKU/existing_nfs_set_bulk_20261031_r11/validate_notebook.py'
# Reuse the exact frozen fixture setup and failure/recovery path through R11 load-only.
source=OLD.read_text().split('# Independent verifier detects')[0]
scope={'__file__':str(OLD),'__name__':'__main__'}
exec(compile(source,str(OLD),'exec'),scope)
remote,local,work,loaded,sdk=[scope[k] for k in ('remote','local','work','loaded','sdk')]
assert loaded['status']=='LOADED_UNVERIFIED'
statepath=local/'oracle-import-r2/full-state.json';statebytes=statepath.read_bytes()
old_deadline=json.loads(statebytes)['deadline']
# A fresh child interpreter is modeled by unloading every prior package module.
for name,module in list(sys.modules.items()):
 p=getattr(module,'__file__',None)
 if p and any(str(p).startswith(str(scope[k])) for k in ('r1root','r2root','r3root')):del sys.modules[name]
sys.path[:]=[p for p in sys.path if not any(str(p).startswith(str(scope[k])) for k in ('r1root','r2root','r3root'))]
r12=work/'r12'
with zipfile.ZipFile(next(DELIVERY.glob('*.zip'))) as z:z.extractall(r12)
sys.path[:0]=[str(r12),str(r12/'client'),str(r12/'client/02_BACKEND')]
import queued_followup as follow,queued_vectors as vectors,existing_client as current
from semantic_runtime import oracle_dp_io as io,oracle_query_catalog as q
from lawrag.pipeline.oracle_query_dataiku import DataikuClient
# Run original port for metadata, counts, and COMPLETE publication; new read-only
# JSON_TABLE checks independently compare every delivered value at the boundary.
scope['install_ports'](current);oldport=DataikuClient.request;set_calls=[]
def request(self,method,path,json):
 b={x['name']:x['value'] for x in json.get('binds',[])};stmt=json['statementText']
 if 'payload' not in b or 'expected' not in b or 'release' in b:return oldport(self,method,path,json)
 assert 'SELECT COUNT(*) INTO n' in stmt and 'INSERT ' not in stmt and 'UPDATE ' not in stmt
 logical=next(k for k in remote.schema_map.tables if remote.schema_map.names(k).table in stmt)
 rows=[{k:v for k,v in r.items() if not k.startswith('_lob_state')} for r in __import__('json').loads(b['payload'])]
 set_calls.append((logical,len(rows)))
 if logical in io.TABLES:
  ok=all(remote.source.data[logical].get(tuple(r[k] for k in io.KEYS[logical]))==r for r in rows)
 elif logical=='query_row':
  def valid(r):
   old=remote.query.rows.get((r['RELEASE_ID'],r['KIND'],r['ROW_ID']))
   return old is not None and all(old.get('VALUE' if k=='VALUE_JSON' else k)==v for k,v in r.items())
  ok=all(valid(r) for r in rows)
 elif logical=='asset_part':
  def valid(r):
   old=remote.source.parts.get((r['ASSET_SHA256'],r['PART_NO']))
   return old is not None and all(old.get(k)==r[c] for k,c in [('a','ASSET_SHA256'),('p','PART_NO'),('n','RAW_BYTES'),('s','PART_SHA256'),('body','DATA_B64')])
  ok=all(valid(r) for r in rows)
 else:raise AssertionError(logical)
 return {'items':[{'result':0}]} if ok else {'items':[{'errorCode':20041}]}
DataikuClient.request=request
vector_calls=[]
def vector_boundary(sql,root,qid,sid,manifest,selection,project,state,**kw):
 assert qid==loaded['query_release_id'] and sid==loaded['source_release_id']
 assert json.loads(statepath.read_text())['status']=='COMPLETE'
 assert remote.source.releases and remote.query.releases
 kw['input_check']()
 vector_calls.append(qid)
 return {'status':'READY','active':False,'count':3,'publication_id':'f'*64}
vectors.build=vector_boundary
pristine=copy.deepcopy((remote.source.data,remote.source.parts,remote.query.rows))
for damage in ['source_missing','source_changed','asset_missing','asset_changed','query_missing','query_changed','extra_query']:
 statepath.write_bytes(statebytes)
 remote.source.data,remote.source.parts,remote.query.rows=copy.deepcopy(pristine)
 if damage=='source_missing':remote.source.data['source_unit'].pop(next(iter(remote.source.data['source_unit'])))
 if damage=='source_changed':next(iter(remote.source.data['block_payload'].values()))['TEXT']='changed'
 if damage=='asset_missing':remote.source.parts.pop(next(iter(remote.source.parts)))
 if damage=='asset_changed':next(iter(remote.source.parts.values()))['body']='changed'
 if damage=='query_missing':remote.query.rows.pop(next(iter(remote.query.rows)))
 if damage=='query_changed':next(iter(remote.query.rows.values())).update(VALUE='{}',N=2)
 if damage=='extra_query':
  key=next(iter(remote.query.rows));remote.query.rows[(key[0],'unlisted','0'*64)]=remote.query.rows[key]
 try:follow.run(loaded)
 except io.DPError:pass
 else:raise AssertionError('Corruption accepted '+damage)
 assert not vector_calls and not remote.source.releases and not remote.query.releases
 print('R12_REJECTED',damage)
statepath.write_bytes(statebytes);remote.source.data,remote.source.parts,remote.query.rows=copy.deepcopy(pristine)
answer=follow.run(loaded)
assert answer['status']=='VERIFIED_AND_VECTOR_READY' and len(vector_calls)==1
assert json.loads(statepath.read_text())['deadline']==old_deadline
assert not remote.query.active and not remote.query.states
assert set(x[0] for x in set_calls)==set(io.TABLES)|{'query_row','asset_part'}
# Exact delivered launcher: failed predecessor before download; exact ZIP extraction,
# same interpreter + DSS context, isolated child command, and bounded stdout filter.
notebook=(DELIVERY/'DATAIKU_QUEUE_AFTER_R11_R12.txt').read_text()
scope['landing'].values[next(DELIVERY.glob('*.zip')).name]=next(DELIVERY.glob('*.zip')).read_bytes()
class Child:
 def __init__(self,args,**kwargs):
  assert args[0]==sys.executable and args[1]=='-u'
  assert Path(args[2]).name=='queued_followup.py' and 'env' in kwargs
  assert json.loads(Path(args[3]).read_text())=={k:loaded[k] for k in ('status','source_release_id','query_release_id')}
  assert hashlib.sha256(Path(args[2]).read_bytes()).digest()==hashlib.sha256((r12/'queued_followup.py').read_bytes()).digest()
  self.stdout=streams.StringIO('private debug\nQP12 MOCK_CHILD_DONE\n')
 def wait(self):return 0
 def send_signal(self,s):raise AssertionError('Unexpected interrupt')
with patch.object(subprocess,'Popen',Child):
 try:exec(compile(notebook,'delivered-R12-cell','exec'),{})
 except RuntimeError as e:assert 'R11' in str(e)
 else:raise AssertionError('No predecessor accepted')
 cell={'NFS_RESULT':loaded};exec(compile(notebook,'delivered-R12-cell','exec'),cell)
 assert cell['NFS_FOLLOWUP_RESULT']['status']=='VERIFIED_AND_VECTOR_READY'
print('R12_DELIVERED_INTEGRATION_PASS',len(set_calls),'set requests; native vector persistence separately verified; no field/model calls')
