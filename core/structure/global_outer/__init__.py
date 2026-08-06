"""전역 정합성 — **바깥** (SPEC §3.3, §4 S2). 레벨을 *정하는* 데 쓴다.

    reg_score(family, cands)      -> float    형식 일관성: 레벨 등재 신뢰도
    induce_ladder(fired)          -> Ladder   중첩 관측으로 순서 유도

## 카테고리 에러 방지 (§1.1 주의)

전역 정합성은 두 갈래다. "형식 일관성" 은 레벨을 **정하는** 데 쓰이므로 바깥(S2),
"서수 일관성·계층성" 은 레벨이 정해진 뒤 후보를 **거르는** 데 쓰이므로 안쪽(S3)이다.
한 덩어리로 두면 순환이 생긴다 — 레벨을 정하려고 서수를 보고, 서수를 보려고 레벨이
필요해진다. 그래서 패키지를 둘로 갈라 두었다.
"""

from core.structure.global_outer import ladder, reg_score

__all__ = ["ladder", "reg_score"]
