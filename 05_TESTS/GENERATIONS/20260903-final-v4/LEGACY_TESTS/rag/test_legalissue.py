from lawrag.core.rag import legalissue


EVIDENCE = [{
    "id": "G1",
    "original_text": "회사의 대표자는 상근이사 1명을 관리자로 지정하여야 한다.",
}]


def test_verify_judgment_drops_unknown_evidence_and_fabricated_quote():
    judgment = {
        "verdict": "entailed",
        "controlling_evidence_ids": ["G1", "X9"],
        "rule_findings": [
            {"statement": "유효", "evidence_id": "G1",
             "span_id": "G1:S1",
             "relation_to_proposition": "supports"},
            {"statement": "조작", "evidence_id": "G1",
             "span_id": "G1:S9",
             "relation_to_proposition": "supports"},
            {"statement": "미등록", "evidence_id": "X9", "span_id": "X9:S1",
             "relation_to_proposition": "supports"},
        ],
        "missing_links": [], "rejected_inferences": [], "explanation": "설명",
    }

    out = legalissue.verify_judgment(judgment, EVIDENCE)

    assert out["controlling_evidence_ids"] == ["G1"]
    assert len(out["rule_findings"]) == 1
    assert out["rule_findings"][0]["statement"] == "유효"
    assert out["rule_findings"][0]["quote"] == EVIDENCE[0]["original_text"]
    assert out["verdict"] == "entailed"


def test_verify_judgment_downgrades_contradiction_without_opposite_span():
    judgment = {
        "verdict": "contradicted",
        "controlling_evidence_ids": ["G1"],
        "rule_findings": [{
            "statement": "관련 문언", "evidence_id": "G1",
            "span_id": "G1:S1",
            "relation_to_proposition": "context",
        }],
        "missing_links": [], "rejected_inferences": [], "explanation": "아니다",
    }

    out = legalissue.verify_judgment(judgment, EVIDENCE)

    assert out["verdict"] == "not_determined"
    assert out["guard_downgraded"] is True


def test_render_not_determined_never_uses_model_conclusion():
    frame = {"proposition": "관리자는 등기임원이어야 한다"}
    judgment = {
        "verdict": "not_determined",
        "rule_findings": [{
            "evidence_id": "G1",
            "quote": "상근이사 1명을 관리자로 지정하여야 한다",
        }],
        "missing_links": ["상근이사와 등기임원의 법적 관계"],
        "explanation": "등기임원일 필요가 없다",
    }

    answer = legalissue.render_answer(frame, judgment)

    assert "확정할 수 없습니다" in answer
    assert "상근이사" in answer
    assert "등기임원일 필요가 없다" not in answer


def test_render_entailed_uses_grounded_explanation():
    frame = {"proposition": "제출기한 구분 기준"}
    judgment = {"verdict": "entailed", "explanation": "45일이 원칙이고 60일은 특례다."}

    assert legalissue.render_answer(frame, judgment) == judgment["explanation"]


def test_interpreter_instructions_activate_only_closed_known_methods():
    frame = {
        "candidate_interpreters": [
            "definition_scope", "unknown_method", "subsumption", "definition_scope",
        ]
    }

    active = legalissue.interpreter_instructions(frame)

    assert [row["name"] for row in active] == ["definition_scope", "subsumption"]
    assert all(row["rule"] for row in active)


def test_prepare_evidence_assigns_closed_span_id_without_rewriting_text():
    prepared = legalissue.prepare_evidence(EVIDENCE)

    assert prepared[0]["spans"] == [{
        "id": "G1:S1", "text": EVIDENCE[0]["original_text"],
    }]
    assert "original_text" not in prepared[0]


def test_decision_term_guard_downgrades_polarity_when_query_concept_is_absent():
    frame = {
        "question_type": "proposition_verification",
        "decision_terms": ["관리자", "등기임원"],
    }
    judgment = {
        "verdict": "contradicted",
        "controlling_evidence_ids": ["G1"],
        "rule_findings": [{
            "statement": "상근이사를 지정한다", "evidence_id": "G1",
            "span_id": "G1:S1", "relation_to_proposition": "contradicts",
        }],
        "missing_links": [], "rejected_inferences": [], "explanation": "아니다",
    }

    out = legalissue.verify_judgment(judgment, EVIDENCE, frame)

    assert out["verdict"] == "not_determined"
    assert out["guard_downgraded"] is True
    assert out["guard_missing_decision_terms"] == ["등기임원"]


def test_decision_term_guard_does_not_block_open_rule_explanation():
    frame = {
        "question_type": "rule_explanation",
        "decision_terms": ["관리자", "등기임원"],
    }
    judgment = {
        "verdict": "entailed",
        "controlling_evidence_ids": ["G1"],
        "rule_findings": [{
            "statement": "지정 규칙을 설명한다", "evidence_id": "G1",
            "span_id": "G1:S1", "relation_to_proposition": "supports",
        }],
        "missing_links": [], "rejected_inferences": [], "explanation": "설명",
    }

    out = legalissue.verify_judgment(judgment, EVIDENCE, frame)

    assert out["verdict"] == "entailed"
    assert out["guard_downgraded"] is False


def test_typed_answer_requires_closed_requirement_and_span_ids():
    frame = {
        "question_type": "rule_explanation",
        "requirement_cards": [
            {"id": "R1", "requirement": "원칙 기한"},
            {"id": "R2", "requirement": "예외 기한"},
        ],
    }
    raw = {
        "status": "answered", "conclusion": "기한이 나뉜다", "answer": "답변",
        "findings": [
            {"requirement_id": "R1", "statement": "원칙", "evidence_id": "G1",
             "span_id": "G1:S1"},
            {"requirement_id": "R9", "statement": "조작", "evidence_id": "G1",
             "span_id": "G1:S1"},
        ],
        "missing_requirement_ids": [], "rejected_inferences": [],
    }

    out = legalissue.verify_typed_answer(raw, frame, EVIDENCE)

    assert len(out["findings"]) == 1
    assert out["findings"][0]["quote"] == EVIDENCE[0]["original_text"]
    assert out["status"] == "partial"
    assert out["missing_requirement_ids"] == ["R2"]


def test_typed_partial_answer_keeps_verified_content_and_names_gap():
    frame = {
        "question_type": "scope_classification",
        "proposition": "A와 B 중 적용 범위",
        "requirement_cards": [
            {"id": "R1", "requirement": "A 적용 여부"},
            {"id": "R2", "requirement": "B 적용 여부"},
        ],
    }
    result = {
        "status": "partial", "answer": "A에는 적용됩니다.",
        "missing_requirement_ids": ["R2"],
    }

    answer = legalissue.render_typed_answer(frame, result)

    assert "A에는 적용됩니다" in answer
    assert "B 적용 여부" in answer


def test_typed_answer_without_valid_evidence_becomes_not_determined():
    frame = {
        "question_type": "procedure", "proposition": "신고 절차",
        "requirement_cards": [{"id": "R1", "requirement": "신고처"}],
    }
    raw = {
        "status": "answered", "conclusion": "기관에 신고", "answer": "기관에 신고한다.",
        "findings": [], "missing_requirement_ids": [], "rejected_inferences": [],
    }

    checked = legalissue.verify_typed_answer(raw, frame, [])
    answer = legalissue.render_typed_answer(frame, checked)

    assert checked["status"] == "not_determined"
    assert "답할 수 없습니다" in answer
    assert "기관에 신고한다" not in answer


def test_review_guard_blocks_absence_to_negative_proposition():
    frame = {
        "question_type": "proposition_verification",
        "decision_terms": ["내부회계관리자", "등기임원"],
    }
    result = {
        "status": "partial",
        "answer": ("법령이 등기임원을 명시하지 않으므로 내부회계관리자는 "
                   "등기임원일 필요가 없습니다."),
        "rejected_inferences": [],
    }

    checked = legalissue.guard_reviewed_proposition(result, frame, EVIDENCE)

    assert checked["status"] == "not_determined"
    assert checked["guard_downgraded"] is True
    assert "등기임원" in checked["guard_missing_decision_terms"]


def test_review_guard_keeps_direct_threshold_answer_with_conditional_negative():
    frame = {
        "question_type": "proposition_verification",
        "decision_terms": ["계열회사", "공동주관 의무"],
    }
    evidence = [{
        "id": "G2",
        "original_text": "이해관계인이 합하여 100분의 5 이상이면 공동으로 하여야 한다.",
    }]
    result = {
        "status": "partial",
        "answer": ("단순 보유만으로는 발생하지 않습니다. 합하여 100분의 5 이상이면 "
                   "공동으로 하여야 합니다."),
        "rejected_inferences": [],
    }

    checked = legalissue.guard_reviewed_proposition(result, frame, evidence)

    assert checked["status"] == "partial"
    assert checked["guard_downgraded"] is False


def test_review_guard_blocks_categorical_bridge_when_all_decision_terms_absent():
    frame = {
        "question_type": "proposition_verification",
        "decision_terms": ["이미 과세된", "저가분", "조정"],
    }
    result = {
        "status": "answered", "answer": "가액 감소분은 환급으로 조정됩니다.",
        "rejected_inferences": [],
    }

    checked = legalissue.guard_reviewed_proposition(result, frame, EVIDENCE)

    assert checked["status"] == "not_determined"
    assert checked["guard_downgraded"] is True
