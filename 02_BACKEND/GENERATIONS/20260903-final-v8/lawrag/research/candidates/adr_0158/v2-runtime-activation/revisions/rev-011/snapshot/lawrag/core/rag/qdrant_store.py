"""선택형 온프레미스 Qdrant 어댑터.

기본 벡터 저장소는 계속 ``vectors.npz + meta.jsonl`` 이다. 이 모듈은
``RAG_VECTOR_BACKEND=qdrant`` 일 때만 import/호출되며, 외부 SDK 없이 Qdrant의
HTTP API를 사용한다. 따라서 폐쇄망 반입물은 requests 외에 별도 Python wheel을
요구하지 않는다.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import stat
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import urlsplit, urlunsplit

from lawrag.core.rag.content_snapshot import (
    ContentSnapshot,
    ContentSnapshotError,
    current_content_snapshot,
)


QDRANT_IDENTITY_SCHEMA = "rag-qdrant-index-identity-v1"
QDRANT_CONFIG_SCHEMA = "rag-qdrant-runtime-binding-v1"
QDRANT_CONFIG_FILE = "qdrant.json"
_IDENTITY_NAMESPACE = uuid.UUID("272b9e16-1b64-4b97-95d2-d9a8a5d91ea1")
_IDENTITY_POINT_ID = str(uuid.uuid5(_IDENTITY_NAMESPACE, "lawrag-index-identity"))
_COLLECTION = re.compile(r"[A-Za-z0-9_-]{1,255}\Z")
_BOUND_CONFIG_CACHE: tuple[str, dict[str, str] | None] | None = None


def _adapter_enabled() -> bool:
    from lawrag.core.rag import switches as switches_mod

    return switches_mod.is_on("sourceset_content_snapshot")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _stable_regular_bytes(path: Path) -> bytes:
    """Read a sealed runtime member without following or racing a symlink."""

    try:
        before = path.lstat()
    except OSError as exc:
        raise ContentSnapshotError(f"cannot stat Qdrant binding: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ContentSnapshotError("Qdrant binding must be a regular file")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ContentSnapshotError("Qdrant binding reads require no-follow opens")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | no_follow,
        )
    except OSError as exc:
        raise ContentSnapshotError(f"cannot safely open Qdrant binding: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        identity = lambda info: (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )
        if not stat.S_ISREG(opened.st_mode) or identity(before) != identity(opened):
            raise ContentSnapshotError("Qdrant binding changed before read")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        if identity(opened) != identity(os.fstat(descriptor)):
            raise ContentSnapshotError("Qdrant binding changed during read")
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def load_bound_config(snapshot: ContentSnapshot) -> Mapping[str, str] | None:
    """Load an optional endpoint identity from the release-proved vector tree.

    Credentials are deliberately excluded.  ``QDRANT_API_KEY`` remains an
    injected secret, while backend choice, URL, and collection are immutable
    release inputs.  Absence means the release selected the local file index.
    """

    global _BOUND_CONFIG_CACHE
    cache_key = snapshot.content_snapshot_sha256
    if _BOUND_CONFIG_CACHE is not None:
        if _BOUND_CONFIG_CACHE[0] != cache_key:
            raise ContentSnapshotError(
                "Qdrant config was initialized for another content snapshot"
            )
        cached = _BOUND_CONFIG_CACHE[1]
        return None if cached is None else dict(cached)

    vector_artifact = snapshot.runtime_artifact_path("index.vector")
    if vector_artifact.resolve() != snapshot.runtime_path("RAG_VECTOR_STORE").resolve():
        raise ContentSnapshotError(
            "Qdrant binding is outside the release-proved vector artifact"
        )
    path = vector_artifact / QDRANT_CONFIG_FILE
    try:
        path.lstat()
    except FileNotFoundError:
        _BOUND_CONFIG_CACHE = (cache_key, None)
        return None
    except OSError as exc:
        raise ContentSnapshotError(f"cannot inspect Qdrant binding: {exc}") from exc
    raw = _stable_regular_bytes(path)
    try:
        blob = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContentSnapshotError("Qdrant binding is not valid UTF-8 JSON") from exc
    allowed = {
        "schema_version",
        "url",
        "collection",
        "credential_binding_id",
        "credential_binding_version",
        "trust_policy_id",
        "trust_zone",
        "config_sha256",
    }
    if not isinstance(blob, Mapping) or set(blob) != allowed:
        raise ContentSnapshotError("Qdrant binding is incomplete or unexpected")
    core = dict(blob)
    declared = core.pop("config_sha256", None)
    if not isinstance(declared, str) or _digest(core) != declared:
        raise ContentSnapshotError("Qdrant binding self-hash mismatch")
    if core.get("schema_version") != QDRANT_CONFIG_SCHEMA:
        raise ContentSnapshotError("unsupported Qdrant binding schema")
    raw_url = core.get("url")
    raw_collection = core.get("collection")
    trust_zone = core.get("trust_zone")
    if not isinstance(raw_url, str) or not isinstance(raw_collection, str):
        raise ContentSnapshotError("Qdrant binding URL/collection must be strings")
    parsed = urlsplit(raw_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ContentSnapshotError("Qdrant binding URL must be a credential-free origin")
    if parsed.scheme == "http":
        try:
            loopback = ipaddress.ip_address(parsed.hostname or "").is_loopback
        except ValueError:
            loopback = (parsed.hostname or "").casefold() == "localhost"
        if not loopback:
            raise ContentSnapshotError(
                "Qdrant binding must use HTTPS unless it is loopback-only"
            )
    canonical_url = urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), "", "", "")
    ).rstrip("/")
    if raw_url != canonical_url:
        raise ContentSnapshotError("Qdrant binding URL is not canonical")
    if _COLLECTION.fullmatch(raw_collection) is None:
        raise ContentSnapshotError("Qdrant binding collection is invalid")
    if trust_zone not in {"internal", "external"}:
        raise ContentSnapshotError("Qdrant binding trust_zone is invalid")
    identity_fields = (
        "credential_binding_id",
        "credential_binding_version",
        "trust_policy_id",
    )
    for field in identity_fields:
        value = core.get(field)
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or any(ord(character) < 32 for character in value)
        ):
            raise ContentSnapshotError(
                f"Qdrant binding {field} must be exact non-empty text"
            )
    result = {
        "url": canonical_url,
        "collection": raw_collection,
        "credential_binding_id": str(core["credential_binding_id"]),
        "credential_binding_version": str(
            core["credential_binding_version"]
        ),
        "trust_policy_id": str(core["trust_policy_id"]),
        "trust_zone": str(trust_zone),
        "config_sha256": str(declared),
    }
    _BOUND_CONFIG_CACHE = (cache_key, result)
    return dict(result)


def bound_backend(snapshot: ContentSnapshot) -> str:
    """The release, rather than an ambient variable, selects the backend."""

    return "qdrant" if load_bound_config(snapshot) is not None else "file"


def _snapshot_identity(
    snapshot: ContentSnapshot,
    *,
    vector_identity_sha256: str,
    qdrant_config_sha256: str,
) -> dict[str, Any]:
    binding = snapshot.index_binding("vector")
    return {
        "identity_schema": QDRANT_IDENTITY_SCHEMA,
        "source_set_id": snapshot.source_set_id,
        "source_set_generation": snapshot.source_set_generation,
        "source_set_sha256": snapshot.source_set_sha256,
        "semantic_generation": snapshot.semantic_generation,
        "authority_generation": snapshot.authority_generation,
        "index_artifact_sha256": binding.artifact_sha256,
        "index_build_fingerprint": binding.build_fingerprint,
        "embedding_model_fingerprint": binding.embedding_model_fingerprint,
        "vector_identity_sha256": vector_identity_sha256,
        "qdrant_config_sha256": qdrant_config_sha256,
    }


def _identity_filter(identity: Mapping[str, Any]) -> list[dict]:
    return [
        {"key": key, "match": {"value": value}}
        for key, value in sorted(identity.items())
    ]


def verify_collection_identity(
    snapshot: ContentSnapshot,
    *,
    timeout: float = 5.0,
) -> Mapping[str, Any]:
    """Reject an absent/stale collection before returning any search results."""

    from lawrag.core.rag.vector import (
        load_vector_identity,
        runtime_embedding_model_fingerprint,
    )

    expected_model = snapshot.index_binding("vector").embedding_model_fingerprint
    if (
        not expected_model
        or runtime_embedding_model_fingerprint() != expected_model
    ):
        raise ContentSnapshotError(
            "runtime embedding model does not match the Qdrant collection"
        )

    config = load_bound_config(snapshot)
    if config is None:
        raise ContentSnapshotError("active release does not bind a Qdrant backend")
    vector_dir = snapshot.runtime_artifact_path("index.vector")
    file_identity = load_vector_identity(
        vector_dir,
        snapshot=snapshot,
        model_fingerprint=str(expected_model),
    )
    expected = _snapshot_identity(
        snapshot,
        vector_identity_sha256=str(file_identity["identity_sha256"]),
        qdrant_config_sha256=config["config_sha256"],
    )
    response = _session().get(
        f"{config['url']}/collections/{config['collection']}/points/{_IDENTITY_POINT_ID}",
        timeout=timeout,
        allow_redirects=False,
    )
    response.raise_for_status()
    result = response.json().get("result") or {}
    payload = result.get("payload") or {}
    if not isinstance(payload, Mapping) or payload.get("record_kind") != "identity":
        raise ContentSnapshotError("Qdrant collection has no trusted identity point")
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ContentSnapshotError("Qdrant collection belongs to another content snapshot")
    return expected


def url(content_snapshot: ContentSnapshot | None = None) -> str:
    if content_snapshot is None and _adapter_enabled():
        content_snapshot = current_content_snapshot(required=True)
    if content_snapshot is not None:
        config = load_bound_config(content_snapshot)
        if config is None:
            raise ContentSnapshotError("active release does not bind a Qdrant backend")
        return config["url"]
    return os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")


def collection(content_snapshot: ContentSnapshot | None = None) -> str:
    if content_snapshot is None and _adapter_enabled():
        content_snapshot = current_content_snapshot(required=True)
    if content_snapshot is not None:
        config = load_bound_config(content_snapshot)
        if config is None:
            raise ContentSnapshotError("active release does not bind a Qdrant backend")
        return config["collection"]
    return os.environ.get("QDRANT_COLLECTION", "lawrag_sections")


def _session():
    import requests

    session = requests.Session()
    session.trust_env = False
    session.headers.update({"Content-Type": "application/json"})
    key = os.environ.get("QDRANT_API_KEY", "")
    if key:
        session.headers["api-key"] = key
    return session


def ping(timeout: float = 5.0,
         content_snapshot: ContentSnapshot | None = None) -> dict:
    """서버와 대상 collection 상태를 읽는다. 상태 변경은 하지 않는다."""
    if content_snapshot is None and _adapter_enabled():
        content_snapshot = current_content_snapshot(required=True)
    server = url(content_snapshot)
    target_collection = collection(content_snapshot)
    session = _session()
    response = session.get(
        f"{server}/collections/{target_collection}", timeout=timeout,
        allow_redirects=False,
    )
    if response.status_code == 404:
        return {"ok": True, "ready": False, "server": server,
                "collection": target_collection,
                "collection_exists": False, "points": 0}
    response.raise_for_status()
    result = response.json().get("result") or {}
    return {"ok": True, "ready": True, "server": server,
            "collection": target_collection,
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
           coordinates: Optional[frozenset[tuple]] = None,
           content_snapshot: ContentSnapshot | None = None) -> list[tuple]:
    if content_snapshot is None and _adapter_enabled():
        content_snapshot = current_content_snapshot(required=True)
    body = {"vector": [float(x) for x in qvec], "limit": topk,
            "score_threshold": minimum, "with_payload": True}
    query_filter = _filter(doc_ids, coordinates)
    identity: Mapping[str, Any] | None = None
    if content_snapshot is not None:
        identity = verify_collection_identity(content_snapshot)
        if query_filter is None:
            query_filter = {"must": []}
        query_filter.setdefault("must", []).append(
            {"key": "record_kind", "match": {"value": "section"}}
        )
        query_filter["must"].extend(_identity_filter(identity))
    if query_filter:
        body["filter"] = query_filter
    server = url(content_snapshot)
    target_collection = collection(content_snapshot)
    response = _session().post(
        f"{server}/collections/{target_collection}/points/search",
        json=body, timeout=(5, float(os.environ.get("QDRANT_TIMEOUT", "30"))),
        allow_redirects=False)
    response.raise_for_status()
    rows = response.json().get("result") or []
    out = []
    for row in rows:
        payload = row.get("payload") or {}
        if "doc_id" not in payload or "node" not in payload:
            continue
        if identity is not None:
            if payload.get("record_kind") != "section" or any(
                payload.get(key) != value for key, value in identity.items()
            ):
                raise ContentSnapshotError(
                    "Qdrant returned a row from another content snapshot"
                )
            assert content_snapshot is not None
            if payload["doc_id"] not in set(content_snapshot.document_ids()):
                raise ContentSnapshotError("Qdrant returned an unmapped document")
        out.append((payload["doc_id"], payload["node"], round(float(row["score"]), 4)))
    return out


def _chunks(rows: list, size: int) -> Iterable[list]:
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def sync_from_files(vector_dir: Path, *, recreate: bool = False,
                    batch_size: int = 128,
                    content_snapshot: ContentSnapshot | None = None,
                    embedding_model_fingerprint: str | None = None) -> dict:
    """기존 정본 파일 인덱스를 Qdrant에 멱등 upsert한다."""
    import numpy as np

    meta_path = vector_dir / "meta.jsonl"
    vectors_path = vector_dir / "vectors.npz"
    if not (meta_path.exists() and vectors_path.exists()):
        raise FileNotFoundError(f"벡터 정본이 없습니다: {vector_dir}")
    if content_snapshot is None and _adapter_enabled():
        content_snapshot = current_content_snapshot(required=True)
    rows = [json.loads(line) for line in meta_path.read_text(encoding="utf-8").splitlines()]
    matrix = np.load(vectors_path, allow_pickle=False)["v"].astype(np.float32)
    if not len(rows) or len(rows) != len(matrix):
        raise ValueError(f"meta/vector 행 불일치: {len(rows)}/{len(matrix)}")
    if content_snapshot is not None:
        allowed_docs = set(content_snapshot.document_ids())
        coordinates = []
        for row in rows:
            if not isinstance(row, Mapping) or row.get("doc_id") not in allowed_docs:
                raise ContentSnapshotError("Qdrant source contains an unmapped document")
            coordinates.append((row.get("doc_id"), row.get("node")))
        if len(coordinates) != len(set(coordinates)):
            raise ContentSnapshotError("Qdrant source contains duplicate coordinates")
    server = url(content_snapshot)
    target_collection = collection(content_snapshot)
    session = _session()
    target = f"{server}/collections/{target_collection}"
    exists = session.get(target, timeout=5, allow_redirects=False).status_code == 200
    if recreate and exists:
        response = session.delete(target, timeout=30, allow_redirects=False)
        response.raise_for_status()
        exists = False
    if not exists:
        response = session.put(target, json={"vectors": {"size": int(matrix.shape[1]),
                                                           "distance": "Cosine"}}, timeout=30,
                               allow_redirects=False)
        response.raise_for_status()
    fingerprint = hashlib.sha256(vectors_path.read_bytes() + meta_path.read_bytes()).hexdigest()
    identity: Mapping[str, Any] | None = None
    if content_snapshot is not None:
        from lawrag.core.rag.vector import (
            load_vector_identity,
            runtime_embedding_model_fingerprint,
        )

        model_fingerprint = (
            embedding_model_fingerprint or runtime_embedding_model_fingerprint()
        )
        expected_model = content_snapshot.index_binding(
            "vector"
        ).embedding_model_fingerprint
        if not model_fingerprint or model_fingerprint != expected_model:
            raise ContentSnapshotError(
                "Qdrant sync model does not match the pinned vector index"
            )
        file_identity = load_vector_identity(
            vector_dir,
            snapshot=content_snapshot,
            model_fingerprint=model_fingerprint,
        )
        identity = _snapshot_identity(
            content_snapshot,
            vector_identity_sha256=str(file_identity["identity_sha256"]),
            qdrant_config_sha256=str(
                (load_bound_config(content_snapshot) or {})["config_sha256"]
            ),
        )
    points = []
    uploaded = 0
    namespace = uuid.UUID("0e0adc5d-b6e5-4e25-903a-b4afde04fc23")
    for pos, (row, vector) in enumerate(zip(rows, matrix)):
        payload = dict(row)
        payload.update({"source_index_sha256": fingerprint, "source_row": pos})
        if identity is not None:
            payload.update(identity)
            payload["record_kind"] = "section"
        point_key = f"{payload.get('doc_id')}|{payload.get('node')}|{pos}"
        if identity is not None:
            point_key = f"{identity['vector_identity_sha256']}|{point_key}"
        point_id = str(uuid.uuid5(namespace, point_key))
        points.append({"id": point_id, "vector": [float(x) for x in vector],
                       "payload": payload})
        if len(points) >= batch_size:
            response = session.put(f"{target}/points?wait=true", json={"points": points},
                                   timeout=(5, 120), allow_redirects=False)
            response.raise_for_status()
            uploaded += len(points)
            points = []
    if points:
        response = session.put(f"{target}/points?wait=true", json={"points": points},
                               timeout=(5, 120), allow_redirects=False)
        response.raise_for_status()
        uploaded += len(points)
    if identity is not None:
        # Publish identity last.  Point IDs include the vector generation, so a
        # partial new upload cannot overwrite the previously active generation.
        identity_payload = {**identity, "record_kind": "identity"}
        response = session.put(
            f"{target}/points?wait=true",
            json={
                "points": [
                    {
                        "id": _IDENTITY_POINT_ID,
                        "vector": [0.0] * int(matrix.shape[1]),
                        "payload": identity_payload,
                    }
                ]
            },
            timeout=(5, 120),
            allow_redirects=False,
        )
        response.raise_for_status()
    return {"ok": True, "collection": target_collection, "uploaded": uploaded,
            "dimension": int(matrix.shape[1]), "source_sha256": fingerprint,
            **({"vector_identity_sha256": identity["vector_identity_sha256"]}
               if identity is not None else {})}
