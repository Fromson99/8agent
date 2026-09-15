"""LLM 검색어 추출 + 일반 본문 검색의 독립 계약."""

from lawrag.core.rag import answer as answer_mod
from lawrag.core.rag.general_search import (
    extract_keywords,
    fuse_with_registered,
    search_keywords,
    search_question,
)
from lawrag.core.rag.index import Index
from lawrag.core.rag.search import search as registered_search


def _index():
    return Index.from_docs([
        ("sales", {"name": "금융소비자보호법"}, {
            "nodes": [
                {"id": 1, "parent": None, "level": 1, "surface": "제19조",
                 "title": "설명의무", "page": 1, "span": [0, 2]},
                {"id": 2, "parent": None, "level": 1, "surface": "제21조",
                 "title": "부당권유행위 금지", "page": 2, "span": [2, 3]},
            ],
            "blocks": [
                {"idx": 0, "page": 1, "text": "금융상품판매업자는 계약 전에 중요한 사항을",
                 "kind": "text"},
                {"idx": 1, "page": 1, "text": "소비자가 이해할 수 있도록 설명하여야 한다.",
                 "kind": "text"},
                {"idx": 2, "page": 2, "text": "단정적 판단을 제공하는 행위를 해서는 안 된다.",
                 "kind": "text"},
            ],
        }),
        ("research", {"name": "금융투자업규정"}, {
            "nodes": [
                {"id": 7, "parent": None, "level": 1, "surface": "제7조",
                 "title": "조사분석자료", "page": 3, "span": [0, 1]},
            ],
            "blocks": [
                {"idx": 0, "page": 3,
                 "text": "조사분석자료 작성을 담당하는 자에게 성과보수를 지급하는 행위",
                 "kind": "text"},
            ],
        }),
        ("unrelated", {"name": "문서관리지침"}, {
            "nodes": [
                {"id": 9, "parent": None, "level": 1, "surface": "제9조",
                 "title": "보존", "page": 1, "span": [0, 1]},
            ],
            "blocks": [{"idx": 0, "page": 1, "text": "문서를 5년간 보존한다.",
                        "kind": "text"}],
        }),
    ])


class _LLM:
    def __init__(self, keywords):
        self.keywords = keywords
        self.calls = []

    def structured(self, kind, system, user, schema, **kwargs):
        self.calls.append((kind, system, user, schema, kwargs))
        return {"keywords": self.keywords}


def test_llm_extracts_and_sanitizes_keywords():
    llm = _LLM(["소비자", " 설명하다 ", "소비자", "", "?"])
    plan = extract_keywords(llm, "상품을 팔 때 뭐를 설명해야 해?")

    assert list(plan.keywords) == ["소비자", "설명하다"]
    assert plan.via == "llm"
    assert llm.calls[0][0] == "rag.general_search.keywords"
    assert "[질문]" in llm.calls[0][2]


def test_general_search_finds_unregistered_body_terms_and_ranks_coverage():
    # 용어집은 비어 있다. 두 검색어가 모두 든 조문이 하나만 든 문서보다 위다.
    result = search_keywords(_index(), ["소비자", "설명"], question="q")

    assert result.hits
    assert (result.hits[0].doc_id, result.hits[0].node) == ("sales", 1)
    assert result.hits[0].matched == ("소비자", "설명")
    assert result.documents[0]["doc"] == "금융소비자보호법"


def test_prefix_matching_handles_korean_particles():
    result = search_keywords(_index(), ["성과보수", "지급"])

    assert result.hits[0].doc_id == "research"
    assert set(result.hits[0].matched) == {"성과보수", "지급"}


def test_hallucinated_keyword_is_reported_but_real_hit_survives():
    result = search_keywords(_index(), ["설명", "세상에없는검색어"])

    assert result.hits[0].doc_id == "sales"
    assert result.unmatched == ["세상에없는검색어"]


def test_scope_is_respected():
    scoped = _index().scoped({"research"}, name="리서치")
    result = search_keywords(scoped, ["설명", "성과보수"])

    assert {hit.doc_id for hit in result.hits} == {"research"}
    assert result.unmatched == ["설명"]


def test_question_flow_and_existing_assembler_adapter():
    llm = _LLM(["성과보수", "지급", "없는법령"])
    idx = _index()
    result = search_question(idx, "애널리스트에게 성과급 줘도 돼?", llm)
    sections = answer_mod.assemble(idx, result.as_search_result())

    assert result.extractor == "llm"
    assert result.unmatched == ["없는법령"]
    assert sections[0].kind == "일반검색"
    assert (sections[0].doc_id, sections[0].node) == ("research", 7)
    assert "성과보수" in sections[0].matched


def test_no_llm_falls_back_without_crashing():
    result = search_question(_index(), "성과보수 지급 알려줘", None)

    assert result.extractor == "fallback"
    assert result.hits[0].doc_id == "research"
    assert "알려줘" not in result.keywords


def test_hybrid_rrf_promotes_overlap_and_keeps_general_only_hit():
    idx = _index()
    registered = registered_search(idx, "설명의무 성과보수")
    general = search_keywords(idx, ["설명의무", "소비자", "성과보수"])

    hits = fuse_with_registered(idx, registered, general)

    assert hits[0]["doc_id"] == "sales"
    assert hits[0]["channels"] == ["역매칭", "일반검색"]
    assert any(hit["doc_id"] == "research" and "일반검색" in hit["channels"]
               for hit in hits)


def test_api_router_is_installed_without_touching_main_rag_router():
    from lawrag.api.structure_app import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}
    for included in (route for route in app.routes
                     if hasattr(route, "original_router")):
        paths.update(route.path for route in included.original_router.routes
                     if hasattr(route, "path"))
    assert "/v1/rag/general-search" in paths
    assert "/v1/rag/hybrid-search" in paths


def test_hybrid_api_returns_both_channels(monkeypatch):
    from lawrag.api.routers import general_search as api

    idx = _index()
    monkeypatch.setattr(api.index_mod, "current", lambda: idx)
    monkeypatch.setattr(api.scopes_mod, "apply",
                        lambda index, _scope, _documents: (index, {"missing": []}))
    monkeypatch.setattr(api, "_llm", lambda: _LLM(["설명의무", "소비자"]))
    monkeypatch.setattr(api.logbook, "rag_event", lambda *_args, **_kwargs: None)

    out = api.hybrid_search(api.GeneralSearchRequest(
        question="설명의무는 어디 있어?", limit=5))

    assert out["mode"] == "역매칭+일반검색"
    assert out["registered"]["hits"]
    assert out["general"]["documents"][0]["doc_id"] == "sales"
    assert out["hits"][0]["channels"] == ["역매칭", "일반검색"]
