"""Current-turn search plans must reach navigation; synthetic contracts only."""
from copy import deepcopy

import pytest

from semantic_runtime.legal_agent import law_navigation as ln
from semantic_runtime.legal_agent.source_recall import SourceRecall
from test_unit_fulltext_adaptive_read import tree, session
from test_law_grouped_navigation import prepared, reader


@pytest.fixture
def two_law_tree(tmp_path, term_glossary):
    import json
    import sqlite3
    from test_document_release import source
    from lawrag.pipeline.term_generation import build_generation
    from lawrag.core.legal_coordinate import find_coordinates
    from semantic_runtime import unit_fulltext
    raw = source(tmp_path/'raw.sqlite', [
        ('d', '모의승인규정', ['승인 기준의 원문']),
        ('other', '다른규정', ['별도 원문'])])
    with sqlite3.connect(raw) as db:
        for did, uid, text in db.execute('SELECT document_id,unit_id,json FROM source_unit').fetchall():
            unit = json.loads(text)
            coordinate = find_coordinates(unit['surface'])[0].coordinate
            unit.update(title='승인' if did == 'd' else '별도',
                legal_coordinate=coordinate.as_dict(), coordinate_scope='body',
                coordinate_key='body:'+coordinate.canonical_surface())
            db.execute('UPDATE source_unit SET json=? WHERE document_id=? AND unit_id=?',
                (json.dumps(unit, ensure_ascii=False), did, uid))
    build_generation(raw, term_glossary, tmp_path/'built', serving=True)
    gen = tmp_path/'built/generation'
    index = tmp_path/'unit-index'
    unit_fulltext.build(gen, gen/'navigation', index, workers=1)
    return gen, unit_fulltext.UnitFulltextIndex(index, json.loads((gen/'navigation/manifest.json').read_text()))


def test_user_replan_uses_new_catalogue_even_when_goal_and_scope_are_unchanged(session):
    native, _ = session
    s = native.sources
    first = prepared(s)
    first['query_plan'] = {'law_names': [], 'queries': ['긴급 승인 예외']}
    old = ln.Investigation(s, '긴급 승인 예외', first, reader, 120, None, None)
    saved = deepcopy(old.p)
    s.law_search_queries = ['보고']
    second = SourceRecall(s).prepare()
    second['query_plan'] = {'law_names': [], 'queries': ['보고']}
    assert second['law_navigation']['query_fingerprint'] != saved['catalogue']['query_fingerprint']
    s.investigation_prior_route = True
    current = ln.Investigation(s, '긴급 승인 예외', second, reader, 120, saved, None)
    assert current.p['catalogue'] == second['law_navigation']
    assert current.p['law_page'] == second['law_navigation']['law_page']
    assert current.p['query_surface_history'] == [['보고']]
    assert saved == old.p  # The old, completed route is immutable history.


def test_same_plan_user_reentry_retains_navigation(session):
    native, _ = session
    s = native.sources
    rec = prepared(s)
    old = ln.Investigation(s, '긴급 승인 예외', rec, reader, 120, None, None)
    old.p['notes'] = '현재 질문에서 확인한 메모'
    s.investigation_prior_route = True
    current = ln.Investigation(s, '긴급 승인 예외', rec, reader, 120, deepcopy(old.p), None)
    assert current.p['notes'] == old.p['notes']
    assert current.p['catalogue'] == old.p['catalogue']
    assert current.p['reopened']['reason'] == 'USER_REENTRY'


def test_previous_question_documents_remain_hints_not_direct_targets(session):
    native, _ = session
    s = native.sources
    s.law_search_queries = ['미존재대상']
    s.investigation_hints = {'origin': 'PREVIOUS_QUESTION_IN_SESSION',
        'previous_question': '다른 이전 질문', 'document_ids': ['d']}
    rec = prepared(s)
    # Use an authorized document which was not a current search hit.
    did = next(d for d in s.scope if d not in {r['document_id'] for r in rec['law_navigation']['law_page']['items']})
    s.investigation_hints['document_ids'] = [did]
    inv = ln.Investigation(s, '새 질문', rec, reader, 120, None, None)
    assert inv.p['prior_investigation']['document_ids'] == [did]
    assert did not in {law['document_id'] for law in inv.p['laws'].values()}
    assert not inv.p['direct_laws']


def test_resume_rejects_a_changed_entry_plan_and_preserves_saved_state(session):
    from semantic_runtime.legal_agent.errors import ContractError
    native, _ = session
    s = native.sources
    rec = prepared(s)
    rec['query_plan'] = {'law_names': [], 'queries': ['승인']}
    old = ln.Investigation(s, '관리 기준', rec, reader, 120, None, None)
    saved = deepcopy(old.p)
    changed = {**rec, 'query_plan': {'law_names': [], 'queries': ['보고']}}
    with pytest.raises(ContractError, match='entry plan changed'):
        ln.Investigation(s, '관리 기준', changed, reader, 120, saved, None)
    assert saved == old.p


def test_same_request_search_retains_entry_plan_and_budget(session):
    from semantic_runtime.legal_agent.source_selection import select_sources
    from test_law_grouped_navigation import decide
    native, _ = session
    s = native.sources
    rec = prepared(s)
    plan = {'law_names': [], 'queries': ['승인']}
    rec['query_plan'] = plan
    saved = []

    def research(system, data, schema, phase, timeout):
        action = next(a for a in data['actions'] if a['action'] == 'RESEARCH')
        value = decide(data, 'RESEARCH', action['id'])
        value['queries'] = ['보고']
        return value

    result = select_sources('관리 기준', rec, research, session=s, remaining_seconds=120,
        on_checkpoint=lambda p: saved.append(deepcopy(p)))
    assert result['needs_fulltext']
    s.law_search_queries = ['보고']
    new = {**SourceRecall(s).prepare(), 'query_plan': plan}
    budget = s.repo.budget()
    resumed = ln.Investigation(s, '관리 기준', new, reader, 120, saved[-1], None)
    assert resumed.p['catalogue']['queries'] == ['보고']
    assert resumed.p['entry_plan_hash'] == saved[-1]['entry_plan_hash']
    assert len(resumed.p['query_history']) == 2
    assert resumed.p['decisions'] == saved[-1]['decisions']
    assert s.repo.budget() == budget


def test_current_request_survives_navigation_and_compact_model_input(session, monkeypatch):
    from semantic_runtime.legal_agent import decision_projection as dp
    from semantic_runtime.legal_agent import completion_contracts as cc
    from semantic_runtime.legal_agent.navigation_input import compact_cards, expand_cards
    native, _ = session
    s = native.sources
    rec = prepared(s)
    s.profile['candidate_navigation'].update(investigation_control=True,
        completion_contract=True, completion_policy_version=cc.V8, compact_input=True)
    request = '기존 승인 말고 다른 관리 대상의 근거도 찾아줘.'
    rec['current_request'] = request
    inv = ln.Investigation(s, '승인 기준 조사', rec, reader, 120, None, None)
    data, actions = inv.view()
    assert data['current_request'] == request
    seen = []

    class Captured(Exception):
        pass

    def capture(system, view, schema, phase, timeout):
        seen.append(expand_cards(compact_cards(view)))
        raise Captured()

    inv.invoke = capture
    with pytest.raises(Captured):
        dp.choose_read(inv, data, actions, 'source-law-navigation-1')
    assert seen[0]['current_request'] == request
    assert seen[0]['request'] == '승인 기준 조사'


@pytest.mark.parametrize('new_question', [False, True])
def test_actual_api_reads_a_different_document_on_next_turn(tmp_path, two_law_tree, new_question):
    import json
    import sqlite3
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.shortcut_store import selected_store
    from semantic_runtime.legal_agent.navigation_input import expand_cards
    from test_assessment_source_reply import EmptyAssessment
    from test_memory_runtime_v2 import command
    from test_bounded_source_main import settings
    from test_legal_agent_double_harness import ROOT, wire
    class Transport(EmptyAssessment):
        def __init__(self):
            super().__init__('repaired')
            self.views = []

        def send_once(self, *, body, ticket):
            view = expand_cards(json.loads(body['messages'][1]['content'])['view'])
            phase = view.get('source_stage', view.get('phase'))
            if phase.startswith('memory-intent'):
                self.phases.append(phase)
                utterance = view['current_request']
                return wire({'purpose': '관리 기준 조사', 'concepts': ['승인'], 'background_quotes': [],
                    'issues': [{'id': 'Q1', 'question': utterance, 'request_quote': utterance,
                                'subject': '관리 기준', 'kind': 'OTHER'}]})
            if '-read-choice' in phase:
                self.phases.append(phase)
                self.views.append(deepcopy(view))
                if view['sources']:
                    return wire({'choice': 'FINISH', 'basis_refs': [s['id'] for s in view['sources']],
                        'issue_refs': [i['id'] for i in view['issues']], 'evidence_sufficient': False,
                        'reason': '실제 확보 원문을 확인'})
                if view['read_candidates']:
                    return wire({'choice': 'READ', 'selections': [{
                        'target': view['read_candidates'][0]['target'], 'issue_id': view['issues'][0]['id'],
                        'missing_need': '현재 검색 결과의 원문', 'relation': 'DIRECT', 'source_ref': None}]})
                option = next((o for o in view['tool_options'] if o['choice'] == 'OPEN_LAW'), None)
                if option:
                    return wire({'choice': 'OPEN_LAW', 'target': option['target'],
                        'issue_id': view['issues'][0]['id'], 'missing_need': '검색된 다른 규정 열람',
                        'relation': 'DIRECT', 'source_ref': None})
                return wire({'choice': 'PENDING', 'reason': '현재 검색 결과 없음'})
            return super().send_once(body=body, ticket=ticket)

    generation, index = two_law_tree
    transport = Transport()
    transport.command = command('CASE_START', document_scope_mode='AUTHORIZED',
        task='관리 기준 조사', queries=['승인'], facts=[])
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000,
        'request_entry_policy': 'legacy', 'candidate_navigation': {
            'mode': 'law-first-v1', 'investigation_control': True, 'completion_contract': True,
            'completion_policy_version': 'investigation-completion-v8', 'compact_input': True,
            'structure_first': True, 'selectable_search': True, 'answer_first': True,
            'assessment_reentry_limit': 0}}
    runtime = tmp_path/'runtime'
    def app():
        value = create_app(tmp_path, generation, contracts_root=ROOT, provider=object(),
            implementation='legal-agent-unified-v6', legal_agent_profile=profile,
            legal_agent_transport=transport, runtime_root=runtime,
            memory_identity=lambda _: {'team_id': 'risk_team', 'document_ids': ['d', 'other']})
        value.state.pipeline.term_agent.unit_fulltext = index
        return value

    body = {'question': '승인 기준을 찾아줘.', 'session_id': 'different-laws', 'request_id': 'r1'}
    with TestClient(app()) as api:
        response = api.post('/v1/rag/ask', json=body)
        assert response.status_code == 200, response.text
        first = response.json()
        question = '완전히 별개로 별도 원문을 찾아줘.' if new_question else '같은 조사에서 별도 원문도 찾아줘.'
        transport.command = (command('CASE_START', document_scope_mode='AUTHORIZED',
            task='별도 원문 조사', queries=['별도'], facts=[]) if new_question else
            command('RESEARCH_REPLAN', target=first['question_id'], queries=['별도']))
        second_body = {**body, 'question': question, 'request_id': 'r2'}
        transport.views.clear()
        response = api.post('/v1/rag/ask', json=second_body)
        assert response.status_code == 200, response.text
        second = response.json()
        assert (second['question_id'] != first['question_id']) is new_question
        assert transport.views and all(v['current_request'] == question for v in transport.views)
        assert '별도 원문' in second['answer']['text']
        count = len(transport.phases)
        duplicate = api.post('/v1/rag/ask', json=second_body)
        assert duplicate.status_code == 200 and duplicate.json()['answer'] == second['answer']
        assert len(transport.phases) == count
    # Reopening the application must recover the result without new model work.
    with TestClient(app()) as api:
        resumed = api.post('/v1/rag/ask', json=second_body)
        assert resumed.status_code == 200 and resumed.json()['answer'] == second['answer']
        assert len(transport.phases) == count
    with sqlite3.connect(selected_store(runtime)) as db:
        selection = json.loads(db.execute("SELECT n.payload FROM head h JOIN node n ON n.id=h.node "
            "WHERE h.goal=? AND h.stage='SELECT'", (second['question_id'],)).fetchone()[0])
        assert {r['document_id'] for r in selection['selected_originals']} == {'other'}
        assert selection['investigation_state']['catalogue']['queries'] == ['별도']
        if new_question:
            assert all('d' not in {d['document_id'] for d in v['document_structures']} for v in transport.views)
