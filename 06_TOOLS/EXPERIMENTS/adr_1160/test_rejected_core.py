from copy import deepcopy
from types import SimpleNamespace
import pytest
from jsonschema import validate
from semantic_runtime.legal_agent import read_judgment_final as f
from semantic_runtime.legal_agent.completion_contracts import obj

def setup():
    schema=obj({'claims':{'type':'array','items':obj({'claim_id':{'type':'string'},'evidence_ref':{'enum':['S41']},'kind':{'const':'OBSERVED'}})},'gaps':{'type':'array','items':obj({'target':{'enum':['T18']}})},f.FIELD:obj({'disposition':{'const':'USE'}})})
    raw={'claims':[{'claim_id':'C9','evidence_ref':'S41'}],'gaps':[{'target':'T18'}],f.FIELD:{'disposition':'BAD'}}
    seen=[]
    def decode(value, wire, name):
        validate(value,wire);seen.append(name);v=deepcopy(value);v['claims'][0]['evidence_ref']='canonical-original';return v
    return raw,schema,SimpleNamespace(decode=decode),seen

def test_rejected_review_never_becomes_accepted_and_core_uses_current_binding():
    raw,schema,refs,seen=setup();before=deepcopy(raw)
    value=f.independent_core(raw,schema,refs,'BoundedAssessment')
    assert value[f.FIELD] is None and value['claims'][0]['kind']=='OBSERVED'
    assert value['claims'][0]['evidence_ref']=='canonical-original' and seen==['BoundedAssessment']
    assert raw==before

@pytest.mark.parametrize('bad',['unknown_reference','extra_root','wrong_constant','wrong_target','missing_core','not_object'])
def test_invalid_core_cannot_be_salvaged(bad):
    raw,schema,refs,seen=setup()
    if bad=='unknown_reference':raw['claims'][0]['evidence_ref']='S999'
    if bad=='extra_root':raw['forged']='untrusted'
    if bad=='wrong_constant':raw['claims'][0]['kind']='INFERRED'
    if bad=='wrong_target':raw['gaps'][0]['target']='T999'
    if bad=='missing_core':raw.pop('claims')
    if bad=='not_object':raw=[]
    assert f.independent_core(raw,schema,refs,'BoundedAssessment') is None and seen==[]
