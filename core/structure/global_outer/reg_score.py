"""형식 일관성 — 이 계열을 레벨에 등재해도 되는가 (SPEC §3.3, S3).

    score(family, survivors) -> float

**계열 정합(S2)을 통과한 후보만 받는다.** 이것이 이전 판과의 핵심 차이다.

## 예전 공식이 왜 틀렸나 (실측)

    등재점수 = (양수 후보 수 ÷ 전체 후보 수) × 서수 규칙성

분모가 **제안자가 주운 것 전부**였다. 조(條)는 본문에서 제목과 같은 글자로 인용되므로
금소법에서 후보 251건 중 159건이 인용이었고, 가드가 그것을 **정확히** 음수로 깎아낼수록
비율이 낮아졌다. 잘 잡아낸 것이 벌점이 되어 0.37 → 탈락.

지금은 인용이 S2 에서 이미 빠졌으므로 그런 계산 자체가 없다.

## 지금 무엇을 재는가 — 런의 결

계열이 진짜 구조라면 번호가 **길게 이어진다**. 리셋은 정상이지만(장마다 조가 1부터),
매번 끊기면 그건 계열이 아니라 우연이다.

    등재점수 = 생존 수 ÷ (생존 수 + 런 개수)

런이 길수록 1 에 가깝고, 후보마다 런이 끊기면 0.5 로 내려간다. 리셋을 **감점하지
않으면서** 불규칙만 잡는다. 실측(금소법): 조 77건/런 3개 → 0.96, 장 8건/런 1개 → 0.89,
목 96건/런 30개 → 0.76. 인용만 있는 준칙의 조는 생존 0건 → 0.00.

생존이 둘 미만이면 계열이라고 부를 수 없으므로 0 이다.
"""

from __future__ import annotations

from core.structure import scoring
from core.structure.model import Candidate

ID = "reg_score"
ROLE = "global_outer"
LANG = "any"
SURFACE = "런의 결 — 생존 ÷ (생존 + 런 개수)"


def runs(cands: list[Candidate]) -> list[list[Candidate]]:
    """생존 후보를 단조증가 런으로 자른다. 되감기는 자리에서 끊는다."""
    out: list[list[Candidate]] = []
    cur: list[Candidate] = []
    for c in sorted(cands, key=lambda x: (x.doc, x.block_idx, x.offset)):
        prev = next((x for x in reversed(cur) if x.ordinal is not None), None)
        if not cur or c.ordinal is None or prev is None or c.ordinal > prev.ordinal:
            cur.append(c)
        else:
            out.append(cur)
            cur = [c]
    if cur:
        out.append(cur)
    return out


def score(family: str, survivors: list[Candidate]) -> float:
    if len(survivors) < 2:
        return 0.0                       # 하나짜리는 계열이 아니다
    n_runs = len(runs(survivors))
    return round(len(survivors) / (len(survivors) + n_runs), 4)


def registered(family: str, survivors: list[Candidate]) -> bool:
    return score(family, survivors) >= scoring.REG_SCORE_MIN


def outliers(survivors: list[Candidate]) -> list[Candidate]:
    """리셋했는데 뒤가 안 이어지는 후보 — '미배정, 문맥판정' 딱지를 붙일 것들.

    계열은 멀쩡한데 그 하나가 문맥을 타는 경우다(골든 §8.3 의 c9: `2.` 뒤의 `1.`).
    죽이지 않고 S4 로 넘겨 여러 레벨을 시도하게 한다.
    """
    out: dict[int, Candidate] = {}
    for i, run in enumerate(runs(survivors)):
        if i > 0 and len(run) < 2:
            out.update({id(c): c for c in run})
    return sorted(out.values(), key=lambda c: (c.doc, c.block_idx, c.offset))
