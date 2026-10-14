"""Declared consumer contract: native chat preserves completion outcomes."""
import pytest
import asyncio
from semantic_runtime import chat_adapter as adapter

@pytest.mark.parametrize('status,raw,expected',[
    (422,{'code':'SOURCE_INVESTIGATION_INCOMPLETE','detail':'모의 미완료'},'incomplete'),
    (503,{'code':'MODEL_UPSTREAM_UNAVAILABLE','detail':'모의 상류 실패'},'unavailable'),
    (200,{'answer':{'text':'모의 확인 범위'},'assembly':{'term_agent':{'completion_contract':'investigation-completion-v1','answer_coverage':'PARTIAL'}}},'partial'),
])
def test_native_chat_preserves_typed_completion(monkeypatch,tmp_path,status,raw,expected):
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path));monkeypatch.setenv('GENOS_MEMORY_ENABLED','0')
    async def local(body):return {'status':status,'body':raw}
    monkeypatch.setattr(adapter,'call_service',local)
    result=asyncio.run(adapter.chat({'question':'모의 질문','request_id':expected}))
    assert result['data']['answer_status']==expected


@pytest.mark.parametrize('status,raw,expected',[
    (422,{'code':'SOURCE_INVESTIGATION_INCOMPLETE','detail':'모의 미완료'},'incomplete'),
    (503,{'code':'MODEL_UPSTREAM_UNAVAILABLE','detail':'모의 상류 실패'},'unavailable'),
    (200,{'answer':{'text':'모의 확인 범위'},'assembly':{'term_agent':{'completion_contract':'investigation-completion-v1','answer_coverage':'PARTIAL'}}},'partial'),
    (200,{'answer':{'text':'모의 완료'},'assembly':{'term_agent':{'completion_contract':'investigation-completion-v1','answer_coverage':'COVERED'}}},'answered'),
])
@pytest.mark.parametrize('stream',[False,True])
def test_exact_candidate_http_consumes_completion(monkeypatch,tmp_path,status,raw,expected,stream):
    import sys,json
    from pathlib import Path
    from fastapi.testclient import TestClient
    root=Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(root))
    import main,stream_app
    assert Path(main.__file__).resolve()==root/'main.py'
    assert Path(stream_app.__file__).resolve()==root/'08_DEPLOYMENT/GENOS/stream_app.py'
    assert Path(adapter.__file__).resolve()==root/'02_BACKEND/semantic_runtime/chat_adapter.py'
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path));monkeypatch.setenv('GENOS_MEMORY_ENABLED','0')
    monkeypatch.setenv('GENOS_CHAT_TRANSPORT','auto')
    calls=[]
    async def local(body):calls.append(body);return {'status':status,'body':raw}
    monkeypatch.setattr(adapter,'call_service',local)
    response=TestClient(main.app).post('/chat',json={'question':'모의','stream':stream})
    if stream:
        rows=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        result=next(row['data'] for row in rows if row['event']=='result')
    else:result=response.json()['data']
    assert result['answer_status']==expected
    assert len(calls)==1
