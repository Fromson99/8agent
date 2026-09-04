from lawrag.core.rag.experiments.haiku_hard_distractors import (
    VARIANTS, build_variants, deterministic_random_ids, normalize_labels,
)


def _row(evidence_id):
    return {"id": evidence_id, "document": "법", "path": evidence_id,
            "original_text": evidence_id}


def test_normalize_labels_keeps_candidate_order_and_fills_missing():
    candidates = [_row("E2"), _row("E3")]
    got = normalize_labels(candidates, {"rows": [{
        "id": "E3", "label": "HARD_DISTRACTOR", "subtype": "OTHER_MARKET",
        "risk": 3, "reason": "다른 시장",
    }]})
    assert [row["id"] for row in got] == ["E2", "E3"]
    assert got[0]["classifier_missing"] is True
    assert got[1]["label"] == "HARD_DISTRACTOR"


def test_build_variants_changes_only_evidence_membership_and_order():
    gold = [_row("G1")]
    candidates = [_row("H1"), _row("S1"), _row("I1")]
    labels = [
        {"id": "H1", "label": "HARD_DISTRACTOR", "risk": 3},
        {"id": "S1", "label": "SUPPORTIVE", "risk": 2},
        {"id": "I1", "label": "EASY_IRRELEVANT", "risk": 1},
    ]
    random_rows = [_row("R1")]
    got = build_variants(gold, candidates, labels, random_rows)
    assert tuple(got) == VARIANTS
    assert [row["id"] for row in got["hard_after"]] == ["G1", "H1"]
    assert [row["id"] for row in got["hard_before"]] == ["H1", "G1"]
    assert [row["id"] for row in got["supportive_after"]] == ["G1", "S1"]
    assert [row["id"] for row in got["full_original"]] == ["G1", "H1", "S1", "I1"]


def test_deterministic_random_ids_is_stable():
    pool = [{"pool_id": f"P{i}"} for i in range(8)]
    assert deterministic_random_ids("cm-001", pool) == deterministic_random_ids(
        "cm-001", list(reversed(pool)))
