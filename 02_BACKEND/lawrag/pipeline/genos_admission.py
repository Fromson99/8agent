"""Mechanical structure admission for the explicitly selected offline DRAFT path.

Heuristic fitness remains evidence, not an admission threshold.  This validator
does not repair a tree, invent legal units, change fitness, or approve semantics.
It validates the existing viewer/source-field payload coordinate contract.
"""
from __future__ import annotations

import re
from typing import Any

POLICY = "score-advisory-v1"


def validate_structure(document_id: str, meta: dict, result: dict) -> dict[str, Any]:
    """Return a deterministic receipt, or raise an actionable ``ValueError``.

    Space is proportional to the supplied rows, never to an untrusted span end.
    Interval coverage is O(n log n); parent cycle detection is iterative O(n).
    Nested/enclosing spans may overlap.  Explicit table/figure attachments may
    also belong to a unit outside its text span, as the viewer contract permits.
    Source-byte/hash verification remains the caller's responsibility.
    """
    def fail(field: str, message: str) -> None:
        raise ValueError(f"구조화 계약 오류: 문서 {document_id} | {field}: {message}")

    def integer(value: Any, field: str, *, minimum: int = 0) -> int:
        if type(value) is not int or value < minimum:
            fail(field, f"{minimum} 이상의 정수가 필요합니다 (bool/문자열 불가)")
        return value

    if not isinstance(document_id, str) or not document_id.strip():
        fail("document_id", "비어 있지 않은 문서 ID가 필요합니다")
    if not isinstance(meta, dict) or not isinstance(result, dict):
        fail("meta/result", "JSON 객체가 필요합니다")
    if meta.get("doc_id") != document_id:
        fail("meta.doc_id", "원문 문서 ID와 구조화 문서 ID가 다릅니다")
    if "doc_id" in result and result["doc_id"] != document_id:
        fail("result.doc_id", "원문 문서 ID와 구조화 문서 ID가 다릅니다")

    review = meta.get("recipe_review")
    if review is not None or result.get("recipe_review") is not None:
        if not isinstance(review, dict) or review != result.get("recipe_review"):
            fail("recipe_review", "저장된 구조와 메타데이터의 검수 기록이 다릅니다")
        if review.get("status") not in {"visual_approved", "visual_sampled"}:
            fail("recipe_review.status", "보류/실패한 PDF 구조는 후속 의미 추출에 전달할 수 없습니다")

    nodes, blocks = result.get("nodes"), result.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        fail("blocks", "본문 블록이 없습니다. 파서 결과와 원문 암호화 여부를 확인하세요")
    if not isinstance(nodes, list) or not nodes:
        fail("nodes", "구조 마디가 없습니다. 등록한 형식 태그/마커와 원문을 확인하세요")

    def source_identity(value: dict, field: str) -> None:
        if "document_id" in value and value["document_id"] != document_id:
            fail(field + ".document_id", "원문 문서 ID 연결이 잘못되었습니다")
        fingerprint = value.get("source_artifact_sha256")
        if fingerprint is not None and (
            not isinstance(fingerprint, str)
            or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None
            or not fingerprint.startswith(document_id)
        ):
            fail(field + ".source_artifact_sha256", "원문 SHA-256/문서 ID 좌표가 잘못되었습니다")

    source_identity(meta, "meta")
    source_identity(result, "result")
    block_ids: set[int] = set()
    has_text = False
    for pos, block in enumerate(blocks):
        field = f"blocks[{pos}]"
        if not isinstance(block, dict):
            fail(field, "블록 JSON 객체가 필요합니다")
        idx = integer(block.get("idx"), field + ".idx")
        if idx >= len(blocks):
            fail(field + ".idx", f"본문 블록 범위 0..{len(blocks) - 1}를 벗어났습니다")
        if idx in block_ids:
            fail(field + ".idx", f"중복 블록 ID {idx}")
        block_ids.add(idx)
        if not isinstance(block.get("text"), str):
            fail(field + ".text", "본문 문자열이 필요합니다")
        has_text = has_text or bool(block["text"].strip())
        if block.get("page") is not None:
            integer(block["page"], field + ".page", minimum=1)
        source_identity(block, field)
    if not has_text:
        fail("blocks.text", "읽을 수 있는 본문이 없습니다. 빈 결과를 통과 처리하지 않습니다")

    by_id: dict[int, dict] = {}
    spans: dict[int, tuple[int, int]] = {}
    attached: dict[int, set[int]] = {}
    for pos, node in enumerate(nodes):
        field = f"nodes[{pos}]"
        if not isinstance(node, dict):
            fail(field, "구조 마디 JSON 객체가 필요합니다")
        ident = integer(node.get("id"), field + ".id")
        if ident in by_id:
            fail(field + ".id", f"중복 구조 마디 ID {ident}")
        by_id[ident] = node
        # Native source-field adapters use span, without the viewer's opening
        # heading block.  Validate that optional coordinate only when supplied.
        start_block = None
        if "block" in node:
            start_block = integer(node["block"], field + ".block")
            if start_block not in block_ids:
                fail(field + ".block", f"연결한 본문 블록 {start_block}가 없습니다")
        span = node.get("span")
        if not isinstance(span, (list, tuple)) or len(span) != 2:
            fail(field + ".span", "[시작 블록, 끝 블록 직후] 좌표가 필요합니다")
        lo = integer(span[0], field + ".span[0]")
        hi = integer(span[1], field + ".span[1]")
        if not (0 <= lo < hi <= len(blocks)):
            fail(field + ".span", "비어 있거나 역전되었거나 본문 범위를 벗어난 좌표입니다")
        if start_block is not None and not lo <= start_block < hi:
            fail(field + ".block", "마디의 시작 블록이 자신의 span 범위를 벗어났습니다")
        spans[ident] = (lo, hi)
        if node.get("page") is not None:
            integer(node["page"], field + ".page", minimum=1)
        source_identity(node, field)
        attachments = node.get("attachments")
        if attachments is None:
            attachments = []
        if not isinstance(attachments, list):
            fail(field + ".attachments", "첨부 블록 목록이 필요합니다")
        owned: set[int] = set()
        for number, attachment in enumerate(attachments):
            path = f"{field}.attachments[{number}]"
            if not isinstance(attachment, dict):
                fail(path, "첨부 블록 JSON 객체가 필요합니다")
            idx = integer(attachment.get("block"), path + ".block")
            if idx not in block_ids:
                fail(path + ".block", f"연결한 첨부 블록 {idx}가 없습니다")
            owned.add(idx)
        attached[ident] = owned

    for ident, node in by_id.items():
        parent = node.get("parent")
        if parent is not None:
            integer(parent, f"nodes[id={ident}].parent")
            if parent not in by_id:
                fail(f"nodes[id={ident}].parent", f"부모 마디 ID {parent}가 없습니다")
    # Mark paths once; never recurse through a deep document or allocate span ranges.
    checked: set[int] = set()
    for ident in by_id:
        path: set[int] = set()
        current = ident
        while current is not None and current not in checked:
            if current in path:
                fail(f"nodes[id={current}].parent", "부모 연결이 순환합니다")
            path.add(current)
            current = by_id[current].get("parent")
        checked.update(path)

    intervals = list(spans.values())
    intervals.extend((idx, idx + 1) for values in attached.values() for idx in values)
    covered_to = 0
    for lo, hi in sorted(intervals):
        if lo > covered_to:
            fail(f"blocks[idx={covered_to}]", "어느 구조 마디에도 포함되지 않은 본문 블록입니다")
        covered_to = max(covered_to, hi)
    if covered_to < len(blocks):
        fail(f"blocks[idx={covered_to}]", "어느 구조 마디에도 포함되지 않은 본문 블록입니다")

    for block in blocks:
        unit = block.get("node")
        if unit is None:
            continue  # Coverage may be present even without a viewer overlay owner.
        idx = block["idx"]
        integer(unit, f"blocks[idx={idx}].node")
        if unit not in by_id:
            fail(f"blocks[idx={idx}].node", f"연결한 구조 마디 ID {unit}가 없습니다")
        lo, hi = spans[unit]
        if not lo <= idx < hi and idx not in attached[unit]:
            fail(f"blocks[idx={idx}].node", "연결한 마디의 span/첨부 목록에 블록이 없습니다")

    fitness = result.get("fitness")
    fitness = fitness if isinstance(fitness, dict) else {}
    passed = meta.get("passed", fitness.get("passed"))
    score = meta.get("score", fitness.get("score"))
    warnings = []
    if passed is False:
        warnings.append("휴리스틱 구조 점수/판정은 참고용입니다. 원래 실패 판정은 보존하고 기계적 계약으로 수용했습니다")
    return {
        "policy": POLICY,
        "accepted": True,
        "document_id": document_id,
        "heuristic_passed": passed,
        "heuristic_score": score,
        "checks": {"document_identity": True, "nonempty_text": True,
                   "unique_ids": True, "parent_acyclic": True,
                   "block_coordinates": True, "structure_coverage": True},
        "counts": {"blocks": len(blocks), "nodes": len(nodes)},
        "warnings": warnings,
    }
