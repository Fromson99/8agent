"""제안자 — 한글 자모 열거 `가. 나. 다.` (SPEC §6.1).

가~하 열네 자만 받는다. `[가-힣]` 로 열면 `위. ` 같은 문장 첫머리까지 삼킨다(KSB 실측).
마커와 마침표 사이 공백이 벌어지는 판본이 있어(`가 .` — KOFIA-R 실측) 파편으로 받는다.
"""

from __future__ import annotations

import re

from lawrag.core.structure.model import Block, Candidate
from lawrag.core.structure.proposers import scan

ID = "hangul_jamo"
ROLE = "proposer"
LANG = "ko"
FAMILY = "hangul_jamo"
SURFACE = "가. 나. 다. … 하."

_LETTERS = "가나다라마바사아자차카타파하"
_FULL = re.compile(rf"(?<![가-힣])([{_LETTERS}])\.(?=\s)")
_FRAGMENT = re.compile(rf"(?<![가-힣])([{_LETTERS}])\s+\.\s|(?<![가-힣])([{_LETTERS}])\.(?=\S)")


def _ordinal_factory(lex):
    def _ordinal(m: re.Match):
        token = next((g for g in m.groups() if g), None)
        n = lex.numerals.read(token) if token else None
        return (n,) if n is not None else None
    return _ordinal


def propose(block: Block, lex) -> list[Candidate]:
    return scan(block, FAMILY, _FULL, _ordinal_factory(lex), fragment=_FRAGMENT)
