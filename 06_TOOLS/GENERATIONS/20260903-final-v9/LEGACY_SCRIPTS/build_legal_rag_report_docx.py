#!/usr/bin/env python3
"""Build the Korean legal-domain RAG experiment report as a polished DOCX."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from generate_legal_rag_report_diagrams import generate_all


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/LEGAL_DOMAIN_RAG_EXPERIMENTS_COMPREHENSIVE_REPORT_2026-08-31.md"
OUTPUT = ROOT / "artifacts/법률도메인_RAG_구조화_실험_종합보고서_2026-08-31_다이어그램_보강본.docx"
ADR_ROOT = ROOT / "docs/adr"
DIAGRAM_ROOT = ROOT / "artifacts/legal_rag_report_diagrams"

FIGURES = {
    "{{FIGURE_END_TO_END}}": (
        DIAGRAM_ROOT / "01_end_to_end_pipeline.png",
        "그림 1. 법률 질문에서 근거형 답변까지의 전체 처리 흐름",
        "질문 구조화, 법체계 진입, 회수와 관계 확장, 명제 컴파일, 근거형 답변의 순차 흐름",
    ),
    "{{FIGURE_DATA_LAYERS}}": (
        DIAGRAM_ROOT / "02_data_schema_layers.png",
        "그림 2. Legal Graph의 네 데이터 계층과 공통 원문 좌표",
        "canonical, observation, projection, runtime 계층과 모든 계층을 원문으로 연결하는 좌표 spine",
    ),
    "{{FIGURE_QUESTION_SCHEMA}}": (
        DIAGRAM_ROOT / "03_question_schema_funnel.png",
        "그림 3. 질문 원문이 검색 신호와 법률 명제로 강화되는 과정",
        "원문, mention, closed binding, issue fact rule, coverage applicability의 단계적 질문 스키마",
    ),
    "{{FIGURE_TWO_LANE}}": (
        DIAGRAM_ROOT / "04_retrieval_compiler_lanes.png",
        "그림 4. 회수용 스키마와 컴파일용 스키마의 이중 경로",
        "넓게 찾는 fail-open 회수 경로와 명제별로 검증하는 claim-local fail-closed 컴파일 경로",
    ),
    "{{FIGURE_ADR_EVOLUTION}}": (
        DIAGRAM_ROOT / "05_adr_evolution_map.png",
        "그림 5. ADR 실험 계열의 발전 지도",
        "검색 도달성에서 데이터 정본화, Legal Graph, 계층형 조사, 법률 컴파일러로 이동한 ADR 흐름",
    ),
}

PAGE_WIDTH_DXA = 12240
PAGE_HEIGHT_DXA = 15840
MARGIN_DXA = 1440
CONTENT_WIDTH_DXA = 9360
TABLE_INDENT_DXA = 120

NAVY = "17365D"
BLUE = "2E74B5"
DARK_BLUE = "1F4D78"
INK = "1F2937"
MUTED = "667085"
LIGHT_BLUE = "E8EEF5"
LIGHT_GRAY = "F2F4F7"
CALLOUT = "F4F6F9"
WHITE = "FFFFFF"
GOLD = "8A6D1F"


def _set_run_font(run, *, size: float | None = None, bold: bool | None = None,
                  italic: bool | None = None, color: str | None = None,
                  mono: bool = False) -> None:
    name = "Consolas" if mono else "Calibri"
    east_asia = "Malgun Gothic"
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.rFonts
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    fonts.set(qn("w:ascii"), name)
    fonts.set(qn("w:hAnsi"), name)
    fonts.set(qn("w:eastAsia"), east_asia)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)


def _set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _set_cell_margins(cell, top=80, start=120, bottom=80, end=120) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for edge, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        tag = tc_mar.find(qn(f"w:{edge}"))
        if tag is None:
            tag = OxmlElement(f"w:{edge}")
            tc_mar.append(tag)
        tag.set(qn("w:w"), str(value))
        tag.set(qn("w:type"), "dxa")


def _set_table_geometry(table, widths: list[int]) -> None:
    total = sum(widths)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(total))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(TABLE_INDENT_DXA))
    tbl_ind.set(qn("w:type"), "dxa")
    layout = tbl_pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")

    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(widths[idx]))
            tc_w.set(qn("w:type"), "dxa")
            cell.width = Inches(widths[idx] / 1440)
            _set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def _prevent_row_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    cant_split.set(qn("w:val"), "true")
    tr_pr.append(cant_split)


def _paragraph_border(paragraph, *, left: str | None = None, bottom: str | None = None,
                      color: str = BLUE, size: int = 12, space: int = 6) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        p_pr.append(p_bdr)
    for edge, style in (("left", left), ("bottom", bottom)):
        if style is None:
            continue
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:val"), style)
        node.set(qn("w:sz"), str(size))
        node.set(qn("w:space"), str(space))
        node.set(qn("w:color"), color)
        p_bdr.append(node)


def _paragraph_shading(paragraph, fill: str) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    shd = p_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        p_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _add_page_field(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("Page ")
    _set_run_font(run, size=9, color=MUTED)
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    r = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), MUTED)
    size = OxmlElement("w:sz")
    size.set(qn("w:val"), "18")
    r_pr.append(color)
    r_pr.append(size)
    r.append(r_pr)
    t = OxmlElement("w:t")
    t.text = "1"
    r.append(t)
    fld.append(r)
    paragraph._p.append(fld)


def _ensure_numbering(doc: Document) -> tuple[int, int]:
    numbering = doc.part.numbering_part.element

    def add_abstract(abstract_id: int, *, bullet: bool) -> None:
        abstract = OxmlElement("w:abstractNum")
        abstract.set(qn("w:abstractNumId"), str(abstract_id))
        multi = OxmlElement("w:multiLevelType")
        multi.set(qn("w:val"), "multilevel")
        abstract.append(multi)
        for ilvl in range(3):
            lvl = OxmlElement("w:lvl")
            lvl.set(qn("w:ilvl"), str(ilvl))
            start = OxmlElement("w:start")
            start.set(qn("w:val"), "1")
            lvl.append(start)
            num_fmt = OxmlElement("w:numFmt")
            num_fmt.set(qn("w:val"), "bullet" if bullet else "decimal")
            lvl.append(num_fmt)
            lvl_text = OxmlElement("w:lvlText")
            markers = ("•", "–", "◦")
            lvl_text.set(qn("w:val"), markers[ilvl] if bullet else f"%{ilvl + 1}.")
            lvl.append(lvl_text)
            suff = OxmlElement("w:suff")
            suff.set(qn("w:val"), "tab")
            lvl.append(suff)
            ppr = OxmlElement("w:pPr")
            tabs = OxmlElement("w:tabs")
            tab = OxmlElement("w:tab")
            tab.set(qn("w:val"), "num")
            position = 540 + 360 * ilvl
            tab.set(qn("w:pos"), str(position))
            tabs.append(tab)
            ppr.append(tabs)
            ind = OxmlElement("w:ind")
            ind.set(qn("w:left"), str(position))
            ind.set(qn("w:hanging"), "270")
            ppr.append(ind)
            spacing = OxmlElement("w:spacing")
            spacing.set(qn("w:after"), "80")
            spacing.set(qn("w:line"), "300")
            spacing.set(qn("w:lineRule"), "auto")
            ppr.append(spacing)
            lvl.append(ppr)
            rpr = OxmlElement("w:rPr")
            fonts = OxmlElement("w:rFonts")
            fonts.set(qn("w:ascii"), "Calibri")
            fonts.set(qn("w:hAnsi"), "Calibri")
            fonts.set(qn("w:eastAsia"), "Malgun Gothic")
            rpr.append(fonts)
            lvl.append(rpr)
            abstract.append(lvl)
        numbering.append(abstract)

    existing_abs = [int(x.get(qn("w:abstractNumId"))) for x in numbering.findall(qn("w:abstractNum"))]
    existing_num = [int(x.get(qn("w:numId"))) for x in numbering.findall(qn("w:num"))]
    next_abs = max(existing_abs, default=0) + 1
    next_num = max(existing_num, default=0) + 1
    add_abstract(next_abs, bullet=True)
    add_abstract(next_abs + 1, bullet=False)
    out = []
    for offset in range(2):
        num = OxmlElement("w:num")
        num_id = next_num + offset
        num.set(qn("w:numId"), str(num_id))
        abs_id = OxmlElement("w:abstractNumId")
        abs_id.set(qn("w:val"), str(next_abs + offset))
        num.append(abs_id)
        numbering.append(num)
        out.append(num_id)
    return out[0], out[1]


def _apply_numbering(paragraph, num_id: int, level: int = 0) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    num_pr = p_pr.find(qn("w:numPr"))
    if num_pr is None:
        num_pr = OxmlElement("w:numPr")
        p_pr.append(num_pr)
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), str(min(level, 2)))
    num = OxmlElement("w:numId")
    num.set(qn("w:val"), str(num_id))
    num_pr.append(ilvl)
    num_pr.append(num)


def _new_num_instance(doc: Document, source_num_id: int) -> int:
    numbering = doc.part.numbering_part.element
    source = next(
        node for node in numbering.findall(qn("w:num"))
        if int(node.get(qn("w:numId"))) == source_num_id
    )
    abstract_id = source.find(qn("w:abstractNumId")).get(qn("w:val"))
    existing = [int(node.get(qn("w:numId"))) for node in numbering.findall(qn("w:num"))]
    new_id = max(existing, default=0) + 1
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(new_id))
    abstract = OxmlElement("w:abstractNumId")
    abstract.set(qn("w:val"), abstract_id)
    num.append(abstract)
    override = OxmlElement("w:lvlOverride")
    override.set(qn("w:ilvl"), "0")
    start = OxmlElement("w:startOverride")
    start.set(qn("w:val"), "1")
    override.append(start)
    num.append(override)
    numbering.append(num)
    return new_id


INLINE_RE = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))")


def _add_inline(paragraph, text: str, *, base_size: float = 11, color: str = INK) -> None:
    pos = 0
    for match in INLINE_RE.finditer(text):
        if match.start() > pos:
            run = paragraph.add_run(text[pos:match.start()])
            _set_run_font(run, size=base_size, color=color)
        token = match.group(0)
        if token.startswith("**"):
            run = paragraph.add_run(token[2:-2])
            _set_run_font(run, size=base_size, bold=True, color=color)
        elif token.startswith("`"):
            run = paragraph.add_run(token[1:-1])
            _set_run_font(run, size=max(9, base_size - 0.5), color=DARK_BLUE, mono=True)
            rpr = run._element.get_or_add_rPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:fill"), LIGHT_GRAY)
            rpr.append(shd)
        else:
            label = token[1:token.index("]")]
            run = paragraph.add_run(label)
            _set_run_font(run, size=base_size, color=BLUE)
            run.underline = True
        pos = match.end()
    if pos < len(text):
        run = paragraph.add_run(text[pos:])
        _set_run_font(run, size=base_size, color=color)


def _set_style_font(style, name="Calibri", east_asia="Malgun Gothic", size=11,
                    color=INK, bold=None) -> None:
    style.font.name = name
    style.font.size = Pt(size)
    style.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        style.font.bold = bold
    rpr = style.element.get_or_add_rPr()
    fonts = rpr.rFonts
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    fonts.set(qn("w:ascii"), name)
    fonts.set(qn("w:hAnsi"), name)
    fonts.set(qn("w:eastAsia"), east_asia)


def _configure_styles(doc: Document) -> None:
    normal = doc.styles["Normal"]
    _set_style_font(normal, size=11, color=INK)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25

    tokens = {
        "Heading 1": (16, BLUE, 18, 10),
        "Heading 2": (13, BLUE, 14, 7),
        "Heading 3": (12, DARK_BLUE, 10, 5),
        "Heading 4": (11, NAVY, 8, 4),
    }
    for name, (size, color, before, after) in tokens.items():
        style = doc.styles[name]
        _set_style_font(style, size=size, color=color, bold=True)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.keep_together = True

    for style_name in ("Report Kicker", "Report Subtitle", "Report Meta", "Code Block", "Table Text", "Figure Caption"):
        if style_name not in doc.styles:
            doc.styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)
    _set_style_font(doc.styles["Report Kicker"], size=10, color=GOLD, bold=True)
    _set_style_font(doc.styles["Report Subtitle"], size=15, color=DARK_BLUE)
    _set_style_font(doc.styles["Report Meta"], size=10, color=MUTED)
    _set_style_font(doc.styles["Code Block"], name="Consolas", size=9.2, color=NAVY)
    _set_style_font(doc.styles["Table Text"], size=9.3, color=INK)
    _set_style_font(doc.styles["Figure Caption"], size=9.2, color=MUTED)
    code = doc.styles["Code Block"]
    code.paragraph_format.space_before = Pt(2)
    code.paragraph_format.space_after = Pt(2)
    code.paragraph_format.line_spacing = 1.10
    table_text = doc.styles["Table Text"]
    table_text.paragraph_format.space_before = Pt(0)
    table_text.paragraph_format.space_after = Pt(0)
    table_text.paragraph_format.line_spacing = 1.12
    caption = doc.styles["Figure Caption"]
    caption.paragraph_format.space_before = Pt(4)
    caption.paragraph_format.space_after = Pt(10)
    caption.paragraph_format.keep_with_next = False
    caption.paragraph_format.keep_together = True


def _configure_section(section, *, first: bool = False) -> None:
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.right_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)
    section.different_first_page_header_footer = first


def _add_header_footer(section) -> None:
    header = section.header
    p = header.paragraphs[0]
    p.text = ""
    p.paragraph_format.space_after = Pt(3)
    run = p.add_run("법률도메인 RAG 구조화·실험 종합보고서")
    _set_run_font(run, size=8.5, color=MUTED)
    _paragraph_border(p, bottom="single", color="D5DCE5", size=4, space=3)
    footer = section.footer
    fp = footer.paragraphs[0]
    fp.text = ""
    fp.paragraph_format.space_before = Pt(3)
    _add_page_field(fp)


def _add_cover(doc: Document) -> None:
    p = doc.add_paragraph(style="Report Kicker")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(92)
    p.paragraph_format.space_after = Pt(18)
    p.add_run("LEGAL DOMAIN RAG · TECHNICAL REPORT")

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(10)
    title.paragraph_format.keep_with_next = True
    run = title.add_run("법률도메인 RAG\n구조화·실험 종합보고서")
    _set_run_font(run, size=28, bold=True, color=NAVY)

    sub = doc.add_paragraph(style="Report Subtitle")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_after = Pt(28)
    sub.add_run("데이터·질문 스키마에서 명제별 법률 컴파일러와 ADR 성능 원장까지")

    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(2)
    rule.paragraph_format.space_after = Pt(26)
    _paragraph_border(rule, bottom="single", color=BLUE, size=12, space=1)

    summary = doc.add_paragraph()
    summary.alignment = WD_ALIGN_PARAGRAPH.CENTER
    summary.paragraph_format.space_after = Pt(76)
    r = summary.add_run(
        "법체계 진입 · 조문 회수 · 관계 확장 · 근거 결속 · 적용 가능성 심사 · 답변"
    )
    _set_run_font(r, size=11, color=DARK_BLUE, bold=True)

    meta = doc.add_paragraph(style="Report Meta")
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.paragraph_format.space_after = Pt(3)
    meta.add_run("기준일  2026-08-31")
    meta2 = doc.add_paragraph(style="Report Meta")
    meta2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta2.add_run("실험 범위  저장소 현존 ADR-0038 ~ ADR-0124")

    doc.add_page_break()


def _add_lead_callout(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.18)
    p.paragraph_format.right_indent = Inches(0.08)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(10)
    p.paragraph_format.line_spacing = 1.25
    _paragraph_shading(p, CALLOUT)
    _paragraph_border(p, left="single", color=BLUE, size=18, space=8)
    run = p.add_run(text)
    _set_run_font(run, size=11, bold=True, color=NAVY)


def _table_widths(rows: list[list[str]]) -> list[int]:
    cols = len(rows[0])
    weights = []
    for idx in range(cols):
        max_len = max(len(re.sub(r"[`*]", "", row[idx])) for row in rows)
        weights.append(max(8, min(max_len, 44)))
    if cols == 2:
        weights[0] = min(weights[0], 22)
    total_weight = sum(weights)
    widths = [max(900, round(CONTENT_WIDTH_DXA * w / total_weight)) for w in weights]
    diff = CONTENT_WIDTH_DXA - sum(widths)
    widths[-1] += diff
    if widths[-1] < 900:
        shortage = 900 - widths[-1]
        donor = max(range(cols - 1), key=lambda i: widths[i])
        widths[donor] -= shortage
        widths[-1] = 900
    return widths


def _add_table(doc: Document, rows: list[list[str]], *,
               widths: list[int] | None = None, font_size: float = 9.3) -> None:
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    _set_table_geometry(table, widths or _table_widths(rows))
    _repeat_table_header(table.rows[0])
    for ridx, row in enumerate(rows):
        _prevent_row_split(table.rows[ridx])
        for cidx, value in enumerate(row):
            cell = table.cell(ridx, cidx)
            p = cell.paragraphs[0]
            p.style = doc.styles["Table Text"]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            if ridx == 0:
                _set_cell_shading(cell, LIGHT_BLUE)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_inline(p, value, base_size=font_size,
                        color=NAVY if ridx == 0 else INK)
            for run in p.runs:
                if ridx == 0:
                    run.bold = True
    tail = doc.add_paragraph()
    tail.paragraph_format.space_before = Pt(0)
    tail.paragraph_format.space_after = Pt(2)
    tail.paragraph_format.keep_with_next = True


def _add_code_block(doc: Document, lines: list[str]) -> None:
    p = doc.add_paragraph(style="Code Block")
    p.paragraph_format.left_indent = Inches(0.12)
    p.paragraph_format.right_indent = Inches(0.08)
    _paragraph_shading(p, LIGHT_GRAY)
    _paragraph_border(p, left="single", color="A9B7C6", size=10, space=6)
    for idx, line in enumerate(lines):
        run = p.add_run(line)
        _set_run_font(run, size=9.2, color=NAVY, mono=True)
        if idx < len(lines) - 1:
            run.add_break()


def _add_figure(doc: Document, path: Path, caption: str, alt_text: str) -> None:
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(6)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.keep_together = True
    run = paragraph.add_run()
    shape = run.add_picture(str(path), width=Inches(6.35))
    shape._inline.docPr.set("descr", alt_text)
    shape._inline.docPr.set("title", caption)

    cap = doc.add_paragraph(style="Figure Caption")
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap_run = cap.add_run(caption)
    _set_run_font(cap_run, size=9.2, italic=True, color=MUTED)


def _parse_table(lines: list[str], start: int) -> tuple[list[list[str]], int]:
    rows: list[list[str]] = []
    idx = start
    while idx < len(lines) and lines[idx].strip().startswith("|"):
        cells = [cell.strip() for cell in lines[idx].strip().strip("|").split("|")]
        rows.append(cells)
        idx += 1
    if len(rows) >= 2 and all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in rows[1]):
        rows.pop(1)
    return rows, idx


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if match is None:
        return {}
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def _clean_markdown(value: str) -> str:
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    value = value.replace("**", "").replace("`", "")
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value).strip(" |-:")
    return value


def _section_body(text: str, names: tuple[str, ...]) -> str:
    headings = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", text))
    for index, heading in enumerate(headings):
        label = heading.group(1)
        if not any(name in label for name in names):
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        return text[heading.end():end].strip()
    return ""


def _markdown_tables(text: str) -> list[list[list[str]]]:
    lines = text.splitlines()
    tables: list[list[list[str]]] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip().startswith("|"):
            index += 1
            continue
        rows, next_index = _parse_table(lines, index)
        if rows:
            tables.append(rows)
        index = next_index
    return tables


ANSWER_ACCURACY_ADRS = {
    "ADR-0040", "ADR-0041", "ADR-0042", "ADR-0048", "ADR-0049",
    "ADR-0051", "ADR-0052", "ADR-0053", "ADR-0055", "ADR-0056",
    "ADR-0057", "ADR-0058", "ADR-0059", "ADR-0060", "ADR-0100",
    "ADR-0114", "ADR-0115", "ADR-0116", "ADR-0117", "ADR-0118",
    "ADR-0120", "ADR-0121",
}


def _answer_accuracy(text: str, adr_id: str, directory_name: str) -> str:
    # The repository ADR template also calls retrieval hits and unit-test passes
    # "correct/total".  Only ADRs whose frozen primary outcome actually grades a
    # generated legal answer belong in this column; retrieval and contract scores
    # stay in the representative-performance column.
    if (adr_id not in ANSWER_ACCURACY_ADRS
            or directory_name == "ADR-0052-legal-checklist-verifier"):
        return "미측정"
    if adr_id == "ADR-0042":
        return "대조군 2/5 (40%); strict 1/5 (20%); guarded 2/5 (40%)"

    # Prefer an explicit result table.  This preserves per-arm figures and
    # avoids confusing article recall with final-answer correctness.
    for rows in _markdown_tables(_section_body(text, ("결과",)) or text):
        header = rows[0]
        answer_idx = next((i for i, value in enumerate(header)
                           if "정답" in value and "조문" not in value), None)
        accuracy_idx = next((i for i, value in enumerate(header)
                             if "정확도" in value), None)
        if answer_idx is None or len(rows) < 2:
            continue
        arm_idx = next(
            (i for i, value in enumerate(header)
             if re.search(r"\barm\b|model", value, re.I)),
            0,
        )
        parsed: list[tuple[str, str, str, float]] = []
        for row in rows[1:]:
            if answer_idx >= len(row):
                continue
            answer = _clean_markdown(row[answer_idx])
            if not re.search(r"\d+\s*/\s*\d+", answer):
                denominator = re.search(r"정답\s*/\s*(\d+)", header[answer_idx])
                if denominator and re.fullmatch(r"\d+", answer):
                    answer = f"{answer}/{denominator.group(1)}"
                else:
                    continue
            arm = _clean_markdown(row[arm_idx]) or "arm"
            accuracy = (
                _clean_markdown(row[accuracy_idx])
                if accuracy_idx is not None and accuracy_idx < len(row) else ""
            )
            numerator, denominator = map(int, re.findall(r"\d+", answer)[:2])
            parsed.append((arm, answer, accuracy, numerator / denominator))
        if parsed:
            baseline = next(
                (item for item in parsed
                 if re.search(r"baseline|qwen|gold-only|full-context", item[0], re.I)),
                parsed[0],
            )
            chosen = [baseline, max(parsed, key=lambda item: item[3]),
                      min(parsed, key=lambda item: item[3])]
            unique: list[tuple[str, str, str, float]] = []
            for item in chosen:
                if item not in unique:
                    unique.append(item)
            return "; ".join(
                f"{arm}: {answer}" + (f" ({accuracy})" if accuracy else "")
                for arm, answer, accuracy, _ in unique
            )

    result = _section_body(text, ("결과", "결정 요약", "결정", "결론")) or text
    candidates: list[str] = []
    for paragraph in re.split(r"\n\s*\n", result):
        cleaned = _clean_markdown(" ".join(paragraph.splitlines()))
        if not cleaned:
            continue
        if re.search(r"정답\s*(조문|조항|좌표|인스턴스|근거)", cleaned):
            continue
        if not re.search(r"\d+\s*/\s*\d+", cleaned):
            continue
        if not re.search(r"정답|정확도|의미|최종\s*추론|답변", cleaned):
            continue
        candidates.append(cleaned[:180])
        if len(candidates) >= 2:
            break
    return "; ".join(candidates) if candidates else "미측정"


def _evaluation_type(text: str, answer_accuracy: str) -> str:
    if answer_accuracy != "미측정":
        return "답변 정확도"
    result = (_section_body(text, ("결과", "결정 요약", "결론")) or text).lower()
    if any(token in result for token in ("recall", "회수", "적중")):
        return "조문 회수"
    if any(token in result for token in ("validator", "테스트", "통과", "계약")):
        return "구조·계약"
    if "감사" in result or "audit" in result:
        return "데이터 감사"
    return "정성·구조"


def _representative_result(text: str) -> str:
    body = _section_body(text, ("결과", "결정 요약", "결정", "결론"))
    if not body:
        body = re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, flags=re.S)
    paragraphs = re.split(r"\n\s*\n", body)
    for paragraph in paragraphs:
        lines = [line for line in paragraph.splitlines()
                 if not line.strip().startswith(("|", "```", "#"))]
        cleaned = _clean_markdown(" ".join(lines))
        if not cleaned or len(cleaned) < 20:
            continue
        return cleaned[:300] + ("…" if len(cleaned) > 300 else "")
    return "README에 별도 정량 결과 없음"


def _infer_status(meta: dict[str, str], text: str) -> str:
    status = meta.get("status", "").strip()
    if status:
        return status
    legacy = re.search(
        r"(?im)^\s*[-*]?\s*(?:상태|status)\s*:\s*\**"
        r"(Accepted|Rejected|Proposed|In Progress|Superseded|Deprecated|Draft)",
        text,
    )
    if legacy:
        return legacy.group(1)
    summary = (_section_body(text, ("결정", "결론")) or text[:2500]).lower()
    if "rejected" in summary or "기각" in summary:
        return "Rejected"
    if "accepted" in summary or "채택" in summary:
        return "Accepted"
    return "Legacy"


def _adr_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for directory in sorted(
        (path for path in ADR_ROOT.iterdir()
         if path.is_dir() and re.match(r"ADR-\d{4}", path.name)),
        key=lambda path: path.name,
    ):
        readme = directory / "README.md"
        if not readme.exists():
            continue
        text = readme.read_text(encoding="utf-8")
        meta = _frontmatter(text)
        adr_id = meta.get("adr_id") or directory.name[:8]
        title = meta.get("title")
        if not title:
            title_match = re.search(r"(?m)^#\s+ADR-\d+:\s*(.+)$", text)
            title = title_match.group(1).strip() if title_match else directory.name[9:]
        accuracy = _answer_accuracy(text, adr_id, directory.name)
        rows.append({
            "adr": adr_id,
            "title": _clean_markdown(title),
            "status": _infer_status(meta, text),
            "evaluation": _evaluation_type(text, accuracy),
            "accuracy": accuracy,
            "result": _representative_result(text),
        })
    return rows


def _add_adr_ledger(doc: Document) -> None:
    rows = _adr_rows()
    measured = sum(row["accuracy"] != "미측정" for row in rows)
    _add_lead_callout(
        doc,
        f"현존 ADR 디렉터리 {len(rows)}개를 수록했다. 최종 답변 정답률을 직접 측정한 ADR은 "
        f"{measured}개이며, 나머지는 조문 회수·구조·정책·데이터 감사를 측정했다.",
    )
    groups = ((38, 60), (61, 81), (82, 96), (97, 106), (107, 114), (115, 124))
    for lower, upper in groups:
        selected = [row for row in rows if lower <= int(row["adr"].split("-")[1]) <= upper]
        if not selected:
            continue
        heading = doc.add_paragraph(style="Heading 2")
        _add_inline(heading, f"C.{lower:04d}-{upper:04d}", base_size=13, color=BLUE)
        table_rows = [["ADR·실험", "결정·평가", "답변 정답률", "대표 성능·해석"]]
        for row in selected:
            table_rows.append([
                f"{row['adr']} — {row['title']}",
                f"{row['status']}\n{row['evaluation']}",
                row["accuracy"],
                row["result"],
            ])
        _add_table(
            doc, table_rows,
            widths=[2700, 1500, 1800, 3360],
            font_size=8.4,
        )


def _add_body(doc: Document, source: str, bullet_num_id: int, decimal_num_id: int) -> None:
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## 1."))
    lines = lines[start:]
    idx = 0
    code_lines: list[str] | None = None
    active_list_kind: str | None = None
    active_decimal_num_id = decimal_num_id
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        if code_lines is not None:
            if stripped.startswith("```"):
                _add_code_block(doc, code_lines)
                code_lines = None
            else:
                code_lines.append(line)
            idx += 1
            continue
        if stripped.startswith("```"):
            code_lines = []
            idx += 1
            continue
        if not stripped:
            active_list_kind = None
            idx += 1
            continue
        if stripped == "{{ADR_PERFORMANCE_LEDGER}}":
            active_list_kind = None
            _add_adr_ledger(doc)
            idx += 1
            continue
        if stripped in FIGURES:
            active_list_kind = None
            path, caption, alt_text = FIGURES[stripped]
            _add_figure(doc, path, caption, alt_text)
            idx += 1
            continue
        if stripped.startswith("|"):
            active_list_kind = None
            rows, idx = _parse_table(lines, idx)
            if rows:
                _add_table(doc, rows)
            continue
        heading = re.match(r"^(#{2,4})\s+(.*)$", stripped)
        if heading:
            active_list_kind = None
            level = len(heading.group(1)) - 1
            title = heading.group(2)
            p = doc.add_paragraph(style=f"Heading {level}")
            if title.startswith(("10. 고정 설정표", "부록 A.", "부록 B.", "부록 C.")):
                p.paragraph_format.page_break_before = True
            _add_inline(p, title, base_size={1: 16, 2: 13, 3: 12}[level],
                        color={1: BLUE, 2: BLUE, 3: DARK_BLUE}[level])
            if level == 1:
                _paragraph_border(p, bottom="single", color="D5DCE5", size=4, space=5)
            idx += 1
            continue
        if stripped.startswith("> "):
            active_list_kind = None
            _add_lead_callout(doc, stripped[2:])
            idx += 1
            continue
        bullet = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        numbered = re.match(r"^(\s*)\d+[.)]\s+(.*)$", line)
        if bullet or numbered:
            match = bullet or numbered
            level = min(len(match.group(1).replace("\t", "    ")) // 2, 2)
            kind = "bullet" if bullet else "numbered"
            if kind != active_list_kind and numbered:
                active_decimal_num_id = _new_num_instance(doc, decimal_num_id)
            active_list_kind = kind
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(8 if numbered else 4)
            p.paragraph_format.line_spacing = 1.25
            p.paragraph_format.keep_together = True
            _apply_numbering(p, bullet_num_id if bullet else active_decimal_num_id, level)
            _add_inline(p, match.group(2))
            idx += 1
            continue

        active_list_kind = None
        para_lines = [stripped]
        idx += 1
        while idx < len(lines):
            nxt = lines[idx].strip()
            if (not nxt or nxt.startswith(("#", "```", "|", "> "))
                    or re.match(r"^(\s*)[-*]\s+", lines[idx])
                    or re.match(r"^(\s*)\d+[.)]\s+", lines[idx])):
                break
            para_lines.append(nxt)
            idx += 1
        text = " ".join(para_lines)
        p = doc.add_paragraph()
        p.paragraph_format.widow_control = True
        _add_inline(p, text)
    if code_lines is not None:
        _add_code_block(doc, code_lines)


def _structural_audit(doc: Document) -> None:
    section = doc.sections[0]
    assert round(section.page_width.inches, 2) == 8.5
    assert round(section.page_height.inches, 2) == 11.0
    assert all(round(value.inches, 2) == 1.0 for value in (
        section.top_margin, section.right_margin, section.bottom_margin, section.left_margin
    ))
    assert len(doc.paragraphs) > 300
    assert len(doc.tables) >= 12
    assert len(doc.inline_shapes) == len(FIGURES)
    for table in doc.tables:
        grid = table._tbl.tblGrid.findall(qn("w:gridCol"))
        assert sum(int(col.get(qn("w:w"))) for col in grid) == CONTENT_WIDTH_DXA
        assert table._tbl.tblPr.find(qn("w:tblInd")).get(qn("w:w")) == str(TABLE_INDENT_DXA)


def build() -> None:
    generate_all()
    source = SOURCE.read_text(encoding="utf-8")
    doc = Document()
    _configure_styles(doc)
    _configure_section(doc.sections[0], first=True)
    _add_header_footer(doc.sections[0])
    bullet_num_id, decimal_num_id = _ensure_numbering(doc)
    _add_cover(doc)
    _add_body(doc, source, bullet_num_id, decimal_num_id)
    _structural_audit(doc)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.core_properties.title = "법률도메인 RAG 구조화·실험 종합보고서"
    doc.core_properties.subject = "대한민국 법령·금융규제 RAG 실험 및 구조 종합보고서"
    doc.core_properties.author = "8-AGENT"
    doc.core_properties.keywords = (
        "법률 RAG, Legal Graph, LegalClosure, 데이터 스키마, 질문 스키마, "
        "법률 컴파일러, ADR 성능 원장"
    )
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build()
