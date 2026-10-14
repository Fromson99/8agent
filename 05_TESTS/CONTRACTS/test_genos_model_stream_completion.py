"""Synthetic terminal framing and actual urllib/httpx adapter parity."""
import asyncio
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import httpx
import pytest

from semantic_runtime.legal_agent.answer_stream import DraftText
from semantic_runtime.legal_agent.errors import TransportError
from semantic_runtime.legal_agent.model_stream import ModelEventStream
from semantic_runtime.genos import endpoint
from test_genos_answer_stream import frame, transport
from test_legal_agent_double_harness import generation

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'08_DEPLOYMENT/GENOS/handoffs/model_stream_fix_20261013_r1'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=['installed'] if os.getenv('GENOS_TEST_INSTALLED_TRANSPORT') else ['urllib', 'httpx'])
def make_transport(request, monkeypatch, tmp_path):
    if request.param in ('urllib', 'installed'):
        return lambda frames: transport(monkeypatch, frames)
    field = ROOT/'08_DEPLOYMENT/GENOS/patches/answer_stream_20260929_r1/payload/02_BACKEND/semantic_runtime/legal_agent/transport.py'
    patched = tmp_path/'transport.py'
    patched.write_bytes(load('rewrite_transport_test', OUT/'rewrite_transport.py').rewrite(field.read_bytes()))
    module = load('semantic_runtime.legal_agent.field_test_transport', patched)
    def make(frames):
        requests = []
        def serve(req):
            requests.append(json.loads(req.content))
            return httpx.Response(200, headers={'content-type': 'text/event-stream; charset=utf-8'},
                                  content=''.join(frames).encode())
        original = httpx.AsyncClient
        monkeypatch.setattr(module.httpx, 'AsyncClient',
            lambda **kw: original(**kw, transport=httpx.MockTransport(serve)))
        target = endpoint('http://fixture', token='synthetic', label='synthetic')
        binding = {'provider': 'genos', 'trust_zone': 'internal', 'adapter_version': 'genos-single-send-v1',
            'model': 'fixture-model', 'endpoint_identity': hashlib.sha256(target.root.encode()).hexdigest()}
        return module.GenosTransport(target, binding), requests
    return make


@pytest.mark.parametrize('ending', ['data: [DONE]\n\n', 'data: [DONE]\n', 'data:[DONE]'])
def test_missing_finish_with_done_streams_and_keeps_usage(make_transport, ending):
    body = '{"paragraphs":[{"text":"생성 중인 답변 😀"}],"limitations":[]}'
    chunks = [body[:26], body[26:]]
    t, requests = make_transport([': heartbeat\r\n\r\n', *[frame({'content': p}) for p in chunks],
        'data: '+json.dumps({'model':'fixture-model','choices':[], 'usage':{'completion_tokens':18}})+'\n\n', ending])
    tokens = []
    result = t.send_stream_once(body={'stream':True},ticket={'remaining_seconds':2},on_content=DraftText(tokens.append).feed)
    assert ''.join(tokens) == '생성 중인 답변 😀'
    assert len(tokens) > 1 and len(requests) == 1
    assert result['body_json']['choices'][0]['finish_reason'] is None
    assert result['body_json']['choices'][0]['message']['content'] == body
    assert result['body_json']['usage'] == {'completion_tokens':18}
    assert result['stream_complete'] is True and result['stream_diagnostics']['done_marker'] is True
    assert result['stream_diagnostics']['trailing_frame_parsed'] == (ending != 'data: [DONE]\n\n')


@pytest.mark.parametrize('ending', ['', 'data: {"choices":[],"usage":{"completion_tokens":1}}\n\n'])
def test_valid_json_or_usage_without_done_still_fails(make_transport, ending):
    t, requests = make_transport([frame({'content':'{"paragraphs":[{"text":"一部"}]}'}), ending])
    with pytest.raises(TransportError, match='before completion') as caught:
        t.send_stream_once(body={'stream':True},ticket={'remaining_seconds':2},on_content=lambda _:None)
    response = caught.value.response
    assert len(requests)==1 and response['status_code']==200
    assert response['stream_complete'] is False
    assert response['stream_diagnostics']['done_marker'] is False
    assert response['stream_diagnostics']['eof_received'] is True


@pytest.mark.parametrize('reason',['length','content_filter'])
def test_explicit_incomplete_reason_fails_even_with_done(make_transport, reason):
    t,_ = make_transport([frame({'content':'{}'},finish=reason), 'data: [DONE]\n\n'])
    with pytest.raises(TransportError,match='did not complete normally') as caught:
        t.send_stream_once(body={'stream':True},ticket={'remaining_seconds':2},on_content=lambda _:None)
    assert caught.value.response['stream_diagnostics']['finish_reason']==reason


@pytest.mark.parametrize('asynchronous',[False,True])
@pytest.mark.parametrize('wire',[
    'data: {"choices":[],\ndata: "usage":{"completion_tokens":1}}\n\ndata: [DONE]\n\n',
    'event: message\r\ndata: {"choices":[]}\r\n\r\ndata: [DONE]',
])
def test_multiline_and_crlf_sync_async_parity(asynchronous, wire):
    parser = ModelEventStream()
    if asynchronous:
        async def lines():
            for line in wire.splitlines():yield line
        async def read():return [event async for event in parser.aiter_events(lines())]
        events = asyncio.run(read())
    else:
        events = list(parser.iter_events(wire.splitlines()))
    parser.require_complete()
    assert len(events)==1 and parser.done


@pytest.mark.parametrize('wire',['data: {"choices":', 'data: {"error":"failure"}\n\n',
    'event: error\ndata: {}\n\n', 'data: {"choices":null}\n\n'])
def test_invalid_or_error_frame_is_not_completed(wire):
    parser=ModelEventStream()
    with pytest.raises((TransportError,ValueError)):
        list(parser.iter_events(wire.splitlines()))
    assert not parser.done
    if wire == 'data: {"choices":':
        assert parser.diagnostics()['trailing_frame_seen'] is True
        assert parser.diagnostics()['trailing_frame_parsed'] is False


@pytest.mark.parametrize('asynchronous',[False,True])
def test_network_failure_does_not_flush_pending_done(asynchronous):
    parser=ModelEventStream()
    if asynchronous:
        async def lines():
            yield 'data: [DONE]'
            raise TimeoutError('synthetic')
        async def read():return [event async for event in parser.aiter_events(lines())]
        call=lambda:asyncio.run(read())
    else:
        def lines():
            yield 'data: [DONE]'
            raise TimeoutError('synthetic')
        call=lambda:list(parser.iter_events(lines()))
    with pytest.raises(TimeoutError):call()
    assert not parser.done and not parser.eof and parser.diagnostics()['pending_frame_lines']==1


def test_missing_finish_passes_actual_gateway_validation_and_commit(make_transport, tmp_path, generation, monkeypatch):
    from semantic_runtime.legal_agent.answer_stream import capture
    from semantic_runtime.legal_agent.numbered_references import NumberedReferences
    from test_legal_agent_v5 import SETTINGS, drafted, session
    from test_tool_exploration_v3 import delivered
    with session(tmp_path,generation,profile={**SETTINGS,'final_review_enabled':False}) as s:
        drafted(s)
        draft={'paragraphs':[deepcopy(s.work.heads('claim',current=True)[0]['payload'])],'limitations':[]}
        view=s.view('compose',required=s.packed['evidence_ids']);delivered(s,view)
        raw=json.dumps(NumberedReferences(view).project(draft))
        model=s.gateway.transport.binding['model']
        t,requests=make_transport([frame({'content':raw[:20]},model=model),frame({'content':raw[20:]},model=model),'data: [DONE]'])
        t.binding={**t.binding,'model':model}
        monkeypatch.setattr(s.gateway.transport,'send_stream_once',t.send_stream_once,raising=False)
        emitted=[]
        with capture('actual-gateway',emitted.append):
            value=s.gateway.generate('compose',view,'Draft')
        assert value==draft and len(requests)==1 and emitted
        assert ''.join(x['text'] for x in emitted)==draft['paragraphs'][0]['text']
        s.commit_draft(view,value)
        assert s.work.heads('claim',current=True)[0]['payload']['text']==draft['paragraphs'][0]['text']
