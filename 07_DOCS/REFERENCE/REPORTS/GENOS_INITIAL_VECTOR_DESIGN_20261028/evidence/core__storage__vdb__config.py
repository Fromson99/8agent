"""VDB 도메인 설정 — 임베더를 무엇으로 쓸지 환경변수에서 고른다.

벡터는 Dataiku 가 적재한 오라클 벡터 표에 있고 검색은 `oracle_search.py` 가 한다.
이 파일은 **질의가 쓸 임베더를 고르는 일**만 한다.

임베딩은 VDB 도메인의 관심사라 여기서 고른다(genos | local | none) — 온프렘에서는
GenOS 게이트웨이 뒤의 임베딩 서빙을 부르고, 맥에서 시험할 때는 프로세스에 모델을
올린다. 무엇을 고르는가는 `resolve_embedder()` 의 설명을 보라.
"""
from __future__ import annotations

import os
from functools import lru_cache


_EMBEDDERS = ("genos", "local")
# 옛 이름. 로컬 임베더가 bge-m3 만 올리던 시절의 값이라 설정 파일에 남아 있을 수 있다.
# ⚠ 이 이름은 **로컬 임베더를 고른다는 뜻일 뿐** 모델을 bge-m3 로 고정하지 않는다.
#   어느 모델을 올릴지는 LOCAL_EMBED_MODEL 이 정하고 기본은 KURE-v1 이다 — 옛 이름을
#   그대로 둔 설정은 이름과 실제 모델이 어긋나므로 EMBEDDER=local 로 고쳐 적어라.
_EMBEDDER_ALIASES = {"bge-m3": "local", "bge_m3": "local"}


def genos_embed_configured() -> bool:
    """GenOS 임베딩을 부를 수 있는 설정이 다 있는가. 하나라도 비면 부르지 않는다.

    토큰을 따로 안 주면 LLM 것을 쓴다 — 같은 게이트웨이의 서빙이라 토큰 한 벌로
    둘 다 부르는 배포가 흔하다.
    """
    return bool(os.getenv("GENOS_URL", "").strip()
                and os.getenv("GENOS_EMBED_ID", "").strip()
                and _embed_token())


def _embed_token() -> str:
    return (os.getenv("GENOS_EMBED_TOKEN", "").strip()
            or os.getenv("GENOS_LLM_TOKEN", "").strip())


class EmbedderNotConfigured(ValueError):
    """어느 임베더를 쓸지 정해지지 않았다 — 짐작하지 않고 여기서 멈춘다."""


def resolve_embedder(name: str | None = None) -> str:
    """어느 임베더를 쓸지 — `genos` | `local` | `none`.

    ```text
    EMBEDDER
     ├─ genos   → GenOS 게이트웨이 뒤의 임베딩 서빙 (온프렘 정본)
     ├─ local   → 이 프로세스에 모델을 올린다 (맥에서 시험할 때, 수 GB)
     │            어느 모델인지는 LOCAL_EMBED_MODEL 이 정한다 (기본 KURE-v1)
     ├─ none    → 벡터 없이 BM25 키워드 검색만
     └─ auto(기본)
          ├─ GENOS_URL·GENOS_EMBED_ID·토큰이 다 있다 → genos
          └─ 아니면                                  → 실패
    ```

    **`auto` 가 로컬로 내려가지 않는 이유.** 예전에는 GenOS 설정이 없으면 조용히 로컬
    bge-m3 로 돌았다. 적재된 벡터가 bge-m3 라 "없는 것보다 낫다" 는 판단이었는데, 적재
    임베딩을 다른 모델(예: KURE-v1)로 바꾸는 순간 그 전제가 깨진다.

    **이 사고는 차원 검증으로 안 잡힌다.** KURE-v1 은 bge-m3 를 파인튜닝한 모델이라
    둘 다 1024차원이다. 좌표계만 다르고 길이는 같아서, 설정 하나가 빠진 채로 배포되면
    에러 없이 검색 결과만 엉뚱해진다 — 가장 찾기 어려운 실패다. 그래서 짐작하지 않고
    멈춘다. 로컬 모델을 쓰려면 `EMBEDDER=local` 이라고 적으면 된다.
    """
    raw = (name or os.getenv("EMBEDDER", "auto") or "auto").strip().lower()
    raw = _EMBEDDER_ALIASES.get(raw, raw)
    if raw in ("none", "", "off", "bm25"):
        return "none"
    if raw == "auto":
        if genos_embed_configured():
            return "genos"
        raise EmbedderNotConfigured(
            "EMBEDDER=auto 인데 GenOS 임베딩 설정이 비어 있다 "
            "(GENOS_URL·GENOS_EMBED_ID·GENOS_EMBED_TOKEN). 적재 벡터와 다른 모델로 "
            "조용히 내려가지 않는다 — EMBEDDER 를 genos·local·none 중 하나로 적어라."
        )
    if raw not in _EMBEDDERS:
        raise ValueError(
            f"알 수 없는 EMBEDDER: {raw!r} ({'|'.join(_EMBEDDERS)}|none|auto)")
    return raw


def build_embedder(name: str | None = None):
    """EMBEDDER 환경변수(genos|local|none|auto)로 임베더를 만든다.

    None 이면 벡터 없이 저장·검색한다(BM25 키워드 검색만).
    """
    choice = resolve_embedder(name)
    if choice == "none":
        return None
    if choice == "genos":
        from .embedder import GenOSEmbedder
        return GenOSEmbedder(
            base_url=os.getenv("GENOS_URL", "").strip(),
            serving_id=os.getenv("GENOS_EMBED_ID", "").strip(),
            token=_embed_token(),
            model=os.getenv("GENOS_EMBED_MODEL", "").strip(),
            # 적재된 벡터·컬렉션 색인과 같아야 한다. bge-m3·KURE-v1 둘 다 1024차원이다.
            dim=int(os.getenv("GENOS_EMBED_DIM", "1024")),
            batch_size=int(os.getenv("GENOS_EMBED_BATCH", "32")),
            timeout=float(os.getenv("GENOS_EMBED_TIMEOUT_SECONDS", "120")),
            max_retries=int(os.getenv("GENOS_EMBED_MAX_RETRIES", "3")),
        )
    from .embedder import LocalEmbedder
    return LocalEmbedder()


@lru_cache(maxsize=1)
def process_embedder():
    """질의 임베더 — 프로세스에 **한 번만** 올린다. EMBEDDER=none 이면 None.

    `build_deps` 가 요청마다 의존성을 새로 만들기 때문에(api/query.py), 임베더를
    리트리버 인스턴스에 두면 요청마다 수 GB 를 다시 올린다. 적재(전처리기)와 질의가
    같은 모델을 써야 하므로 캐시도 여기 한 곳에 둔다.
    """
    return build_embedder()
