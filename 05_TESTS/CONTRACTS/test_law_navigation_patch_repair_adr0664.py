"""Real partial model output becomes a validated field replacement, not a new answer."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from jsonschema import validate,ValidationError
from test_unit_fulltext_adaptive_read import tree, session
from test_law_grouped_navigation import prepared,reader
from test_law_navigation_one_repair_adr0663 import conflict
from semantic_runtime.legal_agent import law_navigation as ln, bounded_source_session as bs
from semantic_runtime.legal_agent.errors import ProposalError

ROOT=Path('/home/jin/8-AGENT')


def historical():
    p=ROOT/'04_EXPERIMENTS/ADR/ADR-0663-law-navigation-one-repair-probe/artifacts'
    data=json.loads((p/'first-law-navigation-input.json').read_text())
    events=json.loads((p/'retry-audit.json').read_text())
    rejected=next(r['payload']['decision'] for r in events if r['kind']=='LAW_DECISION_REJECTED')
    response=json.loads(next((p/'run-001/provider').glob('call-006-*/response.json')).read_text())
    partial=json.loads(response['choices'][0]['message']['content'])
    return data,rejected,partial


def test_exact_actual_partial_correction_preserves_every_other_field():
    data,rejected,partial=historical();before=copy.deepcopy(rejected)
    gid=rejected['branch_decisions'][0]['branch_id'];handle=rejected['targets'][0]
    actions={r['id']:{**r,'identity':{'branch_id':gid} if r['id']==handle else {}} for r in data['actions']}
    groups={r['id'] for r in data['branches']}
    schema,is_patch=ln.correction_schema(data,actions,groups,rejected)
    assert is_patch and list(partial)==['branch_decisions']
    validate(partial,schema);merged=ln.corrected_decision(rejected,partial,is_patch)
    strong,_=ln.repair_contract(data,actions,groups,rejected,ProposalError('read and defer'))
    validate(merged,strong)
    for key in rejected:
        if key!='branch_decisions':assert merged[key]==rejected[key]
    assert rejected==before and merged['branch_decisions']==partial['branch_decisions']


def test_empty_patch_rejected_and_incomplete_initial_output_needs_full_decision():
    data,rejected,_=historical();groups={r['id'] for r in data['branches']}
    actions={r['id']:{**r,'identity':{}} for r in data['actions']}
    schema,is_patch=ln.correction_schema(data,actions,groups,rejected);assert is_patch
    with pytest.raises(ValidationError):validate({},schema)
    incomplete=copy.deepcopy(rejected);incomplete.pop('reason')
    schema,is_patch=ln.correction_schema(data,actions,groups,incomplete)
    assert not is_patch and 'reason' in schema['required']


def test_shape_invalid_initial_requires_full_correction_on_actual_path(session):
    native,_=session;s=native.sources;record=prepared(s);calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(phase)
        if len(calls)==1:return conflict(data)
        if phase.endswith('-repair'):
            assert data['repair_contract']['response_mode']=='FULL_DECISION'
            assert not s.law_navigation_state['selected']
            return reader(system,data,schema,phase,timeout)
        return reader(system,data,schema,phase,timeout)
    result=ln.select('승인 예외',record,invoke,session=s,remaining_seconds=30)
    assert result['status']=='complete' and sum(p.endswith('-repair') for p in calls)==1
    assert result['decisions'][0]['decision']['branch_decisions']==[]


def test_bad_partial_patch_is_never_executed(session):
    native,_=session;s=native.sources;record=prepared(s);calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(phase)
        if len(calls)==1:return conflict(data)
        return {'branch_decisions':data['rejected_decision']['branch_decisions']}
    with pytest.raises(ValidationError):ln.select('승인 예외',record,invoke,session=s,remaining_seconds=30)
    assert len(calls)==2 and not s.law_navigation_state['selected']
    assert len(s.law_navigation_state['rejected_decisions'])==2


def test_nested_schema_repairs_disabled_for_stage_owned_navigation(session,monkeypatch):
    native,_=session;profiles=[];native.profile['max_schema_repairs']=1
    native.gateway=SimpleNamespace(domain={},transport=object())
    class Gateway:
        def __init__(self,work,context,profile,*args,**kwargs):profiles.append(profile)
        def generate(self,*args):return {}
    monkeypatch.setattr(bs,'_Gateway',Gateway)
    native.structured('system',{}, {'type':'object'}, 'source-law-navigation-1-repair',30)
    native.structured('system',{}, {'type':'object'}, 'source-reference-law-1-1',30)
    assert profiles[0]['max_schema_repairs']==0 and profiles[0]['max_transport_retries']==0
    assert profiles[1]['max_schema_repairs']==0
