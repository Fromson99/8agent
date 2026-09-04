#!/usr/bin/env python3
"""CM 골든 원본을 질문·답변 카드와 좌표 표로 재구성한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from annotate_cm_golden_coordinates_docx import ROLE_LABELS


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
DEFAULT_SOURCE = ROOT / "[CM본부] 주요 법규정 질의 등_260819.docx"
DEFAULT_SUITE = ROOT / "01_DATA/review/cm_core_e2e_v3.json"
DEFAULT_OUTPUT = ROOT / "09_ARTIFACTS/LEGACY_ARTIFACTS/[CM본부] 주요 법규정 질의 등_260819_골든좌표_가독성개선본.docx"
DEFAULT_REPORT = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0141-cm-golden-docx-readable-layout/artifacts/run-001.json"

EASY_CM_003 = (
    "제3자배정으로 취득했다는 형식만 보면 제26조 제1항 제3호를 먼저 검토합니다. "
    "그런데 취득자가 벤처금융 또는 전문투자자이면, 시행세칙 제23조 제4항 제2호가 "
    "이를 제3호 단서의 제외사유로 다룹니다. 따라서 이 경우는 제3호가 아니라 제4호의 "
    "의무보유 대상으로 분류합니다."
)

NAVY = "17365D"
BLUE = "DCE6F1"
GREEN = "E2F0D9"
GOLD = "FFF2CC"
PALE = "F7F9FC"
GRAY = "E7E6E6"
WHITE = "FFFFFF"
TEXT = "1F2937"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _strip_label(text: str, kind: str) -> str:
    text = _normalized(text)
    if kind == "question":
        text = re.sub(r"^\d+(?:\.\d+)?\.\s*", "", text)
        return re.sub(r"^\((?:추가)?질문\)\s*", "", text)
    return re.sub(r"^\((?:추가)?답변\)\s*", "", text)


def _shade(cell: Any, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def _margins(cell: Any, top: int = 100, start: int = 120, bottom: int = 100, end: int = 120) -> None:
    properties = cell._tc.get_or_add_tcPr()
    tc_mar = properties.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        properties.append(tc_mar)
    for tag, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{tag}"))
        if node is None:
            node = OxmlElement(f"w:{tag}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _set_cell(
    cell: Any,
    text: str,
    *,
    fill: str,
    bold: bool = False,
    color: str = TEXT,
    size: float = 9.0,
    align: WD_ALIGN_PARAGRAPH = WD_ALIGN_PARAGRAPH.LEFT,
) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = align
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.12
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.name = "Malgun Gothic"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    _shade(cell, fill)
    _margins(cell)


def _fixed_table(table: Any, widths: list[float]) -> None:
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    properties = table._tbl.tblPr
    layout = properties.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        properties.append(layout)
    layout.set(qn("w:type"), "fixed")
    for row in table.rows:
        for index, cell in enumerate(row.cells):
            cell.width = Cm(widths[index])
        cant_split = OxmlElement("w:cantSplit")
        row._tr.get_or_add_trPr().append(cant_split)


def _repeat_header(row: Any) -> None:
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    row._tr.get_or_add_trPr().append(repeat)


def _set_repeat_table_header(row: Any) -> None:
    _repeat_header(row)


def _add_card(document: Document, label: str, text: str, label_fill: str, body_fill: str) -> Any:
    table = document.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    _set_cell(table.cell(0, 0), label, fill=label_fill, bold=True, color=WHITE, size=9.5,
              align=WD_ALIGN_PARAGRAPH.CENTER)
    _set_cell(table.cell(0, 1), text, fill=body_fill, size=9.5)
    _fixed_table(table, [2.0, 15.4])
    document.add_paragraph().paragraph_format.space_after = Pt(0)
    return table


def _add_coordinate_table(document: Document, case: dict[str, Any]) -> int:
    articles = list(case.get("evidence_articles") or [])
    label = document.add_paragraph()
    label.paragraph_format.space_before = Pt(2)
    label.paragraph_format.space_after = Pt(3)
    label.paragraph_format.keep_with_next = True
    run = label.add_run(f"골든 좌표  ·  {case['id']}  ·  article-root {len(articles)}개")
    run.bold = True
    run.font.name = "Malgun Gothic"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
    run.font.size = Pt(9.5)
    run.font.color.rgb = RGBColor.from_string(NAVY)

    table = document.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    headers = ("역할", "법령·조문", "기계 좌표", "검증")
    for index, header in enumerate(headers):
        _set_cell(table.cell(0, index), header, fill=NAVY, bold=True, color=WHITE,
                  align=WD_ALIGN_PARAGRAPH.CENTER)
    _set_repeat_table_header(table.rows[0])
    for article in articles:
        row = table.add_row()
        role = str(article.get("evidence_role_v3") or "")
        _set_cell(row.cells[0], f"{ROLE_LABELS.get(role, role)}\n{role}", fill=BLUE, bold=True, size=8.2)
        _set_cell(row.cells[1], f"{article.get('law')}\n{article.get('article')}", fill=WHITE, size=8.7)
        _set_cell(
            row.cells[2],
            f"{article.get('coordinate_key')}\ndoc_id {article.get('doc_id')}  /  node {article.get('node')}",
            fill=PALE,
            size=8.2,
        )
        _set_cell(
            row.cells[3],
            f"{article.get('corpus_status')}\n{article.get('authority_as_of')}",
            fill=GREEN,
            bold=True,
            size=8.2,
            align=WD_ALIGN_PARAGRAPH.CENTER,
        )
    _fixed_table(table, [3.2, 5.0, 6.8, 2.4])
    spacer = document.add_paragraph()
    spacer.paragraph_format.space_after = Pt(3)
    return len(articles)


def _add_page_number(section: Any) -> None:
    paragraph = section.footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("CM Golden v3  ·  ")
    run.font.name = "Malgun Gothic"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
    run.font.size = Pt(8)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    paragraph._p.append(field)


def _configure(document: Document) -> None:
    section = document.sections[0]
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    _add_page_number(section)
    normal = document.styles["Normal"]
    normal.font.name = "Malgun Gothic"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
    normal.font.size = Pt(9.5)
    normal.font.color.rgb = RGBColor.from_string(TEXT)
    for style_name, size, color in (("Title", 21, NAVY), ("Heading 1", 14, NAVY)):
        style = document.styles[style_name]
        style.font.name = "Malgun Gothic"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor.from_string(color)
        style.font.bold = True


def _add_front_matter(document: Document) -> None:
    title = document.add_paragraph(style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run("[CM본부] 주요 법·규정 질의응답")
    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(10)
    run = subtitle.add_run("Golden v3 최소충분 조문 · 좌표 검증본")
    run.bold = True
    run.font.color.rgb = RGBColor.from_string(NAVY)

    summary = document.add_table(rows=1, cols=4)
    summary.style = "Table Grid"
    for index, (value, label) in enumerate((("51", "평가 질의"), ("98", "필수 조문"),
                                            ("98/98", "코퍼스 해소"), ("20260827", "좌표 기준일"))):
        _set_cell(summary.cell(0, index), f"{value}\n{label}", fill=BLUE, bold=True, color=NAVY,
                  size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
    _fixed_table(summary, [4.35, 4.35, 4.35, 4.35])

    note = document.add_paragraph()
    note.paragraph_format.space_before = Pt(7)
    note.paragraph_format.space_after = Pt(7)
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = note.add_run("※ 채점 좌표는 항·호가 아닌 canonical article-root(조문) 단위입니다.")
    run.italic = True
    run.font.size = Pt(8.5)

    legend_title = document.add_paragraph()
    legend_title.paragraph_format.space_after = Pt(3)
    legend_title.add_run("근거 역할 범례").bold = True
    legend = document.add_table(rows=1, cols=2)
    legend.style = "Table Grid"
    _set_cell(legend.cell(0, 0), "근거 역할", fill=NAVY, bold=True, color=WHITE,
              align=WD_ALIGN_PARAGRAPH.CENTER)
    _set_cell(legend.cell(0, 1), "이 문서에서의 뜻", fill=NAVY, bold=True, color=WHITE,
              align=WD_ALIGN_PARAGRAPH.CENTER)
    for role in ("MAIN", "CONDITION_EXCEPTION", "DEFINITION", "INCORPORATION_BRIDGE",
                 "INCORPORATED_RULE", "DELEGATION_BRIDGE", "DELEGATED_DETAIL"):
        row = legend.add_row()
        _set_cell(row.cells[0], f"{ROLE_LABELS[role]} ({role})", fill=BLUE, bold=True, size=8.2)
        descriptions = {
            "MAIN": "결론을 직접 정하는 주된 조문",
            "CONDITION_EXCEPTION": "적용 요건·단서·예외를 정하는 조문",
            "DEFINITION": "질문의 핵심 용어 범위를 정하는 조문",
            "INCORPORATION_BRIDGE": "다른 조문을 준용하도록 연결하는 조문",
            "INCORPORATED_RULE": "준용에 따라 실제로 적용되는 조문",
            "DELEGATION_BRIDGE": "하위규정에 세부사항을 위임하는 조문",
            "DELEGATED_DETAIL": "위임을 받아 수치·절차를 정한 하위규정",
        }
        _set_cell(row.cells[1], descriptions[role], fill=WHITE, size=8.2)
    _fixed_table(legend, [6.0, 11.4])
    document.add_page_break()


def build(source: Path, suite_path: Path, output: Path, report_path: Path) -> dict[str, Any]:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    cases = list(suite.get("cases") or [])
    source_sha = _sha256(source)
    frozen_sha = str((suite.get("source") or {}).get("sha256") or "")
    if source_sha != frozen_sha:
        raise ValueError(f"source_sha256:{frozen_sha}:{source_sha}")
    if len(cases) != 51:
        raise ValueError(f"case_count:{len(cases)}")

    output_document = Document()
    _configure(output_document)
    _add_front_matter(output_document)
    source_document = Document(source)
    case_index = 0
    current_case: dict[str, Any] | None = None
    question_count = 0
    answer_count = 0
    coordinate_count = 0
    easy_count = 0
    role_counts: Counter[str] = Counter()
    alignment_errors: list[str] = []

    for paragraph in source_document.paragraphs:
        text = _normalized(paragraph.text)
        if not text or text == "[CM본부] 주요 법·규정 질의응답 정리":
            continue
        if re.search(r"\((?:추가)?질문\)", text):
            question_count += 1
            question = _strip_label(text, "question")
            if question_count == 1:
                _add_card(output_document, "묶음 질문", question, NAVY, BLUE)
                current_case = None
                continue
            current_case = cases[case_index]
            case_index += 1
            if question != str(current_case.get("source_question") or ""):
                alignment_errors.append(f"{current_case.get('id')}:question")
            label = "추가질문" if "(추가질문)" in text else "질문"
            _add_card(output_document, label, question, NAVY, BLUE)
            continue
        if re.search(r"\((?:추가)?답변\)", text):
            answer_count += 1
            if current_case is None:
                alignment_errors.append(f"answer_without_case:{answer_count}")
                continue
            answer = _strip_label(text, "answer")
            if answer != str(current_case.get("reference_answer") or ""):
                alignment_errors.append(f"{current_case.get('id')}:answer")
            label = "추가답변" if "(추가답변)" in text else "답변"
            _add_card(output_document, label, answer, "2F6B4F", GREEN)
            if current_case["id"] == "cm-003":
                _add_card(output_document, "쉽게 풀면", EASY_CM_003, "B7791F", GOLD)
                easy_count += 1
            coordinate_count += _add_coordinate_table(output_document, current_case)
            role_counts.update(
                str(article.get("evidence_role_v3") or "")
                for article in current_case.get("evidence_articles") or []
            )
            current_case = None
            continue
        if re.match(r"^\d+\.\s+", text):
            heading = output_document.add_paragraph(text, style="Heading 1")
            heading.paragraph_format.keep_with_next = True
            heading.paragraph_format.space_before = Pt(9)
            heading.paragraph_format.space_after = Pt(5)
            continue
        alignment_errors.append(f"unclassified:{text[:40]}")

    if alignment_errors:
        raise ValueError("; ".join(alignment_errors))
    if (question_count, answer_count, case_index, coordinate_count, easy_count) != (52, 51, 51, 98, 1):
        raise ValueError(
            f"counts:questions={question_count}:answers={answer_count}:cases={case_index}:"
            f"coordinates={coordinate_count}:easy={easy_count}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output_document.save(output)
    reopened = Document(output)
    coordinate_tables = [
        table for table in reopened.tables
        if len(table.rows) and [cell.text for cell in table.rows[0].cells] == ["역할", "법령·조문", "기계 좌표", "검증"]
    ]
    embedded_coordinates = sum(len(table.rows) - 1 for table in coordinate_tables)
    labels = [table.cell(0, 0).text for table in reopened.tables if table.rows and table.columns]
    reopened_easy = labels.count("쉽게 풀면")
    if len(coordinate_tables) != 51 or embedded_coordinates != 98 or reopened_easy != 1:
        raise ValueError(
            f"roundtrip:coordinate_tables={len(coordinate_tables)}:"
            f"coordinates={embedded_coordinates}:easy={reopened_easy}"
        )

    report = {
        "schema_version": "cm-golden-readable-docx-audit-v1",
        "status": "complete",
        "source": {"path": str(source), "sha256": source_sha, "unchanged": True},
        "suite": {"path": str(suite_path), "sha256": _sha256(suite_path),
                  "version": suite.get("version"), "authority_as_of": "20260827"},
        "output": {"path": str(output), "sha256": _sha256(output), "bytes": output.stat().st_size},
        "counts": {
            "source_questions": question_count,
            "source_answers": answer_count,
            "scorable_cases": case_index,
            "coordinate_tables": len(coordinate_tables),
            "embedded_coordinates": embedded_coordinates,
            "easy_explanation_cm_003": reopened_easy,
        },
        "role_counts": dict(sorted(role_counts.items())),
        "validation": {
            "source_hash_matches_frozen": True,
            "question_answer_alignment": "51/51",
            "coordinate_embedding": "98/98",
            "docx_roundtrip": True,
            "fixed_table_layout": True,
            "row_split_prevention": True,
            "repeating_coordinate_headers": True,
            "llm_calls": 0,
            "retrieval_calls": 0,
        },
        "cm_003_easy_explanation": EASY_CM_003,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = build(args.source, args.suite, args.output, args.report)
    counts = report["counts"]
    print(
        f"PASS: 문답 {counts['scorable_cases']}/51 · 좌표 "
        f"{counts['embedded_coordinates']}/98 · 표 {counts['coordinate_tables']}/51 "
        f"· cm-003 쉬운 설명 {counts['easy_explanation_cm_003']}/1"
    )
    print(args.output)
    print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
