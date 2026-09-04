"""내규 업로드 배선 — 화면 업로드(folder=내규)가 CLI(ingest_naegyu)와 같은 문을
지나는가 (2026-08-19 과제 2 · 내규는 같은 스토어에 태그로 가른다).

docling 을 돌리지 않는다 — 두 문(ingest_internal_rule · ingest)을 기록기로 바꿔
**어느 문으로 갔고 무엇을 들고 갔는지**만 본다. 구조화 자체는
tests/core/test_internal_rules.py 가 지킨다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def _client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from lawrag.api.routers import structure as structure_router

    monkeypatch.setattr(structure_router, "STORE", tmp_path / "store")
    app = FastAPI()
    app.include_router(structure_router.router)
    return TestClient(app), structure_router


def _fake_result(store, doc_id, meta):
    d = store / doc_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text('{"doc_id": "%s", "name": "%s"}' % (doc_id, meta.get("name", "")),
                                 encoding="utf-8")
    return {"doc_id": doc_id, "meta": {"doc_id": doc_id, **meta}}


def test_내규_폴더_업로드는_내규_문으로_간다(tmp_path, monkeypatch):
    from lawrag.core import internal_rules
    c, router = _client(tmp_path, monkeypatch)
    calls = {}

    def fake_internal(raw, filename, *, store, name="", folder="", status="현행",
                      series="", version="", extra_meta=None):
        calls["internal"] = dict(filename=filename, name=name, folder=folder,
                                 status=status, series=series)
        return _fake_result(store, "abc123abc123abc1", {"name": name, "kind": "internal",
                                              "status": status, "folder": folder})

    def fake_ingest(*a, **k):                       # 여기로 오면 배선이 틀린 것
        calls["generic"] = True
        return _fake_result(k["store"], "0000000000000000", {"name": k.get("name", "")})

    monkeypatch.setattr(internal_rules, "ingest_internal_rule", fake_internal)
    monkeypatch.setattr(router.ingest_mod, "ingest", fake_ingest)

    r = c.post("/v1/structure/documents",
               files={"file": ("위험관리기준시행세칙_v1_2024.docx", b"PK\x03\x04fake",
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
               data={"folder": "내규", "status": "구판"})
    assert r.status_code == 200, r.text
    assert "generic" not in calls
    assert calls["internal"]["folder"] == internal_rules.FOLDER
    assert calls["internal"]["status"] == "구판"
    assert calls["internal"]["name"] == "위험관리기준시행세칙_v1_2024"   # 확장자 없이
    assert r.json()["doc_id"] == "abc123abc123abc1"


def test_내규_폴더에_docxstyle_엔진은_거절(tmp_path, monkeypatch):
    c, router = _client(tmp_path, monkeypatch)
    r = c.post("/v1/structure/documents",
               files={"file": ("지침.docx", b"PK\x03\x04fake", "application/octet-stream")},
               data={"folder": "내규", "engine": "docxstyle"})
    assert r.status_code == 400 and "유도" in r.text


def test_다른_폴더는_일반_문으로_간다(tmp_path, monkeypatch):
    from lawrag.core import internal_rules
    c, router = _client(tmp_path, monkeypatch)
    calls = {}
    monkeypatch.setattr(internal_rules, "ingest_internal_rule",
                        lambda *a, **k: calls.setdefault("internal", True))

    def fake_ingest(raw, filename, *, store, name="", folder="", **k):
        calls["generic"] = dict(folder=folder)
        return _fake_result(store, "abcdef0123456789", {"name": name, "folder": folder})

    monkeypatch.setattr(router.ingest_mod, "ingest", fake_ingest)
    r = c.post("/v1/structure/documents",
               files={"file": ("상장규정.docx", b"PK\x03\x04fake", "application/octet-stream")},
               data={"folder": "상장규정"})
    assert r.status_code == 200, r.text
    assert "internal" not in calls and calls["generic"]["folder"] == "상장규정"


def test_재해석은_내규_프로파일을_다시_건다(tmp_path, monkeypatch):
    """meta.kind=internal 문서는 재해석 때도 장>절>조 부분순서가 따라간다."""
    from lawrag.core import internal_rules
    c, router = _client(tmp_path, monkeypatch)
    d = router.STORE / "doc1"
    d.mkdir(parents=True)
    (d / "meta.json").write_text('{"doc_id":"doc1","name":"세칙","kind":"internal"}', encoding="utf-8")
    (d / "source.pdf").write_bytes(b"%PDF-fake")
    seen = {}

    def fake_interpret(pdf, *, store, binding_of=None, **kw):
        seen.update(kw)
        return {"pages": [], "nodes": [], "blocks": [],
                "fitness": {"score": 0.9, "passed": True, "tier": "ok"}}

    monkeypatch.setattr(router.ingest_mod, "interpret_doc", fake_interpret)
    router._interpret(d / "source.pdf", cache=d / "parse.json", doc_id="doc1")
    assert seen.get("partial_order") == internal_rules.PROFILE["partial_order"]
    # 사람이 순서 힌트를 명시하면 그것이 이긴다
    seen.clear()
    router._interpret(d / "source.pdf", doc_id="doc1", partial_order=[("kr_장", "kr_article")])
    assert seen.get("partial_order") == [("kr_장", "kr_article")]
