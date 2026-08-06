"""제안자 — 한국 법령의 대구역 `제N편/장/절/관` (SPEC §6.1).

편·장·절·관을 **한 파일에 두되 family 는 글자별로 가른다**(`kr_편`, `kr_장` …).
같은 구성(`제 + 번호 + 단위`)이라 패턴은 하나고, 계열은 단위 글자가 정한다.
서로의 상하 관계는 여기서 선언하지 않는다 — 문서에서 관측된다(§4 S2-2).

완전형은 `제3장`, 파편은 `제 3 장`(자간 벌어짐)·`3장`(제 없음)이다(§5.1).
"""

from __future__ import annotations

import re

from core.structure.model import Block, Candidate
from core.structure.proposers import scan

ID = "kr_division"
ROLE = "proposer"
LANG = "ko"
FAMILY = "kr_division"
SURFACE = "제N편 / 제N장 / 제N절 / 제N관"

_UNITS = "편장절관"
_FULL = re.compile(rf"제(\d{{1,3}})([{_UNITS}])")
_FRAGMENT = re.compile(rf"제\s+(\d{{1,3}})\s*([{_UNITS}])|(?<![제\d])(\d{{1,3}})\s*([{_UNITS}])(?=\s)")


def _ordinal(m: re.Match):
    for g in m.groups():
        if g and g.isdigit():
            return (int(g),)
    return None


def _unit(m: re.Match) -> str:
    for g in m.groups():
        if g and g in _UNITS:
            return g
    return "?"


def propose(block: Block, lex) -> list[Candidate]:
    out = scan(block, FAMILY, _FULL, _ordinal, fragment=_FRAGMENT)
    for c in out:
        m = _FULL.match(c.surface) or _FRAGMENT.match(c.surface)
        c.family = f"kr_{_unit(m)}" if m else FAMILY
    return out
