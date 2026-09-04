"""LLM 검색어 추출 + 일반 문서 검색 API.

기존 ``/v1/rag/search``의 용어 사다리와 분리된 실험 창이다. 검색 품질을
독립 검수한 뒤에만 기본 답변 회수와 합류시키기 위해 별도 endpoint로 둔다.
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from lawrag.core import llm as llm_mod
from lawrag.core import logbook
from lawrag.core.rag import index as index_mod
from lawrag.core.rag import scopes as scopes_mod
from lawrag.core.rag.general_search import fuse_with_registered, search_question
from lawrag.core.rag.search import search as registered_search


router = APIRouter(prefix="/v1/rag", tags=["rag"])


class GeneralSearchRequest(BaseModel):
    question: str
    scope: str = ""
    documents: Optional[list[str]] = None
    limit: int = Field(default=8, ge=1, le=30)


def _llm():
    return llm_mod.LLM() if llm_mod.available() else None


@router.post("/general-search",
             summary="질문 → LLM 검색어 → 일반 제목·본문 검색")
def general_search(body: GeneralSearchRequest):
    """등록 용어가 없어도 질문에서 일반 검색어를 뽑아 관련 문서를 찾는다.

    LLM이 만든 검색어는 문서 좌표로 취급하지 않는다. 실제 제목·본문에 맞은
    결과만 반환하며 코퍼스에 없는 검색어는 ``unmatched``에 그대로 드러난다.
    LLM이 없거나 호출에 실패하면 ``extractor=fallback``으로 질문 어절 검색을
    수행한다.
    """
    t0 = time.perf_counter()
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(400, "질문이 비었습니다")
    index = index_mod.current()
    try:
        index, scope_info = scopes_mod.apply(index, body.scope, body.documents)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    result = search_question(index, question, _llm(), limit=body.limit)
    logbook.rag_event(
        "general_search", q=question, mode="일반검색",
        n_hits=len(result.hits), n_documents=len(result.documents),
        keywords=result.keywords, unmatched=result.unmatched,
        extractor=result.extractor, dur_ms=logbook.ms(t0),
    )
    out = result.as_dict()
    out["scope"] = {
        "name": index.scope_name or "",
        "documents": len(index.entry_docs),
        "missing": scope_info.get("missing") or [],
    }
    return out


def _registered_dump(result) -> dict:
    return {
        "mode": result.mode,
        "ladder": result.ladder,
        "hits": [{
            "kind": hit.kind, "value": hit.value, "score": hit.score,
            "match": hit.match, "reasons": hit.reasons,
            "doc_id": hit.doc_id, "doc": hit.doc, "node": hit.node,
            "block": hit.block,
            "occurrences": len(hit.occurrences or []),
        } for hit in result.hits],
    }


@router.post("/hybrid-search",
             summary="기존 역매칭 + LLM 일반검색을 함께 실행하고 RRF 합류")
def hybrid_search(body: GeneralSearchRequest):
    """두 검색 채널을 모두 보존하면서 좌표 중복만 접어 관련 구역을 반환한다."""
    t0 = time.perf_counter()
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(400, "질문이 비었습니다")
    index = index_mod.current()
    try:
        index, scope_info = scopes_mod.apply(index, body.scope, body.documents)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    registered = registered_search(index, question)
    general = search_question(index, question, _llm(), limit=body.limit)
    hits = fuse_with_registered(index, registered, general, limit=body.limit)
    logbook.rag_event(
        "hybrid_search", q=question, mode="역매칭+일반검색",
        n_hits=len(hits), registered_hits=len(registered.hits),
        general_hits=len(general.hits), keywords=general.keywords,
        unmatched=general.unmatched, extractor=general.extractor,
        dur_ms=logbook.ms(t0),
    )
    return {
        "question": question,
        "mode": "역매칭+일반검색",
        "hits": hits,
        "registered": _registered_dump(registered),
        "general": general.as_dict(),
        "scope": {
            "name": index.scope_name or "",
            "documents": len(index.entry_docs),
            "missing": scope_info.get("missing") or [],
        },
    }
