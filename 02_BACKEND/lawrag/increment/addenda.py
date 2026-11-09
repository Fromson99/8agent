"""마지막 부칙의 시행일 조문에서 문서·조문별 시행일을 읽는다.

부칙이 여러 개면 마지막 부칙만 이번 개정의 시행일 근거로 쓴다.
읽는 형태
- `이 법(영·규칙·고시·규정…)은 공포한 날부터 시행한다.`
- `… YYYY년 M월 D일부터 시행한다.`
- `공포 후 N개월(년·일)이 경과한 날부터` — 초일 불산입: 공포일 + 기간 + 1일.
  실측 대조: 자본시장법 제21324호(공포 2026.2.3) “공포 후 6개월이 경과한 날” →
  시행일 기준 조회본 시행일자 20260804.
- `다만, 제50조제1항 단서의 개정규정은 …부터 시행하고, 제166조의 개정규정은 …`
  처럼 조문별 예외. `제N조부터 제M조까지`는 범위로 편다.
- `다음 각 호(목)의 개정규정은 …` 뒤의 번호 항목은 앞 날짜를 잇거나 자기 날짜를 쓴다.

읽지 못한 예외 문장은 unparsed에 남겨 게이트가 ‘시행일 판독 불가’로 경고하게 한다.
다른 법률을 가리키는 인용(「…」·부칙 제N조)은 이 문서 조문 예외로 쓰지 않는다.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from .normalize import ARTICLE_REF, citations, normalize_text

_WHEN = (r"(공포한\s*날|공포\s*후\s*\d+\s*(?:개월|년|일)이\s*경과한\s*날|"
         r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일|발령한\s*날)")
_MAIN = re.compile(r"이\s*(?:법|영|규칙|고시|규정|훈령|예규|세칙|시행령|시행규칙|지침|기준)"
                   r"(?:은|는)\s*" + _WHEN + r"\s*부터\s*시행")
_EXCEPTION = re.compile(r"(?P<targets>[^.]*?)개정규정(?:은|는|:)?\s*" + _WHEN + r"\s*부터\s*시행")
_ITEM_DATE = re.compile(r"개정규정\s*[:：]\s*" + _WHEN)
_RANGE = re.compile(r"제\s*(\d+)\s*조(?:의\s*\d+)?\s*부터\s*제\s*(\d+)\s*조(?:의\s*\d+)?\s*까지")
_FIRST_ARTICLE_END = re.compile(r"\n\s*제\s*2\s*조\s*\(")
_ITEM_HEAD = re.compile(r"^\s*(?:\d+\.|[가-하]\.)\s*")
_INHERIT = re.compile(r"다음\s*각\s*(?:호|목)의\s*개정규정(?:은|는)\s*" + _WHEN + r"\s*부터")
_OWN_DATE_LIST = re.compile(r"다음\s*각\s*(?:호|목)의\s*개정규정(?:은|는)\s*해당\s*(?:호|목)에서\s*정하는\s*날")


@dataclass
class Schedule:
    default: str = ""                                 # 문서 기본 시행일 YYYYMMDD
    per_article: dict[str, str] = field(default_factory=dict)
    unparsed: list[str] = field(default_factory=list)
    source_key: str = ""
    foreign: str = ""          # 타법개정 부칙 — `부칙(정부조직법)`처럼 다른 법의 부칙이면 그 이름


def _ymd(value: date) -> str:
    return value.strftime("%Y%m%d")


def _parse_ymd(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def add_months(start: date, months: int) -> date:
    month = start.month - 1 + months
    year = start.year + month // 12
    month = month % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def resolve_when(expression: str, promulgated: str) -> str:
    text = re.sub(r"\s+", "", expression)
    if text in ("공포한날", "발령한날"):
        return promulgated
    if (m := re.fullmatch(r"(\d{4})년(\d{1,2})월(\d{1,2})일", text)):
        return f"{int(m[1]):04d}{int(m[2]):02d}{int(m[3]):02d}"
    if (m := re.fullmatch(r"공포후(\d+)(개월|년|일)이경과한날", text)) and len(promulgated) == 8:
        base = _parse_ymd(promulgated)
        n = int(m[1])
        if m[2] == "개월":
            end = add_months(base, n)
        elif m[2] == "년":
            end = add_months(base, 12 * n)
        else:
            end = base + timedelta(days=n)
        return _ymd(end + timedelta(days=1))
    return ""


def _targets(segment: str) -> list[str]:
    segment = normalize_text(segment)
    keys: list[str] = []
    for m in _RANGE.finditer(segment):
        low, high = int(m[1]), int(m[2])
        if 0 < low <= high and high - low <= 300:
            keys.extend(str(n) for n in range(low, high + 1))
    ranged = _RANGE.sub(" ", segment)
    for cite in citations(ranged, skip_own_heading=False):
        if not cite.external:
            keys.append(cite.key)
    seen: list[str] = []
    for key in keys:
        if key not in seen:
            seen.append(key)
    return seen


def read_schedule(text: str, promulgated: str, *, source_key: str = "") -> Schedule:
    schedule = Schedule(source_key=source_key)
    if not text:
        return schedule
    end = _FIRST_ARTICLE_END.search(text)
    first = text[:end.start()] if end else text
    flat = normalize_text(first)
    main = _MAIN.search(flat)
    if main:
        schedule.default = resolve_when(main.group(1), promulgated)
        if not schedule.default:
            schedule.unparsed.append(main.group(0))
    lines = [line.strip() for line in first.splitlines() if line.strip()]
    inherited = ""
    own_dates = False
    for line in lines:
        line_flat = normalize_text(line)
        if (m := _INHERIT.search(line_flat)):
            inherited = resolve_when(m.group(1), promulgated)
            own_dates = False
            continue                          # 머리 문장 — 대상은 다음 항목들에 있다
        if _OWN_DATE_LIST.search(line_flat):
            inherited, own_dates = "", True
        if _ITEM_HEAD.match(line_flat) and (inherited or own_dates):
            item = _ITEM_HEAD.sub("", line_flat)
            when = ""
            if (m := _ITEM_DATE.search(item)):
                when = resolve_when(m.group(1), promulgated)
                item = item[:m.start()]
            when = when or inherited
            keys = _targets(item)
            if keys and when:
                for key in keys:
                    schedule.per_article.setdefault(key, when)
            elif "개정규정" in item:
                schedule.unparsed.append(line_flat[:300])
            continue
        for m in _EXCEPTION.finditer(line_flat):
            targets = m.group("targets")
            if "다음 각" in targets:
                continue
            when = resolve_when(m.group(2), promulgated)
            keys = _targets(targets)
            if keys and when:
                for key in keys:
                    schedule.per_article.setdefault(key, when)
            elif ARTICLE_REF.search(targets) and not keys:
                continue                      # 다른 법률·부칙 조문 — 이 문서 예외 아님
            elif "다만" in targets or keys:
                schedule.unparsed.append(normalize_text(m.group(0))[:300])
    return schedule


_FOREIGN_HEAD = re.compile(r"^\s*부칙\s*\(([^)]+)\)")


def schedule_for(snapshot) -> Schedule:
    last = snapshot.last_addendum
    if last is None:
        return Schedule(default=snapshot.effective)
    head = _FOREIGN_HEAD.match(last.text)
    if head and normalize_text(head.group(1)).replace(" ", "") != normalize_text(snapshot.name).replace(" ", ""):
        # 다른 법의 부칙: 그 안의 제N조는 그 법의 조문이다 (실측: 금융회사의 지배구조에 관한 법률
        # 제21065호 = 부칙(정부조직법), 실제 개정은 그 부칙 제7조 <602>의 제26조 문구 교체).
        return Schedule(default=snapshot.effective, source_key=last.key, foreign=head.group(1))
    schedule = read_schedule(last.text, last.promulgated or snapshot.promulgated, source_key=last.key)
    if not schedule.default:
        schedule.default = snapshot.effective
    return schedule

