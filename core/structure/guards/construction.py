"""국소 가드 — construction (SPEC §3.2, §5.1).

    완전형 (제N장 / 1. / ①)   +0.7
    파편   (제 3 장 / 3장)     −0.3

토큰이 아니라 **구성**이 잡혔는가를 본다. `장` 을 찾으면 문장·시장·공장·통장이 다
걸리지만 `제N장` 이라는 구성으로 잡으면 그것들이 전부 즉사한다 — 그 판정은 제안자의
완전형 패턴이 이미 했고, 여기서는 그 결과에 점수를 매긴다.

파편을 0 이 아니라 음수로 두는 이유: 자간이 벌어진 `제 3 장` 은 진짜 헤더일 수도
있으므로 죽이지는 않되, 완전형보다 뒤로 밀어 둔다. 블록위치가 좋으면(+0.8) 파편도
살아남는다 — 그것이 하드컷 대신 점수를 쓰는 이유다.
"""

from __future__ import annotations

from core.structure import scoring
from core.structure.model import Candidate

ID = "construction"
ROLE = "local_guard"
LANG = "any"
SURFACE = "완전형 / 파편"


def score(cand: Candidate, blocks, lex) -> dict[str, float]:
    # "style" 은 표면이 없는 대신 작성자가 제목이라 **선언**한 것이다(Word 스타일).
    # 완전형과 같게 본다 — 선언보다 완전한 구성은 없다.
    return {ID: (scoring.CONSTRUCTION_FULL if cand.construction in ("full", "style")
                 else scoring.CONSTRUCTION_FRAGMENT)}
