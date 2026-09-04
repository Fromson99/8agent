"""표면형 임베딩 — 디듀프 클러스터링 전용 (계획 확정: 로컬 BGE-M3).

**여기가 임베딩의 유일한 자리다.** 질의·검색 런타임은 이 모듈을 import 하지
않는다(tests/architecture/test_terms_isolation.py 가 강제). 벡터는 DB 없이
파일로 남는다:

    var/out/terms/embeddings/bge-m3/vectors.npz    fp16 행렬 (정규화됨)
    var/out/terms/embeddings/bge-m3/meta.jsonl     행마다 {key, sha1} — 증분의 기준

재실행 시 sha1 이 같은 표면형은 다시 임베딩하지 않는다 — 모델 로드(~2GB)와
인코딩이 이 파이프라인의 유일하게 무거운 자리라, 증분이 없으면 매 빌드가
콜드 스타트다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MODEL = "BAAI/bge-m3"
DIRNAME = "bge-m3"


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def encode(surfaces: list[str], cache_dir: Path):
    """표면형 목록 → (numpy 행렬, 표면형 순서 그대로). 캐시 적중분은 재사용."""
    import numpy as np

    d = cache_dir / DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    npz, meta = d / "vectors.npz", d / "meta.jsonl"

    cached: dict[str, int] = {}
    vecs = None
    if npz.exists() and meta.exists():
        try:
            vecs = np.load(npz)["v"]
            for i, line in enumerate(meta.read_text(encoding="utf-8").splitlines()):
                cached[json.loads(line)["sha1"]] = i
        except Exception:
            cached, vecs = {}, None

    hashes = [_sha1(s) for s in surfaces]
    fresh = [s for s, h in zip(surfaces, hashes) if h not in cached]
    if fresh:
        from lawrag.core import embedding

        enc = embedding.encode(fresh)
        if enc is None:
            raise RuntimeError("임베딩 모델을 부르지 못했습니다 — --no-embed 로 우회할 수 있습니다")
        new = enc.astype(np.float16)
        base = 0 if vecs is None else len(vecs)
        vecs = new if vecs is None else np.vstack([vecs, new])
        with meta.open("a", encoding="utf-8") as f:
            for k, s in enumerate(fresh):
                h = _sha1(s)
                cached[h] = base + k
                f.write(json.dumps({"key": s, "sha1": h}, ensure_ascii=False) + "\n")
        np.savez_compressed(npz, v=vecs)

    idx = [cached[h] for h in hashes]
    return vecs[idx].astype(np.float32), len(fresh)
