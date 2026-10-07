"""RAG API — 구조화된 문서에 묻는다.

    GET  /v1/rag/search?q=…     검색만 — 결정론, LLM 없음. 저작·검수 화면용.
    POST /v1/rag/ask            LegalClosure → 답변 합성 (LLM)

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

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from lawrag.core import llm as llm_mod
from lawrag.core import logbook
from lawrag.core.rag import answer as answer_mod
from lawrag.core.rag import audit as audit_mod
from lawrag.core.rag import companion_recovery
from lawrag.core.rag import index as index_mod
from lawrag.core.rag import judge as judge_mod
from lawrag.core.rag import legal_coordinates
from lawrag.core.rag import promote as promote_mod
from lawrag.core.rag import recover as recover_mod
from lawrag.core.rag import scopes as scopes_mod
from lawrag.core.rag import switches as switches_mod
from lawrag.core.rag import tuples as tuples_mod
from lawrag.core.rag import wikictx
from lawrag.core.rag import wikiledger
from lawrag.core.rag import verdicts as verdicts_mod
from lawrag.runtime.content_snapshot import (
    current_content_snapshot,
    current_retrieval_runtime_receipt,
)
from lawrag.core.rag.controls import value as control_value
from lawrag.feedback import lifecycle as feedback_lifecycle
# `core.rag.search` 모듈이 아니라 함수를 바로 받는다 — 패키지 facade 가
# 같은 이름(search)으로 함수를 내보내서, 모듈 경유 접근은 헷갈린다.
from lawrag.core.rag.search import search as run_search

router = APIRouter(prefix="/v1/rag", tags=["rag"])

log = logging.getLogger("lawrag.api.rag")

LEGALCLOSURE_MODE = "legalclosure"
_ASK_MODE_ALIASES = {
    "legalclosure": LEGALCLOSURE_MODE,
    "legal-closure": LEGALCLOSURE_MODE,
    # 예전 클라이언트의 vector/auto 값은 깨지지 않게 받되, 응답에는 보관
    # 경로임을 명시한다. 새 호출은 legacy-* 이름으로 의도를 드러낸다.
    "vector": "legacy-vector",
    "legacy-vector": "legacy-vector",
    "legacy_vector": "legacy-vector",
    "auto": "legacy-auto",
    "legacy-auto": "legacy-auto",
    "legacy_auto": "legacy-auto",
}


def _resolve_ask_mode(value: str) -> tuple[str, str, bool]:
    """(요청값, 실제 경로, 운영 스위치 롤백 여부)."""
    requested = str(value or LEGALCLOSURE_MODE).strip().lower()
    effective = _ASK_MODE_ALIASES.get(requested)
    if effective is None:
        raise HTTPException(
            400, "mode는 legalclosure | legacy-vector | legacy-auto 중 하나여야 합니다")
    rolled_back = False
    if effective == LEGALCLOSURE_MODE and not switches_mod.is_on("legalclosure_main"):
        effective, rolled_back = "legacy-vector", True
    return requested, effective, rolled_back


def _ask_event(out: dict, dur_ms: int) -> None:
    """질의 한 건의 관측 — /logs/ 화면이 그리는 그대로. 응답에서 뽑아 적는다:
    응답이 곧 사용자가 본 것이라, 따로 모으면 화면과 로그가 갈린다."""
    snapshot_event = {}
    if out.get("content_snapshot") is not None:
        snapshot_event["content_snapshot"] = out["content_snapshot"]
    if out.get("retrieval_runtime") is not None:
        snapshot_event["retrieval_runtime"] = out["retrieval_runtime"]
    logbook.rag_event(
        "ask",
        q=out.get("question", ""), qid=out.get("qid"),
        mode=out.get("mode", ""), dur_ms=dur_ms,
        retriever=out.get("retriever"),
        answerable=out.get("answerable"),
        n_context=len(out.get("context") or []),
        n_refs=len(out.get("refs") or []),
        n_discards=len(out.get("discards") or []),
        ladder=out.get("ladder") or [],
        filter=out.get("filter"),
        recovery=(out.get("recovery") or {}).get("rungs_fired"),
        usage=out.get("usage"),
        legal_graph={
            key: ((out.get("legalclosure") or {}).get("legal_graph") or {}).get(key)
            for key in ("enabled", "status", "generation_id", "added_count",
                        "considered_count", "reason_counts", "fallback")
        },
        answer=(out.get("answer") or "")[:400],
        refs=[{"doc": r.get("doc"), "path": r.get("path"), "page": r.get("page")}
              for r in (out.get("refs") or [])[:10]],
        error=out.get("error"), **snapshot_event)


def _content_snapshot_receipt(idx=None) -> dict | None:
    snapshot = getattr(idx, "content_snapshot", None)
    if snapshot is None:
        snapshot = current_content_snapshot()
    return None if snapshot is None else snapshot.compact_receipt()


def _attach_content_snapshot(out: dict, idx=None) -> dict:
    """Add release identity only in the enabled snapshot path.

    Omitting the key in legacy mode is deliberate: OFF responses retain their
    historical JSON shape instead of gaining a null field.
    """

    receipt = _content_snapshot_receipt(idx)
    if switches_mod.is_on("sourceset_content_snapshot") and receipt is None:
        raise RuntimeError(
            "SourceSet content snapshot is enabled but no snapshot is bound"
        )
    if receipt is not None:
        out["content_snapshot"] = receipt
    if switches_mod.is_on("sourceset_content_snapshot"):
        runtime_receipt = current_retrieval_runtime_receipt(required=True)
        if runtime_receipt is None:  # narrowed by required=True
            raise RuntimeError(
                "SourceSet content snapshot is enabled but no retrieval runtime is bound"
            )
        out["retrieval_runtime"] = runtime_receipt
    return out


def _content_provenance(value) -> dict | None:
    provenance = getattr(value, "content_provenance", None)
    if provenance is None:
        return None
    return provenance.receipt() if hasattr(provenance, "receipt") else dict(provenance)


def _required_content_provenance(value, *, label: str) -> dict | None:
    """Require document evidence in the enabled SourceSet serving path."""

    provenance = _content_provenance(value)
    if switches_mod.is_on("sourceset_content_snapshot") and provenance is None:
        raise RuntimeError(f"SourceSet content provenance is missing: {label}")
    return provenance


def _snapshot_bound_candidate_coords(out: dict, coords: list[dict]) -> list[dict]:
    """Bind candidate landings to proof already present in this exact answer.

    Legacy mode returns the original list object unchanged.  Snapshot mode
    does not manufacture provenance from a bare document ID: a coordinate is
    recordable only when the response context/ref boundary already carried the
    current structure-artifact receipt for that same coordinate.
    """

    if not switches_mod.is_on("sourceset_content_snapshot"):
        return coords
    receipt = out.get("content_snapshot")
    if not isinstance(receipt, dict):
        return []
    proofs: dict[tuple, dict] = {}
    conflicted: set[tuple] = set()
    for row in [*(out.get("context") or []), *(out.get("refs") or [])]:
        if not isinstance(row, dict):
            continue
        key = (row.get("doc_id"), row.get("node"))
        proof = row.get("content_provenance")
        if not isinstance(key[0], str) or key[1] is None or not isinstance(proof, dict):
            continue
        prior = proofs.get(key)
        if prior is not None and prior != proof:
            conflicted.add(key)
            continue
        proofs[key] = proof
    bound: list[dict] = []
    for row in coords:
        if not isinstance(row, dict):
            continue
        key = (row.get("doc_id"), row.get("node"))
        proof = proofs.get(key)
        if proof is None or key in conflicted:
            continue
        supplied_snapshot = row.get("content_snapshot")
        supplied_provenance = row.get("content_provenance")
        if supplied_snapshot is not None and supplied_snapshot != receipt:
            continue
        if supplied_provenance is not None and supplied_provenance != proof:
            continue
        bound.append({
            **row,
            "content_snapshot": dict(receipt),
            "content_provenance": dict(proof),
        })
    return bound


def _hit_row(h) -> dict:
    row = {"kind": h.kind, "value": h.value, "score": h.score,
           "match": h.match, "reasons": h.reasons,
           "doc_id": h.doc_id, "doc": h.doc, "node": h.node, "block": h.block,
           "occurrences": len(h.occurrences) if h.occurrences else 0}
    provenance = _required_content_provenance(h, label=f"search-hit:{h.doc_id}")
    if provenance is not None:
        row["content_provenance"] = provenance
    return row


@router.get("/search", summary="검색만 — LLM 없음 (mode=vector: 벡터 우선 회수)")
def rag_search(q: str = Query(..., description="질의"),
               mode: str = Query("auto", description="auto | vector"),
               scope: str = Query("", description="스코프 이름 (scopes.yml · 외규/내규/서식)")):
    t0 = time.perf_counter()
    idx = index_mod.current()
    try:
        idx, scope_info = scopes_mod.apply(idx, scope, None)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    n_docs = len(idx.scope) if idx.scope is not None else len(idx.docs)
    if mode == "vector":
        from lawrag.core.rag import vecfirst

        sections, vmeta = vecfirst.retrieve(idx, q)
        sections, smeta = answer_mod.enforce_scope(idx, sections)
        logbook.rag_event("search", q=q, mode="벡터우선",
                          n_hits=len(sections), dur_ms=logbook.ms(t0),
                          vector_hits=vmeta.get("vector_hits"),
                          depth=vmeta.get("depth"))
        return _attach_content_snapshot({
            "query": q, "mode": "벡터우선",
            "refs": vecfirst.static_refs(sections), **vmeta,
            "scope": _scope_out(idx, smeta), "documents": n_docs,
        }, idx)
    res = run_search(idx, q)
    logbook.rag_event("search", q=q, mode=res.mode, n_hits=len(res.hits),
                      ladder=res.ladder, dur_ms=logbook.ms(t0))
    return _attach_content_snapshot({
        "query": res.query, "mode": res.mode, "ladder": res.ladder,
        "hits": [_hit_row(h) for h in res.hits],
        "scope": _scope_out(idx, {"dropped": [], "out": 0}),
        "documents": n_docs, "entries": len(idx.entries),
    }, idx)


class Ask(BaseModel):
    question: str
    # 필터를 끌 수 있다 — 회수가 왜 이런지 볼 때는 거르지 않은 원본이 필요하다.
    filter: bool = True
    # 회복 루프(의미해석→깔때기→원문→수색대→둘러보기)를 끌 수 있다.
    recover: bool = True
    # "legalclosure"가 운영 기본. 이전 vector/auto는 삭제하지 않고
    # "legacy-vector"/"legacy-auto" 롤백 모드로 보관한다. 옛 이름도 호환된다.
    mode: str = LEGALCLOSURE_MODE
    # 질의 스코프 — "이 문서들만 대상으로". scope 는 scopes.yml 의 이름(또는
    # 내장 외규·내규·서식), documents 는 즉석 파일명 목록. 합집합. 진입은 이
    # 안에서만, 동반(배제·위임·준용…)은 밖으로 나가되 표식이 붙는다
    # (lawrag/core/rag/scopes.py 머리). 둘 다 비면 기본 스코프(구판 제외).
    scope: str = ""
    documents: Optional[list[str]] = None


def _llm():
    """키가 없으면 None — 호출부가 검색까지만 내려간다."""
    if not llm_mod.available():
        return None
    return llm_mod.LLM()


def _legalclosure_assertion_llm(primary):
    """Assertion 닫힌 메뉴는 허용된 product-role Haiku만 사용한다."""
    if primary is None:
        return None
    configured = os.environ.get("RAG_LEGALCLOSURE_ASSERTION_MODEL", "").strip()
    if not configured and getattr(primary, "backend", "") == "anthropic":
        configured = "claude-haiku-4-5-20251001"
    if not configured or configured == getattr(primary, "model", ""):
        return primary
    return llm_mod.LLM(model=configured)


@router.get("/links/summary", summary="참조 수만 — 상단바 배지·홈 현황용")
def rag_links_summary():
    """/links 는 기하·원문 문맥까지 실어 수 MB 다. 배지와 현황 칩은 수만
    필요하므로 여기서 끝낸다 — 홈이 11.8MB 를 받아 length 만 세던 것을 끊는다."""
    idx = index_mod.current()
    edges, pending = idx.cross_refs()
    return _attach_content_snapshot({
        "docs": len(idx.docs),
        "cross": len(edges),
        "pending": len(pending),
        "in_doc": sum(len(es or []) for es in idx.ref_edges().values()),
    }, idx)


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
        row = {**e,
                "src_doc_name": sv.name if sv else e.get("src_doc", ""),
                "dst_doc_name": dv.name if dv else e.get("dst_doc", ""),
                "src_path": sv.path(e.get("src")) if sv else "",
                "dst_path": dv.path(e.get("dst")) if dv else "",
                "src_geo": block_geo(sv, e.get("block")),
                "dst_geo": node_geo(dv, e.get("dst"))}
        if sv is not None:
            proof = _required_content_provenance(
                sv, label=f"relation-source:{e.get('src_doc')}"
            )
            if proof is not None:
                row["src_content_provenance"] = proof
        if dv is not None:
            proof = _required_content_provenance(
                dv, label=f"relation-target:{e.get('dst_doc')}"
            )
            if proof is not None:
                row["dst_content_provenance"] = proof
        return row

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

    docs = []
    for doc_id, view in idx.docs.items():
        row = {
            "doc_id": doc_id,
            "doc": view.name,
            "pages": n_pages(view),
            "n_in": len(idx.ref_edges().get(doc_id) or []),
        }
        proof = _required_content_provenance(
            view, label=f"links-document:{doc_id}"
        )
        if proof is not None:
            row["content_provenance"] = proof
        docs.append(row)
    return _attach_content_snapshot({
        "docs": docs,
        "in_doc": in_doc,
        "cross": [_cross_row(e) for e in edges],
        "pending": pend,
    }, idx)


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

    provenance = _required_content_provenance(v, label=f"section:{doc_id}:{node}")
    out = {"doc_id": doc_id, "node": node, "doc": v.name, "path": v.path(node),
            "page": n.get("page"), "geo": geo(v, node),
            "pages": max([b.get("page") or 1 for b in v.blocks] or [1]),
            "text": v.section_text(n, cap=SECTION_CHARS),
            # 구조화 본문 — 항(①)·호(1.)가 마디로 서 있으면 들여쓰기로 계층이
            # 보인다. 본문을 보여주는 화면은 이것을 기본으로 쓴다(text 는 호환용).
            "outline": outline,
            "terms": terms,
            "children": children,
            "refs": refs, "cited_by": cited}
    if provenance is not None:
        out["content_provenance"] = provenance
    return _attach_content_snapshot(out, idx)


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
def rag_links_settle(src_doc: Optional[list[str]] = Query(
        None, description="출발 문서 doc_id — 주면 그 문서들의 보류만 판정 (반복 가능)")):
    """컴파일 국면의 걸음이다 — 한 번 판정해 links.json 에 고정하고, 질의마다
    재판단하지 않는다. fail-closed: 저신뢰 판정은 보류로 남는다.
    src_doc 을 주면 새로 넣은 문서 몇 건의 참조만 굳힐 수 있다 — 전체 보류
    수천 건을 매번 다시 판정하는 비용을 피한다."""
    idx = index_mod.current()
    llm = _llm()
    if llm is None:
        raise HTTPException(503, f"LLM 없음 — {llm_mod.MISSING_HINT} 를 설정해야 판정이 돕니다")
    scope = set(src_doc) if src_doc else None
    links, meta = judge_mod.settle_cross(llm, idx, src_docs=scope)
    if scope:
        meta["src_docs"] = sorted(scope)
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
    from lawrag.platform import main_promotion
    from lawrag.core.rag import switches as switches_mod
    return {
        "switches": switches_mod.snapshot(),
        "main_pipeline": main_promotion.runtime_provenance(),
    }


class SwitchSet(BaseModel):
    key: str
    on: bool


@router.post("/switches", summary="엔진 규칙 켜고 끄기 — 다음 질의부터 반영")
def rag_switches_set(body: SwitchSet):
    """규칙은 코드가 갖고 있지만 켜짐/꺼짐은 사용자 소유다. 끄면 확정 규칙의
    간선은 보류로 내려가고, 동반 규칙은 회수에서 빠진다. 저장된 판정
    (links.json·정정·억제)은 스위치와 무관하다."""
    from lawrag.platform import main_promotion
    from lawrag.core.rag import switches as switches_mod
    try:
        switches_mod.set_switch(body.key, body.on)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "switches": switches_mod.snapshot(),
        "main_pipeline": main_promotion.runtime_provenance(),
    }


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


def _ctx_row(idx, s) -> dict:
    """응답 context 한 행 — 두 경로(auto·벡터)가 같은 모양을 내야 검수 화면이
    한 벌로 선다. 부칙 종류·성격 태그·시행일은 전부 **관측**이다 — 회수·순위에
    관여하지 않는다(태그층 규율: 이름표만 붙인다, lawrag/core/rag/tags.py 머리)."""
    from lawrag.core.rag import tags as tags_mod

    row = {"n": s.n, "doc": s.doc, "doc_id": s.doc_id,
           "node": s.node, "path": s.path,
           "page": s.page, "kind": s.kind, "matched": s.matched}
    if getattr(s, "legal_meta", None):
        row["법률검증"] = s.legal_meta
    provenance = _content_provenance(s)
    if provenance is None:
        view = idx.docs.get(s.doc_id)
        provenance = _content_provenance(view) if view is not None else None
    if switches_mod.is_on("sourceset_content_snapshot") and provenance is None:
        raise RuntimeError(
            f"SourceSet content provenance is missing: section:{s.doc_id}:{s.node}"
        )
    if provenance is not None:
        row["content_provenance"] = provenance
    add = _addendum(idx, s)
    if add:
        row["부칙"] = add
    if getattr(s, "scope_out", False):
        row["scope_out"] = True            # 질의 범위 밖 — 간선으로 동반된 구역
    v = idx.docs.get(s.doc_id)
    if v is not None:
        marks = tags_mod.node_marks(v, s.node)
        if marks:
            row["성격"] = marks
        if v.enforce:
            row["시행일"] = v.enforce
        # 내규·외규·서식 — 답변 화면이 "이건 사내 규정, 저건 법령" 을 가를 표식.
        # 내규는 판(status)·문서군(series)도 함께 — 신구 대비의 좌표다.
        row["문서군"] = v.scope_kind
        if v.scope_kind == "내규":
            row["판"] = v.status or "현행"
            if v.series:
                row["series"] = v.series
    return row


def _scope_rung(idx, smeta: dict) -> dict:
    """사다리 한 칸 — 스코프가 무엇을 막고 무엇을 밖에서 데려왔나."""
    n_drop = len(smeta.get("dropped") or [])
    n_out = smeta.get("out", 0)
    note = f"'{idx.scope_name or '기본'}' 문서 {len(idx.scope)} — 진입은 이 안에서만"
    if n_drop:
        note += f" · 밖 진입 {n_drop} 버림"
    if n_out:
        note += f" · 밖 동반 {n_out} (표식)"
    return {"stage": "스코프", "count": len(idx.scope), "note": note}


def _scope_out(idx, smeta: dict) -> Optional[dict]:
    """응답의 scope 칸 — 화면이 "어느 문서들만 봤나·무엇이 밖에서 왔나" 를 보인다.
    스코프가 없으면 None(키는 둔다 — 화면이 분기하기 쉽게)."""
    if idx.scope is None:
        return None
    return {"name": idx.scope_name or "기본",
            "documents": sorted(idx.docs[d].name for d in idx.scope
                                if d in idx.docs),
            "count": len(idx.scope),
            "dropped": smeta.get("dropped") or [],
            "out_of_scope": smeta.get("out", 0)}


def _memory_note(mem: list) -> str:
    """질문 기억 사다리 note — 왜 열렸나(같은 질문/비슷한 질문)."""
    return " · ".join((m.get("why") or "승인 연결") for m in mem[:4])


def _spot_note(spots: list, expanded: bool) -> str:
    """사다리 note — 어느 판정기가 골랐는지(트리거/LLM)를 제목 앞에 박는다."""
    via = (spots[0].get("via") or "트리거") if spots else "트리거"
    head = "LLM(검색 전) — " if via.startswith("llm") else "트리거 — "
    return (head + " · ".join(s["title"] for s in spots)
            + (" · 조문질의로 확장" if expanded else ""))


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


RESPOT_MAX = int(control_value("api.respot_sections_max"))


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


def _after_answer(out: dict, q: str, llm, sections: list, ans, fixes: list,
                  cand_coords: Optional[list] = None) -> None:
    """답을 만든 **뒤**의 기록 — 두 질의 경로(auto·벡터)가 같은 순서로 같은
    원장에 적는다. 여기가 피드백 루프의 트리거 자리다:

        진단 튜플(qid)  → /feedback 이 정답·오답을 붙일 자리
        사후 감사 큐    → 판정 지문 → 백로그(verdicts.jsonl)
        위키 적중 원장  → 부검(피드백)이 붙을 자리
        착지 교정 로그  → 교정 백로그
        용어 실적       → 인용된 용어 진입은 hits (misses 는 감사가 적는다)
        승격 후보       → candidates.json (사람 승인 뒤에야 질문 기억이 된다)

    기록 실패로 질의응답이 죽으면 안 된다 — 전부 fail-open. out["qid"] 를 채운다."""
    try:
        out["qid"] = tuples_mod.log_ask(out, prompt=_answer_prompt(llm),
                                       calls=_calls(llm))
        # 사후 감사 — 응답을 만든 뒤 큐에 넣는다(여기서 기다리지 않는다).
        audit_mod.submit(llm, out["qid"], q, ans.answer, sections,
                         {r.get("n") for r in ans.refs})
        if ans.wiki:
            # 위키 적중 원장 — 어떤 아티클이 끼었나. 피드백이 오면 부검이 붙는다.
            wikiledger.record(out["qid"], q, [w["slug"] for w in ans.wiki],
                              ans.answerable)
        if fixes:
            verdicts_mod.log_fixes(out["qid"], q, fixes)
        # 용어 진입의 실적 — 인용되면 hits. misses(검색무관)는 사후 감사가
        # 백로그에 적을 때 함께 센다(audit._run_one). 중립은 세지 않는다.
        cited_n = {r.get("n") for r in ans.refs}
        hit_keys = [s.term_key for s in sections
                    if s.term_key and s.n in cited_n]
        if hit_keys:
            verdicts_mod.score_terms(hit_keys, [])
        if cand_coords and ans.answerable:
            tuples_mod.record_candidates(
                q, _snapshot_bound_candidate_coords(out, cand_coords)
            )
    except Exception:                                    # pragma: no cover
        log.exception("진단 튜플 적재 실패 — 질의응답은 그대로 낸다")


def _ask_vector(idx, q: str, llm, spots: Optional[list] = None,
                qx: Optional[str] = None,
                spots_trig: Optional[list] = None,
                qv: str = "", memory: Optional[list] = None) -> Optional[dict]:
    """벡터 우선 모드 — 진입은 벡터, 연결은 참조 닫힘, 출처는 정적.
    LLM 은 답변 문장 합성에만 쓰인다. 필터도 없다 — 회수가 곧 출처다.
    벡터가 빈손이면 None — 호출부가 용어 사다리로 폴백한다.
    spots·qx 는 검색 전 쟁점 분해의 산물 — 회수는 확장 질의(qx)로,
    합성·기록은 원 질의(q)로 간다. memory 는 질문 기억(승인 좌표) — 진입 앞에 앉는다."""
    from lawrag.core.rag import vecfirst

    spots = spots or []
    sections, vmeta = vecfirst.retrieve(idx, qx or q, llm=llm, vec_query=qv,
                                        seeds=memory, raw_query=q)
    # 스코프 보루 — 진입이 밖으로 샜으면 버리고, 동반은 표식을 붙인다.
    sections, smeta = answer_mod.enforce_scope(idx, sections)
    if not sections:
        return None
    n_kw = len(vmeta.get("keywords", []))
    n_entry = len(vmeta["entries"])
    n_mem = len(vmeta.get("memory") or [])
    n_frame = len(vmeta.get("frame_hits") or [])
    n_concept = len(vmeta.get("concept_hits") or [])
    n_combo = len(vmeta.get("combination_hits") or [])
    n_dc = len(vmeta.get("doc_companion") or [])
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
         "count": len(sections) - n_entry - n_kw - n_mem - n_frame - n_concept
                  - n_combo - n_dc
                  - len(vmeta.get("floor") or []),
         "note": f"참조 간선 닫힘, 깊이 {vmeta['depth']}"},
    ]
    if n_dc:
        srcs = sorted({idx.docs[d["src"]].name[:18] for d in vmeta["doc_companion"]
                       if d["src"] in idx.docs})
        ladder.insert(2, {"stage": "문서 동반", "count": n_dc,
                          "note": "밖 인용 전부 — " + " · ".join(srcs)})
    if n_frame:
        fq = vmeta.get("frame_query") or []
        ladder.insert(1, {"stage": "프레임 진입", "count": n_frame,
                          "note": "행위 어휘 대조 — " + " · ".join(
                              (f.get("act") or f.get("object") or "?") for f in fq)})
    if n_concept:
        alignment = (vmeta.get("concept") or {}).get("alignment") or {}
        labels = [c.get("label", "") for c in alignment.get("selected") or []]
        ladder.insert(0, {"stage": "1급 Concept", "count": n_concept,
                          "note": "OQL 고정 패턴 — " + " · ".join(labels)})
    if n_combo:
        combo = vmeta.get("combination") or {}
        general = combo.get("general_search") or {}
        ccounts = combo.get("combination_counts") or {}
        ladder.insert(0, {
            "stage": "좌표 후보 조합", "count": n_combo,
            "note": (f"0 교집합 {ccounts.get('zero_intersections', 0)} 제거 · "
                     f"생존 {ccounts.get('surviving', 0)} · "
                     f"LLM 메뉴 {combo.get('option_count', 0)}"
                     + (" · 일반검색 " + " · ".join(general.get("keywords") or [])
                        if general.get("keywords") else "")),
        })
    if n_mem:
        ladder.insert(1 if (n_concept or n_combo) else 0,
                      {"stage": "질문 기억", "count": n_mem,
                          "note": _memory_note(vmeta["memory"])})
    floor = vmeta.get("floor") or []
    if floor:
        kinds = {}
        for f in floor:
            kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
        ladder.insert(2, {"stage": "필수 동반", "count": len(floor),
                          "note": " · ".join(f"{k} {c}" for k, c in kinds.items())
                                  + " (배제·위임·준용·정의·제재는 판단 없이 동반)"})
    nav = vmeta.get("nav")
    if nav:
        ladder.append({"stage": "간선 항해", "count": len(nav.get("picked", [])),
                       "note": f"LLM 이 간선 카드에서 고름, {nav['hops']}홉"})
    if idx.scope is not None:
        ladder.append(_scope_rung(idx, smeta))
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
            added = (_respot(idx, q, spots, sections)
                     if spots and switches_mod.is_on("issue_respot") else [])
            if added:
                sections = sections + added
                sections, _ = answer_mod.enforce_scope(idx, sections)
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
           "scope": _scope_out(idx, smeta),
           "쟁점": {"트리거": _spot_dump(spots_trig, "트리거"),
                    "분해": _spot_dump(spots, "llm(검색전)")
                            if (spots and spots[0].get("via", "").startswith("llm")) else None,
                    "판정": spots_judged, "질의확장": qx if qx and qx != q else "",
                    "벡터질의": vmeta.get("vec_query") or ""},
           "filter": {"in": len(sections), "out": len(sections),
                      "applied": False, "reason": "벡터 모드 — 필터 없음(출처는 정적)"},
           "context": [_ctx_row(idx, s) for s in sections],
           "answer": ans.answer, "answerable": ans.answerable,
           # 출처는 회수 집합 그대로 — 모델 인용은 cited 로 따로 준다.
           "refs": vecfirst.static_refs(sections),
           "cited": [r.get("n") for r in ans.refs],
           # 판정 지문은 여기 없다 — 답을 보낸 **뒤** 백그라운드 감사가 남긴다
           # (audit.py). 답변 콜에 얹으면 그 판정을 만드는 시간이 곧 응답 지연이다.
           "discards": [],
           # 착지 교정 — 이번 답변에서 LLM 이 고쳐 앉힌 참조. 간선 반영은 승인 몫.
           "fixes": fixes}
    combo_meta = vmeta.get("combination") or {}
    if combo_meta.get("exploration"):
        # 검색 좌표가 어떤 문서→조→항 탐색 범위가 됐고 무엇이 선택됐는지 검수
        # 화면에서 그대로 재현한다. 원문 전문은 context에만 있고 여기에는 경로만 있다.
        out["exploration"] = combo_meta["exploration"]
        out["exploration_selection"] = {
            "choice": combo_meta.get("choice") or {},
            "selected": combo_meta.get("selected") or [],
            "coordinate_option_count": combo_meta.get("coordinate_option_count", 0),
        }
    if ans.wiki:
        out["wiki"] = ans.wiki
    if ans.error:
        out["error"] = ans.error
    if llm is not None and llm.log:
        out["usage"] = llm.totals()
        out["timing"] = _timing(llm)
    _attach_content_snapshot(out, idx)
    # 벡터 진입은 종착이 아니라 용어의 씨앗 — 승격 후보(잠정)로 적는다.
    _after_answer(out, q, llm, sections, ans, fixes,
                  cand_coords=[{"doc_id": e["doc_id"], "node": e["node"],
                                "via": "벡터"} for e in vmeta["entries"]])
    return out


@router.get("/scopes", summary="질의 스코프 목록 — scopes.yml 정의(해석 결과) + 내장")
def rag_scopes():
    """사용자가 yml 로 정의한 문서 묶음이 스토어의 어느 문서로 해석됐는지 — 못
    찾은 이름(missing)이 같이 나온다. 빈 스코프·오타가 조용히 전체 검색으로
    새지 않게 하는 관측 창."""
    idx = index_mod.current()
    if idx.content_snapshot is not None:
        out = {
            "path": None,
            "exists": False,
            "source": "release-bound-builtins",
            "scopes": scopes_mod.listing(idx),
        }
    else:
        path = scopes_mod.scopes_path()
        out = {
            "path": str(path),
            "exists": path.exists(),
            "source": "legacy-file-and-builtins",
            "scopes": scopes_mod.listing(idx),
        }
    return _attach_content_snapshot(out, idx)


@router.post("/scopes/file", summary="scopes.yml 교체 — yml 본문을 올린다")
async def rag_scopes_upload(file: UploadFile = File(...)):
    """화면이나 curl 로 yml 을 올리면 정본 자리에 쓴다. 쓰기 전에 파싱·해석해
    모양이 틀리면 400 — 깨진 파일로 스코프를 전부 잃지 않는다."""
    import yaml
    raw = await file.read()
    try:
        data = yaml.safe_load(raw.decode("utf-8")) or {}
    except Exception as exc:
        raise HTTPException(400, f"yml 을 읽지 못했습니다: {exc}")
    if isinstance(data, list):
        data = {"scopes": data}
    if not isinstance(data, dict) or not isinstance(data.get("scopes"), list):
        raise HTTPException(400, "꼭대기에 scopes: [ {name, documents…}, … ] 목록이 있어야 합니다")
    for row in data["scopes"]:
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            raise HTTPException(400, f"name 이 없는 스코프 항목: {row!r}"[:200])
    path = scopes_mod.save(data)
    return {"path": str(path), "scopes": scopes_mod.listing(index_mod.current())}


def _legalclosure_public(meta: dict) -> dict:
    """호환 wrapper. 표현 로직은 전용 presenter가 소유한다."""
    from lawrag.api import legalclosure_presenter
    return legalclosure_presenter.public_meta(meta)


def _ask_legalclosure(body: Ask, idx, q: str, llm, *, t0: float,
                      requested_mode: str) -> dict:
    """운영 메인: LegalClosure 조문 좌표를 그대로 답변 근거로 합성한다."""
    from lawrag.api import legalclosure_presenter
    from lawrag.runtime import registry as runtime_registry
    from lawrag.core.rag import vecfirst
    assertion_llm = _legalclosure_assertion_llm(llm)
    sections, retrieval_meta = runtime_registry.retrieve(
        idx, q, llm=llm, assertion_llm=assertion_llm, cap=20,
        shortcut_enabled=switches_mod.is_on("legalclosure_proof_shortcut"),
        feedback_enabled=switches_mod.is_on("legalclosure_feedback_explore"),
        graph_enabled=switches_mod.is_on("legal_graph_v1_closure"),
        semantic_graph_enabled=switches_mod.is_on(
            "legal_semantic_entity_search"))
    # 한 질의의 감사 로그는 기존 튜플 계약상 한 객체에 있어야 한다. 정확 구조가
    # 먼저, Assertion이 다음에 실행되므로 별도 모델 로그를 그 순서로 합친다.
    if (llm is not None and assertion_llm is not None and assertion_llm is not llm
            and getattr(assertion_llm, "log", None)):
        llm.log.extend(assertion_llm.log)

    sections, smeta = answer_mod.enforce_scope(idx, sections)
    feedback = retrieval_meta.get("feedback_loop") or {}
    feedback_failed = bool(
        feedback.get("enabled") and feedback.get("ran")
        and feedback.get("sufficient") is False)
    recovery = None
    if not sections and body.recover and not feedback_failed:
        recovery = recover_mod.run(llm, idx, q)
        if recovery.coords:
            sections = answer_mod.sections_from_coords(idx, recovery.coords)
            sections, smeta = answer_mod.enforce_scope(idx, sections)

    public_meta = _legalclosure_public(retrieval_meta)
    main_pipeline = (retrieval_meta.get("runtime") or {}).get("main_pipeline") or {}
    ladder = legalclosure_presenter.ladder(public_meta, len(sections))
    if recovery is not None:
        ladder.extend(recovery.trail)
    if idx.scope is not None:
        ladder.append(_scope_rung(idx, smeta))

    # 쟁점 카드는 검색 좌표를 바꾸지 않고 답변 배경으로만 사용한다. 평가된
    # LegalClosure 회수에 검색 전 LLM 재작성 경로를 섞지 않는다.
    spots = wikictx.spot(q) if switches_mod.is_on("issue_spot") else []
    if feedback_failed:
        ans = answer_mod.Answer(
            answer=("최종 회수 조문을 관계·구조·키워드·벡터로 다시 탐색했지만 "
                    "질문에 답할 지배 근거를 확인하지 못했습니다."),
            answerable=False)
    else:
        ans = answer_mod.synthesize(llm, q, sections, spots=spots)
    if ans.wiki:
        ladder.append({"stage": "위키 맥락", "count": len(ans.wiki),
                       "note": " · ".join(w["title"] for w in ans.wiki)})
    refs = [] if feedback_failed else vecfirst.static_refs(sections)
    effective_profile = str(
        (retrieval_meta.get("runtime") or {}).get("effective_profile")
        or main_pipeline.get("runtime_profile")
        or "legalclosure-v2"
    )
    out = {
        "question": q, "mode": "LegalClosure", "ladder": ladder,
        "retriever": {
            "id": effective_profile, "status": "main",
            "requested_mode": requested_mode,
            "strategy": retrieval_meta.get("strategy"),
            "legal_graph": {
                "enabled": bool((retrieval_meta.get("legal_graph") or {}).get("enabled")),
                "status": (retrieval_meta.get("legal_graph") or {}).get("status"),
                "generation_id": (retrieval_meta.get("legal_graph") or {}).get(
                    "generation_id", ""),
                "added_count": (retrieval_meta.get("legal_graph") or {}).get(
                    "added_count", 0),
            },
            "main_pipeline": main_pipeline,
            "primary_model": getattr(llm, "model", "") if llm else "",
            "assertion_model": getattr(assertion_llm, "model", "")
                               if assertion_llm else "",
        },
        "scope": _scope_out(idx, smeta),
        # LegalClosure의 닫힌 조문 선택을 일반 관련성 필터가 다시 삭제하지 않는다.
        "filter": {"in": len(sections), "out": len(sections),
                   "applied": False,
                   "reason": "LegalClosure 확정 좌표 — 일반 관련성 필터 미적용"},
        "context": [_ctx_row(idx, section) for section in sections],
        "answer": ans.answer, "answerable": ans.answerable,
        "refs": refs, "cited": [row.get("n") for row in ans.refs],
        "discards": [], "fixes": [], "legalclosure": public_meta,
    }
    legal_warnings = (public_meta.get("legal_annotations") or {}).get("warnings") or []
    if legal_warnings:
        out["legal_warnings"] = legal_warnings
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
    _attach_content_snapshot(out, idx)
    _after_answer(out, q, llm, sections, ans, [], cand_coords=None)
    _ask_event(out, logbook.ms(t0))
    return out


@router.post("/ask", summary="질의응답 — LegalClosure 기본, legacy 경로는 롤백용")
def rag_ask(body: Ask):
    t0 = time.perf_counter()
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(400, "질문이 비었습니다")
    requested_mode, effective_mode, rolled_back = _resolve_ask_mode(body.mode)
    log.info("질의 시작 — '%s' (requested=%s, effective=%s, filter=%s, recover=%s)",
             q[:60], requested_mode, effective_mode, body.filter, body.recover)
    idx = index_mod.current()
    # 질의 스코프 — "이 문서들만". 이름을 모르거나 비면 400 — 조용히 전체를
    # 뒤지는 것이 과제 1 의 정반대다.
    try:
        idx, scope_info = scopes_mod.apply(idx, body.scope, body.documents)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if idx.scope is not None:
        log.info("스코프 '%s' — 문서 %d (못 찾음 %d)", idx.scope_name,
                 len(idx.scope), len(scope_info.get("missing") or []))
    llm = _llm()
    if llm is None:
        log.warning("LLM 없음 — 검색까지만 내려간다 (%s 미설정)", llm_mod.MISSING_HINT)
    if effective_mode == LEGALCLOSURE_MODE:
        return _ask_legalclosure(
            body, idx, q, llm, t0=t0, requested_mode=requested_mode)

    # 여기부터는 롤백·A/B를 위해 보존한 이전 경로다. 옛 vector/auto 요청도
    # 이 이름으로 정규화되며 응답 retriever가 archived/rollback을 드러낸다.
    from lawrag.platform import main_promotion
    legacy_mode = "vector" if effective_mode == "legacy-vector" else "auto"
    legacy_retriever = {
        "id": effective_mode,
        "status": "rollback" if rolled_back else "archived",
        "requested_mode": requested_mode,
        "rollback_reason": ("legalclosure_main 스위치 OFF"
                            if rolled_back else ""),
        "main_pipeline": main_promotion.runtime_provenance(),
    }

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

    # 질문 기억 — 같은/비슷한 질문에 사람이 승인한 착지(candidates 활성).
    # 검색 없이 열며 두 경로 모두 진입 앞에 앉는다. 잠정은 안 연다.
    memory = promote_mod.direct_hits(q, index=idx)

    vector_missed = False
    auto_concept_sections, auto_concept_meta = [], {}
    if legacy_mode == "vector":
        out_v = _ask_vector(idx, q, llm, spots=spots, qx=qx,
                            spots_trig=spots_trig, qv=qv, memory=memory)
        if out_v is not None:
            out_v["retriever"] = legacy_retriever
            _ask_event(out_v, logbook.ms(t0))
            return out_v
        vector_missed = True          # 색인·모델 부재 포함 — 사다리가 받는다
    elif switches_mod.is_on("concept_entry"):
        from lawrag.core.rag import conceptfirst as conceptfirst_mod
        auto_concept_sections, auto_concept_meta = conceptfirst_mod.retrieve(
            idx, q, llm=llm, coordinate_first=True)

    res = run_search(idx, qx)
    if vector_missed:
        res.ladder.insert(0, {"stage": "벡터 진입", "count": 0,
                              "note": "미스(색인·모델 부재 포함) — 용어 사다리로 폴백"})
    if memory:
        res.ladder.insert(0, {"stage": "질문 기억", "count": len(memory),
                              "note": _memory_note(memory)})
    if spots:
        res.ladder.insert(0, {"stage": "쟁점 분해", "count": len(spots),
                              "note": _spot_note(spots, qx != q)})
    sections = answer_mod.assemble(idx, res, seeds=memory)
    if auto_concept_sections:
        seen_concept = {(s.doc_id, s.node) for s in auto_concept_sections}
        sections = (auto_concept_sections
                    + [s for s in sections if (s.doc_id, s.node) not in seen_concept])[
                        :answer_mod.CANDIDATES_MAX]
        sections = answer_mod.expand_refs(idx, sections, cap=answer_mod.CANDIDATES_MAX)
        for i, section in enumerate(sections, 1):
            section.n = i
        labels = [c.get("label", "") for c in
                  (auto_concept_meta.get("alignment") or {}).get("selected") or []]
        if not labels:
            labels = [c.get("label", "") for c in
                      auto_concept_meta.get("landings") or []]
        res.ladder.insert(0, {"stage": "구조·역할 교집합",
                              "count": len(auto_concept_sections),
                              "note": "DB 객체 착지 — " + " · ".join(labels)})
    sections, smeta = answer_mod.enforce_scope(idx, sections)
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
            added = (_respot(idx, q, spots, sections)
                     if spots and switches_mod.is_on("issue_respot") else [])
            if added:
                sections = sections + added
                for i, s in enumerate(sections, start=1):
                    s.n = i
                res.ladder.append({"stage": "판정 재회수", "count": len(added),
                                   "note": "쟁점 조문 후보 재검색 — "
                                           + " · ".join(sorted({s.doc for s in added}))})

    # 스코프 보루 — 회복·판정 재회수·참조 확장이 무엇을 데려왔든 진입은 안,
    # 동반은 표식. 합성 직전이 마지막 자리다.
    if idx.scope is not None:
        sections, smeta2 = answer_mod.enforce_scope(idx, sections)
        smeta = {"dropped": smeta["dropped"] + smeta2["dropped"],
                 "out": smeta2["out"]}
        res.ladder.append(_scope_rung(idx, smeta))
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
           "retriever": legacy_retriever,
           "scope": _scope_out(idx, smeta),
           # 쟁점기의 전모 — 트리거가 무엇을 물었고(왜), 판정이 무엇으로
           # 고쳤고, 질의가 어떻게 넓어졌는지. 사다리 note 는 제목뿐이다.
           "쟁점": {"트리거": _spot_dump(spots_trig, "트리거"),
                    "분해": _spot_dump(spots_pre, "llm(검색전)") if spots_pre is not None else None,
                    "판정": spots_judged, "질의확장": qx if qx != q else "",
                    "벡터질의": qv},
           "filter": fmeta,
           "context": [_ctx_row(idx, s) for s in sections],
           "answer": ans.answer, "answerable": ans.answerable, "refs": ans.refs,
           "discards": [], "fixes": fixes}
    if auto_concept_meta:
        out["concept"] = auto_concept_meta
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
    _attach_content_snapshot(out, idx)

    # 승격 후보 — 탐험(회복) 착지와, 벡터 단이 찾아 실제 답변에 실린 착지.
    # 벡터 히트는 종착이 아니라 용어의 씨앗이다 (하이브리드 결정, vector.py 머리).
    cand: list = []
    if recovery is not None and recovery.coords:
        cand += recovery.coords
    vec_nodes = {(h.doc_id, h.node) for h in res.hits if h.kind == "벡터"}
    if vec_nodes:
        cand += [{"doc_id": r["doc_id"], "node": r["node"], "via": "벡터"}
                 for r in ans.refs
                 if (r.get("doc_id"), r.get("node")) in vec_nodes]
    _after_answer(out, q, llm, sections, ans, fixes, cand_coords=cand)
    _ask_event(out, logbook.ms(t0))
    return out


class Compare(BaseModel):
    """내규 조 하나를 외규와 비교 — 상충/미비/부합/재검토와 근거 좌표.

    doc 은 내규 문서 이름(부분 일치), article 은 조 표면형('제12조' —
    '제12조제2항'을 줘도 조로 접는다). 흐름·판정 규칙의 정본은
    docs/COMPARE_INTERNAL_EXTERNAL.md, 엔진은 lawrag/core/rag/compare.py."""
    doc: str
    article: str
    scope: str = "외규"


@router.post("/compare", summary="내규↔외규 비교 — 수치 override+원자명제 coverage gate")
def rag_compare(body: Compare):
    import re as _re

    from lawrag.core.rag import compare as compare_mod

    t0 = time.perf_counter()
    idx = index_mod.current()
    name = (body.doc or "").strip()
    named = [v for v in idx.docs.values() if name and name in v.name]
    if not named:
        raise HTTPException(404, f"문서를 못 찾았습니다: {name}")
    hits = [v for v in named if v.scope_kind == "내규"]
    if not hits:
        raise HTTPException(400, f"비교 입력은 내규 문서여야 합니다: {name}")
    if len(hits) > 1:
        # 현행 우선 — 신·구판이 같이 걸리면 개정일이 최신인 판. 이름순이면
        # '…_v1_2024' 가 '…_v2_2026' 보다 앞서 구판이 잡힌다.
        hits.sort(key=lambda v: (v.is_current, v.revised or ""), reverse=True)
    v = hits[0]
    jo = _re.match(r"제\s*[\d\-]+\s*조(의\s*\d+)?", (body.article or "").replace(" ", ""))
    if not jo:
        raise HTTPException(400, f"조 표면형이 아닙니다: {body.article}")
    jo_s = jo.group(0)
    node = next((n["id"] for n in v.nodes
                 if (n.get("surface") or "").replace(" ", "") == jo_s
                 and "부칙" not in v.path(n["id"])), None)
    if node is None:
        raise HTTPException(404, f"{v.name} 에 {jo_s} 가 없습니다")
    try:
        out = compare_mod.compare_article(_llm(), idx, v.doc_id, node,
                                          scope=body.scope or "외규")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    from lawrag.platform import main_promotion
    from lawrag.core.rag import switches as switches_mod
    switch_row = next(
        (row for row in switches_mod.snapshot()
         if row["key"] == "internal_compliance_compiler_v1"), {})
    out["pipeline"] = {
        "profile": ("internal-compliance-atomic-v1" if switch_row.get("on")
                    else "legalclosure-comparison-v2"),
        "switch": switch_row,
        "main": main_promotion.runtime_provenance(),
    }
    out["ms"] = int((time.perf_counter() - t0) * 1000)
    return out


class Feedback(BaseModel):
    """사용자 신호 — "A 를 물었는데 B 가 나왔다(오답)" 또는 "맞았다(정답)"."""
    qid: str
    verdict: str                       # "정답" | "오답"
    expected: Optional[dict] = None    # 오답일 때 기대 좌표 {doc_id, node}
    note: str = ""


def _role_predicate_feedback_recovery(idx, ask_record: dict) -> dict:
    """Return source-validated suggestions without rewriting the prior answer.

    The stored question and already-presented context are the only tuple fields
    consumed.  Existing coordinates form an immutable exclusion floor; the
    router therefore returns additions only.
    """
    question = str(ask_record.get("질의") or "").strip()
    if not question:
        return {
            "enabled": True, "attempted": False,
            "reason": "stored_question_missing", "selected": [],
        }
    floor = []
    for row in ask_record.get("context") or ():
        doc_id, node = row.get("doc_id"), row.get("node")
        view = idx.docs.get(doc_id)
        if view is None or node not in view.by_id:
            continue
        coordinate = (str(doc_id), legal_coordinates.article_root(view, int(node)))
        if coordinate not in floor:
            floor.append(coordinate)
    branches, meta = companion_recovery.role_predicate_governing_feedback(
        idx, question, answer_incorrect=True, exclude=floor,
        preferred_document_ids=sorted(getattr(idx, "canonical_doc_ids", None) or ()),
        card_limit=2, addition_cap=4)
    selected = [{
        "doc_id": row.doc_id,
        "node": row.node,
        "doc": row.doc,
        "path": row.path,
        "origin": row.origin,
    } for row in branches]
    return {
        "enabled": True,
        "attempted": True,
        "reason": meta.get("reason") or "no_validated_governing_hypothesis",
        "baseline_count": len(floor),
        "baseline_preserved": True,
        "added_count": len(selected),
        "selected": selected,
        "audit": {
            "general_lexical_search_calls": meta.get("general_lexical_search_calls", 0),
            "forbidden_fields_used": meta.get("forbidden_fields_used") or [],
            "predicate_families": meta.get("predicate_families") or [],
            "caps": meta.get("caps") or {"cards": 2, "additions": 4},
            # Card body is not present in router metadata.  These bounded fields
            # make a failed feedback attempt explainable without exposing gold,
            # reference answers, or opening another search path.
            "cards": [{
                "slug": card.get("slug"),
                "title": card.get("title"),
                "matched_triggers": card.get("matched_triggers") or [],
                "actor_roles": card.get("actor_roles") or [],
                "predicate_families": card.get("predicate_families") or [],
                "gate_open": bool(card.get("gate_open")),
                "hypotheses": card.get("hypotheses") or [],
            } for card in (meta.get("cards") or [])],
        },
    }


@router.post("/feedback", summary="질의 피드백 — 진단 튜플에 기대 출력을 기록")
def rag_feedback(body: Feedback):
    """실패_원인(a~d) 판정은 여기서 하지 않는다 — 책임 귀속은 별도 국면이다.
    기대 좌표는 실재하는 구역만 받는다(닫힌 후보 규율과 같다)."""
    if body.verdict not in ("정답", "오답"):
        raise HTTPException(400, "verdict 는 '정답' 또는 '오답'이어야 합니다")
    ask_record = tuples_mod.find(body.qid)
    if ask_record is None:
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
        if switches_mod.is_on("sourceset_content_snapshot"):
            snapshot = current_content_snapshot(required=True)
            assert snapshot is not None  # narrowed by required=True
            expected["content_provenance"] = (
                snapshot.provenance_for_document(doc_id).receipt()
            )
    ontology_event = None
    ontology_error = None
    try:
        ontology_event = feedback_lifecycle.build_rag_feedback_event(
            qid=body.qid,
            verdict=body.verdict,
            ask_record=ask_record,
            expected=expected,
            note=body.note,
        )
    except (TypeError, ValueError) as exc:
        # The original feedback receipt remains authoritative and durable even
        # when the optional ontology observation cannot be compiled.
        ontology_error = f"{type(exc).__name__}: {exc}"
    rec = tuples_mod.log_feedback(
        body.qid,
        body.verdict,
        expected,
        body.note,
        ontology_feedback=ontology_event,
    )
    logbook.rag_event("feedback", qid=body.qid, verdict=body.verdict,
                      expected_path=(expected or {}).get("path"),
                      note=body.note[:200])
    # 위키 부검 — 그 질의에 아티클이 끼었을 때만 원장에 남는다.
    wikiledger.feedback(body.qid, body.verdict, body.note)
    log.info("피드백 — %s %s%s", body.qid, body.verdict,
             f" (기대: {expected['path']})" if expected else "")
    recovery_enabled = switches_mod.is_on("role_predicate_feedback_recovery")
    if body.verdict != "오답":
        recovery = {
            "enabled": recovery_enabled, "attempted": False,
            "reason": "verdict_not_incorrect", "selected": [],
        }
    elif expected is not None:
        recovery = {
            "enabled": recovery_enabled, "attempted": False,
            "reason": "explicit_expected_coordinate", "selected": [],
        }
    elif not recovery_enabled:
        recovery = {
            "enabled": False, "attempted": False,
            "reason": "switch_off", "selected": [],
        }
    else:
        try:
            recovery = _role_predicate_feedback_recovery(
                index_mod.current(), ask_record)
        except Exception as exc:  # feedback receipt must remain durable
            log.exception("오답 역할·판단축 복구 실패 — 피드백 기록은 보존: %s", body.qid)
            recovery = {
                "enabled": True, "attempted": True,
                "reason": "recovery_failed_open", "selected": [],
                "error": type(exc).__name__,
            }
    change_candidates = (
        list(feedback_lifecycle.compile_change_candidates([ontology_event]))
        if ontology_event is not None else []
    )
    return {
        "saved": True,
        "record": rec,
        "recovery": recovery,
        "ontology_feedback": {
            "event": ontology_event,
            "change_candidates": change_candidates,
            "error": ontology_error,
            "activation": "INERT_UNTIL_REVIEW",
        },
    }


@router.get("/tuples", summary="진단 튜플 목록 — 질의 기록 + 피드백 합본")
def rag_tuples(limit: int = Query(100, ge=1, le=1000)):
    rows = tuples_mod.read(limit=limit)
    n_fb = sum(1 for r in rows if r.get("피드백"))
    return {"tuples": rows, "count": len(rows), "with_feedback": n_fb,
            "candidates": tuples_mod.candidates()}


@router.get("/approvals", summary="사람 판정 공통 receipt — 승인 원장 합본")
def rag_approvals(limit: int = Query(200, ge=1, le=2000),
                  current_only: bool = Query(False)):
    """기능별 정본을 바꾸지 않고 승인·기각·교정 사건을 한 계보로 보여준다."""
    from lawrag.core.rag import approvals

    rows = approvals.current() if current_only else approvals.read()
    return {"rows": rows[-limit:], "count": len(rows),
            "store": str(approvals.receipts_path())}


@router.get("/approvals/evolution",
            summary="승인 receipt 기반 진화 후보 — 실패×효과 집계")
def rag_approval_evolution(min_evidence: int = Query(2, ge=1, le=100)):
    """읽기 전용 후보표다. 이 API는 설정이나 정본을 자동 변경하지 않는다."""
    from lawrag.core.rag import approvals

    return approvals.evolution_summary(min_evidence=min_evidence)


@router.get("/verdicts", summary="판정 백로그 — 잘못 끌려온 간선의 지문 묶음")
def rag_verdicts():
    """답변 시점 LLM 이 찍은 '오참조·무관' 지문을 간선별로 묶어 준다.
    승인 전까지는 아무것도 안 바뀐다 — 이 화면의 승인이 억제 규칙을 만든다.
    질문 기억 후보(승격 원장 잠정) 수도 함께 — 상단바 배지가 백로그 하나로 센다."""
    return {**verdicts_mod.backlog(), "memory_pending": len(promote_mod.queue("잠정"))}


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
    # 질문 기억 후보 — 승인형 원장(candidates.json)의 잠정 행. 백로그 화면이
    # 같은 자리에서 승인/기각한다(용어 사전과 같은 규율: 활성만 채널에 실린다).
    bl["memory"] = _memory_rows("잠정")[:50]
    bl["memory_counts"] = _memory_counts()
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


def _memory_counts() -> dict:
    out = {"잠정": 0, "활성": 0, "tombstone": 0}
    for r in promote_mod._load():
        out[(r.get("status") or "잠정")] = out.get(r.get("status") or "잠정", 0) + 1
    return out


def _memory_rows(status: str) -> list[dict]:
    """승격 원장 행에 사람이 읽는 좌표(문서명·경로)를 붙인다 — 원장은 좌표만
    적는다. 없는 문서(삭제·재색인)는 '?' 로 남겨 화면이 기각할 수 있게 한다."""
    idx = index_mod.current()
    rows = promote_mod.queue(status) if status != "전부" else promote_mod._load()
    out = []
    for r in rows:
        v = idx.docs.get(r.get("doc_id"))
        out.append({**r, "status": r.get("status") or "잠정",
                    "doc": v.name if v else "?",
                    "path": v.path(r.get("node")) if v else "",
                    "exists": v is not None and v.by_id.get(r.get("node")) is not None})
    return out


@router.get("/terms/proposals", summary="새 표현 검수 — LLM 제안, 사람 승인/기각")
def rag_term_proposals(
        status: str = Query("pending", description="pending|approved|rejected|all"),
        limit: int = Query(200, ge=1, le=2000)):
    """질의 중 DB 값과 달랐던 표현의 단일 검수 원장.

    pending은 검색에 아직 쓰이지 않는다. 사람이 승인한 표현만 문서 별칭 또는
    Concept aliases 정본에 발행된다.
    """
    from lawrag.core.rag import term_proposals

    try:
        rows = term_proposals.queue(status)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"rows": rows[:limit], "count": len(rows)}


class TermProposalResolve(BaseModel):
    proposal_id: str
    action: str                       # "승인" | "기각"
    note: str = ""
    reviewer: str = "user"


@router.post("/terms/proposals/resolve",
             summary="새 표현 처리 — 승인만 검색 정본에 발행")
def rag_term_proposal_resolve(body: TermProposalResolve):
    from lawrag.core.rag import term_proposals

    pending = {row.get("id"): row for row in term_proposals.queue("all")}
    row = pending.get(body.proposal_id)
    if row is None:
        raise HTTPException(404, "용어 제안을 찾을 수 없습니다")
    target = row.get("target") or {}
    if body.action == "승인" and target.get("kind") == "document":
        view = index_mod.current().docs.get(str(target.get("id") or ""))
        if view is None or view.name != target.get("label"):
            raise HTTPException(400, "문서 대상이 현재 DB 정본과 일치하지 않습니다")
    try:
        saved = term_proposals.resolve(
            body.proposal_id, body.action,
            reviewer=body.reviewer or "user", note=body.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    logbook.rag_event("term_proposal", proposal_id=body.proposal_id,
                      action=body.action, target=target)
    return {"saved": True, "proposal": saved}


@router.get("/memory", summary="질문 기억 — 승격 원장(잠정·활성·기각) 목록")
def rag_memory(status: str = Query("잠정", description="잠정|활성|tombstone|전부"),
               limit: int = Query(200, ge=1, le=2000)):
    """candidates.json 의 읽는 쪽. 잠정은 자동 적재(벡터·깔때기·회복 착지),
    활성만 다음 질의의 직행 좌표(promote.direct_hits)가 된다."""
    if status not in ("잠정", "활성", "tombstone", "전부"):
        raise HTTPException(400, "status 는 잠정|활성|tombstone|전부")
    rows = _memory_rows(status)
    return {"rows": rows[:limit], "count": len(rows), "counts": _memory_counts()}


class MemoryResolve(BaseModel):
    """승격 원장 처리 — 화면의 후보 카드가 그대로 보낸다.
    승인=활성(직행 좌표가 된다) · 기각=tombstone · 보류=잠정 복귀."""
    qkey: str
    doc_id: str
    node: int
    action: str                        # "승인" | "기각" | "보류"
    note: str = ""


@router.post("/memory/resolve", summary="질문 기억 처리 — 승인은 다음 질의의 직행 좌표가 된다")
def rag_memory_resolve(body: MemoryResolve):
    status = {"승인": "활성", "기각": "tombstone", "보류": "잠정"}.get(body.action)
    if status is None:
        raise HTTPException(400, "action 은 승인|기각|보류")
    if status == "활성":
        # 활성은 검색 없이 열리는 좌표다 — 실재하는 구역만 (닫힌 후보 규율).
        v = index_mod.current().docs.get(body.doc_id)
        if v is None or v.by_id.get(body.node) is None:
            raise HTTPException(400, "좌표가 유효하지 않습니다 — 문서나 구역이 없습니다")
    if not promote_mod.set_status(body.qkey, body.doc_id, body.node, status,
                                  body.note):
        raise HTTPException(404, "원장에 그 행이 없습니다")
    logbook.rag_event("memory", qkey=body.qkey, doc_id=body.doc_id,
                      node=body.node, action=body.action, note=body.note[:200])
    return {"saved": True, "status": status, "counts": _memory_counts()}


@router.get("/nodes", summary="문서의 구역 목록 — 좌표 선택용 (가벼운 형태)")
def rag_nodes(doc_id: str = Query(...)):
    """피드백 화면이 기대 구역을 고를 때 쓴다. 검수 payload(result.json)는
    블록·이미지까지 실려 무겁다 — 여기는 (id, 경로, 쪽)만 준다."""
    idx = index_mod.current()
    v = idx.docs.get(doc_id)
    if v is None:
        raise HTTPException(404, f"문서가 없습니다: {doc_id}")
    provenance = _required_content_provenance(v, label=f"nodes:{doc_id}")
    out = {
        "doc_id": doc_id,
        "doc": v.name,
        "nodes": [
            {
                "node": n.get("id"),
                "path": v.path(n.get("id")),
                "page": n.get("page"),
                "level": n.get("level"),
            }
            for n in v.nodes
        ],
    }
    if provenance is not None:
        out["content_provenance"] = provenance
    return _attach_content_snapshot(out, idx)


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
