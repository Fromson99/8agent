"""제안자 — 괄호번호 `(1)` / `1)` (SPEC §6.1).

두 표기를 **다른 계열로 낸다** (2026-08-11 결정, 아래 실측). 예전에는 한 계열로
묶었는데 — "한 문서가 둘을 섞어 쓰면 계열이 갈려 사다리가 쓸데없이 깊어지고,
실제로 같은 층으로 쓰이는 것이 관측됐다" — 반례가 나왔다:

    삼성증권 상품설명서 (n=201)
        (N)   중앙값 0.1241   Q1 0.0941  Q3 0.1360
        N)    중앙값 0.1768   Q1 0.1607  Q3 0.1881
        → Q3(N) < Q1(N)) — 두 분포가 거의 겹치지 않는다. 다른 층이다.

한 계열로 묶으면 층만 뭉개지는 게 아니라 **서수 스코프를 나눠 쓴다.** 실측에서
`5) … 가.나.다. … (2) … 6)` 순서일 때, 목을 5) 안에 옳게 넣으면 뒤따르는 `(2)`
가 같은 스코프에서 서수 역행(2 ≤ 5)으로 −1.5 를 맞아, 틀린 배치가 더 싸졌다.

**계열을 가른다고 층이 갈리지는 않는다.** 같은 층으로 쓰인 문서에서는 사다리의
증거가 둘을 같은 칸에 나란히 앉힌다(위상정렬은 한 층에 여러 계열을 담는다).
가르는 것은 "다를 수 있다"를 표현할 자리를 만드는 것이지 다르다고 우기는 게
아니다 — 판단은 문서가 한다(§0).

이름에 `paren_number:` 를 남겨 두어 `families` 힌트("paren_number")가 예전처럼
두 갈래를 함께 고른다.
"""

from __future__ import annotations

import re

from lawrag.core.structure.model import Block, Candidate
from lawrag.core.structure.proposers import scan

ID = "paren_number"
ROLE = "proposer"
LANG = "any"
FAMILY = "paren_number"
SURFACE = "(1) / 1)"

# 계열 이름 — 앞머리를 공유해 힌트 필터(`family.split(":")[0]`)가 둘 다 잡는다.
FAMILY_BOTH = "paren_number:both"     # (1) — 여닫는 괄호
FAMILY_RIGHT = "paren_number:right"   # 1)  — 닫는 괄호만

_BOTH = re.compile(r"\((\d{1,3})\)")
_BOTH_FRAGMENT = re.compile(r"\((\d{1,3})\)(?=\S)")
# `1)` 은 여는 괄호 없이 닫는 괄호만 오는 것이 구성 신호다.
_RIGHT = re.compile(r"(?<![(\d.])(\d{1,3})\)(?=\s|$)")
_RIGHT_FRAGMENT = re.compile(r"(?<![(\d.])(\d{1,3})\)(?=\S)")


def _ordinal(m: re.Match):
    g = next((x for x in m.groups() if x), None)
    return (int(g),) if g else None


def propose(block: Block, lex) -> list[Candidate]:
    return (scan(block, FAMILY_BOTH, _BOTH, _ordinal, fragment=_BOTH_FRAGMENT)
            + scan(block, FAMILY_RIGHT, _RIGHT, _ordinal, fragment=_RIGHT_FRAGMENT))
