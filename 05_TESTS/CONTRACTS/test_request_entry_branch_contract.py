"""Fresh-entry field conflicts: synthetic decisions, no model quality claims."""
from copy import deepcopy
from itertools import product
import json
import sqlite3

import pytest
from jsonschema import Draft202012Validator

from semantic_runtime.legal_agent import request_entry as entry
from test_unified_scope_semantic_authority import wire
from test_natural_language_routing import EntryTransport, app
from test_structure_first_search import structured_generation
from test_legal_agent_double_harness import wire as response_wire
from fastapi.testclient import TestClient
from test_multiturn_structured_scope import tree as scoped_tree


def proposal(route='CASE', method='CASE_START', intent=True, search=True):
    value = wire()
    value['routing'] = {'mode': route, 'answer': '모의 안내' if route == 'DIRECT' else '', 'reason': '합성 분류'}
    if route == 'BROWSE':
        value['routing']['catalogue'] = {'browse_view': 'documents', 'document_category': 'all', 'title_query': ''}
    if method is None:
        value['command'] = None
    else:
        value['command']['method_id'] = method
        if method == 'NEED_TARGET':
            value['command']['queries'] = []
    if not intent:
        value['intent'] = None
    if not search:
        value['search'] = None
    return value


@pytest.mark.parametrize('route,method,intent,search', list(product(
    ['CASE', 'DIRECT', 'BROWSE'], [None, 'CASE_START', 'NEED_TARGET'], [False, True], [False, True])))
def test_wire_only_admits_consistent_entry_branches(route, method, intent, search):
    expected = ((route in ('DIRECT', 'BROWSE') and method is None and not intent and not search)
        or (route == 'CASE' and method == 'CASE_START' and intent and search)
        or (route == 'CASE' and method == 'NEED_TARGET' and not intent and not search))
    assert Draft202012Validator(entry.schema(model=True)).is_valid(proposal(route, method, intent, search)) is expected


@pytest.mark.parametrize('method', [None, 'NEED_TARGET'])
def test_photographed_conflict_has_field_paths_without_changing_the_proposal(method):
    raw = proposal(method=method)
    before = deepcopy(raw)
    with pytest.raises(entry.output.OutputContractError) as caught:
        entry.decode_scope(raw, {'candidates': []})
    details = entry.output.diagnostics(caught.value)
    assert details['category'] == 'DECISION_CONFLICT'
    assert any(row['path'] == '/search' and '/command/method_id' in row['related_paths'] for row in details['issues'])
    assert all(row['path'] != '/' and row['expected_constraint'] for row in details['issues'])
    assert raw == before


class ConflictingEntry(EntryTransport):
    def __init__(self, method, *, fail=False, route='BROWSE'):
        super().__init__(route)
        self.method = method
        self.fail = fail
        self.bad = proposal(route='CASE', method=method)
        self.schemas = []

    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        phase = view.get('source_stage', view['phase'])
        if phase.startswith('request-entry'):
            self.bad['intent']['issues'][0]['request_quote'] = view['question']
            self.bad['search']['scope_decision']['user_quote'] = view['question']
            self.views.append(deepcopy(view))
            self.phases.append(phase)
            self.schemas.append(body['response_format']['json_schema']['schema'])
            if len(self.views) == 1 or self.fail:
                return response_wire(self.bad)
            assert view['rejected_decision'] == self.bad
            assert view['repair_contract']['same_evidence_scope'] is True
            details = view['repair_contract']['validation']
            assert details['category'] == 'DECISION_CONFLICT'
            assert any(row['path'] == '/search' for row in details['issues'])
            return response_wire(proposal(self.mode, None, False, False))
        return super().send_once(body=body, ticket=ticket)


@pytest.mark.parametrize('method', [None, 'NEED_TARGET'])
@pytest.mark.parametrize('fail', [False, True])
def test_actual_api_repairs_or_stops_and_preserves_request_after_restart(tmp_path, structured_generation, method, fail):
    transport = ConflictingEntry(method, fail=fail)
    body = {'question': '읽을 수 있는 문서 목록을 알려줘', 'session_id': 's', 'request_id': 'same-request', 'document_ids': ['d']}
    first = None
    for _ in range(2):
        with TestClient(app(tmp_path, structured_generation, transport, fused=True)) as api:
            response = api.post('/v1/rag/ask', json=body)
            if fail:
                assert response.status_code >= 400
                assert '모의승인규정' not in response.text
            else:
                assert response.status_code == 200, response.text
                result = response.json()
                assert '모의승인규정' in result['answer']['text']
                assert '다른문서' not in result['answer']['text']
                assert result['question_id'] is None and not result['answer']['claims']
                if first is None:
                    first = result['answer']
                assert result['answer'] == first
        assert transport.phases == ['request-entry', 'request-entry-repair']
    assert transport.schemas[0] == transport.schemas[1]
    assert not Draft202012Validator(transport.schemas[0]).is_valid(transport.bad)
    # Case journal retains the exact rejected proposal; no goal was admitted.
    from semantic_runtime.legal_agent.shortcut_store import selected_store
    from semantic_runtime.contracts import digest
    with sqlite3.connect(selected_store(tmp_path/'90_RUNTIME/semantic')) as db:
        records = [json.loads(row[0])['row'] for row in db.execute(
            "SELECT command FROM event WHERE kind='OUTPUT_DECISION_STATE'")]
        rejected = [r for r in records if r['status'] == 'REJECTED']
        assert rejected and rejected[0]['proposal'] == transport.bad
        assert rejected[0]['proposal_hash'] == digest(transport.bad)
        assert db.execute('SELECT count(*) FROM goal').fetchone()[0] == 0
        assert records[-1]['status'] == ('REJECTED' if fail else 'ACCEPTED')
        if fail:
            assert records[-1]['repairable'] is False


def test_bound_quotes_and_optional_history_survive_branch_rebuild():
    question = '모의승인규정에서 승인 요건을 알려줘'
    schema, _ = entry.bind_task_quotes(entry.schema(True, model=True), question)
    from semantic_runtime.legal_agent import wiki_recall
    _, schema = wiki_recall.augment({}, schema, [{'view': {'memory_id': 'H1'}}])
    schema = entry.constrain_schema(schema)
    value = proposal()
    value['intent']['issues'][0]['request_quote'] = question
    value['history_ids'] = ['H1']
    assert Draft202012Validator(schema).is_valid(value)
    value['intent']['issues'][0]['request_quote'] = '다른 질문'
    assert not Draft202012Validator(schema).is_valid(value)


def test_shape_transport_and_integrity_errors_are_not_branch_recovery():
    from semantic_runtime.legal_agent.minimal_output import Projection
    shape = {k: v for k, v in entry.schema(model=True).items() if k != 'anyOf'}
    bad = proposal(method=None)
    bad['search'].pop('scope_decision')
    with pytest.raises(entry.output.OutputContractError) as caught:
        Projection(entry.schema(model=True)).expand(bad)
    assert entry.rejected_branch(caught.value, shape) is None
    assert entry.rejected_branch(RuntimeError('transport failure'), shape) is None
    from semantic_runtime.legal_agent.errors import ContractError
    assert entry.rejected_branch(ContractError('hash mismatch'), shape) is None


@pytest.mark.parametrize('method', [None, 'NEED_TARGET'])
def test_repaired_case_reaches_originals_with_exclusion_and_reuses_answer(tmp_path, scoped_tree, method):
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.shortcut_store import selected_store
    from test_assessment_source_reply import EmptyAssessment
    from test_bounded_source_main import settings
    from test_legal_agent_double_harness import ROOT
    from test_model_structure_selection import choose, single

    question = '모의승인규정 제1조 1항에서 2호는 빼고 전부 설명해'
    selected = choose(exclude=[single(2)], article=1, dash=None, paragraph=1)
    good = proposal()
    good['command']['queries'] = ['승인']
    good['intent']['issues'][0]['request_quote'] = question
    good['search'].update(mode='STRUCTURE')
    good['search']['scope_decision'].update(user_quote=question, targets=[
        {'document': '모의승인규정', 'structure': None, 'selection': selected}])
    bad = deepcopy(good)
    if method is None:
        bad['command'] = None
    else:
        bad['command']['method_id'] = method

    class Transport(EmptyAssessment):
        def send_once(self, *, body, ticket):
            view = json.loads(body['messages'][1]['content'])['view']
            phase = view.get('source_stage', view['phase'])
            if phase.startswith('request-entry'):
                self.phases.append(phase)
                if phase == 'request-entry':
                    return response_wire(bad)
                assert view['rejected_decision'] == bad
                assert view['question'] == question
                return response_wire(good)
            return super().send_once(body=body, ticket=ticket)

    generation, index = scoped_tree
    transport = Transport('repaired')
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000,
        'request_entry_policy': 'fused-title-v1', 'candidate_navigation': {
            'mode': 'law-first-v1', 'investigation_control': True, 'completion_contract': True,
            'completion_policy_version': 'investigation-completion-v8', 'compact_input': True,
            'structure_first': True, 'selectable_search': True, 'answer_first': True, 'assessment_reentry_limit': 0}}
    runtime = tmp_path/'runtime'
    body = {'question': question, 'session_id': 's', 'request_id': 'r'}
    answer = None
    for _ in range(2):
        application = create_app(tmp_path, generation, contracts_root=ROOT, provider=object(),
            implementation='legal-agent-unified-v6', legal_agent_profile=profile,
            legal_agent_transport=transport, runtime_root=runtime,
            memory_identity=lambda _: {'user_id': 'synthetic', 'team_id': 'risk_team', 'document_ids': ['d']})
        application.state.pipeline.term_agent.unit_fulltext = index
        with TestClient(application) as api:
            response = api.post('/v1/rag/ask', json=body)
            assert response.status_code == 200, response.text
            result = response.json()
            assert '긴급 승인 예외는 허용한다' in result['answer']['text']
            assert '일반 승인 예외는 허용하지 않는다' not in result['answer']['text']
            if answer is None:
                answer, calls = result['answer'], len(transport.phases)
            assert result['answer'] == answer and len(transport.phases) == calls
    assert transport.phases[:2] == ['request-entry', 'request-entry-repair']
    with sqlite3.connect(selected_store(runtime)) as db:
        state = json.loads(db.execute('SELECT state FROM goal WHERE id=?', (result['question_id'],)).fetchone()[0])
        assert [r['unit_id'] for r in state['search_scope']['targets']] == ['2']
        assert state['search_scope']['selections'][0]['excluded_unit_ids'] == ['4']
