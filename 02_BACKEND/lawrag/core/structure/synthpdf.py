"""합성 PDF 조판 — 지면이 없는 문서를 검수 화면에 세우기 위한 것.

검수 화면은 "원본 PDF 위에 구조를 겹쳐 보이기"가 전부라, 지면 좌표가 없는
문서(법령 본문 XML, HWP·DOCX 변환분)는 그대로는 설 자리가 없다. 화면을 고치는
대신 **지면을 만들어 준다** — 블록을 위에서 아래로 흘려 찍고 그 좌표를 되돌려
받는다. 이후는 PDF 문서와 완전히 같은 길(viewer.payload · 페이지 PNG)이다.

처음 lawxml(법령 본문 XML)이 만든 조판기를 옮겨 왔다 — 좌표 규약(TOPLEFT,
A4, 여백)의 소유자가 한 곳이어야 lawxml 과 HWP 경로가 어긋나지 않는다.
"""
from __future__ import annotations

PAGE_W, PAGE_H = 595.32, 841.92
MARGIN = 50.0
LINE_H = 1.45

# paginate() 의 글자 크기 — 제목이 본문보다 커야 화면에서 경계가 보인다.
# 구조 판정은 이 크기를 보지 않는다(합성 좌표는 오버레이 전용, §2 Block.bbox).
HEADING_FONT = 12.0
BODY_FONT = 10.0
TABLE_FONT = 9.0


def _circ_no(ch: str) -> int:
    if len(ch) != 1:                # "①삭제" 처럼 붙어 온 번호 필드 방어
        ch = ch[:1] or " "
    o = ord(ch)
    if 0x2460 <= o <= 0x2473:       # ①-⑳
        return o - 0x2460 + 1
    if 0x3251 <= o <= 0x325F:       # ㉑-㉟
        return o - 0x3251 + 21
    if 0x32B1 <= o <= 0x32BF:       # ㊱-㊿
        return o - 0x32B1 + 36
    return 0


def _char_w(ch: str, size: float) -> float:
    # 실제 폰트 메트릭 대신 보수적 추정 — 넘치면 잘려 보이고, 남으면 여백일 뿐이다
    return size * (1.04 if ord(ch) > 0x2E7F or _circ_no(ch) else 0.62)


def _wrap(text: str, size: float, maxw: float) -> list[str]:
    lines: list[str] = []
    for para in text.splitlines() or [""]:
        cur, w = "", 0.0
        for ch in para:
            cw = _char_w(ch, size)
            if cur and w + cw > maxw:
                lines.append(cur)
                cur, w = "", 0.0
            cur += ch
            w += cw
        lines.append(cur)
    return lines or [""]


class Layout:
    """블록을 위에서 아래로 흘리며 합성 PDF 에 찍는다."""

    def __init__(self) -> None:
        import fitz
        self.doc = fitz.open()
        self.fitz = fitz
        self.page = None
        self.page_no = 0
        self.y = PAGE_H
        self._new_page()

    def _new_page(self) -> None:
        self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        self.page_no += 1
        self.y = MARGIN

    def put(self, text: str, indent: float, size: float) -> tuple[int, list[float]]:
        """텍스트 하나를 찍고 (page, TOPLEFT bbox) 를 돌려준다."""
        x0 = MARGIN + indent
        maxw = PAGE_W - MARGIN - x0
        lines = _wrap(text, size, maxw)
        lh = size * LINE_H
        if self.y + lh * min(len(lines), 2) > PAGE_H - MARGIN:
            self._new_page()
        top, page = self.y, self.page_no
        for line in lines:
            if self.y + lh > PAGE_H - MARGIN:
                self._new_page()
                if page == self.page_no - 1 and top == self.y:
                    page = self.page_no
            self.page.insert_text((x0, self.y + size), line,
                                  fontname="korea", fontsize=size)
            self.y += lh
        bottom = self.y
        self.y += lh * 0.35
        if page != self.page_no:
            # 쪽을 넘긴 블록 — bbox 는 시작 쪽 것만 남긴다 (오버레이는 근사면 충분)
            bottom = PAGE_H - MARGIN
        return page, [x0, top, x0 + maxw, bottom]


# 원문 들여쓰기를 지면에 옮길 때 넘지 않는 한도 — 그 너머는 글이 설 자리가 없다
MAX_INDENT = (PAGE_W - 2 * MARGIN) / 2


def _indent(e, default=0.0):
    """원문이 선언한 첫 줄 시작점(pt, 본문 영역 왼쪽 기준). DOCX 의 w:ind 만 싣는다."""
    twips = ((getattr(e, 'meta', None) or {}).get('docx') or {}).get('start_twips')
    if twips is None:
        return default
    return min(max(twips / 20.0, 0.0), MAX_INDENT)


def paginate(elements) -> bytes:
    """요소들을 합성 지면에 찍고, page·bbox(TOPLEFT) 를 **요소에 되돌려 심는다.**

    반환은 PDF 바이트. 요소를 고치는 이유: 이 좌표가 parse.json 으로 저장되면
    재해석(reinterpret)이 캐시에서 요소를 되살려도 오버레이가 그대로 성립한다 —
    합성을 한 번만 하고도 업로드와 재해석이 같은 화면을 얻는다.
    """
    lay = Layout()
    for e in elements:
        if e.table is not None:
            text, size = e.table.text(), TABLE_FONT
        elif e.is_picture:
            # 픽셀은 변환이 버렸다(lawrag/core/hwp5_md.py 한계) — 자리가 있었다는 사실만 찍는다
            text, size = e.text or "〔그림〕", BODY_FONT
        else:
            text, size = e.text, HEADING_FONT if e.is_heading else BODY_FONT
        page, bbox = lay.put(text or " ", _indent(e), size)
        e.page, e.bbox, e.bbox_origin = page, bbox, "TOPLEFT"
        if _indent(e, None) is not None:
            e.text_x = bbox[0]              # 원문이 선언한 첫 줄 시작점 — 들여쓰기 증거(S3)
    pdf = lay.doc.tobytes()
    lay.doc.close()
    return pdf
