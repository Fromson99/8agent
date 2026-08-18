"""좌표 공통 연산 — 원점(origin)이 섞인 bbox 를 다루는 단 한 곳.

docling prov 는 BOTTOMLEFT, 표 셀·PyMuPDF 는 TOPLEFT 로 온다(`parse_adapter._prov`).
파싱 단계는 원점을 통일하지 않고 그대로 실어 보내므로(페이지 높이를 모른다), 통일은
**쓰는 쪽**이 페이지 높이를 갖고 여기 함수들로 한다.

같은 변환이 typography · grid_recover · reading_order 에 제각각 복붙되어 있었다.
복붙된 좌표 코드는 한 곳만 고쳐지는 사고의 온상이라 여기로 모은다. 판정 임계값
(pad 등)은 **호출하는 쪽의 것**이다 — 이 모듈은 판단 없이 계산만 한다.
"""

from __future__ import annotations

from typing import Optional


def to_topleft(bbox: list[float], origin: str, height: float) -> list[float]:
    """어떤 원점으로 왔든 TOPLEFT (x0, top, x1, bottom) 로.

    통일하지 않고 비교하면 위아래가 뒤집혀 엉뚱한 칸에 담긴다.
    """
    if str(origin).upper() == "BOTTOMLEFT":
        return [bbox[0], height - max(bbox[1], bbox[3]),
                bbox[2], height - min(bbox[1], bbox[3])]
    return [bbox[0], min(bbox[1], bbox[3]), bbox[2], max(bbox[1], bbox[3])]


def screen_top(bbox: Optional[list[float]], origin: str) -> Optional[float]:
    """화면 기준 '위쪽' 을 **하나의 축으로** — 값이 작을수록 위.

    BOTTOMLEFT 는 y 가 클수록 위, TOPLEFT 는 작을수록 위다. 페이지 높이 없이도
    같은 쪽 안에서의 **순서 비교**는 이 축 하나로 된다.
    """
    if not bbox:
        return None
    if str(origin).upper() == "BOTTOMLEFT":
        return -max(bbox[1], bbox[3])
    return min(bbox[1], bbox[3])


def center(box: list[float]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def holds(box: list[float], x: float, y: float, pad: float = 0.0) -> bool:
    """점 (x, y) 가 상자 안에 있는가. 세로는 min/max 로 접어 원점 방향과 무관하다."""
    return (box[0] - pad <= x <= box[2] + pad
            and min(box[1], box[3]) - pad <= y <= max(box[1], box[3]) + pad)


def holds_center(outer: list[float], inner: list[float], pad: float = 0.0) -> bool:
    """inner 상자의 **중심**이 outer 안에 있는가.

    겹침 면적이 아니라 중심을 쓴다 — 글자가 칸 경계를 살짝 넘는 일이 흔해서
    면적으로 재면 큰 상자가 다 가져간다.
    """
    cx, cy = center(inner)
    return holds(outer, cx, cy, pad)
