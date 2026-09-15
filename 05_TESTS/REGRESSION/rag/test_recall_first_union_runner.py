from scripts import rag_recall_first_union_golden_61 as runner


def test_retention_contract_separates_pool_from_verified_promotion():
    valid = {
        "retained": [{"doc_id": "d", "node": 2},
                     {"doc_id": "d", "node": 3}],
        "evidence_pool": [{"doc_id": "d", "node": 1},
                          {"doc_id": "d", "node": 2},
                          {"doc_id": "d", "node": 3}],
        "verified_evidence": [{"coordinate": ["d", 2]}],
        "promoted": [{"doc_id": "d", "node": 2}],
        "union_candidate_count": 2,
    }
    invalid = {**valid, "promoted": [{"doc_id": "d", "node": 3}]}

    assert runner._retention_valid(valid) is True
    assert runner._retention_valid(invalid) is False
