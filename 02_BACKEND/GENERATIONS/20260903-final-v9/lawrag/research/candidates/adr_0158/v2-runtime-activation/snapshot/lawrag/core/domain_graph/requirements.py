"""법령 원문에서 구성요건 qualifier의 근거 span을 보수적으로 표시한다.

의미를 새로 생성하지 않는다. 조건·예외·시간·수치·방법·효과를 나타내는 닫힌
표지와 그 표지가 속한 원문 절을 반환한다. 이 결과는 Concept 자동 승격이 아니라
Requirement 후보와 Evidence Auditor 입력을 위한 shadow 자료다.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


KINDS = ("CONDITION", "EXCEPTION", "TIME", "QUANTITY", "METHOD", "EFFECT")

_TRIGGERS = {
    "CONDITION": re.compile(r"경우|때에는|때에는|때|한하여|요건|요구되는|해당하면|해당하는"),
    "EXCEPTION": re.compile(r"다만|에도 불구하고|제외한다|제외되는|그러하지 아니하다|예외"),
    "METHOD": re.compile(r"서면|전자문서|전자우편|신고서|제출하여|제출해야|결의|승인|인가|통지|공시"),
    "EFFECT": re.compile(r"무효|취소|효력이|효력을|로 본다|으로 본다|간주|책임을 진다|과태료|벌금|처분할 수"),
}
_QUANTITY = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:퍼센트|%|원|만원|억원|조원|명|인|회|개|주|일|개월|년)"
    r"|\d+분의\s*\d+|100분의\s*\d+|과반수|3분의\s*2|3분의\s*1)"
)
_TIME = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:일|개월|년)\s*(?:이내|이상|이하|전|후|동안|경과)?"
    r"|기준일|시행일|영업일|과세기간|사업연도|회계연도|납입기일|제출기한)"
)
_BOUNDARY = re.compile(r"[\n。]|(?<=[다요])\.(?=\s|$)|(?<=한다)\.(?=\s|$)")


@dataclass(frozen=True)
class RequirementSpan:
    kind: str
    surface: str
    start: int
    end: int
    trigger: str
    trigger_start: int
    trigger_end: int

    def as_dict(self) -> dict:
        return asdict(self)


def _clauses(text: str):
    start = 0
    for match in _BOUNDARY.finditer(text or ""):
        end = match.start()
        if (text[start:end]).strip():
            yield start, end, text[start:end]
        start = match.end()
    if (text[start:]).strip():
        yield start, len(text), text[start:]


def _trim(source: str, start: int, end: int) -> tuple[int, int, str]:
    raw = source[start:end]
    left = len(raw) - len(raw.lstrip())
    right = len(raw.rstrip())
    start += left
    end = start + max(0, right - left)
    return start, end, source[start:end]


def extract(text: str) -> tuple[RequirementSpan, ...]:
    """동일 원문 절의 정확 offset을 가진 qualifier 후보를 반환한다."""
    text = str(text or "")
    out: list[RequirementSpan] = []
    seen = set()
    for clause_start, clause_end, clause in _clauses(text):
        start, end, surface = _trim(text, clause_start, clause_end)
        if not surface:
            continue
        matches = []
        for kind, pattern in _TRIGGERS.items():
            matches.extend((kind, match) for match in pattern.finditer(surface))
        matches.extend(("QUANTITY", match) for match in _QUANTITY.finditer(surface))
        matches.extend(("TIME", match) for match in _TIME.finditer(surface))
        for kind, match in matches:
            key = (kind, start, end)
            if key in seen:
                continue
            seen.add(key)
            out.append(RequirementSpan(
                kind=kind, surface=surface, start=start, end=end,
                trigger=match.group(0),
                trigger_start=start + match.start(),
                trigger_end=start + match.end(),
            ))
    return tuple(sorted(out, key=lambda row: (row.start, KINDS.index(row.kind))))


_QUESTION_CUES = {
    "CONDITION": re.compile(r"요건|기준|경우|해당|전제"),
    "EXCEPTION": re.compile(r"예외|제외|단서|불구하고"),
    "TIME": re.compile(r"언제|기간|기한|기준일|이내|이후|이전|며칠|몇\s*년"),
    "QUANTITY": re.compile(r"얼마|몇\s*(?:명|개|주|회|일|개월|년)|비율|한도|수량|100분|퍼센트|%"),
    "METHOD": re.compile(r"어떻게|절차|방법|제출|신고|승인|결의|어디에|누구에게"),
    "EFFECT": re.compile(r"효력|무효|취소|책임|제재|처분|결과|어떻게 되는"),
}


def requested_kinds(question: str) -> tuple[str, ...]:
    return tuple(kind for kind in KINDS
                 if _QUESTION_CUES[kind].search(str(question or "")))
