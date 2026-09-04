from __future__ import annotations

from copy import deepcopy

from lawrag.core.rag.answer import Section
from lawrag.core.rag import proposition_assessment_shadow as shadow


QUESTION = "금융회사가 심사업무를 외부 기관에 위탁할 수 있는가?"
TEXT = "금융회사는 심사업무를 외부 기관에 위탁할 수 있다. 위탁은 계약 체결 시 효력이 발생한다."


def _section() -> Section:
    return Section(
        n=1, doc_id="DOC", doc="금융회사 업무위탁규정", node=10,
        path="제10조", page=1, kind="본문", matched="위탁", text=TEXT,
        legal_meta={"existing": True},
    )


def _rule(rule_id: str, role: str, quote: str, slots: dict) -> dict:
    return {
        "rule_id": rule_id,
        "issue_id": "I1",
        "role": role,
        "evidence_id": shadow.evidence_from_sections([_section()])[0].evidence_id,
        "source_quote": quote,
        "slots": slots,
        "relation_coverage_keys": [],
    }


def _raw(*, facts=True, effect=True) -> dict:
    rows = [_rule(
        "R1", "GOVERNING_RULE",
        "금융회사는 심사업무를 외부 기관에 위탁할 수 있다.",
        {"ACTOR": ["금융회사"], "ACTION": ["위탁"], "OBJECT": ["심사업무"]},
    )]
    if effect:
        rows.append(_rule(
            "R2", "LEGAL_EFFECT", "위탁은 계약 체결 시 효력이 발생한다.",
            {"EFFECT": ["효력이 발생"]},
        ))
    return {
        "issues": [{
            "issue_id": "I1",
            "question_span": "심사업무를 외부 기관에 위탁할 수 있는가",
            "required_roles": [],
            "facts": ([{
                "fact_id": "F1", "kind": "ACTOR", "question_span": "금융회사",
            }] if facts else []),
        }],
        "rules": rows,
        "applicability": [],
    }


class FakeLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def structured(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return deepcopy(self.outputs.pop(0))


def _attach(monkeypatch, outputs):
    monkeypatch.setattr(shadow, "capture_stages", lambda *args, **kwargs: {"stages": []})
    llm = FakeLLM(outputs)
    section = _section()
    result, meta = shadow.attach_shadow_compilation(
        object(), QUESTION, [section], llm=llm, case_id="case-1",
    )
    return section, result, meta, llm


def test_verified_supported_fact_reaches_direct_assessment(monkeypatch) -> None:
    binding = {
        "binding_id": "B1", "issue_id": "I1", "rule_id": "R1",
        "fact_id": "F1", "state": "SUPPORTED",
    }
    _, sections, meta, _ = _attach(monkeypatch, [_raw(), {"bindings": [binding]}])
    packet = sections[0].legal_meta["legal_compilation"]
    assert meta["status"] == "READY_FOR_ASSESSMENT"
    assert packet["answer_mode"] == "DIRECT_RULE"
    assert packet["direct_legal_conclusion_allowed_by_compiler"] is False


def test_unresolved_verified_fact_stays_conditional(monkeypatch) -> None:
    binding = {
        "binding_id": "B1", "issue_id": "I1", "rule_id": "R1",
        "fact_id": "F1", "state": "UNRESOLVED",
    }
    _, sections, meta, _ = _attach(monkeypatch, [_raw(), {"bindings": [binding]}])
    assert meta["status"] == "BLOCKED_UNRESOLVED_FACTS"
    assert sections[0].legal_meta["legal_compilation"]["answer_mode"] \
        == "CONDITIONAL_APPLICATION"


def test_no_fact_skips_verifier_and_can_assess_rule_question(monkeypatch) -> None:
    _, sections, meta, llm = _attach(monkeypatch, [_raw(facts=False)])
    assert len(llm.calls) == 1
    assert meta["verifier_receipt"]["attempted"] is False
    assert sections[0].legal_meta["legal_compilation"]["answer_mode"] == "DIRECT_RULE"


def test_missing_legal_effect_gets_one_same_menu_retry(monkeypatch) -> None:
    initial = _raw(facts=False, effect=False)
    retry = {"rules": [_rule(
        "RR1", "LEGAL_EFFECT", "위탁은 계약 체결 시 효력이 발생한다.",
        {"EFFECT": ["효력이 발생"]},
    )]}
    _, sections, meta, llm = _attach(monkeypatch, [initial, retry])
    assert len(llm.calls) == 2
    assert meta["coverage_retry_receipt"]["attempted"] is True
    assert meta["coverage_retry_receipt"]["accepted_rule_delta"] == 1
    assert sections[0].legal_meta["legal_compilation"]["answer_mode"] == "DIRECT_RULE"


def test_invalid_retry_rule_cannot_satisfy_coverage(monkeypatch) -> None:
    initial = _raw(facts=False, effect=False)
    retry = {"rules": [_rule(
        "RR1", "LEGAL_EFFECT", "원문에 없는 효력이다.", {"EFFECT": ["효력"]},
    )]}
    _, sections, meta, _ = _attach(monkeypatch, [initial, retry])
    packet = sections[0].legal_meta["legal_compilation"]
    assert meta["status"] == "BLOCKED_MISSING_COVERAGE"
    assert packet["answer_mode"] == "INSUFFICIENT"
    assert packet["missing"]


def test_compact_packet_never_creates_context_claims(monkeypatch) -> None:
    _, sections, meta, _ = _attach(monkeypatch, [_raw(facts=False)])
    packet = sections[0].legal_meta["legal_compilation"]
    assert meta["context_claim_count"] == 0
    assert {claim["origin"] for claim in packet["claims"]} \
        == {"exact-proposition-compiler"}


def test_selected_evidence_is_derived_only_from_accepted_rules(monkeypatch) -> None:
    _, sections, _, _ = _attach(monkeypatch, [_raw(facts=False)])
    packet = sections[0].legal_meta["legal_compilation"]
    assert set(packet["selected_evidence_ids"]) == {
        claim["evidence_id"] for claim in packet["claims"]
    }


def test_original_sections_are_not_mutated(monkeypatch) -> None:
    original, sections, _, _ = _attach(monkeypatch, [_raw(facts=False)])
    assert "legal_compilation" not in original.legal_meta
    assert "legal_compilation" in sections[0].legal_meta
    assert sections[0].legal_meta["existing"] is True


def test_coordinates_and_count_remain_identical(monkeypatch) -> None:
    original, sections, meta, _ = _attach(monkeypatch, [_raw(facts=False)])
    assert [(original.doc_id, original.node)] == [
        (row.doc_id, row.node) for row in sections
    ]
    assert meta["before_count"] == meta["after_count"] == 1
    assert meta["coordinates_unchanged"] is True


def test_all_product_roles_pin_haiku(monkeypatch) -> None:
    binding = {
        "binding_id": "B1", "issue_id": "I1", "rule_id": "R1",
        "fact_id": "F1", "state": "SUPPORTED",
    }
    _, _, _, llm = _attach(monkeypatch, [_raw(), {"bindings": [binding]}])
    assert all(
        kwargs["model"] == "claude-haiku-4-5-20251001"
        for _, kwargs in llm.calls
    )


def test_verifier_schema_uses_closed_issue_rule_fact_ids() -> None:
    evidence = shadow.evidence_from_sections([_section()])
    result = shadow.compile_legal_review(QUESTION, evidence, _raw())
    schema = shadow._applicability_schema(result)
    props = schema["properties"]["bindings"]["items"]["properties"]
    assert props["issue_id"]["enum"] == ["I1"]
    assert props["rule_id"]["enum"] == ["R1", "R2"]
    assert props["fact_id"]["enum"] == ["F1"]


def test_coverage_schema_closes_issue_evidence_and_role() -> None:
    evidence_id = shadow.evidence_from_sections([_section()])[0].evidence_id
    schema = shadow._coverage_schema([evidence_id], ["I1"], ["LEGAL_EFFECT"])
    props = schema["properties"]["rules"]["items"]["properties"]
    assert props["evidence_id"]["enum"] == [evidence_id]
    assert props["issue_id"]["enum"] == ["I1"]
    assert props["role"]["enum"] == ["LEGAL_EFFECT"]


def test_stage_plan_has_same_identity_floor_and_candidate_intermediate_steps() -> None:
    baseline = [row[0] for row in shadow.stage_specs("baseline")]
    candidate = [row[0] for row in shadow.stage_specs(shadow.PROFILE)]
    assert baseline == [
        "question-source", "inherited-parent-evidence", "compiled-evidence-present",
    ]
    assert "legal-proposition-compile" in candidate
    assert "bounded-coverage-retry" in candidate
    assert "closed-applicability-verify" in candidate


def test_missing_coverage_can_never_produce_direct_mode() -> None:
    evidence = shadow.evidence_from_sections([_section()])
    result = shadow.compile_legal_review(
        QUESTION, evidence, _raw(facts=False, effect=False),
    )
    packet = shadow._answer_packet(result)
    assert packet["missing"]
    assert packet["answer_mode"] == "INSUFFICIENT"
    assert packet["direct_rule_answer_allowed"] is False


def test_rule_cap_violation_list_is_empty_for_sanitized_packet(monkeypatch) -> None:
    _, _, meta, _ = _attach(monkeypatch, [_raw(facts=False)])
    assert meta["rule_count"] <= 12
    assert meta["validation"]["rule_cap_violations"] == []


def test_exact_rule_and_closed_evidence_invariants_are_audited(monkeypatch) -> None:
    _, _, meta, _ = _attach(monkeypatch, [_raw(facts=False)])
    assert meta["validation"]["exact_rule_violations"] == []
    assert meta["validation"]["closed_evidence_violations"] == []
    assert meta["validation"]["missing_direct_violations"] == []
