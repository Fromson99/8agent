"""제안자 — 로마숫자 `Ⅰ Ⅱ Ⅲ` / `ⅰ ⅱ ⅲ` / ASCII `I II III` (SPEC §6.1).

대문자와 소문자를 **다른 family** 로 가른다(`roman_upper` / `roman_lower`). 한 문서가
둘을 쓰면 실제로 다른 층이다. 전각과 ASCII 는 같은 계열이다 — 한 문서 안에서 표기가
섞이는 것이 관측됐다(KOFIA-R 실측 [52]).

`Ⅰ-1.` 같은 복합 표기는 서수를 정수 배열 `(1, 1)` 로 읽는다.
"""

from __future__ import annotations

import re

from lawrag.core.structure.model import Block, Candidate
from lawrag.core.structure.proposers import scan

ID = "roman"
ROLE = "proposer"
LANG = "any"
FAMILY = "roman"
SURFACE = "Ⅰ Ⅱ Ⅲ / ⅰ ⅱ ⅲ / I II III"

_UPPER = r"(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|(?<![A-Za-z])[IVX]{1,4}(?![A-Za-z]))"
_LOWER = r"(?:[ⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹ]+|(?<![A-Za-z])[ivx]{1,4}(?![A-Za-z]))"

_FULL_UPPER = re.compile(rf"({_UPPER})(?:-(\d{{1,2}}))?\.(?=\s|$)")
_FULL_LOWER = re.compile(rf"({_LOWER})(?:-(\d{{1,2}}))?\.(?=\s|$)")
_FRAG_UPPER = re.compile(rf"({_UPPER})\)(?=\s|$)")
_FRAG_LOWER = re.compile(rf"({_LOWER})\)(?=\s|$)")


def _ordinal_factory(lex):
    def _ordinal(m: re.Match):
        head = lex.numerals.read(m.group(1))
        if head is None:
            return None
        sub = m.group(2) if m.re.groups >= 2 else None
        return (head, int(sub)) if sub else (head,)
    return _ordinal


def propose(block: Block, lex) -> list[Candidate]:
    ordinal = _ordinal_factory(lex)
    out = scan(block, "roman_upper", _FULL_UPPER, ordinal, fragment=_FRAG_UPPER)
    taken = {(c.offset, c.end) for c in out}
    for c in scan(block, "roman_lower", _FULL_LOWER, ordinal, fragment=_FRAG_LOWER):
        if not any(a < c.end and c.offset < b for a, b in taken):
            out.append(c)
    out.sort(key=lambda c: c.offset)
    return out
