"""문장 임베딩 공용 인코더 — 컴파일(용어 디듀프·구역 색인)과 검색(벡터 단)이
같은 모델을 써야 한다. 모델이 갈리면 질의 벡터와 구역 벡터가 다른 공간에
있어 코사인이 무의미해진다.

결정 변경 기록 (2026-08-10): 애초 임베딩은 용어 생성 배치 전용이었으나,
"용어가 아직 없는 초반"의 회수를 위해 **검색 사다리의 후순위 단**으로도
쓰기로 했다 (사용자 결정). 규율은 유지된다:
  · 용어 단(정확·부분)이 항상 먼저다 — 벡터는 용어가 빗나갔을 때만
  · 벡터가 찾아준 착지는 승격 후보로 적재된다 — 벡터 히트는 종착이 아니라
    용어가 태어나는 신호다 (자기상각)
  · 무거운 import 는 전부 지연 — 모델이 없으면 벡터 단은 조용히 빠지고
    렉시컬만으로 동작한다 (오프라인 환경 보존)

백엔드는 둘이다 (2026-08-18, lawrag/core/llm.py 와 같은 구도):
  · local — sentence-transformers 로 EMBED_MODEL(기본 BAAI/bge-m3)을 프로세스에
    하나 띄운다(~2GB). 첫 호출이 느린 것은 로드 비용이다.
  · genos — GenOS 임베딩 서빙. 서비스 라우터(유형 "서빙 - Embedding")가
    `{GENOS_EMBED_URL}/v1/embeddings` 로 노출한다 (실측: genos-docs v1.9.0
    "서비스 라우터" — 경로만 문서에 있고 몸통 스키마는 없다). 요청·응답은
    OpenAI 형식으로 가정한다 — `{"model", "input": [...]}` →
    `{"data": [{"index", "embedding": [...]}]}`. 그쪽 엔진(vLLM·TEI 계열)이
    다 이 형식이다. 첫 호출이 400 이면 그때 형식을 맞춘다.
  고르는 규칙: EMBED_BACKEND 가 있으면 그것, 없으면 GENOS_EMBED_URL 이 있을 때
  genos, 아니면 local.

**벡터 색인과 질의는 같은 백엔드·같은 모델이어야 한다.** 색인을 다른 모델로
다시 만들면(그쪽에서 재생성) 옛 vectors.npz 를 지우고 만들어라 —
embed_sections 는 sha1 이 같으면 옛 벡터를 재사용한다.
"""

from __future__ import annotations

import os
from typing import Optional

MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")
BACKENDS = ("local", "genos")

_model = None
_failed = False
_genos = None            # (session, url, model) — 첫 호출 때 세운다
_local_runtime_configured = False


def _configure_local_runtime() -> None:
    """WSL/CPU에서 과도한 BLAS·Torch 스레드 경쟁을 피한다.

    실측상 기본 스레드 자동 선택은 BGE-M3 첫 질의를 7분 이상 끌었고, 4개로
    제한하면 같은 입력이 10.5초였다. 명시한 OMP/MKL 값은 존중한다.
    """
    global _local_runtime_configured
    if _local_runtime_configured:
        return
    threads = max(1, int(os.environ.get("EMBED_CPU_THREADS", "4")))
    os.environ.setdefault("OMP_NUM_THREADS", str(threads))
    os.environ.setdefault("MKL_NUM_THREADS", str(threads))
    try:
        import torch

        torch.set_num_threads(threads)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
    except Exception:
        pass
    _local_runtime_configured = True


def backend() -> str:
    b = (os.environ.get("EMBED_BACKEND") or "").strip().lower()
    if b in BACKENDS:
        return b
    return "genos" if os.environ.get("GENOS_EMBED_URL") else "local"


def available() -> bool:
    """임베딩을 할 수 있는가 — local 이면 sentence-transformers 가 깔려 있고,
    genos 면 URL 이 있고. 명시적으로 끄면(RAG_VECTOR=0) 둘 다 아니다.
    실패도 기억한다 — 매 질의마다 다시 실패하면 안 된다."""
    if os.environ.get("RAG_VECTOR", "1") == "0":
        return False
    if _failed:
        return False
    if backend() == "genos":
        return bool(os.environ.get("GENOS_EMBED_URL"))
    try:
        _configure_local_runtime()
        import sentence_transformers  # noqa: F401
        return True
    except Exception:
        return False


def _encode_local(texts: list[str], batch_size: int):
    global _model
    _configure_local_runtime()
    if _model is None:
        from sentence_transformers import SentenceTransformer
        kwargs = {"device": os.environ.get("EMBED_DEVICE", "cpu")}
        if os.environ.get("EMBED_LOCAL_FILES_ONLY", "0") == "1":
            kwargs["local_files_only"] = True
        _model = SentenceTransformer(MODEL, **kwargs)
    return _model.encode(texts, normalize_embeddings=True,
                         batch_size=batch_size,
                         show_progress_bar=False).astype("float32")


def _encode_genos(texts: list[str], batch_size: int):
    """OpenAI 호환 /v1/embeddings — 배치로 끊어 보내고 정규화해 돌려준다."""
    global _genos
    import numpy as np
    import requests

    if _genos is None:
        url = os.environ["GENOS_EMBED_URL"].rstrip("/")
        s = requests.Session()
        s.headers["Content-Type"] = "application/json"
        key = os.environ.get("GENOS_EMBED_KEY") or os.environ.get("GENOS_LLM_KEY", "")
        if key:
            s.headers["Authorization"] = f"Bearer {key}"
        model = os.environ.get("GENOS_EMBED_MODEL", "")
        if not model:                          # LLM 쪽과 같은 절차 — /v1/models 첫 모델
            try:
                r = s.get(url + "/v1/models", timeout=15)
                r.raise_for_status()
                model = r.json()["data"][0]["id"]
            except Exception:
                model = MODEL                  # 못 물으면 로컬 기본 이름으로 — 서빙이 무시할 수도
        _genos = (s, url, model)
    s, url, model = _genos
    bs = int(os.environ.get("GENOS_EMBED_BATCH", str(batch_size)))
    out = []
    for i in range(0, len(texts), bs):
        chunk = texts[i:i + bs]
        r = s.post(url + "/v1/embeddings", json={"model": model, "input": chunk},
                   timeout=(15, 300))
        r.raise_for_status()
        data = sorted(r.json()["data"], key=lambda d: d.get("index", 0))
        if len(data) != len(chunk):
            raise RuntimeError(f"임베딩 응답 행 수 불일치 — 보냄 {len(chunk)}, 받음 {len(data)}")
        out.extend(d["embedding"] for d in data)
    m = np.asarray(out, dtype=np.float32)
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def encode(texts: list[str], batch_size: int = 64):
    """정규화된 float32 행렬. 호출 전에 available() 로 걸러라 —
    여기서 실패하면 None 을 돌려주고 이후 available() 도 False 가 된다."""
    global _failed
    if not texts:
        import numpy as np
        return np.zeros((0, 1024), dtype=np.float32)
    try:
        if backend() == "genos":
            return _encode_genos(texts, batch_size)
        return _encode_local(texts, batch_size)
    except Exception:
        _failed = True
        return None


def encode_one(text: str) -> Optional[object]:
    m = encode([text])
    return None if m is None or len(m) == 0 else m[0]
