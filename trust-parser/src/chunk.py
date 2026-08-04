"""T4. 청킹 — **순수 의미 단위. 토큰 예산 없음** (SPEC §5-3, §D1).

## 토큰 기반 split/merge 를 하지 않는 이유

검색이 임베딩을 쓰지 않기로 했다(§D1). 임베딩 모델의 입력 한계가 사라지므로
토큰 크기를 맞출 이유 자체가 없다. 남는 상한은 LLM 컨텍스트뿐이고 조 단위 청크는
거기에 전혀 문제가 없다. 그래서 분할 기준은 **오직 의미 경계**(조/항/필드)다.

문장 중간에서 자르지 않는다 — §9-6 이 "모든 청크 경계가 의미 경계와 일치" 를 요구한다.

## 무엇을 어떻게 자를지는 온톨로지가 정한다 (§C6)

    structure.조.chunk:  primary         조 = 기본 청크 단위
    structure.조.chunk_boundary: hard    이 경계를 절대 넘지 않음 (§9-2)
    structure.항.chunk:  split_if_long   조가 매우 길 때만 항 단위로
    structure.호.chunk:  inline          부모 항의 items[] 로
    structure.별지.chunk: per_field      필드/표 단위

코드에 "조는 이렇게, 항은 저렇게" 를 박지 않는다. HybridChunker 도 쓰지 않는다 —
자기 기준으로 병합·분할하므로 조 경계 불가침을 보장하지 못한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import recognizers as rec
from ontology import Ontology
from parse_stage import Element
from structure import Node, Part, Structure, heading_path

# 조가 "매우 길다"의 기준 — 토큰 예산이 아니라 **가독·인용 단위** 판단이다.
# 이 값을 넘으면 항 단위로 나눈다(의미 경계). 넘지 않으면 조 하나가 한 청크다.
LONG_ARTICLE_CHARS = 1200


@dataclass
class RawChunk:
    """태깅 전의 청크. tag_rules 가 role/topic/refs 를 채운다."""
    level: str                              # 조 | 항 | 호 | 필드 | 표
    text: str
    part_role: str
    article: Optional[str] = None           # "15"
    article_title: str = ""
    clause: Optional[str] = None            # "①"
    heading_path: list[str] = field(default_factory=list)
    page: int = 1
    bbox: Optional[list[float]] = None
    elements: list[Element] = field(default_factory=list)
    items: Optional[list[dict]] = None
    options: Optional[list[dict]] = None
    table_options: Optional[list[str]] = None
    structure_kind: Optional[str] = None
    value_template: Optional[str] = None
    field_name: Optional[str] = None        # 별지 필드명
    cross_ref_cell: Optional[str] = None    # 별지 표의 `계약서제N조` 셀 원문
    seq: int = 0

    def size(self) -> int:
        return len(self.text)


# ===========================================================================
# 본문 — 조 단위 기본, 길면 항 단위
# ===========================================================================

def _clause_chunks(article: Node, part_title: str, role: str,
                   onto: Ontology) -> list[RawChunk]:
    splittable = set(onto.nodes_with_chunk("split_if_long"))
    inline = set(onto.nodes_with_chunk("inline"))
    chunks: list[RawChunk] = []
    clauses = [c for c in article.children if c.level in splittable]

    # 조 머리글(항 앞의 본문)이 있으면 조 단위 청크로 따로 남긴다
    if article.text.strip():
        chunks.append(RawChunk(
            level="조", text=article.text.strip(), part_role=role,
            article=article.no, article_title=article.title,
            heading_path=heading_path(article, part_title),
            page=article.page(), bbox=article.bbox(), elements=list(article.elements)))

    for c in clauses:
        items = [{"level": g.level, "no": g.no, "text": g.full_text()}
                 for g in c.children if g.level in inline]
        body = c.text.strip()
        chunks.append(RawChunk(
            level=c.level, text=body or c.full_text(), part_role=role,
            article=article.no, article_title=article.title, clause=c.no,
            heading_path=heading_path(c, part_title),
            page=c.page(), bbox=c.bbox(), elements=list(c.elements),
            items=items or None))
    return chunks


def chunk_body(part: Part, onto: Ontology, part_title: str) -> list[RawChunk]:
    """본문 청킹 — 온톨로지 chunk 선언을 읽어 실행한다.

    primary(조) 를 기본 단위로 하고, 그 조가 길면 split_if_long(항) 으로 나눈다.
    inline(호) 은 부모 항의 items[] 로 들어간다. 토큰 기반 분할·병합은 하지 않는다.
    """
    primary = onto.nodes_with_chunk("primary")
    splittable = set(onto.nodes_with_chunk("split_if_long"))
    if not primary:
        return []

    out: list[RawChunk] = []
    for article in part.articles:
        whole = article.full_text()
        children = [c for c in article.children if c.level in splittable]

        if not children:
            # 나눌 하위 단위가 없으면 조 하나가 한 청크 (정본 body-a01 이 이 형태)
            out.append(RawChunk(
                level=article.level, text=whole, part_role=part.role,
                article=article.no, article_title=article.title,
                heading_path=heading_path(article, part_title),
                page=article.page(), bbox=article.bbox(),
                elements=list(article.elements)))
        else:
            # 항이 있으면 항 단위로. 정본이 body-a02-p2·body-a15-p1 처럼
            # 항 단위 레코드를 기대하며, §12 는 정본과의 구조 일치를 최우선으로 둔다.
            out.extend(_clause_chunks(article, part_title, part.role, onto))
    return out


# ===========================================================================
# 별지 — 필드/표 단위
# ===========================================================================

# 별지 표에서 값이 아니라 라벨인 셀을 걸러내기 위한 최소 길이
_MIN_LABEL = 2


def _dedupe_row(cells: list[str]) -> list[str]:
    """병합 셀이 가로로 복제된 것을 접는다.

    실측(체결본 골든 PDF): 도클링이 7열 표에서 값을 2~6열에 똑같이 반복했다.
    중복 제거 없이 Fact 를 뽑으면 같은 값이 6번 들어온다.
    """
    out: list[str] = []
    for c in cells:
        c = rec.normalize_ws(c)
        if not c:
            continue
        if out and out[-1] == c:
            continue
        if c in out:
            continue
        out.append(c)
    return out


def chunk_appendix(part: Part, onto: Ontology, part_title: str) -> list[RawChunk]:
    """별지 요소를 필드/표 청크로.

    표 행 하나가 대개 필드 하나다(라벨 | 값… | 계약서제N조).
    표가 아닌 줄은 표 밖 기재 사항이므로 필드로 남긴다.
    """
    out: list[RawChunk] = []
    known = set(onto.fields)
    buffer: list[Element] = []

    for e in part.elements:
        if e.kind == "table" and e.table:
            for row in e.table:
                cells = _dedupe_row(row)
                if not cells:
                    continue
                label = cells[0]
                xref = next((rec.contract_article_cell(c) for c in reversed(cells)
                             if rec.contract_article_cell(c)), None)
                values = [c for c in cells[1:]
                          if rec.contract_article_cell(c) is None]

                # 체크박스 그리드인가
                opts = rec.checkbox_options(" ".join(cells))
                is_grid = len(opts) >= 5

                if is_grid:
                    out.append(RawChunk(
                        level="표", text=rec.normalize_ws(" ".join(cells))[:400],
                        part_role=part.role, heading_path=[part_title, label],
                        page=e.page, bbox=e.bbox, elements=[e], options=opts,
                        structure_kind="checkbox_grid",
                        field_name=label if label in known else None,
                        cross_ref_cell=xref))
                    continue

                if len(label) < _MIN_LABEL and not values:
                    continue
                text = f"{label}: {' '.join(values)}".strip(": ").strip()
                multi = len(values) > 1
                out.append(RawChunk(
                    level="표" if multi else "필드",
                    text=text, part_role=part.role,
                    heading_path=[part_title, label],
                    page=e.page, bbox=e.bbox, elements=[e],
                    table_options=values if multi else None,
                    field_name=label if label in known else label,
                    cross_ref_cell=xref))
        else:
            buffer.append(e)

    # 표로 인식되지 않은 별지(빈 템플릿에서 흔하다)는 텍스트 시퀀스로 온다.
    # 실측(ss2207 별지1): `계좌번호 / 신탁금액 / 금 원정(\ ) / 계약서제2조 / 신탁기간 / …`
    # 즉 `라벨 → 값칸 → 계약서제N조` 순서다. cross-ref 셀이 필드의 **종결자** 역할을 한다.
    # 온톨로지가 "별지 필드는 cross-ref 로 조에 대응"(structure.별지.field_links_to)을
    # 선언하고, 여기서는 이 문서 포맷에서 그 그룹핑을 실현할 뿐이다.
    out.extend(_group_appendix_text(buffer, part, onto, part_title, known))
    return out


def _group_appendix_text(elements: list[Element], part: Part, onto: Ontology,
                         part_title: str, known: set[str]) -> list[RawChunk]:
    out: list[RawChunk] = []
    buf: list[Element] = []

    def flush(xref: Optional[str], anchor: Optional[Element]) -> None:
        nonlocal buf
        lines = [rec.normalize_ws(e.content()) for e in buf]
        lines = [l for l in lines if l]
        buf = []
        if not lines:
            return
        # 알려진 필드명이 있으면 그것을 라벨로, 없으면 첫 줄을 라벨로
        label = next((l for l in lines if l in known), lines[0])
        values = [l for l in lines if l != label]
        anchor = anchor or (buf[0] if buf else None)
        page = anchor.page if anchor else 1
        bbox = anchor.bbox if anchor else None
        text = f"{label}: {' '.join(values)}".strip(": ").strip()
        out.append(RawChunk(
            level="표" if len(values) > 1 else "필드",
            text=text or label, part_role=part.role,
            heading_path=[part_title, label],
            page=page, bbox=bbox, elements=list(elements[:0]),
            table_options=values if len(values) > 1 else None,
            value_template=values[0] if len(values) == 1 else None,
            field_name=label if label in known else label,
            cross_ref_cell=xref))

    # 체크박스 그리드는 요소 하나에 안 담긴다 — 실측(ss2207 별지1): 운용방법 1~24 가
    # 열 단위로 쪼개져 24개 이상의 개별 요소로 온다. 연속 구간을 모아서 판정한다.
    grid_run: list[Element] = []

    def flush_grid() -> None:
        nonlocal grid_run
        run, grid_run = grid_run, []
        if not run:
            return
        joined = " ".join(rec.normalize_ws(x.content()) for x in run)
        opts = rec.checkbox_options(joined)
        if len(opts) >= 5:
            out.append(RawChunk(
                level="표", text=joined[:400], part_role=part.role,
                heading_path=[part_title, "신탁자금 운용방법"],
                page=run[0].page, bbox=run[0].bbox, elements=list(run),
                options=opts, structure_kind="checkbox_grid",
                field_name="신탁자금 운용방법"))
        else:
            for x in run:                      # 그리드가 아니었으면 일반 줄로 되돌린다
                buf.append(x)

    for e in elements:
        line = rec.normalize_ws(e.content())
        if not line:
            continue
        if rec.checkbox_options(line):         # `N. 라벨` 이 하나라도 있으면 그리드 후보
            if not grid_run:
                flush(None, e)
            grid_run.append(e)
            continue
        # 그리드 중간에 안내 문구(주1~주5)가 끼어 구간이 끊기는 일이 잦다.
        # 짧은 줄은 흘려보내고, 문단급 텍스트가 나와야 그리드를 닫는다.
        if grid_run and len(line) < 120:
            continue
        flush_grid()

        xref = rec.contract_article_cell(line)
        if xref:
            flush(xref, e)            # cross-ref 를 만나면 직전까지가 한 필드
            continue
        # 다음 라벨이 시작되면(알려진 필드명) 앞의 것을 끊는다
        if line in known and buf and any(rec.normalize_ws(b.content()) in known for b in buf):
            flush(None, buf[0])
        buf.append(e)
    flush_grid()
    flush(None, buf[0] if buf else None)
    return out


# ===========================================================================

PART_TITLES = {
    "약관본문": "특정금전신탁 계약서",
    "별지1_입력": "[별지1] 신탁계약 세부내역",
    "별지2_변경": "[별지2] 변경계약서",
}


def build(st: Structure, onto: Ontology) -> list[RawChunk]:
    body_role = onto.default_role()
    out: list[RawChunk] = []
    for part in st.parts:
        title = PART_TITLES.get(part.role, part.role)
        if part.role == body_role:
            out.extend(chunk_body(part, onto, title))
        else:
            out.extend(chunk_appendix(part, onto, title))
    out = _merge_grids(out)
    for i, c in enumerate(out):
        c.seq = i
    return out


def _merge_grids(chunks: list[RawChunk]) -> list[RawChunk]:
    """같은 필드의 체크박스 그리드가 여러 조각으로 나오면 하나로 합친다.

    실측(ss2207): 운용방법 1~24 가 열 단위로 흩어지고 중간에 주석이 끼어
    2개 청크로 갈렸다. 정본은 옵션 24개를 담은 **하나의** 그리드를 기대한다.
    """
    merged: list[RawChunk] = []
    by_field: dict[str, RawChunk] = {}
    for c in chunks:
        if c.structure_kind != "checkbox_grid" or not c.field_name:
            merged.append(c)
            continue
        first = by_field.get(c.field_name)
        if first is None:
            by_field[c.field_name] = c
            merged.append(c)
            continue
        seen = {o["no"] for o in (first.options or [])}
        for o in (c.options or []):
            if o["no"] not in seen:
                first.options.append(o)
                seen.add(o["no"])
        first.options.sort(key=lambda o: o["no"])
        first.text = (first.text + " " + c.text)[:600]
        first.elements.extend(c.elements)
    return merged
