from copy import deepcopy
from types import SimpleNamespace
import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.legal_agent import decision_projection as dp,law_navigation as nav,output_contract as oc,completion_execution as ce,completion_v8 as v8,investigation_scope as scope
from semantic_runtime.legal_agent.errors import ProposalError

def fixture(monkeypatch,value,*,original=True):
 data={'issues':[{'id':'Q1','request_quote':'질문'}],'sources':[{'id':'E1','text':'원문'}] if original else [],'basis':[{'id':'E1','branch_id':'B1'}] if original else [],'laws':[],'branches':[], 'presentation_id':'P1','state_version':9,'control_contract':'control','completion_contract':nav.cc.V8,'read_batch_limit':8,'investigation_scope':{'request':'질문'}}
 actions={k:{'id':k,'action':kind,'identity':ident,'label':kind} for k,kind,ident in [('T1','READ_ARTICLES',{'document_id':'D1'}),('T2','RESEARCH',{}),('T3','FOLLOW_CONNECTION',{}),('T4','SEARCH_STRUCTURE',{'document_id':'D1'}),('T5','SEARCH_STRUCTURE',{}),('T6','NEXT_ARTICLES',{'document_id':'D1'}),('T7','RETURN_TO',{}),('T8','READ_PARENT',{}),('T9','SEARCH_BODY',{'document_id':'D1'})]}
 payloads=[];out=[]
 def check(v,d,a):validate(v,nav.decision_schema(d,a,set()));scope.validate(v,d);out.append(v)
 inv=SimpleNamespace(modern=True,p={'binding':{}},s=SimpleNamespace(repo=SimpleNamespace(budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3),event=lambda *v:None)),question='질문',save=lambda:None,validate=check)
 def decide(*args,**kwargs):payloads.append(args[2]);args[5](value);return deepcopy(value)
 monkeypatch.setattr(oc,'bounded_decision',decide)
 return inv,data,actions,payloads,out

def choice(kind='RESEARCH',target='T2',**extra):
 return {'choice':kind,'target':target,'issue_id':'Q1','missing_need':'직접 필요한 원문','relation':'DIRECT','source_ref':None,**extra}

@pytest.mark.parametrize('kind,target,extra',[('RESEARCH','T2',{'queries':['주체 행위']}),('FOLLOW_CONNECTION','T3',{}),('LOCATE','T4',{'structure_filter':{'coordinate':'','title':'주체의 의무','coordinate_scope':'body'}}),('CATALOG_SEARCH','T5',{'queries':['실제 문서명']}),('NEXT_ARTICLES','T6',{}),('RETURN_TO','T7',{}),('READ_PARENT','T8',{}),('SEARCH_BODY','T9',{'queries':['의무 조건']})])
def test_each_selected_tool_exact_canonical(monkeypatch,kind,target,extra):
 inv,d,a,p,out=fixture(monkeypatch,choice(kind,target,**extra));v=dp.choose_read(inv,d,a,'p')
 assert v['targets']==[target] and v['next_action']==a[target]['action'] and v['expected_state_version']==9
 assert v['exploration'][0]['request_quote']=='질문' and not v['branch_decisions']
 assert v['queries']==extra.get('queries',[])
 if 'structure_filter'in extra:assert v['structure_filter']==extra['structure_filter']
 assert len(p)==1

@pytest.mark.parametrize('raw',[
 {'choice':'EXPLORE','reason':'추가 탐색'},choice(target='T3',queries=['q']),choice('LOCATE','T4',queries=['법'],structure_filter={'coordinate':'','title':'의무','coordinate_scope':'body'}),choice(queries=[]),choice(queries=['a','b','c']),choice(queries=['q'],relation='DEPENDENCY',source_ref=None),choice(queries=['q'],issue_id='wrong')])
def test_no_ambiguous_or_unbound_dispatch(monkeypatch,raw):
 inv,d,a,p,out=fixture(monkeypatch,raw)
 with pytest.raises((ValidationError,ProposalError)):dp.choose_read(inv,d,a,'p')
 assert not out

def test_pending_without_original(monkeypatch):
 inv,d,a,p,out=fixture(monkeypatch,{'choice':'PENDING','reason':'허용 범위 조사를 마쳤으나 필요한 원문 미확보'},original=False)
 v=dp.choose_read(inv,d,a,'p');assert v['next_action']=='PENDING' and not v['basis_refs']

def test_pending_cannot_discard_delivered_original(monkeypatch):
 inv,d,a,p,out=fixture(monkeypatch,{'choice':'PENDING','reason':'불확실'})
 with pytest.raises(ValidationError):dp.choose_read(inv,d,a,'p')

def test_terminal_finish_requires_original(monkeypatch):
 inv,d,a,p,out=fixture(monkeypatch,{'choice':'FINISH','basis_refs':['E1'],'issue_refs':['Q1'],'reason':'끝','evidence_sufficient':False},original=False)
 with pytest.raises(ValidationError):dp.choose_read(inv,d,a,'p')

def test_bounded_reviews_and_reserve(monkeypatch):
 inv,d,a,p,out=fixture(monkeypatch,choice(queries=['주체 행위']));inv.p['read_choice_reviews']={str(i):{} for i in range(8)}
 assert dp.choose_read(inv,d,a,'p') is None and not p
 inv.p['read_choice_reviews']={};inv.s.repo.budget=lambda:dict(model_limit=40,model_reserved=35,finalization_reserve=3)
 assert dp.choose_read(inv,d,a,'p') is None and not p

@pytest.mark.parametrize('utterance',['분류가 무엇인가?','조건 A일 때의 일반 규칙은?','어떻게 계산하나요?'])
def test_unadmitted_question_not_fact(utterance):
 assert ce.assessment_fact_sources(utterance,{'facts':[]},modern=True)==[]

def test_existing_facts_and_legacy_preserved():
 state={'facts':[{'name':'date','value':'2026-01-01'}]};before=deepcopy(state)
 assert ce.assessment_fact_sources('질문',state,modern=True)==[{'id':'U0','text':'질문'},{'id':'U1','text':'2026-01-01'}]
 assert state==before and ce.assessment_fact_sources('질문',{'facts':[]},modern=False)==[{'id':'U0','text':'질문'}]

def test_no_case_application_without_admitted_facts():
 schema=v8.assessment_schema([{'id':'Q1'}],[],[{'id':'S1','text':'원문'}],[]);wire,expand=ce.assessment_projection(schema)
 def walk(x):
  if isinstance(x,dict):
   if 'properties' in x and 'fact_refs' in x['properties'] and 'anyOf' in x:
    assert [a['properties']['kind']['const'] for a in x['anyOf']]==['GENERAL_RULE']
   for v in x.values():walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(wire)
