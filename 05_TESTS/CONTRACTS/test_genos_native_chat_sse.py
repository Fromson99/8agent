"""Native /chat streams from the same RAG worker without workflow sockets."""
import asyncio
import json
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from semantic_runtime import chat_adapter as adapter
from semantic_runtime.legal_agent.answer_stream import current_sink

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import main
import stream_app


@pytest.fixture(autouse=True)
def native_env(monkeypatch,tmp_path):
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path/'runtime'))
    monkeypatch.setenv('GENOS_MEMORY_ENABLED','0')
    monkeypatch.setenv('GENOS_CHAT_TRANSPORT','auto')
    monkeypatch.delenv('GENOS_CHAT_TRUST_PLATFORM_IDENTITY',raising=False)
    monkeypatch.delenv('TEAM_ID',raising=False)
    monkeypatch.setitem(sys.modules,'main_socketio',None)
    import urllib.request
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**kw:pytest.fail('HTTP self-call'))


def frames(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


def test_native_negotiation_and_final_json_envelope(monkeypatch):
    calls=[]
    async def local(body):
        calls.append(body)
        sink=current_sink()
        if sink:sink('답변 [1]')
        return {'status':200,'body':{'answer':{'text':'답변 [1]'},'assembly':{}}}
    monkeypatch.setattr(adapter,'call_service',local)
    client=TestClient(main.app)
    body={'question':'모의','chatId':'conversation','apiKey':'secret'}
    plain=client.post('/chat',json=body).json()
    response=client.post('/chat',json=body,headers={'Accept':'text/event-stream'})
    events=frames(response)
    assert response.headers['content-type'].startswith('text/event-stream')
    assert response.headers['x-genos-chat-contract']=='genos-chat-sse-v1'
    assert ''.join(e['data'] for e in events if e['event']=='token')=='답변'
    result=next(e['data'] for e in events if e['event']=='result')
    assert result['text']==plain['data']['text'] and 'code' not in result
    assert result['chatId']=='conversation' and 'apiKey' not in result
    assert result['chat_stream_transport']['answer_events']==1
    assert result['execution_transport']=='in-process'
    assert events[-1]['event']=='result'
    assert len(calls)==2 and all(b['API_TYPE']=='LEGAL_AGENT' for b in calls)


def test_worker_emits_answer_and_heartbeat_before_completion(monkeypatch):
    waiting=threading.Event();release=threading.Event();completed=threading.Event()
    async def local(body):
        waiting.set()
        current_sink()('먼저 보이는 답변')
        assert release.wait(3)
        completed.set()
        return {'status':200,'body':{'answer':{'text':'먼저 보이는 답변입니다.'},'assembly':{}}}
    monkeypatch.setattr(adapter,'call_service',local)
    monkeypatch.setattr(stream_app,'HEARTBEAT_SECONDS',0.01)
    async def execute(data,on_progress,on_answer):
        return await adapter.chat(data,on_progress=on_progress,on_answer=on_answer)
    async def check():
        response=await stream_app.stream_response({'question':'모의','request_id':'early'},execute,
                                                 display=adapter.stream_display())
        iterator=response.body_iterator
        assert await anext(iterator)==': connected\n\n'
        first=json.loads((await anext(iterator))[6:])
        assert first=={'event':'token','data':'먼저 보이는 답변'}
        assert waiting.is_set() and not completed.is_set()
        assert await anext(iterator)==': keep-alive\n\n'
        release.set()
        rest=[json.loads(raw[6:]) async for raw in iterator if raw.startswith('data: ')]
        result=next(e['data'] for e in rest if e['event']=='result')
        assert result['chat_stream_transport']['heartbeat_events']>=1
        assert ''.join(e['data'] for e in [first,*rest] if e['event']=='token')==result['text']
        assert completed.is_set() and 'early' not in stream_app._ACTIVE_REQUESTS
    try:asyncio.run(check())
    finally:release.set()


@pytest.mark.parametrize('probe_request',[
    {'headers':{'Accept':'text/event-stream'}}, {'json':{'API_TYPE':'SSE_CHECK','stream':True}},
])
def test_probe_and_platform_handshake_do_not_call_backend(monkeypatch,probe_request):
    async def forbidden(body):pytest.fail('probe called backend/model')
    monkeypatch.setattr(adapter,'call_service',forbidden)
    client=TestClient(main.app)
    body=probe_request.get('json',{'API_TYPE':'SSE_CHECK'})
    response=client.post('/chat',json=body,headers=probe_request.get('headers',{}))
    result=next(e['data'] for e in frames(response) if e['event']=='result')
    assert result['sse_check']['sse_ready'] and result['sse_check']['route']=='/chat'
    assert result['chat_stream_transport']['answer_events']==0
    monkeypatch.setenv('GENOS_CHAT_TRANSPORT','sse')
    assert client.post('/chat',json={'question':'__verify__','stream':True},
        headers={'Accept':'text/event-stream'}).json()=={'code':0,'data':{'text':'verified'}}


@pytest.mark.parametrize('mode,body,accept,streaming',[
    ('auto',{},'*/*',False),('auto',{},'text/event-stream;q=0',False),
    ('auto',{'stream':True},'*/*',True),('sse',{},'*/*',True),
    ('sse',{'stream':False},'text/event-stream',False),
    ('json',{},'*/*',False),
])
def test_transport_selection_can_restore_json(monkeypatch,mode,body,accept,streaming):
    monkeypatch.setenv('GENOS_CHAT_TRANSPORT',mode)
    async def local(data):return {'status':200,'body':{'answer':{'text':'완료'},'assembly':{}}}
    monkeypatch.setattr(adapter,'call_service',local)
    response=TestClient(main.app).post('/chat',json={'question':'모의',**body},headers={'Accept':accept})
    assert response.headers['content-type'].startswith('text/event-stream') is streaming


def test_stream_denies_untrusted_personal_memory(monkeypatch):
    monkeypatch.setenv('GENOS_MEMORY_ENABLED','1')
    async def forbidden(body):pytest.fail('untrusted memory reached RAG')
    monkeypatch.setattr(adapter,'call_service',forbidden)
    events=frames(TestClient(main.app).post('/chat',json={
        'question':'모의','userId':'u','chatId':'s','stream':True}))
    result=next(e['data'] for e in events if e['event']=='result')
    assert result['answer_status']=='failed' and events[-1]['event']=='result'


def test_disconnect_before_computation_releases_native_request(monkeypatch):
    calls=[]
    async def execute(*args):calls.append(args);pytest.fail('detached request executed')
    async def check():
        response=await stream_app.stream_response({'request_id':'detached-native'},execute,
                                                 display=adapter.stream_display())
        assert await anext(response.body_iterator)==': connected\n\n'
        await response.body_iterator.aclose()
        assert not calls and 'detached-native' not in stream_app._ACTIVE_REQUESTS
    asyncio.run(check())


def test_slow_consumer_preserves_all_answer_fragments(monkeypatch):
    expected='답'*300
    async def local(body):
        sink=current_sink()
        for char in expected:sink(char)
        return {'status':200,'body':{'answer':{'text':expected},'assembly':{}}}
    monkeypatch.setattr(adapter,'call_service',local)
    async def execute(data,on_progress,on_answer):
        return await adapter.chat(data,on_progress=on_progress,on_answer=on_answer)
    async def check():
        response=await stream_app.stream_response({'question':'모의','request_id':'slow-native'},execute,
                                                 display=adapter.stream_display())
        found=[]
        async for raw in response.body_iterator:
            if raw.startswith('data: '):found.append(json.loads(raw[6:]))
            await asyncio.sleep(0.001)
        assert ''.join(e['data'] for e in found if e['event']=='token')==expected
        result=next(e['data'] for e in found if e['event']=='result')
        assert result['chat_stream_transport']['answer_events']==300
    asyncio.run(check())


def test_live_http_emits_tokens_and_answers_health_before_rag_finishes(monkeypatch):
    import httpx
    import socket
    import time
    import uvicorn
    release=threading.Event();completed=threading.Event()
    async def local(body):
        current_sink()('HTTP 조기 답변')
        assert release.wait(5)
        completed.set()
        return {'status':200,'body':{'answer':{'text':'HTTP 조기 답변 완료'},'assembly':{}}}
    monkeypatch.setattr(adapter,'call_service',local)
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(8)
    url='http://127.0.0.1:'+str(sock.getsockname()[1])
    server=uvicorn.Server(uvicorn.Config(main.app,lifespan='off',log_level='critical'))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    deadline=time.monotonic()+3
    try:
        while not server.started and time.monotonic()<deadline:time.sleep(0.01)
        assert server.started
        with httpx.Client(base_url=url,trust_env=False,timeout=3) as client:
            with client.stream('POST','/chat?stream=1',json={'question':'모의 HTTP'}) as response:
                found=[]
                for line in response.iter_lines():
                    if not line.startswith('data: '):continue
                    frame=json.loads(line[6:]);found.append(frame)
                    if frame['event']=='token' and 'HTTP 조기 답변' in frame['data']:
                        assert not completed.is_set()
                        assert client.get('/healthcheck').status_code==200
                        release.set()
                assert found[-1]['event']=='result' and found[-1]['data']['answer_status']=='answered'
                assert ''.join(e['data'] for e in found if e['event']=='token')==found[-1]['data']['text']
    finally:
        release.set();server.should_exit=True;thread.join(3);sock.close()
