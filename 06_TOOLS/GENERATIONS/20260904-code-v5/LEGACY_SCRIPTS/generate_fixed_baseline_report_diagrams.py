#!/usr/bin/env python3
"""Generate diagrams for the ADR-0118 fixed research baseline report."""

from __future__ import annotations

from pathlib import Path

from PIL import ImageDraw

import generate_legal_rag_report_diagrams as base


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
OUTPUT_DIR = ROOT / "09_ARTIFACTS" / "LEGACY_ARTIFACTS" / "legal_rag_fixed_baseline_diagrams"
base.OUTPUT_DIR = OUTPUT_DIR


def _save(image, name: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / name
    image.save(path, format="PNG", optimize=True, dpi=(220, 220))
    return path


def fixed_overview() -> Path:
    image, draw = base.canvas(1080)
    base.title(
        draw,
        "최종 고정 연구구조: ADR-0118 v4b",
        "법체계 기반 회수와 비파괴 원자 claim compiler를 결합하되 MAIN과 분리",
        1080,
    )
    cards = [
        ("질문 계획", "exact span\nfamily·predicate 복수 가설", base.BLUE, base.PALE_BLUE),
        ("12단계 회수", "법체계 진입\n관계 확장·원문 검증", base.GREEN, base.PALE_GREEN),
        ("최종 28개", "current article roots\nbaseline floor 보존", base.NAVY, "#E7ECF3"),
        ("atomic compiler", "issue·role·closed E ID\nexact quote 결속", base.GOLD, base.PALE_GOLD),
        ("답변 + gate", "사용 E ID 선언\n구조 위반은 INSUFFICIENT", base.NAVY, "#E7ECF3"),
    ]
    x0, y1, y2, card_w, gap = 70, 265, 630, 300, 45
    for idx, (head, body, accent, fill) in enumerate(cards, 1):
        x = x0 + (idx - 1) * (card_w + gap)
        base.card(
            draw, (x, y1, x + card_w, y2), head, body,
            accent=accent, fill=fill, badge=str(idx), heading_size=24, body_size=21,
        )
        if idx < len(cards):
            base.arrow(draw, (x + card_w + 4, 448), (x + card_w + gap - 5, 448), accent, 7)
    base.pill(
        draw, (130, 735, 825, 825),
        "연구 기준선: ADR-0118-experiment-v1 / integrated-atomic-claim-v4b",
        fill=base.PALE_GREEN, color=base.GREEN, outline="#AFD6C8", size=22,
    )
    base.pill(
        draw, (975, 735, 1670, 825),
        "운영 상태: Rejected · decision_eligible=false · MAIN unchanged",
        fill=base.PALE_RED, color=base.RED, outline="#E2BABA", size=22,
    )
    base.arrow(draw, (835, 780), (965, 780), base.MUTED, 5, dashed=True)
    draw.text((330, 915), "‘최고 비교 구조’와 ‘운영 합격’은 서로 다른 판단이다.",
              font=base.font(31, True), fill=base.NAVY)
    return _save(image, "01_fixed_overview.png")


def retrieval_stages() -> Path:
    image, draw = base.canvas(1420)
    base.title(
        draw,
        "회수·검증 상태 머신의 12단계",
        "넓게 진입하고, floor를 보존하며, current 원문 검증 뒤 28개만 제시",
        1420,
    )
    stages = [
        ("1", "질문 원문", "question-source", base.BLUE),
        ("2", "Closed grounding", "DB ID 후보", base.BLUE),
        ("3", "법체계 route", "법률→법령→조문", base.GREEN),
        ("4", "Semantic card", "검색 진입 posting", base.GREEN),
        ("5", "Baseline floor", "기존 결과 add-only", base.NAVY),
        ("6", "Typed relation", "위임·준용·정의", base.GOLD),
        ("7", "Wiki dependency", "단서·제재·정의", base.GOLD),
        ("8", "Adaptive page", "법령 내부 cursor", base.GREEN),
        ("9", "Canonicalize", "현행 좌표·원문 검증", base.NAVY),
        ("10", "Actor/scope", "시장·행위자 정렬", base.BLUE),
        ("11", "Coverage select", "검증 후보 cap", base.NAVY),
        ("12", "Final present", "28 article roots", base.NAVY),
    ]
    cols, card_w, card_h = 4, 365, 230
    x0, y0, xgap, ygap = 85, 260, 55, 75
    for idx, (badge, head, body, accent) in enumerate(stages):
        row, col = divmod(idx, cols)
        x = x0 + col * (card_w + xgap)
        y = y0 + row * (card_h + ygap)
        fill = base.PALE_BLUE if accent == base.BLUE else base.PALE_GREEN if accent == base.GREEN else base.PALE_GOLD if accent == base.GOLD else "#E7ECF3"
        base.card(draw, (x, y, x + card_w, y + card_h), head, body,
                  accent=accent, fill=fill, badge=badge, heading_size=23, body_size=20)
        if col < cols - 1:
            base.arrow(draw, (x + card_w + 5, y + card_h // 2),
                       (x + card_w + xgap - 6, y + card_h // 2), accent, 6)
        elif row < 2:
            base.arrow(draw, (x + card_w // 2, y + card_h + 5),
                       (x + card_w // 2, y + card_h + ygap - 8), base.LINE, 6)
    base.pill(draw, (110, 1230, 790, 1315),
              "회수 실패: floor-only fallback (fail-open)",
              fill=base.PALE_BLUE, color=base.BLUE, outline=base.SKY, size=23)
    base.pill(draw, (1010, 1230, 1690, 1315),
              "관계 발견 ≠ verified evidence ≠ 법률 결론",
              fill=base.PALE_GOLD, color=base.GOLD, outline="#E4CD93", size=23)
    return _save(image, "02_retrieval_stages.png")


def compiler_packet() -> Path:
    image, draw = base.canvas(1230)
    base.title(
        draw,
        "비파괴 atomic claim compiler",
        "원문을 줄이지 않고 질문 쟁점과 exact quote를 closed evidence ID에 결속",
        1230,
    )
    base.card(draw, (85, 275, 520, 830), "입력", "사용자 질문\n+\nE01~E28 좌표\n법명·조문·scope\n조문 원문 전문",
              accent=base.BLUE, fill=base.PALE_BLUE, heading_size=30, body_size=25)
    base.arrow(draw, (535, 550), (655, 550), base.BLUE, 9)
    draw.rounded_rectangle((670, 235, 1285, 870), 30, fill=base.WHITE, outline=base.GOLD, width=5)
    base.pill(draw, (735, 270, 1220, 345), "legal_compilation packet",
              fill=base.GOLD, color=base.WHITE, size=27)
    rows = [
        ("issues ≤ 4", "질문의 연속 exact span"),
        ("soft units ≤ 20", "issue + role + E ID + quote"),
        ("8 legal roles", "본칙·정의·요건·예외·절차…"),
        ("claims", "proposition == exact quote"),
        ("CONTEXT fallback", "미선택 조문도 삭제하지 않음"),
        ("scope gate", "명시 시장 불일치 unit 제외"),
    ]
    y = 380
    for label, detail in rows:
        base.pill(draw, (725, y, 965, y + 62), label,
                  fill=base.PALE_GOLD, color=base.GOLD, outline="#E4CD93", size=19)
        draw.text((990, y + 15), detail, font=base.font(20, True), fill=base.INK)
        y += 76
    base.arrow(draw, (1300, 550), (1415, 550), base.GREEN, 9)
    base.card(draw, (1430, 275, 1715, 830), "답변", "28개 원문 전체\n+packet 가이드\n\nanswer\nanswerable\nevidence_ids",
              accent=base.GREEN, fill=base.PALE_GREEN, heading_size=30, body_size=24)
    base.pill(draw, (170, 955, 815, 1045),
              "불변식: 좌표·순서·본문은 compiler 전후 동일",
              fill=base.PALE_GREEN, color=base.GREEN, outline="#AFD6C8", size=24)
    base.pill(draw, (985, 955, 1630, 1045),
              "한계: coverage·실제 포섭은 아직 완성되지 않음",
              fill=base.PALE_RED, color=base.RED, outline="#E2BABA", size=24)
    draw.text((490, 1135), "exact quote는 근거이며, 자동으로 법률효과가 되는 것은 아니다.",
              font=base.font(26, True), fill=base.MUTED)
    return _save(image, "03_compiler_packet.png")


def cm008() -> Path:
    image, draw = base.canvas(1050)
    base.title(
        draw,
        "cm-008: 본칙과 시행세칙을 함께 고르는 사례",
        "‘3개월이 6개월로 연장되는 경우’는 숫자 하나가 아니라 두 조문의 원자적 결속",
        1050,
    )
    base.card(draw, (100, 270, 560, 720), "사용자 질문",
              "국내 일반기업의\n3개월 보유기간이\n6개월로 연장되는 경우는?",
              accent=base.BLUE, fill=base.PALE_BLUE, heading_size=28, body_size=28)
    base.arrow(draw, (580, 495), (710, 495), base.BLUE, 9)
    base.card(draw, (730, 235, 1190, 545), "E01 · 제13조",
              "GOVERNING_RULE\n기본 3개월\n혁신기술기업 + 세칙상 사유이면 6개월",
              accent=base.NAVY, fill="#E7ECF3", heading_size=27, body_size=23)
    base.card(draw, (730, 600, 1190, 910), "E13 · 세칙 제15조",
              "CONDITION / COMPANION\n‘세칙으로 정하는 사유’의\n구체적인 최근 3년·상장 후 2년 요건",
              accent=base.GOLD, fill=base.PALE_GOLD, heading_size=27, body_size=22)
    base.arrow(draw, (1210, 390), (1350, 485), base.GREEN, 8)
    base.arrow(draw, (1210, 750), (1350, 565), base.GREEN, 8)
    base.card(draw, (1370, 330, 1710, 730), "완전 답변",
              "본칙 + 연장 관문\n+ 세부 사유\n+ 자동 연장 아님",
              accent=base.GREEN, fill=base.PALE_GREEN, heading_size=28, body_size=25)
    base.pill(draw, (250, 845, 655, 925), "원문 직접선택: E26 오선",
              fill=base.PALE_RED, color=base.RED, outline="#E2BABA", size=23)
    base.pill(draw, (1270, 845, 1660, 925), "ADR-0118: E01 + E13",
              fill=base.PALE_GREEN, color=base.GREEN, outline="#AFD6C8", size=23)
    return _save(image, "04_cm008.png")


def performance() -> Path:
    image, draw = base.canvas(1170)
    base.title(
        draw,
        "왜 ADR-0118을 고정했는가",
        "micro F1 하나가 아니라 FN 우선 Tversky와 core/hard 난도균형 점수로 비교",
        1170,
    )
    rows = [
        ("ADR-0131 원문 직접", 50.479709, 65, 61, 51, base.BLUE),
        ("ADR-0118 전체 compiler", 52.638970, 67, 72, 49, base.GREEN),
        ("ADR-0132 선별 가이드", 52.490865, 69, 79, 47, base.GOLD),
    ]
    max_score = 55.0
    y = 300
    for name, score, tp, fp, fn, color in rows:
        draw.text((110, y), name, font=base.font(27, True), fill=base.NAVY)
        draw.rounded_rectangle((565, y - 2, 1480, y + 58), 26, fill="#E7ECF3")
        bar_w = int(915 * score / max_score)
        draw.rounded_rectangle((565, y - 2, 565 + bar_w, y + 58), 26, fill=color)
        draw.text((1510, y + 4), f"{score:.6f}", font=base.font(24, True), fill=color)
        draw.text((565, y + 80), f"TP {tp}   FP {fp}   FN {fn}",
                  font=base.font(22, True), fill=base.MUTED)
        y += 190
    base.pill(draw, (140, 890, 790, 980), "최종 검색 제시: 95 / 116 (81.90%)",
              fill=base.PALE_BLUE, color=base.BLUE, outline=base.SKY, size=24)
    base.arrow(draw, (805, 935), (990, 935), base.RED, 7)
    base.pill(draw, (1005, 890, 1660, 980), "답변 사용 선언: 67 / 116 (57.76%)",
              fill=base.PALE_RED, color=base.RED, outline="#E2BABA", size=24)
    draw.text((500, 1050), "현재 핵심 병목: 찾아온 정답을 마지막 답변에서 선택하는 단계",
              font=base.font(28, True), fill=base.NAVY)
    return _save(image, "05_performance.png")


def generate_all() -> list[Path]:
    return [fixed_overview(), retrieval_stages(), compiler_packet(), cm008(), performance()]


if __name__ == "__main__":
    for path in generate_all():
        print(path)
