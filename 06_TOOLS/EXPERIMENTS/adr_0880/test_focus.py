from copy import deepcopy
from types import SimpleNamespace
import pytest
from semantic_runtime.legal_agent import completion_execution as ce, completion_v8 as v8, decision_projection as dp, law_navigation as nav
from semantic_runtime.legal_agent.errors import ProposalError
from jsonschema import ValidationError

def test_assessment_projection():
 schema=v8.assessment_schema([{'id':'Q1'}],[],[],[{'id':'U0','text':'q'}]);wire,expand=ce.assessment_projection(schema)
 assert 'disposition' not in wire['properties'] and 'reason' not in wire['properties']['issue_assessments']['items']['properties']
 raw={'claims':[],'issue_assessments':[{'issue_id':'Q1','status':'INSUFFICIENT'}],'gaps':[{'issue_id':'Q1','kind':'MISSING_SOURCE','reason':'원문 미확보','material':True,'material_id':None,'suggested_action':'RESEARCH'}]}
 out=expand(raw);assert out['gaps']==raw['gaps'] and out['disposition']=='NEEDS_INVESTIGATION' and 'reason' not in raw['issue_assessments'][0]

def fixture(monkeypatch,value,*,original=True,limit=8):
 events=[];view={'sources':[{'id':'E1','text':'주변 원문'}] if original else [],'basis':[{'id':'E1','branch_id':'B1'}] if original else [],'issues':[{'id':'Q1','request_quote':'질문'}],'presentation_id':'P1','laws':[],'branches':[],'read_batch_limit':limit}
 actions={'T1':{'action':'READ_ARTICLES','identity':{'document_id':'D'},'label':'제3조','id':'T1'}}
 repo=SimpleNamespace(budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3),event=lambda *x:events.append(x))
 inv=SimpleNamespace(modern=True,p={'binding':{}},s=SimpleNamespace(repo=repo),save=lambda:None,question='질문',validate=lambda *a:None)
 def decide(*args,**kwargs):args[5](value);return deepcopy(value)
 monkeypatch.setattr(ce.output,'bounded_decision',decide)
 monkeypatch.setattr(nav,'decision_schema',lambda *a:{'anyOf':[{'properties':{'next_action':{'const':kind},'presentation_id':{'enum':['P1']},'targets':{'type':'array'},'basis_refs':{'type':'array'},'exploration':{'type':'array'}}} for kind in ('READ_ARTICLES','FINISH')]})
 return inv,view,actions,events

def test_read_despite_peripheral_original(monkeypatch):
 value={'choice':'READ','selections':[{'target':'T1','issue_id':'Q1','missing_need':'핵심 본문','relation':'DIRECT','source_ref':None}]};inv,v,a,e=fixture(monkeypatch,value)
 out=dp.choose_read(inv,v,a,'p');assert out['next_action']=='READ_ARTICLES' and out['targets']==['T1'] and out['exploration'][0]['request_quote']=='질문'

def test_model_selects_finish(monkeypatch):
 value={'choice':'FINISH','basis_refs':['E1'],'issue_refs':['Q1'],'evidence_sufficient':False,'reason':'추가 조건은 미확인'};inv,v,a,e=fixture(monkeypatch,value)
 out=dp.choose_read(inv,v,a,'p');assert out['next_action']=='FINISH' and out['basis_refs']==['E1'] and not out['evidence_sufficient']

def test_no_finish_without_original(monkeypatch):
 value={'choice':'FINISH','basis_refs':['E1'],'issue_refs':['Q1'],'evidence_sufficient':True,'reason':'완료'};inv,v,a,e=fixture(monkeypatch,value,original=False)
 with pytest.raises(ValidationError):dp.choose_read(inv,v,a,'p')

def test_decline_and_limit(monkeypatch):
 inv,v,a,e=fixture(monkeypatch,{'choice':'EXPLORE','reason':'다른 주체만 다루는 후보'})
 assert dp.choose_read(inv,v,a,'p') is None
 monkeypatch.setattr(ce.output,'bounded_decision',lambda *a,**k:pytest.fail('duplicate model call'))
 assert dp.choose_read(inv,v,a,'p') is None
 inv.p['read_choice_reviews']={str(i):{} for i in range(4)}
 assert dp.choose_read(inv,v,a,'p') is None

@pytest.mark.parametrize('change',[{'target':'UNKNOWN'},{'relation':'DEPENDENCY','source_ref':None},{'relation':'DEPENDENCY','source_ref':'UNKNOWN'}])
def test_provenance_rejected(monkeypatch,change):
 row={'target':'T1','issue_id':'Q1','missing_need':'원문','relation':'DIRECT','source_ref':None};row.update(change)
 inv,v,a,e=fixture(monkeypatch,{'choice':'READ','selections':[row]})
 with pytest.raises((ValidationError,ProposalError)):dp.choose_read(inv,v,a,'p')
