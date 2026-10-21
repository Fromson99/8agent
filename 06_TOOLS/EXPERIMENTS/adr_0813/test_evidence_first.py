"""Evidence-first wire order, unchanged meanings and durable call identity."""
from copy import deepcopy
import json
from types import SimpleNamespace as NS

import pytest
from jsonschema import validate

from workflow.adapters import projection
from workflow.adapters.model import ModelAdapter
from workflow.contracts import digest
from workflow.risk_team_compare_workflow import compare
from workflow.risk_team_compare_workflow.contracts import BASIS, COMPARE
from semantic_runtime.legal_agent.bounded_source_session import _Gateway, _Protocol
from semantic_runtime.legal_agent.local_gemma import provider_request

from test_wire_mechanics import packet, proposal


OBSERVATIONS=('citations','dimensions','difference','reason','unresolved','verdict')


def resolved(schema, root):
    while '$ref' in schema:
        assert schema['$ref'].startswith('#/$defs/')
        schema=root['$defs'][schema['$ref'].removeprefix('#/$defs/')]
    return schema


@pytest.mark.parametrize('numeric',[True,False])
def test_wire_properties_and_required_order_put_verdict_after_observations(numeric):
    data=packet(numeric=numeric);before=deepcopy(data);before_schema=deepcopy(COMPARE)
    _,wire,_,receipt=projection.prepare('COMPARE',data,COMPARE)
    row=wire['properties']['rows']['items']
    assert list(row['properties'])==['item',*OBSERVATIONS]
    assert row['required']==['item',*[name for name in OBSERVATIONS if name!='dimensions' or numeric]]
    assert receipt['version']=='workflow-mechanical-projection-v4'
    assert data==before and COMPARE==before_schema


def test_multiple_pair_identity_fields_are_preserved_before_observations():
    data=packet();other=deepcopy(data['basis']['pairs'][0]);other['pair_id']='another-pair'
    data['basis']['pairs'].append(other)
    _,wire,_,_=projection.prepare('COMPARE',data,COMPARE)
    row=wire['properties']['rows']['items']
    assert list(row['properties'])==['pair_id','item','numeric',*OBSERVATIONS]
    assert row['required']==list(row['properties'])
    assert row['properties']['dimensions']['type']=='array'


@pytest.mark.parametrize('numeric',[True,False])
def test_actual_gateway_and_provider_cleaner_preserve_generation_order(numeric):
    view,wire,_,_=projection.prepare('COMPARE',packet(numeric=numeric),COMPARE)
    gateway=_Gateway.__new__(_Gateway)
    gateway.protocol=_Protocol(wire)
    gateway.transport=NS(binding={'model':'qwen/qwen3.8-27b'})
    gateway.compact=False;gateway.profile={'max_output_tokens':4000};gateway.system='모의 검사'
    request=gateway.request('compose',view,'WorkflowDecision')
    body=provider_request(request)
    schema=body['response_format']['json_schema']['schema']
    rows=resolved(schema['properties']['rows'],schema)
    row=resolved(rows['items'],schema)
    expected=['item',*[name for name in OBSERVATIONS if name!='dimensions' or numeric]]
    assert list(row['properties'])==expected and row['required']==expected
    # The textual schema is serialized with sorted object keys. The required
    # array still exposes the same declared order without weakening validation.
    in_message=json.loads(request['messages'][1]['content'])['output_schema']
    assert in_message['properties']['rows']['items']['required']==expected


def test_required_order_changes_actual_model_adapter_call_identity(monkeypatch):
    data=packet();view,wire,expand,receipt=projection.prepare('COMPARE',data,COMPARE)
    legacy=deepcopy(wire)
    row=legacy['properties']['rows']['items']
    previous=['item','verdict','difference','reason','citations','dimensions','unresolved']
    row['properties']={name:row['properties'][name] for name in previous}
    # Object order alone does not change the sorted structural digest.
    assert digest(legacy)==digest(wire)
    row['required']=previous
    assert digest(legacy)!=digest(wire)
    records=[]
    class StopBeforeModel(Exception):pass
    def intent(ident,kind,value):
        records.append((ident,kind,deepcopy(value)))
        raise StopBeforeModel()
    adapter=ModelAdapter(NS(intent=intent),NS(),NS())
    with pytest.raises(StopBeforeModel):
        adapter.decide('COMPARE',data,COMPARE,'동일한 의미 판단 지시',lambda value:None)
    monkeypatch.setattr(projection,'prepare',lambda *args:(view,legacy,expand,receipt))
    with pytest.raises(StopBeforeModel):
        adapter.decide('COMPARE',data,COMPARE,'동일한 의미 판단 지시',lambda value:None)
    assert records[0][0]!=records[1][0]
    assert records[0][2]['data']==records[1][2]['data']
    assert records[0][2]['instructions']==records[1][2]['instructions']


@pytest.mark.parametrize('verdict',['CONFORMS','CONFLICT','ADDITIONAL_INTERNAL','DEFERRED'])
def test_wire_order_does_not_compute_or_replace_semantic_verdict(verdict):
    data=packet();view,wire,expand,_=projection.prepare('COMPARE',data,COMPARE)
    value=proposal(view);value['rows'][0]['verdict']=verdict;before=deepcopy(value)
    validate(value,wire);canonical=expand(value);validate(canonical,COMPARE)
    assert value==before and canonical['rows'][0]['verdict']==verdict
    assert canonical['rows'][0]['reason']==value['rows'][0]['reason']
    assert next(d for d in canonical['rows'][0]['dimensions'] if d['name']=='value')['status']=='DIFFERENT'
    if verdict=='CONFORMS':
        with pytest.raises(ValueError,match='cannot conceal'):
            compare.validate(canonical,data['sources'],data['basis'],data['scope']['issues'])
    else:
        compare.validate(canonical,data['sources'],data['basis'],data['scope']['issues'])


def test_other_stage_field_order_and_source_projection_remain_unchanged():
    data=packet();view,wire,_,_=projection.prepare('BASIS',data,BASIS)
    assert list(wire['properties'])==list(BASIS['properties'])
    assert wire['required']==BASIS['required']
    assert view==projection.project_sources(data)[0]


def test_compare_instructions_are_generic_and_use_one_model_stage(monkeypatch):
    import workflow.presentation as presentation
    instructions=[];stages=[]
    class StopBeforeModel(Exception):pass
    def capture(stage,data,schema,instruction,checked):
        instructions.append(instruction);stages.append(stage)
        raise StopBeforeModel()
    for numeric in (True,False):
        data=packet(numeric=numeric)
        data['packet']={'plan_hash':digest(data),'index':0,'count':1,'dependency_closure_complete':True}
        monkeypatch.setattr(presentation,'packets',lambda *args,**kwargs:[(data,data['sources'])])
        ctx=NS(request={'use_llm':True},model=NS(decide=capture))
        state={'basis':deepcopy(data['basis']),'scope':deepcopy(data['scope'])}
        with pytest.raises(StopBeforeModel):compare.compare(ctx,state)
    assert stages==['COMPARE','COMPARE'] and instructions[0]==instructions[1]
    instruction=instructions[0]
    assert instruction.index('citations')<instruction.index('dimensions')<instruction.index('difference')
    assert instruction.index('difference')<instruction.index('reason')<instruction.index('unresolved')<instruction.index('verdict')
    assert '마지막에 전체 요구 조건' in instruction
    assert '일부 차원이 같다는 사실만으로' in instruction
