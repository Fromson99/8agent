"""Execution omissions, distinct from legal uncertainty; no external model."""
from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.legal_agent import request_repair as rr, output_contract as oc
from semantic_runtime.legal_agent import tool_availability as availability
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from test_output_contract_recovery import Journal
from test_main50_request_repair import tree, session, GAP


@pytest.fixture
def case(monkeypatch):
    span = {'document_id': 'd', 'block_id': 'b2', 'start_cp': 0, 'end_cp': 10}
    gap = {'gap_id': 'G1', 'gap_key': 'K1', 'material': True, 'kind': 'MISSING_SOURCE',
           'missing_target': '모의승인규정 제2조', 'target_binding': {
               'status': 'EXACT', 'source_ids': ['s2'], 'expected': [span]}}
    action = {'id': 'T2', 'action': 'READ_ARTICLES', 'identity': {'document_id': 'd', 'source_id': 's2'}}
    current = {'action_receipts': [{'action': 'TARGET_STRUCTURE_LOOKUP', 'status': 'COMPLETED',
               'gap_ids': ['G1'], 'targets': [], 'outcome': {'status': 'EXACT'}}]}
    state = {'basis_history': {}, 'selected': {}}
    budget = {'model_limit': 10, 'finalization_reserve': 2, 'model_reserved': 4}
    investigation = S(modern=True, p=state, current_gap_round=lambda: current,
                     s=S(repo=S(budget=lambda: budget), profile={'selection_time_reserve_seconds': 20}),
                     left=lambda: 100)
    data = {'sources': [], 'assessment_gaps': [gap],
            'gap_targets': [{'gap_id': 'G1', 'read_actions': ['T2'], 'navigation_actions': []}]}
    monkeypatch.setattr(availability, 'navigation_reason', lambda inv, action, data: action.get('blocked'))
    return investigation, data, {'T2': action}, {'next_action': 'FINISH', 'gap_resolutions': []}


def check(case):
    inv, data, actions, decision = case
    return rr.validate_unattempted_gap_finish(inv, decision, data, actions)


def conflict(case):
    with pytest.raises(oc.OutputContractError) as caught: check(case)
    assert caught.value.category == 'DECISION_CONFLICT' and rr.is_unattempted_gap(caught.value)
    return caught.value


def test_exact_lookup_is_not_a_read_and_validation_is_pure(case):
    inv, data, actions, decision = case
    before = deepcopy([inv.p, inv.current_gap_round(), data, actions, decision])
    error = conflict(case)
    assert error.issues[0]['expected_constraint']['unattempted_gaps'][0]['available_actions'] == ['T2']
    assert before == [inv.p, inv.current_gap_round(), data, actions, decision]


@pytest.mark.parametrize('change', ['read', 'legacy', 'no_round', 'not_material', 'fact', 'unknown_target',
                                   'no_handle', 'forbidden', 'tool_budget', 'not_needed', 'presented', 'acquired'])
def test_no_forced_research_for_legitimate_limits_or_delivered_originals(case, change):
    inv, data, actions, decision = case
    if change == 'read': decision['next_action'] = 'READ_ARTICLES'
    elif change == 'legacy': inv.modern = False
    elif change == 'no_round': inv.current_gap_round = lambda: None
    elif change == 'not_material': data['assessment_gaps'][0]['material'] = False
    elif change == 'fact': data['assessment_gaps'][0]['kind'] = 'MISSING_FACT'
    elif change == 'unknown_target': data['gap_targets'] = []
    elif change == 'no_handle': actions.clear()
    elif change in ('forbidden', 'tool_budget'): actions['T2']['blocked'] = change
    elif change == 'not_needed': decision['gap_resolutions'] = [{'gap_id': 'G1', 'status': 'NOT_NEEDED', 'reason': '재검토 이유'}]
    else:
        spans = deepcopy(data['assessment_gaps'][0]['target_binding']['expected'])
        if change == 'presented': data['sources'] = [{'document_id': 'd', 'spans': spans}]
        else: inv.p['selected'] = {'B2': {'document_id': 'd', 'evidence': [{'spans': spans}]}}
    assert check(case) is None


@pytest.mark.parametrize('status', ['COMPLETED', 'FAILED'])
def test_matching_attempt_is_preserved_without_claiming_resolution(case, status):
    inv, data, actions, _ = case
    receipt = {'action': 'READ_ARTICLES', 'status': status, 'targets': [deepcopy(actions['T2'])], 'gap_ids': []}
    inv.current_gap_round()['action_receipts'].append(receipt)
    assert check(case) is None
    assert data['assessment_gaps'][0]['kind'] == 'MISSING_SOURCE'


def test_unrelated_read_and_unresolved_label_do_not_hide_omission(case):
    inv, _, actions, decision = case
    wrong = deepcopy(actions['T2']); wrong['id'] = 'T1'; wrong['identity']['source_id'] = 's1'
    inv.current_gap_round()['action_receipts'].append({'action': 'READ_ARTICLES', 'status': 'COMPLETED',
                                                    'targets': [wrong], 'gap_ids': ['G1']})
    decision['gap_resolutions'] = [{'gap_id': 'G1', 'status': 'UNRESOLVED', 'reason': '미확인'}]
    conflict(case)


@pytest.mark.parametrize('matches', [True, False])
def test_completed_exact_absence_does_not_force_another_lookup(case, matches):
    inv, data, _, _ = case
    receipt = inv.current_gap_round()['action_receipts'][0]
    receipt['outcome'] = {'target_key': 'K1' if matches else 'other', 'absence_proven': True}
    if matches: assert check(case) is None
    else: conflict(case)
    assert data['assessment_gaps'][0]['kind'] == 'MISSING_SOURCE'


def test_one_reconsidered_gap_does_not_erase_another(case):
    _, data, _, decision = case
    second = deepcopy(data['assessment_gaps'][0]); second['gap_id'] = 'G2'
    data['assessment_gaps'].append(second)
    data['gap_targets'].append({**data['gap_targets'][0], 'gap_id': 'G2'})
    decision['gap_resolutions'] = [{'gap_id': 'G1', 'status': 'NOT_NEEDED', 'reason': '재판단'}]
    error = conflict(case)
    assert [g['gap_id'] for g in error.issues[0]['expected_constraint']['unattempted_gaps']] == ['G2']


@pytest.mark.parametrize('mode', ['repair', 'repeat', 'model_budget', 'time_budget'])
def test_existing_owner_repairs_once_and_restart_keeps_budget(case, tmp_path, mode):
    inv, data, actions, decision = case
    path = tmp_path / 'journal.sqlite'; repo = Journal(path); calls = []
    if mode == 'model_budget': inv.s.repo.budget()['model_reserved'] = 7
    if mode == 'time_budget': inv.left = lambda: 20
    def invoke(payload, attempt):
        calls.append(deepcopy(payload))
        if attempt:
            assert payload['sources'] == data['sources']
            assert payload['repair_contract']['same_evidence_scope']
            assert payload['repair_contract']['validation']['issues'][0]['code'] == rr.UNATTEMPTED_GAP
        return {**decision, 'next_action': 'READ_ARTICLES' if attempt and mode == 'repair' else 'FINISH'}
    def run():
        return oc.bounded_decision(repo, 'read-choice', data, {}, invoke,
            lambda value: rr.validate_unattempted_gap_finish(inv, value, data, actions),
            can_repair=lambda: rr.gap_review_capacity(inv) is None)
    if mode == 'repair': assert run()['next_action'] == 'READ_ARTICLES'
    else:
        with pytest.raises(ProposalError): run()
    assert len(calls) == (1 if mode.endswith('budget') else 2)
    repo.db.close(); repo = Journal(path)
    if mode == 'repair': assert run()['next_action'] == 'READ_ARTICLES'
    else:
        with pytest.raises(ProposalError): run()
    assert len(calls) == (1 if mode.endswith('budget') else 2)
    repo.db.close()


def test_availability_contract_error_is_not_a_semantic_retry(case, monkeypatch):
    def invalid(*_): raise ContractError('source binding mismatch')
    monkeypatch.setattr(availability, 'navigation_reason', invalid)
    with pytest.raises(ContractError): check(case)


@pytest.mark.parametrize('version', ['investigation-completion-v5', 'investigation-completion-v6',
                                   'investigation-completion-v7', 'investigation-completion-v8'])
def test_native_versions_and_canonical_owner_reconsider_once(session, monkeypatch, version):
    from semantic_runtime.legal_agent import law_navigation as nav, unit_reading as ur, decision_projection as dp
    from semantic_runtime.legal_agent import completion_contracts as cc
    from test_law_grouped_navigation import prepared, enable
    from test_unit_fulltext_adaptive_read import hit
    from test_investigation_completion_adr0678 import decision
    native, _ = session; s = native.sources; record = prepared(s)
    enable(s, investigation_control=True, completion_contract=True, completion_policy_version=version)
    s.profile['max_read_chars'] = 10000
    record['unit_reads'] = ur.acquire_batch(s, [hit(native, '3')], record['read_state'])
    record['unit_hits'] = [hit(native, '3')]
    inv = nav.Investigation(s, '모의승인규정 제1조 승인 기준', record, None, 120, None, None)
    first_data, first_actions = inv.view()
    target = next(k for k, a in first_actions.items() if a['action'] == 'READ_SCOPE' and a['identity'].get('scope') == 'exact:3')
    selected = decision(first_data, 'READ_SCOPE', target)
    selected['basis_refs'] = []
    if version != cc.V5:
        selected['exploration'] = [{'target': target, 'issue_id': 'Q1', 'request_quote': inv.question,
                                    'missing_need': '모의 목 원문 확인', 'relation': 'DIRECT', 'source_quote': ''}]
    inv.validate(selected, first_data, first_actions)
    inv.execute(selected, first_data, first_actions)
    gap = rr.bind_gap(GAP, s); gap.update(gap_id=nav.gap_id(gap), gap_key=cc.gap_key(gap))
    inv.p['assessment_gaps'] = [gap]; inv.open_gap_round()
    data, actions = inv.view(); initial = decision(data, 'FINISH')
    with pytest.raises(oc.OutputContractError) as caught: inv.validate(initial, data, actions)
    assert rr.is_unattempted_gap(caught.value)
    inv.p['state_version'] += 1
    with pytest.raises(ContractError, match='stale'): inv.validate(initial, data, actions)
    inv.p['state_version'] -= 1
    calls = []
    monkeypatch.setattr(dp, 'choose_read', lambda *_: None)  # Exercise the existing alternate owner.
    def invoke(system, payload, schema, phase, timeout):
        calls.append(deepcopy(payload))
        value = deepcopy(initial)
        if len(calls) == 2:
            assert payload['repair_contract']['validation']['issues'][0]['code'] == rr.UNATTEMPTED_GAP
            value['gap_resolutions'] = [{'gap_id': gap['gap_id'], 'status': 'NOT_NEEDED',
                                        'reason': '모의 재검토: 확보한 목의 규칙으로 범위를 제한한다.',
                                        'basis_refs': [], 'action_refs': []}]
        return value
    inv.invoke = invoke
    value = inv.request_decision(data, actions, 'canonical-gap-review')
    assert value['gap_resolutions'][0]['status'] == 'NOT_NEEDED'
    assert len(calls) == 2
    again = nav.Investigation(s, inv.question, record, invoke, 120, deepcopy(inv.p), None)
    assert again.request_decision(data, actions, 'canonical-gap-review') == value
    assert len(calls) == 2
