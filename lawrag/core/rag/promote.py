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
from typing import Optional

from lawrag.core.rag import tuples as tuples_mod
from lawrag.core.rag.index import norm

log = logging.getLogger("lawrag.core.rag.promote")

MEMORY_MIN_COS = 0.80      # 질문 기억 문턱 — 같은 사안 유형이면 넘고, 주제만 같으면 못 넘는 자리
MEMORY_MAX = 4             # 직행으로 여는 좌표 상한
_qvec_cache: dict = {}     # 활성 행 질문 → 임베딩 (원장 mtime 으로 무효화)


# ---------------------------------------------------------------- 원장 읽기·쓰기
def _load() -> list[dict]:
    p = tuples_mod.candidates_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("candidates", [])
    except Exception:
        return []


def _save(rows: list[dict]) -> None:
    p = tuples_mod.candidates_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"candidates": rows}, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def queue(status: str = "잠정") -> list[dict]:
    """승인 큐 — 증거가 많은 것부터 (재발 횟수 → 최근)."""
    rows = [r for r in _load() if (r.get("status") or "잠정") == status]
    rows.sort(key=lambda r: (-int(r.get("count", 0)), r.get("last", "")), reverse=False)
    return rows


def set_status(qkey: str, doc_id: str, node, status: str, note: str = "") -> bool:
    """잠정 ↔ 활성 ↔ tombstone. 적었으면 True. 상태 변경 이력을 행에 남긴다."""
    if status not in ("잠정", "활성", "tombstone"):
        raise ValueError(f"모르는 상태: {status}")
    rows = _load()
    hit = False
    for r in rows:
        if r.get("qkey") == qkey and r.get("doc_id") == doc_id and r.get("node") == node:
            r["status"] = status
            r.setdefault("이력", []).append({"ts": tuples_mod._now(), "status": status,
                                            "메모": note[:120]})
            hit = True
    if hit:
        _save(rows)
        _qvec_cache.clear()
    return hit


def approve(qkey: str, doc_id: str, node, note: str = "") -> bool:
    return set_status(qkey, doc_id, node, "활성", note)


def reject(qkey: str, doc_id: str, node, note: str = "") -> bool:
    return set_status(qkey, doc_id, node, "tombstone", note)


def active() -> list[dict]:
    return [r for r in _load() if r.get("status") == "활성"]


# ---------------------------------------------------------------- 소비자 ① 질문 기억
def direct_hits(question: str, cap: int = MEMORY_MAX,
                min_cos: float = MEMORY_MIN_COS) -> list[dict]:
    """활성 원장에서 이 질문에 닿는 좌표 — [{doc_id, node, via, why, score}].
    ① 정규형 완전일치 → score 1.0  ② 질문 임베딩 코사인 ≥ 문턱.
    임베딩이 없으면 ①만 — 결정론 부분은 언제나 돈다."""
    rows = active()
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
            import numpy as np
            if embedding.available():
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
        except Exception as exc:                          # pragma: no cover
            log.debug("질문 기억 임베딩 생략 — %s", exc)
    ranked = sorted(out.values(), key=lambda x: -x["score"])
    return ranked[:cap]
