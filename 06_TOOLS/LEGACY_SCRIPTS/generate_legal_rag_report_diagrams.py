"""Generate polished explanatory diagrams for the legal-domain RAG report."""

from __future__ import annotations

import math
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "legal_rag_report_diagrams"

W = 1800
BG = "#F7F9FC"
NAVY = "#17365D"
BLUE = "#2E74B5"
SKY = "#DCEBFA"
PALE_BLUE = "#EDF4FB"
INK = "#1F2937"
MUTED = "#667085"
LINE = "#B8C7D9"
GOLD = "#B58A2A"
PALE_GOLD = "#F8F0DB"
GREEN = "#2F7D67"
PALE_GREEN = "#E3F2ED"
RED = "#B14E4E"
PALE_RED = "#F8E8E8"
WHITE = "#FFFFFF"

FONT_REGULAR = Path("C:/Windows/Fonts/malgun.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/malgunbd.ttf")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def canvas(height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (W, height), BG)
    return image, ImageDraw.Draw(image)


def title(draw: ImageDraw.ImageDraw, heading: str, subtitle: str, height: int) -> None:
    draw.text((90, 65), heading, font=font(58, True), fill=NAVY)
    draw.text((92, 145), subtitle, font=font(27), fill=MUTED)
    draw.rounded_rectangle((90, height - 30, W - 90, height - 22), 4, fill=BLUE)


def text_lines(draw: ImageDraw.ImageDraw, text: str, max_width: int,
               text_font: ImageFont.FreeTypeFont) -> list[str]:
    lines: list[str] = []
    for explicit in text.split("\n"):
        if not explicit:
            lines.append("")
            continue
        words = explicit.split(" ")
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if draw.textlength(candidate, font=text_font) <= max_width:
                current = candidate
            elif current:
                lines.append(current)
                current = word
            else:
                # Long identifiers are split conservatively at character boundaries.
                part = ""
                for char in word:
                    if draw.textlength(part + char, font=text_font) <= max_width:
                        part += char
                    else:
                        lines.append(part)
                        part = char
                current = part
        if current:
            lines.append(current)
    return lines


def centered_multiline(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
                       text: str, text_font: ImageFont.FreeTypeFont, fill: str,
                       spacing: int = 10) -> None:
    x1, y1, x2, y2 = box
    lines = text_lines(draw, text, x2 - x1, text_font)
    bbox = draw.textbbox((0, 0), "가Ag", font=text_font)
    line_h = bbox[3] - bbox[1]
    total_h = len(lines) * line_h + max(0, len(lines) - 1) * spacing
    y = y1 + (y2 - y1 - total_h) / 2
    for line in lines:
        width = draw.textlength(line, font=text_font)
        draw.text((x1 + (x2 - x1 - width) / 2, y), line, font=text_font, fill=fill)
        y += line_h + spacing


def card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], heading: str,
         body: str, *, accent: str = BLUE, fill: str = WHITE,
         badge: str | None = None, heading_size: int = 32,
         body_size: int = 23) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle((x1 + 10, y1 + 12, x2 + 10, y2 + 12), 28, fill="#DCE3EC")
    draw.rounded_rectangle(box, 28, fill=fill, outline=LINE, width=3)
    draw.rounded_rectangle((x1, y1, x1 + 14, y2), 7, fill=accent)
    if badge:
        draw.ellipse((x1 + 28, y1 + 25, x1 + 86, y1 + 83), fill=accent)
        centered_multiline(draw, (x1 + 28, y1 + 25, x1 + 86, y1 + 83), badge,
                           font(25, True), WHITE, 0)
        heading_x = x1 + 105
    else:
        heading_x = x1 + 35
    draw.text((heading_x, y1 + 27), heading, font=font(heading_size, True), fill=NAVY)
    lines = text_lines(draw, body, x2 - x1 - 70, font(body_size))
    y = y1 + 91
    for line in lines:
        draw.text((x1 + 36, y), line, font=font(body_size), fill=INK)
        y += body_size + 13


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int],
          color: str = BLUE, width: int = 8, dashed: bool = False) -> None:
    x1, y1 = start
    x2, y2 = end
    if dashed:
        segments = 10
        for i in range(segments):
            if i % 2 == 0:
                a = i / segments
                b = (i + 1) / segments
                draw.line((x1 + (x2 - x1) * a, y1 + (y2 - y1) * a,
                           x1 + (x2 - x1) * b, y1 + (y2 - y1) * b),
                          fill=color, width=width)
    else:
        draw.line((x1, y1, x2, y2), fill=color, width=width)
    angle = math.atan2(y2 - y1, x2 - x1)
    length = 25
    spread = 0.55
    points = [
        (x2, y2),
        (x2 - length * math.cos(angle - spread), y2 - length * math.sin(angle - spread)),
        (x2 - length * math.cos(angle + spread), y2 - length * math.sin(angle + spread)),
    ]
    draw.polygon(points, fill=color)


def pill(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str,
         *, fill: str = PALE_BLUE, color: str = NAVY, outline: str | None = None,
         size: int = 23, bold: bool = True) -> None:
    draw.rounded_rectangle(box, (box[3] - box[1]) // 2, fill=fill,
                           outline=outline or fill, width=2)
    centered_multiline(draw, (box[0] + 15, box[1], box[2] - 15, box[3]), text,
                       font(size, bold), color, 2)


def save(image: Image.Image, name: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / name
    image.save(path, format="PNG", optimize=True, dpi=(220, 220))
    return path


def diagram_end_to_end() -> Path:
    image, draw = canvas(900)
    title(draw, "법률 질문이 답변으로 바뀌는 전체 흐름",
          "검색 한 번이 아니라, 진입 → 회수 → 관계 확장 → 명제 검증의 연속 과정", 900)
    headings = ["질문 원문", "질문 구조화", "법체계 진입", "회수·확장", "명제 검증", "근거형 답변"]
    bodies = [
        "법명·조문·숫자와\n사용자 사실 보존",
        "mention · issue · fact\n복수 가설 생성",
        "쟁점별 지배 법령과\n규범 역할 선택",
        "본문 검색 + 관계 closure\n정의·예외·위임 보강",
        "사실 ↔ 규칙 결속\n충족·예외·충돌 검사",
        "지지된 명제만 사용\n조건·예외·불확실성 제시",
    ]
    colors = [BLUE, BLUE, GREEN, GREEN, GOLD, NAVY]
    fills = [PALE_BLUE, PALE_BLUE, PALE_GREEN, PALE_GREEN, PALE_GOLD, "#E7ECF3"]
    gap = 28
    x0 = 70
    card_w = 255
    y1, y2 = 270, 620
    for i, (head, body) in enumerate(zip(headings, bodies)):
        x1 = x0 + i * (card_w + gap)
        card(draw, (x1, y1, x1 + card_w, y2), head, body, accent=colors[i],
             fill=fills[i], badge=str(i + 1), heading_size=24, body_size=21)
        if i < len(headings) - 1:
            arrow(draw, (x1 + card_w + 4, (y1 + y2) // 2),
                  (x1 + card_w + gap - 4, (y1 + y2) // 2), colors[i + 1], 7)
    pill(draw, (195, 700, 805, 775), "회수 경계: 놓치지 않도록 fail-open",
         fill=PALE_BLUE, color=BLUE, outline=SKY, size=24)
    pill(draw, (995, 700, 1605, 775), "판단 경계: 명제별 claim-local fail-closed",
         fill=PALE_GOLD, color=GOLD, outline="#E4CD93", size=24)
    arrow(draw, (810, 738), (985, 738), MUTED, 5, dashed=True)
    return save(image, "01_end_to_end_pipeline.png")


def diagram_data_layers() -> Path:
    image, draw = canvas(1170)
    title(draw, "Legal Graph 데이터 스키마: 네 계층과 하나의 좌표",
          "정본과 관찰값, 검색용 파생물, 질의 실행 상태를 섞지 않는다", 1170)
    layers = [
        ("runtime", "질의 실행", "query_frame · landing · decision_bundle · retrieval_trace", NAVY, "#E7ECF3"),
        ("projection", "검색·탐색용 파생", "semantic_card · closure_projection · rule_bundle", BLUE, PALE_BLUE),
        ("observation", "미승인 관찰·후보", "entity_mention · relation_candidate · requirement_observation", GOLD, PALE_GOLD),
        ("canonical", "정본 법령·명제·근거", "instrument/provision · term_sense · rule/relation · evidence", GREEN, PALE_GREEN),
    ]
    y = 245
    for idx, (name, role, objects, accent, fill) in enumerate(layers):
        box = (340, y, 1650, y + 160)
        draw.rounded_rectangle((box[0] + 9, box[1] + 10, box[2] + 9, box[3] + 10), 25,
                               fill="#DDE4ED")
        draw.rounded_rectangle(box, 25, fill=fill, outline=LINE, width=3)
        draw.rounded_rectangle((340, y, 620, y + 160), 25, fill=accent)
        centered_multiline(draw, (360, y + 10, 600, y + 85), name, font(34, True), WHITE, 0)
        centered_multiline(draw, (360, y + 78, 600, y + 145), role, font(22), WHITE, 0)
        centered_multiline(draw, (675, y + 25, 1605, y + 135), objects,
                           font(25, True), NAVY, 10)
        if idx < len(layers) - 1:
            arrow(draw, (995, y + 164), (995, y + 207), LINE, 6)
        y += 205
    # Coordinate spine
    draw.rounded_rectangle((75, 270, 280, 930), 32, fill=WHITE, outline=BLUE, width=4)
    draw.rounded_rectangle((75, 270, 280, 355), 32, fill=BLUE)
    centered_multiline(draw, (90, 280, 265, 345), "원문 좌표", font(30, True), WHITE, 0)
    coordinate = "document_id\nnode_id · block_id\nstart / end\nquote hash"
    centered_multiline(draw, (100, 390, 255, 770), coordinate, font(22, True), NAVY, 20)
    pill(draw, (95, 815, 260, 885), "모든 계층 공통", fill=PALE_BLUE,
         color=BLUE, outline=SKY, size=20)
    arrow(draw, (280, 600), (330, 600), BLUE, 7)
    draw.text((375, 1060), "아래에서 위로: 정본 → 후보 → 검색용 파생 → 질의 실행",
              font=font(24, True), fill=MUTED)
    return save(image, "02_data_schema_layers.png")


def diagram_question_schema() -> Path:
    image, draw = canvas(1040)
    title(draw, "질문 스키마는 원문을 버리지 않고 단계적으로 강해진다",
          "LLM이 임의 JSON을 만드는 대신, exact span과 DB closed-set을 거쳐 법률 명제로 컴파일", 1040)
    stages = [
        ("원문 anchor", "금융회사가 외부기관에\n심사업무를 위탁해도 되는가?", BLUE, PALE_BLUE),
        ("mention", "금융회사 · 외부기관\n심사업무 · 위탁\n(start/end 검증)", BLUE, PALE_BLUE),
        ("DB ID 결속", "DB에 존재하는 ID만 선택\n불확실하면 UNRESOLVED", GREEN, PALE_GREEN),
        ("쟁점·사실·규칙", "업무위탁 쟁점\n행위자·행위·대상 사실\n근거·예외·절차 규칙", GOLD, PALE_GOLD),
        ("포섭 · 충족도", "필수 역할 충족 여부\nSUPPORTED / MISSING\nCONDITIONAL / CONFLICTED", NAVY, "#E7ECF3"),
    ]
    x_positions = [75, 420, 765, 1110, 1455]
    y1, y2 = 285, 720
    card_w = 285
    for i, (head, body, accent, fill) in enumerate(stages):
        x = x_positions[i]
        card(draw, (x, y1, x + card_w, y2), head, body, accent=accent, fill=fill,
             badge=str(i + 1), heading_size=22, body_size=21)
        if i < len(stages) - 1:
            arrow(draw, (x + card_w + 3, 500), (x_positions[i + 1] - 8, 500),
                  accent, 7)
    pill(draw, (115, 805, 760, 885), "검색 신호: 복수 가설 · soft boost · 병렬 branch",
         fill=PALE_BLUE, color=BLUE, outline=SKY, size=23)
    pill(draw, (1015, 805, 1685, 885), "판단 계약: exact evidence · 명제별 보류 · 표적 재검색",
         fill=PALE_GOLD, color=GOLD, outline="#E4CD93", size=23)
    draw.text((660, 940), "원문 span은 끝까지 provenance로 유지",
              font=font(25, True), fill=MUTED)
    return save(image, "03_question_schema_funnel.png")


def diagram_two_lane() -> Path:
    image, draw = canvas(930)
    title(draw, "회수용 스키마와 컴파일용 스키마는 실패 방식이 다르다",
          "관련 조문을 찾는 단계와 법률 결론을 허용하는 단계를 분리해야 안전성과 recall을 함께 지킨다", 930)
    # Lane backgrounds
    draw.rounded_rectangle((90, 245, 1710, 495), 30, fill=PALE_BLUE, outline=SKY, width=3)
    draw.rounded_rectangle((90, 570, 1710, 820), 30, fill=PALE_GOLD, outline="#E4CD93", width=3)
    pill(draw, (120, 275, 355, 350), "회수 LANE", fill=BLUE, color=WHITE, size=27)
    pill(draw, (120, 600, 355, 675), "컴파일 LANE", fill=GOLD, color=WHITE, size=27)
    recovery = ["명시 좌표", "full text", "vector / reverse", "법체계 지도", "관계 closure"]
    compile_steps = ["명제 분해", "exact quote", "사실 대조", "예외·충돌", "답변 허용"]
    start_x, card_w, gap = 390, 235, 55
    for i, label in enumerate(recovery):
        x = start_x + i * (card_w + gap)
        pill(draw, (x, 315, x + card_w, 410), label, fill=WHITE, color=NAVY,
             outline=SKY, size=22)
        if i < 4:
            arrow(draw, (x + card_w + 7, 363), (x + card_w + gap - 8, 363), BLUE, 6)
    for i, label in enumerate(compile_steps):
        x = start_x + i * (card_w + gap)
        pill(draw, (x, 640, x + card_w, 735), label, fill=WHITE, color=NAVY,
             outline="#E4CD93", size=22)
        if i < 4:
            arrow(draw, (x + card_w + 7, 688), (x + card_w + gap - 8, 688), GOLD, 6)
    arrow(draw, (1100, 500), (1100, 560), GREEN, 8)
    pill(draw, (845, 475, 1355, 555), "verified evidence bundle",
         fill=PALE_GREEN, color=GREEN, outline="#AFD6C8", size=24)
    draw.text((120, 430), "실패 시: 후보를 넓히고 다음 branch로 이동 (fail-open)",
              font=font(22, True), fill=BLUE)
    draw.text((120, 755), "실패 시: 질문 전체가 아니라 해당 명제만 보류 (claim-local fail-closed)",
              font=font(22, True), fill=GOLD)
    return save(image, "04_retrieval_compiler_lanes.png")


def diagram_adr_evolution() -> Path:
    image, draw = canvas(1080)
    title(draw, "ADR 실험은 검색기에서 법률 컴파일러로 이동했다",
          "각 계열은 앞 단계의 실패 원인을 데이터·탐색·근거 결속 문제로 분해하며 발전", 1080)
    milestones = [
        ("0038–0042", "검색 도달성·법률 프레임", "회수와 답변 정확도 분리", BLUE),
        ("0043–0060", "실험 거버넌스·인과", "prompt·모델·조문 간섭 분리", BLUE),
        ("0061–0081", "후보 생성·선택 손실", "찾은 것과 버린 것의 원장화", GREEN),
        ("0082–0091", "데이터·좌표 정본화", "현행성·좌표·Golden 교정", GREEN),
        ("0092–0096", "관계 기반 표적 회복", "역할·predicate별 피드백", GOLD),
        ("0097–0106", "Legal Graph·grounding", "스키마·query family·trace", GOLD),
        ("0107–0114", "법체계 계층형 조사", "법령→조문→cursor 탐색", NAVY),
        ("0115–0124", "명제별 법률 컴파일러", "coverage·포섭·비파괴 보존", NAVY),
    ]
    coords = [(140, 300), (530, 300), (920, 300), (1310, 300),
              (1310, 650), (920, 650), (530, 650), (140, 650)]
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        if i == 3:
            arrow(draw, (x1 + 155, y1 + 185), (x2 + 155, y2 - 25), LINE, 8)
        else:
            direction = 1 if y1 == 300 else -1
            arrow(draw, (x1 + (305 if direction == 1 else 0), y1 + 90),
                  (x2 + (0 if direction == 1 else 305), y2 + 90), LINE, 8)
    for index, ((adr, head, body, accent), (x, y)) in enumerate(zip(milestones, coords), start=1):
        draw.rounded_rectangle((x + 8, y + 10, x + 313, y + 195), 25, fill="#DDE4ED")
        draw.rounded_rectangle((x, y, x + 305, y + 185), 25, fill=WHITE, outline=accent, width=4)
        pill(draw, (x + 22, y + 18, x + 157, y + 68), adr, fill=accent, color=WHITE,
             size=19)
        draw.text((x + 22, y + 83), head, font=font(24, True), fill=NAVY)
        lines = text_lines(draw, body, 260, font(19))
        yy = y + 127
        for line in lines:
            draw.text((x + 22, yy), line, font=font(19), fill=INK)
            yy += 27
    pill(draw, (265, 915, 1535, 995),
         "주의: 데이터셋·judge·prompt가 달라 ADR 수치를 하나의 리더보드처럼 직접 비교하지 않는다",
         fill="#EEF1F5", color=MUTED, outline=LINE, size=23)
    return save(image, "05_adr_evolution_map.png")


def generate_all() -> list[Path]:
    return [
        diagram_end_to_end(),
        diagram_data_layers(),
        diagram_question_schema(),
        diagram_two_lane(),
        diagram_adr_evolution(),
    ]


if __name__ == "__main__":
    for generated in generate_all():
        print(generated)
