"""T2–T3. 파트 분리 + 조/항/호 트리 복원.

온톨로지가 구조를 선언하고(`structure`, `parts`), 이 모듈은 그 선언을 읽어
recognizers 로 실현한다. 어떤 마커를 쓸지·무엇이 무엇을 포함하는지는
여기에 하드코딩하지 않는다(§C8 완료기준 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import recognizers as rec
from ontology import Ontology
from parse_stage import Element, ParseResult


@dataclass
class Node:
    """조/항/호 트리의 한 마디."""
    level: str                       # 조 | 항 | 호
    no: str
    title: str = ""
    text: str = ""
    elements: list[Element] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)
    parent: Optional["Node"] = None

    def label(self) -> str:
        if self.level == "조":
            return f"제{self.no}조" + (f"({self.title})" if self.title else "")
        return self.no

    def article_no(self) -> Optional[str]:
        n = self
        while n and n.level != "조":
            n = n.parent
        return n.no if n else None

    def page(self) -> int:
        return self.elements[0].page if self.elements else 1

    def bbox(self) -> Optional[list[float]]:
        return self.elements[0].bbox if self.elements else None

    def full_text(self) -> str:
        parts = [self.text] if self.text else []
        parts += [c.full_text() for c in self.children]
        return "\n".join(p for p in parts if p).strip()

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class Part:
    """문서 파트 — role 하나에 대응."""
    role: str
    elements: list[Element] = field(default_factory=list)
    articles: list[Node] = field(default_factory=list)     # 본문 파트만
    appendix_no: Optional[int] = None

    def pages(self) -> tuple[int, int]:
        pgs = [e.page for e in self.elements] or [1]
        return min(pgs), max(pgs)


@dataclass
class Structure:
    parts: list[Part] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def part(self, role: str) -> Optional[Part]:
        return next((p for p in self.parts if p.role == role), None)

    def all_articles(self) -> list[Node]:
        out: list[Node] = []
        for p in self.parts:
            out.extend(p.articles)
        return out

    def article_numbers(self) -> list[str]:
        return [a.no for a in self.all_articles()]


# ===========================================================================
# T2 — 파트 분리
# ===========================================================================

def split_parts(result: ParseResult, onto: Ontology) -> Structure:
    """온톨로지 `parts` 선언(`starts_at` 마커)으로 본문/별지1/별지2 를 나눈다.

    별지 마커는 본문 안에서 **참조**로도 등장한다("[별지1]에 기재된 금액").
    그래서 마커만 보지 않고 두 조건을 함께 본다.
      · 그 요소가 짧다(제목 줄이지 본문이 아니다)
      · 아직 그 파트에 진입하지 않았다(첫 등장만 경계로 인정)

    귀속은 **읽기 순서가 아니라 지면 위치(page, y)로 한다.** 실측: 도클링은 표를
    요소 목록 맨 끝에 몰아서 낸다(별지1 표가 `[별지2]` 마커 뒤에 도착). 읽기 순서로
    파트를 흘리면 별지1의 표 전체가 별지2로 새고, 값이 표 안에 있는 체결본에서는
    별지1 필드가 통째로 사라진다. 읽기 순서는 파트 **안에서만** 유지한다 —
    본문의 조/항 트리는 그 순서에 의존하기 때문이다.
    """
    st = Structure()
    default_role = onto.default_role()
    appendix = {}
    for p in onto.appendix_parts():
        m = rec.appendix_marker(p.starts_at or "")
        if m:
            appendix[m.no] = p

    # --- 1) 경계 찾기 — 마커의 지면 위치를 잡는다 ---------------------------
    boundaries: list[tuple[tuple[int, float], object]] = []
    marker_ids: set[int] = set()
    entered: set[str] = set()
    for e in result.elements:
        # 표 안의 문구는 마커로 보지 않는다(참조로 적혀 있을 수 있다).
        text = rec.normalize_ws(e.content()) if e.kind != "table" else ""
        m = rec.appendix_marker(text) if text else None
        if not m or m.no not in appendix or m.no in entered:
            continue
        # 본문 속 참조("[별지1]에 기재된 금액")가 아니라 파트 제목인지.
        # 제목은 마커로 **시작하고** 뒤에 제목 한 토막만 붙는다("[별지1] 신탁계약 세부내역").
        # 머리말/꼬리말도 후보로 남긴다: 도클링이 ss2207 의 `[별지1]` 을 page_header 로 분류했다.
        if not _is_part_title(text, m):
            continue
        entered.add(m.no)
        marker_ids.add(id(e))
        boundaries.append((_position(e), appendix[m.no]))
    boundaries.sort(key=lambda b: b[0])

    # --- 2) 위치로 귀속 ----------------------------------------------------
    parts: dict[str, Part] = {default_role: Part(role=default_role)}
    order = [default_role]
    for _, spec in boundaries:
        if spec.role not in parts:
            parts[spec.role] = Part(role=spec.role, appendix_no=spec.appendix_no)
            order.append(spec.role)

    last: tuple[int, float] = (0, 0.0)
    for e in result.elements:
        if id(e) in marker_ids:
            continue                          # 마커 줄 자체는 내용이 아니다
        if e.furniture:
            continue
        pos = _position(e, fallback=last)
        last = pos
        role = default_role
        for b_pos, spec in boundaries:
            if b_pos <= pos:
                role = spec.role
        parts[role].elements.append(e)

    st.parts = [parts[r] for r in order]
    missing = [p.role for p in onto.appendix_parts() if p.role not in parts]
    if missing:
        st.warnings.append(f"파트를 찾지 못했습니다: {', '.join(missing)}")
    return st


_TITLE_TAIL_MAX = 20        # 마커 뒤에 허용하는 제목 길이


def _is_part_title(text: str, marker) -> bool:
    """마커 줄이 파트 제목인가, 본문 속 참조인가.

    실측 근거(ss2207): 진짜 마커는 `[별지1]` 단독 줄이고, 본문 참조는
    `[별지1]신탁계약 세부내역의 위탁자와 …` 처럼 문장이 이어지거나
    `① 위탁자는 [별지1] …` 처럼 문장 중간에 나온다. 길이만 보면 짧은 참조를 놓친다.
    """
    start, end = marker.span
    if start != 0:
        return False                                   # 문장 중간의 참조
    return len(text[end:].strip()) <= _TITLE_TAIL_MAX


def _position(e: Element, fallback: tuple[int, float] | None = None) -> tuple[int, float]:
    """지면 위치를 정렬 가능한 키로. 페이지가 먼저, 같은 페이지면 위에서 아래로.

    PDF 좌표는 아래가 원점이라 y 가 클수록 위다. 그래서 부호를 뒤집는다.
    bbox 가 없으면 읽기 순서상 직전 요소의 위치를 물려받는다(순서 정보는 그것뿐이다).
    """
    if not e.bbox or len(e.bbox) < 4:
        return (e.page, fallback[1] if fallback and fallback[0] == e.page else 0.0)
    top = max(e.bbox[1], e.bbox[3])
    return (e.page, -top)


# ===========================================================================
# T3 — 조/항/호 트리
# ===========================================================================

def build_tree(part: Part, onto: Ontology) -> list[Node]:
    """온톨로지의 중첩 체인(조→항→호)을 따라 트리를 세운다.

    체인과 recognizer 를 온톨로지에서 읽으므로, 다른 문서 종류가
    `장→조→항` 이면 온톨로지만 바꾸면 된다.
    """
    chain = onto.containment_chain("조")           # ["조","항","호"]
    if not chain:
        return []
    recognizers = [(lvl, rec.get(onto.recognizer_for(lvl))) for lvl in chain]

    roots: list[Node] = []
    stack: dict[str, Node] = {}

    def attach(node: Node, level_idx: int) -> None:
        if level_idx == 0:
            roots.append(node)
        else:
            parent_level = chain[level_idx - 1]
            parent = stack.get(parent_level)
            if parent is None:
                roots.append(node)                # 부모 없이 나온 마커 — 최상위로
            else:
                parent.children.append(node)
                node.parent = parent
        stack[chain[level_idx]] = node
        for deeper in chain[level_idx + 1:]:
            stack.pop(deeper, None)

    for e in part.elements:
        if e.kind == "table":
            target = stack.get(chain[-1]) or stack.get(chain[0])
            if target:
                target.elements.append(e)
            continue

        line = e.content()
        matched = False
        for i, (level, fn) in enumerate(recognizers):
            if fn is None:
                continue
            m = fn(line)
            if not m:
                continue
            node = Node(level=level, no=m.no, title=m.title,
                        text=m.inline_text, elements=[e])
            attach(node, i)
            matched = True
            break

        if matched:
            continue
        # 마커가 없는 줄은 가장 깊은 열린 마디에 붙인다
        target = None
        for level in reversed(chain):
            if level in stack:
                target = stack[level]
                break
        if target is not None:
            target.text = (target.text + "\n" + line).strip() if target.text else line
            target.elements.append(e)

    return roots


def build(result: ParseResult, onto: Ontology) -> Structure:
    st = split_parts(result, onto)
    body_role = onto.default_role()
    for part in st.parts:
        if part.role == body_role:
            part.articles = build_tree(part, onto)

    body = st.part(body_role)
    if body and not body.articles:
        st.warnings.append("본문에서 조를 하나도 찾지 못했습니다 — recognizer 선택을 확인하세요")
    return st


def heading_path(node: Node, part_title: str) -> list[str]:
    """파트 → 조 → 항 순 (§4)."""
    chain: list[str] = []
    n: Optional[Node] = node
    while n is not None:
        chain.append(n.label())
        n = n.parent
    return [part_title] + list(reversed(chain))
