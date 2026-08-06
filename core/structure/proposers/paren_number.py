"""제안자 — 괄호번호 `(1)` / `1)` (SPEC §6.1).

두 표기를 같은 family 로 둔다. 한 문서가 둘을 섞어 쓰면 계열이 갈려 사다리가
쓸데없이 깊어지고, 실제로 같은 층으로 쓰이는 것이 관측된 형태다.
`1)` 은 여는 괄호 없이 닫는 괄호만 오는 것이 구성 신호다.
"""

from __future__ import annotations

import re

from core.structure.model import Block, Candidate
from core.structure.proposers import scan

ID = "paren_number"
ROLE = "proposer"
LANG = "any"
FAMILY = "paren_number"
SURFACE = "(1) / 1)"

_FULL = re.compile(r"\((\d{1,3})\)|(?<![(\d.])(\d{1,3})\)(?=\s|$)")
_FRAGMENT = re.compile(r"(?<![(\d.])(\d{1,3})\)(?=\S)")


def _ordinal(m: re.Match):
    g = next((x for x in m.groups() if x), None)
    return (int(g),) if g else None


def propose(block: Block, lex) -> list[Candidate]:
    return scan(block, FAMILY, _FULL, _ordinal, fragment=_FRAGMENT)
