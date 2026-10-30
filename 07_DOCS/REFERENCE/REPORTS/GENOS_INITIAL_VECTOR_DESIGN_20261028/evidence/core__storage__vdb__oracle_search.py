"""오라클 벡터 표 검색 — core.query.retrieval.ChunkRetriever 구현(`RETRIEVAL_BACKEND=ords`, vector · hybrid).

## 무엇을 하나

Dataiku 임베딩 레시피가 조각과 벡터를 오라클 벡터 표(매핑의 `vdb_chunk` — dev 는 `SIDDS.ELS_QA_VDB_CHUNK_S`)에 쓴다. 질의는 그
표에서 질문과 가까운 조각을 찾는다. 코드서빙은 오라클에 직접 붙지 못하므로 상품 조회와 같은 ORDS
읽기 연결(`core/storage/ords_conn.py`)로 SQL 한 문장을 보낸다.

```text
질문 → 질의 임베딩(EMBEDDER=genos) → 벡터 글자 → SELECT … VECTOR_DISTANCE … FETCH FIRST k → 조각
```

## hybrid — 벡터 후보는 그대로, 키워드 후보를 더한다

키워드(BM25) 검색은 Oracle Text 색인이 있어야 하는데 그 색인이 없다. 그래서 hybrid 는 **같은 SQL
한 번**으로 상품의 조각을 전부 거리순으로 받아, 키워드 점수는 코드서빙에서 센다(`keyword.py`).

```text
vector : 거리순 상위 candidate_k 행만 받는다
hybrid : 상품의 조각 전부를 거리순으로 받는다(SQL 한 번 · 임베딩 한 번 — vector 와 같다)
          ├─ 거리순 상위 candidate_k        ← vector 와 똑같은 후보, 순서도 그대로
          └─ BM25 상위 keyword_k 중 위에 없는 것을 뒤에 더한다
```

**합치는 방식은 합집합이다 — RRF 로 다시 줄 세워 자르지 않는다.** 융합 순위로 상위 k 를 자르면
키워드 점수가 끌어올린 조각이 자리를 채워 코사인이 높은 조각이 잘린다(GenOS hybrid 때 실제로 겪었고
후보를 세 배로 받아 버텼다). 합집합이면 vector 가 찾은 후보는 하나도 빠지지 않는다. 뒤의 판정
(`grounding.apply_threshold`)은 순서와 무관하게 코사인으로 가르고 코사인 순으로 자리에 앉히므로,
더한 조각은 코사인이 임계를 넘거나 질문의 말이 원문에 그대로 있을 때(`keyword_hits`) 남는 자리에
들어간다 — 벡터 근거를 밀어내지 않는다. 더한 조각도 거리를 함께 받았으므로 코사인이 있다.

상품 필터가 없으면 표 전체를 받게 되므로 hybrid 라도 vector 로 찾고 그 사실을 남긴다. 한 상품의
조각이 `_SCAN_MAX` 를 넘으면 거리순 앞쪽만 세고 경고를 남긴다.

## 질의 벡터는 글자로 싣는다

ORDS 바인드는 VARCHAR2 로 가서 4000바이트를 넘는 1024차원 벡터를 담지 못한다. Dataiku 적재와
같은 방법으로 `TO_VECTOR(TO_CLOB('[…]') || …, 1024, FLOAT32)` 글자를 문장에 넣는다(값은 우리가 만든
숫자뿐이라 따옴표가 섞일 일이 없다). 필터 값(상품코드 등)은 바인드로 보낸다.

## 점수

`VECTOR_DISTANCE(…, COSINE)` 는 1 − 코사인 유사도다.
`vector_similarity = 1 − distance` 로 옮기면 임계(`RETRIEVAL_SCORE_THRESHOLD`)를 그대로 쓴다.

## 하지 않는 것

active 문서 거르기는 여기서 하지 않는다 — 검색 뒤 `answer._keep_active` 가 적재 표(SIDDA)에서
확인한다. 두 스키마를 한 문장에서 묶지 않아도 되고, 확인 실패 시 전부 버리는 규율도 한 곳에 남는다.
"""
from __future__ import annotations

import math
import time

from ... import obs
from ...query.errors import RetrievalNotConfigured
from ...query.retrieval import RetrievalFilters, RetrievedChunk
from ..ords import OrdsError
from . import keyword, vdb_schema

# 문장 안 글자 조각 한도. 오라클 리터럴 하나는 4000바이트까지라 여유를 둔다(els_dku/sql.py 와 같은 값).
_PIECE = 3900
_MAX_LIMIT = 100
# hybrid 가 한 상품에서 키워드를 셀 조각 수 상한. 한 상품은 수백 건 안쪽이라 여기 닿으면 이상 신호다.
_SCAN_MAX = 2000

# RetrievalFilters 의 이름 → 벡터 표 열(vdb_schema.py). 바인드 이름은 왼쪽을 그대로 쓴다.
_FILTER_COLUMNS = {
    "product_code": "prdt_code",
    "document_id": "doc_id",
    "document_type": "doc_type",
    "chunk_type": "chnk_type",
    "section_kind": "section_kind",
}

# 끝 쪽은 메타 JSON 에만 있다(검증 도구의 verify.chunks.vdb 와 같은 읽기). 0 은 "모름" 이다.
# 표 열 이름(사내 표준)을 안쪽 SELECT 에서 별칭으로 코드의 이름(chunk_id …)에 옮긴다 — _to_chunk 는 그 이름으로 읽는다.
_SQL = """
SELECT chunk_id, document_id, document_type, chunk_type, section_kind, page_start, page_end,
       chunk_content_hash, embedding_model, text, distance
  FROM (SELECT chnk_id AS chunk_id, doc_id AS document_id, doc_type AS document_type,
               chnk_type AS chunk_type, section_kind,
               page_no AS page_start,
               NULLIF(JSON_VALUE(chnk_meta_ctnt, '$.e_page' RETURNING NUMBER), 0) AS page_end,
               chnk_ctnt_hash AS chunk_content_hash, embd_mdl_name AS embedding_model,
               embd_txt_ctnt AS text,
               VECTOR_DISTANCE(embd_vctr, TO_VECTOR({vector}, {dim}, FLOAT32), COSINE) AS distance
          FROM els_vdb_chunk
         WHERE {where})
 ORDER BY distance
 FETCH FIRST {limit} ROWS ONLY
"""

_conn = None


def _embedder():
    """질의 임베더 — 프로세스에 하나(`config.process_embedder`)."""
    from .config import process_embedder
    return process_embedder()


def _connection(fresh: bool = False):
    """ORDS 읽기 연결을 프로세스에서 재사용한다. 코드 스페이스의 원격 읽기는 등록된 조회만 보내므로 쓰지 않는다.

    `fresh` 면 쥐고 있던 연결을 버리고 새로 연다 — 인증이 만료된 연결을 계속 쓰지 않게.
    """
    global _conn
    if fresh:
        _conn = None
    if _conn is None:
        from ..ords_conn import open_ords
        try:
            _conn = open_ords(allow_remote=False)
        except OrdsError as exc:
            raise RetrievalNotConfigured(f"오라클 벡터 표를 읽을 ORDS 연결이 없다 — {exc}") from exc
    return _conn


def vector_literal(vector, dim: int = vdb_schema.EMBED_DIM) -> str:
    """질의 벡터 → `TO_CLOB('[…]') || …` 글자. 차원이 표와 다르거나 NaN · 무한대가 있으면 멈춘다."""
    if len(vector) != dim:
        raise RetrievalNotConfigured(
            f"질의 벡터 차원이 {len(vector)} 이다 — 벡터 표는 {dim} 차원이다. "
            "적재(Dataiku LLM Mesh)와 같은 임베딩 모델로 GENOS_EMBED_ID 를 맞출 것")
    values = []
    for v in vector:
        v = float(v)
        if math.isnan(v) or math.isinf(v):
            raise RetrievalNotConfigured("질의 벡터에 NaN · 무한대가 있다 — 임베딩 서빙 응답을 확인할 것")
        values.append("%.8g" % v)
    text = "[" + ",".join(values) + "]"
    return " || ".join("TO_CLOB('%s')" % text[i:i + _PIECE] for i in range(0, len(text), _PIECE))


def build_sql(vector, filters: RetrievalFilters, limit: int) -> tuple[str, dict]:
    """(SQL, 바인드). 필터는 값이 있는 것만 조건에 넣는다."""
    binds = {name: value for name, value in filters.to_dict().items() if name in _FILTER_COLUMNS}
    where = " AND ".join(f"{_FILTER_COLUMNS[name]} = :{name}" for name in binds) or "1 = 1"
    sql = _SQL.format(vector=vector_literal(vector), dim=vdb_schema.EMBED_DIM,
                      where=where, limit=int(limit))
    return sql, binds


def _int(value):
    return None if value is None else int(value)


def _text(value) -> str:
    read = getattr(value, "read", None)
    if callable(read):
        value = read()
    return "" if value is None else str(value)


def _to_chunk(row: dict) -> RetrievedChunk:
    distance = row.get("distance")
    page_start = _int(row.get("page_start"))
    return RetrievedChunk(
        chunk_id=str(row["chunk_id"]),
        document_id=str(row.get("document_id") or ""),
        text=_text(row.get("text")),
        # vector 검색은 순위 점수와 임계 점수가 같다 — GenOS nearVector 처럼 score 는 비워 둔다.
        score=None,
        vector_similarity=None if distance is None else 1.0 - float(distance),
        document_type=row.get("document_type"),
        chunk_type=row.get("chunk_type"),
        section_kind=row.get("section_kind"),
        page_start=page_start,
        page_end=_int(row.get("page_end")) or page_start,
        content_hash=row.get("chunk_content_hash"),
    )


def _run(conn, sql: str, binds: dict) -> tuple[list[str], list[dict]]:
    cur = conn.cursor()
    cur.execute(sql, binds)
    columns = [d[0].lower() for d in cur.description or []]
    return columns, [dict(zip(columns, row)) for row in cur.fetchall()]


class OracleVdbChunkRetriever:
    """Dataiku 가 적재한 오라클 벡터 표를 ORDS 로 검색한다 — vector, 또는 vector + 키워드 보강(hybrid)."""

    backend = "ords"

    def __init__(self, conn=None, *, search_type: str = "vector", keyword_k: int = 8):
        self._conn = conn
        self.search_type = search_type
        self.keyword_k = keyword_k

    def search(self, query: str, filters: RetrievalFilters, *, candidate_k: int) -> list[RetrievedChunk]:
        embedder = _embedder()
        if embedder is None:
            raise RetrievalNotConfigured(
                "EMBEDDER=none 이라 vector 검색을 할 수 없다 — EMBEDDER=genos · GENOS_EMBED_ID 를 맞출 것")
        vector = embedder.embed([query])[0]
        candidate_k = min(candidate_k, _MAX_LIMIT)
        # 키워드는 상품 안에서만 센다 — 필터가 없으면 표 전체를 받게 되므로 vector 로 찾는다.
        hybrid = self.search_type == "hybrid" and bool(filters.product_code)
        sql, binds = build_sql(vector, filters, _SCAN_MAX if hybrid else candidate_k)

        started = time.perf_counter()
        conn = self._conn or _connection()
        try:
            _, rows = _run(conn, sql, binds)
        except OrdsError as exc:
            # 접속 · 인증 쪽 실패(401 · 403 · 네트워크 — code 2)면 쥐고 있던 연결을 버리고 한 번만 다시 연다.
            # 프로세스 내내 한 연결을 쓰므로 토큰이 만료되면 이 자리에서 드러난다. SQL 오류(code 1)는 그대로 올린다.
            if self._conn is not None or exc.code != 2:
                raise
            obs.bind(obs.get_logger("query.retrieval")).event(
                "retrieval.ords_reconnect", level=30, reason=str(exc)[:200])
            conn = _connection(fresh=True)
            _, rows = _run(conn, sql, binds)
        chunks = [_to_chunk(row) for row in rows]
        picked, added = (_with_keyword(query, chunks, candidate_k, self.keyword_k) if hybrid
                         else (chunks[:candidate_k], 0))
        # 어느 표를 읽었고 그 조각이 어느 모델로 임베딩됐는지 — 질의가 오라클 벡터 표를 탔는지,
        # 질의 임베딩과 적재 임베딩이 같은 모델인지를 로그 한 줄로 확인한다.
        log = obs.bind(obs.get_logger("query.retrieval"))
        log.event(
            "retrieval.ords", table=(conn.mapping.table(vdb_schema.VDB_CHUNK).qualified
                                     if getattr(conn, "mapping", None) else vdb_schema.VDB_CHUNK),
            n_rows=len(rows), elapsed_ms=int((time.perf_counter() - started) * 1000),
            embedding_models=sorted({str(r.get("embedding_model")) for r in rows if r.get("embedding_model")}),
            filters=binds, search_type="hybrid" if hybrid else "vector", n_keyword_added=added)
        if self.search_type == "hybrid" and not hybrid:
            log.event("retrieval.hybrid_skipped", level=30, reason="상품 필터가 없어 vector 로 찾았다")
        if hybrid and len(rows) >= _SCAN_MAX:
            log.event("retrieval.hybrid_scan_capped", level=30, n_rows=len(rows),
                      reason="상품 조각이 상한을 넘어 거리순 앞쪽만 키워드로 셌다")
        return picked


def _with_keyword(query: str, chunks: list[RetrievedChunk], candidate_k: int,
                  keyword_k: int) -> tuple[list[RetrievedChunk], int]:
    """거리순 상위 candidate_k 를 그대로 두고, BM25 상위 keyword_k 중 거기 없는 것을 뒤에 더한다."""
    head = chunks[:candidate_k]
    scores = keyword.bm25(query, [c.text for c in chunks])
    extra = [chunks[i] for i in keyword.top(scores, keyword_k) if i >= candidate_k]
    return head + extra, len(extra)
