"""제안자 (SPEC §3.1, §4 S0) — `propose(text, blocks) -> [Candidate]`.

    표면 패턴 매칭 + 서수 추출만. **판단·레벨 의미 없음.**

각 제안자가 아는 것은 셋뿐이다: 표면 패턴, 서수 추출법, family. 여기에 "이게 몇 번째
레벨이냐" 는 절대 들어가지 않는다 — 레벨은 문서가 유도한다(§6). 관리소가 등록 시점에
그것을 검사한다(`registry.FORBIDDEN_ATTRS`).

## 왜 `^` 앵커로만 훑지 않는가

블록 첫머리만 보면 본문 속 참조(mention)가 **후보로조차 생기지 않는다.** 그러면
블록위치 가드가 매길 점수도 없고, 그것이 왜 버려졌는지 감사 로그에 남지도 않는다.
골든 §8 의 c8(`(1.1의 원칙을 준용)`)이 정확히 그 경우다. 그래서 제안자는 블록 전체를
훑어 **전량 수집**하고(§4 S0 "판단 0, 순수 수집"), 가르는 일은 가드와 DP 가 한다.

## 공통 도구

`scan()` 이 완전형/파편 두 패턴을 훑어 후보를 만든다. 제안자 파일은 패턴 두 개와
서수 읽는 법만 적으면 된다.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from core.structure.model import Block, Candidate, Ordinal


def in_paren(text: str, offset: int) -> bool:
    """이 위치가 괄호 안인가 — 블록위치 가드가 인라인 참조를 가르는 데 쓴다."""
    depth = 0
    for ch in text[:offset]:
        if ch in "([{（〔":
            depth += 1
        elif ch in ")]}）〕":
            depth = max(0, depth - 1)
    return depth > 0


def scan(block: Block, family: str, full: re.Pattern,
         ordinal_of: Callable[[re.Match], Optional[Ordinal]],
         *, fragment: Optional[re.Pattern] = None,
         depth_of: Optional[Callable[[re.Match], Optional[int]]] = None,
         prefix: str = "") -> list[Candidate]:
    """블록 하나에서 후보를 전량 수집한다.

    완전형이 먼저다 — 같은 자리에서 완전형이 잡히면 파편은 만들지 않는다.
    """
    out: list[Candidate] = []
    taken: list[tuple[int, int]] = []

    for pattern, construction in ((full, "full"), (fragment, "fragment")):
        if pattern is None:
            continue
        for m in pattern.finditer(block.text):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            out.append(Candidate(
                id="", family=family,
                depth=depth_of(m) if depth_of else None,
                surface=m.group(0).strip(),
                ordinal=ordinal_of(m),
                block_idx=block.idx, offset=m.start(), end=m.end(),
                page=block.page, element_index=block.element_index,
                text=block.text, construction=construction,
                in_paren=in_paren(block.text, m.start()),
                is_heading=block.is_heading, bbox=block.bbox))
    out.sort(key=lambda c: c.offset)
    if prefix:
        for c in out:
            c.family = prefix
    return out
