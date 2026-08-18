"""벡터 우선 모드 — 진입·참조 닫힘·정적 출처의 계약을 시험한다.

모델 없이 돈다: 벡터 색인은 가짜 npz, 질의 임베딩은 monkeypatch,
참조 간선은 색인 캐시에 직접 심는다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import vecfirst, vector as vector_mod        # noqa: E402
from lawrag.core.rag.index import Index                           # noqa: E402


def _docs():
    """3개 구역: 1 → 2 → 3 으로 참조가 이어진다 (닫힘 시험용)."""
    nodes = [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "총칙", "page": 1, "span": [0, 1]},
        {"id": 2, "parent": None, "level": 1, "surface": "제2조",
         "title": "정의", "page": 1, "span": [1, 2]},
        {"id": 3, "parent": None, "level": 1, "surface": "제3조",
         "title": "벌칙", "page": 2, "span": [2, 3]},
    ]
    blocks = [
        {"idx": 0, "page": 1, "text": "제2조를 따른다", "kind": "text"},
        {"idx": 1, "page": 1, "text": "제3조를 참고한다", "kind": "text"},
        {"idx": 2, "page": 2, "text": "벌칙 조항이다", "kind": "text"},
    ]
    return [("d1", {"name": "A.pdf"}, {"nodes": nodes, "blocks": blocks})]


def _index_with_refs():
    idx = Index.from_docs(_docs())
    # 참조 간선을 직접 심는다 — refs 파서가 아니라 닫힘 로직을 시험한다
    idx._refs = {"d1": [
        {"src": 1, "dst": 2, "surface": "제2조", "block": 0},
        {"src": 2, "dst": 3, "surface": "제3조", "block": 1},
    ]}
    idx._cross = ([], [])
    return idx


def _arm_vector(tmp_path, monkeypatch, qvec):
    d = tmp_path / "sections"
    d.mkdir(parents=True)
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


def test_진입은_벡터_연결은_참조_닫힘(tmp_path, monkeypatch):
    _arm_vector(tmp_path, monkeypatch, [1.0, 0.0])      # 구역 1 에만 가깝다
    idx = _index_with_refs()
    sections, meta = vecfirst.retrieve(idx, "아무 질의", entry_k=1)
    kinds = [(s.node, s.kind) for s in sections]
    # 진입 1(벡터) → 1이 참조하는 2(참조) → 2가 참조하는 3(참조) — 닫힘
    assert kinds == [(1, "벡터"), (2, "참조"), (3, "참조")]
    assert meta["depth"] == 2
    assert [s.n for s in sections] == [1, 2, 3]          # 번호는 연속


def test_출처는_정적이다(tmp_path, monkeypatch):
    _arm_vector(tmp_path, monkeypatch, [1.0, 0.0])
    idx = _index_with_refs()
    sections, _ = vecfirst.retrieve(idx, "아무 질의", entry_k=1)
    refs = vecfirst.static_refs(sections)
    # LLM 없이도 출처 전부 — 좌표·경위·딥링크가 결정론으로 붙는다
    assert len(refs) == 3
    assert refs[0]["kind"] == "벡터" and "코사인" in refs[0]["matched"]
    assert refs[1]["kind"] == "참조" and refs[1]["link"].startswith("/structure/?doc=d1")


def test_벡터_미스면_빈손을_정직하게(tmp_path, monkeypatch):
    _arm_vector(tmp_path, monkeypatch, [0.1, 0.1])      # 전 구역 문턱 미달
    idx = _index_with_refs()
    sections, meta = vecfirst.retrieve(idx, "먼 질의")
    assert sections == [] and meta["entries"] == []


def test_상한을_지킨다(tmp_path, monkeypatch):
    _arm_vector(tmp_path, monkeypatch, [1.0, 0.0])
    idx = _index_with_refs()
    sections, _ = vecfirst.retrieve(idx, "아무 질의", entry_k=1, cap=2)
    assert len(sections) == 2                            # 진입 1 + 연결 1 에서 멈춘다


def test_승인_용어가_벡터보다_먼저_진입한다(tmp_path, monkeypatch):
    """전문 용어는 keyword 가 맞다 — 질의에 승인(활성) 용어가 통째로 있으면
    그 앵커가 벡터보다 앞선 정밀 진입이 된다. 벡터 자리는 뺏지 않는다."""
    _arm_vector(tmp_path, monkeypatch, [1.0, 0.0])       # 벡터는 구역 1 을 가리킨다
    docs = _docs()
    terms = [{"term": "벌칙", "key": "벌칙", "status": "활성",
              "surfaces": ["벌칙"],
              "occurrences": [{"doc_id": "d1", "node": 3, "via": "제목"}]}]
    idx = Index.from_docs(docs, terms)
    idx._refs = {"d1": []}
    idx._cross = ([], [])
    sections, meta = vecfirst.retrieve(idx, "벌칙 규정 알려줘", entry_k=1)
    assert sections[0].kind == "용어" and sections[0].node == 3
    assert "승인 용어" in sections[0].matched
    assert meta["keywords"][0]["용어"] == "벌칙"
    # 벡터 진입도 그대로 산다 — 용어가 자리를 뺏지 않는다
    assert any(s.kind == "벡터" and s.node == 1 for s in sections)
