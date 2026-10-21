from copy import deepcopy
from types import SimpleNamespace
import sqlite3,json
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import evidence_inventory as inv
from semantic_runtime.legal_agent.errors import ContractError

def data(*,historical=True):
 old={'id':'old','block_ids':['1']};new={'id':'new','block_ids':['1','2']}
 page={'id':'E1','branch_id':'B1','source_id':'S1','document_id':'D1','page':1,'total_pages':1,'scope_id':digest(old),'spans':[{'block_id':'1','start_cp':0,'end_cp':3,'text':'원문😀'}]}
 state={'state_version':7,'groups':{'B1':{'id':'B1'}},'selected':{'B1':{'source_id':'S1','document_id':'D1','offer':new if historical else old}},'basis_history':{'E1':{**deepcopy(page),'accepted':True}} if historical else {}}
 session=SimpleNamespace(scope={'D1'},store=SimpleNamespace(source=lambda *a:{'text':'원문😀 후속'}))
 return session,state,page

def delivery_db(session,state,page,*,version=7,bad_view_hash=False):
 db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
 db.executescript('CREATE TABLE event(payload_json TEXT,payload_hash TEXT,kind TEXT);CREATE TABLE model_view(view_id TEXT,body_json TEXT,body_hash TEXT);CREATE TABLE model_attempt(attempt_id TEXT,view_id TEXT,status TEXT);')
 value={'sources':[page],'presentation_id':'P1','state_version':version,'source_stage':'p'}
 event={'presentation_id':'P1','source_stage':'p','contract':inv.DELIVERY,'view_id':'V1','attempt_id':'A1','view_sha256':digest(value),'state_version':version,'sources_sha256':digest(value['sources'])}
 db.execute('INSERT INTO event VALUES(?,?,?)',(json.dumps(event),digest(event),'NAVIGATION_INPUT_DELIVERED'))
 db.execute('INSERT INTO model_view VALUES(?,?,?)',('V1',json.dumps(value),'bad' if bad_view_hash else digest(value)))
 db.execute('INSERT INTO model_attempt VALUES(?,?,?)',('A1','V1','SUCCEEDED'))
 session.repo=SimpleNamespace(db=db);return db,value

def consume(kind,s,p,page):
 if kind=='ack':inv.acknowledge(s,p,page,'P1')
 else:
  db,value=delivery_db(s,p,page)
  try:
   assert inv.reconcile_delivery(s,p,value,'p')
   assert not inv.reconcile_delivery(s,p,value,'p')
  finally:db.close()

@pytest.mark.parametrize('kind',['ack','reconcile'])
@pytest.mark.parametrize('historical',[False,True])
def test_both_delivery_consumers_accept_exact_receipt_only(kind,historical):
 s,p,page=data(historical=historical);expected=deepcopy(page)
 consume(kind,s,p,page)
 assert page==expected and p['selected']['B1']['offer']['id']==('new' if historical else 'old')
 if kind=='ack':assert p['basis_history']['E1']['scope_id']==page['scope_id']
 else:assert len(p['delivery_history'])==1

@pytest.mark.parametrize('kind',['ack','reconcile'])
@pytest.mark.parametrize('defect',['unaccepted','unknown_id','scope','span','source','document','acl','original_changed','page_number'])
def test_historical_flag_cannot_bypass_integrity(kind,defect):
 s,p,page=data();page['retained_historical_scope']=True
 if defect=='unaccepted':p['basis_history']['E1']['accepted']=False
 elif defect=='unknown_id':page['id']='unknown'
 elif defect=='scope':page['scope_id']='forged'
 elif defect=='span':page['spans'][0].update(end_cp=2,text='원문')
 elif defect=='source':p['selected']['B1']['source_id']='changed'
 elif defect=='document':page['document_id']='D2'
 elif defect=='acl':s.scope=set()
 elif defect=='original_changed':s.store.source=lambda *a:{'text':'변조된 원문'}
 else:page['page']=2
 before=deepcopy(p)
 with pytest.raises(ContractError):consume(kind,s,p,page)
 assert p==before

@pytest.mark.parametrize('defect',['state','view_hash'])
def test_historical_receipt_does_not_bypass_event_state_hash(defect):
 s,p,page=data();db,value=delivery_db(s,p,page,version=6 if defect=='state' else 7,bad_view_hash=defect=='view_hash');before=deepcopy(p)
 try:
  with pytest.raises(ContractError):inv.reconcile_delivery(s,p,value,'p')
  assert p==before
 finally:db.close()
