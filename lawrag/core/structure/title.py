"""제목 추출 — 구역의 **이름**을 찾는다 (S4 뒤).

    extract(candidates, blocks) -> 활성 후보의 `title` 을 채운다

`제7조` 는 좌표이고 `금융소비자의 기본적 권리` 가 이름이다. 다운스트림은 좌표로
찾고 이름으로 읽는다.

## 어디까지가 이름인가 — 실측이 규칙을 준다

    kr_article    '제7조' → '(금융소비자의 기본적 권리) 금융소비자는 …'   괄호 안이 이름
    kr_장          '제1장' → ' 총칙'                                    꼬리 전부가 이름
    kr_절          '제1절' → ' 영업행위 일반원칙'                          꼬리 전부
    paren_number  '1)'   → ' 보장성 상품의 내용'                         꼬리 전부
    dot_number    '1.'   → " '금융상품'이란 다음 각 목의 …"               이름 없음(본문)
    hangul_jamo   '가.'  → ' 「은행법」에 따른 예금 및 대출'                이름 없음(본문)

## 네 규칙, 센 것부터

**1. 마커 직후 괄호.** `제7조(금융소비자의 기본적 권리)` — 한국 법령의 조 제목 규약이다.
   괄호가 마커에 **바로 붙어** 있어야 한다. 문장 중간의 괄호는 이름이 아니다.

**2. 같은 블록의 다음 마커 앞까지.** `제4장 금융상품판매업자등의 … 제1절 영업행위 …`
   처럼 원문이 한 줄이면, 각 마커의 이름은 다음 마커 직전까지다.

**3. 꼬리 전부.** 꼬리가 짧고(≤ `MAX_TITLE`) **종결부호가 없으면** 제목 줄이다.
   `제1장 총칙`.

**4. 다음 블록.** 마커만 있는 줄이면(`제1절` 뒤에 아무것도 없음) 바로 다음 블록이
   짧을 때 그것을 이름으로 본다. 절 제목이 줄바꿈되어 오는 판본이 있다.

어디에도 안 걸리면 **이름 없음**이다. 억지로 첫 구절을 잘라 이름이라고 하지 않는다 —
`1. '금융상품'이란 다음 각 목의 …` 는 이름이 없는 것이 맞다.

## 본문과 제목이 같으면 제목이 아니다

`가. 「은행법」에 따른 예금 및 대출` 은 짧고 종결부호도 없지만 **그것이 그 목의 내용
전부**다. 제목이 되려면 그 이름이 가리키는 **내용이 따로 있어야** 한다.

그래서 꼬리에서 뽑는 규칙(2·3·4)은 그 마디가 **자기 블록 말고 더 가진 것이 있을 때만**
쓴다 — 자식이 있거나, 자기 블록 뒤로 구간이 이어지거나. 실측(KSB):

    kr_장        이름 8건, 자기 블록만인 것 0건    →  전부 진짜 제목
    kr_절        이름 6건, 자기 블록만 0건        →  진짜 제목
    hangul_jamo 이름 62건, 자기 블록만 56건      →  대부분 본문이었다
    paren_number 이름 19건, 자기 블록만 19건     →  전부 본문이었다

괄호 규칙(1)은 예외다. `제1조(목적)` 은 span 이 한 블록이어도 괄호가 문법적으로
"여기까지가 이름"이라고 말해 준다.

## 폰트·간격은 왜 안 쓰나

같은 폰트 크기·볼드체·다음 글자와의 거리도 제목 신호다. 다만 지금 `Block` 은 docling
에서 `type`(제목 계열인가)과 bbox 만 받아 오고 **글꼴 정보는 안 들고 온다.** 위 네
규칙이 실측 세 문서를 전부 설명하므로, 글꼴을 끌어오는 것은 이 규칙들이 못 가르는
문서가 실제로 나타났을 때 한다(§9 error-driven).
"""

from __future__ import annotations

import collections
import re
from typing import Optional

from lawrag.core.structure.model import Block, Candidate

# 제목 줄로 볼 꼬리 길이 상한. 넘으면 본문이다.
MAX_TITLE = 60
# 다음 블록을 이름으로 삼을 때의 길이 상한 (규칙 4)
MAX_NEXT_BLOCK = 40

# 마커에 바로 붙은 괄호. 반각·전각 둘 다.
_PAREN = re.compile(r"^\s*[(（]\s*([^)）]{1,%d})\s*[)）]" % MAX_TITLE)
# 종결부호가 있으면 문장이지 제목이 아니다.
_SENTENCE_END = ("다.", "요.", "함.", "음.", ".", "?", "!", ";", "…")


def _clean(s: str) -> str:
    return " ".join((s or "").split()).strip(" ·-—:")


def _looks_like_title(text: str) -> bool:
    t = _clean(text)
    if not t or len(t) > MAX_TITLE:
        return False
    return not t.endswith(_SENTENCE_END)


def of(cand: Candidate, block_cands: list[Candidate], next_block: Optional[Block],
       has_content: bool) -> tuple[str, str]:
    """(제목, 근거). 못 찾으면 ("", 사유).

    has_content — 이 마디가 자기 블록 말고 더 가진 것이 있는가(자식이나 뒤따르는 구간).
                  없으면 꼬리가 곧 본문이므로 꼬리에서 이름을 뽑지 않는다.
    """
    tail = cand.text[cand.end:]

    # 1. 마커 직후 괄호 — 괄호가 "여기까지가 이름"이라고 문법적으로 말해 준다.
    #    내용이 따로 없어도 인정한다.
    m = _PAREN.match(tail)
    if m:
        return _clean(m.group(1)), "마커 직후 괄호"

    if not has_content:
        return "", "이름 없음 (꼬리가 곧 이 마디의 본문)"

    # 2. 같은 블록의 다음 마커 앞까지
    later = [o for o in block_cands if o.offset > cand.offset and o.activated]
    if later:
        cut = min(o.offset for o in later)
        between = cand.text[cand.end:cut]
        if _looks_like_title(between):
            return _clean(between), f"같은 블록의 다음 마커('{later[0].surface}') 앞까지"

    # 3. 꼬리 전부 — 짧고 종결부호가 없으면 제목 줄이다
    if _looks_like_title(tail):
        return _clean(tail), "꼬리 전부 (짧고 종결부호 없음)"

    # 4. 마커만 있는 줄 → 다음 블록
    if not _clean(tail) and next_block is not None:
        nxt = _clean(next_block.text)
        if nxt and len(nxt) <= MAX_NEXT_BLOCK and not nxt.endswith(_SENTENCE_END):
            return nxt, "마커만 있는 줄 — 다음 블록을 이름으로"

    return "", "이름 없음 (꼬리가 본문)"


def extract(roots, candidates: list[Candidate], blocks: list[Block]) -> int:
    """트리를 훑어 마디의 `title` 을 채우고 해당 후보에도 되쓴다.

    **트리가 만들어진 뒤에** 돈다 — "이 마디가 내용을 따로 가졌는가"를 알아야
    꼬리가 제목인지 본문인지 갈리기 때문이다(span·children).
    """
    by_block: dict[int, list[Candidate]] = collections.defaultdict(list)
    for c in candidates:
        by_block[c.block_idx].append(c)
    for v in by_block.values():
        v.sort(key=lambda c: c.offset)
    by_id = {c.id: c for c in candidates}

    found = 0
    stack = list(roots)
    while stack:
        n = stack.pop()
        stack.extend(n.children)
        c = by_id.get(n.candidate_id)
        if c is None:
            continue
        # 규칙 4(다음 블록이 이름)는 본문 블록에만 쓴다. 마커 다음이 표면 그 표는
        # 그 구역의 **내용**이지 이름이 아니다.
        nxt = blocks[n.block_idx + 1] if n.block_idx + 1 < len(blocks) else None
        if nxt is not None and not nxt.proposes:
            nxt = None
        has_content = bool(n.children) or (n.span[1] - n.span[0]) > 1
        n.title, n.title_reason = of(c, by_block[n.block_idx], nxt, has_content)
        c.title, c.title_reason = n.title, n.title_reason
        found += bool(n.title)
    return found
