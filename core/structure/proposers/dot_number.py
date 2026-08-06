"""제안자 — 범용 점번호 `1.` / `1.1` / `1.1.1` (SPEC §6.1).

이 계열만이 **표면이 스스로 깊이를 말한다**(§4 S2-1: "점번호는 dot-depth 가 곧 계층 →
관측 없이 확정"). 그래서 `depth` 를 채워 내보내고, 사다리는 `dot_number:1`,
`dot_number:2` … 를 각각 다른 계열로 등재한다.

`depth` 는 표면에서 **읽은** 것이지 레벨을 **정한** 것이 아니다. 몇 번째 칸에
앉을지는 여전히 S2 가 정한다 — `1.1` 이 L0 인 문서도 있을 수 있다.
"""

from __future__ import annotations

import re

from core.structure.model import Block, Candidate
from core.structure.proposers import scan

ID = "dot_number"
ROLE = "proposer"
LANG = "any"
FAMILY = "dot_number"
SURFACE = "1. / 1.1 / 1.1.1"

# 완전형: 번호(들) + 마침표 + 공백. 뒤에 숫자가 바로 붙는 형태는 소수·금액이므로 뺀다.
_FULL = re.compile(r"(?<![\d.)])(\d{1,3}(?:\.\d{1,3})*)\.(?=\s|$)")
# 다단 표기 `1.1` 은 끝 마침표가 없다. 뒤에 공백을 요구하면 안 된다 — `1.1의 원칙`
# 처럼 조사가 바로 붙은 **참조**가 후보로조차 생기지 않아 조사 가드가 매길 점수가
# 없어진다(골든 §8 의 c8). 후보는 전량 수집하고 가르는 일은 가드가 한다(§4 S0).
_MULTI = re.compile(r"(?<![\d.)])(\d{1,3}(?:\.\d{1,3})+)(?![\d.])")
# 파편: 마침표 뒤 공백이 없는 것 (`1.가입금액`)
_FRAGMENT = re.compile(r"(?<![\d.)])(\d{1,3}(?:\.\d{1,3})*)\.(?=\D)")


def _ordinal(m: re.Match):
    return tuple(int(p) for p in m.group(1).split("."))


def _depth(m: re.Match) -> int:
    return len(m.group(1).split("."))


def propose(block: Block, lex) -> list[Candidate]:
    out = scan(block, FAMILY, _FULL, _ordinal, fragment=_FRAGMENT, depth_of=_depth)
    seen = {(c.offset, c.end) for c in out}
    for c in scan(block, FAMILY, _MULTI, _ordinal, depth_of=_depth):
        if not any(a <= c.offset < b or a < c.end <= b for a, b in seen):
            out.append(c)
    out.sort(key=lambda c: c.offset)
    return out
