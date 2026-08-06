"""T3. 용어 마킹기 — 파싱 결과에 용어집 용어의 출현을 표시한다 (SPEC §2.3-2, §1.3).

## 왜 필요한가

컴파일 국면에서 LLM 에게 "용어를 찾아라"고 시키지 않는다. **문자열 매칭으로 미리 표시해서**
넘기고, LLM 은 표시된 출현을 *해석*만 한다(§2.3-2). 찾기는 결정론이 잘하고,
해석은 LLM 이 잘한다 — 잘하는 쪽에 맡긴다.

## mention vs section-marker (§1.3)

같은 글자가 두 가지로 나타난다.
    section 경계 — 별지1의 제목처럼 heading 위치 + 줄 단독 출현
    mention     — 본문 문장 속 참조("… [별지1] 신탁계약 세부내역에 기재된 …")
구별은 **레이아웃 신호**로 한다. 애매한 소수는 컴파일 시 LLM 이 판단해 형식에 고정하고,
런타임에는 형식에 이미 박혀 있으므로 재판단이 없다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from core.glossary import Glossary, normalize
from core.parse_adapter import Element

# 줄 단독 출현으로 볼 여유분 — 제목 뒤에 짧은 꼬리가 붙는 경우까지 인정한다
SOLO_TAIL_MAX = 12


@dataclass
class Mention:
    """용어 출현 하나."""
    term: str                  # 정규 용어명
    surface: str               # 문서에 실제로 쓰인 표면형
    element_index: int
    page: int
    kinds: list[str]           # 용어집이 선언한 kind
    in_heading: bool           # docling 이 heading 계열로 본 요소인가
    line_solo: bool            # 그 줄이 사실상 이 용어뿐인가
    in_table: bool             # 표 안에서 나왔는가
    cell: Optional[tuple[int, int]] = None   # 표면 (row, col)

    @property
    def is_section_candidate(self) -> bool:
        """section 경계 후보인가 — 용어가 section 이고 레이아웃이 제목 신호를 준다."""
        return "section" in self.kinds and (self.in_heading or self.line_solo)

    def dump(self) -> dict:
        d = {"term": self.term, "surface": self.surface,
             "element_index": self.element_index, "page": self.page,
             "kinds": self.kinds, "in_heading": self.in_heading,
             "line_solo": self.line_solo, "in_table": self.in_table,
             "section_candidate": self.is_section_candidate}
        if self.cell:
            d["cell"] = list(self.cell)
        return d


def _find(text: str, index: dict[str, str], glossary: Glossary) -> list[tuple[str, str]]:
    """한 문자열에서 용어 출현을 (정규명, 표면형)으로. 긴 표면형을 먼저 본다.

    정규화 후 부분 문자열로 찾는다 — 조사·괄호·공백 차이를 흡수하기 위해서다.
    긴 것부터 보는 이유: "신탁계약 세부내역"이 "신탁계약"에 먹히지 않게.
    """
    norm_text = normalize(text)
    if not norm_text:
        return []
    hits: list[tuple[str, str]] = []
    taken: list[tuple[int, int]] = []
    for surface in sorted(index, key=len, reverse=True):
        start = norm_text.find(surface)
        while start >= 0:
            end = start + len(surface)
            if not any(s < end and start < e for s, e in taken):   # 겹치면 긴 쪽 우선
                taken.append((start, end))
                hits.append((index[surface], _original_surface(text, index[surface], glossary)))
            start = norm_text.find(surface, start + 1)
    return hits


def _original_surface(text: str, term: str, glossary: Glossary) -> str:
    """원문에 쓰인 표면형을 돌려준다 — 찾지 못하면 정규 용어명."""
    for s in glossary.surfaces_of(term):
        if s in text:
            return s
    return term


def mark(elements: Iterable[Element], glossary: Glossary) -> list[Mention]:
    """요소 리스트에 용어 출현을 표시한다."""
    index = glossary.surface_index()
    out: list[Mention] = []

    for e in elements:
        if e.table:
            for row in e.table.rows():
                for cell in row:
                    for term, surface in _find(cell.text, index, glossary):
                        solo = _is_solo(cell.text, surface)
                        out.append(Mention(
                            term=term, surface=surface, element_index=e.index,
                            page=e.page, kinds=glossary.terms[term].kind,
                            in_heading=False, line_solo=solo, in_table=True,
                            cell=(cell.row, cell.col)))
            continue

        for term, surface in _find(e.text, index, glossary):
            out.append(Mention(
                term=term, surface=surface, element_index=e.index, page=e.page,
                kinds=glossary.terms[term].kind,
                in_heading=e.is_heading, line_solo=_is_solo(e.text, surface),
                in_table=False))
    return out


def _is_solo(text: str, surface: str) -> bool:
    """그 줄이 사실상 이 용어뿐인가 — 제목 신호(§1.3)."""
    rest = normalize(text).replace(normalize(surface), "", 1)
    return len(rest) <= SOLO_TAIL_MAX


def summarize(mentions: list[Mention]) -> dict:
    """컴파일 리포트용 집계."""
    per_term: dict[str, dict] = {}
    for m in mentions:
        e = per_term.setdefault(m.term, {"total": 0, "section_candidates": 0,
                                         "in_table": 0, "pages": set()})
        e["total"] += 1
        e["section_candidates"] += int(m.is_section_candidate)
        e["in_table"] += int(m.in_table)
        e["pages"].add(m.page)
    for e in per_term.values():
        e["pages"] = sorted(e["pages"])
    return per_term


def unmatched_headings(elements: Iterable[Element], glossary: Glossary,
                       max_len: int = 40) -> list[Element]:
    """용어집에 없는데 제목처럼 보이는 요소 — 미등록 section 용어 후보(§2.3-4).

    최종 후보 판정은 LLM 이 근거와 함께 하지만(§2.3), LLM 없이도 이 목록만으로
    사용자가 승격 판단을 할 수 있다. 컴파일에 LLM 을 못 쓰는 환경의 대비책이다.
    """
    index = glossary.surface_index()
    out: list[Element] = []
    for e in elements:
        if e.table or not e.is_heading or e.is_furniture:
            continue
        text = e.text.strip()
        if not text or len(text) > max_len:
            continue
        if _find(text, index, glossary):
            continue                        # 이미 등록된 용어가 들어 있다
        out.append(e)
    return out
