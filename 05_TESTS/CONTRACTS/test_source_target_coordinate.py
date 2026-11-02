"""Real Qwen display-coordinate failure: preserve exact scope and target identity."""
from copy import deepcopy
import pytest
from semantic_runtime.legal_agent import source_goal_control as goals
from semantic_runtime.legal_agent.output_contract import OutputContractError, diagnostics


@pytest.mark.parametrize('scope',goals.COORDINATE_SCOPES)
@pytest.mark.parametrize('prefix',[False,True])
def test_exact_coordinate_display_scope_is_lossless(scope,prefix):
    row={'coordinate':(scope+':' if prefix else '')+'제1조제2항','coordinate_scope':scope}
    before=deepcopy(row)
    assert goals.target_coordinate(row)=='제1조제2항'
    assert row==before


@pytest.mark.parametrize('text,scope,code',[
    ('addendum:제1조','body','SOURCE_TARGET_SCOPE_CONFLICT'),
    ('body:제1조','annex','SOURCE_TARGET_SCOPE_CONFLICT'),
    ('unknown:제1조','body','SOURCE_TARGET_SCOPE_CONFLICT'),
    ('제1조:제2조','body','SOURCE_TARGET_SCOPE_CONFLICT'),
    ('body:제1조부터 제3조','body','SOURCE_TARGET_COORDINATE_INVALID'),
    ('body:제1조, 제2조','body','SOURCE_TARGET_COORDINATE_INVALID'),
    ('body:제1조 승인','body','SOURCE_TARGET_COORDINATE_INVALID'),
    ('body:','body','SOURCE_TARGET_COORDINATE_INVALID'),
    ('body:body:제1조','body','SOURCE_TARGET_COORDINATE_INVALID'),
])
def test_scope_conflict_or_ambiguous_coordinate_requires_model_correction(text,scope,code):
    with pytest.raises(OutputContractError) as failure:
        goals.target_coordinate({'coordinate':text,'coordinate_scope':scope},path='/source_targets/0/coordinate')
    report=diagnostics(failure.value)
    assert report['repairable']
    assert report['issues'][0]['code']==code
    assert report['issues'][0]['path']=='/source_targets/0/coordinate'
