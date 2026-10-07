"""Model-decision correction on synthetic inputs; no external model calls."""
from copy import deepcopy
from dataclasses import replace
import json
import logging
import sqlite3
import time
from types import SimpleNamespace

import pytest

from semantic_runtime.legal_agent.bounded_source_session import BoundedSourceSession
from semantic_runtime.legal_agent import obligation_protocol, source_selection
from semantic_runtime.legal_agent.domain import DOMAIN
from semantic_runtime.legal_agent.errors import (
    BudgetExhausted, ContractError, DeadlineExceeded, ProposalError, StaleProposal, TransportError,
)
from semantic_runtime.progress import ProgressCapture
from test_legal_agent_double_harness import work as base_work, WireTransport
from test_legal_agent_v5 import plan, app_for
from test_bounded_source_main import generation, settings, Transport


@pytest.fixture
def work(base_work, tmp_path):
    from semantic_runtime.legal_agent.obligation_repository import ObligationRepository
    repo = ObligationRepository(tmp_path/'obligation-journal.sqlite', base_work.context, settings())
    yield repo
    repo.close()


def bounded(work, responses, **overrides):
    session = object.__new__(BoundedSourceSession)
    session.work, session.context = work, work.context
    session.profile = {**settings(), **overrides}
    session.gateway = SimpleNamespace(domain=DOMAIN, transport=WireTransport(responses))
    session.selection_views = {}
    session.navigation_context = {}  # This fixture bypasses __init__; navigation itself has separate real-session tests.
    return session


SCHEMA = {'type': 'object', 'properties': {'mode': {'type': 'string', 'enum': ['SEARCH']}},
          'required': ['mode'], 'additionalProperties': False}


@pytest.mark.parametrize('invalid,error', [
    ('{broken', 'Expecting property name'),
    ({}, 'required property'),
    ({'mode': 4}, 'not of type'),
    ({'mode': 'OTHER'}, 'not one of'),
    ({'mode': 'SEARCH', 'extra': True}, 'Additional properties'),
    ([], 'not of type'),
])
def test_json_and_schema_errors_return_to_model_with_original_view(work, invalid, error):
    session = bounded(work, [invalid, {'mode': 'SEARCH'}], max_schema_repairs=1)
    result = session.structured('검증용 지침', {'question': '모의 질문'}, SCHEMA, 'source-query-plan', 10)
    assert result == {'mode': 'SEARCH'}
    first, second = session.gateway.transport.calls
    assert first['messages'] == second['messages'][:2]
    correction = json.loads(second['messages'][2]['content'])
    assert error in correction['error']
    assert correction['invalid_response_excerpt']
    assert correction['schema'] == 'BoundedSourceDecision'
    assert work.budget()['model_reserved'] == 2
    events = [json.loads(row[0]) for row in work.db.execute(
        "SELECT payload_json FROM event WHERE kind='OUTPUT_SCHEMA_INVALID'")]
    assert len(events) == 1 and events[0]['repair_scheduled'] is True
    assert events[0]['source_stage'] == 'source-query-plan'
    assert not work.heads('question_plan')


@pytest.mark.parametrize('failure,error', [
    ('overlap', 'must be disjoint'),
    ('missing', 'should be non-empty'),
    ('unknown', 'unknown original question segment'),
    ('duplicate', 'duplicate answer demand'),
    ('whitespace', 'non-whitespace characters'),
])
def test_question_plan_semantic_errors_correct_before_commit(work, failure, error):
    invalid = plan()
    if failure == 'overlap':
        invalid['context_refs'] = ['Q1']
    elif failure == 'missing':
        invalid['demands'] = []
    elif failure == 'unknown':
        invalid['demands'][0]['question_refs'] = ['Q999']
    elif failure == 'duplicate':
        invalid['demands'].append(deepcopy(invalid['demands'][0]))
    else:
        invalid['demands'][0]['requirement'] = '    '
    session = bounded(work, [invalid, plan()], max_schema_repairs=1)
    session.question_review = None
    session.prepare_question_plan()
    assert len(session.gateway.transport.calls) == 2
    correction = json.loads(session.gateway.transport.calls[-1]['messages'][2]['content'])
    assert error in correction['error']
    assert len(work.heads('question_plan')) == 1
    assert len(session.plan()['demands']) == 2
    assert work.db.execute("SELECT count(*) FROM event WHERE kind='QUESTION_PLAN'").fetchone()[0] == 1


@pytest.mark.parametrize('phase', ['source-triage', 'source-omission-review'])
@pytest.mark.parametrize('failure', ['outside', 'duplicate', 'blank'])
def test_selection_errors_do_not_adopt_rejected_choices(work, phase, failure):
    valid = {'issues': [], 'choices': [{'id': 'C001', 'reason': '원문 확인'}]}
    invalid = deepcopy(valid)
    if failure == 'outside':
        invalid['choices'][0]['id'] = 'UNAVAILABLE'
    elif failure == 'duplicate':
        invalid['choices'].append({'id': 'C001', 'reason': '중복된 다른 이유'})
    else:
        invalid['choices'][0]['reason'] = ' '
    session = bounded(work, [invalid, valid], max_schema_repairs=1)
    assert session.structured('선별', {'question': '모의 질문'},
        source_selection.selection_schema(['C001', 'C002'], 2), phase, 10) == valid
    assert len(session.gateway.transport.calls) == 2
    assert not work.heads('source_selection')


def test_cross_field_route_validation_returns_error_to_model(work):
    from semantic_runtime.legal_agent import source_query_planning as planning
    valid = {'mode': 'SEARCH', 'law_names': ['모의법'], 'queries': ['승인 규정'], 'answer': '',
             'reason': '법률 원문 확인', 'browse_view': 'documents', 'document_category': 'all',
             'title_query': '', 'inspect_documents': False}
    invalid = {**valid, 'answer': '검색 전에 답변함'}
    session = bounded(work, [invalid, valid], max_schema_repairs=1)
    session.sources = SimpleNamespace(matcher=SimpleNamespace(documents={'d': '모의법'}), scope={'d'})
    assert session.plan_request_search()['mode'] == 'SEARCH'
    assert 'SEARCH requires queries without answer' in session.gateway.transport.calls[-1]['messages'][2]['content']


@pytest.mark.parametrize('search_required', [True, False])
def test_catalogue_next_step_checks_are_inside_correction_loop(work, search_required):
    choice = {'targets': ['D1'], 'reason': '관련 목차 확인'}
    invalid = {'search_required': search_required, 'answer': '', 'queries': [], 'law_names': []}
    valid = {**invalid, 'search_required': False, 'answer': '모의법 제1조부터 확인하십시오.'}
    session = bounded(work, [choice, invalid, valid], max_schema_repairs=1)
    session.sources = SimpleNamespace(
        scope={'d'}, matcher=SimpleNamespace(document_catalogue={'d': {'category': 'external'}}),
        handle=lambda *args: 'R1')
    session.catalogue_pages = lambda tool, args, label, **kwargs: (
        [{'target': 'D1', 'name': '모의법'}] if label == 'root'
        else [{'target': 'U1', 'title': '제1조 승인'}], [], True)
    answer, query = session.catalogue_observation({'document_category': 'all', 'title_query': '',
        'browse_view': 'documents', 'inspect_documents': True, 'mode': 'BROWSE'})
    assert answer == valid['answer'] and query is None
    assert len(session.gateway.transport.calls) == 3
    correction = json.loads(session.gateway.transport.calls[-1]['messages'][2]['content'])
    assert ('catalogue search' if search_required else 'catalogue recommendation') in correction['error']


def test_uncovered_original_question_reference_is_corrected_before_commit(base_work, tmp_path):
    from semantic_runtime.legal_agent.context import RequestContext
    from semantic_runtime.legal_agent.obligation_repository import ObligationRepository
    question = '승인 대상은?\n승인 예외는?'
    context = RequestContext.create({**base_work.context.query, 'question': question},
        {**base_work.context.request, 'question': question}, base_work.context.binding, 30)
    repo = ObligationRepository(tmp_path/'two-questions.sqlite', context, settings())
    try:
        session = bounded(repo, [plan(), plan(context=('Q2',))], max_schema_repairs=1)
        session.question_review = None
        session.prepare_question_plan()
        correction = json.loads(session.gateway.transport.calls[-1]['messages'][2]['content'])
        assert 'every original question segment' in correction['error']
        assert session.plan()['context_refs'] == ['Q2']
    finally:
        repo.close()


@pytest.mark.parametrize('limit,calls', [(0, 1), (1, 2), (2, 3)])
def test_repeated_invalid_output_stops_at_declared_limit(work, limit, calls):
    session = bounded(work, [{}] * calls, max_schema_repairs=limit)
    with pytest.raises(ProposalError, match='after bounded repair'):
        session.structured('검증', {}, SCHEMA, 'bounded-question-plan', 10)
    assert len(session.gateway.transport.calls) == calls
    assert work.budget()['model_reserved'] == calls
    payload = json.loads(work.db.execute(
        "SELECT payload_json FROM event WHERE kind='OUTPUT_SCHEMA_INVALID' ORDER BY seq DESC LIMIT 1"
    ).fetchone()[0])
    assert payload['repair_scheduled'] is False
    assert not session.selection_views


@pytest.mark.parametrize('failure', [
    ContractError('source binding mismatch'), sqlite3.OperationalError('storage failure'),
    StaleProposal('stale view'), BudgetExhausted('source budget exhausted'),
])
def test_system_failures_in_validation_do_not_become_format_repairs(work, failure):
    session = bounded(work, [{'mode': 'SEARCH'}], max_schema_repairs=2)
    def validator(value):
        raise failure
    with pytest.raises(type(failure), match=str(failure)):
        session.structured('검증', {}, SCHEMA, 'bounded-question-plan', 10, validator=validator)
    assert len(session.gateway.transport.calls) == 1
    assert work.db.execute("SELECT count(*) FROM event WHERE kind='OUTPUT_SCHEMA_INVALID'").fetchone()[0] == 0


def test_transport_failure_is_not_schema_repaired(work):
    session = bounded(work, [TransportError('provider rejected input', retryable=True)], max_schema_repairs=2)
    with pytest.raises(TransportError):
        session.structured('검증', {}, SCHEMA, 'source-triage-test', 10)
    assert len(session.gateway.transport.calls) == 1


def test_valid_output_does_not_add_a_correction_call(work):
    session = bounded(work, [{'mode': 'SEARCH'}], max_schema_repairs=2)
    session.structured('검증', {}, SCHEMA, 'source-query-plan', 10)
    assert len(session.gateway.transport.calls) == 1


def test_different_validation_errors_still_share_one_bounded_call(work):
    session = bounded(work, ['{broken', {'mode': 'OTHER'}, {'mode': 'SEARCH'}], max_schema_repairs=2)
    session.structured('검증', {}, SCHEMA, 'source-query-plan', 10)
    calls = session.gateway.transport.calls
    assert len(calls) == 3
    assert all(body['messages'][:2] == calls[0]['messages'] for body in calls)
    attempts = list(work.db.execute('SELECT logical_call_id,view_id FROM model_attempt'))
    assert len({tuple(row) for row in attempts}) == 1


def test_repair_cannot_bypass_physical_call_budget(base_work, tmp_path):
    from semantic_runtime.legal_agent.obligation_repository import ObligationRepository
    profile = {**settings(), 'max_model_attempts': 2, 'finalization_reserve': 1}
    repo = ObligationRepository(tmp_path/'limited.sqlite', base_work.context, profile)
    try:
        session = bounded(repo, [{}], max_schema_repairs=2)
        with pytest.raises(BudgetExhausted):
            session.structured('검증', {}, SCHEMA, 'source-query-plan', 10)
        assert len(session.gateway.transport.calls) == 1
        assert repo.budget()['model_reserved'] == 1
    finally:
        repo.close()


def test_expired_deadline_does_not_send_repair(work):
    session = bounded(work, [], max_schema_repairs=2)
    session.context = replace(session.context, deadline=time.monotonic()-1)
    with pytest.raises(DeadlineExceeded):
        session.structured('검증', {}, SCHEMA, 'bounded-question-plan', 10)
    assert not session.gateway.transport.calls


@pytest.mark.parametrize('scheduled', [True, False])
def test_progress_describes_correction_without_raw_response(tmp_path, scheduled):
    events = []
    capture = ProgressCapture('test-request', tmp_path, events.append)
    record = logging.LogRecord('genos', logging.WARNING, '', 0, 'model.output.invalid', (), None)
    record.fields = {'request_id': 'test-request', 'repair_scheduled': scheduled,
                     'error': 'PRIVATE MODEL TEXT', 'response': 'PRIVATE RESPONSE'}
    capture.emit(record)
    assert len(events) == 1 and events[0]['kind'] == 'repair'
    assert ('재요청' if scheduled else '소진') in events[0]['label']
    assert 'PRIVATE' not in json.dumps(events)


def test_full_bounded_pipeline_repairs_plan_then_publishes_answer(tmp_path, generation):
    class IncorrectOnce(Transport):
        rejected = False
        def send_once(self, *, body, ticket):
            result = super().send_once(body=body, ticket=ticket)
            view = json.loads(body['messages'][1]['content'])['view']
            if view.get('source_stage') == 'bounded-question-plan' and not self.rejected:
                self.rejected = True
                value = json.loads(result['body_json']['choices'][0]['message']['content'])
                value['context_refs'] = value['demands'][0]['question_refs']
                result['body_json']['choices'][0]['message']['content'] = json.dumps(value)
            return result
    transport = IncorrectOnce()
    app = app_for(tmp_path, generation, transport,
                  {**settings(), 'max_schema_repairs': 1, 'final_review_enabled': False})
    pipeline = app.state.pipeline
    progress = []
    capture = ProgressCapture('synthetic-repair-request', tmp_path, progress.append)
    logger = logging.getLogger('genos')
    logger.addHandler(capture)
    try:
        from semantic_runtime import observability as obs
        with obs.context(request_id='synthetic-repair-request'):
            result = pipeline.run('모의승인규정의 승인 대상과 예외는?', ['d'], use_llm=True)
        assert result['answer']['claims']
        repaired = [body for body in transport.calls if len(body['messages']) == 3]
        assert len(repaired) == 1
        assert 'must be disjoint' in repaired[0]['messages'][-1]['content']
        assert any(event['kind'] == 'repair' and '재요청' in event['label'] for event in progress)
    finally:
        logger.removeHandler(capture)
        pipeline.store.close()
