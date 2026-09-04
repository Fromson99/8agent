"""계열 정합 — 위치 정당성 (S2).

    anchored(cand, block_cands) -> (ok, 사유)

`run` 이 못 잡는 것을 잡는다. 서수는 **역행**을 잡지 **전진하는 인용**을 못 잡는다.

    「자본시장과 금융투자업에 관한 법률」 제161조 …
    「보험업법」 제336조 …            ← 오름차순이라 수열 검사를 그냥 통과한다

그래서 위치를 함께 본다.

    블록 첫머리        → 통과. 구역은 블록을 여는 자리에서 시작한다.
    블록 중간          → **1로 시작하고, 같은 블록 앞쪽에 다른 계열 마커가 있을 때만** 통과.

## 두 번째 조건이 필요한 이유 (실측)

블록 중간을 통째로 막으면 금소법에서 ① 180건 중 173건이 죽는다. 대부분이

    "제8조(금융소비자의 책무) ① 금융소비자는 …"

처럼 **조 제목 줄에 붙어 온 제1항**이라서다. Docling 이 헤더와 본문을 한 블록으로
뱉는 것이 아니라 원문이 원래 그렇게 생겼다. 이건 진짜 구조이므로 살려야 한다.

살리면서 인용을 막는 선이 **"1로 시작 + 블록을 연 다른 계열 마커가 앞에"** 다.

    "제8조(…) ① …"          ① 은 1이고, 앞의 제8조가 **블록 첫머리(offset 0)** → 통과
    "제56조(…) ① … 제49조"   제49조는 1이 아니다                          → 기각
    "… 「보험업법」 제336조"   336 은 1이 아니다                            → 기각

## 앞 마커가 블록을 연 것이어야 하는 이유 (실측)

"앞에 다른 계열 마커가 있으면" 으로만 두면 본문 속 복합 인용이 샌다.

    "3) 임직원등은 … 14. 1) 에 따른 설명시 …"
      ↑ off 0        ↑ off 45  ↑ off 49
                     둘 다 블록 중간인데, `1)` 이 `14.` 를 근거 삼아 통과했다

`14.` 자신이 인용이므로 그것에 기대는 `1)` 도 인용이다. 근거가 될 수 있는 것은
**블록을 연 마커**뿐이다 — 그것만이 "여기서 새 구역이 시작했으니 하위가 1로
열린다" 는 말이 된다.

실측: KSB 51건·KSB-D 62건은 이미 전부 앞 마커가 offset 0 이라 영향이 없고,
KOFIA-R 만 10건이 이 구멍으로 새고 있었다.

같은 계열이 앞에 있는 것도 근거가 되지 않는다. `2.1 운용방법 (1.1의 원칙을 준용)`
에서 괄호 속 `1.1` 앞에 있는 것은 같은 점번호 계열이라, 리셋을 정당화하지 못한다
(골든 §8 의 c8 이 이렇게 걸러진다).
"""

from __future__ import annotations

from typing import Iterable

from lawrag.core.structure.model import Candidate

ID = "anchor"
ROLE = "family_coherence"
LANG = "any"
SURFACE = "블록 첫머리 / 중간이면 1로 시작 + 앞에 다른 계열"


def anchored(cand: Candidate, block_cands: Iterable[Candidate]) -> tuple[bool, str]:
    if cand.offset == 0:
        return True, ""

    if cand.ordinal is None or cand.ordinal[0] != 1:
        return False, (f"블록 {cand.offset}번째 글자에서 시작하는데 번호가 1이 아닙니다 "
                       f"— 본문 속 인용입니다")

    opener = [o for o in block_cands
              if o.offset == 0 and o.family_key != cand.family_key]
    if not opener:
        return False, ("블록 중간에서 1로 시작하지만 **블록을 연** 다른 계열 마커가 "
                       "없습니다 — 리셋을 정당화할 상위 경계가 같은 블록에 없습니다")
    return True, (f"블록 중간이지만 1로 시작하고 블록을 연 '{opener[0].surface}' 가 "
                  f"앞에 있습니다")
