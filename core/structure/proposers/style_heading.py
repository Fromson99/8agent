"""제안자 — Word 스타일 제목 (`Block.heading_level`) (SPEC §6.1).

## 마커가 아니라 **선언**이다

docx 의 msword_backend 는 Word 스타일(outlineLvl·"Heading N")의 레벨을
`meta.level` 로 실어 온다(§00.4.1). 글자 표면에는 아무것도 없다 — 작성자가
"이 문단은 N층 제목" 이라고 선언한 것이 신호의 전부다. 그래서 이 제안자의
후보는 **너비 0** 이다: `offset == end == 0`, 잘라낼 표면 마커가 없다.

    · PDF 는 레이아웃 모델이 전부 level=1 로 평면화하므로 여기서 발화해도
      깊이 정보가 없다 — `depth=1` 후보 하나가 설 뿐이고, 마커가 있는 블록에서는
      아래 잉여 규칙으로 사라진다. hwp 는 `heading_level` 자체가 없다.
    · 표면 없음 → `construction="style"`. construction 가드는 이것을 완전형과
      같게 본다(작성자의 선언이 곧 완전한 구성이다). 조사 가드는 너비 0 마커를
      건너뛴다 — 붙을 표면이 없는데 꼬리 첫 글자로 조사를 재면 `은행…` 처럼
      조사 글자로 시작하는 제목이 억울하게 깎인다.

## depth 는 자기계열 depth 다

`1.1.1` 이 스스로 깊이를 말하듯, `Heading 2` 는 스스로 2층이라 말한다.
`depth=heading_level` 로 실으면 family_key 가 `style_h:1`, `style_h:2` … 로
갈리고, 사다리는 자기계열 depth 규칙으로 그 순서를 관측 없이 얻는다.
다른 계열(kr_장, dot_number …)과의 상하는 여기서 정하지 않는다 — 문서가
유도한다(§6).

## 표면 마커에 자리를 내준다 (S0 잉여 규칙)

`제1장 총칙` 이 Heading 1 스타일이면 kr_장 후보와 이 후보가 **같은 자리**에
선다. 마커 후보는 서수를 실어 계열 정합·서수 게이트가 작동하지만 스타일
후보는 서수가 없다 — 같은 절단이면 마커가 엄격히 더 많은 정보를 준다.
그래서 s0 가 같은 블록 offset 0 에 표면 후보가 있으면 스타일 후보를 버린다
(`pipeline.s0_propose`). 스타일 후보가 서는 곳은 **마커 없는 제목**뿐이다:
`총칙`, `개요` 처럼 스타일만으로 선언된 제목이 정확히 이 계열의 지분이다.
"""

from __future__ import annotations

from core.structure.model import Block, Candidate

ID = "style_heading"
ROLE = "proposer"
LANG = "any"
FAMILY = "style_h"
SURFACE = "Word 스타일 제목 (Heading N — 표면 없는 선언)"

# 화면·감사 로그에 보일 표면 길이 상한. 마커 계열의 surface 는 `제3장` 처럼
# 짧지만 이 계열은 표면이 없어 제목 전문을 대신 보여 준다.
_MAX_SURFACE = 40


def _ordinal(m):
    """스타일 제목은 자기가 몇 번째인지 말하지 않는다 — 서수 없음."""
    return None


def propose(block: Block, lex) -> list[Candidate]:
    if block.heading_level is None or not block.text.strip():
        return []
    surface = " ".join(block.text.split())
    if len(surface) > _MAX_SURFACE:
        surface = surface[:_MAX_SURFACE] + "…"
    return [Candidate(
        id="", family=FAMILY, depth=int(block.heading_level),
        surface=surface, ordinal=None,
        block_idx=block.idx, offset=0, end=0,
        page=block.page, element_index=block.element_index,
        text=block.text, construction="style",
        in_paren=False, is_heading=True,
        bbox=block.bbox, text_x=block.text_x)]
