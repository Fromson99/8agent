"""코퍼스 그래프 — 간선이 타입별로 서고, 걷기가 좌표를 되짚는지 시험한다."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag.graph import Graph                   # noqa: E402
from lawrag.core.rag.index import Index, norm             # noqa: E402


def _docs():
    a = ("d1", {"name": "KSB.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제2장",
         "title": "영업행위 준수사항", "page": 1, "span": [0, 3]},
        {"id": 2, "parent": 1, "level": 2, "surface": "제19조",
         "title": "설명의무", "page": 1, "span": [1, 2]},
        {"id": 3, "parent": 1, "level": 2, "surface": "제21조",
         "title": "부당권유행위 금지", "page": 2, "span": [2, 3]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제2장", "kind": "text"},
        {"idx": 1, "page": 1, "text": "설명의무 조문", "kind": "text"},
        {"idx": 2, "page": 2, "text": "부당권유 조문", "kind": "text"},
    ]})
    b = ("d2", {"name": "GUIDE.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "Ⅳ",
         "title": "설명의무", "page": 5, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 5, "text": "설명의무 이행 지침", "kind": "text"},
    ]})
    return [a, b]


def _graph(user_terms=None):
    return Graph.from_index(Index.from_docs(_docs(), user_terms or []))


def test_계층_간선():
    g = _graph()
    assert g.parent[("d1", 2)] == ("d1", 1)
    assert set(g.children[("d1", 1)]) == {("d1", 2), ("d1", 3)}
    assert g.siblings(("d1", 2)) == [("d1", 3)]


def test_출현_간선은_제목이_먼저():
    terms = [{"term": "설명의무", "key": norm("설명의무"), "occurrences": [
        {"doc_id": "d1", "node": 3, "via": "본문"}]}]     # 다른 구역의 언급
    g = _graph(terms)
    rows = g.sections_of(norm("설명의무"))
    vias = [via for _, via in rows]
    assert vias[0] == "제목" and "본문" in vias            # 다루는 자리가 앞선다


def test_브리지는_문서를_가로지른다():
    g = _graph()
    out = g.bridge(("d1", 2))                              # d1 의 설명의무 구역에서
    assert (("d2", 1), norm("설명의무")) in out            # d2 의 설명의무 구역으로
    assert all(sec[0] != "d1" for sec, _ in out)           # 같은 문서는 계층이 담당


def test_공유_용어와_지형도():
    g = _graph()
    shared = g.shared_terms()
    assert norm("설명의무") in shared                      # 두 문서에 걸친 용어
    t = g.terrain()
    assert {d["doc"] for d in t} == {"KSB.pdf", "GUIDE.pdf"}
    assert t[0]["sections"][0]["title"]                    # 최상위 구역 이름이 실린다
