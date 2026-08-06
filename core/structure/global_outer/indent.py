"""들여쓰기 — 계층의 **기하 증거** (S3).

    order(a_blocks, b_blocks) -> a 가 b 보다 확실히 얕은가

문서가 계층을 눈에 보이게 표현하는 방식 그대로를 읽는다. 실측(페이지 폭 대비 왼쪽 x):

    KSB                      KSB-D                    KOFIA-R
      kr_장         0.050      kr_장        0.119       roman_upper   0.094
      kr_절         0.050      kr_article   0.119       dot_number:1  0.100
      kr_article    0.057      dot_number:1 0.143       paren_number  0.119
      dot_number:1  0.084      circled      0.143       hangul_jamo   0.139
      circled       0.084      hangul_jamo  0.166       circled       0.141
      hangul_jamo   0.101      paren_number 0.190
      paren_number  0.101

세 문서 모두 중앙값 순서가 계층과 일치한다.

## 왜 이 증거가 필요한가 — 다른 증거가 못 미치는 자리가 있다

**리셋 정렬은 통번호 계열에 안 통한다.** 한국 법령의 조 번호는 장·절이 바뀌어도
리셋되지 않는다(실측 KSB: 장 1~8, 절 1,2,3|1,2,3, 조 1~69 연속). 조가 리셋을 안 하니
"리셋이 어디서 일어나나" 로는 장→조 를 영영 못 잡는다.

**덮음·사이-끼임은 희소 계열에 안 통한다.** 절은 6건뿐이라 자기 구간이 5개고,
장 8건과의 덮음이 20% 밖에 안 나온다. 실측에서 `kr_장 ↔ kr_절` 은 네 증거가 모두
침묵해 **순서 미정**으로 남았고, 그래서 절이 조와 같은 칸에 얹혔다.

들여쓰기는 계열이 몇 건이든, 번호가 리셋되든 말든 잰다.

## 동률은 간선을 놓지 않는다

장과 절이 같은 0.050, 항과 호가 같은 0.084 로 나온다 — 문서가 그 둘을 같은 깊이로
그린 것이다. 억지로 가르지 않고 다른 증거에 넘긴다.

## 한계

Docling 이 헤더와 본문을 한 블록으로 붙이면 그 블록의 왼쪽 끝이 본문 들여쓰기가 된다.
그래서 **중앙값**을 쓰고(한두 건의 병합에 흔들리지 않게), 퍼짐이 크면 신뢰를 낮춘다.
"""

from __future__ import annotations

import statistics
from typing import Optional

from core.structure.model import Candidate

ID = "indent"
ROLE = "global_outer"
LANG = "any"
SURFACE = "들여쓰기 — 왼쪽 x 중앙값"

# 페이지 폭 대비 이만큼 차이가 나야 "확실히 얕다" 로 본다.
# 실측 최소 간격이 0.007(장 0.050 vs 조 0.057)이므로 그 절반으로 잡는다.
MIN_GAP = 0.004
# 퍼짐(사분위 범위)이 이보다 크면 그 계열의 들여쓰기를 믿지 않는다.
MAX_SPREAD = 0.06
# 이 개수 미만이면 중앙값이 흔들린다
MIN_N = 2


def left(cands: list[Candidate], page_width: dict[int, float]) -> Optional[float]:
    """계열의 왼쪽 들여쓰기 중앙값 (페이지 폭 대비 0~1). 잴 수 없으면 None."""
    xs = []
    for c in cands:
        if c.offset != 0 or not c.bbox:
            continue                      # 블록 중간 마커는 들여쓰기를 말하지 않는다
        w = page_width.get(c.page)
        if w:
            xs.append(c.bbox[0] / w)
    if len(xs) < MIN_N:
        return None
    return statistics.median(xs)


def spread(cands: list[Candidate], page_width: dict[int, float]) -> float:
    xs = sorted(c.bbox[0] / page_width[c.page] for c in cands
                if c.offset == 0 and c.bbox and page_width.get(c.page))
    if len(xs) < 4:
        return 0.0
    q1, q3 = xs[len(xs) // 4], xs[len(xs) * 3 // 4]
    return q3 - q1


def order(a: list[Candidate], b: list[Candidate],
          page_width: dict[int, float]) -> Optional[tuple[float, float]]:
    """a 가 b 보다 확실히 얕으면 (a 중앙값, b 중앙값). 아니면 None.

    동률이거나 퍼짐이 크면 판정하지 않는다 — 다른 증거에 넘긴다.
    """
    la, lb = left(a, page_width), left(b, page_width)
    if la is None or lb is None:
        return None
    if spread(a, page_width) > MAX_SPREAD or spread(b, page_width) > MAX_SPREAD:
        return None
    if lb - la >= MIN_GAP:
        return (la, lb)
    return None
