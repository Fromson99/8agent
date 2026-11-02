"""Regression of ADR1279 actual proposal, with no external model calls."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import scenario_facts as facts, scenario_review as review
from semantic_runtime.legal_agent.scenario_branch import compare
from semantic_runtime.legal_agent.completion_execution import assessment_fact_sources
from semantic_runtime.legal_agent.errors import ContractError, ProposalError

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def case():
    folder=ROOT/'04_EXPERIMENTS/ADR/ADR-1279-whatif-live-continuation/artifacts/live/review-whatif/canonical'
    original=json.loads(gzip.decompress((folder/'001.json.gz').read_bytes()))['view']
    proposal=json.loads(gzip.decompress((folder/'001-output.json.gz').read_bytes()))
    # This is the original case, before the previously faulty appended assumption.
    state={'facts':deepcopy(original['current_facts'][:-1])}
    catalog=next(c['payload']['assembly_catalog'] for c in original['ontology_bundles'] if c.get('payload',{}).get('assembly_catalog'))
    explanation={'ontology':{'bundles':[{'assembly':catalog}]},'items':[],'outcome':'INSUFFICIENT','content_sha256':'baseline'}
    choices=facts.options(state)
    binding={'cost':[r['id'] for r in choices if r['name']=='작업 비용']}
    change={'cost':{'type':'money','unit':'KRW','value':'500000'}}
    comparison=compare(explanation,state,change,kind='FACT',operation_id='test',bindings=binding)
    current=facts.effective(state,change,comparison['fact_bindings'],'FACT')
    context={'schema_version':'scenario-context-v2','changes':change,'evaluations':comparison['evaluations'],
        'unresolved':comparison['unresolved'],'superseded_facts':[r for r in choices if r['id'] in binding['cost']]}
    context['content_sha256']=digest(context)
    return state,explanation,binding,comparison,current,context,original,proposal


def receipt(context):
    return {'context_hash':context['content_sha256'],'condition_results':review.results(context),'outcome':'UNCONFIRMED'}


def test_archived_alias_is_replaced_and_both_conditions_are_evaluated(case):
    state,explanation,binding,c,current,context,original,_=case
    assert next(r for r in c['comparisons'] if r['node_id']=='N2')['before']['status']=='FALSE'
    assert next(r for r in c['comparisons'] if r['node_id']=='N2')['after']['status']=='TRUE'
    assert {r['node_id']:r['result']['status'] for r in c['evaluations']}=={'N2':'TRUE','N3':'UNKNOWN'}
    assert not c['unbound_changes']
    assert {'name':'작업 비용','value':'1500000원'} in state['facts']
    assert not any('1500000' in f['value'] for f in current)
    assert {'name':'담당자 서면 승인 여부','value':'미확인'} in current
    wire=review.project(original,context,current)
    assert '1500000' not in wire['current_request']
    assert '1500000' in wire['baseline_history']['records']['current_request']
    sources=assessment_fact_sources(original['question'],{'facts':current,'scenario_context':context},modern=True)
    assert all(s['id']!='U0' and '1500000' not in s['text'] for s in sources)
    unbound=compare(explanation,state,c['changes'],kind='FACT',operation_id='unbound')
    assert unbound['unbound_changes']==['cost']
    rule=compare(explanation,state,{'limit':{'type':'money','unit':'KRW','value':'2000000'}},kind='RULE',operation_id='rule',bindings=binding)
    assert next(r for r in rule['comparisons'] if r['node_id']=='N2')['before']['status']=='FALSE' and next(r for r in rule['comparisons'] if r['node_id']=='N2')['after']['status']=='TRUE'
    assert facts.effective(state,rule['changes'],rule['fact_bindings'],'RULE')==state['facts']


def test_actual_wrong_model_proposal_rejected_even_with_correct_receipt(case):
    *_,current,context,original,proposal=case
    proposal['scenario_review']=receipt(context)
    with pytest.raises(ProposalError) as error:review.check(proposal,context,current)
    assert 'SCENARIO_SUPERSEDED_FACT' in str(error.value.issues)


@pytest.mark.parametrize('fault',['missing','stale','shape','condition','duplicate','confirmed','false'])
def test_invalid_final_scenario_contract_is_repairable(case,fault):
    *_,current,context,original,proposal=case
    value={'claims':[],'scenario_review':receipt(context)}
    r=value['scenario_review']
    if fault=='missing':value.pop('scenario_review')
    if fault=='stale':r['context_hash']='old'
    if fault=='shape':r['condition_results']=[None]
    if fault=='condition':r['condition_results'][0]['status']='FALSE'
    if fault=='duplicate':r['condition_results'].append(deepcopy(r['condition_results'][0]))
    if fault=='confirmed':r['outcome']='CONDITIONS_MET'
    if fault=='false':r['outcome']='CONDITION_NOT_MET'
    with pytest.raises(ProposalError):review.check(value,context,current)


def test_valid_unconfirmed_receipt_and_original_quote_preserved(case):
    *_,current,context,original,proposal=case
    value={'claims':[{'explanation':'현재 비용 500000원은 한도 이하지만 서면 승인은 미확인이다.',
                      'rule':{'kind':'GENERAL_RULE','quote':'기존 규정의 예시 금액 1500000원'}}], 'scenario_review':receipt(context)}
    before=deepcopy(value)
    schema=review.attach({'properties':{'claims':{}},'required':['claims']},context)
    core,shape,r=review.core(value,schema,context,current)
    assert 'scenario_review' not in core and r==receipt(context) and value==before
    review.verify_saved({'claims':value['claims'],'model_proposal':{'scenario_review':r}},context,current)
    with pytest.raises(ProposalError):review.verify_saved({'claims':value['claims']},context,current)


@pytest.mark.parametrize('fault',['foreign','duplicate','empty','conflict','same_fact_twice'])
def test_fact_binding_conflicts_are_not_guessed(case,fault):
    state,explanation,binding,*_=case
    fields=deepcopy(explanation['ontology']['bundles'][0]['assembly']['evaluation_plan']['spec']['fields'])
    if fault=='foreign':binding['cost']=['F-other']
    if fault=='duplicate':binding['cost']*=2
    if fault=='empty':state['facts'].append({'name':'cost','value':'1500000'});binding['cost']=[]
    if fault=='conflict':
        state['facts'].append({'name':'작업 비용','value':'3000000원'})
        binding['cost']=[r['id'] for r in facts.options(state) if r['name']=='작업 비용']
    if fault=='same_fact_twice':fields['other']=deepcopy(fields['cost']);binding['other']=binding['cost']
    with pytest.raises(ContractError):facts.bind(state,fields,binding)


def test_literal_parsing_does_not_invent_units_or_boolean():
    money={'type':'money','unit':'KRW'}
    assert facts.typed_value('1,500,000원',money)['value']=='1500000'
    for text in ('150만원','1500000USD','약 1500000원','1,50,000원'):
        assert facts.typed_value(text,money) is None
    assert facts.typed_value('미확인',{'type':'boolean','unit':''}) is None


def test_numeric_comparison_is_not_a_substring_and_handles_decimal_notation():
    assert review.numbers('금액1500000.00원') == review.numbers('1,500,000원')
    assert not review.numbers('21500000원') & review.numbers('1500000원')
    assert not review.numbers(None)
    assert facts.typed_value(None,{'type':'money','unit':'KRW'}) is None
