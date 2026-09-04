from lawrag.core.rag.experiments import high_risk_claim_veto as veto


def _claim(status, answer_quote="3개월", sources=None):
    return {
        "claim_id": "C1", "claim_type": "numeric_condition",
        "answer_quote": answer_quote, "normalized_claim": "기간은 3개월",
        "source_status": status, "source_quote_ids": sources or [],
        "reason": "원문과 대조",
    }


def test_validation_accepts_sourced_direct_contradiction():
    raw = {"claims": [_claim("contradicts", sources=["E1:L1"])],
           "decision": "veto", "decision_reason": "수치가 반대"}
    result = veto.validate_veto(
        raw, "적용 기간은 3개월입니다.", [{"quote_id": "E1:L1"}])
    assert result["valid"]
    assert result["expected_decision"] == "veto"


def test_validation_rejects_veto_without_source_or_answer_span():
    raw = {"claims": [_claim("contradicts", answer_quote="6개월")],
           "decision": "veto", "decision_reason": "수치가 반대"}
    result = veto.validate_veto(
        raw, "적용 기간은 3개월입니다.", [{"quote_id": "E1:L1"}])
    assert not result["valid"]
    assert "C1:answer_quote_not_found" in result["errors"]
    assert "C1:contradiction_without_source" in result["errors"]


def test_validation_requires_uncertain_for_insufficient_claim():
    raw = {"claims": [_claim("insufficient")],
           "decision": "pass", "decision_reason": "문제 없음"}
    result = veto.validate_veto(
        raw, "적용 기간은 3개월입니다.", [{"quote_id": "E1:L1"}])
    assert not result["valid"]
    assert "decision_mismatch:pass!=uncertain" in result["errors"]


def test_veto_model_is_haiku():
    assert veto.HAIKU_MODEL == "claude-haiku-4-5-20251001"
