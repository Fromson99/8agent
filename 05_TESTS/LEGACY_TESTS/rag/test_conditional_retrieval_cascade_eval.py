from scripts import rag_conditional_retrieval_cascade_eval as evaluate


def _row(scope="resolved-structure", unresolved=None, family=10, broad=20,
         family_hit=True, broad_hit=True):
    return {
        "case_no": "cm-x", "scope_kind": scope,
        "unresolved_locators": unresolved or [],
        "policies": {
            "family_top8": {"candidate_coordinates": family, "hierarchy": {
                "documents": 2, "selection_roots": 3,
                "lossless_pages_upper_bound": 1}},
            "broad_or": {"candidate_coordinates": broad, "hierarchy": {
                "documents": 8, "selection_roots": 9,
                "lossless_pages_upper_bound": 2}},
        },
        "gold": [{"policy_hits": {"family_top8": family_hit,
                                   "broad_or": broad_hit}}],
    }


def test_resolved_scope_uses_family_route():
    item = evaluate.cascade_row(_row())
    assert item["route"] == "family_top8"
    assert item["candidate_coordinates"] == 10


def test_missing_scope_fails_open_without_gold_signal():
    item = evaluate.cascade_row(
        _row(scope="none", family_hit=False, broad_hit=True))
    assert item["route"] == "broad_or"
    assert item["gold_hits"] == 1
    assert "no_resolved_structure_scope" in item["fallback_reasons"]


def test_unresolved_or_empty_family_fails_open():
    assert evaluate.cascade_row(_row(unresolved=["제99조"]))["route"] == "broad_or"
    assert evaluate.cascade_row(_row(family=0))["route"] == "broad_or"


def test_summary_keeps_denominators():
    summary = evaluate.summarize([
        evaluate.cascade_row(_row()),
        evaluate.cascade_row(_row(scope="none", family_hit=False)),
    ])
    assert summary["gold"] == 2
    assert summary["gold_hits"] == 2
    assert summary["suite_candidate_presentations"] == 30
