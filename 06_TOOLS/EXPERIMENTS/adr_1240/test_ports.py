from types import SimpleNamespace as S
import json,sqlite3,hashlib,importlib.util
from pathlib import Path
import pytest
from semantic_runtime.unit_fulltext import UnitFulltextIndex
from semantic_runtime.oracle_query_fulltext import UnitIndex
from semantic_runtime.oracle_dp_io import DPError,digest
from semantic_runtime.legal_agent import law_candidates as lc,query_scope as qs,structure_query
from semantic_runtime import oracle_query_db

@pytest.fixture
def units():
 rows=[]
 for did in ('doc','foreign'):
  for i in range(205):
   value={'key':did+'#unit:'+str(i),'document_id':did,'source_id':did+':root'+str(i//10),'unit_id':str(i)}
   rows.append({**{k:value[k] for k in ('key','document_id','source_id')},'json':json.dumps(value)})
 return rows

@pytest.fixture
def local(units):
 db=sqlite3.connect(':memory:');db.execute('create table unit(key primary key,source_id,document_id,json)')
 db.executemany('insert into unit values(:key,:source_id,:document_id,:json)',units)
 idx=object.__new__(UnitFulltextIndex);idx.check_unchanged=lambda:None
 yield idx,db
 db.close()

def remote(monkeypatch,local,units,mutation=None):
 idx=object.__new__(UnitIndex);idx.asset='fulltext/units.sqlite';idx.kinds={'unit':'asset_test.unit'};idx.request=S(sources=S(allowed={'doc'}));idx.check_unchanged=lambda:None;calls=[]
 class Relation:
  def __init__(self,request,asset):assert request is idx.request and asset==idx.asset
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def set_progress_handler(self,*a):pass
  def execute(self,statement,params):
   assert params[0]=='doc';calls.append(('relation',params[0],len(json.loads(params[1]))))
   rows=local[1].execute(statement,params).fetchall()
   if mutation=='duplicate':rows+=rows[:1]
   return rows
 def page(kind,**kw):
  assert kind==idx.kinds['unit'] and kw['document_id']=='doc' and len(kw['lookup_ids'])<=100
  calls.append(('verified',len(kw['lookup_ids'])))
  values=[dict(x) for x in units if x['key'] in kw['lookup_ids'] and x['document_id']=='doc']
  if mutation=='missing':values=values[1:]
  if mutation in ('doc','unit','source','key') and values:
   v=values[0];body=json.loads(v['json']);body[{'doc':'document_id','unit':'unit_id','source':'source_id','key':'key'}[mutation]]='wrong';v['json']=json.dumps(body)
  if mutation=='hash':raise DPError('QUERY_ROW_HASH')
  return {'rows':values,'next':None}
 idx.records=S(page=page);monkeypatch.setattr(oracle_query_db,'Connection',Relation)
 return idx,calls

@pytest.mark.parametrize('selected',[[],['0'],['0','0','3'],['missing'],[str(i) for i in range(205)]])
def test_exact_scope_port_parity(monkeypatch,local,units,selected):
 idx,calls=remote(monkeypatch,local,units)
 assert idx.scope_keys(idx,'doc',selected)==sorted(map(tuple,local[0].scope_keys(local[1],'doc',selected)))
 assert not hasattr(idx,'execute')
 assert (len(calls)==0) is (not selected)
 if len(selected)==205:assert [c[1] for c in calls if c[0]=='verified']==[100,100,5]

@pytest.mark.parametrize('mutation',['duplicate','missing','doc','unit','source','key','hash'])
def test_selected_remote_rows_fail_closed(monkeypatch,local,units,mutation):
 idx,_=remote(monkeypatch,local,units,mutation)
 with pytest.raises(DPError):idx.scope_keys(idx,'doc',['0','1'])

@pytest.mark.parametrize('mutation',['foreign','wrong_connection','cancel','manifest'])
def test_scope_and_snapshot_checked_before_reads(monkeypatch,local,units,mutation):
 idx,calls=remote(monkeypatch,local,units)
 if mutation in ('cancel','manifest'):
  def reject():raise DPError('QUERY_CANCELLED' if mutation=='cancel' else 'QUERY_RELEASE_BINDING')
  idx.check_unchanged=reject
 with pytest.raises(DPError):idx.scope_keys(object() if mutation=='wrong_connection' else idx,'foreign' if mutation=='foreign' else 'doc',['0'])
 assert calls==[]

@pytest.mark.parametrize('selected',['0',[None],[1],[''],['1',2]])
def test_invalid_unit_scope_rejected(monkeypatch,local,units,selected):
 idx,_=remote(monkeypatch,local,units)
 with pytest.raises((DPError,ValueError)):idx.scope_keys(idx,'doc',selected)
 with pytest.raises(ValueError):local[0].scope_keys(local[1],'doc',selected)

@pytest.mark.parametrize('root,excluded,permitted,expected',[(None,set(),{'s0','s1','s2'},{'k0','k1','k2'}),('1',set(),{'s0','s1','s2'},{'k1','k2'}),('1',{'2'},{'s0','s1','s2'},{'k1'}),('1',set(),{'s1'},{'k1'})])
def test_native_scope_consumer_preserves_tree_exclusion_acl(monkeypatch,root,excluded,permitted,expected):
 tree={'nodes':{'0':{},'1':{},'2':{}},'children':{'0':['1'],'1':['2']}}
 monkeypatch.setattr(structure_query,'document_tree',lambda *a:tree)
 monkeypatch.setattr(qs,'active',lambda s:bool(excluded));monkeypatch.setattr(qs,'direct',lambda s,d,u:u not in excluded)
 monkeypatch.setattr(lc,'allowed',lambda s:permitted)
 idx=S(check_unchanged=lambda:None,scope_keys=lambda db,d,us:[('k'+u,'s'+u) for u in us]);session=S(scope={'doc'},matcher=object())
 monkeypatch.setattr(lc,'index',lambda s:(idx,object()))
 assert lc.fulltext_scope_keys(session,'doc',root)==frozenset(expected)
 with pytest.raises(Exception,match='outside'):lc.fulltext_scope_keys(session,'foreign',root)
 with pytest.raises(Exception,match='not stored'):lc.fulltext_scope_keys(session,'doc','bad')
