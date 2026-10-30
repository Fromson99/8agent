"""임베딩 생성 — 텍스트 청크를 벡터로.

**부르는 길이 둘이다.**

| 구현 | 어디서 도나 | 언제 쓰나 |
|---|---|---|
| `GenOSEmbedder` | GenOS 게이트웨이 뒤의 임베딩 서빙 | 온프렘 — 정본 |
| `LocalEmbedder` | 이 프로세스 안 (sentence-transformers) | 맥에서 시험할 때 |

**왜 서빙으로 옮기나.** 로컬 경로는 첫 호출에서 모델을 내려받아 프로세스에 올린다
(수 GB, torch 포함). 온프렘 반입에서 가장 무거운 짐이고, GenOS 가 요청마다 프로세스를
띄우는 구조라면 그 비용을 매번 문다. 게이트웨이 뒤의 서빙을 부르면 우리 쪽에는
HTTP 호출만 남는다.

**차원이 맞아야 한다.** GenOS 가 색인해 둔 벡터가 1024차원이고 컬렉션도 그 차원으로
잡혀 있다. 서빙이 다른 차원을
내면 적재는 거부당하고 검색은 의미가 어긋난다 — 그래서 두 구현 모두 받은 벡터의
길이를 확인하고 다르면 **그 자리에서 실패시킨다.** 조용히 넘기면 "검색은 되는데
엉뚱한 게 올라오는" 상태가 되어 원인을 찾기 어렵다.

**질의 벡터와 적재 벡터는 같은 모델이어야 한다.** 차원이 같아도 좌표계는 다르다 —
bge-m3 와 KURE-v1 은 둘 다 1024차원이지만 서로의 벡터를 이해하지 못한다. 그래서
**차원 검증으로는 이 사고가 안 잡힌다.** 모델을 바꿀 때는 재적재가 함께 가야 한다.

L2 정규화한 벡터를 낸다 → 컬렉션이 코사인 거리로 색인돼 있어서다. 서빙이 정규화해
주지 않는 경우가 있어 받은 쪽에서 한 번 건다.
"""
from __future__ import annotations

import math
import os
from typing import Protocol

from ... import genos


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingError(RuntimeError):
    """임베딩을 얻지 못했다. 호출부는 이걸 잡아 해당 적재·질의를 실패로 남긴다."""


class LocalEmbedder:
    """이 프로세스에 모델을 올려 쓰는 임베딩(sentence-transformers).

    어느 모델을 올릴지는 `LOCAL_EMBED_MODEL` 로 정한다 — 온프렘 서빙에 올라간 모델이
    무엇이든 맥에서 같은 것으로 시험할 수 있어야 하기 때문이다. 기본은 한국어 특화인
    `nlpai-lab/KURE-v1` 이다. 우리 문서가 전부 한글이라 한국어로 파인튜닝된 쪽이
    맞고, 온프렘 서빙에 올릴 모델도 이쪽으로 본다. 예전 기본이던 `BAAI/bge-m3` 를
    쓰려면 그 이름을 적으면 된다(둘 다 1024차원이라 컬렉션 색인은 그대로다).

    **기본을 바꿨다는 것은 이미 적재된 벡터와 좌표계가 달라졌다는 뜻이다.** 차원이
    같아 검증에 걸리지 않으므로, 바꾼 뒤에는 재적재가 함께 가야 한다.

    모델을 바꾸면 **차원을 함께 맞춰야 한다**(`LOCAL_EMBED_DIM`). 첫 임베딩에서 실제로
    나온 길이를 확인하고 다르면 그 자리에서 실패시킨다 — 차원이 어긋난 채로 적재하면
    색인이 거부하거나(적재) 검색이 조용히 엉뚱해진다(질의).
    """

    def __init__(self, model_name: str | None = None, *, dim: int | None = None,
                 batch_size: int = 12):
        self.model_name = (model_name
                           or os.getenv("LOCAL_EMBED_MODEL", "").strip()
                           or "nlpai-lab/KURE-v1")
        self.dim = dim if dim is not None else int(os.getenv("LOCAL_EMBED_DIM", "1024"))
        self.batch_size = batch_size
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer   # 무거운 import — 지연
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._load().encode(
            list(texts),
            normalize_embeddings=True,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        out = [v.tolist() for v in vecs]
        if len(out[0]) != self.dim:
            raise EmbeddingError(
                f"{self.model_name}: 차원이 다르다 — 받은 {len(out[0])}, 색인 {self.dim}. "
                f"LOCAL_EMBED_DIM 을 맞추거나 재적재해야 한다")
        return out


class GenOSEmbedder:
    """GenOS 게이트웨이가 서빙하는 임베딩 — OpenAI 규약의 `/embeddings`.

    한 번에 `batch_size` 개씩 나눠 보낸다. 서빙마다 입력 개수·토큰 상한이 있어
    수백 개를 한 요청에 실으면 413/400 으로 통째로 떨어지는데, 그러면 그 배치의
    청크가 전부 벡터 없이 남는다.
    """

    def __init__(self, base_url: str, serving_id: str, token: str, *,
                 model: str = "", dim: int = 1024, batch_size: int = 32,
                 timeout: float = 120.0, max_retries: int = 3, normalize: bool = True):
        missing = [name for name, value in
                   (("GENOS_URL", base_url), ("GENOS_EMBED_ID", serving_id),
                    ("GENOS_EMBED_TOKEN", token)) if not value]
        if missing:
            raise ValueError(f"GenOS 임베딩 설정이 비어 있다 — {'·'.join(missing)}")
        self.endpoint = genos.genos_endpoint(base_url, serving_id, token,
                                             timeout=timeout, max_retries=max_retries)
        # 게이트웨이는 서빙 번호로 모델을 고른다. 규약이 칸을 요구해 형식상 채운다.
        self.model_name = model or "genos"
        self.dim = dim
        self.batch_size = max(1, batch_size)
        self.normalize = normalize

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start:start + self.batch_size])
            out.extend(self._embed_batch(batch, offset=start))
        return out

    def _embed_batch(self, batch: list[str], *, offset: int) -> list[list[float]]:
        try:
            data = genos.embeddings(self.endpoint,
                                    {"model": self.model_name, "input": batch})
        except genos.ServingError as exc:
            raise EmbeddingError(str(exc)) from exc

        rows = data.get("data") or []
        if len(rows) != len(batch):
            raise EmbeddingError(
                f"{self.endpoint.label}: {len(batch)}개를 물었는데 {len(rows)}개가 왔다")
        # 서빙이 순서를 섞어 보내는 경우가 있어 index 로 되돌린다 — 섞인 채로 두면
        # 청크와 벡터가 어긋나 검색이 조용히 엉뚱한 것을 올린다.
        rows = sorted(rows, key=lambda r: r.get("index", 0))

        vectors: list[list[float]] = []
        for position, row in enumerate(rows):
            vector = row.get("embedding")
            if not isinstance(vector, list) or not vector:
                raise EmbeddingError(
                    f"{self.endpoint.label}: {offset + position}번째 벡터가 비었다")
            if len(vector) != self.dim:
                raise EmbeddingError(
                    f"{self.endpoint.label}: 차원이 다르다 — 받은 {len(vector)}, "
                    f"색인 {self.dim}. GENOS_EMBED_DIM 을 맞추거나 재적재해야 한다")
            vectors.append(_l2(vector) if self.normalize else [float(v) for v in vector])
        return vectors


def _l2(vector: list[float]) -> list[float]:
    """L2 정규화. 적재된 벡터가 정규화돼 있어 질의 벡터도 같아야 한다."""
    norm = math.sqrt(sum(float(v) * float(v) for v in vector))
    if norm == 0:
        return [float(v) for v in vector]
    return [float(v) / norm for v in vector]

