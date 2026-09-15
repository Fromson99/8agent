"""망분리 운반(ops) — 기록·반출·재생·스냅샷의 왕복 규약.

여기서 지키는 것 넷:
  (1) 기록 모드에서 쓰기 조작만 아웃박스에 쌓인다 — GET·4xx·재생은 안 쌓인다.
  (2) 재생은 멱등이다 — 같은 묶음을 두 번 돌려도 두 번 적용되지 않는다.
  (3) 기준(rev)이 낡으면 409 로 멈춘다 — force=1 만 이를 덮는다.
  (4) 스냅샷→복원은 상태를 그 시점으로 통째로 되돌린다 (rev 포함).

폴더 만들기(POST /v1/structure/folders)를 표본 조작으로 쓴다 — 파일만 쓰고
LLM·docling 을 부르지 않아서다.
"""
from __future__ import annotations

import base64
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi", reason="FastAPI 필요")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """저장 경로 전부를 tmp 로 갈아끼우고 기록·복원을 연 앱."""
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
    monkeypatch.setenv("OPS_RECORD", "1")
    monkeypatch.setenv("OPS_ALLOW_RESTORE", "1")
    monkeypatch.delenv("OPS_INBOX_DIR", raising=False)

    # 경로 상수는 임포트 시점에 굳는다 — api.ops 까지 전부 다시 읽게 한다.
    for mod in [m for m in list(sys.modules)
                if m.startswith(("lawrag.api.routers", "lawrag.api.structure_app", "lawrag.api.ops"))]:
        del sys.modules[mod]

    from fastapi.testclient import TestClient

    from lawrag.api.structure_app import app

    # 등록부는 사본 — 시험이 저장소의 registry.yaml 을 건드리면 안 된다.
    reg_copy = tmp_path / "registry.yaml"
    reg_copy.write_text((Path(__import__("lawrag").__file__).resolve().parent / "core" / "registry.yaml").read_text(encoding="utf-8"),
                        encoding="utf-8")
    from lawrag.core import router as core_router
    monkeypatch.setattr(core_router, "DEFAULT_REGISTRY", reg_copy)
    core_router.load.cache_clear()

    c = TestClient(app)
    yield c
    core_router.load.cache_clear()


def _op(op_id: str, method: str, path: str, body: dict | None) -> dict:
    raw = json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
    return {"id": op_id, "ts": "t", "method": method, "path": path, "query": "",
            "content_type": "application/json" if body is not None else "",
            "status": 0, "body_b64": base64.b64encode(raw).decode()}


def _outbox_tar(ops: list[dict], base: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        def put(name: str, data: bytes) -> None:
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))
        put("ops.jsonl",
            "".join(json.dumps(o, ensure_ascii=False) + "\n" for o in ops).encode())
        put("manifest.json", json.dumps(
            {"format": "8agent-ops/1", "exported_at": "t",
             "base": base, "count": len(ops)}).encode())
    return buf.getvalue()


def _apply(client, blob: bytes, **params):
    return client.post("/v1/ops/apply", params=params,
                       files={"file": ("outbox.tar.gz", blob, "application/gzip")})


def _folders(client) -> list[str]:
    return [f["name"] for f in client.get("/v1/structure/folders").json()["folders"]]


def test_record_scope(client):
    """쓰기만 쌓인다 — GET 도, 거절당한(4xx) 쓰기도 아웃박스에 남지 않는다."""
    assert client.post("/v1/structure/folders", json={"name": "갑"}).status_code == 200
    client.get("/v1/structure/folders")                        # GET — 기록 밖
    assert client.post("/v1/structure/folders",
                       json={"name": ""}).status_code == 400   # 4xx — 기록 밖

    s = client.get("/v1/ops/status").json()
    assert s["record"] is True and s["outbox"] == 1 and s["rev"] == 1

    ob = client.get("/v1/ops/outbox").json()
    assert ob["count"] == 1
    op = ob["ops"][0]
    assert (op["method"], op["path"]) == ("POST", "/v1/structure/folders")
    assert op["body_bytes"] > 0 and "body_b64" not in op       # 목록엔 몸통이 없다


def test_apply_is_idempotent_and_not_rerecorded(client):
    """같은 묶음 두 번 → 두 번째는 전부 건너뛴다. 재생은 다시 기록되지 않는다."""
    blob = _outbox_tar([_op("op-1", "POST", "/v1/structure/folders", {"name": "을"})])

    r = _apply(client, blob).json()
    assert r["applied"] == 1 and r["failed"] == 0
    assert r["warning"]                                        # 기준 없는 묶음 — 경고
    assert "을" in _folders(client)
    assert client.get("/v1/ops/status").json()["outbox"] == 0  # 재생 ≠ 기록

    again = _apply(client, blob).json()
    assert again["applied"] == 0 and again["skipped"] == 1


def test_stale_base_needs_force(client):
    """기준 rev 가 낡으면 409 — 낡은 스냅샷 보고 내린 결정이 정본을 덮으면 안 된다."""
    a = _outbox_tar([_op("a-1", "POST", "/v1/structure/folders", {"name": "갑"})],
                    base={"snapshot_id": "s0", "rev": 0})
    assert _apply(client, a).json()["applied"] == 1            # rev 0 → 1

    b = _outbox_tar([_op("b-1", "POST", "/v1/structure/folders", {"name": "을"})],
                    base={"snapshot_id": "s0", "rev": 0})
    assert _apply(client, b).status_code == 409
    assert "을" not in _folders(client)

    forced = _apply(client, b, force=1).json()
    assert forced["applied"] == 1 and "을" in _folders(client)


def test_export_then_apply_round(client):
    """기록 → 반출 → (같은 서버에) 재생. 실전에선 재생만 그쪽에서 일어난다."""
    client.post("/v1/structure/folders", json={"name": "갑"})
    r = client.get("/v1/ops/outbox/export")
    assert r.status_code == 200

    report = _apply(client, r.content).json()
    assert report["applied"] == 1 and report["ops"][0]["ok"]
    # 폴더 만들기는 있으면 조용히 지나간다 — 상태는 그대로 갑 하나다.
    assert _folders(client) == ["갑"]


def test_snapshot_restore_roundtrip(client):
    """스냅샷 뒤에 생긴 것은 복원이 지운다 — rev 도 그 시점으로 돌아간다."""
    client.post("/v1/structure/folders", json={"name": "갑"})
    snap = client.get("/v1/ops/snapshot")
    assert snap.status_code == 200

    client.post("/v1/structure/folders", json={"name": "을"})
    assert sorted(_folders(client)) == ["갑", "을"]
    assert client.get("/v1/ops/status").json()["rev"] == 2

    r = client.post("/v1/ops/restore",
                    files={"file": ("snap.tar.gz", snap.content, "application/gzip")})
    assert r.status_code == 200
    body = r.json()
    assert "structure" in body["restored"] and body["rev"] == 1

    assert _folders(client) == ["갑"]
    s = client.get("/v1/ops/status").json()
    assert s["rev"] == 1 and s["outbox"] == 0                  # 옛 기록은 치워졌다
    assert s["base"] and s["base"]["snapshot_id"] == body["snapshot_id"]


def test_restore_is_locked_by_default(client, monkeypatch):
    """OPS_ALLOW_RESTORE 없이는 403 — 정본 위에서 실수로 눌러도 안 덮인다."""
    import lawrag.api.ops as ops_mod
    monkeypatch.setattr(ops_mod, "ALLOW_RESTORE", False)
    r = client.post("/v1/ops/restore",
                    files={"file": ("x.tar.gz", b"junk", "application/gzip")})
    assert r.status_code == 403
