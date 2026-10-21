from copy import deepcopy
from types import SimpleNamespace
import hashlib,sqlite3
import pytest
from semantic_runtime.legal_agent import decision_projection as dp,evidence_inventory as inv,law_navigation as nav
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.contracts import digest
from semantic_runtime import resident_data,storage

def case(status='DEFERRED'):
 page={'id':'E1','branch_id':'B1','source_id':'S1','document_id':'D1','page':1,'total_pages':1,'scope_id':'old','accepted':True,'spans':[{'block_id':'1','start_cp':0,'end_cp':2,'text':'원문','evidence_id':'X1'}]}
 state={'groups':{'B1':{'source_id':'S1','status':status,'page_plan':[]}},'selected':{'B1':{'source_id':'S1','document_id':'D1','offer':{'id':'new'}}},'basis_history':{'E1':page}}
 session=SimpleNamespace(scope={'D1'},store=SimpleNamespace(source=lambda *a:{'text':'원문'}),profile={'max_read_chars':10,'max_context_chars':100},repo=SimpleNamespace(event=lambda *a:None,budget=lambda:{}))
 return session,state

@pytest.fixture
def pack(monkeypatch):
 def output(s,p,sources,gathered):return [{'source_id':sid,'spans':deepcopy(gathered[sid])} for sid in sources]
 monkeypatch.setattr(inv,'_pack',output)

@pytest.mark.parametrize('status',['READ','DEFERRED','ACTIVE'])
def test_delivered_context_preserves_disposition_without_adoption(status,pack):
 s,p=case(status);before=deepcopy(p)
 refs,receipt=dp.bounded_original_refs(p,[],50);got=inv.originals_for(s,p,context_refs=refs)
 assert got[0]['spans']==p['basis_history']['E1']['spans'];assert p==before
 assert got[0]['delivered_context_only']==(status!='ACTIVE')
 assert not receipt['automatic_adoption']

@pytest.mark.parametrize('defect',['excluded','acl','source','range','unaccepted','missing'])
def test_context_integrity_still_blocks_invalid_original(defect,pack):
 s,p=case()
 if defect=='excluded':p['groups']['B1']['status']='EXCLUDED'
 elif defect=='acl':s.scope=set()
 elif defect=='source':p['selected']['B1']['source_id']='S2'
 elif defect=='range':p['basis_history']['E1']['spans'][0]['text']='가짜'
 elif defect=='unaccepted':p['basis_history']['E1']['accepted']=False
 else:p['selected'].clear()
 with pytest.raises(ContractError):inv.originals_for(s,p,context_refs=['E1'])

def test_legacy_explicit_selection_still_rejects_deferral(pack):
 s,p=case()
 with pytest.raises(ContractError):inv.originals_for(s,p,['E1'])

def test_bounded_stop_hands_off_deferred_original_with_uncertainty(pack):
 s,p=case();obj=SimpleNamespace(p=p,s=s,modern=True,control=True,close_gap_round=lambda *a:None,save=lambda:None,result=lambda d:d)
 d=nav.Investigation.bounded_result(obj,'NO_PROGRESS')
 assert d['next_action']=='FINISH' and not d['evidence_sufficient'];assert p['groups']['B1']['status']=='DEFERRED'
 assert p['adoption_fallback']['source_ids']==['S1']

def test_excluded_only_stop_remains_pending(pack):
 s,p=case('EXCLUDED');obj=SimpleNamespace(p=p,s=s,modern=True,control=True,close_gap_round=lambda *a:None,save=lambda:None,result=lambda d:d)
 assert nav.Investigation.bounded_result(obj,'NO_PROGRESS')['next_action']=='PENDING'

@pytest.mark.parametrize('action',['SKIP','FOLLOW'])
def test_identical_closed_reference_choice_survives_focus(action):
 d={'action':action,'scopes':[],'reason':'원문에 기반한 이전 판단'};old={'binding':'B','decisions':{'K':d}};current={};states={'old':old,'new':current};before=deepcopy(old)
 assert dp.shared_reference_decisions(states,current,'B')==['K'];assert current['decisions']['K']==d
 current['decisions']['K']['reason']='new';assert old==before

def test_conflicting_scoped_choices_are_not_resolved_by_host():
 states={'a':{'binding':'B','decisions':{'K':{'action':'SKIP'}}},'b':{'binding':'B','decisions':{'K':{'action':'FOLLOW'}}}};current={}
 assert dp.shared_reference_decisions(states,current,'B')==[] and not current['decisions']

def test_current_replay_and_deferred_and_foreign_binding_preserved():
 current={'binding':'B','decisions':{'K':{'action':'FOLLOW'}}};before=deepcopy(current)
 states={'a':{'binding':'B','decisions':{'K':{'action':'SKIP'},'D':{'action':'DEFER'}}},'b':{'binding':'foreign','decisions':{'Z':{'action':'SKIP'}}}}
 assert dp.shared_reference_decisions(states,current,'B')==[] and current==before

def test_stale_current_binding_rejected():
 with pytest.raises(ContractError):dp.shared_reference_decisions({}, {'binding':'old'},'new')

def test_low_ram_direct_read_has_no_ram_or_disk_mirror(tmp_path):
 path=tmp_path/'source.sqlite'
 with sqlite3.connect(path) as db:db.execute('CREATE TABLE data(x)');db.execute('INSERT INTO data VALUES(?)',('원문 😀',))
 pin=hashlib.sha256(path.read_bytes()).hexdigest();storage.verify_store_binding(path,pin)
 pool=resident_data.ResidentPool(mode='off',directory=tmp_path/'cache')
 with pool.connect(path,expected=pin) as db:
  assert db.execute('SELECT x FROM data').fetchone()[0]=='원문 😀'
  assert db.execute('PRAGMA database_list').fetchone()[2]==str(path)
  with pytest.raises(sqlite3.OperationalError):db.execute('DELETE FROM data')
 db.close();assert not pool.entries and pool.memory_bytes==pool.local_bytes==0 and pool.local_root is None
 pool.close();assert not (tmp_path/'cache').exists()
 with path.open('ab') as f:f.write(b'changed')
 with pytest.raises(ValueError):storage.verify_store_binding(path,pin)
