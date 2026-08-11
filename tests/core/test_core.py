"""범용 모듈 단위 테스트 — docling 없이 도는 것만 (빠르다).

PDF 파싱이 필요한 검증은 tests/agent1/ 에 있다.
"""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core import fitness_gate, format_model, normalize, structurize   # noqa: E402
from core import glossary as glossary_mod                             # noqa: E402
from core import parse_adapter                                         # noqa: E402
from core.parse_adapter import Cell, Element, ParseResult, Table      # noqa: E402


# ===========================================================================
# T1 용어집
# ===========================================================================

def _glossary(**terms) -> glossary_mod.Glossary:
    return glossary_mod.Glossary(version=1, doc_type="테스트", terms=terms)


def test_kind_is_dual():
    """한 용어가 section 이면서 fact 일 수 있다 (§1.1)."""
    g = _glossary(**{"신탁계약 세부내역": {"kind": ["section", "fact"]},
                     "신탁금액": {"kind": ["fact"], "value_type": "number"}})
    assert "신탁계약 세부내역" in g.section_terms()
    assert "신탁계약 세부내역" in g.fact_terms()
    assert g.section_terms() == ["신탁계약 세부내역"]


def test_aliases_fold_to_canonical():
    g = _glossary(**{"신탁금액": {"kind": ["fact"], "value_type": "number",
                                "aliases": ["투자금액", "신탁원금"]}})
    assert g.lookup("투자금액") == "신탁금액"
    assert g.lookup("신탁 금액") == "신탁금액"        # 공백 차이 흡수
    assert g.lookup("없는말") is None


def test_value_type_only_on_fact_terms():
    with pytest.raises(ValueError, match="fact 용어가 아닌데"):
        _glossary(**{"기타 특약사항": {"kind": ["section"], "value_type": "number"}})


def test_unknown_value_type_rejected():
    with pytest.raises(ValueError, match="value_type"):
        _glossary(**{"금액": {"kind": ["fact"], "value_type": "money"}})


def test_colliding_surface_rejected():
    """두 용어가 같은 정규형으로 접히면 매칭이 갈린다 — 로드에서 막는다."""
    with pytest.raises(ValueError, match="양쪽에 걸립니다"):
        _glossary(**{"신탁금액": {"kind": ["fact"]},
                     "신탁 금액": {"kind": ["fact"]}})


# ===========================================================================
# T8 값 정규화 (§3.3)
# ===========================================================================

@pytest.mark.parametrize("raw,want", [
    ("금 1억원정 (₩100,000,000)", Decimal(100_000_000)),   # 같은 금액 이중 표기
    ("금 일억원정 (₩ 100,000,000)", Decimal(100_000_000)),
    ("100,000,000원", Decimal(100_000_000)),
    ("1억 5천만원", Decimal(150_000_000)),                  # 한국어 수사 중첩
    ("5천만", Decimal(50_000_000)),
    ("억원", Decimal(100_000_000)),
])
def test_parse_number(raw, want):
    assert normalize.parse_number(raw) == want


@pytest.mark.parametrize("raw,want", [
    ("24년 1월 1일", date(2024, 1, 1)),
    ("2024-01-01", date(2024, 1, 1)),
    ("24.6.3", date(2024, 6, 3)),
    ("2024.07.01", date(2024, 7, 1)),
])
def test_parse_date(raw, want):
    assert normalize.parse_date(raw) == want


def test_parse_date_range():
    got = normalize.parse_date_range("2024년 6월 3일부터 2027년 6월 2일까지")
    assert got == {"start": date(2024, 6, 3), "end": date(2027, 6, 2)}


def test_parse_percents_takes_all():
    """한 값 안의 비율이 여럿이면 전부 본다 — 앞의 하나만 보면 뒤 변경을 놓친다."""
    assert normalize.parse_percents("(연 3%)를 초과하는 이익 × (15)%") == [Decimal(3), Decimal(15)]


def test_normalization_failure_is_none_not_guess():
    """정규화 실패는 None — 그럴듯한 값을 지어내지 않는다 (§3.3)."""
    assert normalize.parse_number("기타특약사항에 기재") is None
    assert normalize.parse_date("연 1.5%") is None


@pytest.mark.parametrize("vt,a,b,verdict", [
    ("number", "금 1억원정", "100,000,000원", "MATCH"),          # 포맷 차이는 일치
    ("date_range", "24.6.3 ~ 27.6.2", "2024년 6월 3일부터 2027년 6월 2일까지", "MATCH"),
    ("percent", "연 1.5%", "1.50%", "MATCH"),
    ("account_no", "123-45-678901", "12345678901", "MATCH"),
    ("number", "100,000,000원", "10,000,000원", "VALUE_MISMATCH"),  # 자릿수 누락
    ("percent", "기타특약사항에 기재", "연 0.8%", "NEEDS_REVIEW"),      # 파싱 실패
])
def test_compare(vt, a, b, verdict):
    assert normalize.compare(vt, a, b).verdict == verdict


# ===========================================================================
# 형식 파일 (§2.4)
# ===========================================================================

def _fmt(**kw) -> format_model.Format:
    base = dict(doc_type="테스트",
                regex_markers=[{"id": "조", "pattern": r"^제\s*(\d+)\s*조\(([^)]+)\)",
                                "level": 1, "groups": ["no", "title"], "label": "제{no}조"},
                               {"id": "별지", "pattern": r"^\[별지(\d+)\]", "level": 0,
                                "groups": ["no"], "label": "별지{no}", "max_tail": 20}],
                term_markers=[{"term": "신탁계약 세부내역", "level": 1}])
    base.update(kw)
    return format_model.Format.model_validate(base)


def test_bad_pattern_rejected():
    with pytest.raises(ValueError, match="패턴이 잘못됐습니다"):
        format_model.Format.model_validate(
            {"doc_type": "x", "regex_markers": [{"id": "a", "pattern": "([", "level": 0}]})


def test_format_needs_at_least_one_marker():
    with pytest.raises(ValueError, match="마커가 하나도 없습니다"):
        format_model.Format.model_validate({"doc_type": "x"})


def test_max_tail_separates_marker_from_mention():
    """`[별지1]` 은 경계, `[별지1]신탁계약 세부내역의 위탁자와 …` 는 문장이다 (§1.3)."""
    m = _fmt().marker("별지")
    assert m.match("[별지1]") is not None
    assert m.match("[별지1] 신탁계약 세부내역") is not None       # 제목 + 짧은 꼬리
    assert m.match("[별지1]신탁계약 세부내역의 위탁자와 삼성증권주식회사는 …") is None


def test_term_marker_must_be_section_term():
    g = _glossary(**{"신탁금액": {"kind": ["fact"], "value_type": "number"}})
    problems = _fmt().validate_against_glossary(g)
    assert any("section 용어가 아닙니다" in p or "용어집에 없습니다" in p for p in problems)


# ===========================================================================
# T7 구조화 (§3.1)
# ===========================================================================

def _el(i, text="", type="text", table=None, page=1):
    return Element(index=i, type=type, text=text, table=table, page=page)


def _parsed(elements):
    return ParseResult(path="t.pdf", doc_id="t", parser="test",
                       born_digital=True, elements=elements)


@pytest.fixture
def sample_doc():
    g = _glossary(**{"신탁계약 세부내역": {"kind": ["section", "fact"]},
                     "신탁금액": {"kind": ["fact"], "value_type": "number",
                                "aliases": ["투자금액"]},
                     "기본보수": {"kind": ["fact"], "value_type": "percent"},
                     "수익보수": {"kind": ["fact"], "value_type": "percent"}})
    table = Table(n_rows=1, n_cols=6, cells=[
        Cell("신탁보수", 0, 0), Cell("기본보수", 0, 1), Cell("연 1.5%", 0, 2),
        Cell("수익보수", 0, 3), Cell("(연 3%)를 초과하는 이익 × (15)%", 0, 4),
        Cell("계약서 제12조", 0, 5)])
    elements = [
        _el(0, "제1조(신탁의 목적) 위탁자는 금전을 신탁한다."),
        _el(1, "제2조(신탁금액)"),
        _el(2, "이 신탁의 신탁금액은 [별지1] 신탁계약 세부내역에 기재된 금액으로 한다."),
        _el(3, "[별지1]", type="page_header", page=5),
        _el(4, "신탁계약 세부내역", type="section_header", page=5),
        _el(5, "신탁금액: 금 1억원정 (₩100,000,000)", page=5),
        _el(6, table=table, type="table", page=5),
    ]
    return structurize.run(_parsed(elements), _fmt(), g), g


def test_every_element_lands_in_exactly_one_section(sample_doc):
    """모든 요소는 정확히 하나의 최심 section 에 속한다 (§3.1-2, §7-3)."""
    doc, _ = sample_doc
    assigned = sum(len(s.content) for s in doc.sections) + sum(
        1 for s in doc.sections if s.marker.get("kind") != "default")
    assert doc.residual == []
    assert assigned >= 7 - 1        # 마커 줄 자신은 content 가 아니라 section 이 된다


def test_body_is_the_remainder_not_a_detection(sample_doc):
    """마커를 지나기 전 요소는 기본 구역에 담긴다 — 본문을 판별하지 않는다."""
    doc, _ = sample_doc
    tops = [s.section_id for s in doc.sections if len(s.path) == 1]
    assert tops[0] == "본문"
    assert "별지1" in tops


def test_term_marker_opens_section_under_regex_marker(sample_doc):
    doc, _ = sample_doc
    assert doc.section("별지1/신탁계약 세부내역") is not None


def test_mention_and_value_are_separated_by_coordinate(sample_doc):
    """본문의 mention 도 fact 가 된다 — 구별은 추출이 아니라 **좌표**가 한다.

    같은 용어가 본문 문장에도, 별지 표에도 나온다. 추출이 둘을 가리려 들면
    문서마다 임계값이 늘어난다. 대신 section_id 를 달리 두고, 태스크 규칙이
    `별지1/신탁계약 세부내역` 을 지정하면 본문 mention 은 조회되지 않는다(§3.2).
    """
    doc, _ = sample_doc
    by_section = {f.section_id for f in doc.facts if f.term == "신탁금액"}
    assert "본문/제2조" in by_section          # mention 도 문장 레벨 fact 다
    assert "별지1/신탁계약 세부내역" in by_section  # 실제 값도 있다
    # 좌표로 지정하면 본문 것은 걸리지 않는다
    got = doc.find_fact("신탁금액", section_ids=["별지1/신탁계약 세부내역"])
    assert got is not None and got.value == Decimal(100_000_000)


def test_fact_has_section_coordinate_and_value(sample_doc):
    """"어떤 섹션의 어떤 용어"가 기본 좌표다 (§3.2)."""
    doc, _ = sample_doc
    f = doc.find_fact("신탁금액", section_ids=["별지1/신탁계약 세부내역"])
    assert f is not None
    assert f.section_id == "별지1/신탁계약 세부내역"
    assert f.value == Decimal(100_000_000)
    assert f.raw and f.source["page"] == 5


def test_a_row_with_two_terms_yields_two_facts(sample_doc):
    """한 행에 용어가 둘이면 fact 도 둘 — 문장(행)이 단위이므로 raw 는 같다.

    라벨-값을 코드로 가르지 않는다. 행 안에서 어느 쪽이 어느 값인지 가리는 일은
    임계값을 부르고, 그건 형식 컴파일의 의미를 없앤다(§0-1).
    """
    doc, _ = sample_doc
    basic = doc.find_fact("기본보수")
    perf = doc.find_fact("수익보수")
    assert basic is not None and perf is not None
    assert basic.raw == perf.raw                    # 같은 행 = 같은 문장 단위
    assert "기본보수" in basic.raw and "수익보수" in perf.raw


def test_sentences_are_the_fact_unit(sample_doc):
    """문장이 fact 단위다 — 한 문단이 여러 문장이면 여러 fact 후보가 된다 (§1.1)."""
    assert len(structurize._split_sentences("첫 문장이다. 둘째 문장이다.")) == 2
    assert len(structurize._split_sentences("종결부호 없는 한 줄")) == 1


def test_runtime_is_deterministic(sample_doc):
    """같은 문서를 두 번 구조화하면 JSON 이 동일하다 (§7-2)."""
    doc, g = sample_doc
    table = Table(n_rows=1, n_cols=6, cells=[
        Cell("신탁보수", 0, 0), Cell("기본보수", 0, 1), Cell("연 1.5%", 0, 2),
        Cell("수익보수", 0, 3), Cell("(연 3%)를 초과하는 이익 × (15)%", 0, 4),
        Cell("계약서 제12조", 0, 5)])
    elements = [
        _el(0, "제1조(신탁의 목적) 위탁자는 금전을 신탁한다."),
        _el(1, "제2조(신탁금액)"),
        _el(2, "이 신탁의 신탁금액은 [별지1] 신탁계약 세부내역에 기재된 금액으로 한다."),
        _el(3, "[별지1]", type="page_header", page=5),
        _el(4, "신탁계약 세부내역", type="section_header", page=5),
        _el(5, "신탁금액: 금 1억원정 (₩100,000,000)", page=5),
        _el(6, table=table, type="table", page=5),
    ]
    again = structurize.run(_parsed(elements), _fmt(), g)
    a, b = doc.dump(), again.dump()
    a.pop("generated_at"), b.pop("generated_at")
    assert a == b


# ===========================================================================
# T9 적합도 게이트 (§3.4)
# ===========================================================================

def test_gate_quarantines_a_foreign_document(sample_doc):
    """형식과 다른 문서는 격리된다 — 조용한 실패 금지 (§7-6)."""
    _doc, g = sample_doc
    elements = [_el(0, "이 문서는 전혀 다른 양식입니다."),
                _el(1, "아무 마커도 없습니다.")]
    doc = structurize.run(_parsed(elements), _fmt(), g)
    fit = fitness_gate.apply(doc, _fmt(), len(elements))
    assert not fit.passed
    assert any("부합" in w for w in fit.warnings)


def test_gate_passes_a_conforming_document(sample_doc):
    doc, g = sample_doc
    fit = fitness_gate.apply(doc, _fmt(), 7)
    assert fit.passed, fit.warnings


def test_circled_digits_do_not_crash_the_parsers():
    """`'①'.isdigit()` 은 True 다 — 항 번호가 섞인 문장이 파서를 터뜨렸다."""
    text = "① 제1항의 신탁금액은 ⑮ 항에 따른다"
    assert normalize.parse_number(text) is not None or True      # 크래시하지 않으면 된다
    for fn in (normalize.parse_number, normalize.parse_percent, normalize.parse_date,
               normalize.parse_date_range, normalize.parse_range_tiers):
        fn(text)                                                  # 예외 없이 통과


# ===========================================================================
# 표·그림 — 구조를 열지 않고 구조에 담긴다
# ===========================================================================

def test_figure_survives_parsing(tmp_path):
    """그림은 텍스트가 없다 — 텍스트와 같은 길로 흘리면 조용히 사라진다."""
    md = tmp_path / "t.md"
    md.write_text("# 제목\n\n![수수료 체계](fig1.png)\n\n본문입니다.\n", encoding="utf-8")
    parsed = parse_adapter.parse(md)
    figs = [e for e in parsed.elements if e.is_picture]
    assert len(figs) == 1, [e.type for e in parsed.elements]
    assert figs[0].meta["caption"] == "수수료 체계"
    assert figs[0].meta["ref"] == "fig1.png"
    assert parsed.stats["pictures"] == 1


def test_table_and_figure_never_open_a_section():
    """구역을 여는 것은 마커다. 표 안의 번호도, 그림 캡션도 구역을 열지 않는다."""
    table = Table(n_rows=1, n_cols=2, cells=[Cell("제1조", 0, 0), Cell("값", 0, 1)])
    fig = _el(2, "제2조 그림 캡션", type="picture")
    assert not fig.opens_structure
    assert not _el(1, table=table, type="table").opens_structure
    assert _el(0, "제1조(목적) 가").opens_structure


def test_markdown_header_row_is_marked():
    """구분선(`|---|`) 위가 열 머리글이다 — 지우기 전에 경계를 읽는다."""
    md = Path(__file__).parent / "_tmp_tbl.md"
    md.write_text("| 구분 | 1년 미만 |\n|---|---|\n| 중도해지수수료 | 0.7% |\n",
                  encoding="utf-8")
    try:
        parsed = parse_adapter.parse(md)
    finally:
        md.unlink()
    t = next(e.table for e in parsed.elements if e.table)
    assert t.header_source() == "parser"
    assert t.col_header_of(1) == "1년 미만"
    assert t.row_header_of(1) == "중도해지수수료"


def test_fact_from_a_table_carries_its_axes():
    """값이 표를 떠나도 `무엇의 값인지` 가 남아야 한다 (§3.2 좌표)."""
    g = _glossary(**{"중도해지수수료": {"kind": ["fact"], "value_type": "percent"}})
    table = Table(n_rows=2, n_cols=2, cells=[
        Cell("구분", 0, 0, is_col_header=True), Cell("1년 미만", 0, 1, is_col_header=True),
        Cell("중도해지수수료", 1, 0, is_row_header=True), Cell("0.7%", 1, 1)])
    doc = structurize.run(_parsed([_el(0, "제1조(수수료)"), _el(1, table=table, type="table")]),
                          _fmt(), g)
    f = doc.find_fact("중도해지수수료")
    assert f is not None
    assert f.source["cell"] == [1, 0]
    assert f.source["col_header"] == "구분"
    assert f.source["header_source"] == "parser"


# ===========================================================================
# 입구 방어 — 못 읽는 파일은 **이름을 대고** 거부한다
# ===========================================================================

def _encrypted_pdf(path: Path) -> Path:
    fitz = pytest.importorskip("fitz")
    d = fitz.open()
    d.new_page().insert_text((72, 72), "제1조(신탁의 목적) " * 30)
    d.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256,
           user_pw="secret", owner_pw="secret")
    d.close()
    return path


def test_encrypted_pdf_is_refused_by_name(tmp_path):
    """암호화 PDF 는 fitz 내부 예외('document closed or encrypted')로 터지면 안 된다.

    그 메시지는 원인을 말하지 않아 사용자가 우리 코드의 버그로 읽는다(§00 게이트).
    """
    p = _encrypted_pdf(tmp_path / "enc.pdf")
    with pytest.raises(parse_adapter.EncryptedDocument, match="비밀번호/DRM"):
        parse_adapter.parse(p)


def test_encrypted_pdf_is_not_mistaken_for_a_scan(tmp_path):
    """암호화 PDF 는 텍스트가 0자로 보인다 — 그대로 두면 스캔본으로 오판해 OCR 이 켜진다."""
    p = _encrypted_pdf(tmp_path / "enc.pdf")
    with pytest.raises(parse_adapter.EncryptedDocument):
        parse_adapter.is_born_digital(p)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp949", "euc-kr"])
def test_korean_text_reads_in_common_encodings(tmp_path, encoding):
    """한국어 문서는 cp949/euc-kr 로 오는 일이 흔하다 — utf-8 고정이면 원문이 멀쩡한데
    파이프라인이 죽는다."""
    p = tmp_path / "t.txt"
    p.write_bytes("제1조(신탁의 목적) 한글 본문".encode(encoding))
    assert parse_adapter.decode_text(p) == "제1조(신탁의 목적) 한글 본문"
    assert parse_adapter.parse(p).elements[0].text == "제1조(신탁의 목적) 한글 본문"


def test_undecodable_file_is_refused_not_mangled(tmp_path):
    """`errors='replace'` 로 흘려보내면 깨진 글자가 게이트를 통과해 **틀린 줄 모르는
    판정**이 나간다. 못 읽으면 못 읽었다고 말한다."""
    p = tmp_path / "t.txt"
    p.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(parse_adapter.UndecodableText, match="인코딩을 알 수 없습니다"):
        parse_adapter.parse(p)


def test_utf8_is_not_hijacked_by_a_lenient_encoding(tmp_path):
    """후보 순서가 안전장치다 — cp949 는 거의 모든 바이트열을 받으므로 utf-8 보다
    먼저 오면 멀쩡한 utf-8 원문을 조용히 깨뜨린다."""
    p = tmp_path / "t.txt"
    p.write_bytes("특정금전신탁 계약서 — 제1조".encode("utf-8"))
    assert parse_adapter.decode_text(p) == "특정금전신탁 계약서 — 제1조"


# ===========================================================================
# 잔여·미적중 제목 — "구조를 다 반영했는가"의 신호 (문서별 임계값 없음)
# ===========================================================================

def test_residual_is_the_default_section_mass():
    """마커를 지나기 전 내용이 잔여로 잡힌다 — 형식이 설명하지 못한 질량."""
    elements = [_el(0, "표지 제목"), _el(1, "머리말 문장이다."),
                _el(2, "제1조(목적) 목적이다."), _el(3, "본문 문장이다.")]
    doc = structurize.run(_parsed(elements), _fmt(), _glossary())
    assert doc.residual == [0, 1]          # 마커(2)와 그 내용(3)은 설명된 것


def test_marker_elements_are_not_residual():
    """문서가 마커로 시작하면 잔여가 없다 — ensure_default 가 기본 구역을 열 때
    마커 요소 자신이 잔여로 새면 안 된다(구역을 열었으니 설명된 것이다)."""
    elements = [_el(0, "제1조(목적) 내용이다."), _el(1, "본문이다.")]
    doc = structurize.run(_parsed(elements), _fmt(), _glossary())
    assert doc.residual == []


def test_unmatched_heading_in_marker_section_is_recorded():
    """마커 구역 안의 제목상 요소 — 마커를 놓쳐 그 아래 내용이 앞 구역에 붙는
    **조용한 오배정**을 보는 유일한 창이다. 파서의 문서 무관 라벨만 쓴다."""
    elements = [_el(0, "제1조(목적) 내용이다."),
                _el(1, "부칙", type="section_header"),      # 형식에 없는 구역 제목
                _el(2, "부칙 내용이다.")]
    doc = structurize.run(_parsed(elements), _fmt(), _glossary())
    assert [h["index"] for h in doc.unmatched_headings] == [1]
    assert doc.unmatched_headings[0]["landed_in"] == "본문/제1조"


def test_default_section_heading_is_not_double_reported():
    """기본 구역에 담긴 제목은 잔여로 이미 셌다 — 같은 요소를 두 경고로 알리지 않는다."""
    elements = [_el(0, "표지 제목", type="section_header"),
                _el(1, "제1조(목적) 내용이다.")]
    doc = structurize.run(_parsed(elements), _fmt(), _glossary())
    assert doc.residual == [0]
    assert doc.unmatched_headings == []


def test_furniture_heading_is_not_a_missed_marker():
    """쪽마다 반복되는 머리말은 신호가 아니라 소음이다."""
    elements = [_el(0, "제1조(목적) 내용이다."),
                _el(1, "회사명 내부문서", type="page_header")]
    doc = structurize.run(_parsed(elements), _fmt(), _glossary())
    assert doc.unmatched_headings == []


def test_gate_scores_unexplained_mass():
    """기본 구역에 쌓인 질량이 점수를 깎는다 — 비율 기반이라 문서 종류·크기와
    무관하게 성립한다(죽어 있던 residual 지표의 교체)."""
    front = [_el(i, f"설명되지 않는 문장 {i}이다.") for i in range(8)]
    tail = [_el(8, "제1조(목적) 내용이다."), _el(9, "본문이다.")]
    doc = structurize.run(_parsed(front + tail), _fmt(), _glossary())
    fit = fitness_gate.score(doc, _fmt(), 10)
    assert fit.detail["parts"]["residual"] == pytest.approx(1 - 8 / 10, abs=0.01)
    assert any("설명하지 못한" in w for w in fit.warnings)


def test_small_front_matter_does_not_warn():
    """표지 몇 줄은 어느 문서에나 있다 — 그때마다 경고하면 소음이 된다."""
    elements = [_el(0, "표지")] + [_el(i, f"제{i}조(목적{i}) 내용이다.")
                                   for i in range(1, 12)]
    doc = structurize.run(_parsed(elements), _fmt(), _glossary())
    fit = fitness_gate.score(doc, _fmt(), 12)
    assert len(doc.residual) == 1
    assert not any("설명하지 못한" in w for w in fit.warnings)


def test_gate_warns_on_unmatched_headings():
    elements = [_el(0, "제1조(목적) 내용이다."),
                _el(1, "부칙", type="section_header")]
    doc = structurize.run(_parsed(elements), _fmt(), _glossary())
    fit = fitness_gate.score(doc, _fmt(), 2)
    assert any("제목으로 보이는데" in w for w in fit.warnings)


# ===========================================================================
# 검수 payload — 형식이 못 먹은 자리를 사람에게 (오추출 방어 3)
# ===========================================================================

def test_review_payload_carries_the_unexplained(tmp_path):
    """잔여·미적중 제목이 페이지·텍스트와 함께 실린다 — 격리 문서 진단의 재료."""
    from core import review

    md = tmp_path / "t.md"
    md.write_text("표지 문장이다.\n\n제1조(목적) 내용이다.\n\n# 부칙\n\n부칙 내용.\n",
                  encoding="utf-8")
    parsed = parse_adapter.parse(md)
    g = _glossary()
    doc = structurize.run(parsed, _fmt(), g)
    fit = fitness_gate.apply(doc, _fmt(), len(parsed.elements))

    class _R:                                  # router.Routed 의 최소 형태
        pass
    r = _R()
    r.doc, r.parsed, r.fitness = doc, parsed, fit
    r.doc_type, r.quarantined = "테스트", not fit.passed

    p = review.payload(r)
    kinds = {it["kind"] for it in p["items"]}
    assert "residual" in kinds and "unmatched_heading" in kinds
    heading = next(it for it in p["items"] if it["kind"] == "unmatched_heading")
    assert heading["text"] == "부칙" and heading["landed_in"] == "본문/제1조"
    assert p["pages"] == {}                    # md — 페이지 크기 없음, bbox 없이 동작


def test_norm_bbox_flips_bottomleft_to_topleft():
    """PDF prov(BOTTOMLEFT)를 화면 좌표(0~1, TOPLEFT)로 — 렌더 배율 무관."""
    from core.review import norm_bbox

    # 100x200 페이지에서 아래에서 150~180 높이의 상자 = 위에서 20~50
    box = norm_bbox([10, 180, 90, 150], "BOTTOMLEFT", (100, 200))
    assert box == {"l": 0.1, "t": 0.1, "r": 0.9, "b": 0.25}
    assert norm_bbox([10, 20, 90, 40], "TOPLEFT", (100, 200)) == \
           {"l": 0.1, "t": 0.1, "r": 0.9, "b": 0.2}
    assert norm_bbox([10, 20, 90, 40], "TOPLEFT", None) is None   # 크기 모름 → 정규화 안 함
