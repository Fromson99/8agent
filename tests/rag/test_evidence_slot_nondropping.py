from __future__ import annotations

from lawrag.core.rag.answer import Section
from lawrag.core.rag.evidence_slot_nondropping import (
    build_slot_packet,
    packet_integrity,
    slot_answer_schema,
    synthesize_slot_answer,
    validate_slot_output,
)
from lawrag.core.rag.legal_proposition_compiler import (
    CompilationResult,
    CompilerStatus,
)


def _result() -> CompilationResult:
    return CompilationResult(
        status=CompilerStatus.BLOCKED_MISSING_COVERAGE,
        issues=({
            "issue_id": "I1", "question_span": "위탁할 수 있나",
            "required_roles": ["GOVERNING_RULE", "EXCEPTION"], "facts": [],
        },),
        facts=(),
        rules=({
            "rule_id": "R1", "issue_id": "I1", "role": "GOVERNING_RULE",
            "evidence_id": "E1", "source_quote": "업무를 위탁할 수 있다.",
            "proposition": "업무를 위탁할 수 있다.", "slots": {},
        },),
        applicability=(),
        coverage=(
            {
                "issue_id": "I1", "coverage_key": "role:I1:GOVERNING_RULE",
                "required_role": "GOVERNING_RULE", "state": "SATISFIED",
                "rule_ids": ["R1"], "evidence_ids": ["E1"],
            },
            {
                "issue_id": "I1", "coverage_key": "role:I1:EXCEPTION",
                "required_role": "EXCEPTION", "state": "MISSING",
                "rule_ids": [], "evidence_ids": [],
            },
        ),
        search_plan=(), clarification_requests=(), relation_behaviors=(),
        validation_errors=(), diagnostics={}, direct_legal_conclusion_allowed=False,
    )


class _LLM:
    def __init__(self, value):
        self.value = value
        self.schema = None

    def structured(self, kind, system, user, schema, **kwargs):
        self.schema = schema
        return self.value


def test_slot_packet_turns_coverage_into_required_properties():
    packet = build_slot_packet(_result())
    schema = slot_answer_schema(packet)
    assert packet["satisfied_slot_ids"] == ["S001"]
    assert packet["missing_slot_ids"] == ["S002"]
    assert schema["properties"]["claims"]["required"] == ["S001"]
    assert schema["properties"]["limitations"]["required"] == ["S002"]
    assert packet_integrity(packet) == []


def test_missing_required_claim_is_a_binding_violation():
    packet = build_slot_packet(_result())
    _, _, violations = validate_slot_output(
        packet, {"summary": "요약", "claims": {}, "limitations": {"S002": "확인"}},
    )
    assert violations == ["missing_claim:S001"]


def test_answer_evidence_is_derived_from_emitted_required_slot_claim():
    llm = _LLM({
        "summary": "위탁 근거는 있으나 예외를 확인해야 합니다.",
        "claims": {"S001": "법문상 업무 위탁의 근거가 있습니다."},
        "limitations": {"S002": "예외 규정을 추가로 확인해야 합니다."},
    })
    result = synthesize_slot_answer(
        llm, "위탁할 수 있나", _result(),
        [Section(n=1, doc_id="D1", doc="법", node=1, path="제1조", page=None,
                 kind="조문", matched="", text="업무를 위탁할 수 있다.")],
    )
    assert result.answer.evidence_ids == ["E1"]
    assert result.answer.conclusion_strength == "CONDITIONAL"
    assert result.answer.issue_results[0]["evidence_ids"] == ["E1"]
    assert result.violations == ()


def test_empty_claim_does_not_create_a_false_evidence_declaration():
    llm = _LLM({
        "summary": "확인이 필요합니다.",
        "claims": {"S001": ""},
        "limitations": {"S002": "예외를 확인해야 합니다."},
    })
    result = synthesize_slot_answer(
        llm, "위탁할 수 있나", _result(),
        [Section(n=1, doc_id="D1", doc="법", node=1, path="제1조", page=None,
                 kind="조문", matched="", text="업무를 위탁할 수 있다.")],
    )
    assert result.answer.evidence_ids == []
    assert result.answer.gate_violation is True
    assert "empty_claim:S001" in result.violations
