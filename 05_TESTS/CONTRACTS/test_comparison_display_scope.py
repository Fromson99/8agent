"""Regression for duplicate original display; no model-effect evaluation."""
from copy import deepcopy
import json
from types import SimpleNamespace as S

import pytest
from fastapi.testclient import TestClient

import test_internal_concept_comparison as fixture
from workflow.risk_team_compare_workflow import concept_report

tree = fixture.tree


def example():
    internal = fixture.source()
    concept = fixture.concept(internal)
    concept.pop('existing_id')
    concept['id'] = 'concept-1'
    external = fixture.source('route-1', 'external')
    external.update(document_id='external-document', unit_id='article-1')
    external['spans'][0].update(block_id='b1', block_hash='block-original',
                               start_cp=0, end_cp=len(external['text']))
    other = deepcopy(external)
    other['evidence_id'] = 'route-2'
    by = {e['evidence_id']: e for e in (internal, external, other)}
    state = {'concept_plan': {'concepts': [concept]}}
    item = {'issue_id': 'concept-1', 'field': 'obligation', 'difference': ''}
    for side, sources in [('internal', [internal]), ('external', [external, other])]:
        item[side] = {'text': '판단 원문', 'missing': '', 'dependencies': [],
                      'citations': [{'evidence': e['evidence_id'], 'quote': e['text']} for e in sources]}
    body = {'comparison_items': {'items': [item]},
            'assembly': {'term_agent': {'source_bundle': {'sources': []}}},
            'report': {}, 'answer': {}, 'evidence_refs': [], 'evidence_summary': {}, 'unresolved': []}
    return state, body, by, S(request={'question': '승인 의무 대사', 'as_of': None})


def test_same_original_routes_share_one_display_row_and_keep_all_audit_ids():
    state, body, by, ctx = example()
    before = deepcopy((state, by, body['comparison_items']))
    result = concept_report.apply(ctx, state, body, by)
    rows = result['comparison_table']['rows'][0]['external']
    assert len(rows) == 1
    assert rows[0]['selection_ids'] == ['route-1', 'route-2']
    assert rows[0]['quote'] == by['route-1']['text']
    assert result['evidence_refs'] == ['in', 'route-1', 'route-2']
    assert {c['selection_id'] for c in result['assembly']['term_agent']['source_bundle']['sources']} == set(by)
    assert (state, by, body['comparison_items']) == before
    saved = deepcopy(result)
    assert concept_report.apply(ctx, state, body, by) == saved


@pytest.mark.parametrize('difference', [
    'document_id', 'generation_id', 'source_artifact_hash', 'unit_id',
    'block_id', 'block_hash', 'position', 'unknown_location', 'quote',
])
def test_distinct_or_unresolved_originals_are_not_merged(difference):
    state, body, by, ctx = example()
    other = by['route-2']
    if difference in ('document_id', 'generation_id', 'source_artifact_hash', 'unit_id'):
        other[difference] += '-different'
    elif difference in ('block_id', 'block_hash'):
        other['spans'][0][difference] += '-different'
    elif difference == 'position':
        other['spans'][0]['start_cp'] += 10
        other['spans'][0]['end_cp'] += 10
    elif difference == 'unknown_location':
        other.pop('unit_id')
    else:
        body['comparison_items']['items'][0]['external']['citations'][1]['quote'] = '승인 후 보고한다.'
    result = concept_report.apply(ctx, state, body, by)
    assert len(result['comparison_table']['rows'][0]['external']) == 2


def test_matching_quote_in_full_and_partial_spans_uses_absolute_original_location():
    state, body, by, ctx = example()
    quote = '단서는 보존한다.'
    for citation in body['comparison_items']['items'][0]['external']['citations']:
        citation['quote'] = quote
    span = by['route-2']['spans'][0]
    span.update(start_cp=span['text'].index(quote), text=quote)
    result = concept_report.apply(ctx, state, body, by)
    assert len(result['comparison_table']['rows'][0]['external']) == 1


def test_ambiguous_repeated_quote_positions_keep_route_identity():
    state, body, by, ctx = example()
    for name in ('route-1', 'route-2'):
        by[name]['spans'][0].update(text='동일 원문. 동일 원문.', end_cp=13)
    for citation in body['comparison_items']['items'][0]['external']['citations']:
        citation['quote'] = '동일 원문.'
    result = concept_report.apply(ctx, state, body, by)
    assert len(result['comparison_table']['rows'][0]['external']) == 2


@pytest.mark.parametrize('defect', ['false_quote', 'wrong_side'])
def test_display_grouping_never_bypasses_citation_integrity(defect):
    state, body, by, ctx = example()
    if defect == 'false_quote':
        body['comparison_items']['items'][0]['external']['citations'][1]['quote'] = '없는 원문'
    else:
        by['route-2']['side'] = 'internal'
    with pytest.raises(ValueError):
        concept_report.apply(ctx, state, body, by)


def test_api_scope_instructions_reach_both_stages_and_saved_display_is_identical(tmp_path, tree):
    app, _ = fixture.application(tmp_path, tree)
    class Capture(fixture.Transport):
        def __init__(self):
            super().__init__()
            self.instructions = {}

        def send_once(self, *, body, ticket):
            view = json.loads(body['messages'][1]['content'])['view']
            phase = view.get('source_stage', view['phase'])
            self.instructions.setdefault(phase, []).append(json.dumps(body, ensure_ascii=False))
            return super().send_once(body=body, ticket=ticket)
    transport = Capture()
    app.state.pipeline.term_agent.transport = transport
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=fixture.fixture.prior.BODY)
        assert response.status_code == 200, response.text
        result = response.json()
        for stage in ('workflow-concepts', 'workflow-items'):
            shown = transport.instructions[stage][0]
            assert '그 답을 바꿀 수 있는 의존 원문' in shown
            assert '적용 결과를 바꿀 수 있으면 연결 외규를 계속 탐색' in shown
        assert 'CONTEXT만 보충하려는 조사는 next_tasks에 넣지 않고' in transport.instructions['workflow-items'][0]
        calls = len(transport.views)
        repeated = client.post('/v1/rag/ask', json=fixture.fixture.prior.BODY).json()
        saved = client.get('/v1/workflows/runs/' + result['run_id'], params={'session_id': 's'}).json()
        assert repeated['comparison_table'] == saved['comparison_table'] == result['comparison_table']
        assert repeated['answer'] == saved['answer'] == result['answer']
        assert len(transport.views) == calls
