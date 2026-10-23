"""Finite input-loss regressions at projection, wire and actual API boundaries."""
from conftest import term_glossary
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as S
import importlib.util
import json

import pytest
from semantic_runtime.legal_agent import decision_projection as dp, output_contract as oc
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.bounded_source_session import _Gateway, _Protocol
from semantic_runtime.legal_agent.navigation_input import NavigationReferences

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '06_TOOLS/EXPERIMENTS/adr_0885/test_focus.py').is_file())


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


unit = load('input_preservation_unit_fixture', '06_TOOLS/EXPERIMENTS/adr_0885/test_focus.py')
api = load('input_preservation_api_fixture', '06_TOOLS/EXPERIMENTS/adr_0892/test_focus.py')
tree = api.tree


def capture(monkeypatch, change):
    inv, data, actions, payloads, _ = unit.fixture(monkeypatch, unit.choice(queries=['승인 절차']))
    change(data, actions)
    before = deepcopy((data, actions))
    dp.choose_read(inv, data, actions, 'preservation-test')
    assert (data, actions) == before
    return payloads[0]


def wire(view):
    data = deepcopy(view) | {'input_projection': 'compact-selection-source-v3', 'source_stage': 'source-law-navigation-1-read-choice'}
    gateway = object.__new__(_Gateway)
    gateway.protocol = _Protocol({'type': 'object', 'properties': {}, 'additionalProperties': False})
    gateway.compact = True
    gateway.transport = S(binding={'model': 'synthetic'})
    gateway.profile = {'max_output_tokens': 500}
    gateway.system = 'contract test'
    codec = NavigationReferences(data)
    request = gateway.request('investigate', data, 'schema', references=codec)
    from semantic_runtime.legal_agent.navigation_input import expand_cards
    return expand_cards(codec.restore(json.loads(request['messages'][1]['content'])['view']))


@pytest.mark.parametrize('title', ['변경 절차', '예외・特例 😀 e\u0301', ''])
def test_stored_title_surface_preview_reach_actual_provider_wire(monkeypatch, title):
    def setup(data, actions):
        data['structure_catalogue'] = {'items': [{'document_id': 'D1', 'document_name': '모의 규정',
            'coordinate': '제10조', 'title': title, 'surface': '제10조(' + title + ')',
            'read_action': 'T1', 'preview': '예외에는 승인 후 통지한다.'}]}
    view = capture(monkeypatch, setup)
    row = wire(view)['read_candidates'][0]
    assert row['surface'] == '제10조(' + title + ')'
    assert row['preview'] == '예외에는 승인 후 통지한다.'
    assert row.get('title', '') == title
    assert row['document'] == '모의 규정'


@pytest.mark.parametrize('reverse', [False, True])
def test_duplicate_order_never_discards_nonempty_hints(monkeypatch, reverse):
    def setup(data, actions):
        rich = {'read_action': 'T1', 'article': '제10조 승인 절차', 'preview': '승인과 통지 필요'}
        sparse = {'read_action': 'T1', 'coordinate': '제10조', 'title': '승인 절차', 'preview': ''}
        data['laws'] = [{'id': 'L1', 'name': '모의 규정', 'document_id': 'D1', 'articles': [sparse, rich] if reverse else [rich, sparse]}]
        data['structure_catalogue'] = {'items': [sparse]}
    rows = wire(capture(monkeypatch, setup))['read_candidates']
    assert len(rows) == 1
    assert rows[0]['preview'] == '승인과 통지 필요' and rows[0]['article'] == '제10조 승인 절차'
    assert rows[0]['title'] == '승인 절차' and rows[0]['coordinate'] == '제10조'


def test_conflicting_hints_retained_once_without_semantic_arbitration(monkeypatch):
    def setup(data, actions):
        data['laws'] = [{'id': 'L1', 'document_id': 'D1', 'name': '모의 규정', 'articles': [{'read_action': 'T1', 'preview': x} for x in ['① 승인한다.', '② 통지한다.', '② 통지한다.']]}]
    row = wire(capture(monkeypatch, setup))['read_candidates'][0]
    assert row['preview'] == '① 승인한다.'
    assert row['additional_hints'] == [{'field': 'preview', 'value': '② 통지한다.'}]


def test_same_coordinate_in_distinct_document_or_range_never_merges(monkeypatch):
    def setup(data, actions):
        actions['T10'] = {'id': 'T10', 'action': 'READ_ARTICLES', 'label': '다른 문서', 'identity': {'document_id': 'D2'}}
        actions['T11'] = {'id': 'T11', 'action': 'READ_ARTICLES', 'label': '다른 범위', 'identity': {'document_id': 'D1', 'scope': 'item-2'}}
        data['structure_catalogue'] = {'items': [
            {'document_id': d, 'coordinate': '제10조', 'read_action': t, 'title': name}
            for d, t, name in [('D1', 'T1', '승인'), ('D2', 'T10', '보고'), ('D1', 'T11', '예외')]]}
    rows = wire(capture(monkeypatch, setup))['read_candidates']
    assert len(rows) == 3 and len({row['target'] for row in rows}) == 3
    assert {row['title'] for row in rows} == {'승인', '보고', '예외'}


def test_wrong_document_hint_is_host_error_before_model(monkeypatch):
    inv, data, actions, calls, _ = unit.fixture(monkeypatch, unit.choice(queries=['q']))
    data['structure_catalogue'] = {'items': [{'document_id': 'D2', 'read_action': 'T1', 'title': '잘못된 문서'}]}
    with pytest.raises(ContractError, match='document'):
        dp.choose_read(inv, data, actions, 'contract')
    assert not calls


def test_unoffered_target_is_not_promoted_to_candidate(monkeypatch):
    def setup(data, actions):
        data['structure_catalogue'] = {'items': [{'read_action': 'UNAUTHORIZED', 'title': '권한 밖 원문'}]}
    view = capture(monkeypatch, setup)
    assert [r['target'] for r in view['read_candidates']] == ['T1']
    assert '권한 밖 원문' not in json.dumps(view, ensure_ascii=False)


@pytest.mark.parametrize('kind', ['READ_PARENT', 'READ_SCOPE', 'VIEW_SAVED_SOURCE'])
def test_branch_scope_page_and_path_distinguish_same_label_tools(monkeypatch, kind):
    def setup(data, actions):
        for n in (10, 11):
            target = 'T' + str(n)
            actions[target] = {'id': target, 'action': kind, 'label': '원문 이어보기',
                'identity': {'branch_id': 'G' + str(n), 'scope': 'S' + str(n), 'page': n}}
        data['actions'] = [{'id': 'T' + str(n), 'target_path': '문서 ' + str(n) + ' 제10조'} for n in (10, 11)]
        data['articles'] = [{'id': 'G10', 'read_options': [{'action': 'T10', 'label': '전체', 'extent': 'FULL', 'characters': 450}]}]
    rows = {r['target']: r for r in wire(capture(monkeypatch, setup))['tool_options']}
    assert rows['T10']['scope'] == {'branch_id': 'G10', 'scope': 'S10', 'page': 10}
    assert rows['T11']['scope']['page'] == 11
    assert rows['T10']['target_path'] == '문서 10 제10조'
    assert rows['T11']['target_path'] == '문서 11 제10조'
    assert rows['T10']['read_extent'] == {'label': '전체', 'extent': 'FULL', 'characters': 450}


def test_return_retains_frame_search_and_saved_original_context(monkeypatch):
    def setup(data, actions):
        actions['T7']['identity'] = {'frame_id': 'H1'}
        data['return_points'] = [{'id': 'H1', 'number': 1, 'kind': 'NAVIGATION', 'search_queries': ['승인 절차'],
                                 'laws': ['모의 규정'], 'originals': ['제10조'], 'private_unrelated': 'not input'}]
    row = next(r for r in wire(capture(monkeypatch, setup))['tool_options'] if r['target'] == 'T7')
    assert row['scope']['frame_id'] == 'H1'
    assert row['return_context'] == {'number': 1, 'kind': 'NAVIGATION', 'search_queries': ['승인 절차'], 'laws': ['모의 규정'], 'originals': ['제10조']}


def test_original_exception_and_paragraph_boundaries_are_unchanged(monkeypatch):
    original = '① 허용한다. 다만 예외에는 적용하지 않는다.\n② 통지해야 한다.'
    def setup(data, actions):
        data['sources'] = [{'id': 'E1', 'text': original}]
    view = capture(monkeypatch, setup)
    assert view['sources'][0]['text'] == wire(view)['sources'][0]['text'] == original


def test_one_selection_can_still_read_four_targets(monkeypatch):
    selection = lambda target: {'target': target, 'issue_id': 'Q1', 'missing_need': '필요 원문', 'relation': 'DIRECT', 'source_ref': None}
    inv, data, actions, calls, _ = unit.fixture(monkeypatch, {'choice': 'READ', 'selections': [selection('R' + str(n)) for n in range(4)]})
    for n in range(4):
        actions['R' + str(n)] = {'id': 'R' + str(n), 'action': 'READ_ARTICLES', 'identity': {'document_id': 'D1'}, 'label': '범위 ' + str(n)}
    out = dp.choose_read(inv, data, actions, 'batch')
    assert out['targets'] == ['R0', 'R1', 'R2', 'R3'] and len(calls) == 1


def test_actual_api_calls_same_projection_and_publishes_original(tmp_path, tree, monkeypatch):
    calls = []
    original = dp.read_candidate_rows
    def observed(data, candidates, matcher=None):
        rows = original(data, candidates, matcher)
        calls.append({'rows': len(rows), 'offered': len(candidates)})
        return rows
    monkeypatch.setattr(dp, 'read_candidate_rows', observed)
    import semantic_runtime.app as app_module
    create = app_module.create_app
    def current_fixture(*args, **kwargs):
        kwargs['memory_identity'] = lambda _: {'team_id': 'test_team', 'document_ids': ['d']}
        kwargs['legal_agent_transport'].direct_note = False
        return create(*args, **kwargs)
    monkeypatch.setattr(app_module, 'create_app', current_fixture)
    # Use the current SpanTransport fixture; ADR0892's historical wrapper removes required assessment reasons.
    api.prior.test_compact_assessment_without_navigation_publishes_through_api(tmp_path, tree)
    assert calls and any(c['rows'] > 0 for c in calls)
