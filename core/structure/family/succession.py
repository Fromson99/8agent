"""계열 정합 — **다음 번호 규칙** (S2).

    follows(cur, prev) -> bool     cur 가 prev 바로 다음인가

`run` 은 "한 칸씩 이어지는 묶음"을 찾고, **무엇이 한 칸인지는 여기가 안다.** 둘을 갈라
두는 이유: 묶음을 만드는 방식은 계열과 무관한 기계이고, "다음 번호"는 그 번호 체계의
관습이기 때문이다.

## 왜 필요했나 — 가지조(제N조의M)

한국 법령은 조를 삭제하지 않고 **사이에 끼워 넣는다.**

    제15조
    제16조
    제16조의2      ← 제16조 다음, 제17조 앞
    제16조의3
    제17조

서수로는 `(15,) (16,) (16,2) (16,3) (17,)` 이라 **자릿수가 섞인다.** 같은 자릿수만
비교하던 규칙에서는 가지조가 어떤 묶음에도 못 붙어 인용으로 오판됐다(실측 KSB:
`제16조의2`, `제21조의2` 가 가드 만점인데 탈락).

## 네 가지가 한 칸이다

    같은 자릿수, 마지막 다른 자리가 +1      (16,) → (17,)      (16,2) → (16,3)
    본조 → 첫 가지조                        (16,) → (16,2)
    가지조 → 다음 본조                      (16,2) → (17,)
    가지조 → 다음 가지조                    (16,2) → (16,3)   (같은 자릿수 규칙이 처리)

가지조는 **의2 부터 시작한다**(의1 은 없다). 그래서 본조에서 넘어갈 때 마지막 자리가
2 여야 한다 — `(16,) → (16,4)` 는 중간이 빈 것이므로 한 칸이 아니다.

## 이 규칙이 필요한 계열은 하나뿐이다

`kr_article` 만 자릿수가 섞인다. `roman_sub`(`Ⅰ-1`)·`dot_number:2`(`1.1`) 는 계열 안에서
자릿수가 늘 같아 첫 번째 규칙만으로 처리된다. 그래서 계열별 설정이 아니라 **모든 계열에
같은 규칙**을 걸어도 부작용이 없다 — 자릿수가 안 섞이면 나머지 규칙은 발동하지 않는다.
"""

from __future__ import annotations

from core.structure.model import Ordinal

ID = "succession"
ROLE = "family_coherence"
LANG = "any"
SURFACE = "다음 번호 — 가지 표기(제N조의M) 포함"

# 가지 표기는 2 부터 시작한다. `제16조의1` 은 없다.
FIRST_BRANCH = 2


def follows(cur: Ordinal, prev: Ordinal) -> bool:
    """cur 가 prev 바로 다음 번호인가."""
    if not cur or not prev:
        return False

    if len(cur) == len(prev):
        # 처음으로 달라지는 자리가 +1 이고, **그 뒤는 전부 1 로 리셋**되어야 한다.
        #   1.1 → 1.2   뒷자리 +1
        #   1.2 → 2.1   앞자리 +1, 뒷자리 리셋      ← 계층 번호의 정상 승계
        #   1.2 → 2.3   앞자리는 +1 인데 뒤가 안 리셋 → 이어지지 않는다
        diff = next((i for i, (a, b) in enumerate(zip(prev, cur)) if a != b), None)
        if diff is None:
            return False                          # 같은 번호
        return (cur[diff] == prev[diff] + 1
                and all(x == 1 for x in cur[diff + 1:]))

    if len(cur) == len(prev) + 1:
        # 본조 → 첫 가지조. 앞자리가 그대로여야 한다.
        return tuple(cur[:len(prev)]) == tuple(prev) and cur[-1] == FIRST_BRANCH

    if len(prev) == len(cur) + 1:
        # 가지조 → 다음 본조. 가지 자리를 떼고 본조 번호가 +1.
        return (tuple(cur[:-1]) == tuple(prev[:len(cur) - 1])
                and cur[-1] == prev[len(cur) - 1] + 1)

    return False
