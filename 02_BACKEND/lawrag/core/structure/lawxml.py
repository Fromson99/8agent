"""국가법령정보센터 본문 XML → 구조 해석 결과 (결정적 — 추론 없음).

PDF 는 마커·타이포그래피로 구조를 **추론**해야 하지만, law.go.kr 본문 XML 은
편·장·절·조·항·호·목 계층이 태그로 이미 명시되어 있다. 여기서는 그 계층을
`StructureResult` 로 **옮기기만** 하고, 검수 화면이 요구하는 좌표·페이지는
PyMuPDF 로 본문을 조판한 합성 PDF 에서 얻는다. 산출물은 업로드 경로와 같은
`viewer.payload()` 를 통과하므로 스키마가 어긋날 수 없다.

두 가지 입력 (실측 — docs/site_survey.md §3.5):
- `<법령>` (target=law): 조문단위/항/호/목 이 전부 태그다. 편·장·절은
  조문여부=전문 인 행의 텍스트에서 읽는다.
- `<AdmRulService>` (target=admrul): 조문내용이 **평문 덩어리**다
  (기본정보의 조문형식여부=N). 행 머리 패턴(제1-1조·①·1.·가.)으로 가른다 —
  들여쓰기·번호가 규칙적이라 이것도 결정적이다.

fitness 는 1.0/hot 으로 둔다 — 구조가 원천 데이터에서 왔으므로 "추론이 얼마나
믿을 만한가"라는 질문 자체가 성립하지 않는다. stats.source 로 출처를 남긴다.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lawrag.core.legal_coordinate import MOK_LETTERS
from lawrag.core.structure.model import (
    Block,
    Fingerprint,
    Ladder,
    Node,
    Rung,
    StructureResult,
)
from lawrag.core.structure.synthpdf import Layout as _Layout
from lawrag.core.structure.synthpdf import _circ_no

# ---------------------------------------------------------------- 중간 표현

# 계층 순서 — 문서에 없는 종류는 건너뛰고 있는 것끼리 이 순서로 레벨을 받는다
KIND_ORDER = ["편", "장", "절", "관", "조", "항", "호", "목"]
FAMILY = {"편": "kr_편", "장": "kr_장", "절": "kr_절", "관": "kr_관",
          "조": "kr_article", "항": "circled", "호": "dot_number:1",
          "목": "hangul_dot", "부칙": "buchik", "별표": "annex"}
# 조판 들여쓰기 (pt) — 화면에서 계층이 보이게만 하면 된다
INDENT = {"편": 0, "장": 0, "절": 8, "관": 8, "조": 0, "항": 14, "호": 28,
          "목": 42, "부칙": 0, "별표": 0, "내용": 14}
FONT = {"편": 14.0, "장": 13.0, "절": 12.0, "관": 12.0, "조": 11.0,
        "부칙": 12.0, "별표": 11.0}
BODY_FONT = 9.5

_DIV_RE = re.compile(r"^제(\d+)(편|장|절|관)")
# 조 행: "제1-1조(목적)" / "제5조(…)" / "제5-13조" (제목 없이 끝) / "제3-2조 <삭제 …>"
# 뒤가 (·<·행끝이어야 한다 — "제7-2조제1항의 …" 같은 인용 계속행을 조로 오인하면 안 된다
_JO_LINE_RE = re.compile(r"^제(\d+(?:-\d+)?)조(?:의(\d+))?\s*(?:\(|<|$)")
_JO_TOKEN_RE = re.compile(r"^제\d+(?:-\d+)?조(?:의\d+)?")
_JO_TITLE_RE = re.compile(r"^제[\d-]+조(?:의\d+)?\s*\(([^)]*)\)")
# 항 번호: ①-㊿ 그리고 51항 이상… 이 아니라 **16항 이상**은 원문이 <16> 으로 찍는다 (실측)
_HANG_RE = re.compile(r"^([①-㊿]|<\d{1,2}>)")
_HO_RE = re.compile(r"^(\d+(?:의\d+)?)\.\s")       # 호 가지 "10의2." 실재 (실측 60건)
_MOK_RE = re.compile(rf"^([{MOK_LETTERS}])\.\s")
_MOK_SEQ = MOK_LETTERS


@dataclass
class U:
    """구역 하나 — XML 에서 옮겨 온 중간 마디."""
    kind: str                       # KIND_ORDER 의 하나 | 부칙 | 별표
    surface: str = ""
    title: str = ""
    heading: str = ""               # 제목 블록에 찍을 원문 (번호 포함)
    ordinal: Optional[tuple] = None
    content: list[str] = field(default_factory=list)
    children: list["U"] = field(default_factory=list)


def _jo_ordinal(no: str, branch: str | None) -> tuple:
    parts = [int(p) for p in no.split("-")]
    if branch:
        parts.append(int(branch))
    return tuple(parts)


def _hang_no(s: str) -> int:
    """항 번호 표면 → 수. ①-㊿ 와 16항 이상의 <16> 표기(실측) 둘 다."""
    m = re.fullmatch(r"<(\d+)>", s)
    if m:
        return int(m.group(1))
    return _circ_no(s)


def _num_ordinal(s: str) -> Optional[tuple]:
    """"4" → (4,) / "10의2" → (10, 2) — 호 가지번호는 별개 호다."""
    m = re.fullmatch(r"(\d+)(?:의(\d+))?", s)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2))) if m.group(2) else (int(m.group(1)),)


# ---------------------------------------------------------------- XML → U 트리

def _clean(text: Optional[str]) -> str:
    return re.sub(r"[ \t]+", " ", (text or "").replace(" ", " ")).strip()


def _mok_unit(mok: ET.Element) -> U:
    no = _clean(mok.findtext("목번호")).rstrip(".")
    idx = _MOK_SEQ.find(no) + 1 if no in _MOK_SEQ else None
    return U(kind="목", surface=f"{no}." if no else "목",
             ordinal=(idx,) if idx else None,
             heading=_clean(mok.findtext("목내용")))


def _ho_units(el: ET.Element) -> list[U]:
    """항(또는 항 없는 조)의 호·목 — **문서 순서**로 걷는다.

    법령 XML 에서 목은 호의 자식이 아니라 항의 자식으로 온다(실측: 목의 부모는
    전부 항). 순서상 바로 앞의 호에 속하는 것이므로 앞 호의 자식으로 되돌린다.
    """
    out: list[U] = []
    for child in el:
        if child.tag == "호":
            no = _clean(child.findtext("호번호")).rstrip(".")
            out.append(U(kind="호", surface=f"{no}.",
                         ordinal=_num_ordinal(no),
                         heading=_clean(child.findtext("호내용")),
                         children=[_mok_unit(m) for m in child.findall("목")]))
        elif child.tag == "목":
            (out[-1].children if out else out).append(_mok_unit(child))
    return out


def law_tree(root: ET.Element) -> tuple[list[U], dict]:
    """`<법령>` → U 트리. 편·장·절·관은 전문 행에서 연다."""
    top: list[U] = []
    div_stack: list[U] = []         # 열린 편/장/절/관

    def attach(u: U) -> None:
        (div_stack[-1].children if div_stack else top).append(u)

    for jo in root.iter("조문단위"):
        text = _clean(jo.findtext("조문내용"))
        if _clean(jo.findtext("조문여부")) == "전문":
            m = _DIV_RE.match(text)
            if not m:
                # 편·장 아닌 전문 행 — 현재 구역의 내용으로 남긴다 (버리지 않는다)
                if text and div_stack:
                    div_stack[-1].content.append(text)
                elif text and top:
                    top[-1].content.append(text)
                elif text:
                    _ensure_head(top).content.append(text)
                continue
            kind = m.group(2)
            u = U(kind=kind, surface=f"제{m.group(1)}{kind}", title=text,
                  ordinal=(int(m.group(1)),), heading=text)
            while div_stack and KIND_ORDER.index(div_stack[-1].kind) >= KIND_ORDER.index(kind):
                div_stack.pop()
            attach(u)
            div_stack.append(u)
            continue

        no = _clean(jo.findtext("조문번호"))
        branch = _clean(jo.findtext("조문가지번호")) or None
        surface = f"제{no}조" + (f"의{branch}" if branch else "")
        u = U(kind="조", surface=surface, title=_clean(jo.findtext("조문제목")),
              ordinal=_jo_ordinal(no, branch) if no.isdigit() or "-" in no else None,
              heading=text or surface)
        for hang in jo.findall("항"):
            h_no = _clean(hang.findtext("항번호"))
            h_text = _clean(hang.findtext("항내용"))
            if h_no or h_text:
                hu = U(kind="항", surface=h_no or "항",
                       ordinal=(_hang_no(h_no),) if h_no and _hang_no(h_no) else None,
                       heading=h_text or h_no, children=_ho_units(hang))
                u.children.append(hu)
            else:
                # 번호 없는 항 껍데기 — 호를 조에 바로 단다
                u.children.extend(_ho_units(hang))
        attach(u)

    base = root.find("기본정보")
    info = {el.tag: _clean(el.text) for el in (base if base is not None else [])
            if el.text and not len(el)}
    return top, info


def _match_line(line: str, allow_div: bool) -> Optional[U]:
    """행 머리 마커 → U. 마커가 아니면 None (계속행)."""
    if allow_div and (m := _DIV_RE.match(line)):
        return U(kind=m.group(2), surface=f"제{m.group(1)}{m.group(2)}",
                 title=line, ordinal=(int(m.group(1)),), heading=line)
    if (m := _JO_LINE_RE.match(line)):
        tm = _JO_TITLE_RE.match(line)
        return U(kind="조", surface=_JO_TOKEN_RE.match(line).group(0),
                 title=tm.group(1) if tm else "",
                 ordinal=_jo_ordinal(m.group(1), m.group(2)), heading=line)
    if (m := _HANG_RE.match(line)):
        n = _hang_no(m.group(1))
        return U(kind="항", surface=m.group(1),
                 ordinal=(n,) if n else None, heading=line)
    if (m := _HO_RE.match(line)):
        return U(kind="호", surface=f"{m.group(1)}.",
                 ordinal=_num_ordinal(m.group(1)), heading=line)
    if (m := _MOK_RE.match(line)):
        idx = _MOK_SEQ.find(m.group(1)) + 1
        return U(kind="목", surface=f"{m.group(1)}.",
                 ordinal=(idx,) if idx else None, heading=line)
    return None


def _parse_flat(lines, allow_div: bool, head: Optional[U] = None) -> list[U]:
    """평문 행들 → U 트리 (공용 분류기 — 행정규칙 조문내용·부칙내용·별표내용).

    head 를 주면 첫 마커 이전의 서문 행이 그 마디의 내용이 되고, 없으면
    "(전문)" 마디를 만들어 담는다 — 어느 쪽이든 행은 버려지지 않는다.
    """
    top: list[U] = []
    stack: list[U] = []             # 열린 마디 (얕은 → 깊은)

    def close_to(kind: str) -> None:
        idx = KIND_ORDER.index(kind)
        while stack and KIND_ORDER.index(stack[-1].kind) >= idx:
            stack.pop()

    for raw in lines:
        line = _clean(raw)
        if not line:
            continue
        u = _match_line(line, allow_div)
        if u is not None:
            close_to(u.kind)
            (stack[-1].children if stack else top).append(u)
            stack.append(u)
        elif stack:
            stack[-1].content.append(line)
        elif head is not None:
            head.content.append(line)
        else:
            _ensure_head(top).content.append(line)
    return top


def admrul_tree(root: ET.Element) -> tuple[list[U], dict]:
    """`<AdmRulService>` → U 트리. 조문내용을 행 머리 패턴으로 가른다.

    조문내용은 두 켜로 온다 — 조문형식여부=N 은 문서 전체가 한 덩어리,
    =Y 는 **조마다 요소가 반복**된다(실측: 금융복합기업집단 감독규정 22개).
    전부 이어 한 흐름으로 가른다. findtext(첫 요소만)로 읽으면 Y형 문서의
    본문이 통째로 사라진다 — 실측(2026-08-13): 조 22개 중 제1조만 남았다.
    """
    lines: list[str] = []
    for el in root.iter("조문내용"):
        lines.extend((el.text or "").splitlines())
    top = _parse_flat(lines, allow_div=True)
    base = root.find("행정규칙기본정보")
    info = {el.tag: _clean(el.text) for el in (base if base is not None else [])
            if el.text and not len(el)}
    return top, info


def _ensure_head(top: list[U]) -> U:
    """조문 앞의 서문 행이 붙을 자리 — 이름 없는 전문 마디."""
    if not top or top[0].kind != "조" or top[0].surface != "(전문)":
        top.insert(0, U(kind="조", surface="(전문)", title="전문", heading="전문"))
    return top[0]


def _strip_md_header(text: str) -> list[str]:
    """lawrag/core/hwp5_md.py/hwpx_md 사이드카의 `# key: value` 출처 머리를 뗀 본문 행들."""
    lines = text.splitlines()
    i = 0
    while i < len(lines) and (lines[i].startswith("# ") or not lines[i].strip()):
        i += 1
    return lines[i:]


def _appendix_units(root: ET.Element, annex_md: Optional[dict[str, str]] = None,
                    stats: Optional[dict] = None) -> list[U]:
    """부칙·별표 → 최상위 컨테이너 마디들 (법령·행정규칙 공통).

    annex_md: {"별표 14의1": md 본문} — 수집해 둔 별표서식 HWP 를 변환한
    사이드카다. 있으면 XML 별표내용 대신 쓴다 — XML 은 표를 평문으로 뭉개는데
    (실측: 표 태그 0건) HWP→md 변환은 md 표로 살리기 때문이다.
    """
    annex_md = annex_md or {}
    out: list[U] = []

    buchik = root.find("부칙")
    if buchik is not None:
        cont = U(kind="부칙", surface="부칙", title="부칙", heading="부칙")
        units = buchik.findall("부칙단위")
        if units:
            rows = [(_clean(u.findtext("부칙공포일자")), _clean(u.findtext("부칙공포번호")),
                     u.findtext("부칙내용") or "") for u in units]
        else:                       # 행정규칙: 단위 래퍼 없이 세 태그가 반복된다 (실측)
            rows, cur = [], ["", "", ""]
            for el in buchik:
                if el.tag == "부칙공포일자":
                    if any(cur):
                        rows.append(tuple(cur))
                    cur = [_clean(el.text), "", ""]
                elif el.tag == "부칙공포번호":
                    cur[1] = _clean(el.text)
                elif el.tag == "부칙내용":
                    cur[2] = el.text or ""
            if any(cur):
                rows.append(tuple(cur))
        for date, no, body in rows:
            label = f"부칙 <제{no}호, {date}>" if no else f"부칙 <{date}>"
            u = U(kind="조", surface="부칙", title=label, heading=label)
            # 부칙 본문도 조·항·호 구조다 (실측: 법령 부칙에 조 행 1,006개)
            u.children.extend(_parse_flat(body.splitlines(), allow_div=False, head=u))
            cont.children.append(u)
        if cont.children:
            out.append(cont)

    byul = root.find("별표")
    if byul is not None:
        cont = U(kind="별표", surface="별표", title="별표·서식", heading="별표·서식")
        for unit in byul.findall("별표단위"):
            gubun = _clean(unit.findtext("별표구분")) or "별표"
            no = _clean(unit.findtext("별표번호")).lstrip("0") or "0"
            branch = _clean(unit.findtext("별표가지번호")).lstrip("0")
            title = _clean(unit.findtext("별표제목"))
            # 가지번호는 별개 별표다 — surface 에서 빼면 14·14의1·14의2 가 전부
            # "별표 14" 로 뭉개진다 (실측 회귀: 금융투자업규정시행세칙)
            number = f"{no}의{branch}" if branch else no
            label = f"[{gubun} {number}] {title}"
            u = U(kind="조", surface=f"{gubun} {number}", title=title or label,
                  heading=label,
                  ordinal=(tuple(int(x) for x in (no, branch) if x.isdigit())
                           if no.isdigit() else None))
            # 별표 본문의 ①·1.·가. 도 구조다 (실측: 세칙 별표에 마커 행 1.4만+).
            # 표가 평문으로 뭉개진 행은 마커가 없어 내용으로 남는다.
            md = annex_md.get(f"{gubun} {number}")
            if md is not None:
                lines = _strip_md_header(md)     # HWP 원본 변환 — 표가 md 표다
                if stats is not None:
                    stats["annex_md_used"] = stats.get("annex_md_used", 0) + 1
            else:
                lines = (unit.findtext("별표내용") or "").splitlines()
            u.children.extend(_parse_flat(lines, allow_div=False, head=u))
            cont.children.append(u)
        if cont.children:
            out.append(cont)
    return out


# ---------------------------------------------------------------- 조판 (합성 PDF)
# 조판기는 core.structure.synthpdf 로 옮겼다 — HWP·DOCX 경로와 좌표 규약을 공유한다.


# ---------------------------------------------------------------- 조립

def build(xml_text: str, doc_name: str,
          annex_md: Optional[dict[str, str]] = None,
          ) -> tuple[StructureResult, list[Block], bytes, dict]:
    """본문 XML → (결과, 블록, 합성 PDF 바이트, 기본정보).

    annex_md 는 `_appendix_units` 로 전달 — 별표 본문을 HWP 변환 md 로 바꾼다.
    """
    root = ET.fromstring(xml_text)
    if root.tag == "법령":
        tree, info = law_tree(root)
    elif root.tag == "AdmRulService":
        tree, info = admrul_tree(root)
    else:
        raise ValueError(f"모르는 본문 XML 루트: {root.tag}")
    annex_stats: dict = {}
    tree = tree + _appendix_units(root, annex_md, annex_stats)
    result, blocks, pdf_bytes = assemble(tree, doc_name,
                                         source_label="law.go.kr XML",
                                         tag="lawxml", extra_stats=annex_stats)
    return result, blocks, pdf_bytes, info


def assemble(tree: list[U], doc_name: str, *, source_label: str, tag: str,
             extra_stats: Optional[dict] = None,
             ) -> tuple[StructureResult, list[Block], bytes]:
    """U 트리 → (결과, 블록, 합성 PDF). 결정적 이관 경로들의 공용 조립부.

    lawxml(XML 태그)과 rulehtml(조문 HTML 클래스)이 같은 문으로 나온다 —
    원천이 무엇이든 "구조가 원천에 명시돼 있어 추론이 없다"는 성질이 같아서
    fitness 1.0/hot 규약을 공유한다. source_label 이 그 원천의 이름이다.
    """
    extra_stats = extra_stats or {}

    # 레벨 배정 — 있는 종류끼리 KIND_ORDER 순서. 부칙·별표 컨테이너는 L0.
    used_kinds: set[str] = set()

    def scan(us: list[U]) -> None:
        for u in us:
            used_kinds.add(u.kind)
            scan(u.children)
    scan(tree)
    div_levels = {k: i for i, k in
                  enumerate([k for k in KIND_ORDER if k in used_kinds])}

    layout = _Layout()
    blocks: list[Block] = []
    counts: dict[str, int] = {}

    def emit_block(text: str, kind: str, heading: bool, size: float) -> Block:
        page, bbox = layout.put(text, float(INDENT.get(kind, 14)), size)
        b = Block(idx=len(blocks), text=text, page=page, is_heading=heading,
                  element_index=len(blocks), bbox=bbox, bbox_origin="TOPLEFT",
                  kind="text")
        blocks.append(b)
        return b

    def emit(u: U, level: int) -> Node:
        counts[u.kind] = counts.get(u.kind, 0) + 1
        size = FONT.get(u.kind, BODY_FONT)
        hb = emit_block(u.heading or u.surface, u.kind,
                        u.kind not in ("항", "호", "목"), size)
        node = Node(level=level, ordinal=u.ordinal, family=FAMILY.get(u.kind, u.kind),
                    surface=u.surface, block_idx=hb.idx, page=hb.page,
                    element_index=hb.idx, candidate_id=f"{tag}:{hb.idx}",
                    title=u.title, title_reason="원천 태그",
                    activation_reason=f"{source_label} 태그", bbox=hb.bbox,
                    bbox_origin="TOPLEFT")
        for line in u.content:
            emit_block(line, "내용", False, BODY_FONT)
        for child in u.children:
            child_level = (div_levels.get(child.kind, level + 1)
                           if child.kind in div_levels else level + 1)
            node.children.append(emit(child, max(child_level, level + 1)))
        node.span = (hb.idx, len(blocks))
        return node

    roots: list[Node] = []
    for u in tree:
        lv = div_levels.get(u.kind, 0) if u.kind in div_levels else 0
        roots.append(emit(u, lv))

    # 사다리·지문 — 실제 배정된 레벨에서 역산한다
    by_level: dict[int, set[str]] = {}

    def walk(ns: list[Node]) -> None:
        for n in ns:
            by_level.setdefault(n.level, set()).add(n.family)
            walk(n.children)
    walk(roots)
    ladder = Ladder(rungs=[Rung(level=lv, families=sorted(fams), reg_score=1.0,
                                evidence=f"{source_label} 태그 계층 (추론 없음)")
                           for lv, fams in sorted(by_level.items())])
    fams = sorted({f for s in by_level.values() for f in s})
    fp = Fingerprint(families=fams,
                     order=[sorted(by_level[lv]) for lv in sorted(by_level)])

    result = StructureResult(
        doc=doc_name, tree=roots, ladder=ladder, candidates=[],
        fitness_score=1.0, fitness_passed=True, tier="hot", fingerprint=fp,
        stats={"coverage": 1.0, "consistency": 1.0, "ladder_quality": 1.0,
               "source": source_label, "deterministic": True,
               "units": counts, "blocks": len(blocks), **extra_stats},
        applied={"root": None, "families": None, "ladder_hint": None,
                 "partial_order": None, "llm": False, "lang": "ko",
                 "source": tag},
    )
    pdf_bytes = layout.doc.tobytes()
    layout.doc.close()
    return result, blocks, pdf_bytes
