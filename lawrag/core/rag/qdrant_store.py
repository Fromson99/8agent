"""선택형 온프레미스 Qdrant 어댑터.

기본 벡터 저장소는 계속 ``vectors.npz + meta.jsonl`` 이다. 이 모듈은
``RAG_VECTOR_BACKEND=qdrant`` 일 때만 import/호출되며, 외부 SDK 없이 Qdrant의
HTTP API를 사용한다. 따라서 폐쇄망 반입물은 requests 외에 별도 Python wheel을
요구하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Iterable, Optional


def url() -> str:
    return os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")


def collection() -> str:
    return os.environ.get("QDRANT_COLLECTION", "lawrag_sections")


def _session():
    import requests

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    key = os.environ.get("QDRANT_API_KEY", "")
    if key:
        session.headers["api-key"] = key
    return session


def ping(timeout: float = 5.0) -> dict:
    """서버와 대상 collection 상태를 읽는다. 상태 변경은 하지 않는다."""
    session = _session()
    response = session.get(f"{url()}/collections/{collection()}", timeout=timeout)
    if response.status_code == 404:
        return {"ok": True, "ready": False, "server": url(), "collection": collection(),
                "collection_exists": False, "points": 0}
    response.raise_for_status()
    result = response.json().get("result") or {}
    return {"ok": True, "ready": True, "server": url(), "collection": collection(),
            "collection_exists": True,
            "status": result.get("status"),
            "points": result.get("points_count", result.get("vectors_count", 0))}


def _filter(doc_ids: Optional[frozenset],
            coordinates: Optional[frozenset[tuple]]) -> Optional[dict]:
    must: list[dict] = []
    if doc_ids:
        must.append({"key": "doc_id", "match": {"any": sorted(doc_ids)}})
    payload: dict = {"must": must} if must else {}
    if coordinates:
        payload["should"] = [
            {"must": [
                {"key": "doc_id", "match": {"value": str(doc_id)}},
                {"key": "node", "match": {"value": node}},
            ]}
            for doc_id, node in sorted(coordinates, key=lambda x: (str(x[0]), str(x[1])))
        ]
        payload["min_should"] = {"conditions": payload["should"], "min_count": 1}
        payload.pop("should", None)
    return payload or None


def search(qvec, *, topk: int, minimum: float,
           doc_ids: Optional[frozenset] = None,
           coordinates: Optional[frozenset[tuple]] = None) -> list[tuple]:
    body = {"vector": [float(x) for x in qvec], "limit": topk,
            "score_threshold": minimum, "with_payload": True}
    query_filter = _filter(doc_ids, coordinates)
    if query_filter:
        body["filter"] = query_filter
    response = _session().post(
        f"{url()}/collections/{collection()}/points/search",
        json=body, timeout=(5, float(os.environ.get("QDRANT_TIMEOUT", "30"))))
    response.raise_for_status()
    rows = response.json().get("result") or []
    out = []
    for row in rows:
        payload = row.get("payload") or {}
        if "doc_id" not in payload or "node" not in payload:
            continue
        out.append((payload["doc_id"], payload["node"], round(float(row["score"]), 4)))
    return out


def _chunks(rows: list, size: int) -> Iterable[list]:
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def sync_from_files(vector_dir: Path, *, recreate: bool = False,
                    batch_size: int = 128) -> dict:
    """기존 정본 파일 인덱스를 Qdrant에 멱등 upsert한다."""
    import numpy as np

    meta_path = vector_dir / "meta.jsonl"
    vectors_path = vector_dir / "vectors.npz"
    if not (meta_path.exists() and vectors_path.exists()):
        raise FileNotFoundError(f"벡터 정본이 없습니다: {vector_dir}")
    rows = [json.loads(line) for line in meta_path.read_text(encoding="utf-8").splitlines()]
    matrix = np.load(vectors_path)["v"].astype(np.float32)
    if not len(rows) or len(rows) != len(matrix):
        raise ValueError(f"meta/vector 행 불일치: {len(rows)}/{len(matrix)}")
    session = _session()
    target = f"{url()}/collections/{collection()}"
    exists = session.get(target, timeout=5).status_code == 200
    if recreate and exists:
        response = session.delete(target, timeout=30)
        response.raise_for_status()
        exists = False
    if not exists:
        response = session.put(target, json={"vectors": {"size": int(matrix.shape[1]),
                                                           "distance": "Cosine"}}, timeout=30)
        response.raise_for_status()
    fingerprint = hashlib.sha256(vectors_path.read_bytes() + meta_path.read_bytes()).hexdigest()
    points = []
    uploaded = 0
    namespace = uuid.UUID("0e0adc5d-b6e5-4e25-903a-b4afde04fc23")
    for pos, (row, vector) in enumerate(zip(rows, matrix)):
        payload = dict(row)
        payload.update({"source_index_sha256": fingerprint, "source_row": pos})
        point_id = str(uuid.uuid5(namespace,
                                  f"{payload.get('doc_id')}|{payload.get('node')}|{pos}"))
        points.append({"id": point_id, "vector": [float(x) for x in vector],
                       "payload": payload})
        if len(points) >= batch_size:
            response = session.put(f"{target}/points?wait=true", json={"points": points},
                                   timeout=(5, 120))
            response.raise_for_status()
            uploaded += len(points)
            points = []
    if points:
        response = session.put(f"{target}/points?wait=true", json={"points": points},
                               timeout=(5, 120))
        response.raise_for_status()
        uploaded += len(points)
    return {"ok": True, "collection": collection(), "uploaded": uploaded,
            "dimension": int(matrix.shape[1]), "source_sha256": fingerprint}
