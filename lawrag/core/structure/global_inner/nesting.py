"""계층성 — `check_nesting(cand, scope_stack) -> ok | FORBID` (SPEC §3.3, §5.2).

목이 조 없이 튀어나오면 금지한다. 위반은 벌점이 아니라 **경로 배제**(FORBID)다 —
계층이 깨진 트리는 좌표가 성립하지 않으므로 점수로 무마할 수 있는 종류가 아니다.

## "부모 레벨" 을 무엇으로 읽는가

바로 위 레벨이 아니라 **자기보다 얕은 레벨 아무거나**가 열려 있으면 통과다.
법령이 실제로 층을 건너뛰기 때문이다 — `제2조(정의)` 는 항(①) 없이 곧바로
`1.` `가.` 로 내려간다. 바로 위 레벨을 요구하면 그런 정상 문서가 통째로 FORBID 된다.
층을 건너뛴 것 자체는 §5.2 의 novelty 벌점이 가볍게 받는다.

L0 은 위가 없으므로 언제나 통과한다.
"""

from __future__ import annotations

from lawrag.core.structure.model import ScopeStack

OK = "ok"
FORBID = "FORBID"


def check(level: int, stack: ScopeStack) -> str:
    if level <= 0:
        return OK
    if any(stack.last[i] is not None for i in range(level)):
        return OK
    return FORBID
