"""Development unit checks of the storage primitive, not a RAG evaluation."""
from pathlib import Path
import importlib.util,json,logging,os,sys,time,uuid
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1242/oracle-records/snapshot'
sys.path.insert(0,str(C/'02_BACKEND'))
spec=importlib.util.spec_from_file_location('local_admin',ROOT/'06_TOOLS/maintenance/agent_record_oracle_r2.py')
admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)
import oracledb
from semantic_runtime.oracle_agent_records import AgentRecords,RecordSQL
from semantic_runtime import oracle_runtime_paths as paths
from semantic_runtime import runtime_sqlite

class LocalClient:
 SQL_PATH='/local-agent-sql'
 def __init__(self,db):self.db=db;self.errors=[]
 def request(self,method,path,json):
  types={'CLOB':oracledb.DB_TYPE_CLOB,'VARCHAR2':oracledb.DB_TYPE_VARCHAR,'NUMBER':oracledb.DB_TYPE_NUMBER}
  try:
   with self.db.cursor() as c:
    binds=json.get('binds',[]);c.setinputsizes(**{b['name']:types[b['data_type']] for b in binds})
    c.execute(json['statementText'],{b['name']:b['value'] for b in binds})
    if c.description is None:return {'items':[{'result':c.rowcount}]}
    names=[d[0] for d in c.description];rows=c.fetchmany(json['limit']+1)
    convert=lambda v:v.read() if isinstance(v,oracledb.LOB) else v
    return {'items':[{'resultSet':{'items':[{k:convert(v) for k,v in zip(names,r)} for r in rows[:json['limit']]],'offset':0,'hasMore':len(rows)>json['limit']}}]}
  except oracledb.DatabaseError as exc:
   e=exc.args[0];self.errors.append({'code':e.code,'message':e.message});print('Oracle development error',e.code,e.message,flush=True)
   return {'items':[{'errorCode':e.code}]}

def main():
 logging.disable(logging.CRITICAL)
 os.environ['DP']='oracle';os.environ['GENOS_RUNTIME_DIR']=paths.DEFAULT_ROOT
 test=uuid.uuid4().hex
 db=admin.connection();client=LocalClient(db)
 sql=RecordSQL(client,binding='local-development',deadline=time.monotonic()+180,max_calls=10000)
 store=AgentRecords(sql,namespace='unit-'+test)
 checks=[]
 try:
  with paths.using(store):
   checks.append(store.preflight())
   raw=('한글\n🌱 "test"\r\n'*2000).encode()
   store.put_bodies([raw]);assert store.body(__import__('hashlib').sha256(raw).hexdigest())==raw
   root=paths.Path(paths.DEFAULT_ROOT)/test;root.mkdir(parents=True)
   p=root/'record.txt';p.write_text('원래\n');assert p.read_text()=='원래\n'
   with p.open('a',encoding='utf-8') as f:f.write('추가1\n');f.flush();f.write('추가2\n')
   assert p.read_text()=='원래\n추가1\n추가2\n'
   assert sorted(x.name for x in root.iterdir())==['record.txt']
   path=root/'journal.sqlite';conn=runtime_sqlite.connect(path,isolation_level=None)
   conn.executescript('CREATE TABLE item(id INTEGER PRIMARY KEY,text TEXT NOT NULL,data BLOB,optional TEXT);PRAGMA user_version=7;')
   conn.execute('BEGIN IMMEDIATE');conn.execute('INSERT INTO item VALUES(?,?,?,?)',(1,'한글',b'\x00\xff',None));conn.execute('COMMIT');conn.close()
   assert path.is_file()
   conn=runtime_sqlite.connect(path,isolation_level=None)
   assert conn.execute('PRAGMA user_version').fetchone()[0]==7
   assert tuple(conn.execute('SELECT * FROM item').fetchone())==(1,'한글',b'\x00\xff',None)
   conn.execute('BEGIN IMMEDIATE');conn.execute("UPDATE item SET text='rollback'");conn.execute('ROLLBACK');conn.close()
   conn=runtime_sqlite.connect(path,isolation_level=None)
   assert conn.execute('SELECT text FROM item').fetchone()[0]=='한글';conn.close()
   from semantic_runtime.legal_agent.case_repository import CaseRepository
   case=CaseRepository(root/'cases-v3.sqlite',None,None)
   with case.transaction():
    case.identity('s',{'user_id':'u','team_id':'t'})
   case.close()
   case=CaseRepository(root/'cases-v3.sqlite',None,None)
   assert case.db.execute('SELECT owner,team FROM session WHERE id=?',('s',)).fetchone()[0]=='u'
   case.close()
   from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
   shortcut=ShortcutRepository(root/'cases-v4.sqlite')
   principal={'user_id':'u','team_id':'t','authenticated':True,'document_ids':['d']}
   with shortcut.transaction():
    artifact=shortcut.artifact(b'original artifact',principal,documents=['d'])
   assert shortcut.read_artifact(artifact,principal)==b'original artifact'
   shortcut.close()
   shortcut=ShortcutRepository(root/'cases-v4.sqlite')
   assert shortcut.read_artifact(artifact,principal)==b'original artifact'
   shortcut.close()
   from semantic_runtime.legal_agent.context import RequestContext
   from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
   from semantic_runtime.legal_agent.publication import owner_lock
   query={'id':'query:development','question':'technical storage contract','scope':{'document_version_ids':['d']}}
   binding={'generation_id':'synthetic','store_sha256':'a'*64}
   context=RequestContext.create(query,{'question':query['question'],'use_llm':False},binding,120)
   directory=root/'legal-agent'/'runs'/'20261030'/context.run_id
   profile={'max_model_attempts':10,'finalization_reserve':2,'max_tool_actions':100}
   with owner_lock(directory):
    work=UnifiedRepository(directory/'journal.sqlite',context,profile)
    with work.transaction():work.event('TECHNICAL_UNIT',{'unicode':'한글🌱','reason':None,'purpose':None})
    work.close()
   with owner_lock(directory):
    work=UnifiedRepository(directory/'journal.sqlite')
    row=work.db.execute("SELECT payload_json FROM event WHERE kind='TECHNICAL_UNIT'").fetchone()
    assert json.loads(row[0])=={'unicode':'한글🌱','reason':None,'purpose':None}
    work.close()
   checks.append({'bodies':True,'unicode':True,'logical_paths':True,'append':True,'row_delta':True,'reconnect':True,'rollback':True,'sql_calls':sql.calls})
  result={'development_checks':checks,'oracle_errors':client.errors}
  out=ROOT/'04_EXPERIMENTS/ADR/ADR-1242-oracle-agent-records-main/artifacts/development';out.mkdir(exist_ok=True)
  (out/('pass-'+test+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps(result,ensure_ascii=False))
 finally:
  db.rollback()
  with db.cursor() as c:
   for name in ('LGL_AGT_REC_A','LGL_AGT_RUN_A','LGL_EXEC_ST_A','LGL_AGT_BODY_A'):
    c.execute('DELETE FROM SIDDA.'+name+' WHERE SCOPE_HASH_VAL=:scope',scope=store.scope)
  db.commit();db.close()

if __name__=='__main__':main()
