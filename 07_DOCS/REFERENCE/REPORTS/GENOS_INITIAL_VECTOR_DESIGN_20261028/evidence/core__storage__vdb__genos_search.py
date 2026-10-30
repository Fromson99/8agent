"""GenOS 벡터 DB 검색 — core.query.retrieval.ChunkRetriever 구현.

## 무엇을 하나

적재는 GenOS 전처리기가 하고 색인도 GenOS 가 한다. 그 컬렉션을 질의가 검색하는
자리가 여기다.

```text
GenOS 전처리기 (preprocessor/adapter.py) → GenOS 임베딩·색인 → GenOS VDB → 이 파일 (URL 호출)
```

읽는 창(`genos_vdb.py`)은 **조건으로 골라 읽기**만 해서 질의에 쓸 수 없다. 여기서
벡터·키워드 검색을 붙인다.

## 세 가지 검색을 다 한다 — 다만 키워드는 배포를 탄다

`vector` · `keyword` · `hybrid` 를 모두 받는다(`RETRIEVAL_SEARCH_TYPE` 이 고른다).

키워드(BM25)에는 조건이 하나 붙는다. **본문이 평문으로 색인돼 있어야 한다.** GenOS 는
본문을 AES-256-GCM 으로 암호화해 넣는 배포가 있고, 그런 컬렉션에서는 BM25 가 암호문을
토큰으로 잡아 한국어 질문이 영영 안 걸린다 — 오류가 아니라 **0건**이라 "문서에 근거가
없다" 로 읽힌다.

**그래서 코드가 미리 단정하지 않는다.** 평문으로 들어 있는 배포도 있고(`is_encrypted`
가 false 인 경우), 어느 쪽인지는 컬렉션을 열어 봐야 안다. 대신 검색 결과의 본문이
암호문으로 보이면 그때 경고를 남긴다(`_warn_if_encrypted`) — 짐작이 아니라 실측으로
말한다. 온프렘 기본값을 `vector` 로 두는 이유도 그것이지, 다른 방식이 안 되어서가
아니다.

## 질의 벡터는 적재를 한 그 서빙이 만들어야 한다

전처리기는 **GenOS 임베딩 서빙**으로 벡터를 만들어 넣었다. 질의도 같은 서빙이어야
좌표계가 맞는다 — `EMBEDDER=genos` 와 `GENOS_EMBED_ID` 를 적재 때와 같게 둔다.
다른 모델을 쓰면 차원이 같아도(1024) 오류 없이 엉뚱한 청크만 올라온다.

## 우리 스키마로 옮겨 준다

문서·청크를 잇는 키는 전처리기가 `document_id`·`chunk_id` 속성으로 실어 보낸 값이다
(`genos_vdb.DOCUMENT_KEY`). **`file_hash` 를 쓰면 안 된다** — GenOS 가 자기 값으로
덮는 자리라 그것으로 좁히면 언제나 0건이다.

`content_hash` 자리는 GenOS 컬렉션에 없다. 우리 싱크와 같은 방법(본문 SHA-256)으로
다시 계산한다 — 대조의 기준은 어차피 **내용**이다.
"""
from __future__ import annotations

import hashlib
import math

from ... import obs
from ...query.errors import RetrievalNotConfigured
from ...query.retrieval import RetrievalFilters, RetrievedChunk
from . import genos_vdb
from .asis import genos
from .http import all_of, equal

# 읽어 올 속성. 본문은 `text` 하나이고 나머지는 근거 표시·필터에 쓰는 값이다.
# chunk_bboxes 같은 큰 자리는 부르지 않는다 — 프롬프트에 들어가지도 않는다.
_PROPERTIES = ("text", "product_code", genos("document_type"), "chunk_type", "section_kind",
               "i_page", "e_page", "i_chunk_on_doc", "is_encrypted",
               "document_id", "chunk_id")

# RetrievalFilters 의 이름 → GenOS 컬렉션의 자리 이름. 지금은 이름이 같지만 상수를
# 거쳐 간다 — 전처리기가 어느 자리에 실어 보내는지가 한 번 바뀐 적이 있다(file_hash).
# BM25 가 볼 속성 — **본문만**. 지정하지 않으면 Weaviate 는 검색 가능한 모든 text 속성을
# 훑는데, 나머지는 식별자·문서유형 같은 자리라 키워드 점수가 망가진다(search.py 와 같은 규율).
_BM25_PROPERTIES = ["text"]

# 후보를 몇 건 받을지는 **호출부가 정한다**(`RETRIEVAL_CANDIDATE_K`). 여기서 검색
# 방식마다 다르게 부풀리지 않는다.
#
# 한때 hybrid·keyword 만 세 배로 받았다(`_HYBRID_OVERFETCH = 3`). 관찰은 맞았다 —
# Weaviate 는 융합 점수로 상위 N 건을 주는데 임계 판정은 코사인으로 하므로
# (core/query/grounding.py — 융합 점수는 정규화 랭킹값이라 절대 임계를 못 건다),
# 상한이 좁으면 BM25 가 끌어올린 청크가 자리를 차지하고 코사인이 높은 청크가 밀린다.
# 실제로 같은 질문에서 vector 는 3건이 임계를 넘어 답이 나왔고 hybrid 는 1건만 남았다
# (두 실행의 top_score 는 0.5259 로 같았다 — 즉 후보에서 잘려 나간 것이다).
#
# 문제는 그 보정을 **구현 안에 숨겨 둔 것**이었다. 같은 `RETRIEVAL_TOP_K=8` 이
# vector 에서는 8건, hybrid 에서는 24건을 뜻해서, 후보를 늘려 볼 때 무엇을 늘리는
# 것인지부터 갈렸다. 이제 후보 수 자체가 설정이라 넉넉히 받고 싶으면 그 값을 올린다 —
# 여기서 한 번 더 곱하면 24 로 맞춘 설정이 72건을 받는다.
_MAX_LIMIT = 100

_FILTER_KEYS = {
    "product_code": "product_code",
    "document_id": genos_vdb.DOCUMENT_KEY,
    "document_type": genos("document_type"),
    "chunk_type": "chunk_type",
    "section_kind": "section_kind",
}

_client = None
_client_key: tuple[str, str] = ("", "")


def _embedder():
    """질의 임베더. 캐시는 `config.process_embedder` 에 있다 — ElsChunk 검색과 같은 것을 쓴다."""
    from .config import process_embedder
    return process_embedder()


def _connection(cfg):
    """URL 창구를 프로세스에서 재사용한다.

    연결을 붙들지는 않지만(urllib) **벡터 자리를 물어본 결과**를 들고 있다. 요청마다
    새로 만들면 그 확인 호출이 요청마다 한 번씩 더 나간다.
    """
    global _client, _client_key
    key = (cfg.http_url, cfg.token)
    if _client is None or _client_key != key:
        _client = genos_vdb.open_genos_vdb(cfg)
        _client_key = key
    return _client


def _where(filters: RetrievalFilters):
    """RetrievalFilters → GraphQL where. 값이 없는 항목은 조건에서 뺀다."""
    return all_of([equal(_FILTER_KEYS[name], value)
                   for name, value in filters.to_dict().items()
                   if name in _FILTER_KEYS])


def _cosine(query_vector, stored) -> float | None:
    """임계 판정용 코사인. hybrid 는 거리를 주지 않아 직접 잰다.

    정규화를 가정하지 않고 크기로 나눈다 — 적재 벡터를 만든 것이 GenOS 임베딩 서빙이라
    L2 정규화가 돼 있는지 우리가 보증할 수 없다. 정규화돼 있으면 내적과 같은 값이다.
    """
    if not query_vector or not stored:
        return None
    dot = sum(float(a) * float(b) for a, b in zip(query_vector, stored))
    qa = math.sqrt(sum(float(a) * float(a) for a in query_vector))
    sa = math.sqrt(sum(float(b) * float(b) for b in stored))
    if qa == 0 or sa == 0:
        return None
    return dot / (qa * sa)


def _warn_if_encrypted(chunks: list[RetrievedChunk], search_type: str) -> None:
    """본문이 암호문으로 올라왔나 — BM25 가 무의미한 배포라는 뜻이다.

    이 상태에서는 인용 대조가 전부 실패해 답변이 나가지 않으므로 **틀린 답이 나가지는
    않는다.** 다만 왜 안 나오는지가 안 보이니 로그로 말해 준다. 복호화 키가 어긋난
    경우도 같은 얼굴이라 둘을 함께 짚는다.
    """
    if not chunks:
        return
    bad = [c.chunk_id for c in chunks if genos_vdb.looks_encrypted(c.text)]
    if not bad:
        return
    # 복호화 패키지가 없으면 decrypt() 가 조용히 암호문을 돌려줘 키가 틀린 것과 같은 얼굴이 된다 — 갈라 말한다.
    crypto = genos_vdb.crypto_available()
    hint = ("본문이 암호문 그대로다 — 복호화 패키지(cryptography)가 이 실행 환경에 없다. "
            "코드 스페이스는 pip install cryptography==50.0.1, 코드서빙은 부팅 로그 deps 의 "
            "filled · failed 를 볼 것" if not crypto else
            "본문이 암호문 그대로다 — 복호화 키(GENOS_VDB_SECRET·GENOS_VDB_SALT)가 "
            "어긋났거나 이 배포가 암호화 색인이다. 후자면 keyword·hybrid 는 0건에 "
            "가깝다(BM25 가 암호문을 훑는다) — RETRIEVAL_SEARCH_TYPE=vector 로 둬라.")
    obs.bind(obs.get_logger("query.retrieval")).event(
        "genos_vdb.encrypted_body", level=30, search_type=search_type,
        n_encrypted=len(bad), n_results=len(chunks), chunk_ids=bad[:5],
        cryptography=crypto, hint=hint)


def _to_chunk(row: dict, query_vector=None) -> RetrievedChunk:
    """GenOS 객체 하나 → RetrievedChunk.

    본문은 복호화해서 싣는다. 복호화가 안 되는 배포에서는 받은 값이 그대로 오는데
    (`genos_vdb.decrypt`), 그 경우 인용 대조가 전부 실패하므로 답변이 나가지 않는다 —
    암호문이 근거로 붙는 일은 없다.
    """
    text = genos_vdb.decrypt(row.get("text") or "")
    if not isinstance(text, str):
        text = str(text)
    document_id = str(row.get(genos_vdb.DOCUMENT_KEY) or "")
    page_start = row.get("i_page")
    distance = row.get("_distance")
    return RetrievedChunk(
        # 전처리기가 chunk_id 를 실어 보낸다. 없으면 문서 안 순번으로 대신한다
        # (genos_vdb._row 와 같은 규칙 — 덤프와 검색이 같은 이름을 불러야 한다).
        chunk_id=str(row.get("chunk_id")
                     or f"{document_id or '?'}#{row.get('i_chunk_on_doc')}"),
        document_id=document_id,
        text=text,
        # 점수를 둘로 나눠 싣는다 — 순위용(hybrid 융합값·BM25)과 임계 판정용(코사인).
        # nearVector 는 거리를 주고, hybrid 는 안 주는 대신 저장 벡터를 같이 받는다.
        score=row.get("_score"),
        vector_similarity=((1.0 - distance) if distance is not None
                           else _cosine(query_vector, row.get("_vector"))),
        document_type=row.get(genos("document_type")),
        chunk_type=row.get("chunk_type"),
        section_kind=row.get("section_kind"),
        page_start=page_start,
        page_end=row.get("e_page") or page_start,
        # GenOS 에는 해시 자리가 없다. 우리 싱크가 쓰는 것과 같은 방법(본문 SHA-256)으로
        # 다시 계산해 둔다 — 적재분과 대조할 때 같은 값이 나온다.
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


class GenOSVdbChunkRetriever:
    """GenOS 전처리기가 적재한 컬렉션을 검색한다 — vector · keyword · hybrid.

    설정이 덜 찼을 때는 `RetrievalNotConfigured` 로 올린다 — 분류되지 않은 예외로
    새어 나가면 응답에 `INTERNAL_ERROR` 만 남고 무엇이 비었는지가 사라진다.
    """

    backend = "genos"

    def __init__(self, search_type: str = "vector", hybrid_alpha: float = 0.5):
        # 검색 방식은 만들 때 받는다 — 검색기 규약(ChunkRetriever.search)이 방식을 받지 않는다
        # (오라클 검색기와 같은 모양, core/query/retrieval.py).
        self.search_type = search_type
        self.hybrid_alpha = hybrid_alpha

    def search(self, query: str, filters: RetrievalFilters, *, candidate_k: int) -> list[RetrievedChunk]:
        search_type, hybrid_alpha = self.search_type, self.hybrid_alpha
        if search_type not in ("vector", "keyword", "hybrid"):
            raise RetrievalNotConfigured(f"지원하지 않는 검색 방식이다: {search_type!r}")

        cfg = genos_vdb.GenOSVdbConfig.from_env()
        problem = cfg.problem()
        if problem:
            raise RetrievalNotConfigured(problem)
        if not cfg.configured:
            raise RetrievalNotConfigured(
                f"GenOS 벡터 DB 설정이 비어 있다 — {', '.join(cfg.missing())}. "
                "컬렉션 이름이 곧 그 VDB 의 인증키다(GenOS 화면의 벡터 DB 상세).")

        # keyword 는 임베더 없이 돈다. vector·hybrid 는 **적재를 한 그 서빙**이어야
        # 좌표계가 맞는다 — 다른 모델이면 오류 없이 엉뚱한 청크만 올라온다.
        vector = None
        if search_type in ("vector", "hybrid"):
            embedder = _embedder()
            if embedder is None:
                raise RetrievalNotConfigured(
                    f"EMBEDDER=none 이라 {search_type} 검색을 할 수 없다 — 적재를 한 그 "
                    "임베딩 서빙으로 EMBEDDER=genos·GENOS_EMBED_ID 를 맞추거나, "
                    "RETRIEVAL_SEARCH_TYPE=keyword 로 바꿔라.")
            vector = embedder.embed([query])[0]

        client = _connection(cfg)
        # 세 방식이 **같은 수**를 받는다. 방식을 바꿔도 후보 수가 따라 바뀌지 않아야
        # 검색 품질 비교에서 무엇이 달라진 것인지 가릴 수 있다.
        limit = min(candidate_k, _MAX_LIMIT)
        common = {"properties": list(_PROPERTIES), "where": _where(filters)}

        if search_type == "vector":
            rows = client.search(cfg.collection, vector=vector, limit=limit, **common)
        else:
            # keyword 는 alpha=0 인 hybrid 다 — Weaviate 가 그 자리에서 BM25 만 쓴다.
            # 호출을 하나로 두면 두 방식이 같은 필터·같은 속성 목록을 쓰는 것이 보장된다.
            rows = client.hybrid(
                cfg.collection, query=query, vector=vector,
                alpha=hybrid_alpha if search_type == "hybrid" else 0.0,
                bm25_properties=_BM25_PROPERTIES, limit=limit, **common)

        chunks = [_to_chunk(row, vector) for row in rows]
        _warn_if_encrypted(chunks, search_type)
        return chunks
