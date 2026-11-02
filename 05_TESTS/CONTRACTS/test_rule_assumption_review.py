"""Regression checks of observed ADR1280 failures; no external model calls."""
from copy import deepcopy
from pathlib import Path
import gzip,json
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import scenario_review as review
from semantic_runtime.legal_agent.scenario_branch import compare
from semantic_runtime.legal_agent.scenario_facts import options
from semantic_runtime.legal_agent.minimal_output import Projection
from semantic_runtime.legal_agent.errors import ProposalError

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def actual():
    p=ROOT/'04_EXPERIMENTS/ADR/ADR-1280-scenario-bound-facts-live/artifacts/live/review-whatif/canonical'
    view=json.loads(gzip.decompress((p/'007.json.gz').read_bytes()))['view']
    output=json.loads(gzip.decompress((p/'007-output.json.gz').read_bytes()))
    catalog=next(c['payload']['assembly_catalog'] for c in view['ontology_bundles'] if c.get('payload',{}).get('assembly_catalog'))
    state={'facts':deepcopy(view['current_facts'])}
    binding={'cost':[r['id'] for r in options(state) if r['value']=='1380000원']}
    explanation={'ontology':{'bundles':[{'assembly':catalog}]},'items':[],'outcome':'INSUFFICIENT','content_sha256':'baseline'}
    c=compare(explanation,state,{'limit':{'type':'money','unit':'KRW','value':'2450000'}},kind='RULE',operation_id='test',bindings=binding)
    context={k:deepcopy(c[k]) for k in ('kind','changes','evaluations','changed_fields','unresolved')}
    context.update(schema_version='scenario-context-v3',superseded_facts=[])
    context['content_sha256']=digest(context)
    return context,state,output,explanation,binding


def canonical(context,claims):
    return {'claims':claims,'scenario_review':{'context_hash':context['content_sha256'],'condition_results':review.results(context),
        'outcome':'UNCONFIRMED','application_links':[{'claim_id':c['claim_id'],'condition_ids':['scenario-condition:1']} for c in claims if c.get('explanation')]}}


def test_host_binds_identity_without_model_hash_and_rejects_foreign_context(actual):
    context,state,_,_,_=actual
    schema=review.attach({'type':'object','additionalProperties':False,'properties':{},'required':[]},context)
    projection=Projection(schema)
    assert 'context_hash' not in projection.wire['properties']['scenario_review']['properties']
    value=canonical(context,[]);value.pop('claims')
    wire=deepcopy(value);wire['scenario_review'].pop('context_hash')
    before=deepcopy(wire)
    expanded=projection.expand(wire)
    assert expanded==value and wire==before
    other=deepcopy(context);other['content_sha256']='different-request'
    with pytest.raises(ProposalError):review.check(expanded,other,state['facts'])
    wire['scenario_review']['context_hash']='foreign'
    with pytest.raises(ProposalError):projection.expand(wire)


def test_archived_rule_proposal_cannot_pass_with_correct_numeric_table(actual):
    context,state,output,_,_=actual
    value=deepcopy(output)
    value['scenario_review']=canonical(context,output['claims'])['scenario_review']
    with pytest.raises(ProposalError) as e:review.check(value,context,state['facts'])
    codes={r['code'] for r in e.value.issues}
    assert 'SCENARIO_SUPERSEDED_RULE' in codes and 'SCENARIO_CHANGED_VALUE_MISSING' in codes
    assert output!=value  # Only test copy enriched; archived original untouched.


def test_rule_application_and_real_source_quote_remain_distinct(actual):
    context,state,_,_,_=actual
    value=canonical(context,[{'claim_id':'C1','rule':{'kind':'GENERAL_RULE','norms':[{'text':'원래 규정은 1000000원 이하를 요구한다.'}]},'explanation':''},
        {'claim_id':'C2','rule':None,'explanation':'가정 한도 2450000원에서 비용 1380000원은 금액 요건을 충족한다. 승인은 미확인이므로 개시 여부는 미확정이다.'}])
    receipt=review.check(value,context,state['facts'])
    saved={'claims':[{'claim_id':c['claim_id'],'answer_content':c} for c in value['claims']], 'model_proposal':{'scenario_review':receipt}}
    review.verify_saved(saved,context,state['facts'])
    saved['claims'][1]['answer_content']['explanation']='현재 한도1000000원으로 비용1380000원은 불충족이다.'
    with pytest.raises(ProposalError):review.verify_saved(saved,context,state['facts'])


@pytest.mark.parametrize('fault',['missing','duplicate','foreign_claim','unchanged_only','missing_value','old_rule'])
def test_claim_links_cannot_hide_changed_rule(actual,fault):
    context,state,_,_,_=actual
    value=canonical(context,[{'claim_id':'C1','rule':None,'explanation':'가정 한도2450000원 이하 금액 조건 충족, 승인 미확인.'}])
    links=value['scenario_review']['application_links']
    if fault=='missing':links.clear()
    if fault=='duplicate':links.append(deepcopy(links[0]))
    if fault=='foreign_claim':links[0]['claim_id']='not-present'
    if fault=='unchanged_only':links[0]['condition_ids']=['scenario-condition:2']
    if fault=='missing_value':value['claims'][0]['explanation']='금액 조건 충족.'
    if fault=='old_rule':value['claims'][0]['explanation']='현재1000000원 이하 조건을 적용한다. 가정값은2450000원.'
    with pytest.raises(ProposalError):review.check(value,context,state['facts'])


@pytest.mark.parametrize('name,before,after',[('ceiling_zeta','937','938'),('allowed_amount','2400000','2900000')])
def test_rule_check_uses_registered_values_not_case_constants(name,before,after):
    lit=lambda x:{'type':'money','unit':'KRW','value':x}
    context={'schema_version':'scenario-context-v3','kind':'RULE','changes':{name:lit(after)},'changed_fields':{name:{'before':lit(before),'after':lit(after)}},
        'evaluations':[{'package_sha256':'p','node_id':'different-node','result':{'status':'TRUE'},'input_fields':[name]}], 'unresolved':[]}
    context['content_sha256']=digest(context)
    good=canonical(context,[{'claim_id':'C1','rule':None,'explanation':f'가정값{after}원으로 판단한다.'}])
    review.check(good,context,[])
    good['claims'][0]['explanation']=f'원래 값{before}원을 적용한다.'
    with pytest.raises(ProposalError):review.check(good,context,[])


def test_actual_low_amount_needs_no_model_hash_copy():
    p=ROOT/'04_EXPERIMENTS/ADR/ADR-1280-scenario-bound-facts-live/artifacts/live/review-whatif/canonical'
    view=json.loads(gzip.decompress((p/'004.json.gz').read_bytes()))['view']
    proposal=json.loads(gzip.decompress((p/'004-output.json.gz').read_bytes()))
    context=view['hypothetical_scenario']
    # View-only decorations do not replace the frozen context identity.
    schema=review.attach({'type':'object','additionalProperties':False,'properties':{},'required':[]},context)
    raw=deepcopy(proposal['scenario_review'])
    assert raw['context_hash']==context['baseline_hash']!=context['content_sha256']
    raw.pop('context_hash')
    expanded=Projection(schema).expand({'scenario_review':raw})
    result={**proposal,**expanded}
    assert review.check(result,context,view['current_facts'])['context_hash']==context['content_sha256']
    assert proposal['scenario_review']['context_hash']==context['baseline_hash']


def test_general_rules_alone_do_not_claim_rule_assumption_coverage(actual):
    context,state,_,_,_=actual
    value=canonical(context,[{'claim_id':'C1','rule':{'kind':'GENERAL_RULE'},'explanation':''}])
    with pytest.raises(ProposalError) as e:review.check(value,context,state['facts'])
    assert 'SCENARIO_APPLICATION_COVERAGE' in {r['code'] for r in e.value.issues}
