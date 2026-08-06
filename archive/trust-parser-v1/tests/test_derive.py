"""파생식 해석기 — 계산 규칙이 코드가 아니라 온톨로지에 있는지 검증한다 (§B7, §C6, §C8-1).

핵심 회귀: **식을 바꾸면 답이 바뀌어야 한다.** `신탁기간.end` 를 `.start` 로 고쳤는데
같은 값이 나오면, 그 식은 주석이고 계산은 코드에 박혀 있다는 뜻이다(고치기 전 상태가 그랬다).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import derive           # noqa: E402
import fact_query       # noqa: E402
import ontology         # noqa: E402
import reconcile        # noqa: E402
from schema import ChunkDocument   # noqa: E402

PAIR = ROOT / "data" / "golden_pairs" / "acct_001"
# 골든 쌍: 계약 신탁기간 2024-06-03 ~ 2027-06-02, 요약서 만기일 2027-06-02
START, END = date(2024, 6, 3), date(2027, 6, 2)


@pytest.fixture(scope="module")
def onto():
    return ontology.load(ontology.default_path(ROOT))


@pytest.fixture(scope="module")
def doc():
    return ChunkDocument.model_validate(
        json.loads((PAIR / "contract.chunks.json").read_text(encoding="utf-8")))


def _with(onto, expr):
    """만기일의 파생식만 바꾼 온톨로지 사본."""
    o = onto.model_copy(deep=True)
    o.fields["만기일"].derived = expr
    return o


def _query(onto, doc, expr):
    return fact_query.FactStore(doc, _with(onto, expr)).get("만기일")


def _row(onto, expr):
    rep = reconcile.run(PAIR / "contract.chunks.json", PAIR / "summary.md",
                        _with(onto, expr))
    return next(r for r in rep.rows if r.field_name == "만기일")


# ---------------------------------------------------------------------------
# 회귀 — 식이 실제로 해석되는가
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr,want", [
    ("신탁기간.end", END),
    ("신탁기간.start", START),          # ← 고치기 전에는 여기서도 END 가 나왔다
    ("신탁기간.종료일", END),            # 한국어 접근자 별칭
    ("신탁기간.시작일", START),
])
def test_accessor_decides_the_answer(onto, doc, expr, want):
    a = _query(onto, doc, expr)
    assert a.found and a.value == want, f"{expr} → {a.value} (기대 {want})"


def test_start_and_end_differ(onto, doc):
    """두 접근자가 같은 값을 내면 식이 무시되고 있는 것이다."""
    assert _query(onto, doc, "신탁기간.start").value != _query(onto, doc, "신탁기간.end").value


def test_spec_example_expression(onto, doc):
    """§C6 이 예시로 든 식 — start + duration 은 end 로 정확히 되돌아와야 한다."""
    a = _query(onto, doc, "신탁기간.start + 신탁기간.duration")
    assert a.found and a.value == END


@pytest.mark.parametrize("expr,want", [
    ("신탁기간.start + 3년", date(2027, 6, 3)),
    ("신탁기간.start + 2년 11개월 30일", END),
    ("신탁기간.end - 1일", date(2027, 6, 1)),
    ("신탁기간.start + 6개월", date(2024, 12, 3)),
])
def test_duration_literals(onto, doc, expr, want):
    a = _query(onto, doc, expr)
    assert a.found and a.value == want, f"{expr} → {a.value}"


def test_month_shift_clamps_to_month_end():
    """1/31 + 1개월 = 2/28. 달 산술을 일수로 환산하면 틀린다."""
    assert derive._shift(date(2024, 1, 31), derive.Duration(months=1)) == date(2024, 2, 29)
    assert derive._shift(date(2023, 1, 31), derive.Duration(months=1)) == date(2023, 2, 28)


# ---------------------------------------------------------------------------
# 실패는 조용하지 않아야 한다 (§B3-3)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr,fragment", [
    ("신탁기간.middle", "없는 접근자"),
    ("신탁기간", "접근자가 필요"),
    ("없는필드.end", "온톨로지에 없습니다"),
    ("신탁금액.end", "없는 접근자"),       # number 에는 접근자가 없다
])
def test_bad_expression_fails_loudly(onto, doc, expr, fragment):
    a = _query(onto, doc, expr)
    assert not a.found, f"{expr} 가 조용히 값을 냈습니다: {a.value}"
    assert fragment in a.note, a.note
    row = _row(onto, expr)
    assert row.verdict == "NEEDS_REVIEW" and fragment in row.note


def test_ontology_rejects_bad_derived_at_load(onto, tmp_path):
    """오타는 런타임이 아니라 로드 시점에 잡는다."""
    import yaml
    data = yaml.safe_load(ontology.default_path(ROOT).read_text(encoding="utf-8"))
    data["fields"]["만기일"]["derived"] = "신탁기간.middle"
    p = tmp_path / "broken.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="derived"):
        ontology.load(p)


# ---------------------------------------------------------------------------
# 대사 — 파생 필드는 '동일'이 아니라 '계산상 일관'으로 판정한다 (§B7)
# ---------------------------------------------------------------------------

def test_reconcile_follows_the_formula(onto):
    assert _row(onto, "신탁기간.end").verdict == "MATCH"
    off = _row(onto, "신탁기간.start")
    assert off.verdict == "VALUE_MISMATCH" and "계산상 불일치" in off.note
    assert "신탁기간.start" in off.note, "리포트에 계산식이 남아야 한다"


def test_reconcile_and_query_agree(onto, doc):
    """같은 식을 두 소비자가 따로 계산하면 조용히 갈라진다 — 실제로 갈라져 있었다."""
    for expr in ("신탁기간.end", "신탁기간.start", "신탁기간.start + 1년"):
        assert str(_query(onto, doc, expr).value) in _row(onto, expr).note, expr


# ---------------------------------------------------------------------------
# 토크나이저
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token,want", [
    ("3년", derive.Duration(months=36)),
    ("6개월", derive.Duration(months=6)),
    ("30일", derive.Duration(days=30)),
    ("2주", derive.Duration(days=14)),
    ("1년 6개월", derive.Duration(months=18)),
    ("신탁기간", None),          # 필드명은 기간 리터럴이 아니다
    ("3", None),
    ("", None),
])
def test_parse_duration(token, want):
    assert derive.parse_duration(token) == want


def test_referenced_fields():
    assert derive.referenced_fields("신탁기간.start + 3년") == ["신탁기간"]
    assert derive.referenced_fields("신탁금액 - 신탁기간.end") == ["신탁금액", "신탁기간"]
