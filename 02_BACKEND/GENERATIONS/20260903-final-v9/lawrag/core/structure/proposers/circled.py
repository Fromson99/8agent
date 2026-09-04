"""제안자 — 원문자 `① … ⑳` (SPEC §6.1).

낱글자 나열이 아니라 **범위**로 받는다. 실측(kofia_rule)에서 `[①②③…⑮]` 식으로
열거한 패턴이 ⑯~⑳ 을 조용히 빠뜨렸다.

이 계열이 법령에서는 항, 다른 문서에서는 열거의 맨 아래에 온다 — **그 차이는 여기서
정하지 않는다.** 같은 family 하나이고, 몇 번째 칸에 앉을지는 문서가 유도한다(§6).
"""

from __future__ import annotations

import re

from lawrag.core.structure.model import Block, Candidate
from lawrag.core.structure.proposers import scan

ID = "circled"
ROLE = "proposer"
LANG = "any"
FAMILY = "circled"
SURFACE = "① … ⑳"

_FULL = re.compile(r"([①-⑳])")


def _ordinal_factory(lex):
    def _ordinal(m: re.Match):
        n = lex.numerals.read(m.group(1))
        return (n,) if n is not None else None
    return _ordinal


def propose(block: Block, lex) -> list[Candidate]:
    return scan(block, FAMILY, _FULL, _ordinal_factory(lex))
