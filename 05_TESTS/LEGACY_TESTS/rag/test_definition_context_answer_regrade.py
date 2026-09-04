from scripts.rag_definition_context_answer_regrade import _majority


def test_majority_is_per_answer_and_requires_two_votes():
    votes = [
        {"baseline": {"correct": True}, "candidate": {"correct": False}},
        {"baseline": {"correct": False}, "candidate": {"correct": True}},
        {"baseline": {"correct": True}, "candidate": {"correct": True}},
    ]
    assert _majority(votes, "baseline") is True
    assert _majority(votes, "candidate") is True

