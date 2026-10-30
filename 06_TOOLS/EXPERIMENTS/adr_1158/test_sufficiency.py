from copy import deepcopy
import sqlite3,json
from types import SimpleNamespace
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import ontology_scenarios as sc,ontology_scenario_runtime as rt
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
from test_scenarios import compiled,fixture,choice,issues,options

class Journal:
 def __init__(self,path):
  self.binding={'test':'scenario'};self.db=sqlite3.connect(path)
  self.db.execute('CREATE TABLE IF NOT EXISTS event(seq INTEGER PRIMARY KEY,kind TEXT,payload_json TEXT,payload_hash TEXT)')
 def event(self,k,v):self.db.execute('INSERT INTO event(kind,payload_json,payload_hash) VALUES(?,?,?)',(k,json.dumps(v),digest(v)));self.db.commit()
 def budget(self):return {'model_limit':40,'finalization_reserve':4,'model_reserved':0}

class Host:
 def __init__(self,journal,values,available=36,remaining=600):
  self.host=SimpleNamespace(binding={'test':'same'});self.s=SimpleNamespace(work=journal,context=SimpleNamespace(remaining=lambda:remaining),sources=SimpleNamespace(profile={'selection_time_reserve_seconds':30}))
  journal.budget=lambda:{'model_limit':40,'finalization_reserve':4,'model_reserved':36-available}
  self.values=iter(values);self.calls=[]
 def invoke(self,system,data,schema,phase):self.calls.append(deepcopy(data));return deepcopy(next(self.values))
 def verify_claims(self,claims,sources):assert all(c['span_receipts'] for c in claims)

def incomplete(action='RESELECT',paths=None):
 v=choice();v['choices'][0].update(next_action=action,missing_scope=['예외 적용 범위 확인'])
 if paths is not None:v['choices'][0]['path_ids']=paths
 return v

def test_short_prompt_and_explicit_multiple_choices():
 assert len(sc.PROMPT)<500 and '복수 선택' in sc.PROMPT and '비교해야' not in sc.PROMPT
 r,s,f=fixture();two=deepcopy(r['paths'][0]);two['id']='PATH2';r['paths'].append(two)
 c=sc.bind_current(sc.compile_package(r,s),f);v=choice(paths=['PATH1','PATH2']);sc.validate_choice(v,c,issues())
 assert len(sc.materialize_choice(v,c,issues(),options())['claims'])==2

@pytest.mark.parametrize('mutate',['missing_scope','answer_with_gap','nomatch_reselect','unknown_action'])
def test_sufficiency_contract_rejects_conflicts(mutate):
 p,c=compiled();v=choice()
 if mutate=='missing_scope':v['choices'][0]['next_action']='RESELECT'
 if mutate=='answer_with_gap':v['choices'][0]['missing_scope']=['부족']
 if mutate=='nomatch_reselect':v=choice('NO_MATCH',[]);v['choices'][0]['next_action']='RESELECT'
 if mutate=='unknown_action':v['choices'][0]['next_action']='AUTO_APPROVE'
 with pytest.raises(ProposalError):sc.validate_choice(v,c,issues())

@pytest.mark.parametrize('available,remaining,expected',[(36,600,2),(3,600,1),(36,5,1)])
def test_reselection_budget_and_persistent_same_request(tmp_path,available,remaining,expected):
 p,c=compiled();j=Journal(tmp_path/'j.sqlite');h=Host(j,[incomplete(),choice()],available,remaining)
 result=rt.assess(h,c,[],options(),issues(),'질문',{},None)
 assert len(h.calls)==expected
 receipt=result['assessment_basis']['scenario_choice'];assert receipt['effective_action']==('ANSWER' if expected==2 else 'SEARCH')
 if expected==2:assert h.calls[1]['previous_choice']==incomplete() and h.calls[1]['reselection_remaining']==0
 j.db.close();j2=Journal(tmp_path/'j.sqlite');h2=Host(j2,[],available,remaining)
 again=rt.assess(h2,c,[],options(),issues(),'질문',{},None)
 assert not h2.calls and again==result
 j2.db.close()

def test_second_insufficiency_retains_claims_and_search_gap(tmp_path):
 p,c=compiled();j=Journal(tmp_path/'j');h=Host(j,[incomplete(),incomplete()]);v=rt.assess(h,c,[],options(),issues(),'질문',{},None)
 assert len(h.calls)==2 and v['claims'] and v['gaps'][0]['kind']=='MISSING_SCOPE'
 assert v['assessment_basis']['scenario_choice']['effective_action']=='SEARCH';sc.verify_selected_text(v);j.db.close()

def test_partial_multi_issue_search_preserves_supported_path(tmp_path):
 p,c=compiled();is_=[*issues(),{'id':'Q2','question':'다른 범위'}];v=choice();other=choice('NO_MATCH',[])['choices'][0];other['issue_id']='Q2';v['choices'].append(other)
 j=Journal(tmp_path/'j');h=Host(j,[v]);result=rt.assess(h,c,[],options(),is_,'질문',{},None)
 assert len(h.calls)==1 and result['claims'][0]['issue_refs']==['Q1'] and result['gaps'][0]['issue_id']=='Q2';j.db.close()

def test_unknown_transport_not_retried_as_semantic_gap(tmp_path):
 p,c=compiled();j=Journal(tmp_path/'j');h=Host(j,[])
 def fail(*a):raise TimeoutError('outcome unknown')
 h.invoke=fail
 with pytest.raises(TimeoutError):rt.assess(h,c,[],options(),issues(),'질문',{},None)
 with pytest.raises(ContractError,match='unknown'):rt.assess(h,c,[],options(),issues(),'질문',{},None)
 j.db.close()

def test_catalog_absence_skips_model_and_reentry_skips_scenarios(tmp_path):
 p,c=compiled();c['paths']=[];j=Journal(tmp_path/'j');h=Host(j,[])
 v=rt.assess(h,c,[],options(),issues(),'질문',{},None)
 assert not h.calls and v['gaps'] and v['assessment_basis']['scenario_choice']['effective_action']=='SEARCH'
 assert rt.ordinary_after_reentry({'investigation_state':{'gap_rounds':[{}]}})
 assert not rt.ordinary_after_reentry({'investigation_state':{}});j.db.close()
