"""Failure, recovery, isolation and semantic-control tests using synthetic data."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
import io
import logging
from pathlib import Path
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient
from semantic_runtime.contracts import Contracts, digest
from semantic_runtime.legal_agent.errors import ContractError, ProposalError, StaleProposal, TransportError, PublicationConflict, AdmissionRejected
from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.repository import WorkRepository, text_hash
from semantic_runtime.legal_agent.publication import prepare, export, recover
from semantic_runtime.legal_agent.composer import commit_draft
from semantic_runtime.legal_agent.reviewer import commit_review
from semantic_runtime.legal_agent.gate import evaluate
from semantic_runtime.legal_agent.packer import pack
from semantic_runtime.legal_agent.domain import DOMAIN, profile
from semantic_runtime.legal_agent.gateway import ModelGateway
from semantic_runtime.legal_agent.transport import GenosTransport, _error_details
from semantic_runtime.genos import endpoint
from semantic_runtime import observability as obs
from test_legal_agent_double_harness import (
    ROOT, PROFILE, BINDING, work, generation, issue, proposal, tool, seed,
    visible_view, apply, establish, draft_and_review, WireTransport, RevisionTransport, wire, make_app,
)


def minimal_result(repo):
    request = repo.context.request
    query = repo.context.query
    state = {'final': True, 'status': 'BOUNDED'}
    return {'request': request, 'query': query,
        'retrieval': {'candidates': [], 'routes': {}, 'vector_status': 'NOT_USED', 'generation_id': 'g', 'term_agent': state},
        'selection': {'selected': [], 'discarded_ids': [], 'method': 'term-agent', 'term_agent': state},
        'assembly': {'context': [], 'unresolved': ['모의 근거 부족'], 'data_status': 'EXAMPLE', 'term_agent': state},
        'answer': {'schema_version': 'term-runtime-v1', 'id': 'answer:'+repo.context.run_id, 'scope': query['scope'],
            'query_id': query['id'], 'generation_id': 'g', 'source_store_sha256': 'a'*64, 'text': '확인 가능한 근거가 부족합니다.',
            'claims': [], 'unresolved': [{'reason': '모의 근거 부족'}], 'provider_receipt': {}}}


def final_control(repo):
    with repo.transaction():
        repo.event('CONTROL', {'decision': 'FINAL', 'gate': 'BOUNDED'})


def test_publication_no_clobber_and_idempotent_export(work, tmp_path):
    final_control(work)
    envelope = prepare(work, minimal_result(work), None, Contracts(ROOT))
    assert work.run()['status'] == 'COMMIT_READY'
    assert export(work, tmp_path/'runs') == envelope
    assert export(work, tmp_path/'runs') == envelope
    assert work.run()['status'] == 'COMPLETED'
    with pytest.raises(sqlite3.IntegrityError, match='immutable'):
        work.db.execute("UPDATE publication SET result_json='{}'")


def test_publication_conflict_preserves_both_journal_and_existing_result(work, tmp_path):
    final_control(work)
    prepare(work, minimal_result(work), None, Contracts(ROOT))
    folder = tmp_path/'runs'
    folder.mkdir()
    target = folder/(work.context.run_id+'.json')
    target.write_text('{"existing": true}')
    with pytest.raises(PublicationConflict):
        export(work, folder)
    assert target.read_text() == '{"existing": true}'
    assert work.run()['status'] == 'COMMIT_READY'


@pytest.mark.parametrize('after_install', [False, True])
def test_recover_commit_ready_before_or_after_file_install(work, tmp_path, after_install):
    final_control(work)
    result = prepare(work, minimal_result(work), None, Contracts(ROOT))
    directory = tmp_path/'journals/20260919'/work.context.run_id
    directory.mkdir(parents=True)
    with sqlite3.connect(directory/'journal.sqlite') as db:
        work.db.backup(db)
    runs = tmp_path/'runs'
    runs.mkdir()
    if after_install:
        (runs/(work.context.run_id+'.json')).write_text(json.dumps(result))
    output = recover(tmp_path/'journals', runs)
    assert output == [{'run_id': work.context.run_id, 'status': 'COMPLETED'}]
    assert json.loads((runs/(work.context.run_id+'.json')).read_text()) == result
    assert recover(tmp_path/'journals', runs) == []


def test_only_final_result_may_enter_publication(work):
    with pytest.raises(ContractError, match='FINAL'):
        prepare(work, minimal_result(work), None, Contracts(ROOT))


def test_wrong_generation_request_binding_is_immutable(work):
    with pytest.raises(sqlite3.IntegrityError, match='immutable'):
        work.db.execute("UPDATE run SET binding_json='{}'")
    wrong = replace(work.context, binding={**work.context.binding, 'generation_id': 'another'})
    with pytest.raises(ContractError, match='binding mismatch'):
        WorkRepository(work.path, wrong, PROFILE)


def test_dependency_cycle_and_missing_tmp_roll_back_entire_batch(work):
    with pytest.raises(ProposalError, match='cyclic'):
        apply(work, {'op': 'propose_finding', 'temp_id': 'tmp:f', 'issue_id': 'tmp:i',
                     'assessment_ids': ['tmp:f'], 'fact_ids': [], 'text': '순환', 'applicability': 'source_only'},
                    {'op': 'create_issue', 'temp_id': 'tmp:i', 'issue': issue()})
    assert not work.heads()


def test_review_of_prior_claim_version_cannot_approve_rewritten_answer(work):
    establish(work)
    packed, claims = draft_and_review(work)
    view = visible_view(work, 'compose', packed['evidence_ids'])
    commit_draft(work, view, {'paragraphs': [{'text': '검토하지 않은 새 답변 문장', 'finding_ids': packed['finding_ids'],
                                           'evidence_ids': packed['evidence_ids']}], 'limitations': []}, packed)
    result = evaluate(work, packed)
    assert not result['claims']
    assert result['control']['gate'] == 'BOUNDED'


def test_not_applicable_requires_its_own_coverage_review(work):
    ids = establish(work)
    apply(work, {'op': 'mark_not_applicable', 'issue_id': ids['tmp:i'], 'expected_version': 1,
                 'finding_ids': [ids['tmp:f']], 'reason': '합성 적용 제외 주장'})
    coverage = work.heads('claim', current=True)
    assert coverage[0]['payload']['purpose'] == 'coverage'
    result = evaluate(work, pack(work, PROFILE))
    assert result['control']['gate'] == 'BOUNDED'
    assert any('검토' in s for s in result['unresolved'])


def test_current_applicability_requires_verified_source_date(work):
    ids = establish(work)
    with pytest.raises(ProposalError, match='effective date'):
        apply(work, {'op': 'propose_finding', 'temp_id': 'tmp:new', 'issue_id': ids['tmp:i'],
                     'assessment_ids': [ids['tmp:a']], 'fact_ids': [], 'text': '지금 적용', 'applicability': 'current'})


def test_conflicting_assessment_is_not_hidden_by_selected_finding(work):
    ids = establish(work)
    seed(work, '특정 경우에는 승인 없이 진행한다.', 'E2')
    apply(work, {'op': 'assess', 'temp_id': 'tmp:opposed', 'issue_id': ids['tmp:i'], 'evidence_ids': ['E2'],
                 'relation': 'contradicts', 'reason': '원칙과 예외 적용의 충돌 미해결'}, evidence_ids=['E2'])
    packed, _ = draft_and_review(work)
    assert set(packed['evidence_ids']) == {'E1', 'E2'}
    result = evaluate(work, packed)
    assert result['control']['gate'] == 'BOUNDED'
    assert not result['claims']
    assert any('상충' in r for r in result['unresolved'])


def test_packer_never_fills_between_disjoint_fragments(work):
    block = '승인 원칙 사이에 읽지 않은 문장 위임 예외'
    seed(work, '승인 원칙', 'E1', source_id='source:shared', block_text=block)
    seed(work, '위임 예외', 'E2', source_id='source:shared', start=block.index('위임'), block_text=block)
    ids = apply(work, {'op': 'create_issue', 'temp_id': 'tmp:i', 'issue': issue()},
        {'op': 'assess', 'temp_id': 'tmp:a', 'issue_id': 'tmp:i', 'evidence_ids': ['E1','E2'], 'relation': 'qualifies', 'reason': '두 원문'},
        {'op': 'propose_finding', 'temp_id': 'tmp:f', 'issue_id': 'tmp:i', 'assessment_ids': ['tmp:a'], 'fact_ids': [],
         'text': '원칙과 예외', 'applicability': 'source_only'}, evidence_ids=['E1','E2'])
    packed = pack(work, PROFILE)
    assert [c['text'] for c in packed['contexts']] == ['승인 원칙\n위임 예외']
    assert len(packed['contexts'][0]['evidence_spans']) == 2
    limited = pack(work, {**PROFILE, 'max_context_chars': 1})
    assert limited['incomplete'] and not limited['contexts'] and limited['unresolved']


def test_packer_merges_only_overlapping_text_preserving_both_anchors(work):
    block = '승인 원칙과 위임 예외'
    seed(work, block[:7], 'E1', source_id='source:shared', block_text=block)
    seed(work, block[4:], 'E2', source_id='source:shared', start=4, block_text=block)
    apply(work, {'op': 'create_issue', 'temp_id': 'tmp:i', 'issue': issue()},
          {'op': 'assess', 'temp_id': 'tmp:a', 'issue_id': 'tmp:i', 'evidence_ids': ['E1', 'E2'], 'relation': 'qualifies', 'reason': '겹치는 원문'},
          {'op': 'propose_finding', 'temp_id': 'tmp:f', 'issue_id': 'tmp:i', 'assessment_ids': ['tmp:a'], 'fact_ids': [],
           'text': '원칙과 예외', 'applicability': 'source_only'}, evidence_ids=['E1', 'E2'])
    packed = pack(work, PROFILE)
    assert packed['contexts'][0]['text'] == block
    assert len(packed['contexts'][0]['blocks']) == 1
    assert len(packed['contexts'][0]['evidence_spans']) == 2


def test_late_reply_is_recorded_but_never_applied(work):
    view = work.save_view('investigate', {}, [])
    attempt = work.reserve_attempt(view, {}, 'logical', 1, 'investigate')
    work.attempt_sent(attempt)
    work.context = replace(work.context, deadline=time.monotonic()-1)
    assert work.finish_attempt(attempt, 'SUCCEEDED', {'raw': True}, {}) == 'IGNORED_LATE'
    with pytest.raises(ProposalError):
        work.apply_proposal(view, proposal(), event_id='late')


def test_nonretryable_auth_error_and_actual_model_mismatch(work):
    transport = WireTransport([TransportError('auth', retryable=False)])
    gateway = ModelGateway(work, work.context, PROFILE, DOMAIN, transport)
    view = work.save_view('investigate', {}, [])
    with pytest.raises(TransportError):
        gateway.generate('investigate', view, 'InvestigateDecision')
    assert len(transport.calls) == 1
    class FormatFailure(WireTransport):
        def send_once(self, **kwargs):
            self.calls.append(kwargs['body'])
            raise ProposalError('adapter classified model format failure')
    format_transport = FormatFailure()
    with pytest.raises(ProposalError, match='format failure'):
        ModelGateway(work, work.context, PROFILE, DOMAIN, format_transport).generate(
            'investigate', view, 'InvestigateDecision')
    attempts = list(work.db.execute('SELECT status,receipt_json FROM model_attempt ORDER BY created_seq'))
    assert attempts[-1][0] == 'FAILED'
    assert json.loads(attempts[-1][1])['error'] == 'MODEL_PROPOSAL_INVALID'

    class WrongModel(WireTransport):
        def send_once(self, **kwargs):
            response = wire(proposal())
            response['body_json']['model'] = 'unexpected'
            return response
    with pytest.raises(ContractError, match='actual response model'):
        ModelGateway(work, work.context, PROFILE, DOMAIN, WrongModel()).generate('investigate', view, 'InvestigateDecision')


def test_genos_single_send_has_total_deadline_and_no_hidden_retry(monkeypatch):
    target = endpoint('http://synthetic.invalid', api_prefix='/v1')
    binding = {**BINDING, 'provider': 'genos', 'adapter_version': 'genos-single-send-v1',
               'endpoint_identity': text_hash(target.root)}
    transport = GenosTransport(target, binding)
    calls = []
    import time
    from contextlib import contextmanager
    import semantic_runtime.legal_agent.transport as module
    @contextmanager
    def opened(*args, **kwargs):
        calls.append(args)
        time.sleep(.1)
        kwargs['deadline'].check()
        yield None
    monkeypatch.setattr(module, 'open_response', opened)
    with pytest.raises(TransportError) as caught:
        transport.send_once(body={}, ticket={'remaining_seconds': .02})
    assert caught.value.unknown and len(calls) == 1


def test_genos_http_failure_is_diagnosable_in_container_log_without_response_body(monkeypatch):
    target = endpoint('http://synthetic.invalid', api_prefix='/v1')
    binding = {**BINDING, 'provider': 'genos', 'adapter_version': 'genos-single-send-v1',
               'endpoint_identity': text_hash(target.root)}
    transport = GenosTransport(target, binding)
    from contextlib import contextmanager
    import semantic_runtime.legal_agent.transport as module
    from semantic_runtime.stdlib_http import Response
    class Raw(io.BytesIO):
        code = 400
        headers = {'content-type': 'application/json'}
    @contextmanager
    def opened(*args, **kwargs):
        raw = Raw(json.dumps({'error': {
            'type': 'invalid_request_error', 'code': 'unsupported_parameter',
            'param': 'response_format',
            'message': 'response_format json_schema is unsupported; PRIVATE SOURCE TEXT',
        }}).encode())
        with raw:
            yield Response(raw, kwargs['timeout'], kwargs['deadline'])
    monkeypatch.setattr(module, 'open_response', opened)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(obs.JsonFormatter())
    logger = obs.get_logger('legal_agent.model_http')
    logger.addHandler(handler)
    try:
        with pytest.raises(TransportError) as caught:
            transport.send_once(body={'messages': [{'content': 'PRIVATE QUESTION'}]},
                                ticket={'remaining_seconds': 1, 'attempt_id': 'M123'})
    finally:
        logger.removeHandler(handler)
    assert caught.value.response['status_code'] == 400
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    failed = next(e for e in events if e['event'] == 'model_http.failed')
    assert failed['attempt_id'] == 'M123'
    assert failed['http_status'] == 400
    assert failed['upstream_error_code'] == 'unsupported_parameter'
    assert failed['upstream_error_param'] == 'response_format'
    assert 'json_schema' in failed['upstream_error_hints']
    assert 'PRIVATE' not in stream.getvalue()


def test_model_attempt_log_correlates_run_phase_and_upstream_status(work):
    view = work.save_view('investigate', {}, [])
    transport = WireTransport([TransportError('upstream HTTP error', retryable=False,
                                              response={'status_code': 400})])
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(obs.JsonFormatter())
    logger = obs.get_logger('legal_agent.model')
    logger.addHandler(handler)
    try:
        with obs.context(request_id='request-123'):
            with pytest.raises(TransportError):
                ModelGateway(work, work.context, PROFILE, DOMAIN, transport).generate(
                    'investigate', view, 'InvestigateDecision')
    finally:
        logger.removeHandler(handler)
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    started = next(e for e in events if e['event'] == 'model.attempt.started')
    failed = next(e for e in events if e['event'] == 'model.attempt.failed')
    assert started['request_id'] == failed['request_id'] == 'request-123'
    assert started['run_id'] == failed['run_id'] == work.context.run_id
    assert started['attempt_id'] == failed['attempt_id']
    assert failed['phase'] == 'investigate'
    assert failed['http_status'] == 400
    assert failed['retry_scheduled'] is False


def test_fastapi_validation_details_keep_field_paths_but_not_input():
    details = _error_details({'detail': [{
        'loc': ['body', 'response_format', 'type'],
        'type': 'value_error',
        'msg': 'PRIVATE SOURCE TEXT',
        'input': 'PRIVATE QUESTION',
    }]})
    assert details['validation_locations'] == ['body.response_format.type']
    assert details['validation_error_types'] == ['value_error']
    assert 'PRIVATE' not in json.dumps(details)


def test_unreviewed_composer_notes_cannot_bypass_claim_review(tmp_path, generation):
    note = '근거 없이도 무조건 승인이 면제된다는 검증되지 않은 주장'
    class NotesTransport(RevisionTransport):
        def send_once(self, **kwargs):
            response = super().send_once(**kwargs)
            message = response['body_json']['choices'][0]['message']
            data = json.loads(message['content'])
            if 'paragraphs' in data:
                data['limitations'] = [note]
                message['content'] = json.dumps(data, ensure_ascii=False)
            return response
    transport = NotesTransport()
    with TestClient(make_app(tmp_path, generation, transport)) as client:
        response = client.post('/v1/rag/ask', json={'question': '승인 필요?', 'document_ids': ['d']})
        assert response.status_code == 200, response.text
        assert note not in response.text
    review_views = [json.loads(c['messages'][1]['content'])['view'] for c in transport.calls
                    if json.loads(c['messages'][1]['content'])['view']['phase'] == 'review']
    assert all(v['unverified_composer_notes'] == [note] for v in review_views)


def test_direct_pipeline_call_completes_durable_publication(tmp_path, generation):
    app = make_app(tmp_path, generation)
    with TestClient(app):
        result = app.state.pipeline.run('승인 필요?', ['d'], False, execution_context={'runtime': tmp_path/'direct'})
        Contracts(ROOT).validate_port('runtime.result', result)
    saved = list((tmp_path/'direct/runs').glob('*.json'))
    assert len(saved) == 1
    envelope = json.loads(saved[0].read_text())
    assert envelope['answer'] == result['answer']
    journal = next((tmp_path/'direct/legal-agent/runs').glob('*/*/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT status FROM run').fetchone()[0] == 'COMPLETED'


def test_candidate_manifest_topology_and_code_pins_are_valid():
    import importlib.util
    spec = importlib.util.spec_from_file_location('legal_agent_host_check', ROOT/'02_BACKEND/PIPELINE/engine_host.py')
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    planned = host.plan(host.load(ROOT), 'legal-agent-rag-v1', root=ROOT)
    assert [step['node'] for step in planned['steps']] == ['retrieve', 'select', 'assemble', 'answer']
    assert planned['mode'] == 'tool'


def test_foreign_generation_exact_span_and_scope_rejected(tmp_path, generation):
    app = make_app(tmp_path, generation)
    p = app.state.pipeline
    request = {'question': '승인', 'document_ids': ['d'], 'use_llm': False}
    with p.term_agent.open_session(request, query=p.plan('승인',['d']), runtime=tmp_path/'runtime') as s:
        d = s.sources.execute(tool('list_documents', query='', cursor=None))['items'][0]['document']
        node = s.sources.execute(tool('list_structure', document=d, cursor=None))['items'][0]['node']
        obs = s.sources.execute(tool('read_node', node=node, cursor=None))
        e = s.work.evidence(obs['evidence_ids'][0])
        for field, value in [('generation_id', 'elsewhere'), ('document_id', 'other'), ('text_hash', 'f'*64)]:
            bad = deepcopy(e)
            bad[field] = value
            with pytest.raises(ContractError):
                s.sources.verify(bad)
        e['spans'][0]['text'] = '근거 변조'
        with pytest.raises(ContractError, match='exact-span'):
            s.sources.verify(e)


def test_shared_pipeline_requests_have_isolated_journals_and_queries(tmp_path, generation):
    app = make_app(tmp_path, generation)
    with TestClient(app) as client:
        def ask(did):
            response = client.post('/v1/rag/ask', json={'question': '문서', 'document_ids': [did], 'use_llm': False})
            assert response.status_code == 200, response.text
            return response.json()
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = list(pool.map(ask, ['d', 'other']))
    assert a['run_id'] != b['run_id'] and a['query']['id'] != b['query']['id']
    assert a['query']['scope']['document_version_ids'] == ['d']
    assert b['query']['scope']['document_version_ids'] == ['other']


def test_admission_limit_returns_503_without_hidden_queue(tmp_path, generation):
    app = make_app(tmp_path, generation, execution_profile={**PROFILE, 'max_concurrent_requests_per_process': 1})
    agent = app.state.pipeline.term_agent
    agent.admission.acquire()
    try:
        with TestClient(app) as client:
            response = client.post('/v1/rag/ask', json={'question': '문서', 'document_ids': ['d'], 'use_llm': False})
            assert response.status_code == 503
            assert response.json()['run_id']
    finally:
        agent.admission.release()


class RewriteTransport(RevisionTransport):
    def __init__(self):
        super().__init__()
        self.reviews = 0
    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        if view['phase'] != 'review':
            return super().send_once(body=body, ticket=ticket)
        self.calls.append(body)
        self.reviews += 1
        claims = [h for h in view['work']['entities'] if h['kind'] == 'claim' and h['validity'] == 'CURRENT']
        return wire({'claims': [{'claim_id': c['entity_id'], 'claim_version': c['version'],
                    'verdict': 'NEEDS_REWRITE' if self.reviews == 1 else 'SUPPORTED', 'reason': '모의 표현 보완',
                    'evidence_ids': c['payload']['evidence_ids'], 'follow_up_reads': []} for c in claims],
                     'question_checks': [{'question_piece_id': 'Q1', 'claim_ids': [c['entity_id'] for c in claims],
                         'status': 'RESOLVED', 'reason': '모의 직접 대조', 'follow_up_reads': []}],
                     'whole_question': {'status': 'RESOLVED', 'reason': '모의 전체 대조', 'follow_up_reads': []}})


def test_recompose_reuses_current_assembly_without_research(tmp_path, generation):
    app = make_app(tmp_path, generation, RewriteTransport())
    with TestClient(app) as client:
        r = client.post('/v1/rag/ask', json={'question': '승인 원칙을 설명해줘', 'document_ids': ['d']})
        assert r.status_code == 200, r.text
        assert r.json()['answer']['claims']
    journal = next((tmp_path/'90_RUNTIME/semantic/legal-agent/runs').glob('*/*/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        assert db.execute("SELECT count(*) FROM stage_artifact WHERE stage='retrieve'").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM stage_artifact WHERE stage='answer'").fetchone()[0] == 2


def test_no_progress_bounds_empty_searches_and_keeps_finalize_budget(tmp_path, generation):
    transport = WireTransport([proposal(reads=[tool('search_text', query='존재하지않는합성어', document=None, cursor=None)]) for _ in range(5)])
    app = make_app(tmp_path, generation, transport)
    with TestClient(app) as client:
        r = client.post('/v1/rag/ask', json={'question': '미확인 질문', 'document_ids': ['d']})
        assert r.status_code == 200, r.text
        assert not r.json()['answer']['claims']
        assert '진전 없이' in r.json()['answer']['text']
        assert len(transport.calls) == PROFILE['max_no_progress']


def test_els_metadata_does_not_leak_into_closed_request_contract():
    import service
    value = service._normalize({'API_TYPE': 'ELS_QUERY', 'question': '승인?', 'channel': 'chat', 'session_id': 's', 'request_id': 'r'})
    assert value['json'] == {'question': '승인?'}
