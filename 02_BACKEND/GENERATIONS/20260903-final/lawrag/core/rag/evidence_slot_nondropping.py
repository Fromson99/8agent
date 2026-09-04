"""Required evidence-slot claim compiler for ADR-0130 research only.

The LLM may write the text of a claim, but it cannot choose or drop the
evidence attached to a satisfied required slot.  Each slot is a required
structured-output property and final ``evidence_ids`` are derived from those
emitted slot claims.  Missing slots create required limitations and never
block unrelated issues or the whole answer.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import re
from typing import Any, Mapping, Sequence

from lawrag.core.rag.answer import Answer, Section
from lawrag.core.rag.legal_proposition_compiler import (
    CompilationResult,
    PRODUCT_MODEL,
)


PROFILE_SLOT_ONLY = "evidence-slot-only-v1"
PROFILE_SLOT_TARGETED = "evidence-slot-targeted-v1"
MAX_ANSWER_TOKENS = 6000


SLOT_SYSTEM = """너는 법률 명제-근거 결속 compiler다. 최종 법률의견을 자유 형식으로
재구성하지 말고 서버가 준 required evidence slot마다 정확히 하나의 claim 문장을 작성한다.

1. claims 객체의 모든 key는 schema가 요구한 satisfied slot이고 빠뜨리거나 추가하지 않는다.
2. 각 claim은 해당 slot의 exact source quote만 근거로 삼는다. 다른 slot의 효과·예외·요건을
   섞거나 법문에 없는 사실·조건을 만들지 않는다.
3. limitations 객체의 모든 key는 evidence가 없는 missing slot이다. 확인이 필요한 법적 역할을
   단정 없이 설명한다.
4. summary는 claims와 limitations의 범위를 넘지 않는다. missing slot이 있는 쟁점은 조건부로
   표현하되 다른 쟁점과 답변 전체를 차단하지 않는다.
5. evidence ID를 선택하거나 출력하지 않는다. 서버가 slot에 이미 결속한 ID를 사용한다."""


@dataclass(frozen=True, slots=True)
class SlotAnswerResult:
    answer: Answer
    packet: Mapping[str, Any]
    violations: tuple[str, ...]


def build_slot_packet(result: CompilationResult) -> dict[str, Any]:
    """Convert compiler coverage into stable satisfied/missing required slots."""

    issue_by_id = {str(row["issue_id"]): dict(row) for row in result.issues}
    rules_by_id = {str(row["rule_id"]): dict(row) for row in result.rules}
    slots: list[dict[str, Any]] = []
    for number, coverage in enumerate(result.coverage, 1):
        if str(coverage.get("issue_id") or "") == "RELATION":
            continue
        issue_id = str(coverage.get("issue_id") or "")
        state = str(coverage.get("state") or "MISSING")
        rules = [
            rules_by_id[rule_id] for rule_id in coverage.get("rule_ids") or ()
            if rule_id in rules_by_id
        ]
        evidence_ids = list(dict.fromkeys(
            str(value) for value in coverage.get("evidence_ids") or () if str(value)
        ))
        slots.append({
            "slot_id": f"S{number:03d}",
            "issue_id": issue_id,
            "issue_question_span": str(issue_by_id.get(issue_id, {}).get("question_span") or ""),
            "required_role": str(coverage.get("required_role") or ""),
            "coverage_key": str(coverage.get("coverage_key") or ""),
            "state": state,
            "evidence_ids": evidence_ids,
            "rules": [{
                "rule_id": str(rule.get("rule_id") or ""),
                "evidence_id": str(rule.get("evidence_id") or ""),
                "role": str(rule.get("role") or ""),
                "source_quote": str(rule.get("source_quote") or ""),
                "slots": dict(rule.get("slots") or {}),
            } for rule in rules],
        })
    return {
        "schema_version": "evidence-slot-contract-v1",
        "compiler_status": str(result.status),
        "issues": [dict(row) for row in result.issues],
        "facts": [dict(row) for row in result.facts],
        "slots": slots,
        "satisfied_slot_ids": [row["slot_id"] for row in slots if row["state"] == "SATISFIED"],
        "missing_slot_ids": [row["slot_id"] for row in slots if row["state"] != "SATISFIED"],
    }


def slot_answer_schema(packet: Mapping[str, Any]) -> dict[str, Any]:
    satisfied = [str(value) for value in packet.get("satisfied_slot_ids") or ()]
    missing = [str(value) for value in packet.get("missing_slot_ids") or ()]
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "claims": {
                "type": "object",
                "properties": {slot_id: {"type": "string"} for slot_id in satisfied},
                "required": satisfied,
                "additionalProperties": False,
            },
            "limitations": {
                "type": "object",
                "properties": {slot_id: {"type": "string"} for slot_id in missing},
                "required": missing,
                "additionalProperties": False,
            },
        },
        "required": ["summary", "claims", "limitations"],
        "additionalProperties": False,
    }


def _clean_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(item or "").strip() for key, item in value.items()}


def validate_slot_output(packet: Mapping[str, Any], raw: object) -> tuple[dict[str, str], dict[str, str], list[str]]:
    satisfied = set(str(value) for value in packet.get("satisfied_slot_ids") or ())
    missing = set(str(value) for value in packet.get("missing_slot_ids") or ())
    value = raw if isinstance(raw, Mapping) else {}
    claims = _clean_mapping(value.get("claims"))
    limitations = _clean_mapping(value.get("limitations"))
    violations: list[str] = []
    for slot_id in sorted(satisfied - set(claims)):
        violations.append(f"missing_claim:{slot_id}")
    for slot_id in sorted(set(claims) - satisfied):
        violations.append(f"extra_claim:{slot_id}")
    for slot_id in sorted(key for key in satisfied & set(claims) if not claims[key]):
        violations.append(f"empty_claim:{slot_id}")
    for slot_id in sorted(missing - set(limitations)):
        violations.append(f"missing_limitation:{slot_id}")
    for slot_id in sorted(set(limitations) - missing):
        violations.append(f"extra_limitation:{slot_id}")
    for slot_id in sorted(key for key in missing & set(limitations) if not limitations[key]):
        violations.append(f"empty_limitation:{slot_id}")
    return claims, limitations, violations


def synthesize_slot_answer(
    llm: Any,
    question: str,
    result: CompilationResult,
    sections: Sequence[Section],
    *,
    kind: str = "rag.evidence_slot_nondropping.answer",
) -> SlotAnswerResult:
    packet = build_slot_packet(result)
    schema = slot_answer_schema(packet)
    user = (
        f"[질문]\n{question}\n\n[evidence-slot packet]\n"
        f"{json.dumps(packet, ensure_ascii=False, separators=(',', ':'))}"
    )
    raw = llm.structured(
        kind, SLOT_SYSTEM, user, schema,
        max_tokens=MAX_ANSWER_TOKENS, effort="high", model=PRODUCT_MODEL,
    )
    value = raw if isinstance(raw, Mapping) else {}
    claims, limitations, violations = validate_slot_output(packet, raw)
    slot_by_id = {str(row["slot_id"]): row for row in packet["slots"]}

    consumed_evidence: list[str] = []
    issue_claims: dict[str, list[str]] = defaultdict(list)
    issue_evidence: dict[str, list[str]] = defaultdict(list)
    issue_missing: dict[str, list[str]] = defaultdict(list)
    answer_lines: list[str] = []
    summary = str(value.get("summary") or "").strip()
    if summary:
        answer_lines.append(summary)
    else:
        violations.append("empty_summary")
    for slot_id in packet["satisfied_slot_ids"]:
        slot = slot_by_id[slot_id]
        claim = claims.get(slot_id, "")
        if not claim:
            continue
        evidence_ids = [str(item) for item in slot["evidence_ids"]]
        consumed_evidence.extend(evidence_ids)
        issue_id = str(slot["issue_id"])
        issue_claims[issue_id].append(claim)
        issue_evidence[issue_id].extend(evidence_ids)
        answer_lines.append(
            f"- [{slot['required_role']}] {claim} "
            f"(근거: {', '.join(evidence_ids)})"
        )
    for slot_id in packet["missing_slot_ids"]:
        slot = slot_by_id[slot_id]
        limitation = limitations.get(slot_id, "")
        if not limitation:
            continue
        issue_missing[str(slot["issue_id"])].append(str(slot["required_role"]))
        answer_lines.append(f"- [확인 필요: {slot['required_role']}] {limitation}")

    issue_results: list[dict[str, Any]] = []
    for issue in packet["issues"]:
        issue_id = str(issue["issue_id"])
        missing_roles = list(dict.fromkeys(issue_missing.get(issue_id, ())))
        issue_results.append({
            "issue_id": issue_id,
            "conclusion": " ".join(issue_claims.get(issue_id, ())),
            "conclusion_strength": "CONDITIONAL" if missing_roles else "DIRECT",
            "evidence_ids": list(dict.fromkeys(issue_evidence.get(issue_id, ()))),
            "unresolved_requirements": missing_roles,
        })

    allowed_ids = {
        str(rule["evidence_id"]) for slot in packet["slots"]
        for rule in slot.get("rules") or ()
    }
    closed_violations = sorted(set(consumed_evidence) - allowed_ids)
    violations.extend(f"closed_evidence:{value}" for value in closed_violations)
    answer = Answer(
        answer="\n".join(answer_lines),
        refs=[section.cite() for section in sections],
        answerable=bool(packet["satisfied_slot_ids"]),
        conclusion_strength=("CONDITIONAL" if packet["missing_slot_ids"] else "DIRECT"),
        evidence_ids=list(dict.fromkeys(consumed_evidence)),
        issue_results=issue_results,
        gate_violation=bool(violations),
        discards=sorted(set(violations)),
    )
    return SlotAnswerResult(
        answer=answer,
        packet=packet,
        violations=tuple(sorted(set(violations))),
    )


def packet_integrity(packet: Mapping[str, Any]) -> list[str]:
    """Validate that every satisfied slot has real rule/evidence bindings."""

    violations: list[str] = []
    seen: set[str] = set()
    for slot in packet.get("slots") or ():
        slot_id = str(slot.get("slot_id") or "")
        if not re.fullmatch(r"S[0-9]{3}", slot_id) or slot_id in seen:
            violations.append(f"slot_identity:{slot_id}")
        seen.add(slot_id)
        if slot.get("state") == "SATISFIED":
            evidence_ids = [str(value) for value in slot.get("evidence_ids") or ()]
            rules = list(slot.get("rules") or ())
            rule_ids = {str(rule.get("evidence_id") or "") for rule in rules}
            if not evidence_ids or not rules:
                violations.append(f"empty_satisfied_slot:{slot_id}")
            if set(evidence_ids) != rule_ids:
                violations.append(f"slot_rule_evidence_mismatch:{slot_id}")
            if any(not str(rule.get("source_quote") or "") for rule in rules):
                violations.append(f"empty_source_quote:{slot_id}")
        elif slot.get("evidence_ids") or slot.get("rules"):
            violations.append(f"missing_slot_has_evidence:{slot_id}")
    return sorted(set(violations))


__all__ = [
    "PROFILE_SLOT_ONLY",
    "PROFILE_SLOT_TARGETED",
    "SLOT_SYSTEM",
    "SlotAnswerResult",
    "build_slot_packet",
    "packet_integrity",
    "slot_answer_schema",
    "synthesize_slot_answer",
    "validate_slot_output",
]
