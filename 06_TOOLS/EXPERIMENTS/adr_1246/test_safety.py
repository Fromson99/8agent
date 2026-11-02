"""Deterministic storage and active-cursor fixtures, no model or network."""
from contextlib import contextmanager
import json,os,sqlite3,random,hashlib,copy,threading
from pathlib import Path
import pytest
from semantic_runtime import oracle_runtime_paths as paths,runtime_sqlite
from semantic_runtime.oracle_agent_records import AgentRecords,sha
from semantic_runtime.oracle_dp_io import canonical,digest,DPError
from semantic_runtime.oracle_query_state import StateConflict
from semantic_runtime.legal_agent import journal_storage as js

class MemorySQL:
 def __init__(self):self.parts={};self.calls=0;self.writes=0
 def query(self,text,binds=(),*,limit=100):
  self.calls+=1;b={k:v for k,v,*_ in binds};wanted=json.loads(b['hashes']);rows=[]
  for (h,n),value in sorted(self.parts.items()):
   if h in wanted and (b['first_page'] or (h,n)>(b['after_hash'],b['after_part'])):rows.append({'BODY_HASH_VAL':h,'PART_SEQ_NO':n,'PART':canonical(value)})
  return rows[:limit]
 def mutate(self,text,binds):
  self.calls+=1;self.writes+=1;b={k:v for k,v,*_ in binds}
  for row in json.loads(b['parts']):
   key=(row['hash'],row['seq'])
   if key in self.parts and self.parts[key]!=row['json']:raise DPError('AGENT_BODY_COLLISION')
   self.parts[key]=row['json']

class MemoryRecords:
 """SQL adapter tests isolate RAM execution from Oracle SQL/codec contracts."""
 def __init__(self):self.heads={};self.data={};self.documents={};self.commits=0;self.lock=threading.RLock()
 def state(self,key):return copy.deepcopy(self.heads.get(key))
 def body(self,key):return self.data[key]
 def bodies(self,keys):return {k:self.data[k] for k in keys}
 def put_bodies(self,values):
  for raw in values:self.data[sha(raw)]=raw
 def rows(self,owner,*,kind=None):return [dict(v) for (o,k,key),v in self.documents.items() if o==owner and (kind is None or kind==k)]
 @contextmanager
 def lease(self,*args,**kwargs):
  with self.lock:yield {}
 def commit(self,owner,expected,value,changes,*,run=None,bodies=()):
  assert self.heads.get('a1:head:'+owner,{}).get('revision',0)==expected
  self.put_bodies(bodies);self.commits+=1
  for r in changes:
   key=(r.get('owner',owner),r['kind'],r['key'])
   if r['deleted']:self.documents.pop(key,None)
   else:self.documents[key]={'REC_KIND_CD':r['kind'],'REC_KEY_HASH_VAL':r['key'],'REC_REV_NO':0,'BODY_HASH_VAL':r['body']}
  self.heads['a1:head:'+owner]={'revision':expected+1,'value':copy.deepcopy(value),'sha256':digest(value)}
  return expected+1

@pytest.fixture
def ram(monkeypatch):
 records=MemoryRecords();monkeypatch.setenv('DP','oracle');monkeypatch.setenv('GENOS_RUNTIME_DIR','/oracle-safety-contract')
 for n in ('GENOS_DETAIL_LOG_DIR','GENOS_SHARED_LOG_DIR','GENOS_SYSTEM_LOG_DIR','GENOS_STATE_DIR'):monkeypatch.delenv(n,raising=False)
 with paths.using(records):yield records,paths.Path('/oracle-safety-contract/journal.sqlite')

@pytest.mark.parametrize('raw',[b'',b'\x00\xff',('한글🌱\n'*9000).encode(),random.Random(1246).randbytes(12521)])
def test_v3_roundtrip(raw):
 if not hasattr(AgentRecords,'_encode_body'):pytest.skip('new codec contract')
 sql=MemorySQL();r=AgentRecords(sql,namespace='codec');r.put_bodies([raw]);fresh=AgentRecords(sql,namespace='codec');assert fresh.body(sha(raw))==raw
 assert sql.parts[(sha(raw),0)]['layout_version']==3
 assert all(len(canonical(v).encode())<=4000 for v in sql.parts.values())

def test_body_part_reduction_and_legacy_reuse():
 if not hasattr(AgentRecords,'_encode_body'):pytest.skip('new codec contract')
 raw=canonical({'sources':[{'id':str(i),'text':'문자 원문 및 근거 조건 보존 '*80,'nullable':None,'coords':[1,3,9]} for i in range(600)]}).encode()
 old,manifest=AgentRecords._encode_body(raw,layout=2);new,m3=AgentRecords._encode_body(raw)
 assert len(new)<=len(old)*.5
 sql=MemorySQL()
 for row in [*old,manifest]:sql.parts[(row['hash'],row['seq'])]=row['json']
 r=AgentRecords(sql,namespace='compat');before=copy.deepcopy(sql.parts);r.put_bodies([raw]);assert sql.parts==before and sql.writes==0 and r.body(sha(raw))==raw
 print('PARTS',len(old)+1,'->',len(new)+1,'RAW',len(raw))

@pytest.mark.parametrize('layout',[2,3])
def test_partial_upload_resume_and_missing_parts(layout):
 if not hasattr(AgentRecords,'_encode_body'):pytest.skip('new codec contract')
 raw=random.Random(1246).randbytes(9000);parts,manifest=AgentRecords._encode_body(raw,layout=layout);sql=MemorySQL();sql.parts[(sha(raw),1)]=parts[0]['json']
 r=AgentRecords(sql,namespace='partial')
 with pytest.raises(DPError):r.body(sha(raw))
 r.put_bodies([raw]);assert AgentRecords(sql,namespace='partial').body(sha(raw))==raw
 del sql.parts[(sha(raw),1)]
 with pytest.raises(DPError):AgentRecords(sql,namespace='partial').body(sha(raw))

@pytest.mark.parametrize('field',['body_sha256','stored_sha256','part_count','codec'])
def test_manifest_tamper(field):
 if not hasattr(AgentRecords,'_encode_body'):pytest.skip('new codec contract')
 raw=b'repeated source and condition\n'*1000;sql=MemorySQL();r=AgentRecords(sql,namespace='tamper');r.put_bodies([raw]);m=sql.parts[(sha(raw),0)];m[field]=99 if field=='part_count' else 'invalid'
 with pytest.raises((DPError,ValueError)):AgentRecords(sql,namespace='tamper').body(sha(raw))


def test_interleaved_writer_keeps_detached_cursor_snapshot(ram):
 records,p=ram;a=runtime_sqlite.connect(p,isolation_level=None)
 a.executescript('CREATE TABLE t(id INTEGER PRIMARY KEY,v TEXT);INSERT INTO t VALUES(1,"a"),(2,"b"),(3,"c");')
 b=runtime_sqlite.connect(p,isolation_level=None)
 for i in range(40):
  cursor=a.execute('SELECT id,v FROM t ORDER BY id');first=cursor.fetchone()
  b.execute('UPDATE t SET v=? WHERE id=3',('other'+str(i),))
  a.execute('UPDATE t SET v=? WHERE id=1',('self'+str(i),))
  remaining=cursor.fetchall();assert first[0]==1 and [r[0] for r in remaining]==[2,3]
 assert a.execute('SELECT v FROM t WHERE id=3').fetchone()[0]=='other39'
 a.close();b.close();assert not Path(str(p)).exists()


def test_cursor_types_rollback_and_rows(ram):
 records,p=ram;db=runtime_sqlite.connect(p,isolation_level=None);db.executescript('CREATE TABLE t(k TEXT PRIMARY KEY,v BLOB,n TEXT) WITHOUT ROWID;')
 db.execute('INSERT INTO t VALUES(?,?,?)',('한글',b'\x00\xff',None));db.execute('BEGIN');db.execute('DELETE FROM t');db.rollback()
 db.close();db=runtime_sqlite.connect(p,isolation_level=None);db.row_factory=sqlite3.Row;c=db.execute('SELECT * FROM t');assert c.description[0][0]=='k';assert dict(c.fetchone())=={'k':'한글','v':b'\x00\xff','n':None};assert c.fetchone() is None;db.close()


def test_oracle_does_not_factor_new_blobs_and_restores_old(ram,monkeypatch):
 records,p=ram;monkeypatch.setenv('GENOS_JOURNAL_STORAGE','compact');db=js.connect(p,isolation_level=None);js.initialize(db)
 # Seed an old compact value then restore it after reopening with the new writer.
 text=canonical({'original':'보존 원문\n'*2000});old=js._put(db,text.encode());ref=js.MAGIC+old.encode()+b'"}'
 assert js.restore(db,ref)==text
 before=db.execute('SELECT COUNT(*) FROM journal_blob_v1').fetchone()[0];value=js.store(db,text);assert value==text and not db.compact
 assert db.execute('SELECT COUNT(*) FROM journal_blob_v1').fetchone()[0]==before
 db.close();db=js.connect(p,isolation_level=None);assert js.restore(db,ref)==text;db.close()
