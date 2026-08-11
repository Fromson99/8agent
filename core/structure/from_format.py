"""형식 구조화 결과(structurize.Document) → 검수 화면 payload 재료.

폴더/문서에 형식(doc_type)이 연결되면 그 문서는 유도(S0~S6)가 아니라 **형식
파일의 마커**로 잘린다(router 경로와 같은 결정론). 그런데 검수 화면은
`StructureResult` 만 안다 — lawxml 이 태그 트리를 옮길 때와 같은 문제라서,
같은 방식으로 변환기를 한 곳에 둔다. 화면 스키마가 바뀌면 여기 하나만 고친다.

판정의 실체는 structurize 가 이미 끝냈다 — 여기는 **모양만 옮긴다.**
"""
from __future__ import annotations

from typing import Optional

from core.fitness_gate import Fitness
from core.parse_adapter import ParseResult
from core.structure.model import (
    Block,
    Fingerprint,
    Ladder,
    Node,
    Rung,
    StructureResult,
)
from core.structurize import Document, Section


def _ordinal(marker: dict) -> Optional[tuple]:
    no = str(marker.get("no") or "")
    if no.isascii() and no.isdigit():
        return (int(no),)
    return None


def _family(marker: dict) -> str:
    if marker.get("kind") == "term":
        return f"term:{marker.get('term', '')}"
    return str(marker.get("id") or "?")


def _is_default(sec: Section) -> bool:
    return sec.marker.get("kind") == "default"


def result_from_document(parsed: ParseResult, doc: Document, fitness: Fitness,
                         *, doc_type: str) -> tuple[StructureResult, list[Block]]:
    """(blocks, 트리, 사다리, 지문)을 형식 구조화 산출물에서 조립한다.

    기본 구역(default)은 마디로 만들지 않는다 — 형식이 설명하지 못한 잔여이고,
    화면에서는 어느 마디의 span 에도 안 덮인 블록으로 그대로 보인다.
    """
    blocks = Block.from_elements(parsed.elements)
    e2b = {b.element_index: b.idx for b in blocks}

    by_id = {s.section_id: s for s in doc.sections}
    nodes: dict[str, Node] = {}
    roots: list[Node] = []

    def first_block(sec: Section) -> Optional[int]:
        for ei in sec.elements:
            if ei in e2b:
                return e2b[ei]
        return None

    for sec in doc.sections:
        if _is_default(sec):
            continue
        b0 = first_block(sec)
        el0 = parsed.elements[sec.elements[0]] if sec.elements else None
        marker = sec.marker
        surface = sec.path[-1] if sec.path else sec.section_id
        n = Node(
            level=sec.level,
            ordinal=_ordinal(marker),
            family=_family(marker),
            surface=surface,
            block_idx=b0 if b0 is not None else 0,
            page=min(sec.pages) if sec.pages else 1,
            element_index=sec.elements[0] if sec.elements else 0,
            candidate_id=f"format:{sec.section_id}",
            title=str(marker.get("title") or
                      (marker.get("term") if marker.get("kind") == "term" else "")),
            title_reason="형식 마커" if marker.get("title") or marker.get("term") else "",
            activation_reason=f"형식 '{doc_type}' 마커 ({_family(marker)})",
            bbox=el0.bbox if el0 is not None else None,
            bbox_origin=el0.bbox_origin if el0 is not None else "BOTTOMLEFT",
        )
        nodes[sec.section_id] = n
        # 부모: 기본 구역이 아닌 가장 가까운 조상. 기본 구역 아래 열린 마커는 루트다.
        parent = sec.parent
        while parent is not None and _is_default(by_id[parent]):
            parent = by_id[parent].parent
        if parent is not None and parent in nodes:
            nodes[parent].children.append(n)
        else:
            roots.append(n)

    # span — 자기 요소와 자손 전체가 덮는 블록 범위. 후위로 접어 올린다.
    def close(sec_id: str) -> tuple[int, int]:
        sec, n = by_id[sec_id], nodes[sec_id]
        lo = [e2b[ei] for ei in sec.elements if ei in e2b]
        start = min(lo) if lo else n.block_idx
        end = (max(lo) + 1) if lo else n.block_idx
        for child_id in sec.children:
            if child_id in nodes:
                cs, ce = close(child_id)
                start, end = min(start, cs), max(end, ce)
        n.span = (start, end)
        return start, end

    for sec in doc.sections:
        if not _is_default(sec) and (
                sec.parent is None or _is_default(by_id[sec.parent])):
            close(sec.section_id)

    # 사다리·지문 — 실제 쓰인 레벨에서 역산 (lawxml 과 같은 규약)
    by_level: dict[int, set[str]] = {}
    for n in nodes.values():
        by_level.setdefault(n.level, set()).add(n.family)
    ladder = Ladder(rungs=[Rung(level=lv, families=sorted(fams), reg_score=1.0,
                                evidence=f"형식 파일 '{doc_type}' (유도 없음)")
                           for lv, fams in sorted(by_level.items())])
    fp = Fingerprint(families=sorted({f for s in by_level.values() for f in s}),
                     order=[sorted(by_level[lv]) for lv in sorted(by_level)])

    parts = (fitness.detail or {}).get("parts", {})
    result = StructureResult(
        doc=doc.source_file, tree=roots, ladder=ladder, candidates=[],
        fitness_score=fitness.score, fitness_passed=fitness.passed,
        tier="hot" if fitness.passed else "cold", fingerprint=fp,
        warnings=list(fitness.warnings),
        stats={"source": f"format:{doc_type}", "deterministic": True,
               "blocks": len(blocks), "sections": len(nodes),
               "residual_elements": len(doc.residual),
               "coverage": parts.get("residual"),
               "consistency": parts.get("marker_density"),
               "ladder_quality": parts.get("ordinal_continuity")},
        applied={"root": None, "families": None, "ladder_hint": None,
                 "partial_order": None, "llm": False, "lang": "ko",
                 "source": f"format:{doc_type}"},
    )
    return result, blocks
