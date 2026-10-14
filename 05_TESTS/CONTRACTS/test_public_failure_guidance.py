"""Failure notices retain actionable codes across API, workflow and chat hops."""
import asyncio
from copy import deepcopy
import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from semantic_runtime import chat_adapter as adapter
from semantic_runtime.app import legal_error_payload
from semantic_runtime.legal_agent.errors import (
    AdmissionRejected, ContractError, DeadlineExceeded, InvestigationPending, TransportError,
)
from test_structure_first_search import structured_generation
from test_unified_legal_agent import unified


def wrapped_timeout():
    try:
        raise TimeoutError('private timeout details')
    except TimeoutError as cause:
        exc = TransportError('private model details', unknown=True)
        exc.__cause__ = cause
        return exc


@pytest.mark.parametrize('exc,status,marker', [
    (AdmissionRejected('private capacity'), 503, '503'),
    (TransportError('private upstream', response={'status_code': 503}), 502, '503'),
    (wrapped_timeout(), 502, 'timeout'),
    (DeadlineExceeded('private deadline'), 504, 'timeout'),
    (ContractError('private hash mismatch'), 500, '500'),
    (InvestigationPending('private no verified claims'), 422, None),
])
def test_actual_v6_api_failure_preserves_status_code_and_no_extra_calls(unified, monkeypatch, exc, status, marker):
    client, send, transport, _, runtime = unified
    calls = []
    def fail(*a, **kw):
        calls.append(1)
        raise exc
    monkeypatch.setattr(client.app.state.pipeline, 'run', fail)
    response = send()
    assert response.status_code == status
    body = response.json()
    assert body['answer_status'] == 'failed' and body.get('error_code') == marker
    assert body['message'].startswith('현재 충분한 법률 검토를 하지 못했습니다.')
    assert 'private' not in response.text and 'answer' not in body
    assert len(calls) == 1 and transport.phases == []
    assert not list((runtime / 'runs').glob('*.json'))
    view = adapter.views()
    original = deepcopy(body)
    projected = view.public_response(body, status=status)
    assert view.public_response(projected, status=status) == projected
    assert body == original
    text = view.render(projected)
    assert f'({marker})' in text if marker else '조금 더 구체적으로 질문해 주세요.' in text
    if marker:
        assert '질문해 주세요' not in text


@pytest.mark.parametrize('route', ['/json', '/stream'])
@pytest.mark.parametrize('kind', ['bootstrap', 'timeout', 'incomplete'])
def test_workflow_backend_keeps_marker_and_bound_display(monkeypatch, tmp_path, route, kind):
    import main_workflow
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path))
    status, body = {
        'bootstrap': (503, {'code': 'RUNTIME_BOOTSTRAP_ERROR', 'detail': 'private bootstrap'}),
        'timeout': (502, legal_error_payload(wrapped_timeout(), 'notice-r1')),
        'incomplete': (422, legal_error_payload(InvestigationPending('private'), 'notice-r1')),
    }[kind]
    async def service(config, data):
        return {'status': status, 'body': body}
    monkeypatch.setattr(main_workflow.backend, 'service', service)
    response = TestClient(main_workflow.app).post(route, json={
        'API_TYPE': 'LEGAL_AGENT', 'question': '모의 질문', 'request_id': 'notice-r1'})
    if route == '/stream':
        frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        result = next(f['data'] for f in frames if f['event'] == 'result')
    else:
        result = response.json()
    public = result['body']
    assert result['status'] == status and public['answer_status'] == 'failed'
    assert 'private' not in json.dumps(result)
    display = public['workflow_display']
    assert adapter.views()._bound_workflow_display(adapter.views().unwrap(result), 'notice-r1') == display
    marker = {'bootstrap': '503', 'timeout': 'timeout', 'incomplete': None}[kind]
    assert public.get('error_code') == marker
    assert display['answer_status'] == 'failed'
    assert f'({marker})' in display['text'] if marker else '질문해 주세요' in display['text']


@pytest.mark.parametrize('phase', ['preflight', 'request'])
@pytest.mark.parametrize('kind', ['http', 'wrapped_timeout'])
def test_standalone_workflow_reports_transport_failures_once(monkeypatch, phase, kind):
    view = adapter.views()
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'off')
    calls = []
    def fail():
        calls.append(1)
        if kind == 'http':
            raise urllib.error.HTTPError('https://fixture.invalid', 503, 'private', {}, io.BytesIO(b'private'))
        raise urllib.error.URLError(TimeoutError('private timeout'))
    def preflight(data):
        if phase == 'preflight':
            fail()
        return {'status': 200, 'body': {'ad_handled': False}}
    async def request(*a, **kw):
        fail()
    monkeypatch.setattr(view, '_post_code_serving', preflight)
    monkeypatch.setattr(view, '_stream_code_serving', request)
    result = asyncio.run(view.run({'question': '모의 질문', 'request_id': 'notice-r1'}))
    assert result['answer_status'] == 'failed' and len(calls) == 1
    marker = '503' if kind == 'http' else 'timeout'
    assert f'({marker})' in result['text'] and 'private' not in result['text']


@pytest.mark.parametrize('mode', ['json', 'sse'])
def test_native_chat_failure_after_delta_stays_failed(monkeypatch, tmp_path, mode):
    import main
    from semantic_runtime.legal_agent.answer_stream import current_sink
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path))
    monkeypatch.setenv('GENOS_MEMORY_ENABLED', '0')
    calls = []
    async def service(data):
        calls.append(1)
        sink = current_sink()
        if sink:
            sink('작성 중인 미완료 문장')
        raise wrapped_timeout()
    monkeypatch.setattr(adapter, 'call_service', service)
    response = TestClient(main.app).post('/chat', json={
        'question': '모의 질문', 'request_id': 'notice-r1', 'stream': mode == 'sse'})
    if mode == 'sse':
        frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        result = next(f['data'] for f in frames if f['event'] == 'result')
        assert '작성 중인 미완료 문장' in response.text
    else:
        result = response.json()['data']
    assert result['answer_status'] == 'failed' and '(timeout)' in result['text']
    assert '작성 중인 미완료 문장' not in result['text']
    assert 'private' not in response.text and len(calls) == 1


def test_normal_partial_and_fact_request_answers_are_preserved():
    view = adapter.views()
    for coverage in ('FULL', 'PARTIAL', 'INSUFFICIENT'):
        body = {'answer': {'text': '확인한 범위의 답변. 적용 시점을 알려 주세요.'},
                'assembly': {'term_agent': {'completion_contract': 'v8', 'answer_coverage': coverage}}}
        assert view.render(view.public_response(body)).startswith(body['answer']['text'])
        assert view._completion_answer_status(body, True) == ('answered' if coverage == 'FULL' else 'partial')
    assert view.render({}) == view.REVIEW_INCOMPLETE_MESSAGE


def test_unknown_codes_and_raw_error_text_cannot_enter_notice():
    view = adapter.views()
    body = {'request_id': 'notice-r1', 'answer_status': 'failed',
            'failure_reason': 'technical', 'error_code': '<script>private</script>',
            'detail': 'timeout 503 private', 'message': 'private', 'traceback': 'private'}
    result = view.public_response(body)
    assert result['error_code'] == 'internal' and 'private' not in json.dumps(result)
    assert '(처리 오류)' in view.render(result)
