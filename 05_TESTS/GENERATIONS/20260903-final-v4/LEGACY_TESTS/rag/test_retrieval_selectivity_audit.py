from scripts.rag_retrieval_selectivity_audit import (
    policy_selectivity,
    navigation_exposure,
    ratio,
    retrieval_selectivity,
)


def test_ratio_is_safe_and_stable():
    assert ratio(10, 100) == 0.1
    assert ratio(1, 0) == 0.0


def test_policy_selectivity_uses_explicit_universes():
    row = policy_selectivity({
        "candidate_coordinates": {"min": 10, "median": 20, "p95": 40,
                                  "max": 50, "mean": 25},
        "documents": {"min": 1, "median": 5, "p95": 8, "max": 9, "mean": 4},
    }, coordinate_universe=100, document_universe=10)
    assert row["coordinate_selectivity"]["mean"] == 0.25
    assert row["document_selectivity"]["median"] == 0.5


def test_final_retrieval_counts_repeated_and_unique_presentations_separately():
    artifact = {
        "contract": {"final_cap": 20},
        "summary": {"control": {"gold": 2, "selected_hits": 2,
                                  "selected_recall": 1.0}},
        "rows": [
            {"variants": {"control": {"selected_count": 2, "body_chars": 100,
                "selected": [{"doc_id": "d", "node": 1},
                             {"doc_id": "d", "node": 2}]}}},
            {"variants": {"control": {"selected_count": 2, "body_chars": 120,
                "selected": [{"doc_id": "d", "node": 1},
                             {"doc_id": "e", "node": 3}]}}},
        ],
    }
    result = retrieval_selectivity(
        artifact, variant="control", article_universe=1000, article_chars=10000)
    assert result["suite_total_presentations"] == 4
    assert result["suite_unique_selected_articles"] == 3
    assert result["article_selectivity_per_query"]["mean"] == 0.002
    assert result["body_char_selectivity_per_query"]["mean"] == 0.011


def test_navigation_exposure_does_not_call_menu_slots_unique_candidates():
    primary = {"summary": {"calls": 3}, "rows": [{
        "case_no": "c", "selection": [{"option_count": 10}, {"option_count": 4}]}]}
    assertion = {"rows": [{"case_no": "c", "tree": {
        "families": 2, "documents": 3, "provisions": 20, "calls": 4}}]}
    result = navigation_exposure(primary, assertion)
    assert result["combined_recorded_menu_item_exposures_per_query"]["mean"] == 39
    assert result["combined_recorded_navigation_calls_per_query"]["mean"] == 6
    assert "unique" in result["note"]
