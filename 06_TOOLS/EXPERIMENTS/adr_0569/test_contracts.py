"""Exact-input and conservative fallback contracts for the two changed stages."""
from copy import deepcopy
import json
from pathlib import Path
import runpy

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUN = runpy.run_path(str(ROOT / '06_TOOLS/EXPERIMENTS/adr_0569/run.py'))
FROZEN = RUN['verify']()
MODULES = {arm: RUN['modules'](path) for arm, path in FROZEN.items()}
A = ROOT / '04_EXPERIMENTS/ADR/ADR-0569-compact-plan-smallpool'


def record():
    return json.loads((A / 'artifacts/native-contracts/cases/APP-01/combined/recall.json').read_text())


def invoke_spy(calls, *, structural=False, invalid=False):
    def invoke(system, data, schema, phase, timeout):
        calls.append({'data': data, 'schema': schema, 'phase': phase})
        value = {'issues': [], 'choices': []}
        if phase == 'source-triage':
            value['choices'] = [{'id': 'OUT_OF_POOL' if invalid else schema['properties']['choices']['items']['properties']['id']['enum'][0], 'reason': '계약 확인'}]
        if structural: value['needs_fulltext'] = True
        return value
    return invoke


def test_one_pass_sends_every_complete_original_verbatim():
    module = MODULES['combined']['selection']; r = record(); calls = []
    result = module.select_sources('적용요건과 예외 확인', r, invoke_spy(calls), remaining_seconds=240)
    assert len(calls) == 1 and calls[0]['phase'] == 'source-triage'
    original_map = module.originals(r)
    cards = calls[0]['data']['originals']
    assert len(cards) == len(original_map) == 6
    for card in cards:
        sid = result['label_to_source'][card['id']]
        assert card['excerpts'] == [{'start': 0, 'end': len(original_map[sid]['text']), 'text': original_map[sid]['text']}]
    assert result['small_pool_full_originals']
    assert result['recovered_ids'] == []
    assert set(result['full_original_candidate_ids']) == set(original_map)


def test_compact_only_keeps_native_two_pass_selection():
    calls = []
    result = MODULES['compact']['selection'].select_sources('규정 확인', record(), invoke_spy(calls), remaining_seconds=240)
    assert [c['phase'] for c in calls] == ['source-triage', 'source-omission-review']
    assert 'originals' not in calls[0]['data']
    assert 'small_pool_full_originals' not in result


@pytest.mark.parametrize('boundary', ['unread', 'large_original', 'large_pool', 'serialized_limit'])
def test_incomplete_or_large_pool_retains_content_review(monkeypatch, boundary):
    module = MODULES['combined']['selection']; r = record(); calls = []; budget = 80000
    if boundary == 'unread': r['selected_for_read'].append('unread-source')
    elif boundary == 'large_original':
        original_map = module.originals(r)
        original_map[next(iter(original_map))]['text'] = '원' * 16001
        monkeypatch.setattr(module, 'originals', lambda unused: original_map)
    elif boundary == 'large_pool':
        p = ROOT / '04_EXPERIMENTS/ADR/ADR-0568-action-concepts-presql/artifacts/run-001/cases/INV-01/integrated/recall.json'
        r = json.loads(p.read_text()); r['selected_for_read'] = r['selected_for_read'][:17]
    else: budget = 32
    result = module.select_sources('규정 확인', r, invoke_spy(calls), remaining_seconds=240, max_fulltext_chars=budget)
    assert [c['phase'] for c in calls] == ['source-triage', 'source-omission-review']
    assert not result['small_pool_full_originals']
    assert 'originals' not in calls[0]['data']


def test_structure_fallback_decision_is_not_overridden():
    r = record(); r['discovery_mode'] = 'structure'; calls = []
    result = MODULES['combined']['selection'].select_sources('추가 근거 필요', r, invoke_spy(calls, structural=True), remaining_seconds=240)
    assert result['needs_fulltext'] is True
    assert not result['small_pool_full_originals']


def test_single_pass_choice_must_still_be_in_closed_pool():
    with pytest.raises(ValueError, match='closed pool'):
        MODULES['combined']['selection'].select_sources('규정 확인', record(), invoke_spy([], invalid=True), remaining_seconds=240)


def plan():
    return {'mode': 'SEARCH', 'reason': '규정과 실적 확인', 'answer': '', 'law_names': [],
        'queries': ['적용규정', '업무실적'], 'browse_view': 'documents', 'document_category': 'all',
        'title_query': '', 'inspect_documents': False, 'query_concepts': ['purpose:applicable', 'purpose:performance']}


def test_concepts_are_aligned_to_queries_without_duplicate_reason_output():
    module = MODULES['compact']['plan']; value = plan()
    module.validate_action_catalogue(value, [], ['purpose:applicable', 'purpose:performance'])
    actions = module.as_actions(value)
    assert actions == [{'query': '적용규정', 'concept_refs': ['purpose:applicable']}, {'query': '업무실적', 'concept_refs': ['purpose:performance']}]
    value['query_concepts'][0] = ''
    assert module.as_actions(value)[0]['concept_refs'] == []
    value['query_concepts'].pop()
    with pytest.raises(ValueError, match='exactly match'):
        module.validate_action_catalogue(value, [], ['purpose:applicable', 'purpose:performance'])


def test_unknown_concept_and_nonsearch_context_rejected():
    module = MODULES['compact']['plan']; value = plan()
    value['query_concepts'][0] = 'made-up-concept'
    with pytest.raises(Exception): module.validate_action_catalogue(value, [], ['purpose:applicable', 'purpose:performance'])
    value = plan(); value.update(mode='BROWSE', queries=[], query_concepts=['purpose:applicable'])
    with pytest.raises(ValueError): module.validate_action_catalogue(value, [], ['purpose:applicable'])


def test_graph_recall_sql_and_read_guard_are_byte_identical_to_parent():
    for arm in ['compact', 'combined']:
        for rel in ['02_BACKEND/lawrag/core/investigation_graph.py', '02_BACKEND/lawrag/core/investigation_actions.py',
                    '02_BACKEND/semantic_runtime/fulltext.py', '02_BACKEND/semantic_runtime/legal_agent/source_recall.py',
                    '02_BACKEND/semantic_runtime/legal_agent/source_recall_global.py']:
            assert (FROZEN[arm] / rel).read_bytes() == (FROZEN['baseline'] / rel).read_bytes()
