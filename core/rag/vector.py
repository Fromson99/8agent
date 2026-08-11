"""검색 벡터 단 — 미리 임베딩한 구역 위에서 질의 코사인 (하이브리드의 반쪽).

결정 변경 기록 (2026-08-10): 용어 기반 동작은 그대로다 — 벡터는 용어 단
(정확·부분)이 빗나간 뒤 렉시컬 본문 검색과 **융합(RRF)** 되는 후순위 단이고,
용어가 아직 태어나지 않은 초반의 회수를 위한 대비다. 벡터가 찾은 착지는
승격 후보로 적재된다(api/routers/rag.py) — 벡터 히트는 용어의 씨앗이다.

이 모듈은 core.terms 를 import 하지 않는다(아키텍처 테스트가 강제). 구역
벡터의 컴파일은 core/terms/embed_sections.py 의 일이고, 여기는 그 산출
파일을 읽고 질의 하나를 임베딩할 뿐이다. 모델·색인·numpy 가 없으면 전부
조용히 빠진다 — 렉시컬 사다리는 언제나 돈다.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from core.rag.index import store_path

log = logging.getLogger("core.rag.vector")

# 코사인 문턱 — BGE-M3 실측에서 무관한 한국어 구역은 0.3대, 관련은 0.5↑.
VECTOR_MIN = float(os.environ.get("RAG_VECTOR_MIN", "0.45"))
TOPK = 8


def sections_dir() -> Path:
    return Path(os.environ.get("RAG_VECTOR_STORE",
                               store_path().parent / "embeddings" / "sections"))


class VectorIndex:
    def __init__(self, rows: list[dict], mat) -> None:
        self.rows = rows
        self.mat = mat                      # float32, 정규화됨

    def search(self, qvec, topk: int = TOPK,
               minimum: float = VECTOR_MIN) -> list[tuple]:
        import numpy as np

        sims = self.mat @ qvec
        order = np.argsort(-sims)[:topk]
        out = []
        for i in order:
            s = float(sims[i])
            if s < minimum:
                break
            r = self.rows[int(i)]
            out.append((r["doc_id"], r["node"], round(s, 4)))
        return out


_cache: dict = {}


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


def search(query: str, topk: int = TOPK) -> list[tuple]:
    """질의 → [(doc_id, node, cosine)]. 어떤 이유로든 못 하면 빈 목록 —
    호출부(search.py)는 벡터가 '없다'와 '못 한다'를 구별할 필요가 없다."""
    from core import embedding

    if not embedding.available():
        log.debug("임베딩 모델 없음 — 벡터 단 생략")
        return []
    idx = current()
    if idx is None:
        log.debug("벡터 색인 없음 — 벡터 단 생략")
        return []
    qv = embedding.encode_one(query)
    if qv is None:
        log.debug("질의 임베딩 실패 — 벡터 단 생략")
        return []
    out = idx.search(qv, topk=topk)
    log.debug("벡터 검색 '%s' → %d건 (문턱 %.2f)", query[:40], len(out), VECTOR_MIN)
    return out
