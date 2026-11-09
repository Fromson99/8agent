"""구조화 결과(GENOS 구조화 산출물) → 증분 공통 구조 (DocumentSnapshot).

입력 형식과 관계없이(법령 XML·행정규칙 XML·내규 docx 등) 구조화를 먼저 거친 결과로
증분 비교를 하기 위한 변환기다. 구조화 산출물은 `result.json`의 `nodes`·`blocks`
(소스 스토어의 source_unit·block과 같은 내용)이다.

마디 읽는 법 (실측: 금융회사의 지배구조에 관한 법률 제21065호 구조화 결과)
- 본문 조문: family=kr_article, 표면 `제N조` / `제N조의M` / `제N-M조`.
  마디가 덮는 블록 범위(span)가 조 제목·항·호·목 줄 전체다.
- 부칙: family=buchik 아래 표면 `부칙` 마디 하나가 공포 1건이다. 제목은
  `부칙 <제13453호, 20150731>`이고 첫 블록은 그 제목을 다시 적은 합성 줄이다.
  부칙 안의 `제1조(시행일)` 같은 조문은 부칙 본문이며 본문 조문 키로 쓰지 않는다.
- 별표: family=annex 아래 표면 `별표 0`·`별표 1의2`·`서식 3` 마디. 번호 0은 번호 없는
  [별표]다 (법령 XML 별표번호 0000).
- 편·장·절·관 제목은 조문 본문에 넣지 않는다 (마디 범위에 들어가지 않는다).
- 첫 본문 조문 앞의 장·절이 아닌 줄은 `전문`으로 보존한다.

coordinate_scope(body·addendum·annex)가 있으면 그것을 쓰고, 없는 구조화 결과(내규 등)는
조상 마디의 family(buchik·annex)로 정한다.

문서 정보(불변 문서코드·공포번호·시행일)는 구조화 결과에 없을 수 있어 따로 받는다.
`header_from_xml`(법제처 XML 머리말) 또는 `header_from_name`(문서명·파일명·부칙)을 쓴다.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .lawgo_parse import (KIND_ADDENDUM, KIND_ANNEX, KIND_ARTICLE, KIND_PREAMBLE, PREAMBLE, Addendum,
                          Article, DocumentSnapshot, ParseError, _date, _info)
from .normalize import article_key, normalize_text

_ARTICLE_SURFACE = re.compile(r"^제\s*(\d+(?:-\d+)?)\s*조(?:\s*의\s*(\d+))?$")
_ANNEX_SURFACE = re.compile(r"^(별표|별지|서식|부표|양식|별첨)\s*(\d+)(?:\s*의\s*(\d+))?$")
# 행정규칙 구조화는 제목 없는 `제26조 삭제<2025. 2. 5.>` 줄을 조로 세우지 않고 앞 조에 붙인다
_DELETED_LINE = re.compile(r"^제\s*(\d+(?:-\d+)?)\s*조(?:\s*의\s*(\d+))?\s*<?\s*삭제\b")
_ANNEX_HEAD = re.compile(r"^\[[^\]]*\]\s*")
_DIVISION = re.compile(r"^제\s*\d+\s*(?:편|장|절|관)(?:\s*의\s*\d+)?(?:\s|\[|$)")
_DELETED = re.compile(r"^제\s*\d+(?:-\d+)?\s*조(?:\s*의\s*\d+)?\s*(?:\([^)]*\)\s*)?<?\s*삭제")
# 부칙 <제21065호, 20251001> / 부칙 <제2026-29호,2026.7.1> / 부칙 <2026.7.1>
_ADDENDUM_TITLE = re.compile(r"<\s*(?:제\s*([^,>]+?)\s*호\s*)?,?\s*([\d.\s]+)?\s*>")
_FILENAME_DATE = re.compile(r"(?:^|[_\-\s(])((?:19|20)\d{6})(?:[_\-\s).]|$)")
_KIND_BODY, _KIND_ADDENDUM, _KIND_ANNEX = "body", "addendum", "annex"


@dataclass(frozen=True)
class Header:
    """구조화 결과 밖에서 오는 문서 정보."""
    doc_cd: str
    source_kind: str            # LAW | ADMRUL | RULE (내규 등 법제처 밖 문서)
    official_id: str
    name: str
    promulgated: str = ""
    promulgation_no: str = ""
    effective: str = ""
    revision_kind: str = ""
    source_sha256: str = ""


def header_from_xml(raw: bytes, *, source_sha256: str | None = None) -> Header:
    """법제처 본문 XML의 머리말만 읽는다 (조문은 구조화 결과에서 읽는다)."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ParseError(f"XML 형식 오류: {exc}") from exc
    digest = source_sha256 or hashlib.sha256(raw).hexdigest()
    if root.tag == "법령":
        info = _info(root, "기본정보")
        official = info.get("법령ID", "")
        header = Header(f"LAW:{official}", "LAW", official, info.get("법령명_한글", ""),
                        _date(info.get("공포일자")), info.get("공포번호", ""), _date(info.get("시행일자")),
                        info.get("제개정구분", ""), digest)
    elif root.tag == "AdmRulService":
        info = _info(root, "행정규칙기본정보")
        official = info.get("행정규칙ID", "")
        header = Header(f"ADMRUL:{official}", "ADMRUL", official, info.get("행정규칙명", ""),
                        _date(info.get("발령일자")), info.get("발령번호", ""),
                        _date(info.get("시행일자")) or _date(info.get("발령일자")),
                        info.get("제개정구분명", ""), digest)
    else:
        raise ParseError(f"지원하지 않는 XML 루트: {root.tag}")
    if not official:
        raise ParseError("문서 불변 ID(법령ID/행정규칙ID)가 없음")
    return header


def name_code(name: str) -> str:
    """법제처 밖 문서(내규 등)의 불변 문서코드. 등록된 정식 명칭이 키다 (공백 무시)."""
    compact = re.sub(r"\s+", "", normalize_text(name))
    if not compact:
        raise ParseError("문서명이 없음")
    return "RULE:" + hashlib.sha256(compact.encode("utf-8")).hexdigest()[:16]


def header_from_name(name: str, *, filename: str = "", source_sha256: str) -> Header:
    """법제처 밖 문서. 시행일은 파일명의 YYYYMMDD → 없으면 부칙(snapshot 조립 뒤 채움) 순서."""
    match = _FILENAME_DATE.search(filename or "")
    effective = match.group(1) if match else ""
    return Header(name_code(name), "RULE", name_code(name).split(":", 1)[1], normalize_text(name),
                  effective=effective, source_sha256=source_sha256)


def _surface(node: dict) -> str:
    return normalize_text(node.get("surface") or "")


def _scopes(nodes: list[dict]) -> dict[int, str]:
    by_id = {n["id"]: n for n in nodes}
    out: dict[int, str] = {}

    def scope(node: dict) -> str:
        cached = out.get(node["id"])
        if cached:
            return cached
        given = node.get("coordinate_scope")
        if given in (_KIND_BODY, _KIND_ADDENDUM, _KIND_ANNEX):
            value = given
        elif node.get("family") == "buchik":
            value = _KIND_ADDENDUM
        elif node.get("family") == "annex":
            value = _KIND_ANNEX
        elif node.get("parent") is not None and node["parent"] in by_id:
            value = scope(by_id[node["parent"]])
        else:
            value = _KIND_BODY
        out[node["id"]] = value
        return value

    for node in nodes:
        scope(node)
    return out


def _span_lines(node: dict, blocks: list[dict]) -> list[str]:
    start, end = node.get("span") or (node["block"], node["block"] + 1)
    end = max(end, start + 1)
    lines = []
    for block in blocks[start:end]:
        if block.get("kind", "text") != "text":
            continue
        text = normalize_text(block.get("text"))
        if text:
            lines.append(text)
    return lines


def _addendum_from_node(node: dict, blocks: list[dict]) -> tuple[str, str, list[str]]:
    title = normalize_text(node.get("title") or "")
    match = _ADDENDUM_TITLE.search(title)
    number = normalize_text(match.group(1)) if match and match.group(1) else ""
    date = _date(match.group(2)) if match and match.group(2) else ""
    lines = _span_lines(node, blocks)
    if lines and title and lines[0] == title:
        lines = lines[1:]                      # 구조화가 붙인 합성 제목 줄
    return number, date, lines


def from_structure(nodes: list[dict], blocks: list[dict], header: Header) -> DocumentSnapshot:
    if not nodes:
        raise ParseError("구조화 마디 0건")
    blocks = sorted(blocks, key=lambda b: b["idx"])
    if [b["idx"] for b in blocks] != list(range(len(blocks))):
        raise ParseError("구조화 블록 번호가 0부터 연속이 아님")
    scopes = _scopes(nodes)
    ordered = sorted(nodes, key=lambda n: (n.get("block", 0), n.get("level", 0)))

    body_items: list[tuple[tuple[int, int], Article]] = []
    annexes: list[Article] = []
    rows: list[tuple[str, str, str]] = []
    first_body_block = None
    for node in ordered:
        scope = scopes[node["id"]]
        surface = _surface(node)
        if node.get("family") != "kr_article":
            continue
        if scope == _KIND_BODY:
            match = _ARTICLE_SURFACE.match(surface)
            if not match:
                continue
            lines = _span_lines(node, blocks)
            first_body_block = node["block"] if first_body_block is None else first_body_block
            pieces = [(article_key(match.group(1), match.group(2)), normalize_text(node.get("title") or ""), [])]
            for i, line in enumerate(lines):
                deleted = _DELETED_LINE.match(line) if i else None
                if deleted:
                    pieces.append((article_key(deleted.group(1), deleted.group(2)), "", []))
                pieces[-1][2].append(line)
            for offset, (key, title, part) in enumerate(pieces):
                body_items.append(((node["block"], offset), Article(
                    key, KIND_ARTICLE, title, "\n".join(part), 0,
                    deleted=bool(_DELETED.match(part[0] if part else "")))))
        elif scope == _KIND_ADDENDUM and surface.startswith("부칙"):
            number, date, lines = _addendum_from_node(node, blocks)
            rows.append((date, number, "\n".join(lines)))
        elif scope == _KIND_ANNEX:
            match = _ANNEX_SURFACE.match(surface)
            if not match:
                continue
            kind, number, branch = match.group(1), match.group(2).lstrip("0") or "0", (match.group(3) or "").lstrip("0")
            key = kind + ("" if number == "0" and not branch else f"{number}의{branch}" if branch else number)
            lines = _span_lines(node, blocks)
            if lines:                          # 구조화가 붙인 머리 `[별표 0] 제목` → 제목
                lines[0] = _ANNEX_HEAD.sub("", lines[0]) or lines[0]
            annexes.append(Article(key, KIND_ANNEX, normalize_text(node.get("title") or ""),
                                   "\n".join(lines), 0))

    division_ids = {n["id"] for n in nodes if scopes[n["id"]] == _KIND_BODY
                    and n.get("family", "").startswith("kr_") and n.get("family") != "kr_article"}
    for block in blocks:
        if block.get("node") in division_ids and block.get("kind", "text") == "text":
            text = normalize_text(block.get("text"))
            deleted = _DELETED_LINE.match(text)
            if deleted:                        # 장·절 제목 마디에 붙은 `제12조 삭제 <…>` 줄
                body_items.append(((block["idx"], 0), Article(
                    article_key(deleted.group(1), deleted.group(2)), KIND_ARTICLE, "", text, 0, deleted=True)))
                if first_body_block is None or block["idx"] < first_body_block:
                    first_body_block = block["idx"]
    articles = [a for _, a in sorted(body_items, key=lambda x: x[0])]

    if first_body_block is not None:
        heading_blocks = {n["block"] for n in nodes if n.get("family", "").startswith("kr_")
                          and n.get("family") != "kr_article"}
        preamble = []
        for block in blocks[:first_body_block]:
            text = normalize_text(block.get("text"))
            if text and block.get("kind", "text") == "text" and block["idx"] not in heading_blocks \
                    and not _DIVISION.match(text) and text != normalize_text(header.name):
                preamble.append(text)
        if preamble:
            articles.insert(0, Article(PREAMBLE, KIND_PREAMBLE, PREAMBLE, "\n".join(preamble), 0))

    addenda: list[Addendum] = []
    seen: dict[str, int] = {}
    for date, number, body in rows:
        base = f"부칙:{number or date or 'unknown'}"
        seen[base] = seen.get(base, 0) + 1
        key = base if seen[base] == 1 else f"{base}#{seen[base]}"
        addenda.append(Addendum(key, date, number, body))

    if not any(a.kind == KIND_ARTICLE for a in articles):
        raise ParseError("조문 0건 (조문 구조가 없는 문서)")
    snapshot = DocumentSnapshot(
        doc_cd=header.doc_cd, source_kind=header.source_kind, official_id=header.official_id,
        name=header.name, promulgated=header.promulgated, promulgation_no=header.promulgation_no,
        effective=header.effective, revision_kind=header.revision_kind, source_sha256=header.source_sha256,
        articles=articles, addenda=addenda, meta={"input": "structured"})
    if header.source_kind == "RULE" and addenda:
        last = addenda[-1]                     # 법제처 밖 문서: 공포번호·공포일은 마지막 부칙에서
        snapshot.promulgation_no = snapshot.promulgation_no or last.number
        snapshot.promulgated = snapshot.promulgated or last.promulgated
    tail = [Article(a.key, KIND_ADDENDUM, a.key, a.text, 0) for a in addenda]
    merged = articles + annexes + tail
    keys = [a.key for a in merged]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise ParseError(f"조문 키 중복: {duplicates[:10]}")
    snapshot.articles = [Article(**{**a.__dict__, "seq": i}) for i, a in enumerate(merged, 1)]
    return snapshot


def from_result(result: dict, header: Header) -> DocumentSnapshot:
    """구조화 result.json 한 개 → DocumentSnapshot."""
    return from_structure(result.get("nodes") or [], result.get("blocks") or [], header)


__all__ = ["Header", "from_result", "from_structure", "header_from_name", "header_from_xml", "name_code"]
