"""GenOS 백엔드(lawrag/core/llm.py) — OpenAI 호환 서빙 앞에서 structured() 계약이 서는지.

가짜 서빙 하나를 스레드로 띄운다 (실측 문서 v1.9.0 "LLM 서빙 API 사용"의 모양:
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
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

pytest.importorskip("requests", reason="requests 필요")

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}},
          "required": ["answer"], "additionalProperties": False}


def _fresh():
    """lawrag.core.llm 을 진짜로 다시 적재한다 — sys.modules 만 지우면
    `from core import llm` 이 패키지 속성의 옛 모듈을 돌려준다."""
    import lawrag.core as core
    sys.modules.pop("lawrag.core.llm", None)
    if hasattr(core, "llm"):
        delattr(core, "llm")
    return importlib.import_module("lawrag.core.llm")


class _Fake:
    """모드: 'schema' 는 response_format 을 받아 JSON 을 낸다. 'reject' 는
    response_format 이 오면 400, 없으면 <think>+울타리를 두른 JSON 을 낸다.
    'length' 는 잘린 응답 + finish_reason=length."""

    def __init__(self, mode: str):
        self.mode = mode
        self.requests: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):            # 조용히
                pass

            def do_GET(self):
                if self.path.endswith("/v1/models"):
                    body = json.dumps({"data": [{"id": "fake-llm-7b"}]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers(); self.wfile.write(body)
                else:
                    self.send_response(404); self.end_headers()

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
                req["_auth"] = self.headers.get("Authorization", "")
                outer.requests.append(req)
                if outer.mode == "reject" and "response_format" in req:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error":"response_format not supported"}')
                    return
                if outer.mode == "length":
                    pieces, finish = ['{"answer": "잘', '린'], "length"
                elif outer.mode == "reject":
                    pieces = ["<think>생각 중…</think>\n```json\n",
                              '{"answer": "울타리 안"}', "\n```"]
                    finish = "stop"
                else:
                    pieces, finish = ['{"answer": ', '"스키마 그대로"}'], "stop"
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for i, p in enumerate(pieces):
                    last = i == len(pieces) - 1
                    chunk = {"choices": [{"index": 0, "delta": {"content": p},
                                          "finish_reason": finish if last else None}]}
                    self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode())
                usage = {"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 5}}
                self.wfile.write(f"data: {json.dumps(usage)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


@pytest.fixture()
def genos_env(monkeypatch):
    def _set(url):
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        monkeypatch.delenv("GENOS_LLM_MODEL", raising=False)
        monkeypatch.delenv("GENOS_LLM_JSON_MODE", raising=False)
        monkeypatch.setenv("GENOS_LLM_URL", url)
        monkeypatch.setenv("GENOS_LLM_KEY", "test-key")
        return _fresh()
    return _set


def test_backend_selection(monkeypatch):
    llm_mod = _fresh()
    monkeypatch.setattr(llm_mod, "load_env", lambda: None)   # .env 의 진짜 키 차단
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.delenv("GENOS_LLM_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_mod.backend() == "anthropic" and not llm_mod.available()
    monkeypatch.setenv("GENOS_LLM_URL", "http://x")
    assert llm_mod.backend() == "genos" and llm_mod.available()
    monkeypatch.setenv("LLM_BACKEND", "anthropic")      # 명시가 이긴다
    assert llm_mod.backend() == "anthropic" and not llm_mod.available()


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
