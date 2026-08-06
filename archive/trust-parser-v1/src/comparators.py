"""T11. value_type 별 비교기 (SPEC §B7).

**최종 판정은 코드 결정론이다** (§B3-3, §B11-5). LLM 은 여기 관여하지 않는다.
자릿수 누락·환각 위험 때문이며, 애매하면 auto-pass/fail 하지 않고 NEEDS_REVIEW 로 뺀다.

정규식을 쓰지 않는다. 값 파싱에 정규식을 쓰면 무너진다는 것이 실측으로 확인됐다
(dataset 9종: 금액 파서 오탐 80%, 「소득세법」 제14조의 '조'를 4조원으로 읽음).
여기서는 문자 단위 스캔으로 파싱하고, 파싱 실패는 None 을 내 NEEDS_REVIEW 로 흐르게 한다.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

MATCH, MISMATCH, REVIEW = "MATCH", "VALUE_MISMATCH", "NEEDS_REVIEW"

# 한국어 수 단위
_UNITS = {"조": Decimal(10) ** 12, "억": Decimal(10) ** 8,
          "만": Decimal(10) ** 4, "천": Decimal(10) ** 3}
_KO_DIGITS = {"영": 0, "일": 1, "이": 2, "삼": 3, "사": 4,
              "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_STRIP = set(" \t\xa0,₩\\원정()（）[]")


@dataclass
class Result:
    verdict: str
    note: str = ""


# ---------------------------------------------------------------------------
# 파서 — 문자 스캔 (정규식 없음)
# ---------------------------------------------------------------------------

def parse_number(raw: str) -> Optional[Decimal]:
    """`금 일억원정 (₩100,000,000)` / `100,000,000원` / `1억 5천만원` → Decimal.

    같은 금액을 한글과 아라비아로 **두 번** 적는 서식이 흔하다(`금 일억원정 (₩100,000,000)`).
    두 표기를 더하면 2억이 된다 — 실측에서 실제로 났던 오류다.
    그래서 아라비아 표기(콤마 포함 3자리 이상)가 있으면 그것만 쓴다.
    """
    if raw is None:
        return None
    s = str(raw)
    plain = _plain_amount(s)
    if plain is not None:
        return plain
    # 한국어 수사는 중첩된다: "5천만" = 5 × 1000 × 10000.
    # 작은 단위(천·백·십)는 그룹 안에서 더하고, 큰 단위(만·억·조)를 만나면 그룹 전체에 곱한다.
    _SMALL = {"천": 1000, "백": 100, "십": 10}
    total, group, digits, saw = Decimal(0), Decimal(0), "", False

    def take() -> Decimal:
        nonlocal digits
        v = Decimal(digits) if digits else Decimal(0)
        digits = ""
        return v

    for ch in s:
        if ch.isdigit():
            digits += ch
            saw = True
        elif ch in _KO_DIGITS:
            digits += str(_KO_DIGITS[ch])
            saw = True
        elif ch in _SMALL:
            n = take() or Decimal(1)
            group += n * _SMALL[ch]
            saw = True
        elif ch in _UNITS:
            n = take()
            group += n
            if group == 0:
                group = Decimal(1)          # "억원" = 1억
            total += group * _UNITS[ch]
            group = Decimal(0)
            saw = True
        elif ch in _STRIP or ch.isspace():
            continue
        else:
            group += take()
    total += group + take()
    return total if saw else None


def _plain_amount(s: str) -> Optional[Decimal]:
    """콤마가 들어간 아라비아 금액이 있으면 그 값. 없으면 None."""
    best: Optional[Decimal] = None
    digits, has_comma = "", False
    for ch in list(s) + [" "]:
        if ch.isdigit():
            digits += ch
        elif ch == "," and digits:
            has_comma = True
        else:
            if digits and has_comma and len(digits) >= 4:
                v = Decimal(digits)
                best = v if best is None or v > best else best
            digits, has_comma = "", False
    return best


def parse_percent(raw: str) -> Optional[Decimal]:
    """`연 1.5%` / `1.50%` / `1.5` → Decimal('1.5')."""
    if raw is None:
        return None
    digits, seen_dot, out = "", False, None
    for ch in str(raw):
        if ch.isdigit():
            digits += ch
        elif ch == "." and digits and not seen_dot:
            digits += ch
            seen_dot = True
        elif digits:
            break
    if not digits:
        return None
    try:
        out = Decimal(digits)
    except InvalidOperation:
        return None
    return out


def parse_percents(raw: str) -> list[Decimal]:
    """문자열 안의 **모든** 비율을 등장 순서대로.

    `(연 3%)를 초과하는 이익 × (15)%` → [3, 15].
    성과보수처럼 기준수익률과 요율이 한 문장에 같이 오는 값은
    앞의 하나만 보면 뒤의 요율이 바뀌어도 못 잡는다(T19 변이 perf_fee_rate).
    """
    if raw is None:
        return []
    s = str(raw)
    out: list[Decimal] = []
    for i, ch in enumerate(s):
        if ch != "%":
            continue
        j, digits = i - 1, ""
        while j >= 0 and s[j] in " \t)）":      # `(15)%` 처럼 닫는 괄호를 건너뛴다
            j -= 1
        while j >= 0 and (s[j].isdigit() or s[j] == "."):
            digits = s[j] + digits
            j -= 1
        digits = digits.strip(".")
        if digits:
            try:
                out.append(Decimal(digits))
            except InvalidOperation:
                pass
    return out


def parse_date(raw: str) -> Optional[date]:
    """`24년 1월 1일` / `2024-01-01` / `24.6.3` / `2024.07.01` → date."""
    if raw is None:
        return None
    nums, cur = [], ""
    for ch in str(raw):
        if ch.isdigit():
            cur += ch
        else:
            if cur:
                nums.append(cur)
                cur = ""
    if cur:
        nums.append(cur)
    if len(nums) < 3:
        return None
    y, m, d = nums[0], nums[1], nums[2]
    try:
        yi = int(y)
        if len(y) == 2:
            yi += 2000
        return date(yi, int(m), int(d))
    except (ValueError, TypeError):
        return None


def parse_date_range(raw: str) -> Optional[tuple[Optional[date], Optional[date]]]:
    """`2024년 6월 3일부터 2027년 6월 2일까지` / `24.6.3 ~ 27.6.2`."""
    if raw is None:
        return None
    nums, cur = [], ""
    for ch in str(raw):
        if ch.isdigit():
            cur += ch
        else:
            if cur:
                nums.append(cur)
                cur = ""
    if cur:
        nums.append(cur)
    if len(nums) < 6:
        return None
    return _mk(nums[0:3]), _mk(nums[3:6])


def _mk(parts: list[str]) -> Optional[date]:
    try:
        y = int(parts[0])
        if len(parts[0]) == 2:
            y += 2000
        return date(y, int(parts[1]), int(parts[2]))
    except (ValueError, TypeError, IndexError):
        return None


def parse_account(raw: str) -> Optional[str]:
    if raw is None:
        return None
    s = "".join(ch for ch in str(raw) if ch.isdigit())
    return s or None


def normalize_text(raw: str) -> str:
    if raw is None:
        return ""
    out = []
    for ch in unicodedata.normalize("NFKC", str(raw)):
        if unicodedata.category(ch)[0] in ("L", "N"):
            out.append(ch)
    return "".join(out).casefold()


def parse_option_set(raw: Any) -> Optional[set[str]]:
    """체크된 항목의 집합. list[dict] (options) 또는 쉼표 구분 문자열을 받는다."""
    if raw is None:
        return None
    if isinstance(raw, (list, tuple, set)):
        out = set()
        for x in raw:
            if isinstance(x, dict):
                if x.get("checked"):
                    out.add(normalize_text(x.get("label", "")))
            elif hasattr(x, "checked") and hasattr(x, "label"):
                if getattr(x, "checked"):      # pydantic Option 객체
                    out.add(normalize_text(getattr(x, "label")))
            else:
                out.add(normalize_text(str(x)))
        return {o for o in out if o}
    parts = str(raw).replace("·", ",").replace("/", ",").split(",")
    return {normalize_text(p) for p in parts if normalize_text(p)}


def parse_range_tiers(raw: Any) -> Optional[list[tuple[str, Decimal]]]:
    """다단 조건 → [(구간 정규형, 요율)]. 순서 무관 집합 비교용."""
    if raw is None:
        return None
    lines = raw if isinstance(raw, (list, tuple)) else str(raw).split("\n")
    tiers: list[tuple[str, Decimal]] = []
    for line in lines:
        s = str(line)
        rate = parse_percent(_after_last(s, "의")) if "의" in s else None
        if rate is None:
            rate = _last_percent(s)
        if rate is None:
            continue
        cond = normalize_text(_before_last(s, "해지신탁금") or s)
        tiers.append((cond, rate))
    return tiers or None


def _last_percent(s: str) -> Optional[Decimal]:
    idx = s.rfind("%")
    if idx < 0:
        return None
    j, digits = idx - 1, ""
    while j >= 0 and (s[j].isdigit() or s[j] == "."):
        digits = s[j] + digits
        j -= 1
    try:
        return Decimal(digits) if digits else None
    except InvalidOperation:
        return None


def _after_last(s: str, sep: str) -> str:
    i = s.rfind(sep)
    return s[i + len(sep):] if i >= 0 else s


def _before_last(s: str, sep: str) -> str:
    i = s.rfind(sep)
    return s[:i] if i >= 0 else s


# ---------------------------------------------------------------------------
# 비교기
# ---------------------------------------------------------------------------

def cmp_number(a: Any, b: Any) -> Result:
    x, y = parse_number(a), parse_number(b)
    if x is None or y is None:
        return Result(REVIEW, "금액을 파싱하지 못했습니다")
    return Result(MATCH, f"{x:,}") if x == y else Result(MISMATCH, f"{x:,} vs {y:,}")


def cmp_percent(a: Any, b: Any) -> Result:
    xs, ys = parse_percents(a), parse_percents(b)
    if xs and ys:
        # 한 값 안에 비율이 여럿이면(성과보수 = 기준수익률 + 요율) 전부 일치해야 한다
        if xs == ys:
            return Result(MATCH, "%, ".join(str(v) for v in xs) + "%")
        fmt = lambda vs: "/".join(f"{v}%" for v in vs)
        return Result(MISMATCH, f"{fmt(xs)} vs {fmt(ys)}")
    x, y = parse_percent(a), parse_percent(b)      # `%` 기호 없이 숫자만 온 경우
    if x is None or y is None:
        return Result(REVIEW, "비율을 파싱하지 못했습니다")
    return Result(MATCH, f"{x}%") if x == y else Result(MISMATCH, f"{x}% vs {y}%")


def cmp_date(a: Any, b: Any) -> Result:
    x, y = parse_date(a), parse_date(b)
    if x is None or y is None:
        return Result(REVIEW, "날짜를 파싱하지 못했습니다")
    return Result(MATCH, f"{x}") if x == y else Result(MISMATCH, f"{x} vs {y}")


def cmp_date_range(a: Any, b: Any) -> Result:
    x, y = parse_date_range(a), parse_date_range(b)
    if not x or not y:
        return Result(REVIEW, "기간을 파싱하지 못했습니다")
    if None in x or None in y:
        return Result(REVIEW, "기간의 한쪽 끝점을 파싱하지 못했습니다")
    if x == y:
        return Result(MATCH, f"{x[0]} ~ {x[1]}")
    diffs = []
    if x[0] != y[0]:
        diffs.append(f"시작 {x[0]} vs {y[0]}")
    if x[1] != y[1]:
        diffs.append(f"종료 {x[1]} vs {y[1]}")
    return Result(MISMATCH, " / ".join(diffs))


def cmp_account(a: Any, b: Any) -> Result:
    x, y = parse_account(a), parse_account(b)
    if x is None or y is None:
        return Result(REVIEW, "계좌번호를 파싱하지 못했습니다")
    return Result(MATCH, x) if x == y else Result(MISMATCH, f"{x} vs {y}")


def cmp_option_set(a: Any, b: Any) -> Result:
    x, y = parse_option_set(a), parse_option_set(b)
    if x is None or y is None:
        return Result(REVIEW, "선택 항목을 파싱하지 못했습니다")
    if not x and not y:
        return Result(REVIEW, "양쪽 모두 선택 항목이 비어 있습니다")
    if x == y:
        return Result(MATCH, f"{len(x)}개 일치")
    only_a, only_b = sorted(x - y), sorted(y - x)
    return Result(MISMATCH,
                  f"계약서에만 {only_a or '없음'} / 요약서에만 {only_b or '없음'}")


def cmp_range_tiers(a: Any, b: Any) -> Result:
    x, y = parse_range_tiers(a), parse_range_tiers(b)
    if not x or not y:
        return Result(REVIEW, "다단 조건을 파싱하지 못했습니다")
    sx, sy = sorted(x), sorted(y)
    if sx == sy:
        return Result(MATCH, f"{len(sx)}구간 일치")
    rates_x = sorted(r for _, r in x)
    rates_y = sorted(r for _, r in y)
    if rates_x != rates_y:
        return Result(MISMATCH, f"요율이 다릅니다: {rates_x} vs {rates_y}")
    return Result(MISMATCH, f"구간 구성이 다릅니다 ({len(x)} vs {len(y)})")


def cmp_text(a: Any, b: Any) -> Result:
    x, y = normalize_text(a), normalize_text(b)
    if not x or not y:
        return Result(REVIEW, "서술 값이 비어 있습니다")
    return Result(MATCH, "문자열 동일") if x == y else Result(MISMATCH, "서술이 다릅니다")


COMPARATORS = {
    "number": cmp_number,
    "percent": cmp_percent,
    "date": cmp_date,
    "date_range": cmp_date_range,
    "account_no": cmp_account,
    "option_set": cmp_option_set,
    "range_tiers": cmp_range_tiers,
    "text": cmp_text,
}

PARSERS = {
    "number": parse_number,
    "percent": parse_percent,
    "date": parse_date,
    "date_range": parse_date_range,
    "account_no": parse_account,
    "option_set": parse_option_set,
    "range_tiers": parse_range_tiers,
    "text": normalize_text,
}


def compare(value_type: str, contract: Any, summary: Any) -> Result:
    fn = COMPARATORS.get(value_type)
    if fn is None:
        return Result(REVIEW, f"알 수 없는 value_type '{value_type}'")
    return fn(contract, summary)
