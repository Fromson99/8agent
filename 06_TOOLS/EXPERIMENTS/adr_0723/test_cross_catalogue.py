"""Read-only diagnostic discovered after model run freeze; no product mutation."""
from test_main50_request_repair import *


def test_exact_gap_outside_current_catalogue_executes_original_read(session):
    native, _ = session
    investigation = modern(native)
    gap = rr.bind_gap(GAP, investigation.s)
    gap.update(gap_id=ln.gap_id(gap), gap_key=cc.gap_key(gap))
    investigation.p.update(laws={}, groups={}, selected={}, direct_laws=[], window_groups=[])
    investigation.p['law_page']['items'] = []
    investigation.p['structure_page']['items'] = []
    investigation.p['assessment_gaps'] = [gap]
    investigation.open_gap_round()
    data, actions = investigation.view()
    target = data['gap_targets'][0]['read_actions'][0]
    value = decision(data, 'READ_ARTICLES', target)
    investigation.validate(value, data, actions)
    investigation.execute(value, data, actions)
    assert investigation.p['selected']
    assert not inv.originals_for(investigation.s, investigation.p)


def test_accepted_batch_resume_keeps_completed_target_receipts(session, monkeypatch):
    native, _ = session
    investigation = modern(native)
    gap = rr.bind_gap(GAP, investigation.s)
    gap.update(gap_id=ln.gap_id(gap), gap_key=cc.gap_key(gap))
    investigation.p['assessment_gaps'] = [gap]
    investigation.open_gap_round()
    data, actions = investigation.view()
    first = data['gap_targets'][0]['read_actions'][0]
    actions['second'] = {**deepcopy(actions[first]), 'id': 'second'}
    actions['second']['identity']['unit_id'] = '1'
    value = decision(data, 'READ_ARTICLES', first)
    value['targets'] = [first, 'second']
    from semantic_runtime.contracts import digest
    investigation.p['accepted'] = {'input_hash': digest(data), 'decision': value,
        'phase': 'test-batch', 'data': data, 'actions': actions,
        'before': deepcopy(investigation.p)}
    acquired = []
    original = ur.acquire_batch
    def acquire(source, hits, state):
        acquired.append(hits[0]['unit_id'])
        if len(acquired) == 2:
            raise RuntimeError('synthetic interruption after first target checkpoint')
        return original(source, hits, state)
    monkeypatch.setattr(ur, 'acquire_batch', acquire)
    investigation.invoke = lambda *args: pytest.fail('already accepted decision must not call model')
    with pytest.raises(RuntimeError, match='synthetic interruption'):
        investigation.run()
    plan = next(iter(investigation.p['read_plans'].values()))
    assert first in plan['completed']
    again = modern(native, deepcopy(investigation.p))
    again.request_decision = lambda data, actions, phase: decision(data, 'PENDING')
    again.bounded_result = lambda reason: {'bounded': reason}
    assert again.run() == {'bounded': 'MODEL_PENDING'}
    assert acquired == ['0', '1', '1']
    assert next(iter(again.p['read_plans'].values()))['status'] == 'ACQUIRED'


def test_equivalent_failed_search_is_not_an_alternate_route(session):
    native, _ = session
    investigation = modern(native)
    data, actions = investigation.view()
    target = next(k for k, action in actions.items() if action['action'] == 'SEARCH_STRUCTURE')
    value = decision(data, 'SEARCH_STRUCTURE', target)
    value['queries'] = ['제1조']
    investigation.p['tool_failures'] = [{'operation_key': rr.operation_key(value, actions)}]
    with pytest.raises(ProposalError, match='same failed'):
        rr.validate_failed_operation(investigation, {**value, 'queries': [' 제 1 조 ']}, actions)


def test_recoverable_failure_invalidates_pre_failure_state_version(session):
    native, _ = session
    investigation = modern(native)
    data, actions = investigation.view()
    value = decision(data, 'READ_PARENT', data['articles'][0]['read_parent_action'])
    version = investigation.p['state_version']
    def fail(*args):
        raise TimeoutError('synthetic source timeout')
    investigation.execute_tool = fail
    assert investigation.execute(value, data, actions) is False
    assert investigation.p['state_version'] == version + 1
