"""법적 검토 — 사실을 요건에 대는 API (docs/REVIEW.md).

    POST /v1/review              사실 → 쟁점 → 규범 → 포섭 → 결론
    GET  /v1/review/bindings     의존성 원장 (자산별 요약)
    GET  /v1/review/impacted     역인덱스 — 이 조문이 바뀌면 누가 영향받나

질의응답(/v1/rag/ask)과 다른 산출물을 낸다: 산문이 아니라 **요건별 충족표**다.
회수는 rag 의 자산을 그대로 쓴다 — 검토는 새 검색기가 아니라 판단 층이다.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from lawrag.core import llm as llm_mod
from lawrag.core import logbook
from lawrag.core.rag import index as index_mod
from lawrag.core.rag import switches as switches_mod
from lawrag.core.casereview import binding as binding_mod
from lawrag.core.casereview import pipeline as review_mod

router = APIRouter(prefix="/v1/review", tags=["review"])
log = logging.getLogger("lawrag.api.review")


class Review(BaseModel):
    text: str                                  # 사실관계 또는 서비스 설계
    track: str = "해석"                        # 해석 | 적법성 | 개정
    asset: Optional[str] = None                # 자산명 — 주면 원장에 적재된다
    scope: str = ""                            # 질의 스코프 (scopes.yml 이름 · 외규/내규/서식)
    documents: Optional[list[str]] = None      # 즉석 파일명 목록 — scope 와 합집합


def _llm():
    if not llm_mod.available():
        return None
    return llm_mod.LLM()


@router.post("", summary="법적 검토 — 요건별 충족표를 낸다")
def post_review(body: Review):
    t0 = time.perf_counter()
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "검토할 내용이 비었습니다")
    if body.track not in ("해석", "적법성", "개정"):
        raise HTTPException(400, "track 은 해석·적법성·개정 중 하나입니다")
    llm = _llm()
    if llm is None:
        raise HTTPException(503, "LLM 없음 — 검토는 판단이라 LLM 이 필요합니다 "
                                 f"({llm_mod.MISSING_HINT}). 검색은 /v1/rag 로.")
    from lawrag.core.rag import scopes as scopes_mod
    try:
        idx, scope_info = scopes_mod.apply(index_mod.current(), body.scope, body.documents)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    st = review_mod.run(llm, idx, text, track=body.track)
    out = st.to_dict()
    if idx.scope is not None:
        out["scope"] = {"name": idx.scope_name, "count": len(idx.scope),
                        "missing": scope_info.get("missing") or []}

    # 원장 적재 — 자산명이 있을 때만. 원장은 "무엇이 무엇에 매였나"의 기록이지
    # 질의 로그가 아니다 (binding.py 머리).
    if body.asset and switches_mod.is_on("review_binding"):
        try:
            out["bound"] = binding_mod.record(st, body.asset.strip())
        except Exception:                      # pragma: no cover
            log.exception("원장 적재 실패 — 검토 결과는 그대로 낸다")
    if llm.log:
        out["usage"] = llm.totals()
    try:
        logbook.rag_event("review", q=text[:200], mode=body.track,
                          n_hits=len(st.subs), ladder=st.trail,
                          dur_ms=logbook.ms(t0))
    except Exception:                          # pragma: no cover
        log.exception("이벤트 기록 실패 — 검토 결과는 그대로 낸다")
    return out


@router.get("/bindings", summary="의존성 원장 — 자산별 요약")
def get_bindings(asset: Optional[str] = Query(None, description="자산명 필터")):
    rows = binding_mod.load()
    if asset:
        rows = [b for b in rows if b.get("asset") == asset]
        return {"asset": asset, "bindings": rows}
    return {"assets": binding_mod.assets(), "total": len(rows)}


@router.get("/impacted", summary="역인덱스 — 이 조문이 바뀌면 누가 영향받나")
def get_impacted(doc: str = Query(..., description="문서명"),
                 node: Optional[int] = Query(None, description="마디 id")):
    rows = binding_mod.impacted(doc, node)
    return {"doc": doc, "node": node, "count": len(rows),
            "assets": sorted({b.get("asset", "") for b in rows}),
            "bindings": rows}
