from scripts import rag_quote_decision_regrade as regrade


def test_regrade_summary_pairs_guarded_and_raw():
    rows = [{"grades": {
        "baseline": {"correct": True}, "raw_candidate": {"correct": False},
        "guarded": {"correct": True},
    }}, {"grades": {
        "baseline": {"correct": False}, "raw_candidate": {"correct": True},
        "guarded": {"correct": True},
    }}]
    summary = regrade.summarize(rows)
    assert summary["baseline"]["correct"] == 1
    assert summary["raw_candidate"]["versus_baseline"]["baseline_only_correct"] == 1
    assert summary["guarded"]["versus_baseline"]["candidate_only_correct"] == 1
