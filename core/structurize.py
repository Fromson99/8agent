"""T7. 런타임 구조화기 — 형식으로 문서를 section 트리 + fact 로 만든다 (SPEC §3.1-3.2).

**LLM 이 없다.** 형식 파일의 `regex_markers` + `term_markers` 만 읽어 결정론으로 돈다.
같은 문서를 두 번 구조화하면 JSON 이 동일해야 한다(§7-2).

## 세 가지 규칙이 전부다

1. 요소가 **regex 마커**에 적중하면 그 레벨에 새 section 을 연다.
2. 요소가 제목 위치의 **용어형 마커**면 그 레벨에 새 section 을 연다.
3. 어느 것도 아니면 **가장 깊은 열린 section 의 내용**이 된다.

세 번째가 "모든 요소는 정확히 하나의 최심 section 에 속한다"(§3.1-2)를 보장한다.
아직 어떤 마커도 지나지 않은 요소는 기본 구역(`default_section`)에 담긴다 — 본문을
판별하는 것이 아니라 **나머지로 정의**한다. 확실한 경계만 positive 로 잡는 편이 견고하다.

## fact 는 section 좌표를 갖는다

"어떤 섹션의 어떤 용어"가 모든 downstream 태스크의 기본 좌표다(§3.2). fact 는
자기가 속한 section_id 를 반드시 들고 다닌다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from core.format_model import Format
from core.glossary import Glossary, normalize
from core.normalize import parse_value, to_jsonable
from core.parse_adapter import Cell, Element, ParseResult, Table

# heading 에서 용어 앞뒤에 허용하는 수식어 길이
_TERM_TAIL_MAX = 12


@dataclass
class Section:
    section_id: str
    marker: dict
    path: list[str]
    level: int
    content: list[dict] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    parent: Optional[str] = None
    pages: list[int] = field(default_factory=list)
    elements: list[int] = field(default_factory=list)     # 원본 요소 index

    def page_range(self) -> list[int]:
        return [min(self.pages), max(self.pages)] if self.pages else []

    def dump(self) -> dict:
        return {"section_id": self.section_id, "marker": self.marker,
                "path": self.path, "page_range": self.page_range(),
                "content": self.content, "children": self.children}


@dataclass
class Fact:
    fact_id: str
    term: str
    section_id: str
    value_type: str
    value: Any
    raw: str
    source: dict
    needs_review: bool = False
    note: str = ""

    def dump(self) -> dict:
        d = {"fact_id": self.fact_id, "term": self.term, "section_id": self.section_id,
             "value_type": self.value_type, "value": to_jsonable(self.value),
             "raw": self.raw, "source": self.source}
        if self.needs_review:
            d["needs_review"] = True
            if self.note:
                d["note"] = self.note
        return d


@dataclass
class Document:
    doc_type: str
    format_version: int
    source_file: str
    sections: list[Section] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    fitness: dict = field(default_factory=dict)
    # 형식이 설명하지 못한 요소 — 마커 구역이 아니라 **기본 구역에 내용으로** 담긴
    # 것의 index. 유실이 아니다(모든 요소는 어딘가에 담긴다, §3.1-2). "구조를 다
    # 반영했는가"의 정량 신호이며 게이트가 이 질량의 비율을 채점한다.
    residual: list[int] = field(default_factory=list)
    # 파서 레이아웃이 제목이라 한 요소가 어느 마커에도 걸리지 않은 것
    # ({index, page, text}). 마커를 놓친 가장 싼 신호다 — 놓친 경계는 대개 제목상을
    # 하고 있다. 문서별 임계값 없이 파서의 문서 무관 판단만 쓴다.
    unmatched_headings: list[dict] = field(default_factory=list)
    generated_at: str = ""

    def section(self, section_id: str) -> Optional[Section]:
        return next((s for s in self.sections if s.section_id == section_id), None)

    def facts_of(self, section_id: str) -> list[Fact]:
        return [f for f in self.facts if f.section_id == section_id]

    def find_fact(self, term: str, section_ids: Optional[list[str]] = None) -> Optional[Fact]:
        hits = [f for f in self.facts
                if f.term == term
                and not (section_ids and f.section_id not in section_ids)]
        if not hits:
            return None
        # 값 정규화에 성공한 것을 먼저 — 같은 용어가 본문에서도 잡힐 수 있다
        return next((f for f in hits if not f.needs_review), hits[0])

    def dump(self) -> dict:
        d = {
            "doc_type": self.doc_type,
            "format_version": self.format_version,
            "source_file": self.source_file,
            "generated_at": self.generated_at,
            "sections": [s.dump() for s in self.sections],
            "facts": [f.dump() for f in self.facts],
            "fitness": self.fitness,
        }
        # 비어 있으면 키를 내지 않는다 — 건강한 문서의 산출 JSON 을 바꾸지 않는다
        if self.residual:
            d["residual"] = self.residual
        if self.unmatched_headings:
            d["unmatched_headings"] = self.unmatched_headings
        return d


# ===========================================================================
# section 트리
# ===========================================================================

class _Builder:
    def __init__(self, fmt: Format, glossary: Glossary):
        self.fmt = fmt
        self.glossary = glossary
        self.sections: list[Section] = []
        self.stack: dict[int, Section] = {}          # level → 열려 있는 section
        self.term_keys = {normalize(t.term): t for t in fmt.term_markers}

    # --- 열기 -------------------------------------------------------------
    def open(self, key: str, marker: dict, level: int, element: Element) -> Section:
        parent = self._parent_for(level)
        path = (parent.path if parent else []) + [key]
        section_id = "/".join(path)
        # 같은 id 가 이미 있으면 뒤에 번호를 붙인다(반복 구조가 같은 이름을 낼 수 있다)
        if any(s.section_id == section_id for s in self.sections):
            n = sum(1 for s in self.sections if s.section_id.startswith(section_id))
            section_id = f"{section_id}#{n + 1}"
        sec = Section(section_id=section_id, marker=marker, path=path, level=level,
                      parent=parent.section_id if parent else None)
        if parent:
            parent.children.append(section_id)
        self.sections.append(sec)
        self.stack[level] = sec
        for deeper in [lv for lv in self.stack if lv > level]:
            self.stack.pop(deeper, None)             # 더 깊은 마디는 닫힌다
        sec.pages.append(element.page)
        sec.elements.append(element.index)
        return sec

    def _parent_for(self, level: int) -> Optional[Section]:
        for lv in sorted((lv for lv in self.stack if lv < level), reverse=True):
            return self.stack[lv]
        return None

    def ensure_default(self, level: int, element: Element) -> None:
        """깊은 마커가 최상위보다 먼저 오면 기본 구역을 먼저 연다.

        문서가 '제1조' 로 시작하면 조가 문서 최상위가 되어 버린다 — 같은 문서 종류인데
        머리글 한 줄 유무로 트리 모양이 달라지면 section_id 가 흔들린다.
        기본 구역을 항상 먼저 열어 경로를 안정시킨다."""
        if level > 0 and not any(lv < level for lv in self.stack):
            self.open(self.fmt.default_section,
                      {"kind": "default", "id": self.fmt.default_section}, 0, element)

    def deepest(self) -> Optional[Section]:
        return self.stack[max(self.stack)] if self.stack else None

    def ancestors_of(self, sec: Optional[Section]) -> list[str]:
        return list(sec.path) if sec else []


def _match_regex(fmt: Format, element: Element) -> Optional[tuple[Any, dict]]:
    """레벨이 얕은 마커부터 걸어 본다. 첫 적중이 이긴다.

    `require_heading` 마커는 제목 요소에서만 인정한다 — 번호 패턴이 구역 제목과
    본문 열거에 함께 쓰이는 문서에서는 패턴만으로 둘이 갈리지 않는다(RegexMarker 주석).
    """
    for marker in fmt.by_level():
        if marker.require_heading and not element.is_heading:
            continue
        captured = marker.match(element.text)
        if captured:
            return marker, captured
    return None


def _match_term(builder: _Builder, element: Element) -> Optional[Any]:
    """제목 위치의 용어형 마커. 정규표현식을 만들지 않는다(§2.3, §0-2)."""
    if not element.opens_structure:
        return None
    key = normalize(element.text)
    tm = builder.term_keys.get(key)
    if tm is None and element.is_heading:
        # 제목에 수식어가 붙는 경우("특정금전신탁 변경계약서") — 꼬리가 짧으면 인정한다.
        # heading 신호가 있을 때만 완화한다. 본문 문장에는 적용되지 않는다(§1.3).
        for k, cand in builder.term_keys.items():
            if k in key and len(key) - len(k) <= _TERM_TAIL_MAX:
                tm = cand
                break
    if tm is None:
        return None
    if tm.under:
        if normalize(tm.under) not in {normalize(p) for p in builder.ancestors_of(builder.deepest())}:
            return None                              # 지정된 상위 구역 밖이면 무시
    return tm


def build_sections(elements: list[Element], fmt: Format,
                   glossary: Glossary) -> tuple[list[Section], list[int], list[dict]]:
    """요소를 section 트리에 배정한다. 반환: (sections, 잔여, 미적중 제목).

    잔여(residual)는 기본 구역에 **내용으로** 담긴 요소의 index 다 — 형식이 문서를
    설명하지 못한 질량. 마커 요소 자신은 잔여가 아니다(구역을 열었으니 설명된 것이다).

    미적중 제목은 파서가 제목이라 한 요소가 어느 마커에도 걸리지 않은 것.
    반복되는 머리말/꼬리말(furniture)은 뺀다 — 쪽마다 나와 신호가 아니라 소음이다.
    """
    b = _Builder(fmt, glossary)
    residual: list[int] = []
    unmatched: list[dict] = []

    for e in elements:
        heading_missed = False
        if e.opens_structure:
            hit = _match_regex(fmt, e)
            if hit:
                marker, captured = hit
                key = marker.key_of(captured)
                info = {"kind": "regex", "id": marker.id}
                for name in marker.groups:
                    if captured.get(name):
                        info[name] = captured[name]
                b.ensure_default(marker.level, e)
                sec = b.open(key, info, marker.level, e)
                # 마커 뒤에 이어지는 본문은 그 section 의 내용이다
                tail = e.text[int(captured.get("_end", 0)):].strip()
                if tail:
                    sec.content.append({"type": "text", "text": tail, "page": e.page})
                continue

            tm = _match_term(b, e)
            if tm is not None:
                b.ensure_default(tm.level, e)
                b.open(tm.term, {"kind": "term", "term": tm.term}, tm.level, e)
                continue

            # 구조를 열 수 있는 요소인데 아무 마커도 안 걸렸다. 파서 레이아웃까지
            # 제목이라 하면 마커를 놓쳤을 후보다. 어디에 담기는지 본 뒤에 가른다 —
            # 기본 구역이면 잔여로 이미 세므로 여기서 또 알리지 않는다.
            heading_missed = e.is_heading and not e.is_furniture

        target = b.deepest()
        if target is None:
            # 아직 어떤 마커도 지나지 않았다 — 기본 구역을 연다(본문은 '나머지')
            target = b.open(fmt.default_section,
                            {"kind": "default", "id": fmt.default_section}, 0, e)
        if target.marker.get("kind") == "default":
            residual.append(e.index)       # 기본 구역 질량 = 형식이 설명 못 한 부분
        elif heading_missed:
            # 마커 구역 **안에** 제목상 요소가 끼어들었다 — 마커를 놓쳐 그 아래
            # 내용이 앞 구역에 붙는 조용한 오배정을 보는 유일한 창이다.
            unmatched.append({"index": e.index, "page": e.page,
                              "text": e.text[:80],
                              "landed_in": target.section_id})
        target.pages.append(e.page)
        target.elements.append(e.index)
        target.content.append(_content_of(e))

    return b.sections, residual, unmatched


def _content_of(e: Element) -> dict:
    """내용 한 덩어리 — 출처(page/bbox)를 함께 실어 downstream 이 되돌릴 수 있게 한다."""
    base = {"page": e.page}
    if e.bbox:
        base["bbox"] = e.bbox
    if e.meta:
        base["meta"] = e.meta          # 페이지·bbox 가 없는 문서의 출처 (예: 발화 타임스탬프)
    if e.table:
        return {"type": "table", **base, "cells": e.table.dump()}
    if e.is_picture:
        # 그림은 표와 같은 자리에 선다 — 구역을 열지 않고 구역의 내용이 된다.
        # 캡션이 유일한 언어 단서이므로 `text` 로도 둔다(fact 추출이 훑는 자리다).
        return {"type": "figure", "text": e.text, **base,
                "caption": e.text, "ref": (e.meta or {}).get("ref", ""),
                "element_type": e.type}
    return {"type": "text", "text": e.text, **base, "element_type": e.type}


# ===========================================================================
# fact 추출 (§3.1-4) — **문장 레벨**
# ===========================================================================
#
# section 은 문단/구역 레벨, fact 는 **문장 레벨** 개념이다(§1.1). 그래서 추출은
# 단순하다: section 이 자른 구역 안을 문장 단위로 다시 끊고, 그 문장에 용어집의
# fact 용어가 나오면 그 문장이 곧 그 용어의 fact다.
#
# ## 라벨-값 매칭을 하지 않는 이유
#
# "매칭한 용어 **옆의** 어느 것이 값인가"를 코드로 맞히려 들면 문서를 하나 붙일 때마다
# 임계값이 하나씩 늘어난다(실제로 그렇게 늘어났다: 값 꼬리 길이, 라벨 전용 줄,
# 셀이 용어로 시작하는가 …). 그건 형식 컴파일로 stochastic 을 가둔 의미를 없앤다.
#
# 대신 **좌표로 가른다.** 같은 용어가 본문 문장에도, 별지 표에도 나오지만
# 둘은 section_id 가 다르다 — 태스크 규칙이 `별지1/신탁계약 세부내역` 을 지정하면
# 본문의 mention 은 애초에 조회되지 않는다. 구별은 추출이 아니라 좌표의 몫이다.
#
# 값 정규화는 여전히 value_type 파서가 하고, 실패는 needs_review 로 남는다(§3.3).

# 문장 경계 — 한국어 종결부호 + 줄바꿈
_SENTENCE_END = ("다.", "요.", "함.", "음.", ".", "?", "!", ";")


@dataclass
class _Unit:
    """문장 레벨 단위 하나 — 텍스트면 문장, 표면 행.

    표에서 온 단위는 **자기가 어느 표의 어느 행인지**를 들고 다닌다. 행을 한 문장으로
    이어 붙이고 나면 `연 1.5%` 가 어느 열의 값이었는지 사라지는데, 표 밖으로 값을
    꺼내는 순간 그 열 이름이 곧 값의 의미이기 때문이다.
    """
    text: str
    page: int
    bbox: Optional[list[float]] = None
    cell: Optional[tuple[int, int]] = None
    cells: list[Cell] = field(default_factory=list)
    table: Optional[Table] = None


def _split_sentences(text: str) -> list[str]:
    """문장 단위로 끊는다. 종결부호가 없으면 줄 전체가 한 문장이다."""
    out, buf = [], ""
    for ch in text:
        buf += ch
        if any(buf.endswith(e) for e in _SENTENCE_END):
            s = buf.strip()
            if s:
                out.append(s)
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out or ([text.strip()] if text.strip() else [])


def _units(sec: Section, by_index: dict[int, Element]) -> list[_Unit]:
    """구역의 내용을 문장 레벨 단위로 편다."""
    units: list[_Unit] = []
    elem_indices = _content_element_indices(sec, by_index)
    for item, elem_index in zip(sec.content, elem_indices):
        elem = by_index.get(elem_index)
        bbox = elem.bbox if elem else None
        page = item.get("page", 1)
        if item.get("type") == "table":
            table = _rebuild_table(item["cells"])
            for row in table.rows():
                text = " ".join(c.text for c in row if c.text).strip()
                if text:
                    first = row[0] if row else None
                    units.append(_Unit(text, page, bbox,
                                       (first.row, first.col) if first else None,
                                       cells=row, table=table))
        else:
            for sentence in _split_sentences(item.get("text", "")):
                units.append(_Unit(sentence, page, bbox))
    return units


def _locate(unit: _Unit, term: str, glossary: Glossary) -> dict:
    """표 단위에서 이 용어가 실제로 들어 있는 셀과 그 셀의 표 안 좌표.

    행 전체를 한 문장으로 이어 붙였으므로 `raw` 만으로는 어느 칸인지 모른다. 용어의
    표면형이 든 셀을 되찾아 **행 머리 · 열 머리**를 붙인다 — 그러면 값이 표를 떠나도
    `중도해지수수료 × 1년 미만` 이 남는다.
    """
    if not unit.cells or unit.table is None:
        return {}
    surfaces = [normalize(s) for s in glossary.surfaces_of(term)]
    hit = next((c for c in unit.cells
                if c.text and any(s and s in normalize(c.text) for s in surfaces)), None)
    if hit is None:
        hit = unit.cells[0]
    out: dict = {"cell": [hit.row, hit.col]}
    row_h = unit.table.row_header_of(hit.row)
    col_h = unit.table.col_header_of(hit.col)
    if row_h and normalize(row_h) != normalize(hit.text):
        out["row_header"] = row_h
    if col_h and normalize(col_h) != normalize(hit.text):
        out["col_header"] = col_h
    if row_h or col_h:
        out["header_source"] = unit.table.header_source()
    return out


def extract_facts(sections: list[Section], glossary: Glossary,
                  elements: list[Element]) -> list[Fact]:
    """구역 안의 문장 단위를 훑어, 용어가 나온 문장을 그 용어의 fact 로 삼는다."""
    fact_index = {normalize(s): term
                  for term in glossary.fact_terms()
                  for s in glossary.surfaces_of(term)}
    by_index = {e.index: e for e in elements}
    facts: list[Fact] = []
    seq = 0

    for sec in sections:
        for unit in _units(sec, by_index):
            for term in _terms_in(unit.text, fact_index):
                seq += 1
                facts.append(_make_fact(seq, term, sec, glossary, unit.text,
                                        unit.page, unit.bbox,
                                        where=_locate(unit, term, glossary)))

        # 구역 제목 자체가 fact 용어인 경우 — 그 구역의 내용 전체가 값이다.
        # 용어집이 `kind: [section, fact]` 로 선언한 용어가 이 형태다(§1.1):
        # "중도해지수수료" 는 소절 제목이면서, 그 소절의 표가 곧 그 값이다.
        term = sec.marker.get("term")
        if term and term in set(glossary.fact_terms()) and sec.content:
            raw = "\n".join(u.text for u in _units(sec, by_index)).strip()
            if raw and not any(f.term == term and f.section_id == sec.section_id
                               for f in facts):
                seq += 1
                facts.append(_make_fact(seq, term, sec, glossary, raw,
                                        sec.content[0].get("page", 1), None))
    return facts


def _terms_in(text: str, fact_index: dict[str, str]) -> list[str]:
    """이 문장에 나온 fact 용어들. 긴 표면형을 먼저 봐서 짧은 것에 먹히지 않게."""
    norm = normalize(text)
    if not norm:
        return []
    found: list[str] = []
    taken: list[tuple[int, int]] = []
    for key in sorted(fact_index, key=len, reverse=True):
        pos = norm.find(key)
        while pos >= 0:
            end = pos + len(key)
            if not any(a < end and pos < b for a, b in taken):
                taken.append((pos, end))
                term = fact_index[key]
                if term not in found:
                    found.append(term)
            pos = norm.find(key, pos + 1)
    return found


def _content_element_indices(sec: Section, by_index: dict[int, Element]) -> list[int]:
    """content 항목과 원본 요소 index 를 짝지어 준다(길이가 어긋나면 앞에서부터)."""
    idxs = [i for i in sec.elements if i in by_index]
    if len(idxs) >= len(sec.content):
        return idxs[len(idxs) - len(sec.content):]
    return idxs + [idxs[-1] if idxs else -1] * (len(sec.content) - len(idxs))


def _rebuild_table(dumped: dict) -> Table:
    """`Table.dump()` 의 역. 셀에 필드가 늘어도 기본값으로 채워진다."""
    cells = [Cell(**c) for c in dumped.get("cells", [])]
    n_rows = dumped.get("n_rows") or (max((c.row for c in cells), default=-1) + 1)
    n_cols = dumped.get("n_cols") or (max((c.col for c in cells), default=-1) + 1)
    return Table(n_rows=n_rows, n_cols=n_cols, cells=cells)


def _make_fact(seq: int, term: str, sec: Section, glossary: Glossary, raw: str,
               page: int, bbox, where: Optional[dict] = None) -> Fact:
    vt = glossary.value_type(term)
    value = parse_value(vt, raw)
    source = {"page": page, "bbox": bbox}
    source.update(where or {})
    needs_review = value is None or (vt != "text" and value == "")
    return Fact(fact_id=f"f-{seq:03d}", term=term, section_id=sec.section_id,
                value_type=vt, value=value, raw=raw, source=source,
                needs_review=needs_review,
                note=f"{vt} 로 정규화하지 못했습니다" if needs_review else "")


# ===========================================================================

def run(parsed: ParseResult, fmt: Format, glossary: Glossary) -> Document:
    """파싱 결과 → 구조화된 Document. 여기까지가 런타임 국면의 전부다."""
    sections, residual, unmatched = build_sections(parsed.elements, fmt, glossary)
    facts = extract_facts(sections, glossary, parsed.elements)
    doc = Document(
        doc_type=fmt.doc_type, format_version=fmt.format_version,
        source_file=parsed.path.rsplit("/", 1)[-1],
        sections=sections, facts=facts, residual=residual,
        unmatched_headings=unmatched,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return doc
