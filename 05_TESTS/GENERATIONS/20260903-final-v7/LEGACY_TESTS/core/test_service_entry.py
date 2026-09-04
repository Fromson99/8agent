"""GenOS 진입점(service.py)의 봉인된 조회 터널 계약.

여기서 지키는 것 셋:
  (1) 검증된 release 없이 기동하면 legacy 모드로 내려가지 않고 fail-closed 한다.
  (2) call 은 승인된 조회 경로만 ASGI 앱으로 전달하고 mutation surface를 막는다.
  (3) 성공·실패 모두 GenOS 터미널이 읽을 수 있는 JSON 봉투로 돌려준다.
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi", reason="FastAPI 필요")


@pytest.fixture()
def svc(monkeypatch):
    """Import the production entry point without a deployment release binding."""

    monkeypatch.delenv("LAWRAG_RELEASE_STORE", raising=False)
    sys.modules.pop("service", None)
    import service

    yield service


def _run(svc, data):
    return asyncio.run(svc.service({}, data))


def _admit_unit_tunnel(
    svc,
    monkeypatch,
    *,
    status: int = 200,
    raw: bytes = b'{"ok":true}',
):
    """Isolate dispatch tests after separately proving startup is fail-closed."""

    calls = []

    async def fake_call(_app, method, path, query, content_type, body):
        calls.append(
            {
                "method": method,
                "path": path,
                "query": query,
                "content_type": content_type,
                "body": body,
            }
        )
        return status, raw

    release = {"release_id": "test-release", "generation": 7}
    monkeypatch.setattr(svc, "_RELEASE_BOOTSTRAP_ERROR", None)
    monkeypatch.setattr(
        svc,
        "_RELEASE_BINDING",
        {"mode": "release", "ready": True, "release": release},
    )
    # Full release construction/integrity is covered by the release contract suite.
    # These tests exercise only the JSON entry-point dispatch after admission.
    monkeypatch.setattr(svc, "_require_ready", lambda: None)
    monkeypatch.setattr(svc, "_app", lambda: object())
    monkeypatch.setattr(
        svc,
        "_ops",
        lambda: SimpleNamespace(
            _call_self=fake_call,
            _rev=lambda: 7,
            RECORD=False,
            _OPS_FILE=Path("/sealed/outbox.jsonl"),
            _read_ops=lambda _path: [],
        ),
    )
    monkeypatch.setenv("STRUCTURE_STORE", "/sealed/runtime/structure")
    return calls, release


def test_ping_fails_closed_without_release(svc):
    out = _run(svc, {"op": "ping"})
    assert out == {
        "service": "8-AGENT",
        "ready": False,
        "release_mode": "release",
        "release_error": "RuntimeError",
    }
    assert "rev" not in out


def test_ping_and_unknown_op_in_admitted_release(svc, monkeypatch):
    _calls, release = _admit_unit_tunnel(svc, monkeypatch)

    out = _run(svc, {"op": "ping"})
    assert out == {
        "service": "8-AGENT",
        "ready": True,
        "release_mode": "release",
        "release": release,
        "rev": 7,
        "record": False,
        "outbox": 0,
        "store": "/sealed/runtime/structure",
    }

    bad = _run(svc, {"op": "없는것"})
    assert bad["op"] == "없는것"
    assert bad["error"].startswith("PermissionError: ")
    assert "query-only" in bad["error"]


def test_call_params_are_urlencoded_on_approved_get(svc, monkeypatch):
    calls, _release = _admit_unit_tunnel(svc, monkeypatch)
    assert svc._RELEASE_GET_ALLOWLIST == frozenset(
        {
            "/health",
            "/v1/rag/search",
            "/v1/rag/links/summary",
            "/v1/rag/section",
            "/v1/rag/scopes",
            "/v1/rag/nodes",
        }
    )

    out = _run(
        svc,
        {
            "op": "call",
            "method": "GET",
            "path": "/v1/rag/search",
            "params": {"q": "설명의무 & 적합성", "tag": ["가", "나"]},
        },
    )

    assert out == {"status": 200, "ok": True, "json": {"ok": True}}
    assert calls == [
        {
            "method": "GET",
            "path": "/v1/rag/search",
            "query": (
                "q=%EC%84%A4%EB%AA%85%EC%9D%98%EB%AC%B4+%26+"
                "%EC%A0%81%ED%95%A9%EC%84%B1&tag=%EA%B0%80&tag=%EB%82%98"
            ),
            "content_type": "",
            "body": b"",
        }
    ]


def test_call_json_body_on_approved_post(svc, monkeypatch):
    calls, _release = _admit_unit_tunnel(
        svc,
        monkeypatch,
        status=422,
        raw=b'{"detail":"question required"}',
    )
    assert svc._RELEASE_POST_ALLOWLIST == frozenset({"/v1/rag/ask"})
    payload = {"question": "설명의무", "filter": False}

    out = _run(
        svc,
        {
            "op": "call",
            "method": "POST",
            "path": "/v1/rag/ask",
            "json": payload,
        },
    )

    assert out == {
        "status": 422,
        "ok": False,
        "json": {"detail": "question required"},
    }
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/v1/rag/ask"
    assert calls[0]["content_type"] == "application/json"
    assert json.loads(calls[0]["body"].decode("utf-8")) == payload


def test_call_preserves_binary_request_and_response_envelopes(svc, monkeypatch):
    calls, _release = _admit_unit_tunnel(
        svc, monkeypatch, raw=b"\x89PNG\r\n\x1a\n"
    )
    body = b"sealed-query-bytes"

    out = _run(
        svc,
        {
            "op": "call",
            "method": "POST",
            "path": "/v1/rag/ask",
            "body_b64": base64.b64encode(body).decode("ascii"),
            "content_type": "application/octet-stream",
        },
    )

    assert out == {
        "status": 200,
        "ok": True,
        "body_b64": base64.b64encode(b"\x89PNG\r\n\x1a\n").decode("ascii"),
    }
    assert calls[0]["body"] == body
    assert calls[0]["content_type"] == "application/octet-stream"


def test_removed_mutation_operations_are_blocked(svc, monkeypatch):
    calls, _release = _admit_unit_tunnel(svc, monkeypatch)
    requests = (
        {"op": "upload", "filename": "mutation.pdf", "file_b64": "AA=="},
        {"op": "apply", "tar_b64": "AA=="},
        {"op": "apply_from", "path": "/tmp/mutation.tar"},
        {"op": "snapshot"},
        {"op": "snapshot_to", "path": "/tmp/mutation.tar"},
        {"op": "report"},
        {"op": "ls", "path": "/tmp"},
    )

    for request in requests:
        out = _run(svc, request)
        assert out["op"] == request["op"]
        assert out["error"].startswith("PermissionError: ")
        assert "query-only" in out["error"]

    assert calls == []
    assert not any(
        hasattr(svc, name) for name in ("_do_upload", "_do_snapshot", "_do_apply")
    )


def test_unapproved_routes_and_methods_are_blocked(svc, monkeypatch):
    calls, _release = _admit_unit_tunnel(svc, monkeypatch)
    requests = (
        {"op": "call", "method": "GET", "path": "/docs"},
        {"op": "call", "method": "POST", "path": "/v1/rag/feedback"},
        {"op": "call", "method": "POST", "path": "/v1/structure/folders"},
        {"op": "call", "method": "PUT", "path": "/v1/rag/search"},
        {"op": "call", "method": "HEAD", "path": "/health"},
        {"op": "call", "method": "OPTIONS", "path": "/health"},
    )

    for request in requests:
        out = _run(svc, request)
        assert out["op"] == "call"
        assert out["error"].startswith("PermissionError: ")

    assert calls == []


def test_noncanonical_application_paths_are_blocked(svc, monkeypatch):
    calls, _release = _admit_unit_tunnel(svc, monkeypatch)
    paths = (
        "v1/rag/search",
        "/v1//rag/search",
        "/v1/rag/../search",
        "/v1/rag/search?q=x",
        "/v1/rag/search#fragment",
        "/v1\\rag\\search",
    )

    for path in paths:
        out = _run(
            svc,
            {"op": "call", "method": "GET", "path": path},
        )
        assert out["error"].startswith("PermissionError: ")
        assert "canonical application path" in out["error"]

    non_string = _run(
        svc,
        {"op": "call", "method": "GET", "path": ["v1", "rag", "search"]},
    )
    assert non_string["error"].startswith("ValueError: ")
    assert calls == []
