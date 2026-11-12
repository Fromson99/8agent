"""ADR-1503/1504 대사: the stopped report left out a read original an item review had marked unrelated;
the final answer cited it and the whole request ended with 409 (WORKFLOW_FINALIZATION_SOURCE) and no
answer. A cited verified read original is now published with the answer; an unknown original or a
quote outside the read spans is still rejected."""
from copy import deepcopy

import pytest

from workflow.contracts import digest
from workflow.risk_team_compare_workflow import finalize


def original(ident, side, text):
    return {'evidence_id': ident, 'side': side, 'document_id': 'D-' + side, 'generation_id': 'G1',
            'source_artifact_hash': 'h' * 64, 'text': text, 'spans': [{'text': text, 'start_cp': 0, 'end_cp': len(text)}],
            'metadata': {'document_name': ('내규' if side == 'internal' else '외규') + ' 문서', 'heading': '제1조'}}


def setup(cited):
    by = {'E1': original('E1', 'internal', '회사는 유동성비율을 관리한다.'),
          'E2': original('E2', 'external', '유동성비율은 100분의 100 이상이어야 한다.')}
    card = {'selection_id': 'E1', 'document_id': 'D-internal', 'document_name': '내규 문서', 'coordinate_label': '제1조',
            'generation_id': 'G1', 'source_artifact_hash': 'h' * 64, 'spans': by['E1']['spans'], 'excerpt': by['E1']['text'],
            'side': 'internal', 'content_read': True, 'interpretation_status': 'UNVERIFIED', 'coverage': 'READ_SPANS_ONLY'}
    bundle = {'schema_version': 'workflow-source-v1', 'sources': [card], 'binding_hash': 'b'}
    bundle['bundle_hash'] = digest(bundle)
    result = {'answer': {'text': '', 'unresolved': []}, 'unresolved': [], 'evidence_refs': ['E1'],
              'evidence_summary': {'reported': 1}, 'assembly': {'term_agent': {'source_bundle': bundle}}}
    value = {'paragraphs': [{'text': '외규는 100% 이상을 요구한다.', 'citations': cited}], 'unresolved': []}
    state = {'finalization': {'status': 'COMPLETE', 'value': value, 'value_hash': digest(value), 'reason': 'r', 'cause': 'X'}}
    return state, result, by


def test_cited_read_original_is_published_with_the_answer():
    state, result, by = setup([{'evidence': 'E2', 'quote': '100분의 100 이상'}])
    out = finalize.apply(state, result, by)
    bundle = out['assembly']['term_agent']['source_bundle']
    assert out['evidence_refs'] == ['E1', 'E2']
    assert [c['selection_id'] for c in bundle['sources']] == ['E1', 'E2']
    assert bundle['sources'][1]['excerpt'] == by['E2']['text'] and bundle['sources'][1]['side'] == 'external'
    check = deepcopy(bundle); check.pop('bundle_hash')
    assert bundle['bundle_hash'] == digest(check)
    assert out['final_answer_published_sources'] == ['E2'] and out['evidence_summary']['reported'] == 2
    assert '[E2]' in out['answer']['text']


def test_already_published_citation_adds_nothing():
    state, result, by = setup([{'evidence': 'E1', 'quote': '유동성비율을 관리한다'}])
    before = deepcopy(result['assembly'])
    out = finalize.apply(state, result, by)
    assert out['assembly'] == before and 'final_answer_published_sources' not in out


@pytest.mark.parametrize('citation', [{'evidence': 'E9', 'quote': '100분의 100'}, {'evidence': 'E2', 'quote': '100분의 50 이상'}])
def test_unknown_or_unquoted_original_stays_rejected(citation):
    state, result, by = setup([citation])
    with pytest.raises(ValueError):
        finalize.apply(state, result, by)
