from copy import deepcopy
from types import SimpleNamespace as NS
import json,inspect
import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import investigation_supervisor as su,answer_progress as ap
from semantic_runtime.legal_agent.errors import ContractError,TransportError
from semantic_runtime.legal_agent.completion_contracts import obj

class Repo:
 def __init__(self):self.reserved=0;self.events=[]
 def budget(self):return dict(model_limit=40,finalization_reserve=3,model_reserved=self.reserved)
 def event(self,k,v):self.events.append((k,deepcopy(v)))

def fixture():
 data={'presentation_id':'p1','issues':[{'id':'Q1','request_quote':'기준은?'}],'sources':[{'id':'E1','text':'실제 원문'}], 'laws':[]}
 inv=NS(policy={'supervisor_mode':'enforce','read_candidate_page_size':20},p={'binding':'fixed'},question='기준은?',s=NS(repo=Repo(),profile={'selection_time_reserve_seconds':30}),save=lambda:None,left=lambda:200)
 inv.validate=lambda d,v,a:None
 action=obj({'choice':{'const':'OPEN_LAW'},'target':{'enum':['T1','T2']}});schema={'type':'object','anyOf':[action]}
 def expand(v):validate({k:v[k] for k in ('choice','target')},schema);return {'next_action':'OPEN_LAW','target':v['target']}
 value={'choice':'OPEN_LAW','target':'T1','answer_progress':{'goals':[{'issue_id':'Q1','status':'NEEDS_SOURCE','answer_so_far':'','basis_refs':[], 'material_need':'위임 기준','next_answer_change':'기준 확인','previous_effect':'NO_CHANGE'}]}}
 payload={'read_candidates':[{'target':'T1'},{'target':'T2'}],'issues':data['issues'],'sources':data['sources'],'tool_options':[]}
 return inv,data,value,payload,schema,expand

def seed(inv,data):
 st=su.state_for(inv,data);st['unchanged']={'Q1':1};su.save(inv,st)

def call(inv,data,v,p,s,x,k='key'):
 return su.gate(inv,data,{},p,v,x(v),s,x,k)

def test_no_basis_grammar_has_only_satisfiable_statuses():
 schema=ap.schema({},[{'id':'Q1'}],False)
 statuses=[b['properties']['status']['const'] for b in schema['properties']['goals']['items']['anyOf']]
 assert statuses==['NEEDS_SOURCE','NO_PROGRESS']
 for status in statuses:
  validate({'goals':[dict(issue_id='Q1',status=status,answer_so_far='',basis_refs=[],material_need='필요 원문',next_answer_change='확인',previous_effect='INITIAL')]},schema)

@pytest.mark.parametrize('directive',['CONTINUE_TARGETED','REDIRECT','ASSESS_NOW','STOP_UNRESOLVED'])
def test_gates_before_actual_execution(directive):
 inv,d,v,p,s,x=fixture();seed(inv,d);calls=[];executed=[]
 def invoke(*args):
  calls.append(args);inv.s.repo.reserved+=1
  return {'directive':directive,'reason':'현재 쟁점을 확인','remaining_scope':'위임 기준',**({'action':{'choice':'OPEN_LAW','target':'T1' if directive=='CONTINUE_TARGETED' else 'T2'}} if directive in ('CONTINUE_TARGETED','REDIRECT') else {})}
 inv.invoke=invoke
 if directive in ('ASSESS_NOW','STOP_UNRESOLVED'):
  with pytest.raises(ap.ProgressHandoff):call(inv,d,v,p,s,x)
  assert not executed
 else:
  out=call(inv,d,v,p,s,x);su.before_execute(inv,d,out);executed.append(out['target']);su.after_execute(inv,d,out,True)
  assert executed==['T1' if directive=='CONTINUE_TARGETED' else 'T2']
  if directive=='REDIRECT':
   with pytest.raises(ContractError):su.before_execute(inv,d,x(v))
  # Response checkpoint resumes without another model call.
  inv.p=json.loads(json.dumps(inv.p));assert call(inv,d,v,p,s,x)==out
 assert len(calls)==1 and inv.s.repo.reserved==1

@pytest.mark.parametrize('failure',['malformed','429','unknown'])
def test_failed_supervisor_no_retry_or_original_execution(failure):
 inv,d,v,p,s,x=fixture();seed(inv,d);calls=[]
 def invoke(*args):
  calls.append(1)
  if failure=='malformed':return {'directive':'REDIRECT'}
  raise TransportError('test',retryable=failure=='429',unknown=failure=='unknown')
 inv.invoke=invoke
 with pytest.raises(ap.ProgressHandoff):call(inv,d,v,p,s,x)
 with pytest.raises(ap.ProgressHandoff):call(inv,d,v,p,s,x)
 with pytest.raises(ContractError):su.before_execute(inv,d,x(v))
 assert len(calls)==1

@pytest.mark.parametrize('reason',['limit','reserve','pending','deadline'])
def test_no_call_after_limits_and_resume(reason):
 inv,d,v,p,s,x=fixture();seed(inv,d);st=su.state_for(inv,d)
 if reason=='limit':st['calls']=2
 if reason=='pending':st['pending']={'key':'lost'}
 if reason=='reserve':inv.s.repo.reserved=37
 if reason=='deadline':inv.left=lambda:30
 su.save(inv,st);inv.p=json.loads(json.dumps(inv.p));inv.invoke=lambda *a:pytest.fail('call forbidden')
 with pytest.raises(ap.ProgressHandoff):call(inv,d,v,p,s,x)

@pytest.mark.parametrize('change',['binding','state_hash','target','presentation'])
def test_integrity_cannot_be_overridden(change):
 inv,d,v,p,s,x=fixture();out=call(inv,d,v,p,s,x)
 if change=='binding':inv.p['binding']='other'
 if change=='state_hash':next(iter(inv.p['investigation_supervisor'].values()))['calls']=100
 if change=='target':out['target']='evil'
 if change=='presentation':d['presentation_id']='new'
 with pytest.raises(ContractError):su.before_execute(inv,d,out)

def test_visible_page_limit_and_scope_not_coverage_proof():
 inv,d,v,p,s,x=fixture();d['laws']=[{'document_id':'market','name':'시장규정','article_count':92,'article_matches':[{}]*8,'open_action':'T2'}]
 f=su.frontier(inv,d)[0];assert f['matched_articles']==92 and f['prepared_articles']==8 and not f['scope_checked']
 seed(inv,d)
 def invoke(prompt,body,schema,*args):
  assert len(body['read_candidates'])<=20 and body['candidate_frontier'][0]['open_action']=='T2'
  return {'directive':'REDIRECT','reason':'미확인 시장 범위','remaining_scope':'시장규정 확인','action':{'choice':'OPEN_LAW','target':'T2'}}
 inv.invoke=invoke;assert call(inv,d,v,p,s,x)['target']=='T2'

def test_sparse_progress_does_not_stop_valid_dependency():
 inv,d,v,p,s,x=fixture();seed(inv,d)
 inv.invoke=lambda *a:{'directive':'CONTINUE_TARGETED','reason':'실제 위임 조항 미확인','remaining_scope':'위임 기준', 'action':{'choice':'OPEN_LAW','target':'T1'}}
 out=call(inv,d,v,p,s,x);su.before_execute(inv,d,out)
 assert out['target']=='T1' and not su.state_for(inv,d)['halt']

def test_dictionary_claim_keys_and_text_roundtrip():
 from semantic_runtime.legal_agent.navigation_input import NavigationReferences
 from semantic_runtime.legal_agent.stable_references import identities
 r=object.__new__(NavigationReferences);r.stable=True;r.forward={'C1':'C2','E1':'E2'};r.reverse={v:k for k,v in r.forward.items()}
 value={'claims':[{'claim_id':'C1','text':'C1은 문장 그대로 100분의10'}], 'claim_evidence_refs':{'C1':['E1']}}
 encoded=r.view(value);assert encoded['claim_evidence_refs']=={'C2':['E2']};assert encoded['claims'][0]['text']==value['claims'][0]['text']
 assert r.restore(encoded)==value and 'C1' in identities({'claim_evidence_refs':{'C1':['E1']}})[0]

def test_physical_attempt_policy_and_execute_gate_wiring():
 from semantic_runtime.legal_agent.bounded_source_session import BoundedSourceSession
 from semantic_runtime.legal_agent.law_navigation import Investigation
 text=inspect.getsource(BoundedSourceSession.structured)
 assert "profile['max_transport_retries'] = 0" in text and "profile['max_schema_repairs'] = 0" in text
 text=inspect.getsource(Investigation.run)
 assert text.index('supervisor.before_execute(self,data,decision)')<text.index("self.p['accepted'] = {'input_hash':")
 assert "'investigation_supervisor'" in text
 assert 'supervisor.after_execute(self,data,decision,applied)' in text


def test_independent_gap_read_after_handoff_only_once(monkeypatch):
 inv,d,v,p,s,x=fixture();st=su.state_for(inv,d);st['halt']='ASSESS_NOW';su.save(inv,st)
 d['assessment_gaps']=[{'gap_id':'g'}]
 monkeypatch.setattr(ap,'assessment_requirements',lambda *a:[{'gap_id':'g','target_binding_hash':'bound','issue_id':'Q1','offered_actions':['T2']}])
 decision={'next_action':'READ_ARTICLES','targets':['T2'],'issue_refs':['Q1']}
 assert su.independent_recovery(inv,d,decision,st,'k1')
 su.authorize(inv,d,decision,st,recovery=True);su.before_execute(inv,d,decision)
 assert not su.independent_recovery(inv,d,decision,st,'k2')
 assert st['halt']=='ASSESS_NOW' and st['calls']==0
