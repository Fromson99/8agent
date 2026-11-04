from copy import deepcopy
import gzip,json,base64
from pathlib import Path
import pytest
from semantic_runtime.legal_agent import source_goal_control as sg
from semantic_runtime.legal_agent.errors import ProposalError
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[3]
def recorded():
    p=ROOT/'04_EXPERIMENTS/ADR/ADR-1359-grouped-original-review-answer/artifacts/public-live/B03-17-parasail/raw/call-007'
    schema=json.load(gzip.open(p/'request.json.gz','rt'))['response_format']['json_schema']['schema']
    partial=json.load(gzip.open(p/'partial.json.gz','rt'));text=''
    for line in base64.b64decode(partial['body_base64']).decode().splitlines():
        if not line.startswith('data:'):continue
        try:row=json.loads(line[5:])
        except ValueError:continue
        for c in row.get('choices',[]):text+=c.get('delta',{}).get('content') or ''
    # Synthetic complete fixture only, never submitted as a live model response.
    return schema,json.loads(text.rstrip()+']}')
def test_saved_whitespace_location_is_fixed_empty_and_exactly_restored():
    schema,value=recorded();before=deepcopy((schema,value));wire,expand=sg.model_projection(schema)
    assert Draft202012Validator(schema).is_valid(value)
    raw=deepcopy(value);raw.pop('source_goal_exclusions')
    assert all('source_goal_exclusions' not in b['properties'] for b in wire['anyOf'])
    assert all('source_targets' in b['properties'] for b in wire['anyOf'])
    assert expand(raw)==value and (schema,value)==before
@pytest.mark.parametrize('fault',['supplied_empty','supplied_exclusion','missing_target_choice','unknown_action','invalid_evidence'])
def test_model_choices_and_original_validation_not_repaired_implicitly(fault):
    s,v=recorded();w,e=sg.model_projection(s);v.pop('source_goal_exclusions')
    if fault=='supplied_empty':v['source_goal_exclusions']=[]
    if fault=='supplied_exclusion':v['source_goal_exclusions']=[{'goal_id':'invented'}]
    if fault=='missing_target_choice':v.pop('source_targets')
    if fault=='unknown_action':v['action']['choice']='INVENT'
    if fault=='invalid_evidence':v['action']['basis_refs']=['FOREIGN']
    before=deepcopy(v)
    with pytest.raises(ProposalError):e(v)
    assert v==before
@pytest.mark.parametrize('change',['nonempty_branch','optional_branch','impossible_minimum'])
def test_only_unambiguous_required_empty_fields_are_removed(change):
    s,v=recorded();b=s['anyOf'][1]
    if change=='nonempty_branch':b['properties']['source_goal_exclusions']['maxItems']=1
    if change=='optional_branch':b['required'].remove('source_goal_exclusions')
    if change=='impossible_minimum':b['properties']['source_goal_exclusions']['minItems']=1
    w,e=sg.model_projection(s);assert w==s and e(v)==v
