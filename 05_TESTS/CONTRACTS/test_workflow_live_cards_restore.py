"""Foldable workflow action cards arrive before preflight or the final SSE answer."""
import asyncio
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import sys
import threading
import types

import pytest

ROOT = Path(__file__).resolve().parents[2]


def workflow():
    path = Path(os.environ.get('WORKFLOW_CARDS_TEST_FILE', str(
        ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')))
    module = types.ModuleType('live_cards_restore')
    module.__file__ = str(path)
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), module.__dict__)
    return module


def cards(sent):
    return [json.loads(block['data']['output']['content'])['visible_rationale']
            for event, value, room in sent if event == 'agentFlowExecutedData'
            for block in value]


@pytest.mark.parametrize('mode', [None, 'on', 'socketio', 'socketio-inline'])
def test_preparation_card_precedes_slow_preflight_and_answer(monkeypatch, mode):
    if mode is None:
        monkeypatch.delenv('GENOS_RAG_PROGRESS_UI', raising=False)
    else:
        monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', mode)
    w = workflow()
    sent = []
    ready = threading.Event()
    release = threading.Event()
    backend_calls = []

    async def emit(event, value, room=None):
        sent.append((event, value, room))
    monkeypatch.setitem(sys.modules, 'main_socketio', types.SimpleNamespace(
        sio_server=types.SimpleNamespace(emit=emit)))

    def preflight(body):
        assert body['API_TYPE'] == 'AD_PROBE'
        ready.set()
        assert release.wait(3)
        return {'status': 200, 'body': {}}
    monkeypatch.setattr(w, '_post_code_serving', preflight)

    async def backend(question, data, display, *, probe=False):
        backend_calls.append(data['request_id'])
        await display.progress({'schema_version': 'rag-progress-v1',
            'kind': 'candidate', 'label': '관련 원문 후보를 찾았습니다', 'count': 2})
        return {'answer': {'text': '확인한 답변.'}, 'assembly': {}}
    monkeypatch.setattr(w, '_stream_code_serving', backend)

    async def check():
        task = asyncio.create_task(w.run({'question': '공개 모의 질문',
            'request_id': 'live-prepare', 'socketIOClientId': 'real-chat-room'}))
        try:
            assert await asyncio.to_thread(ready.wait, 2)
            assert not task.done() and not backend_calls
            assert any('준비' in text and '있습니다' in text for text in cards(sent))
            assert all(room == 'real-chat-room' for event, value, room in sent)
            assert not any(event == 'token' and '확인한 답변' in value
                           for event, value, room in sent)
        finally:
            release.set()
            result = await asyncio.wait_for(task, 3)
        assert result['text'] == '확인한 답변.'
        assert backend_calls == ['live-prepare']
        assert any('관련 원문 후보' in text for text in cards(sent))
        assert sent[-1] == ('end', 'end', 'real-chat-room')
        tokens = [value for event, value, room in sent if event == 'token']
        assert ''.join(tokens) == '확인한 답변.'
    asyncio.run(check())


def test_actual_sse_action_and_full_judgment_cards_arrive_before_result(monkeypatch):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio')
    w = workflow()
    sent = []
    entered = threading.Event()
    release = threading.Event()
    requests = []
    detail = '현재 판단: ' + '확인된 근거와 적용 조건 ' * 100

    async def emit(event, value, room=None):
        sent.append((event, value, room))
    monkeypatch.setitem(sys.modules, 'main_socketio', types.SimpleNamespace(
        sio_server=types.SimpleNamespace(emit=emit)))
    monkeypatch.setattr(w, '_post_code_serving', lambda body: {'status': 200, 'body': {}})
    monkeypatch.setattr(w, '_settings', lambda: ('http://mock-server/json', 'mock-token', 2100))

    class Response:
        status = 200
        headers = {'Content-Type': 'text/event-stream'}
        def __init__(self, rid):
            self.rid = rid
        def __enter__(self):
            return self
        def __exit__(self, *args):
            release.set()
        def __iter__(self):
            yield b': connected\n\n'
            for kind, label, details, basis in [
                ('phase', '원문 확인 · 원문을 열람 중', [],
                 {'kind': 'WORKFLOW_CHECKPOINT', 'detail_mode': 'activity'}),
                ('decision', '적용 판단 · 현재 판단을 확인했습니다', [detail],
                 {'kind': 'CASE_JUDGMENT_ACCEPTED', 'stage': 'ASSESS',
                  'detail_mode': 'judgment', 'state': 'COMPLETED'})]:
                yield ('data: ' + json.dumps({'event': 'progress', 'data': {
                    'schema_version': 'rag-progress-v1', 'request_id': self.rid,
                    'kind': kind, 'label': label, 'details': details, 'basis': basis}},
                    ensure_ascii=False) + '\n\n').encode()
            entered.set()
            assert release.wait(3)
            yield ('data: ' + json.dumps({'event': 'result', 'data': {'status': 200,
                'body': {'answer': {'text': '최종 확인.'}}}}) + '\n\n').encode()

    def urlopen(request, timeout):
        requests.append(request.full_url)
        return Response(json.loads(request.data)['request_id'])
    monkeypatch.setattr(w.urllib.request, 'urlopen', urlopen)

    async def check():
        task = asyncio.create_task(w.run({'question': '공개 모의 질문',
            'socketIOClientId': 'chat-room', 'request_id': 'stream-card'}))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            # The reader waits for each queued item, so a short event-loop turn
            # completes the current card emit without releasing the result.
            for _ in range(30):
                if any(detail.strip() in text for text in cards(sent)):
                    break
                await asyncio.sleep(0.01)
            assert not task.done()
            assert any('원문을 열람 중' in text for text in cards(sent))
            assert any(detail.strip() in text for text in cards(sent))
            assert not any(event == 'token' for event, value, room in sent)
        finally:
            release.set()
            result = await asyncio.wait_for(task, 3)
        assert result['text'] == '최종 확인.'
        assert result['code_serving_transport']['progress_events'] == 2
        assert result['workflow_progress_delivery']['emitted_card_events'] >= 3
        assert requests == ['http://mock-server/stream']
    asyncio.run(check())


@pytest.mark.parametrize('mode,with_sid', [('off', True), ('final-cards', True),
    ('socketio-final', True), ('socketio', False)])
def test_optional_socket_modes_keep_final_dict_and_report_true_settings(monkeypatch, mode, with_sid):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', mode)
    monkeypatch.setitem(sys.modules, 'main_socketio', None)
    w = workflow()
    monkeypatch.setattr(w, '_settings', lambda: ('http://mock-server/json', 'mock-token', 2100))
    settings = w._workflow_settings({'request_id': 'settings'})['workflow_settings']
    assert settings['progress_mode'] == mode
    monkeypatch.setattr(w, '_post_code_serving', lambda body: {})
    async def backend(question, data, display, *, probe=False):
        await display.progress({'schema_version': 'rag-progress-v1', 'kind': 'phase',
            'label': '원문 확인 중'})
        return {'answer': {'text': '최종.'}}
    monkeypatch.setattr(w, '_stream_code_serving', backend)
    data = {'question': '모의'}
    if with_sid:
        data['socketIOClientId'] = 'room'
    result = asyncio.run(w.run(data))
    assert result['text'] == '최종.'
    if mode == 'off':
        assert not result.get('agentFlowExecutedData')
    elif mode == 'final-cards' or not with_sid:
        assert result['agentFlowExecutedData']


def test_failed_workflow_emitter_keeps_one_backend_result(monkeypatch):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio')
    w = workflow()
    monkeypatch.setitem(sys.modules, 'main_socketio', None)
    monkeypatch.setattr(w, '_post_code_serving', lambda body: {})
    calls = []
    async def backend(question, data, display, *, probe=False):
        calls.append(data['request_id'])
        return {'answer': {'text': '보존한 답변.'}}
    monkeypatch.setattr(w, '_stream_code_serving', backend)
    result = asyncio.run(w.run({'question': '모의', 'request_id': 'emitter-fail',
        'socketIOClientId': 'room'}))
    assert result['text'] == '보존한 답변.'
    assert calls == ['emitter-fail']


def test_local_http_stream_flushes_foldable_cards_before_final_answer(monkeypatch):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio')
    w = workflow()
    sent = []
    release = threading.Event()
    observed = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            observed.append((self.path, data['API_TYPE']))
            self.send_response(200)
            if self.path == '/json':
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status":200,"body":{}}')
                return
            assert self.path == '/stream'
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            self.wfile.write(('data: ' + json.dumps({'event': 'progress', 'data': {
                'schema_version': 'rag-progress-v1', 'request_id': data['request_id'],
                'kind': 'selected', 'label': '근거 선택 · 원문을 선택했습니다'}}) + '\n\n').encode())
            self.wfile.flush()
            assert release.wait(4)
            self.wfile.write(('data: ' + json.dumps({'event': 'result', 'data': {
                'status': 200, 'body': {'answer': {'text': 'HTTP 최종 답변.'}}}},
                ensure_ascii=False) + '\n\n').encode())
            self.wfile.flush()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(w, '_settings', lambda: (
        f'http://127.0.0.1:{server.server_port}/json', 'synthetic-only', 5))
    async def emit(event, value, room=None):
        sent.append((event, value, room))
    monkeypatch.setitem(sys.modules, 'main_socketio', types.SimpleNamespace(
        sio_server=types.SimpleNamespace(emit=emit)))

    async def check():
        task = asyncio.create_task(w.run({'question': '공개 모의',
            'request_id': 'local-http-card', 'socketIOClientId': 'local-chat-room'}))
        try:
            for _ in range(200):
                if any('원문을 선택했습니다' in text for text in cards(sent)):
                    break
                await asyncio.sleep(0.01)
            assert any('준비 중' in text for text in cards(sent))
            assert any('원문을 선택했습니다' in text for text in cards(sent))
            assert not task.done()
            assert not any(event == 'token' for event, value, room in sent)
        finally:
            release.set()
            result = await asyncio.wait_for(task, 3)
        assert result['text'] == 'HTTP 최종 답변.'
        assert result['workflow_progress_delivery']['emitted_card_events'] >= 2
        assert result['code_serving_transport']['opened']
        assert observed == [('/json', 'AD_PROBE'), ('/stream', 'LEGAL_AGENT')]
    try:
        asyncio.run(check())
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_genos_native_panel_receives_token_card_end_and_same_final_cards(monkeypatch):
    """GENOS V1.8.6 panel prerequisites from 514 and the progress bridge."""
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio')
    w = workflow()
    stream_started = False
    panel = []
    emissions = []
    backend_entered = asyncio.Event()
    release = asyncio.Event()

    async def emit(event, value, room=None):
        nonlocal stream_started
        emissions.append((event, value))
        if event == 'token' and value.strip():
            stream_started = True
        elif event == 'agentFlowExecutedData':
            for block in value:
                assert block['nodeId'] and block['status'] == 'FINISHED'
                assert block['nodeLabel'] == 'Visible Reasoner'
                content = json.loads(block['data']['output']['content'])
                assert set(content) == {'visible_rationale'}
                assert isinstance(content['visible_rationale'], str)
            panel[:] = value
    monkeypatch.setitem(sys.modules, 'main_socketio', types.SimpleNamespace(
        sio_server=types.SimpleNamespace(emit=emit)))
    monkeypatch.setattr(w, '_post_code_serving', lambda body: {})
    server_cards = [{'nodeId': 'server-final-only'}]
    async def backend(question, data, display, *, probe=False):
        await display.progress({'schema_version': 'rag-progress-v1', 'kind': 'phase',
            'label': '근거 선택 · 원문을 확인 중'})
        backend_entered.set()
        await release.wait()
        return {'answer': {'text': '플랫폼 계약 최종 답변.'}}
    monkeypatch.setattr(w, '_stream_code_serving', backend)
    monkeypatch.setattr(w, '_bound_workflow_display', lambda body, rid: {
        'text': '플랫폼 계약 최종 답변.', 'schema_version': 'genos-workflow-display-v1',
        'producer': 'main_workflow', 'response_sha256': 'mock', 'content_sha256': 'mock',
        'agentFlowExecutedData': server_cards})

    async def check():
        task = asyncio.create_task(w.run({'question': '모의', 'socketIOClientId': 'room'}))
        try:
            await asyncio.wait_for(backend_entered.wait(), 2)
            assert not task.done()
            assert not stream_started and panel
            assert any('준비 중' in json.loads(row['data']['output']['content'])['visible_rationale']
                       for row in panel)
            assert emissions[0][0] == 'agentFlowExecutedData'
            assert not any(event == 'token' for event, value in emissions)
        finally:
            release.set()
            result = await asyncio.wait_for(task, 3)
        assert emissions[-1] == ('end', 'end')
        assert stream_started
        assert ''.join(value for event, value in emissions if event == 'token') == '플랫폼 계약 최종 답변.'
        assert result['agentFlowExecutedData'] == panel
        assert result['agentFlowExecutedData'] != server_cards
        assert result['text'] == '플랫폼 계약 최종 답변.'
    asyncio.run(check())
