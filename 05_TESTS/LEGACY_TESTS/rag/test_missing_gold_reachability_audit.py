from scripts import rag_missing_gold_reachability_audit as audit


def test_query_builder_has_no_gold_input_and_uses_frozen_trace():
    arm68 = {
        "llm_calls": [{
            "kind": "rag.legalclosure.recall_first_planner",
            "structured_output": {
                "exact_query": "채무조정 절차",
                "keywords": ["채무조정", "절차"],
                "operation_terms": ["채무조정"],
            },
        }],
        "retrieval_meta": {"actions": []},
    }
    arm67 = {"retrieval_meta": {"actions": [{
        "kind": "keyword_search", "query": "채무조정 신청",
        "keywords": ["신청"],
    }]}}
    variants = audit.build_query_variants(
        "채무를 줄일 수 있나", ["채무"], arm68, arm67)
    assert any(row["query"] == "채무조정 절차" for row in variants["phrases"])
    assert any(row["terms"] == ["채무조정", "절차"]
               for row in variants["term_sets"])


def test_rank_helpers_dedupe_documents():
    ranked = [("a", 1), ("a", 2), ("b", 3)]
    assert audit.rank_coordinate(ranked, ("a", 2)) == 2
    assert audit.rank_document(ranked, "b") == 2
    assert audit.rank_coordinate(ranked, ("c", 4)) is None


def test_classification_prioritizes_direct_rank():
    matrix = {
        "exact": [{"article_rank": 12, "document_rank": 1}],
        "keyword": [], "assertion": [], "vector": [],
        "relations": {
            "selected_seed_policy": {"depth": 1},
            "observed_seed_raw": {"depth": 1},
        },
    }
    assert audit.classify_reachability(matrix) == "direct-top20-cap"


def test_classification_relation_and_document_only():
    relation = {
        "exact": [], "keyword": [], "assertion": [], "vector": [],
        "relations": {
            "selected_seed_policy": {"depth": None},
            "observed_seed_raw": {"depth": 2},
        },
    }
    assert audit.classify_reachability(relation) == "relation-only"
    document = {
        "exact": [{"article_rank": None, "document_rank": 3}],
        "keyword": [], "assertion": [], "vector": [], "relations": {},
    }
    assert audit.classify_reachability(document) == "document-reachable-article-miss"
