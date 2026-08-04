"""T1. born-digital 판별 + Docling 파싱 — 인스턴스 계층의 원재료.

이 단계는 도메인을 모른다. "무엇이 어디에 있다"만 낸다(§C1).
온톨로지를 참조하지 않는 것이 의도다 — §C7-2 "Part A 추출은 온톨로지 참조 없이 범용으로".

## 설정 근거 (dataset 실측)

    do_ocr = False           텍스트 레이어가 있는 PDF 에 OCR 을 돌리니 39초 → 6초로 느려지고
                             꼬리말에 "A 是 ! sxuanties (Korea)" 같은 쓰레기가 섞였다.
                             born-digital 판별에서 텍스트가 없는 문서만 OCR 로 재시도한다.
    do_table_structure = True  계약서의 실제 값은 별지 표에 있다. 반드시 켠다.

## 표 인식 폴백

도클링이 표를 놓치는 경우가 있다 — 유안타 계약서에서 tables=0(별지1을 통째로 놓침).
격자선 기반인 pdfplumber 가 잡는 표가 있어 보완한다(§7 엣지 케이스의 PP-StructureV3 자리에
우선 pdfplumber 를 둔다 — 이미 검증됐고 의존성이 가볍다).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# 페이지마다 반복되어 구조 인식을 방해하는 라벨.
# **버리지 않고 표시만 한다.** 파싱 단계는 도메인을 모르므로 무엇이 버려도 되는지 판단할 수 없다.
# 실측: 도클링이 ss2207 의 `[별지1]` 을 page_header 로 분류했고, 그걸 버렸더니
# 별지1 파트를 통째로 놓쳤다. 무엇을 무시할지는 온톨로지를 아는 structure.py 가 정한다.
FURNITURE_LABELS = {"page_header", "page_footer"}

_CONVERTER: Optional[tuple] = None


@dataclass
class Element:
    """도클링이 낸 요소 하나 — 정규화된 형태."""
    index: int                        # reading_order
    kind: str                         # text | list_item | section_header | table | footnote | ...
    text: str = ""
    table: Optional[list[list[str]]] = None
    page: int = 1
    bbox: Optional[list[float]] = None
    doc_ref: str = ""
    source: str = "docling"
    furniture: bool = False           # 머리말/꼬리말 후보 — 버리지 않고 표시만

    def content(self) -> str:
        if self.kind == "table" and self.table:
            return "\n".join(" | ".join(c for c in row) for row in self.table)
        return self.text


@dataclass
class ParseResult:
    path: str
    doc_id: str
    born_digital: bool
    parser: str
    elements: list[Element] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def pages(self) -> int:
        return max((e.page for e in self.elements), default=0)


# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return " ".join((s or "").replace("\xa0", " ").split())


def is_born_digital(path: Path, min_chars: int = 200) -> tuple[bool, dict]:
    """PyMuPDF 로 텍스트 레이어 유무 확인 (§6 T1)."""
    import fitz

    doc = fitz.open(str(path))
    total, empty = 0, 0
    for p in doc:
        t = p.get_text().strip()
        total += len(t)
        if not t:
            empty += 1
    n = doc.page_count
    doc.close()
    stats = {"pages": n, "text_chars": total, "empty_pages": empty}
    return total >= min_chars and empty < n, stats


def _converter(ocr: bool):
    global _CONVERTER
    if _CONVERTER and _CONVERTER[0] == ocr:
        return _CONVERTER[1]

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = ocr
    opts.do_table_structure = True
    opts.table_structure_options.do_cell_matching = True
    conv = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    _CONVERTER = (ocr, conv)
    return conv


def _docling_version() -> str:
    try:
        from importlib.metadata import version
        return version("docling")
    except Exception:            # pragma: no cover
        return "?"


def _prov(item) -> tuple[Optional[int], Optional[list[float]]]:
    prov = getattr(item, "prov", None)
    if not prov:
        return None, None
    page = getattr(prov[0], "page_no", None)
    bb = getattr(prov[0], "bbox", None)
    box = None
    if bb is not None:
        try:
            box = [round(bb.l, 2), round(bb.t, 2), round(bb.r, 2), round(bb.b, 2)]
        except AttributeError:   # pragma: no cover
            box = None
    return page, box


def _grid(table) -> list[list[str]]:
    grid = getattr(getattr(table, "data", None), "grid", None) or []
    rows = []
    for row in grid:
        cells = [_norm(getattr(c, "text", "") or "") for c in row]
        if any(cells):
            rows.append(cells)
    return rows


def _supplement_tables(path: Path, elements: list[Element], stats: dict,
                       warnings: list[str]) -> None:
    if any(e.kind == "table" for e in elements):
        return
    try:
        import pdfplumber
    except ImportError:          # pragma: no cover
        return
    found = 0
    idx = max((e.index for e in elements), default=-1) + 1
    with pdfplumber.open(str(path)) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            try:
                tables = page.extract_tables() or []
            except Exception:    # pragma: no cover
                continue
            for tbl in tables:
                rows = [[_norm(c or "") for c in r] for r in tbl if r]
                rows = [r for r in rows if any(r)]
                if len(rows) < 2 or all(len(r) <= 1 for r in rows):
                    continue     # 한 열로 뭉개진 것은 표가 아니라 서술이다
                elements.append(Element(index=idx, kind="table", table=rows,
                                        page=pno, source="pdfplumber"))
                idx += 1
                found += 1
    stats["pdfplumber_tables"] = found
    warnings.append(f"도클링이 표를 찾지 못해 pdfplumber 로 {found}개를 보완했습니다"
                    if found else
                    "표가 하나도 인식되지 않았습니다 — 별지 값이 서술로 처리됩니다")


def parse(pdf_path: str | Path) -> ParseResult:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 PDF 를 찾을 수 없습니다: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"v1 은 PDF 만 지원합니다: {path.suffix}")

    born, pdf_stats = is_born_digital(path)
    warnings: list[str] = []
    if not born:
        warnings.append("born-digital 이 아닙니다 — OCR 로 파싱하며 정확도가 낮을 수 있습니다 (§10 범위 밖)")

    doc = _converter(ocr=not born).convert(str(path)).document
    texts = list(getattr(doc, "texts", []))
    tables = list(getattr(doc, "tables", []))

    elements: list[Element] = []
    idx, furniture = 0, 0
    for t in texts:
        kind = str(getattr(t, "label", "text")).split(".")[-1].strip("'\"").lower()
        text = _norm(getattr(t, "text", ""))
        if not text:
            continue
        is_furn = kind in FURNITURE_LABELS
        furniture += int(is_furn)
        page, bbox = _prov(t)
        elements.append(Element(index=idx, kind=kind, text=text, page=page or 1,
                                bbox=bbox, doc_ref=getattr(t, "self_ref", ""),
                                furniture=is_furn))
        idx += 1

    for tb in tables:
        rows = _grid(tb)
        if not rows:
            continue
        page, bbox = _prov(tb)
        elements.append(Element(index=idx, kind="table", table=rows, page=page or 1,
                                bbox=bbox, doc_ref=getattr(tb, "self_ref", "")))
        idx += 1

    stats = {
        "docling_texts": len(texts),
        "docling_tables": len(tables),
        "furniture_elements": furniture,
        **pdf_stats,
    }
    _supplement_tables(path, elements, stats, warnings)
    elements.sort(key=lambda e: e.index)
    stats["elements"] = len(elements)
    stats["tables"] = sum(1 for e in elements if e.kind == "table")

    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    ocr_note = "ocr=on" if not born else "ocr=off"
    return ParseResult(
        path=str(path), doc_id=digest, born_digital=born,
        parser=f"docling {_docling_version()} ({ocr_note}, tables=on)",
        elements=elements, warnings=warnings, stats=stats)
