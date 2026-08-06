"""계열 정합 — **연속 단위(run)** 찾기 (S2).

    chains(cands) -> (연속 단위들, 벗어난 후보들)

계열의 후보를 읽기순으로 훑어 **한 칸씩 이어지는 묶음**을 찾는다. 그 묶음이 구조이고,
어디에도 안 끼는 것이 본문 속 인용이다.

    조:  1,2,3,4,5 …            → 하나의 연속 단위
    절:  1,2,3 | 1,2,3          → 두 개의 연속 단위 (장이 바뀌며 리셋)
    별표: 3, 9, 22               → 이어지는 것이 없다 → 전부 인용

**무엇이 "한 칸"인지는 `succession` 이 안다.** 한국 법령은 조를 삭제하지 않고 사이에
끼워 넣으므로(`제16조 → 제16조의2 → 제17조`) 자릿수가 섞인다 — 그 관습을 여기에
섞지 않고 갈라 두었다.

## 왜 "직전 번호(prev) 하나" 로 걷지 않는가

`prev` 를 들고 왼→오로 걸으면 인용 하나가 수열 전체를 오염시킨다.

    1조 2조 3조 [20조] 4조 5조 …
                  ↑ prev 를 20 으로 밀면 뒤의 4·5조가 전부 죽는다
                    prev 를 3 에 묶어 두면 파싱이 ② 를 빠뜨렸을 때 ③④⑤ 가 줄줄이 죽는다

실측에서 두 방식 모두 수십 건을 잘못 죽였다. 어느 쪽도 맞지 않는 이유는 같다 —
**수열은 상태 하나가 아니라 묶음**이기 때문이다.

여러 묶음을 동시에 열어 두고 각 후보를 자기가 이어갈 수 있는 묶음에 붙이면 둘 다 풀린다.

    1조 2조 3조 [20조] 4조 …    20조는 아무 묶음도 못 이어 혼자 남는다 → 인용
                               4조는 [1,2,3] 을 그대로 이어간다 → 구조
    1항 [② 누락] ③항 ④항 …      ③ 이 새 묶음을 열고 ④ 가 붙어 길이 2 → 구조

## 판정

    길이 2 이상          연속 단위 → 구조
    길이 1 이고 번호 1    스코프를 여는 유일한 항목일 수 있다 → 구조
    길이 1 이고 그 외     이어지는 것이 없다 → 인용
"""

from __future__ import annotations

from typing import Optional

from core.structure.family import succession
from core.structure.model import Candidate, Ordinal

ID = "run"
ROLE = "family_coherence"
LANG = "any"
SURFACE = "연속 단위(run) — 한 칸씩 이어지는 묶음"

# 이 길이 이상이면 연속 단위로 인정한다
MIN_CHAIN = 2


def chains(cands: list[Candidate]) -> tuple[list[list[Candidate]], list[Candidate]]:
    """읽기순 후보를 연속 단위로 묶는다. 반환: (묶음들, 어디에도 못 낀 것들).

    각 후보는 **자기를 이어갈 수 있는 묶음 중 가장 최근 것**에 붙는다. 못 붙으면
    새 묶음을 연다 — 그것이 파싱 누락으로 생긴 새 시작인지 인용인지는 뒤가 붙는지로 갈린다.
    """
    open_chains: list[list[Candidate]] = []
    for c in cands:
        if c.ordinal is None:
            open_chains.append([c])            # 번호 없는 계열(부칙) — 홀로 둔다
            continue
        for ch in reversed(open_chains):
            last = ch[-1].ordinal
            if last is not None and succession.follows(c.ordinal, last):
                ch.append(c)
                break
        else:
            open_chains.append([c])

    keep, stray = [], []
    for ch in open_chains:
        if len(ch) >= MIN_CHAIN:
            keep.append(ch)
        elif ch[0].ordinal is None or ch[0].ordinal[0] == 1:
            keep.append(ch)                    # 1 로 여는 유일 항목
        else:
            stray.extend(ch)
    return keep, stray


def reason(cand: Candidate, keep: list[list[Candidate]]) -> str:
    """어디에도 못 낀 이유 — 감사 로그에 그대로 실린다."""
    near = []
    for ch in keep:
        for x in ch:
            if x.ordinal and cand.ordinal and abs(x.ordinal[0] - cand.ordinal[0]) <= 3:
                near.append(_fmt(x.ordinal))
    hint = f" (가까운 연속 단위: {', '.join(sorted(set(near))[:4])})" if near else ""
    return (f"번호 {_fmt(cand.ordinal)} 가 어떤 연속 단위에도 이어지지 않습니다{hint} "
            f"— 본문 속 인용입니다")


def _fmt(o: Optional[Ordinal]) -> str:
    return ".".join(str(x) for x in o) if o else "?"
