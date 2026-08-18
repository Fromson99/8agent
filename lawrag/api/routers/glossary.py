"""용어집 API — 올라온 문서들의 **제목을 용어로 모은다.**

    GET /v1/glossary            용어 목록 + 출현 지점 (네트워크 형태)
    GET /v1/glossary/{term}     그 용어 하나의 출현 전부

## 왜 제목이 용어인가

구조화가 끝나면 문서마다 마디에 이름이 붙는다 — `설명의무`, `위험등급`,
`청약철회권`. 그 이름들이 곧 그 문서군이 쓰는 어휘다. 사람이 용어집을 손으로
채우는 대신 **이미 뽑아 둔 구조에서 거둔다.**

## 같은 용어는 하나의 마디로 묶는다

`설명의무` 가 금소법 제19조에도, 준칙 Ⅳ-3 에도, 설명서 p2 에도 나오면 그것은
**같은 용어의 세 출현**이지 세 개의 용어가 아니다. 공백을 지운 정규형으로 묶는다 —
`민원처리,분쟁조정절차` 와 `민원처리, 분쟁조정 절차` 가 갈리면 안 된다.

묶는 일을 화면이 아니라 **여기서** 한다. 화면마다 따로 묶으면 규칙이 갈린다.

## 좌표를 함께 싣는다

출현 하나는 `{doc, node, level, page, bbox, extent}` 다. 어느 문서의 어느 자리인지
없으면 "이 용어가 있다" 까지만 알고 되돌아갈 수 없다. `extent` 는 그 마디가 지면에서
덮은 범위다(`pipeline.measure_extent`).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/v1/glossary", tags=["glossary"])

ROOT = Path(__file__).resolve().parents[3]
STORE = Path(os.environ.get("STRUCTURE_STORE", ROOT / "var" / "out" / "structure" / "viewer"))
# 사람이 더한 용어가 남는 자리 — **DB 는 없지만 이 파일이 정본이다.**
# 문서 저장소 **옆**에 둔다(안이 아니라). 저장소 안은 컨테이너 사용자 소유라
# 호스트에서 쓸 수 없고, 문서를 지울 때 용어까지 함께 날아간다.
TERMS_FILE = Path(os.environ.get("GLOSSARY_STORE", STORE.parent / "glossary.json"))

# 용어로 올리지 않을 제목. 번호만 있는 것(`②`)과 너무 긴 문장은 이름이 아니다.
MAX_TERM = 40
_ORDINAL_ONLY = re.compile(r"^[\d\s.,()①-⑳가-힣]{0,3}$")
# 문장으로 끝나면 제목이 아니라 본문이다 — 구조화가 꼬리를 이름으로 잘못 잡은 경우.
_SENTENCE_TAIL = ("다.", "요.", "니다", "습니다", "됩니다", "합니다", "바랍니다")


def norm(s: str) -> str:
    """묶음 키. 공백만 지운다 — 괄호·쉼표는 뜻을 가르므로 남긴다."""
    return re.sub(r"\s+", "", s or "")


def _is_term(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > MAX_TERM:
        return False
    if _ORDINAL_ONLY.fullmatch(t):
        return False
    if t.endswith(_SENTENCE_TAIL):
        return False
    return bool(re.search(r"[가-힣A-Za-z]", t))      # 글자가 하나라도 있어야 이름이다


def _docs() -> list[tuple[str, dict, dict]]:
    """(doc_id, meta, result). 해석 산출이 있는 문서만."""
    out = []
    if not STORE.exists():
        return out
    for d in sorted(STORE.iterdir()):
        rj, mj = d / "result.json", d / "meta.json"
        if not (rj.exists() and mj.exists()):
            continue
        try:
            out.append((d.name, json.loads(mj.read_text(encoding="utf-8")),
                        json.loads(rj.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return out


def _ancestor_path(n: dict, byid: dict) -> str:
    """조상 제목 사슬 — "8. 사모펀드 ▸ 나. 투자위험" 처럼 어느 자리인지 읽히게.

    같은 제목이 여러 구역에 반복되는 문서(상품설명서의 반복 블록)에서 이것이
    없으면 출현 목록이 전부 같은 줄로 보인다 — 중복이 아니라 맥락 부재다.
    """
    parts, cur, seen = [], n.get("parent"), set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        p = byid.get(cur)
        if not p:
            break
        label = (p.get("title") or "").strip() or (p.get("surface") or "").strip()
        if label:
            parts.append(label)
        cur = p.get("parent")
    return " ▸ ".join(reversed(parts))


def collect() -> dict[str, Any]:
    """모든 문서의 제목을 거둬 **용어 하나에 출현 여럿** 형태로 묶는다."""
    terms: dict[str, dict] = {}
    docs: list[dict] = []
    # 이 말 **자체가** 어느 구역의 제목인 키들 — 특화/범용 분리의 기준.
    # 제목 블록 안에 부분 문자열로 스친 것(via=제목 출현)과 다르다: "금융"이
    # "금융상품판매업자…" 제목 안에 있다고 제목 용어가 되면 분리가 뒤집힌다.
    # 레벨(구역 깊이)도 함께 적는다 — 같은 말이 L1 장 제목이기도 하고 L3 항
    # 제목이기도 할 수 있어 집합이다.
    title_keys: set[str] = set()
    title_levels: dict[str, set] = {}

    for doc_id, meta, res in _docs():
        name = meta.get("name", doc_id)
        docs.append({"doc_id": doc_id, "name": name,
                     "folder": meta.get("folder"),
                     "pages": meta.get("pages"), "score": meta.get("score"),
                     "nodes": len(res.get("nodes", []))})

        # 문서 이름과 폴더도 어휘다. "금소법" 을 찾으면 그 **문서**가 나와야
        # 하고, 폴더(예: 법령문서)는 문서들을 한 덩어리로 묶는 상위 용어다 —
        # 폴더 하나가 여러 문서에 걸치므로 화면의 "문서를 잇는 용어"에 그대로
        # 올라온다. 마디 제목과 같은 키 규칙으로 묶여, 제목·본문 출현과
        # 문서명이 겹치면 같은 용어의 출현이 늘어난다.
        doc_label = re.sub(r"\.pdf$", "", name.strip(), flags=re.I)
        for label, via in ((doc_label, "문서명"),
                           ((meta.get("folder") or "").strip(), "폴더")):
            if not label:
                continue
            key = norm(label)
            row = terms.setdefault(key, {
                "term": label, "key": key, "surfaces": [], "occurrences": [],
            })
            if label not in row["surfaces"]:
                row["surfaces"].append(label)
            row["occurrences"].append({
                "doc_id": doc_id, "doc": name, "node": None, "level": 0,
                "family": None, "surface": label, "page": 1, "block": None,
                "span": None, "bbox": None, "extent": {}, "via": via,
            })

        nodes = res.get("nodes", [])
        byid = {n.get("id"): n for n in nodes}
        # 노드에는 bbox 가 없다 — 제목 블록의 자리(rect, 0~1 비율)를 빌려 온다.
        # 화면이 출현을 그 자리에서 바로 보여 주려면(페이지 미리보기) 좌표가 필요하다.
        rects = {b.get("idx"): b.get("rect") for b in res.get("blocks", [])}
        for n in nodes:
            label = (n.get("title") or "").strip() or (n.get("surface") or "").strip()
            if not _is_term(label):
                continue
            key = norm(label)
            title_keys.add(key)
            if n.get("level"):
                title_levels.setdefault(key, set()).add(int(n["level"]))
            row = terms.setdefault(key, {
                "term": label, "key": key, "surfaces": [], "occurrences": [],
            })
            if label not in row["surfaces"]:
                row["surfaces"].append(label)
            row["occurrences"].append({
                "doc_id": doc_id, "doc": name,
                "node": n.get("id"), "level": n.get("level"),
                "family": n.get("family"), "surface": n.get("surface"),
                "page": n.get("page"), "block": n.get("block"),
                "span": n.get("span"),
                "bbox": n.get("bbox") or rects.get(n.get("block")),
                "extent": n.get("extent") or {}, "via": "제목",
                "path": _ancestor_path(n, byid),
            })

    # 사람이 더한 용어를 **같은 키로** 합친다. 겹치면 새 용어가 아니라 출현이 는다 —
    # 두 목록이 갈리면 "같은 말인데 두 개" 가 되고 그때부터 어느 쪽이 정본인지 모른다.
    for key, u in _load_user().items():
        row = terms.setdefault(key, {"term": u["term"], "key": key,
                                     "surfaces": [], "occurrences": []})
        for sfc in u.get("surfaces", []):
            if sfc not in row["surfaces"]:
                row["surfaces"].append(sfc)
        row["occurrences"] += u.get("occurrences", [])
        row["user"] = True
        # 생애주기는 저장된 용어의 것 — 제목에서 거둔 출현은 상태가 없다.
        for k in ("status", "source", "confidence", "hits", "misses"):
            row[k] = u.get(k)
        if u.get("note"):
            row["note"] = u["note"]

    rows = []
    for row in terms.values():
        docs_of = sorted({o["doc"] for o in row["occurrences"]})
        via: dict[str, int] = {}
        for o in row["occurrences"]:
            v = o.get("via", "본문")
            via[v] = via.get(v, 0) + 1
        rows.append({**row, "n": len(row["occurrences"]), "via": via,
                     "user": bool(row.get("user")),
                     "docs": docs_of, "n_docs": len(docs_of),
                     # 이 말 자체가 구역 제목이다 — 문서가 **다루는** 특화 어휘
                     "is_heading": row["key"] in title_keys,
                     # 어느 깊이의 제목인가 — L1(장) 이 굵은 주제, 깊을수록 세목
                     "heading_levels": sorted(title_levels.get(row["key"], [])),
                     # 여러 문서에 걸친 용어가 이 어휘의 뼈대다 — 먼저 보여 준다
                     "shared": len(docs_of) > 1})
    # 걸친 문서 수 → 출현 수 → 이름 순
    rows.sort(key=lambda r: (-r["n_docs"], -r["n"], r["key"]))
    return {"docs": docs, "terms": rows,
            "stats": {"terms": len(rows), "documents": len(docs),
                      "shared": sum(1 for r in rows if r["shared"]),
                      "occurrences": sum(r["n"] for r in rows)}}


@router.get("", summary="용어 + 출현 지점")
def glossary(shared_only: bool = Query(False, description="여러 문서에 걸친 용어만"),
             q: Optional[str] = Query(None, description="이름으로 거르기"),
             include_dead: bool = Query(False, description="tombstone 도 포함")):
    data = collect()
    rows = data["terms"]
    if not include_dead:
        # 강등된 용어는 기본 목록에서 뺀다 — 지운 게 아니라 비활성이다(감사 가능).
        rows = [r for r in rows if r.get("status") != "tombstone"]
    if shared_only:
        rows = [r for r in rows if r["shared"]]
    if q:
        needle = norm(q)
        rows = [r for r in rows if needle in r["key"]]
    return {**data, "terms": rows}


# `/{key}` 캐치올보다 **먼저** 등록해야 하는 고정 경로들 — 'review' 는 용어가 아니다.
@router.get("/review", summary="검수 큐 — 잠정 용어와 근거")
def review_queue(limit: int = Query(100, ge=1, le=500)):
    """잠정 용어를 근거(출처·판정 메모·스니펫)와 함께 — 사람이 승인/반려한다.
    오래된 것부터 — 먼저 태어난 후보가 먼저 심사받는다."""
    rows = [r for r in _load_user().values() if r.get("status") == "잠정"]
    rows.sort(key=lambda r: r.get("created", ""))
    out = []
    for r in rows[:limit]:
        out.append({"term": r["term"], "key": r["key"],
                    "surfaces": r.get("surfaces", []),
                    "source": r.get("source"), "confidence": r.get("confidence"),
                    "note": r.get("note", ""), "created": r.get("created", ""),
                    "n_occ": len(r.get("occurrences", [])),
                    "docs": r.get("scope", {}).get("docs", []),
                    # 실적 — 재심사 근거 (인용 ✓ / 무관 지문 ✗)
                    "hits": r.get("hits", 0), "misses": r.get("misses", 0),
                    "snippets": [o.get("text", "") for o in
                                 r.get("occurrences", [])[:3] if o.get("text")]})
    return {"queue": out, "total": len(rows)}


@router.post("/scan-doc-titles",
             summary="외부 문서제목 추출 — 참조가 부른, 코퍼스에 없는 문서명을 잠정 용어로")
def scan_doc_titles():
    """본문 참조가 이름으로 부른 문서(「보험업법」 제108조) 중 **코퍼스에 없는
    것**의 제목을 뽑아 잠정 용어로 등재한다. 참조 해소(cross_resolve)는 이런
    참조를 후보 없음으로 조용히 버린다 — 그 버려지는 이름이 여기의 재료다.

    등재는 잠정(source="문서제목")이라 검수 큐를 지나야 산다 — 승인해야
    색인·하이라이트에 참여하고, 반려(tombstone)하면 다시 올라오지 않는다."""
    from lawrag.core.rag import index as index_mod          # 지연 — 순환 회피
    from lawrag.core.rag import refs as refs_mod
    idx = index_mod.current()
    fold = refs_mod._fold_name
    corpus = {fold(v.name) for v in idx.docs.values() if v.name}
    rows = _load_user()
    found: dict[str, dict] = {}
    # 신호 둘의 합집합이다 (전수조사 2026-08-12: 외부 「」 제목 318 중 137은
    # 제N조가 한 번도 안 따라와 참조 문법만으로는 사각).
    #   참조   "「보험업법」 제108조" — 참조 문법의 힌트 (따옴표 없어도 잡힘)
    #   꺽쇠   "「건축법」에 따른…"  — 법령 표기 관행상 「」 안은 거의 문서 제목
    #          (실측 328 중 비제목 잡음 ~5건 — 승인제도가 거른다)
    _BRACKET = re.compile(r"「([^」\n]{2,60})」")

    for doc_id, v in idx.docs.items():
        for b in v.blocks:
            text = b.get("text") or ""

            def take(hint: str, example: str) -> None:
                h = fold(hint)
                if not h or any(h in nm or nm in h for nm in corpus):
                    return                           # 내 문서 — 참조 해소 몫이다
                key = norm(hint)
                if not key or key in rows:
                    return                           # 이미 있음 — 기각(tombstone)도 존중
                r = found.setdefault(key, {
                    "term": hint, "key": key, "surfaces": [hint],
                    "source": "문서제목", "status": "잠정", "confidence": "medium",
                    "note": f"본문이 부른 외부 문서 — 예: {example}",
                    "occurrences": [], "hits": 0, "misses": 0,
                    "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })
                if len(r["occurrences"]) < 200:      # 폭주 방지 — 근거는 이걸로 충분
                    own = v.owner(b.get("idx")) or {}
                    r["occurrences"].append({
                        "doc_id": doc_id, "doc": v.name,
                        "node": own.get("id"), "level": own.get("level"),
                        "surface": own.get("surface"), "section": own.get("title"),
                        "path": v.path(own.get("id")),
                        "page": b.get("page"), "block": b.get("idx"),
                        "text": text[:120], "bbox": b.get("rect"),
                        "kind": b.get("kind", "text"), "via": "본문"})

            # 신호 ① — 참조 문법의 힌트 (따옴표 없는 "보험업법 제108조"도 잡는다)
            if "제" in text:
                for ref in refs_mod.find(text):
                    hint = (ref.hint or "").strip()
                    if not hint or refs_mod._ANAPHORA.match(hint):
                        continue
                    h = fold(hint)
                    # cross_resolve 의 named 판정과 같은 규율 — 총칭('법')은 이름이 아니다
                    if not h or (not ref.quoted and refs_mod._GENERIC_HINT.match(h)):
                        continue
                    take(hint, f"「{hint}」 {ref.surface.strip()}")
            # 신호 ② — 꺽쇠 자체. 제N조가 안 따라와도 제목이다
            for m in _BRACKET.finditer(text):
                hint = m.group(1).strip()
                if re.match(r"제\s*\d", hint):       # 「제7조 재예치」 — 조 라벨 오탐
                    continue
                take(hint, f"「{hint}」")
    for key, r in found.items():
        rows[key] = _defaults(r)
    if found:
        _save_user(rows)
    return {"added": len(found),
            "terms": sorted(r["term"] for r in found.values()),
            "queued": sum(1 for r in rows.values() if r.get("status") == "잠정")}


@router.get("/relations", summary="용어 관계 — 문서 관계 위에 얹어 보여주기 (실험)")
def relations():
    """타이핑된 관계는 아직 없다 — 컴파일이 모아 둔 **후보**(계층·PROTO_REL)를
    문서 간 참조와 함께 그대로 보여 준다. 사람이 간접적으로 추론하는 용도다
    (사용자 결정 2026-08-10: 보여주기 우선, 타이핑은 수요 확인 후)."""
    out_dir = ROOT / "var" / "out" / "terms"

    def _load(name: str, key: str) -> list:
        p = out_dir / name
        if not p.exists():
            return []
        try:
            return json.loads(p.read_text(encoding="utf-8")).get(key, [])
        except Exception:
            return []

    hier = _load("hierarchy.json", "edges")
    proto = [r for r in _load("proto_rel.json", "proto_rel")
             if r.get("status") == "candidate"]

    # 용어 → 걸친 문서 (저장된 용어의 스코프에서) — 관계가 어느 문서 사이에
    # 걸쳐 있는지 없으면 "간접 추론"이 안 된다.
    docs_of: dict[str, list] = {}
    names: dict[str, str] = {}
    for doc_id, meta, _res in _docs():
        names[doc_id] = meta.get("name", doc_id)
    for key, t in _load_user().items():
        docs_of[key] = [{"doc_id": d, "doc": names.get(d, d)}
                        for d in t.get("scope", {}).get("docs", [])]

    for e in hier:
        e["docs"] = docs_of.get(e.get("child"), [])
    for r in proto:
        r["docs"] = sorted({d["doc"] for k in (r["a"], r["b"])
                            for d in docs_of.get(k, [])})

    # 문서 간 확정 참조 요약 — links.json 유래 간선을 쌍으로 센다
    doc_links: dict[tuple, int] = {}
    try:
        from lawrag.core.rag import index as index_mod
        for e in index_mod.current().cross_ref_edges():
            k = (e.get("src_doc"), e.get("dst_doc"))
            doc_links[k] = doc_links.get(k, 0) + 1
    except Exception:
        pass
    links = [{"src": names.get(a, a), "dst": names.get(b, b), "n": n}
             for (a, b), n in sorted(doc_links.items(), key=lambda kv: -kv[1])]

    return {"hierarchy": hier, "proto_rel": proto[:100], "doc_links": links,
            "note": "전부 후보다 — 승인·타이핑 전. 근거는 var/out/terms/ 감사 파일."}


@router.get("/coverage", summary="커버리지 공백 지도 — 구역별 앵커 용어 수")
def coverage_map():
    """공백 구역의 크기가 곧 탐험 루프가 감당할 몫이다(ontology_kg Phase 1).
    저장된 용어의 출현 좌표에서 즉석 계산한다 — 문서·용어가 바뀌면 바로 반영."""
    anchored: dict[tuple, set] = {}
    for t in _load_user().values():
        if t.get("status") == "tombstone":
            continue
        for o in t.get("occurrences", []):
            if o.get("node") is not None:
                anchored.setdefault((o["doc_id"], o["node"]), set()).add(t["key"])
    docs = []
    for doc_id, meta, res in _docs():
        byid = {n.get("id"): n for n in res.get("nodes", [])}
        per = [{"node": n.get("id"),
                "path": _ancestor_path(n, byid) or (n.get("title") or ""),
                "title": (n.get("title") or n.get("surface") or ""),
                "terms": len(anchored.get((doc_id, n.get("id")), ()))}
               for n in res.get("nodes", [])]
        gaps = [p for p in per if p["terms"] == 0]
        docs.append({"doc_id": doc_id, "doc": meta.get("name", doc_id),
                     "nodes": len(per), "gaps": len(gaps),
                     "gap_nodes": gaps[:40],
                     "avg_terms": round(sum(p["terms"] for p in per)
                                        / max(len(per), 1), 2)})
    tn = sum(d["nodes"] for d in docs)
    tg = sum(d["gaps"] for d in docs)
    return {"docs": docs, "total": {"nodes": tn, "gaps": tg,
                                    "gap_ratio": round(tg / max(tn, 1), 3)}}


@router.get("/{key}", summary="용어 하나의 출현 전부")
def term(key: str):
    for row in collect()["terms"]:
        if row["key"] == norm(key):
            return row
    raise HTTPException(404, f"용어를 찾을 수 없습니다: {key}")


# ===========================================================================
# 사람이 더하는 용어 — 저장하고, 모든 문서에서 찾아 잇는다
# ===========================================================================
#
# 제목에서 거둔 용어(`collect`)만으로는 부족하다. 사람이 "이 말이 중요하다" 고
# 아는 것이 있고, 그건 제목이 아니라 본문 한가운데 있을 수 있다.
#
# 더한 용어도 **같은 키로 묶인다.** 제목에서 이미 거둔 것과 겹치면 새 용어가 아니라
# 그 용어의 출현이 늘어난다 — 두 목록이 갈리면 "같은 말인데 두 개" 가 된다.


class AddTerms(BaseModel):
    terms: list[str]
    note: str = ""


# 용어의 생애주기(ontology_kg §2.3) — 태어난 경위(source)와 살아있는지(status)를
# 항목마다 갖는다. 승격만 있고 강등이 없으면 인덱스가 노이즈로 비대해진다.
#   source: 수기 | tier1 | 통계 | 질의루프      status: 잠정 | 활성 | tombstone
def _defaults(row: dict) -> dict:
    """옛 파일 마이그레이션 — 읽을 때 채운다. 파일을 일괄 변환하지 않는 이유:
    쓰기 경로가 어차피 전부 여기를 지나고, 읽기 정규화는 옛 백업도 그대로 연다."""
    src = row.get("source") or "수기"
    row["source"] = "수기" if src == "user" else src
    row.setdefault("status", "활성")
    row.setdefault("confidence", "high" if row["source"] == "수기" else "low")
    row.setdefault("scope", {"docs": sorted({o.get("doc_id")
                                             for o in row.get("occurrences", [])
                                             if o.get("doc_id")})})
    row.setdefault("hits", 0)
    row.setdefault("misses", 0)
    row.setdefault("created", "")
    return row


def _load_user() -> dict[str, dict]:
    if not TERMS_FILE.exists():
        return {}
    try:
        raw = json.loads(TERMS_FILE.read_text(encoding="utf-8"))
        return {t["key"]: _defaults(t) for t in raw.get("terms", [])}
    except Exception:
        return {}


def _save_user(rows: dict[str, dict]) -> None:
    TERMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TERMS_FILE.write_text(json.dumps(
        {"terms": sorted(rows.values(), key=lambda r: r["key"])},
        ensure_ascii=False, indent=2), encoding="utf-8")


def _scan(term: str) -> list[dict]:
    """모든 문서의 **블록 본문**에서 이 말을 찾는다.

    제목만 보는 `collect` 와 다르다 — 사람이 더한 말은 본문 한가운데 있을 수 있다.
    찾을 때는 공백을 지운 정규형으로 본다(`민원 처리` 와 `민원처리` 가 갈리면 안 된다).
    """
    needle = norm(term)
    if not needle:
        return []
    out: list[dict] = []
    for doc_id, meta, res in _docs():
        name = meta.get("name", doc_id)
        # 블록 → 그 블록을 덮는 마디. 어느 구역에서 나왔는지가 좌표다.
        owner = {}
        for n in res.get("nodes", []):
            for b in range(n.get("span", [0, 0])[0], max(n.get("span", [0, 0])[1],
                                                          n.get("span", [0, 0])[0] + 1)):
                cur = owner.get(b)
                if cur is None or n.get("level", 0) > cur.get("level", 0):
                    owner[b] = n
        # 제목에서 나온 것과 본문에서 나온 것은 무게가 다르다. 제목이면 그 구역이
        # 그 말을 **다루는** 것이고, 본문이면 그저 **언급**일 수 있다. 표 셀은 또
        # 다르다 — 값의 라벨일 때가 많다. 셋을 갈라 두지 않으면 34회가 다 같아 보인다.
        titles = {n.get("block"): n for n in res.get("nodes", [])}
        byid = {n.get("id"): n for n in res.get("nodes", [])}
        # 덮는 마디까지 포함한 온 경로 — 본문 출현은 "어느 구역 안"이 곧 맥락이다.
        def _full_path(n):
            if not n:
                return ""
            own = (n.get("title") or "").strip() or (n.get("surface") or "").strip()
            up = _ancestor_path(n, byid)
            return f"{up} ▸ {own}" if up and own else (up or own)
        for b in res.get("blocks", []):
            if needle not in norm(b.get("text", "")):
                continue
            n = owner.get(b.get("idx"))
            out.append({
                "doc_id": doc_id, "doc": name,
                "node": (n or {}).get("id"), "level": (n or {}).get("level"),
                "surface": (n or {}).get("surface"), "section": (n or {}).get("title"),
                "path": _full_path(n),
                "page": b.get("page"), "block": b.get("idx"),
                "text": (b.get("text") or "")[:120],
                "bbox": b.get("rect"),        # 0~1 비율 (뷰어가 그대로 쓴다)
                "kind": b.get("kind", "text"),
                "via": ("제목" if b.get("idx") in titles
                        else "표" if b.get("kind") == "table"
                        else "그림" if b.get("kind") == "figure" else "본문"),
            })
    return out


@router.post("/terms", summary="용어 더하기 — 목록으로 받는다")
def add_terms(body: AddTerms):
    """받은 말들을 저장하고 **모든 문서에서 찾아** 출현을 붙인다.

    이미 있는 키면 새로 만들지 않고 그 용어를 다시 훑는다(문서가 늘었을 수 있다).
    """
    rows = _load_user()
    added, updated = [], []
    for raw in body.terms:
        t = (raw or "").strip()
        if not t:
            continue
        key = norm(t)
        row = rows.get(key)
        if row is None:
            row = _defaults({
                "term": t, "key": key, "surfaces": [t], "note": body.note,
                "source": "수기", "status": "활성", "confidence": "high",
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            rows[key] = row
            added.append(t)
        else:
            if t not in row["surfaces"]:
                row["surfaces"].append(t)
            row["note"] = body.note or row.get("note", "")
            updated.append(t)
        _rescan_row(row)                  # 표면형 전부를 다시 훑는다 — 문서가 늘었을 수 있다
    _save_user(rows)
    return {"added": added, "updated": updated, "total": len(rows),
            "store": str(TERMS_FILE),
            "found": {norm(t): len(rows[norm(t)]["occurrences"])
                      for t in body.terms if norm(t) in rows}}


class PatchTerm(BaseModel):
    status: Optional[str] = None       # 활성 | 잠정 | tombstone
    note: Optional[str] = None


@router.patch("/terms/{key}", summary="용어 검수 — 상태 승급/강등")
def patch_term(key: str, body: PatchTerm):
    """검수 큐의 승인(잠정→활성)·반려(→tombstone)가 이 문 하나로 지나간다.
    수기 용어의 상태도 바꿀 수 있다 — 사람이 넣었어도 틀릴 수 있다."""
    rows = _load_user()
    row = rows.get(norm(key))
    if row is None:
        raise HTTPException(404, f"저장된 용어가 아닙니다: {key}")
    if body.status is not None:
        if body.status not in ("활성", "잠정", "tombstone"):
            raise HTTPException(400, "status 는 활성|잠정|tombstone 중 하나입니다")
        row["status"] = body.status
    if body.note is not None:
        row["note"] = body.note
    _save_user(rows)
    return {"ok": True, "term": row["term"], "status": row["status"]}


def _rescan_row(row: dict) -> None:
    """표면형 **전부**로 훑는다 — 별칭(PSV)으로만 나오는 자리도 출현이다.
    같은 (문서, 블록) 은 한 번만 싣는다."""
    seen: set[tuple] = set()
    occ: list[dict] = []
    for sfc in row.get("surfaces") or [row.get("term", "")]:
        for o in _scan(sfc):
            k = (o.get("doc_id"), o.get("block"))
            if k in seen:
                continue
            seen.add(k)
            occ.append(o)
    row["occurrences"] = occ
    row["scope"] = {"docs": sorted({o.get("doc_id") for o in occ if o.get("doc_id")})}


@router.delete("/terms/{key}", summary="용어 강등 — 시스템 산 용어는 tombstone, 수기는 삭제")
def del_term(key: str):
    """시스템이 낳은 용어(tier1·통계·질의루프)는 지우지 않고 **비활성 표기**한다 —
    같은 후보가 다시 올라오는 것을 막으려면 "거부했다"는 기록이 남아야 한다.
    사람이 직접 넣은 용어만 실삭제한다(오타 정리)."""
    rows = _load_user()
    row = rows.get(norm(key))
    if row is None:
        raise HTTPException(404, f"더한 용어가 아닙니다: {key}")
    if row.get("source") == "수기":
        rows.pop(norm(key))
        action = "삭제"
    else:
        row["status"] = "tombstone"
        action = "tombstone"
    _save_user(rows)
    return {"ok": True, "action": action, "total": len(rows)}


@router.post("/rescan", summary="저장된 용어를 모든 문서에서 다시 훑는다")
def rescan():
    """문서를 새로 올린 뒤 부른다 — 저장된 용어의 출현을 갱신한다.
    tombstone 은 건너뛴다(죽은 용어를 훑는 것은 낭비다)."""
    rows = _load_user()
    alive = 0
    for key, row in rows.items():
        if row.get("status") == "tombstone":
            continue
        _rescan_row(row)
        alive += 1
    _save_user(rows)
    return {"terms": len(rows), "rescanned": alive,
            "occurrences": sum(len(r["occurrences"]) for r in rows.values())}
