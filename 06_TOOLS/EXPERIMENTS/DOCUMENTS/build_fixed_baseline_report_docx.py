#!/usr/bin/env python3
"""Build the detailed ADR-0118 fixed research baseline DOCX."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

import build_legal_rag_report_docx as report
from generate_fixed_baseline_report_diagrams import generate_all


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
SOURCE = ROOT / "07_DOCS" / "REFERENCE" / "REPORTS" / "LEGAL_RAG_FIXED_BASELINE_ADR0118_2026-08-31.md"
OUTPUT = ROOT / "09_ARTIFACTS" / "LEGACY_ARTIFACTS" / "대한민국_법령_금융규제_RAG_최종고정구조_상세설계서_ADR-0118_2026-08-31.docx"
DIAGRAM_ROOT = ROOT / "09_ARTIFACTS" / "LEGACY_ARTIFACTS" / "legal_rag_fixed_baseline_diagrams"

FIGURES = {
    "{{FIGURE_FIXED_OVERVIEW}}": (
        DIAGRAM_ROOT / "01_fixed_overview.png",
        "그림 1. 최종 고정 연구구조와 운영 상태의 경계",
        "질문 계획에서 회수, 28개 원문, atomic compiler, 답변 gate로 이어지는 ADR-0118 고정 구조",
    ),
    "{{FIGURE_RETRIEVAL_STAGES}}": (
        DIAGRAM_ROOT / "02_retrieval_stages.png",
        "그림 2. 법체계 진입부터 최종 제시까지의 12단계 회수·검증 상태 머신",
        "closed grounding, 법체계 route, semantic card, baseline floor, typed relation, provenance 검증과 final present 단계",
    ),
    "{{FIGURE_COMPILER_PACKET}}": (
        DIAGRAM_ROOT / "03_compiler_packet.png",
        "그림 3. 비파괴 atomic claim compiler의 입력·packet·답변 계약",
        "28개 원문을 유지하면서 issue, role, exact quote, closed evidence ID를 결속하는 compiler packet",
    ),
    "{{FIGURE_CM008}}": (
        DIAGRAM_ROOT / "04_cm008.png",
        "그림 4. cm-008에서 본칙 E01과 시행세칙 E13을 함께 사용하는 구조",
        "3개월에서 6개월 연장 질문이 코스닥시장 상장규정 제13조와 시행세칙 제15조로 완성되는 사례",
    ),
    "{{FIGURE_PERFORMANCE}}": (
        DIAGRAM_ROOT / "05_performance.png",
        "그림 5. 최신 세 구조의 난도균형 점수와 최종 제시·답변 선언 간 손실",
        "ADR-0118이 난도균형 점수에서 가장 높고 final-present 95개 중 answer-declared 67개만 사용된 선택 병목",
    ),
}


def _header_footer(section) -> None:
    header = section.header
    paragraph = header.paragraphs[0]
    paragraph.text = ""
    paragraph.paragraph_format.space_after = Pt(2)
    run = paragraph.add_run("대한민국 법령·금융규제 RAG | ADR-0118 고정 연구구조")
    report._set_run_font(run, size=8.5, color=report.MUTED)

    footer = section.footer
    foot = footer.paragraphs[0]
    foot.text = ""
    foot.paragraph_format.space_before = Pt(3)
    report._add_page_field(foot)


def _cover(doc: Document) -> None:
    kicker = doc.add_paragraph(style="Report Kicker")
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kicker.paragraph_format.space_before = Pt(112)
    kicker.paragraph_format.space_after = Pt(20)
    kicker.add_run("FIXED RESEARCH BASELINE · ARCHITECTURE GUIDE")

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(12)
    title.paragraph_format.keep_with_next = True
    run = title.add_run("대한민국 법령·금융규제 RAG\n최종 고정 연구구조 상세설계서")
    report._set_run_font(run, size=27, bold=True, color=report.NAVY)

    subtitle = doc.add_paragraph(style="Report Subtitle")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(32)
    subtitle.add_run("ADR-0118 integrated-atomic-claim-v4b")

    lead = doc.add_paragraph()
    lead.alignment = WD_ALIGN_PARAGRAPH.CENTER
    lead.paragraph_format.left_indent = Inches(0.55)
    lead.paragraph_format.right_indent = Inches(0.55)
    lead.paragraph_format.space_after = Pt(86)
    lead_run = lead.add_run(
        "법체계 기반 12단계 회수 · immutable baseline floor · exact-quote atomic compiler · closed evidence answer gate"
    )
    report._set_run_font(lead_run, size=11.2, bold=True, color=report.DARK_BLUE)

    meta = doc.add_paragraph(style="Report Meta")
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.paragraph_format.space_after = Pt(5)
    meta.add_run("고정 기준  ADR-0118-experiment-v1 / integrated-atomic-claim-v4b / run-002")
    meta2 = doc.add_paragraph(style="Report Meta")
    meta2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta2.paragraph_format.space_after = Pt(5)
    meta2.add_run("평가 정본  Golden61 v3 · authority as-of 20260827")
    meta3 = doc.add_paragraph(style="Report Meta")
    meta3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta3.add_run("상태  연구 기준선 고정 · MAIN/API/검색 기본 배선 변경 없음")
    doc.add_page_break()


def _audit(doc: Document) -> None:
    section = doc.sections[0]
    assert round(section.page_width.inches, 2) == 8.5
    assert round(section.page_height.inches, 2) == 11.0
    assert all(round(value.inches, 2) == 1.0 for value in (
        section.top_margin, section.right_margin, section.bottom_margin, section.left_margin
    ))
    assert len(doc.paragraphs) > 150
    assert len(doc.tables) >= 14
    assert len(doc.inline_shapes) == len(FIGURES)
    all_text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert "{{FIGURE_" not in all_text
    assert "ADR-0118-experiment-v1" in all_text
    for table in doc.tables:
        grid = table._tbl.tblGrid.findall(qn("w:gridCol"))
        assert sum(int(col.get(qn("w:w"))) for col in grid) == report.CONTENT_WIDTH_DXA
        assert table._tbl.tblPr.find(qn("w:tblInd")).get(qn("w:w")) == str(report.TABLE_INDENT_DXA)


def build() -> Path:
    generate_all()
    report.FIGURES = FIGURES
    source = SOURCE.read_text(encoding="utf-8")
    doc = Document()
    report._configure_styles(doc)
    report._configure_section(doc.sections[0], first=True)
    _header_footer(doc.sections[0])
    bullet_num_id, decimal_num_id = report._ensure_numbering(doc)
    _cover(doc)
    report._add_body(doc, source, bullet_num_id, decimal_num_id)
    _audit(doc)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.core_properties.title = "대한민국 법령·금융규제 RAG 최종 고정 연구구조 상세설계서"
    doc.core_properties.subject = "ADR-0118 integrated-atomic-claim-v4b의 고정 결정, 구조, 성능과 한계"
    doc.core_properties.author = "8-AGENT"
    doc.core_properties.keywords = (
        "법률 RAG, ADR-0118, integrated legal research, atomic claim compiler, "
        "Golden61, evidence confusion matrix, fixed research baseline"
    )
    doc.save(OUTPUT)
    print(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    build()
