from scripts import rag_verified_span_selector_golden_61 as runner


def test_zero_usage_has_complete_keys():
    usage = runner._zero_usage()
    assert usage["calls"] == 0
    assert usage["errors"] == 0


def test_percentile_is_bounded():
    assert runner._percentile([], .95) == 0
    assert runner._percentile([1, 2, 3], .95) == 3


def test_promotion_stats_separates_gold_and_noise():
    row = {
        "case_id": "x",
        "input_state": {"parent_selected": [
            {"doc_id": "d", "node": 1}]},
        "arms": {"candidate": {
            "selected": [
                {"doc_id": "d", "node": 1},
                {"doc_id": "d", "node": 2},
                {"doc_id": "d", "node": 3},
            ],
            "gold_results": [
                {"doc_id": "d", "node": 2, "scorable": True}],
        }},
    }
    stats = runner._promotion_stats([row], "candidate")
    assert stats["total"] == 2
    assert stats["gold"] == 1
    assert stats["non_gold"] == 1
