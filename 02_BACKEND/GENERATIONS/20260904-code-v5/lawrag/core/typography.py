r"""T2c. 타이포그래피 — 글자의 **크기·굵기·간격**을 요소에 붙인다.

    annotate(path, elements) -> stats

## 왜 필요한가

지금까지 구조 판별이 쓴 신호는 텍스트·offset·bbox 셋뿐이었다. 그래서 **마커 없는
제목**을 원리적으로 못 잡는다:

    삼성증권 디폴트옵션 안정형 투자형 포트폴리오 1     ← 번호도 불릿도 없다
    『퇴직연금용 정기예금(만기지급형)』특약              ← 괄호가 마커처럼 보이지만 아니다

사람은 이걸 **크고 굵고 위아래가 트여 있어서** 제목으로 읽는다. 그 축이 데이터에
없으면 판별기가 아무리 정교해도 볼 수 없다.

## 왜 docling 이 아니라 PyMuPDF 인가

docling 의 `TextItem` 은 레이아웃 모델의 **분류 결과**(`section_header` 등)만 주고
글자 크기를 주지 않는다. 그 분류는 힌트로만 쓰기로 이미 정해져 있다(§2.2). 반면
PyMuPDF 의 `page.get_text("dict")` 는 span 마다 `size` 와 `flags`(굵기 비트)를 준다.
이미 의존성에 있다(`is_born_digital` 이 쓴다) — 새 의존성이 늘지 않는다.

## 정렬 — 두 파서의 좌표를 맞춘다

docling prov bbox 는 **BOTTOMLEFT**, PyMuPDF 는 **TOPLEFT** 다. 여기서 TOPLEFT 로
통일해 비교한다. span 의 중심이 요소 상자 안에 들어가면 그 요소의 것으로 본다.

한 요소에 여러 span 이 붙으므로 대푯값을 정해야 한다.

    크기   **글자 수로 가중한 최빈값.** 평균은 각주 한 조각에 끌려가고, 최댓값은
           위첨자 하나에 속는다. "이 줄을 이루는 대부분의 글자가 몇 pt 인가"가 맞다.
    굵기   굵은 글자의 **비율**. `bold` 는 그 비율이 과반인가로 접는다. 제목 일부만
           굵은 경우(`『퇴직연금용 정기예금』**특약**`)를 놓치지 않으려고 비율도 남긴다.

## 상대값으로 남기는 이유

문서마다 본문 크기가 다르다(10pt 도 있고 9pt 도 있다). 절대 pt 로 임계를 걸면 문서를
하나 붙일 때마다 숫자가 하나씩 는다. 그래서 **본문 중앙값 대비 배율**(`size_ratio`)을
함께 싣는다 — 판별은 이쪽을 본다.

이 단계는 **판정을 하지 않는다.** 무엇이 제목인지는 제안자와 가드가 정한다(§4 S0).
여기서는 잴 수 있는 것만 재서 실어 나른다.
"""

from __future__ import annotations

import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from lawrag.core import geometry

# PyMuPDF 의 span flags 중 굵기 비트 (fitz.TEXT_FONT_BOLD)
BOLD_BIT = 1 << 4
# 글꼴 이름에 이게 들어가면 굵은 것으로 본다 — flags 를 안 세우는 PDF 가 흔하다.
BOLD_NAMES = ("bold", "heavy", "black", "semib", "demib", "extrab")
# 굵은 글자가 이 비율을 넘으면 그 요소를 '굵다' 로 본다
BOLD_T = 0.6
# 이보다 글자가 적은 쪽은 자기 최빈 크기를 믿지 않는다(표지·간지) — 문서 최빈을 쓴다
MIN_PAGE_CHARS = 400
# span 중심이 요소 상자를 살짝 벗어나는 일이 흔하다. 이 여유까지는 그 요소의 것으로 본다.
PAD = 1.5


def _is_bold(span: dict) -> bool:
    """굵기 판정. **이름으로 맞히는 것은 여기까지가 한계다.**

    실측(ss2207): flags 에 굵기 비트가 **하나도** 없고 글꼴이 `SECGCL`(Light)·
    `SECGCM`(Medium)·`SECGCR`(Regular) 이다. 삼성 사내 글꼴이 굵기를 이름 끝 한
    글자로 표현하는데, 이런 규약은 회사마다 다르고 표준이 없다.

    그래서 여기서 억지로 규칙을 늘리지 않는다. 대신 `font_name` 을 요소에 그대로
    실어 보낸다 — 문서군을 아는 쪽이 "이 문서에서는 M 이 굵은 것이다" 를 정하는 편이,
    파서가 세계의 모든 글꼴 이름 규약을 맞히려 드는 것보다 낫다.
    """
    if int(span.get("flags", 0)) & BOLD_BIT:
        return True
    name = str(span.get("font", "")).lower()
    return any(k in name for k in BOLD_NAMES)


def _page_spans(page) -> list[dict]:
    """이 쪽의 span 들 — (bbox_TOPLEFT, size, bold, 글자수, 잉크 시작 x).

    `rawdict` 로 읽는 이유는 `ink_x` 하나 때문이다. span 의 bbox 는 **선행 공백을
    포함**해서 시작한다 — 들여쓰기를 공백 문자로 표현한 조판에서는 span bbox 만
    보면 서로 다른 층이 같은 x 로 읽힌다(실측 2026-08-11: `가.` span bbox 101.72,
    첫 글자 '가' 는 115.04). 글자 단위로 내려가야 진짜 왼쪽 끝이 나온다.
    """
    out: list[dict] = []
    data = page.get_text("rawdict")
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                chars = span.get("chars") or []
                text = "".join(c.get("c", "") for c in chars).strip()
                if not text:
                    continue
                bb = span.get("bbox")
                if not bb:
                    continue
                ink = next((c for c in chars if c.get("c", "").strip()), None)
                ink_x = float(ink["bbox"][0]) if ink and ink.get("bbox") else float(bb[0])
                out.append({"bbox": list(bb), "size": round(float(span.get("size", 0)), 2),
                            "bold": _is_bold(span), "n": len(text),
                            "font": str(span.get("font", "")), "ink_x": ink_x})
    return out


def _dominant(spans: list[dict]) -> tuple[Optional[float], float, str]:
    """(글자수 가중 최빈 크기, 굵은 글자 비율, 최빈 글꼴). span 이 없으면 (None, 0.0, "")."""
    if not spans:
        return None, 0.0, ""
    weight: Counter = Counter()
    fonts: Counter = Counter()
    total = bold = 0
    for s in spans:
        weight[s["size"]] += s["n"]
        fonts[s["font"]] += s["n"]
        total += s["n"]
        if s["bold"]:
            bold += s["n"]
    size = weight.most_common(1)[0][0] if weight else None
    font = fonts.most_common(1)[0][0] if fonts else ""
    return size, (bold / total if total else 0.0), font


def ensure_text_x(path: str | Path, elements: list) -> int:
    """캐시에서 되살린 요소에 `text_x` 가 없으면 채운다 — 몇 개를 채웠는지 돌려준다.

    `annotate` 는 파싱 때 한 번 도는데, 그 전에 굳은 `parse.json` 에는 이 축이
    없다. 재파싱(docling 몇 분)을 강요하지 않으려고 이 값만 다시 잰다 —
    PyMuPDF 텍스트 추출뿐이라 싸다. 이미 있으면 아무것도 하지 않는다.
    """
    if not elements or all(getattr(e, "text_x", None) is not None
                           for e in elements if getattr(e, "bbox", None)):
        return 0
    import fitz

    try:
        doc = fitz.open(str(path))
    except Exception:                                  # pragma: no cover
        return 0
    try:
        by_page = {i: _page_spans(pg) for i, pg in enumerate(doc, start=1)}
        heights = {i: float(pg.rect.height) for i, pg in enumerate(doc, start=1)}
    finally:
        doc.close()
    n = 0
    for e in elements:
        if getattr(e, "text_x", None) is not None or not getattr(e, "bbox", None):
            continue
        h, spans = heights.get(e.page), by_page.get(e.page)
        if not h or not spans:
            continue
        box = geometry.to_topleft(e.bbox, getattr(e, "bbox_origin", "BOTTOMLEFT"), h)
        hit = [s for s in spans if geometry.holds_center(box, s["bbox"], PAD)]
        if hit:
            e.text_x = round(min(s["ink_x"] for s in hit), 2)
            n += 1
    return n


def annotate(path: str | Path, elements: list) -> dict[str, Any]:
    """요소마다 `font_size` · `bold` · `bold_ratio` · `gap_before` · `size_ratio` 를 심는다.

    요소 리스트를 제자리에서 고치고 통계를 돌려준다. PyMuPDF 로 열 수 없거나 텍스트
    레이어가 없으면 **아무것도 심지 않고** 그 사실을 통계에 남긴다 — 신호가 없는 것과
    0 인 것은 다르다.
    """
    import fitz

    stats: dict[str, Any] = {"typography": "off", "sized": 0, "bolded": 0}
    try:
        doc = fitz.open(str(path))
    except Exception:                                  # pragma: no cover
        stats["typography"] = "열 수 없음"
        return stats

    try:
        by_page: dict[int, list[dict]] = {}
        heights: dict[int, float] = {}
        for i, page in enumerate(doc, start=1):
            heights[i] = float(page.rect.height)
            by_page[i] = _page_spans(page)
    finally:
        doc.close()

    if not any(by_page.values()):
        stats["typography"] = "span 없음 (텍스트 레이어 부재)"
        return stats

    # --- 요소마다 대푯값 ---------------------------------------------------
    for e in elements:
        if not getattr(e, "bbox", None):
            continue
        h = heights.get(e.page)
        spans = by_page.get(e.page)
        if not h or not spans:
            continue
        box = geometry.to_topleft(e.bbox, getattr(e, "bbox_origin", "BOTTOMLEFT"), h)
        hit = [s for s in spans if geometry.holds_center(box, s["bbox"], PAD)]
        # 글자가 **실제로 시작하는** x. 요소 bbox 의 왼쪽 끝과 다를 수 있다:
        # 들여쓰기를 좌표가 아니라 **선행 공백 문자**로 표현하는 조판이 흔하고
        # (실측 2026-08-11 상품설명서: `가.` 앞 공백 4개 → bbox 0.1709 인데
        # 글자는 0.1932 에서 시작), 그러면 bbox 만 보는 들여쓰기 증거는 서로
        # 다른 층을 같은 자리로 읽는다. _page_spans 는 빈 span 을 이미 버리므로
        # 여기 남은 것은 전부 잉크다.
        if hit:
            e.text_x = round(min(s["ink_x"] for s in hit), 2)
            if e.bbox and e.text_x - e.bbox[0] > 1.0:
                stats["indented_by_space"] = stats.get("indented_by_space", 0) + 1
        size, ratio, font = _dominant(hit)
        if size is None:
            continue
        e.font_size = size
        e.bold_ratio = round(ratio, 3)
        e.bold = ratio >= BOLD_T
        e.font_name = font
        stats["sized"] += 1
        stats["bolded"] += int(e.bold)

    # --- 본문 크기 — **쪽마다 따로** 잡는다 ---------------------------------
    #
    # 처음에는 문서 전체의 최빈 크기를 썼는데 양식 문서에서 무너졌다. 실측
    # (신한은행 신규가입신청서 11쪽):
    #
    #     문서 전체 최빈   4.92pt      ← 6·8쪽의 깨알 인쇄가 글자 수를 지배
    #     쪽별 최빈        8.76 8.76 7.38 8.3 8.3 4.92 8.3 4.92 8.76 8.76 8.3
    #
    # 전체 최빈을 분모로 쓰면 **본문 문장까지 1.78배**가 되어 530개 요소가 "본문보다
    # 크다"로 잡혔다. 배율의 뜻은 "이 줄이 **그 쪽의** 본문보다 큰가"이므로 분모도
    # 그 쪽에서 와야 한다. 실측에서 ss2207·하나은행은 쪽별 최빈이 문서 최빈과 같아
    # 달라지는 것이 없다 — 양식 문서만 고쳐진다.
    #
    # 글자가 적은 쪽(표지·간지)의 최빈은 잡음이므로 문서 최빈으로 물러선다.
    weight: Counter = Counter()
    page_weight: dict[int, Counter] = {}
    for pno, spans in by_page.items():
        c: Counter = Counter()
        for s in spans:
            c[s["size"]] += s["n"]
            weight[s["size"]] += s["n"]
        page_weight[pno] = c
    body = weight.most_common(1)[0][0] if weight else 0.0
    page_body: dict[int, float] = {}
    for pno, c in page_weight.items():
        total = sum(c.values())
        page_body[pno] = c.most_common(1)[0][0] if total >= MIN_PAGE_CHARS else body
    stats["body_size"] = body
    stats["page_body"] = {str(k): v for k, v in sorted(page_body.items())}
    stats["size_hist"] = [[sz, n] for sz, n in weight.most_common(8)]

    for e in elements:
        size = getattr(e, "font_size", None)
        base = page_body.get(e.page) or body
        if size and base:
            e.size_ratio = round(size / base, 3)

    # --- 앞 요소와의 세로 간격 --------------------------------------------
    # 제목은 위가 트여 있다. 같은 쪽 안에서만 잰다 — 쪽을 넘으면 뜻이 없다.
    prev_bottom: dict[int, float] = {}
    for e in elements:
        if not getattr(e, "bbox", None):
            continue
        h = heights.get(e.page)
        if not h:
            continue
        box = geometry.to_topleft(e.bbox, getattr(e, "bbox_origin", "BOTTOMLEFT"), h)
        last = prev_bottom.get(e.page)
        if last is not None:
            e.gap_before = round(max(0.0, box[1] - last), 2)
        prev_bottom[e.page] = max(box[3], last if last is not None else box[3])

    gaps = [g for g in (getattr(e, "gap_before", None) for e in elements) if g is not None]
    stats["typography"] = "on"
    stats["median_gap"] = round(statistics.median(gaps), 2) if gaps else None
    return stats
