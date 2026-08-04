"""파트 분리 — 귀속은 읽기 순서가 아니라 지면 위치로 한다 (§6 T2).

이 버그는 기존 테스트 89개를 **전부 통과했다.** 빈 템플릿에서는 별지1 값이
텍스트 요소로도 나와 표가 새는 것이 가려졌고, 값이 채워진 체결본에서만
별지1 필드가 통째로 사라졌다. 그래서 도클링의 실제 출력 순서를 재현해 못 박는다.

실측(ss2207): 도클링은 표를 요소 목록 **맨 끝**에 몰아서 낸다.
    idx 107  p5  page_header  '[별지1]'
    idx 135  p7  text         '[별지2]'
    idx 165  p5  table        ← 별지1 의 표가 [별지2] 마커 뒤에 도착한다
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import ontology     # noqa: E402
import structure    # noqa: E402
from parse_stage import Element, ParseResult   # noqa: E402


@pytest.fixture(scope="module")
def onto():
    return ontology.load(ontology.default_path(ROOT))


def _el(index, page, top, kind="text", text="", table=None, furniture=False):
    """PDF 좌표는 아래가 원점이라 top 이 클수록 페이지 위쪽이다."""
    return Element(index=index, kind=kind, text=text, table=table, page=page,
                   bbox=[28.0, top, 560.0, top - 11.0], furniture=furniture)


def _doc(elements):
    return ParseResult(path="x.pdf", doc_id="x", born_digital=True,
                       parser="test", elements=elements)


@pytest.fixture
def sample():
    """본문 p1 → 별지1 p5 → 별지2 p7. 표 2개는 읽기 순서 맨 끝에 붙는다."""
    return _doc([
        _el(0, 1, 700, text="제1조(신탁의 목적) 이 계약은 …"),
        _el(1, 1, 660, text="① 위탁자는 [별지1] 신탁계약 세부내역에 기재된 금액을 신탁한다"),
        _el(2, 5, 797, kind="page_header", text="[별지1]", furniture=True),
        _el(3, 5, 700, text="신탁금액"),
        _el(4, 6, 500, text="기타 특약사항"),
        _el(5, 7, 797, text="[별지2]"),
        _el(6, 7, 700, text="변경계약서"),
        _el(7, 5, 600, kind="table", table=[["신탁금액", "금 일억원정", "계약서제2조"]]),
        _el(8, 7, 600, kind="table", table=[["구분", "변경 전", "변경 후"]]),
    ])


def test_appendix_table_stays_in_its_own_part(sample, onto):
    """맨 끝에 도착한 p5 표는 별지1 것이다 — 읽기 순서상 [별지2] 뒤에 있어도."""
    st = structure.build(sample, onto)
    where = {p.role: [e.index for e in p.elements] for p in st.parts}
    assert 7 in where["별지1_입력"], f"별지1 표가 샜습니다: {where}"
    assert 8 in where["별지2_변경"]
    assert 7 not in where["별지2_변경"]


def test_body_reference_is_not_a_boundary(sample, onto):
    """본문의 '[별지1] …에 기재된' 은 참조이지 파트 경계가 아니다."""
    st = structure.build(sample, onto)
    body = st.part(onto.default_role())
    assert [e.index for e in body.elements] == [0, 1]


def test_reading_order_preserved_within_part(sample, onto):
    """파트 안에서는 읽기 순서를 지킨다 — 조/항 트리가 그 순서에 의존한다."""
    st = structure.build(sample, onto)
    for p in st.parts:
        idx = [e.index for e in p.elements]
        assert idx == sorted(idx), f"{p.role} 의 순서가 흐트러졌습니다: {idx}"


def test_marker_line_itself_is_not_content(sample, onto):
    st = structure.build(sample, onto)
    texts = [e.content() for p in st.parts for e in p.elements]
    assert "[별지1]" not in texts and "[별지2]" not in texts


def test_element_without_bbox_falls_back_to_reading_order(onto):
    """bbox 가 없으면 직전 요소의 위치를 물려받는다 — 순서 정보가 그것뿐이다."""
    els = [
        _el(0, 5, 797, kind="page_header", text="[별지1]", furniture=True),
        _el(1, 5, 700, text="신탁금액"),
        Element(index=2, kind="text", text="금 일억원정", page=5, bbox=None),
    ]
    st = structure.build(_doc(els), onto)
    assert [e.index for e in st.part("별지1_입력").elements] == [1, 2]


def test_page_split_between_appendices(sample, onto):
    """같은 페이지에 두 파트가 걸치면 마커 아래쪽만 다음 파트다."""
    els = list(sample.elements) + [
        _el(9, 7, 750, text="별지2 마커 아래 — 별지2"),
        _el(10, 5, 300, text="별지1 페이지 아래쪽 — 별지1"),
    ]
    st = structure.build(_doc(els), onto)
    where = {p.role: [e.index for e in p.elements] for p in st.parts}
    assert 10 in where["별지1_입력"] and 9 in where["별지2_변경"]
