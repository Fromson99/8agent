from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.legal_agent.decision_projection import prepare
from semantic_runtime.legal_agent.model_contract import genos_wire_schema
from semantic_runtime.legal_agent.local_gemma import provider_request
from semantic_runtime.legal_agent.law_navigation import _object
from test_generation_fields import schemas
from test_system_mechanics import sample
from workflow.adapters.projection import prepare as project
from workflow.risk_team_compare_workflow.contracts import BASIS


def test_every_conditional_semantic_field_remains_required_in_flat_grammar():
    canonical,wire,_=schemas()
    canonical['properties']['gap_ids']={'type':'array','items':{'enum':['G1','G2']}}
    for b in canonical['anyOf']:
        b['properties']['gap_ids']=deepcopy(canonical['properties']['gap_ids'])
        if b['properties']['next_action']['const']=='RESEARCH':b['required'].append('gap_ids')
    wire,expand,_=prepare(canonical,{'issues':[{'id':'Q1','request_quote':'기준은?'}]})
    generated=provider_request({'response_format':{'json_schema':{'schema':genos_wire_schema(wire)}}})['response_format']['json_schema']['schema']
    assert 'gap_ids' in generated['required']
    raw={'next_action':'PENDING','targets':[],'queries':[],'reason':'미확인','sufficiency_reason':'부족','exploration':[]}
    with pytest.raises(ValidationError):validate(raw,generated)


def test_inactive_investigation_rows_cannot_trigger_read_or_adoption():
    canonical,_,_=schemas();view={'issues':[{'id':'Q1','request_quote':'기준은?'}]}
    wire,expand,receipt=prepare(canonical,view)
    raw={'next_action':'PENDING','targets':['T1'],'queries':['남아 있는 검색어'],'reason':'미확인',
        'evidence_sufficient':False,'sufficiency_reason':'부족',
        'exploration':[{'target':'T1','issue_id':'Q1','missing_need':'규정','relation':'DIRECT'}]}
    value=expand(raw);validate(value,canonical)
    assert value['targets']==value['queries']==value['exploration']==[]
    assert 'exploration' in receipt['system_empty_fields_by_action']['PENDING']
    assert raw['targets']==['T1']
    bad=deepcopy(raw);bad['presentation_id']='stale'
    with pytest.raises(ValidationError):expand(bad)


@pytest.mark.parametrize('side,value',[('internal','E'),('external','I'),('internal','문서 이름'),('external','UNKNOWN')])
def test_basis_can_only_select_actual_side_bound_ids(side,value):
    sources,pair=sample();data={'sources':sources,'scope':{'issues':[{'id':'q1'}]},'as_of':None}
    _,wire,_,_=project('BASIS',data,BASIS)
    pair.pop('pair_id');pair['applicability'].pop('as_of');pair['applicability']['citations']=[]
    pair[side]=[value]
    with pytest.raises(ValidationError):validate({'pairs':[pair],'gaps':[],'summary':'test'},wire)


def test_absent_side_cannot_produce_a_pair():
    sources,pair=sample();_,wire,_,_=project('BASIS',{'sources':sources[:1]},BASIS)
    assert wire['properties']['pairs']['maxItems']==0


@pytest.mark.parametrize('forged',[False,True])
def test_followup_facts_bind_original_parent_not_generated_followup(forged):
    from semantic_runtime.workflow_rag import execute
    from semantic_runtime.legal_agent.errors import ContractError
    task={'source_category':'internal','search_hints':['승인'],'issues':[{'id':'q','question':'승인 기준','numeric':False}],
          'facts':[{'name':'회사','value':'B' if forged else 'A','user_quote':'회사 B' if forged else '회사 A'}]}
    ctx=NS(run_id='parent',request={'question':'회사 A의 승인 기준을 비교'})
    port=NS(services=object(),session=NS(context=ctx),all_scope=[],categories={})
    action={'side':'internal','operation':'ask_rag','args':{'question':'회사 B에 대한 예외를 추가 조사','previous':None,'task':task}}
    if forged:
        with pytest.raises(ContractError):execute(port,action,'c')
    else:assert execute(port,action,'c')['status']=='not_registered'
