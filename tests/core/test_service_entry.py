"""GenOS 진입점(service.py) — 게이트웨이 JSON 봉투 하나로 전부가 나가는지.

여기서 지키는 것 셋:
  (1) call — 임의 API 가 터널을 지나 앱 상태를 실제로 바꾼다.
  (2) snapshot/apply — 망분리 운반이 게이트웨이 봉투로도 왕복한다.
  (3) 실패는 예외가 아니라 JSON 이다 — 그쪽 터미널이 원인을 읽을 수 있어야 한다.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi", reason="FastAPI 필요")


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("STRUCTURE_STORE", str(store))
    monkeypatch.setenv("STRUCTURE_LEDGER", str(tmp_path / "ledger.json"))
    monkeypatch.setenv("STRUCTURE_CUSTOM_DIR", str(tmp_path / "custom"))
    monkeypatch.setenv("FORMAT_BINDINGS", str(tmp_path / "bindings.json"))
    monkeypatch.setenv("FORMAT_CANVAS", str(tmp_path / "canvas.json"))
    monkeypatch.setenv("FORMATS_DIR", str(tmp_path / "formats"))
    monkeypatch.setenv("GLOSSARY_STORE", str(tmp_path / "glossary.json"))
    monkeypatch.setenv("RAG_LINKS_STORE", str(tmp_path / "links.json"))
    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path / "rag"))
    monkeypatch.setenv("RAG_RULES_DIR", str(tmp_path / "rules"))
    monkeypatch.setenv("RAG_VECTOR_STORE", str(tmp_path / "embeddings"))
    monkeypatch.setenv("OPS_DIR", str(tmp_path / "ops"))
    monkeypatch.delenv("OPS_RECORD", raising=False)
    monkeypatch.delenv("OPS_INBOX_DIR", raising=False)

    for mod in [m for m in list(sys.modules)
                if m.startswith(("api.routers", "api.structure_app", "api.ops",
                                 "service"))]:
        del sys.modules[mod]

    import service
    yield service


def _run(svc, data):
    return asyncio.run(svc.service({}, data))


def test_ping_and_unknown_op(svc):
    out = _run(svc, {"op": "ping"})
    assert out["service"] == "8-AGENT" and out["rev"] == 0

    bad = _run(svc, {"op": "없는것"})
    assert "error" in bad and "ping" in bad["ops"]


def test_ls_probe(svc, tmp_path):
    """볼륨 공유 판별용 진단 — 디렉토리·파일·부재를 구분해 말한다."""
    (tmp_path / "vol").mkdir()
    (tmp_path / "vol" / "probe.txt").write_text("x", encoding="utf-8")

    d = _run(svc, {"op": "ls", "path": str(tmp_path / "vol")})
    assert d["dir"] and d["entries"][0]["name"] == "probe.txt"

    f = _run(svc, {"op": "ls", "path": str(tmp_path / "vol" / "probe.txt")})
    assert f["dir"] is False and f["bytes"] == 1

    none = _run(svc, {"op": "ls", "path": str(tmp_path / "없다")})
    assert none["exists"] is False


def test_call_mutates_and_reads_back(svc):
    made = _run(svc, {"op": "call", "method": "POST",
                      "path": "/v1/structure/folders", "json": {"name": "갑"}})
    assert made["ok"] and made["json"] == {"created": "갑"}

    got = _run(svc, {"op": "call", "path": "/v1/structure/folders"})
    assert [f["name"] for f in got["json"]["folders"]] == ["갑"]

    denied = _run(svc, {"op": "call", "method": "POST",
                        "path": "/v1/structure/folders", "json": {"name": ""}})
    assert denied["status"] == 400 and not denied["ok"]   # 실패도 JSON 봉투다


def test_report_is_selfcontained_html(svc, tmp_path):
    """현황 리포트 — 서버 없이 열 파일 하나. 상태가 실제로 비친다."""
    _run(svc, {"op": "call", "method": "POST",
               "path": "/v1/structure/folders", "json": {"name": "갑"}})

    out = _run(svc, {"op": "report"})
    assert "데이터 현황" in out["html"] and "갑" in out["html"]
    assert "<script" not in out["html"]           # 정적 — 실행 코드 없음

    dst = tmp_path / "vol" / "현황.html"
    to = _run(svc, {"op": "report", "path": str(dst)})
    assert dst.exists() and to["bytes"] == dst.stat().st_size


def test_snapshot_apply_roundtrip(svc, tmp_path):
    _run(svc, {"op": "call", "method": "POST",
               "path": "/v1/structure/folders", "json": {"name": "갑"}})

    snap = _run(svc, {"op": "snapshot"})
    assert snap["meta"]["keys"] and snap["bytes"] > 0
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(snap["tar_b64"]))) as tar:
        assert "meta.json" in tar.getnames()

    # snapshot_to — 공유 볼륨 경로에 파일로 (b64 한계 우회 길)
    dst = tmp_path / "vol" / "snap.tar.gz"
    to = _run(svc, {"op": "snapshot_to", "path": str(dst)})
    assert dst.exists() and to["bytes"] == dst.stat().st_size

    # apply — 아웃박스 봉투 재생 + 멱등
    raw = json.dumps({"name": "을"}, ensure_ascii=False).encode()
    op = {"id": "svc-1", "ts": "t", "method": "POST",
          "path": "/v1/structure/folders", "query": "",
          "content_type": "application/json", "status": 0,
          "body_b64": base64.b64encode(raw).decode()}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, payload in (
                ("ops.jsonl", (json.dumps(op) + "\n").encode()),
                ("manifest.json", json.dumps(
                    {"format": "8agent-ops/1", "base": None, "count": 1}).encode())):
            ti = tarfile.TarInfo(name)
            ti.size = len(payload)
            tar.addfile(ti, io.BytesIO(payload))
    blob = base64.b64encode(buf.getvalue()).decode()

    report = _run(svc, {"op": "apply", "tar_b64": blob})
    assert report["applied"] == 1
    again = _run(svc, {"op": "apply", "tar_b64": blob})
    assert again["applied"] == 0 and again["skipped"] == 1

    got = _run(svc, {"op": "call", "path": "/v1/structure/folders"})
    assert [f["name"] for f in got["json"]["folders"]] == ["갑", "을"]
