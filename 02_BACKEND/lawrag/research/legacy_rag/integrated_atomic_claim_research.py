"""Non-destructive atomic claim layer for ADR-0118.

The selected ADR-0114 integrated evidence is immutable input.  This module
never adds, removes, reorders, or caps a section.  It only attaches:

* soft question-span issues (answer checklist, never a hard gate),
* exact-source quote units bound to closed evidence IDs, and
* deterministic fallback quote units for otherwise unbound in-scope evidence.

Opaque requirement IDs and issue-result echo contracts are deliberately absent.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
import time
from typing import Any, Iterable, Mapping, Sequence

from lawrag.core.rag.answer import Section
from lawrag.runtime import retrieval_stage_ledger as stage_ledger
from lawrag.core.rag.index import Index
from lawrag.research.legacy_rag import integrated_legal_research as integrated


ISSUE_CAP = 4
UNIT_CAP = 20
FALLBACK_QUOTE_CHARS = 1000
_ROLES = (
    "GOVERNING_RULE", "DEFINITION", "CONDITION", "EXCEPTION",
    "PROCEDURE", "SANCTION", "COMPANION", "CONTEXT",
)
_STAGE_SPECS = (
    ("question-source", "source", ()),
    ("shared-integrated-evidence", "retrieve", ("question-source",)),
    ("soft-issue-claim-compile", "select", ("shared-integrated-evidence",)),
    ("atomic-claim-bind", "select", ("soft-issue-claim-compile",)),
    ("scope-safe-claim-gate", "filter", ("atomic-claim-bind",)),
    ("compiled-evidence-present", "present", ("scope-safe-claim-gate",)),
)


COMPILER_SYSTEM = """너는 법률답변을 작성하지 않는 soft issue·claim compiler다.
질문과 이미 선택·검증된 조문 메뉴를 받는다.

1. 질문의 독립 쟁점을 최대 4개로 나누되 question_span은 질문의 연속 exact span이어야 한다.
2. unit은 메뉴의 닫힌 evidence_id, issue_id, legal role, excerpt의 연속 exact quote만 사용한다.
3. quote를 요약하거나 법률효과를 새로 쓰지 않는다. question requirement ID를 만들지 않는다.
4. 답에 직접 도움 되는 unit만 최대 20개 낸다. 애매하면 빼도 된다. 코드가 조문을 삭제하지
   않으며 미선택 조문에는 별도 exact-source CONTEXT binding을 만든다.
5. 질문이 특정 시장을 명시하면 다른 시장 규범을 unit으로 선택하지 않는다. 공통 상위법은 가능하다."""

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
        "units": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "unit_id": {"type": "string"},
                "evidence_id": {"type": "string"},
                "issue_ids": {"type": "array", "items": {"type": "string"}},
                "role": {"type": "string", "enum": list(_ROLES)},
                "quote": {"type": "string"},
            },
            "required": ["unit_id", "evidence_id", "issue_ids", "role", "quote"],
            "additionalProperties": False,
        }},
        "reason": {"type": "string"},
    },
    "required": ["issues", "units", "reason"],
    "additionalProperties": False,
}


def _explicit_market_scopes(question: str) -> frozenset[str]:
    output = set()
    if "코스닥" in question:
        output.add("MARKET:KOSDAQ")
    if "유가증권시장" in question or "코스피" in question:
        output.add("MARKET:KOSPI")
    if "코넥스" in question:
        output.add("MARKET:KONEX")
    return frozenset(output)


def _scope_id(section: Section) -> str:
    lifecycle = ((section.legal_meta or {}).get("integrated_research") or {})
    value = str(lifecycle.get("scope_id") or "")
    if value:
        return value
    document = section.doc
    if "코스닥시장" in document:
        return "MARKET:KOSDAQ"
    if "유가증권시장" in document:
        return "MARKET:KOSPI"
    if "코넥스시장" in document:
        return "MARKET:KONEX"
    return f"INSTRUMENT:{section.doc_id}"


def _evidence_id(section: Section) -> str:
    return integrated._candidate_id((section.doc_id, int(section.node)))


def _menu(sections: Sequence[Section]) -> list[dict[str, Any]]:
    return [{
        "evidence_id": _evidence_id(section),
        "coordinate": [section.doc_id, section.node],
        "document": section.doc,
        "path": section.path,
        "scope_id": _scope_id(section),
        "excerpt": str(section.text or ""),
    } for section in sections]


def _sanitize(
    raw: Mapping[str, Any] | None,
    question: str,
    menu: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    menu_by_id = {str(row["evidence_id"]): row for row in menu}
    explicit = _explicit_market_scopes(question)
    issues: list[dict[str, str]] = []
    issue_ids: set[str] = set()
    invalid_issue_count = 0
    for number, row in enumerate((raw or {}).get("issues") or (), 1):
        if not isinstance(row, Mapping):
            invalid_issue_count += 1
            continue
        span = str(row.get("question_span") or "").strip()
        issue_id = str(row.get("issue_id") or f"I{number}").strip() or f"I{number}"
        if not span or span not in question or issue_id in issue_ids:
            invalid_issue_count += 1
            continue
        issue_ids.add(issue_id)
        issues.append({"issue_id": issue_id, "question_span": span[:500]})
        if len(issues) >= ISSUE_CAP:
            break
    if not issues:
        span = question.strip()[:500] or "질문"
        issues = [{"issue_id": "I1", "question_span": span}]
        issue_ids = {"I1"}

    units: list[dict[str, Any]] = []
    unit_ids: set[str] = set()
    claimed_evidence: set[str] = set()
    invalid_unit_count = 0
    scope_rejections = 0
    for number, row in enumerate((raw or {}).get("units") or (), 1):
        if not isinstance(row, Mapping):
            invalid_unit_count += 1
            continue
        evidence_id = str(row.get("evidence_id") or "")
        menu_row = menu_by_id.get(evidence_id) or {}
        scope_id = str(menu_row.get("scope_id") or "")
        quote = str(row.get("quote") or "").strip()
        excerpt = str(menu_row.get("excerpt") or "")
        role = str(row.get("role") or "")
        linked = list(dict.fromkeys(
            str(value) for value in row.get("issue_ids") or ()
            if str(value) in issue_ids
        ))
        wrong_market = (
            bool(explicit) and scope_id.startswith("MARKET:") and scope_id not in explicit
        )
        if wrong_market:
            scope_rejections += 1
            continue
        if (
            evidence_id not in menu_by_id or not quote or quote not in excerpt
            or role not in _ROLES or not linked
        ):
            invalid_unit_count += 1
            continue
        unit_id = str(row.get("unit_id") or f"U{number}").strip() or f"U{number}"
        if unit_id in unit_ids:
            unit_id = f"U{number}"
        unit_ids.add(unit_id)
        claimed_evidence.add(evidence_id)
        units.append({
            "unit_id": unit_id,
            "evidence_id": evidence_id,
            "scope_id": scope_id,
            "issue_ids": linked,
            "role": role,
            "quote": quote[:1200],
            "origin": "soft-compiler",
        })
        if len(units) >= UNIT_CAP:
            break

    # Non-destructive binding: every remaining in-scope evidence receives an
    # exact-source CONTEXT unit.  This cannot create an inferred proposition.
    for number, row in enumerate(menu, 1):
        evidence_id = str(row["evidence_id"])
        scope_id = str(row.get("scope_id") or "")
        if evidence_id in claimed_evidence:
            continue
        if explicit and scope_id.startswith("MARKET:") and scope_id not in explicit:
            continue
        quote = str(row.get("excerpt") or "")[:FALLBACK_QUOTE_CHARS].strip()
        if not quote:
            continue
        unit_id = f"CONTEXT-{number}-{evidence_id}"
        units.append({
            "unit_id": unit_id,
            "evidence_id": evidence_id,
            "scope_id": scope_id,
            "issue_ids": [],
            "role": "CONTEXT",
            "quote": quote,
            "origin": "deterministic-context",
        })
        claimed_evidence.add(evidence_id)

    claims = [{
        "claim_id": row["unit_id"],
        "evidence_id": row["evidence_id"],
        "scope_id": row["scope_id"],
        "issue_ids": row["issue_ids"],
        "role": row["role"],
        "proposition": row["quote"],
        "quote": row["quote"],
        "origin": row["origin"],
    } for row in units]
    return {
        "issues": issues,
        "units": units,
        "claims": claims,
        "selected_evidence_ids": list(dict.fromkeys(
            str(row["evidence_id"]) for row in units
        )),
        "reason": str((raw or {}).get("reason") or "")[:1000],
        "invalid_issue_count": invalid_issue_count,
        "invalid_unit_count": invalid_unit_count,
        "scope_rejection_count": scope_rejections,
    }


def _capture(
    index: Index,
    case_id: str,
    arm_id: str,
    sections: Sequence[Section],
) -> dict[str, Any]:
    coordinates = [(section.doc_id, int(section.node)) for section in sections]
    recorder = stage_ledger.StageLedgerRecorder(
        case_id, arm_id, stage_ledger.index_article_root_canonicalizer(index)
    )
    for stage_id, kind, parents in _STAGE_SPECS:
        after = [] if stage_id == "question-source" else coordinates
        recorder.record_stage(stage_id, kind, after, parent_stage_ids=parents)
    return recorder.capture()


def attach_compilation(
    index: Index,
    question: str,
    sections: Sequence[Section],
    *,
    llm: Any,
    case_id: str,
    arm_id: str,
    max_tokens: int = 4000,
) -> tuple[list[Section], dict[str, Any]]:
    """Attach soft atomic claims without changing the evidence coordinates."""

    started = time.perf_counter()
    output = deepcopy(list(sections))
    menu = _menu(output)
    user = f"[질문]\n{question}\n\n[선택 evidence 메뉴]\n{json.dumps(menu, ensure_ascii=False)}"
    compiler_started = time.perf_counter()
    raw = None if llm is None else llm.structured(
        "rag.integrated_atomic_claim.soft_compiler",
        COMPILER_SYSTEM,
        user,
        COMPILER_SCHEMA,
        max_tokens=max_tokens,
        effort="low",
    )
    compiler_wall_ms = round((time.perf_counter() - compiler_started) * 1000, 3)
    packet = _sanitize(raw, question, menu)
    compilation = {
        "schema_version": "integrated-atomic-claim-evidence-v4",
        "answer_mode": "ADVISORY",
        "direct_rule_answer_allowed": True,
        "selected_evidence_ids": packet["selected_evidence_ids"],
        "issues": packet["issues"],
        "units": packet["units"],
        "claims": packet["claims"],
        "coverage": [],
        "missing": [],
        "selected_scope_ids": list(dict.fromkeys(
            str(row["scope_id"]) for row in packet["units"]
        )),
        "reason": packet["reason"],
    }
    for section in output:
        section.legal_meta = {
            **dict(section.legal_meta or {}),
            "legal_compilation": deepcopy(compilation),
        }

    selected_ids = set(compilation["selected_evidence_ids"])
    all_ids = {_evidence_id(section) for section in output}
    claims = packet["claims"]
    claim_evidence_violations = sorted({
        str(row["evidence_id"]) for row in claims
        if str(row["evidence_id"]) not in all_ids
    })
    atomic_claim_violations = sorted({
        str(row["claim_id"]) for row in claims
        if row["proposition"] != row["quote"]
        or str(row["evidence_id"]) not in selected_ids
    })
    explicit = _explicit_market_scopes(question)
    scope_violations = sorted({
        str(row["scope_id"]) for row in claims
        if explicit and str(row["scope_id"]).startswith("MARKET:")
        and str(row["scope_id"]) not in explicit
    })
    meta = {
        "enabled": True,
        "profile": "integrated-atomic-claim-v4",
        "status": "attached",
        "before_count": len(sections),
        "after_count": len(output),
        "coordinates_unchanged": [
            (section.doc_id, section.node) for section in sections
        ] == [(section.doc_id, section.node) for section in output],
        "compiler_wall_ms": compiler_wall_ms,
        "compiler_max_tokens": max_tokens,
        "issue_count": len(packet["issues"]),
        "unit_count": len(packet["units"]),
        "soft_unit_count": sum(row["origin"] == "soft-compiler" for row in packet["units"]),
        "context_unit_count": sum(row["origin"] == "deterministic-context" for row in packet["units"]),
        "claim_count": len(claims),
        "invalid_issue_count": packet["invalid_issue_count"],
        "invalid_unit_count": packet["invalid_unit_count"],
        "scope_rejection_count": packet["scope_rejection_count"],
        "validation": {
            "claim_evidence_violations": claim_evidence_violations,
            "atomic_claim_violations": atomic_claim_violations,
            "scope_violations": scope_violations,
            "coordinate_violations": [] if len(output) == len(sections) else ["count"],
        },
        "evidence_packet": compilation,
        "stage_capture": _capture(index, case_id, arm_id, output),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    return output, meta


__all__ = [
    "COMPILER_SCHEMA", "COMPILER_SYSTEM", "attach_compilation", "_sanitize",
]
