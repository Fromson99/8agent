"""제안자 — 한국 법령의 `제N조`, `제N조의M` (SPEC §6.1).

가지조(`제10조의2`)는 서수가 **정수 배열**이다(§2 "ordinal(정수 또는 정수배열)").
`(10, 2)` 로 읽으면 `제10조` `제10조의2` `제11조` 가 사전식으로 자연히 단조증가하므로,
가지조를 위해 계열을 따로 만들 필요가 없다. 서수 게이트도 그대로 통과한다.

`제10조의2` 의 `의` 는 조사가 아니라 구성의 일부다 — 완전형 패턴이 그것을 먼저
집어가므로 조사 가드가 오인할 자리가 없다.
"""

from __future__ import annotations

import re

from core.structure.model import Block, Candidate
from core.structure.proposers import scan

ID = "kr_article"
ROLE = "proposer"
LANG = "ko"
FAMILY = "kr_article"
SURFACE = "제N조 / 제N조의M"

_FULL = re.compile(r"제\s*(\d{1,4})\s*조(?:\s*의\s*(\d{1,3}))?")
_FRAGMENT = re.compile(r"(?<![제\d])(\d{1,4})\s*조(?![가-힣])")


def _ordinal(m: re.Match):
    g = m.groups()
    if len(g) >= 2 and g[1]:
        return (int(g[0]), int(g[1]))
    return (int(g[0]),)


def propose(block: Block, lex) -> list[Candidate]:
    return scan(block, FAMILY, _FULL, _ordinal, fragment=_FRAGMENT)
