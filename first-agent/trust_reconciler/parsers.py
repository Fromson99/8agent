"""P1. 파싱 — 도클링으로 문서를 블록으로 만든다.

정규표현식을 쓰지 않는다. 이 모듈은 "텍스트를 출처와 함께 정확히 꺼내는 일"만 하고,
그 텍스트가 무슨 의미인지는 전혀 판단하지 않는다. 의미 판단은 P2 태깅(LLM)이 한다.

## 도클링 설정 근거 (dataset 실측)

    do_ocr = False
        텍스트 레이어가 있는 PDF 에 OCR 을 돌리면 39초 → 6초로 6배 느려지고,
        page_footer 에 "A 是 ! sxuanties (Korea)" 같은 쓰레기가 섞였다.
        텍스트가 안 나오는 페이지가 있으면 그 문서만 OCR 을 켜서 다시 돌린다.

    do_table_structure = True
        계약서의 실제 값은 별지 세부내역서(표)에 있다. 반드시 켜야 한다.

## pdfplumber 보완이 필요한 이유

도클링이 표를 놓치는 경우가 있다 — 유안타 계약서는 tables 0개였다(별지1 세부내역서를 못 잡음).
격자선 기반인 pdfplumber 가 잡는 표가 있어서, 도클링이 못 찾은 페이지만 보완한다.
둘 다 놓쳐도 치명적이지 않다. 표가 서술로 풀려도 텍스트는 남아 있고, 값 추출은 LLM 이 한다.
"""

from __future__ import annotations

import hashlib
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from .docmodel import DocBlock, DocMeta, ParsedDocument, Provenance
from .textkit import clean, is_blank

SUPPORTED = (".pdf", ".docx", ".md", ".txt")

# 대사에 쓸모없는 블록 — 머리말/꼬리말은 페이지마다 반복되어 태깅을 방해한다
DROP_KINDS = {"page_header", "page_footer"}

_CONVERTER = None


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


# ===========================================================================
# 도클링
# ===========================================================================

def _converter(ocr: bool):
    """도클링 컨버터. 모델 로딩이 무거워 프로세스당 한 번만 만든다."""
    global _CONVERTER
    key = ("ocr", ocr)
    if _CONVERTER and _CONVERTER[0] == key:
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
    _CONVERTER = (key, conv)
    return conv


def _docling_version() -> str:
    try:
        from importlib.metadata import version
        return version("docling")
    except Exception:            # pragma: no cover
        return "?"


def _page_of(item) -> Optional[int]:
    prov = getattr(item, "prov", None)
    if prov:
        return getattr(prov[0], "page_no", None)
    return None


def _bbox_of(item) -> Optional[list]:
    prov = getattr(item, "prov", None)
    if not prov:
        return None
    bb = getattr(prov[0], "bbox", None)
    if bb is None:
        return None
    try:
        return [bb.l, bb.t, bb.r, bb.b]
    except AttributeError:       # pragma: no cover
        return None


def _grid_rows(table) -> list[list[str]]:
    grid = getattr(getattr(table, "data", None), "grid", None) or []
    rows = []
    for row in grid:
        cells = [clean(getattr(c, "text", "") or "") for c in row]
        if any(cells):
            rows.append(cells)
    return rows


def _parse_with_docling(path: Path, doc_id: str) -> tuple[list[DocBlock], list[str], dict, str]:
    warnings: list[str] = []
    blocks: list[DocBlock] = []

    conv = _converter(ocr=False)
    doc = conv.convert(str(path)).document

    texts = list(getattr(doc, "texts", []))
    tables = list(getattr(doc, "tables", []))

    if not texts and not tables:
        # 텍스트 레이어가 없는 스캔 문서 — 이때만 OCR 을 켠다
        warnings.append("텍스트 레이어가 없어 OCR 로 재파싱했습니다 (정확도가 낮을 수 있음)")
        doc = _converter(ocr=True).convert(str(path)).document
        texts = list(getattr(doc, "texts", []))
        tables = list(getattr(doc, "tables", []))

    order = 0
    dropped = 0
    for t in texts:
        kind = str(getattr(t, "label", "text")).split(".")[-1].strip("'\"").lower()
        if kind in DROP_KINDS:
            dropped += 1
            continue
        text = clean(getattr(t, "text", ""))
        if is_blank(text):
            continue
        blocks.append(DocBlock(
            block_id=f"{doc_id}_b{order:04d}", order=order, kind=kind, text=text,
            provenance=Provenance(page=_page_of(t), doc_ref=getattr(t, "self_ref", ""),
                                  bbox=_bbox_of(t)),
            source="docling"))
        order += 1

    for tb in tables:
        rows = _grid_rows(tb)
        if not rows:
            continue
        blocks.append(DocBlock(
            block_id=f"{doc_id}_b{order:04d}", order=order, kind="table", table=rows,
            provenance=Provenance(page=_page_of(tb), doc_ref=getattr(tb, "self_ref", ""),
                                  bbox=_bbox_of(tb)),
            source="docling"))
        order += 1

    stats = {
        "docling_texts": len(texts),
        "docling_tables": len(tables),
        "dropped_header_footer": dropped,
        "section_headers": sum(1 for b in blocks if b.kind == "section_header"),
    }
    parser = f"docling {_docling_version()} (ocr=off, tables=on)"
    return blocks, warnings, stats, parser


def _supplement_tables(path: Path, blocks: list[DocBlock], doc_id: str,
                       stats: dict, warnings: list[str]) -> None:
    """도클링이 표를 하나도 못 찾은 경우에만 pdfplumber 로 보완한다."""
    if any(b.kind == "table" for b in blocks):
        return
    try:
        import pdfplumber
    except ImportError:          # pragma: no cover
        return

    found = 0
    order = max((b.order for b in blocks), default=-1) + 1
    with pdfplumber.open(str(path)) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            try:
                tables = page.extract_tables() or []
            except Exception:    # pragma: no cover
                continue
            for tbl in tables:
                rows = [[clean(c or "") for c in row] for row in tbl if row]
                rows = [r for r in rows if any(r)]
                if len(rows) < 2 or all(len(r) <= 1 for r in rows):
                    continue     # 한 열로 뭉개진 것은 표가 아니라 서술이다
                blocks.append(DocBlock(
                    block_id=f"{doc_id}_b{order:04d}", order=order, kind="table", table=rows,
                    provenance=Provenance(page=pno), source="pdfplumber"))
                order += 1
                found += 1
    stats["pdfplumber_tables"] = found
    if found:
        warnings.append(f"도클링이 표를 찾지 못해 pdfplumber 로 {found}개를 보완했습니다")
    else:
        warnings.append("표가 하나도 인식되지 않았습니다 — 별지·별표 값이 서술로 처리됩니다")


# ===========================================================================
# DOCX / 텍스트 — 도클링을 거치지 않고 원본 구조를 그대로 읽는다
# ===========================================================================

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_style_kind(pPr) -> str:
    """Word 스타일 이름으로 제목 여부만 판정한다. 문자열 연산이며 패턴 매칭이 아니다."""
    if pPr is None:
        return "text"
    st = pPr.find(f"{_W}pStyle")
    if st is None:
        return "text"
    val = (st.get(f"{_W}val") or "").lower()
    return "section_header" if ("heading" in val or "제목" in val) else "text"


def _parse_docx(path: Path, doc_id: str) -> tuple[list[DocBlock], list[str], dict, str]:
    blocks: list[DocBlock] = []
    warnings: list[str] = []
    with zipfile.ZipFile(path) as z:
        body = ET.fromstring(z.read("word/document.xml")).find(f"{_W}body")
    if body is None:
        raise ValueError(f"DOCX 본문이 비어 있습니다: {path.name}")

    order = 0
    for child in body:
        if child.tag == f"{_W}p":
            text = clean("".join(t.text or "" for t in child.iter(f"{_W}t")))
            if is_blank(text):
                continue
            blocks.append(DocBlock(
                block_id=f"{doc_id}_b{order:04d}", order=order,
                kind=_docx_style_kind(child.find(f"{_W}pPr")), text=text,
                provenance=Provenance(page=1), source="docx"))
            order += 1
        elif child.tag == f"{_W}tbl":
            rows = []
            for tr in child.findall(f"{_W}tr"):
                cells = [clean("".join(p.text or "" for tc_p in tc.iter(f"{_W}p")
                                       for p in tc_p.iter(f"{_W}t")))
                         for tc in tr.findall(f"{_W}tc")]
                if any(cells):
                    rows.append(cells)
            if rows:
                blocks.append(DocBlock(
                    block_id=f"{doc_id}_b{order:04d}", order=order, kind="table", table=rows,
                    provenance=Provenance(page=1), source="docx"))
                order += 1

    stats = {"section_headers": sum(1 for b in blocks if b.kind == "section_header")}
    if not stats["section_headers"]:
        warnings.append("DOCX 에 제목 스타일이 없습니다 — 섹션은 태깅으로만 형성됩니다")
    return blocks, warnings, stats, "docx(zip+xml)"


def _split_md_row(line: str) -> Optional[list[str]]:
    """마크다운 표 행을 셀로 쪼갠다. str 메서드만 쓴다."""
    s = line.strip()
    if len(s) < 2 or not s.startswith("|") or not s.endswith("|"):
        return None
    cells = [clean(c) for c in s[1:-1].split("|")]
    # 구분선(|---|---|)은 셀이 대시·콜론뿐이다
    if all(c and set(c) <= set("-: ") for c in cells):
        return None
    return cells


def _parse_text(path: Path, doc_id: str) -> tuple[list[DocBlock], list[str], dict, str]:
    """TXT/MD. 마크다운 헤딩(#)만 제목으로 보고, 나머지 해석은 하지 않는다.

    **줄 하나가 블록 하나다.** 빈 줄 기준으로 문단을 뭉치지 않는다.
    실측 근거: 뭉쳤더니 계약서 제1조~제17조가 1,795자 한 블록이 되었고,
    한 블록에는 태그가 하나만 붙으므로 태깅이 아예 불가능해졌다.
    잘게 쪼개는 쪽은 안전하다 — P2 가 같은 태그의 연속 블록을 다시 묶기 때문이다.
    """
    blocks: list[DocBlock] = []
    order = 0
    pending: list[list[str]] = []

    def add(kind: str, text: str = "", table=None):
        nonlocal order
        blocks.append(DocBlock(block_id=f"{doc_id}_b{order:04d}", order=order,
                               kind=kind, text=text, table=table,
                               provenance=Provenance(page=1), source="text"))
        order += 1

    def flush_table():
        nonlocal pending
        rows, pending = pending, []
        if len(rows) >= 2:
            add("table", table=rows)
        else:
            for r in rows:
                add("text", clean(" ".join(r)))

    for raw in path.read_text(encoding="utf-8").split("\n"):
        cells = _split_md_row(raw)
        if cells is not None:
            pending.append(cells)
            continue
        flush_table()
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#"):
            title = clean(s.lstrip("#"))
            if title:
                add("section_header", title)
            continue
        add("text", clean(s))
    flush_table()

    stats = {"section_headers": sum(1 for b in blocks if b.kind == "section_header")}
    return blocks, [], stats, "text"


# ===========================================================================
# 공개 API
# ===========================================================================

def parse(file_path: str, doc_role: str, doc_id: Optional[str] = None) -> ParsedDocument:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {file_path}")
    if doc_role not in ("contract", "product_statement", "change_table"):
        raise ValueError(f"doc_role 이 올바르지 않습니다: {doc_role}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"지원하지 않는 형식입니다: {suffix} ({'/'.join(SUPPORTED)})")

    content_hash = _file_hash(path)
    doc_id = doc_id or f"d{content_hash[:8]}"

    if suffix == ".pdf":
        blocks, warnings, stats, parser = _parse_with_docling(path, doc_id)
        _supplement_tables(path, blocks, doc_id, stats, warnings)
    elif suffix == ".docx":
        blocks, warnings, stats, parser = _parse_docx(path, doc_id)
    else:
        blocks, warnings, stats, parser = _parse_text(path, doc_id)

    blocks.sort(key=lambda b: b.order)
    if not blocks:
        warnings.append("문서에서 어떤 내용도 추출하지 못했습니다")

    stats["blocks"] = len(blocks)
    stats["tables"] = sum(1 for b in blocks if b.kind == "table")
    return ParsedDocument(
        doc_id=doc_id, doc_role=doc_role, source_path=str(path),
        source_format=suffix.lstrip("."), parser=parser, content_hash=content_hash,
        meta=DocMeta(title=clean(path.stem)), blocks=blocks,
        warnings=warnings, stats=stats)
