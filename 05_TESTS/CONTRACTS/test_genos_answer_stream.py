"""Synthetic streaming contracts: early visibility, isolation, completion and failure."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import threading
from copy import deepcopy

import pytest

from semantic_runtime.legal_agent.answer_stream import DraftText, capture, current_sink
from semantic_runtime.legal_agent.transport import GenosTransport
from semantic_runtime.legal_agent.errors import ContractError, TransportError
from semantic_runtime.genos import endpoint
from conftest import term_glossary
from test_legal_agent_double_harness import generation, wire
from test_legal_agent_v5 import SETTINGS, drafted, session
from test_tool_exploration_v3 import delivered

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('ascii_output', [False, True])
@pytest.mark.parametrize('width', [1, 2, 7, 8192])
def test_projection_only_emits_paragraph_text_with_json_escapes(ascii_output, width):
    data = {'limitations': ['private limit'], 'paragraphs': [
        {'evidence': ['private-id'], 'text': '한글 "인용"\\경로\n다음 😀', 'reason': 'private reason'},
        {'text': '두 번째 문단', 'nested': {'text': 'private quote'}}], 'text': 'private metadata'}
    raw = json.dumps(data, ensure_ascii=ascii_output)
    emitted = []; projection = DraftText(emitted.append)
    for i in range(0, len(raw), width): projection.feed(raw[i:i+width])
    assert ''.join(emitted) == '\n\n'.join(p['text'] for p in data['paragraphs'])


def test_projection_exposes_text_before_paragraph_object_finishes():
    rows = []; parser = DraftText(rows.append)
    parser.feed('{"paragraphs":[{"text":"생성 중')
    assert rows == ['생성 중']
    parser.feed('입니다","evidence":["hidden"]}],"limitations":[]}')
    assert ''.join(rows) == '생성 중입니다'


def transport(monkeypatch, frames, *, json_body=None, status=200):
    requests = []
    import io
    from contextlib import contextmanager
    import semantic_runtime.legal_agent.transport as module
    from semantic_runtime.stdlib_http import Response
    class Raw(io.BytesIO):
        def __init__(self, payload, content_type):
            super().__init__(payload)
            self.code = status
            self.headers = {'content-type': content_type}
    @contextmanager
    def opened(method, url, *, headers, body, timeout, deadline):
        requests.append(body)
        payload = (json.dumps(json_body).encode() if json_body is not None else
                   b''.join(frame.encode() if isinstance(frame, str) else frame for frame in frames))
        raw = Raw(payload, 'application/json' if json_body is not None else 'text/event-stream')
        with raw:
            yield Response(raw, timeout, deadline)
    monkeypatch.setattr(module, 'open_response', opened)
    target = endpoint('http://fixture', token='synthetic', label='synthetic')
    binding = {'provider': 'genos', 'trust_zone': 'internal', 'adapter_version': 'genos-single-send-v1',
               'model': 'fixture-model', 'endpoint_identity': hashlib.sha256(target.root.encode()).hexdigest()}
    return GenosTransport(target, binding), requests


def frame(delta, *, finish=None, model='fixture-model', usage=None):
    return 'data: '+json.dumps({'model': model, 'choices': [{'index': 0, 'delta': delta,
                'finish_reason': finish}], 'usage': usage})+'\n\n'


def test_transport_preserves_complete_response_usage_and_private_reasoning(monkeypatch):
    parts = ['{"paragraphs":[{"text":"먼저', ' 보이는 답변"}],"limitations":[]}']
    t, requests = transport(monkeypatch, [frame({'reasoning_content': 'hidden thinking'}),
        frame({'content': parts[0]}), frame({'content': parts[1]}),
        frame({}, finish='stop', usage={'completion_tokens': 20}), 'data: [DONE]\n\n'])
    tokens = []; projection = DraftText(tokens.append)
    result = t.send_stream_once(body={'stream': True}, ticket={'remaining_seconds': 2}, on_content=projection.feed)
    assert len(requests) == 1 and requests[0]['stream'] is True
    assert ''.join(tokens) == '먼저 보이는 답변'
    body = result['body_json']
    assert body['choices'][0]['message']['content'] == ''.join(parts)
    assert body['choices'][0]['message']['reasoning_content'] == 'hidden thinking'
    assert body['usage'] == {'completion_tokens': 20} and result['stream_events']


@pytest.mark.parametrize('model_id', ['fixture-model', 'server-alias', None])
def test_stream_disconnect_is_unknown_and_never_a_completed_answer(monkeypatch, model_id):
    t, requests = transport(monkeypatch, [frame({'content': '{"paragraphs":[{"text":"일부 답변'}, model=model_id)])
    rows = []
    with pytest.raises(TransportError, match='before completion') as failure:
        t.send_stream_once(body={'stream': True}, ticket={'remaining_seconds': 2}, on_content=DraftText(rows.append).feed)
    assert failure.value.unknown and len(requests) == 1 and rows == ['일부 답변']


@pytest.mark.parametrize('model_id', ['fixture-model', 'server-alias', None])
def test_genos_stream_model_metadata_does_not_block_display(monkeypatch, model_id):
    t, requests = transport(monkeypatch, [
        frame({'content': '{"paragraphs":[{"text":"정상 본문"}]}'}, model=model_id),
        frame({}, finish='stop', model=model_id), 'data: [DONE]\n\n'])
    rows = []
    result = t.send_stream_once(body={'stream': True}, ticket={'remaining_seconds': 2},
                               on_content=DraftText(rows.append).feed)
    assert rows == ['정상 본문'] and len(requests) == 1
    assert result['body_json']['model'] == model_id
    assert result['stream_events'][0]['model'] == model_id


def test_buffered_gateway_keeps_same_single_request(monkeypatch):
    body = {'model': 'fixture-model', 'choices': [{'message': {'content': '{}'}}]}
    t, requests = transport(monkeypatch, [], json_body=body)
    rows = []
    result = t.send_stream_once(body={'stream': True}, ticket={'remaining_seconds': 2}, on_content=rows.append)
    assert result['body_json'] == body and len(requests) == 1 and not rows


def test_workflow_early_tokens_suppress_progress_and_do_not_duplicate_final(monkeypatch):
    w = load('answer_workflow', '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio')
    async def run():
        display = w._ChatProgress({'socketIOClientId': 'fixture'})
        sent = []
        async def emit(event, value, **kw): sent.append((event, value))
        display.emit = emit
        display.primed = True
        raw = '문장~범위\n다음\n\n마지막 😀'
        for i, char in enumerate(raw, 1):
            await display.answer_delta({'schema_version': 'rag-answer-delta-v1', 'seq': i, 'text': char})
        text = w._for_markdown(raw)
        before = ''.join(value for event,value in sent if event == 'token')
        assert before.endswith(text) and not any(event == 'end' for event,value in sent)
        await display.progress({'schema_version': 'rag-progress-v1', 'kind': 'heartbeat', 'label': 'later'})
        await display.finish(text+'\n\n**출처**\n\n- 합성 원문')
        rendered = ''.join(value for event,value in sent if event == 'token')
        assert rendered == '---\n\n**최종 답변**\n\n'+text+'\n\n**출처**\n\n- 합성 원문'
        assert sent[-1] == ('end', 'end')
    asyncio.run(run())


def test_workflow_changed_or_failed_result_is_explicit(monkeypatch):
    w = load('answer_failure_workflow', '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    async def run():
        d = w._ChatProgress({'socketIOClientId': 'fixture'}); sent = []
        async def emit(event,value,**kw): sent.append((event,value))
        d.emit = emit
        await d.answer_delta({'schema_version': 'rag-answer-delta-v1', 'seq': 1, 'text': '일부 본문'})
        await d.finish('지금 답변을 만들지 못했습니다.',failed=True)
        assert '답변 전달 미완료' in ''.join(x for e,x in sent if e == 'token')
        with pytest.raises(ValueError):
            await d.answer_delta({'schema_version': 'rag-answer-delta-v1', 'seq': 3, 'text': '누락'})
    asyncio.run(run())


def test_server_delivers_answer_before_backend_completion_and_without_loss(monkeypatch):
    app = load('answer_sse_app', '08_DEPLOYMENT/GENOS/stream_app.py')
    release = threading.Event()
    async def service(config, data):
        sink = current_sink()
        assert sink is not None
        for i in range(260): sink(str(i)+' ')
        await asyncio.to_thread(release.wait, 3)
        return {'status': 200, 'body': {'answer': {'text': 'complete'}}}
    monkeypatch.setattr(app, 'service', service)
    class Request:
        async def json(self): return {'API_TYPE': 'LEGAL_AGENT', 'request_id': 'stream-test'}
    async def consume():
        response = await app.stream_endpoint(Request()); seen = []
        async for raw in response.body_iterator:
            if raw.startswith(':'): continue
            data = json.loads(raw[5:])
            if data['event'] == 'answer_delta':
                seen.append(data['data'])
                assert data['data']['request_id'] == 'stream-test'
                if len(seen) == 260: release.set()
            elif data['event'] == 'result':
                assert len(seen) == 260
        assert [d['seq'] for d in seen] == list(range(1,261))
        assert not app._ACTIVE_REQUESTS
    try: asyncio.run(consume())
    finally: release.set()


def test_answer_channel_context_isolation():
    async def request(name):
        frames = []
        with capture(name, frames.append):
            await asyncio.to_thread(current_sink(), name)
            await asyncio.sleep(0)
        assert frames == [{'schema_version': 'rag-answer-delta-v1', 'request_id': name, 'seq': 1, 'text': name}]
    async def run(): await asyncio.gather(request('one'), request('two'))
    asyncio.run(run()); assert current_sink() is None


@pytest.mark.parametrize('review_enabled', [False, True])
def test_gateway_uses_stream_only_for_unreviewed_final_draft_and_preserves_journal(tmp_path, generation, monkeypatch, review_enabled):
    with session(tmp_path, generation, profile={**SETTINGS, 'final_review_enabled': review_enabled}) as s:
        drafted(s)
        draft = {'paragraphs': [deepcopy(s.work.heads('claim', current=True)[0]['payload'])], 'limitations': []}
        view = s.view('compose', required=s.packed['evidence_ids']); delivered(s, view)
        from semantic_runtime.legal_agent.numbered_references import NumberedReferences
        wire_draft = NumberedReferences(view).project(draft)
        before = s.work.budget()['model_reserved']
        calls = []; tokens = []
        def send(*, body, ticket, on_content=None):
            calls.append(body)
            if on_content:
                for char in json.dumps(wire_draft): on_content(char)
                assert ''.join(row['text'] for row in tokens) == draft['paragraphs'][0]['text']
            return wire(wire_draft)
        monkeypatch.setattr(s.gateway.transport, 'send_once', send)
        monkeypatch.setattr(s.gateway.transport, 'send_stream_once', send, raising=False)
        with capture('gateway-fixture', tokens.append):
            value = s.gateway.generate('compose', view, 'Draft')
        assert value == draft
        assert calls[0]['stream'] is not review_enabled
        assert bool(tokens) is not review_enabled
        assert s.work.budget()['model_reserved'] == before+1
        s.commit_draft(view, value)
        assert s.work.heads('claim', current=True)[0]['payload']['text'] == draft['paragraphs'][0]['text']


def test_gateway_never_retries_after_visible_answer(tmp_path, generation, monkeypatch):
    with session(tmp_path, generation, profile={**SETTINGS, 'final_review_enabled': False, 'max_transport_retries': 2}) as s:
        drafted(s)
        view = s.view('compose', required=s.packed['evidence_ids']); delivered(s, view)
        before = s.work.budget()['model_reserved']; calls = []; tokens = []
        def send(*, body, ticket, on_content):
            calls.append(body)
            on_content('{"paragraphs":[{"text":"일부 문장')
            raise TransportError('synthetic disconnect', unknown=True, retryable=True)
        monkeypatch.setattr(s.gateway.transport, 'send_stream_once', send, raising=False)
        with capture('no-retry', tokens.append), pytest.raises(TransportError):
            s.gateway.generate('compose', view, 'Draft')
        assert len(calls) == 1 and tokens and s.work.budget()['model_reserved'] == before+1


@pytest.mark.parametrize('mode', ['socketio', 'socketio-final', 'off'])
def test_workflow_forwards_answer_frame_before_result_and_keeps_final_dict(monkeypatch, mode):
    w = load('answer_bridge_'+mode, '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', mode)
    monkeypatch.setattr(w, '_post_code_serving', lambda body: {'status':200,'body':{'ad_handled':False}})
    monkeypatch.setattr(w, '_settings', lambda: ('http://fixture/json', 'synthetic', 2))
    emitted = []; visible = threading.Event()
    async def emit(self, event, value):
        if self.enabled:
            emitted.append((event, value))
            if event == 'token' and '실시간 본문' in value: visible.set()
    monkeypatch.setattr(w._ChatProgress, '_send', emit)
    class Response:
        status = 200
        headers = {'Content-Type': 'text/event-stream'}
        def __init__(self, rid): self.rid = rid
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def __iter__(self):
            yield ('data: '+json.dumps({'event': 'answer_delta', 'data': {
                'schema_version': 'rag-answer-delta-v1', 'request_id': self.rid,
                'seq': 1, 'text': '실시간 본문'}})+'\n\n').encode()
            if mode != 'off': assert visible.wait(2), 'Answer must display before final result'
            yield ('data: '+json.dumps({'event': 'result', 'data': {'status': 200,
                'body': {'answer': {'text': '실시간 본문입니다.'}}}})+'\n\n').encode()
    monkeypatch.setattr(w.urllib.request, 'urlopen', lambda req, **kw: Response(json.loads(req.data)['request_id']))
    result = asyncio.run(w.run({'question': 'synthetic', 'socketIOClientId': 'fixture'}))
    assert result['text'] == '실시간 본문입니다.' and result['answer_status'] == 'answered'
    if mode == 'off': assert not emitted
    else: assert ''.join(v for e,v in emitted if e == 'token') == result['text']


def test_workflow_slow_socket_does_not_drop_answer_fragments(monkeypatch):
    w = load('answer_slow_socket', '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    monkeypatch.setattr(w, '_post_code_serving', lambda body: {'status':200,'body':{'ad_handled':False}})
    monkeypatch.setattr(w, '_settings', lambda: ('http://fixture/json', 'synthetic', 2))
    emitted = []
    async def emit(self,event,value):
        await asyncio.sleep(0.001)
        if event == 'token': emitted.append(value)
    monkeypatch.setattr(w._ChatProgress, '_send', emit)
    expected = 'x'*260
    class Response:
        status = 200
        headers = {'Content-Type': 'text/event-stream'}
        def __init__(self,rid): self.rid = rid
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def __iter__(self):
            for i in range(260):
                yield ('data: '+json.dumps({'event':'answer_delta','data':{
                    'schema_version':'rag-answer-delta-v1','request_id':self.rid,
                    'seq':i+1,'text':'x'}})+'\n\n').encode()
            yield ('data: '+json.dumps({'event':'result','data':{'status':200,
                'body':{'answer':{'text':expected}}}})+'\n\n').encode()
    monkeypatch.setattr(w.urllib.request,'urlopen',lambda req,**kw:Response(json.loads(req.data)['request_id']))
    result = asyncio.run(w.run({'question':'synthetic','socketIOClientId':'fixture'}))
    assert result['answer_status'] == 'answered' and result['text'] == expected
    assert result['code_serving_transport']['answer_events'] == 260
    assert ''.join(emitted) == expected


def test_sse_check_exposes_server_answer_revision(monkeypatch):
    app = load('answer_probe_app', '08_DEPLOYMENT/GENOS/stream_app.py')
    w = load('answer_probe_workflow', '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    async def call(*args,**kw):
        args[2].transport['opened'] = True
        class Request:
            async def json(self): return {'API_TYPE':'SSE_CHECK'}
        response = await app.stream_endpoint(Request())
        frames = [raw async for raw in response.body_iterator]
        return json.loads(frames[-1][5:])['data']
    monkeypatch.setattr(w,'_stream_code_serving',call)
    result=asyncio.run(w.run({'question':'SSE_CHECK'}))
    assert result['sse_check']['stream_answer_revision'] == 'answer-stream-20260929-r1'
    assert result['sse_check']['workflow_revision'] == w.WORKFLOW_REVISION
