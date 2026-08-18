"""해석 결과 → 검수 화면 payload.

    payload(result, blocks, pdf_path) -> dict

## 왜 별도 파일인가

해석기는 좌표를 **쓰지 않는다** — 판별은 텍스트와 블록 offset 으로만 한다. 좌표는
결과를 사람에게 되돌려 보여 줄 때만 필요하다. 그래서 해석 경로에 섞지 않고 여기서
페이지 크기와 함께 조립한다.

## 좌표를 여기서 뒤집는 이유

Docling 의 PDF prov bbox 는 **BOTTOMLEFT 원점**이다. 화면은 TOPLEFT 다. 뒤집으려면
페이지 높이가 필요한데, 파싱 단계는 페이지 크기를 모른다(`parse_adapter._prov` 주석).
그래서 원점을 그대로 실어 보내고, 페이지 크기를 아는 여기서 정규화한다.

정규화 결과는 **0~1 비율**이다. 화면이 어떤 배율로 렌더하든 그대로 곱하면 되고,
서버가 렌더 배율을 몰라도 된다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from lawrag.core import geometry
from lawrag.core.structure.model import Block, Node, StructureResult


def page_sizes(pdf_path: str | Path) -> dict[int, tuple[float, float]]:
    """페이지 번호 → (너비, 높이). PyMuPDF 로 싸게 얻는다."""
    import fitz

    doc = fitz.open(str(pdf_path))
    try:
        return {i + 1: (p.rect.width, p.rect.height) for i, p in enumerate(doc)}
    finally:
        doc.close()


def _rect(block: Block, sizes: dict[int, tuple[float, float]]) -> Optional[dict]:
    """블록 bbox → 0~1 비율 사각형. 좌표가 없으면 None."""
    if not block.bbox:
        return None
    size = sizes.get(block.page)
    if not size:
        return None
    w, h = size
    if not w or not h:
        return None
    x0, top, x1, bottom = geometry.to_topleft(block.bbox, block.bbox_origin, h)
    x0, x1 = min(x0, x1), max(x0, x1)
    return {"x": round(x0 / w, 5), "y": round(top / h, 5),
            "w": round((x1 - x0) / w, 5), "h": round((bottom - top) / h, 5)}


def _flat_tree(nodes: list[Node], out: list[dict], parent: Optional[int] = None) -> None:
    """트리를 평평한 목록으로 — 화면이 접기/펼치기를 스스로 하게."""
    for n in nodes:
        nid = len(out)
        out.append({
            "id": nid, "parent": parent, "level": n.level, "family": n.family,
            "surface": n.surface, "title": n.title, "title_reason": n.title_reason,
            "ordinal": list(n.ordinal) if n.ordinal else None,
            "page": n.page, "block": n.block_idx,
            "span": [n.span[0], n.span[1]],
            "reason": n.activation_reason,
            "n_children": len(n.children),
            # 이 마디에 딸린 표·그림. 자식 마디가 아니라 잎이다(`attach_leaves`).
            "attachments": n.attachments,
            # 지면에서 덮은 범위 — 2단 편집의 어긋남을 되짚는 재료(`measure_extent`)
            "extent": {str(k): v for k, v in sorted(n.extent.items())},
        })
        _flat_tree(n.children, out, nid)


# 그림 픽셀을 payload 에 실을 총량 상한(바이트). 도장·서명 몇 개는 가볍지만, 사진이
# 많은 문서는 화면이 못 받을 만큼 커진다. 넘치면 **넘쳤다고 말하고** 자른다.
IMAGE_BUDGET = 4 * 1024 * 1024


def _table_payload(table) -> dict:
    """표를 화면이 그대로 그릴 수 있는 형태로 — 병합과 머리글을 살려서.

    `grid()` 로 펼치면 병합 셀이 복제되어 `<td colspan>` 을 되만들 수 없다. 논리 셀을
    행 단위로 주고 span 을 함께 실어, 화면이 원본 모양대로 그린다.
    """
    return {
        "n_rows": table.n_rows, "n_cols": table.n_cols,
        "header_source": table.header_source(),
        "rows": [[{"text": c.text, "row": c.row, "col": c.col,
                   "row_span": c.row_span, "col_span": c.col_span,
                   "col_header": c.is_col_header, "row_header": c.is_row_header}
                  for c in row] for row in table.rows()],
    }


def payload(result: StructureResult, blocks: list[Block],
            pdf_path: Optional[str | Path] = None,
            elements: Optional[list] = None,
            images: Optional[dict[int, str]] = None) -> dict[str, Any]:
    """검수 화면이 필요한 것 전부를 한 덩어리로.

    `elements` 를 주면 표 블록에 셀 격자를, 그림 블록에 캡션을 실어 보낸다. 없으면
    블록의 평문(`a | b`)만 간다 — 화면은 둘 다 처리한다.

    `images`(`ParseResult.images`)를 주면 그림 블록에 픽셀까지 간다. 검수 화면은
    "여기 그림이 있었다"가 아니라 **그 그림이 무엇인지** 보여야 한다.
    """
    sizes = page_sizes(pdf_path) if pdf_path else {}
    by_element = {e.index: e for e in (elements or [])}
    images = images or {}

    nodes: list[dict] = []
    _flat_tree(result.tree, nodes)

    # 블록 → 그 블록을 덮는 **가장 깊은** 마디. 오버레이 색을 그것으로 칠한다.
    owner: dict[int, dict] = {}
    for n in nodes:
        for b in range(n["span"][0], max(n["span"][1], n["span"][0] + 1)):
            cur = owner.get(b)
            if cur is None or n["level"] > cur["level"]:
                owner[b] = n
    # 표·그림의 소속은 **포함이 아니라 자리**가 정한다(`pipeline.attach_leaves`).
    # span 포함으로 칠하면 503블록짜리 구간의 색을 뒤집어쓰거나(실측) 아무 색도 못
    # 받는다. 매달린 마디를 그대로 쓴다 — 트리에 보이는 소속과 오버레이 색이 같아야
    # 화면에서 두 곳을 대조할 수 있다.
    for n in nodes:
        for a in n.get("attachments") or []:
            owner[a["block"]] = n

    opened: dict[int, list[int]] = {}
    for n in nodes:
        opened.setdefault(n["block"], []).append(n["id"])

    by_block: dict[int, list] = {}
    for c in result.candidates:
        by_block.setdefault(c.block_idx, []).append(c)

    blocks_out = []
    spent, omitted = 0, 0                  # 그림 픽셀 예산 (IMAGE_BUDGET)
    for b in blocks:
        own = owner.get(b.idx)
        cands = by_block.get(b.idx, [])
        extra: dict[str, Any] = {}
        el = by_element.get(b.element_index)
        if b.kind == "table" and el is not None and el.table is not None:
            extra["table"] = _table_payload(el.table)
        elif b.kind == "figure":
            meta = getattr(el, "meta", None) or {}
            uri = images.get(b.element_index, "")
            if uri and spent + len(uri) > IMAGE_BUDGET:
                uri, omitted = "", omitted + 1
            else:
                spent += len(uri)
            extra["figure"] = {"caption": b.text, "ref": meta.get("ref", ""),
                               "size": meta.get("image_size"),
                               "image": uri,
                               "omitted": bool(meta.get("has_image") and not uri)}
        blocks_out.append({
            "idx": b.idx, "page": b.page, "text": b.text, "kind": b.kind,
            "rect": _rect(b, sizes),
            "node": own["id"] if own else None,
            "level": own["level"] if own else None,
            "opens": opened.get(b.idx, []),
            **extra,
            "markers": [{"id": c.id, "family": c.family_key, "surface": c.surface,
                         "s": round(c.s, 2), "survives": c.survives,
                         "activated": c.activated,
                         "level": c.activated_level,
                         "note": c.decision_note or c.family_note,
                         "llm": c.llm_verdict}
                        for c in sorted(cands, key=lambda x: x.offset)],
        })

    residual_ids = {r.split()[1] for r in result.residual}
    warns = list(result.warnings)
    if omitted:
        # 조용히 자르지 않는다 — 화면이 "그림이 없다" 와 "너무 커서 안 실었다" 를
        # 구별할 수 있어야 한다.
        warns.append(f"그림 {omitted}개는 payload 상한({IMAGE_BUDGET // 1024}KB)을 "
                     f"넘어 픽셀을 싣지 않았습니다")
    return {
        "doc": result.doc,
        "pages": [{"n": p, "w": w, "h": h} for p, (w, h) in sorted(sizes.items())],
        "fitness": {"score": round(result.fitness_score, 3),
                    "passed": result.fitness_passed, "tier": result.tier,
                    **{k: result.stats.get(k) for k in
                       ("coverage", "consistency", "ladder_quality")}},
        "ladder": result.ladder.dump(),
        "nodes": nodes,
        "blocks": blocks_out,
        "residual": result.residual,
        "residual_ids": sorted(residual_ids),
        "llm": result.stats.get("llm"),
        "warnings": warns,
        "stats": result.stats,
        "applied": result.applied,
        "fingerprint": result.fingerprint.dump(),
    }


def page_png(pdf_path: str | Path, page: int, scale: float = 2.0) -> str:
    """페이지 하나를 base64 data URI 로. VLM 에 그림째 던질 때 쓴다.

    검수 화면이 이미 같은 방식으로 페이지를 렌더한다(`lawrag/api/routers/structure.py`).
    같은 것을 두 번 구현하지 않으려고 여기 둔다 — 코어 쪽에서도 필요해졌다.
    """
    import base64

    import fitz

    doc = fitz.open(str(pdf_path))
    try:
        pix = doc[page - 1].get_pixmap(matrix=fitz.Matrix(scale, scale))
        return "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()
    finally:
        doc.close()
