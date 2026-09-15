"""GENOS service(config, data) integration contract."""
from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import pytest


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))
pytest.importorskip("fastapi")


@pytest.fixture()
def svc(monkeypatch, tmp_path):
    monkeypatch.delenv("GENOS_GENERATION", raising=False)
    monkeypatch.setenv("GENOS_RUNTIME_DIR", str(tmp_path / "runtime"))
    sys.modules.pop("service", None)
    module = importlib.import_module("service")
    yield module


def run(svc, data):
    return asyncio.run(svc.service({}, data))


def test_ping_is_lazy_and_api_type_compatible(svc):
    assert svc._APP is None
    direct = run(svc, {"op": "ping"})
    compat = run(svc, {"API_TYPE": "PING"})
    assert direct == compat
    assert direct["ok"] is True
    assert direct["service"] == "8-AGENT"
    assert direct["runtime"] == "genos-semantic-v2"
    assert direct["app_loaded"] is False
    assert svc._APP is None


def test_connections_does_not_require_generation(svc, monkeypatch):
    expected = {"ok": True, "checks": [{"component": "llm", "status": "PASS"}]}
    monkeypatch.setattr("semantic_runtime.genos.smoke", lambda execute=False: expected)
    out = run(svc, {"API_TYPE": "CONNECTIONS", "execute": False})
    assert out == {"status": 200, "body": expected}
    assert svc._APP is None


def test_diagnostics_runs_three_axis_check_without_generation(svc, monkeypatch):
    expected = {
        "ok": True,
        "checks": [
            {"component": "llm", "status": "PASS"},
            {"component": "embed", "status": "PASS"},
            {"component": "vdb", "status": "PASS"},
        ],
    }
    monkeypatch.setattr("semantic_runtime.genos.diagnostics", lambda: expected)
    out = run(svc, {"API_TYPE": "DIAGNOSTICS"})
    assert out == {"status": 200, "body": expected}
    assert svc._APP is None


def test_missing_generation_is_classified_as_503(svc, monkeypatch):
    monkeypatch.setattr(
        svc,
        "_local_release",
        lambda: (_ for _ in ()).throw(RuntimeError("not packaged")),
    )
    out = run(svc, {"op": "call", "method": "GET", "path": "/health"})
    assert out["status"] == 503
    assert out["body"]["error"] == "generation/runtime unavailable"
    assert out["body"]["error_type"] == "RuntimeError"
    assert "not packaged" not in str(out)


def test_query_only_allowlist_blocks_mutation_and_unknown_api_type(svc):
    blocked = run(
        svc,
        {"op": "call", "method": "POST", "path": "/v1/rag/feedback", "json": {}},
    )
    assert blocked == {"status": 403, "body": {"error": "route not allowed"}}
    unknown = run(svc, {"API_TYPE": "DELETE_ALL"})
    assert unknown["status"] == 400
    assert unknown["body"]["supported"] == sorted(svc._API_TYPES)


def test_explicit_generation_boots_health_and_search(svc, monkeypatch):
    generation = ROOT / "01_DATA/SEMANTIC/GENERATIONS/semantic-main-20260907-v1"
    monkeypatch.setenv("GENOS_GENERATION", str(generation))
    health = run(svc, {"API_TYPE": "HEALTH"})
    assert health["status"] == 200
    assert health["body"]["status"] == "ok"
    assert health["body"]["generation_id"] == generation.name
    assert health["body"]["release"]["mode"] == "genos-generation"

    search = run(svc, {"API_TYPE": "RAG_SEARCH", "q": "설명의무", "limit": 3})
    assert search["status"] == 200
    assert isinstance(search["body"]["candidates"], list)
    assert len(search["body"]["candidates"]) <= 3


def test_rag_ask_alias_preserves_body(svc, monkeypatch):
    captured = {}

    async def fake_call(data):
        captured.update(data)
        return {"status": 200, "body": {"ok": True}}

    monkeypatch.setattr(svc, "_call", fake_call)
    out = run(
        svc,
        {"API_TYPE": "RAG_ASK", "question": "신탁재산 구분", "use_llm": False},
    )
    assert out["status"] == 200
    assert captured["path"] == "/v1/rag/ask"
    assert captured["json"] == {"question": "신탁재산 구분", "use_llm": False}


def test_els_query_alias_uses_the_same_grounded_rag_path(svc, monkeypatch):
    captured = {}

    async def fake_call(data):
        captured.update(data)
        return {"status": 200, "body": {"answer": {"text": "답변"}}}

    monkeypatch.setattr(svc, "_call", fake_call)
    out = run(
        svc,
        {
            "API_TYPE": "ELS_QUERY",
            "question": "내규상 승인 절차",
            "channel": "genos-chat",
            "session_id": "chat-1",
        },
    )
    assert out["status"] == 200
    assert captured["path"] == "/v1/rag/ask"
    assert captured["json"]["question"] == "내규상 승인 절차"
    assert captured["json"]["channel"] == "genos-chat"
