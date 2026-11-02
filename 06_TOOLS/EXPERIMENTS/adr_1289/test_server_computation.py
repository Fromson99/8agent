"""Offline recorded inputs and adversarial contracts; no model quality claim."""
from copy import deepcopy
from pathlib import Path
import gzip,json
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import scenario_computation as calc, scenario_review as review, scenario_application as app
from semantic_runtime.legal_agent import completion_contracts as contracts
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
from semantic_runtime.legal_agent.minimal_output import Projection
from semantic_runtime.ontology_work.evaluation_plan import run

ROOT=Path(__file__).resolve().parents[3]
LIVE=ROOT/'04_EXPERIMENTS/ADR/ADR-1286-scenario-scope-contract-live/artifacts/live/review-whatif'
def read(name):
 with gzip.open(LIVE/name,'rt') as f:return json.load(f)
def seal(c):
 c['content_sha256']=digest({k:v for k,v in c.items() if k!='content_sha256'});return c
def context(cell=4):
 c=read('canonical/%03d.json.gz'%cell)['view']['hypothetical_scenario']
 for k in ('expected_condition_results','application_conditions','application_values'):c.pop(k)
 assert c['content_sha256']==digest({k:v for k,v in c.items() if k!='content_sha256'})
 c['schema_version']='scenario-context-v4'
 c['calculation_catalog']=calc.catalog(read('initial-response.json.gz')['body']['assembly']['term_agent']['review_explanation'])
 return seal(c)
def proposal(c,text='서면 승인과 예외 여부는 별도로 확인해야 합니다.'):
 return {'claims':[{'claim_id':'C1','explanation':text,'rule':None}], 'scenario_review':{
  'version':app.SERVER_VERSION,'context_hash':c['content_sha256'],'condition_results':review.results(c),'outcome':'UNCONFIRMED'}}
def gap_schema():
 schema=contracts.assessment_schema([{'id':'Q1'},{'id':'Q2'}],[],[],contract=contracts.V1)
 return {'type':'object','properties':{'gaps':schema['properties']['gaps']},'required':['gaps'],'additionalProperties':False}
def gap(reason):
 return {'kind':'MISSING_FACT','material':True,'reason':reason,'issue_id':'Q1','material_id':None,'missing_target':'','suggested_action':'REQUEST_FACT'}

@pytest.mark.parametrize('cell,amount,status',[(4,'735000','TRUE'),(5,'1725000','FALSE'),(7,'2450000','TRUE')])
def test_recorded_current_comparison_approval_and_unregistered_effect(cell,amount,status):
 c=context(cell);before=deepcopy(c);r=calc.build(c)
 assert c==before and amount in [x['value']['value'] for x in r['inputs'] if x['value']]
 assert [(p['node_id'],p['current']['status']) for p in r['predicates']]==[('N2',status),('N3','UNKNOWN')]
 assert r['missing_fields']==['approved'] and r['unresolved_effects'][0]['node_id']=='N1'
 assert not r['legal_conclusion_confirmed'] and r['changes'][0]['before']!=r['changes'][0]['current']
 text=calc.render(r);assert amount+'원' in text and '최종 허용 판단은 별도' in text
 assert '담당자 서면 승인 미확인' in text

@pytest.mark.parametrize('fault',['hash','plan_hash','plan_approval','plan_specs','drop_plan','duplicate_plan','input','unregistered_input','change','change_type','drop_change','predicate_status','predicate_missing','predicate_binding','predicate_fields','duplicate_predicate','drop_predicate'])
def test_context_authority_and_evaluation_tamper_rejected(fault):
 c=context();plan=c['calculation_catalog']['plans'][0]['plan']
 if fault=='hash':c['content_sha256']='bad'
 elif fault=='plan_hash':plan['plan_hash']='bad'
 elif fault=='plan_approval':plan['approval_ref']=''
 elif fault=='plan_specs':c['calculation_catalog']['fields']['cost']['concept']='different'
 elif fault=='drop_plan':c['calculation_catalog']['plans']=[]
 elif fault=='duplicate_plan':c['calculation_catalog']['plans']*=2
 elif fault=='input':c['typed_inputs']['limit']['value']='999'
 elif fault=='unregistered_input':c['typed_inputs']['foreign']=c['typed_inputs']['cost']
 elif fault=='change':c['changed_fields']['cost']['after']['value']='1'
 elif fault=='change_type':c['changed_fields']['cost']['field']['unit']='USD'
 elif fault=='drop_change':c['changed_fields']={}
 elif fault=='predicate_status':c['evaluations'][0]['result']['status']='FALSE'
 elif fault=='predicate_missing':c['evaluations'][1]['result']['missing']=[]
 elif fault=='predicate_binding':c['evaluations'][0]['result']['binding']='foreign'
 elif fault=='predicate_fields':c['evaluations'][0]['input_fields']=[]
 elif fault=='duplicate_predicate':c['evaluations']*=2
 elif fault=='drop_predicate':c['evaluations'].pop()
 if fault!='hash':seal(c)
 with pytest.raises(ContractError):calc.build(c)

def test_new_wire_omits_server_values_and_application_links():
 c=context(7);shape=review.attach({'type':'object','properties':{},'required':[],'additionalProperties':False},c,typed=True)
 p=Projection(shape);assert set(p.wire['properties']['scenario_review']['properties'])=={'outcome'}
 expanded=p.expand({'scenario_review':{'outcome':'UNCONFIRMED'}})
 expanded['claims']=proposal(c)['claims'];assert review.check(expanded,c,[])['version']==app.SERVER_VERSION
 assert 'application_links' not in expanded['scenario_review']
 old=deepcopy(c);old.pop('calculation_catalog');seal(old)
 assert review.attach({'properties':{},'required':[]},old,typed=True)['properties']['scenario_review']['properties']['version']['const']==app.VERSION
 with pytest.raises(ContractError):review.check(proposal(old),old,[])

@pytest.mark.parametrize('text',['245만 원','2,450,000원'])
def test_valid_current_money_needs_no_model_link(text):
 c=context(7);review.check(proposal(c,'현재 가정 한도 '+text+'을 적용한다.'),c,[])

@pytest.mark.parametrize('cell,text',[(7,'현재 한도100만원으로 판단한다.'),(5,'현재172.5만원(변경 전138만원)으로 판단한다.')])
def test_stale_rule_rejected_and_known_free_prose_comparison_limit_remains(cell,text):
 c=context(cell)
 with pytest.raises(ProposalError):review.check(proposal(c,text),c,[])

def test_gap_expands_only_selected_option_at_same_index_preserves_full_other_reason():
 c=context();wire,expand=calc.projection(gap_schema(),c);option=calc.gap_options(c)[0]
 long='앞'*594+'끝예외보존!';assert len(long)==600
 raw={'gaps':[gap(long),{'computed_gap_ref':option['computed_gap_ref'],'issue_id':'Q1'},gap('추가 사실 확인')]}
 before=deepcopy(raw);result=expand(raw)
 assert raw==before and result['gaps'][0]==raw['gaps'][0] and result['gaps'][2]==raw['gaps'][2]
 assert result['gaps'][1]==gap(option['reason']) and len(result['gaps'])==3

@pytest.mark.parametrize('fault',['foreign_ref','foreign_issue','duplicate','extra_reason','cross_scenario'])
def test_no_inferred_gap_or_issue_binding(fault):
 c=context();wire,expand=calc.projection(gap_schema(),c);option=calc.gap_options(c)[0]
 row={'computed_gap_ref':option['computed_gap_ref'],'issue_id':'Q1'};raw={'gaps':[row]}
 if fault=='foreign_ref':row['computed_gap_ref']='computed-gap:unknown'
 elif fault=='foreign_issue':row['issue_id']='Q9'
 elif fault=='duplicate':raw['gaps'].append(deepcopy(row))
 elif fault=='extra_reason':row['reason']='승인됨'
 elif fault=='cross_scenario':row['computed_gap_ref']=calc.gap_options(context(7))[0]['computed_gap_ref']
 with pytest.raises(ProposalError) as exc:expand(raw)
 assert exc.value.proposal==raw

def test_explicit_same_missing_input_for_distinct_issues_and_no_auto_add():
 c=context();_,expand=calc.projection(gap_schema(),c);ref=calc.gap_options(c)[0]['computed_gap_ref']
 assert expand({'gaps':[]})=={'gaps':[]}
 value=expand({'gaps':[{'computed_gap_ref':ref,'issue_id':issue} for issue in ('Q2','Q1')]})
 assert [r['issue_id'] for r in value['gaps']]==['Q2','Q1']

def test_long_concept_not_sliced_or_offered_as_invalid_gap():
 c=context();concept='미확인 승인'*150+'끝보존'
 cat=c['calculation_catalog'];cat['fields']['approved']['concept']=concept
 plan=cat['plans'][0]['plan'];plan['spec']['fields']['approved']['concept']=concept
 plan['plan_hash']=digest({k:v for k,v in plan.items() if k!='plan_hash'});seal(c)
 assert calc.gap_options(c)==[] and concept in calc.render(calc.build(c))

@pytest.mark.parametrize('fault',['missing','changed_value','changed_status','changed_unknown','forged_hash'])
@pytest.mark.parametrize('incomplete',[False,True])
def test_saved_receipt_protected_including_source_only_answers(fault,incomplete):
 c=context();p=proposal(c);saved={'claims':p['claims'],'model_proposal':{'scenario_review':p['scenario_review']},
  'assessment_basis':{'scenario_application_version':app.SERVER_VERSION},'scenario_calculation':calc.build(c)}
 if incomplete:saved.update(claims=[],model_proposal={'review_status':'INCOMPLETE'})
 review.verify_saved(saved,c,[])
 if fault=='missing':saved.pop('scenario_calculation')
 else:
  r=saved['scenario_calculation']
  if fault=='changed_value':r['inputs'][1]['value']['value']='1'
  elif fault=='changed_status':r['predicates'][0]['current']['status']='FALSE'
  elif fault=='changed_unknown':r['legal_conclusion_confirmed']=True
  elif fault=='forged_hash':r['content_sha256']='bad'
 with pytest.raises(ContractError):review.verify_saved(saved,c,[])

def test_render_is_independent_of_claims_without_rewriting_prose():
 c=context();r=calc.build(c);text='원문 설명 전체와 마지막 예외를 보존합니다.'
 for claims in ([],[{'claim_id':'C1','text':text}]):
  assessment={'claims':claims,'limitations':[],'scenario_calculation':r}
  shown=contracts.render(assessment,{'claim_order':[x['claim_id'] for x in claims],'layout':'paragraphs'})
  assert calc.render(r) in shown
  if claims:assert text in shown

def test_projection_retains_full_originals_and_current_inputs_without_execution_catalog_copy():
 c=context();source='원문 '*200+'끝의 예외'
 view=review.project({'question':'질문','sources':[{'text':source}]},c,[{'name':'cost','value':'735000원'}])
 assert view['sources'][0]['text']==source
 shown=view['hypothetical_scenario']
 assert shown['typed_inputs']==c['typed_inputs'] and shown['evaluations']==c['evaluations']
 assert not {'calculation_catalog','application_values','application_conditions'}&shown.keys()
 assert view['computed_gap_options']==calc.gap_options(c)
 assert 'calculation_catalog' in c

def test_no_expression_keeps_existing_contract_and_unknown_rule_is_not_a_fact_gap():
 c=context();empty=deepcopy(c)
 empty['calculation_catalog']['plans'][0]['plan']['spec']['rules']=[]
 assert not calc.enabled(empty)
 # Approved absent rule baseline remains UNKNOWN, not a user fact to invent.
 cat=c['calculation_catalog'];cat['fields']['limit']['baseline']=None
 plan=cat['plans'][0]['plan'];plan['spec']['fields']['limit']['baseline']=None
 plan['plan_hash']=digest({k:v for k,v in plan.items() if k!='plan_hash'})
 c['typed_inputs']['limit']=None
 computed=run(plan,c['typed_inputs'],binding=c['evaluations'][0]['result']['binding'])
 for row in c['evaluations']:row['result']=computed[row['node_id']]
 seal(c);r=calc.build(c)
 assert r['predicates'][0]['current']['status']=='UNKNOWN' and r['missing_fields']==['approved']
 assert all(o['field']!='limit' for o in calc.gap_options(c))
 review.check(proposal(c),c,[])
