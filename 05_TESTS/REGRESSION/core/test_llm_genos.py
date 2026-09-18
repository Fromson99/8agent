"""GenOS 백엔드(lawrag/core/llm.py) — OpenAI 호환 서빙 앞에서 structured() 계약이 서는지.

소켓 없는 모의 HTTP 전송을 사용한다 (실측 문서 v1.9.0 "LLM 서빙 API 사용"의 모양:
/v1/models · /v1/chat/completions · SSE `data:` 청크 · [DONE]). 지키는 것:
  (1) 백엔드 선택 — GENOS_LLM_URL 만 있으면 genos, LLM_BACKEND 가 이긴다.
  (2) json_schema 를 받는 엔진 — 그대로 JSON 이 파싱된다.
  (3) json_schema 를 400 으로 거부하는 엔진 — prompt 모드로 내려가 스키마가
      시스템 프롬프트에 실리고, <think>·코드 울타리를 벗겨 JSON 을 얻는다.
      한 번 내려가면 세션 내내 그 길이다.
  (4) finish_reason=length → max_tokens 절단으로 이름 붙어 None.
  (5) 모델 이름은 /v1/models 에서 얻는다 (환경이 말하지 않으면).
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))

pytest.importorskip("requests", reason="requests 필요")

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}},
          "required": ["answer"], "additionalProperties": False}

_LLM_ENV_KEYS = (
    "LLM_BACKEND", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL", "LOCAL_LLM_URL", "LOCAL_LLM_KEY",
    "LOCAL_LLM_MODEL", "GENOS_BASE_URL", "GENOS_LLM_URL",
    "GENOS_LLM_KEY", "GENOS_LLM_MODEL", "GENOS_LLM_PROFILE",
    "GENOS_LLM_SERVING_ID", "GENOS_QWEN_SERVING_ID", "GENOS_QWEN_KEY",
    "GENOS_QWEN_MODEL", "OPEN_ROUTER", "OPENROUTER_API_KEY",
    "OPENROUTER_URL", "OPENROUTER_MODEL",
)


@pytest.fixture(autouse=True)
def _isolate_llm_environment(monkeypatch):
    """다른 테스트나 실행 호스트의 provider 선택값을 상속하지 않는다."""
    for key in _LLM_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    import requests
    def request(session, method, url, **kwargs):
        for root, fake in _Fake.servers.items():
            if url.startswith(root+'/'):
                return fake.request(method, url[len(root):], session.headers, kwargs)
        raise AssertionError('Unexpected network request: '+url)
    monkeypatch.setattr(requests.sessions.Session, 'request', request)


def _fresh():
    """lawrag.core.llm 을 진짜로 다시 적재한다 — sys.modules 만 지우면
    `from core import llm` 이 패키지 속성의 옛 모듈을 돌려준다."""
    import lawrag.core as core
    sys.modules.pop("lawrag.core.llm", None)
    if hasattr(core, "llm"):
        delattr(core, "llm")
    return importlib.import_module("lawrag.core.llm")


class _Fake:
    """Synthetic HTTP/SSE peer; exercises requests without opening sockets."""
    servers = {}
    def __init__(self, mode):
        self.mode=mode;self.requests=[]
        self.url=f'http://fake-{id(self)}.invalid'
        self.servers[self.url]=self
    def request(self,method,path,headers,kwargs):
        import requests
        if method.upper()=='GET':
            assert path.endswith('/v1/models')
            return self.reply(200, {'data':[{'id':'fake-llm-7b'}]})
        assert method.upper()=='POST' and path.endswith('/v1/chat/completions')
        req={**kwargs['json'],'_auth':headers.get('Authorization','')}
        self.requests.append(req)
        if self.mode=='reject' and 'response_format' in req:
            return self.reply(400,{'error':'response_format not supported'})
        if self.mode=='length':pieces,finish=['{"answer": "잘','린'],'length'
        elif self.mode=='reject':
            pieces=['<think>생각 중…</think>\n```json\n','{"answer": "울타리 안"}','\n```'];finish='stop'
        else:pieces,finish=['{"answer": ','"스키마 그대로"}'],'stop'
        chunks=[{'choices':[{'index':0,'delta':{'content':piece},
                            'finish_reason':finish if i==len(pieces)-1 else None}]}
                for i,piece in enumerate(pieces)]
        chunks.append({'choices':[],'usage':{'prompt_tokens':11,'completion_tokens':5}})
        return self.reply(200,{},chunks)
    @staticmethod
    def reply(status,body,chunks=None):
        import requests
        class Reply:
            status_code=status;headers={};text=json.dumps(body)
            def json(self):return body
            def raise_for_status(self):
                if status>=400:raise requests.HTTPError(self.text)
            def iter_lines(self):
                for chunk in chunks or []:yield ('data: '+json.dumps(chunk,ensure_ascii=False)).encode()
                yield b'data: [DONE]'
        return Reply()
    def close(self):
        self.servers.pop(self.url,None)


@pytest.fixture()
def genos_env(monkeypatch):
    def _set(url):
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        monkeypatch.delenv("LOCAL_LLM_URL", raising=False)
        monkeypatch.delenv("GENOS_LLM_MODEL", raising=False)
        monkeypatch.delenv("GENOS_LLM_JSON_MODE", raising=False)
        monkeypatch.setenv("GENOS_LLM_URL", url)
        monkeypatch.setenv("GENOS_LLM_KEY", "test-key")
        module = _fresh()
        monkeypatch.setattr(module, "load_env", lambda: None)
        return module
    return _set


def test_backend_selection(monkeypatch):
    llm_mod = _fresh()
    monkeypatch.setattr(llm_mod, "load_env", lambda: None)   # .env 의 진짜 키 차단
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.delenv("LOCAL_LLM_URL", raising=False)
    monkeypatch.delenv("GENOS_LLM_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_mod.backend() == "anthropic" and not llm_mod.available()
    monkeypatch.setenv("GENOS_LLM_URL", "http://x")
    assert llm_mod.backend() == "genos" and llm_mod.available()
    monkeypatch.setenv("LLM_BACKEND", "anthropic")      # 명시가 이긴다
    assert llm_mod.backend() == "anthropic" and not llm_mod.available()


def test_profile_builds_endpoint_and_selects_its_key(monkeypatch):
    llm_mod = _fresh()
    monkeypatch.setattr(llm_mod, "load_env", lambda: None)
    monkeypatch.delenv("GENOS_LLM_URL", raising=False)
    monkeypatch.setenv("GENOS_BASE_URL", "https://genos.example/")
    monkeypatch.setenv("GENOS_LLM_PROFILE", "qwen")
    monkeypatch.setenv("GENOS_QWEN_SERVING_ID", "226")
    monkeypatch.setenv("GENOS_QWEN_KEY", "qwen-secret")
    monkeypatch.setenv("GENOS_QWEN_MODEL", "qwen-served-name")

    assert llm_mod._genos_llm_url() == "https://genos.example/api/gateway/rep/serving/226"
    assert llm_mod._genos_llm_key() == "qwen-secret"
    assert llm_mod._genos_llm_model() == "qwen-served-name"
    assert llm_mod.backend() == "genos" and llm_mod.available()


def test_openrouter_uses_saved_key_and_qwen_default(monkeypatch):
    fake = _Fake("schema")
    try:
        llm_mod = _fresh()
        monkeypatch.setattr(llm_mod, "load_env", lambda: None)
        monkeypatch.setenv("LLM_BACKEND", "openrouter")
        monkeypatch.setenv("OPEN_ROUTER", "openrouter-test-key")
        monkeypatch.setenv("OPENROUTER_URL", fake.url)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

        assert llm_mod.backend() == "openrouter" and llm_mod.available()
        llm = llm_mod.LLM()
        assert llm.backend == "openrouter"
        assert llm.model == "qwen/qwen3.8-27b"
        assert llm.structured("t.openrouter", "시스템", "질문", SCHEMA,
                              max_tokens=64) == {"answer": "스키마 그대로"}
        req = fake.requests[-1]
        assert req["_auth"] == "Bearer openrouter-test-key"
        assert req["model"] == "qwen/qwen3.8-27b"
        assert req["response_format"]["type"] == "json_schema"
    finally:
        fake.close()


def test_local_openai_compatible_backend(monkeypatch):
    fake = _Fake("schema")
    try:
        llm_mod = _fresh()
        monkeypatch.setattr(llm_mod, "load_env", lambda: None)
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        monkeypatch.delenv("GENOS_LLM_URL", raising=False)
        monkeypatch.setenv("LOCAL_LLM_URL", fake.url)
        monkeypatch.setenv("LOCAL_LLM_MODEL", "onsite-test-model")
        monkeypatch.setenv("LOCAL_LLM_KEY", "local-key")

        assert llm_mod.backend() == "local" and llm_mod.available()
        llm = llm_mod.LLM()
        assert llm.structured("t.local", "시스템", "질문", SCHEMA,
                              max_tokens=64) == {"answer": "스키마 그대로"}
        assert fake.requests[-1]["model"] == "onsite-test-model"
        assert fake.requests[-1]["_auth"] == "Bearer local-key"
    finally:
        fake.close()


def test_json_schema_engine(genos_env):
    fake = _Fake("schema")
    try:
        llm_mod = genos_env(fake.url)
        llm = llm_mod.LLM()
        assert llm.backend == "genos" and llm.model == "fake-llm-7b"   # /v1/models
        out = llm.structured("t.a", "시스템", "질문", SCHEMA, max_tokens=64)
        assert out == {"answer": "스키마 그대로"}
        req = fake.requests[-1]
        assert req["_auth"] == "Bearer test-key"
        assert req["response_format"]["type"] == "json_schema"
        assert req["response_format"]["json_schema"]["schema"] == SCHEMA
        assert req["messages"][0] == {"role": "system", "content": "시스템"}
        ex = llm.log[-1]
        assert not ex.error and ex.usage == {"input_tokens": 11, "output_tokens": 5}
        assert ex.stop_reason == "end_turn" and ex.model == "fake-llm-7b"
    finally:
        fake.close()


def test_reject_falls_back_to_prompt_mode(genos_env):
    fake = _Fake("reject")
    try:
        llm = genos_env(fake.url).LLM()
        out = llm.structured("t.b", "시스템", "질문", SCHEMA, max_tokens=64)
        assert out == {"answer": "울타리 안"}          # <think>·울타리 벗김
        # 400 → 재시도 두 번, 두 번째는 response_format 없이 스키마가 프롬프트에
        assert len(fake.requests) == 2
        assert "response_format" not in fake.requests[-1]
        assert '"answer"' in fake.requests[-1]["messages"][0]["content"]
        # 세션 내내 내려간 길로 — 다음 호출은 바로 prompt 모드(요청 1회)
        n = len(fake.requests)
        assert llm.structured("t.c", "s", "u", SCHEMA, max_tokens=64) == {"answer": "울타리 안"}
        assert len(fake.requests) == n + 1
        assert "response_format" not in fake.requests[-1]
    finally:
        fake.close()


def test_length_is_named_truncation(genos_env):
    fake = _Fake("length")
    try:
        llm = genos_env(fake.url).LLM()
        assert llm.structured("t.d", "s", "u", SCHEMA, max_tokens=8) is None
        assert "max_tokens=8" in llm.log[-1].error
    finally:
        fake.close()


def test_extract_json():
    f = _fresh().LLM._extract_json
    assert f('{"a":1}') == '{"a":1}'
    assert f('<think>x</think>\n```json\n{"a":1}\n```') == '{"a":1}'
    assert f('답은 다음과 같다: {"a": {"b": 2}} 끝') == '{"a": {"b": 2}}'


def test_disable_thinking_reaches_server_and_survives_schema_fallback(genos_env):
    fake=_Fake('reject')
    try:
        client=genos_env(fake.url).LLM()
        result=client.structured('structure.test','s','u',SCHEMA,max_tokens=64,enable_thinking=False)
        assert result=={'answer':'울타리 안'}
        assert len(fake.requests)==2
        assert all(r['chat_template_kwargs']=={'enable_thinking':False} for r in fake.requests)
        exchange=client.log[-1]
        # This fake intentionally ignores the flag, to verify unfiltered receipt.
        assert exchange.raw_response=='<think>생각 중…</think>\n```json\n{"answer": "울타리 안"}\n```'
        assert exchange.parsed==result and exchange.requested_thinking is False
        assert exchange.provider_usage=={'prompt_tokens':11,'completion_tokens':5}
        assert len(exchange.provider_response)==4
        assert exchange.dump()['provider_response'][0]['choices'][0]['delta']['content'].startswith('<think>')
    finally:fake.close()


def test_separate_reasoning_only_cutoff_is_preserved(genos_env,monkeypatch):
    fake=_Fake('schema')
    try:
        client=genos_env(fake.url).LLM()
        chunks=[{'choices':[{'delta':{'reasoning_content':'synthetic reasoning field'},'finish_reason':None}]},
                {'choices':[{'delta':{},'finish_reason':'length'}],
                 'usage':{'prompt_tokens':8,'completion_tokens':16,'completion_tokens_details':{'reasoning_tokens':16}}}]
        class Reply:
            status_code=200;headers={}
            def raise_for_status(self):pass
            def iter_lines(self):
                for c in chunks:yield ('data: '+json.dumps(c)).encode()
                yield b'data: [DONE]'
        monkeypatch.setattr(client._session,'post',lambda *a,**k:Reply())
        assert client.structured('structure.cutoff','s','u',SCHEMA,max_tokens=16,enable_thinking=False) is None
        ex=client.log[-1]
        assert ex.raw_response=='' and ex.stop_reason=='max_tokens'
        assert ex.provider_response==chunks
        assert ex.provider_usage['completion_tokens_details']['reasoning_tokens']==16
        assert '예산을 올려라' not in ex.error
    finally:fake.close()


def test_partial_content_survives_transport_failure(genos_env,monkeypatch):
    fake=_Fake('schema')
    try:
        client=genos_env(fake.url).LLM()
        chunk={'choices':[{'delta':{'content':'{"answer": "partial'},'finish_reason':None}]}
        class Reply:
            status_code=200;headers={}
            def raise_for_status(self):pass
            def iter_lines(self):
                yield ('data: '+json.dumps(chunk)).encode()
                raise RuntimeError('synthetic interrupted stream')
        monkeypatch.setattr(client._session,'post',lambda *a,**k:Reply())
        assert client.structured('structure.partial','s','u',SCHEMA,enable_thinking=False) is None
        assert client.log[-1].raw_response=='{"answer": "partial'
        assert client.log[-1].provider_response==[chunk]
    finally:fake.close()
