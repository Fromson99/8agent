from lawrag.core.rag.evidence_confusion import (
    EvidenceConfusion,
    aggregate_evidence_confusions,
    difficulty_balanced_score,
)


def test_confusion_counts_and_tn_is_audit_only() -> None:
    row = EvidenceConfusion.from_sets({"a", "b"}, {"b", "c"}, universe_size=10)
    assert (row.tp, row.fp, row.fn, row.tn) == (1, 1, 1, 7)
    assert row.precision == 0.5
    assert row.recall == 0.5
    assert row.tversky() == 1 / 2.25


def test_legal_tversky_monotonicity_and_asymmetric_cost() -> None:
    exact = EvidenceConfusion(2, 0, 0, 8)
    one_extra = EvidenceConfusion(2, 1, 0, 7)
    one_missing = EvidenceConfusion(1, 0, 1, 8)
    empty = EvidenceConfusion(0, 0, 2, 8)
    assert exact.tversky() == 1.0
    assert exact.tversky() > one_extra.tversky() > one_missing.tversky() > empty.tversky()
    assert one_extra.tversky() - one_missing.tversky() > 0


def test_group_score_counts_empty_and_complete_cases() -> None:
    summary = aggregate_evidence_confusions([
        EvidenceConfusion(1, 0, 0, 9),
        EvidenceConfusion(0, 0, 1, 9),
    ])
    assert summary["cases"] == 2
    assert summary["complete_cases"] == 1
    assert summary["complete_rate"] == 0.5
    assert 0 < summary["group_score"] < 100


def test_difficulty_balancing_gives_equal_group_weight() -> None:
    score = difficulty_balanced_score({
        "core": {"group_score": 90.0},
        "hard": {"group_score": 30.0},
    })
    assert score == 60.0

