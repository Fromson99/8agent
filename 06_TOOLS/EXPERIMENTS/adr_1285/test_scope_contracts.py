from copy import deepcopy
from decimal import Decimal
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import assessment_links as links, scenario_application as app, scenario_review as scenario, requirement_coverage as rc
from semantic_runtime.legal_agent.scenario_facts import typed_value
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from semantic_runtime.legal_agent.minimal_output import Projection
from fixtures import share


def literal(value):return {'type':'money','unit':'KRW','value':str(value)}
def context(kind='RULE'):
 c={'schema_version':'scenario-context-v3','kind':kind,'changes':{'limit':literal(2450000)},
  'typed_inputs':{'limit':literal(2450000),'cost':literal(1380000)},
  'changed_fields':{'limit':{'before':literal(1000000),'after':literal(2450000)}},
  'evaluations':[{'package_sha256':'p','node_id':'N1','input_fields':['limit','cost'],'result':{'status':'TRUE'}},
                 {'package_sha256':'p','node_id':'N2','input_fields':['approval'],'result':{'status':'UNKNOWN','missing':['approval']}}],
  'unresolved':[],'superseded_facts':[]}
 c['content_sha256']=digest(c);return c

def value(c,text='가정 금액 조건을 검토했으며 승인은 아직 미확인이다.',comparison=False):
 v={'claims':[{'claim_id':'C1','explanation':text,'rule':None}],
  'scenario_review':{'version':app.VERSION,'context_hash':c['content_sha256'],'condition_results':scenario.results(c),'outcome':'UNCONFIRMED',
  'application_links':[{'claim_id':'C1','condition_ids':['scenario-condition:1'],
   'applied_value_refs':['scenario-value:1:current'],'comparison_value_refs':['scenario-value:1:before'] if comparison else []}]}}
 return v

@pytest.mark.parametrize('text',['245만 원','245만원','2,450,000원','2450000 KRW','0.0245억 원','2450천원','+245만 원'])
def test_equivalent_money_is_exact(text):
 assert Decimal(typed_value(text,{'type':'money','unit':'KRW'},written_units=True)['value'])==Decimal(2450000)
 c=context();v=value(c,'가정 한도 '+text+'을 적용하고 승인 여부는 미확인이다.')
 assert scenario.check(v,c,[])['version']==app.VERSION

@pytest.mark.parametrize('text,expected',[('-0.5만원','-5000.0'),('0만 원','0'),('1.00000000000000000000000000001만 원','10000.0000000000000000000000001')])
def test_magnitude_sign_precision_without_rounding(text,expected):
 assert Decimal(typed_value(text,{'type':'money','unit':'KRW'},written_units=True)['value'])==Decimal(expected)

@pytest.mark.parametrize('text',['2,45만원','245만달러','2.45.0만원','약245만원','245만 원 추가','245만원 이하'])
def test_only_exact_written_amounts_bind_facts(text):
 assert typed_value(text,{'type':'money','unit':'KRW'},written_units=True) is None


def test_explicit_comparison_preserves_both_values_and_legacy_unchanged():
 c=context();text='변경 전 100만 원과 가정 한도 245만 원을 비교하면 비용138만원은 가정 조건을 충족한다. 승인은 미확인이다.'
 v=value(c,'가정 한도245만 원을 적용하며 승인은 미확인이다.',True);v['scenario_review']['application_links'][0]['comparison_text']=text
 before=deepcopy(v);receipt=scenario.check(v,c,[])
 assert v==before
 display=app.display(receipt,c);assert '2450000원' in display[0]['text'] and '1000000원' in display[0]['text']
 saved={'claims':v['claims'],'model_proposal':{'scenario_review':receipt},'scenario_application_display':display,'assessment_basis':{'scenario_application_version':app.VERSION}}
 scenario.verify_saved(saved,c,[])
 for fault in ('display','receipt','current','old_not_compared','unit_scale'):
  changed=deepcopy(saved)
  if fault=='display':changed['scenario_application_display'][0]['text']='승인 완료'
  elif fault=='receipt':changed['model_proposal']['scenario_review'].pop('version')
  elif fault=='current':changed['model_proposal']['scenario_review']['application_links'][0]['applied_value_refs']=['scenario-value:1:before']
  elif fault=='old_not_compared':changed['model_proposal']['scenario_review']['application_links'][0]['comparison_value_refs']=[]
  elif fault=='unit_scale':changed['claims'][0]['explanation']='가정 한도245원 적용'
  with pytest.raises((ContractError,ProposalError)):scenario.verify_saved(changed,c,[])


def test_no_need_to_rewrite_numeric_values_and_no_condition_constants_on_wire():
 c=context();schema=scenario.attach({'type':'object','properties':{},'required':[],'additionalProperties':False},c,typed=True)
 p=Projection(schema);assert 'condition_results' not in p.wire['properties']['scenario_review']['properties']
 v=value(c);v.pop('claims');v['scenario_review'].pop('condition_results');v['scenario_review'].pop('context_hash');v['scenario_review'].pop('version')
 expanded=p.expand(v);expanded['claims']=value(c)['claims']
 scenario.check(expanded,c,[])
 assert '2450000원' in app.display(expanded['scenario_review'],c)[0]['text']

@pytest.mark.parametrize('fault',['missing','foreign_claim','duplicate','old_current','current_as_history','other_field','old_prose','false_outcome','unknown_approval','foreign_branch'])
def test_typed_application_failures_remain_visible(fault):
 c=context();v=value(c);row=v['scenario_review']['application_links'][0]
 if fault=='missing':row['applied_value_refs']=[]
 if fault=='foreign_claim':row['claim_id']='C9'
 if fault=='duplicate':v['scenario_review']['application_links'].append(deepcopy(row))
 if fault=='old_current':row['applied_value_refs']=['scenario-value:1:before']
 if fault=='current_as_history':row['comparison_value_refs']=['scenario-value:1:current']
 if fault=='other_field':row['condition_ids']=['scenario-condition:2']
 if fault=='old_prose':v['claims'][0]['explanation']='현재 한도100만원을 적용한다.'
 if fault=='false_outcome':v['scenario_review']['outcome']='CONDITION_NOT_MET'
 if fault=='unknown_approval':v['scenario_review']['outcome']='CONDITIONS_MET'
 if fault=='foreign_branch':v['scenario_review']['context_hash']='other'
 with pytest.raises(ProposalError):scenario.check(v,c,[])


def review_case():
 options=[{'id':'S1','source_id':'s1','text':'승인 필요'},{'id':'S2','source_id':'s2','text':'금액 요건'}]
 ctx=rc.context('금액과 승인을 검토해 주세요.',[{'id':'Q1','question':'금액과 승인'}],options)
 row={'request_refs':['R1'],'issue_refs':['Q1'],'requirement':'금액 검토','reason':'금액 부분을 설명함',
      'status':'SATISFIED','basis_refs':['S2'],'claim_refs':['C1'],'gap_indices':[],'scope_quote':''}
 gap={'issue_id':'Q1','material':True,'kind':'MISSING_FACT','reason':'아직 승인 확인이 안 됨. '*70+'끝의 예외를 보존한다.'}
 unresolved={**row,'requirement':'승인 검토','status':'UNRESOLVED','claim_refs':[],'basis_refs':[],'gap_indices':[1],'reason':'미확인 승인 gap 참조'}
 value={'claims':[{'claim_id':'C1','issue_refs':['Q1'],'evidence_refs':['S2']}],'gaps':[gap],rc.FIELD:[row,unresolved],
  'read_judgment_review':{'judgments':[{'id':'J1','disposition':'USE','reason':'원문 판단 채택','claim_refs':['C1'],'basis_refs':['S2']}],
  'needs':[{'id':'N1','status':'RESOLVED','reason':'금액 필요 충족','claim_refs':['C1'],'basis_refs':['S2']}],
  'scope_reviews':[{'target_id':'T1','groups':[{'disposition':'USE','reason':'범위의 실제 채택','claim_refs':['C1'],'basis_refs':['S2']}]}]}}
 pair={'type':'object','properties':{'id':{'type':'string'},'claim_refs':{'type':'array','items':{'type':'string'}},'basis_refs':{'type':'array','items':{'enum':['S1','S2']}}},'required':['claim_refs','basis_refs']}
 schema={'type':'object','properties':{'claims':{'type':'array'},'gaps':{'type':'array'},'read_judgment_review':{'type':'object','properties':{
  'judgments':{'type':'array','items':deepcopy(pair)},'needs':{'type':'array','items':deepcopy(pair)},
  'scope_reviews':{'type':'array','items':{'type':'object','properties':{'groups':{'type':'array','items':deepcopy(pair)}}}}}}},'required':['claims','gaps','read_judgment_review']}
 return value,links.attach(rc.attach(schema,ctx,options),options),ctx,options


def test_one_relationship_used_by_four_reviews_and_original_validators():
 value,schema,ctx,options=review_case();raw=share(value);before=deepcopy(raw);wire,expand=links.projection(schema)
 expanded=expand(raw);assert raw==before
 assert {k:v for k,v in expanded.items() if k!=links.FIELD}==value
 assert len(raw['review_links'])==1
 assert sum(b['link_id']=='review-link:1' for b in expanded[links.FIELD]['bindings'])==4
 rc.validate_review(expanded,ctx,options)
 saved={'claims':expanded['claims'],'gaps':expanded['gaps'],links.FIELD:expanded[links.FIELD],
        'read_judgment_review':{'review':expanded['read_judgment_review']}}
 rc.retain(saved,expanded,ctx,options);links.verify_saved(saved)
 saved['read_judgment_review']['review']['judgments'][0]['basis_refs']=['S1']
 with pytest.raises(ContractError):links.verify_saved(saved)
 assert expanded['gaps'][0]['reason'].endswith('끝의 예외를 보존한다.')

@pytest.mark.parametrize('fault',['missing','duplicate','unknown','unused','foreign_evidence','foreign_claim','wrong_evidence','cross_issue','mixed_old_fields'])
def test_shared_links_do_not_infer_or_relax_review(fault):
 value,schema,ctx,options=review_case();wire,expand=links.projection(schema);raw=share(value)
 if fault=='missing':raw.pop('review_links')
 if fault=='duplicate':raw['review_links'].append(deepcopy(raw['review_links'][0]))
 if fault=='unknown':raw['requirement_review'][0]['link_ref']='review-link:99'
 if fault=='unused':raw['review_links'].append({'id':'review-link:99','claim_refs':[],'basis_refs':[]})
 if fault=='foreign_evidence':raw['review_links'][0]['basis_refs']=['S999']
 if fault=='foreign_claim':raw['review_links'][0]['claim_refs']=['C99']
 if fault=='wrong_evidence':raw['review_links'][0]['basis_refs']=['S1']
 if fault=='cross_issue':raw['claims'][0]['issue_refs']=['Q2']
 if fault=='mixed_old_fields':raw['requirement_review'][0]['basis_refs']=['S1']
 from jsonschema import ValidationError
 with pytest.raises((ProposalError,ValidationError)):
  expanded=expand(raw);rc.validate_review(expanded,ctx,options)


def test_new_link_identity_cannot_alias_a_source_locator():
 from semantic_runtime.legal_agent.navigation_input import NavigationReferences
 ref=NavigationReferences({'locator_id':'L'+'a'*32})
 assert ref.forward['L'+'a'*32]=='L1'
 value,schema,ctx,options=review_case();wire=share(value)
 assert ref.restore(wire)==wire
 _,expand=links.projection(schema);rc.validate_review(expand(ref.restore(wire)),ctx,options)


def test_empty_claim_review_receipt_required_but_failed_review_stays_incomplete():
 saved={'claims':[],'assessment_basis':{'review_links_version':links.VERSION}}
 with pytest.raises(ContractError):links.verify_saved(saved)
 saved['model_proposal']={'review_status':'INCOMPLETE'}
 links.verify_saved(saved)


@pytest.mark.parametrize('text',['한도2,45만 원을 적용한다.','비용245.0.0원이다.','비용-245만 원이다.'])
def test_malformed_or_wrong_signed_amount_cannot_hide_in_prose(text):
 c=context()
 with pytest.raises(ProposalError):scenario.check(value(c,text),c,[])


def test_bound_computed_value_can_be_explained_without_new_input_field():
 c=context();c['evaluations'][0]['result']={'status':'VALUE','value':literal(1070000)}
 c['content_sha256']=digest(c)
 v=value(c,'서버가 계산한 차액은107만원이다. 승인은 미확인이다.')
 scenario.check(v,c,[])


def test_false_condition_and_unconfirmed_conclusion_remain_separate():
 c=context();c['evaluations'][0]['result']={'status':'FALSE'};c['content_sha256']=digest(c)
 v=value(c);v['scenario_review']['outcome']='CONDITION_NOT_MET'
 scenario.check(v,c,[])
 v['scenario_review']['outcome']='CONDITIONS_MET'
 with pytest.raises(ProposalError):scenario.check(v,c,[])



def test_repair_receives_exact_shared_vocabulary_and_original_bad_link():
 value,schema,ctx,options=review_case();raw=share(value);_,expand=links.projection(schema)
 expanded=expand(raw);before=deepcopy(expanded)
 assert links.repair_proposal(expanded)==raw and expanded==before
 raw['requirement_review'][0]['link_ref']='review-link:999'
 with pytest.raises(ProposalError) as caught:expand(raw)
 assert caught.value.proposal==raw
 assert links.repair_proposal(caught.value.proposal)==raw


def test_unchanged_explanations_need_no_scenario_links_but_changed_condition_does():
 c=context();v=value(c)
 v['claims'] += [{'claim_id':'C2','explanation':'일반 작업이므로 긴급 예외는 적용되지 않는다.'},
                 {'claim_id':'C3','explanation':'서면 승인 여부는 미확인이다.'}]
 original=deepcopy(v);scenario.check(v,c,[]);assert v==original
 v['scenario_review']['application_links']=[]
 with pytest.raises(ProposalError) as caught:scenario.check(v,c,[])
 assert any(x['code']=='SCENARIO_APPLICATION_COVERAGE' for x in caught.value.issues)


@pytest.mark.parametrize('linked',[True,False])
def test_historical_reference_does_not_authorize_old_current_prose(linked):
 c=context();v=value(c,'현재 비용138만 원은 한도100만 원을 초과하므로 금액 요건은 불충족이다.',True)
 if not linked:
  v['claims'].append({'claim_id':'C2','explanation':v['claims'][0]['explanation']})
  v['claims'][0]['explanation']='현재 가정의 금액 조건을 적용했다.'
 with pytest.raises(ProposalError) as caught:scenario.check(v,c,[])
 assert any(x['code']=='SCENARIO_SUPERSEDED_RULE' for x in caught.value.issues)


def test_full_comparison_is_separate_and_never_sliced_or_used_as_current():
 c=context();v=value(c,'현재 비용138만 원은 가정 한도245만 원 이하이며 승인은 미확인이다.',True)
 text='변경 전 한도100만 원과 가정 한도245만 원을 비교한다. '+'비교의 전체 이유와 예외를 보존한다. '*60+'마지막 단서는 현재 승인 미확인을 유지한다.'
 v['scenario_review']['application_links'][0]['comparison_text']=text
 original=deepcopy(v);receipt=scenario.check(v,c,[])
 assert v==original and app.display(receipt,c)[0]['text'].endswith(text)
 v['scenario_review']['application_links'][0]['comparison_value_refs']=[]
 with pytest.raises(ProposalError):scenario.check(v,c,[])


def test_v2_saved_receipt_keeps_reader_and_v3_cannot_downgrade():
 c=context();v=value(c,'변경 전100만 원과 현재245만 원을 비교한다.',True)
 v['scenario_review']['version']=app.LEGACY_VERSION
 receipt=scenario.check(v,c,[])
 saved={'claims':v['claims'],'model_proposal':{'scenario_review':receipt},
        'scenario_application_display':app.display(receipt,c),
        'assessment_basis':{'scenario_application_version':app.LEGACY_VERSION}}
 scenario.verify_saved(saved,c,[])
 saved['assessment_basis']['scenario_application_version']=app.VERSION
 with pytest.raises(ContractError):scenario.verify_saved(saved,c,[])


def test_nonadopting_row_has_server_empty_claims_without_shared_claim_link():
 from semantic_runtime.legal_agent.minimal_output import Projection
 from semantic_runtime.legal_agent.output_contract import validate_shape
 v,schema,ctx,options=review_case();wire,expand=links.projection(schema)
 raw=share(v);unresolved=raw['requirement_review'][1]
 assert 'link_ref' not in unresolved and 'claim_refs' not in unresolved
 p=Projection(wire);provider=p.project(raw)
 validate_shape(provider,p.wire)
 restored=p.expand(provider);expanded=expand(restored)
 assert expanded['requirement_review'][1]==v['requirement_review'][1]
 rc.validate_review(expanded,ctx,options)
 wrong=deepcopy(provider);wrong['requirement_review'][1]['link_ref']='review-link:1'
 with pytest.raises(ProposalError):validate_shape(wrong,p.wire)


def test_shared_cardinality_error_points_to_visible_link_and_definition():
 v,schema,ctx,options=review_case();wire,expand=links.projection(schema);raw=share(v)
 raw['review_links'][0]['claim_refs']=[]
 with pytest.raises(ProposalError) as caught:expand(raw)
 issues=caught.value.issues
 assert any(x['path']=='/requirement_review/0/link_ref' and x['related_paths']==['/review_links/0/claim_refs'] for x in issues)
 assert caught.value.proposal==raw


@pytest.mark.parametrize('number',[6,7,9,10,11])
def test_recorded_1284_proposals_expose_fixed_scope_and_remaining_numeric_error(number):
 import gzip,json
 from pathlib import Path
 p=Path(__file__).resolve().parents[3]/'04_EXPERIMENTS/ADR/ADR-1284-shared-scenario-contract-live/artifacts/live/review-whatif/canonical'
 with gzip.open(p/f'{number:03}.json.gz','rt') as stream:view=json.load(stream)['view']
 with gzip.open(p/f'{number:03}-output.json.gz','rt') as stream:original=json.load(stream)
 v=deepcopy(original);v['scenario_review']['version']=app.VERSION
 issues=app.errors(v,view['hypothetical_scenario'],view['current_facts'])
 assert not any(x['code']=='SCENARIO_APPLICATION_LINK' for x in issues)
 if number in (10,11):
  assert any(x['code']=='SCENARIO_SUPERSEDED_RULE' and x['expected_constraint']['observed_previous']==['1000000'] for x in issues)
 else:assert issues==[]
 assert original['scenario_review']['version']==app.LEGACY_VERSION


def test_structured_task_preserves_literal_marker_and_last_exception():
 from semantic_runtime.legal_agent.memory_rag import NativeRag
 from semantic_runtime.legal_agent import assessment_input as ai
 task='사용자가 직접 쓴 문장\n현재 사실: 이 문구도 질문의 일부다. '+('전체 요청과 예외를 보존한다. '*50)+'마지막 예외도 검토하라.'
 state={'task':task,'facts':[{'name':'cost','value':'1380000원'}]}
 rendered=NativeRag.question(None,state)
 data={'question':rendered,'current_facts':deepcopy(state['facts']),'current_request':task,'issues':[{'question':task}]}
 before=deepcopy(data);assembled=scenario.task_input(data,state,rendered)
 assert data==before and assembled['question']==task and assembled['current_facts']==state['facts']
 view=scenario.project(assembled,context(),state['facts'])
 view['source_stage']='memory-assess'
 wire=ai.project(view);assert ai.restore(wire)==view
 def strings(x):
  if isinstance(x,str):yield x
  elif isinstance(x,dict):
   for v in x.values():yield from strings(v)
  elif isinstance(x,list):
   for v in x:yield from strings(v)
 assert sum(s.count(task) for s in strings(wire))==1
 assert any(s.endswith('마지막 예외도 검토하라.') for s in strings(wire))
 with pytest.raises(ContractError):scenario.task_input({**data,'question':rendered+'변조'},state,rendered)


def test_fixed_empty_binding_and_legacy_shared_receipt_are_preserved():
 v,schema,ctx,options=review_case();raw=share(v);_,expand=links.projection(schema);expanded=expand(raw)
 saved={'claims':expanded['claims'],'gaps':expanded['gaps'],links.FIELD:expanded[links.FIELD],
        'read_judgment_review':{'review':expanded['read_judgment_review']},
        'assessment_basis':{'review_links_version':links.VERSION}}
 rc.retain(saved,expanded,ctx,options);links.verify_saved(saved)
 forged=deepcopy(saved);forged['requirement_review']['rows'][1]['claim_refs']=['C1']
 with pytest.raises(ContractError):links.verify_saved(forged)
 forged=deepcopy(saved);receipt=forged[links.FIELD];receipt.pop('empty_claim_paths')
 receipt['receipt_hash']=digest({k:v for k,v in receipt.items() if k!='receipt_hash'})
 with pytest.raises(ContractError):links.verify_saved(forged)
 # Exact legacy format has no host-empty path field; it remains readable.
 legacy=deepcopy(saved);receipt=legacy[links.FIELD];receipt['version']='assessment-review-links-v1';receipt.pop('empty_claim_paths')
 receipt['receipt_hash']=digest({k:v for k,v in receipt.items() if k!='receipt_hash'})
 legacy['assessment_basis']['review_links_version']='assessment-review-links-v1'
 links.verify_saved(legacy)
 legacy['assessment_basis']['review_links_version']=links.VERSION
 with pytest.raises(ContractError):links.verify_saved(legacy)
