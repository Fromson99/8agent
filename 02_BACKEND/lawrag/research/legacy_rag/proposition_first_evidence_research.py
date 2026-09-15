"""Proposition-first, evidence-preserving research pipeline for ADR-0129.

The inherited ADR-0118 evidence is an immutable floor.  The compiler first
derives question issues, facts, required legal roles and exact-source rules.
Only missing roles may trigger at most two gold-blind LegalClosure probes.
The expanded evidence is compiled again and answered claim-locally without a
question-wide coverage block.  This module is not imported by MAIN or the API.
"""
from __future__ import annotations

from copy import deepcopy
import json
import time
from typing import Any, Mapping, Sequence

from lawrag.core.rag import answer as answer_mod
from lawrag.research.legacy_rag import integrated_legal_research as integrated
from lawrag.core.rag import legalclosure_runtime
from lawrag.core.rag.answer import Answer, Section
from lawrag.runtime import retrieval_stage_ledger as stage_ledger
from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_proposition_compiler import (
    EvidenceSpan,
    PRODUCT_MODEL,
    compile_with_llm,
)


PROFILE = "proposition-first-evidence-v1"
INITIAL_COMPILER_MAX_TOKENS = 7000
FINAL_COMPILER_MAX_TOKENS = 8000
TARGETED_PROBE_CAP = 2
TARGETED_ADD_CAP = 4
FINAL_EVIDENCE_CAP = 32

_ROLE_PRIORITY = {
    "GOVERNING_RULE": 0,
    "LEGAL_EFFECT": 1,
    "DEFINITION": 2,
    "EXCEPTION": 3,
    "CONDITION": 4,
    "ACTOR_SCOPE": 5,
    "NUMERIC": 6,
    "TEMPORAL": 7,
    "PROCEDURE": 8,
    "AUTHORITY": 9,
    "COMPANION": 10,
    "SANCTION": 11,
}
_ROLE_HINT = {
    "GOVERNING_RULE": "직접 적용 지배규정 본문",
    "LEGAL_EFFECT": "법률효과 의무 허용 금지",
    "DEFINITION": "정의 용어의 뜻",
    "EXCEPTION": "단서 예외 제외 불구하고",
    "CONDITION": "요건 조건 경우",
    "ACTOR_SCOPE": "적용대상 주체 범위",
    "NUMERIC": "수치 비율 금액 기간",
    "TEMPORAL": "시행일 기준일 경과조치",
    "PROCEDURE": "승인 신고 보고 절차",
    "AUTHORITY": "권한 위임 위탁 대리",
    "COMPANION": "준용 인용 연결 조문",
    "SANCTION": "벌칙 과태료 제재",
}

_BASELINE_STAGES = (
    ("question-source", "source", ()),
    ("inherited-parent-evidence", "retrieve", ("question-source",)),
    ("inherited-identity-filter", "filter", ("inherited-parent-evidence",)),
    ("compiled-evidence-present", "present", ("inherited-identity-filter",)),
)
_CANDIDATE_STAGES = (
    ("question-source", "source", ()),
    ("inherited-parent-evidence", "retrieve", ("question-source",)),
    ("proposition-first-compile", "select", ("inherited-parent-evidence",)),
    ("missing-role-targeted-retrieve", "retrieve", ("proposition-first-compile",)),
    ("provenance-canonicalize", "canonicalize", ("missing-role-targeted-retrieve",)),
    ("role-evidence-select", "select", ("provenance-canonicalize",)),
    ("compiled-evidence-present", "present", ("role-evidence-select",)),
)


PROPOSITION_FIRST_ANSWER_SYSTEM = answer_mod.ANSWER_SYSTEM + """
⑦ [법률 evidence compiler]의 issues를 모두 검토하고 issue_results에 각 issue_id를 정확히
한 번씩 낸다. 각 결론은 그 issue에 연결된 exact-source claim의 evidence_id만 사용한다.
⑧ coverage가 MISSING인 역할은 해당 쟁점만 CONDITIONAL 또는 INSUFFICIENT로 표시하고
unresolved_requirements에 누락 role을 적는다. 다른 쟁점과 답변 전체를 차단하지 않는다.
⑨ evidence_id는 닫힌 목록에서만 고른다. 법문 인용과 질문 사실의 포섭을 구별하고, 원문에
없는 조건·예외·효과를 만들지 않는다. 답변에는 결론을 먼저 쓰고 필요한 정의·예외·절차를
빠뜨리지 않는다."""


def stage_specs(arm_id: str) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    return _BASELINE_STAGES if arm_id == "baseline" else _CANDIDATE_STAGES


def _candidate_id(section: Section) -> str:
    meta = dict(section.legal_meta or {})
    research = dict(meta.get("integrated_research") or {})
    value = str(research.get("candidate_id") or "")
    if value:
        return value
    return integrated._candidate_id((str(section.doc_id), int(section.node)))


def _ensure_candidate_id(section: Section) -> None:
    meta = dict(section.legal_meta or {})
    research = dict(meta.get("integrated_research") or {})
    research["candidate_id"] = _candidate_id(section)
    meta["integrated_research"] = research
    section.legal_meta = meta


def evidence_from_sections(sections: Sequence[Section]) -> tuple[EvidenceSpan, ...]:
    rows: list[EvidenceSpan] = []
    used: set[str] = set()
    for section in sections:
        _ensure_candidate_id(section)
        evidence_id = _candidate_id(section)
        if evidence_id in used:
            raise ValueError(f"duplicate evidence ID: {evidence_id}")
        used.add(evidence_id)
        meta = dict(section.legal_meta or {})
        research = dict(meta.get("integrated_research") or {})
        rows.append(EvidenceSpan(
            evidence_id=evidence_id,
            doc_id=str(section.doc_id),
            node=int(section.node) if section.node is not None else None,
            document=str(section.doc),
            path=str(section.path),
            text=str(section.text or ""),
            scope_id=str(research.get("scope_id") or f"INSTRUMENT:{section.doc_id}"),
            verified=not bool(meta.get("verification_error")),
        ))
    return tuple(rows)


def _missing_targets(result) -> list[dict[str, Any]]:
    rows = [
        dict(row) for row in result.coverage
        if row.get("state") == "MISSING" and row.get("issue_id") != "RELATION"
    ]
    rows.sort(key=lambda row: (
        _ROLE_PRIORITY.get(str(row.get("required_role") or ""), 99),
        str(row.get("issue_id") or ""),
    ))
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row.get("issue_id") or ""), str(row.get("required_role") or ""))
        if key in seen:
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) >= TARGETED_PROBE_CAP:
            break
    return selected


def _target_query(question: str, result, target: Mapping[str, Any]) -> str:
    issue_id = str(target.get("issue_id") or "")
    role = str(target.get("required_role") or "")
    issue = next((row for row in result.issues if row.get("issue_id") == issue_id), {})
    span = str(issue.get("question_span") or question)
    hint = _ROLE_HINT.get(role, role)
    return " ".join(dict.fromkeys(part for part in (span, hint, question) if part))


def _targeted_expand(
    index: Index,
    question: str,
    sections: Sequence[Section],
    initial_result,
    llm: Any,
) -> tuple[list[Section], list[dict[str, Any]]]:
    output = deepcopy(list(sections))
    seen = {(str(row.doc_id), int(row.node)) for row in output}
    receipts: list[dict[str, Any]] = []
    remaining = max(0, FINAL_EVIDENCE_CAP - len(output))
    for target in _missing_targets(initial_result):
        if remaining <= 0:
            break
        query = _target_query(question, initial_result, target)
        started = time.perf_counter()
        found, meta = legalclosure_runtime.retrieve(
            index, query, llm=llm, assertion_llm=llm, cap=8,
            shortcut_enabled=False, feedback_enabled=False,
            graph_enabled=False, semantic_graph_enabled=False,
            integrated_research_enabled=False,
        )
        added: list[str] = []
        per_probe_cap = min(2, remaining)
        for section in found:
            coordinate = (str(section.doc_id), int(section.node))
            if coordinate in seen:
                continue
            _ensure_candidate_id(section)
            section.kind = f"표적검색:{target['required_role']}"
            output.append(section)
            seen.add(coordinate)
            added.append(f"{coordinate[0]}:{coordinate[1]}")
            remaining -= 1
            if len(added) >= per_probe_cap or remaining <= 0:
                break
        receipts.append({
            "issue_id": target["issue_id"],
            "required_role": target["required_role"],
            "query": query,
            "retrieved_count": len(found),
            "added_coordinates": added,
            "meta": meta,
            "wall_ms": round((time.perf_counter() - started) * 1000, 3),
        })
    for number, section in enumerate(output, 1):
        section.n = number
    return output, receipts


def _answer_packet(result, sections: Sequence[Section]) -> dict[str, Any]:
    claims = [{
        "claim_id": str(rule["rule_id"]),
        "evidence_id": str(rule["evidence_id"]),
        "issue_ids": [str(rule["issue_id"])],
        "role": str(rule["role"]),
        "proposition": str(rule["source_quote"]),
        "quote": str(rule["source_quote"]),
        "slots": deepcopy(dict(rule.get("slots") or {})),
        "origin": "proposition-first-exact-rule",
    } for rule in result.rules]
    missing = [dict(row) for row in result.coverage if row.get("state") == "MISSING"]
    return {
        "schema_version": PROFILE,
        "answer_mode": "ADVISORY",
        "direct_rule_answer_allowed": True,
        "selected_evidence_ids": [_candidate_id(row) for row in sections],
        "selected_scope_ids": list(dict.fromkeys(
            str(rule.get("scope_id") or "") for rule in result.rules
            if str(rule.get("scope_id") or "")
        )),
        "issues": [dict(row) for row in result.issues],
        "units": claims,
        "claims": claims,
        "entailments": [dict(row) for row in result.applicability],
        "coverage": [dict(row) for row in result.coverage],
        "missing": missing,
        "search_plan": [dict(row) for row in result.search_plan],
        "clarification_requests": [dict(row) for row in result.clarification_requests],
        "reason": str(result.status),
    }


def capture_stages(
    index: Index,
    case_id: str,
    arm_id: str,
    initial_sections: Sequence[Section],
    final_sections: Sequence[Section] | None = None,
) -> dict[str, Any]:
    initial = [(row.doc_id, int(row.node)) for row in initial_sections]
    final = [(row.doc_id, int(row.node)) for row in (final_sections or initial_sections)]
    recorder = stage_ledger.StageLedgerRecorder(
        case_id, arm_id, stage_ledger.index_article_root_canonicalizer(index)
    )
    for stage_id, kind, parents in stage_specs(arm_id):
        if stage_id == "question-source":
            after = []
        elif stage_id in {"inherited-parent-evidence", "proposition-first-compile",
                          "inherited-identity-filter"}:
            after = initial
        else:
            after = final
        recorder.record_stage(stage_id, kind, after, parent_stage_ids=parents)
    return recorder.capture()


def attach_compilation(
    index: Index,
    question: str,
    sections: Sequence[Section],
    *,
    llm: Any,
    case_id: str,
    arm_id: str = PROFILE,
) -> tuple[list[Section], dict[str, Any]]:
    started = time.perf_counter()
    initial = deepcopy(list(sections))
    initial_coordinates = [(row.doc_id, int(row.node)) for row in initial]
    evidence = evidence_from_sections(initial)
    compile_started = time.perf_counter()
    first, first_receipt = compile_with_llm(
        question, evidence, llm, max_tokens=INITIAL_COMPILER_MAX_TOKENS,
    )
    first_ms = round((time.perf_counter() - compile_started) * 1000, 3)
    expanded, probes = _targeted_expand(index, question, initial, first, llm)
    final_evidence = evidence_from_sections(expanded)
    recompile_started = time.perf_counter()
    final, final_receipt = compile_with_llm(
        question, final_evidence, llm, max_tokens=FINAL_COMPILER_MAX_TOKENS,
    )
    final_ms = round((time.perf_counter() - recompile_started) * 1000, 3)
    packet = _answer_packet(final, expanded)
    for section in expanded:
        section.legal_meta = {
            **dict(section.legal_meta or {}),
            "legal_compilation": deepcopy(packet),
        }
    final_coordinates = [(row.doc_id, int(row.node)) for row in expanded]
    final_ids = {_candidate_id(row) for row in expanded}
    exact_quote_violations = sorted({
        str(rule["rule_id"]) for rule in final.rules
        if str(rule["source_quote"]) != str(rule["proposition"])
    })
    closed_evidence_violations = sorted({
        str(rule["evidence_id"]) for rule in final.rules
        if str(rule["evidence_id"]) not in final_ids
    })
    meta = {
        "enabled": True,
        "profile": PROFILE,
        "status": str(final.status),
        "before_count": len(initial),
        "after_count": len(expanded),
        "floor_preserved": final_coordinates[:len(initial_coordinates)] == initial_coordinates,
        "coordinates_unique": len(set(final_coordinates)) == len(final_coordinates),
        "initial_compile_ms": first_ms,
        "final_compile_ms": final_ms,
        "initial_issue_count": len(first.issues),
        "final_issue_count": len(final.issues),
        "initial_rule_count": len(first.rules),
        "final_rule_count": len(final.rules),
        "initial_missing_count": sum(row["state"] == "MISSING" for row in first.coverage),
        "final_missing_count": sum(row["state"] == "MISSING" for row in final.coverage),
        "targeted_probe_count": len(probes),
        "targeted_added_count": len(expanded) - len(initial),
        "targeted_probe_receipts": probes,
        "initial_compiler_receipt": first_receipt,
        "final_compiler_receipt": final_receipt,
        "validation_errors": list(final.validation_errors),
        "validation": {
            "exact_quote_violations": exact_quote_violations,
            "closed_evidence_violations": closed_evidence_violations,
            "floor_violations": [] if final_coordinates[:len(initial_coordinates)] == initial_coordinates else ["floor"],
            "coordinate_violations": [] if len(set(final_coordinates)) == len(final_coordinates) else ["duplicate"],
            "evidence_cap_violations": [] if len(expanded) <= FINAL_EVIDENCE_CAP else [str(len(expanded))],
        },
        "evidence_packet": packet,
        "stage_capture": capture_stages(index, case_id, arm_id, initial, expanded),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    return expanded, meta


def _answer_schema(packet: Mapping[str, Any]) -> dict[str, Any]:
    evidence_ids = list(dict.fromkeys(str(value) for value in packet["selected_evidence_ids"]))
    issue_ids = [str(row["issue_id"]) for row in packet.get("issues") or ()]
    return {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "answerable": {"type": "boolean"},
            "conclusion_strength": {"type": "string", "enum": ["DIRECT", "CONDITIONAL", "INSUFFICIENT"]},
            "evidence_ids": {"type": "array", "items": {"type": "string", "enum": evidence_ids}},
            "issue_results": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string", "enum": issue_ids},
                    "conclusion": {"type": "string"},
                    "conclusion_strength": {"type": "string", "enum": ["DIRECT", "CONDITIONAL", "INSUFFICIENT"]},
                    "evidence_ids": {"type": "array", "items": {"type": "string", "enum": evidence_ids}},
                    "unresolved_requirements": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["issue_id", "conclusion", "conclusion_strength", "evidence_ids", "unresolved_requirements"],
                "additionalProperties": False,
            }},
        },
        "required": ["answer", "answerable", "conclusion_strength", "evidence_ids", "issue_results"],
        "additionalProperties": False,
    }


def synthesize_answer(llm: Any, question: str, sections: Sequence[Section]) -> Answer:
    packet = next(
        (dict((row.legal_meta or {}).get("legal_compilation") or {}) for row in sections
         if (row.legal_meta or {}).get("legal_compilation")),
        {},
    )
    if not packet:
        raise ValueError("proposition-first answer requires compilation packet")
    context = answer_mod._context_text(list(sections)) + answer_mod._definition_context_text(list(sections))
    out = llm.structured(
        "rag.proposition_first.answer",
        PROPOSITION_FIRST_ANSWER_SYSTEM,
        f"[질문]\n{question}\n\n[컨텍스트]\n{context}",
        _answer_schema(packet),
        max_tokens=5000,
        effort="high",
        model=PRODUCT_MODEL,
    )
    if not isinstance(out, Mapping):
        return Answer(answer="", answerable=False, error="proposition-first answer failed")
    allowed = set(str(value) for value in packet.get("selected_evidence_ids") or ())
    rules_by_issue: dict[str, set[str]] = {}
    for claim in packet.get("claims") or ():
        for issue_id in claim.get("issue_ids") or ():
            rules_by_issue.setdefault(str(issue_id), set()).add(str(claim["evidence_id"]))
    missing_by_issue: dict[str, set[str]] = {}
    for row in packet.get("missing") or ():
        missing_by_issue.setdefault(str(row.get("issue_id") or ""), set()).add(
            str(row.get("required_role") or "")
        )
    returned: dict[str, Mapping[str, Any]] = {}
    violations: list[str] = []
    for row in out.get("issue_results") or ():
        issue_id = str(row.get("issue_id") or "")
        if issue_id in returned:
            violations.append(f"duplicate_issue:{issue_id}")
            continue
        returned[issue_id] = row
    issue_results: list[dict[str, Any]] = []
    for issue in packet.get("issues") or ():
        issue_id = str(issue["issue_id"])
        row = returned.get(issue_id)
        if row is None:
            violations.append(f"missing_issue:{issue_id}")
            issue_results.append({
                "issue_id": issue_id,
                "conclusion": "이 쟁점은 생성 결과에서 누락되었습니다.",
                "conclusion_strength": "INSUFFICIENT",
                "evidence_ids": [],
                "unresolved_requirements": sorted(missing_by_issue.get(issue_id, {"ISSUE_RESULT"})),
            })
            continue
        issue_evidence = [
            str(value) for value in row.get("evidence_ids") or ()
            if str(value) in rules_by_issue.get(issue_id, set())
        ]
        if len(issue_evidence) != len(row.get("evidence_ids") or ()):
            violations.append(f"issue_evidence:{issue_id}")
        strength = str(row.get("conclusion_strength") or "INSUFFICIENT")
        missing = missing_by_issue.get(issue_id, set())
        if strength == "DIRECT" and missing:
            violations.append(f"missing_direct:{issue_id}")
            strength = "CONDITIONAL"
        unresolved = set(str(value) for value in row.get("unresolved_requirements") or ())
        unresolved.update(missing)
        issue_results.append({
            "issue_id": issue_id,
            "conclusion": str(row.get("conclusion") or ""),
            "conclusion_strength": strength,
            "evidence_ids": list(dict.fromkeys(issue_evidence)),
            "unresolved_requirements": sorted(value for value in unresolved if value),
        })
    evidence_ids = [
        str(value) for value in out.get("evidence_ids") or () if str(value) in allowed
    ]
    if len(evidence_ids) != len(out.get("evidence_ids") or ()):
        violations.append("answer_evidence_outside_menu")
    return Answer(
        answer=str(out.get("answer") or ""),
        refs=[row.cite() for row in sections],
        answerable=bool(out.get("answerable")),
        conclusion_strength=str(out.get("conclusion_strength") or ""),
        evidence_ids=list(dict.fromkeys(evidence_ids)),
        issue_results=issue_results,
        gate_violation=bool(violations),
        discards=violations,
    )


__all__ = [
    "FINAL_EVIDENCE_CAP",
    "PROFILE",
    "PROPOSITION_FIRST_ANSWER_SYSTEM",
    "TARGETED_PROBE_CAP",
    "attach_compilation",
    "capture_stages",
    "evidence_from_sections",
    "stage_specs",
    "synthesize_answer",
]
