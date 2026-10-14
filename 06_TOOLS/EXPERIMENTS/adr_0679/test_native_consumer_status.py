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
