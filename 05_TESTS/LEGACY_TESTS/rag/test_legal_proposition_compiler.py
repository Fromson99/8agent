from __future__ import annotations

from copy import deepcopy

import pytest

from lawrag.core.legal_graph.behavior import RELATION_BEHAVIOR_POLICIES
from lawrag.core.legal_graph.model import RelationPredicate
from lawrag.core.rag.answer import Section
from lawrag.core.rag.legal_proposition_compiler import (
    ApplicabilityState,
    CompilerStatus,
    EvidenceSpan,
    FactKind,
    LegalRole,
    PRODUCT_MODEL,
    SearchRoute,
    compile_legal_review,
    compile_with_llm,
    compiler_schema,
    evidence_from_sections,
)


QUESTION = "코스닥시장 금융회사가 심사업무를 외부 기관에 위탁할 수 있는가?"
SOURCE = "금융회사는 심사업무를 외부 기관에 위탁할 수 있다. 위탁의 효력은 계약 체결 시 발생한다."


def _evidence(
    evidence_id: str = "EV-1",
    *,
    document: str = "코스닥시장 업무규정",
    scope_id: str = "MARKET:KOSDAQ",
    text: str = SOURCE,
    verified: bool = True,
) -> EvidenceSpan:
    return EvidenceSpan(
        evidence_id=evidence_id,
        doc_id="DOC-1",
        node=10,
        document=document,
        path="제10조",
        text=text,
        scope_id=scope_id,
        verified=verified,
    )


def _base_raw(*, facts: list[dict] | None = None) -> dict:
    return {
        "issues": [{
            "issue_id": "I1",
            "question_span": "심사업무를 외부 기관에 위탁할 수 있는가",
            "required_roles": [],
            "facts": facts or [],
        }],
        "rules": [
            {
                "rule_id": "R1",
                "issue_id": "I1",
                "role": "GOVERNING_RULE",
                "evidence_id": "EV-1",
                "source_quote": "금융회사는 심사업무를 외부 기관에 위탁할 수 있다.",
                "slots": {
                    "ACTOR": ["금융회사"],
                    "ACTION": ["위탁"],
                    "OBJECT": ["심사업무"],
                },
                "relation_coverage_keys": [],
            },
            {
                "rule_id": "R2",
                "issue_id": "I1",
                "role": "LEGAL_EFFECT",
                "evidence_id": "EV-1",
                "source_quote": "위탁의 효력은 계약 체결 시 발생한다.",
                "slots": {"EFFECT": ["효력은 계약 체결 시 발생"]},
                "relation_coverage_keys": [],
            },
        ],
        "applicability": [],
    }


def test_complete_exact_packet_is_ready_only_for_assessment() -> None:
    result = compile_legal_review(QUESTION, [_evidence()], _base_raw())
    assert result.status == CompilerStatus.READY_FOR_ASSESSMENT
    assert result.direct_legal_conclusion_allowed is False
    assert result.to_dict()["direct_legal_conclusion_allowed"] is False
    assert result.rules[0]["proposition"] == result.rules[0]["source_quote"]


def test_question_span_outside_question_creates_fail_closed_fallback() -> None:
    raw = _base_raw()
    raw["issues"][0]["question_span"] = "질문에 없는 쟁점"
    result = compile_legal_review(QUESTION, [_evidence()], raw)
    assert result.status == CompilerStatus.BLOCKED_MISSING_COVERAGE
    assert "no_valid_issue:fallback_created" in result.validation_errors
    assert result.rules == ()


def test_fact_span_must_be_exact_question_text() -> None:
    raw = _base_raw(facts=[{
        "fact_id": "F1", "kind": "ACTOR", "question_span": "없는 회사",
    }])
    result = compile_legal_review(QUESTION, [_evidence()], raw)
    assert result.facts == ()
    assert "fact_span_not_exact:F1" in result.validation_errors


def test_rule_evidence_id_is_closed_to_menu() -> None:
    raw = _base_raw()
    raw["rules"][0]["evidence_id"] = "EV-NOT-IN-MENU"
    result = compile_legal_review(QUESTION, [_evidence()], raw)
    assert result.status == CompilerStatus.BLOCKED_MISSING_COVERAGE
    assert all(rule["rule_id"] != "R1" for rule in result.rules)


def test_source_quote_must_be_exact_contiguous_source_text() -> None:
    raw = _base_raw()
    raw["rules"][0]["source_quote"] = "금융회사는 무엇이든 위탁할 수 있다."
    result = compile_legal_review(QUESTION, [_evidence()], raw)
    assert all(rule["rule_id"] != "R1" for rule in result.rules)
    assert "source_quote_not_exact:R1" in result.validation_errors


def test_semantic_slot_must_be_inside_accepted_quote() -> None:
    raw = _base_raw()
    raw["rules"][0]["slots"]["OBJECT"] = ["대출업무"]
    result = compile_legal_review(QUESTION, [_evidence()], raw)
    assert all(rule["rule_id"] != "R1" for rule in result.rules)
    assert "slot_span_not_exact:R1:OBJECT" in result.validation_errors


def test_unknown_slot_kind_rejects_whole_rule() -> None:
    raw = _base_raw()
    raw["rules"][0]["slots"]["FREE_TEXT"] = ["위탁"]
    result = compile_legal_review(QUESTION, [_evidence()], raw)
    assert all(rule["rule_id"] != "R1" for rule in result.rules)
    assert "invalid_slot_kind:R1:FREE_TEXT" in result.validation_errors


def test_explicit_market_conflict_is_rejected() -> None:
    source = _evidence(
        document="유가증권시장 업무규정", scope_id="MARKET:KOSPI",
    )
    result = compile_legal_review(QUESTION, [source], _base_raw())
    assert result.rules == ()
    assert any(error.startswith("explicit_scope_conflict:") for error in result.validation_errors)


def test_unverified_source_cannot_satisfy_coverage() -> None:
    result = compile_legal_review(
        QUESTION, [_evidence(verified=False)], _base_raw(),
    )
    assert result.status == CompilerStatus.BLOCKED_MISSING_COVERAGE
    assert result.rules == ()


def test_issue_role_quota_prunes_surplus_atom() -> None:
    raw = _base_raw()
    surplus = deepcopy(raw["rules"][0])
    surplus["rule_id"] = "R3"
    raw["rules"].append(surplus)
    result = compile_legal_review(
        QUESTION, [_evidence()], raw,
        role_quotas={LegalRole.GOVERNING_RULE: 1},
    )
    assert [rule["rule_id"] for rule in result.rules] == ["R1", "R2"]
    assert any(error.startswith("role_quota_exceeded:") for error in result.validation_errors)


def test_global_atom_cap_is_enforced() -> None:
    result = compile_legal_review(
        QUESTION, [_evidence()], _base_raw(), global_rule_cap=1,
    )
    assert len(result.rules) == 1
    assert result.status == CompilerStatus.BLOCKED_MISSING_COVERAGE
    assert "global_rule_cap_exceeded:R2" in result.validation_errors


def test_unused_evidence_is_not_repackaged_as_context_claim() -> None:
    result = compile_legal_review(
        QUESTION,
        [_evidence(), _evidence("EV-2", text="관련 없는 부록이다.")],
        _base_raw(),
    )
    assert result.diagnostics["evidence_menu_count"] == 2
    assert result.diagnostics["context_claim_count"] == 0
    assert len(result.rules) == 2


@pytest.mark.parametrize("state", list(ApplicabilityState))
def test_all_four_applicability_states_are_preserved_when_verified(state) -> None:
    raw = _base_raw(facts=[{
        "fact_id": "F1", "kind": FactKind.ACTOR.value, "question_span": "금융회사",
    }])
    raw["applicability"] = [{
        "binding_id": "B1", "issue_id": "I1", "rule_id": "R1",
        "fact_id": "F1", "state": state.value,
    }]
    result = compile_legal_review(
        QUESTION, [_evidence()], raw, verified_binding_ids=["B1"],
    )
    assert result.applicability[0]["state"] == state.value
    assert result.applicability[0]["verified"] is True
    assert result.status == (
        CompilerStatus.BLOCKED_UNRESOLVED_FACTS
        if state == ApplicabilityState.UNRESOLVED
        else CompilerStatus.READY_FOR_ASSESSMENT
    )


def test_unverified_supported_binding_is_downgraded_and_blocked() -> None:
    raw = _base_raw(facts=[{
        "fact_id": "F1", "kind": "ACTOR", "question_span": "금융회사",
    }])
    raw["applicability"] = [{
        "binding_id": "B1", "issue_id": "I1", "rule_id": "R1",
        "fact_id": "F1", "state": "SUPPORTED",
    }]
    result = compile_legal_review(QUESTION, [_evidence()], raw)
    assert result.applicability[0]["state"] == "UNRESOLVED"
    assert result.status == CompilerStatus.BLOCKED_UNRESOLVED_FACTS
    assert "unverified_applicability_downgraded:B1" in result.validation_errors


def test_fact_without_binding_requests_clarification() -> None:
    raw = _base_raw(facts=[{
        "fact_id": "F1", "kind": "OBJECT", "question_span": "심사업무",
    }])
    result = compile_legal_review(QUESTION, [_evidence()], raw)
    assert result.status == CompilerStatus.BLOCKED_UNRESOLVED_FACTS
    assert result.clarification_requests[0]["question_span"] == "심사업무"


def test_missing_role_search_plan_reuses_only_question_spans() -> None:
    raw = _base_raw()
    raw["rules"] = raw["rules"][:1]
    result = compile_legal_review(QUESTION, [_evidence()], raw)
    plan = next(row for row in result.search_plan if row["required_role"] == "LEGAL_EFFECT")
    assert plan["query_spans"] == ["심사업무를 외부 기관에 위탁할 수 있는가"]
    assert plan["generated_search_terms"] == []


def test_relation_missing_coverage_uses_relation_route_and_question_span() -> None:
    result = compile_legal_review(
        QUESTION, [_evidence()], _base_raw(),
        relation_predicates=[RelationPredicate.ENTRUSTS_TASK],
    )
    relation_plan = [row for row in result.search_plan if row["issue_id"] == "RELATION"]
    assert relation_plan
    assert {row["route"] for row in relation_plan} == {SearchRoute.RELATION.value}
    assert all(row["query_spans"] for row in relation_plan)
    assert result.relation_behaviors[0]["status"] == "BLOCKED_MISSING_COVERAGE"


def test_complete_relation_coverage_bridges_to_behavior_ready() -> None:
    raw = _base_raw()
    predicate = RelationPredicate.ENTRUSTS_TASK
    raw["rules"][0]["relation_coverage_keys"] = [
        f"relation:{predicate.value}:{key}"
        for key in RELATION_BEHAVIOR_POLICIES[predicate].required_coverage
    ]
    result = compile_legal_review(
        QUESTION, [_evidence()], raw, relation_predicates=[predicate],
    )
    assert result.status == CompilerStatus.READY_FOR_ASSESSMENT
    assert result.relation_behaviors[0]["status"] == "READY_FOR_ASSESSMENT"
    assert not [row for row in result.coverage if row["state"] == "MISSING"]


def test_relation_coverage_key_is_closed_to_requested_predicates() -> None:
    raw = _base_raw()
    raw["rules"][0]["relation_coverage_keys"] = ["relation:ENTRUSTS_TASK:made_up"]
    result = compile_legal_review(
        QUESTION, [_evidence()], raw,
        relation_predicates=[RelationPredicate.ENTRUSTS_TASK],
    )
    assert "relation_coverage_outside_menu:R1:relation:ENTRUSTS_TASK:made_up" \
        in result.validation_errors


def test_schema_closes_evidence_relation_and_slot_menus() -> None:
    schema = compiler_schema(["EV-1"], ["relation:ENTRUSTS_TASK:legal_basis"])
    rule = schema["properties"]["rules"]["items"]["properties"]
    assert rule["evidence_id"]["enum"] == ["EV-1"]
    assert rule["relation_coverage_keys"]["items"]["enum"] == [
        "relation:ENTRUSTS_TASK:legal_basis"
    ]
    assert rule["slots"]["additionalProperties"] is False
    assert set(rule["slots"]["properties"]) == {kind.value for kind in compiler_slot_kinds()}


def test_schema_without_relation_contract_has_no_empty_enum_or_fake_sentinel() -> None:
    schema = compiler_schema(["EV-1"])
    rule = schema["properties"]["rules"]["items"]
    assert "relation_coverage_keys" not in rule["properties"]
    assert "relation_coverage_keys" not in rule["required"]

    def walk(value):
        if isinstance(value, dict):
            if "enum" in value:
                assert value["enum"]
                assert not any(str(item).startswith("__") for item in value["enum"])
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(schema)


def compiler_slot_kinds():
    from lawrag.core.rag.legal_proposition_compiler import SlotKind
    return list(SlotKind)


def test_section_adapter_is_stable_and_does_not_mutate_section() -> None:
    section = Section(
        n=1, doc_id="DOC", doc="코스닥시장 규정", node=3, path="제3조",
        page=None, kind="본문", matched="위탁", text="업무를 위탁한다.", block=2,
    )
    before = deepcopy(section)
    first = evidence_from_sections([section])
    second = evidence_from_sections([section])
    assert first == second
    assert first[0].evidence_id.startswith("EV-")
    assert first[0].scope_id == "MARKET:KOSDAQ"
    assert section == before


def test_duplicate_evidence_id_is_rejected_before_compilation() -> None:
    with pytest.raises(ValueError, match="duplicate evidence_id"):
        compile_legal_review(QUESTION, [_evidence(), _evidence()], _base_raw())


def test_llm_adapter_pins_product_model_and_still_runs_gate() -> None:
    class FakeLLM:
        def __init__(self):
            self.call = None

        def structured(self, *args, **kwargs):
            self.call = (args, kwargs)
            return _base_raw()

    llm = FakeLLM()
    result, receipt = compile_with_llm(QUESTION, [_evidence()], llm)
    assert result.status == CompilerStatus.READY_FOR_ASSESSMENT
    assert llm.call[1]["model"] == PRODUCT_MODEL
    assert receipt["model"] == "claude-haiku-4-5-20251001"
    assert receipt["main_wiring"] == "unchanged"
