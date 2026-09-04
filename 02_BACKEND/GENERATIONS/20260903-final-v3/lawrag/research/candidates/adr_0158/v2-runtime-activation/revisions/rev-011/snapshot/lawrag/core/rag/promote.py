"""승격 원장 — 어렵게 찾은 착지를 다음번엔 쉽게 찾게 하는 장부의 **읽는 쪽**.

원장 자체는 tuples.record_candidates 가 적는 data/rag/candidates.json 이다
(질의 정규형 · 좌표 · 경위 · 쟁점 카드 · 상태). 원래는 벡터 착지가 "용어가
되기를 기다리며" 적히기만 하고 아무도 안 읽었다. 여기가 그 소비자다.

    착지 (깔때기·벡터·항해)  → 잠정 (자동, record_candidates)
    잠정 → 활성              → 사람 승인 (approve) — 용어 사전과 같은 승인형
    활성                     → 다음 질의의 **직행 좌표** (direct_hits)

왜 승인형인가: 착지 한 번으로 굳히면 오답 착지도 굳는다 — 18-0124 에서 벡터가
찾은 제81조의13 도 착지였다. 활성만 채널에 실린다(2026-08-18 사용자 결정).

첫 소비자는 **질문 기억**이다 — 활성 행의 질문과 새 질문을 대조해 닿으면 그
좌표를 문면 인용처럼 검색 없이 연다. 대조는 두 겹: 정규형 완전일치(공짜) →
질문 임베딩 코사인(문턱). 질문↔조문은 문체가 달라 벡터가 헛돌았지만
질문↔질문은 같은 구어라 잘 맞는다 — 그게 이 기억이 벡터 채널과 다른 이유다.
슬롯 별칭(국세청→세무공무원)·카드↔조문 연결은 원장이 차면 다음 소비자다.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from lawrag.core.rag import tuples as tuples_mod
from lawrag.core.rag.content_snapshot import ContentSnapshotError
from lawrag.core.rag.controls import value as control_value
from lawrag.core.rag.index import norm

log = logging.getLogger("lawrag.core.rag.promote")

MEMORY_MIN_COS = float(control_value("entry.memory_cos_min"))
MEMORY_MAX = int(control_value("entry.memory_sections_max"))
_qvec_cache: dict = {}     # 활성 행 질문 → 임베딩 (원장 mtime 으로 무효화)


# ---------------------------------------------------------------- 원장 읽기·쓰기
def _load_raw() -> list[dict]:
    snapshot_context = tuples_mod._active_snapshot_context()
    if snapshot_context is not None and not os.environ.get(
        "RAG_QUERY_SHORTCUT_STORE", ""
    ).strip():
        # Writable feedback observations are not a retrieval authority.  A
        # SourceSet release sees shortcuts only through an explicitly pinned
        # reviewed store admitted by service bootstrap.
        return []
    return tuples_mod.reviewed_candidates()


def _load() -> list[dict]:
    """Read rows visible to this process generation.

    The raw file remains a multi-generation ledger.  With the SourceSet
    adapter OFF this is exactly the historical reader; with it ON, legacy,
    stale, and partially forged rows are invisible to every consumer.
    """

    rows = _load_raw()
    snapshot_context = tuples_mod._active_snapshot_context()
    if snapshot_context is None:
        return rows
    return [
        row for row in rows
        if tuples_mod._candidate_matches_snapshot(row, *snapshot_context)
    ]


def _save(rows: list[dict]) -> None:
    if tuples_mod._active_snapshot_context() is not None:
        raise PermissionError(
            "sealed SourceSet question-memory is deployment-pinned and read-only"
        )
    p = tuples_mod.candidates_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"candidates": rows}, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def queue(status: str = "잠정") -> list[dict]:
    """승인 큐 — 증거가 많은 것부터 (재발 횟수 → 최근)."""
    rows = [r for r in _load() if (r.get("status") or "잠정") == status]
    rows.sort(key=lambda r: (-int(r.get("count", 0)), r.get("last", "")), reverse=False)
    return rows


def set_status(qkey: str, doc_id: str, node, status: str, note: str = "",
               actor: str = "human") -> bool:
    """잠정 ↔ 활성 ↔ tombstone. 적었으면 True. 상태 변경 이력을 행에 남긴다."""
    if tuples_mod._active_snapshot_context() is not None:
        raise PermissionError(
            "reviewed question-memory must be published offline as a new pinned store"
        )
    if status not in ("잠정", "활성", "tombstone"):
        raise ValueError(f"모르는 상태: {status}")
    rows = _load_raw()
    snapshot_context = tuples_mod._active_snapshot_context()
    hit = False
    for r in rows:
        if snapshot_context is not None and not tuples_mod._candidate_matches_snapshot(
            r, *snapshot_context
        ):
            continue
        if r.get("qkey") == qkey and r.get("doc_id") == doc_id and r.get("node") == node:
            before = r.get("status") or "잠정"
            r["status"] = status
            r.setdefault("이력", []).append({"ts": tuples_mod._now(), "status": status,
                                            "메모": note[:120]})
            hit = True
    if hit:
        _save(rows)
        _qvec_cache.clear()
        from lawrag.core.rag import approvals
        effect = {"활성": "memory_activate", "tombstone": "memory_reject",
                  "잠정": "pending"}[status]
        failure = {"활성": "질문기억_누락", "tombstone": "질문기억_오염",
                   "잠정": ""}[status]
        source = {"ledger": "candidates"}
        if snapshot_context is not None:
            source.update({
                "content_snapshot": snapshot_context[1],
                "content_provenance": tuples_mod._document_provenance(
                    snapshot_context[0], doc_id
                ),
            })
        approvals.safe_record(
            kind="question_memory", decision=status, effect=effect, failure=failure,
            subject={"qkey": qkey, "doc_id": doc_id, "node": node},
            before={"status": before}, after={"status": status}, note=note,
            actor=actor, source=source)
    return hit


def approve(qkey: str, doc_id: str, node, note: str = "") -> bool:
    return set_status(qkey, doc_id, node, "활성", note)


def reject(qkey: str, doc_id: str, node, note: str = "") -> bool:
    return set_status(qkey, doc_id, node, "tombstone", note)


def active() -> list[dict]:
    return [r for r in _load() if r.get("status") == "활성"]


# ---------------------------------------------------------------- 소비자 ① 질문 기억
def direct_hits(question: str, cap: int = MEMORY_MAX,
                min_cos: float = MEMORY_MIN_COS, *, index=None) -> list[dict]:
    """활성 원장에서 이 질문에 닿는 좌표 — [{doc_id, node, via, why, score}].
    ① 정규형 완전일치 → score 1.0  ② 질문 임베딩 코사인 ≥ 문턱.
    임베딩이 없으면 ①만 — 결정론 부분은 언제나 돈다."""
    from lawrag.core.rag import switches as switches_mod
    if not switches_mod.is_on("memory_entry"):
        return []
    try:
        rows = active()
    except ContentSnapshotError as exc:
        # Question memory is an optimization, never the legal corpus.  A
        # substituted/stale reviewed store must not be consumed, but it also
        # must not suppress the normal release-bound retrieval ladder.
        log.error("reviewed question-memory rejected; using normal retrieval — %s", exc)
        return []
    if index is not None:
        rows = [
            row for row in rows
            if row.get("doc_id") in index.docs
            and row.get("node") in index.docs[row["doc_id"]].by_id
        ]
    if not rows or not (question or "").strip():
        return []
    qk = norm(question)
    out: dict[tuple, dict] = {}
    for r in rows:
        if r.get("qkey") == qk:
            out[(r["doc_id"], r["node"])] = {
                "doc_id": r["doc_id"], "node": r["node"], "via": "질문 기억",
                "why": "같은 질문 (승인 연결)", "score": 1.0}
    if len(out) < cap:
        try:
            from lawrag.core import embedding
            from lawrag.core.rag.content_snapshot import current_content_snapshot
            import numpy as np
            snapshot = current_content_snapshot()
            vector_bound = snapshot is None
            if snapshot is not None:
                try:
                    snapshot.index_binding("vector")
                    vector_bound = True
                except Exception:
                    vector_bound = False
            if vector_bound and embedding.available():
                qv = np.asarray(embedding.encode_one(question), dtype=np.float32)
                qv /= (np.linalg.norm(qv) + 1e-9)
                for r in rows:
                    key = (r["doc_id"], r["node"])
                    if key in out:
                        continue
                    best = 0.0
                    for s in r.get("surfaces") or []:
                        v = _qvec_cache.get(s)
                        if v is None:
                            v = np.asarray(embedding.encode_one(s), dtype=np.float32)
                            v /= (np.linalg.norm(v) + 1e-9)
                            _qvec_cache[s] = v
                        best = max(best, float(v @ qv))
                    if best >= min_cos:
                        out[key] = {"doc_id": r["doc_id"], "node": r["node"],
                                    "via": "질문 기억",
                                    "why": f"비슷한 질문 (코사인 {best:.2f}, 승인 연결)",
                                    "score": best}
        except ContentSnapshotError:
            raise
        except Exception as exc:                          # pragma: no cover
            log.debug("질문 기억 임베딩 생략 — %s", exc)
    ranked = sorted(out.values(), key=lambda x: -x["score"])
    return ranked[:cap]
