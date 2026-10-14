"""Migrated native /chat: local dispatch, envelope, identity and liveness."""
import asyncio
import json
from pathlib import Path
import sys
import threading
import time
import pytest
from fastapi.testclient import TestClient
from semantic_runtime import chat_adapter as adapter
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import main
from test_unified_legal_agent import unified
from test_memory_runtime_v2 import command
from test_structure_first_search import structured_generation

@pytest.fixture(autouse=True)
def ordinary_env(monkeypatch,tmp_path):
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path/'runtime'))
    monkeypatch.setenv('GENOS_MEMORY_ENABLED','0')
    monkeypatch.delenv('TEAM_ID',raising=False)
    monkeypatch.delenv('GENOS_CHAT_TRUST_PLATFORM_IDENTITY',raising=False)
    monkeypatch.delenv('GENOS_CHAT_GATEWAY_TOKEN',raising=False)


def test_main_verify_and_liveness_are_model_free(monkeypatch):
    async def forbidden(body):raise AssertionError('verify must not call RAG')
    monkeypatch.setattr(adapter,'call_service',forbidden)
    c=TestClient(main.app)
    assert c.post('/chat',json={'question':'__verify__'}).json()=={'code':0,'data':{'text':'verified'}}
    assert c.get('/healthcheck').json()['readiness_scope']=='http'


def test_chat_preserves_payload_and_uses_local_service_once(monkeypatch):
    calls=[]
    async def local(body):
        calls.append(body)
        return {'status':200,'body':{'run_id':'r','answer':{'text':'확인한 답변 [1]'},'assembly':{}}}
    monkeypatch.setattr(adapter,'call_service',local)
    import urllib.request
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**k:pytest.fail('HTTP self-call'))
    data={'question':'모의 승인','chatId':'c-1','socketIOClientId':'socket','user_id':'untrusted',
          'apiKey':'do-not-echo','overrideConfig':{'token':'secret','ordinary':'preserved'}}
    result=TestClient(main.app).post('/chat',json=data).json()
    assert result['code']==0 and result['data']['answer_status']=='answered'
    assert result['data']['text']=='확인한 답변'
    assert result['data']['chatId']=='c-1' and result['data']['socketIOClientId']=='socket'
    assert result['data']['overrideConfig']=={'ordinary':'preserved'}
    assert 'apiKey' not in result['data'] and 'session_id' not in calls[0] and 'user_id' not in calls[0]
    assert len(calls)==1 and calls[0]['API_TYPE']=='LEGAL_AGENT'


def test_session_memory_needs_stable_platform_ids(monkeypatch):
    monkeypatch.setenv('GENOS_MEMORY_ENABLED','1');monkeypatch.setenv('TEAM_ID','risk_team')
    async def forbidden(body):raise AssertionError('missing session reached RAG')
    monkeypatch.setattr(adapter,'call_service',forbidden)
    out=TestClient(main.app).post('/chat',json={'question':'모의 정정','userId':'u'}).json()
    assert out['data']['answer_status']=='failed'


def test_platform_session_works_without_signing_or_extra_gateway_secret(monkeypatch):
    from semantic_runtime.legal_agent.memory_identity import validate_session
    monkeypatch.setenv('GENOS_MEMORY_ENABLED','1');monkeypatch.setenv('TEAM_ID','risk_team')
    monkeypatch.delenv('GENOS_MEMORY_SIGNING_KEY',raising=False)
    async def local(body):
        principal=validate_session({k:v for k,v in body.items() if k not in {'API_TYPE','channel'}})
        assert principal['team_id']=='risk_team' and 'memory_authorization' not in body
        return {'status':200,'body':{'answer':{'text':'확정 경험'},'assembly':{}}}
    monkeypatch.setattr(adapter,'call_service',local)
    out=TestClient(main.app).post('/chat',json={'question':'모의 확인','userId':'u','chatId':'s'}).json()
    assert out['data']['answer_status']=='answered' and 'memory_authorization' not in out['data']


def test_old_signature_is_ignored_and_never_returned(monkeypatch):
    data={'question':'모의','memory':True,'session_id':'s','request_id':'r','user_id':'u','team_id':'risk_team',
          'memory_authorization':{'issued_at':1,'signature':'s'}}
    request=adapter.request_body(data,'모의')
    assert request['memory'] is True and 'memory_authorization' not in request


def test_main_does_not_block_liveness_during_chat(monkeypatch):
    started=threading.Event();release=threading.Event()
    async def blocking(body):
        started.set();assert release.wait(5)
        return {'status':200,'body':{'answer':{'text':'완료'},'assembly':{}}}
    monkeypatch.setattr(adapter,'call_service',blocking)
    with TestClient(main.app) as c:
        outputs=[];thread=threading.Thread(target=lambda:outputs.append(c.post('/chat',json={'question':'모의'})))
        thread.start();assert started.wait(2)
        try:
            assert c.get('/healthcheck').status_code==200
        finally:release.set();thread.join(3)
        assert outputs[0].json()['data']['answer_status']=='answered'


@pytest.mark.parametrize('streaming',[False,True])
def test_migrated_chat_reaches_real_v6_and_preserves_ad_read_gate(unified,monkeypatch,streaming):
    client,send,transport,principal,runtime=unified
    import service
    monkeypatch.setattr(service,'_bootstrap_application',lambda:client.app)
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(runtime))
    import hashlib
    principal['user_id']='u-'+hashlib.sha256(b'u').hexdigest()
    n=0
    def request(c=None):
        nonlocal n
        n+=1
        if c is not None:transport.command=c
        data={'question':'모의승인규정 제1조의 승인 대상은?','session_id':'s',
              'request_id':'local'+str(n),'memory':True,'user_id':'u','team_id':'risk_team'}
        response=TestClient(main.app).post('/chat',json={**data,'stream':streaming})
        if streaming:
            result=next(json.loads(line[6:])['data'] for line in response.text.splitlines()
                if line.startswith('data: ') and json.loads(line[6:])['event']=='result')
        else:result=response.json()['data']
        assert result['answer_status']=='answered',result
        return result
    first=request();gid=first['question_id']
    corrected=request(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'A'}]))
    assert corrected['executed']==['ASSESS','COMPOSE']
    stored=request(command('EXPERIENCE_CONFIRM',target=gid))
    assert stored['experience_id'] and stored['status']=='STORED'
    monkeypatch.setenv('TEAM_ID','risk_team')
    query={'question':'','session_id':'s','request_id':'wiki','query_kind':'user_wiki'}
    # These management APIs now require AD mode; migrating /chat must not bypass
    # that current gate merely because its ordinary RAG turn has session selectors.
    for kind in ('user_wiki','legal_wiki'):
        response=client.post('/v1/rag/memory/query',json={**query,'query_kind':kind})
        assert response.status_code==403 and 'AD_REQUIRED' in response.text,response.text
