#!/usr/bin/env python3
"""골든 쌍의 PDF 생성 — 원본 빈 템플릿에 값을 실제로 얹는다.

    python tools/make_golden_pdf.py

왜 이렇게 만드나
    골든 쌍을 마크다운/JSON 으로 두면 정합성 로직만 검증되고 **파싱 경로가 빠진다.**
    실제 체결본은 PDF 이고, 값이 표의 빈칸에 들어가 있어 도클링이 그걸 셀과 함께
    읽어내야 한다. 그 난이도를 골든 테스트가 반영해야 한다.

    그래서 `ss2207_special_trust.pdf`(빈 템플릿) 위에 값을 직접 스탬프해
    `contract_filled.pdf` 를 만든다. 레이아웃·표 구조·조항은 원본 그대로이고
    빈칸만 채워지므로, 실제 체결본에 가장 가까운 합성물이 된다.

    요약서는 원본이 없으므로 새로 생성한다(표 레이아웃 포함).

한계
    값은 지어낸 것이다. 손글씨가 아니라 텍스트 레이어로 들어가므로
    실제 자필 기재 체결본보다는 읽기 쉽다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT.parent / "first-agent" / "dataset" / "ss2207_special_trust.pdf"
OUT_DIR = ROOT / "data" / "golden_pairs" / "acct_001"

FONT_CANDIDATES = [
    "/home/jin/semi_conductor/analysis_ext/.fonts/NanumGothic-Regular.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/mnt/c/Windows/Fonts/malgun.ttf",
]

INK = (0.05, 0.15, 0.45)      # 파란 볼펜 — 인쇄된 본문(검정)과 구분되게
FS = 9.0


def font_path() -> str:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    raise SystemExit("한글 폰트를 찾지 못했습니다: " + ", ".join(FONT_CANDIDATES))


class Stamper:
    """앵커 텍스트를 찾아 그 옆/안에 값을 써 넣는다.

    절대 좌표를 하드코딩하지 않는다 — 원본이 조금 바뀌어도 앵커만 있으면 따라간다.
    """

    def __init__(self, page: fitz.Page, font: str):
        self.page = page
        self.font = font
        self.misses: list[str] = []

    def rect(self, anchor: str, nth: int = 0, near_y: float | None = None) -> fitz.Rect | None:
        hits = self.page.search_for(anchor)
        if not hits:
            self.misses.append(anchor)
            return None
        if near_y is not None:
            hits = sorted(hits, key=lambda r: abs(r.y0 - near_y))
        return hits[nth] if nth < len(hits) else hits[0]

    def put(self, x: float, y_top: float, text: str, size: float = FS,
            color=INK) -> None:
        self.page.insert_text((x, y_top + size * 0.85), text,
                              fontname="ko", fontfile=self.font,
                              fontsize=size, color=color)

    def after(self, anchor: str, text: str, dx: float = 6, dy: float = 0,
              nth: int = 0, near_y: float | None = None, size: float = FS) -> None:
        r = self.rect(anchor, nth, near_y)
        if r:
            self.put(r.x1 + dx, r.y0 + dy, text, size)

    def before(self, anchor: str, text: str, dx: float = 6, dy: float = 0,
               nth: int = 0, near_y: float | None = None, size: float = FS) -> None:
        r = self.rect(anchor, nth, near_y)
        if r:
            w = fitz.get_text_length(text, fontsize=size, fontname="helv") * 1.3
            self.put(r.x0 - w - dx, r.y0 + dy, text, size)

    def check(self, anchor: str, nth: int = 0, near_y: float | None = None) -> None:
        """[  ] 또는 □ 안에 체크 표시."""
        r = self.rect(anchor, nth, near_y)
        if r:
            self.put(r.x0 + 1.5, r.y0 - 0.5, "√", FS + 1)


def fill_appendix1(page: fitz.Page, font: str) -> Stamper:
    """[별지1] 신탁계약 세부내역 — 실제 필드 구성에 맞춰 값 기재."""
    s = Stamper(page, font)

    # 상단 계약일
    s.before("년        월        일", "2024", dx=2)

    # 계좌번호 (계약서 링크 없음)
    s.after("계좌번호", "123-45-678901", dx=32)

    # 신탁금액 [계약서제2조]  "금 ____ 원정 (\ ____)"
    s.before("원정", "일억", dx=8, near_y=143)
    s.after("(\\", "100,000,000", dx=4, near_y=143)

    # 신탁기간 [계약서제3조]  "20__년 __월 __일부터  20__년 __월 __일까지"
    r = s.rect("일부터", near_y=164)
    if r:
        s.put(r.x0 - 118, r.y0, "24     6      3")
        s.put(r.x0 + 120, r.y0, "27     6      2")

    # 운용내역 통지여부 [계약서제7조]
    s.check("[  ] 통지 요청", near_y=185)
    s.check("□ 이메일", near_y=185)

    # 신탁보수 [계약서제12조]
    #   기본보수는 원본에 "기타특약사항에 기재" 가 이미 인쇄되어 있다 — 그것이 곧 계약서 값이다.
    #   수익보수: "(        )를 초과하는 이익  X (    )%"
    r = s.rect("를 초과하는 이익", near_y=225)
    if r:
        s.put(r.x0 - 100, r.y0, "연 3%")
    r = s.rect("X (", near_y=239)
    if r:
        s.put(r.x1 + 4, r.y0, "15")

    # 이익계산 및 지급 [계약서제13조]
    s.after("지급주기", "매월", dx=10, near_y=256)
    s.after("원금지급비율", "0%", dx=10, near_y=256)
    r = s.rect("~", near_y=277)
    if r:
        s.put(r.x0 - 62, r.y0, "2024.07.01")
        s.put(r.x1 + 6, r.y0, "2027.06.02")
    s.after("지급계좌", "123-45-678901", dx=10, near_y=277)

    # 중도해지수수료 [계약서제15조] — 3개 구간 선택 + 요율 기재
    tiers = [
        ("신탁계약일로부터 (___) 미만 경과 시 : 해지신탁금의 (___)%", ["1년", "0.5"]),
        ("신탁계약일로부터 (___) 이상 (___) 미만 경과 시 : 해지신탁금의 (___)", ["1년", "2년", "0.3"]),
        ("신탁계약일로부터 (___) 이상 경과 시 : 해지신탁금의 (___)%", ["2년", "0"]),
    ]
    for line, values in tiers:
        r = s.rect(line)
        if not r:
            continue
        s.put(r.x0 - 14, r.y0 - 0.5, "√", FS + 1)
        # (___) 자리에 값을 순서대로. 줄 안에서 "(___)" 위치를 찾아 각각 채운다.
        blanks = [h for h in page.search_for("(___)") if abs(h.y0 - r.y0) < 3]
        blanks.sort(key=lambda h: h.x0)
        for h, v in zip(blanks, values):
            s.put(h.x0 + 2.5, h.y0, v, FS - 1.5)

    # 신탁자금 운용방법 1~24 — 1, 3, 10 선택
    for label in ["1. 채무증권", "3. 수익증권", "10. 금융기관에의 예치 A"]:
        s.check(label)

    return s


def fill_detail_instruction(page: fitz.Page, font: str) -> None:
    """세부 운용지시 표 — 운용대상 종류 / 최소·최대 편입비중 / 세부내용."""
    s = Stamper(page, font)
    r = s.rect("운용대상 종류")
    if not r:
        return
    rows = [
        ("국고채권", "30", "50", "잔존만기 3년 이내"),
        ("A0등급 이상 회사채", "20", "40", "잔존만기 2년 이내"),
        ("금융기관 예치", "10", "30", "정기예금"),
    ]
    x = [r.x0, r.x0 + 118, r.x0 + 196, r.x0 + 274]
    for i, row in enumerate(rows):
        y = r.y1 + 4 + i * 13
        for xi, cell in zip(x, row):
            s.put(xi, y, cell, FS - 0.5)


def build_summary_pdf(out: Path, font: str) -> None:
    """투자요약서 — 원본이 없으므로 새로 만든다. 표 레이아웃을 포함해 실제 요약서에 가깝게."""
    doc = fitz.open()
    page = doc.new_page(width=595.32, height=841.92)

    def text(x, y, s, size=9.5, bold=False, color=(0, 0, 0)):
        page.insert_text((x, y), s, fontname="ko", fontfile=font,
                         fontsize=size, color=color)

    def row(y, label, value, x0=60, xm=210, x1=540):
        page.draw_line((x0, y + 4), (x1, y + 4), color=(0.8, 0.8, 0.8), width=0.5)
        text(x0 + 6, y, label)
        text(xm, y, value)

    text(60, 70, "투자요약서", 18)
    text(60, 92, "삼성증권 특정금전신탁 (일반형)", 10, color=(0.35, 0.35, 0.35))
    text(60, 106, "작성일 2024.06.03", 9, color=(0.35, 0.35, 0.35))
    page.draw_line((60, 118), (540, 118), color=(0.2, 0.2, 0.2), width=1.0)

    y = 148
    text(60, y, "1. 계약 개요", 11); y += 20
    page.draw_line((60, y - 12), (540, y - 12), color=(0.6, 0.6, 0.6), width=0.7)
    for label, value in [("계좌번호", "12345678901"),
                         ("투자금액", "100,000,000원"),
                         ("투자기간", "24.6.3 ~ 27.6.2"),
                         ("만기일", "2027-06-02")]:
        row(y, label, value); y += 22

    y += 14
    text(60, y, "2. 보수 및 수수료", 11); y += 20
    page.draw_line((60, y - 12), (540, y - 12), color=(0.6, 0.6, 0.6), width=0.7)
    for label, value in [("기본보수", "연 0.8%"),
                         ("성과보수", "기준수익률(연 3%) 초과분의 15.00%")]:
        row(y, label, value); y += 22

    y += 10
    text(66, y, "중도해지수수료", 10); y += 18
    page.draw_line((60, y - 10), (540, y - 10), color=(0.6, 0.6, 0.6), width=0.7)
    for label, value in [("1년 미만", "해지신탁금의 0.5%"),
                         ("1년 이상 2년 미만", "해지신탁금의 0.2%"),
                         ("2년 이상", "0%")]:
        row(y, label, value, x0=72); y += 20

    y += 14
    text(60, y, "3. 이익 지급", 11); y += 20
    page.draw_line((60, y - 12), (540, y - 12), color=(0.6, 0.6, 0.6), width=0.7)
    for label, value in [("지급주기", "분기"),
                         ("원금지급비율", "0%"),
                         ("지급기간", "2024.7.1 ~ 2027.6.2")]:
        row(y, label, value); y += 22

    y += 14
    text(60, y, "4. 운용", 11); y += 20
    page.draw_line((60, y - 12), (540, y - 12), color=(0.6, 0.6, 0.6), width=0.7)
    row(y, "운용방법", "수익증권, 채무증권, 금융기관에의 예치 A"); y += 22
    row(y, "투자전략", "국고채권 30~50%, A0등급 이상 회사채 20~40%, 금융기관 예치 10~30%"); y += 30

    text(60, y, "5. 유의사항", 11); y += 18
    text(66, y, "이 상품은 실적배당상품으로 원금 손실이 발생할 수 있으며,", 9)
    text(66, y + 14, "예금자보호법에 따른 보호 대상이 아닙니다.", 9)

    doc.save(out)
    doc.close()


def main() -> int:
    if not SRC.exists():
        print(f"원본을 찾지 못했습니다: {SRC}", file=sys.stderr)
        return 1
    font = font_path()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(SRC))
    s = fill_appendix1(doc[4], font)
    fill_detail_instruction(doc[4], font)
    out_contract = OUT_DIR / "contract_filled.pdf"
    doc.save(str(out_contract))
    doc.close()

    out_summary = OUT_DIR / "summary.pdf"
    build_summary_pdf(out_summary, font)

    print(f"생성: {out_contract.relative_to(ROOT)}  ({out_contract.stat().st_size//1024} KB)")
    print(f"생성: {out_summary.relative_to(ROOT)}  ({out_summary.stat().st_size//1024} KB)")
    if s.misses:
        print("앵커를 못 찾은 항목:", ", ".join(sorted(set(s.misses))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
