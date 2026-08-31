from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_ALIGN_VERTICAL, WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "대한민국_법령_금융규제_RAG_심화학습서_2026-08-28.docx"

# compact_reference_guide + named override: A4 Korean print
FONT = "Malgun Gothic"
INK = "17233A"
BLUE = "2E5E8C"
DARK_BLUE = "1F4D78"
LIGHT_BLUE = "E8EEF5"
PALE_BLUE = "F3F7FB"
LIGHT_GRAY = "F2F4F7"
MID_GRAY = "687386"
GOLD = "8A6A10"
PALE_GOLD = "FFF8E1"
RED = "9B1C1C"
PALE_RED = "FDECEC"
GREEN = "2E6B4F"
PALE_GREEN = "EAF5EF"
WHITE = "FFFFFF"
TABLE_WIDTH = 9638  # 170 mm usable width in DXA
TABLE_INDENT = 120
CELL_TOP = 90
CELL_BOTTOM = 90
CELL_SIDE = 120


def set_run_font(run, size: float = 10.5, bold=None, italic=None, color: str = INK):
    run.font.name = FONT
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), FONT)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), FONT)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT)
    run._element.get_or_add_rPr().rFonts.set(qn("w:cs"), FONT)
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_para_format(p, before=0, after=6, line=1.25, align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    pf.widow_control = True


def add_rich_text(p, text: str, size: float = 10.5, color: str = INK):
    parts = text.split("**")
    for i, part in enumerate(parts):
        if not part:
            continue
        r = p.add_run(part)
        set_run_font(r, size=size, bold=(i % 2 == 1), color=color)


def add_body(doc: Document, text: str, *, after=6, line=1.25, align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    p = doc.add_paragraph()
    set_para_format(p, after=after, line=line, align=align)
    add_rich_text(p, text)
    return p


def add_label_para(doc: Document, label: str, text: str, color: str = INK):
    p = doc.add_paragraph()
    set_para_format(p, after=5, line=1.22)
    r = p.add_run(label + "  ")
    set_run_font(r, size=10.5, bold=True, color=BLUE)
    add_rich_text(p, text, size=10.5, color=color)
    return p


def set_repeat_table_header(row):
    trPr = row._tr.get_or_add_trPr()
    tblHeader = OxmlElement("w:tblHeader")
    tblHeader.set(qn("w:val"), "true")
    trPr.append(tblHeader)


def prevent_row_split(row):
    trPr = row._tr.get_or_add_trPr()
    cantSplit = OxmlElement("w:cantSplit")
    trPr.append(cantSplit)


def set_cell_shading(cell, fill: str):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcPr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=CELL_TOP, start=CELL_SIDE, bottom=CELL_BOTTOM, end=CELL_SIDE):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcMar = tcPr.first_child_found_in("w:tcMar")
    if tcMar is None:
        tcMar = OxmlElement("w:tcMar")
        tcPr.append(tcMar)
    for m, v in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tcMar.find(qn(f"w:{m}"))
        if node is None:
            node = OxmlElement(f"w:{m}")
            tcMar.append(node)
        node.set(qn("w:w"), str(v))
        node.set(qn("w:type"), "dxa")


def set_cell_width(cell, width: int):
    tcPr = cell._tc.get_or_add_tcPr()
    tcW = tcPr.find(qn("w:tcW"))
    if tcW is None:
        tcW = OxmlElement("w:tcW")
        tcPr.append(tcW)
    tcW.set(qn("w:w"), str(width))
    tcW.set(qn("w:type"), "dxa")


def set_table_geometry(table, widths: Sequence[int]):
    if sum(widths) != TABLE_WIDTH:
        raise ValueError(f"table widths must sum to {TABLE_WIDTH}: {widths}")
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl = table._tbl
    tblPr = tbl.tblPr
    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)
    tblW.set(qn("w:w"), str(TABLE_WIDTH))
    tblW.set(qn("w:type"), "dxa")
    tblInd = tblPr.find(qn("w:tblInd"))
    if tblInd is None:
        tblInd = OxmlElement("w:tblInd")
        tblPr.append(tblInd)
    tblInd.set(qn("w:w"), str(TABLE_INDENT))
    tblInd.set(qn("w:type"), "dxa")
    layout = tblPr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tblPr.append(layout)
    layout.set(qn("w:type"), "fixed")
    grid = tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    for row in table.rows:
        prevent_row_split(row)
        for idx, cell in enumerate(row.cells):
            set_cell_width(cell, widths[min(idx, len(widths) - 1)])
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def set_table_borders(table, color="AAB4C0", size="4"):
    tblPr = table._tbl.tblPr
    borders = tblPr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tblPr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = borders.find(qn(f"w:{edge}"))
        if e is None:
            e = OxmlElement(f"w:{edge}")
            borders.append(e)
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), size)
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), color)


def fill_cell_text(cell, text: str, *, bold=False, color=INK, size=9.2, align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.text = ""
    p = cell.paragraphs[0]
    set_para_format(p, after=0, line=1.15, align=align)
    for i, segment in enumerate(text.split("**")):
        if not segment:
            continue
        r = p.add_run(segment)
        set_run_font(r, size=size, bold=(bold or i % 2 == 1), color=color)


def add_table(doc: Document, headers: Sequence[str], rows: Sequence[Sequence[str]], widths: Sequence[int], *, font_size=9.2):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    set_table_geometry(table, widths)
    set_table_borders(table)
    hdr = table.rows[0]
    set_repeat_table_header(hdr)
    for i, h in enumerate(headers):
        set_cell_shading(hdr.cells[i], LIGHT_BLUE)
        fill_cell_text(hdr.cells[i], h, bold=True, color=DARK_BLUE, size=font_size, align=WD_ALIGN_PARAGRAPH.CENTER)
    for row_data in rows:
        row = table.add_row()
        prevent_row_split(row)
        for i, value in enumerate(row_data):
            set_cell_width(row.cells[i], widths[i])
            set_cell_margins(row.cells[i])
            fill_cell_text(row.cells[i], str(value), size=font_size)
    p = doc.add_paragraph()
    set_para_format(p, after=4, line=1.0)
    return table


def add_callout(doc: Document, title: str, text: str, *, kind="info"):
    palette = {
        "info": (PALE_BLUE, BLUE),
        "warning": (PALE_GOLD, GOLD),
        "risk": (PALE_RED, RED),
        "success": (PALE_GREEN, GREEN),
    }
    fill, color = palette[kind]
    table = doc.add_table(rows=1, cols=1)
    set_table_geometry(table, [TABLE_WIDTH])
    set_table_borders(table, color=color, size="6")
    cell = table.cell(0, 0)
    set_cell_shading(cell, fill)
    set_cell_margins(cell, top=130, bottom=130, start=170, end=170)
    p = cell.paragraphs[0]
    set_para_format(p, after=2, line=1.18, align=WD_ALIGN_PARAGRAPH.LEFT)
    r = p.add_run(title)
    set_run_font(r, size=10.4, bold=True, color=color)
    p2 = cell.add_paragraph()
    set_para_format(p2, after=0, line=1.22, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    add_rich_text(p2, text, size=10.0, color=INK)
    spacer = doc.add_paragraph()
    set_para_format(spacer, after=3, line=1.0)
    return table


def add_process(doc: Document, lines: Sequence[str], *, title="법적 탐색 경로"):
    table = doc.add_table(rows=1, cols=1)
    set_table_geometry(table, [TABLE_WIDTH])
    set_table_borders(table, color="B7C6D8", size="4")
    cell = table.cell(0, 0)
    set_cell_shading(cell, "F7FAFD")
    set_cell_margins(cell, top=130, bottom=130, start=220, end=180)
    p = cell.paragraphs[0]
    set_para_format(p, after=6, line=1.0, align=WD_ALIGN_PARAGRAPH.LEFT)
    r = p.add_run(title)
    set_run_font(r, size=9.4, bold=True, color=BLUE)
    for idx, line in enumerate(lines):
        q = cell.add_paragraph()
        set_para_format(q, after=2, line=1.12, align=WD_ALIGN_PARAGRAPH.LEFT)
        marker = "→" if idx else "●"
        rr = q.add_run(f"{marker}  {line}")
        set_run_font(rr, size=9.5, color=INK)
        q.paragraph_format.left_indent = Cm(0.2 if idx == 0 else 0.55)
    spacer = doc.add_paragraph()
    set_para_format(spacer, after=4, line=1.0)
    return table


def add_bullet(doc: Document, text: str, level=0):
    p = doc.add_paragraph(style="Guide Bullet")
    p.paragraph_format.left_indent = Cm(0.95 + level * 0.55)
    p.paragraph_format.first_line_indent = Cm(-0.48)
    set_para_format(p, after=4, line=1.25, align=WD_ALIGN_PARAGRAPH.LEFT)
    p.style = doc.styles["Guide Bullet"]
    add_rich_text(p, text)
    return p


def add_number(doc: Document, text: str):
    p = doc.add_paragraph(style="Guide Number")
    p.paragraph_format.left_indent = Cm(0.95)
    p.paragraph_format.first_line_indent = Cm(-0.48)
    set_para_format(p, after=4, line=1.25, align=WD_ALIGN_PARAGRAPH.LEFT)
    p.style = doc.styles["Guide Number"]
    add_rich_text(p, text)
    return p


def add_heading(doc: Document, text: str, level=1, *, page_break=False):
    p = doc.add_paragraph(text, style=f"Heading {level}")
    if page_break:
        p.paragraph_format.page_break_before = True
    return p


def add_part(doc: Document, number: str, title: str, subtitle: str):
    p = doc.add_paragraph()
    p.paragraph_format.page_break_before = True
    p.paragraph_format.space_before = Pt(44)
    p.paragraph_format.space_after = Pt(8)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run(f"PART {number}")
    set_run_font(r, size=12, bold=True, color=GOLD)
    p2 = doc.add_paragraph()
    set_para_format(p2, after=10, line=1.0, align=WD_ALIGN_PARAGRAPH.LEFT)
    r2 = p2.add_run(title)
    set_run_font(r2, size=24, bold=True, color=DARK_BLUE)
    p3 = doc.add_paragraph()
    set_para_format(p3, after=24, line=1.25, align=WD_ALIGN_PARAGRAPH.LEFT)
    r3 = p3.add_run(subtitle)
    set_run_font(r3, size=11.5, color=MID_GRAY)


def add_source_note(doc: Document, text: str):
    p = doc.add_paragraph()
    set_para_format(p, before=2, after=6, line=1.15, align=WD_ALIGN_PARAGRAPH.LEFT)
    r = p.add_run("근거·주의  ")
    set_run_font(r, size=8.5, bold=True, color=MID_GRAY)
    rr = p.add_run(text)
    set_run_font(rr, size=8.5, color=MID_GRAY)


def add_case_card(doc: Document, case: dict):
    add_heading(doc, f"{case['id']}  {case['title']}", level=2)
    add_label_para(doc, "실제 질문", case["question"])
    add_label_para(doc, "필수 근거", case["gold"])
    add_label_para(doc, "기존 V2", case["baseline"])
    add_label_para(doc, "피드백 루프", case["feedback"])
    add_label_para(doc, "법률가식 쟁점", case["legal"])
    add_process(doc, case["path"], title="정답 조항으로 가는 최소 경로")
    add_callout(doc, "개선 포인트", case["fix"], kind=case.get("kind", "info"))


def add_success_case(doc: Document, title: str, question: str, provisions: str, route: Sequence[str], why: str):
    add_heading(doc, title, level=2)
    add_label_para(doc, "질문", question)
    add_label_para(doc, "정답 조항", provisions)
    add_process(doc, route)
    add_label_para(doc, "작동한 이유", why)


def configure_styles(doc: Document):
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = FONT
    normal._element.rPr.rFonts.set(qn("w:ascii"), FONT)
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), FONT)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string(INK)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25
    for name, size, color, before, after in (
        ("Heading 1", 17, BLUE, 18, 10),
        ("Heading 2", 14, BLUE, 14, 7),
        ("Heading 3", 11.5, DARK_BLUE, 10, 5),
    ):
        st = styles[name]
        st.font.name = FONT
        st._element.rPr.rFonts.set(qn("w:ascii"), FONT)
        st._element.rPr.rFonts.set(qn("w:hAnsi"), FONT)
        st._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = RGBColor.from_string(color)
        st.paragraph_format.space_before = Pt(before)
        st.paragraph_format.space_after = Pt(after)
        st.paragraph_format.keep_with_next = True
        st.paragraph_format.widow_control = True
    for style_name in ("Guide Bullet", "Guide Number"):
        st = styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)
        st.base_style = styles["Normal"]
        st.font.name = FONT
        st._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)


def add_numbering(doc: Document):
    numbering = doc.part.numbering_part.element
    existing_abs = [int(x.get(qn("w:abstractNumId"))) for x in numbering.findall(qn("w:abstractNum"))]
    existing_num = [int(x.get(qn("w:numId"))) for x in numbering.findall(qn("w:num"))]
    next_abs = max(existing_abs or [0]) + 1
    next_num = max(existing_num or [0]) + 1

    def make(abstract_id: int, num_id: int, fmt: str, text: str, style_name: str):
        abstract = OxmlElement("w:abstractNum")
        abstract.set(qn("w:abstractNumId"), str(abstract_id))
        multi = OxmlElement("w:multiLevelType")
        multi.set(qn("w:val"), "singleLevel")
        abstract.append(multi)
        lvl = OxmlElement("w:lvl")
        lvl.set(qn("w:ilvl"), "0")
        start = OxmlElement("w:start")
        start.set(qn("w:val"), "1")
        lvl.append(start)
        numFmt = OxmlElement("w:numFmt")
        numFmt.set(qn("w:val"), fmt)
        lvl.append(numFmt)
        lvlText = OxmlElement("w:lvlText")
        lvlText.set(qn("w:val"), text)
        lvl.append(lvlText)
        suff = OxmlElement("w:suff")
        suff.set(qn("w:val"), "tab")
        lvl.append(suff)
        pPr = OxmlElement("w:pPr")
        tabs = OxmlElement("w:tabs")
        tab = OxmlElement("w:tab")
        tab.set(qn("w:val"), "num")
        tab.set(qn("w:pos"), "540")
        tabs.append(tab)
        pPr.append(tabs)
        ind = OxmlElement("w:ind")
        ind.set(qn("w:left"), "540")
        ind.set(qn("w:hanging"), "270")
        pPr.append(ind)
        lvl.append(pPr)
        numbering.append(abstract)
        num = OxmlElement("w:num")
        num.set(qn("w:numId"), str(num_id))
        aid = OxmlElement("w:abstractNumId")
        aid.set(qn("w:val"), str(abstract_id))
        num.append(aid)
        numbering.append(num)
        style = doc.styles[style_name]
        pPrStyle = style._element.get_or_add_pPr()
        numPr = OxmlElement("w:numPr")
        ilvl = OxmlElement("w:ilvl")
        ilvl.set(qn("w:val"), "0")
        numId = OxmlElement("w:numId")
        numId.set(qn("w:val"), str(num_id))
        numPr.append(ilvl)
        numPr.append(numId)
        pPrStyle.append(numPr)

    make(next_abs, next_num, "bullet", "•", "Guide Bullet")
    make(next_abs + 1, next_num + 1, "decimal", "%1.", "Guide Number")


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("쪽 ")
    set_run_font(run, size=8.5, color=MID_GRAY)
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    paragraph._p.append(fld)


def configure_page(doc: Document):
    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Mm(18)
    section.bottom_margin = Mm(18)
    section.left_margin = Mm(20)
    section.right_margin = Mm(20)
    section.header_distance = Mm(10)
    section.footer_distance = Mm(10)
    section.different_first_page_header_footer = True
    header = section.header
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    hr = hp.add_run("대한민국 법령·금융규제 구조 심화학습서")
    set_run_font(hr, size=8.5, bold=True, color=MID_GRAY)
    footer = section.footer
    add_page_number(footer.paragraphs[0])


def add_cover(doc: Document):
    for _ in range(5):
        p = doc.add_paragraph()
        set_para_format(p, after=12, line=1.0)
    kicker = doc.add_paragraph()
    set_para_format(kicker, after=15, line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER)
    r = kicker.add_run("법령해석 · 금융규제 · RAG 실전")
    set_run_font(r, size=11.5, bold=True, color=GOLD)
    title = doc.add_paragraph()
    set_para_format(title, after=10, line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER)
    rr = title.add_run("대한민국 법령·금융규제 구조\n심화학습서")
    set_run_font(rr, size=28, bold=True, color=DARK_BLUE)
    sub = doc.add_paragraph()
    set_para_format(sub, after=35, line=1.35, align=WD_ALIGN_PARAGRAPH.CENTER)
    rs = sub.add_run("효력 계층, 위임·준용·특례, 외규→내규 전환,\n실제 골든 작동 사례와 잔여 오답 16건 해부")
    set_run_font(rs, size=13, color=MID_GRAY)
    meta = doc.add_paragraph()
    set_para_format(meta, after=5, line=1.2, align=WD_ALIGN_PARAGRAPH.CENTER)
    rm = meta.add_run("2026년 8월 28일 기준 · 인쇄 학습용")
    set_run_font(rm, size=10.5, bold=True, color=BLUE)
    meta2 = doc.add_paragraph()
    set_para_format(meta2, after=5, line=1.2, align=WD_ALIGN_PARAGRAPH.CENTER)
    rm2 = meta2.add_run("8-AGENT LegalClosure V2 Golden 및 ADR-0091·0094·0096 근거")
    set_run_font(rm2, size=9.5, color=MID_GRAY)
    p = doc.add_paragraph()
    p.add_run().add_break(WD_BREAK.PAGE)


def build():
    doc = Document()
    configure_styles(doc)
    add_numbering(doc)
    configure_page(doc)
    doc.core_properties.title = "대한민국 법령·금융규제 구조 심화학습서"
    doc.core_properties.subject = "법령 계층, 금융규제, 외규와 내규, RAG 골든 사례"
    doc.core_properties.author = "8-AGENT 연구용"
    doc.core_properties.keywords = "대한민국 법체계, 금융법, 위임, 준용, 내규, RAG"
    add_cover(doc)

    add_heading(doc, "이 책의 목적과 읽는 방법", level=1)
    add_body(doc, "이 자료는 대한민국 법령 구조를 단순 암기하는 데서 멈추지 않고, **하나의 법률 질문이 어떤 조문 묶음으로 완성되는지**를 추적하기 위한 학습서다. 특히 금융 분야에서는 법률 하나로 판단이 끝나는 경우가 드물다. 시행령·감독규정·시행세칙·거래소 및 협회 규정·회사 내규·서식·시스템 통제가 서로 다른 역할을 수행한다.")
    add_callout(doc, "중요한 전제", "이 문서는 교육·연구용이다. 실제 사건에는 기준일, 적용대상, 회사 형태, 인허가 단위, 경과조치, 감독당국의 최신 해석을 다시 확인해야 한다. 저장소의 ‘위험관리기준시행세칙’과 ‘투자 및 인수 위험관리지침’은 **AI Agent 검증용 예시 내규이며 실제 금융회사의 규정이 아니다.**", kind="warning")
    add_heading(doc, "학습 목표", level=2)
    for text in (
        "헌법·법률·대통령령·부령·조례·행정규칙의 효력관계를 설명할 수 있다.",
        "위임, 수임, 재위임, 준용, 적용, 인용, 특례, 의제, 경과조치를 서로 구별할 수 있다.",
        "금융법에서 법률·시행령·감독규정·시행세칙·자율규제가 어떻게 결합하는지 설명할 수 있다.",
        "외규의 의무를 내부 규정·업무절차·서식·시스템 통제로 전환하는 방법을 이해한다.",
        "실제 V2 골든 성공 사례와 오답 사례를 보고 검색 실패와 법률해석 실패를 구분할 수 있다.",
    ):
        add_bullet(doc, text)

    add_heading(doc, "전체 목차", level=2)
    toc_rows = [
        ("PART I", "대한민국 법체계의 뼈대", "효력 계층과 조문 구조"),
        ("PART II", "법령을 연결하는 문법", "위임·준용·특례·정의·부칙"),
        ("PART III", "금융규제 생태계", "법률부터 감독규정·자율규제까지"),
        ("PART IV", "외규에서 내규로", "내부 규정체계와 통제 설계"),
        ("PART V", "RAG와 실제 골든", "검색 채널·성공 사례·관계 edge"),
        ("PART VI", "잔여 오답 16건 사례집", "17개 미도달 조항의 실패 해부"),
        ("부록", "용어사전·체크리스트·출처", "인쇄 후 반복 학습용"),
    ]
    add_table(doc, ["구분", "주제", "핵심"], toc_rows, [1200, 3300, 5138], font_size=9.5)

    add_part(doc, "I", "대한민국 법체계의 뼈대", "법규범의 효력 순서와 한 법령 안의 구조를 먼저 세운다.")
    add_heading(doc, "1. 하나의 피라미드가 아니라 가지가 있는 체계", level=1)
    add_body(doc, "대한민국 법체계는 ‘헌법→법률→시행령→시행규칙’이라는 중심축을 가지지만, 지방자치법규와 헌법기관 규칙은 별도 가지를 이룬다. 조약·국제법규, 긴급명령, 자율규제, 행정규칙, 판례·행정해석도 서로 다른 방식으로 작동한다. 따라서 **효력의 높이**와 **적용을 연결하는 관계**를 분리해서 보아야 한다.")
    add_process(doc, [
        "헌법 — 국가조직과 기본권, 입법·행정·사법 권한의 최상위 규범",
        "법률 — 국회가 국민의 권리·의무와 제도의 핵심을 정함",
        "대통령령 — 법률의 위임사항과 집행사항을 구체화",
        "총리령·부령 — 소관 행정의 절차·기준·서식을 세분화",
        "위임받은 고시·감독규정 — 기술적·전문적 사항을 보충",
        "일반 행정규칙 — 원칙적으로 행정조직 내부의 업무처리 기준",
    ], title="중앙 법령의 중심축")
    hierarchy_rows = [
        ("헌법", "국민·헌법제정권력", "국가조직·기본권·권력통제", "최상위"),
        ("법률", "국회", "권리·의무와 제도 핵심", "헌법에 위반 불가"),
        ("대통령령", "대통령", "법률 위임·집행", "법률 및 위임범위에 구속"),
        ("총리령·부령", "국무총리·장관", "절차·기술·서식", "법률·대통령령에 구속"),
        ("조례", "지방의회", "자치사무·지역규율", "법령 범위 안"),
        ("지방 규칙", "지자체장", "조례 집행·지방행정", "법령·조례에 구속"),
        ("행정규칙", "행정기관", "내부 지휘·업무처리", "원칙적으로 내부효"),
        ("법령보충적 행정규칙", "행정기관", "위임받은 전문·기술 세부", "위임범위에서 외부효 가능"),
    ]
    add_table(doc, ["규범", "제정 주체", "주된 역할", "통제"], hierarchy_rows, [1450, 1600, 3500, 3088])
    add_callout(doc, "시행령·시행규칙의 정체", "‘○○법 시행령’은 보통 대통령령이고, ‘○○법 시행규칙’은 총리령 또는 부령이다. 시행령·시행규칙은 기능적 이름이며 그 자체가 별도의 법 형식인 것은 아니다.", kind="info")

    add_heading(doc, "2. 병렬 가지: 지방자치법규와 헌법기관 규칙", level=1)
    add_body(doc, "대법원규칙·헌법재판소규칙·중앙선거관리위원회규칙·국회규칙은 행정부의 대통령령 아래에 단순 배치하기 어렵다. 각각 헌법과 법률이 부여한 독립된 규칙제정권의 산물이다. 조례와 지방자치단체 규칙도 지방자치라는 별도 헌법적 가지에 속한다. 실제 충돌에서는 제정권의 근거와 규율대상, 상위 법률의 수권범위를 확인해야 한다.")
    add_process(doc, [
        "헌법",
        "국회 법률 → 대통령령·총리령·부령",
        "헌법기관 규칙 → 해당 기관의 조직·절차 규율",
        "지방자치 → 조례 → 지방자치단체 규칙",
    ], title="가지가 갈리는 구조")

    add_heading(doc, "3. 법령 내부의 문서 구조", level=1)
    add_body(doc, "한 법령은 본칙과 부칙으로 나뉘고, 본칙은 필요에 따라 편·장·절·관으로 묶인다. 실제 법적 효과는 조·항·호·목에 배치된다. 검색 시스템은 제목만이 아니라 이 구조적 관할을 보존해야 한다.")
    structure_rows = [
        ("편·장·절·관", "주제별 상위 묶음", "검색 범위와 정의 관할을 좁히는 데 사용"),
        ("조", "독립된 규율 주제", "제416조처럼 기본 인용 단위"),
        ("항", "조 안의 독립 규율", "①·②; 원칙과 별도 의무가 갈림"),
        ("호", "요건·대상·사유 열거", "1. 2. 3.; ‘각 호의 어느 하나’ 확인"),
        ("목", "호의 세분", "가. 나. 다.; 단서 적용범위 주의"),
        ("본문·단서", "원칙과 예외", "‘다만’ 앞뒤를 한 세트로 회수"),
        ("전단·후단", "한 항 안의 효과 분할", "뒤 문장이 독립 요건일 수 있음"),
        ("별표·서식", "수치표·기술기준·제출양식", "본문 위임과 결합해 효력 판단"),
        ("부칙", "시행일·적용례·경과조치", "현행본문만 보면 시간 적용을 놓침"),
    ]
    add_table(doc, ["단위", "기능", "읽을 때의 주의"], structure_rows, [1450, 3000, 5188])

    add_heading(doc, "4. 법 적용의 우선순위", level=1)
    for text in (
        "먼저 **적용대상·행위·시점**이 같은 규범인지 확인한다.",
        "상위규범이 하위규범보다 우선한다. 하위규범은 위임범위를 넘을 수 없다.",
        "같은 단계에서는 명시적 우선·배제 문언을 먼저 본다.",
        "동일 사항이 충돌할 때 특별법과 일반법 관계를 검토한다.",
        "여전히 충돌하면 신법과 구법 관계, 부칙의 적용례·경과조치를 확인한다.",
        "형벌·조세·기본권 제한은 문언과 명확성 요구를 더 엄격하게 본다.",
    ):
        add_number(doc, text)
    add_callout(doc, "특별법 우선의 한계", "특별법이 관련되어 있다는 이유만으로 일반법 전체가 사라지는 것은 아니다. 특별법이 실제로 달리 정한 범위만 우선하고, 나머지 공백에는 일반법이 계속 작동할 수 있다.", kind="warning")

    add_part(doc, "II", "법령을 연결하는 문법", "조문 사이의 관계를 잘못 분류하면 정답 법령을 알아도 필요한 조항 묶음을 완성할 수 없다.")
    add_heading(doc, "5. 위임·수임·재위임", level=1)
    add_body(doc, "입법 위임은 상위 규범이 하위 규범에 세부 기준을 만들 권한을 주는 수직 관계다. ‘대통령령으로 정한다’는 표현은 시행령을 찾으라는 강한 신호이고, 시행령의 ‘법 제○조에서 대통령령으로 정하는’이라는 표현은 수임조항의 신호다.")
    add_process(doc, [
        "법률: 규율대상과 핵심 기준 설정",
        "대통령령: 법률이 위임한 기준·요건·범위 구체화",
        "총리령·부령: 절차·서식·기술사항 세분화",
        "고시·감독규정: 전문·기술적 세부를 제한적으로 보충",
    ], title="위임의 수직 사슬")
    delegation_rows = [
        ("위임", "상위가 아래에 정할 권한 부여", "대통령령으로 정한다"),
        ("수임", "하위가 위임받아 실제 내용 규정", "법 제○조에서 정하는 기준은"),
        ("재위임", "받은 권한의 일부를 더 아래로", "총리령으로 정한다"),
        ("위임범위", "하위 규범이 정할 수 있는 경계", "대상·내용·범위의 예측 가능성"),
        ("위임일탈", "하위가 맡지 않은 사항까지 규정", "상위법 위반·무효 문제"),
        ("포괄위임", "대강 없이 전부 맡김", "조세·형벌에서 특히 엄격"),
    ]
    add_table(doc, ["용어", "의미", "대표 신호"], delegation_rows, [1550, 4050, 4038])
    add_callout(doc, "RAG 규칙", "상위 조문에서 ‘대통령령으로 정한다’를 찾았으면 단순 인접조문이 아니라 **해당 위임을 실제로 받은 시행령 조항**을 찾아야 한다. 법률과 시행령의 조번호가 같을 것이라고 가정하면 안 된다.", kind="success")

    add_heading(doc, "6. 입법 위임·권한 위임·업무 위탁·대리", level=1)
    authority_rows = [
        ("입법 위임", "하위 규범에 기준 제정권 부여", "법률→시행령"),
        ("행정권한 위임", "허가·처분 등 권한 자체를 수임기관으로 이전", "장관→시도지사"),
        ("업무 위탁", "업무 수행을 기관·법인·민간에 맡김", "감독·책임·재위탁 확인"),
        ("대리", "권한은 본인에게 남고 대리인이 본인 이름으로 행사", "대리권 범위"),
        ("내부 전결", "기관 내부 결재선 배분", "대외 권한 주체는 원래 기관"),
        ("임용", "사람을 직위·공무원 신분에 임명", "법령 간 연결관계가 아님"),
    ]
    add_table(doc, ["관계", "핵심", "확인할 것"], authority_rows, [1600, 4538, 3500])

    add_heading(doc, "7. 준용·적용·예에 따른다", level=1)
    add_body(doc, "준용은 다른 조문을 빌려와 대상의 성질에 맞게 필요한 문구를 바꾸어 적용하는 수평 관계다. 상법 제415조가 제388조를 감사에게 준용하면, 제388조의 ‘이사’를 ‘감사’에 맞게 읽는다.")
    add_process(doc, [
        "상법 제415조: 제388조를 감사에게 준용",
        "상법 제388조: 이사 보수는 정관 또는 주주총회 결의",
        "문구 치환: 이사 → 감사",
        "결론: 감사 보수도 정관 또는 주주총회가 결정",
    ], title="준용의 실제 작동")
    apply_rows = [
        ("적용한다", "규정을 그대로 사용", "수정 없음이 원칙"),
        ("준용한다", "유사 대상에 필요한 수정을 거쳐 사용", "원조문 본문까지 회수"),
        ("예에 따른다", "제도·절차의 처리방식을 포괄적으로 따름", "사정거리 확인"),
        ("따른다", "기준·절차를 해당 규정에 의존", "직접 적용인지 참조인지 문맥 판단"),
        ("준하여", "기준으로 삼아 유사 처리", "법적 근거와 효력 별도 확인"),
    ]
    add_table(doc, ["표현", "효과", "검색·해석 포인트"], apply_rows, [1650, 3800, 4188])
    add_callout(doc, "준용의 한계", "준용된 의무규정이 있다고 해서 벌칙까지 자동으로 따라오는 것은 아니다. 형벌·조세 영역에서는 죄형법정주의와 명확성 때문에 준용 확대에 특히 신중해야 한다.", kind="risk")

    add_heading(doc, "8. 인용·특례·배제·정의", level=1)
    relation_rows = [
        ("제○조에 따른", "요건·대상·절차 참조", "references"),
        ("제○조를 준용", "수정 적용", "applies_mutatis_mutandis"),
        ("제○조에도 불구하고", "일반규정에 대한 특례", "exception_to / special_to"),
        ("적용하지 아니한다", "명시적 적용 배제", "excludes"),
        ("이 법에서 ○○란", "법 전체의 용어 정의", "defined_by"),
        ("이 조에서 ○○란", "해당 조문 안의 국지적 정의", "defined_by(scope=article)"),
        ("위반한 자", "의무와 제재 연결", "sanctioned_by"),
        ("다른 법률에 특별한 규정", "다른 법의 구체적 특례만 우선", "special_law_gate"),
    ]
    add_table(doc, ["문언", "법적 기능", "관계 edge"], relation_rows, [2450, 3900, 3288])

    add_heading(doc, "9. 의제·간주·추정·갈음", level=1)
    fiction_rows = [
        ("본다·간주한다", "사실과 달라도 법률상 동일 취급", "원칙적으로 반대사실만으로 뒤집기 어려움"),
        ("추정한다", "일단 그렇게 인정", "반대증명으로 번복 가능"),
        ("갈음한다", "한 행위·문서·절차로 다른 것을 대체", "대체 범위를 넘지 않음"),
        ("면제한다", "원래 의무를 제거", "면제 요건 충족 여부"),
        ("생략할 수 있다", "절차 일부를 하지 않아도 됨", "재량인지 요건부인지 확인"),
    ]
    add_table(doc, ["표현", "효과", "핵심 주의"], fiction_rows, [1800, 3800, 4038])

    add_heading(doc, "10. 본문·단서·부칙·제재", level=1)
    add_body(doc, "본문과 단서는 원칙·예외의 한 세트다. 부칙은 시간 적용을 통제하고, 벌칙·과태료는 의무 조항에서 멀리 떨어진 법령 말미에 위치한다. 검색기는 조문 하나를 찾는 데 그치지 않고 이 원거리 관계를 따라야 한다.")
    temporal_rows = [
        ("시행일", "새 법령의 효력 발생일", "공포일과 다를 수 있음"),
        ("적용례", "어떤 계약·신청·사건부터 새 규정을 적용", "‘최초로’의 목적어 확인"),
        ("경과조치", "구법상 지위·처분·절차를 일정 범위 보호", "시점·주체·사유가 바뀌면 끊길 수 있음"),
        ("다른 법률 개정", "부칙에서 관련 법률 문언을 함께 수정", "현행본문 좌표와 구분"),
        ("벌칙·과태료", "의무 위반의 제재", "의무의 수범자와 제재 수범자 일치 확인"),
    ]
    add_table(doc, ["구조", "역할", "읽기 포인트"], temporal_rows, [1700, 4050, 3888])

    add_heading(doc, "11. 법령·판례·행정해석·비조치의견서", level=1)
    source_rows = [
        ("법령 원문", "무엇이 규정되어 있는가", "직접 규범"),
        ("대법원 판례", "법원이 문언을 어떻게 해석·적용했는가", "실무상 강한 해석 기준"),
        ("헌법재판소 결정", "헌법 합치성과 효력", "위헌결정 등은 효력에 직접 영향"),
        ("법제처 법령해석", "정부 내 법령해석 통일", "법원 판결과 동일하지 않음"),
        ("금융위·금감원 회신", "소관 금융규제의 행정 해석·집행 입장", "사실관계·기준일 한정"),
        ("비조치의견서", "특정 사실관계에 제재하지 않을 예정이라는 행정 입장", "일반적 허용 규정으로 확대 금지"),
        ("FAQ·매뉴얼", "실무 안내", "독립 법적 근거가 아닐 수 있음"),
    ]
    add_table(doc, ["자료", "역할", "법적 사용법"], source_rows, [2000, 4100, 3538])

    add_part(doc, "III", "금융규제 생태계", "금융 분야에서는 여러 규범층이 동시에 작동한다. 업권법과 공통법, 감독규정과 자율규제를 분리해 본다.")
    add_heading(doc, "12. 금융법의 다층 구조", level=1)
    add_process(doc, [
        "헌법·상법·민법 등 일반법",
        "금융 공통법: 지배구조·금융소비자·신용정보·전자금융·실명·AML·외부감사",
        "업권법: 은행·보험·자본시장·여전·저축은행·상호금융 등",
        "시행령·시행규칙",
        "금융위원회 감독규정·고시",
        "금융감독원 시행세칙·검사업무 기준",
        "거래소·협회 자율규제",
        "금융회사 정관·이사회 규정·내부통제기준·세칙·지침·매뉴얼",
        "계약서·설명서·서식·전산통제·증적",
    ], title="금융규제가 내부 업무까지 내려오는 길")
    add_heading(doc, "13. 금융 공통법과 업권법", level=1)
    common_rows = [
        ("금융회사 지배구조법", "이사회·임원·준법감시인·위험관리책임자·내부통제", "조직·역할·겸직"),
        ("금융소비자보호법", "판매원칙·설명의무·부당권유·광고·분쟁", "상품 판매 전 과정"),
        ("신용정보법", "개인신용정보·신용정보업·제공·이용", "정보의 종류·주체·허가"),
        ("전자금융거래법", "전자금융업무·안전성·접근매체", "IT·보안·전자거래"),
        ("금융실명법", "실명거래와 비밀보장", "계좌·거래정보 제공"),
        ("특정금융정보법", "고객확인·의심거래보고·AML", "자금세탁방지"),
        ("외부감사법", "감사·내부회계관리제도", "재무보고 통제"),
        ("개인채무자보호법", "채권추심·채무조정·개인채무자 보호", "업무 자체와 담당자 적격을 구분"),
    ]
    add_table(doc, ["공통법", "중심 규율", "자주 묻는 축"], common_rows, [2200, 4300, 3138])
    sector_rows = [
        ("은행", "은행법·은행업감독규정", "인가·건전성·업무범위·신용공여"),
        ("금융투자", "자본시장법·금융투자업규정", "업의 정의·인가·영업행위·공시·시장"),
        ("보험", "보험업법·보험업감독규정", "상품·모집·자산운용·건전성"),
        ("여신전문금융", "여신전문금융업법·감독규정", "카드·리스·할부·신기술금융"),
        ("저축은행", "상호저축은행법·감독규정", "업무범위·건전성·대주주"),
        ("상호금융", "개별 설립법·감독규정", "회원·조합·신용사업"),
    ]
    add_table(doc, ["업권", "주요 규범", "핵심 규율"], sector_rows, [1600, 3650, 4388])
    add_callout(doc, "금융법의 기본 질문", "‘어떤 업무를 하는가’는 업권법이 답할 수 있지만, ‘그 업무를 특정 임원이 겸직할 수 있는가’는 지배구조법이 답할 수 있다. 업무의 출처 법률과 행위자를 규율하는 법률을 구분해야 한다.", kind="success")

    add_heading(doc, "14. 감독규정·시행세칙·자율규제", level=1)
    financial_layers = [
        ("금융위원회 감독규정", "법률·시행령의 위임을 받아 전문적 기준 구체화", "금융투자업규정·전자금융감독규정 등"),
        ("금융감독원 시행세칙", "감독규정의 산식·보고·서식·검사 세부", "업무보고서·위험액 산식·제출서식"),
        ("한국거래소 규정", "시장 운영·상장·공시·매매", "상장규정·시행세칙·업무규정"),
        ("금융투자협회 규정", "인수·판매·업무행위 자율규제", "증권 인수업무 등에 관한 규정"),
        ("표준준칙·모범규준", "회원사·업권의 표준 통제모델", "채택 여부와 근거·강제력 확인"),
        ("법령해석·비조치", "사실관계에 대한 감독당국 입장", "일반규범으로 자동 승격 금지"),
    ]
    add_table(doc, ["규범층", "기능", "예"], financial_layers, [2200, 4300, 3138])
    add_callout(doc, "명칭보다 근거가 중요", "‘규정’, ‘고시’, ‘세칙’, ‘모범규준’이라는 제목만으로 대외적 구속력을 단정할 수 없다. 상위 법령의 위임, 제정 주체, 적용대상, 회원계약·시장참가 관계, 회사의 채택 여부를 확인해야 한다.", kind="warning")

    add_heading(doc, "15. 금융 분야의 반복 판단축", level=1)
    axes_rows = [
        ("업의 포섭", "명칭보다 자기계산·타인계산·위험부담·대가·계약실질", "투자매매업/중개업"),
        ("인가·등록 범위", "허가받은 업무단위와 부수·겸영업무", "새 서비스 허용 여부"),
        ("행위자 적격", "임원·준법감시인·위험관리책임자의 겸직·독립성", "지배구조법"),
        ("판매행위", "권유·설명·광고·계약체결 관여의 실질", "금소법"),
        ("정보 흐름", "수집·이용·제공·위탁·조회·결합", "신용정보·개인정보"),
        ("IT·보안", "전자금융업무 여부, 정보처리 위탁, 접근매체·망분리", "전자금융감독규정"),
        ("건전성", "자본·유동성·신용공여·위험한도·보고", "업권 감독규정"),
        ("시장·공시", "상장·발행·배정·보고서·제출기한", "자본시장법·KRX"),
        ("이해상충", "계열사·이해관계인·정보교류·공동주관", "형식 금지와 예외 검증"),
    ]
    add_table(doc, ["판단축", "판단요소", "대표 영역"], axes_rows, [1800, 4850, 2988])

    add_part(doc, "IV", "외규에서 내규로", "외규를 그대로 복사하는 것이 아니라 책임·절차·통제·증적으로 번역해야 한다.")
    add_heading(doc, "16. 외규와 내규의 의미", level=1)
    add_body(doc, "금융회사 실무에서 ‘외규’는 법률·시행령·감독규정뿐 아니라 거래소·협회 규정, 감독당국 지침, 계약상 준수해야 하는 시장규칙 등을 넓게 가리키기도 한다. ‘내규’는 회사 내부의 정관·기준·규정·세칙·지침·매뉴얼·전결기준·서식을 포괄한다. 그러나 모든 외규와 내규의 법적 효력이 동일한 것은 아니다.")
    internal_rows = [
        ("정관", "회사의 기본 조직·주주·기관", "상법·특별법의 강행규정 우선"),
        ("이사회 규정·위원회 규정", "기관 구성·권한·운영", "법률·정관이 정한 권한 배분 준수"),
        ("내부통제기준·위험관리기준", "통제체계의 원칙·책임", "법률·감독규정에 근거"),
        ("세칙", "상위 내부기준의 세부 실행", "상위 기준의 위임범위 안"),
        ("지침·매뉴얼", "부서·업무별 처리절차", "규정·세칙을 구체적 행동으로 번역"),
        ("전결규정", "승인권자·금액구간·대결", "법정 이사회 권한을 임의 이전 불가"),
        ("서식·체크리스트", "입력값·증빙·승인 흔적", "실제 준수의 증거"),
        ("시스템 통제", "차단·경보·권한·로그", "문서상 의무를 실행 가능하게 함"),
    ]
    add_table(doc, ["내규층", "기능", "상위 통제"], internal_rows, [2050, 4000, 3588])
    add_callout(doc, "내규의 한계", "내규는 외부의 강행법규를 완화하거나 면제할 수 없다. 반대로 회사가 위험관리 목적으로 외규보다 엄격한 내부 한도를 정하는 것은 가능할 수 있지만, 고객 권리 침해나 법정 권한 배분 위반이 없어야 한다.", kind="risk")

    add_heading(doc, "17. 외규 의무를 내규로 변환하는 9단계", level=1)
    for text in (
        "**외규 원문 확보:** 시행일·개정일·적용대상·부칙까지 고정한다.",
        "**의무 원자화:** 수범자, 행위, 대상, 조건, 기한, 예외, 승인, 보고, 보존, 제재로 분해한다.",
        "**관계 조문 확장:** 정의·위임·준용·단서·별표·서식·벌칙을 함께 묶는다.",
        "**내부 책임 배정:** 이사회, 위원회, 책임자, 준법, 위험관리, 영업, IT, 감사의 RACI를 정한다.",
        "**내규층 선택:** 기본 원칙은 기준·규정, 수치와 절차는 세칙, 작업순서는 지침·매뉴얼에 둔다.",
        "**승인권한 확인:** 법·정관이 정한 주주총회·이사회 권한을 하위 내규로 옮기지 않는다.",
        "**통제 설계:** 예방·탐지·사후통제, 시스템 차단, 예외승인, 보고기한, 기록보존을 만든다.",
        "**효력·경과 관리:** 제정·개정일, 시행일, 구판 폐기, 진행 중 거래의 경과조치를 둔다.",
        "**검증·교육·증적:** 실제 업무가 내규대로 작동하는지 테스트하고 로그와 서류를 남긴다.",
    ):
        add_number(doc, text)

    add_heading(doc, "18. 외규 문언을 내규 통제로 번역하는 표", level=1)
    mapping_rows = [
        ("‘하여야 한다’", "의무", "담당자·기한·완료조건·증빙 지정"),
        ("‘승인을 받아야 한다’", "사전 승인", "승인권자·대결·예외·시스템 차단"),
        ("‘보고하여야 한다’", "보고", "보고대상·주기·서식·미보고 경보"),
        ("‘보관하여야 한다’", "기록", "보존기간·매체·접근권한·폐기"),
        ("‘각 호의 어느 하나’", "선택 요건", "체크리스트와 증빙 분기"),
        ("‘다만’", "예외", "예외승인과 근거자료 별도 보존"),
        ("‘대통령령으로 정한다’", "하위 기준", "시행령 수임조항까지 반영"),
        ("‘준용한다’", "다른 규칙 차용", "원조문의 행위자 치환표 작성"),
        ("‘지체 없이’", "정량화되지 않은 기한", "내부 SLA를 더 엄격하게 정하되 법 취지 유지"),
    ]
    add_table(doc, ["외규 문언", "법적 의미", "내규 구현"], mapping_rows, [2050, 2350, 5238])

    add_heading(doc, "19. 예시 내규의 실제 계층", level=1)
    add_source_note(doc, "아래 사례는 data/corpus/internal의 AI Agent 검증용 예시 내규를 해설한 것이며 실제 회사 규정이 아니다.")
    add_process(doc, [
        "지배구조법 제27조·시행령 + 금융투자업규정 제3-44조",
        "이사회가 정한 위험관리기준",
        "위험관리기준시행세칙 — 조직·위험한도·보고·개정 절차",
        "투자 및 인수 위험관리지침 — 딜 승인·인수한도·미매각·공동주관",
        "신규 딜 리스크검토요청서 — 입력값·승인·증빙",
        "리스크 시스템 — 한도 차단·경보·로그·보고서",
    ], title="외규→기준→세칙→지침→서식→시스템")
    example_rows = [
        ("정의 승계", "세칙 제2조", "자본시장법·금융투자업규정·상위 기준의 정의를 사용"),
        ("기관 권한", "세칙 제4조", "위험관리위원회가 기본방침·위험수준·한도를 승인"),
        ("조직 독립성", "세칙 제5조", "리스크관리부를 영업·지원부서와 독립 운영"),
        ("내부 한도", "세칙 제7조·제9조", "총위험한도와 내부 관리목표를 외규보다 구체화"),
        ("초과 조치", "세칙 제11조", "즉시 보고·3영업일 이내 해소계획·위원회 보고"),
        ("하위 지침", "투자·인수 지침 제3조 이하", "금액구간별 승인, 인수·미매각·채무보증 통제"),
        ("외규 직접 연결", "지침 제5·6·9조", "협회 인수규정의 신용평가·수요예측·공동주관을 내부 절차로 변환"),
    ]
    add_table(doc, ["설계요소", "예시 조항", "외규가 내규로 바뀐 모습"], example_rows, [1800, 2100, 5738])

    add_heading(doc, "20. 내규를 검토할 때의 충돌 체크", level=1)
    for text in (
        "내규가 인용한 외규의 법령명·조번호·개정본이 현행인지",
        "법률이 이사회 또는 주주총회에 준 권한을 부서장 전결로 바꾸지 않았는지",
        "상위 내규가 위원회 승인사항으로 정한 것을 하위 지침이 완화하지 않았는지",
        "외규의 예외요건을 내규가 넓혀 쓰지 않았는지",
        "내부 한도와 법정 최소·최대한도가 서로 뒤집히지 않았는지",
        "시행일과 경과조치가 있어 진행 중 거래·구판 서식 처리 기준이 있는지",
        "업무절차뿐 아니라 증빙·보존·보고·위반 시 조치가 연결되어 있는지",
        "시스템 권한과 문서상 승인권자가 일치하는지",
    ):
        add_bullet(doc, text)

    add_part(doc, "V", "RAG와 실제 골든", "법률가의 탐색 순서를 검색 단계와 typed relation으로 변환한다.")
    add_heading(doc, "21. 법률 질문을 구조화하는 기본 프레임", level=1)
    query_rows = [
        ("행위자", "누가 하는가", "준법감시인·은행·발행회사·투자자"),
        ("법적 객체", "무엇을 대상으로 하는가", "신주 발행사항·검토보고서·괴리율"),
        ("행위", "무엇을 하는가", "결정·제출·겸직·산정·위탁"),
        ("판단술어", "무엇을 판단하는가", "해당하는가·언제·누가·가능한가"),
        ("조건", "언제 어떤 요건에서", "보유비율·기간·회사유형·예외"),
        ("규율기능", "어떤 종류의 조문인가", "정의·권한·의무·예외·제재"),
        ("시간", "어느 법령 세대인가", "질문 기준일·회신 당시·현행"),
    ]
    add_table(doc, ["축", "질문", "예"], query_rows, [1550, 2950, 5138])
    add_process(doc, [
        "질문 본문과 괄호 업무 문맥을 분리",
        "핵심 판단술어와 법적 객체를 우선 추출",
        "업무의 출처 법률과 행위자를 규율하는 법률을 분리",
        "정의·위임·준용·특례·단서·부칙 관계를 typed edge로 확장",
        "조문 원문에서 행위자·대상·행위·조건·예외를 검증",
        "주조문과 companion을 bundle로 제시",
    ], title="질문→조항 bundle의 표준 경로")

    add_heading(doc, "22. LegalClosure V2의 실제 단계", level=1)
    stage_rows = [
        ("A_EXACT", "질문의 명시 용어와 구조적 일치", "정확 법령·조문·업무어에 강함"),
        ("B_ASSERTION", "주장·문장 의미를 넓게 탐색", "회수량이 크고 선택 손실 위험"),
        ("C_BM25", "키워드 기반 회수", "표면어가 직접 겹칠 때 강함"),
        ("ABC UNION", "앞 채널의 선택 후보 합침", "서로 다른 진입 경로 결합"),
        ("D_CLOSURE", "인용·정의·관계 조문 확장", "companion·인접·준용·위임 후보"),
        ("REFERENCE RESCUE", "명시 참조 구조 보완", "V2 61건에서는 기여 0"),
        ("PRESENT", "cap·세대·scope를 통과한 최종 제시", "최대 20개"),
    ]
    add_table(doc, ["단계", "역할", "대표 위험"], stage_rows, [1750, 4100, 3788])
    metrics_rows = [
        ("질문", "61건"),
        ("decisive gold", "90개 조항"),
        ("V2 최종 회수", "71/90 = 78.8889%"),
        ("all-gold case", "44/61 = 72.1311%"),
        ("D 확장 전/후 raw gold", "69→81"),
        ("D 선택 후 최종", "71 — 관계 cap에서 10 gold 손실"),
        ("role-predicate 피드백", "fsc-hard-003의 2개를 복구하여 73/90"),
    ]
    add_table(doc, ["지표", "결과"], metrics_rows, [3200, 6438], font_size=9.5)
    add_callout(doc, "수치 해석", "71/90은 답변 문장 정확도가 아니라, 90개의 결정적 정답 조항 중 최종 후보에 들어온 조항 비율이다. 44/61은 한 질문에 필요한 모든 정답 조항을 전부 회수한 질문 수다.", kind="info")

    add_heading(doc, "23. 실제 골든에서 잘 작동한 사례", level=1)
    add_success_case(doc, "23.1 직접 권한 조문", "정관 변경의 결의요건은?", "상법 제434조 — 최종 2위", ["정관 변경", "결의요건", "상법 제434조의 특별결의"], "질문의 핵심 객체와 조문 제목·본문이 직접 겹쳐 A_EXACT가 단독 기여했다.")
    add_success_case(doc, "23.2 회사기관 구성", "상장회사는 이사를 3명 이상 두어야 하는가?", "상법 제383조 — 최종 14위", ["상장회사·이사 수", "이사의 원수", "상법 제383조"], "기관·수치·조문 기능이 명확해 정확 구조검색이 살아남았다.")
    add_success_case(doc, "23.3 규정과 시행세칙 bundle", "재무적투자자가 제3자배정으로 취득한 주식은 제3호와 제4호 중 어디에 해당하는가?", "코스닥시장 상장규정 제26조 + 시행세칙 제23조", ["신규상장 의무보유", "상장규정 제26조의 대상 구분", "시행세칙 제23조의 세부 산정·기준"], "상위 규정과 시행세칙의 업무 문맥이 모두 질문에 노출되어 두 층을 회수했다.")
    add_success_case(doc, "23.4 법률과 시행령", "부여 기준시가 관련 규정은?", "벤처기업법 제16조의3 + 시행령 제11조의3", ["벤처기업 주식매수선택권", "부여요건", "법률 근거", "시행령의 기준시가 세부"], "정식 제도명이 강한 anchor가 되어 법률과 시행령이 함께 회수됐다.")
    add_success_case(doc, "23.5 여러 법률을 건너는 평가", "행사가격 설정에 필요한 부여일 기준 시가는 어떻게 평가하는가?", "벤처기업법 시행령 제11조의3 + 상증세법 제60조 + 시행령 제49조", ["주식매수선택권 행사가격", "시가 평가", "벤처기업법의 연결", "상증세법 평가 원칙", "시행령의 평가방법"], "질문이 요구하는 산식이 다른 법률의 평가체계로 넘어간다는 점을 회수했다.")
    add_success_case(doc, "23.6 의무와 면제 기준", "내부회계관리제도 구축의무와 그 면제 기준은?", "외부감사법 제8조 + 시행령 제9조", ["구축의무", "법률 제8조", "면제·적용예외", "시행령 제9조"], "원칙과 예외를 명시적으로 함께 묻고 있어 법률·시행령 bundle이 완성됐다.")
    add_success_case(doc, "23.7 지배구조법 겸직", "외국금융회사 국내지점의 자산 변동 시 준법감시인이 위험관리책임자를 겸직할 수 있는가?", "지배구조법 제29조 + 시행령 제24조", ["준법감시인", "위험관리책임자", "겸직 가능", "법률의 금지원칙", "시행령의 예외·규모기준"], "행위자와 겸직 판단술어, 회사 규모라는 조건이 모두 드러나 법률과 시행령을 회수했다.")
    add_success_case(doc, "23.8 오답 피드백에서 governing law 전환", "준법감시인이 개인채무자보호법상 채무조정 전담인력 업무를 수행할 수 있는가?", "지배구조법 제29조 + 시행령 제24조 — 피드백에서 0/2→2/2", ["질문에 나온 업무의 출처: 개인채무자보호법", "행위자: 준법감시인", "판단: 그 업무를 겸직·수행할 수 있는가", "규율법 전환: 지배구조법", "제29조·시행령 제24조 원문 검증"], "질문에 적힌 법률을 반복 검색하지 않고, 행위자와 판단술어를 통해 실제 governing law로 전환했다.")

    add_heading(doc, "24. 법률 관계를 RAG edge로 저장하는 방법", level=1)
    edge_rows = [
        ("delegates_to", "위임", "법률→시행령·시행규칙", "하위 구체화 필수"),
        ("implemented_by", "수임", "상위 근거←하위 조항", "역방향 탐색"),
        ("applies_mutatis_mutandis", "준용", "감사보수→이사보수", "원조문 본문 회수"),
        ("references", "일반 인용", "제○조에 따른", "무조건 필수로 보지 않음"),
        ("defined_by", "정의", "주요주주→정의조", "관할 범위 보존"),
        ("exception_to", "단서·예외", "원칙→예외", "원칙과 세트"),
        ("special_to", "특례", "상장법 특례→상법 일반", "충돌 범위 확인"),
        ("transitional_for", "경과조치", "구법 관계→신법", "시점·주체·사유"),
        ("sanctioned_by", "제재", "의무→벌칙·과태료", "수범자 일치"),
        ("authority_allocated_to", "권한 배분", "발행사항→이사회", "기관 질문"),
    ]
    add_table(doc, ["edge", "법적 관계", "예", "회수 계약"], edge_rows, [2200, 1700, 2900, 2838], font_size=8.8)
    add_callout(doc, "핵심 설계 원칙", "모든 연결을 related_article 하나로 저장하면 안 된다. 위임은 아래로, 준용은 옆으로, 특례는 일반규정과 대립하고, 경과조치는 시간축을 탄다. 질문의 판단축에 따라 열어야 할 edge가 다르다.", kind="success")

    add_part(doc, "VI", "잔여 오답 16건 사례집", "ADR-0096 기준 남은 16문제·17개 미도달 조항을 기존 V2와 피드백 루프로 나누어 해부한다.")
    add_heading(doc, "25. 전수 결과부터 이해하기", level=1)
    miss_summary = [
        ("raw 생성 후 선택 탈락", "14/17 조항", "검색 확대보다 bundle·선택·cap 개선이 우선"),
        ("완전 미생성", "3/17 조항", "준용 2단계·개념변환·법률→시행령 연결"),
        ("피드백 쟁점 카드 없음", "5/16 질문", "산식·기간·보수위임·임계값 카드 부재"),
        ("카드는 있으나 gate 실패", "11/16 질문", "판단술어 family와 actor 결속 없음"),
        ("조문 가설 해소 진입", "0/16", "모두 gate 이전에 종료"),
        ("신규 복구", "0/17", "점수 12/29 유지"),
    ]
    add_table(doc, ["구분", "결과", "의미"], miss_summary, [2500, 1800, 5338])
    add_callout(doc, "가장 큰 오해", "‘못 맞혔다’는 말만으로는 부족하다. 정답이 raw에도 없었는지, 생성됐지만 선택에서 떨어졌는지, 주조문만 있고 companion이 빠졌는지, 피드백 gate가 열리지 않았는지를 구분해야 한다.", kind="warning")

    cases = [
        {
            "id":"cm-004", "title":"괴리율 산식의 외규 간 결합",
            "question":"제5호의 괴리율은 어떻게 산정하는가? (업무 문맥: 신규상장 의무보유 — 코스닥시장 상장규정 제26조)",
            "gold":"코스닥시장 상장규정 시행세칙 제23조는 발견. 증권 인수업무 등에 관한 규정 제5조는 미도달.",
            "baseline":"제5조는 D 관계확장에서 생성됐지만 relation cap에서 탈락했다. 계산식은 찾았으나 공모가격의 정의 근거를 필수 산식 구성요소로 보존하지 못했다.",
            "feedback":"괴리율·산정을 처리하는 쟁점 카드가 없어 no_issue_card로 종료했다.",
            "legal":"하나의 조문 문제가 아니라 취득가격, 공모가격, 괴리율 계산식을 서로 다른 외규에서 조달하는 산식 bundle이다.",
            "path":["신규상장 의무보유 제5호", "시행세칙 제23조의 괴리율 공식", "인수업무규정 제5조의 공모가격", "두 값을 결합해 계산"],
            "fix":"numeric_formula family를 만들고, 계산식이 참조하는 변수 정의 조항을 cap 보호 대상으로 지정한다.", "kind":"info"
        },
        {
            "id":"cm-008", "title":"3개월에서 6개월로 늘어나는 위임 사유",
            "question":"국내 일반기업의 3개월 보유기간이 6개월로 연장되는 경우는? (상장주선인의 의무인수 및 보유)",
            "gold":"코스닥시장 상장규정 제13조는 발견. 시행세칙 제15조는 미도달.",
            "baseline":"시행세칙 제15조는 B·C·D 모두에서 생성됐으나 각 선택 cap에서 탈락했다. ‘시행세칙으로 정하는 사유’를 companion으로 유지하지 못했다.",
            "feedback":"3개월·6개월·연장 표현이 시점 카드 trigger에 포함되지 않아 카드 자체가 없었다.",
            "legal":"기간 숫자보다 ‘원칙 3개월—예외 6개월—시행세칙이 정한 과거 주선실적 사유’라는 위임된 조건 구조가 핵심이다.",
            "path":["상장규정 제13조의 3개월 원칙", "6개월 단서", "시행세칙으로 정한 사유", "시행세칙 제15조의 구체 요건"],
            "fix":"temporal_condition과 delegated_condition을 결합하고 ‘연장·단축·개월’도 시간 trigger로 인식한다.", "kind":"info"
        },
        {
            "id":"cm-011", "title":"실무 조치에서 상장심사 근거로 역탐색",
            "question":"사내규정 정비가 상장심사에서 요구되는 근거는? (질적심사요건과 사내규정 정비)",
            "gold":"코스닥시장 상장규정 제29조.",
            "baseline":"제29조는 B·C·D에서 생성됐으나 모두 탈락했다. ‘사내규정 정비’와 조문의 ‘기업지배구조·내부통제·공시체제·경영투명성’ 사이 개념 거리가 컸다.",
            "feedback":"‘근거’로 다른 법률 근거 카드를, ‘정비’ 주변에서 정보주체 정정 카드까지 잡았으나 legal_basis 판단축이 없었다.",
            "legal":"실무상 개선조치가 어떤 상위 심사기준을 충족하기 위한 것인지 역으로 찾는 legal basis 문제다.",
            "path":["사내규정 정비", "내부통제·공시체제 개선", "경영투명성·경영안정성", "코스닥시장 상장규정 제29조"],
            "fix":"legal_basis family와 ‘실무 조치→규범 목적·심사기준’ 역색인을 만든다.", "kind":"info"
        },
        {
            "id":"cm-016", "title":"행사시점의 원칙과 시행령 예외",
            "question":"벤처기업 주식매수선택권은 언제부터 행사할 수 있는가?",
            "gold":"벤처기업법 제16조의5는 발견. 시행령 제11조의4는 미도달.",
            "baseline":"시행령 제11조의4는 B·C·D에서 생성됐지만 탈락했다. 2년 원칙만 유지하고 사망·비귀책 퇴직 예외를 보존하지 못했다.",
            "feedback":"‘언제’로 시점 카드는 찾았지만 temporal_condition family가 없어 gate가 닫혔다.",
            "legal":"결의일 또는 이사회가 정한 날을 기산점으로 하는 2년 원칙과 시행령상 예외를 한 묶음으로 읽어야 한다.",
            "path":["주식매수선택권 행사", "법 제16조의5의 기산점·2년", "시행령 제11조의4의 예외", "원칙·예외 결합"],
            "fix":"시간 질문은 actor 없이 법적 객체+시간술어로 gate를 열고, 예외 companion을 보호한다.", "kind":"info"
        },
        {
            "id":"cm-025", "title":"이미 과세된 저가분과 부존재 확인",
            "question":"이익 계산 시 이미 과세된 저가분이 조정되는가? (주식등의 상장 등에 따른 이익의 증여)",
            "gold":"상증세법 시행령 제31조의3과 법 제39조는 발견. 법 제35조는 미도달.",
            "baseline":"제35조는 C·D에서 생성됐지만 탈락했다. 현재 계산조항과 선행 저가양수 과세조항을 하나의 조정 bundle로 보지 못했다.",
            "feedback":"과세·저가분·조정을 다루는 카드가 없어 no_issue_card였다.",
            "legal":"계산식과 이미 과세된 거래의 근거를 함께 회수한 뒤, 별도 차감 규정이 존재하는지를 확인하는 부존재 판단이다.",
            "path":["상장차익 계산식 제31조의3", "취득가액·증여세 과세가액 차감", "선행 저가양수 제35조·제39조", "별도 조정 명문 존재 여부"],
            "fix":"numeric_formula에 prior_tax_adjustment와 negative_evidence 검증을 추가한다.", "kind":"warning"
        },
        {
            "id":"cm-030", "title":"첨부서류와 적용대상 인용사슬",
            "question":"증권신고서 제출 시 1분기 검토보고서를 첨부하여야 하는가?",
            "gold":"발행공시규정 제2-6조·제2-4조는 발견. 자본시장법 시행령 제170조는 미도달.",
            "baseline":"시행령 제170조는 B·D에서 생성됐지만 탈락했다. 첨부조항이 인용한 발행인 범위의 근거를 부수 조항으로 취급했다.",
            "feedback":"‘범위’와 ‘신고’ 카드는 잡았지만 filing_requirement family와 발행인 역할 결속이 없었다.",
            "legal":"첨부의무, 서류 정의, 적용 발행인의 3조문 사슬이다. 상장 전 발행인인지 금융기관·상장법인인지가 결론을 바꾼다.",
            "path":["증권신고서 첨부의무 제2-6조", "분기감사·검토보고서 정의 제2-4조", "시행령 제170조의 적용 발행인", "IPO 발행인에의 적용 여부"],
            "fix":"filing_requirement family를 객체 중심으로 열고 selected 조문이 직접 인용한 적용대상 조항을 보호한다.", "kind":"info"
        },
        {
            "id":"cm-031", "title":"거래소 규정상 재무서류 제출",
            "question":"거래소 규정상 요구되는 재무서류는? (IPO 단계의 재무서류 제출범위)",
            "gold":"코스닥시장 상장규정 제5조.",
            "baseline":"B에서 생성됐지만 선택되지 않았다. 거래소 규정·재무서류가 너무 일반적이어서 공시·신고·상장서류 후보에 밀렸다.",
            "feedback":"‘제출범위’로 포섭 카드만 선택했고 제출의무 판단축이 없었다.",
            "legal":"국내기업과 외국기업을 구분하고, 반기 종료 후 45일이 지난 국내기업의 반기재무제표·검토보고서 의무를 찾아야 한다.",
            "path":["IPO 상장신청", "국내기업 여부", "반기 종료 후 45일", "코스닥시장 상장규정 제5조의 제출서류"],
            "fix":"시장·회사유형·서류객체·기한을 묶는 filing_requirement 라우터가 필요하다.", "kind":"info"
        },
        {
            "id":"cm-033", "title":"‘최초’의 수식범위와 60일",
            "question":"종전 별도기준에서 연결기준으로 처음 전환하는 법인도 60일인가?",
            "gold":"자본시장법 제160조.",
            "baseline":"제160조는 B·C에서 생성됐지만 탈락했다. 종전·별도·처음·60일이 경과조치와 일반 기한 후보로 분산됐다.",
            "feedback":"‘종전’을 구법 경과조치로, 문장 끝 ‘인가’를 인가 문제로 오인했다. temporal_condition은 없었다.",
            "legal":"여기서 종전은 구법이 아니다. ‘최초로 연결재무제표를 기준으로 작성하여 제출’이라는 문장에서 최초의 수식범위를 해석하는 문제다.",
            "path":["반기·분기보고서 제출", "연결재무제표 기준으로 최초 작성", "60일 특례 문언", "자본시장법 제160조의 문장구조"],
            "fix":"형태소 경계가 없는 substring trigger를 제거하고, 시간술어와 수식범위 분석을 도입한다.", "kind":"warning"
        },
        {
            "id":"cm-039", "title":"주주총회와 이사회의 잔여 권한",
            "question":"사내규정 제정은 주주총회 결의사항인가, 이사회 결의사항인가?",
            "gold":"상법 제361조는 발견. 제393조는 미도달.",
            "baseline":"제393조는 C·D에서 생성됐지만 탈락했다. 주총 권한 제한과 이사회 업무집행 권한을 쌍으로 유지하지 못했다.",
            "feedback":"‘결의사항인가’ 속 ‘인가’를 별도 인가 문제로 읽어 두 법의 관문 카드를 선택했다. authority_allocation이 없었다.",
            "legal":"주주총회는 법·정관 사항만 결의하고, 별도 열거되지 않은 회사 업무집행은 이사회 권한이라는 잔여 권한 배분이다.",
            "path":["상법 제361조의 주총 권한 한정", "사내규정 제정의 별도 열거 여부", "상법 제393조의 업무집행", "이사회 권한 결론"],
            "fix":"authority_allocation family와 ‘기관 A 대 기관 B’ 비교 bundle을 만든다.", "kind":"info"
        },
        {
            "id":"cm-043", "title":"감사 보수의 2단계 준용",
            "question":"감사 보수의 결정을 이사회에 위임할 수 있는가?",
            "gold":"상법 제415조는 생성 후 탈락. 제388조는 미생성.",
            "baseline":"제415조가 D에서 생성됐지만 탈락했고, 제415조가 준용하는 제388조까지 다음 hop을 열지 않아 제388조는 생성되지 않았다.",
            "feedback":"감사 보수·위임·이사회 권한 카드가 없어 no_issue_card였다.",
            "legal":"감사 보수→제415조의 준용→이사 보수 제388조→정관 또는 주주총회라는 2단계 준용 구조다.",
            "path":["감사 보수", "상법 제415조", "제388조 준용", "정관 또는 주주총회 결정", "이사회 위임 근거 부재"],
            "fix":"준용 edge를 원조문 본문까지 강제하고, late seed에서도 한 번 더 확장하는 authority bundle이 필요하다.", "kind":"risk"
        },
        {
            "id":"cm-048", "title":"발행사항 결정기관의 개념 변환",
            "question":"발행사항은 어느 기관이 결정하는가? (우리사주조합원에 대한 주식 배정)",
            "gold":"상법 제416조 — 미생성.",
            "baseline":"업무 문맥이 본문보다 강하게 작동하여 ‘주식 배정 결정’으로 grounding했고 자본시장법의 우리사주 배정규정으로 이동했다. 상법 문서군이 선택되지 않았다.",
            "feedback":"‘어느 기관’을 행정 절차·소관으로 읽어 절차와 불복 카드를 선택했고 authority_allocation family는 없었다.",
            "legal":"발행사항을 신주 발행사항으로 정규화하고, 이사회·주주총회 사이의 회사기관 권한 문제로 번역해야 한다.",
            "path":["발행사항", "신주 발행사항", "결정기관", "회사기관 권한 배분", "상법 제416조"],
            "fix":"본문 술어를 괄호 문맥보다 우선하고, 법적 객체+결정술어만으로 authority gate를 연다.", "kind":"risk"
        },
        {
            "id":"cm-049", "title":"공동주관 의무와 지분보유 임계값",
            "question":"주관회사 또는 그 계열회사가 발행회사 지분을 보유하면 공동주관 의무가 발생하는가?",
            "gold":"인수업무규정 제2조·제6조는 발견. 제15조는 미도달.",
            "baseline":"제15조는 A·B·D에서 생성됐지만 탈락했다. 이해관계인 정의와 5% 원칙은 잡았지만 10% 예외를 필수로 유지하지 못했다.",
            "feedback":"계열회사로 이해관계인 거래 카드는 찾았지만, 이 질문의 본질인 인수업무 독립성과 threshold 판단술어가 없었다.",
            "legal":"주관회사와 이해관계인의 합산 보유비율, 5% 원칙, 특정 발행회사 10% 예외, 공동주관 의무를 함께 본다.",
            "path":["이해관계인 정의 제2조", "공동주관 의무 제6조", "5% 원칙", "제15조의 10% 예외", "해당 발행회사 여부"],
            "fix":"relationship_threshold family와 정의·의무·예외의 3조문 bundle을 도입한다.", "kind":"info"
        },
        {
            "id":"cm-050", "title":"100분의 10이라는 짧은 임계값 질문",
            "question":"100분의 10이 적용되는 경우는? (공동주관회사 선임의무)",
            "gold":"증권 인수업무 등에 관한 규정 제15조.",
            "baseline":"제15조는 B에서 생성됐지만 탈락했다. 질문이 짧아 다른 10% 조항과 구별하기 어려웠다.",
            "feedback":"산식·임계값 카드가 없어 no_issue_card였다.",
            "legal":"업무 문맥을 제6조 공동주관 의무에 결속한 뒤 제15조제4항제2호 단서의 특정 발행회사 예외로 이동해야 한다.",
            "path":["공동주관회사 선임의무", "제6조의 5% 기준", "제15조제4항제2호 단서", "중소·벤처·중견·기술기업 10%"],
            "fix":"숫자만 있는 질문은 선행 업무 문맥과 cross-reference를 강제하는 numeric_threshold family로 처리한다.", "kind":"info"
        },
        {
            "id":"fsc-hard-004", "title":"국채 거래형태의 업 포섭",
            "question":"은행이 자기계좌로 국채를 먼저 매도한 후 매수하여 결제하는 방식이 국채 투자매매업자로서 가능한 영업형태인가?",
            "gold":"자본시장법 제6조.",
            "baseline":"제6조는 B·C에서 생성됐지만 탈락했다. 국채·외국인·통합계좌·결제라는 긴 사실이 ‘자기의 계산으로 매매’라는 법적 핵심을 압도했다.",
            "feedback":"포섭 카드는 찾았지만 legal_classification family가 없었고, 이용·활용 때문에 정보이용 카드까지 잡았다. 은행도 actor 사전에 없었다.",
            "legal":"위험부담, 자기계좌, 수수료 부재를 통해 투자매매업인지 투자중개업인지 분류하는 업의 정의 문제다.",
            "path":["거래위험 부담", "자기계좌 사용", "중개수수료 없음", "자기계산 매매", "자본시장법 제6조의 투자매매업"],
            "fix":"legal_classification을 역할 사전과 분리하고 사실요소를 업의 구성요건 슬롯으로 변환한다.", "kind":"info"
        },
        {
            "id":"fsc-hard-006", "title":"주요주주 정의와 시행령 companion",
            "question":"투자계약상 동의권을 가진 투자자가 지배구조법상 대주주·주요주주에 해당하는가?",
            "gold":"지배구조법 제2조는 발견. 시행령 제4조는 미생성.",
            "baseline":"법 제2조까지만 도달했다. 제2조가 대통령령에 맡긴 영향력·지배 기준을 시행령 제4조로 내려가는 수직 연결이 작동하지 않았다.",
            "feedback":"포섭 카드는 찾았지만 legal_classification이 없었고, 계약상 동의를 개인정보 동의 카드로도 오인했다. 투자자 역할도 결속되지 않았다.",
            "legal":"10% 보유 또는 임원 과반 선임 등 지배력을 기준으로 단순 동의권이 주요주주 요건에 해당하는지 판단하는 정의 bundle이다.",
            "path":["주요주주 해당 여부", "지배구조법 제2조 정의", "대통령령으로 정한 영향력 기준", "시행령 제4조", "투자계약상 동의권과 비교"],
            "fix":"정의조에서 공식 companion을 강제하고 D에서 늦게 들어온 seed에도 companion 확장을 재실행한다.", "kind":"risk"
        },
        {
            "id":"fsc-hard-009", "title":"투자자문 구조의 업무위탁 포섭",
            "question":"제3자 투자자문을 참고해 증권사가 고객에게 자문하는 구조가 법규에 위배되는가, 업무위수탁인가?",
            "gold":"자본시장법 제42조는 발견. 시행령 제46조는 미도달.",
            "baseline":"시행령 제46조는 B·D에서 생성됐지만 cap에서 탈락했다. 법률상 위탁 근거만 남고 하위 시행령의 범위·방법이 빠졌다.",
            "feedback":"포섭 카드와 정확한 업무위탁 카드를 찾았지만 ‘위배되는가·위수탁인가’를 legal classification으로 인식하지 못했고 투자자문사·증권사 actor도 없었다.",
            "legal":"외부 자문이 단순 참고인지 실질적으로 업무 일부를 맡긴 것인지 판단한 뒤 법 제42조와 시행령 제46조를 결합해야 한다.",
            "path":["제3자 자문 사용", "내부 투자판단의 실질", "업무위탁 해당 여부", "자본시장법 제42조", "시행령 제46조의 범위·방법"],
            "fix":"이 사례는 카드까지 맞았으므로 legal_classification gate와 금융투자회사 역할 사전만 보강해도 가장 먼저 복구될 가능성이 높다.", "kind":"success"
        },
    ]
    for case in cases:
        add_case_card(doc, case)

    add_heading(doc, "26. 오답을 구조적으로 다시 분류", level=1)
    fix_rows = [
        ("선택·cap", "14개 조항", "typed bundle 보호, 주조문이 선택되면 필수 companion 유지"),
        ("준용 2단계", "cm-043", "제415조→제388조까지 확장"),
        ("개념 변환", "cm-048", "발행사항→신주 발행사항→기관 권한"),
        ("수직 위임", "fsc-hard-006", "법 제2조→시행령 제4조"),
        ("numeric_formula", "cm-004·025", "산식과 변수 정의·선행 과세"),
        ("temporal_condition", "cm-008·016·033", "기간·기산점·연장·수식범위"),
        ("filing_requirement", "cm-030·031", "서류·발행인·시점·인용체인"),
        ("authority_allocation", "cm-039·043·048", "주총·이사회·준용"),
        ("legal_classification", "fsc-004·006·009", "업·주요주주·위탁 포섭"),
        ("relationship_threshold", "cm-049·050", "관계인 정의와 비율 예외"),
        ("legal_basis", "cm-011", "실무 조치에서 상위 규범 목적 역탐색"),
    ]
    add_table(doc, ["개선축", "대상", "핵심 구현"], fix_rows, [2300, 2600, 4738])

    add_heading(doc, "27. 개선 우선순위", level=1)
    for text in (
        "**1순위 — 이미 생성된 14개를 살린다.** 검색량을 늘리기보다 정의·위임·준용·예외·산식 bundle을 cap에서 보호한다.",
        "**2순위 — 완전 미생성 3개를 전용 edge로 복구한다.** 준용 2-hop, 권한 개념 변환, 시행령 수직 연결이다.",
        "**3순위 — 피드백 판단축을 분리한다.** numeric, temporal, filing, authority, basis, classification, threshold를 각각 독립 gate로 만든다.",
        "**4순위 — actor 강제를 완화한다.** 산식·기간·서류·기관 질문은 명시 행위자가 없어도 법적 객체+판단술어로 열려야 한다.",
        "**5순위 — trigger를 형태소 단위로 만든다.** ‘결의사항인가’의 ‘인가’, 계약상 ‘동의’를 인허가·개인정보 카드로 잘못 보내지 않는다.",
        "**6순위 — 현재 법령 세대를 고정한다.** 같은 조문이라도 개정본 doc/node가 달라 exact 채점과 실제 서비스가 갈라질 수 있다.",
    ):
        add_number(doc, text)

    add_part(doc, "APPENDIX", "반복 학습 부록", "용어사전, 실전 체크리스트, 근거 문서를 한곳에 모았다.")
    add_heading(doc, "A. 핵심 용어사전", level=1)
    glossary = [
        ("강행규정", "당사자 합의·내규로 배제할 수 없는 규정"),
        ("임의규정", "당사자 합의가 없을 때 보충적으로 적용되는 규정"),
        ("수범자", "법적 의무·금지·제재의 직접 대상"),
        ("포섭", "사실관계가 법률요건에 해당하는지 판단하는 작업"),
        ("위임", "상위 규범이 하위 규범에 구체화 권한을 부여"),
        ("수임", "하위 규범이 위임받은 내용을 규정"),
        ("재위임", "위임받은 사항 일부를 다시 아래에 맡김"),
        ("준용", "다른 조문을 필요한 수정과 함께 적용"),
        ("의제·간주", "사실과 달라도 법률상 그렇게 취급"),
        ("추정", "반대증명 전까지 사실로 인정"),
        ("단서", "본문 원칙에 대한 예외·한정"),
        ("적용례", "새 규정이 적용되는 최초 사건을 지정"),
        ("경과조치", "구법상 지위·처분·절차를 일정 범위 보호"),
        ("법령보충적 행정규칙", "법령의 구체적 위임 아래 외부효가 인정될 수 있는 고시·규정"),
        ("자율규제", "거래소·협회 등이 시장·회원 관계에서 정한 규율"),
        ("내부통제", "법규준수·위험관리·업무건전성을 확보하기 위한 조직·절차·통제"),
        ("companion 조항", "주조문을 완성하는 정의·시행령·예외·준용·산식 조항"),
        ("governing law", "질문에 언급된 법률이 아니라 실제 판단주체·행위를 규율하는 법률"),
        ("gold", "평가에서 반드시 회수해야 한다고 동결된 결정적 조항"),
        ("raw 후보", "선택·cap 적용 전 생성된 조항 후보"),
    ]
    add_table(doc, ["용어", "정의"], glossary, [2500, 7138], font_size=9.4)

    add_heading(doc, "B. 법률 질문 12단계 체크리스트", level=1)
    checklist = [
        "질문의 기준일과 적용 법령 세대를 확인했는가?",
        "본문 질문과 괄호 업무 문맥을 분리했는가?",
        "행위자·객체·행위·판단술어·조건을 추출했는가?",
        "질문에 적힌 법률과 실제 governing law를 구분했는가?",
        "정의조의 관할을 확인했는가?",
        "법률이 시행령·시행규칙·고시에 위임했는가?",
        "다른 조문을 준용·적용·인용하는가?",
        "본문과 단서, 원칙과 예외를 함께 읽었는가?",
        "특별법·일반법 또는 ‘에도 불구하고’ 관계가 있는가?",
        "부칙의 시행일·적용례·경과조치를 확인했는가?",
        "의무조항과 벌칙·과태료·보고·보존 조항을 연결했는가?",
        "최종 답에 필요한 모든 companion 조항이 포함됐는가?",
    ]
    for item in checklist:
        add_number(doc, item)

    add_heading(doc, "C. 외규→내규 검토 체크리스트", level=1)
    for item in (
        "외규의 제정 주체와 법적 효력을 확인한다.",
        "상위 위임근거와 현재 시행일을 기록한다.",
        "외규 의무를 수범자·행위·조건·기한·예외·증빙으로 분해한다.",
        "이사회·위원회·책임자·부서의 권한을 법·정관과 맞춘다.",
        "상위 내규와 하위 세칙·지침의 위임문언을 둔다.",
        "내부 한도는 외규의 최소·최대한도와 방향이 맞는지 검증한다.",
        "예외승인·전결·대결이 법정 기관 권한을 침해하지 않는지 본다.",
        "구판 폐기, 시행일, 진행 중 거래의 경과조치를 둔다.",
        "서식과 시스템이 동일한 필수값·승인자·기한을 요구하는지 확인한다.",
        "교육·모니터링·위반조치·증적 보존까지 닫힌 루프로 만든다.",
    ):
        add_bullet(doc, item)

    add_heading(doc, "D. 주요 근거와 연구 산출물", level=1)
    sources = [
        ("헌법", "국가법령정보센터 대한민국헌법", "https://www.law.go.kr/법령/대한민국헌법"),
        ("법제 기준", "법제처 2026년 법령 입안·심사 기준", "data/wiki/raw/moleg/2026-법령 입안심사 기준.md"),
        ("행정규칙 기준", "법제처 2026년 행정규칙 입안·심사 기준", "data/wiki/raw/moleg/2026-행정규칙 입안심사 기준.md"),
        ("위임", "위임과 법령보충", "data/wiki/wiki/해석원칙/위임과-법령보충.md"),
        ("준용", "준용과 경과조치", "data/wiki/wiki/해석원칙/준용과-경과조치.md"),
        ("정의", "정의 우선", "data/wiki/wiki/방법/정의-우선.md"),
        ("단서", "단서 읽기", "data/wiki/wiki/방법/단서-읽기.md"),
        ("금융위 회신", "better.fsc.go.kr 회신사례 수집본", "data/corpus/fsc/manifest.json"),
        ("거래소 규정", "한국거래소 규정·시행세칙 수집본", "data/corpus/krx/manifest.json"),
        ("협회 규정", "금융투자협회 규정 수집본", "data/corpus/kofia/manifest.json"),
        ("예시 내규", "위험관리기준시행세칙·투자 및 인수 위험관리지침", "data/corpus/internal/manifest.json"),
        ("V2 원장", "ADR-0091 조항 도달 보고서", "docs/adr/ADR-0091-legalclosure-v2-article-reachability-ledger/artifacts/reachability-report-run-002.md"),
        ("피드백 성공", "ADR-0094 role-predicate router", "docs/adr/ADR-0094-role-predicate-governing-law-feedback-router/README.md"),
        ("잔여 오답", "ADR-0096 16건 전수 재생", "docs/adr/ADR-0096-remaining-miss-feedback-loop-replay/README.md"),
    ]
    add_table(doc, ["분류", "자료", "위치"], sources, [1500, 3900, 4238], font_size=8.4)

    add_heading(doc, "마지막 정리", level=1)
    add_callout(doc, "한 문장으로", "법률 검색의 목표는 관련 문서를 많이 모으는 것이 아니라, **질문의 법적 판단축을 정확히 분류하고 그 판단을 완성하는 조문 관계망을 증거와 함께 닫는 것**이다.", kind="success")
    add_body(doc, "효력 계층은 어떤 규범이 우선하는지를 말하고, 위임·준용·특례·정의·단서·부칙은 조항들이 어떻게 결합하는지를 말한다. 금융회사의 내규는 그 결합된 외규를 조직·책임·승인·기한·서식·시스템 통제로 번역한 운영 규범이다. RAG가 이 관계를 타입별로 보존할 때 비로소 법률가가 법을 읽는 경로와 가까워진다.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    build()
