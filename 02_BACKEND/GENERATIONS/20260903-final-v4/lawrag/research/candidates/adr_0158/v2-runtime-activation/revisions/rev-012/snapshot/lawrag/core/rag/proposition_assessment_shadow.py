"""Compact proposition/applicability shadow adapter for ADR-0120.

The adapter consumes an immutable selected ``Section`` list.  It does not
retrieve, add, remove, reorder, or truncate evidence.  Its product-changing
work is limited to a compact compiler packet attached to ``legal_meta``:

    exact proposition compile
      -> at most one same-menu missing-coverage retry
      -> closed-ID applicability verification
      -> deterministic answer-mode assessment

Every LLM response is advisory until it has passed the ADR-0119 deterministic
compiler again.  This module is research-only and is not imported by API or
MAIN.
"""

from __future__ import annotations

from copy import deepcopy
import json
import time
from typing import Any, Mapping, Sequence

from lawrag.core.rag.answer import Section
from lawrag.core.rag.experiments import retrieval_stage_ledger as stage_ledger
from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_proposition_compiler import (
    ApplicabilityState,
    CompilerStatus,
    EvidenceSpan,
    GLOBAL_RULE_CAP,
    LegalRole,
    PRODUCT_MODEL,
    compile_legal_review,
    compile_with_llm,
    compiler_schema,
    evidence_from_sections,
)


PROFILE = "proposition-assessment-shadow-v1"
COMPILER_MAX_TOKENS = 8000
RETRY_MAX_TOKENS = 5000
VERIFIER_MAX_TOKENS = 4000

_BASELINE_STAGES = (
    ("question-source", "source", ()),
    ("inherited-parent-evidence", "retrieve", ("question-source",)),
    ("compiled-evidence-present", "present", ("inherited-parent-evidence",)),
)
_CANDIDATE_STAGES = (
    ("question-source", "source", ()),
    ("inherited-parent-evidence", "retrieve", ("question-source",)),
    ("legal-proposition-compile", "select", ("inherited-parent-evidence",)),
    ("bounded-coverage-retry", "select", ("legal-proposition-compile",)),
    ("closed-applicability-verify", "filter", ("bounded-coverage-retry",)),
    ("compiled-evidence-present", "present", ("closed-applicability-verify",)),
)


COVERAGE_RETRY_SYSTEM = """너는 최종 답변을 쓰지 않는 누락 법률근거 보충기다.
질문, 이미 검증된 issue, 누락 role, 서버 evidence 메뉴만 사용한다.
누락 role을 실제로 충족하는 source_quote가 메뉴에 있을 때만 rule을 낸다.
issue_id와 evidence_id는 닫힌 메뉴에서 고르고 source_quote와 모든 slot은 evidence text의
연속 exact span을 그대로 복사한다. 검색어·법률효과·사실을 새로 만들지 않는다."""


APPLICABILITY_VERIFIER_SYSTEM = """너는 최종 법률답변을 쓰지 않는 사실-규범 포섭 검증기다.
서버가 준 fact와 rule의 닫힌 ID만 사용한다. 각 material fact를 관련 rule에 결속하고 상태를
SUPPORTED, CONTRADICTED, UNRESOLVED, NOT_APPLICABLE 중 하나로 고른다.
질문에 없는 사실, rule quote에 없는 요건, 새로운 법률효과를 만들지 않는다. 의미상 판단이
조금이라도 더 필요한 경우 UNRESOLVED로 둔다."""


def stage_specs(arm_id: str) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    return _BASELINE_STAGES if arm_id == "baseline" else _CANDIDATE_STAGES


def _evidence_menu(evidence: Sequence[EvidenceSpan]) -> list[dict[str, Any]]:
    return [item.public() for item in evidence]


def _canonical_raw(result) -> dict[str, Any]:
    facts_by_issue: dict[str, list[dict[str, Any]]] = {}
    for fact in result.facts:
        facts_by_issue.setdefault(str(fact["issue_id"]), []).append({
            "fact_id": fact["fact_id"],
            "kind": fact["kind"],
            "question_span": fact["question_span"],
        })
    issues = [{
        "issue_id": issue["issue_id"],
        "question_span": issue["question_span"],
        "required_roles": list(issue.get("required_roles") or ()),
        "facts": facts_by_issue.get(str(issue["issue_id"]), []),
    } for issue in result.issues]
    rules = [{
        "rule_id": rule["rule_id"],
        "issue_id": rule["issue_id"],
        "role": rule["role"],
        "evidence_id": rule["evidence_id"],
        "source_quote": rule["source_quote"],
        "slots": deepcopy(rule.get("slots") or {}),
        "relation_coverage_keys": [
            key for key in rule.get("coverage_keys") or ()
            if str(key).startswith("relation:")
        ],
    } for rule in result.rules]
    applicability = [{
        "binding_id": binding["binding_id"],
        "issue_id": binding["issue_id"],
        "rule_id": binding["rule_id"],
        "fact_id": binding["fact_id"],
        "state": binding.get("proposed_state") or binding["state"],
    } for binding in result.applicability]
    return {"issues": issues, "rules": rules, "applicability": applicability}


def _coverage_schema(
    evidence_ids: Sequence[str], issue_ids: Sequence[str], missing_roles: Sequence[str],
) -> dict[str, Any]:
    rule_properties = deepcopy(
        compiler_schema(evidence_ids)["properties"]["rules"]["items"]["properties"]
    )
    rule_properties["issue_id"] = {"type": "string", "enum": list(issue_ids)}
    rule_properties["role"] = {"type": "string", "enum": list(missing_roles)}
    required = [
        "rule_id", "issue_id", "role", "evidence_id", "source_quote", "slots",
    ]
    if "relation_coverage_keys" in rule_properties:
        required.append("relation_coverage_keys")
    return {
        "type": "object",
        "properties": {
            "rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": rule_properties,
                    "required": required,
                    "additionalProperties": False,
                },
            }
        },
        "required": ["rules"],
        "additionalProperties": False,
    }


def _retry_coverage(
    question: str,
    evidence: Sequence[EvidenceSpan],
    result,
    llm: Any,
) -> tuple[Any, dict[str, Any]]:
    missing = [
        row for row in result.coverage
        if row["state"] == "MISSING" and row["issue_id"] != "RELATION"
    ]
    receipt: dict[str, Any] = {
        "attempted": False,
        "missing_before": len(missing),
        "missing_after": len(missing),
        "raw_output": None,
    }
    if not missing or llm is None:
        return result, receipt
    missing_roles = list(dict.fromkeys(str(row["required_role"]) for row in missing))
    issue_ids = [str(row["issue_id"]) for row in result.issues]
    schema = _coverage_schema(
        [item.evidence_id for item in evidence], issue_ids, missing_roles,
    )
    payload = {
        "question": question,
        "issues": list(result.issues),
        "missing_coverage": missing,
        "search_plan": list(result.search_plan),
        "evidence_menu": _evidence_menu(evidence),
    }
    raw = llm.structured(
        "rag.proposition_assessment.coverage_retry",
        COVERAGE_RETRY_SYSTEM,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        schema,
        max_tokens=RETRY_MAX_TOKENS,
        effort="low",
        model=PRODUCT_MODEL,
    )
    canonical = _canonical_raw(result)
    retry_rules = list((raw or {}).get("rules") or ()) if isinstance(raw, Mapping) else []
    canonical["rules"].extend(retry_rules)
    retried = compile_legal_review(question, evidence, canonical)
    missing_after = sum(row["state"] == "MISSING" for row in retried.coverage)
    receipt.update({
        "attempted": True,
        "missing_after": missing_after,
        "raw_output": raw,
        "accepted_rule_delta": max(0, len(retried.rules) - len(result.rules)),
        "validation_errors": list(retried.validation_errors),
    })
    return retried, receipt


def _applicability_schema(result) -> dict[str, Any]:
    issue_ids = [str(row["issue_id"]) for row in result.issues]
    rule_ids = [str(row["rule_id"]) for row in result.rules]
    fact_ids = [str(row["fact_id"]) for row in result.facts]
    return {
        "type": "object",
        "properties": {
            "bindings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "binding_id": {"type": "string"},
                        "issue_id": {"type": "string", "enum": issue_ids},
                        "rule_id": {"type": "string", "enum": rule_ids},
                        "fact_id": {"type": "string", "enum": fact_ids},
                        "state": {
                            "type": "string",
                            "enum": [state.value for state in ApplicabilityState],
                        },
                    },
                    "required": [
                        "binding_id", "issue_id", "rule_id", "fact_id", "state",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["bindings"],
        "additionalProperties": False,
    }


def _verify_applicability(
    question: str,
    evidence: Sequence[EvidenceSpan],
    result,
    llm: Any,
) -> tuple[Any, dict[str, Any]]:
    receipt: dict[str, Any] = {
        "attempted": False,
        "raw_output": None,
        "verified_binding_count": 0,
    }
    if not result.facts or not result.rules or llm is None:
        return result, receipt
    payload = {
        "question": question,
        "issues": list(result.issues),
        "facts": list(result.facts),
        "rules": list(result.rules),
    }
    raw = llm.structured(
        "rag.proposition_assessment.applicability_verifier",
        APPLICABILITY_VERIFIER_SYSTEM,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        _applicability_schema(result),
        max_tokens=VERIFIER_MAX_TOKENS,
        effort="low",
        model=PRODUCT_MODEL,
    )
    canonical = _canonical_raw(result)
    bindings = list((raw or {}).get("bindings") or ()) if isinstance(raw, Mapping) else []
    canonical["applicability"] = bindings
    verified_ids = [
        str(row.get("binding_id") or "") for row in bindings
        if isinstance(row, Mapping) and str(row.get("binding_id") or "")
    ]
    verified = compile_legal_review(
        question, evidence, canonical, verified_binding_ids=verified_ids,
    )
    receipt.update({
        "attempted": True,
        "raw_output": raw,
        "verified_binding_count": sum(
            bool(row.get("verified")) for row in verified.applicability
        ),
        "validation_errors": list(verified.validation_errors),
    })
    return verified, receipt


def _answer_mode(result) -> str:
    if result.status == CompilerStatus.READY_FOR_ASSESSMENT:
        return "DIRECT_RULE"
    if result.status == CompilerStatus.BLOCKED_UNRESOLVED_FACTS:
        return "CONDITIONAL_APPLICATION"
    return "INSUFFICIENT"


def _answer_packet(result) -> dict[str, Any]:
    mode = _answer_mode(result)
    claims = [{
        "claim_id": rule["rule_id"],
        "evidence_id": rule["evidence_id"],
        "issue_ids": [rule["issue_id"]],
        "role": rule["role"],
        "proposition": rule["source_quote"],
        "quote": rule["source_quote"],
        "slots": deepcopy(rule.get("slots") or {}),
        "origin": "exact-proposition-compiler",
    } for rule in result.rules]
    missing = [row for row in result.coverage if row["state"] == "MISSING"]
    return {
        "schema_version": PROFILE,
        "answer_mode": mode,
        "direct_rule_answer_allowed": mode == "DIRECT_RULE",
        "direct_legal_conclusion_allowed_by_compiler": False,
        "selected_evidence_ids": list(dict.fromkeys(
            str(rule["evidence_id"]) for rule in result.rules
        )),
        "selected_scope_ids": list(dict.fromkeys(
            str(rule["scope_id"]) for rule in result.rules
        )),
        "issues": list(result.issues),
        "units": claims,
        "claims": claims,
        "entailments": list(result.applicability),
        "coverage": list(result.coverage),
        "missing": missing,
        "search_plan": list(result.search_plan),
        "clarification_requests": list(result.clarification_requests),
        "reason": result.status.value,
    }


def capture_stages(
    index: Index,
    case_id: str,
    arm_id: str,
    sections: Sequence[Section],
) -> dict[str, Any]:
    coordinates = [(section.doc_id, int(section.node)) for section in sections]
    recorder = stage_ledger.StageLedgerRecorder(
        case_id, arm_id, stage_ledger.index_article_root_canonicalizer(index)
    )
    for stage_id, kind, parents in stage_specs(arm_id):
        after = [] if stage_id == "question-source" else coordinates
        recorder.record_stage(stage_id, kind, after, parent_stage_ids=parents)
    return recorder.capture()


def attach_shadow_compilation(
    index: Index,
    question: str,
    sections: Sequence[Section],
    *,
    llm: Any,
    case_id: str,
    arm_id: str = PROFILE,
) -> tuple[list[Section], dict[str, Any]]:
    """Attach a compact assessment packet without modifying evidence identity."""

    started = time.perf_counter()
    output = deepcopy(list(sections))
    before_coordinates = [(row.doc_id, row.node) for row in output]
    evidence = evidence_from_sections(output)
    compile_started = time.perf_counter()
    first, compile_receipt = compile_with_llm(
        question, evidence, llm, max_tokens=COMPILER_MAX_TOKENS,
    )
    compile_ms = round((time.perf_counter() - compile_started) * 1000, 3)
    retry_started = time.perf_counter()
    completed, retry_receipt = _retry_coverage(
        question, evidence, first, llm,
    )
    retry_ms = round((time.perf_counter() - retry_started) * 1000, 3)
    verify_started = time.perf_counter()
    assessed, verifier_receipt = _verify_applicability(
        question, evidence, completed, llm,
    )
    verifier_ms = round((time.perf_counter() - verify_started) * 1000, 3)
    packet = _answer_packet(assessed)
    for section in output:
        section.legal_meta = {
            **dict(section.legal_meta or {}),
            "legal_compilation": deepcopy(packet),
        }

    after_coordinates = [(row.doc_id, row.node) for row in output]
    exact_rule_violations = sorted({
        str(rule["rule_id"]) for rule in assessed.rules
        if rule["source_quote"] != rule["proposition"]
    })
    selected_ids = set(packet["selected_evidence_ids"])
    closed_evidence_violations = sorted({
        str(rule["evidence_id"]) for rule in assessed.rules
        if str(rule["evidence_id"]) not in {item.evidence_id for item in evidence}
    })
    missing_direct_violations = (
        ["missing-coverage-direct"]
        if packet["missing"] and packet["answer_mode"] == "DIRECT_RULE" else []
    )
    meta = {
        "enabled": True,
        "profile": PROFILE,
        "status": assessed.status.value,
        "before_count": len(sections),
        "after_count": len(output),
        "coordinates_unchanged": before_coordinates == after_coordinates,
        "context_claim_count": 0,
        "rule_count": len(assessed.rules),
        "issue_count": len(assessed.issues),
        "fact_count": len(assessed.facts),
        "binding_count": len(assessed.applicability),
        "missing_coverage_count": sum(
            row["state"] == "MISSING" for row in assessed.coverage
        ),
        "unresolved_fact_count": assessed.diagnostics["unresolved_fact_count"],
        "compile_ms": compile_ms,
        "coverage_retry_ms": retry_ms,
        "verifier_ms": verifier_ms,
        "compiler_receipt": compile_receipt,
        "coverage_retry_receipt": retry_receipt,
        "verifier_receipt": verifier_receipt,
        "validation_errors": list(assessed.validation_errors),
        "validation": {
            "exact_rule_violations": exact_rule_violations,
            "closed_evidence_violations": closed_evidence_violations,
            "rule_cap_violations": (
                [f"rules:{len(assessed.rules)}"]
                if len(assessed.rules) > GLOBAL_RULE_CAP else []
            ),
            "context_claim_violations": [],
            "coordinate_violations": (
                [] if before_coordinates == after_coordinates else ["coordinates"]
            ),
            "missing_direct_violations": missing_direct_violations,
        },
        "evidence_packet": packet,
        "stage_capture": capture_stages(index, case_id, arm_id, output),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    return output, meta


__all__ = [
    "APPLICABILITY_VERIFIER_SYSTEM",
    "COVERAGE_RETRY_SYSTEM",
    "PROFILE",
    "attach_shadow_compilation",
    "capture_stages",
    "stage_specs",
]
