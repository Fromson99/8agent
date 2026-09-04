"""계열 정합 (S2) — **사다리 없이** 계열 안에서 구조와 인용을 가른다.

    select(candidates) -> None   (후보의 survives / family_note 를 채운다)

## 왜 별도 단계인가 — 카테고리가 셋이다

SPEC 초판(§1.1)은 전역 정합성을 둘로 갈랐다.

    바깥(S2) 형식 일관성 → 레벨을 **정한다**
    안쪽(S3) 서수·계층성 → 레벨 정해진 뒤 후보를 **거른다**

그리고 "서수는 레벨이 정해진 뒤"라고 못박았다. 실측이 그 전제를 뒤집었다 —
**서수 비교는 같은 계열 안에서만 일어나므로 레벨을 몰라도 된다.** 계열은 제안자가
이미 알려 준다. 그래서 카테고리는 셋이다.

    S1 국소   후보 하나를 주변만 보고            → 점수
    S2 계열   한 계열의 후보 전체를 보고         → 구조 / 인용     ← 레벨 불필요
    S3 전역   여러 계열을 함께 보고              → 레벨 사다리
    S4 전역   레벨 고정 뒤 후보를 앉히고 트리로

## 이 순서가 고치는 것

예전에는 레벨을 먼저 정했고, 등재 심사가 "양수 후보 비율"로 계열을 걸렀다. 조(條)는
본문에서 제목과 **같은 글자**로 인용되므로 후보 251건 중 159건이 인용이었고, 가드가
그것을 정확히 깎아낼수록 비율이 낮아져 조 계열이 통째로 탈락했다. 탈락하면 레벨이
없고, 레벨이 없으면 스코프가 없고, 스코프가 없으면 제55조와 제51조가 만나지 못해
서수 규칙이 영영 발동하지 않았다.

계열 정합을 앞으로 옮기면 그 비율 계산 자체가 사라진다. 실측: 금소법 조 251 → 77건,
번호 1~69 연속. 준칙(KOFIA-R)에서는 206 → 0건 — 준칙은 조를 인용만 하고 자기 조가
없는 문서이며, 그 판정이 정확하다.

## 두 신호를 순서대로 건다

    1. anchor  위치. 블록 첫머리이거나, 중간이면 1로 시작 + 앞에 다른 계열.
               여기서 떨어진 것은 **수열 계산에 들어가지도 않는다** — 머리글의 날짜가
               점번호로 잡혀 뒤의 호 번호를 통째로 어긋내는 것을 막는다.
    2. run     연속 단위. 한 칸씩 이어지는 묶음에 낀 것이 구조, 못 낀 것이 인용.
               무엇이 "한 칸" 인지는 `succession` 이 안다(가지조 `제16조의2` 포함).

    anchor 만  → 조 제목 줄에 붙어 온 제1항 173건이 죽는다
    run 만     → 오름차순으로 나열된 다른 법률 인용이 통과한다 (제161조, 제336조 …)

각 파일의 주석에 실측 수치가 적혀 있다.
"""

from __future__ import annotations

import collections

from lawrag.core.structure.family import anchor, run
from lawrag.core.structure.model import Candidate


def select(candidates: list[Candidate]) -> dict[str, int]:
    """후보의 `survives` 를 채운다. 반환: 계열별로 걸러낸 개수."""
    by_block: dict[int, list[Candidate]] = collections.defaultdict(list)
    for c in candidates:
        by_block[c.block_idx].append(c)
    for v in by_block.values():
        v.sort(key=lambda c: c.offset)

    by_family: dict[str, list[Candidate]] = collections.defaultdict(list)
    for c in candidates:
        by_family[c.family_key].append(c)

    dropped: dict[str, int] = {}
    for key in sorted(by_family):
        ordered = sorted(by_family[key], key=lambda x: (x.doc, x.block_idx, x.offset))

        # 1) 위치 — 여기서 떨어진 것은 수열 계산에 **들어가지도 않는다.**
        #    법령 머리글의 날짜(`[시행 2026. 1. 2.] … 2025. 10. 1.,`)가 점번호로 잡히는데,
        #    그것을 수열에 넣으면 뒤의 호 번호가 통째로 어긋난다(KSB 실측 78건).
        anchored: list = []
        for c in ordered:
            ok, why = anchor.anchored(c, by_block[c.block_idx])
            if ok:
                c.survives, c.family_note = True, why
                anchored.append(c)
            else:
                c.survives, c.family_note = False, why
                dropped[key] = dropped.get(key, 0) + 1

        # 2) 연속 단위 — 묶음에 낀 것이 구조, 못 낀 것이 인용
        keep, stray = run.chains(anchored)
        for c in stray:
            c.survives = False
            c.family_note = run.reason(c, keep)
            dropped[key] = dropped.get(key, 0) + 1
        for i, chain in enumerate(keep):
            for c in chain:
                c.chain = i
                if len(chain) < run.MIN_CHAIN and not c.family_note:
                    c.family_note = "1 로 여는 유일 항목"
    return dict(sorted(dropped.items()))
