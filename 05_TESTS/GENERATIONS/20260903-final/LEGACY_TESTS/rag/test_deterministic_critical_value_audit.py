from scripts.rag_deterministic_critical_value_audit import (
    audit_answer,
    extract_values,
    summarize,
)


def test_percent_and_fraction_share_a_canonical_value():
    assert extract_values("20%") == [{"surface": "20%", "canonical": "20%:EQ"}]
    assert extract_values("100분의 20") == [
        {"surface": "100분의 20", "canonical": "20%:EQ"}]


def test_question_or_evidence_can_support_value_but_new_value_is_flagged():
    good = audit_answer("한도는 5억원인가", "한도는 5억원이다", "한도 규정")
    assert not good["flagged"]
    bad = audit_answer("한도는 얼마인가", "한도는 7억원이다", "한도는 5억원이다")
    assert bad["flagged"]
    assert bad["unsupported_values"][0]["canonical"] == "7억원:EQ"


def test_operator_direction_is_audited():
    result = audit_answer("기준은?", "두 금액 중 큰 금액이다", "중 적은 금액")
    assert result["unsupported_operators"] == ["GREATER"]


def test_summary_separates_false_flags_and_error_recall():
    result = summarize([
        {"semantic_correct": True, "flagged": True},
        {"semantic_correct": False, "flagged": True},
        {"semantic_correct": False, "flagged": False},
    ])
    assert result["flag_precision_for_semantic_error"] == 0.5
    assert result["semantic_error_recall"] == 0.5
    assert result["correct_answer_false_flag_rate"] == 1.0
