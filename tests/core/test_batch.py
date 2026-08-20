"""배치 파이프라인 — 라인업·실행기·증분 규율의 계약 (2026-08-19).

모델·docling 없이 돈다: 스토어·corpus·inbox 는 tmp, 무거운 단계는 가짜로 바꾼다.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core import batch as batch_mod   # noqa: E402


def _env(tmp_path, monkeypatch):
    store = tmp_path / "data" / "structure"
    store.mkdir(parents=True)
    monkeypatch.setenv("STRUCTURE_STORE", str(store))
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path / "data" / "corpus"))
    monkeypatch.setenv("PIPELINE_DIR", str(tmp_path / "data" / "pipeline"))
    monkeypatch.setenv("PIPELINE_INBOX", str(tmp_path / "data" / "inbox"))
    monkeypatch.setenv("RAG_VECTOR_STORE", str(tmp_path / "data" / "embeddings" / "sections"))
    monkeypatch.setenv("RAG_FRAMES_DIR", str(tmp_path / "data" / "frames"))
    monkeypatch.setenv("GLOSSARY_STORE", str(tmp_path / "data" / "glossary.json"))
    monkeypatch.setenv("RAG_SCOPES_FILE", str(tmp_path / "data" / "rag" / "scopes.yml"))
    return store


def _doc(store, doc_id, name, kind="law"):
    d = store / doc_id
    d.mkdir(parents=True)
    nodes = [{"id": 1, "parent": None, "level": 1, "surface": "제1조", "title": "목적", "span": [0, 1], "page": 1}]
    blocks = [{"idx": 0, "page": 1, "text": "제1조(목적) 이 법은 시험을 위한 것이다.", "kind": "text"}]
    (d / "result.json").write_text(json.dumps({"nodes": nodes, "blocks": blocks}), encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"doc_id": doc_id, "name": name, "kind": kind,
                                             "folder": "법령·규정", "score": 0.9, "passed": True,
                                             "tier": "hot", "at": "2026-08-19T00:00:00+00:00"}),
                                 encoding="utf-8")


def _wait(runner, timeout=10.0):
    t0 = time.time()
    while runner.is_running() and time.time() - t0 < timeout:
        time.sleep(0.05)
    assert not runner.is_running(), "실행이 끝나지 않았다"


# ---------------------------------------------------------------- 라인업
def test_빈_스토어_라인업은_세기만_한다(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    lu = batch_mod.lineup()
    assert lu["documents"] == 0
    assert list(lu["stages"]) == list(batch_mod.STAGES)
    assert lu["stages"]["ingest"]["pending"] == 0
    assert lu["stages"]["embed"]["pending"] == 0


def test_inbox_파일은_투입_후보로_세어지고_내규_폴더는_내규_문으로(tmp_path, monkeypatch):
    store = _env(tmp_path, monkeypatch)
    inbox = batch_mod.inbox_path()
    (inbox / "내규").mkdir(parents=True)
    (inbox / "법령·규정").mkdir(parents=True)
    (inbox / "내규" / "세칙_v1_2024.docx").write_bytes(b"PK\x03\x04 naegyu")
    (inbox / "법령·규정" / "규정.pdf").write_bytes(b"%PDF fake")
    (inbox / "법령·규정" / "메모.txt").write_bytes(b"ignored")
    tg = batch_mod.ingest_targets()
    assert sorted((t["via"], t["folder"], t["name"]) for t in tg) == [
        ("inbox", "내규", "세칙_v1_2024"), ("inbox", "법령·규정", "규정")]
    assert all(not t["in_store"] for t in tg)

    calls = []
    from lawrag.core import internal_rules, ingest as ingest_mod

    def fake_internal(raw, filename, *, store, name="", folder="", **k):
        calls.append(("internal", filename, folder))
        _doc(store, "a" * 16, name, kind="internal")
        return {"doc_id": "a" * 16}

    def fake_ingest(raw, filename, *, store, name="", folder="", **k):
        calls.append(("generic", filename, folder))
        _doc(store, "b" * 16, name)
        return {"doc_id": "b" * 16}

    monkeypatch.setattr(internal_rules, "ingest_internal_rule", fake_internal)
    monkeypatch.setattr(ingest_mod, "ingest", fake_ingest)

    r = batch_mod.Runner()
    r.start(["ingest"])
    _wait(r)
    st = r.status()
    assert st["status"] == "done" and st["stages"]["ingest"]["status"] == "done"
    assert st["stages"]["ingest"]["result"]["ok"] == 2
    assert st["stages"]["ingest"]["result"]["failed"] == 0 and st["stages"]["ingest"]["errors"] == []
    # 문서별 기록 — 상태 표에는 kind 그대로, 사건 로그에는 doc_kind 로 (사건 종류 kind 와 충돌 금지)
    rows = st["stages"]["ingest"]["docs"]
    assert [r["ok"] for r in rows] == [True, True] and any(r.get("kind") == "internal" for r in rows)
    ev = [e for e in r.log_tail(st["run_id"]) if e["kind"] == "ingest_doc"]
    assert len(ev) == 2 and all(e.get("stage") == "ingest" for e in ev) and any(e.get("doc_kind") == "internal" for e in ev)
    assert ("internal", "세칙_v1_2024.docx", "내규") in calls
    assert ("generic", "규정.pdf", "법령·규정") in calls
    # 처리한 파일은 _done/ 으로 옮겨져 다음 라인업에서 빠진다
    assert not (inbox / "내규" / "세칙_v1_2024.docx").exists()
    assert (inbox / "_done" / "내규" / "세칙_v1_2024.docx").exists()
    assert batch_mod.lineup()["stages"]["ingest"]["pending"] == 0


def test_manifest_미투입은_세어지고_투입된_것은_빠진다(tmp_path, monkeypatch):
    store = _env(tmp_path, monkeypatch)
    corpus = batch_mod.corpus_path()
    (corpus / "kofia" / "X").mkdir(parents=True)
    html = (corpus / "kofia" / "X" / "X 조문.html")
    html.write_text("<html>fake</html>", encoding="utf-8")
    (corpus / "kofia" / "manifest.json").write_text(json.dumps({"items": [
        {"name": "X규정", "kind": "kofia-rule", "body_html_file": str(html)}]}, ensure_ascii=False),
        encoding="utf-8")
    tg = batch_mod.ingest_targets()
    assert len(tg) == 1 and tg[0]["via"] == "kofia" and tg[0]["folder"] == "협회규정" and not tg[0]["in_store"]
    # 같은 바이트의 doc_id 로 스토어에 있으면 투입됨으로 센다
    _doc(store, tg[0]["doc_id"], "X규정", kind="kofia-rule")
    assert batch_mod.ingest_targets()[0]["in_store"]
    assert batch_mod.lineup()["stages"]["ingest"]["pending"] == 0


# ---------------------------------------------------------------- 실행기
def test_실행기는_한_번에_하나만_돌고_상태와_로그를_남긴다(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    r = batch_mod.Runner()
    gate = {"go": False}

    def slow_terms(self, opts):
        while not gate["go"]:
            time.sleep(0.02)
        return {"note": "끝"}

    monkeypatch.setattr(batch_mod.Runner, "_run_terms", slow_terms)
    info = r.start(["terms", "scopes"])
    assert info["stages"] == ["terms", "scopes"]
    import pytest
    with pytest.raises(RuntimeError):
        r.start(["terms"])                                # 둘째 딸깍은 거절
    st = r.status()
    assert st["running"] and st["stages"]["terms"]["status"] in ("queued", "running")
    assert st["stages"]["ingest"]["status"] == "skipped"   # 요청 안 한 단계
    gate["go"] = True
    _wait(r)
    st = r.status()
    assert st["status"] == "done"
    assert st["stages"]["terms"]["status"] == "done" and st["stages"]["scopes"]["status"] == "done"
    # 상태 파일·로그·이력
    assert (batch_mod.pipeline_dir() / "state.json").exists()
    ev = r.log_tail(st["run_id"])
    assert [e["kind"] for e in ev][:2] == ["start", "stage_start"] and ev[-1]["kind"] == "end"
    assert r.runs()[0]["run_id"] == st["run_id"]
    # 단계 순서는 요청 순서가 아니라 파이프라인 순서다
    assert r.start(["scopes", "terms"])["stages"] == ["terms", "scopes"]
    _wait(r)


def test_단계_실패는_기록되고_다음_단계는_계속(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    r = batch_mod.Runner()

    def boom(self, opts):
        raise ValueError("고장")
    monkeypatch.setattr(batch_mod.Runner, "_run_terms", boom)
    r.start(["terms", "scopes"])
    _wait(r)
    st = r.status()
    assert st["status"] == "failed"
    assert st["stages"]["terms"]["status"] == "failed" and "고장" in st["stages"]["terms"]["errors"][0]
    assert st["stages"]["scopes"]["status"] == "done"


def test_모델_없는_단계는_건너뛰고_이유를_남긴다(tmp_path, monkeypatch):
    store = _env(tmp_path, monkeypatch)
    _doc(store, "c" * 16, "시험법")
    from lawrag.core import embedding, llm as llm_mod
    monkeypatch.setattr(embedding, "available", lambda: False)
    monkeypatch.setattr(llm_mod, "available", lambda: False)
    monkeypatch.setattr(llm_mod, "load_env", lambda: None)
    r = batch_mod.Runner()
    r.start(["frames", "embed"])
    _wait(r)
    st = r.status()
    assert st["status"] == "done"
    assert st["stages"]["frames"]["status"] == "skipped" and "LLM 없음" in st["stages"]["frames"]["note"]
    assert st["stages"]["embed"]["status"] == "skipped" and "임베딩 모델 없음" in st["stages"]["embed"]["note"]


def test_중지는_문서_경계에서_듣는다(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    inbox = batch_mod.inbox_path()
    (inbox / "f").mkdir(parents=True)
    for i in range(5):
        (inbox / "f" / f"d{i}.pdf").write_bytes(f"%PDF {i}".encode())
    from lawrag.core import ingest as ingest_mod
    n = {"k": 0}
    r = batch_mod.Runner()

    def slow(raw, filename, *, store, name="", folder="", **k):
        n["k"] += 1
        if n["k"] == 2:
            r.stop()
        time.sleep(0.05)
        did = ("%02d" % n["k"]) * 8
        d = store / did; d.mkdir(parents=True, exist_ok=True)
        (d / "result.json").write_text("{}"); (d / "meta.json").write_text(json.dumps({"doc_id": did, "name": name}))
        return {"doc_id": did}
    monkeypatch.setattr(ingest_mod, "ingest", slow)
    r.start(["ingest", "scopes"])
    _wait(r)
    st = r.status()
    assert st["status"] == "stopped"
    assert n["k"] == 2                                  # 셋째 문서는 안 집었다
    assert st["stages"]["scopes"]["status"] == "stopped"


def test_embed_plan_은_새_구역만_센다(tmp_path, monkeypatch):
    store = _env(tmp_path, monkeypatch)
    _doc(store, "d" * 16, "법A")
    from lawrag.core.terms import embed_sections
    p = embed_sections.plan(store)
    assert p["sections"] == 1 and p["fresh"] == 1 and list(p["docs_pending"]) == ["d" * 16]
    lu = batch_mod.lineup()
    assert lu["stages"]["embed"]["pending"] == 1 and lu["stages"]["embed"]["units"]["fresh"] == 1


def test_API_가_라인업_실행_상태를_낸다(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from lawrag.api.routers import pipeline as pr
    monkeypatch.setattr(batch_mod.Runner, "_run_scopes", lambda self, opts: {"note": "ok"})
    app = FastAPI(); app.include_router(pr.router); c = TestClient(app)
    lu = c.get("/v1/pipeline/lineup").json()
    assert lu["order"] == list(batch_mod.STAGES) and "labels" in lu
    assert c.post("/v1/pipeline/run", json={"stages": ["없는단계"]}).status_code == 400
    r = c.post("/v1/pipeline/run", json={"stages": ["scopes"]})
    assert r.status_code == 200
    _wait(batch_mod.RUNNER)
    st = c.get("/v1/pipeline/status").json()
    assert st["status"] == "done" and st["stages"]["scopes"]["status"] == "done"
    assert c.get("/v1/pipeline/runs").json()["runs"][0]["run_id"] == st["run_id"]
    assert c.get(f"/v1/pipeline/runs/{st['run_id']}/log").json()["events"]
