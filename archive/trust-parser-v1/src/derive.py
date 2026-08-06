"""파생 필드 계산기 — 온톨로지 `fields.*.derived` 식을 **실제로 해석한다** (SPEC §B7 말미, §C6).

파생 필드는 계약서에 값이 없고 계산으로만 존재한다(만기일 = 신탁기간.end).
그래서 판정이 '동일'이 아니라 '계산상 일관'이고, 근거 계산식을 리포트에 남긴다.

## 이 모듈이 따로 있는 이유

식은 온톨로지에 있는데 코드가 그 식을 읽지 않으면, 식은 주석으로 전락한다.
`신탁기간.end` 를 `.start` 로 바꿔도 같은 답이 나오면 계산 규칙은 파일이 아니라
코드에 있는 것이고, 그건 §C8 완료기준 1("어떤 제약도 코드에 하드코딩돼 있지 않다")의 위반이다.
계산이 reconcile 과 fact_query 두 곳에 각각 있으면 조용히 갈라지기도 한다.
그래서 해석기를 하나로 두고 양쪽이 여기를 통과하게 한다.

## 문법 (최소)

    expr := term (('+' | '-') term)*
    term := <필드명>[.<접근자>]  |  <기간 리터럴>        # 3년 / 6개월 / 30일 / 2주

접근자는 **값 타입이 정한다**(`ACCESSORS`). 타입에 없는 접근자는 실패로 만든다 —
조용히 다른 끝점을 돌려주는 것이 고치려는 버그 그 자체다.

정규식은 쓰지 않는다(§ comparators 머리말과 같은 이유). 문자 스캔으로 파싱하고
실패는 None 이 아니라 **이유가 붙은 실패**로 올려 NEEDS_REVIEW 로 흐르게 한다.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field as dc_field
from datetime import date
from decimal import Decimal
from typing import Any, Mapping, Optional

import comparators as cmp


# 접근자 별칭 — 온톨로지를 한국어로도 영어로도 쓸 수 있게 한다.
_ATTR_ALIAS = {
    "start": "start", "시작": "start", "시작일": "start", "개시일": "start",
    "end": "end", "종료": "end", "종료일": "end", "만기": "end", "만기일": "end",
    "duration": "duration", "기간": "duration", "존속기간": "duration",
}

# value_type 별 허용 접근자. 빈 튜플 = 접근자 없이 값 자체를 쓴다.
ACCESSORS: dict[str, tuple[str, ...]] = {
    "date_range": ("start", "end", "duration"),
    "date": (),
    "number": (),
    "percent": (),
    "account_no": (),
    "text": (),
    "option_set": (),
    "range_tiers": (),
}

# 기간 리터럴 단위. '개월' 을 '월' 보다 먼저 봐야 한다(최장 일치).
_DUR_UNITS: list[tuple[str, str, int]] = [
    ("개월", "months", 1), ("년", "months", 12), ("월", "months", 1),
    ("달", "months", 1), ("주", "days", 7), ("일", "days", 1),
]


@dataclass(frozen=True)
class Duration:
    """달과 일을 분리해 담는다 — 달 산술은 일수 환산이 불가능하기 때문이다(2월 28/29일)."""
    months: int = 0
    days: int = 0

    def __str__(self) -> str:
        parts = []
        if self.months:
            parts.append(f"{self.months}개월")
        if self.days:
            parts.append(f"{self.days}일")
        return " ".join(parts) or "0일"

    def negated(self) -> "Duration":
        return Duration(-self.months, -self.days)


@dataclass
class DeriveResult:
    """계산 결과 + 감사 추적. 실패도 값 없이 **이유를 담아** 돌려준다(§B3-3 조용한 판정 금지)."""
    value: Any = None
    ok: bool = False
    reason: str = ""
    explain: str = ""                                   # "신탁기간.end = 2027-06-02"
    basis: list[str] = dc_field(default_factory=list)   # 참조한 필드 — 출처 인용에 쓴다


def referenced_fields(expr: Optional[str]) -> list[str]:
    """식이 참조하는 필드명. 온톨로지 무결성 검사와 출처 인용이 쓴다."""
    out: list[str] = []
    for _, token in _split_terms(expr) or []:
        name = token.split(".", 1)[0].strip()
        if name and parse_duration(token) is None and name not in out:
            out.append(name)
    return out


def check(expr: Optional[str], fields: Mapping[str, Any]) -> list[str]:
    """식을 값 없이 정적으로 검사한다 — 온톨로지 로드 시점에 오타를 잡기 위해서다.

    반환은 문제 문자열 목록(빈 목록 = 이상 없음).
    """
    problems: list[str] = []
    terms = _split_terms(expr)
    if terms is None:
        return [f"파생식을 이해하지 못했습니다: '{expr}'"]
    for _, token in terms:
        if parse_duration(token) is not None:
            continue
        name, _, attr = token.partition(".")
        name, attr = name.strip(), attr.strip()
        spec = fields.get(name)
        if spec is None:
            problems.append(f"파생식이 없는 필드 '{name}' 을 참조합니다")
            continue
        vt = getattr(spec, "value_type", "text")
        allowed = ACCESSORS.get(vt)
        if allowed is None:
            problems.append(f"'{name}' 의 value_type '{vt}' 에 대한 접근자 정의가 없습니다")
            continue
        canon = _ATTR_ALIAS.get(attr, attr) if attr else ""
        if attr and canon not in allowed:
            problems.append(
                f"'{name}.{attr}' — value_type '{vt}' 에 없는 접근자입니다"
                f" (가능: {', '.join(allowed) or '없음'})")
        elif not attr and allowed:
            problems.append(
                f"'{name}' 은 접근자가 필요합니다 (가능: {', '.join(allowed)})")
    return problems


def evaluate(expr: Optional[str], fields: Mapping[str, Any],
             raws: Mapping[str, Any]) -> DeriveResult:
    """식을 계산한다.

    fields  온톨로지의 `fields` (필요한 건 `.value_type` 뿐 — 순환 import 를 피해 덕타이핑)
    raws    필드명 → 계약서에서 뽑은 원문 문자열
    """
    terms = _split_terms(expr)
    if not terms:
        return DeriveResult(reason=f"파생식을 이해하지 못했습니다: '{expr}'")

    total: Any = None
    shown: list[str] = []
    basis: list[str] = []

    for op, token in terms:
        term = _term_value(token, fields, raws)
        if not term.ok:
            return term
        for b in term.basis:
            if b not in basis:
                basis.append(b)
        shown.append(term.explain if op == "+" and not shown else f"{op} {term.explain}")
        if total is None:
            total = term.value if op == "+" else _negate(term.value)
            if total is None:
                return DeriveResult(reason=f"'{token}' 앞의 부호를 적용할 수 없습니다")
            continue
        total = _combine(total, term.value, op)
        if total is None:
            return DeriveResult(
                reason=f"'{' '.join(shown)}' 를 계산할 수 없습니다 — 타입이 맞지 않습니다")

    return DeriveResult(value=total, ok=True, basis=basis,
                        explain=f"{' '.join(shown)} = {_fmt(total)}")


# ---------------------------------------------------------------------------
# 항 해석
# ---------------------------------------------------------------------------

def _term_value(token: str, fields: Mapping[str, Any],
                raws: Mapping[str, Any]) -> DeriveResult:
    lit = parse_duration(token)
    if lit is not None:
        return DeriveResult(value=lit, ok=True, explain=token.strip())

    name, _, attr = token.partition(".")
    name, attr = name.strip(), attr.strip()
    spec = fields.get(name)
    if spec is None:
        return DeriveResult(reason=f"파생식이 참조한 '{name}' 이 온톨로지에 없습니다")

    raw = raws.get(name)
    if raw is None or not str(raw).strip():
        return DeriveResult(reason=f"파생 근거 '{name}' 의 값을 찾지 못했습니다")

    vt = getattr(spec, "value_type", "text")
    allowed = ACCESSORS.get(vt)
    if allowed is None:
        return DeriveResult(reason=f"'{name}' 의 value_type '{vt}' 를 계산에 쓸 수 없습니다")

    canon = _ATTR_ALIAS.get(attr, attr) if attr else ""
    if attr and canon not in allowed:
        return DeriveResult(
            reason=f"'{name}.{attr}' — value_type '{vt}' 에 없는 접근자입니다"
                   f" (가능: {', '.join(allowed) or '없음'})")
    if not attr and allowed:
        return DeriveResult(
            reason=f"'{name}' 은 접근자가 필요합니다 (가능: {', '.join(allowed)})")

    parsed = cmp.PARSERS.get(vt, lambda x: x)(raw)
    if parsed is None:
        return DeriveResult(reason=f"'{name}' 의 값을 {vt} 로 파싱하지 못했습니다: {raw!r}")

    value = _access(vt, parsed, canon)
    if value is None:
        return DeriveResult(reason=f"'{token}' 을 값에서 꺼내지 못했습니다: {raw!r}")
    return DeriveResult(value=value, ok=True, basis=[name],
                        explain=f"{token.strip()}")


def _access(value_type: str, parsed: Any, attr: str) -> Any:
    if value_type != "date_range":
        return parsed
    start, end = (parsed if isinstance(parsed, (tuple, list)) and len(parsed) == 2
                  else (None, None))
    if attr == "start":
        return start
    if attr == "end":
        return end
    if attr == "duration":
        if start is None or end is None:
            return None
        # 일수로 담는다 — start + duration 이 정확히 end 로 되돌아온다.
        return Duration(days=(end - start).days)
    return None


# ---------------------------------------------------------------------------
# 산술
# ---------------------------------------------------------------------------

def _combine(a: Any, b: Any, op: str) -> Any:
    if op == "-":
        if isinstance(a, date) and isinstance(b, date):
            return Duration(days=(a - b).days)
        b = _negate(b)
        if b is None:
            return None
    if isinstance(a, date) and isinstance(b, Duration):
        return _shift(a, b)
    if isinstance(a, Duration) and isinstance(b, date):
        return _shift(b, a)
    if isinstance(a, Duration) and isinstance(b, Duration):
        return Duration(a.months + b.months, a.days + b.days)
    if isinstance(a, Decimal) and isinstance(b, Decimal):
        return a + b
    return None


def _negate(v: Any) -> Any:
    if isinstance(v, Duration):
        return v.negated()
    if isinstance(v, Decimal):
        return -v
    return None                    # 날짜에는 단항 부호를 붙일 수 없다


def _shift(d: date, dur: Duration) -> date:
    """달을 먼저 옮기고 일을 더한다. 말일은 그 달의 마지막 날로 자른다(1/31 + 1개월 = 2/28)."""
    total = d.month - 1 + dur.months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    out = date(year, month, day)
    return out + _days(dur.days)


def _days(n: int):
    from datetime import timedelta
    return timedelta(days=n)


def _fmt(v: Any) -> str:
    if isinstance(v, Decimal):
        return f"{v:,}"
    return str(v)


# ---------------------------------------------------------------------------
# 토크나이저 — 문자 스캔 (정규식 없음)
# ---------------------------------------------------------------------------

def _split_terms(expr: Optional[str]) -> Optional[list[tuple[str, str]]]:
    """`a.end + 3년 - 1일` → [('+','a.end'), ('+','3년'), ('-','1일')].

    필드명에 '-' 가 들어갈 수 있으므로 **공백으로 둘러싸인** 부호만 연산자로 본다.
    """
    if not expr or not str(expr).strip():
        return None
    s = str(expr).strip()
    terms: list[tuple[str, str]] = []
    op, buf = "+", ""
    i = 0
    while i < len(s):
        ch = s[i]
        is_op = (ch in "+-"
                 and (i == 0 or s[i - 1].isspace())
                 and i + 1 < len(s) and s[i + 1].isspace())
        if is_op:
            if not buf.strip():
                return None                     # 연산자가 연달아 나왔다
            terms.append((op, buf.strip()))
            op, buf = ch, ""
            i += 1
            continue
        buf += ch
        i += 1
    if not buf.strip():
        return None
    terms.append((op, buf.strip()))
    return terms


def parse_duration(token: str) -> Optional[Duration]:
    """`3년` / `6개월` / `30일` / `1년 6개월` → Duration. 아니면 None(= 필드 참조)."""
    s = (token or "").strip()
    if not s:
        return None
    months = days = 0
    digits, saw = "", False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isdigit():
            digits += ch
            i += 1
            continue
        if ch.isspace():
            i += 1
            continue
        unit = next((u for u, _, _ in _DUR_UNITS if s.startswith(u, i)), None)
        if unit is None or not digits:
            return None                         # 숫자+단위 형태가 아니다 → 필드명
        kind, mult = next((k, m) for u, k, m in _DUR_UNITS if u == unit)
        n = int(digits)
        digits = ""
        if kind == "months":
            months += n * mult
        else:
            days += n * mult
        saw = True
        i += len(unit)
    if digits or not saw:
        return None
    return Duration(months, days)
