"""서수 단조 — `check_ordinal(cand, scope_stack) -> ok | penalty` (SPEC §3.3, §5.2).

    서수 역행(같은 스코프에서 감소)  −1.5
    서수 gap(건너뜀)                −0.3

**여기가 리셋을 안전하게 다루는 자리다.** 스코프가 이미 닫혀 있으면(`stack.last[L]
is None`) 비교 대상이 없으므로 벌점이 없다. 장이 바뀔 때 `ScopeStack.activate` 가
하위 레벨을 닫으므로, 장마다 조가 1부터 다시 시작하는 문서에서 리셋은 **애초에 역행이
아니다.** 리셋을 감점하지 않으려고 따로 예외를 두는 게 아니라, 스코프 모델이 그것을
구조적으로 보장한다.

서수가 없는 후보(`부칙`)는 검사를 건너뛴다 — 비교할 것이 없다.

벌점이지 FORBID 가 아닌 이유: 번호가 튄 진짜 헤더가 있다(개정으로 조가 삭제되면
`제5조` 다음이 `제7조` 다). 죽이지 않고 깎아서, 다른 신호가 충분히 세면 살아남게 한다.
"""

from __future__ import annotations

from typing import Optional

from lawrag.core.structure import scoring
from lawrag.core.structure.model import Ordinal, ScopeStack


def check(level: int, ordinal: Optional[Ordinal], stack: ScopeStack) -> tuple[float, str]:
    """(벌점, 사유). 벌점 0 이면 통과."""
    if ordinal is None:
        return 0.0, ""
    last = stack.last[level]
    if last is None or last == ():
        return 0.0, ""                      # 새로 여는 스코프 — 비교 대상이 없다

    if ordinal <= last:
        return scoring.ORDINAL_REGRESS, (
            f"서수 역행: 같은 스코프에서 {_fmt(last)} 뒤에 {_fmt(ordinal)}")
    if _gap(last, ordinal):
        return scoring.ORDINAL_GAP, (
            f"서수 건너뜀: {_fmt(last)} → {_fmt(ordinal)}")
    return 0.0, ""


def _gap(last: Ordinal, cur: Ordinal) -> bool:
    """같은 자리에서 1 이 아니라 2 이상 뛰었는가."""
    if len(last) != len(cur):
        return False                        # 깊이가 다르면 gap 을 논하지 않는다
    for a, b in zip(last, cur):
        if b == a:
            continue
        return b - a > 1
    return False


def _fmt(o: Optional[Ordinal]) -> str:
    return ".".join(str(x) for x in o) if o else "?"
