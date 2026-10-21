from copy import deepcopy
import pytest
from semantic_runtime.legal_agent.gateway import compact_wire_view


@pytest.mark.parametrize('stage', ['memory-assess', 'memory-assess-repair'])
@pytest.mark.parametrize('difference', [None, 'source_id', 'document_id', 'block_id', 'start_cp', 'end_cp', 'text', 'extra_span', 'missing_option', 'extra_card'])
def test_only_same_identity_and_exact_span_remove_duplicate_wire_body(stage, difference):
    span = {'block_id': 'b', 'start_cp': 7, 'end_cp': 10, 'text': '가😀나'}
    card = {'source_id': 's', 'document_id': 'd', 'text': span['text'], 'spans': [span]}
    option = {'source_id': 's', 'document_id': 'd', **span}
    view = {'source_stage': stage, 'exact_evidence': [deepcopy(card)], 'evidence_options': [deepcopy(option)]}
    if difference in option:
        view['evidence_options'][0][difference] = 'different'
    elif difference == 'extra_span':
        view['exact_evidence'][0]['spans'].append({**span, 'text': '추가 원문'})
    elif difference == 'missing_option':
        view['evidence_options'] = []
    elif difference == 'extra_card':
        view['exact_evidence'].append({**card, 'source_id': 'untransmitted'})
    before = deepcopy(view)
    result = compact_wire_view(view, 'assess')
    assert ('exact_evidence' not in result) == (difference is None)
    assert view == before and result['evidence_options'] == view['evidence_options']


def test_other_stage_preserves_original_evidence_container():
    span = {'block_id': 'b', 'start_cp': 0, 'end_cp': 1, 'text': '가'}
    card = {'source_id': 's', 'document_id': 'd', 'text': '가', 'spans': [span]}
    view = {'source_stage': 'source-law-navigation', 'exact_evidence': [card],
            'evidence_options': [{'source_id': 's', 'document_id': 'd', **span}]}
    assert compact_wire_view(view, 'assess')['exact_evidence'][0]['text'] == '가'
