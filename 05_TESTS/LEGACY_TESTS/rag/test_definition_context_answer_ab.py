from scripts.rag_definition_context_answer_ab import _labels


def test_paired_judge_order_alternates_by_case_number():
    odd, odd_prompt = _labels("cm-001", "baseline", "candidate")
    even, even_prompt = _labels("cm-002", "baseline", "candidate")

    assert odd == {"baseline": "A", "candidate": "B"}
    assert "[답변 A]\nbaseline" in odd_prompt
    assert even == {"baseline": "B", "candidate": "A"}
    assert "[답변 A]\ncandidate" in even_prompt

