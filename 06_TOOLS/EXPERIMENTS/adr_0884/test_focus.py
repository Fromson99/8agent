from copy import deepcopy
from types import SimpleNamespace
import pytest
from jsonschema import ValidationError
from semantic_runtime.legal_agent import decision_projection as dp,law_navigation as nav,output_contract as oc
from semantic_runtime.legal_agent.errors import ProposalError

def fixture(monkeypatch,value,*,original=True):
 events=[];validated=[];payloads=[]
 data={'issues':[{'id':'Q1','request_quote':'사용자의 업무 질문'}], 'sources':[{'id':'E1','text':'현재 원문'}] if original else [],'basis':[{'id':'E1','branch_id':'B1'}] if original else [],'laws':[],'branches':[],'presentation_id':'P1','state_version':9,'read_batch_limit':8}
 actions={k:{'id':k,'action':kind,'identity':{},'label':kind} for k,kind in [('T1','READ_ARTICLES'),('T2','RESEARCH'),('T3','FOLLOW_CONNECTION')]}
 inv=SimpleNamespace(modern=True,p={'binding':{},'query_surface_history':[['기존 검색']]},s=SimpleNamespace(repo=SimpleNamespace(budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3),event=lambda *v:events.append(v))),question='사용자의 업무 질문',save=lambda:None,validate=lambda *v:validated.append(v))
 def decide(*args,**kwargs):payloads.append(args[2]);args[5](value);return deepcopy(value)
 monkeypatch.setattr(oc,'bounded_decision',decide)
 def canonical(*args):return {'anyOf':[{'properties':{'next_action':{'const':kind},'presentation_id':{'enum':['P1']},'expected_state_version':{'const':9},'targets':{'type':'array'},'issue_refs':{'type':'array'},'basis_refs':{'type':'array'},'exploration':{'type':'array'},'queries':{'type':'array'}}} for kind in ('READ_ARTICLES','FINISH','RESEARCH','FOLLOW_CONNECTION')]}
 monkeypatch.setattr(nav,'decision_schema',canonical)
 return inv,data,actions,validated,payloads

def choice(kind='SEARCH',relation='DIRECT'):
 v={'choice':kind,'target':'T2' if kind=='SEARCH' else 'T3','issue_id':'Q1','missing_need':'직접 필요한 조문','relation':relation,'source_ref':'E1' if relation=='DEPENDENCY' else None}
 if kind=='SEARCH':v['queries']=['주체 핵심행위']
 return v

@pytest.mark.parametrize('kind',['SEARCH','CONNECT'])
@pytest.mark.parametrize('relation',['DIRECT','DEPENDENCY'])
def test_exact_existing_tool_dispatch(monkeypatch,kind,relation):
 raw=choice(kind,relation);inv,data,actions,validated,payloads=fixture(monkeypatch,raw)
 out=dp.choose_read(inv,data,actions,'p')
 assert out['next_action']==('RESEARCH' if kind=='SEARCH' else 'FOLLOW_CONNECTION')
 assert out['targets']==[raw['target']] and out['expected_state_version']==9
 assert out['exploration']==[{**{k:raw[k] for k in ('target','issue_id','missing_need','relation','source_ref')},'request_quote':'사용자의 업무 질문','source_quote':''}]
 assert out['queries']==raw.get('queries',[]) and len(validated)==1
 assert payloads[0]['previous_searches']==[['기존 검색']]
 assert out['basis_refs']==[] # Reading/exploring is not adoption.

@pytest.mark.parametrize('change',[{'target':'T3'},{'target':'UNKNOWN'},{'issue_id':'UNKNOWN'},{'queries':[]},{'queries':['a','b','c']},{'relation':'DEPENDENCY','source_ref':None},{'relation':'DEPENDENCY','source_ref':'UNKNOWN'}])
def test_invalid_exploration_not_executed(monkeypatch,change):
 raw={**choice(),**change};inv,data,actions,validated,payloads=fixture(monkeypatch,raw)
 with pytest.raises((ValidationError,ProposalError)):dp.choose_read(inv,data,actions,'p')
 assert validated==[]

def test_missing_original_cannot_authorize_dependency(monkeypatch):
 inv,data,actions,validated,payloads=fixture(monkeypatch,choice('CONNECT','DEPENDENCY'),original=False)
 with pytest.raises((ValidationError,ProposalError)):dp.choose_read(inv,data,actions,'p')

def test_budget_cap_prevents_additional_calls(monkeypatch):
 inv,data,actions,validated,payloads=fixture(monkeypatch,choice())
 inv.s.repo.budget=lambda:dict(model_limit=40,model_reserved=35,finalization_reserve=3)
 assert dp.choose_read(inv,data,actions,'p') is None and not payloads

def test_resume_key_binds_tool_identity(monkeypatch):
 inv,data,actions,validated,payloads=fixture(monkeypatch,choice())
 dp.choose_read(inv,data,actions,'p');first=list(inv.p['read_choice_reviews'])
 actions['T2']['identity']={'new_query_scope':'changed'}
 dp.choose_read(inv,data,actions,'p')
 assert len(inv.p['read_choice_reviews'])==2 and first[0] in inv.p['read_choice_reviews']
