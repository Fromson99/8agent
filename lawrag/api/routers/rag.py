"""RAG API — 구조화된 문서에 묻는다.

    GET  /v1/rag/search?q=…     검색만 — 결정론, LLM 없음. 저작·검수 화면용.
    POST /v1/rag/ask            검색 → 관련성 필터 → 답변 합성 (LLM)

## 왜 검색과 답변을 가르는가

검색은 결정론이라 키 없이도, 오프라인에서도 돈다. 답변 합성만 LLM 이 필요
하다. 갈라 두면 검색 품질을 사람이 따로 검수할 수 있고(어느 단에서 무엇이
잡혔는지 ladder 가 남는다), LLM 이 죽어도 검색은 산다.

## 인용은 좌표다

답변의 refs 는 {doc_id, node, block, page} 를 싣는다. 구조 뷰어의 딥링크
(`/structure/?doc=…&node=…&block=…`)가 그대로 그 자리를 연다 — "어디에 그렇게
쓰여 있나" 에 화면으로 답할 수 없으면 인용이 아니다.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from lawrag.core import llm as llm_mod
from lawrag.core import logbook
from lawrag.core.rag import answer as answer_mod
from lawrag.core.rag import audit as audit_mod
from lawrag.core.rag import index as index_mod
from lawrag.core.rag import judge as judge_mod
from lawrag.core.rag import recover as recover_mod
from lawrag.core.rag import switches as switches_mod
from lawrag.core.rag import tuples as tuples_mod
from lawrag.core.rag import wikictx
from lawrag.core.rag import wikiledger
from lawrag.core.rag import verdicts as verdicts_mod
# `core.rag.search` 모듈이 아니라 함수를 바로 받는다 — 패키지 facade 가
# 같은 이름(search)으로 함수를 내보내서, 모듈 경유 접근은 헷갈린다.
from lawrag.core.rag.search import search as run_search

router = APIRouter(prefix="/v1/rag", tags=["rag"])

log = logging.getLogger("lawrag.api.rag")


def _ask_event(out: dict, dur_ms: int) -> None:
    """질의 한 건의 관측 — /logs/ 화면이 그리는 그대로. 응답에서 뽑아 적는다:
    응답이 곧 사용자가 본 것이라, 따로 모으면 화면과 로그가 갈린다."""
    logbook.rag_event(
        "ask",
        q=out.get("question", ""), qid=out.get("qid"),
        mode=out.get("mode", ""), dur_ms=dur_ms,
        answerable=out.get("answerable"),
        n_context=len(out.get("context") or []),
        n_refs=len(out.get("refs") or []),
        n_discards=len(out.get("discards") or []),
        ladder=out.get("ladder") or [],
        filter=out.get("filter"),
        recovery=(out.get("recovery") or {}).get("rungs_fired"),
        usage=out.get("usage"),
        answer=(out.get("answer") or "")[:400],
        refs=[{"doc": r.get("doc"), "path": r.get("path"), "page": r.get("page")}
              for r in (out.get("refs") or [])[:10]],
        error=out.get("error"))


def _hit_row(h) -> dict:
    return {"kind": h.kind, "value": h.value, "score": h.score,
            "match": h.match, "reasons": h.reasons,
            "doc_id": h.doc_id, "doc": h.doc, "node": h.node, "block": h.block,
            "occurrences": len(h.occurrences) if h.occurrences else 0}


@router.get("/search", summary="검색만 — LLM 없음 (mode=vector: 벡터 우선 회수)")
def rag_search(q: str = Query(..., description="질의"),
               mode: str = Query("auto", description="auto | vector")):
    t0 = time.perf_counter()
    idx = index_mod.current()
    if mode == "vector":
        from lawrag.core.rag import vecfirst

        sections, vmeta = vecfirst.retrieve(idx, q)
        logbook.rag_event("search", q=q, mode="벡터우선",
                          n_hits=len(sections), dur_ms=logbook.ms(t0),
                          vector_hits=vmeta.get("vector_hits"),
                          depth=vmeta.get("depth"))
        return {"query": q, "mode": "벡터우선",
                "refs": vecfirst.static_refs(sections), **vmeta,
                "documents": len(idx.docs)}
    res = run_search(idx, q)
    logbook.rag_event("search", q=q, mode=res.mode, n_hits=len(res.hits),
                      ladder=res.ladder, dur_ms=logbook.ms(t0))
    return {"query": res.query, "mode": res.mode, "ladder": res.ladder,
            "hits": [_hit_row(h) for h in res.hits],
            "documents": len(idx.docs), "entries": len(idx.entries)}


class Ask(BaseModel):
    question: str
    # 필터를 끌 수 있다 — 회수가 왜 이런지 볼 때는 거르지 않은 원본이 필요하다.
    filter: bool = True
    # 회복 루프(의미해석→깔때기→원문→수색대→둘러보기)를 끌 수 있다.
    recover: bool = True
    # "vector"(기본 — 벡터 진입 + 참조 닫힘 + 정적 출처) | "auto"(용어 사다리).
    # 벤치 실측(2026-08-10)에서 패러프레이즈 질의는 벡터가 뚜렷이 우세해
    # 기본이 됐다. 벡터가 빈손이면 용어 사다리로 자동 폴백한다.
    mode: str = "vector"


def _llm():
    """키가 없으면 None — 호출부가 검색까지만 내려간다."""
    if not llm_mod.available():
        return None
    return llm_mod.LLM()


@router.get("/links/summary", summary="참조 수만 — 상단바 배지·홈 현황용")
def rag_links_summary():
    """/links 는 기하·원문 문맥까지 실어 수 MB 다. 배지와 현황 칩은 수만
    필요하므로 여기서 끝낸다 — 홈이 11.8MB 를 받아 length 만 세던 것을 끊는다."""
    idx = index_mod.current()
    edges, pending = idx.cross_refs()
    return {"docs": len(idx.docs),
            "cross": len(edges),
            "pending": len(pending),
            "in_doc": sum(len(es or []) for es in idx.ref_edges().values())}


@router.get("/links", summary="조문 상호참조 — 확정 간선과 보류 목록")
def rag_links():
    """저작·검수 화면(/links/)용. 좌표에 사람이 읽는 경로를 붙여 준다 —
    화면이 "어디가 어디를 가리키나"를 문장으로 보여줄 수 있어야 검수다.
    pending 은 닫힌 후보와 원문 문맥이 실려 있어 사람이 그대로 고를 수도 있다."""
    idx = index_mod.current()
    edges, pending = idx.cross_refs()

    # PDF 오버레이용 기하 — 블록의 정규화 rect(0~1) 와 쪽. 참조가 쓰인 자리
    # 위에 링크를 얹으려면 화면이 이 좌표를 그대로 비율로 쓰면 된다.
    def block_geo(v, blk) -> dict:
        b = v.block_by_idx.get(blk) or {} if v else {}
        return {"page": b.get("page"), "rect": b.get("rect")}

    def node_geo(v, node_id) -> dict:
        n = (v.by_id.get(node_id) or {}) if v else {}
        blk = n.get("block")
        if blk is None:
            blk = (n.get("span") or [0, 0])[0]
        g = block_geo(v, blk)
        return {"page": n.get("page") or g["page"], "block": blk, "rect": g["rect"]}

    in_doc = {}
    for d, es in idx.ref_edges().items():
        if not es:
            continue
        v = idx.docs[d]
        in_doc[d] = [{"src": e["src"], "src_path": v.path(e["src"]),
                      "dst": e["dst"], "dst_path": v.path(e["dst"]),
                      "surface": e["surface"], "block": e.get("block"),
                      "rel": e.get("rel", "인용"), "rel_via": e.get("rel_via"),
                      "src_geo": block_geo(v, e.get("block")),
                      "dst_geo": node_geo(v, e["dst"])}
                     for e in es]

    def _cross_row(e: dict) -> dict:
        sv, dv = idx.docs.get(e.get("src_doc")), idx.docs.get(e.get("dst_doc"))
        return {**e,
                "src_doc_name": sv.name if sv else e.get("src_doc", ""),
                "dst_doc_name": dv.name if dv else e.get("dst_doc", ""),
                "src_path": sv.path(e.get("src")) if sv else "",
                "dst_path": dv.path(e.get("dst")) if dv else "",
                "src_geo": block_geo(sv, e.get("block")),
                "dst_geo": node_geo(dv, e.get("dst"))}

    pend = []
    for p in pending:
        sv = idx.docs.get(p["src_doc"])
        cands = []
        for c in p.get("candidates", []):
            v = idx.docs.get(c.get("doc_id"))
            cands.append({**c, "doc": v.name if v else c.get("doc_id", ""),
                          "path": v.path(c.get("node")) if v else "",
                          "geo": node_geo(v, c.get("node"))})
        pend.append({**p, "src_doc_name": sv.name if sv else "",
                     "src_path": sv.path(p["src"]) if sv else "",
                     "src_geo": block_geo(sv, p.get("block")),
                     "candidates": cands})

    def n_pages(v) -> int:
        return max([b.get("page") or 1 for b in v.blocks] or [1])

    return {"docs": [{"doc_id": d, "doc": v.name, "pages": n_pages(v),
                      "n_in": len(idx.ref_edges().get(d) or [])}
                     for d, v in idx.docs.items()],
            "in_doc": in_doc,
            "cross": [_cross_row(e) for e in edges],
            "pending": pend}


@router.get("/section", summary="구역 하나 — 원문과 그 구역의 참조")
def rag_section(doc_id: str = Query(...), node: int = Query(...)):
    """그래프 화면의 원문 패널용. 본문(잘리면 표시됨)과 함께, 이 구역 범위에서
    난 참조(나가는 것)와 이 구역을 가리키는 참조(들어오는 것)를 좌표로 준다 —
    화면은 본문 속 표면형을 이 좌표로 링크해 위키처럼 건너다닌다."""
    idx = index_mod.current()
    v = idx.docs.get(doc_id)
    n = v.by_id.get(node) if v else None
    if v is None or n is None:
        raise HTTPException(404, "구역이 없습니다")
    span = n.get("span") or [0, 0]

    def inside(b) -> bool:
        return b is not None and span[0] <= b < max(span[1], span[0] + 1)

    def geo(view, node_id) -> dict:
        """구역의 자리 — 쪽과 정규화 rect. PDF 패널이 앵커 상자를 그린다."""
        nd = (view.by_id.get(node_id) or {}) if view else {}
        blk = nd.get("block")
        if blk is None:
            blk = (nd.get("span") or [0, 0])[0]
        b = view.block_by_idx.get(blk) or {} if view else {}
        return {"page": nd.get("page") or b.get("page"), "rect": b.get("rect")}

    refs, seen = [], set()

    def add_ref(surface, dst_doc, dst, via="", rule=None):
        if (surface, dst_doc, dst) in seen:
            return
        seen.add((surface, dst_doc, dst))
        dv = idx.docs.get(dst_doc)
        refs.append({"surface": surface, "dst_doc": dst_doc, "dst": dst,
                     "dst_path": dv.path(dst) if dv else "", "via": via,
                     # 무기명 발동 금지는 표현층까지다 — 규칙이 옮긴 간선은
                     # 화면에서도 어느 규칙인지 보여야 한다.
                     **({"rule": rule} if rule else {}),
                     "geo": geo(dv, dst)})

    for e in idx.ref_edges().get(doc_id, []):
        if inside(e.get("block")):
            add_ref(e["surface"], doc_id, e["dst"])
    for e in idx.cross_ref_edges():
        if e.get("src_doc") == doc_id and inside(e.get("block")):
            add_ref(e["surface"], e["dst_doc"], e["dst"], e.get("via", ""),
                    e.get("rule"))

    cited = []
    for e in idx.ref_edges().get(doc_id, []):
        if e["dst"] == node:
            cited.append({"surface": e["surface"], "src_doc": doc_id,
                          "src": e["src"], "src_path": v.path(e["src"])})
    for e in idx.cross_ref_edges():
        if e.get("dst_doc") == doc_id and e.get("dst") == node:
            sv = idx.docs.get(e["src_doc"])
            cited.append({"surface": e["surface"], "src_doc": e["src_doc"],
                          "src": e["src"],
                          "src_path": sv.path(e["src"]) if sv else ""})

    # 자식 계층 — 구역 안의 ①·1.·가.·1) 트리. 패널의 "계층 보기"가 각 층을
    # 골라 그 자리(geo)로 하이라이트·이동한다. 라벨이 빈 층을 위해 첫 블록
    # 첫머리도 싣는다.
    kids_of: dict = {}
    for nd in v.nodes:
        if nd.get("parent") is not None:
            kids_of.setdefault(nd["parent"], []).append(nd)

    children: list = []

    def walk(nid: int, depth: int) -> None:
        for nd in kids_of.get(nid, []):
            if len(children) >= 400:            # 폭주 방지 — 부칙 전체 같은 큰 구역
                return
            label = ((nd.get("surface") or "").strip()
                     or (nd.get("title") or "").strip())
            blk = v.block_by_idx.get((nd.get("span") or [0, 0])[0]) or {}
            children.append({"node": nd.get("id"), "parent": nid, "depth": depth,
                             "label": label, "fixed": bool(nd.get("교정됨")),
                             "snippet": (blk.get("text") or "")[:60],
                             "geo": geo(v, nd.get("id"))})
            walk(nd.get("id"), depth + 1)

    walk(node, 0)

    from lawrag.core.rag.answer import SECTION_CHARS
    outline = v.section_outline(n, cap=SECTION_CHARS)

    # 이 본문에 나타나는 **승인(활성) 용어** — 화면이 형광으로 세운다.
    # 색인 항목은 활성 용어만 실으므로(잠정·기각은 밖) 따로 거를 것이 없다.
    terms_hit: dict[str, str] = {}
    for ent in idx.entries:
        if ent.kind == "용어" and ent.value and ent.value in outline:
            terms_hit.setdefault(ent.value, ent.key)
    terms = [{"surface": s, "key": k}
             for s, k in sorted(terms_hit.items(), key=lambda x: -len(x[0]))]

    return {"doc_id": doc_id, "node": node, "doc": v.name, "path": v.path(node),
            "page": n.get("page"), "geo": geo(v, node),
            "pages": max([b.get("page") or 1 for b in v.blocks] or [1]),
            "text": v.section_text(n, cap=SECTION_CHARS),
            # 구조화 본문 — 항(①)·호(1.)가 마디로 서 있으면 들여쓰기로 계층이
            # 보인다. 본문을 보여주는 화면은 이것을 기본으로 쓴다(text 는 호환용).
            "outline": outline,
            "terms": terms,
            "children": children,
            "refs": refs, "cited_by": cited}


def _links_file() -> dict:
    """links.json 전체 — links 밖의 키(runs 등)도 그대로 든다."""
    path = index_mod.links_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _write_links_file(data: dict) -> None:
    path = index_mod.links_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def _save_links(links: list) -> int:
    """links.json 에 덧붙인다 — 같은 (출발, 도착) 좌표는 한 번만.
    links 외의 키(runs)는 건드리지 않고 보존한다."""
    data = _links_file()
    cur: list = data.get("links", [])
    seen = {(c.get("src_doc"), c.get("src"), c.get("dst_doc"), c.get("dst"))
            for c in cur}
    fresh = [l for l in links
             if (l["src_doc"], l["src"], l["dst_doc"], l["dst"]) not in seen]
    if fresh:
        data["links"] = cur + fresh
        _write_links_file(data)
    return len(fresh)


def _record_settle_run(run: dict) -> None:
    """settle 실행 이력을 links.json "runs" 에 남긴다 — 연결 국면의 자기
    기록이다 (docs/LINEAGE.md). 확정이 0건이어도 실행 사실은 남는다 —
    계보 원장이 '한 번도 안 돌았음'과 '돌았는데 굳은 게 없음'을 구별해야
    해서다. 최근 50회만 이력으로 든다 — 이력이지 로그가 아니다."""
    data = _links_file()
    data.setdefault("links", [])
    runs = data.get("runs", [])
    runs.append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 **run})
    data["runs"] = runs[-50:]
    _write_links_file(data)


@router.post("/links/settle", summary="보류 참조를 LLM 판정으로 확정 — links.json 에 고정")
def rag_links_settle():
    """컴파일 국면의 걸음이다 — 한 번 판정해 links.json 에 고정하고, 질의마다
    재판단하지 않는다. fail-closed: 저신뢰 판정은 보류로 남는다."""
    idx = index_mod.current()
    llm = _llm()
    if llm is None:
        raise HTTPException(503, f"LLM 없음 — {llm_mod.MISSING_HINT} 를 설정해야 판정이 돕니다")
    links, meta = judge_mod.settle_cross(llm, idx)
    out = {**meta, "saved": _save_links(links) if links else 0}
    _record_settle_run({"via": "LLM", **meta, "saved": out["saved"]})
    if llm.log:
        out["usage"] = llm.totals()
    return out


class Pick(BaseModel):
    """사람이 보류 참조를 확정할 때의 좌표 — 화면의 후보 버튼이 그대로 보낸다."""
    src_doc: str
    src: int
    dst_doc: str
    dst: int
    surface: str = ""
    hint: str = ""
    key: Optional[list] = None
    block: Optional[int] = None


@router.post("/links/pick", summary="보류 참조를 사람이 확정 — links.json 에 고정")
def rag_links_pick(body: Pick):
    """LLM 판정과 같은 자리에 같은 모양으로 남는다 — via 만 '사람'이다.
    닫힌 후보 밖의 좌표는 받지 않는다(존재하는 구역이어야 한다)."""
    idx = index_mod.current()
    dv = idx.docs.get(body.dst_doc)
    if (body.src_doc not in idx.docs or dv is None
            or dv.by_id.get(body.dst) is None):
        raise HTTPException(400, "좌표가 유효하지 않습니다 — 문서나 구역이 없습니다")
    saved = _save_links([{"src_doc": body.src_doc, "src": body.src,
                          "dst_doc": body.dst_doc, "dst": body.dst,
                          "surface": body.surface, "hint": body.hint,
                          "key": body.key, "block": body.block, "via": "사람"}])
    return {"saved": saved}


class Unlink(BaseModel):
    src_doc: str
    src: int
    dst_doc: str
    dst: int


@router.post("/links/remove", summary="확정 참조 해제 — links.json 에서 제거")
def rag_links_remove(body: Unlink):
    """저장으로 확정된 간선(LLM·사람)만 지울 수 있다. 이름 대조로 선 간선은
    파일에 없어서 지워도 다음 색인에서 다시 선다 — 그건 해제가 아니라 구조를
    고칠 일이다. 지운 보류는 다시 보류 목록에 나타난다(되돌리기다, 삭제가 아니라)."""
    data = _links_file()
    cur: list = data.get("links", [])
    keep = [l for l in cur
            if (l.get("src_doc"), l.get("src"), l.get("dst_doc"), l.get("dst"))
            != (body.src_doc, body.src, body.dst_doc, body.dst)]
    if len(keep) == len(cur):
        raise HTTPException(404, "저장된 간선이 아닙니다 — 이름 대조로 선 간선은 "
                                 "해제할 수 없습니다")
    data["links"] = keep
    _write_links_file(data)
    return {"removed": len(cur) - len(keep), "left": len(keep)}


@router.get("/switches", summary="엔진 규칙 스위치 — 자동 규칙의 등록부와 상태")
def rag_switches():
    from lawrag.core.rag import switches as switches_mod
    return {"switches": switches_mod.snapshot()}


class SwitchSet(BaseModel):
    key: str
    on: bool


@router.post("/switches", summary="엔진 규칙 켜고 끄기 — 다음 질의부터 반영")
def rag_switches_set(body: SwitchSet):
    """규칙은 코드가 갖고 있지만 켜짐/꺼짐은 사용자 소유다. 끄면 확정 규칙의
    간선은 보류로 내려가고, 동반 규칙은 회수에서 빠진다. 저장된 판정
    (links.json·정정·억제)은 스위치와 무관하다."""
    from lawrag.core.rag import switches as switches_mod
    try:
        switches_mod.set_switch(body.key, body.on)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"switches": switches_mod.snapshot()}


class RelFix(BaseModel):
    src_doc: str
    src: int
    dst: int
    dst_doc: str = ""              # 문서 안 간선이면 빈 값
    rel: str = ""                  # 준용|배제|의제|근거|인용 — 빈 값이면 정정 해제
    surface: str = ""              # 표시용 — 키가 아니다


@router.post("/links/rel", summary="간선 관계 라벨 정정 — 사람이 자동 분류를 덮는다")
def rag_links_rel(body: RelFix):
    """문면 술어 분류(rel_of)가 틀릴 수 있다 — 정정은 links.json 의 rel_fixes 에
    남고 조립 시점에 자동 분류를 덮는다(관측은 고쳐 쓰지 않는다). 같은 좌표를
    다시 보내면 갈아끼우고, rel 을 비워 보내면 정정을 해제한다(자동 분류로 복귀)."""
    kinds = ("준용", "배제", "의제", "수임", "근거", "인용")
    if body.rel and body.rel not in kinds:
        raise HTTPException(400, f"rel 은 {'/'.join(kinds)} 중 하나여야 합니다")
    data = _links_file()
    fixes: list = data.get("rel_fixes", [])
    key = (body.src_doc, body.src, body.dst_doc, body.dst)
    fixes = [f for f in fixes
             if (f.get("src_doc"), f.get("src"), f.get("dst_doc", ""), f.get("dst"))
             != key]
    if body.rel:
        fixes.append({"src_doc": body.src_doc, "src": body.src,
                      "dst_doc": body.dst_doc, "dst": body.dst,
                      "rel": body.rel, "surface": body.surface,
                      "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    data["rel_fixes"] = fixes
    _write_links_file(data)
    return {"fixes": len(fixes)}


def _answer_prompt(llm) -> Optional[dict]:
    """답 합성에 실제로 들어간 프롬프트 — 지식이 어떻게 주입됐는지의 원본.
    진단 튜플에 남겨 디버깅 화면이 질문과 답 사이에 펼쳐 보인다."""
    if llm is None or not llm.log:
        return None
    ex = next((e for e in reversed(llm.log) if e.kind == "rag.answer"), None)
    return {"system": ex.system, "user": ex.user} if ex else None


def _calls(llm) -> Optional[list]:
    """이번 질의의 **모든** LLM 콜 — system·user·응답 원문 그대로.

    답 합성 프롬프트만 남기면 "LLM 이 무엇을 보고 무엇이라 답해서 그 판정이
    섰나"가 답 합성 한 콜만 보인다. 쟁점 판정·필터·착지 교정도 각각 판정이라
    같은 자격으로 남긴다 — 관측은 응답을 만든 뒤 접는 일이라 지연이 없다.
    """
    if llm is None or not llm.log:
        return None
    return [{"kind": e.kind, "model": e.model, "dur_ms": e.dur_ms,
             "ttft_ms": e.ttft_ms, "usage": e.usage, "error": e.error,
             "system": e.system, "user": e.user, "응답": e.raw_response}
            for e in llm.log]


def _addendum(idx, sec) -> str:
    """회수 구역이 부칙 조면 그 종류(경과조치·개정·시행일…), 아니면 빈 값.
    관측 전용 — 회수·순위에 관여하지 않는다 (index.addendum_kind 머리 참조)."""
    v = idx.docs.get(sec.doc_id)
    return v.addendum_kind(sec.node) if v is not None else ""


def _spot_note(spots: list, expanded: bool) -> str:
    """사다리 note — 어느 판정기가 골랐는지(트리거/LLM)를 제목 앞에 박는다."""
    via = (spots[0].get("via") or "트리거") if spots else "트리거"
    head = "LLM(검색 전) — " if via.startswith("llm") else "트리거 — "
    return (head + " · ".join(s["title"] for s in spots)
            + (" · 조문 후보로 질의 확장" if expanded else ""))


def _spot_dump(spots: list, via: str) -> list:
    """쟁점 카드를 기록용으로 접는다 — 본문 전문은 아티클이 정본이라 안 싣고,
    **판정에 쓰인 기계 메타**(트리거 적중·판단 축·조문 후보)만 남긴다."""
    return [{"slug": s.get("slug"), "title": s.get("title"),
             "why": s.get("why"), "score": s.get("score"),
             "via": s.get("via") or via, "axis": s.get("axis"),
             # 조문질의 — 질문을 법률용어로 옮긴 문장. 벡터가 무는 실물이라
             # 검수의 핵심 관측이다("왜 이 조문이 왔나"의 앞머리).
             "probe": s.get("probe"),
             "provisions": s.get("provisions")} for s in spots]


def _timing(llm) -> Optional[dict]:
    """이번 질의의 LLM 시간 — 답 합성의 첫 글자 시각(ttft)이 체감 지연이다.
    호출별 내역도 싣는다(교정·필터·판정이 각각 얼마나 먹는지 보인다)."""
    if llm is None or not llm.log:
        return None
    ans = next((e for e in reversed(llm.log) if e.kind == "rag.answer"), None)
    return {"answer_ttft_ms": ans.ttft_ms if ans else None,
            "answer_ms": ans.dur_ms if ans else None,
            "calls": [{"kind": e.kind, "model": e.model,
                       "ttft_ms": e.ttft_ms, "dur_ms": e.dur_ms}
                      for e in llm.log]}


RESPOT_MAX = 6   # 판정 재회수가 보충하는 구역 상한 — 보충이 본 회수를 밀어내면 안 된다


def _respot(idx, q: str, spots: list, sections: list) -> list:
    """판정 재회수 — 판정된 쟁점 카드의 조문 후보로 2차 검색을 돌려 본 회수가
    놓친 구역만 보충한다. 질문이 법령명을 몰라 1차 회수가 빗나간 자리를,
    컨텍스트를 본 판정이 되찾는 recall 장치다 — 리랭커처럼 순서를 고치는 게
    아니라 빠진 것을 데려온다(기존 구역·순서는 그대로). 2차 검색은 결정론
    (run_search)이다 — 판정은 이미 섰고, 여기서 LLM 콜은 없다."""
    qx = wikictx.expand_query(q, spots)
    if qx == q:
        return []
    extra = answer_mod.assemble(idx, run_search(idx, qx))
    have = {(s.doc_id, s.node) for s in sections}
    out = []
    for s in extra:
        if (s.doc_id, s.node) in have:
            continue
        have.add((s.doc_id, s.node))
        out.append(s)
        if len(out) >= RESPOT_MAX:
            break
    return out


def _ask_vector(idx, q: str, llm, spots: Optional[list] = None,
                qx: Optional[str] = None,
                spots_trig: Optional[list] = None,
                qv: str = "") -> Optional[dict]:
    """벡터 우선 모드 — 진입은 벡터, 연결은 참조 닫힘, 출처는 정적.
    LLM 은 답변 문장 합성에만 쓰인다. 필터도 없다 — 회수가 곧 출처다.
    벡터가 빈손이면 None — 호출부가 용어 사다리로 폴백한다.
    spots·qx 는 검색 전 쟁점 분해의 산물 — 회수는 확장 질의(qx)로,
    합성·기록은 원 질의(q)로 간다."""
    from lawrag.core.rag import vecfirst

    spots = spots or []
    sections, vmeta = vecfirst.retrieve(idx, qx or q, llm=llm, vec_query=qv)
    if not sections:
        return None
    n_kw = len(vmeta.get("keywords", []))
    n_entry = len(vmeta["entries"])
    ladder = [
        {"stage": "승인 용어", "count": n_kw,
         "note": (" · ".join(k["용어"] for k in vmeta["keywords"])
                  if n_kw else "질의에 승인 용어 없음")},
        {"stage": "벡터 진입", "count": n_entry,
         "note": ((f"코사인 상위 {n_entry} (히트 {vmeta['vector_hits']})"
                   if n_entry else "벡터 미스 — 색인·모델 확인")
                  + (" · 쟁점 재작성 질의로 진입" if vmeta.get("vec_query")
                     else ""))},
        # 필수 동반(floor)도 sections 에 들어 있다 — 빼지 않으면 겹쳐 센다
        # (실측: 보고 8 vs 실제 5, floor 3).
        {"stage": "참조 확장",
         "count": len(sections) - n_entry - n_kw - len(vmeta.get("floor") or []),
         "note": f"참조 간선 닫힘, 깊이 {vmeta['depth']}"},
    ]
    floor = vmeta.get("floor") or []
    if floor:
        kinds = {}
        for f in floor:
            kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
        ladder.insert(2, {"stage": "필수 동반", "count": len(floor),
                          "note": " · ".join(f"{k} {c}" for k, c in kinds.items())
                                  + " (배제·위임·준용은 판단 없이 동반)"})
    nav = vmeta.get("nav")
    if nav:
        ladder.append({"stage": "간선 항해", "count": len(nav.get("picked", [])),
                       "note": f"LLM 이 간선 카드에서 고름, {nav['hops']}홉"})
    if spots:
        # 쟁점 분해(트리거·확장)는 검색 전의 일이라 사다리 맨 앞에 선다.
        ladder.insert(0, {"stage": "쟁점 분해", "count": len(spots),
                          "note": _spot_note(spots, qx != q if qx else False)})
    # 쟁점 판정 — 컨텍스트 확보 후 LLM 이 사안 전체를 보고 판정한다
    # (키워드 경로와 같은 규약: 판정이 서면 배경을 이끌고, 불가면 트리거 유지).
    spots_judged = None
    if spots_trig is None:
        spots_trig = list(spots)
    if switches_mod.is_on("issue_spot_llm"):
        judged = wikictx.spot_llm(llm, q, sections, index=idx)
        if judged is not None:
            spots = judged
            spots_judged = _spot_dump(spots, "llm")
            ladder.append({"stage": "쟁점 판정", "count": len(spots),
                           "note": "LLM — " + (" · ".join(
                               s["title"] for s in spots)
                               if spots else "걸린 쟁점 없음")})
            added = _respot(idx, q, spots, sections) if spots else []
            if added:
                sections = sections + added
                for i, s in enumerate(sections, start=1):
                    s.n = i
                ladder.append({"stage": "판정 재회수", "count": len(added),
                               "note": "쟁점 조문 후보 재검색 — "
                                       + " · ".join(sorted({s.doc for s in added}))})
    # 착지 교정 — "제2조제3항"을 가리키고 조에 머문 참조를, 답변 전에 자손
    # 후보에서 고쳐 앉힌다. 고친 구역이 곧 이번 답변의 근거다.
    fixes = answer_mod.repair_landings(llm, idx, sections)
    ans = answer_mod.synthesize(llm, q, sections, spots=spots)
    if ans.wiki:
        # 위키는 회수 뒤·합성 안의 일이라 사다리 끝에 선다 — 근거가 아니라 배경.
        ladder.append({"stage": "위키 맥락", "count": len(ans.wiki),
                       "note": " · ".join(w["title"] for w in ans.wiki)})
    out = {"question": q, "mode": "벡터우선", "ladder": ladder,
           "쟁점": {"트리거": _spot_dump(spots_trig, "트리거"),
                    "분해": _spot_dump(spots, "llm(검색전)")
                            if (spots and spots[0].get("via", "").startswith("llm")) else None,
                    "판정": spots_judged, "질의확장": qx if qx and qx != q else "",
                    "벡터질의": vmeta.get("vec_query") or ""},
           "filter": {"in": len(sections), "out": len(sections),
                      "applied": False, "reason": "벡터 모드 — 필터 없음(출처는 정적)"},
           "context": [{"n": s.n, "doc": s.doc, "doc_id": s.doc_id,
                        "node": s.node, "path": s.path,
                        "page": s.page, "kind": s.kind, "matched": s.matched,
                        # 부칙 조의 종류 이름표 — 걸러내지 않는다, 관측만 한다
                        # (어떤 질문에 어떤 종류가 답인지는 아직 데이터가 없다)
                        **({"부칙": _addendum(idx, s)} if _addendum(idx, s) else {})}
                       for s in sections],
           "answer": ans.answer, "answerable": ans.answerable,
           # 출처는 회수 집합 그대로 — 모델 인용은 cited 로 따로 준다.
           "refs": vecfirst.static_refs(sections),
           "cited": [r.get("n") for r in ans.refs],
           # 판정 지문은 여기 없다 — 답을 보낸 **뒤** 백그라운드 감사가 남긴다
           # (audit.py). 답변 콜에 얹으면 그 판정을 만드는 시간이 곧 응답 지연이다.
           "discards": [],
           # 착지 교정 — 이번 답변에서 LLM 이 고쳐 앉힌 참조. 간선 반영은 승인 몫.
           "fixes": fixes}
    if ans.wiki:
        out["wiki"] = ans.wiki
    if ans.error:
        out["error"] = ans.error
    if llm is not None and llm.log:
        out["usage"] = llm.totals()
        out["timing"] = _timing(llm)
    try:
        out["qid"] = tuples_mod.log_ask(out, prompt=_answer_prompt(llm),
                                       calls=_calls(llm))
        # 사후 감사 — 응답을 만든 **뒤** 큐에 넣는다(여기서 기다리지 않는다).
        audit_mod.submit(llm, out["qid"], q, ans.answer, sections,
                         {r.get("n") for r in ans.refs})
        if ans.wiki:
            # 위키 적중 원장 — 어떤 아티클이 끼었나. 피드백이 오면 부검이 붙는다.
            wikiledger.record(out["qid"], q, [w["slug"] for w in ans.wiki],
                              ans.answerable)
        if fixes:
            verdicts_mod.log_fixes(out["qid"], q, fixes)
        # 용어 진입의 실적 — 인용되면 hits, 무관 지문이면 misses. 중립(인용도
        # 지문도 아님)은 세지 않는다 — 애매함을 실적으로 굳히지 않는다.
        if vmeta.get("keywords"):
            kw_by_coord = {(k["doc_id"], k["node"]): k["key"]
                           for k in vmeta["keywords"]}
            cited_n = {r.get("n") for r in ans.refs}
            # 무관 지문은 이제 사후 감사가 남긴다 — 이 시점에 아직 없다.
            # 인용된 것만 hits 로 세고, miss 는 감사가 백로그에 적는다.
            miss_n = set()
            hit_keys, miss_keys = [], []
            for s in sections:
                if s.kind != "용어":
                    continue
                key = kw_by_coord.get((s.doc_id, s.node))
                if key is None:
                    continue
                if s.n in cited_n:
                    hit_keys.append(key)
                elif s.n in miss_n:
                    miss_keys.append(key)
            verdicts_mod.score_terms(hit_keys, miss_keys)
        if vmeta["entries"] and ans.answerable:
            tuples_mod.record_candidates(
                q, [{"doc_id": e["doc_id"], "node": e["node"], "via": "벡터"}
                    for e in vmeta["entries"]])
    except Exception:                                    # pragma: no cover
        log.exception("진단 튜플 적재 실패 — 질의응답은 그대로 낸다")
    return out


@router.post("/ask", summary="질의응답 — 검색 → 필터 → 합성 (mode=vector: 벡터 우선)")
def rag_ask(body: Ask):
    t0 = time.perf_counter()
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(400, "질문이 비었습니다")
    log.info("질의 시작 — '%s' (mode=%s, filter=%s, recover=%s)",
             q[:60], body.mode, body.filter, body.recover)
    idx = index_mod.current()
    llm = _llm()
    if llm is None:
        log.warning("LLM 없음 — 검색까지만 내려간다 (%s 미설정)", llm_mod.MISSING_HINT)

    # 쟁점 분해 두 시점 (wikictx 머리): ① 검색 전 — 트리거 매칭이 조문
    # 후보로 질의를 넓힌다(검색 보조, 결정론). ② 컨텍스트 확보 후 — LLM 이
    # 질문+회수 조문을 보고 걸린 쟁점을 판정한다(issue_spot_llm, 아래).
    # 회수는 확장 질의, 합성·기록은 원 질의.
    spots = wikictx.spot(q) if switches_mod.is_on("issue_spot") else []
    spots_trig = list(spots)          # 트리거 결과 — 대조·백테스트용으로 늘 남긴다
    # 검색 전 분해를 LLM 이 한다(issue_spot_pre) — 트리거는 낱말 겹침이라
    # '등록' 하나로 인허가 카드를 무는 오분류가 나고, 그 카드의 조문 후보가
    # 질의를 넓히므로 회수가 통째로 어긋난다. 판정 불가(None)면 트리거 유지.
    spots_pre = None
    if switches_mod.is_on("issue_spot_pre") and llm is not None:
        spots_pre = wikictx.spot_llm(llm, q, index=idx)   # 컨텍스트 없음 = 검색 전 판
        if spots_pre is not None:
            spots = spots_pre
    qx = wikictx.expand_query(q, spots) if spots else q
    # 벡터 채널 전용 질의 — 구어를 빼고 법률문장+법령명만(실측 0.707 vs 0.649).
    # 어휘 사다리는 원문(qx)을 그대로 쓴다: 채널마다 무는 어휘가 다르다.
    qv = wikictx.vector_query(q, spots) if spots else ""

    vector_missed = False
    if body.mode == "vector":
        out_v = _ask_vector(idx, q, llm, spots=spots, qx=qx,
                            spots_trig=spots_trig, qv=qv)
        if out_v is not None:
            _ask_event(out_v, logbook.ms(t0))
            return out_v
        vector_missed = True          # 색인·모델 부재 포함 — 사다리가 받는다

    res = run_search(idx, qx)
    if vector_missed:
        res.ladder.insert(0, {"stage": "벡터 진입", "count": 0,
                              "note": "미스(색인·모델 부재 포함) — 용어 사다리로 폴백"})
    if spots:
        res.ladder.insert(0, {"stage": "쟁점 분해", "count": len(spots),
                              "note": _spot_note(spots, qx != q)})
    sections = answer_mod.assemble(idx, res)
    fmeta = {"in": len(sections), "out": len(sections), "applied": False, "reason": ""}
    if body.filter:
        sections, fmeta = answer_mod.filter_sections(llm, q, sections)
        if sections:
            # 필터가 자리를 비웠다 — 살아남은 구역의 참조("제4조를 참고한다")를
            # 그 빈자리에 채운다. 히트가 상한을 채우면 조립 때는 못 들어온다.
            sections = answer_mod.expand_refs(idx, sections)
            for i, s in enumerate(sections, start=1):
                s.n = i

    # 회복 루프 — 검색이 빈손이거나 필터가 전부 걸렀을 때만 돈다. 원본과 같은
    # 진입 조건이다: "찾은 것도, 실을 것도 없다".
    recovery = None
    if not sections and body.recover:
        recovery = recover_mod.run(llm, idx, q)
        res.ladder.extend(recovery.trail)
        if recovery.coords:
            sections = answer_mod.sections_from_coords(idx, recovery.coords)

    # 쟁점 판정 — 컨텍스트가 다 선 뒤에야 사안 전체가 보인다. LLM 이 질문 +
    # 회수 조문을 보고 걸린 쟁점 카드를 판정한다. 판정이 서면(빈 판정 포함)
    # 그것이 배경을 이끌고, 판정 불가(무LLM·실패)면 트리거 결과를 유지한다.
    spots_judged = None
    if switches_mod.is_on("issue_spot_llm") and sections:
        judged = wikictx.spot_llm(llm, q, sections, index=idx)
        if judged is not None:
            spots = judged
            spots_judged = _spot_dump(spots, "llm")
            res.ladder.append({"stage": "쟁점 판정", "count": len(spots),
                               "note": "LLM — " + (" · ".join(
                                   s["title"] for s in spots)
                                   if spots else "걸린 쟁점 없음")})
            added = _respot(idx, q, spots, sections) if spots else []
            if added:
                sections = sections + added
                for i, s in enumerate(sections, start=1):
                    s.n = i
                res.ladder.append({"stage": "판정 재회수", "count": len(added),
                                   "note": "쟁점 조문 후보 재검색 — "
                                           + " · ".join(sorted({s.doc for s in added}))})

    # 착지 교정 — "제2조제3항"을 가리키고 조에 머문 참조를, 답변 전에 자손
    # 후보에서 고쳐 앉힌다. 고친 구역이 곧 이번 답변의 근거다.
    fixes = answer_mod.repair_landings(llm, idx, sections)
    ans = answer_mod.synthesize(llm, q, sections, spots=spots)
    if ans.wiki:
        res.ladder.append({"stage": "위키 맥락", "count": len(ans.wiki),
                           "note": " · ".join(w["title"] for w in ans.wiki)})

    # 인용 좌표 → 구조 뷰어 딥링크. 모델이 아니라 여기서 만든다.
    # 루트(`/`)는 이제 문서·데이터 관리 화면이다 — 검수 화면 주소를 못 박는다.
    for r in ans.refs:
        link = f"/structure/?doc={r['doc_id']}"
        if r.get("node") is not None:
            link += f"&node={r['node']}"
        if r.get("block") is not None:
            link += f"&block={r['block']}"
        r["link"] = link

    out = {"question": q, "mode": res.mode, "ladder": res.ladder,
           # 쟁점기의 전모 — 트리거가 무엇을 물었고(왜), 판정이 무엇으로
           # 고쳤고, 질의가 어떻게 넓어졌는지. 사다리 note 는 제목뿐이다.
           "쟁점": {"트리거": _spot_dump(spots_trig, "트리거"),
                    "분해": _spot_dump(spots_pre, "llm(검색전)") if spots_pre is not None else None,
                    "판정": spots_judged, "질의확장": qx if qx != q else "",
                    "벡터질의": qv},
           "filter": fmeta,
           "context": [{"n": s.n, "doc": s.doc, "doc_id": s.doc_id,
                        "node": s.node, "path": s.path,
                        "page": s.page, "kind": s.kind, "matched": s.matched,
                        # 부칙 조의 종류 이름표 — 걸러내지 않는다, 관측만 한다
                        # (어떤 질문에 어떤 종류가 답인지는 아직 데이터가 없다)
                        **({"부칙": _addendum(idx, s)} if _addendum(idx, s) else {})}
                       for s in sections],
           "answer": ans.answer, "answerable": ans.answerable, "refs": ans.refs,
           "discards": [], "fixes": fixes}
    if ans.wiki:
        out["wiki"] = ans.wiki
    if recovery is not None:
        out["recovery"] = {"rungs_fired": recovery.rungs_fired, **recovery.meta}
        if recovery.ask_user:
            out["ask_user"] = recovery.ask_user
    if ans.error:
        out["error"] = ans.error
    if llm is not None and llm.log:
        out["usage"] = llm.totals()
        out["timing"] = _timing(llm)

    # 진단 튜플 — 응답에 실어 보내고 버리던 것을 적재한다(ontology_kg §5.2).
    # 탐험 성공은 승격 후보로도 센다. 기록 실패로 질의응답이 죽으면 안 된다.
    try:
        out["qid"] = tuples_mod.log_ask(out, prompt=_answer_prompt(llm),
                                       calls=_calls(llm))
        audit_mod.submit(llm, out["qid"], q, ans.answer, sections,
                         {r.get("n") for r in ans.refs})
        if ans.wiki:
            wikiledger.record(out["qid"], q, [w["slug"] for w in ans.wiki],
                              ans.answerable)
        if fixes:
            verdicts_mod.log_fixes(out["qid"], q, fixes)
        if recovery is not None and recovery.coords:
            tuples_mod.record_candidates(q, recovery.coords)
        # 벡터 단이 찾아 실제 답변에 실린 착지도 승격 후보다 — 벡터 히트는
        # 종착이 아니라 용어의 씨앗이다 (하이브리드 결정, vector.py 머리).
        vec_nodes = {(h.doc_id, h.node) for h in res.hits if h.kind == "벡터"}
        if vec_nodes and ans.answerable:
            coords = [{"doc_id": r["doc_id"], "node": r["node"], "via": "벡터"}
                      for r in ans.refs
                      if (r.get("doc_id"), r.get("node")) in vec_nodes]
            if coords:
                tuples_mod.record_candidates(q, coords)
    except Exception:                                    # pragma: no cover
        log.exception("진단 튜플 적재 실패 — 질의응답은 그대로 낸다")
    _ask_event(out, logbook.ms(t0))
    return out


class Feedback(BaseModel):
    """사용자 신호 — "A 를 물었는데 B 가 나왔다(오답)" 또는 "맞았다(정답)"."""
    qid: str
    verdict: str                       # "정답" | "오답"
    expected: Optional[dict] = None    # 오답일 때 기대 좌표 {doc_id, node}
    note: str = ""


@router.post("/feedback", summary="질의 피드백 — 진단 튜플에 기대 출력을 기록")
def rag_feedback(body: Feedback):
    """실패_원인(a~d) 판정은 여기서 하지 않는다 — 책임 귀속은 별도 국면이다.
    기대 좌표는 실재하는 구역만 받는다(닫힌 후보 규율과 같다)."""
    if body.verdict not in ("정답", "오답"):
        raise HTTPException(400, "verdict 는 '정답' 또는 '오답'이어야 합니다")
    if tuples_mod.find(body.qid) is None:
        raise HTTPException(404, f"질의 기록이 없습니다: {body.qid}")
    expected = None
    if body.expected:
        idx = index_mod.current()
        doc_id, node = body.expected.get("doc_id"), body.expected.get("node")
        v = idx.docs.get(doc_id)
        if v is None or (node is not None and v.by_id.get(node) is None):
            raise HTTPException(400, "기대 좌표가 유효하지 않습니다 — 문서나 구역이 없습니다")
        expected = {"doc_id": doc_id, "doc": v.name, "node": node,
                    "path": v.path(node) if node is not None else ""}
    rec = tuples_mod.log_feedback(body.qid, body.verdict, expected, body.note)
    logbook.rag_event("feedback", qid=body.qid, verdict=body.verdict,
                      expected_path=(expected or {}).get("path"),
                      note=body.note[:200])
    # 위키 부검 — 그 질의에 아티클이 끼었을 때만 원장에 남는다.
    wikiledger.feedback(body.qid, body.verdict, body.note)
    log.info("피드백 — %s %s%s", body.qid, body.verdict,
             f" (기대: {expected['path']})" if expected else "")
    return {"saved": True, "record": rec}


@router.get("/tuples", summary="진단 튜플 목록 — 질의 기록 + 피드백 합본")
def rag_tuples(limit: int = Query(100, ge=1, le=1000)):
    rows = tuples_mod.read(limit=limit)
    n_fb = sum(1 for r in rows if r.get("피드백"))
    return {"tuples": rows, "count": len(rows), "with_feedback": n_fb,
            "candidates": tuples_mod.candidates()}


@router.get("/verdicts", summary="판정 백로그 — 잘못 끌려온 간선의 지문 묶음")
def rag_verdicts():
    """답변 시점 LLM 이 찍은 '오참조·무관' 지문을 간선별로 묶어 준다.
    승인 전까지는 아무것도 안 바뀐다 — 이 화면의 승인이 억제 규칙을 만든다."""
    return verdicts_mod.backlog()


class EdgeResolve(BaseModel):
    """백로그 처리 — 화면의 간선 카드가 그대로 보낸다."""
    src_doc: str
    src: int
    dst_doc: str
    dst: int
    src_path: str = ""
    dst_path: str = ""
    action: str                      # "승인" | "기각"
    note: str = ""


def _rule_edge(src_doc, src, dst_doc, dst):
    """현재 색인에서 그 좌표에 선 간선이 일반 규칙의 산출인지 — 규칙이 바뀌기
    전(억제·재지정 기록 전)에 찾아야 한다. 기록 후에는 색인이 다시 서서 그
    간선이 사라지거나 제자리로 돌아가 귀속을 잃는다."""
    for e in index_mod.current().cross_refs()[0]:
        if (e.get("via") == "규칙"
                and (e["src_doc"], e["src"], e.get("dst_doc"), e["dst"])
                == (src_doc, src, dst_doc, dst)):
            return e
    return None


@router.post("/verdicts/resolve", summary="지문 처리 — 승인은 간선 억제 규칙이 된다")
def rag_verdicts_resolve(body: EdgeResolve):
    if body.action not in ("승인", "기각"):
        raise HTTPException(400, "action 은 '승인' 또는 '기각'이어야 합니다")
    # 반증 배선 — 끊는 간선이 규칙의 산출이면 그 규칙의 반례로 원장에 남긴다.
    # 사람은 원장을 모른 채 화면에서 끊었을 뿐이고, 나르는 것은 시스템 몫이다.
    re = _rule_edge(body.src_doc, body.src, body.dst_doc, body.dst) \
        if body.action == "승인" else None
    out = verdicts_mod.resolve(body.model_dump(), body.action, body.note)
    if re is not None:
        from lawrag.core.rag import rules as rules_mod
        rules_mod.log_overturn_auto(
            re.get("rule", ""), {**re, "dst": re.get("규칙_전", re["dst"])},
            "규칙 착지에 오참조 승인 — 사람의 끊기")
    return out


class MissResolve(BaseModel):
    """회수 결함(참조무관·검색무관) 처리 — 백로그 카드가 그대로 보낸다.

    간선 억제는 여기 없다. 좌표가 맞는데 이번 질문에 안 맞았을 뿐이라 지우면
    옳은 참조를 잃는다 — 대신 후순위(연결 유지·자리 경쟁에서 뒤로)와
    진입제외(벡터·용어 진입에서만 제외)다.
    """
    판정: str = ""
    구역: Optional[dict] = None
    간선: Optional[dict] = None
    action: str                        # "후순위" | "진입제외" | "정상"
    note: str = ""


@router.post("/verdicts/miss", summary="회수 결함 처리 — 후순위 · 진입제외 · 정상")
def rag_verdicts_miss(body: MissResolve):
    try:
        return verdicts_mod.resolve_miss(
            {"판정": body.판정, "구역": body.구역, "간선": body.간선},
            body.action, body.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


class StructResolve(BaseModel):
    """구조화오류 처리 — 계층은 검수 화면에서 고치고, 여기서는 닫는다."""
    구역: dict
    action: str                        # "고침" | "무시"
    note: str = ""


@router.post("/verdicts/struct", summary="구조화오류 처리 — 고침 · 무시")
def rag_verdicts_struct(body: StructResolve):
    try:
        return verdicts_mod.resolve_struct(body.구역, body.action, body.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


class VerdictEdit(BaseModel):
    """LLM 판단(지문·교정) 수정 — "오참조라 했는데 실제로는 맞는 연결"을 사람이
    바로잡는다. after 는 고칠 필드만 담은 JSON 하나다(허용: 판정·사유·간선·
    새_dst·새_dst_path). 원본은 지워지지 않고 수정 이력이 겹쳐 읽힌다."""
    qid: str
    target: str                      # "지문" | "교정"
    idx: int                         # 그 qid 안에서의 순번 (화면이 아는 값)
    after: dict
    note: str = ""


@router.post("/verdicts/edit", summary="LLM 판단 수정 — 이력이 남고 수정본이 화면의 판단이 된다")
def rag_verdicts_edit(body: VerdictEdit):
    try:
        return verdicts_mod.edit(body.qid, body.target, body.idx,
                                 body.after, body.note)
    except ValueError as e:
        raise HTTPException(400, str(e))


class FixResolve(BaseModel):
    """교정 백로그 처리 — "제2조가 아니라 제2조 제3항" 제안의 승인/기각.
    승인이면 간선의 도착이 새 좌표로 옮겨 앉는다(edge_rules.json redirect)."""
    src_doc: str
    src: int
    dst_doc: str
    dst: int
    new_dst: int
    src_path: str = ""
    dst_path: str = ""
    new_dst_path: str = ""
    surface: str = ""
    action: str                      # "승인" | "기각"
    note: str = ""


@router.post("/fixes/resolve", summary="교정 처리 — 승인은 간선 재지정 규칙이 된다")
def rag_fixes_resolve(body: FixResolve):
    if body.action not in ("승인", "기각"):
        raise HTTPException(400, "action 은 '승인' 또는 '기각'이어야 합니다")
    payload = body.model_dump()
    if body.action == "승인":
        idx = index_mod.current()
        dv = idx.docs.get(body.dst_doc)
        if dv is None or dv.by_id.get(body.new_dst) is None:
            raise HTTPException(400, "새 좌표가 유효하지 않습니다 — 문서나 구역이 없습니다")
        # 반증 배선 + 출처 — 고치는 간선이 규칙의 산출이면 (1) 그 규칙의
        # 반례로 원장에 남기고 (2) 새 사례 행에 출처를 새겨 귀납이 표본에서
        # 빼게 한다(자기확증 방지).
        re = _rule_edge(body.src_doc, body.src, body.dst_doc, body.dst)
        if re is not None:
            payload["출처"] = {"rule": re.get("rule", "")}
            from lawrag.core.rag import rules as rules_mod
            rules_mod.log_overturn_auto(
                re.get("rule", ""), {**re, "dst": re.get("규칙_전", re["dst"])},
                "규칙 착지를 사람이 재교정")
    return verdicts_mod.resolve_fix(payload, body.action, body.note)


@router.get("/debug", summary="디버깅 합본 — 질의 로그 + 판정·교정 + 품질 통계")
def rag_debug(limit: int = Query(50, ge=1, le=500)):
    """디버깅 화면(/rag/debug.html) 한 장이 부르는 단일 응답.

    질의 튜플에 그 질의가 남긴 판정 지문·착지 교정을 qid 로 붙이고, 백로그
    (억제 대기·교정 대기)와 품질 통계를 함께 싣는다 — "무엇을 물었고, 시스템이
    무엇을 봤고, LLM 이 무엇을 고쳤고, 사람이 어떻게 판정했나"가 한 화면이다."""
    rows = tuples_mod.read(limit=limit)
    marks = verdicts_mod.by_qid()
    for r in rows:
        m = marks.get(r.get("qid"))
        if m:
            r["지문"] = m["지문"]
            r["교정"] = m["교정"]
    bl = verdicts_mod.backlog()
    fb = [r for r in rows if r.get("피드백")]
    good = sum(1 for r in fb if (r["피드백"] or {}).get("판정") == "정답")
    stats = {
        "질의": len(rows),
        "answerable": sum(1 for r in rows if r.get("answerable")),
        "피드백": len(fb), "정답": good, "오답": len(fb) - good,
        "지문": sum(len(r.get("지문") or []) for r in rows),
        "교정": sum(len(r.get("교정") or []) for r in rows),
        "억제_대기": len(bl.get("edges") or []),
        "교정_대기": len(bl.get("fixes") or []),
        "억제_규칙": bl.get("suppressed", 0),
        "재지정_규칙": bl.get("redirected", 0),
        "승격_후보": len(tuples_mod.candidates()),
    }
    return {"stats": stats, "tuples": rows, "backlog": bl}


@router.get("/nodes", summary="문서의 구역 목록 — 좌표 선택용 (가벼운 형태)")
def rag_nodes(doc_id: str = Query(...)):
    """피드백 화면이 기대 구역을 고를 때 쓴다. 검수 payload(result.json)는
    블록·이미지까지 실려 무겁다 — 여기는 (id, 경로, 쪽)만 준다."""
    idx = index_mod.current()
    v = idx.docs.get(doc_id)
    if v is None:
        raise HTTPException(404, f"문서가 없습니다: {doc_id}")
    return {"doc_id": doc_id, "doc": v.name,
            "nodes": [{"node": n.get("id"), "path": v.path(n.get("id")),
                       "page": n.get("page"), "level": n.get("level")}
                      for n in v.nodes]}


# ---------------------------------------------------------------- 일반 규칙(귀납층)
# RULE_LOOP.md 의 API 면. 발동·상태는 core.rag.rules 가 정하고, 여기는
# 화면(백로그·적중 원장·스위치)의 문이다.

@router.get("/rules", summary="일반 규칙 — 목록 · 실적 · 유효 모드")
def rag_rules():
    from lawrag.core.rag import rules as rules_mod

    st = rules_mod.stats()
    rows = []
    for r in rules_mod.load():
        rows.append({**r, "실적": st.get(r["id"], {}),
                     "보고서": rules_mod.promotable(r["id"])})
    return {"mode": rules_mod.mode(),
            "env": os.environ.get("RAG_RULES_MODE", "off"),
            "breaker": rules_mod.breaker(), "rules": rows,
            "중첩": rules_mod.overlaps()}


class RuleResolve(BaseModel):
    """상태 전이 — 사람 경로. 잠정→규칙 승인, 규칙→정착 승격, 강등·보류.
    방향 전환(→정착, 정착→)은 이 문으로만 온다 — by 는 항상 '사람'이다."""
    id: str
    status: str                        # "규칙" | "정착" | "보류" | "강등"
    note: str = ""


@router.post("/rules/resolve", summary="규칙 상태 전이 — 정착 승격/강등은 사람만")
def rag_rules_resolve(body: RuleResolve):
    from lawrag.core.rag import rules as rules_mod

    try:
        return rules_mod.set_status(body.id, body.status, by="사람",
                                    note=body.note)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/rules/hits", summary="적중 원장 — 규칙이 증거를 심판한 사건들")
def rag_rules_hits(rule: str = Query("", description="규칙 id 로 거름 (빈값=전부)"),
                   limit: int = Query(200, ge=1, le=2000)):
    from lawrag.core.rag import rules as rules_mod

    led = [r for r in rules_mod._ledger()
           if not rule or r.get("rule") == rule]
    # 부검 상태를 겹쳐 읽는다 — 원장은 append-only 라 적중 행을 다시 쓰지 않는다
    judged: dict[str, str] = {}
    for r in led:
        if r.get("kind") in ("확정", "뒤집힘"):
            judged[json.dumps([r.get("rule"), r.get("대상")],
                              sort_keys=True)] = r["kind"]
    hits = []
    for r in led:
        if r.get("kind") != "적중":
            continue
        k = json.dumps([r.get("rule"), r.get("대상")], sort_keys=True)
        hits.append({**r, "status": judged.get(k, "미검")})
    # 사람이 읽는 좌표 — 원장은 좌표만 적는다(append-only 최소주의). 화면이
    # "어디를 어디로 옮겼나"를 문장으로 보여줘야 부검이 성립한다.
    idx = index_mod.current()

    def _label(t: dict, new_dst) -> dict:
        sv, dv = idx.docs.get(t.get("src_doc")), idx.docs.get(t.get("dst_doc"))
        return {"src": sv.name if sv else (t.get("src_doc") or "?"),
                "src_path": sv.path(t.get("src")) if sv else "",
                "dst": dv.name if dv else (t.get("dst_doc") or "?"),
                "dst_path": dv.path(t.get("dst")) if dv else "",
                "new_path": dv.path(new_dst)
                if dv and new_dst is not None else ""}
    out = hits[-limit:]
    for h in out:
        h["표지"] = _label(h.get("대상") or {},
                           (h.get("행동") or {}).get("redirect_to"))
    # 생애 이벤트 — 등재·상태변경·부검이 타임라인의 재료다.
    events = [r for r in led
              if r.get("kind") in ("등재", "상태변경", "확정", "뒤집힘")
              and (not rule or r.get("rule") == rule)]
    return {"hits": out, "count": len(hits), "events": events[-100:]}


class HitResolve(BaseModel):
    """적중 부검 — 확정(규칙이 옳았다) | 뒤집힘(데이터가 옳았다 = 반례).
    뒤집힘이 쌓이면 차단기가 on→shadow 로 강하한다."""
    rule: str
    대상: dict
    action: str                        # "확정" | "뒤집힘"
    note: str = ""


@router.post("/rules/hits/resolve", summary="적중 부검 — 뒤집힘은 규칙의 반례가 된다")
def rag_rules_hits_resolve(body: HitResolve):
    from lawrag.core.rag import rules as rules_mod

    try:
        return rules_mod.resolve_hit(body.rule, body.대상, body.action,
                                     body.note)
    except ValueError as e:
        raise HTTPException(400, str(e))


class BreakerAction(BaseModel):
    action: str                        # "해제"
    note: str = ""


@router.post("/rules/breaker", summary="차단기 해제 — shadow→on 복귀는 사람만")
def rag_rules_breaker(body: BreakerAction):
    from lawrag.core.rag import rules as rules_mod

    if body.action != "해제":
        raise HTTPException(400, "action 은 '해제'만 있습니다 — 강하는 자동이다")
    return rules_mod.reset_breaker(body.note)


@router.post("/rules/induce", summary="귀납 한 바퀴 — 승인 사례를 일반 규칙 후보로")
def rag_rules_induce():
    """군집화 → 일반화(기계 우선, 잔여는 LLM) → replay 검증 → 잠정 등재.
    발동은 없다 — 등재까지다. 크론이 아니라 화면 버튼으로도 돌 수 있게 둔다."""
    from lawrag.core.rag import induce as induce_mod

    if os.environ.get("RAG_RULES_INDUCE", "on").strip().lower() == "off":
        raise HTTPException(409, "RAG_RULES_INDUCE=off — 유도가 꺼져 있습니다")
    return {"report": induce_mod.run(index_mod.current(), _llm())}
