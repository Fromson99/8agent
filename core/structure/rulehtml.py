"""조문 HTML → 구조 해석 결과 (결정적 이관 — 추론 없음).

KRX(rule.krx.co.kr)·KOFIA(law.kofia.or.kr)는 본문을 HWP 로만 주는 게 아니라
조문 전체 HTML 페이지로도 준다(수집기가 `… 조문.html` 로 전건 보존). HWP 는
스타일이 전무해 추론 구조화를 요구하지만(실측), 조문 HTML 은 **구조가 클래스로
명시**되어 있다 — lawxml 과 같은 "옮기기만 하는" 경로가 성립한다.

KRX 마크업 (실측 2026-08-13, 유가증권시장 상장규정):

    <p class="pyun|jang|jeol">제1편 총칙</p>          ← 편·장·절 제목 문단
    <div class="Mjo"><a name="bonN"><strong>제N조(제목)</strong></a> 본문…
        <br/> ① … <div id="hang"> ② … </div></div>   ← 조 블록 (행 경계 = <br>)
    <p class="buchik_title">부칙 &lt;제7호, …&gt;</p>
    <div id="jo"> ① … </div>                          ← 부칙 본문 (제목 문단 뒤)

추출은 텍스트 행으로 펴고, 행 머리 분류(lawxml._parse_flat: 제N조·①·1.·가.)와
공용 조립(lawxml.assemble)을 재사용한다 — 원천만 다르고 규약은 같다(fitness
1.0/hot). 별표·서식은 HTML 에 없다 — HWP 첨부의 몫으로 남는다(stats 에 표기).

KOFIA 마크업 (실측 2026-08-13, 표준투자권유준칙·영업 및 업무에 관한 규정):

    <div id="lawcontent">
      <div class="PT"><div class="part">Ⅰ. 총 칙</div></div>      ← 편
      <div class="CT"><div class="chapter">Ⅳ-1. …</div></div>     ← 장
      <div class="JO"><div class="article">제1조(목적)…</div>      ← 조 (제목)
        <div class="hang"><table><td>1) </td><td>…</td></table>   ← 항 (마커가 첫 td)
        <div class="ho">…(1) …  <div class="mok">…가. …           ← 호·목
      <div class="addenda">부 칙 (2008. 12. 30)</div>              ← 부칙 라벨

KRX 와 달리 **클래스가 곧 계층**이라 행 머리 정규식이 아니라 클래스 구조를
걷는다. 조 번호 표기는 문서마다 다르다("제1조(목적)" / "1. 목 적") — 종류는
클래스가 정하고 번호는 있으면 읽는다. dann(단서)·partition(참고 상자) 등
구조 클래스 밖 텍스트는 현재 마디의 내용으로 남긴다(행은 버리지 않는다).
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Optional

from core.structure.lawxml import (
    Block,
    StructureResult,
    U,
    _parse_flat,
    assemble,
)

_HEAD_CLASSES = ("pyun", "jang", "jeol", "gwan")


# ---------------------------------------------------------------- KRX 추출기

class _KrxExtract(HTMLParser):
    """innerbody 안의 구조 요소를 문서 순서대로 (kind, text) 목록으로 편다.

    kind: "head"(편·장·절 문단) | "jo"(조 블록) | "buchik"(부칙 제목) |
          "buchik_body"(부칙 제목 직후의 본문 블록)
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.segments: list[tuple[str, str]] = []
        self._in_body = False
        self._body_depth = 0            # innerbody 이후의 div 깊이
        self._capture: Optional[str] = None
        self._cap_depth = 0             # 캡처를 연 요소의 깊이 (div 캡처용)
        self._buf: list[str] = []
        self._pending_buchik = False    # 직전 세그먼트가 부칙 제목이었다
        self._skip: Optional[str] = None

    # -- 캡처 도우미
    def _open(self, kind: str, depth: int) -> None:
        self._capture, self._cap_depth, self._buf = kind, depth, []

    def _close(self) -> None:
        text = "".join(self._buf)
        self.segments.append((self._capture, text))
        self._pending_buchik = self._capture == "buchik"
        self._capture = None

    # -- HTMLParser 훅
    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag in ("script", "style"):
            self._skip = tag
            return
        if not self._in_body:
            if tag == "div" and a.get("id") == "innerbody":
                self._in_body = True
                self._body_depth = 1
            return
        if tag == "div":
            self._body_depth += 1
        if self._capture:
            if tag == "br":
                self._buf.append("\n")
            return
        if tag == "p" and any(c in _HEAD_CLASSES for c in cls):
            self._open("head", -1)                      # p 캡처는 </p> 로 닫는다
        elif tag == "p" and "buchik_title" in cls:
            self._open("buchik", -1)
        elif tag == "div" and "Mjo" in cls:
            self._open("jo", self._body_depth)
        elif tag == "div" and self._pending_buchik and a.get("id") == "jo":
            self._open("buchik_body", self._body_depth)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._skip:
            self._skip = None
            return
        if not self._in_body:
            return
        if tag == "strong" and self._capture == "jo":
            # 조 제목은 <strong> 이고 첫 항·본문이 같은 흐름에 바로 붙는다
            # (실측: "…</strong></a>① 이 규정에서…"). 제목 경계에서 행을 가른다.
            self._buf.append("\n")
            return
        if tag == "p" and self._capture in ("head", "buchik"):
            self._close()
            return
        if tag == "div":
            if self._capture in ("jo", "buchik_body") \
                    and self._body_depth == self._cap_depth:
                self._close()
            self._body_depth -= 1
            if self._body_depth <= 0:
                self._in_body = False

    def handle_data(self, data: str) -> None:
        if self._in_body and self._capture and not self._skip:
            self._buf.append(data)


def krx_segments(html: str) -> list[tuple[str, str]]:
    p = _KrxExtract()
    p.feed(html)
    p.close()
    return [(k, t) for k, t in p.segments if t.strip()]


def krx_tree(html: str) -> list[U]:
    """세그먼트 → U 트리. 본문은 행 머리 분류 한 번, 부칙은 컨테이너로."""
    body_lines: list[str] = []
    buchik: list[tuple[str, list[str]]] = []       # (제목, 본문 행들)
    for kind, text in krx_segments(html):
        lines = text.splitlines()
        if kind in ("head", "jo"):
            body_lines.extend(lines)
        elif kind == "buchik":
            buchik.append((re.sub(r"\s+", " ", text).strip(), []))
        elif kind == "buchik_body" and buchik:
            buchik[-1][1].extend(lines)
    tree = _parse_flat(body_lines, allow_div=True)
    if buchik:
        cont = U(kind="부칙", surface="부칙", title="부칙", heading="부칙")
        for label, lines in buchik:
            u = U(kind="조", surface="부칙", title=label, heading=label)
            u.children.extend(_parse_flat(lines, allow_div=False, head=u))
            cont.children.append(u)
        tree.append(cont)
    return tree


# ---------------------------------------------------------------- KOFIA 추출기

_KOFIA_KINDS = {"part": "편", "chapter": "장", "article": "조",
                "hang": "항", "ho": "호", "mok": "목"}
_KOFIA_JO_RE = re.compile(r"^제(\d+(?:-\d+)?)조(?:의(\d+))?")
_KOFIA_NUMDOT_RE = re.compile(r"^(\d+)(?:-(\d+))?\.\s*(.*)")
_KOFIA_TITLE_RE = re.compile(r"^제[\d-]+조(?:의\d+)?\s*\(([^)]*)\)")
_KOFIA_HANG_RE = re.compile(r"^(?:(\d+)\)|([①-㊿]))")
_KOFIA_HO_RE = re.compile(r"^(?:\((\d+)\)|(\d+(?:의\d+)?)\.\s)")
_KOFIA_MOK_RE = re.compile(r"^([가-힣])\.\s")
_RANK = {"항": 0, "호": 1, "목": 2}


class _KofiaExtract(HTMLParser):
    """lawcontent 안의 구조 클래스를 문서 순서대로 (kind, text) 목록으로 편다.

    kind: "편"|"장"|"조"|"항"|"호"|"목"|"부칙라벨"|"내용"(구조 클래스 밖 잔여)
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.segments: list[tuple[str, str]] = []
        self._in_root = False
        self._depth = 0
        self._capture: Optional[str] = None
        self._cap_depth = 0
        self._buf: list[str] = []
        self._stray: list[str] = []     # JO 안, 구조 클래스 밖 텍스트
        self._jo_depth: Optional[int] = None
        self._skip: Optional[str] = None

    def _flush_stray(self) -> None:
        text = "".join(self._stray).strip()
        self._stray = []
        if text:
            self.segments.append(("내용", text))

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag in ("script", "style"):
            self._skip = tag
            return
        if not self._in_root:
            if tag == "div" and a.get("id") == "lawcontent":
                self._in_root, self._depth = True, 1
            return
        if tag == "div":
            self._depth += 1
        if self._capture:
            if tag == "br":
                self._buf.append("\n")
            return
        kind = next((_KOFIA_KINDS[c] for c in cls if c in _KOFIA_KINDS), None)
        if tag == "div" and kind:
            self._flush_stray()
            self._capture, self._cap_depth, self._buf = kind, self._depth, []
        elif tag == "div" and "addenda" in cls:
            self._flush_stray()
            self._capture, self._cap_depth, self._buf = "부칙라벨", self._depth, []
        elif tag == "div" and "JO" in cls:
            self._flush_stray()
            self._jo_depth = self._depth

    def handle_endtag(self, tag: str) -> None:
        if tag == self._skip:
            self._skip = None
            return
        if not self._in_root:
            return
        if tag == "tr" and self._capture:
            self._buf.append("\n")
        if tag != "div":
            return
        if self._capture and self._depth == self._cap_depth:
            self.segments.append((self._capture, "".join(self._buf)))
            self._capture = None
        if self._jo_depth is not None and self._depth == self._jo_depth:
            self._flush_stray()
            self._jo_depth = None
        self._depth -= 1
        if self._depth <= 0:
            self._flush_stray()
            self._in_root = False

    def handle_data(self, data: str) -> None:
        if not self._in_root or self._skip:
            return
        if self._capture:
            self._buf.append(data)
        elif self._jo_depth is not None:
            self._stray.append(data)


def _clean_text(s: str) -> str:
    return re.sub(r"[ \t ]+", " ", s).strip()


def _kofia_jo(text: str) -> U:
    """조 제목 텍스트 → U. "제1조(목적)…" / "1. 목 적" / 그 밖의 표기."""
    if (m := _KOFIA_JO_RE.match(text)):
        tm = _KOFIA_TITLE_RE.match(text)
        parts = [int(p) for p in m.group(1).split("-")]
        if m.group(2):
            parts.append(int(m.group(2)))
        return U(kind="조", surface=m.group(0), title=tm.group(1) if tm else "",
                 ordinal=tuple(parts), heading=text)
    if (m := _KOFIA_NUMDOT_RE.match(text)):
        parts = [int(m.group(1))] + ([int(m.group(2))] if m.group(2) else [])
        return U(kind="조", surface=f"{m.group(1)}.", title=m.group(3).strip(),
                 ordinal=tuple(parts), heading=text)
    return U(kind="조", surface=text[:20], title=text[:60], heading=text)


def _kofia_sub(kind: str, text: str) -> U:
    """항·호·목 텍스트 → U. 마커는 문서마다 다르다 — 종류는 클래스가 정했다."""
    surface, ordinal = text[:2], None
    if kind == "항" and (m := _KOFIA_HANG_RE.match(text)):
        surface = m.group(0)
        from core.structure.synthpdf import _circ_no
        ordinal = (int(m.group(1)),) if m.group(1) else \
                  ((_circ_no(m.group(2)),) if _circ_no(m.group(2)) else None)
    elif kind == "호" and (m := _KOFIA_HO_RE.match(text)):
        surface = m.group(0).strip()
        no = m.group(1) or m.group(2)
        nm = re.fullmatch(r"(\d+)(?:의(\d+))?", no)
        ordinal = ((int(nm.group(1)), int(nm.group(2))) if nm.group(2)
                   else (int(nm.group(1)),)) if nm else None
    elif kind == "목" and (m := _KOFIA_MOK_RE.match(text)):
        surface = f"{m.group(1)}."
        from core.structure.lawxml import _MOK_SEQ
        idx = _MOK_SEQ.find(m.group(1)) + 1
        ordinal = (idx,) if idx else None
    return U(kind=kind, surface=surface, ordinal=ordinal, heading=text)


def kofia_tree(html: str) -> list[U]:
    """세그먼트 → U 트리 — 클래스 구조 걷기 (행 머리 정규식 없음)."""
    p = _KofiaExtract()
    p.feed(html)
    p.close()
    top: list[U] = []
    containers: list[U] = []            # 열린 편/장
    buchik_cont: Optional[U] = None
    buchik_cur: Optional[U] = None
    sub_stack: list[U] = []             # 현재 조 + 열린 항/호/목

    def jo_parent() -> list[U]:
        if buchik_cur is not None:
            return buchik_cur.children
        return containers[-1].children if containers else top

    for kind, raw in p.segments:
        # 제목·마디 텍스트는 한 줄로 접고, 내용만 행 구조를 지킨다
        if kind == "내용":
            text = "\n".join(filter(None, (_clean_text(l) for l in raw.splitlines())))
        else:
            text = _clean_text(re.sub(r"\s+", " ", raw))
        if not text:
            continue
        if kind in ("편", "장"):
            u = U(kind=kind, surface=text.split()[0], title=text, heading=text)
            while containers and lawxml_order(containers[-1].kind) >= lawxml_order(kind):
                containers.pop()
            (containers[-1].children if containers else top).append(u)
            containers.append(u)
            sub_stack.clear()
        elif kind == "부칙라벨":
            if buchik_cont is None:
                buchik_cont = U(kind="부칙", surface="부칙", title="부칙", heading="부칙")
                top.append(buchik_cont)
            buchik_cur = U(kind="조", surface="부칙", title=text, heading=text)
            buchik_cont.children.append(buchik_cur)
            sub_stack.clear()
        elif kind == "조":
            u = _kofia_jo(text)
            jo_parent().append(u)
            sub_stack[:] = [u]
        elif kind in _RANK:
            u = _kofia_sub(kind, text)
            while len(sub_stack) > 1 and _RANK.get(sub_stack[-1].kind, -1) >= _RANK[kind]:
                sub_stack.pop()
            (sub_stack[-1].children if sub_stack else top).append(u)
            sub_stack.append(u)
        else:                           # 내용 — 현재 가장 깊은 마디에 남긴다
            tgt = sub_stack[-1] if sub_stack else \
                (buchik_cur or (containers[-1] if containers else None))
            if tgt is None:
                tgt = U(kind="조", surface="(전문)", title="전문", heading="전문")
                top.append(tgt)
            tgt.content.extend(text.splitlines())
    return top


def lawxml_order(kind: str) -> int:
    from core.structure.lawxml import KIND_ORDER
    return KIND_ORDER.index(kind) if kind in KIND_ORDER else 99


# ---------------------------------------------------------------- 사이트 등록부
SITES = {"krx": krx_tree, "kofia": kofia_tree}


def build(html_text: str, doc_name: str, site: str = "krx",
          ) -> tuple[StructureResult, list[Block], bytes]:
    """조문 HTML → (결과, 블록, 합성 PDF). lawxml.assemble 공용 조립."""
    maker = SITES.get(site)
    if maker is None:
        raise ValueError(f"모르는 조문 HTML site: {site} — SITES 에 추출기를 등록할 것")
    tree = maker(html_text)
    if not tree:
        raise ValueError("조문 HTML 에서 구조를 하나도 못 읽었다 — 마크업 확인 필요")
    result, blocks, pdf_bytes = assemble(
        tree, doc_name, source_label=f"{site} 조문 HTML", tag="rulehtml",
        extra_stats={"annex_note": "별표·서식은 HTML 에 없음 — HWP 첨부의 몫"})
    return result, blocks, pdf_bytes
