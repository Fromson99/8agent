"""Concise, non-binding legal guidance for answer-time evidence selection.

The guide is a deterministic projection of an already sealed compiler packet.
It never adds, removes, reorders, or caps source provisions.  Only validated
question spans and exact source quotes from non-CONTEXT units are exposed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from lawrag.core.rag import raw_evidence_selection as raw


PROFILE = "selective-legal-guide-v1"
ROLES = (
    "GOVERNING_RULE", "DEFINITION", "CONDITION", "EXCEPTION",
    "PROCEDURE", "SANCTION", "COMPANION", "CONTEXT",
)

SYSTEM = """너는 제공된 원문만 근거로 답하는 법률 문서 질의응답 보조자다.

1. [원문 목록]이 유일한 법률 근거다. 밖의 법령·조문·수치·요건을 만들지 않는다.
2. [선별 법률 가이드]는 원문 탐색을 돕는 비구속적 힌트다. 틀릴 수 있으므로 원문과
   질문을 직접 대조하고, 가이드와 원문이 다르면 원문을 따른다.
3. issues는 빠뜨리기 쉬운 질문의 soft checklist다. units의 role도 잠정 분류이며,
   quote만 해당 evidence의 검증된 연속 원문이다.
4. unresolved_issues는 현재 가이드에 결속 unit이 없다는 뜻일 뿐 답이 없다는 결론이 아니다.
5. 28개 원문은 모두 동등하게 검토한다. 가이드에 없는 원문도 필요하면 선택할 수 있다.
6. selections에는 답변의 핵심 결론에 실제 사용한 E번호만 넣고, 각 선택의 질문 span,
   법적 역할, 연속 exact quote, 필요한 이유와 함께 읽을 dependency E번호를 적는다.
7. rejected_near_matches에는 실제로 혼동하기 쉬웠지만 배제한 근접 후보만 최대 5개 적는다.
8. 질문 span은 질문의 연속 문자열이어야 하고 supporting_quote는 해당 E 원문의 연속 문자열이어야 한다.
9. 답할 근거가 없으면 answerable=false와 빈 selections를 낸다. E번호 밖 ID를 만들지 않는다."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "answerable": {"type": "boolean"},
        "selections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "evidence_id": {"type": "string"},
                    "question_span": {"type": "string"},
                    "legal_role": {"type": "string", "enum": list(ROLES)},
                    "supporting_quote": {"type": "string"},
                    "why_needed": {"type": "string"},
                    "dependency_ids": {
                        "type": "array", "items": {"type": "string"},
                    },
                },
                "required": [
                    "evidence_id", "question_span", "legal_role",
                    "supporting_quote", "why_needed", "dependency_ids",
                ],
                "additionalProperties": False,
            },
        },
        "rejected_near_matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "evidence_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["evidence_id", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answer", "answerable", "selections", "rejected_near_matches"],
    "additionalProperties": False,
}


def _clean_issues(question: str, packet: Mapping[str, Any]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for number, row in enumerate(packet.get("issues") or (), 1):
        span = str(row.get("question_span") or "")
        issue_id = str(row.get("issue_id") or f"I{number}")
        if not span or span not in question or issue_id in seen:
            continue
        output.append({"issue_id": issue_id, "question_span": span})
        seen.add(issue_id)
    return output[:4]


def _typed_links(
    sections: Sequence[Mapping[str, Any]],
    coordinate_to_id: Mapping[tuple[str, int], str],
) -> list[dict[str, str]]:
    """Expose only closed-menu typed links, never generic retrieval provenance."""

    allowed_markers = (
        "DELEG", "ENTRUST", "AGENT", "INCORPOR", "DEFIN", "EXCEPT",
        "APPL", "준용", "위임", "수임", "위탁", "대리", "정의", "예외", "적용",
    )
    output: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for source_number, section in enumerate(sections, 1):
        source_id = f"E{source_number:02d}"
        for edge in section.get("edges") or ():
            relation = str(edge.get("relation") or "")
            if not relation or not any(marker in relation.upper() for marker in allowed_markers):
                continue
            target_id = ""
            target = edge.get("to")
            if isinstance(target, Mapping):
                doc_id = str(target.get("doc_id") or "")
                node = target.get("node")
                if doc_id and isinstance(node, int) and not isinstance(node, bool):
                    target_id = coordinate_to_id.get((doc_id, node), "")
            if not target_id:
                continue
            key = (source_id, relation, target_id)
            if key in seen:
                continue
            seen.add(key)
            output.append({
                "from_evidence_id": source_id,
                "relation": relation,
                "surface": str(edge.get("surface") or ""),
                "to_evidence_id": target_id,
            })
    return output


def build_guide(
    question: str,
    sections: Sequence[Mapping[str, Any]],
    compiler_packet: Mapping[str, Any],
    compiler_id_to_evidence_id: Mapping[str, str],
) -> dict[str, Any]:
    rows = raw.evidence_rows(sections)
    by_id = {str(row["evidence_id"]): row for row in rows}
    issues = _clean_issues(question, compiler_packet)
    issue_ids = {row["issue_id"] for row in issues}
    units: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...], str, str]] = set()
    covered: set[str] = set()
    for row in compiler_packet.get("units") or ():
        role = str(row.get("role") or "")
        if role not in ROLES or role == "CONTEXT":
            continue
        evidence_id = compiler_id_to_evidence_id.get(str(row.get("evidence_id") or ""), "")
        quote = str(row.get("quote") or "")
        linked = tuple(
            str(value) for value in row.get("issue_ids") or ()
            if str(value) in issue_ids
        )
        if not evidence_id or evidence_id not in by_id or not quote or not linked:
            continue
        if quote not in str(by_id[evidence_id]["text"]):
            continue
        key = (evidence_id, linked, role, quote)
        if key in seen:
            continue
        seen.add(key)
        covered.update(linked)
        units.append({
            "evidence_id": evidence_id,
            "issue_ids": list(linked),
            "role": role,
            "quote": quote,
        })
    coordinate_to_id = {
        (str(row["doc_id"]), int(row["node"])): str(row["evidence_id"])
        for row in rows
    }
    return {
        "issues": issues,
        "units": units,
        "legal_links": _typed_links(sections, coordinate_to_id),
        "unresolved_issues": [row for row in issues if row["issue_id"] not in covered],
        "non_binding": True,
    }


def build_request(
    question: str,
    sections: Sequence[Mapping[str, Any]],
    compiler_packet: Mapping[str, Any],
    compiler_id_to_evidence_id: Mapping[str, str],
) -> dict[str, Any]:
    rows = raw.evidence_rows(sections)
    guide = build_guide(question, sections, compiler_packet, compiler_id_to_evidence_id)
    user = (
        f"[질문]\n{question}\n\n[선별 법률 가이드]\n"
        + json.dumps(guide, ensure_ascii=False, separators=(",", ":"))
        + "\n\n[원문 목록]\n"
        + json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    )
    identifier_map = {
        str(row["evidence_id"]): {"doc_id": row["doc_id"], "node": row["node"]}
        for row in rows
    }
    input_hash = hashlib.sha256(json.dumps(
        {"system": SYSTEM, "user": user, "schema": SCHEMA},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return {
        "system": SYSTEM,
        "user": user,
        "schema": SCHEMA,
        "guide": guide,
        "evidence_id_map": identifier_map,
        "evidence_rows": rows,
        "input_sha256": input_hash,
        "evidence_count": len(rows),
    }


def validate_output(
    output: Mapping[str, Any] | None,
    question: str,
    evidence_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_id = {str(row["evidence_id"]): row for row in evidence_rows}
    if output is None:
        return {
            "answer": "", "answerable": False, "evidence_ids": [],
            "selections": [], "rejected_near_matches": [],
            "invalid_evidence_ids": [], "question_span_violations": 0,
            "quote_violations": 0, "dependency_violations": 0,
            "valid": False, "error": "empty structured output",
        }
    selections: list[dict[str, Any]] = []
    invalid_ids: set[str] = set()
    selected_ids: list[str] = []
    span_violations = quote_violations = dependency_violations = 0
    for row in output.get("selections") or ():
        evidence_id = str(row.get("evidence_id") or "")
        if evidence_id not in by_id:
            invalid_ids.add(evidence_id)
            continue
        if evidence_id not in selected_ids:
            selected_ids.append(evidence_id)
        question_span = str(row.get("question_span") or "")
        quote = str(row.get("supporting_quote") or "")
        if not question_span or question_span not in question:
            span_violations += 1
        if not quote or quote not in str(by_id[evidence_id]["text"]):
            quote_violations += 1
        dependencies = list(dict.fromkeys(str(value) for value in row.get("dependency_ids") or ()))
        bad_dependencies = [value for value in dependencies if value not in by_id]
        invalid_ids.update(bad_dependencies)
        dependency_violations += len(bad_dependencies)
        selections.append({
            "evidence_id": evidence_id,
            "question_span": question_span,
            "legal_role": str(row.get("legal_role") or ""),
            "supporting_quote": quote,
            "why_needed": str(row.get("why_needed") or ""),
            "dependency_ids": dependencies,
        })
    rejected: list[dict[str, str]] = []
    for row in list(output.get("rejected_near_matches") or ())[:5]:
        evidence_id = str(row.get("evidence_id") or "")
        if evidence_id not in by_id:
            invalid_ids.add(evidence_id)
            continue
        rejected.append({
            "evidence_id": evidence_id,
            "reason": str(row.get("reason") or ""),
        })
    answerable = bool(output.get("answerable"))
    errors: list[str] = []
    if invalid_ids:
        errors.append("outside closed evidence menu")
    if answerable and not selected_ids:
        errors.append("answerable response without evidence")
    if span_violations:
        errors.append("question span is not exact")
    if quote_violations:
        errors.append("supporting quote is not exact")
    if dependency_violations:
        errors.append("dependency outside closed evidence menu")
    return {
        "answer": str(output.get("answer") or ""),
        "answerable": answerable,
        "evidence_ids": selected_ids,
        "selections": selections,
        "rejected_near_matches": rejected,
        "invalid_evidence_ids": sorted(invalid_ids),
        "question_span_violations": span_violations,
        "quote_violations": quote_violations,
        "dependency_violations": dependency_violations,
        "valid": not errors,
        "error": "; ".join(errors),
    }


def select_and_answer(
    llm: Any,
    question: str,
    sections: Sequence[Mapping[str, Any]],
    compiler_packet: Mapping[str, Any],
    compiler_id_to_evidence_id: Mapping[str, str],
):
    request = build_request(
        question, sections, compiler_packet, compiler_id_to_evidence_id,
    )
    output = llm.structured(
        "rag.selective_legal_guide.answer",
        request["system"], request["user"], request["schema"],
        max_tokens=5000, effort="high",
    )
    return validate_output(output, question, request["evidence_rows"]), request


__all__ = [
    "PROFILE", "ROLES", "SYSTEM", "SCHEMA", "build_guide", "build_request",
    "validate_output", "select_and_answer",
]
