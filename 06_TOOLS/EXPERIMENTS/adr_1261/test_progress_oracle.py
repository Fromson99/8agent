from pathlib import Path
import json,hashlib
import pytest
from test_records import oracle_agent
from test_progress import row,sample
from semantic_runtime import oracle_runtime_paths as paths,runtime_sqlite
from semantic_runtime.oracle_agent_records import AgentRecords,sha
from semantic_runtime.oracle_record_sqlite import decode
from semantic_runtime.oracle_dp_io import canonical,digest,DPError

def fresh(store):
 other=AgentRecords(store.sql,namespace='placeholder');other.scope=store.scope;return other

def test_real_progress_resume_history_rollback_and_budget(oracle_agent):
 store,client,root=oracle_agent;p=root/'cases.sqlite';db=runtime_sqlite.connect(p,isolation_level=None)
 db.execute('CREATE TABLE stage_progress(goal TEXT,input_hash TEXT,payload TEXT,hash TEXT,PRIMARY KEY(goal,input_hash))')
 expected={};value=sample()
 for n in range(8):
  value['frame']=n;value['sources'][n]['claim']='claim'+str(n);text=canonical(value);expected[n]=json.loads(text)
  db.execute('INSERT OR REPLACE INTO stage_progress VALUES(?,?,?,?)',('goal','input',text,digest(value)))
 db.execute('BEGIN IMMEDIATE');db.execute('UPDATE stage_progress SET payload=?',(canonical({'should_not_commit':True}),));db.rollback();db.close()
 other=fresh(store)
 with paths.using(other):
  db=runtime_sqlite.connect(p,isolation_level=None);got=json.loads(db.execute('SELECT payload FROM stage_progress').fetchone()[0]);assert got==expected[7];assert got['budget']==expected[7]['budget'];assert got['ontology']==expected[7]['ontology'];db.close()
 records=store._query("SELECT DISTINCT BODY_HASH_VAL FROM SIDDA.LGL_AGT_REC_A WHERE SCOPE_HASH_VAL=:scope AND REC_KIND_CD='SQLROW:stage_progress' AND REC_REV_NO>0",limit=100)
 restored={}
 for record in records:
  v=json.loads(other.body(record['BODY_HASH_VAL']))
  if v.get('deleted'):continue
  cols={k:decode(x) for k,x in zip(v['columns'],v['values'])};state=json.loads(cols['payload']);restored[state['frame']]=state
 assert restored==expected;assert not Path(str(root)).exists();assert not client.errors

def test_real_interrupted_recipe_resume_and_namespace(oracle_agent):
 store,client,root=oracle_agent;raw=row(sample(11));old=client.request;blocked=False
 def interrupt(method,path,json):
  nonlocal blocked
  for b in json.get('binds',[]):
   if b['name']=='parts' and any(v['seq']==0 and v['json'].get('layout_version')==4 for v in __import__('json').loads(b['value'])) and not blocked:
    blocked=True;raise TimeoutError('Known fixture interruption before root SQL execution')
  return old(method,path,json)
 client.request=interrupt
 with pytest.raises(DPError):store.put_bodies([raw])
 client.request=old;other=fresh(store)
 with pytest.raises(DPError):other.body(sha(raw))
 other.put_bodies([raw]);assert fresh(store).body(sha(raw))==raw
 with pytest.raises(DPError):AgentRecords(store.sql,namespace='another-owner-scope').body(sha(raw))

def test_real_progress_body_ack_loss_reconciles_without_new_root(oracle_agent):
 store,client,root=oracle_agent;owner=digest('progress-ack');raw=row(sample(17));client.fail_after_operation=True
 assert store.commit(owner,0,{'type':'fixture','ontology':['A1'],'budget':{'used':3}},[],bodies=[raw])==1
 assert client.operation_writes==1 and fresh(store).body(sha(raw))==raw
 assert store.operation(owner,digest({'owner':owner,'expected':0,'value':{'type':'fixture','ontology':['A1'],'budget':{'used':3}},'changes':[],'run':None}))

def test_real_legacy_v2_v3_and_shared_progress(oracle_agent):
 store,client,root=oracle_agent
 for layout in (2,3):
  raw=('기존본문'+str(layout)).encode()*2000;parts,manifest=store._encode_body(raw,layout=layout)
  with client.db.cursor() as c:
   import oracledb
   c.setinputsizes(s=oracledb.DB_TYPE_VARCHAR,h=oracledb.DB_TYPE_VARCHAR,n=oracledb.DB_TYPE_NUMBER,j=oracledb.DB_TYPE_CLOB)
   for v in [*parts,manifest]:c.execute('INSERT INTO SIDDA.LGL_AGT_BODY_A VALUES(:s,:h,:n,:j)',s=store.scope,h=v['hash'],n=v['seq'],j=canonical(v['json']))
  client.db.commit();assert fresh(store).body(sha(raw))==raw
 raw=row(sample(23));store.put_bodies([raw]);assert fresh(store).body(sha(raw))==raw
