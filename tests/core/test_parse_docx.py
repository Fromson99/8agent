"""DOCX 파싱 — 추론 없이 스타일·태그를 읽는 경로 (parse_adapter.parse_docx).

docling 은 돌지만 msword_backend 는 모델 추론이 없어(SimplePipeline) 빠르다.
픽스처는 python-docx(docling 의 의존성)로 즉석 생성한다 — 바이너리를 레포에
넣지 않고, 무엇이 들어 있는지 테스트가 스스로 말하게.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core import parse_adapter                                         # noqa: E402

docx = pytest.importorskip("docx", reason="python-docx 필요 (docling 의존성)")


@pytest.fixture(scope="module")
def sample(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("docx") / "sample.docx"
    d = docx.Document()
    d.add_heading("제1장 총칙", level=1)
    d.add_heading("제1절 목적과 정의", level=2)
    d.add_paragraph("제1조(목적) 이 준칙은 무엇을 정하는지를 밝힌다.")
    d.add_paragraph("제2조(정의) 이 준칙에서 쓰는 용어의 뜻은 다음 각 호와 같다.")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "구분"
    t.cell(0, 1).text = "내용"
    t.cell(1, 0).text = "가입자"
    t.cell(1, 1).text = "위탁자 본인"
    d.save(str(p))
    return p


def test_headings_carry_real_levels(sample):
    """PDF 는 전부 level 1 로 평면화되지만 DOCX 는 Word 스타일의 진짜 계층이 온다."""
    r = parse_adapter.parse(sample)
    heads = {e.text: e.meta.get("level") for e in r.elements
             if e.type == "section_header"}
    assert heads.get("제1장 총칙") == 1
    assert heads.get("제1절 목적과 정의") == 2
    assert r.stats["headings_with_level"] >= 2


def test_paragraphs_and_markers_survive(sample):
    r = parse_adapter.parse(sample)
    texts = [e.text for e in r.elements if e.text]
    assert any(t.startswith("제1조(목적)") for t in texts)
    assert any(t.startswith("제2조(정의)") for t in texts)


def test_table_comes_as_logical_cells(sample):
    r = parse_adapter.parse(sample)
    tables = [e for e in r.elements if e.is_table]
    assert len(tables) == 1
    cells = {(c.row, c.col): c.text for c in tables[0].table.cells}
    assert cells[(0, 0)] == "구분" and cells[(1, 1)] == "위탁자 본인"
    assert r.stats["tables"] == 1


def test_no_page_geometry_by_design(sample):
    """DOCX 는 리플로우 문서 — 지면 좌표가 원리적으로 없다. 전부 page=1, bbox 없음."""
    r = parse_adapter.parse(sample)
    assert all(e.page == 1 and e.bbox is None for e in r.elements)
    assert r.born_digital is True
    assert "(docx" in r.parser


# (라우터 판별용 _probe 테스트는 자동 판별(detect) 제거와 함께 걷어냈다 —
#  유형은 호출자가 말하고, 위장 포맷 방어는 각 파서의 입구 게이트가 한다.)
