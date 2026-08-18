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

모델은 프로세스에 하나만 띄운다(~2GB). 첫 호출이 느린 것은 로드 비용이다.
"""

from __future__ import annotations

import os
from typing import Optional

MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")

_model = None
_failed = False


def available() -> bool:
    """sentence-transformers 가 깔려 있고 명시적으로 꺼지지 않았는가.
    모델 로드 실패도 기억한다 — 매 질의마다 다시 실패하면 안 된다."""
    if os.environ.get("RAG_VECTOR", "1") == "0":
        return False
    if _failed:
        return False
    try:
        import sentence_transformers  # noqa: F401
        return True
    except Exception:
        return False


def encode(texts: list[str], batch_size: int = 64):
    """정규화된 float32 행렬. 호출 전에 available() 로 걸러라 —
    여기서 실패하면 None 을 돌려주고 이후 available() 도 False 가 된다."""
    global _model, _failed
    if not texts:
        import numpy as np
        return np.zeros((0, 1024), dtype=np.float32)
    try:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(MODEL, device="cpu")
        return _model.encode(texts, normalize_embeddings=True,
                             batch_size=batch_size,
                             show_progress_bar=False).astype("float32")
    except Exception:
        _failed = True
        return None


def encode_one(text: str) -> Optional[object]:
    m = encode([text])
    return None if m is None or len(m) == 0 else m[0]
