"""SSE transport is independent of socket rendering and retains single execution."""
import asyncio
import importlib.util
import io
import json
from pathlib import Path
import threading
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, '_post_code_serving'):
        # These fixtures exercise the SSE transport after the current AD-mode
        # check. Provide its empty result separately so the SSE response mock
        # is not mistakenly consumed by the preflight /json request. The live
        # routed-workflow test verifies both requests on an actual HTTP port.
        original = module._post_code_serving
        def preflight(body):
            if body.get('API_TYPE') == 'AD_PROBE':
                return {'status': 200, 'body': {}}
            return original(body)
        module._post_code_serving = preflight
    return module


class Response:
    status = 200
    headers = {'Content-Type': 'text/event-stream', 'X-Genos-SSE-Revision': 'sse-transport-20260928-r1'}
    def __init__(self, frames): self.frames = frames
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def __iter__(self):
        yield b': connected\n\n'
        for frame in self.frames:
            yield ('data: ' + json.dumps(frame) + '\n\n').encode()


@pytest.mark.parametrize('mode', ['socketio-final', 'socketio', 'off'])
@pytest.mark.parametrize('socket', [False, True])
def test_stream_choice_does_not_depend_on_socket_or_progress_mode(monkeypatch, mode, socket):
    w = load('sse_workflow', '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', mode)
    monkeypatch.setattr(w, '_settings', lambda: ('http://fixture/json', 'fixture', 2100))
    monkeypatch.setattr(w, 'call_code_serving', lambda *a: pytest.fail('No JSON retry'))
    sent = []
    def send(req, timeout):
        sent.append(req.full_url)
        rid = json.loads(req.data)['request_id']
        return Response([
            {'event': 'progress', 'data': {'schema_version': 'rag-progress-v1',
              'request_id': rid, 'kind': 'heartbeat', 'label': '처리 중', 'elapsed_ms': 400000}},
            {'event': 'result', 'data': {'status': 200, 'body': {'answer': {'text': 'verified'}}}},
        ])
    monkeypatch.setattr(w.urllib.request, 'urlopen', send)
    data = {'question': 'synthetic'}
    if socket: data['socketIOClientId'] = 'fixture-socket'
    result = asyncio.run(w.run(data))
    assert sent == ['http://fixture/stream']
    assert result['text'] == 'verified' and result['answer_status'] == 'answered'
    assert result['code_serving_transport']['opened']
    assert result['code_serving_transport']['route'] == '/stream'
    assert result['code_serving_transport']['heartbeat_events'] == 1


@pytest.mark.parametrize('status', [404, 405, 500])
def test_fallback_without_socket_is_only_for_missing_stream(monkeypatch, status):
    w = load('fallback_sse_workflow', '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    monkeypatch.setattr(w, '_settings', lambda: ('http://fixture/json', 'fixture', 2100))
    calls = []
    def send(req, timeout):
        calls.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, status, 'synthetic', {}, io.BytesIO(b'Internal Server Error'))
    monkeypatch.setattr(w.urllib.request, 'urlopen', send)
    monkeypatch.setattr(w, 'call_code_serving', lambda *a: calls.append('/json') or {'answer': {'text': 'verified'}})
    result = asyncio.run(w.run({'question': 'synthetic'}))
    if status in (404, 405):
        assert calls == ['http://fixture/stream', '/json']
        assert result['code_serving_transport']['fallback_http_status'] == status
    else:
        assert calls == ['http://fixture/stream']
        assert result['http_status'] == 500 and result['answer_status'] == 'failed'


@pytest.mark.parametrize('input_data', [{'question': 'SSE_CHECK'}, {'API_TYPE': 'SSE_CHECK'}])
def test_probe_uses_actual_stream_and_never_a_legal_query(monkeypatch, input_data):
    w = load('probe_sse_workflow', '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    monkeypatch.setattr(w, '_settings', lambda: ('http://fixture/json', 'fixture', 2100))
    monkeypatch.setattr(w, 'call_code_serving', lambda *a: pytest.fail('No model probe'))
    def send(req, timeout):
        assert req.full_url.endswith('/stream')
        body = json.loads(req.data)
        assert body['API_TYPE'] == 'SSE_CHECK' and 'question' not in body
        return Response([{'event': 'result', 'data': {'sse_ready': True,
                         'stream_server_revision': 'sse-transport-20260928-r1', 'heartbeat_seconds': 10}}])
    monkeypatch.setattr(w.urllib.request, 'urlopen', send)
    result = asyncio.run(w.run(input_data))
    assert result['sse_check']['sse_ready'] and result['answer_status'] == 'diagnostics'


def test_missing_probe_route_never_falls_back_to_model(monkeypatch):
    w = load('missing_probe', '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    monkeypatch.setattr(w, '_settings', lambda: ('http://fixture/json', 'fixture', 2100))
    monkeypatch.setattr(w, 'call_code_serving', lambda *a: pytest.fail('No JSON probe retry'))
    def send(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 404, 'missing', {}, io.BytesIO())
    monkeypatch.setattr(w.urllib.request, 'urlopen', send)
    result = asyncio.run(w.run({'question': 'SSE_CHECK'}))
    assert result['sse_check']['http_status'] == 404 and not result['sse_check']['sse_ready']


def test_connection_break_after_stream_opens_does_not_restart_job(monkeypatch):
    w = load('broken_stream', '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    monkeypatch.setattr(w, '_settings', lambda: ('http://fixture/json', 'fixture', 2100))
    monkeypatch.setattr(w, 'call_code_serving', lambda *a: pytest.fail('No duplicate job'))
    class Broken(Response):
        def __iter__(self):
            yield b': connected\n\n'
            raise ConnectionError('synthetic stream disconnect')
    calls = []
    def send(req,timeout):
        calls.append(req.full_url)
        return Broken([])
    monkeypatch.setattr(w.urllib.request, 'urlopen', send)
    result = asyncio.run(w.run({'question':'synthetic'}))
    assert calls == ['http://fixture/stream']
    assert result['answer_status'] == 'failed'
    assert result['failure_kind'] == 'client_exception'
    assert result['code_serving_transport']['opened']


def test_failure_inside_sse_result_is_failed_not_answered(monkeypatch):
    w = load('failed_sse_result', '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    monkeypatch.setattr(w, '_settings', lambda: ('http://fixture/json', 'fixture', 2100))
    monkeypatch.setattr(w, 'call_code_serving', lambda *a: pytest.fail('No duplicate job'))
    monkeypatch.setattr(w.urllib.request, 'urlopen', lambda *a,**k: Response([
        {'event':'result','data':{'status':500,'body':{'error':'synthetic service failure'}}}]))
    result = asyncio.run(w.run({'question':'synthetic'}))
    assert result['answer_status'] == 'failed'
    assert result['text'].startswith('실행 오류 (HTTP 500)')
    assert 'synthetic service failure' in result['text']


def test_server_flushes_before_computation_and_heartbeats_until_result(monkeypatch):
    app = load('heartbeat_sse_app', '08_DEPLOYMENT/GENOS/stream_app.py')
    monkeypatch.setattr(app, 'HEARTBEAT_SECONDS', 0.01)
    released = threading.Event()
    calls = []
    expected = {'status': 200, 'body': {'answer': {'text': 'verified'}}}
    async def service(config, data):
        calls.append(data['request_id'])
        await asyncio.to_thread(released.wait, 2)
        return expected
    monkeypatch.setattr(app, 'service', service)
    class Request:
        async def json(self): return {'API_TYPE': 'LEGAL_AGENT', 'request_id': 'fixture-request'}
    async def consume():
        response = await app.stream_endpoint(Request())
        it = response.body_iterator
        assert await it.__anext__() == ': connected\n\n'
        assert calls == []
        beats = 0
        async for raw in it:
            if raw == ': keep-alive\n\n':
                beats += 1
                if beats == 3: released.set()
                continue
            frame = json.loads(raw[5:])
            assert not (frame['event'] == 'progress' and frame['data'].get('kind') == 'heartbeat')
            if frame['event'] == 'result': assert frame['data'] == expected
        assert beats >= 3 and len(calls) == 1
        assert not app._ACTIVE_REQUESTS
    try: asyncio.run(consume())
    finally: released.set()


def test_server_probe_never_calls_service(monkeypatch):
    app = load('probe_sse_app', '08_DEPLOYMENT/GENOS/stream_app.py')
    monkeypatch.setattr(app, 'service', lambda *a: pytest.fail('Probe must not load data/model'))
    class Request:
        async def json(self): return {'API_TYPE': 'SSE_CHECK'}
    async def consume():
        response = await app.stream_endpoint(Request())
        frames = [raw async for raw in response.body_iterator]
        assert response.headers['x-genos-sse-revision'] == 'sse-transport-20260928-r1'
        assert json.loads(frames[-1][5:])['data']['sse_ready']
        assert not app._ACTIVE_REQUESTS
    asyncio.run(consume())


def test_disconnect_after_initial_chunk_releases_reservation_without_computation(monkeypatch):
    app = load('early_disconnect_sse_app', '08_DEPLOYMENT/GENOS/stream_app.py')
    monkeypatch.setattr(app, 'service', lambda *a: pytest.fail('Disconnected before computation'))
    class Request:
        async def json(self): return {'API_TYPE': 'LEGAL_AGENT', 'request_id': 'disconnect-fixture'}
    async def consume():
        response = await app.stream_endpoint(Request())
        assert await response.body_iterator.__anext__() == ': connected\n\n'
        await response.body_iterator.aclose()
        assert not app._ACTIVE_REQUESTS
    asyncio.run(consume())


def test_startup_reuses_environment_port_and_rejects_conflicts(monkeypatch):
    start = load('sse_start', '08_DEPLOYMENT/GENOS/start_sse.py')
    for key in start.PORT_NAMES: monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match='기존 수신 포트'): start.port_from_environment()
    monkeypatch.setenv('PORT', '8017')
    assert start.port_from_environment() == 8017
    monkeypatch.setenv('UVICORN_PORT', '8018')
    with pytest.raises(ValueError, match='서로 다릅니다'): start.port_from_environment()
