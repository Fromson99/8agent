"""검색 벡터 단 — 미리 임베딩한 구역 위에서 질의 코사인 (하이브리드의 반쪽).

결정 변경 기록 (2026-08-10): 용어 기반 동작은 그대로다 — 벡터는 용어 단
(정확·부분)이 빗나간 뒤 렉시컬 본문 검색과 **융합(RRF)** 되는 후순위 단이고,
용어가 아직 태어나지 않은 초반의 회수를 위한 대비다. 벡터가 찾은 착지는
승격 후보로 적재된다(lawrag/api/routers/rag.py) — 벡터 히트는 용어의 씨앗이다.

이 모듈은 core.terms 를 import 하지 않는다(아키텍처 테스트가 강제). 구역
벡터의 컴파일은 lawrag/core/terms/embed_sections.py 의 일이고, 여기는 그 산출
파일을 읽고 질의 하나를 임베딩할 뿐이다. 모델·색인·numpy 가 없으면 전부
조용히 빠진다 — 렉시컬 사다리는 언제나 돈다.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from lawrag.core.rag.index import store_path
from lawrag.core.rag.controls import value as control_value

log = logging.getLogger("lawrag.core.rag.vector")

# 코사인 문턱 — BGE-M3 실측에서 무관한 한국어 구역은 0.3대, 관련은 0.5↑.
VECTOR_MIN = float(control_value("entry.vector_cos_min"))
TOPK = 8


def sections_dir() -> Path:
    return Path(os.environ.get("RAG_VECTOR_STORE",
                               store_path().parent / "embeddings" / "sections"))


def backend() -> str:
    """벡터 저장 백엔드. 파일형 정본이 기본이고 Qdrant는 명시 선택만 허용한다."""
    value = os.environ.get("RAG_VECTOR_BACKEND", "file").strip().lower()
    return value if value in ("file", "qdrant") else "file"


class VectorIndex:
    def __init__(self, rows: list[dict], mat) -> None:
        self.rows = rows
        self.mat = mat                      # float32, 정규화됨
        self._masks: dict = {}              # 스코프(frozenset) → 행 마스크 캐시
        self._coordinate_rows: dict[tuple, tuple[int, ...]] | None = None

    def _mask(self, doc_ids: frozenset):
        m = self._masks.get(doc_ids)
        if m is None:
            import numpy as np
            m = np.fromiter((r.get("doc_id") in doc_ids for r in self.rows),
                            dtype=bool, count=len(self.rows))
            if len(self._masks) > 32:       # 스코프는 몇 개 안 된다 — 폭주만 막는다
                self._masks.clear()
            self._masks[doc_ids] = m
        return m

    def search(self, qvec, topk: int = TOPK,
               minimum: float = VECTOR_MIN,
               doc_ids: Optional[frozenset] = None,
               coordinates: Optional[frozenset[tuple]] = None) -> list[tuple]:
        """doc_ids 가 있으면 그 문서의 행만 경쟁한다 — 스코프 밖 행이 상위를
        차지해 topk 를 먹는 일이 없어야 "그 문서들만 대상으로" 가 선다.

        coordinates는 구조·역할 교집합이 이미 만든 허용 좌표다. 이 집합을 먼저
        고정한 뒤 그 안에서만 코사인 순위를 매긴다. Vector가 구조 필터보다 앞서
        전역 후보를 다시 섞지 못하게 하는 검색 불변식이다.
        """
        import numpy as np

        row_positions = None
        if coordinates is not None:
            if self._coordinate_rows is None:
                packed: dict[tuple, list[int]] = {}
                for pos, row in enumerate(self.rows):
                    packed.setdefault(
                        (row.get("doc_id"), row.get("node")), []).append(pos)
                self._coordinate_rows = {
                    key: tuple(values) for key, values in packed.items()
                }
            row_positions = np.asarray(sorted({
                pos for coordinate in coordinates
                for pos in self._coordinate_rows.get(coordinate, ())
            }), dtype=np.int64)
            if doc_ids is not None:
                allowed_docs = frozenset(doc_ids)
                row_positions = np.asarray([
                    pos for pos in row_positions
                    if self.rows[int(pos)].get("doc_id") in allowed_docs
                ], dtype=np.int64)
            if not len(row_positions):
                return []
            sims = self.mat[row_positions] @ qvec
        else:
            sims = self.mat @ qvec
        if doc_ids is not None:
            if row_positions is None:
                sims = np.where(self._mask(frozenset(doc_ids)), sims, -np.inf)
        order = np.argsort(-sims)[:topk]
        out = []
        for local_pos in order:
            s = float(sims[local_pos])
            if s < minimum:
                break
            pos = (int(row_positions[int(local_pos)])
                   if row_positions is not None else int(local_pos))
            r = self.rows[pos]
            out.append((r["doc_id"], r["node"], round(s, 4)))
        return out


_cache: dict = {}


def _query_vector(query: str):
    """같은 요청에서 좌표 집합만 바꿔 반복 검색할 때 질의 임베딩을 재사용한다."""
    from lawrag.core import embedding

    cache = _cache.setdefault("query_vectors", {})
    if query in cache:
        return cache[query]
    value = embedding.encode_one(query)
    if value is None:
        return None
    cache[query] = value
    while len(cache) > 128:
        cache.pop(next(iter(cache)))
    return value


def current() -> Optional[VectorIndex]:
    """색인 로드 (mtime 캐시). 없으면 None — 벡터 단은 빠진다."""
    d = sections_dir()
    npz, meta = d / "vectors.npz", d / "meta.jsonl"
    if not (npz.exists() and meta.exists()):
        return None
    sig = (npz.stat().st_mtime_ns, meta.stat().st_mtime_ns)
    if _cache.get("sig") != sig:
        try:
            import numpy as np

            rows = [json.loads(x) for x in
                    meta.read_text(encoding="utf-8").splitlines()]
            mat = np.load(npz)["v"].astype(np.float32)
            if len(rows) != len(mat):
                log.warning("벡터 색인 불일치 — meta %d행, 행렬 %d행: %s",
                            len(rows), len(mat), d)
                return None
            _cache["index"] = VectorIndex(rows, mat)
            _cache["sig"] = sig
            log.info("벡터 색인 로드 — %d행: %s", len(rows), d)
        except Exception as exc:
            log.warning("벡터 색인 로드 실패 — 벡터 단은 빠진다: %s", exc)
            return None
    return _cache.get("index")


def search(query: str, topk: int = TOPK,
           doc_ids: Optional[frozenset] = None,
           coordinates: Optional[frozenset[tuple]] = None,
           minimum: float = VECTOR_MIN) -> list[tuple]:
    """질의 → [(doc_id, node, cosine)]. 어떤 이유로든 못 하면 빈 목록 —
    호출부(search.py)는 벡터가 '없다'와 '못 한다'를 구별할 필요가 없다.
    doc_ids 는 질의 스코프(Index.scope) — 진입은 그 안에서만."""
    from lawrag.core import embedding
    from lawrag.core.rag import switches as switches_mod

    if not switches_mod.is_on("vector_entry"):
        return []

    if not embedding.available():
        log.debug("임베딩 모델 없음 — 벡터 단 생략")
        return []
    qv = _query_vector(query)
    if qv is None:
        log.debug("질의 임베딩 실패 — 벡터 단 생략")
        return []
    if backend() == "qdrant":
        try:
            from lawrag.core.rag import qdrant_store
            out = qdrant_store.search(qv, topk=topk, doc_ids=doc_ids,
                                      coordinates=coordinates, minimum=minimum)
        except Exception as exc:
            log.warning("Qdrant 검색 실패 — 벡터 단은 빠진다: %s", exc)
            return []
    else:
        idx = current()
        if idx is None:
            log.debug("벡터 색인 없음 — 벡터 단 생략")
            return []
        out = idx.search(qv, topk=topk, doc_ids=doc_ids,
                         coordinates=coordinates, minimum=minimum)
    log.debug("벡터 검색 '%s' → %d건 (문턱 %.2f)", query[:40], len(out), VECTOR_MIN)
    return out
