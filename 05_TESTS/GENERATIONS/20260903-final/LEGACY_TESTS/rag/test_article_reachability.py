from __future__ import annotations

import json
from types import SimpleNamespace

from lawrag.core.rag import article_reachability, legalclosure, termexplore
from lawrag.core.rag.answer import Section
from lawrag.core.rag.index import Index


def _index():
    return Index.from_docs([("d", {"name": "시험법", "kind": "law"}, {
        "nodes": [
            {"id": node, "parent": None, "level": 1,
             "surface": f"제{node}조", "title": f"제목{node}",
             "span": [node - 1, node]}
            for node in range(1, 7)
        ],
        "blocks": [
            {"idx": node - 1, "text": f"제{node}조 본문", "kind": "text"}
            for node in range(1, 7)
        ],
    })])


def _branch(index, node, origin):
    return termexplore._branch(index, "d", node, (), origin=origin)


def test_trace_is_gold_free_and_offline_grade_separates_article_fates():
    index = _index()
    trace = article_reachability.ArticleReachabilityTrace(index, "case-1")
    primary = [_branch(index, 1, "exact")]
    assertion = [_branch(index, 3, "assertion")]
    keyword = [_branch(index, 4, "keyword")]
    closure = [_branch(index, 5, "relation")]
    selected = [primary[0], assertion[0], closure[0]]

    capture = legalclosure._trace_reachability(
        trace,
        primary_meta={
            "term_plan": {"rejected": [], "rejected_operation_terms": []},
            "structure": {"unresolved_locators": []},
            "selected_documents": [{"doc_id": "d"}],
            "routed_candidates": [
                {"doc_id": "d", "node": 1, "terms": ["원칙"]},
                {"doc_id": "d", "node": 2, "terms": ["조건"]},
            ],
            "review_candidates": [
                {"doc_id": "d", "node": 1, "mandatory": True},
                {"doc_id": "d", "node": 2, "mandatory": False},
            ],
        },
        primary_channel=primary,
        assertion_meta={
            "candidate_range_rows": [
                {"doc_id": "d", "node": 3, "strength": 7, "signals": ["책임"]}
            ],
            "assertion_hit_rows": [],
        },
        assertion_channel=assertion,
        keyword_meta={
            "ranked_article_candidates": [{
                "doc_id": "d", "node": 4, "rank": 1,
                "selected": True, "reason_code": "selected",
                "max_score": 2.0, "matched": ["절차"],
            }],
            "raw_hit_attempts": [],
        },
        keyword_channel=keyword,
        expansion_meta={
            "candidate_rows": [{
                "doc_id": "d", "node": 5, "rank": 1,
                "selected": True, "reason_code": "selected",
                "mandatory": True, "origin": "relation:outgoing:준용",
                "source_doc_id": "d", "source_node": 1,
            }],
            "lifecycle": [],
        },
        closure_channel=closure,
        reference_meta={"candidates": [], "fallback": "not_applicable"},
        reference_channel=[],
        definition_dropped=[],
        selected=selected,
    )

    article_reachability.validate_capture(capture)
    serialized = json.dumps(capture, ensure_ascii=False)
    assert "expected_articles" not in serialized
    assert "gold_total" not in serialized

    graded = article_reachability.grade_capture(
        capture, [("d", 1), ("d", 2), ("d", 5), ("d", 6)])
    fates = {row["identity"]["node"]: row for row in graded["article_fates"]}

    assert fates[1]["fate"] == "PRESENTED"
    assert fates[2]["fate"] == "GENERATED_NOT_SELECTED"
    assert fates[5]["first_touch"] == "D_CLOSURE"
    assert fates[5]["fate"] == "PRESENTED"
    assert fates[6]["fate"] == "NOT_GENERATED"
    assert graded["channels"]["A_EXACT"]["raw_gold_hits"] == 2
    assert graded["channels"]["D_CLOSURE"]["selected_gold_hits"] == 1
    assert graded["channels"]["D_CLOSURE"]["unique_contribution"] == 1


def test_trace_stage_discard_receipts_cover_every_lost_coordinate():
    index = _index()
    trace = article_reachability.ArticleReachabilityTrace(index, "case-2")
    trace.stage("query-source", "source", [])
    trace.stage("a-exact-retrieve", "retrieve", [("d", 1), ("d", 2)],
                parent_stage_ids=("query-source",))
    stage = trace.stage(
        "a-exact-select", "select", [("d", 1)],
        parent_stage_ids=("a-exact-retrieve",),
        discard_reasons={("d", 2): "article_not_selected"})

    assert stage["discarded"] == [{"doc_id": "d", "node": 2}]
    assert stage["discard_receipts"] == [{
        "identity": {"doc_id": "d", "node": 2},
        "reason": "article_not_selected",
    }]


def test_trace_on_off_does_not_change_legalclosure_selected_coordinates(monkeypatch):
    index = _index().scoped(None)

    def primary(_index, _question, *, llm, cap):
        section = Section(
            n=0, doc_id="d", doc="시험법", node=1, path="제1조",
            page=None, kind="구조적용어탐색", matched="정확용어", text="본문")
        return [section], {
            "term_plan": {"used_terms": ["본문"], "rejected": [],
                          "rejected_operation_terms": []},
            "structure": {"unresolved_locators": []},
            "selected_documents": [{"doc_id": "d"}],
            "routed_candidates": [{"doc_id": "d", "node": 1,
                                   "terms": ["본문"]}],
            "review_candidates": [{"doc_id": "d", "node": 1,
                                    "mandatory": True}],
        }

    keyword_branch = _branch(index, 2, "keyword-bm25")
    closure_branch = _branch(index, 3, "relation:outgoing:준용")
    monkeypatch.setattr(legalclosure.termexplore, "retrieve", primary)
    monkeypatch.setattr(legalclosure, "_assertion_channel",
                        lambda *args, **kwargs: ([], {
                            "candidate_range_rows": [],
                            "assertion_hit_rows": [],
                            "fallback": "canonical 표현과 확정 구조 후보 없음",
                        }))
    monkeypatch.setattr(legalclosure.general_search, "extract_keywords",
                        lambda *_args: SimpleNamespace(as_dict=lambda: {}))
    monkeypatch.setattr(legalclosure, "_keyword_articles",
                        lambda *args: ([keyword_branch], {
                            "ranked_article_candidates": [{
                                "doc_id": "d", "node": 2, "rank": 1,
                                "selected": True, "reason_code": "selected",
                                "max_score": 1.0, "matched": ["본문"],
                            }],
                            "raw_hit_attempts": [], "keywords": ["본문"],
                        }))
    monkeypatch.setattr(legalclosure, "_supplemental_closure",
                        lambda *args: ([closure_branch], {
                            "candidate_rows": [{
                                "doc_id": "d", "node": 3, "rank": 1,
                                "selected": True, "reason_code": "selected",
                                "mandatory": False,
                                "origin": "relation:outgoing:준용",
                            }],
                            "lifecycle": [],
                        }))

    plain, _ = legalclosure.retrieve(index, "본문 질문", object(), llm=None)
    trace = article_reachability.ArticleReachabilityTrace(index, "fixture")
    traced, meta = legalclosure.retrieve(
        index, "본문 질문", object(), llm=None, reachability_trace=trace)

    assert [(row.doc_id, row.node) for row in plain] == [
        (row.doc_id, row.node) for row in traced]
    article_reachability.validate_capture(meta["article_reachability"])
