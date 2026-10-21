from copy import deepcopy
from types import SimpleNamespace
import pytest
from semantic_runtime.legal_agent import completion_execution as ce, completion_v8 as v8, decision_projection as dp
from semantic_runtime.legal_agent import law_navigation as nav
from semantic_runtime.legal_agent.errors import ProposalError

def test_assessment_owns_status_diagnostics_only():
 schema=v8.assessment_schema([{'id':'Q1'}],[],[],[{'id':'U0','text':'q'}])
 wire,expand=ce.assessment_projection(schema)
 assert 'disposition' not in wire['properties']
 assert 'reason' not in wire['properties']['issue_assessments']['items']['properties']
 raw={'claims':[],'issue_assessments':[{'issue_id':'Q1','status':'INSUFFICIENT'}], 'gaps':[{'issue_id':'Q1','kind':'MISSING_SOURCE','reason':'원문 미확보','material':True,'material_id':None,'missing_target':'제3조','suggested_action':'RESEARCH'}]}
 result=expand(raw)
 assert result['disposition']=='NEEDS_INVESTIGATION' and result['gaps']==raw['gaps'] and 'reason' not in raw['issue_assessments'][0]
 assert 'INSUFFICIENT' in result['issue_assessments'][0]['reason']

def test_no_read_review_with_delivered_originals():
 assert dp.choose_read(SimpleNamespace(modern=True),{'sources':[{'text':'원문'}]}, {},'p') is None

def test_read_choice_cap_and_decline(monkeypatch):
 events=[];view={'sources':[],'issues':[{'id':'Q1','request_quote':'질문'}],'presentation_id':'P1','laws':[],'branches':[]}
 actions={'T1':{'action':'READ_ARTICLES','identity':{'document_id':'D'},'label':'제3조','id':'T1'}}
 repo=SimpleNamespace(budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3),event=lambda *x:events.append(x))
 inv=SimpleNamespace(modern=True,p={'binding':{},'read_choice_reviews':{}},s=SimpleNamespace(repo=repo),save=lambda:None,question='질문')
 monkeypatch.setattr(ce.output,'bounded_decision',lambda *a,**k:{'selections':[],'skip_reason':'다른 주체의 조문이다'})
 assert dp.choose_read(inv,view,actions,'p') is None
 assert list(inv.p['read_choice_reviews'].values())[0]['skipped']
 monkeypatch.setattr(ce.output,'bounded_decision',lambda *a,**k:pytest.fail('same declined menu must not repeat'))
 assert dp.choose_read(inv,view,actions,'p') is None
 inv.p['read_choice_reviews']={str(i):{} for i in range(4)}
 assert dp.choose_read(inv,view,actions,'p') is None

def test_read_choice_uses_exact_action(monkeypatch):
 view={'sources':[],'issues':[{'id':'Q1','request_quote':'질문'}],'presentation_id':'P1','laws':[],'branches':[]}
 actions={'T1':{'action':'READ_ARTICLES','identity':{'document_id':'D'},'label':'제3조','id':'T1'}}
 repo=SimpleNamespace(budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3),event=lambda *x:None)
 inv=SimpleNamespace(modern=True,p={'binding':{}},s=SimpleNamespace(repo=repo),save=lambda:None,question='질문',validate=lambda *a:None)
 monkeypatch.setattr(ce.output,'bounded_decision',lambda *a,**k:{'selections':[{'target':'T1','issue_id':'Q1','missing_need':'요건 본문'}],'skip_reason':''})
 monkeypatch.setattr(nav,'decision_schema',lambda *a:{'anyOf':[{'properties':{'next_action':{'const':'READ_ARTICLES'},'presentation_id':{'enum':['P1']},'targets':{'type':'array'},'exploration':{'type':'array'}}}]})
 result=dp.choose_read(inv,view,actions,'p')
 assert result['targets']==['T1'] and result['exploration'][0]['request_quote']=='질문'
 assert result['next_action']=='READ_ARTICLES' and not result['evidence_sufficient']
