"""Atomic internal-rule compliance compiler and deterministic coverage gate.

The retriever is deliberately outside this module.  It receives one internal
article and the already selected external-law candidates, gives the product
model only closed evidence IDs, and validates every returned quote against the
source text.  The resulting gate distinguishes:

* ``상충``: an internal control contradicts an external requirement;
* ``미비``: a substantive external requirement has no internal control;
* ``부합``: every substantive requirement is satisfied or stricter; and
* ``재검토``: retrieval, grounding, or coverage is incomplete.

CONTEXT units preserve navigation but never satisfy the compliance denominator.
"""
from __future__ import annotations

from copy import deepcopy
import json
import time
from typing import Any, Mapping, Sequence


ROLES = (
    "GOVERNING_RULE", "DEFINITION", "CONDITION", "EXCEPTION",
    "PROCEDURE", "SANCTION", "DELEGATION", "COMPANION", "CONTEXT",
)
EFFECTS = (
    "REQUIREMENT", "PROHIBITION", "PERMISSION", "DEFINITION",
    "CONDITION", "EXCEPTION", "PROCEDURE", "DELEGATION", "SANCTION",
    "CONTEXT",
)
BINDING_STATUSES = (
    "SATISFIED", "STRICTER", "CONFLICT", "MISSING", "UNRESOLVED",
)

COMPILER_SYSTEM = """너는 법률답변을 작성하지 않는 내규·외규 비교 compiler다.
내규 조문 한 개와 이미 회수·검증된 외규 evidence 메뉴만 받는다.

1. issue.question_span은 질문의 연속 exact span만 쓴다.
2. internal_units와 requirements는 닫힌 evidence_id와 해당 원문의 연속 exact quote만 쓴다.
3. 외규의 의무·금지·허용·조건·예외·절차·위임을 하나의 requirement로 쪼갠다.
4. 각 substantive requirement를 내규 claim에 결속하고 SATISFIED, STRICTER, CONFLICT,
   MISSING, UNRESOLVED 중 하나로 표시한다. 내규 문구가 없으면 MISSING, 범위·행위자·시점이
   불확실하면 UNRESOLVED다.
5. 정의·배경처럼 비교 결론을 만들지 않는 원문은 role/effect CONTEXT로 둘 수 있다.
6. 원문에 없는 법률효과, evidence ID, quote를 만들지 않는다. 애매하면 UNRESOLVED다."""

COMPILER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "issues": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "question_span": {"type": "string"},
            },
            "required": ["issue_id", "question_span"],
            "additionalProperties": False,
        }},
        "internal_units": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "evidence_id": {"type": "string"},
                "issue_ids": {"type": "array", "items": {"type": "string"}},
                "role": {"type": "string", "enum": list(ROLES)},
                "quote": {"type": "string"},
            },
            "required": ["claim_id", "evidence_id", "issue_ids", "role", "quote"],
            "additionalProperties": False,
        }},
        "requirements": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "requirement_id": {"type": "string"},
                "evidence_id": {"type": "string"},
                "issue_ids": {"type": "array", "items": {"type": "string"}},
                "role": {"type": "string", "enum": list(ROLES)},
                "effect": {"type": "string", "enum": list(EFFECTS)},
                "quote": {"type": "string"},
            },
            "required": ["requirement_id", "evidence_id", "issue_ids", "role", "effect", "quote"],
            "additionalProperties": False,
        }},
        "bindings": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "requirement_id": {"type": "string"},
                "internal_claim_ids": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "string", "enum": list(BINDING_STATUSES)},
                "reason": {"type": "string"},
            },
            "required": ["requirement_id", "internal_claim_ids", "status", "reason"],
            "additionalProperties": False,
        }},
        "reason": {"type": "string"},
    },
    "required": ["issues", "internal_units", "requirements", "bindings", "reason"],
    "additionalProperties": False,
}


def internal_evidence_id(doc_id: str, node: int) -> str:
    return f"N:{doc_id}:{int(node)}"


def external_evidence_id(doc_id: str, node: int) -> str:
    return f"E:{doc_id}:{int(node)}"


def _issues(raw: Mapping[str, Any], question: str) -> tuple[list[dict], int]:
    output: list[dict] = []
    seen: set[str] = set()
    invalid = 0
    for number, row in enumerate(raw.get("issues") or (), 1):
        if not isinstance(row, Mapping):
            invalid += 1
            continue
        issue_id = str(row.get("issue_id") or f"I{number}").strip() or f"I{number}"
        span = str(row.get("question_span") or "").strip()
        if issue_id in seen or not span or span not in question:
            invalid += 1
            continue
        seen.add(issue_id)
        output.append({"issue_id": issue_id, "question_span": span[:500]})
        if len(output) == 4:
            break
    if not output:
        output = [{"issue_id": "I1", "question_span": question[:500] or "내규 비교"}]
    return output, invalid


def sanitize_compilation(
    raw: Mapping[str, Any] | None,
    question: str,
    internal_evidence: Mapping[str, str],
    external_evidence: Mapping[str, str],
) -> dict[str, Any]:
    """Validate IDs and exact quotes, then build an auditable coverage packet."""
    source = raw if isinstance(raw, Mapping) else {}
    issues, invalid_issues = _issues(source, question)
    issue_ids = {row["issue_id"] for row in issues}
    violations = {
        "invalid_issue_count": invalid_issues,
        "closed_id_violations": [],
        "exact_quote_violations": [],
        "invalid_role_or_effect": [],
        "invalid_binding_violations": [],
    }

    internal_units: list[dict] = []
    claim_ids: set[str] = set()
    for number, row in enumerate(source.get("internal_units") or (), 1):
        if not isinstance(row, Mapping):
            violations["invalid_binding_violations"].append(f"internal-unit:{number}")
            continue
        claim_id = str(row.get("claim_id") or f"N{number}").strip() or f"N{number}"
        evidence_id = str(row.get("evidence_id") or "")
        quote = str(row.get("quote") or "").strip()
        role = str(row.get("role") or "")
        linked = list(dict.fromkeys(str(value) for value in row.get("issue_ids") or ()
                                    if str(value) in issue_ids))
        if evidence_id not in internal_evidence:
            violations["closed_id_violations"].append(evidence_id or f"internal-unit:{number}")
            continue
        if not quote or quote not in str(internal_evidence[evidence_id]):
            violations["exact_quote_violations"].append(claim_id)
            continue
        if role not in ROLES or not linked or claim_id in claim_ids:
            violations["invalid_role_or_effect"].append(claim_id)
            continue
        claim_ids.add(claim_id)
        internal_units.append({
            "claim_id": claim_id, "evidence_id": evidence_id,
            "issue_ids": linked, "role": role, "quote": quote[:1200],
        })

    requirements: list[dict] = []
    requirement_ids: set[str] = set()
    used_external_ids: set[str] = set()
    for number, row in enumerate(source.get("requirements") or (), 1):
        if not isinstance(row, Mapping):
            violations["invalid_binding_violations"].append(f"requirement:{number}")
            continue
        requirement_id = str(row.get("requirement_id") or f"R{number}").strip() or f"R{number}"
        evidence_id = str(row.get("evidence_id") or "")
        quote = str(row.get("quote") or "").strip()
        role, effect = str(row.get("role") or ""), str(row.get("effect") or "")
        linked = list(dict.fromkeys(str(value) for value in row.get("issue_ids") or ()
                                    if str(value) in issue_ids))
        if evidence_id not in external_evidence:
            violations["closed_id_violations"].append(evidence_id or requirement_id)
            continue
        if not quote or quote not in str(external_evidence[evidence_id]):
            violations["exact_quote_violations"].append(requirement_id)
            continue
        if (role not in ROLES or effect not in EFFECTS or not linked
                or requirement_id in requirement_ids):
            violations["invalid_role_or_effect"].append(requirement_id)
            continue
        requirement_ids.add(requirement_id)
        used_external_ids.add(evidence_id)
        requirements.append({
            "requirement_id": requirement_id, "evidence_id": evidence_id,
            "issue_ids": linked, "role": role, "effect": effect,
            "quote": quote[:1200],
        })

    bindings: list[dict] = []
    bound: set[str] = set()
    for number, row in enumerate(source.get("bindings") or (), 1):
        if not isinstance(row, Mapping):
            violations["invalid_binding_violations"].append(f"binding:{number}")
            continue
        requirement_id = str(row.get("requirement_id") or "")
        status = str(row.get("status") or "")
        linked_claims = list(dict.fromkeys(str(value) for value in
                                           row.get("internal_claim_ids") or ()
                                           if str(value) in claim_ids))
        supplied_claims = [str(value) for value in row.get("internal_claim_ids") or ()]
        if (requirement_id not in requirement_ids or requirement_id in bound
                or status not in BINDING_STATUSES
                or len(linked_claims) != len(set(supplied_claims))
                or (status in {"SATISFIED", "STRICTER", "CONFLICT"} and not linked_claims)):
            violations["invalid_binding_violations"].append(
                requirement_id or f"binding:{number}")
            continue
        bound.add(requirement_id)
        bindings.append({
            "requirement_id": requirement_id,
            "internal_claim_ids": linked_claims,
            "status": status,
            "reason": str(row.get("reason") or "")[:800],
        })

    substantive_ids = {
        row["requirement_id"] for row in requirements
        if row["role"] != "CONTEXT" and row["effect"] != "CONTEXT"
    }
    unbound = sorted(substantive_ids - bound)
    invalid_count = sum(
        len(value) if isinstance(value, list) else int(value)
        for value in violations.values()
    )
    return {
        "schema_version": "internal-compliance-evidence-v1",
        "issues": issues,
        "internal_units": internal_units,
        "requirements": requirements,
        "bindings": bindings,
        "substantive_requirement_ids": sorted(substantive_ids),
        "unbound_requirement_ids": unbound,
        "context_evidence_ids": sorted(set(external_evidence) - used_external_ids),
        "selected_evidence_ids": sorted(used_external_ids),
        "validation": {**violations, "invalid_count": invalid_count},
        "reason": str(source.get("reason") or "")[:1000],
    }


def assess_packet(packet: Mapping[str, Any], retrieval_status: str = "ok") -> dict[str, Any]:
    """Turn a validated packet into a fail-closed compliance verdict."""
    substantive = set(packet.get("substantive_requirement_ids") or ())
    binding_by_requirement = {
        str(row.get("requirement_id")): str(row.get("status"))
        for row in packet.get("bindings") or () if isinstance(row, Mapping)
    }
    conflicts = sorted(rid for rid in substantive
                       if binding_by_requirement.get(rid) == "CONFLICT")
    missing = sorted(rid for rid in substantive
                     if binding_by_requirement.get(rid) == "MISSING")
    unresolved = sorted(
        rid for rid in substantive
        if binding_by_requirement.get(rid) in (None, "UNRESOLVED")
    )
    invalid_count = int((packet.get("validation") or {}).get("invalid_count") or 0)
    if conflicts:
        verdict, status = "상충", "CONFLICT"
    elif missing:
        verdict, status = "미비", "MISSING_INTERNAL_CONTROL"
    elif retrieval_status != "ok" or invalid_count or unresolved or not substantive:
        verdict, status = "재검토", "BLOCKED_INCOMPLETE_COVERAGE"
    else:
        verdict, status = "부합", "COVERAGE_SATISFIED"
    return {
        "verdict": verdict,
        "status": status,
        "coverage_closed": status == "COVERAGE_SATISFIED",
        "requirement_total": len(substantive),
        "conflict_requirement_ids": conflicts,
        "missing_requirement_ids": missing,
        "unresolved_requirement_ids": unresolved,
        "retrieval_status": retrieval_status,
        "invalid_count": invalid_count,
    }


def compile_compliance(
    llm: Any,
    *,
    question: str,
    internal_id: str,
    internal_text: str,
    external_rows: Sequence[Mapping[str, Any]],
    external_texts: Mapping[str, str],
    retrieval_status: str,
    deterministic_rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Call the product compiler once and return packet plus deterministic gate."""
    started = time.perf_counter()
    internal_evidence = {internal_id: internal_text}
    external_evidence = {
        str(row["evidence_id"]): str(external_texts.get(str(row["evidence_id"]), ""))
        for row in external_rows
    }
    menu = [{
        "evidence_id": str(row["evidence_id"]),
        "coordinate": [row.get("doc_id"), row.get("node")],
        "document": row.get("doc"), "path": row.get("path"),
        "mandatory": bool(row.get("mandatory")),
        "legal_meta": deepcopy(row.get("legal_meta") or {}),
        "text": external_evidence[str(row["evidence_id"])],
    } for row in external_rows]
    payload = {
        "question": question,
        "internal": {"evidence_id": internal_id, "text": internal_text},
        "external_menu": menu,
        "deterministic_quantity_rows": list(deterministic_rows),
    }
    raw = None if llm is None else llm.structured(
        "rag.compare.atomic_compliance_compiler",
        COMPILER_SYSTEM,
        json.dumps(payload, ensure_ascii=False),
        COMPILER_SCHEMA,
        max_tokens=4000,
        effort="low",
    )
    packet = sanitize_compilation(raw, question, internal_evidence, external_evidence)
    assessment = assess_packet(packet, retrieval_status)
    return {
        "enabled": True,
        "profile": "internal-compliance-atomic-v1",
        "model_contract": "claude-haiku-4-5-20251001",
        "call_count": 0 if llm is None else 1,
        "packet": packet,
        "assessment": assessment,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


__all__ = [
    "BINDING_STATUSES", "COMPILER_SCHEMA", "COMPILER_SYSTEM", "EFFECTS", "ROLES",
    "assess_packet", "compile_compliance", "external_evidence_id",
    "internal_evidence_id", "sanitize_compilation",
]
