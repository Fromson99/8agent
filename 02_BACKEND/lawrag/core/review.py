"""검수 payload — 형식이 못 먹은 자리를 사람에게 보인다 (오추출 방어 3).

    from lawrag.core import review
    payload = review.payload(routed)          # router.route() 의 결과

격리(fitness 미달)는 막다른 골목이 아니다. 격리된 문서에서 사람이 알아야 하는 것은
점수가 아니라 **어디를 못 먹었는가**다:

- 잔여      — 기본 구역에 담긴 요소 (형식이 설명하지 못한 질량)
- 미적중 제목 — 마커 구역 안에 제목상으로 끼어든 요소 (조용한 오배정 후보)

이 둘을 페이지·좌표와 함께 실어 화면이 PDF 위에 겹쳐 보이게 한다. 구조화(section
좌표)가 무너져도 파싱층의 page/bbox 좌표는 형식과 무관하게 살아 있다 — 그 강등
좌표가 이 payload 의 축이다. 그래서 어떤 doc_type 이 와도 동작한다: PDF 가 아니면
bbox 없이 페이지·텍스트만 싣는다(전사는 meta 의 발화 좌표가 그 역할을 한다).

## 좌표 정규화

payload 모양은 lawrag/core/structure/viewer.py 와 공유하지 않는다 — 그쪽은 structure
서브시스템(Block/Node)의 검수 화면이고, 여기는 structurize(Document)의 것이다.
다만 **원점 변환 자체는 `core.geometry` 공용**을 쓴다 — 뒤집기 산수가 두 벌이면
한쪽만 고쳐진다. bbox 는 0~1 비율·TOPLEFT 로 통일해 화면이 렌더 배율을 몰라도
되게 한다(PDF prov 는 BOTTOMLEFT — parse_adapter._prov 주석).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from lawrag.core import geometry
from lawrag.core.parse_adapter import Element


def page_sizes(pdf_path: str | Path) -> dict[int, tuple[float, float]]:
    """페이지 번호 → (너비, 높이). PDF 가 아니면 빈 dict."""
    p = Path(pdf_path)
    if p.suffix.lower() != ".pdf" or not p.exists():
        return {}
    import fitz

    doc = fitz.open(str(p))
    try:
        return {i + 1: (pg.rect.width, pg.rect.height) for i, pg in enumerate(doc)}
    finally:
        doc.close()


def norm_bbox(bbox: Optional[list[float]], origin: str,
              size: Optional[tuple[float, float]]) -> Optional[dict]:
    """bbox → 0~1 비율, TOPLEFT 원점. 페이지 크기를 모르면 정규화하지 않는다(None)."""
    if not bbox or not size:
        return None
    w, h = size
    if not w or not h:
        return None
    l, t, r, b = geometry.to_topleft(bbox, origin, h)
    return {"l": round(l / w, 4), "t": round(t / h, 4),
            "r": round(r / w, 4), "b": round(b / h, 4)}


def _item(e: Element, kind: str, reason: str,
          sizes: dict[int, tuple[float, float]], **extra) -> dict:
    d: dict[str, Any] = {"kind": kind, "index": e.index, "page": e.page,
                         "type": e.type, "text": e.content()[:200], "reason": reason}
    box = norm_bbox(e.bbox, e.bbox_origin, sizes.get(e.page))
    if box:
        d["bbox"] = box
    if e.meta:
        d["meta"] = e.meta                     # 페이지·bbox 없는 문서의 출처 (발화 좌표 등)
    d.update(extra)
    return d


def payload(routed) -> dict:
    """router.Routed → 검수 화면 payload.

    격리 문서가 주 대상이지만 통과 문서에도 그대로 돈다 — 미적중 제목 경고를
    확인하는 데 같은 화면을 쓴다.
    """
    doc, parsed, fit = routed.doc, routed.parsed, routed.fitness
    sizes = page_sizes(parsed.path)
    by_index = {e.index: e for e in parsed.elements}

    items: list[dict] = []
    for i in dict.fromkeys(doc.residual):      # 순서 유지 중복 제거
        e = by_index.get(i)
        if e is not None:
            items.append(_item(e, "residual", "형식이 설명하지 못했습니다(기본 구역)", sizes))
    for h in doc.unmatched_headings:
        e = by_index.get(h["index"])
        if e is not None:
            items.append(_item(e, "unmatched_heading",
                               "제목으로 보이는데 어느 마커에도 걸리지 않았습니다",
                               sizes, landed_in=h.get("landed_in", "")))

    return {
        "doc_type": routed.doc_type,
        "source_file": parsed.path,
        "parser": parsed.parser,
        "quarantined": routed.quarantined,
        "fitness": fit.dump(),
        "pages": {str(n): {"width": w, "height": h} for n, (w, h) in sizes.items()},
        # 잡힌 구조의 요약 — 못 먹은 자리와 대조해 보기 위한 것
        "sections": [{"section_id": s.section_id, "page_range": s.page_range(),
                      "elements": len(s.elements)} for s in doc.sections],
        "items": items,
    }
