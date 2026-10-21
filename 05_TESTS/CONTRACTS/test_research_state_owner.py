"""State ownership boundaries, with no model calls or corpus loading."""
from copy import deepcopy
import json

import pytest

from semantic_runtime.contracts import digest
from semantic_runtime.research_state import (
    ResearchLedger, NativeResearchTasks, OriginalProgress, need_id,
)
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent import request_repair


def setup_task(field='condition', side='external', query='조건 원문'):
    task = {'schema_version': 'comparison-research-v1', 'task_id': 'unassigned',
            'issue_id': 'i', 'target_side': side, 'requested_fields': [field],
            'missing_target': query, 'target_locator': None, 'anchor_refs': [],
            'operation': 'search_text', 'allowed_operations': ['search_text'],
            'completion_conditions': ['Read originals'], 'binding_hash': 'bound'}
    proposal = {'priority': 'CORE', 'priority_reason': '직접 요구', 'reason': '조건 확인'}
    return task, proposal


def ledger_with_need():
    board = {'tasks': {}, 'round': 0, 'reviewed': [], 'rows': {}}
    ledger = ResearchLedger(board)
    row = {'status': 'PARTIAL', 'missing': '조건 원문 미확보', 'text': '일부 확인',
           'citations': [{'evidence': 'E1', 'quote': '원문'}], 'dependencies': []}
    def compile_task(proposal):
        task, _ = setup_task(query=proposal['query'])
        return ledger.register(task, proposal, True)
    proposal = {'query': '조건 확인 / 조건 원문 미확보', 'priority': 'CORE',
                'priority_reason': '명시적으로 요청한 조건 원문', 'reason': '조건 확인'}
    task_id = compile_task(proposal)
    ledger.reconcile({'id': 'i', 'external_task': '조건 확인'}, 'condition', 'external',
                     row, 'review-1', [task_id], compile_task)
    return ledger, next(iter(board['tasks'].values()))


@pytest.mark.parametrize('status', ['COMPLETE', 'PARTIAL', 'FAILED'])
def test_child_execution_completion_does_not_resolve_parent_need_after_restart(status):
    ledger, record = ledger_with_need()
    previous = {'request_id': 'old', 'evidence_ids': ['E1']}
    ledger.begin(record, previous)
    child = {}
    receipts = NativeResearchTasks(child)
    seed = receipts.begin(record['task'])
    seed['completed'] = ['read-1']
    receipts.finish(seed, status)
    latest = {'request_id': 'new', 'evidence_ids': ['E1', 'E2'],
              'investigation_return': {'research_tasks': child['comparison_research']}}
    assert ledger.finish(record, latest, True)
    restored = ResearchLedger(json.loads(json.dumps(ledger.board)))
    assert restored.used_followups == 1
    assert restored.needs()[0]['status'] == 'OPEN'
    assert restored.needs()[0]['execution_state'] == 'ATTEMPT_RECORDED'
    assert restored.board['tasks'][record['task']['task_id']]['status'] == status
    context = restored.child_context('external', 'bound', record['task'])
    assert context['needs'][0]['missing'] == '조건 원문 미확보'
    assert context['attempts'][0]['new_evidence_ids'] == ['E2']
    assert context['used_followups'] == 1


def test_committed_receipt_is_idempotent_and_changed_receipt_is_rejected():
    ledger, record = ledger_with_need()
    ledger.begin(record, {'request_id': 'old', 'evidence_ids': ['E1']})
    latest = {'request_id': 'new', 'evidence_ids': ['E1'], 'investigation_return': {}}
    assert not ledger.finish(record, latest, True)
    before = deepcopy(ledger.board)
    assert not ledger.finish(record, latest, True)
    assert ledger.board == before
    with pytest.raises(ContractError, match='different receipt'):
        ledger.finish(record, {**latest, 'evidence_ids': ['fabricated']}, True)
    assert ledger.board == before


def test_partial_or_failed_reuse_keeps_each_need_and_spends_one_followup():
    ledger, record = ledger_with_need()
    task = deepcopy(record['task']);task['requested_fields'] = ['exceptions']
    _, proposal = setup_task()
    sibling_id = ledger.register(task, proposal, True)
    assert sibling_id != record['task']['task_id']
    ledger.begin(record, {'request_id': 'old', 'evidence_ids': ['E1']})
    latest = {'request_id': 'failed', 'evidence_ids': ['E1'], 'investigation_return': {}}
    assert not ledger.finish(record, latest, False)
    sibling = ledger.board['tasks'][sibling_id]
    assert sibling['status'] == record['status'] == 'FAILED'
    assert sibling['reused_acquisition'] and sibling['new_evidence'] == []
    assert ledger.used_followups == 1 and ledger.needs()[0]['status'] == 'OPEN'
    later = deepcopy(task);later['requested_fields'] = ['obligation']
    later_id = ledger.register(later, proposal, True)
    assert ledger.reuse(ledger.board['tasks'][later_id])
    assert ledger.used_followups == 1


def test_resume_keeps_original_evidence_basis_and_exhausted_budget():
    ledger, record = ledger_with_need()
    ledger.begin(record, {'request_id': 'first', 'evidence_ids': ['E1']})
    ledger.board['round'] = 2
    restored = ResearchLedger(json.loads(json.dumps(ledger.board)))
    resumed = restored.board['tasks'][record['task']['task_id']]
    assert restored.begin(resumed, {'request_id': 'later', 'evidence_ids': ['E9']}) == 'first'
    assert resumed['prior_evidence_ids'] == ['E1']
    assert not restored.available(2)
    assert resumed['need_basis'][need_id('i', 'condition', 'external')]


def test_native_identity_violation_does_not_rewrite_receipt():
    task, _ = setup_task()
    owner = NativeResearchTasks({})
    seed = owner.begin(task);owner.finish(seed, 'PARTIAL')
    before = deepcopy(owner.tasks)
    with pytest.raises(ContractError, match='identity reused'):
        owner.begin({**task, 'binding_hash': 'another-generation'})
    assert owner.tasks == before
    assert owner.terminal(owner.begin(task))


def test_progress_uses_same_owner_on_success_failure_and_restore():
    state = {'no_progress': 1, 'selected': {}, 'basis_history': {}}
    assert not request_repair.record_progress(state)
    assert OriginalProgress(state).advance(False)['unchanged_turns'] == 2
    state['selected'] = {'read': {'document_id': 'doc', 'evidence': [
        {'spans': [{'block_id': 'block', 'start_cp': 0, 'end_cp': 10}]}]}}
    assert request_repair.record_progress(state)
    assert OriginalProgress(state).advance(True)['unchanged_turns'] == 0
    restored = json.loads(json.dumps(state));restored['selected'] = {}
    assert not request_repair.record_progress(restored)
    OriginalProgress(restored).advance(False)
    assert OriginalProgress(restored).view()['source_revision'] == 1
    assert OriginalProgress(restored).view()['unchanged_turns'] == 1
    assert not OriginalProgress(restored).view()['absence_proven']


def test_conflicting_parent_judgment_and_unread_child_lead_remain_visible():
    ledger, record = ledger_with_need()
    missing = {'status': 'MISSING', 'missing': '미확인', 'citations': []}
    confirmed = {'status': 'CONFIRMED', 'missing': '', 'citations': [{'evidence': 'E1'}]}
    ledger.board['rows'] = {'i:condition': {'issue_id': 'i', 'field': 'condition',
                                         'current': {'internal': missing, 'external': confirmed}}}
    child = {'external': {'request_id': 'child', 'status': 'completed',
                         'investigation_return': {'leads': {'catalogue_hash': 'bound-catalogue',
                             'items': [{'lead_id': 'unread', 'acquisition': 'NOT_READ'},
                                       {'lead_id': 'partial', 'acquisition': 'PARTIAL'}]}}}}
    before = deepcopy((ledger.board, child))
    audit = ledger.audit(child, limit=2)
    assert audit['sides']['external']['fields'][0]['status'] == 'CONFIRMED'
    assert audit['sides']['external']['unacquired_lead_ids'] == ['unread', 'partial']
    assert audit['needs'][0]['status'] == 'OPEN'
    assert (ledger.board, child) == before
    assert not audit['semantic_quality_certified']
    # An audit observation must not become invented mandatory investigation.
    assert len(ledger.board['tasks']) == 1


def test_review_failure_is_quarantined_without_marking_sources_reviewed():
    ledger = ResearchLedger({'tasks': {}, 'round': 0, 'rows': {}, 'reviewed': []})
    visible = [{'evidence_id': 'E1'}]
    ledger.quarantine('input')
    ledger.commit_review('i', visible, 'key', accepted=False, general=True, updates=[])
    assert ledger.new_review_sources('i', visible) == ['E1']
    assert not ledger.review_allowed(incremental=False, new_ids=['E1'], input_key='input')
    assert ledger.review_allowed(incremental=True, new_ids=['E1'], input_key='other')
    ledger.commit_review('i', visible, 'new-key', accepted=True, general=True, updates=[])
    assert ledger.new_review_sources('i', visible) == []
    assert not ledger.review_allowed(incremental=True, new_ids=[])
