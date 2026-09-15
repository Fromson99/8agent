from lawrag.research.experiments.haiku_legal_effect_executor import (
    execute_compilation, validate_compilation,
)


def _evidence():
    return [{"presented_id": "E1", "original_text": "본문 A. 다만 조건 B이면 제외한다."}]


def test_exact_quote_validation_and_exception_execution():
    output = {
        "task_kind": "EXCEPTION_SWITCH", "unresolved": [],
        "rules": [
            {"id": "R1", "source_evidence_id": "E1", "role": "MAIN",
             "condition": "A", "effect": "A 적용", "quote": "본문 A."},
            {"id": "R2", "source_evidence_id": "E1", "role": "EXCEPTION",
             "condition": "B", "effect": "A 제외", "quote": "다만 조건 B이면 제외한다."},
        ],
        "decisions": [{"id": "D1", "kind": "EXCEPTION_SWITCH",
                       "main_rule_id": "R1", "condition_rule_id": "R2",
                       "condition_satisfied": True, "alternative_rule_id": "",
                       "result_if_true": "A가 제외된다", "result_if_false": "A가 적용된다",
                       "reason": "B"}],
        "answer_slots": [],
    }
    validated = validate_compilation(output, _evidence(), "EXCEPTION_SWITCH")
    assert validated["executable"] is True
    result = execute_compilation(validated)
    assert result["answerable"] is True
    assert "A가 제외된다" in result["answer"]


def test_hallucinated_quote_fails_closed():
    output = {
        "task_kind": "SLOT_COVERAGE", "unresolved": [],
        "rules": [{"id": "R1", "source_evidence_id": "E1", "role": "MAIN",
                   "condition": "", "effect": "", "quote": "없는 문구"}],
        "decisions": [],
        "answer_slots": [{"key": "k", "label": "l", "value": "v",
                          "quote": "없는 문구", "rule_ids": ["R1"]}],
    }
    validated = validate_compilation(output, _evidence(), "SLOT_COVERAGE")
    assert validated["executable"] is False
    assert execute_compilation(validated)["answerable"] is False


def test_guarded_mode_runs_valid_slots_with_unresolved_warning():
    output = {
        "task_kind": "SLOT_COVERAGE", "unresolved": ["부수 정의 미확정"],
        "rules": [{"id": "R1", "source_evidence_id": "E1", "role": "MAIN",
                   "condition": "", "effect": "A", "quote": "본문 A."}],
        "decisions": [],
        "answer_slots": [{"key": "k", "label": "결론", "value": "A",
                          "quote": "본문 A.", "rule_ids": ["R1"]}],
    }
    validated = validate_compilation(output, _evidence(), "SLOT_COVERAGE")
    assert validated["executable"] is False
    assert validated["guarded_executable"] is True
    result = execute_compilation(validated, allow_unresolved=True)
    assert result["answerable"] is True
    assert result["trace"]["status"] == "executed_with_warnings"
