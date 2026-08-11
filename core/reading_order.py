r"""T2b. 읽기 순서 — 양식 페이지에서 뒤섞여 온 요소를 좌표로 다시 세운다.

    reorder(elements) -> (elements, stats, warnings)

## 왜 필요한가 (실측 ss2207)

본문 페이지(p1~p4)는 읽기 순서가 좌표와 100% 일치한다. 그런데 양식 페이지는 다르다:

    p5  요소 71개 중 위로 되돌아간 자리 7개 (10%)
    p6  요소 17개 중 3개 (19%)
    p7  요소 32개 중 4개 (13%)

p7 은 제목 `특정금전신탁 변경계약서` 가 231개 중 **222번째**로 나온다. 그 페이지에서는
"읽기 순서대로 훑으며 마커를 만나면 구역을 연다"(structurize §3.1)가 통째로 성립하지
않는다 — 제목이 자기 내용보다 뒤에 오기 때문이다.

칸이 격자로 배치된 양식에서 레이아웃 모델이 칸 순서를 어떻게 펴야 할지 확신하지 못한
결과다. 우리는 **좌표를 갖고 있으므로** 다시 세울 수 있다.

## 손대는 범위를 좁힌다

읽기 순서를 우리가 다시 정하는 것은 위험하다 — 2단 편집 같은 레이아웃에서는 좌표
정렬이 오히려 원본보다 나쁘다. 그래서

    · **역행이 임계를 넘은 쪽만** 손댄다. 멀쩡한 쪽은 건드리지 않는다.
    · 다시 세운 결과가 **실제로 나아졌을 때만** 채택한다(역행 수가 줄어야 한다).
    · 무엇을 어떻게 바꿨는지 통계와 경고로 남긴다. 조용히 바꾸지 않는다.
"""

from __future__ import annotations

from core import geometry

# 같은 행으로 묶는 세로 허용오차(pt). 본문 줄높이보다 작게 잡는다.
ROW_TOL = 6.0
# 이 비율을 넘게 역행하면 그 페이지를 다시 세운다.
REORDER_T = 0.05
# 역행으로 세는 최소 높이차(pt) — 같은 행 안의 미세한 위아래는 역행이 아니다.
INVERSION_TOL = 8.0


def _inversions(elements) -> int:
    """앞 요소보다 **뚜렷하게 위로** 되돌아간 자리의 수."""
    tops = [geometry.screen_top(e.bbox, e.bbox_origin) for e in elements]
    tops = [t for t in tops if t is not None]
    return sum(1 for a, b in zip(tops, tops[1:]) if b < a - INVERSION_TOL)


def _sorted_by_coords(elements) -> list:
    """행 띠로 묶고, 띠 안에서는 왼쪽부터.

    좌표가 없는 요소는 **바로 앞 요소에 붙여** 둔다. 자기 자리를 말하지 못하는 것을
    맨 앞이나 맨 뒤로 몰면 문장이 끊긴다.
    """
    keys: list[tuple[float, float]] = []
    last = (0.0, 0.0)
    for e in elements:
        t = geometry.screen_top(e.bbox, e.bbox_origin)
        if t is None:
            keys.append(last)
            continue
        last = (float(round(t / ROW_TOL)), float(e.bbox[0]))
        keys.append(last)
    order = sorted(range(len(elements)), key=lambda i: (keys[i][0], keys[i][1], i))
    return [elements[i] for i in order]


def reorder(elements: list) -> tuple[list, dict, list[str]]:
    """양식 페이지의 읽기 순서를 좌표로 다시 세운다.

    `elements` 는 건드리지 않고 새 리스트를 돌려준다. `index` 는 0부터 다시 매긴다 —
    다운스트림이 `element.index` 를 리스트 위치로 쓴다(`structurize._units`).
    """
    stats: dict = {"reordered_pages": []}
    warnings: list[str] = []

    by_page: dict[int, list] = {}
    for e in elements:
        by_page.setdefault(e.page, []).append(e)

    out: list = []
    for pno in sorted(by_page):
        page_els = by_page[pno]
        n_pairs = max(1, len(page_els) - 1)
        before = _inversions(page_els)
        if before / n_pairs > REORDER_T:
            fixed = _sorted_by_coords(page_els)
            after = _inversions(fixed)
            if after < before:                 # 나아졌을 때만 채택한다
                stats["reordered_pages"].append(
                    {"page": pno, "before": before, "after": after,
                     "elements": len(page_els)})
                page_els = fixed
        out.extend(page_els)

    for i, e in enumerate(out):
        e.index = i

    if stats["reordered_pages"]:
        pages = ", ".join(f"p{r['page']}({r['before']}→{r['after']})"
                          for r in stats["reordered_pages"])
        warnings.append(
            f"읽기 순서가 뒤섞인 쪽을 좌표로 다시 세웠습니다: {pages} "
            f"— 양식 레이아웃이라 원본 순서를 믿을 수 없습니다")
    return out, stats, warnings
