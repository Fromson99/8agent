from scripts.rag_evidence_bundle_eval import CASES
from scripts.rag_legal_issue_frame_eval import score


def test_not_determined_uses_gold_as_material_not_controlling():
    case = CASES[1]
    frame = {
        "proposition": "내부회계관리자는 등기임원이어야 한다",
        "candidate_interpreters": ["definition_scope", "subsumption"],
    }
    judgment = {
        "verdict": "not_determined",
        "controlling_evidence_ids": [],
        "rule_findings": [{"evidence_id": "G36"}],
        "missing_links": ["상근이사와 등기임원의 상법상 관계"],
        "guard_downgraded": False,
    }
    answer = (
        "제공된 근거만으로는 명제를 확정할 수 없습니다. "
        "확인된 문언은 상근이사입니다."
    )

    result = score(case, frame, judgment, answer)

    assert result["passed"] is True
    assert result["safety_passed"] is True
    assert result["checks"]["gold_material"] is True


def test_subsumption_is_valid_rule_interpreter_for_deadline_scope():
    case = CASES[0]
    frame = {
        "proposition": "반기보고서 제출기한은 45일과 60일로 구분된다",
        "candidate_interpreters": ["definition_scope", "subsumption"],
    }
    judgment = {
        "verdict": "entailed",
        "controlling_evidence_ids": ["G32"],
        "rule_findings": [{"evidence_id": "G32"}],
        "missing_links": [],
        "guard_downgraded": False,
    }
    answer = (
        "45일이 원칙이며, 연결재무제표 기준으로 작성한 경우 최초 사업연도와 "
        "그 다음 사업연도에는 60일이다."
    )

    result = score(case, frame, judgment, answer)

    assert result["passed"] is True
    assert result["safety_passed"] is True
    assert result["checks"]["selects_rule_interpreter"] is True


def test_first_two_business_years_summary_is_accepted():
    case = CASES[0]
    frame = {
        "proposition": "반기보고서 제출기한은 45일과 60일로 구분된다",
        "candidate_interpreters": ["subsumption", "exception"],
    }
    judgment = {
        "verdict": "entailed",
        "controlling_evidence_ids": ["G32"],
        "rule_findings": [{"evidence_id": "G32"}],
        "missing_links": [], "guard_downgraded": False,
    }
    answer = (
        "45일이 원칙이며 연결재무제표 기준으로 작성한 경우 최초 2개 사업연도에는 "
        "60일 이내 제출할 수 있다."
    )

    assert score(case, frame, judgment, answer)["passed"] is True


def test_missing_exact_quote_fails_trace_but_preserves_safety_score():
    case = CASES[1]
    frame = {
        "proposition": "내부회계관리자는 등기임원이어야 한다",
        "candidate_interpreters": ["definition_scope", "subsumption"],
    }
    judgment = {
        "verdict": "not_determined",
        "controlling_evidence_ids": [],
        "rule_findings": [],
        "missing_links": ["상근이사와 등기임원의 상법상 관계"],
        "guard_downgraded": False,
    }
    answer = (
        "제공된 근거만으로는 명제를 확정할 수 없습니다. "
        "추가 확인 대상은 상근이사와 등기임원의 관계입니다."
    )

    result = score(case, frame, judgment, answer)

    assert result["passed"] is False
    assert result["safety_passed"] is True
    assert result["checks"]["gold_material"] is False
