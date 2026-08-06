r"""T2c. 격자 복원 — 표로 인식되지 못한 격자를 **좌표만** 받아 되찾는다.

    recover(path, elements, recognize=...) -> (elements, stats, warnings)

## 무엇을 어디서 받는가 — 격자와 글자를 가른다

이 모듈의 계약은 한 줄이다.

    recognize(path) -> {쪽번호: [(cells, bbox_BOTTOMLEFT), ...]}
        cells: [Cell(row, col, row_span, col_span, bbox)]   ← **글자는 비어 있다**

**셀 텍스트를 받지 않는다.** 실측이 이유다(contract_filled 골든):

    docling      '신탁금액 금 원정 (₩) 일억 100,000,000 계약서제2조'  → 1억 ✓
    pdfplumber   '신탁금액 금 일 억원정 (₩ 1 0 0 , 0 0 0 , 0 0 0 )'  → 파싱 실패 ✗

자간 넓은 양식 글자를 격자 엔진이 낱자로 끊었고 골든 테스트가 깨졌다. 금액·비율은
한 글자가 판정을 바꾸므로 판독을 갈아 끼우면 안 된다. **격자는 인식기, 글자는 파서.**

그래서 인식기를 갈아 끼울 수 있다 — pdfplumber 든 VLM 이든 위 모양만 돌려주면 된다.
같은 잣대로 비교할 수도 있다(어느 인식기가 몇 개를 되찾고 몇 글자를 흘리는가).

## 왜 필요한가 (실측)

    ss2207 (빈 양식)        p5 신탁계약 세부내역 → 표 아님, 31개 텍스트로 흩어짐
    contract_filled (기재)  p5 같은 표          → docling 이 10행×7열로 정확히 인식

같은 레이아웃인데 채워지면 잡고 비면 못 잡는다. `do_cell_matching` 이 예측 격자를
실제 텍스트 셀에 맞춰 확정하는데, 칸이 비면 맞출 것이 없어 머리글 행으로 무너진다.
실패는 **격자 탐지**이지 셀 판독이 아니다.

흩어지면 값은 다 남지만 **행·열 관계**를 잃는다. `금 원정` 이 `신탁금액` 의 값이고
`계약서제2조` 가 그 근거라는 연결이 사라진다 — 값은 있는데 무엇의 값인지가 없다.

## 흘린 글자를 **세기만 하지 않는다**

앞선 판은 흘린 글자 수만 세고 무엇을 흘렸는지 안 남겼다. 그러면 임계값(`KEEP_T`)을
실측으로 고칠 수가 없다 — "5% 흘렸다"만 알고 그 5% 가 무엇이었는지 모른다.
지금은 흘린 조각을 그대로 남긴다(`dropped_pieces`). 그 목록이 다음 실측의 재료다.

이 단계는 기본으로 **꺼져 있다.** `recognize` 를 주어야 돈다 — 인식기가 무엇인지
부르는 쪽이 정하고, 아무것도 안 주면 docling 이 낸 표가 그대로 간다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

# 되찾은 격자가 이만큼은 글자를 담아야 채택한다.
# **실측으로 뽑은 값이 아니다** — 임계이고, `dropped_pieces` 가 쌓이면 고칠 자리다.
KEEP_T = 0.95
# 격자다움 — 이보다 작으면 흩어진 원본이 더 나은 표현이다(실측: 1행 4열로 잡힌
# 체크박스 덩어리보다 24개 개별 항목이 낫다).
MIN_ROWS = 2
MIN_COLS = 2
# 조각 중심이 셀 경계를 살짝 넘는 일이 흔하다. 이 여유까지는 그 칸으로 본다.
PAD = 1.5


def _norm(s: str) -> str:
    return " ".join((s or "").replace("\xa0", " ").split())


def _to_topleft(bbox: list[float], origin: str, height: float) -> list[float]:
    """어떤 원점으로 왔든 TOPLEFT (x0, top, x1, bottom) 로.

    docling prov 는 BOTTOMLEFT, 셀은 TOPLEFT 다. 통일하지 않고 비교하면 위아래가
    뒤집혀 엉뚱한 칸에 담긴다.
    """
    if str(origin).upper() == "BOTTOMLEFT":
        return [bbox[0], height - max(bbox[1], bbox[3]),
                bbox[2], height - min(bbox[1], bbox[3])]
    return [bbox[0], min(bbox[1], bbox[3]), bbox[2], max(bbox[1], bbox[3])]


def _cell_holding(cells: list, box: list[float]):
    """조각의 **중심**을 품는 셀. 겹침 면적이 아니라 중심을 쓴다 — 글자가 셀 경계를
    살짝 넘는 일이 흔해서 면적으로 재면 큰 셀이 다 가져간다."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    for c in cells:
        if c.bbox and (c.bbox[0] - PAD <= cx <= c.bbox[2] + PAD
                       and c.bbox[1] - PAD <= cy <= c.bbox[3] + PAD):
            return c
    return None


def _pieces(element, height: float):
    """요소가 칸에 담을 **조각**들. (TOPLEFT bbox, 글자, 열머리, 행머리).

    표 요소는 셀 단위로 쪼갠다 — docling 이 낸 껍데기 표를 되찾은 격자 위에 다시
    앉히려면 통째로가 아니라 셀별로 떨어져야 한다. 머리글 표시도 이때 따라온다.
    다만 두 격자의 셀이 1:1 로 대응한다는 보장은 없다(알려진 한계).
    """
    if getattr(element, "table", None) is not None:
        for c in element.table.cells:
            if c.text and c.bbox:
                yield (_to_topleft(c.bbox, c.origin, height), c.text,
                       c.is_col_header, c.is_row_header)
        return
    if getattr(element, "text", "") and getattr(element, "bbox", None):
        yield (_to_topleft(element.bbox, element.bbox_origin, height),
               element.text, False, False)


def fill(cells: list, elements: list, height: float) -> dict[str, Any]:
    """요소의 글자를 칸에 담는다.

    반환: `{placed, dropped, dropped_pieces}`. **흘린 조각을 그대로 남긴다** —
    수만 세면 임계값을 고칠 근거가 없다. 이 목록이 다음 실측의 재료다.
    """
    bucket: dict[int, list] = {}
    placed = dropped = 0
    lost: list[dict] = []
    for e in elements:
        for box, text, col_h, row_h in _pieces(e, height):
            cell = _cell_holding(cells, box)
            if cell is None:
                dropped += len(text)
                lost.append({"element": getattr(e, "index", -1),
                             "text": text[:60], "chars": len(text),
                             "box": [round(v, 1) for v in box]})
                continue
            bucket.setdefault(id(cell), []).append((box[1], box[0], text))
            if col_h:
                cell.is_col_header = True
            if row_h:
                cell.is_row_header = True
            placed += len(text)
    for cell in cells:
        got = bucket.get(id(cell))
        if got:
            cell.text = _norm(" ".join(t for _, _, t in sorted(got)))
    return {"placed": placed, "dropped": dropped, "dropped_pieces": lost}


def _covered(element, box: list[float]) -> bool:
    """요소의 중심이 표 안에 있는가. 원점이 섞이므로 BOTTOMLEFT 로만 비교한다."""
    bb = getattr(element, "bbox", None)
    if not bb or str(getattr(element, "bbox_origin", "")).upper() != "BOTTOMLEFT":
        return False
    cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
    lo, hi = min(box[1], box[3]), max(box[1], box[3])
    return box[0] <= cx <= box[2] and lo <= cy <= hi


def recover(path: str | Path, elements: list, *,
            recognize: Optional[Callable[[Any], dict]] = None,
            page_heights: Optional[dict[int, float]] = None,
            ) -> tuple[list, dict, list[str]]:
    """흩어진 격자를 표로 되돌린다. `recognize` 가 없으면 **아무것도 하지 않는다.**"""
    from core.parse_adapter import Element, Table

    stats: dict = {"recovered_tables": 0, "absorbed_elements": 0,
                   "rejected_grids": 0, "dropped_chars": 0, "dropped_pieces": []}
    warnings: list[str] = []
    if recognize is None:
        return list(elements), stats, warnings

    grids = recognize(path) or {}
    heights = page_heights or {}
    absorbed: set[int] = set()
    inserts: dict[int, list] = {}

    for pno, found in sorted(grids.items()):
        on_page = [e for e in elements if e.page == pno]
        height = heights.get(pno, 0.0)
        for cells, box in found:
            if not cells or not height:
                continue
            n_rows = max(c.row + c.row_span for c in cells)
            n_cols = max(c.col + c.col_span for c in cells)
            if n_rows < MIN_ROWS or n_cols < MIN_COLS:
                continue                      # 격자다움 없음 — 원본이 더 낫다
            hit = [e for e in on_page
                   if e.index not in absorbed and not e.is_furniture
                   and _covered(e, box)]
            if not hit:
                continue
            got = fill(cells, hit, height)
            if got["dropped"] > got["placed"] * (1 - KEEP_T):
                # 선이 실제 칸과 어긋났다. 표 하나를 얻자고 본문을 잃지 않는다.
                stats["rejected_grids"] += 1
                stats["dropped_pieces"] += got["dropped_pieces"][:5]
                continue
            stats["dropped_chars"] += got["dropped"]
            stats["dropped_pieces"] += got["dropped_pieces"][:5]
            absorbed.update(e.index for e in hit)
            meta = {"recovered_by": getattr(recognize, "__name__", "recognize"),
                    "absorbed": len(hit), "dropped_chars": got["dropped"]}
            swallowed = [e.index for e in hit if e.is_table]
            if swallowed:
                meta["replaced_parser_tables"] = swallowed
            inserts.setdefault(min(e.index for e in hit), []).append(
                Element(index=-1, type="table",
                        table=Table(n_rows=n_rows, n_cols=n_cols, cells=cells),
                        page=pno, bbox=box, bbox_origin="BOTTOMLEFT", meta=meta))
            stats["recovered_tables"] += 1
            stats["absorbed_elements"] += len(hit)

    out: list = []
    for e in elements:
        for tbl in inserts.get(e.index, []):
            out.append(tbl)
        if e.index not in absorbed:
            out.append(e)
    for i, e in enumerate(out):
        e.index = i

    if stats["recovered_tables"]:
        warnings.append(
            f"표로 인식되지 못한 격자 {stats['recovered_tables']}개를 좌표로 되찾아 "
            f"요소 {stats['absorbed_elements']}개를 표로 합쳤습니다"
            + (f" (칸 밖으로 흘린 글자 {stats['dropped_chars']}자)"
               if stats["dropped_chars"] else ""))
    if stats["rejected_grids"]:
        warnings.append(
            f"격자 {stats['rejected_grids']}개는 글자가 칸 밖으로 흘러 채택하지 "
            f"않았습니다 — 그 자리는 원본 요소 그대로입니다")
    return out, stats, warnings


# ---------------------------------------------------------------------------
# 인식기 하나 — pdfplumber 의 선분. VLM 인식기도 같은 모양을 돌려주면 된다.
# ---------------------------------------------------------------------------

TABLE_SETTINGS = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}


def _spans(rows, i: int, j: int) -> tuple[int, int]:
    """(row_span, col_span). pdfplumber 는 병합에 덮인 칸을 `None` 으로 준다."""
    cell = rows[i].cells[j]
    col_span = 1
    for k in range(j + 1, len(rows[i].cells)):
        if rows[i].cells[k] is not None:
            break
        col_span += 1
    row_span = 1
    for r in range(i + 1, len(rows)):
        if j >= len(rows[r].cells) or rows[r].cells[j] is not None:
            break
        if cell[3] < rows[r].bbox[3] - 1.0:
            break
        row_span += 1
    return row_span, col_span


def pdfplumber_lines(path) -> dict[int, list]:
    """PDF 콘텐츠 스트림의 **실제 선분**으로 격자를 찾는다. 글자는 담지 않는다.

    `text` 전략은 쓰지 않는다 — 같은 페이지를 76행×15열로 과분할해 쓸모가 없었다.
    """
    from core.parse_adapter import Cell

    try:
        import pdfplumber
    except ImportError:                          # pragma: no cover - 선택 의존성
        return {}

    out: dict[int, list] = {}
    with pdfplumber.open(str(path)) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            h = float(page.height)
            for found in page.find_tables(table_settings=TABLE_SETTINGS):
                rows = found.rows
                cells = []
                for i, row in enumerate(rows):
                    for j, bb in enumerate(row.cells):
                        if bb is None:
                            continue
                        rs, cs = _spans(rows, i, j)
                        cells.append(Cell(text="", row=i, col=j,
                                          row_span=rs, col_span=cs,
                                          bbox=[round(v, 2) for v in bb],
                                          origin="TOPLEFT"))
                if not cells:
                    continue
                x0, top, x1, bottom = found.bbox
                out.setdefault(pno, []).append(
                    (cells, [round(x0, 2), round(h - top, 2),
                             round(x1, 2), round(h - bottom, 2)]))
    return out


def page_heights(path) -> dict[int, float]:
    import fitz

    doc = fitz.open(str(path))
    try:
        return {i + 1: float(p.rect.height) for i, p in enumerate(doc)}
    finally:
        doc.close()
