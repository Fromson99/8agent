"""A source goal and a selector propose different routes on the same menu."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from jsonschema import validate

from lawrag.core.legal_coordinate import find_coordinates
from semantic_runtime.legal_agent import investigation_supervisor as supervisor
from semantic_runtime.legal_agent import source_goal_control as goals
from semantic_runtime.legal_agent.answer_progress import ProgressHandoff
from semantic_runtime.legal_agent.completion_contracts import obj
from semantic_runtime.legal_agent.errors import ContractError, TransportError
from semantic_runtime.legal_agent.law_navigation import decision_schema


@pytest.fixture
def menu():
    issue = {'id': 'Q1', 'request_quote': '위임된 기준은?'}
    data = {'presentation_id': 'P1', 'issues': [issue], 'branches': [], 'basis': [],
            'laws': [{'id': 'L1', 'document_id': 'd', 'name': '규정'}],
            'sources': [{'id': 'E1', 'text': '세부 기준은 다음 조문에 따른다.'}]}
    actions = {target: {'id': target, 'label': unit, 'action': 'READ_ARTICLES',
                        'identity': {'document_id': 'd', 'unit_id': unit}}
               for target, unit in [('A', '1'), ('B', '2')]}
    actions['L'] = {'id': 'L', 'label': '위치 조회', 'action': 'SEARCH_STRUCTURE',
                    'identity': {'document_id': 'd'}}
    matcher = SimpleNamespace(sources={}, units={('d', n): {'coordinate_scope': 'body'} for n in ('1', '2')},
        stored_coordinates={('d', n): find_coordinates(f'제{n}조')[0].coordinate for n in ('1', '2')})
    repo = SimpleNamespace(budget=lambda: {'model_limit': 40, 'model_reserved': 0, 'finalization_reserve': 3},
                           event=lambda *_: None)
    inv = SimpleNamespace(p={'binding': 'bound'}, question=issue['request_quote'],
        policy={'supervisor_mode': 'enforce', 'source_goal_control': True},
        s=SimpleNamespace(scope={'d'}, matcher=matcher, profile={'selection_time_reserve_seconds': 30}, repo=repo),
        left=lambda: 200, save=lambda: None)
    native = decision_schema(data, actions, set())
    inv.validate = lambda decision, *_: validate(decision, native)
    def read(target):
        return {'choice': 'READ', 'selections': [{'target': target, 'issue_id': 'Q1',
            'missing_need': '위임 기준', 'relation': 'DIRECT', 'source_ref': None}]}
    target = {'document_ref': 'd', 'coordinate': '제2조', 'coordinate_scope': 'body',
              'issue_id': 'Q1', 'reason': '필요한 적용 기준'}
    progress = {'goals': [{'issue_id': 'Q1', 'status': 'NEEDS_SOURCE', 'answer_so_far': '위임은 확인했다.',
        'basis_refs': ['E1'], 'material_need': '위임 기준', 'next_answer_change': '기준 확인', 'previous_effect': 'INITIAL'}]}
    proposal = {**read('A'), 'source_targets': [target], 'source_goal_exclusions': [], 'answer_progress': progress}
    action_schema = obj({'choice': {'const': 'READ'}, 'selections': {'type': 'array', 'items': obj({
        'target': {'enum': ['A','B']}, 'issue_id': {'const': 'Q1'}, 'missing_need': {'type': 'string'},
        'relation': {'const': 'DIRECT'}, 'source_ref': {'const': None}})}})
    payload = {**data, 'already_presented_reads': [{'document_id': 'd', 'coordinate': '제1조'}],
               'investigation_chain': {'steps': [{'action': 'READ_ARTICLES', 'status': 'COMPLETED',
        'outcome': '위임 문구 확인'}]}, 'previous_assessments': [{'reason': '기준 원문 미확보'}]}
    def expand(value):
        return goals.native_decision(inv, data, actions, value)
    def gate():
        return supervisor.gate(inv, data, actions, payload, proposal, expand(proposal),
            {'anyOf': [action_schema]}, expand, 'turn1')
    return SimpleNamespace(inv=inv, data=data, actions=actions, target=target, gate=gate,
                           old=expand(proposal), read=read, proposal=proposal, payload=payload)


def reviewer(menu, decisions):
    seen = []
    def invoke(prompt, body, schema, *_):
        seen.append(deepcopy(body))
        assert '직전 행동' in prompt
        assert body['answer_progress_context']['current_goals'] == menu.proposal['answer_progress']['goals']
        assert 'answer_progress' not in body['proposed_action']
        assert body['sources'] == menu.data['sources']
        assert body['already_presented_reads'] == menu.payload['already_presented_reads']
        assert body['previous_assessments'] == menu.payload['previous_assessments']
        assert body['investigation_chain'] == menu.payload['investigation_chain']
        assert body['proposed_action']['selections'][0]['target'] == 'A'
        assert body['execution_plan']['targets'] == ['B']
        assert supervisor.state_for(menu.inv, menu.data)['execution'] == {}
        output = {'reason': '위임 문구와 실제 조회 대상을 대조했다.', 'remaining_scope': '위임 기준',
                  'source_targets': [], **decisions[len(seen)-1]}
        validate(output, schema)
        return output
    menu.inv.invoke = invoke
    return seen


@pytest.mark.parametrize('directive', ['STOP_UNRESOLVED', 'ASSESS_NOW'])
def test_handoff_holds_goal_without_dispatch_even_on_restart(menu, directive):
    seen = reviewer(menu, [{'directive': directive, 'source_targets': [menu.target]}])
    with pytest.raises(ProgressHandoff, match=directive):
        menu.gate()
    menu.inv.p = json.loads(json.dumps(menu.inv.p))
    state = supervisor.state_for(menu.inv, menu.data)
    assert state['pending'] is None and state['source_goals'][0]['status'] == 'REQUIRED'
    assert state['source_goals'][0]['routes'] == [] and not state['execution']
    with pytest.raises(ProgressHandoff, match=directive):
        goals.preselect(menu.inv, menu.data, menu.actions)
    with pytest.raises(ContractError):
        supervisor.before_execute(menu.inv, menu.data, menu.old)
    assert len(seen) == 1


def test_confirming_the_primary_drops_unconfirmed_competing_goal(menu):
    seen = reviewer(menu, [{'directive': 'CONTINUE_TARGETED'}])
    assert menu.gate() == menu.old
    state = supervisor.state_for(menu.inv, menu.data)
    assert state['coverage_review'][-1]['discarded_execution_plan']['targets'] == ['B']
    assert state['source_goals'] == []
    assert goals.preselect(menu.inv, menu.data, menu.actions) == menu.old
    assert len(seen) == 1


def test_conflicting_directive_repaired_before_authorization_and_restored(menu):
    seen = reviewer(menu, [{'directive': 'CONTINUE_TARGETED', 'source_targets': [menu.target]},
        {'directive': 'REDIRECT', 'action': menu.read('B'), 'source_targets': [menu.target]}])
    accepted = menu.gate()
    assert accepted['targets'] == ['B'] and len(seen) == 2
    assert seen[1]['correction_required']['reviewed_action']['targets'] == ['A']
    assert seen[1]['correction_required']['execution_plan']['targets'] == ['B']
    menu.inv.p = json.loads(json.dumps(menu.inv.p))
    assert goals.preselect(menu.inv, menu.data, menu.actions) == accepted
    with pytest.raises(ContractError):
        supervisor.before_execute(menu.inv, menu.data, menu.old)
    supervisor.before_execute(menu.inv, menu.data, accepted)
    assert supervisor.state_for(menu.inv, menu.data)['source_goals'][0]['routes'] == ['READ']
    assert len(seen) == 2


def test_repeated_conflict_stops_both_routes(menu):
    bad = {'directive': 'CONTINUE_TARGETED', 'source_targets': [menu.target]}
    seen = reviewer(menu, [bad, bad])
    with pytest.raises(ProgressHandoff, match='SUPERVISOR_UNRESOLVED'):
        menu.gate()
    state = supervisor.state_for(menu.inv, menu.data)
    assert not state['execution'] and not state.get('source_goal_actions')
    with pytest.raises(ProgressHandoff):
        menu.gate()
    assert len(seen) == 2


def test_unknown_review_cannot_resume_primary_or_goal(menu):
    def unknown(*_):
        raise TransportError('unknown', unknown=True)
    menu.inv.invoke = unknown
    with pytest.raises(TransportError):
        menu.gate()
    menu.inv.p = json.loads(json.dumps(menu.inv.p))
    menu.inv.invoke = lambda *_: pytest.fail('unknown outcome must not be resent')
    with pytest.raises(TransportError):
        menu.gate()
    assert not supervisor.state_for(menu.inv, menu.data)['execution']


@pytest.mark.parametrize('bound', ['deadline', 'model_budget', 'review_budget'])
def test_no_unchecked_fallback_when_review_cannot_run(menu, bound):
    if bound == 'deadline':
        menu.inv.left = lambda: 30
    elif bound == 'model_budget':
        menu.inv.s.repo.budget = lambda: {'model_limit': 4, 'model_reserved': 1, 'finalization_reserve': 3}
    else:
        state = supervisor.state_for(menu.inv, menu.data)
        state['calls'] = 2
        supervisor.save(menu.inv, state)
    menu.inv.invoke = lambda *_: pytest.fail('no review capacity')
    with pytest.raises(ProgressHandoff, match='BOUNDED_HANDOFF'):
        menu.gate()
    assert not supervisor.state_for(menu.inv, menu.data)['execution']


def test_restored_decision_rejects_changed_target_identity(menu):
    reviewer(menu, [{'directive': 'REDIRECT', 'action': menu.read('B'), 'source_targets': [menu.target]}])
    menu.gate()
    menu.actions['B']['identity']['unit_id'] = '9'
    with pytest.raises(ContractError, match='menu changed'):
        goals.preselect(menu.inv, menu.data, menu.actions)


def test_continue_cannot_supply_a_different_action(menu):
    def contradict(*_):
        return {'directive': 'CONTINUE_TARGETED', 'reason': '계속', 'remaining_scope': '원문 확인',
                'source_targets': [], 'action': menu.read('B')}
    menu.inv.invoke = contradict
    with pytest.raises(ProgressHandoff, match='SUPERVISOR_UNRESOLVED'):
        menu.gate()
    assert not supervisor.state_for(menu.inv, menu.data)['execution']


def test_review_page_movement_does_not_approve_original_read_on_hidden_page(menu):
    from semantic_runtime.contracts import digest
    from semantic_runtime.legal_agent import read_candidate_pages as pages
    menu.inv.policy.update(minimal_input=True, read_candidate_page_size=1)
    menu.payload['read_candidates'] = [{'target': 'A'}, {'target': 'B'}]
    menu.inv.p['read_candidate_pager'] = {'binding': digest(menu.payload), 'page': 0, 'sequence': 0}
    pages_seen = []
    def select(prompt, body, schema, *_):
        pages_seen.append(body['read_candidate_page']['page'])
        result = {'reason': '다음 페이지의 필요 원문 확인', 'remaining_scope': '위임 기준', 'source_targets': []}
        if len(pages_seen) == 1:
            return {**result, 'directive': 'REDIRECT', 'action': {'choice': pages.NEXT}}
        from jsonschema import Draft202012Validator
        assert not Draft202012Validator(schema).is_valid({**result, 'directive': 'CONTINUE_TARGETED'})
        return {**result, 'directive': 'REDIRECT', 'action': menu.read('B'), 'source_targets': [menu.target]}
    menu.inv.invoke = select
    assert menu.gate()['targets'] == ['B']
    assert pages_seen == [1, 2]
