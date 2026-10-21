"""Regression tests for previously reproduced transition defects.

Scripted model proposals and synthetic documents only. The isolated candidate is exercised through real service/storage.
Boundary tests isolate scheduling; service tests keep real native RAG/storage.
"""
import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace as S

import jsonschema
import pytest

from semantic_runtime import comparison_research_bridge as bridge, workflow_rag
from semantic_runtime.contracts import digest
from semantic_runtime.research_state import ResearchLedger, OriginalProgress
from semantic_runtime.legal_agent import request_repair
from semantic_runtime.legal_agent.errors import BudgetExhausted, TransportError
from workflow import presentation
from workflow.risk_team_compare_workflow import task_board as tb

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / '04_EXPERIMENTS/ADR/ADR-0943-research-decision-admission/artifacts/run-001'
OUT.mkdir(exist_ok=True)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixtures = load('decision_generalized', '06_TOOLS/EXPERIMENTS/adr_0936/test_generalized.py')
owners = load('decision_owner_fixtures', '05_TESTS/CONTRACTS/test_research_state_owner.py')
tree = fixtures.tree


def record(name, value):
    (OUT / ('observed-' + name + '.json')).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + '\n')


@pytest.mark.parametrize('change', ['unchanged', 'new_lead', 'failed_attempt', 'new_original'])
def test_review_admission_depends_on_original_ids_even_when_other_inputs_change(monkeypatch, change):
    source, value = fixtures.update_fixture()
    source['evidence_id'] = 'old'
    item = deepcopy(value['items'][0])
    item['external']['citations'][0]['evidence'] = 'old'
    sources = [source]
    if change == 'new_original':
        sources.append({**deepcopy(source), 'evidence_id': 'new'})
    ctx = fixtures.context()
    ctx.request = {'use_llm': True}
    ctx.rag = S(port=S(services=type('Services', (), {'__module__': 'semantic_runtime.test_services'})()))
    issue = {'id': 'i', 'requested_fields': ['obligation'], 'requirements': []}
    state = {'scope': {'issues': [issue]}, 'rag_attempts': {'external': {'status': 'completed'}},
             'task_board': {'round': 1, 'reviewed': [], 'tasks': {},
                           'reviewed_sources': {'i': ['old']}, 'rows': {
                               'i:obligation': {'issue_id': 'i', 'field': 'obligation',
                                                'current': item, 'revisions': []}}}}
    ledger = ResearchLedger(state['task_board'])
    old_key = ledger.review_input('i', [source], {'external':'completed'}, {'items':[], 'catalogue_hash':'before'})
    state['task_board']['reviewed_inputs'] = [old_key]
    old_sources = deepcopy(state['task_board']['reviewed_sources'])
    lead_view = {'items': [], 'catalogue_hash': 'before'}
    if change == 'new_lead':
        lead_view = {'items': [{'lead_id': 'new-unread', 'acquisition': 'NOT_READ'}],
                     'catalogue_hash': 'after'}
    if change == 'failed_attempt':
        state['rag_attempts']['external']['status'] = 'failed'
    data = {'question': '승인 기준과 예외', 'as_of': None, 'sources': sources,
            'budget': {}, 'deadline_at': 'unchanged', 'packet': {}}
    monkeypatch.setattr(tb, 'sources_for_issue', lambda *args: sources)
    monkeypatch.setattr(presentation, 'packets', lambda *args, **kwargs: [(deepcopy(data), sources)])
    monkeypatch.setattr(presentation, 'valid_results', lambda _: [])
    monkeypatch.setattr(bridge, 'investigation_leads', lambda *args: {})
    monkeypatch.setattr(bridge, 'lead_view', lambda _: lead_view)
    monkeypatch.setattr(bridge, 'locators', lambda *args: {})
    calls = []

    def decide(stage, shown, schema, instructions, check):
        calls.append(deepcopy(shown))
        proposal = {'items': [], 'evidence_updates': [
            {'evidence_id': ident, 'disposition': 'CONTEXT', 'fields': [],
             'reason': '합성 보충 원문'} for ident in shown['new_evidence_ids']]}
        jsonschema.validate(proposal, schema)
        check(proposal)
        return proposal

    ctx.model = S(decide=decide, services=S(profile={'max_context_chars': 80000},
                    BudgetExhausted=BudgetExhausted, TransportError=TransportError))
    tb.review(ctx, state)
    first_count = len(calls)
    tb.review(ctx, state)
    record('review-' + change, {'level': 'actual review function with synthetic data boundary',
           'change': change, 'new_original_ids': ['new'] if change == 'new_original' else [],
           'lead_view': lead_view, 'attempt_status': state['rag_attempts']['external']['status'],
           'model_calls': first_count, 'model_calls_after_duplicate': len(calls),
           'reviewed_before': old_sources, 'reviewed_after': state['task_board']['reviewed_sources']})
    assert first_count == (0 if change == 'unchanged' else 1)
    assert len(calls) == first_count


@pytest.mark.parametrize('status,missing,cited,expected', [
    ('PARTIAL', '', True, 'OPEN'),
    ('CONFIRMED', '', True, 'OPEN'),
    ('PARTIAL', '조건 원문 미확보', True, 'OPEN'),
    ('PARTIAL', '', False, 'OPEN'),
])
def test_existing_need_resolution_uses_missing_status_and_citation_presence(status, missing, cited, expected):
    ledger, task = owners.ledger_with_need()
    before = deepcopy(ledger.needs()[0])
    row = {'status': status, 'missing': missing, 'text': '일부 원문 확인; 조건 적용 범위는 미확인',
           'citations': [{'evidence': 'E1', 'quote': '원문'}] if cited else [],
           'dependencies': [], 'scope_sufficient': False}
    value = {'evidence_updates': [], 'items': [{'field': 'condition', 'external': row,
             'content_status': 'UNKNOWN', 'difference': '미확인 유지', 'next_tasks': []}]}
    schema = tb.review_contract(['condition'], [], True)
    jsonschema.validate(value, schema)
    tb.checked_update(value, [{'evidence_id': 'E1', 'side': 'external', 'spans': [{'text': '원문'}]}],
                      ['condition'], {}, [], True)
    ledger.reconcile({'id': 'i'}, 'condition', 'external', row, 'review-2', [],
                     lambda _: pytest.fail('Existing pending work must be preserved'))
    after = ledger.needs()[0]
    name = 'resolution-' + status.lower() + ('-missing' if missing else '-empty') + ('-cited' if cited else '-uncited')
    record(name, {'level': 'actual schema, citation validator and state reconciliation',
           'proposal': value, 'need_before': before, 'need_after': after,
           'task_status': task['status'], 'new_originals': 0,
           'separate_need_resolution_proposal_required': True,
           'legal_correctness_evaluated': False})
    assert after['status'] == expected
    assert task['status'] == ('RESOLVED' if expected == 'RESOLVED' else 'PENDING')


@pytest.mark.parametrize('mode', ['normal', 'followup', 'failed_followup', 'resume_after_child'])
def test_service_followup_lifecycle_preserves_sources_but_skips_parent_reconsideration(tmp_path, tree, monkeypatch, mode):
    app, _ = fixtures.prior.app_for(tmp_path, tree)
    transport = fixtures.General('followup' if mode == 'resume_after_child' else mode)
    app.state.pipeline.term_agent.transport = transport
    service = load('decision_service', 'service.py')
    service._APP = app
    service._BINDING = {'mode': 'working-code-test', 'code_root': str(ROOT)}
    definition = app.state.workflow_runtime.registry.resolve('risk_team_compare_workflow', None, 'risk_team')
    assert definition.manifest['version'] == '1.19.0'
    original = workflow_rag.execute
    followups = []
    interrupted = []

    def execute(port, action, call_id):
        is_followup = bool(action['args']['task'].get('research_task'))
        if is_followup:
            followups.append({'call_id': call_id, 'model_views_at_entry': len(transport.views)})
        result = original(port, action, call_id)
        if is_followup:
            followups[-1].update(status=result['status'], model_views_after_child=len(transport.views),
                               evidence_ids=result.get('evidence_ids', []))
            if mode == 'resume_after_child' and not interrupted:
                interrupted.append(True)
                raise KeyboardInterrupt('Synthetic process loss after child commit')
        return result

    monkeypatch.setattr(workflow_rag, 'execute', execute)
    request = {'API_TYPE': 'RAG_ASK', **fixtures.prior.BODY}
    before_resume = None
    if mode == 'resume_after_child':
        with pytest.raises(KeyboardInterrupt):
            asyncio.run(service.service({}, request))
        journal = next(app.state.workflow_runtime.root.glob('*/journal.sqlite'))
        with sqlite3.connect(journal) as db:
            revision = db.execute('SELECT revision FROM workflow_state').fetchone()[0]
            before_resume = {'deadline': db.execute('SELECT deadline_at FROM run').fetchone()[0],
                             'reserved': db.execute('SELECT model_reserved FROM budget').fetchone()[0]}
        response = asyncio.run(service.service({}, {'API_TYPE': 'WORKFLOW_RESUME',
            'run_id': journal.parent.name, 'session_id': 's', 'expected_revision': revision}))
    else:
        response = asyncio.run(service.service({}, request))
    assert response['status'] == 200, response
    value = response['body']
    count = len(transport.views)
    duplicate = asyncio.run(service.service({}, request))
    saved = asyncio.run(service.service({}, {'API_TYPE': 'WORKFLOW_STATUS',
        'run_id': value['run_id'], 'session_id': request['session_id']}))
    assert duplicate['body']['answer'] == saved['body']['answer'] == value['answer']
    assert duplicate['body']['run_id'] == value['run_id']
    assert len(transport.views) == count
    journal = app.state.workflow_runtime.root / value['run_id'] / 'journal.sqlite'
    with sqlite3.connect(journal) as db:
        state = json.loads(db.execute('SELECT checkpoint_json FROM workflow_state').fetchone()[0])
        stages = [json.loads(row[0])['stage'] for row in db.execute(
            "SELECT payload_json FROM event WHERE kind='WORKFLOW_CHECKPOINT' ORDER BY seq")]
        budget = dict(zip(['model_reserved', 'model_limit'], db.execute(
            'SELECT model_reserved,model_limit FROM budget').fetchone()))
        deadline = db.execute('SELECT deadline_at FROM run').fetchone()[0]
    board = state['task_board']
    tasks = [{'status': r['status'], 'operation': r['task']['operation'],
              'new_evidence_ids': r.get('new_evidence', [])} for r in board['tasks'].values()]
    tail = [stage for stage, _ in transport.views[followups[0]['model_views_at_entry']:]] if followups else []
    facts = {'level': 'service.py.service -> actual API/workflow/native RAG/store; scripted model',
             'mode': mode, 'result_status': value['status'], 'followups': followups,
             'post_followup_model_stages': tail, 'checkpoint_stages': stages,
             'tasks': tasks, 'needs': ledger_needs(board), 'used_followups': board['round'],
             'sources_retained': {s: value['rag_results'][s]['evidence_ids'] for s in ('internal', 'external')},
             'budget': budget, 'before_resume': before_resume, 'deadline': deadline,
             'duplicate_and_saved_identical': True, 'duplicate_model_calls': 0,
             'workflow_version': definition.manifest['version']}
    record('service-' + mode, facts)
    assert all(facts['sources_retained'].values())
    if mode == 'normal':
        assert not tasks and board['round'] == 0
    else:
        assert followups and tasks and all(not t['new_evidence_ids'] for t in tasks)
        assert all(t['status'] == ('FAILED' if mode == 'failed_followup' else 'COMPLETE') for t in tasks)
        assert any(n['status'] == 'OPEN' for n in facts['needs'])
        assert tail.count('workflow-items') == 1
        assert 'COMPARE' in stages and state['stage'] == 'END'
        assert board['round'] == 1
    if before_resume:
        assert deadline == before_resume['deadline']
        assert budget['model_reserved'] >= before_resume['reserved']
        assert followups[0]['call_id'] == followups[1]['call_id']
        assert followups[0]['model_views_after_child'] == followups[1]['model_views_after_child']


def ledger_needs(board):
    return ResearchLedger(board).needs(limit=2)


def test_navigation_only_recovery_can_end_before_the_next_read_choice():
    state = {'binding': {'generation': 'synthetic'}, 'state_version': 1, 'investigation_epoch': 0,
             'turn': 3, 'no_progress': 0, 'selected': {}, 'basis_history': {}}
    owner = OriginalProgress(state)
    for step in range(3):
        changed = owner.observe({'navigation-position-' + str(step)})
        owner.advance(changed)
    actions = {'open': {'action': 'OPEN_LAW'}}
    inv = S(modern=True, p=state, view=lambda: ({'page': 'navigation'}, deepcopy(actions)),
            s=S(repo=S(event=lambda *args: None, budget=lambda: {'model_reserved': 3, 'model_limit': 40})),
            save=lambda: None)
    recovery = request_repair.no_progress_recovery(inv)
    assert recovery is not None
    request_repair.finish_no_progress_recovery(state, recovery[2])
    owner.advance(owner.observe({'new-readable-position'}))
    state['turn'] += 1
    actions.clear();actions['read'] = {'action': 'READ_ARTICLES'}
    next_recovery = request_repair.no_progress_recovery(inv)
    record('navigation-only-stop', {'level': 'actual progress/recovery functions; synthetic navigation',
           'progress': owner.view(), 'recovery_status': state['no_progress_recovery']['status'],
           'next_available_action': 'READ_ARTICLES', 'another_selection_allowed': next_recovery is not None,
           'legal_absence_inferred': False, 'actual_case_causality_proven': False})
    assert owner.view()['discovery_changed'] and owner.view()['unchanged_turns'] == 4
    assert next_recovery is not None
    assert state['no_progress_recovery']['selection_count'] == 2
