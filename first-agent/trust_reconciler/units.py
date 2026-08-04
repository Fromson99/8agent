"""값 비교 — 구조화된 값만 다룬다. 문자열을 파싱하지 않는다.

## 역할 분담

    추출(문자 → 구조)   LLM     "연 0.5%"  → {"value": 0.5, "per_annum": true}
    비교(구조 → 판정)   이 모듈  두 dict 를 놓고 match / mismatch / uncertain

정규식으로 문자열을 파싱하던 자리를 전부 LLM 으로 옮긴 이유는 실측 때문이다.
금액 파서는 dataset 9종에서 442건 중 356건(80%)이 오탐이었다 —
"「소득세법」 제14조제3항제6호" 의 '조' 를 4조원(4,000,000,000,000)으로 읽는 식이다.
LLM 은 이 문맥을 틀리지 않는다. 반대로 "36개월 == 3년" 같은 판정은 코드가 해야
재현 가능하고 감사할 수 있다. 그 경계가 이 모듈이다.

## 판정은 3값이다

    match      확실히 같다
    mismatch   확실히 다르다
    uncertain  코드로는 판정할 수 없다 → 호출부가 LLM 에 넘기거나 사람에게 올린다

금융 도메인에서는 틀린 확신보다 정직한 uncertain 이 낫다. 애매하면 uncertain 을 낸다.
"""

from __future__ import annotations

from typing import Any, Optional

from .textkit import fold

MATCH, MISMATCH, UNCERTAIN = "match", "mismatch", "uncertain"
Verdict = tuple[str, str]        # (판정, 사유)


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _close(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


# ---------------------------------------------------------------------------
# 타입별 정규형 — LLM 이 준 dict 를 비교 가능한 형태로
# ---------------------------------------------------------------------------

def total_months(data: dict) -> Optional[float]:
    """기간을 개월로 환산. {"years":3} 과 {"months":36} 이 같아진다."""
    if not data:
        return None
    y, m, d = _num(data.get("years")), _num(data.get("months")), _num(data.get("days"))
    if y is None and m is None and d is None:
        return None
    total = (y or 0) * 12 + (m or 0)
    if d:
        total += d / 30.0        # 일 단위는 근사다 — 그래서 아래에서 일수는 따로 본다
    return total


def _duration_verdict(a: dict, b: dict) -> Verdict:
    # 둘 다 일(日)로만 표현되어 있으면 일수끼리 정확히 본다
    da, db = _num(a.get("days")), _num(b.get("days"))
    only_days_a = da is not None and not a.get("years") and not a.get("months")
    only_days_b = db is not None and not b.get("years") and not b.get("months")
    if only_days_a and only_days_b:
        return (MATCH, f"기간 동일: {da:g}일") if _close(da, db) \
            else (MISMATCH, f"기간 불일치: {da:g}일 vs {db:g}일")

    ma, mb = total_months(a), total_months(b)
    if ma is None or mb is None:
        return UNCERTAIN, "기간 값이 비어 있음"
    if _close(ma, mb, 1e-6):
        return MATCH, f"기간 동일: {ma:g}개월 (= {ma/12:g}년)"
    return MISMATCH, f"기간 불일치: {ma:g}개월 vs {mb:g}개월"


def _percent_verdict(a: dict, b: dict) -> Verdict:
    va, vb = _num(a.get("value")), _num(b.get("value"))
    if va is None or vb is None:
        return UNCERTAIN, "비율 값이 비어 있음"
    if not _close(va, vb):
        return MISMATCH, f"비율 불일치: {va:g}% vs {vb:g}%"
    pa, pb = a.get("per_annum"), b.get("per_annum")
    if pa is None or pb is None:
        return UNCERTAIN, f"값은 {va:g}% 로 같으나 한쪽의 연환산 여부가 불명"
    if pa != pb:
        # 숫자가 같아도 한쪽만 연율이면 실질이 다르다. 확정하지 않는다.
        return UNCERTAIN, f"값은 {va:g}% 로 같으나 연환산 표기가 다름 (연율 {pa} vs {pb})"
    return MATCH, f"비율 동일: {'연 ' if pa else ''}{va:g}%"


def _money_verdict(a: dict, b: dict) -> Verdict:
    aa, ab = _num(a.get("amount")), _num(b.get("amount"))
    if aa is None or ab is None:
        return UNCERTAIN, "금액 값이 비어 있음"
    ca = (a.get("currency") or "KRW").upper()
    cb = (b.get("currency") or "KRW").upper()
    if ca != cb:
        return MISMATCH, f"통화 불일치: {ca} vs {cb}"
    if _close(aa, ab):
        return MATCH, f"금액 동일: {aa:,.0f}{ca}"
    return MISMATCH, f"금액 불일치: {aa:,.0f} vs {ab:,.0f} ({ca})"


def _date_verdict(a: dict, b: dict) -> Verdict:
    ia, ib = a.get("iso"), b.get("iso")
    if not ia or not ib:
        return UNCERTAIN, "날짜 값이 비어 있음"
    return (MATCH, f"날짜 동일: {ia}") if ia == ib else (MISMATCH, f"날짜 불일치: {ia} vs {ib}")


def _boolean_verdict(a: dict, b: dict) -> Verdict:
    va, vb = a.get("value"), b.get("value")
    if not isinstance(va, bool) or not isinstance(vb, bool):
        return UNCERTAIN, "여부 값이 비어 있음"
    return (MATCH, f"여부 동일: {va}") if va == vb else (MISMATCH, f"여부 불일치: {va} vs {vb}")


def _duration_or_date_verdict(a: dict, b: dict) -> Verdict:
    """문서 한쪽은 기간("3년"), 다른 쪽은 만기일("2027-06-02")로 쓸 수 있다."""
    if total_months(a) is not None and total_months(b) is not None:
        return _duration_verdict(a, b)
    if a.get("iso") and b.get("iso"):
        return _date_verdict(a, b)
    if (total_months(a) is not None) != (total_months(b) is not None):
        return UNCERTAIN, "한쪽은 기간, 다른 쪽은 날짜로 기재되어 코드로는 대조 불가"
    return UNCERTAIN, "기간·날짜 값이 비어 있음"


def _enum_verdict(a: dict, b: dict, mapping: Optional[dict]) -> Verdict:
    """표기 체계가 다른 분류값(위험등급 등)은 mapping_table 로 통일해 비교한다."""
    ca, cb = a.get("code"), b.get("code")
    if mapping:
        ca = ca or _map_enum(a.get("raw"), mapping)
        cb = cb or _map_enum(b.get("raw"), mapping)
    if ca and cb:
        return (MATCH, f"표기 체계 매핑 후 동일: {ca}") if ca == cb \
            else (MISMATCH, f"분류 불일치: {ca} vs {cb} ('{a.get('raw')}' vs '{b.get('raw')}')")
    fa, fb = fold(a.get("raw")), fold(b.get("raw"))
    if fa and fa == fb:
        return MATCH, f"표기 동일: {a.get('raw')}"
    return UNCERTAIN, (f"매핑표에 없는 표기라 등가 여부를 확정할 수 없음 "
                       f"('{a.get('raw')}' vs '{b.get('raw')}')")


def _map_enum(raw: Optional[str], mapping: dict) -> Optional[str]:
    """매핑표 조회. 긴 표기부터 봐야 '매우높은위험'이 '높은위험'으로 잘못 잡히지 않는다."""
    f = fold(raw)
    if not f:
        return None
    for surface in sorted((k for k in mapping if not k.startswith("_")), key=len, reverse=True):
        s = fold(surface)
        if s and s in f:
            return mapping[surface]
    return None


def _formula_verdict(a: dict, b: dict) -> Verdict:
    """산식은 피연산자·연산자의 다중집합으로 비교한다.

    LLM 이 operands 를 이미 정규화된 이름으로 준다 ("해지원본" → "해지신탁원본").
    표현이 달라도 계산 결과가 같으면 같은 산식이다.
    """
    oa, ob = a.get("operands"), b.get("operands")
    if not oa or not ob:
        return UNCERTAIN, "산식 피연산자가 비어 있음"
    na = sorted(fold(x) for x in oa)
    nb = sorted(fold(x) for x in ob)
    pa = sorted(a.get("ops") or [])
    pb = sorted(b.get("ops") or [])
    if na == nb and pa == pb:
        return MATCH, f"산식 동일: {' '.join(oa)} / 연산자 {pa}"
    if na == nb:
        return UNCERTAIN, f"피연산자는 같으나 연산자가 다름: {pa} vs {pb}"
    only_a = [x for x in na if x not in nb]
    only_b = [x for x in nb if x not in na]
    return MISMATCH, (f"산식 구성 요소가 다름 — 계약서에만 {only_a or '없음'}, "
                      f"설명서에만 {only_b or '없음'}")


def _ref_verdict(a: dict, b: dict) -> Verdict:
    return UNCERTAIN, (f"양쪽 모두 참조 표기다 (계약서 '{a.get('target')}', "
                       f"설명서 '{b.get('target')}') — 참조를 따라가 실제 값을 다시 추출해야 함")


def _text_verdict(a: dict, b: dict) -> Verdict:
    ta, tb = a.get("text"), b.get("text")
    if not ta or not tb:
        return UNCERTAIN, "서술 값이 비어 있음"
    if fold(ta) == fold(tb):
        return MATCH, "서술 문구 동일"
    # 서술의 의미 동등성은 코드가 판단할 수 없다. 호출부가 LLM 에 넘긴다.
    return UNCERTAIN, "서술형 — 의미 동등성 판정 필요"


_HANDLERS = {
    "duration": lambda a, b, m: _duration_verdict(a, b),
    "percent": lambda a, b, m: _percent_verdict(a, b),
    "money": lambda a, b, m: _money_verdict(a, b),
    "date": lambda a, b, m: _date_verdict(a, b),
    "duration_or_date": lambda a, b, m: _duration_or_date_verdict(a, b),
    "boolean": lambda a, b, m: _boolean_verdict(a, b),
    "enum": _enum_verdict,
    "formula": lambda a, b, m: _formula_verdict(a, b),
    "ref": lambda a, b, m: _ref_verdict(a, b),
    "text": lambda a, b, m: _text_verdict(a, b),
}


def compare(value_type: str, a: dict, b: dict, mapping: Optional[dict] = None) -> Verdict:
    """구조화된 값 두 개를 비교한다. 알 수 없는 타입은 서술로 취급한다."""
    handler = _HANDLERS.get(value_type)
    if handler is None:
        return UNCERTAIN, f"알 수 없는 값 유형 '{value_type}' — 서술로 처리"
    return handler(a or {}, b or {}, mapping)


def needs_llm(verdict: str, value_type: str) -> bool:
    """코드가 판정을 못 냈고 LLM 이 도울 수 있는 경우인가."""
    return verdict == UNCERTAIN and value_type in ("text", "formula", "enum", "ref",
                                                   "duration_or_date")
