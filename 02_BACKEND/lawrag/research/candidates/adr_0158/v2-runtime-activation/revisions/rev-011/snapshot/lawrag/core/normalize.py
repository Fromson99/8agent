"""T8. 값 정규화 — fact 의 `value` 는 원문이 아니라 파싱된 타입값이다 (SPEC §3.3).

비교·계산은 항상 `value` 로, 표시·감사는 `raw`+`source` 로.
정규화 실패는 `value=None` + `needs_review=True` 로 남긴다 — **조용히 버리지 않는다**.

## 정규식을 쓰지 않는다

값 파싱에 정규식을 쓰면 무너진다는 것이 실측으로 확인됐다(dataset 9종:
금액 파서 오탐 80%, 「소득세법」 제14조의 '조'를 4조원으로 읽음). 문자 단위로 스캔한다.
구조 인식(제N조·①·N.)에만 정규식을 쓴다 — 거기서는 352건 매칭에 오탐 1건이었다.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

MATCH, MISMATCH, REVIEW = "MATCH", "VALUE_MISMATCH", "NEEDS_REVIEW"


def _is_digit(ch: str) -> bool:
    """아스키 숫자만. `'①'.isdigit()` 은 True 지만 `Decimal('①')` 은 터진다.

    원문자·한자 숫자도 Numeric_Type=Digit 이라 파이썬 `isdigit()` 을 통과한다.
    항 번호가 섞인 문장을 금액 파서에 넣었다가 실제로 크래시가 났다.
    """
    return ch.isascii() and ch.isdigit()

_UNITS = {"조": Decimal(10) ** 12, "억": Decimal(10) ** 8,
          "만": Decimal(10) ** 4, "천": Decimal(10) ** 3}
_SMALL = {"천": 1000, "백": 100, "십": 10}
_KO_DIGITS = {"영": 0, "일": 1, "이": 2, "삼": 3, "사": 4,
              "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_STRIP = set(" \t\xa0,₩\\원정()（）[]")


@dataclass
class Result:
    verdict: str
    note: str = ""


# ---------------------------------------------------------------------------
# 파서
# ---------------------------------------------------------------------------

def parse_number(raw: Any) -> Optional[Decimal]:
    """`금 일억원정 (₩100,000,000)` / `100,000,000원` / `1억 5천만원` → Decimal.

    같은 금액을 한글과 아라비아로 **두 번** 적는 서식이 흔하다. 두 표기를 더하면
    2억이 된다 — 실측에서 실제로 났던 오류다. 콤마 표기가 있으면 그것만 쓴다.
    """
    if raw is None:
        return None
    s = str(raw)
    plain = _plain_amount(s)
    if plain is not None:
        return plain
    # 한국어 수사는 중첩된다: "5천만" = 5 × 1000 × 10000.
    # 작은 단위(천·백·십)는 그룹 안에서 더하고, 큰 단위(만·억·조)에서 그룹째 곱한다.
    total, group, digits, saw = Decimal(0), Decimal(0), "", False
    saw_unit = False        # 수 단위(천·만·억·조)를 봤는가
    saw_arabic = False      # 아라비아 숫자를 봤는가

    def take() -> Decimal:
        nonlocal digits
        v = Decimal(digits) if digits else Decimal(0)
        digits = ""
        return v

    for ch in s:
        if _is_digit(ch):
            digits += ch
            saw = saw_arabic = True
        elif ch in _KO_DIGITS:
            digits += str(_KO_DIGITS[ch])
            saw = True
        elif ch in _SMALL:
            group += (take() or Decimal(1)) * _SMALL[ch]
            saw = saw_unit = True
        elif ch in _UNITS:
            group += take()
            if group == 0:
                group = Decimal(1)                 # "억원" = 1억
            total += group * _UNITS[ch]
            group = Decimal(0)
            saw = saw_unit = True
        elif ch in _STRIP or ch.isspace():
            continue
        else:
            group += take()
    total += group + take()
    # 한글 수사만 있고 단위가 없으면 숫자가 아니다.
    # "기타특약사항에 기재"의 '사'를 4 로, 「소득세법」 제14조의 '조'를 4조원으로 읽던
    # 실패가 여기서 났다 — 수사는 **단위와 함께일 때만** 수로 인정한다.
    if not saw or (not saw_arabic and not saw_unit):
        return None
    return total


def _plain_amount(s: str) -> Optional[Decimal]:
    """콤마가 들어간 아라비아 금액이 있으면 그 값(가장 큰 것). 없으면 None."""
    best: Optional[Decimal] = None
    digits, has_comma = "", False
    for ch in list(s) + [" "]:
        if _is_digit(ch):
            digits += ch
        elif ch == "," and digits:
            has_comma = True
        else:
            if digits and has_comma and len(digits) >= 4:
                v = Decimal(digits)
                best = v if best is None or v > best else best
            digits, has_comma = "", False
    return best


def parse_percent(raw: Any) -> Optional[Decimal]:
    """`연 1.5%` / `1.50%` / `1.5` → Decimal('1.5')."""
    if raw is None:
        return None
    digits, seen_dot = "", False
    for ch in str(raw):
        if _is_digit(ch):
            digits += ch
        elif ch == "." and digits and not seen_dot:
            digits += ch
            seen_dot = True
        elif digits:
            break
    if not digits:
        return None
    try:
        return Decimal(digits.strip("."))
    except InvalidOperation:
        return None


def parse_percents(raw: Any) -> list[Decimal]:
    """문자열 안의 **모든** 비율을 등장 순서대로.

    `(연 3%)를 초과하는 이익 × (15)%` → [3, 15].
    성과보수처럼 기준수익률과 요율이 한 문장에 오는 값은 앞의 하나만 보면
    뒤의 요율이 바뀌어도 못 잡는다(v1 변이 테스트가 잡아낸 구멍).
    """
    if raw is None:
        return []
    s = str(raw)
    out: list[Decimal] = []
    for i, ch in enumerate(s):
        if ch != "%":
            continue
        j, digits = i - 1, ""
        while j >= 0 and s[j] in " \t)）":            # `(15)%` 의 닫는 괄호를 건너뛴다
            j -= 1
        while j >= 0 and (_is_digit(s[j]) or s[j] == "."):
            digits = s[j] + digits
            j -= 1
        digits = digits.strip(".")
        if digits:
            try:
                out.append(Decimal(digits))
            except InvalidOperation:
                pass
    return out


def _numbers(raw: str) -> list[str]:
    nums, cur = [], ""
    for ch in str(raw):
        if _is_digit(ch):
            cur += ch
        elif cur:
            nums.append(cur)
            cur = ""
    if cur:
        nums.append(cur)
    return nums


def _mk_date(parts: list[str]) -> Optional[date]:
    try:
        y = int(parts[0])
        if len(parts[0]) == 2:
            y += 2000
        return date(y, int(parts[1]), int(parts[2]))
    except (ValueError, TypeError, IndexError):
        return None


def parse_date(raw: Any) -> Optional[date]:
    """`24년 1월 1일` / `2024-01-01` / `24.6.3` / `2024.07.01` → date."""
    if raw is None:
        return None
    nums = _numbers(raw)
    return _mk_date(nums[:3]) if len(nums) >= 3 else None


def parse_date_range(raw: Any) -> Optional[dict]:
    """`2024년 6월 3일부터 2027년 6월 2일까지` / `24.6.3 ~ 27.6.2` → {start, end}."""
    if raw is None:
        return None
    nums = _numbers(raw)
    if len(nums) < 6:
        return None
    start, end = _mk_date(nums[0:3]), _mk_date(nums[3:6])
    if start is None and end is None:
        return None
    return {"start": start, "end": end}


def parse_account(raw: Any) -> Optional[str]:
    """구분자(-) 제거 후 문자열."""
    if raw is None:
        return None
    s = "".join(ch for ch in str(raw) if _is_digit(ch))
    return s or None


def normalize_text(raw: Any) -> str:
    if raw is None:
        return ""
    out = []
    for ch in unicodedata.normalize("NFKC", str(raw)):
        if unicodedata.category(ch)[0] in ("L", "N"):
            out.append(ch)
    return "".join(out).casefold()


def parse_option_set(raw: Any) -> Optional[set[str]]:
    """체크된 항목의 집합. list[dict] 또는 쉼표 구분 문자열을 받는다."""
    if raw is None:
        return None
    if isinstance(raw, (list, tuple, set)):
        out = set()
        for x in raw:
            if isinstance(x, dict):
                if x.get("checked"):
                    out.add(normalize_text(x.get("label", "")))
            else:
                out.add(normalize_text(str(x)))
        return {o for o in out if o}
    parts = str(raw).replace("·", ",").replace("/", ",").replace("\n", ",").split(",")
    return {normalize_text(p) for p in parts if normalize_text(p)}


def parse_range_tiers(raw: Any) -> Optional[list[dict]]:
    """다단 조건 → [{cond, rate}]. 순서 무관 비교용."""
    if raw is None:
        return None
    lines = raw if isinstance(raw, (list, tuple)) else str(raw).split("\n")
    tiers: list[dict] = []
    for line in lines:
        s = str(line)
        rate = parse_percent(_after_last(s, "의")) if "의" in s else None
        if rate is None:
            rate = _last_percent(s)
        if rate is None:
            continue
        cond = normalize_text(_before_last(s, "해지신탁금") or s)
        tiers.append({"cond": cond, "rate": rate})
    return tiers or None


def _last_percent(s: str) -> Optional[Decimal]:
    idx = s.rfind("%")
    if idx < 0:
        return None
    j, digits = idx - 1, ""
    while j >= 0 and (_is_digit(s[j]) or s[j] == "."):
        digits = s[j] + digits
        j -= 1
    try:
        return Decimal(digits.strip(".")) if digits.strip(".") else None
    except InvalidOperation:
        return None


def _after_last(s: str, sep: str) -> str:
    i = s.rfind(sep)
    return s[i + len(sep):] if i >= 0 else s


def _before_last(s: str, sep: str) -> str:
    i = s.rfind(sep)
    return s[:i] if i >= 0 else s


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


def parse_value(value_type: str, raw: Any) -> Any:
    """value_type 에 맞는 파서로. 모르는 타입이면 원문 그대로."""
    fn = PARSERS.get(value_type)
    return fn(raw) if fn else raw


def to_jsonable(value: Any) -> Any:
    """JSON 직렬화용 — Decimal/date/set 을 문자열·리스트로."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return sorted(str(v) for v in value)
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# 비교기 (§4.1-3) — 판정은 코드 결정론. LLM 은 여기 관여하지 않는다.
# ---------------------------------------------------------------------------

def cmp_number(a: Any, b: Any) -> Result:
    x, y = parse_number(a), parse_number(b)
    if x is None or y is None:
        return Result(REVIEW, "금액을 파싱하지 못했습니다")
    return Result(MATCH, f"{x:,}") if x == y else Result(MISMATCH, f"{x:,} vs {y:,}")


def cmp_percent(a: Any, b: Any) -> Result:
    xs, ys = parse_percents(a), parse_percents(b)
    if xs and ys:
        if xs == ys:                                  # 한 값 안의 비율이 여럿이면 전부 일치해야
            return Result(MATCH, ", ".join(f"{v}%" for v in xs))
        fmt = lambda vs: "/".join(f"{v}%" for v in vs)
        return Result(MISMATCH, f"{fmt(xs)} vs {fmt(ys)}")
    x, y = parse_percent(a), parse_percent(b)
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
    if None in (x["start"], x["end"], y["start"], y["end"]):
        return Result(REVIEW, "기간의 한쪽 끝점을 파싱하지 못했습니다")
    if x == y:
        return Result(MATCH, f"{x['start']} ~ {x['end']}")
    diffs = []
    if x["start"] != y["start"]:
        diffs.append(f"시작 {x['start']} vs {y['start']}")
    if x["end"] != y["end"]:
        diffs.append(f"종료 {x['end']} vs {y['end']}")
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
    return Result(MISMATCH,
                  f"정답에만 {sorted(x - y) or '없음'} / 대상에만 {sorted(y - x) or '없음'}")


def cmp_range_tiers(a: Any, b: Any) -> Result:
    x, y = parse_range_tiers(a), parse_range_tiers(b)
    if not x or not y:
        return Result(REVIEW, "다단 조건을 파싱하지 못했습니다")
    key = lambda t: (t["cond"], t["rate"])
    if sorted(x, key=key) == sorted(y, key=key):
        return Result(MATCH, f"{len(x)}구간 일치")
    rx, ry = sorted(t["rate"] for t in x), sorted(t["rate"] for t in y)
    if rx != ry:
        return Result(MISMATCH, f"요율이 다릅니다: {rx} vs {ry}")
    return Result(MISMATCH, f"구간 구성이 다릅니다 ({len(x)} vs {len(y)})")


def cmp_text(a: Any, b: Any) -> Result:
    x, y = normalize_text(a), normalize_text(b)
    if not x or not y:
        return Result(REVIEW, "서술 값이 비어 있습니다")
    return Result(MATCH, "문자열 동일") if x == y else Result(MISMATCH, "서술이 다릅니다")


COMPARATORS = {
    "number": cmp_number, "percent": cmp_percent, "date": cmp_date,
    "date_range": cmp_date_range, "account_no": cmp_account,
    "option_set": cmp_option_set, "range_tiers": cmp_range_tiers, "text": cmp_text,
}


def compare(value_type: str, source: Any, target: Any) -> Result:
    fn = COMPARATORS.get(value_type)
    if fn is None:
        return Result(REVIEW, f"알 수 없는 value_type '{value_type}'")
    return fn(source, target)
