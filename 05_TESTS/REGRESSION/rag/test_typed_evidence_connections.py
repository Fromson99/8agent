from types import SimpleNamespace

from lawrag.research.experiments import typed_evidence_connections as typed


class _Index:
    def __init__(self):
        view = SimpleNamespace(by_id={
            1: {"id": 1, "parent": None, "family": "kr_article", "surface": "제1조"},
            2: {"id": 2, "parent": 1, "family": "kr_clause", "surface": "제1항"},
            10: {"id": 10, "parent": None, "family": "kr_article", "surface": "제2조"},
            11: {"id": 11, "parent": 10, "family": "kr_clause", "surface": "제1항"},
            20: {"id": 20, "parent": None, "family": "kr_article", "surface": "제3조"},
        })
        self.docs = {"D": view}

    def ref_edges(self):
        return {"D": [{"src": 2, "dst": 11, "rel": "배제",
                        "surface": "제2조에도 불구하고"}]}

    def cross_from(self, _doc_id):
        return []


def test_explicit_typed_edge_is_eligible_but_parallel_search_hit_is_not():
    evidence = [
        {"id": "E1", "doc_id": "D", "node": 1, "document": "A법",
         "path": "제1조", "role": "exact-structural"},
        {"id": "E2", "doc_id": "D", "node": 10, "document": "A법",
         "path": "제2조", "role": "assertion-tree"},
        {"id": "E3", "doc_id": "D", "node": 20, "document": "A법",
         "path": "제3조", "role": "keyword-bm25"},
    ]
    result = typed.typed_connections(_Index(), "요건은?", evidence)
    assert result["E1"]["conclusion_eligible"]
    assert result["E2"]["connection_role"] == "direct_typed_companion"
    assert result["E2"]["direct_relations"] == ["배제"]
    assert result["E2"]["conclusion_eligible"]
    assert result["E3"]["connection_role"] == "parallel_search_context"
    assert not result["E3"]["conclusion_eligible"]


def test_enclosing_article_lifts_clause_endpoint():
    index = _Index()
    assert typed.enclosing_article(index.docs["D"], 2) == 1
    assert typed.enclosing_article(index.docs["D"], 11) == 10


def test_title_aligned_keyword_hit_is_support_candidate_not_governing():
    evidence = [
        {"id": "E1", "doc_id": "D", "node": 1, "document": "A법",
         "path": "제1조", "role": "exact-structural"},
        {"id": "E3", "doc_id": "D", "node": 20, "document": "A법",
         "path": "제3조 상장주선인의 의무", "role": "keyword-bm25"},
    ]
    result = typed.typed_connections(
        _Index(), "상장주선인의 의무인수 기간은?", evidence)
    assert not result["E3"]["conclusion_eligible"]
    assert result["E3"]["support_eligible"]
    assert result["E3"]["evidence_tier"] == "B_candidate_support"
    assert result["E3"]["support_reasons"] == ["issue_title_alignment"]


def test_supplemental_title_match_stays_context_only():
    evidence = [
        {"id": "E1", "doc_id": "D", "node": 1, "document": "A법",
         "path": "제1조", "role": "exact-structural"},
        {"id": "E3", "doc_id": "D", "node": 20, "document": "A법",
         "path": "제3조 상장주선인의 의무", "role": "supplemental-closure"},
    ]
    result = typed.typed_connections(
        _Index(), "상장주선인의 의무인수 기간은?", evidence)
    assert result["E3"]["evidence_tier"] == "C_context_only"
    assert not result["E3"]["support_eligible"]


class _PairIndex:
    def __init__(self):
        view = SimpleNamespace(by_id={
            1: {"id": 1, "parent": None, "family": "kr_article",
                "surface": "제1조", "title": "별도 규정"},
            10: {"id": 10, "parent": None, "family": "kr_article",
                 "surface": "제415조", "title": "준용규정"},
            20: {"id": 20, "parent": None, "family": "kr_article",
                 "surface": "제388조", "title": "이사의 보수"},
        })
        self.docs = {"D": view}

    def ref_edges(self):
        return {"D": [{"src": 10, "dst": 20, "rel": "인용",
                        "surface": "제388조"}]}

    def cross_from(self, _doc_id):
        return []


def test_non_seed_selected_pair_recovers_junyong_from_article_title():
    evidence = [
        {"id": "E1", "doc_id": "D", "node": 1, "document": "상법",
         "path": "제1조", "role": "exact-structural"},
        {"id": "E2", "doc_id": "D", "node": 10, "document": "상법",
         "path": "제415조 준용규정", "role": "assertion-tree"},
        {"id": "E3", "doc_id": "D", "node": 20, "document": "상법",
         "path": "제388조 이사의 보수", "role": "keyword-bm25"},
    ]
    result = typed.typed_connections(
        _PairIndex(), "감사의 보수는 누가 정하는가?", evidence)
    assert result["E2"]["connection_role"] == "selected_pair_typed_context"
    assert result["E3"]["connection_role"] == "selected_pair_typed_context"
    assert result["E2"]["incident_relations"] == ["준용"]
    assert result["E2"]["support_reasons"] == ["structural_retrieval"]
    assert not result["E2"]["conclusion_eligible"]
    assert result["E2"]["support_eligible"]
