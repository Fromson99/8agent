from scripts import rag_proof_boundary_feedback_golden_61 as runner


def test_admission_audit_requires_promoted_subset_of_grounded_admission():
    valid = {
        "admitted": [{"doc_id": "d", "node": 2}],
        "promoted": [{"doc_id": "d", "node": 2}],
        "verification": {
            "accepted_evidence": [{"coordinate": ["d", 2]}]},
    }
    invalid = {
        **valid,
        "promoted": [{"doc_id": "d", "node": 3}],
    }

    assert runner._admission_valid(valid) is True
    assert runner._admission_valid(invalid) is False


def test_external_action_count_excludes_inspection_and_skips():
    meta = {"actions": [
        {"kind": "inspect_seen", "skipped": ""},
        {"kind": "keyword_search", "skipped": "novelty_veto"},
        {"kind": "relation_expand", "skipped": ""},
    ]}

    assert runner._action_count(meta) == 2
    assert runner._action_count(meta, external_only=True) == 1
