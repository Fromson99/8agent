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
        # 제목을 '정의'로 두면 정의 동반(floor_definition)이 참조 닫힘보다
        # 먼저 물어가 이 시험의 과녁(닫힘)이 흐려진다 — 중립 제목으로 둔다.
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
    assert meta["counts"] == {
        "combination": 0, "concept": 0, "memory": 0, "keyword": 0, "frame": 0,
        "vector": 1, "floor": 0, "doc_companion": 0, "final": 3,
        "shared_cap": 12, "over_shared_cap": False,
    }


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


def test_문서_동반은_밖인용이_적은_문서만_태운다(monkeypatch, tmp_path):
    """착지 문서의 밖 인용 전부를 동반 — 단 게이트(≤FANOUT) 안의 문서만.

    참조 닫힘은 착지 마디에서만 출발하므로, 인용 마디가 착지하지 않으면 확정
    간선이 있어도 못 탄다(실측 2026-08-20 t3-16). 실무문서(밖 인용 한 자릿수)의
    처방이고, 법령(수백~1,795)은 게이트가 배제한다."""
    monkeypatch.setenv("STRUCTURE_STORE", str(tmp_path))
    caller = ("c1", {"name": "모범기준.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "체크리스트", "page": 1, "span": [0, 1]},
        {"id": 2, "parent": None, "level": 1, "surface": "제2조",
         "title": "배경", "page": 1, "span": [1, 2]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "실사 항목을 정한다", "kind": "text"},
        {"idx": 1, "page": 1, "text": "자본시장법 제125조에 따른다", "kind": "text"},
    ]})
    law = ("c2", {"name": "자본시장법.pdf"}, {"nodes": [
        {"id": 9, "parent": None, "level": 1, "surface": "제125조",
         "title": "배상책임", "page": 1, "span": [0, 1]},
    ], "blocks": [{"idx": 0, "page": 1, "text": "배상책임을 진다", "kind": "text"}]})
    idx = Index.from_docs([caller, law])
    idx._cross = ([{"src_doc": "c1", "src": 2, "dst_doc": "c2", "dst": 9,
                    "surface": "제125조", "hint": "자본시장법", "block": 1,
                    "via": "선언", "rel": "인용"}], [])
    # 진입은 체크리스트 마디(1)만 — 인용 마디(2)는 착지하지 않는다
    monkeypatch.setattr(vecfirst.vector_mod, "search",
                        lambda *a, **k: [("c1", 1, 0.9)])
    sections, meta = vecfirst.retrieve(idx, "실사 기준?")
    dc = [s for s in sections if s.kind == "문서 동반"]
    assert dc and dc[0].doc_id == "c2" and dc[0].node == 9, \
        [(s.kind, s.doc_id, s.node) for s in sections]
    assert dc[0].is_companion, "ref_src 가 있어야 스코프 밖에서도 표식으로 남는다"
    assert meta["doc_companion"] == [{"src": "c1", "doc_id": "c2", "node": 9}]
    assert meta["counts"]["doc_companion"] == 1
    assert meta["counts"]["final"] == len(sections)

    # 게이트 — 밖 인용이 문턱을 넘는 문서는 안 태운다
    monkeypatch.setattr(vecfirst, "DOC_COMPANION_FANOUT", 0)
    sections2, meta2 = vecfirst.retrieve(idx, "실사 기준?")
    assert not [s for s in sections2 if s.kind == "문서 동반"], meta2

    # 스위치 — 끄면 돌지 않는다
    monkeypatch.setattr(vecfirst, "DOC_COMPANION_FANOUT", 20)
    from lawrag.core.rag import switches
    switches.set_switch("doc_companion", False)
    try:
        sections3, _ = vecfirst.retrieve(idx, "실사 기준?")
        assert not [s for s in sections3 if s.kind == "문서 동반"]
    finally:
        switches.set_switch("doc_companion", True)


def test_좌표교집합이_잠기면_문서전체_동반은_생략한다(monkeypatch):
    from lawrag.core.rag import conceptfirst
    from lawrag.core.rag.answer import Section

    caller = ("c1", {"name": "정확한법"}, {"nodes": [{
        "id": 1, "parent": None, "level": 1, "surface": "제1조",
        "title": "정답", "page": 1, "span": [0, 1],
    }], "blocks": [{"idx": 0, "page": 1, "node": 1,
                     "text": "정확한 본문", "kind": "text"}]})
    companion = ("c2", {"name": "동반법"}, {"nodes": [{
        "id": 9, "parent": None, "level": 1, "surface": "제9조",
        "title": "넓은 인용", "page": 1, "span": [0, 1],
    }], "blocks": [{"idx": 0, "page": 1, "node": 9,
                     "text": "문서 전체 동반 후보", "kind": "text"}]})
    idx = Index.from_docs([caller, companion])
    idx._refs = {"c1": [], "c2": []}
    idx._cross = ([{"src_doc": "c1", "src": 1, "dst_doc": "c2", "dst": 9,
                    "surface": "제9조", "rel": "인용"}], [])
    exact = Section(n=0, doc_id="c1", doc="정확한법", node=1, path="제1조",
                    page=1, kind="교집합", matched="정확 좌표", text="정확한 본문")
    monkeypatch.setattr(
        conceptfirst, "retrieve",
        lambda *_a, **_k: ([exact], {"strategy": "coordinate_intersection"}),
    )
    monkeypatch.setattr(
        vecfirst.vector_mod, "search",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("좌표 잠금 뒤 Vector를 호출함")),
    )

    sections, meta = vecfirst.retrieve(idx, "정확한법 제1조 질문", raw_query="질문")

    assert not [section for section in sections if section.kind == "문서 동반"]
    assert meta["entry_policy"] == "coordinate-intersection-only"
    assert meta["doc_companion"] == []


def test_후보조합이_성공하면_운영_rag를_좌표잠금한다(monkeypatch):
    from lawrag.core.rag import combinations, conceptfirst
    from lawrag.core.rag.answer import Section

    idx = Index.from_docs([("d1", {"name": "시험법"}, {
        "nodes": [{"id": 1, "parent": None, "level": 1,
                   "surface": "제1조", "title": "정답", "span": [0, 1]}],
        "blocks": [{"idx": 0, "text": "정답 본문", "kind": "text"}],
    })])
    idx._refs = {"d1": []}
    idx._cross = ([], [])
    exact = Section(n=0, doc_id="d1", doc="시험법", node=1, path="제1조 정답",
                    page=None, kind="조합선택", matched="키워드+구조", text="정답 본문")
    monkeypatch.setattr(conceptfirst, "_registry", lambda _path: object())
    monkeypatch.setattr(
        combinations, "retrieve",
        lambda *_a, **_k: ([exact], {
            "strategy": "structure_constrained_lazy_tree", "option_count": 3,
            "combination_counts": {"zero_intersections": 7, "surviving": 2},
        }),
    )
    monkeypatch.setattr(
        conceptfirst, "retrieve",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("조합 성공 뒤 기존 단일해석 경로를 다시 호출함")),
    )
    monkeypatch.setattr(
        vecfirst.vector_mod, "search",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("조합 성공 뒤 전역 Vector를 호출함")),
    )

    class _StructuredLLM:
        def structured(self, *_args, **_kwargs):
            return {}

    sections, meta = vecfirst.retrieve(
        idx, "확장 질의", llm=_StructuredLLM(), raw_query="원 질문")

    assert [(row.kind, row.node) for row in sections] == [("조합선택", 1)]
    assert meta["entry_policy"] == "structure-constrained-lazy-tree-only"
    assert meta["combination_hits"][0]["node"] == 1
    assert meta["counts"]["combination"] == 1


def test_지연트리가_빈손이어도_운영질의는_옛_진입채널로_우회하지_않는다(monkeypatch):
    from lawrag.core.rag import assertionfirst, conceptfirst, framequery, switches

    idx = Index.from_docs([("d1", {"name": "시험법"}, {
        "nodes": [{"id": 1, "parent": None, "level": 1,
                   "surface": "제1조", "title": "정답", "span": [0, 1]}],
        "blocks": [{"idx": 0, "text": "정답 본문", "kind": "text"}],
    })])
    idx._refs = {"d1": []}
    idx._cross = ([], [])
    monkeypatch.setattr(conceptfirst, "_registry", lambda _path: object())
    original_switch = switches.is_on
    monkeypatch.setattr(
        switches, "is_on",
        lambda key: True if key == "assertion_tree_entry" else original_switch(key))
    monkeypatch.setattr(
        assertionfirst, "retrieve",
        lambda *_a, **_k: ([], {
            "strategy": "assertion_first_structural_navigation",
            "fallback": "선택 없음",
        }),
    )
    monkeypatch.setattr(
        conceptfirst, "retrieve",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("지연 트리 빈손 뒤 옛 Concept 경로를 호출함")),
    )
    monkeypatch.setattr(
        vecfirst.vector_mod, "search",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("지연 트리 빈손 뒤 전역 Vector를 호출함")),
    )
    monkeypatch.setattr(
        framequery, "lex_hits",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("지연 트리 빈손 뒤 옛 Frame 경로를 호출함")),
    )

    class _StructuredLLM:
        def structured(self, *_args, **_kwargs):
            return {}

    sections, meta = vecfirst.retrieve(
        idx, "확장 질의", llm=_StructuredLLM(), raw_query="원 질문")

    assert sections == []
    assert meta["entry_policy"] == "assertion-first-structural-navigation-only"
    assert meta["counts"]["concept"] == 0
    assert meta["counts"]["vector"] == 0
    assert meta["counts"]["frame"] == 0


def test_지연트리_선택뒤에는_선택하지_않은_후단확장을_섞지_않는다(monkeypatch):
    from lawrag.core.rag import answer, assertionfirst, conceptfirst, expand, switches
    from lawrag.core.rag.answer import Section

    idx = Index.from_docs([("d1", {"name": "시험법"}, {
        "nodes": [{"id": 1, "parent": None, "level": 1,
                   "surface": "제1조", "title": "선택 조문", "span": [0, 1]}],
        "blocks": [{"idx": 0, "text": "선택 본문", "kind": "text"}],
    })])
    idx._refs = {"d1": []}
    idx._cross = ([], [])
    chosen = Section(
        n=0, doc_id="d1", doc="시험법", node=1, path="제1조 선택 조문",
        page=None, kind="지연트리선택", matched="R1", text="선택 본문")
    monkeypatch.setattr(conceptfirst, "_registry", lambda _path: object())
    original_switch = switches.is_on
    monkeypatch.setattr(
        switches, "is_on",
        lambda key: True if key == "assertion_tree_entry" else original_switch(key))
    monkeypatch.setattr(
        assertionfirst, "retrieve",
        lambda *_a, **_k: ([chosen], {
            "strategy": "assertion_first_structural_navigation",
            "selected": [{"doc_id": "d1", "node": 1}],
        }),
    )
    monkeypatch.setattr(
        expand, "expand_floor",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("지연 트리 선택 뒤 결정론 바닥을 확장함")),
    )
    monkeypatch.setattr(
        answer, "expand_refs",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("지연 트리 선택 뒤 참조 닫힘을 확장함")),
    )
    monkeypatch.setattr(
        expand, "navigate",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("지연 트리 선택 뒤 LLM 항해를 실행함")),
    )

    class _StructuredLLM:
        def structured(self, *_args, **_kwargs):
            return {}

    sections, meta = vecfirst.retrieve(
        idx, "확장 질의", llm=_StructuredLLM(), raw_query="원 질문")

    assert [(s.kind, s.node) for s in sections] == [("지연트리선택", 1)]
    assert meta["floor"] == []
    assert meta["depth"] == 0
    assert "nav" not in meta
    assert meta["counts"]["final"] == 1
