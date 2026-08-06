"""전역 정합성 — **안쪽** (SPEC §3.3, §4 S3). 레벨 정해진 뒤 후보를 *거르는* 데 쓴다.

    check_nesting(cand, scope_stack) -> ok | FORBID    계층성
    check_ordinal(cand, scope_stack) -> ok | penalty   서수 단조

바깥(S2)과 갈라 둔 이유는 `global_outer/__init__.py` 에 적혀 있다 — 한 덩어리로 두면
레벨을 정하려고 서수를 보고, 서수를 보려고 레벨이 필요해지는 순환이 생긴다.
"""

from core.structure.global_inner import nesting, ordinal

__all__ = ["nesting", "ordinal"]
