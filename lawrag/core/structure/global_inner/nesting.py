"""계층성 — `check_nesting(cand, scope_stack) -> ok | FORBID` (SPEC §3.3, §5.2).

목이 조 없이 튀어나오면 금지한다. 위반은 벌점이 아니라 **경로 배제**(FORBID)다 —
계층이 깨진 트리는 좌표가 성립하지 않으므로 점수로 무마할 수 있는 종류가 아니다.

## "부모 레벨" 을 무엇으로 읽는가

바로 위 레벨이 아니라 **자기보다 얕은 레벨 아무거나**가 열려 있으면 통과다.
법령이 실제로 층을 건너뛰기 때문이다 — `제2조(정의)` 는 항(①) 없이 곧바로
`1.` `가.` 로 내려간다. 바로 위 레벨을 요구하면 그런 정상 문서가 통째로 FORBID 된다.
층을 건너뛴 것 자체는 §5.2 의 novelty 벌점이 가볍게 받는다.

L0 은 위가 없으므로 언제나 통과한다.

## 자기 계열 중첩 — `self_nested`

`제2조` 는 `제1조` 의 자식이 될 수 없다. `②` 는 `①` 안에, `나.` 는 `가.` 안에 들어가지
않는다. 같은 계열은 형제이지 부모·자식이 아니다 — 그런 트리는 좌표(`제1조/제2조`)가
성립하지 않으므로 이것도 벌점이 아니라 FORBID 다.

**바로 위 열린 구간**만 본다 — 조상 사슬 전부가 아니다. 골든 §8 의 `1. 국내채권` 은
`2. → 2.1 → 1.` 로 같은 계열(dot_number:1) 안에 앉는데 그것이 정답이다: 사이에 다른
계열(`2.1`)이 끼어 역할이 갈렸다. 막을 것은 `제1조 → 제2조` 처럼 같은 계열이 **직접
부모**가 되는 자리다.

실측(2026-08 내규, 장 없이 조만 있고 부칙이 둘인 세칙): 사다리가 `부칙 > 조` 로
서서 조가 L1 이 됐는데 첫 조를 열 L0 가 없어 `s4_unlock` 이 조 계열을 풀었고, 풀린
뒤에도 DP 는 옛 층(L1)에 novelty 면제를 줘서 **제2조·제3조·제4조가 제1조 아래로**
들어간 채 적합도 0.83 으로 통과했다 — 조용한 실패. 이 규칙이 그 길을 닫는다.

예외는 하나, **들여쓰기 증거**다. 같은 글머리를 안쪽에 더 들여써 쓴 문서(불릿 안의
불릿)는 문서가 그렇게 그린 것이다 — 그때는 자기 계열 안이라도 앉을 수 있다.
`dp._levels_for` 가 안쪽 자리를 후보로 주는 조건과 같은 잣대(INDENT_EPS)를 쓴다.
계열이 여러 깊이에 그려진 문서는 대개 S2 앞에서 family_key 자체가 갈리므로
(`pipeline.interpret` 의 split_indent) 여기까지 오는 일은 드물다.
"""

from __future__ import annotations

from typing import Optional

from lawrag.core.structure import scoring
from lawrag.core.structure.model import ScopeStack

OK = "ok"
FORBID = "FORBID"


def check(level: int, stack: ScopeStack) -> str:
    if level <= 0:
        return OK
    if any(stack.last[i] is not None for i in range(level)):
        return OK
    return FORBID


def self_nested(family_key: str, level: int, stack: ScopeStack,
                x_norm: Optional[float] = None) -> bool:
    """이 레벨에 앉으면 **바로 위 열린 구간을 연 것이 같은 계열**인가.

    True 면 FORBID 다. 들여쓰기가 그 구간보다 확실히 안쪽이면 문서가 그렇게 그린
    것이므로 허용한다.
    """
    for i in range(min(level, len(stack.fams)) - 1, -1, -1):
        if stack.last[i] is None:
            continue                        # 닫힌 층은 건너뛰고 더 위를 본다
        if stack.fams[i] != family_key:
            return False                    # 바로 위 부모가 다른 계열 — 정상 중첩
        x_open = stack.xs[i]
        if x_norm is not None and x_open is not None \
                and x_open + scoring.INDENT_EPS < x_norm:
            return False                    # 들여쓰기 증거 — 문서가 안쪽으로 그렸다
        return True
    return False
