"""제안자 — 부속 `[별지 N]` `[별표 N]` `[서식 N]` `부칙` (SPEC §6.1).

부속은 본문 계층과 축이 다르다(§10 미해결: "부속 스코프를 본문 계층과 어떻게 분리
보관할지"). 여기서는 **제안자로서 후보만 낸다** — 분리 보관은 아직 결정되지 않았으므로
계층 지식을 담지 않는다는 원칙(§6)대로 축 판단을 하지 않는다.

`부칙` 은 번호가 없어 서수가 `None` 이다. 서수 없는 후보를 서수 게이트가 어떻게
다루는지는 `global_inner/ordinal.py` 에 적혀 있다(검사를 건너뛴다).
"""

from __future__ import annotations

import re

from lawrag.core.structure.model import Block, Candidate
from lawrag.core.structure.proposers import scan

ID = "annex"
ROLE = "proposer"
LANG = "ko"
FAMILY = "annex"
SURFACE = "[별지 N] [별표 N] [서식 N] 부칙"

_KINDS = "별지|별표|서식|양식"
_FULL = re.compile(rf"[\[〔(]\s*({_KINDS})\s*(?:제\s*)?(\d{{1,3}})\s*(?:호)?\s*[\]〕)]")
_FRAGMENT = re.compile(rf"(?<![가-힣])({_KINDS})\s*(\d{{1,3}})(?![가-힣\d])")
# Horizontal spaces and source newlines are distinct: never consume the next
# paragraph as part of a heading. Preserve original offsets, spelling and text.
_B = r"부[^\S\n]*칙"
_BRACKETS = [("[", "]"), ("〔", "〕"), ("【", "】"), ("(", ")"), ("（", "）")]
_MARKER = "|".join(re.escape(a)+r"[^\S\n]*"+_B+r"[^\S\n]*"+re.escape(b)
                   for a,b in _BRACKETS) + "|" + _B
_BUCHIK = re.compile(r"(?m)^[^\S\n]*(?P<marker>"+_MARKER+r")(?P<tail>[^\n]*)$")
_ANNOTATION = re.compile(r"(?:\([^()\n]*\)|（[^（）\n]*）|\[[^\[\]\n]*\]|"
                         r"〔[^〔〕\n]*〕|<[^<>\n]*>|〈[^〈〉\n]*〉)")
_DATE = re.compile(r"(?:19|20)\d{2}\s*[.년/-]\s*\d{1,2}\s*[.월/-]\s*\d{1,2}\s*[.일]?")


def _heading_tail(tail: str) -> bool:
    tail = tail.strip()
    while tail:
        m = _ANNOTATION.match(tail)
        if m is None:
            return bool(_DATE.fullmatch(tail))
        tail = tail[m.end():].strip()
    return True


def _ordinal(m: re.Match):
    return (int(m.group(2)),)


def propose(block: Block, lex) -> list[Candidate]:
    out = scan(block, FAMILY, _FULL, _ordinal, fragment=_FRAGMENT,
               family_of=lambda m: f"annex_{m.group(1)}")

    for m in _BUCHIK.finditer(block.text):
        if not _heading_tail(m.group("tail")):
            continue
        out.append(Candidate(
            id="", family="buchik", surface=m.group("marker").strip(), ordinal=None,
            block_idx=block.idx, offset=m.start("marker"), end=m.end("marker"), page=block.page,
            element_index=block.element_index, text=block.text,
            # Detect merged headings, but do not create overlapping/empty units
            # inside a source block. The review audit records this as a warning.
            construction="fragment" if block.text[:m.start("marker")].strip() else "full",
            in_paren=False, is_heading=block.is_heading,
            bbox=block.bbox, text_x=block.text_x))
    out.sort(key=lambda c: c.offset)
    return out
