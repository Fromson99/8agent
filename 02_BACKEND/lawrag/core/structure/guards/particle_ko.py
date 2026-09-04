"""국소 가드 — 조사 (한국어) (SPEC §3.2, §5.1).

    뒤에 제목명사/개행 (clean)        +0.3
    마커 직후 조사 부착               −0.9
    + 참조 서술어 근접(준용/따른다/정한)  추가 −0.4

마커를 명사로 부려먹는 문법 환경이면 그것은 참조다. `제3장의 규정`, `1.1의 원칙`,
`제19조(설명의무)에 따라` 가 그것이다. 진짜 제목 뒤에는 조사가 붙지 않는다 —
제목 명사가 오거나(공백 뒤) 줄이 끝난다. 그래서 판정은 "**공백 없이** 붙은 것이
조사인가" 하나다.

## 참조 서술어가 조사에 딸린 이유

§5.1 표에서 이 줄은 '조사 부착' 행 아래에 딸려 있다. 독립으로 걸면 골든 §8 의
c7("2.1 운용방법 (1.1의 원칙을 준용)")까지 −0.4 를 맞아 기대값 1.8 이 깨진다.
같은 블록에 참조 서술어가 있다는 사실만으로는 그 블록의 **여는 마커**가 참조가 되지
않는다 — 조사가 붙어 있어야 비로소 그 마커가 참조로 쓰였다는 뜻이다.

어휘는 `lexicon/josa.yaml`, `lexicon/reference_predicates.yaml` 에 있다.
"""

from __future__ import annotations

from lawrag.core.structure import scoring
from lawrag.core.structure.model import Candidate

ID = "particle_ko"
ROLE = "local_guard"
LANG = "ko"
SURFACE = "마커 직후 조사 부착 / 참조 서술어 근접"


def score(cand: Candidate, blocks, lex) -> dict[str, float]:
    if cand.end == cand.offset:
        # 너비 0 마커(스타일 선언) — 조사가 붙을 표면이 없다. 꼬리 첫 글자로
        # 재면 `은행…` `이사회…` 처럼 조사 글자로 시작하는 제목이 억울하게 깎인다.
        return {ID: scoring.PARTICLE_CLEAN}
    tail = cand.tail
    attached = lex.josa.attached(tail) or lex.josa.chained_reference(tail)
    if not attached:
        return {ID: scoring.PARTICLE_CLEAN}

    out = {ID: scoring.PARTICLE_ATTACHED}
    near = tail[:scoring.REFERENT_WINDOW]
    hit = lex.predicates.first_in(near)
    if hit:
        out[f"{ID}:referent"] = scoring.PARTICLE_REFERENT
    return out
