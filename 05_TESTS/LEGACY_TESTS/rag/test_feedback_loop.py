"""피드백 루프의 배선 — 사람이 승인한 원장이 **세 경로 모두**의 회수에 닿는가.

    진입 제외(검색무관 승인)  → auto(assemble)·벡터(vecfirst)·검토(_vector_sections)
    질문 기억(candidates 활성) → auto·벡터의 진입 앞자리 (seeds)
    후순위(참조무관 승인)     → expand_floor 도 뒤로 민다 (cap 을 먼저 먹지 않는다)
    용어 misses               → 감사의 검색무관 지문이 term_key 로 센다
    승격 원장 승인/기각       → /v1/rag/memory{,/resolve}

2026-08-18 감사에서 발견: 진입 제외는 벡터 경로만, 질문 기억은 검토 트랙만,
misses 는 죽은 가지였다 — 그 배선을 시험으로 고정한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import answer as answer_mod                   # noqa: E402
from lawrag.core.rag import promote, tuples as tuples_mod          # noqa: E402
from lawrag.core.rag import vecfirst, vector as vector_mod         # noqa: E402
from lawrag.core.rag import verdicts                               # noqa: E402
from lawrag.core.rag.answer import Section                         # noqa: E402
from lawrag.core.rag.index import Index                            # noqa: E402
from lawrag.core.rag.search import Hit, SearchResult               # noqa: E402


def _docs():
    nodes = [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "총칙", "page": 1, "span": [0, 1]},
        {"id": 2, "parent": None, "level": 1, "surface": "제2조",
         "title": "기준", "page": 1, "span": [1, 2]},
        {"id": 3, "parent": None, "level": 1, "surface": "제3조",
         "title": "벌칙", "page": 2, "span": [2, 3]},
    ]
    blocks = [
        {"idx": 0, "page": 1, "text": "제2조를 따른다", "kind": "text"},
        {"idx": 1, "page": 1, "text": "제3조를 참고한다", "kind": "text"},
        {"idx": 2, "page": 2, "text": "벌칙 조항이다", "kind": "text"},
    ]
    return [("d1", {"name": "A.pdf"}, {"nodes": nodes, "blocks": blocks})]


def _index(terms=None):
    idx = Index.from_docs(_docs(), terms or [])
    idx._refs = {"d1": []}
    idx._cross = ([], [])
    return idx


def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path / "rag"))
    monkeypatch.setenv("RAG_RULES_DIR", str(tmp_path / "rules"))
    verdicts._rules_cache.clear()
    promote._qvec_cache.clear()


def _block_entry(doc_id, node):
    """검색무관 지문 → 사람이 '진입제외' 승인 — 규칙 파일에 entry 행이 선다."""
    verdicts.log("q0", "질문", [{"kind": "검색무관", "reason": "무관", "via": "벡터",
                                "section": {"n": 1, "doc_id": doc_id, "doc": "A",
                                            "node": node, "path": "제3조"},
                                "ref_src": None}])
    g = verdicts.backlog()["misses"][0]
    verdicts.resolve_miss(g, "진입제외", "빗나갔다")
    assert verdicts.is_entry_blocked(doc_id, node)


def _arm_vector(tmp_path, monkeypatch, qvec):
    d = tmp_path / "sections"
    d.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(d / "vectors.npz",
                        v=np.array([[1, 0], [0, 1], [0.6, 0.8]], dtype=np.float16))
    with (d / "meta.jsonl").open("w", encoding="utf-8") as f:
        for node in (1, 2, 3):
            f.write(json.dumps({"doc_id": "d1", "node": node}) + "\n")
    monkeypatch.setenv("RAG_VECTOR_STORE", str(d))
    vector_mod._cache.clear()
    from lawrag.core import embedding
    monkeypatch.setattr(embedding, "available", lambda: True)
    monkeypatch.setattr(embedding, "encode_one",
                        lambda q: np.array(qvec, dtype=np.float32))


# ---------------------------------------------------------------- 진입 제외
def test_진입제외는_auto_경로의_조립에서도_빠진다(tmp_path, monkeypatch):
    """예전엔 vecfirst 만 봤다 — 용어 사다리(assemble)는 그대로 데려왔다."""
    _iso(tmp_path, monkeypatch)
    idx = _index()
    _block_entry("d1", 3)
    res = SearchResult(query="벌칙", mode="정확", ladder=[], hits=[
        Hit(target="doc:d1:3", kind="제목", value="벌칙", score=1.0, match="정확",
            doc_id="d1", doc="A.pdf", node=3),
        Hit(target="doc:d1:1", kind="제목", value="총칙", score=0.9, match="정확",
            doc_id="d1", doc="A.pdf", node=1),
    ])
    secs = answer_mod.assemble(idx, res)
    assert [s.node for s in secs] == [1]              # 3 은 진입으로 안 온다


def test_진입제외는_검토_트랙의_벡터_진입에서도_빠진다(tmp_path, monkeypatch):
    from lawrag.core.casereview import pipeline

    _iso(tmp_path, monkeypatch)
    _arm_vector(tmp_path, monkeypatch, [0.6, 0.8])      # 구역 3 이 최근접
    idx = _index()
    _block_entry("d1", 3)
    secs = pipeline._vector_sections(idx, "벌칙", exclude=set(), topk=3)
    assert 3 not in [s.node for s in secs]
    assert secs                                          # 다른 구역은 온다


# ---------------------------------------------------------------- 질문 기억
def test_질문기억_활성은_두_경로_모두_진입_앞에_앉는다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _arm_vector(tmp_path, monkeypatch, [1.0, 0.0])      # 벡터는 구역 1
    idx = _index()
    tuples_mod.record_candidates("벌칙이 뭐야", [{"doc_id": "d1", "node": 3, "via": "벡터"}])
    # 잠정은 안 열린다
    assert promote.direct_hits("벌칙이 뭐야") == []
    assert promote.approve(tuples_mod.norm("벌칙이 뭐야"), "d1", 3, "맞는 착지")
    mem = promote.direct_hits("벌칙이 뭐야")
    assert [m["node"] for m in mem] == [3] and mem[0]["via"] == "질문 기억"

    # 벡터 경로 — seeds 가 첫 자리, 벡터 예산을 뺏지 않는다
    secs, meta = vecfirst.retrieve(idx, "벌칙이 뭐야", entry_k=1, seeds=mem)
    assert secs[0].kind == "질문 기억" and secs[0].node == 3
    assert any(s.kind == "벡터" and s.node == 1 for s in secs)
    assert len(meta["memory"]) == 1

    # auto 경로 — assemble 의 seeds 도 첫 자리
    res = SearchResult(query="벌칙이 뭐야", mode="정확", ladder=[], hits=[
        Hit(target="doc:d1:1", kind="제목", value="총칙", score=1.0, match="정확",
            doc_id="d1", doc="A.pdf", node=1)])
    secs = answer_mod.assemble(idx, res, seeds=mem)
    assert [(s.node, s.kind) for s in secs][:2] == [(3, "질문 기억"), (1, "제목")]


def test_질문기억은_진입제외를_받지_않는다(tmp_path, monkeypatch):
    """둘 다 사람의 결정이다 — 명시적 '이 질문엔 이 조문'이 이긴다."""
    _iso(tmp_path, monkeypatch)
    idx = _index()
    _block_entry("d1", 3)
    res = SearchResult(query="q", mode="없음", ladder=[], hits=[])
    secs = answer_mod.assemble(idx, res, seeds=[{"doc_id": "d1", "node": 3,
                                                 "via": "질문 기억", "why": "같은 질문"}])
    assert [s.node for s in secs] == [3]


# ---------------------------------------------------------------- 후순위
def test_후순위_간선은_바닥_동반에서도_뒤로_밀린다(tmp_path, monkeypatch):
    """expand_floor 가 먼저 돌아 cap 을 채우면 expand_refs 의 후순위는 관측되지
    않는다 — 바닥에서도 뒤로 밀어야 실제로 밀린다."""
    from lawrag.core.rag import expand as expand_mod

    _iso(tmp_path, monkeypatch)
    idx = _index()
    # 제1조 본문(블록 0)에 배제 간선 둘 — 2 와 3. 2 를 후순위로 민다.
    idx._refs = {"d1": [
        {"src": 1, "dst": 2, "surface": "제2조", "block": 0, "rel": "배제"},
        {"src": 1, "dst": 3, "surface": "제3조", "block": 0, "rel": "배제"},
    ]}
    verdicts.log("q1", "질문", [{"kind": "참조무관", "reason": "무관", "via": "참조",
                                "section": {"n": 2, "doc_id": "d1", "doc": "A",
                                            "node": 2, "path": "제2조"},
                                "ref_src": {"doc_id": "d1", "node": 1,
                                            "path": "제1조", "surface": "제2조"}}])
    verdicts.resolve_miss(verdicts.backlog()["misses"][0], "후순위", "넓다")
    assert verdicts.is_demoted("d1", 1, "d1", 2)

    seed = [Section(n=1, doc_id="d1", doc="A.pdf", node=1, path="제1조", page=1,
                    kind="벡터", matched="", text="")]
    # 자리가 하나뿐이면 후순위(2)가 아니라 3 이 앉는다
    out = expand_mod.expand_floor(idx, list(seed), cap=2)
    assert [s.node for s in out] == [1, 3]
    # 자리가 남으면 후순위도 온다 — 지운 게 아니다
    out = expand_mod.expand_floor(idx, list(seed), cap=3)
    assert [s.node for s in out] == [1, 3, 2]
    assert "후순위" in out[-1].matched


# ---------------------------------------------------------------- 용어 misses
def test_감사의_검색무관은_용어_misses_로_센다(tmp_path, monkeypatch):
    from lawrag.core.rag import audit as audit_mod

    _iso(tmp_path, monkeypatch)
    gl = tmp_path / "glossary.json"
    gl.write_text(json.dumps({"terms": [
        {"term": "벌칙", "key": "벌칙", "status": "활성", "surfaces": ["벌칙"],
         "hits": 0, "misses": 0, "occurrences": []}]}, ensure_ascii=False),
        encoding="utf-8")
    monkeypatch.setenv("GLOSSARY_STORE", str(gl))

    class LLM:
        log = []

        def structured(self, *a, **k):
            return {"findings": [{"n": 1, "kind": "검색무관", "reason": "무관"}]}

    secs = [Section(n=1, doc_id="d1", doc="A", node=3, path="제3조", page=2,
                    kind="용어", matched="승인 용어 '벌칙'", text="본문",
                    term_key="벌칙")]
    audit_mod._run_one({"llm": LLM(), "qid": "q1", "question": "질문",
                        "answer": "답", "sections": secs, "cited": set()})
    row = json.loads(gl.read_text(encoding="utf-8"))["terms"][0]
    assert row["misses"] == 1 and row["hits"] == 0


def test_용어_진입_구역은_term_key_를_들고_다닌다():
    """assemble 이 Hit(term:key)에서 키를 옮겨 적어야 실적이 용어 행에 쌓인다."""
    terms = [{"term": "벌칙", "key": "벌칙", "status": "활성", "surfaces": ["벌칙"],
              "occurrences": [{"doc_id": "d1", "node": 3, "via": "제목"}]}]
    idx = _index(terms)
    res = SearchResult(query="벌칙", mode="정확", ladder=[], hits=[
        Hit(target="term:벌칙", kind="용어", value="벌칙", score=1.0, match="정확",
            occurrences=terms[0]["occurrences"])])
    secs = answer_mod.assemble(idx, res)
    assert secs[0].kind == "용어" and secs[0].term_key == "벌칙"


# ---------------------------------------------------------------- 승격 원장 API
def test_승격_원장_승인은_API_로_닫힌다(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from lawrag.api.routers import rag as rag_router
    from lawrag.core.rag import index as index_mod
    from fastapi import FastAPI

    _iso(tmp_path, monkeypatch)
    idx = _index()
    monkeypatch.setattr(index_mod, "current", lambda: idx)
    app = FastAPI()
    app.include_router(rag_router.router)
    c = TestClient(app)

    tuples_mod.record_candidates("벌칙이 뭐야", [{"doc_id": "d1", "node": 3, "via": "벡터"}])
    r = c.get("/v1/rag/memory").json()
    assert r["counts"]["잠정"] == 1 and r["rows"][0]["doc"] == "A.pdf"
    assert r["rows"][0]["path"] and r["rows"][0]["exists"]
    # 백로그 배지에도 센다
    assert c.get("/v1/rag/verdicts").json()["memory_pending"] == 1

    qkey = r["rows"][0]["qkey"]
    # 없는 좌표는 승인 못 한다
    assert c.post("/v1/rag/memory/resolve", json={
        "qkey": qkey, "doc_id": "d1", "node": 99, "action": "승인"}).status_code == 400
    ok = c.post("/v1/rag/memory/resolve", json={
        "qkey": qkey, "doc_id": "d1", "node": 3, "action": "승인", "note": "맞다"})
    assert ok.status_code == 200 and ok.json()["status"] == "활성"
    assert [m["node"] for m in promote.direct_hits("벌칙이 뭐야")] == [3]
    # 기각 → tombstone, 직행에서 빠진다
    c.post("/v1/rag/memory/resolve", json={
        "qkey": qkey, "doc_id": "d1", "node": 3, "action": "기각"})
    assert promote.direct_hits("벌칙이 뭐야") == []
    assert c.get("/v1/rag/memory?status=tombstone").json()["count"] == 1
