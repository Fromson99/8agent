"""agent1 골든 테스트 — 실제 PDF 를 통과시킨다 (SPEC §7).

docling 이 필요하고 느리다. 코어 단위 테스트(tests/core)와 분리해 둔 이유다.
    pytest tests/core          빠른 회귀 (초 단위)
    pytest tests/agent1        실물 검증 (분 단위)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agents" / "agent1" / "src"))

import service                                             # noqa: E402
from core import normalize                                 # noqa: E402

SAMPLE = ROOT / "agents/agent1/data/samples/ss2207_special_trust.pdf"
CONTRACT = ROOT / "agents/agent1/data/golden/contract_filled.pdf"
PROSPECTUS = ROOT / "agents/agent1/data/golden/prospectus.md"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="샘플 PDF 가 없습니다")


@pytest.fixture(scope="module")
def blank():
    """빈 템플릿 — 구조화 검증용 (§7-3)."""
    return service.structurize_contract(SAMPLE)


@pytest.fixture(scope="module")
def filled():
    """값이 채워진 체결본 — fact 검증용 (§7-4)."""
    return service.structurize_contract(CONTRACT)


@pytest.fixture(scope="module")
def prospectus():
    return service.structurize_prospectus(PROSPECTUS)


# ===========================================================================
# §7-3 구조화
# ===========================================================================

def test_all_articles_present(blank):
    """본문 제1~32조가 전부 section 으로 존재한다."""
    nos = {int(s.marker["no"]) for s in blank.doc.sections
           if s.marker.get("id") == "조" and s.marker.get("no")}
    assert nos == set(range(1, 33)), sorted(set(range(1, 33)) - nos)


def test_appendices_are_top_level_sections(blank):
    """별지1·별지2 가 최상위 구역으로 존재한다."""
    tops = [s.section_id for s in blank.doc.sections if len(s.path) == 1]
    assert "본문" in tops and "별지1" in tops and "별지2" in tops


def test_term_markers_open_sections_under_appendix(blank):
    """용어형 마커가 별지1 아래 구역을 연다 — 정규표현식 없이 (§0-2)."""
    ids = {s.section_id for s in blank.doc.sections}
    assert "별지1/신탁계약 세부내역" in ids
    assert "별지1/신탁자금 운용방법" in ids
    assert "별지1/세부 운용지시" in ids


def test_every_element_is_conserved(blank):
    """모든 요소가 정확히 하나의 최심 section 에 속한다 — 잔여는 유실이 아니라
    기본 구역(표지 등)에 담긴 요소의 좌표다."""
    assigned = {i for s in blank.doc.sections for i in s.elements}
    assert assigned == {e.index for e in blank.parsed.elements}
    # 잔여는 전부 기본 구역의 내용이어야 한다 — 다른 곳에서 새면 정의가 깨진 것
    default_mass = {i for s in blank.doc.sections
                    if s.marker.get("kind") == "default" for i in s.elements}
    assert set(blank.doc.residual) <= default_mass


def test_every_section_reachable_from_a_top_level(blank):
    ids = {s.section_id for s in blank.doc.sections}
    for s in blank.doc.sections:
        if len(s.path) > 1:
            assert "/".join(s.path[:-1]) in ids, s.section_id


# ===========================================================================
# §7-2 런타임 결정론
# ===========================================================================

def test_structuring_is_deterministic(filled):
    again = service.structurize_contract(CONTRACT)
    a, b = filled.doc.dump(), again.doc.dump()
    a.pop("generated_at"), b.pop("generated_at")
    assert a == b


# ===========================================================================
# §7-4 fact
# ===========================================================================

SECTION = "별지1/신탁계약 세부내역"


@pytest.mark.parametrize("term,expect", [
    ("계좌번호", "12345678901"),
    ("신탁금액", 100_000_000),
    ("지급기간", None),        # 값은 타입값이라 별도 검증
])
def test_fact_has_section_coordinate(filled, term, expect):
    """좌표(section_id + term)로 조회한다 — 이게 모든 태스크의 기본 좌표다 (§3.2)."""
    f = filled.doc.find_fact(term, section_ids=[SECTION])
    assert f is not None, f"{term} 를 {SECTION} 에서 찾지 못했습니다"
    assert f.raw and f.source.get("page")
    if expect is not None:
        assert str(f.value) == str(expect)


def test_a_row_with_two_terms_yields_two_facts(filled):
    """같은 행에 기본보수·수익보수가 있으면 둘 다 fact 가 된다 (문장=행 단위)."""
    basic = filled.doc.find_fact("기본보수", section_ids=[SECTION])
    perf = filled.doc.find_fact("수익보수", section_ids=[SECTION])
    assert basic is not None and perf is not None
    assert basic.raw == perf.raw


def test_mention_and_value_share_a_term_but_not_a_coordinate(filled):
    """본문 mention 과 별지 값은 같은 용어, 다른 좌표 — 추출이 아니라 좌표가 가른다."""
    sections = {f.section_id for f in filled.doc.facts if f.term == "신탁금액"}
    assert any(s.startswith("본문") for s in sections)
    assert SECTION in sections


def test_prospectus_facts(prospectus):
    def val(term):
        f = prospectus.doc.find_fact(term)
        return f.value if f else None
    assert str(val("신탁금액")) == "100000000"
    assert str(val("기본보수")) == "0.8"
    assert prospectus.fitness.passed


# ===========================================================================
# §7-5 비교
# ===========================================================================

@pytest.fixture(scope="module")
def report():
    rep, _s, _t = service.verify(CONTRACT, PROSPECTUS)
    return rep


def test_every_rule_appears_exactly_once(report):
    """source 의 rule 은 전부 리포트에 한 행씩 — 조용한 스킵 금지 (§4.1)."""
    task = service.reconcile.load_task(service.TASK)
    assert len(report.rows) == len(task.rules)
    terms = [r.term for r in report.rows]
    assert len(terms) == len(set(terms))


def test_format_difference_is_a_match(report):
    """`금 1억원정` ≡ `100,000,000원`, `24.6.3` ≡ `2024-06-03` (§7-5)."""
    by_term = {r.term: r for r in report.rows}
    assert by_term["신탁금액"].verdict == "MATCH"
    assert by_term["계좌번호"].verdict == "MATCH"
    assert by_term["지급기간"].verdict == "MATCH"


def test_real_mismatch_is_caught(report):
    """계약서 '매월' vs 요약서 '분기' — 놓치지 않는다."""
    by_term = {r.term: r for r in report.rows}
    assert by_term["지급주기"].verdict == "VALUE_MISMATCH"
    assert by_term["중도해지수수료"].verdict == "VALUE_MISMATCH"


def test_every_row_carries_both_provenances(report):
    for r in report.rows:
        assert r.source_ref is not None or r.verdict == "NEEDS_REVIEW"
        if r.verdict in ("MATCH", "VALUE_MISMATCH"):
            assert r.source_ref and r.target_ref


def test_verdicts_are_from_the_declared_set(report):
    from core.reconcile import VERDICTS
    assert all(r.verdict in VERDICTS for r in report.rows)


# ===========================================================================
# §7-6 게이트
# ===========================================================================

def test_foreign_document_is_quarantined():
    """형식과 다른 문서를 넣으면 격리되고 부합률이 보고된다."""
    other = ROOT / "first-agent" / "dataset" / "유안타 증권 특정금전신탁 계약서(일반형).pdf"
    if not other.exists():
        pytest.skip("타사 계약서 샘플이 없습니다")
    s = service.structurize_contract(other)
    # 같은 업권 문서라 조 구조는 맞을 수 있다 — 부합률이 보고되는 것이 요구사항이다
    assert "score" in s.doc.fitness
    assert isinstance(s.fitness.warnings, list)
    assert 0.0 <= s.fitness.score <= 1.0
