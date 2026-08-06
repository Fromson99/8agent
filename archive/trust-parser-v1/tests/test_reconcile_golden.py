"""§B11 — Part B 완료 기준 골든 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import comparators as cmp   # noqa: E402
import ontology             # noqa: E402
import reconcile            # noqa: E402

PAIR = ROOT / "data" / "golden_pairs" / "acct_001"


@pytest.fixture(scope="module")
def onto():
    return ontology.load(ontology.default_path(ROOT))


@pytest.fixture(scope="module")
def report(onto):
    return reconcile.run(PAIR / "contract.chunks.json", PAIR / "summary.md", onto)


@pytest.fixture(scope="module")
def expected():
    return json.loads((PAIR / "expected.reconcile.json").read_text(encoding="utf-8"))


# ===========================================================================
# 값 비교기 (§B7) — 단위 테스트
# ===========================================================================

@pytest.mark.parametrize("a,b", [
    ("금 일억원정 (₩ 100,000,000)", "100,000,000원"),   # §B11-3 포맷 차이
    ("1억원", "100,000,000"),
    ("1억 5천만원", "150,000,000원"),
])
def test_number_format_differences_match(a, b):
    assert cmp.compare("number", a, b).verdict == "MATCH"


def test_number_real_difference_is_caught():
    assert cmp.compare("number", "100,000,000원", "90,000,000원").verdict == "VALUE_MISMATCH"


def test_number_does_not_double_count_dual_notation():
    """`금 일억원정 (₩100,000,000)` 은 1억이지 2억이 아니다 — 실측 오류."""
    assert cmp.parse_number("금 일억원정 (₩ 100,000,000)") == 100_000_000


@pytest.mark.parametrize("a,b", [
    ("2024년 6월 3일부터 2027년 6월 2일까지", "24.6.3 ~ 27.6.2"),
    ("2024.07.01 ~ 2027.06.02", "2024.7.1 ~ 2027.6.2"),
])
def test_date_range_format_differences_match(a, b):
    assert cmp.compare("date_range", a, b).verdict == "MATCH"


def test_percent_format_differences_match():
    assert cmp.compare("percent", "연 1.5%", "1.50%").verdict == "MATCH"
    assert cmp.compare("percent", "(15)%", "15.00%").verdict == "MATCH"


def test_account_ignores_separators():
    assert cmp.compare("account_no", "123-45-678901", "12345678901").verdict == "MATCH"


def test_option_set_is_order_independent():
    a = [{"no": 1, "label": "채무증권", "checked": True},
         {"no": 3, "label": "수익증권", "checked": True},
         {"no": 2, "label": "지분증권", "checked": False}]
    assert cmp.compare("option_set", a, "수익증권, 채무증권").verdict == "MATCH"


def test_option_set_detects_missing_and_extra():
    a = [{"no": 1, "label": "채무증권", "checked": True}]
    r = cmp.compare("option_set", a, "수익증권")
    assert r.verdict == "VALUE_MISMATCH" and "계약서에만" in r.note


def test_range_tiers_detects_rate_difference():
    a = "1년 미만 해지신탁금의 0.5%\n1년 이상 2년 미만 해지신탁금의 0.3%"
    b = "1년 미만 해지신탁금의 0.5%\n1년 이상 2년 미만 해지신탁금의 0.2%"
    assert cmp.compare("range_tiers", a, b).verdict == "VALUE_MISMATCH"


def test_unparseable_goes_to_review_not_pass():
    """§B3-3 — 애매하면 auto-pass/fail 하지 않고 보류한다."""
    assert cmp.compare("percent", "기타특약사항에 기재", "연 0.8%").verdict == "NEEDS_REVIEW"


# ===========================================================================
# §B11 완료 기준
# ===========================================================================

def test_b11_1_every_field_has_exactly_one_row(report, onto):
    """별지1의 모든 필드가 정확히 한 행씩. 조용한 스킵 금지."""
    names = [r.field_name for r in report.rows]
    assert len(names) == len(set(names)), "중복 행이 있습니다"
    assert set(names) == set(onto.fields), \
        f"누락: {set(onto.fields)-set(names)} / 초과: {set(names)-set(onto.fields)}"


def test_b11_2_direction_is_contract_as_truth(report):
    """판정은 계약서 기준. 계약서에 값이 없으면 대조 기준이 없으므로 보류다."""
    for r in report.rows:
        if r.verdict in ("VALUE_MISMATCH", "MISSING_IN_SUMMARY"):
            assert r.contract_value, f"{r.field_name}: 계약서 값 없이 요약서를 틀렸다고 했습니다"


def test_b11_3_format_differences_are_match(report):
    got = {r.field_name: r.verdict for r in report.rows}
    for f in ("신탁금액", "신탁기간", "수익보수", "계좌번호"):
        assert got[f] == "MATCH", f"{f} 가 포맷 차이로 불일치 처리됐습니다: {got[f]}"


def test_b11_4_real_mismatches_are_caught(report):
    got = {r.field_name: r.verdict for r in report.rows}
    assert got["지급주기"] == "VALUE_MISMATCH"
    assert got["중도해지수수료"] == "VALUE_MISMATCH"
    assert got["운용내역 통지여부"] == "MISSING_IN_SUMMARY"
    assert got["지급계좌"] == "MISSING_IN_SUMMARY"


def test_b11_6_provenance_present(report):
    for r in report.rows:
        if r.contract_value:
            assert r.contract_source is not None, f"{r.field_name}: 계약서 출처 없음"


def test_b11_7_matches_expected_verdicts(report, expected):
    exp = {r["field_name"]: r["verdict"] for r in expected["rows"]}
    got = {r.field_name: r.verdict for r in report.rows}
    diffs = {k: (v, got.get(k)) for k, v in exp.items() if got.get(k) != v}
    assert not diffs, f"기대와 다른 판정: {diffs}"
    assert report.stats == expected["stats"]


def test_unmapped_is_distinct_from_missing(report):
    """UNMAPPED(이름 못 찾음) 와 MISSING(값 없음) 은 조치가 다르므로 구분해야 한다."""
    got = {r.field_name: r.verdict for r in report.rows}
    assert got["세부 운용지시"] == "UNMAPPED"
    assert got["지급계좌"] == "MISSING_IN_SUMMARY"


def test_alias_addition_resolves_unmapped(onto, tmp_path):
    """§B6 — 코드 수정 없이 별칭만 추가하면 UNMAPPED 가 해소돼야 한다."""
    onto.fields["세부 운용지시"].aliases = ["투자전략"]
    rep = reconcile.run(PAIR / "contract.chunks.json", PAIR / "summary.md", onto)
    got = {r.field_name: r.verdict for r in rep.rows}
    assert got["세부 운용지시"] != "UNMAPPED", "별칭을 추가해도 매핑되지 않았습니다"


def test_derived_field_is_consistency_not_equality(report):
    """§B7 — 파생값은 '동일'이 아니라 '계산상 일관'으로 판정하고 계산식을 남긴다."""
    row = next(r for r in report.rows if r.field_name == "만기일")
    assert row.verdict == "MATCH"
    assert "계산" in row.note
