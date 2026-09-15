from scripts.rag_claim_matrix_regrade import summarize


def test_regrade_summary_is_paired():
    result = summarize([{"grades": {"full_context": {"correct": True},
                                     "claim_matrix": {"correct": False}}}])
    assert result["claim_matrix"]["versus_full"]["full_only_correct"] == 1
    assert result["claim_matrix"]["versus_full"]["delta"] == -1
