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

def test_flat_conditions_restore_exact_semantics():
 nodes=[{'mode':'LEAF','text':'A','evidence_refs':['S1']},{'mode':'LEAF','text':'B','evidence_refs':['S2']},{'mode':'ANY','children':[0,1]},{'mode':'LEAF','text':'C','evidence_refs':['S3']},{'mode':'ALL','children':[2,3]}]
 old=deepcopy(nodes);out=ce.restore_condition(nodes)
 assert out=={'mode':'ALL','children':[{'mode':'ANY','children':[nodes[0],nodes[1]]},nodes[3]]}
 assert nodes==old

@pytest.mark.parametrize('nodes',[
 [{'mode':'ALL','children':[0]}],
 [{'mode':'LEAF','text':'A','evidence_refs':['S1']},{'mode':'ALL','children':[0,0]}],
 [{'mode':'LEAF','text':'A','evidence_refs':['S1']},{'mode':'LEAF','text':'unused','evidence_refs':['S1']}],
 [{'mode':'LEAF','text':'A','evidence_refs':['S1']}]+[{'mode':'ALL','children':[i]} for i in range(4)]])
def test_bad_condition_graph_rejected(nodes):
 with pytest.raises(ProposalError):ce.restore_condition(nodes)

@pytest.mark.parametrize('mode',['ALL','ANY','UNKNOWN'])
def test_wire_restores_v8_and_empty_general_facts(mode):
 from jsonschema import validate
 options=[{'id':'S1','source_id':'source','text':'원문'}];schema=v8.assessment_schema([{'id':'Q1'}],[],options,[{'id':'U0','text':'질문'}]);wire,expand=ce.assessment_projection(schema)
 claim={'claim_id':'C1','issue_refs':['Q1'],'evidence_refs':['S1'],'content_contract':v8.CONTENT,'explanation':'','rule':{'kind':'GENERAL_RULE','subject':'주체','action':'행위','scope':'범위','fact_refs':[],'condition_tree':[{'mode':'LEAF','text':'조건','evidence_refs':['S1']},{'mode':mode,'children':[0]}],'norms':[{'kind':'OBLIGATION','text':'원문 효과','evidence_refs':['S1'],'source_ref':'S1'}],'exceptions':[]}}
 raw={'claims':[claim],'issue_assessments':[{'issue_id':'Q1','status':'COVERED'}],'gaps':[]}
 value=expand(raw);validate(value,schema);assert value['claims'][0]['rule']['condition_tree']['mode']==mode
 raw['claims'][0]['rule']['fact_refs']=[{'id':'U0','quote':'질문'}]
 with pytest.raises((ValidationError,ce.output.OutputContractError)):expand(raw)

def retention_fixture(status='READ',scope=True,text='본문'):
 from semantic_runtime.contracts import digest
 offer={};page={'id':'E1','branch_id':'B1','source_id':'S1','document_id':'D1','text':text,'spans':[{'block_id':'1','start_cp':0,'end_cp':len(text),'text':text}], 'page':1,'total_pages':1,'scope_id':digest(offer)}
 state={'requested_originals':['B1'],'basis_history':{'E1':{**page,'accepted':True}},'groups':{'B1':{'status':status,'page_plan':[[]]}},'selected':{'B1':{'source_id':'S1','document_id':'D1','offer':offer}}}
 session=SimpleNamespace(scope={'D1'} if scope else set(),store=SimpleNamespace(source=lambda *a:{'text':text}),profile={'max_read_chars':4,'max_context_chars':100})
 inv=SimpleNamespace(p=state,s=session,render_page=lambda *a:deepcopy(page));return inv,{'sources':[],'basis':[]}

def test_retained_original_exact_and_idempotent():
 inv,data=retention_fixture();assert dp.retain_requested(inv,data)==['E1'];assert data['sources'][0]['text']=='본문'
 assert dp.retain_requested(inv,data)==[] and len(data['basis'])==1
 assert dp.requested_refs(inv.p)==['E1']

@pytest.mark.parametrize('status',['DEFERRED','EXCLUDED'])
def test_excluded_original_not_revived(status):
 inv,data=retention_fixture(status);assert dp.retain_requested(inv,data)==[] and not dp.requested_refs(inv.p)

def test_retention_acl_and_whole_page_budget():
 from semantic_runtime.legal_agent.errors import ContractError
 inv,data=retention_fixture(scope=False)
 with pytest.raises(ContractError):dp.retain_requested(inv,data)
 inv,data=retention_fixture(text='긴본문'*30);assert dp.retain_requested(inv,data)==[]
 assert data['retained_original_context']['omitted_by_context_budget']==['E1'] and data['sources']==[]
