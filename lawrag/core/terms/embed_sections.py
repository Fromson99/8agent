"""구역 벡터 색인 — 검색 벡터 단이 읽을 구역(마디) 임베딩의 컴파일.

구역 텍스트(경로+제목+본문 머리)를 임베딩해 문서 스토어 **옆**에 굳힌다 —
glossary.json 과 같은 자리 규약이라 런타임(lawrag/core/rag/vector.py)이 환경만으로
찾는다. 질의 시점에 하는 일은 질의 하나의 임베딩과 코사인뿐이다.

증분: 구역 텍스트의 sha1 이 같으면 다시 임베딩하지 않는다. 문서가 지워지면
그 행도 빠진다 — meta 는 매번 현재 스토어 기준으로 다시 쓴다(스토어와 색인이
어긋난 채 남는 것이 가장 나쁘다).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from lawrag.core.rag.index import store_path
from lawrag.core.terms.transcribe import _load_docs

TEXT_CAP = 800          # 구역 머리 800자 — 벡터는 주제를 잡으면 된다, 전문이 아니라


def sections_dir() -> Path:
    return Path(os.environ.get("RAG_VECTOR_STORE",
                               store_path().parent / "embeddings" / "sections"))


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def section_text(v, n) -> str:
    """임베딩 입력 — 경로(조상 사슬)를 앞에 붙인다. "제3항" 만으로는 주제가
    없다; "제2장 ▸ 제19조 설명의무 ▸ 제3항 …" 이어야 벡터가 자리를 안다."""
    path = v.path(n.get("id"))
    body = v.section_text(n, cap=TEXT_CAP)
    return f"{path}\n{body}".strip()


def run(store: Optional[Path] = None, out: Optional[Path] = None) -> dict:
    import numpy as np

    from lawrag.core import embedding

    out = out or sections_dir()
    views = _load_docs(store)

    rows: list[dict] = []          # {doc_id, node, sha1}
    texts: list[str] = []
    for v in views:
        for n in v.nodes:
            t = section_text(v, n)
            if len(t) < 4:
                continue
            rows.append({"doc_id": v.doc_id, "node": n.get("id"),
                         "sha1": _sha1(t)})
            texts.append(t)

    # 기존 캐시 — sha1 로 재사용
    old_vec = None
    old_idx: dict[str, int] = {}
    npz, meta = out / "vectors.npz", out / "meta.jsonl"
    if npz.exists() and meta.exists():
        try:
            old_vec = np.load(npz)["v"]
            for i, line in enumerate(meta.read_text(encoding="utf-8").splitlines()):
                old_idx[json.loads(line)["sha1"]] = i
        except Exception:
            old_vec, old_idx = None, {}

    fresh_texts = [t for r, t in zip(rows, texts) if r["sha1"] not in old_idx]
    fresh_vecs = None
    if fresh_texts:
        fresh_vecs = embedding.encode(fresh_texts)
        if fresh_vecs is None:
            raise RuntimeError("임베딩 모델을 부르지 못했습니다")

    mat = []
    fi = 0
    for r in rows:
        if r["sha1"] in old_idx and old_vec is not None:
            mat.append(old_vec[old_idx[r["sha1"]]])
        else:
            mat.append(fresh_vecs[fi])
            fi += 1
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(npz, v=np.array(mat, dtype=np.float16))
    with meta.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"sections": len(rows), "fresh": len(fresh_texts), "store": str(out)}


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="python -m lawrag.core.terms embed-sections",
        description="구역 벡터 색인 컴파일 — 검색 벡터 단이 읽는다")
    ap.add_argument("--store", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    # --store 를 지정했으면 색인도 그 옆이다 — transcribe·build 와 같은 규약.
    out = args.out or (args.store.parent / "embeddings" / "sections"
                       if args.store else None)
    rep = run(args.store, out)
    print(f"구역 {rep['sections']}개 (신규 임베딩 {rep['fresh']}) → {rep['store']}")
    return 0
