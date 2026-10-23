"""Nested branch meaning must survive generation projection unchanged."""
from copy import deepcopy
import pytest
from jsonschema import validate
from semantic_runtime.legal_agent.completion_contracts import obj
from semantic_runtime.legal_agent.minimal_output import Projection
from semantic_runtime.legal_agent.output_contract import OutputContractError


def fixture(container='object'):
    def branch(choice,status):
        nested=obj({'status':{'const':status},'reason':{'type':'string','minLength':1}})
        if container=='array':nested={'type':'array','minItems':1,'maxItems':1,'items':nested}
        return obj({'choice':{'const':choice},'review':nested,'binding':{'const':'server-v1'}})
    return {'type':'object','anyOf':[branch('READ','NEEDS_SOURCE'),branch('FINISH','ANSWERABLE'),branch('FINISH','NO_PROGRESS')]}


@pytest.mark.parametrize('container',['object','array'])
@pytest.mark.parametrize('status',['ANSWERABLE','NO_PROGRESS'])
def test_nested_semantic_branch_is_explicit_and_roundtrips(container,status):
    schema=fixture(container);p=Projection(schema)
    nested={'status':status,'reason':'동결한 원문을 검토한 의견'}
    value={'choice':'FINISH','review':[nested] if container=='array' else nested,'binding':'server-v1'}
    raw=p.project(value);validate(raw,p.wire)
    assert p.expand(raw)==value
    actual=raw['review'][0] if container=='array' else raw['review']
    assert actual['status']==status
    assert 'binding' not in raw


def test_missing_nested_discriminator_cannot_be_guessed_from_shared_action():
    p=Projection(fixture())
    with pytest.raises(OutputContractError):p.expand({'choice':'FINISH','review':{'reason':'원문 검토'}})


def test_unique_action_still_restores_only_its_implied_fields():
    p=Projection(fixture());v={'choice':'READ','review':{'status':'NEEDS_SOURCE','reason':'위임 원문 필요'},'binding':'server-v1'}
    raw=p.project(v)
    assert 'status' not in raw['review'] and 'binding' not in raw
    assert p.expand(raw)==v


@pytest.mark.parametrize('mutation',[lambda x:x.update(binding='tampered'),lambda x:x['review'].update(status='UNKNOWN'),lambda x:x.update(choice='OUTSIDE_SCOPE')])
def test_host_binding_and_branch_domain_remain_strict(mutation):
    p=Projection(fixture());v={'choice':'FINISH','review':{'status':'ANSWERABLE','reason':'근거 있음'},'binding':'server-v1'}
    raw=p.project(v);mutation(raw)
    with pytest.raises(OutputContractError):p.expand(raw)
