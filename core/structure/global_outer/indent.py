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

# --- 계열 쪼개기 (한 계열이 여러 깊이에 나타날 때) --------------------------
# 뭉치를 자르는 간격. 이보다 벌어지면 다른 깊이로 본다. 실측(상품설명서)에서
# 진짜 간격은 0.022~0.028 이고 뭉치 내부 퍼짐은 0.000~0.032 다.
SPLIT_GAP = 0.02
# 뭉치가 이보다 작으면 깊이로 인정하지 않는다 — 한두 건의 병합 잡음이 칸을
# 만들면 사다리가 잘게 부서진다.
SPLIT_MIN = 3
# 계열 안에서 이 비중은 넘어야 깊이로 인정한다(개수만으로는 곁가지를 못 거른다).
SPLIT_SHARE = 0.1
# 한 계열이 이보다 여러 깊이에 나타나는 일은 드물다 — 그보다 많이 갈리면
# 깊이가 아니라 판형 흔들림으로 보고 쪼개지 않는다. 실측(상품설명서)에서
# `가.` 는 네 깊이(20% · 17% · 16% · 47%)에 고루 나타난다 — 130쪽짜리 문서의
# 중첩 목록에서는 드문 일이 아니다.
SPLIT_MAX_GROUPS = 4


def _x(c: Candidate) -> Optional[float]:
    """이 후보가 그려진 왼쪽 끝 — **글자가 실제로 시작하는 자리**.

    `bbox[0]` 이 아니라 `text_x` 를 쓴다. 들여쓰기를 좌표가 아니라 **선행 공백
    문자**로 표현하는 조판이 흔한데(실측 2026-08-11 상품설명서: `5)` 와 그 아래
    목 `가.` 가 bbox 로는 둘 다 0.1709, 실제 글자는 0.1709 대 0.1932), bbox 만
    보면 서로 다른 층이 같은 자리로 읽혀 이 증거가 통째로 죽는다.
    text_x 를 못 잰 파서·문서에서는 예전처럼 bbox 로 물러선다.
    """
    if c.text_x is not None:
        return c.text_x
    return c.bbox[0] if c.bbox else None


def left(cands: list[Candidate], page_width: dict[int, float]) -> Optional[float]:
    """계열의 왼쪽 들여쓰기 중앙값 (페이지 폭 대비 0~1). 잴 수 없으면 None."""
    xs = []
    for c in cands:
        if c.offset != 0:
            continue                      # 블록 중간 마커는 들여쓰기를 말하지 않는다
        x, w = _x(c), page_width.get(c.page)
        if x is not None and w:
            xs.append(x / w)
    if len(xs) < MIN_N:
        return None
    return statistics.median(xs)


def spread(cands: list[Candidate], page_width: dict[int, float]) -> float:
    xs = sorted(_x(c) / page_width[c.page] for c in cands
                if c.offset == 0 and _x(c) is not None and page_width.get(c.page))
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


def split(cands: list[Candidate], page_width: dict[int, float]) -> dict:
    """한 계열이 **여러 깊이에 나타나면** 들여쓰기 뭉치로 쪼갠다.

    사다리는 계열마다 칸을 하나씩 준다. 그런데 같은 표기가 두 깊이에 재등장하는
    문서가 있다 — 실측(상품설명서 p.123): `나. 수시공시`(0.097)가 최상위인데
    `5)`(0.171) 아래의 목도 `가.`(0.193)다. 전역 순서 하나로는 "여기선 가.가
    위, 저기선 아래"를 표현할 수 없어서, 다수파를 따르고 소수파 구역이 통째로
    어긋난다.

    쪼개면 `가.@0` 과 `가.@1` 이 각자 칸을 받아 둘 다 표현된다. 서수 검사도
    칸 단위로 갈리므로 "나. 뒤에 가." 가 역행이 아니라 **새 하위 스코프 열기**로
    자동 해석된다 — 예외 규칙을 따로 두지 않아도 된다.

    **함부로 쪼개지 않는다**(fail-closed). 뭉치가 뚜렷이 갈리고, 각 뭉치가
    충분히 크고, 내부가 조밀할 때만. 아니면 아무것도 하지 않는다 — 잡음으로
    칸을 만들면 사다리가 잘게 부서져 증거가 얇아진다.
    """
    # 퍼짐(IQR)으로 진입을 막지 않는다. IQR 은 꼬리에 둔감해서 **소수 뭉치를
    # 통째로 못 본다** — 실측(상품설명서 `①`): 0.119(23건) · 0.149(170건) ·
    # 0.2145(41건) 로 세 깊이에 나타나는데 IQR 은 0.004 라 "퍼지지 않았다" 고
    # 말한다. 그 41 건이 바로 잘못 붙던 자리였다. 과분할은 아래의 비중·간격·
    # 개수 가드가 막는다 — 그쪽이 진짜 안전장치다.
    xs = [(c, _x(c) / page_width[c.page]) for c in cands
          if c.offset == 0 and _x(c) is not None and page_width.get(c.page)]
    if len(xs) < SPLIT_MIN * 2:
        return {}
    xs.sort(key=lambda t: t[1])

    groups: list[list] = [[xs[0]]]
    for prev, cur in zip(xs, xs[1:]):
        (groups.append([cur]) if cur[1] - prev[1] > SPLIT_GAP
         else groups[-1].append(cur))
    # 뭉치는 개수만이 아니라 **비중**도 있어야 깊이다 — 몇 건짜리 곁가지가 칸을
    # 하나 차지하면 그 칸의 증거가 얇아져 사다리 전체가 흔들린다.
    floor = max(SPLIT_MIN, int(len(xs) * SPLIT_SHARE))
    keep = [g for g in groups if len(g) >= floor]
    if not 2 <= len(keep) <= SPLIT_MAX_GROUPS:
        return {}
    for g in keep:                      # 뭉치 내부가 퍼져 있으면 깊이가 아니다
        v = [x for _, x in g]
        if v[len(v) * 3 // 4] - v[len(v) // 4] > MAX_SPREAD:
            return {}
    centers = [statistics.median([x for _, x in g]) for g in keep]
    if any(b - a < SPLIT_GAP for a, b in zip(centers, centers[1:])):
        return {}

    # 살아남은 뭉치에 번호를 주고, 어디에도 못 낀 후보는 **가장 가까운** 뭉치로
    # 보낸다 — 계열에서 떨어져 나가면 그 후보만 미등재가 되어 더 나쁘다.
    assigned = {id(c) for g in keep for c, _ in g}
    for i, g in enumerate(keep):
        for c, _ in g:
            c.indent_group = i
    for c, x in xs:
        if id(c) not in assigned:
            c.indent_group = min(range(len(centers)),
                                 key=lambda i: abs(centers[i] - x))
    # offset 이 0 이 아니라 못 잰 후보는 계열의 최다 뭉치로 — 칸이 없으면
    # 사다리에 미등재로 남는다.
    big = max(range(len(keep)), key=lambda i: len(keep[i]))
    for c in cands:
        if c.indent_group is None:
            c.indent_group = big
    return {"groups": len(keep), "centers": [round(x, 4) for x in centers],
            "sizes": [len(g) for g in keep]}
