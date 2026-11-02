"""Explicit frozen R12 candidate; synthetic real Oracle, mocked Mesh only."""
from pathlib import Path
import hashlib,json,os,secrets,sqlite3,subprocess,sys,tempfile,time,traceback
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1264/queued'
REL=Path('08_DEPLOYMENT/DATAIKU/existing_nfs_resume_only_20261030_r10/candidate')
REV=os.environ.get('ADR1264_REVISION','rev-002');RUN=os.environ.get('ADR1264_RUN','run-002')
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1264-dataiku-queued-verify-kure'
subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/COMMANDS/adr_candidate.py'),'validate',str(C)],check=True)
code=C/'revisions'/REV/'snapshot'/REL
sys.path[:0]=[str(code),str(code/'client'),str(code/'client/02_BACKEND')]
import queued_verify as verify,queued_vectors as v,queued_followup as follow
from semantic_runtime import oracle_dp_io as io,oracle_query_catalog as q,oracle_dp_assets as assets
from semantic_runtime.physical_mapping import SchemaMap
from lawrag.pipeline.oracle_query_dataiku import DataikuClient
from lawrag.pipeline import oracle_query_publish as qp,oracle_deferred_import as defer
from semantic_runtime.initial_vector import Repository,ddl
out=ADR/'artifacts'/RUN;out.mkdir(exist_ok=False)
result={'status':'RUNNING','revision':REV,'checks':[],'model_calls':0,'field_executed':False,'MAIN_changed':False}
def passed(s):result['checks'].append(s)
def reject(fn):
 try:fn()
 except Exception:return
 raise AssertionError('Expected rejection')
def rows(n):return [q.record('synthetic',{'i':i,'text':"한글😀 O'Reilly :body "*8},key=i,document_id='0007',owner_id=None if i%2 else '부모') for i in range(n)]

def test_local():
 expected={'status':'LOADED_UNVERIFIED','source_release_id':'a'*64,'query_release_id':'b'*64}
 state={'status':'LOADED_UNVERIFIED','deferred':{'load_finished':True,'plan':{k:expected[k] for k in ('source_release_id','query_release_id')}}}
 follow.gate(expected,state)
 for bad in ({},{**state,'status':'FAILED'},{**state,'deferred':{**state['deferred'],'load_finished':False}}):reject(lambda:follow.gate(expected,bad))
 reject(lambda:follow.gate({**expected,'query_release_id':'c'*64},state));passed('queued_success_failed_stale_gate')
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)
  with patch.object(defer.query,'describe',return_value=({}, {}, {})):
   original=defer.io.file_sha
   with patch.object(defer.io,'file_sha',side_effect=lambda x:defer.R11_DESCRIPTOR_EXECUTOR if str(x)==defer.__file__ else original(x)):
    defer.prepared_descriptor(p,{'x':1},{},p)
  with patch.object(defer.query,'describe',side_effect=AssertionError('re-description')):defer.prepared_descriptor(p,{'x':1},{},p,strict=True)
 passed('R11_descriptor_strict_reuse')
 reject(lambda:v.checked_vectors([[0.0]*1024],1));reject(lambda:v.checked_vectors([[float('nan')]*1024],1))
 reject(lambda:v.checked_vectors([[1.0]*32],1));passed('model_invalid_zero_dimension_nan')
 class Response:
  def get_embeddings(self):return [[1.0]+[0.0]*1023]*2
 class Query:
  def __init__(self):self.texts=[]
  def add_text(self,t):self.texts.append(t)
  def execute(self):return Response()
 class Model:
  def new_embeddings(self,**kw):assert kw=={'text_overflow_mode':'FAIL'};return Query()
 class Project:
  def get_llm(self,name):assert name==v.MODEL_ID;return Model()
 assert len(v.MeshEncoder(Project()).encode(['하나','둘']))==2;passed('exact_Mesh_API_no_truncation')

def main():
 import oracledb,pandas as pd
 test_local()
 metadata=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
 password=dict(x.split('=',1) for x in metadata['Config']['Env'])['ORACLE_PASSWORD']
 admin=oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1',user='system',password=password)
 user='A8_Q12_'+secrets.token_hex(4).upper();pw=secrets.token_hex(20);conn=None
 try:
  with admin.cursor() as c:
   c.execute(f'CREATE USER {user} IDENTIFIED BY "{pw}" DEFAULT TABLESPACE USERS QUOTA 96M ON USERS');c.execute(f'GRANT CREATE SESSION,CREATE TABLE TO {user}')
  conn=oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1',user=user,password=pw)
  schema=SchemaMap.load(code/'client/physical_mapping.yaml')
  class Executor:
   fail_ack=False;fail_vector_commit=False
   def query_to_df(self,stmt,**kw):
    with conn.cursor() as cur:
     for text in kw.get('pre_queries',[]):
      cur.execute(text.replace('SIDDS.',user+'.'))
      if self.fail_vector_commit and 'TO_VECTOR(j.vec' in text:self.fail_ack=True;self.fail_vector_commit=False
     cur.execute(stmt.replace('SIDDS.',user+'.'));names=[x[0] for x in cur.description]
     values=[[x.read() if hasattr(x,'read') else x for x in row] for row in cur.fetchall()]
     for text in kw.get('post_queries',[]):cur.execute(text)
    if self.fail_ack:self.fail_ack=False;raise TimeoutError('Injected ACK loss')
    return pd.DataFrame(values,columns=names)
  executor=Executor();client=DataikuClient(executor,'SYNTHETIC','TEST',schema_map=schema)
  sql=io.SQL(client,journal=out/'sql.jsonl',binding=user,seconds=3600)
  def execute(stmt,binds=None):
   with conn.cursor() as cur:cur.execute(stmt.replace('SIDDS.',user+'.'),binds or {})
   conn.commit()
  # Exactly the mapped physical column names, no production schema touched.
  specs=[('query_row',{'RELEASE_ID':'VARCHAR2(64)','KIND':'VARCHAR2(64)','ROW_ID':'VARCHAR2(64)','DOCUMENT_ID':'VARCHAR2(512)','LOOKUP_ID':'VARCHAR2(512)','OWNER_ID':'VARCHAR2(512)','TARGET_ID':'VARCHAR2(512)','ROW_SHA256':'VARCHAR2(64)','VALUE_JSON':'CLOB'},['RELEASE_ID','KIND','ROW_ID'])]
  for kind in io.TABLES:specs.append((kind,{c:('CLOB' if c in io.CLOBS else 'NUMBER' if c=='JSON_TEXT_ELIDED' else 'VARCHAR2(512)') for c in io.COLUMNS[kind]},io.KEYS[kind]))
  specs.append(('asset_part',{'ASSET_SHA256':'VARCHAR2(64)','PART_NO':'NUMBER','RAW_BYTES':'NUMBER','PART_SHA256':'VARCHAR2(64)','DATA_B64':'CLOB'},['ASSET_SHA256','PART_NO']))
  for kind,cols,keys in specs:
   p=schema.names(kind)
   execute('CREATE TABLE '+p.table+' ('+','.join(p.c(c)+' '+t for c,t in cols.items())+',PRIMARY KEY('+','.join(p.c(k) for k in keys)+'))')
  batch=rows(5000);rid='a'*64;q.insert_records(sql,rid,batch)
  start=sql.calls;began=time.monotonic();verify.query(sql,rid,batch)
  result['query_verify']={'rows':5000,'sql_calls':sql.calls-start,'seconds':time.monotonic()-began};assert sql.calls-start==1
  passed('native5000_full_query_validation_one_call')
  p=schema.names('query_row')
  execute(f'UPDATE {p.table} SET {p.c("VALUE_JSON")}=TO_CLOB(\'{{"changed":true}}\') WHERE {p.c("ROW_ID")}=\'{batch[-1]["row_id"]}\'')
  reject(lambda:verify.query(sql,rid,batch));passed('native_query_body_corruption_rejected')
  for kind in io.TABLES:
   row={c:('a'*64 if c=='DATASET_VERSION' else None if c=='PARENT_ID' else 1 if c=='JSON_TEXT_ELIDED' else '{"text":"한글😀"}' if c=='SOURCE_JSON' else '' if c=='TEXT' else '0007') for c in io.COLUMNS[kind]}
   statement,binds=io.insert_statement(kind,[row],sql=sql);sql.request(statement,binds,write=True)
   verify.source(sql,kind,[row]);bad={**row,'SOURCE_JSON':'{"bad":true}'};reject(lambda:verify.source(sql,kind,[bad]))
  passed('native_all_source_kinds_null_empty_unicode_full_compare')
  item={'sha256':'b'*64};raw=('원문😀'*4000).encode();defer.put_staged_part(sql,item,0,raw);verify.asset(sql,item,0,raw)
  reject(lambda:verify.asset(sql,item,0,raw+b'x'));passed('native_asset_compressed_content_compare')
  for statement in ddl(user):execute(statement)
  repo=Repository(sql,user);pub='c'*64;lease='lease'
  execute(f'INSERT INTO {repo.r} VALUES(:p,:body)',{'p':pub,'body':'{"status":"BUILDING","lease":"lease"}'})
  items=[{'id':io.digest(i),'meta':{'document_id':'0007','source_id':'s','i':i},'text':'본문'} for i in range(32)]
  vectors=v.checked_vectors([[i+1.0]+[.2]*1023 for i in range(32)],32)
  v.insert_batch(sql,repo,pub,lease,items,vectors,{'progress':32});v.insert_batch(sql,repo,pub,lease,items,vectors,{'progress':32})
  assert sql.query(f'SELECT COUNT(*) AS N FROM {repo.s} WHERE PUB_ID=\'{pub}\'',limit=1)==[{'N':32}]
  passed('native32x1024_set_insert_exact_and_replay')
  new=[{**x,'id':io.digest(['new',i])} for i,x in enumerate(items)];conflict={**items[-1],'meta':{'wrong':True}}
  reject(lambda:v.insert_batch(sql,repo,pub,lease,new[:31]+[conflict],vectors,{}))
  assert sql.query(f'SELECT COUNT(*) AS N FROM {repo.s} WHERE PUB_ID=\'{pub}\'',limit=1)==[{'N':32}]
  passed('native_vector_conflict_whole_batch_rollback')
  # Small synthetic immutable source fixture, independent expected segment generator below.
  root=out/'source';root.mkdir();(root/'navigation').mkdir()
  manifest={'scope':{'document_version_ids':['0007','excluded']},'navigation':{'path':'navigation'}}
  (root/'manifest.json').write_text(json.dumps(manifest))
  source={'id':'s1','document_id':'0007','document_name':'문서','heading':'제1조','unit_id':1,'blocks':[{'block_id':'001'}]}
  body='한글😀'+('본문'*25000)
  with sqlite3.connect(root/'navigation/navigation.sqlite') as db:db.execute('CREATE TABLE source(id TEXT,document_id TEXT,json TEXT)');db.execute('INSERT INTO source VALUES(?,?,?)',('s1','0007',io.canonical(source)))
  with sqlite3.connect(root/'store.sqlite') as db:db.execute('CREATE TABLE block_payload(document_id TEXT,block_id TEXT,text TEXT)');db.execute('INSERT INTO block_payload VALUES(?,?,?)',('0007','001',body))
  segments=list(v.local_segments(root,'d'*64,manifest,{'0007'}));assert len(segments)>64
  for item in segments:
   m=item['meta'];assert m['block_id']=='001' and m['source_sha256']==io.digest(source) and m['block_sha256']==io.digest(body)
   assert item['text']=='문서 / 제1조\n'+body[m['start']:m['end']]
   assert item['id']==io.digest(['d'*64,m])
  from semantic_runtime.vector_publish import segments as original_segments
  from types import SimpleNamespace
  request=SimpleNamespace(snapshot=SimpleNamespace(manifest=manifest),release_id='d'*64,
      records=SimpleNamespace(page=lambda *a,**k:{'rows':[{'json':source}],'next':None}),
      sources=SimpleNamespace(allowed={'0007'},sources=lambda did,bids:[{'block_id':'001','text':body}]))
  assert sorted(segments,key=lambda x:x['id'])==sorted(original_segments(request),key=lambda x:x['id'])
  passed('local_window_ID_text_scope_exact_old_segments')
  class Encoder:
   calls=0;fail=False
   def encode(self,texts):
    self.calls+=1
    if self.fail:raise TimeoutError('injected model UNKNOWN')
    return v.checked_vectors([[1.0]+[.25]*1023 for _ in texts],len(texts))
  encoder=Encoder();project=SimpleNamespace()
  from lawrag.pipeline import oracle_full_package as full
  with patch.object(full,'verify_restored',return_value=(root,{})):
   executor.fail_vector_commit=True
   reject(lambda:v.build(sql,root,'d'*64,'e'*64,manifest,{},project,out/'job',owner=user,encoder=encoder,input_check=lambda:None))
   calls=encoder.calls;assert calls==1
   done=v.build(sql,root,'d'*64,'e'*64,manifest,{},project,out/'job',owner=user,encoder=encoder,input_check=lambda:None)
   assert done['status']=='READY' and not done['active'] and done['count']==len(segments)
   assert encoder.calls==len(list(v.groups(iter(segments))))
   again=v.build(sql,root,'d'*64,'e'*64,manifest,{},project,out/'job',owner=user,encoder=encoder,input_check=lambda:None)
   assert again['reused'] and encoder.calls==len(list(v.groups(iter(segments))))
  passed('full_build_commit_ACK_loss_resume_no_model_repeat_READY_no_activation')
  unknown=Encoder();unknown.fail=True
  with patch.object(full,'verify_restored',return_value=(root,{})):
   reject(lambda:v.build(sql,root,'f'*64,'e'*64,manifest,{},project,out/'unknown',owner=user,encoder=unknown,input_check=lambda:None))
   assert unknown.calls==1
   reject(lambda:v.build(sql,root,'f'*64,'e'*64,manifest,{},project,out/'unknown',owner=user,encoder=unknown,input_check=lambda:None))
   assert unknown.calls==1
  passed('UNKNOWN_model_no_automatic_or_explicit_replay_without_cache')
  result['oracle_version']=conn.version;result['status']='PASS'
 finally:
  if conn:conn.close()
  with admin.cursor() as c:c.execute('DROP USER '+user+' CASCADE')
  admin.close();result['isolated_schema_removed']=True

try:main()
except BaseException as e:
 result.update(status='FAIL',error_type=type(e).__name__,error=str(e)[:800],traceback=traceback.format_exc())
 raise
finally:
 sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
 from experiment_json import write_summary
 write_summary(out/'results.json',result)
 print(json.dumps({k:v for k,v in result.items() if k!='traceback'},ensure_ascii=False))
