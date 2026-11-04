import pytest,time
from copy import deepcopy
from types import SimpleNamespace as NS
from semantic_runtime.oracle_query_matcher import Units
from semantic_runtime.oracle_dp_io import DPError,BudgetPause,digest

def fixture(rows=None):
 rows=rows if rows is not None else [{'document_id':'d','unit_id':str(i),'unit':{'parent':None if i==0 else '0','span':[i,i]},'coordinate':None} for i in range(6)]
 calls=[]
 def page(kind,**kw):
  calls.append(kw);data=[r for r in rows if r['document_id']==kw.get('document_id','d')]
  if kw.get('owner_id') is not None:data=[r for r in data if r['unit']['parent']==kw['owner_id']]
  if kw.get('lookup_id'):data=[r for r in data if digest([r['document_id'],r['unit_id']])==kw['lookup_id']]
  return {'rows':deepcopy(data),'next':None}
 req=NS(release_id='r',snapshot=NS(binding_hash='s'),sources=NS(allowed={'d'}),records=NS(manifest={'tables':['native.unit']},page=page),sql=NS(deadline=time.monotonic()+100))
 return Units(req),calls,rows

def test_complete_root_reuses_children_points_and_missing_without_extra_sql():
 u,c,rows=fixture();assert list(u.children_for('d',None))==[(('d','0'),rows[0]['unit'])];assert len(c)==1
 assert len(list(u.children_for('d','0')))==5;assert u[('d','5')]==rows[5]['unit'];assert list(u.children_for('d','missing'))==[]
 with pytest.raises(KeyError):u[('d','missing')]
 assert len(c)==1

def test_cached_view_returns_copies():
 u,c,rows=fixture();list(u.children_for('d',None));value=u[('d','1')];value['parent']='bad';items=list(u.children_for('d','0'));items[0][1]['parent']='bad';assert u[('d','1')]==rows[1]['unit'];assert len(c)==1

@pytest.mark.parametrize('kind',['deadline','release','snapshot','acl','manifest'])
def test_cached_view_keeps_binding_and_deadline_checks(kind):
 u,c,_=fixture();list(u.children_for('d',None));r=u.request
 if kind=='deadline':r.sql.deadline=time.monotonic()-1
 elif kind=='release':r.release_id='changed'
 elif kind=='snapshot':r.snapshot.binding_hash='changed'
 elif kind=='acl':r.sources.allowed={'d','foreign'}
 else:r.records.manifest={'changed':True}
 with pytest.raises((DPError,BudgetPause)):list(u.children_for('d','0'))
 with pytest.raises((DPError,BudgetPause)):u[('d','1')]
 assert len(c)==1

@pytest.mark.parametrize('limit',['ROOT_MAX_UNITS','ROOT_MAX_BYTES'])
def test_overflow_does_not_cache_partial_document(limit):
 u,c,rows=fixture();setattr(u,limit,1);assert len(list(u.children_for('d',None)))==1;assert getattr(u,'_root_document',None) is None
 assert len(list(u.children_for('d','0')))==5;assert len(c)==2

def test_duplicate_identity_rejected_and_not_cached():
 u,c,rows=fixture();rows.append(deepcopy(rows[1]))
 with pytest.raises(DPError,match='duplicate'):list(u.children_for('d',None))
 assert getattr(u,'_root_document',None) is None

def test_authorized_empty_view_is_complete_and_request_local():
 u,c,_=fixture([]);assert list(u.children_for('d',None))==[]
 with pytest.raises(KeyError):u[('d','1')]
 assert len(c)==1;v,d,_=fixture();assert v[('d','1')]['parent']=='0';assert len(d)==1
 with pytest.raises(DPError,match='unauthorized'):list(u.children_for('other',None))
