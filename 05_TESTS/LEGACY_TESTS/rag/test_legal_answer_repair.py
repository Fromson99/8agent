from lawrag.core.rag.experiments import legal_answer_repair as repair


class FakeLLM:
    def __init__(self, result):
        self.result = result

    def structured(self, *args, **kwargs):
        return self.result


def _evidence():
    return [{"id": "E1", "document": "법", "path": "제1조",
             "original_text": "하여야 한다"}]


def test_keep_preserves_exact_draft():
    llm = FakeLLM({
        "checks": [], "draft_errors": [], "action": "keep", "reason": "일치",
        "support_ids": ["E1"], "corrected_answer": "모델이 바꾼 문장",
    })
    out = repair.verify_and_repair(llm, "질문", _evidence(), "원래 초안")
    assert out["answer"] == "원래 초안"
    assert out["guard"] == "keep_exact_draft"


def test_repair_accepts_only_closed_evidence_ids():
    valid = FakeLLM({
        "checks": [], "draft_errors": ["modality"], "action": "repair",
        "reason": "강행성을 고침", "support_ids": ["E1"],
        "corrected_answer": "하여야 합니다.",
    })
    out = repair.verify_and_repair(valid, "질문", _evidence(), "할 수 있습니다.")
    assert out["answer"] == "하여야 합니다."
    assert out["guard"] == "accepted_repair"

    invalid = FakeLLM({
        "checks": [], "draft_errors": ["modality"], "action": "repair",
        "reason": "강행성을 고침", "support_ids": ["E99"],
        "corrected_answer": "하여야 합니다.",
    })
    out = repair.verify_and_repair(invalid, "질문", _evidence(), "할 수 있습니다.")
    assert out["answer"] == "할 수 있습니다."
    assert out["guard"] == "invalid_support_keep_draft"


def test_llm_failure_falls_back_to_draft():
    out = repair.verify_and_repair(FakeLLM(None), "질문", _evidence(), "초안")
    assert out["action"] == "keep"
    assert out["answer"] == "초안"


def test_unresolved_check_cannot_flip_direct_rule_absence():
    llm = FakeLLM({
        "checks": [{
            "item": "별도 조정 규정", "status": "unknown",
            "finding": "별도 명문은 확인되지 않는다", "evidence_ids": ["E1"],
        }],
        "draft_errors": ["conclusion"], "action": "repair",
        "reason": "일반 산식은 있다", "support_ids": ["E1"],
        "corrected_answer": "네, 조정됩니다.",
    })
    draft = "회수된 자료에는 별도 조정에 관한 명시적 규정이 없습니다."
    out = repair.verify_and_repair(llm, "조정되는가?", _evidence(), draft)
    assert out["action"] == "keep"
    assert out["answer"] == draft
    assert out["guard"] == "unresolved_absence_keep_draft"


def test_interpretive_qualification_is_not_hardened_to_certainty():
    llm = FakeLLM({
        "checks": [{
            "item": "적용 여부", "status": "satisfied",
            "finding": "문언은 적용 가능", "evidence_ids": ["E1"],
        }],
        "draft_errors": ["omission"], "action": "repair",
        "reason": "설명을 보완", "support_ids": ["E1"],
        "corrected_answer": "적용됩니다.",
    })
    draft = "조문의 구조상 적용되는 것으로 해석됩니다."
    out = repair.verify_and_repair(llm, "적용되는가?", _evidence(), draft)
    assert out["action"] == "keep"
    assert out["answer"] == draft
    assert out["guard"] == "interpretive_qualification_keep_draft"
