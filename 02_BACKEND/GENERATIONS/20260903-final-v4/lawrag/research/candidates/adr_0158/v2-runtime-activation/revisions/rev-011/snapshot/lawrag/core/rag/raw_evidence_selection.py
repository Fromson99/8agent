"""Compiler-free answer-time evidence selection research helper.

This module intentionally knows nothing about legal issue families, roles,
claims, coverage, Wiki cards, retrieval scores, or compiler packets.  It turns
an already frozen list of raw provisions into opaque evidence IDs and asks one
answer model to declare which IDs directly support the answer it wrote.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


PROFILE = "raw-context-evidence-id-v1"

SYSTEM = """너는 제공된 원문만 근거로 답하는 문서 질의응답 보조자다.

1. [원문 목록] 밖의 법령·조문·수치·요건을 만들지 않는다.
2. 질문에 먼저 답하고 필요한 근거를 간결하게 설명한다.
3. evidence_ids에는 답변의 핵심 결론을 직접 뒷받침하기 위해 실제 사용한 E번호만 넣는다.
4. 관련 있어 보인다는 이유만으로 사용하지 않은 원문을 넣지 않는다.
5. 답할 근거가 없으면 answerable=false와 빈 evidence_ids를 낸다.
6. E번호 밖의 ID를 만들지 않는다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "answerable": {"type": "boolean"},
        "evidence_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["answer", "answerable", "evidence_ids"],
    "additionalProperties": False,
}


def evidence_rows(sections: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return the only fields permitted to enter the raw-selector prompt."""

    output: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for number, source in enumerate(sections, 1):
        doc_id = str(source.get("doc_id") or "")
        node = source.get("node")
        if not doc_id or isinstance(node, bool) or not isinstance(node, int):
            raise ValueError(f"invalid evidence coordinate at rank {number}")
        coordinate = (doc_id, node)
        if coordinate in seen:
            raise ValueError(f"duplicate evidence coordinate: {doc_id}:{node}")
        seen.add(coordinate)
        output.append({
            "evidence_id": f"E{number:02d}",
            "document": str(source.get("doc") or ""),
            "doc_id": doc_id,
            "node": node,
            "path": str(source.get("path") or ""),
            "page": source.get("page"),
            "text": str(source.get("text") or ""),
        })
    return output


def build_request(
    question: str,
    sections: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = evidence_rows(sections)
    user = (
        f"[질문]\n{question}\n\n[원문 목록]\n"
        + json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    )
    identifier_map = {
        row["evidence_id"]: {"doc_id": row["doc_id"], "node": row["node"]}
        for row in rows
    }
    input_hash = hashlib.sha256(
        json.dumps(
            {"system": SYSTEM, "user": user, "schema": SCHEMA},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "system": SYSTEM,
        "user": user,
        "schema": SCHEMA,
        "evidence_id_map": identifier_map,
        "input_sha256": input_hash,
        "evidence_count": len(rows),
    }


def validate_output(
    output: Mapping[str, Any] | None,
    identifier_map: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if output is None:
        return {
            "answer": "",
            "answerable": False,
            "evidence_ids": [],
            "invalid_evidence_ids": [],
            "valid": False,
            "error": "empty structured output",
        }
    raw_ids = output.get("evidence_ids") or []
    declared = list(dict.fromkeys(str(value) for value in raw_ids))
    invalid = sorted(value for value in declared if value not in identifier_map)
    valid_ids = [value for value in declared if value in identifier_map]
    answerable = bool(output.get("answerable"))
    errors = []
    if invalid:
        errors.append("outside closed evidence menu")
    if answerable and not valid_ids:
        errors.append("answerable response without evidence")
    return {
        "answer": str(output.get("answer") or ""),
        "answerable": answerable,
        "evidence_ids": valid_ids,
        "declared_evidence_ids_raw": declared,
        "invalid_evidence_ids": invalid,
        "valid": not errors,
        "error": "; ".join(errors),
    }


def select_and_answer(llm: Any, question: str, sections: Sequence[Mapping[str, Any]]):
    request = build_request(question, sections)
    output = llm.structured(
        "rag.raw_evidence_id_selection.answer",
        request["system"],
        request["user"],
        request["schema"],
        max_tokens=4000,
        effort="high",
    )
    result = validate_output(output, request["evidence_id_map"])
    return result, request
