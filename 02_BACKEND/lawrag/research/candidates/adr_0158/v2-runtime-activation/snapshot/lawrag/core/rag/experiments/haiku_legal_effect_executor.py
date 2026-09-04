"""원문 span으로 증명되는 법률효과 워크시트와 결정론 렌더러.

Haiku는 자유형 최종답변 대신 rule/decision/slot 후보만 만든다. 코드는 모든 quote가
실제 입력 원문에 있는지 확인하고, 유효한 구조만 고정 순서로 답변에 렌더링한다.
이 모듈은 shadow 실험 전용이며 운영 RAG에서 import하지 않는다.
"""

from __future__ import annotations

from typing import Any

from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL


TASK_KINDS = ("EXCEPTION_SWITCH", "SLOT_COVERAGE", "APPLICABILITY_GATE",
              "RULE_WITH_EXCEPTION")
RULE_ROLES = ("MAIN", "CONDITION", "EXCEPTION", "ALTERNATIVE", "FORMULA",
              "SCOPE", "DEFINITION", "EXCLUSION")
DECISION_KINDS = ("EXCEPTION_SWITCH", "APPLICABILITY_GATE", "OVERRIDE")

COMPILER_SYSTEM = (
    "너는 법률효과 컴파일러다. 최종 답변 문장을 자유롭게 작성하지 말고, 제공된 "
    "골든 원문만 실행 가능한 rule·decision·answer_slot 구조로 옮긴다.\n"
    "절대 규칙:\n"
    "1. 모든 rule.quote와 answer_slot.quote는 [골든 원문]에 연속된 문자열로 실제 "
    "존재해야 한다. 요약하거나 문자를 바꾸지 말고 그대로 복사한다.\n"
    "2. 본문, 단서, 예외, 대체규정, 적용대상, 산식·수치, 제외를 별도 rule로 만든다.\n"
    "3. 본문에 해당해도 단서가 적용되면 본문 효과가 배제되는지를 decision에 "
    "명시한다. 관련성이 아니라 법적 효과를 기록한다.\n"
    "4. 질문이 단수 표현을 써도 원문에 서로 다른 기준일·산정방식·예외가 있으면 "
    "answer_slots에 모두 기록한다.\n"
    "5. 원문만으로 확정할 수 없으면 추측하지 말고 unresolved에 적는다.\n"
    "6. 기준답변은 제공되지 않는다. task contract를 지키되 없는 사실을 만들지 마라."
)

COMPILER_SCHEMA = {
    "type": "object",
    "properties": {
        "task_kind": {"type": "string", "enum": list(TASK_KINDS)},
        "issue": {"type": "string"},
        "rules": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "source_evidence_id": {"type": "string"},
                "role": {"type": "string", "enum": list(RULE_ROLES)},
                "condition": {"type": "string"},
                "effect": {"type": "string"},
                "quote": {"type": "string"},
            },
            "required": ["id", "source_evidence_id", "role", "condition", "effect",
                         "quote"],
            "additionalProperties": False,
        }},
        "decisions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "kind": {"type": "string", "enum": list(DECISION_KINDS)},
                "main_rule_id": {"type": "string"},
                "condition_rule_id": {"type": "string"},
                "condition_satisfied": {"type": "boolean"},
                "alternative_rule_id": {"type": "string"},
                "result_if_true": {"type": "string"},
                "result_if_false": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["id", "kind", "main_rule_id", "condition_rule_id",
                         "condition_satisfied", "alternative_rule_id", "result_if_true",
                         "result_if_false", "reason"],
            "additionalProperties": False,
        }},
        "answer_slots": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "label": {"type": "string"},
                "value": {"type": "string"},
                "quote": {"type": "string"},
                "rule_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["key", "label", "value", "quote", "rule_ids"],
            "additionalProperties": False,
        }},
        "unresolved": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["task_kind", "issue", "rules", "decisions", "answer_slots",
                 "unresolved"],
    "additionalProperties": False,
}


def compiler_user(question: str, evidence: list[dict], task_kind: str,
                  task_contract: str) -> str:
    blocks = []
    for position, row in enumerate(evidence, 1):
        evidence_id = str(row.get("presented_id") or f"E{position}")
        blocks.append(
            f"[{evidence_id}] {row.get('document')} ▸ {row.get('path')}\n"
            f"{row.get('original_text', '')}"
        )
    return (
        f"[질문]\n{question}\n\n"
        f"[task kind]\n{task_kind}\n\n"
        f"[task contract]\n{task_contract}\n\n"
        f"[골든 원문]\n" + "\n\n".join(blocks) + "\n\n"
        "원문에 있는 모든 물질적 조건·예외·수치·기준일을 빠짐없이 컴파일하라."
    )


def validate_compilation(output: dict | None, evidence: list[dict],
                         expected_task: str) -> dict[str, Any]:
    """원문 증명과 참조 무결성을 검사한다. 실패한 부품은 실행에서 제외한다."""
    output = dict(output or {})
    source_by_id = {
        str(row.get("presented_id") or f"E{position}"): str(row.get("original_text") or "")
        for position, row in enumerate(evidence, 1)
    }
    errors = []
    if output.get("task_kind") != expected_task:
        errors.append(f"task_kind mismatch: {output.get('task_kind')} != {expected_task}")
    valid_rules, invalid_rules, seen = [], [], set()
    for rule in output.get("rules") or []:
        rule_id = str(rule.get("id") or "")
        source_id = str(rule.get("source_evidence_id") or "")
        quote = str(rule.get("quote") or "")
        reasons = []
        if not rule_id or rule_id in seen:
            reasons.append("missing_or_duplicate_rule_id")
        if source_id not in source_by_id:
            reasons.append("unknown_source_evidence_id")
        elif not quote or quote not in source_by_id[source_id]:
            reasons.append("quote_not_exact_source_span")
        if reasons:
            invalid_rules.append({"rule": rule, "reasons": reasons})
            continue
        seen.add(rule_id)
        valid_rules.append(dict(rule))
    valid_ids = {row["id"] for row in valid_rules}
    valid_slots, invalid_slots = [], []
    for slot in output.get("answer_slots") or []:
        quote = str(slot.get("quote") or "")
        refs = [str(value) for value in slot.get("rule_ids") or []]
        source_match = any(quote and quote in text for text in source_by_id.values())
        reasons = []
        if not source_match:
            reasons.append("slot_quote_not_exact_source_span")
        if not refs or any(value not in valid_ids for value in refs):
            reasons.append("slot_rule_reference_invalid")
        if reasons:
            invalid_slots.append({"slot": slot, "reasons": reasons})
        else:
            valid_slots.append(dict(slot))
    valid_decisions, invalid_decisions = [], []
    for decision in output.get("decisions") or []:
        refs = [str(decision.get("main_rule_id") or ""),
                str(decision.get("condition_rule_id") or "")]
        alternative = str(decision.get("alternative_rule_id") or "")
        if alternative:
            refs.append(alternative)
        missing = [value for value in refs if value not in valid_ids]
        if missing:
            invalid_decisions.append({"decision": decision,
                                      "reasons": ["invalid_rule_refs: " + ",".join(missing)]})
        else:
            valid_decisions.append(dict(decision))
    guarded_executable = not errors and (bool(valid_slots) or bool(valid_decisions))
    executable = guarded_executable and not output.get("unresolved")
    return {
        "task_kind": expected_task,
        "valid_rules": valid_rules,
        "invalid_rules": invalid_rules,
        "valid_slots": valid_slots,
        "invalid_slots": invalid_slots,
        "valid_decisions": valid_decisions,
        "invalid_decisions": invalid_decisions,
        "unresolved": list(output.get("unresolved") or []),
        "errors": errors,
        "executable": executable,
        "guarded_executable": guarded_executable,
    }


def execute_compilation(validated: dict, *, allow_unresolved: bool = False) -> dict[str, Any]:
    """LLM 재호출 없이 검증된 decision/slot을 고정 순서로 렌더링한다."""
    executable_key = "guarded_executable" if allow_unresolved else "executable"
    if not validated.get(executable_key):
        return {
            "answerable": False,
            "answer": "원문에서 법률효과를 안전하게 확정하지 못했습니다.",
            "trace": {"status": "fail_closed", "errors": validated.get("errors"),
                      "unresolved": validated.get("unresolved")},
        }
    rules = {row["id"]: row for row in validated.get("valid_rules") or []}
    lines, trace_decisions = [], []
    # SLOT_COVERAGE와 RULE_WITH_EXCEPTION은 질문에 구체적 사실값이 없을 수 있다.
    # 이때 compiler가 condition_satisfied=false를 임의 사실처럼 쓴 것을 실행하지 않고
    # 검증된 원칙·예외 슬롯을 모두 제시한다. 실제 분기 실행은 두 task에서만 한다.
    use_decisions = validated.get("task_kind") in (
        "EXCEPTION_SWITCH", "APPLICABILITY_GATE")
    for decision in (validated.get("valid_decisions") or []) if use_decisions else []:
        satisfied = bool(decision.get("condition_satisfied"))
        result = (str(decision.get("result_if_true") or "") if satisfied else
                  str(decision.get("result_if_false") or ""))
        lines.append(f"결론: {result}")
        chain = [decision.get("main_rule_id"), decision.get("condition_rule_id")]
        if satisfied and decision.get("alternative_rule_id"):
            chain.append(decision.get("alternative_rule_id"))
        quotes = [rules[value]["quote"] for value in chain if value in rules]
        trace_decisions.append({"decision_id": decision.get("id"),
                                "condition_satisfied": satisfied,
                                "selected_result": result,
                                "rule_chain": chain, "source_quotes": quotes})
        for quote in quotes:
            lines.append(f"- 원문: {quote}")
    trace_slots = []
    for slot in validated.get("valid_slots") or []:
        lines.append(f"{slot.get('label')}: {slot.get('value')}")
        lines.append(f"- 원문: {slot.get('quote')}")
        trace_slots.append({"key": slot.get("key"), "value": slot.get("value"),
                            "rule_ids": slot.get("rule_ids"),
                            "source_quote": slot.get("quote")})
    warnings = list(validated.get("unresolved") or []) if allow_unresolved else []
    if warnings:
        lines.append("주의: 원문만으로 미확정된 부수 사항은 실행 trace에 보존했습니다.")
    return {
        "answerable": True,
        "answer": "\n".join(lines),
        "trace": {"status": "executed_with_warnings" if warnings else "executed",
                  "decisions": trace_decisions, "slots": trace_slots,
                  "unresolved_warnings": warnings},
    }


__all__ = [
    "COMPILER_SCHEMA", "COMPILER_SYSTEM", "HAIKU_MODEL", "TASK_KINDS",
    "compiler_user", "execute_compilation", "validate_compilation",
]
