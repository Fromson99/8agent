from scripts.rag_claim_entailment_answer_ab import summarize


def test_answer_summary_is_paired():
    rows = [{"alignment": {"valid": True}, "matrix_render": {"valid": True},
             "variants": {"full_context": {"correct": True, "usage": {}},
                          "claim_matrix": {"correct": False, "usage": {}}}},
            {"alignment": {"valid": True}, "matrix_render": {"valid": True},
             "variants": {"full_context": {"correct": False, "usage": {}},
                          "claim_matrix": {"correct": True, "usage": {}}}}]
    result = summarize(rows)
    assert result["coverage_cases"] == 2
    assert result["claim_matrix"]["versus_full"]["full_only_correct"] == 1
    assert result["claim_matrix"]["versus_full"]["matrix_only_correct"] == 1
