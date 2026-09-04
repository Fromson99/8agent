"""하이브리드 검색 — 벡터 단의 계약을 시험한다.

모델은 부르지 않는다: 벡터 색인은 가짜 npz 로 만들고, 질의 임베딩은
monkeypatch 로 준다. 시험하는 것은 융합·강등·격리의 규율이다:
  · 용어 단(정확·부분)이 잡으면 벡터는 돌지 않는다
  · 렉시컬+벡터가 겹치면 RRF 융합, 벡터만 잡으면 kind=벡터 로 표시
  · 색인·모델이 없으면 렉시컬만 — 오늘까지의 동작 그대로
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import vector as vector_mod                  # noqa: E402
from lawrag.core.rag.index import Index                           # noqa: E402
from lawrag.core.rag.search import search                         # noqa: E402


def _docs():
    nodes = [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "설명의무", "page": 1, "span": [0, 1]},
        {"id": 2, "parent": None, "level": 1, "surface": "제2조",
         "title": "손해배상", "page": 2, "span": [1, 2]},
    ]
    blocks = [
        {"idx": 0, "page": 1, "text": "중요사항을 설명하여야 한다", "kind": "text"},
        {"idx": 1, "page": 2, "text": "손해를 배상할 책임이 있다", "kind": "text"},
    ]
    return [("d1", {"name": "A.pdf"}, {"nodes": nodes, "blocks": blocks})]


def _vector_store(tmp_path, monkeypatch, rows, vecs):
    d = tmp_path / "sections"
    d.mkdir(parents=True)
    np.savez_compressed(d / "vectors.npz", v=np.array(vecs, dtype=np.float16))
    with (d / "meta.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    monkeypatch.setenv("RAG_VECTOR_STORE", str(d))
    vector_mod._cache.clear()


def _fake_query_vec(monkeypatch, vec):
    from lawrag.core import embedding

    monkeypatch.setattr(embedding, "available", lambda: True)
    monkeypatch.setattr(embedding, "encode_one",
                        lambda q: np.array(vec, dtype=np.float32))


def test_용어가_잡으면_벡터는_돌지_않는다(tmp_path, monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(vector_mod, "search",
                        lambda q, topk=8: called.__setitem__("n", called["n"] + 1) or [])
    idx = Index.from_docs(_docs())
    r = search(idx, "설명의무가 뭐야")
    assert r.mode == "정확" and called["n"] == 0


def test_벡터만_잡으면_kind_벡터(tmp_path, monkeypatch):
    # 렉시컬이 전혀 못 잡는 질의 — 구역 2가 벡터로만 잡힌다
    _vector_store(tmp_path, monkeypatch,
                  [{"doc_id": "d1", "node": 1}, {"doc_id": "d1", "node": 2}],
                  [[1, 0], [0, 1]])
    _fake_query_vec(monkeypatch, [0.1, 0.995])
    idx = Index.from_docs(_docs())
    r = search(idx, "누가 물어주나요")          # 색인·본문에 없는 표현
    assert r.mode == "벡터"
    assert r.hits[0].kind == "벡터" and r.hits[0].node == 2
    assert any("코사인" in x for x in r.hits[0].reasons)


def test_렉시컬과_벡터가_겹치면_융합(tmp_path, monkeypatch):
    _vector_store(tmp_path, monkeypatch,
                  [{"doc_id": "d1", "node": 2}], [[0, 1]])
    _fake_query_vec(monkeypatch, [0.0, 1.0])
    idx = Index.from_docs(_docs())
    # "책임"은 제목 색인엔 없고(①② 미스) 블록 본문엔 있다 → ③에서 만난다
    r = search(idx, "책임 소재는?")
    assert r.mode == "하이브리드"
    top = r.hits[0]
    assert top.node == 2 and top.match == "하이브리드"
    assert any("키워드" in x for x in top.reasons)
    assert any("코사인" in x for x in top.reasons)


def test_색인이_없으면_렉시컬만(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_VECTOR_STORE", str(tmp_path / "없는곳"))
    vector_mod._cache.clear()
    idx = Index.from_docs(_docs())
    r = search(idx, "책임 소재는?")
    assert r.mode == "본문"                     # 오늘까지의 동작 그대로
    assert all(h.kind == "본문" for h in r.hits)


def test_모델이_꺼져_있으면_벡터_단은_빈손(tmp_path, monkeypatch):
    _vector_store(tmp_path, monkeypatch,
                  [{"doc_id": "d1", "node": 2}], [[0, 1]])
    monkeypatch.setenv("RAG_VECTOR", "0")
    assert vector_mod.search("아무거나") == []


def test_코사인_문턱_미달은_버린다(tmp_path, monkeypatch):
    _vector_store(tmp_path, monkeypatch,
                  [{"doc_id": "d1", "node": 1}], [[1, 0]])
    _fake_query_vec(monkeypatch, [0.3, 0.954])   # cos ≈ 0.3 < 0.45
    assert vector_mod.search("먼 질의") == []


def test_같은_질문의_좌표검색은_임베딩을_한번만_계산한다(tmp_path, monkeypatch):
    from lawrag.core import embedding

    _vector_store(tmp_path, monkeypatch,
                  [{"doc_id": "d1", "node": 1}, {"doc_id": "d1", "node": 2}],
                  [[1, 0], [0, 1]])
    called = {"n": 0}
    monkeypatch.setattr(embedding, "available", lambda: True)
    monkeypatch.setattr(
        embedding, "encode_one",
        lambda _q: called.__setitem__("n", called["n"] + 1)
        or np.array([1.0, 0.0], dtype=np.float32),
    )

    vector_mod.search("같은 질문", coordinates=frozenset({("d1", 1)}))
    vector_mod.search("같은 질문", coordinates=frozenset({("d1", 2)}))

    assert called["n"] == 1
