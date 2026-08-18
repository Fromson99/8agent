"""법령 관계망 전사 — 위임 간선(lsDelegated)과 법령 문서 인덱스(체계도·제1조).

law.go.kr 이 편집·유지하는 관계 데이터를 우리 좌표계로 옮긴다(전부 결정론,
LLM 없음 — 선언된 것의 전사):

- 위임 간선: data/corpus/law/relations/lsDelegated_*.xml → data/delegation.json
  "대통령령으로 정하는 바에 따라"처럼 **대상 문서명이 문면에 없는** 암묵 위임을
  법제처 편집자가 조항호목 단위로 해소해 둔 것이다. refs.py 의 문면 전사가
  원리상 못 잡는 구멍을 메운다. 위임구분(시행령·위임행정규칙·인용법령…)이
  간선 타입이다 — 위임은 "구체 내용이 저기 있다"는 보완 관계라 확장이 거의
  항상 옳고, 인용은 문맥 따라 무관할 수 있어 정책을 갈라 쓸 수 있다.
- 문서 인덱스: manifest + lsStmd 체계도 + 본문 XML → data/law_index.json
  문서 행(종별·시행일·제1조 목적 전사)과 가족 트리(법률→시행령→…→세칙).
  요약은 만들지 않는다 — 제1조(목적)가 저자가 쓴 공식 한 줄 요약이다.

조인 규약 셋:
- 우리 스토어와는 본문 sha256[:16] == doc_id (lawrag/core/lineage.py 와 같은 규약).
- 위임 데이터의 **대상** 법령은 공식 명칭 완전일치(공백 무시)로 잇는다. 대상
  일련번호(MST)는 편집 시점 구판이라 못 쓴다 — 실측(2026-08-13): 자본시장법
  현행 MST 283193, 위임 데이터 안에는 238305. 행정규칙 대상은 일련번호가
  맞으면 번호로, 아니면 명칭으로.
- 조문 좌표는 surface 완전일치 — 조문번호 N·가지 M → "제N조"/"제N조의M".

대상이 코퍼스에 없는 간선도 버리지 않는다(dst.doc_id=null) — 문서가 들어오면
재전사로 이어지고, "코퍼스에 빠진 문서 목록"이라는 부산물도 된다.

경로는 인자로 받는다 — env 해석은 CLI(main)가 한 번만 한다 (lineage 규약).
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lawrag.core.lineage import body_of

# 조번호 두 체계 — 법령 "제34조(의2)" · 행정규칙 편-조 "제2-3조(의2)" (실측:
# 금융투자업규정류). 하이픈을 못 읽으면 시행령→금투업규정 위임 664건이 통째로
# 미해소가 된다 (실측 2026-08-13).
_JO_RE = re.compile(r"^제(\d+(?:-\d+)?)조(?:의(\d+))?")
_JO_SURFACE_RE = re.compile(r"^제\d+(-\d+)?조(의\d+)?$")


def _norm_name(s: Optional[str]) -> str:
    return re.sub(r"\s+", "", s or "")


def _jo_surface(no: str, gaji: str = "") -> Optional[str]:
    """조문번호·가지번호 → 스토어 surface. "34"+"2" → "제34조의2",
    "2-3" → "제2-3조" (행정규칙 편-조 체계)."""
    no, gaji = (no or "").strip(), (gaji or "").strip()
    if not re.fullmatch(r"\d+(?:-\d+)?", no):
        return None
    norm_no = "-".join(str(int(p)) for p in no.split("-"))
    s = f"제{norm_no}조"
    if gaji.isdigit() and int(gaji) > 0:
        s += f"의{int(gaji)}"
    return s


# ---------------------------------------------------------------- 코퍼스 조인
def load_manifest(corpus: Path) -> list[dict]:
    p = corpus / "law" / "manifest.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("items", [])


def _doc_maps(items: list[dict]) -> tuple[dict, dict]:
    """manifest → (일련번호별, 정규화 명칭별) 문서 카드. doc_id 는 sha256[:16]."""
    by_serial: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    for it in items:
        sha, _, _ = body_of(it)
        card = {"name": it.get("name", ""), "kind": it.get("kind", ""),
                "doc_id": sha[:16] if sha else None,
                "serial": str(it.get("doc_no", ""))}
        if card["serial"]:
            by_serial[card["serial"]] = card
        if card["name"]:
            by_name[_norm_name(card["name"])] = card
    return by_serial, by_name


# ---------------------------------------------------------------- 위임 전사
def transcribe_delegations(relations_dir: Path, items: list[dict]) -> dict:
    """lsDelegated_*.xml 전부 → 간선 목록. 대상 미보유도 dst.doc_id=null 로 남긴다."""
    by_serial, by_name = _doc_maps(items)
    edges: list[dict] = []
    sources: list[dict] = []
    for f in sorted(relations_dir.glob("lsDelegated_*.xml")):
        root = ET.parse(f).getroot()
        info = root.find(".//법령정보")
        src_name = (info.findtext("법령명", "") if info is not None else "").strip()
        src_mst = (info.findtext("법령일련번호", "") if info is not None else "").strip()
        src_card = by_serial.get(src_mst) or by_name.get(_norm_name(src_name)) or {}
        n0 = len(edges)
        for jo in root.iter("위임조문정보"):
            head = jo.find("조정보")
            if head is None:
                continue
            src_jo = _jo_surface(head.findtext("조문번호", ""),
                                 head.findtext("조문가지번호", ""))
            src = {"name": src_name, "doc_id": src_card.get("doc_id"),
                   "jo": src_jo, "jo_title": (head.findtext("조문제목") or "").strip()}
            for wi in jo.iter("위임정보"):
                kind = (wi.findtext("위임구분") or "").strip()
                # 법령 대상 — 일련번호·제목이 위임정보 수준에 있다 (번호는 구판, 명칭으로).
                # 조항호목은 대상이 아니라 **출발 조문 안의 위치**다 — 실측(2026-08-13):
                # 위임행정규칙 1,251건 중 1,250건, 시행령 2,137건에서 조항호목의 조가
                # 출발 조와 일치. src.anchor 로 싣는다. 대상 조는 법령이면
                # 위임법령조문번호(명시 필드)가 정본이고, 행정규칙 대상은 **조 좌표가
                # 데이터에 없다**(문서 수준 포인터) — coord 로 대상 조를 지어내면
                # 같은 번호 우연 일치의 오해소가 난다(실측 154건).
                law_title = (wi.findtext("위임법령제목") or "").strip()
                law_card = by_name.get(_norm_name(law_title), {}) if law_title else {}
                for d in wi:
                    if d.tag == "위임법령조문정보":
                        jo_s = _jo_surface(d.findtext("위임법령조문번호", ""),
                                           d.findtext("위임법령조문가지번호", ""))
                        coords = [c.text.strip() for c in d.iter("조항호목")
                                  if c.text and c.text.strip()] or [None]
                        for coord in coords:
                            edges.append({
                                "kind": kind,
                                "src": {**src, "anchor": coord},
                                "dst": {"name": law_title,
                                        "doc_id": law_card.get("doc_id"),
                                        "jo": jo_s},
                                "link": (d.findtext("링크텍스트") or "").strip()})
                    elif d.tag == "위임행정규칙조문정보":
                        serial = (d.findtext("위임행정규칙일련번호") or "").strip()
                        title = (d.findtext("위임행정규칙제목") or "").strip()
                        card = by_serial.get(serial) or by_name.get(_norm_name(title), {})
                        coords = [c.text.strip() for c in d.iter("조항호목")
                                  if c.text and c.text.strip()] or [None]
                        for coord in coords:
                            edges.append({
                                "kind": kind,
                                "src": {**src, "anchor": coord},
                                "dst": {"name": title, "doc_id": card.get("doc_id"),
                                        "jo": None},
                                "link": (d.findtext("링크텍스트") or "").strip()})
        sources.append({"mst": src_mst, "name": src_name, "file": f.name,
                        "edges": len(edges) - n0})
    return {"edges": edges, "sources": sources}


# ---------------------------------------------------------------- 좌표 해소
def _jo_nodes(store: Path, doc_id: str) -> dict[str, int]:
    """스토어 문서의 조 surface → node id. 같은 surface 는 첫 노드가 이긴다.

    부칙·별표 자손은 뺀다 — 부칙 본문의 "제1조(시행일)"가 surface 를 갖고
    있어서, 편-조 체계 문서(본문은 제1-2조…)에 온 "제2조" 좌표가 부칙 조에
    잘못 붙는다(실측 2026-08-13: 금융투자업규정 위임 38건 오해소).
    """
    p = store / doc_id / "result.json"
    if not p.exists():
        return {}
    nodes = json.loads(p.read_text(encoding="utf-8")).get("nodes", [])
    by_id = {n.get("id"): n for n in nodes}

    def in_appendix(n: dict) -> bool:
        cur = n
        while cur is not None:
            s = (cur.get("surface") or "").strip()
            if s == "부칙" or s.startswith("별표") or s.startswith("별지"):
                return True
            cur = by_id.get(cur.get("parent"))
        return False

    out: dict[str, int] = {}
    for n in nodes:
        s = (n.get("surface") or "").strip()
        if _JO_SURFACE_RE.fullmatch(s) and s not in out \
                and n.get("id") is not None and not in_appendix(n):
            out[s] = n["id"]
    return out


def resolve_nodes(edges: list[dict], store: Path) -> int:
    """스토어에 있는 문서의 조 좌표를 node id 로 해소. 해소된 끝 수를 돌려준다."""
    cache: dict[str, dict[str, int]] = {}
    hit = 0
    for e in edges:
        for end in (e["src"], e["dst"]):
            doc_id, jo = end.get("doc_id"), end.get("jo")
            if not doc_id or not jo:
                continue
            if doc_id not in cache:
                cache[doc_id] = _jo_nodes(store, doc_id)
            node = cache[doc_id].get(jo)
            if node is not None:
                end["node"] = node
                hit += 1
    return hit


# ---------------------------------------------------------------- 문서 인덱스
def _purpose_law(body: Path) -> Optional[str]:
    """법령 XML 제1조 — 조문단위(조문여부=조문, 조문번호=1, 가지 없음)의 첫 줄."""
    root = ET.parse(body).getroot()
    for jo in root.iter("조문단위"):
        if (jo.findtext("조문여부", "").strip() == "조문"
                and jo.findtext("조문번호", "").strip() == "1"
                and not jo.findtext("조문가지번호", "").strip()):
            text = (jo.findtext("조문내용") or "").strip()
            return text.splitlines()[0].strip()[:300] if text else None
    return None


def _purpose_admrul(body: Path) -> Optional[str]:
    """행정규칙 XML — 조문내용이 평문 덩어리라 목적 조항 줄을 찾는다.

    조번호 체계가 둘이다: "제1조(목적)"(장·조 문서)와 "제1-1조(목적)"(편-조
    문서 — 금융투자업규정류, 실측 2026-08-13). (목적) 표제가 이기고, 없으면
    첫 조 줄이 폴백이다.
    """
    root = ET.parse(body).getroot()
    fallback: Optional[str] = None
    for el in root.iter("조문내용"):
        for line in (el.text or "").splitlines():
            line = line.strip()
            if re.match(r"^제[\d-]+조(?:의\d+)?\(목적\)", line):
                return line[:300]
            if fallback is None and re.match(r"^제1(?:-1)?조\b", line):
                fallback = line[:300]
    return fallback


def transcribe_purpose(item: dict, repo_root: Path) -> Optional[str]:
    sha, file, fmt = body_of(item)
    if not file or fmt != "xml":
        return None
    p = repo_root / file
    if not p.exists():
        return None
    try:
        fn = _purpose_law if item.get("kind") == "law" else _purpose_admrul
        return fn(p) or (_purpose_admrul(p) if fn is _purpose_law else _purpose_law(p))
    except ET.ParseError:
        return None


_STMD_LEVELS = {"법률", "시행령", "시행규칙", "고시", "훈령", "예규", "기타", "행정규칙"}


def _stmd_members(el: ET.Element, depth: int, out: list[dict]) -> None:
    b = el.find("기본정보")
    got = None
    if b is not None:
        got = {"name": (b.findtext("법령명") or b.findtext("행정규칙명") or "").strip(),
               "serial": (b.findtext("법령일련번호")
                          or b.findtext("행정규칙일련번호") or "").strip(),
               "kind": (b.findtext("법종구분") or "").strip(), "depth": depth}
        out.append(got)
    for c in el:
        if c.tag in _STMD_LEVELS:
            _stmd_members(c, depth + (1 if got else 0), out)


def transcribe_families(relations_dir: Path, items: list[dict]) -> list[dict]:
    """lsStmd 체계도 → 가족별 구성원(보유 여부 표기). 같은 일련번호는 한 번만."""
    by_serial, by_name = _doc_maps(items)
    fams: list[dict] = []
    for f in sorted(relations_dir.glob("lsStmd_*.xml")):
        root = ET.parse(f).getroot()
        top = root.find("상하위법")
        if top is None:
            continue
        rows: list[dict] = []
        for child in top:
            _stmd_members(child, 0, rows)
        seen: set[str] = set()
        members = []
        for r in rows:
            if not r["serial"] or r["serial"] in seen:
                continue
            seen.add(r["serial"])
            card = by_serial.get(r["serial"]) or by_name.get(_norm_name(r["name"]), {})
            members.append({**r, "held": bool(card), "doc_id": card.get("doc_id")})
        if members:
            fams.append({"root": members[0]["name"], "members": members})
    return fams


def build_index(corpus: Path, relations_dir: Path, store: Path,
                repo_root: Path) -> dict:
    items = load_manifest(corpus)
    fams = transcribe_families(relations_dir, items)
    kind_by_serial = {m["serial"]: m["kind"]
                      for fam in fams for m in fam["members"] if m["serial"]}
    docs = []
    for it in items:
        sha, _, _ = body_of(it)
        doc_id = sha[:16] if sha else None
        docs.append({
            "name": it.get("name", ""),
            "kind": kind_by_serial.get(str(it.get("doc_no", "")))
                    or ("법률" if it.get("kind") == "law" else "행정규칙"),
            "enforce": it.get("enforce", ""),
            "doc_id": doc_id,
            "in_store": bool(doc_id and (store / doc_id).exists()),
            "purpose": transcribe_purpose(it, repo_root)})
    return {"docs": docs, "families": fams}


# ---------------------------------------------------------------- CLI
def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    import os

    root = Path(__file__).resolve().parent.parent.parent
    ap = argparse.ArgumentParser(description="법령 관계망 전사 — 위임 간선·문서 인덱스")
    ap.add_argument("--corpus", default=os.environ.get("CORPUS_DIR", str(root / "data" / "corpus")))
    ap.add_argument("--store", default=os.environ.get("STRUCTURE_STORE",
                                                      str(root / "data" / "structure")))
    ap.add_argument("--out", default=None, help="산출 디렉토리 (기본: 스토어 부모)")
    args = ap.parse_args(argv)

    corpus, store = Path(args.corpus), Path(args.store)
    out = Path(args.out) if args.out else store.parent
    relations = corpus / "law" / "relations"
    items = load_manifest(corpus)
    built = datetime.now(timezone.utc).isoformat(timespec="seconds")

    deleg = transcribe_delegations(relations, items)
    hits = resolve_nodes(deleg["edges"], store)
    kinds = Counter(e["kind"] or "∅" for e in deleg["edges"])
    missing = Counter(e["dst"]["name"] for e in deleg["edges"]
                      if not e["dst"]["doc_id"] and e["dst"]["name"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "delegation.json").write_text(json.dumps(
        {"built": built, "sources": deleg["sources"], "edges": deleg["edges"],
         "stats": {"total": len(deleg["edges"]), "by_kind": dict(kinds),
                   "resolved_ends": hits,
                   "dst_missing_top": dict(missing.most_common(20))}},
        ensure_ascii=False), encoding="utf-8")

    index = build_index(corpus, relations, store, root)
    (out / "law_index.json").write_text(json.dumps(
        {"built": built, **index}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"위임 간선 {len(deleg['edges'])}개 (좌표 해소 {hits}끝) → {out/'delegation.json'}")
    print(f"  타입: {dict(kinds)}")
    print(f"  대상 미보유 상위: {dict(missing.most_common(8))}")
    print(f"문서 {len(index['docs'])}행 · 가족 {len(index['families'])}개 → {out/'law_index.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
