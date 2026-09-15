"""검색 벡터 단 — 미리 임베딩한 구역 위에서 질의 코사인 (하이브리드의 반쪽).

결정 변경 기록 (2026-08-10): 용어 기반 동작은 그대로다 — 벡터는 용어 단
(정확·부분)이 빗나간 뒤 렉시컬 본문 검색과 **융합(RRF)** 되는 후순위 단이고,
용어가 아직 태어나지 않은 초반의 회수를 위한 대비다. 벡터가 찾은 착지는
승격 후보로 적재된다(lawrag/api/routers/rag.py) — 벡터 히트는 용어의 씨앗이다.

이 모듈은 core.terms 를 import 하지 않는다(아키텍처 테스트가 강제). 구역
벡터의 컴파일은 lawrag/core/terms/embed_sections.py 의 일이고, 여기는 그 산출
파일을 읽고 질의 하나를 임베딩할 뿐이다. 모델·색인·numpy 가 없으면 전부
조용히 빠진다 — 렉시컬 사다리는 언제나 돈다.
"""

from __future__ import annotations

import json
import hashlib
import logging
import os
from pathlib import Path
import stat
from typing import Any, Mapping, Optional

from lawrag.runtime.content_snapshot import (
    ContentSnapshot,
    ContentSnapshotError,
    current_content_snapshot,
)
from lawrag.core.rag.index import store_path
from lawrag.core.rag.controls import value as control_value

log = logging.getLogger("lawrag.core.rag.vector")

# 코사인 문턱 — BGE-M3 실측에서 무관한 한국어 구역은 0.3대, 관련은 0.5↑.
VECTOR_MIN = float(control_value("entry.vector_cos_min"))
TOPK = 8
VECTOR_IDENTITY_SCHEMA = "rag-vector-index-identity-v1"
VECTOR_IDENTITY_FILE = "identity.json"


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


def _file_sha256(path: Path) -> str:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ContentSnapshotError(f"cannot stat vector artifact {path}: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ContentSnapshotError(f"vector artifact is not a regular file: {path}")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ContentSnapshotError("vector artifact reads require no-follow opens")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | no_follow,
        )
    except OSError as exc:
        raise ContentSnapshotError(f"cannot safely open vector artifact {path}: {exc}") from exc
    digest = hashlib.sha256()
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
        if not stat.S_ISREG(opened.st_mode) or identity(opened) != identity(before):
            raise ContentSnapshotError(f"vector artifact changed before hashing: {path}")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if identity(opened) != identity(os.fstat(descriptor)):
            raise ContentSnapshotError(f"vector artifact changed while hashing: {path}")
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _adapter_enabled() -> bool:
    from lawrag.core.rag import switches as switches_mod

    return switches_mod.is_on("sourceset_content_snapshot")


def runtime_embedding_model_fingerprint() -> str:
    """Identity derived from the backend/model/revision the encoder consumes."""

    from lawrag.core import embedding

    try:
        return embedding.runtime_fingerprint()
    except RuntimeError as exc:
        if _adapter_enabled():
            raise ContentSnapshotError(
                "sealed embedding runtime identity is invalid"
            ) from exc
        return os.environ.get("RAG_EMBEDDING_MODEL_FINGERPRINT", "").strip()


def _require_runtime_model(snapshot: ContentSnapshot) -> str:
    expected = snapshot.index_binding("vector").embedding_model_fingerprint
    actual = runtime_embedding_model_fingerprint()
    if not expected or not actual or actual != expected:
        raise ContentSnapshotError(
            "runtime embedding model does not match the pinned vector index"
        )
    return actual


def _has_bound_vector_index(snapshot: ContentSnapshot) -> bool:
    """Return False only for an explicitly lexical-only pinned release.

    A duplicate vector binding is still an integrity error.  In particular,
    callers must not use the absence of a vector binding as permission to read
    an ambient ``RAG_VECTOR_STORE``.
    """

    matches = [row for row in snapshot.indexes if row.kind == "vector"]
    if not matches:
        return False
    snapshot.index_binding("vector")
    return True


def build_vector_identity(
    *,
    snapshot: ContentSnapshot,
    vector_dir: Path,
    row_count: int,
    model_fingerprint: str,
) -> dict[str, Any]:
    """Build a non-circular sidecar bound to vector inputs and actual bytes."""

    binding = snapshot.index_binding("vector")
    if model_fingerprint != binding.embedding_model_fingerprint:
        raise ContentSnapshotError("vector build used another embedding model")
    meta_path = vector_dir / "meta.jsonl"
    vectors_path = vector_dir / "vectors.npz"
    core = {
        "schema_version": VECTOR_IDENTITY_SCHEMA,
        "source_set_id": snapshot.source_set_id,
        "source_set_generation": snapshot.source_set_generation,
        "source_set_sha256": snapshot.source_set_sha256,
        "semantic_generation": snapshot.semantic_generation,
        "authority_generation": snapshot.authority_generation,
        "index_build_fingerprint": binding.build_fingerprint,
        "embedding_model_fingerprint": model_fingerprint,
        "meta_sha256": _file_sha256(meta_path),
        "vectors_sha256": _file_sha256(vectors_path),
        "row_count": row_count,
    }
    return {**core, "identity_sha256": _digest(core)}


def load_vector_identity(
    vector_dir: Path,
    *,
    snapshot: ContentSnapshot,
    model_fingerprint: str,
) -> Mapping[str, Any]:
    """Strictly validate a file index against one pinned release snapshot."""

    identity_path = vector_dir / VECTOR_IDENTITY_FILE
    try:
        blob = json.loads(identity_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContentSnapshotError(f"cannot read vector identity: {exc}") from exc
    if not isinstance(blob, Mapping):
        raise ContentSnapshotError("vector identity root must be an object")
    allowed = {
        "schema_version",
        "source_set_id",
        "source_set_generation",
        "source_set_sha256",
        "semantic_generation",
        "authority_generation",
        "index_build_fingerprint",
        "embedding_model_fingerprint",
        "meta_sha256",
        "vectors_sha256",
        "row_count",
        "identity_sha256",
    }
    if set(blob) != allowed or blob.get("schema_version") != VECTOR_IDENTITY_SCHEMA:
        raise ContentSnapshotError("vector identity schema is incomplete or unexpected")
    core = dict(blob)
    declared = core.pop("identity_sha256", None)
    if not isinstance(declared, str) or _digest(core) != declared:
        raise ContentSnapshotError("vector identity hash mismatch")
    binding = snapshot.index_binding("vector")
    expected = {
        "source_set_id": snapshot.source_set_id,
        "source_set_generation": snapshot.source_set_generation,
        "source_set_sha256": snapshot.source_set_sha256,
        "semantic_generation": snapshot.semantic_generation,
        "authority_generation": snapshot.authority_generation,
        "index_build_fingerprint": binding.build_fingerprint,
        "embedding_model_fingerprint": model_fingerprint,
    }
    mismatches = [key for key, value in expected.items() if blob.get(key) != value]
    meta_path = vector_dir / "meta.jsonl"
    vectors_path = vector_dir / "vectors.npz"
    if not meta_path.is_file() or not vectors_path.is_file():
        mismatches.append("index_files")
    else:
        if blob.get("meta_sha256") != _file_sha256(meta_path):
            mismatches.append("meta_sha256")
        if blob.get("vectors_sha256") != _file_sha256(vectors_path):
            mismatches.append("vectors_sha256")
    if mismatches:
        raise ContentSnapshotError(
            "vector index does not match the pinned content snapshot: "
            + ", ".join(mismatches)
        )
    row_count = blob.get("row_count")
    if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 0:
        raise ContentSnapshotError("vector identity row_count is invalid")
    return blob


def sections_dir() -> Path:
    return Path(os.environ.get("RAG_VECTOR_STORE",
                               store_path().parent / "embeddings" / "sections"))


def backend() -> str:
    """벡터 저장 백엔드. 파일형 정본이 기본이고 Qdrant는 명시 선택만 허용한다."""
    value = os.environ.get("RAG_VECTOR_BACKEND", "file").strip().lower()
    return value if value in ("file", "qdrant") else "file"


class VectorIndex:
    def __init__(self, rows: list[dict], mat, *,
                 content_snapshot_sha256: str = "",
                 content_fingerprint: str = "",
                 identity: Mapping[str, Any] | None = None) -> None:
        self.rows = rows
        self.mat = mat                      # float32, 정규화됨
        self.content_snapshot_sha256 = content_snapshot_sha256
        self.content_fingerprint = content_fingerprint
        self.identity = dict(identity or {})
        self._masks: dict = {}              # 스코프(frozenset) → 행 마스크 캐시
        self._coordinate_rows: dict[tuple, tuple[int, ...]] | None = None

    def _mask(self, doc_ids: frozenset):
        m = self._masks.get(doc_ids)
        if m is None:
            import numpy as np
            m = np.fromiter((r.get("doc_id") in doc_ids for r in self.rows),
                            dtype=bool, count=len(self.rows))
            if len(self._masks) > 32:       # 스코프는 몇 개 안 된다 — 폭주만 막는다
                self._masks.clear()
            self._masks[doc_ids] = m
        return m

    def search(self, qvec, topk: int = TOPK,
               minimum: float = VECTOR_MIN,
               doc_ids: Optional[frozenset] = None,
               coordinates: Optional[frozenset[tuple]] = None) -> list[tuple]:
        """doc_ids 가 있으면 그 문서의 행만 경쟁한다 — 스코프 밖 행이 상위를
        차지해 topk 를 먹는 일이 없어야 "그 문서들만 대상으로" 가 선다.

        coordinates는 구조·역할 교집합이 이미 만든 허용 좌표다. 이 집합을 먼저
        고정한 뒤 그 안에서만 코사인 순위를 매긴다. Vector가 구조 필터보다 앞서
        전역 후보를 다시 섞지 못하게 하는 검색 불변식이다.
        """
        import numpy as np

        row_positions = None
        if coordinates is not None:
            if self._coordinate_rows is None:
                packed: dict[tuple, list[int]] = {}
                for pos, row in enumerate(self.rows):
                    packed.setdefault(
                        (row.get("doc_id"), row.get("node")), []).append(pos)
                self._coordinate_rows = {
                    key: tuple(values) for key, values in packed.items()
                }
            row_positions = np.asarray(sorted({
                pos for coordinate in coordinates
                for pos in self._coordinate_rows.get(coordinate, ())
            }), dtype=np.int64)
            if doc_ids is not None:
                allowed_docs = frozenset(doc_ids)
                row_positions = np.asarray([
                    pos for pos in row_positions
                    if self.rows[int(pos)].get("doc_id") in allowed_docs
                ], dtype=np.int64)
            if not len(row_positions):
                return []
            sims = self.mat[row_positions] @ qvec
        else:
            sims = self.mat @ qvec
        if doc_ids is not None:
            if row_positions is None:
                sims = np.where(self._mask(frozenset(doc_ids)), sims, -np.inf)
        order = np.argsort(-sims)[:topk]
        out = []
        for local_pos in order:
            s = float(sims[local_pos])
            if s < minimum:
                break
            pos = (int(row_positions[int(local_pos)])
                   if row_positions is not None else int(local_pos))
            r = self.rows[pos]
            out.append((r["doc_id"], r["node"], round(s, 4)))
        return out


_cache: dict = {}


def _query_vector(query: str):
    """같은 요청에서 좌표 집합만 바꿔 반복 검색할 때 질의 임베딩을 재사용한다."""
    from lawrag.core import embedding

    cache = _cache.setdefault("query_vectors", {})
    cache_key: object = query
    if _adapter_enabled():
        snapshot = current_content_snapshot(required=True)
        assert snapshot is not None
        cache_key = (_require_runtime_model(snapshot), query)
    if cache_key in cache:
        return cache[cache_key]
    value = embedding.encode_one(query)
    if value is None:
        return None
    cache[cache_key] = value
    while len(cache) > 128:
        cache.pop(next(iter(cache)))
    return value


def current(*, content_snapshot: ContentSnapshot | None = None) -> Optional[VectorIndex]:
    """색인 로드 (mtime 캐시). 없으면 None — 벡터 단은 빠진다."""
    if content_snapshot is None and _adapter_enabled():
        content_snapshot = current_content_snapshot(required=True)
    if content_snapshot is not None:
        if not _has_bound_vector_index(content_snapshot):
            return None
        model_fingerprint = _require_runtime_model(content_snapshot)
        d = content_snapshot.runtime_path("RAG_VECTOR_STORE")
        npz, meta = d / "vectors.npz", d / "meta.jsonl"
        identity = load_vector_identity(
            d,
            snapshot=content_snapshot,
            model_fingerprint=model_fingerprint,
        )
        sig = (
            "sourceset-vector-index-v1",
            content_snapshot.content_fingerprint("vector"),
            identity["identity_sha256"],
        )
        if _cache.get("sig") != sig:
            import numpy as np

            try:
                rows = [json.loads(line) for line in meta.read_text(encoding="utf-8").splitlines()]
            except (OSError, json.JSONDecodeError) as exc:
                raise ContentSnapshotError(f"cannot read vector metadata: {exc}") from exc
            if any(not isinstance(row, dict) for row in rows):
                raise ContentSnapshotError("vector metadata rows must be objects")
            try:
                mat = np.load(npz, allow_pickle=False)["v"].astype(np.float32)
            except Exception as exc:
                raise ContentSnapshotError(f"cannot read vector matrix: {exc}") from exc
            if len(rows) != len(mat) or len(rows) != identity["row_count"]:
                raise ContentSnapshotError(
                    f"vector meta/matrix/identity row mismatch: "
                    f"{len(rows)}/{len(mat)}/{identity['row_count']}"
                )
            allowed_docs = set(content_snapshot.document_ids())
            row_docs = [row.get("doc_id") for row in rows]
            if any(not isinstance(doc_id, str) or doc_id not in allowed_docs for doc_id in row_docs):
                raise ContentSnapshotError("vector index contains an unmapped document")
            coordinates = [(row.get("doc_id"), row.get("node")) for row in rows]
            if len(coordinates) != len(set(coordinates)):
                raise ContentSnapshotError("vector index contains duplicate coordinates")
            _cache["index"] = VectorIndex(
                rows,
                mat,
                content_snapshot_sha256=content_snapshot.content_snapshot_sha256,
                content_fingerprint=content_snapshot.content_fingerprint("vector"),
                identity=identity,
            )
            _cache["sig"] = sig
            log.info("SourceSet 벡터 색인 로드 — %d행: %s", len(rows), d)
        return _cache.get("index")

    d = sections_dir()
    npz, meta = d / "vectors.npz", d / "meta.jsonl"
    if not (npz.exists() and meta.exists()):
        return None
    sig = (npz.stat().st_mtime_ns, meta.stat().st_mtime_ns)
    if _cache.get("sig") != sig:
        try:
            import numpy as np

            rows = [json.loads(x) for x in
                    meta.read_text(encoding="utf-8").splitlines()]
            mat = np.load(npz)["v"].astype(np.float32)
            if len(rows) != len(mat):
                log.warning("벡터 색인 불일치 — meta %d행, 행렬 %d행: %s",
                            len(rows), len(mat), d)
                return None
            _cache["index"] = VectorIndex(rows, mat)
            _cache["sig"] = sig
            log.info("벡터 색인 로드 — %d행: %s", len(rows), d)
        except Exception as exc:
            log.warning("벡터 색인 로드 실패 — 벡터 단은 빠진다: %s", exc)
            return None
    return _cache.get("index")


def search(query: str, topk: int = TOPK,
           doc_ids: Optional[frozenset] = None,
           coordinates: Optional[frozenset[tuple]] = None,
           minimum: float = VECTOR_MIN) -> list[tuple]:
    """질의 → [(doc_id, node, cosine)]. 어떤 이유로든 못 하면 빈 목록 —
    호출부(search.py)는 벡터가 '없다'와 '못 한다'를 구별할 필요가 없다.
    doc_ids 는 질의 스코프(Index.scope) — 진입은 그 안에서만."""
    from lawrag.core import embedding
    from lawrag.core.rag import switches as switches_mod

    if not switches_mod.is_on("vector_entry"):
        return []

    snapshot = None
    if _adapter_enabled():
        snapshot = current_content_snapshot(required=True)
        assert snapshot is not None
        if not _has_bound_vector_index(snapshot):
            return []
        _require_runtime_model(snapshot)

    if not embedding.available():
        if snapshot is not None:
            raise ContentSnapshotError("pinned vector encoder is unavailable")
        log.debug("임베딩 모델 없음 — 벡터 단 생략")
        return []
    qv = _query_vector(query)
    if qv is None:
        if snapshot is not None:
            raise ContentSnapshotError("pinned vector query encoding failed")
        log.debug("질의 임베딩 실패 — 벡터 단 생략")
        return []
    if backend() == "qdrant":
        if snapshot is not None:
            from lawrag.core.rag import qdrant_store

            try:
                remote = qdrant_store.search(
                    qv,
                    topk=topk,
                    doc_ids=doc_ids,
                    coordinates=coordinates,
                    minimum=minimum,
                    content_snapshot=snapshot,
                )
            except ContentSnapshotError:
                raise
            except Exception as exc:
                raise ContentSnapshotError(
                    "release-bound Qdrant query failed"
                ) from exc
            # Qdrant is a mutable accelerator, not the legal index authority.
            # Recompute the same top-k from the release-proved file matrix and
            # accept the remote result only when coordinates/order and rounded
            # scores agree.  This closes the hole where an identity payload is
            # retained while point vectors are changed underneath it.
            canonical_index = current(content_snapshot=snapshot)
            if canonical_index is None:
                raise ContentSnapshotError(
                    "release-proved vector index is unavailable for Qdrant verification"
                )
            canonical = canonical_index.search(
                qv,
                topk=topk,
                doc_ids=doc_ids,
                coordinates=coordinates,
                minimum=minimum,
            )
            if len(remote) != len(canonical) or any(
                left[:2] != right[:2] or abs(float(left[2]) - float(right[2])) > 0.001
                for left, right in zip(remote, canonical)
            ):
                raise ContentSnapshotError(
                    "Qdrant result disagrees with the release-proved vector index"
                )
            out = canonical
        else:
            try:
                from lawrag.core.rag import qdrant_store
                out = qdrant_store.search(qv, topk=topk, doc_ids=doc_ids,
                                          coordinates=coordinates, minimum=minimum)
            except Exception as exc:
                log.warning("Qdrant 검색 실패 — 벡터 단은 빠진다: %s", exc)
                return []
    else:
        idx = current(content_snapshot=snapshot) if snapshot is not None else current()
        if idx is None:
            log.debug("벡터 색인 없음 — 벡터 단 생략")
            return []
        out = idx.search(qv, topk=topk, doc_ids=doc_ids,
                         coordinates=coordinates, minimum=minimum)
    log.debug("벡터 검색 '%s' → %d건 (문턱 %.2f)", query[:40], len(out), VECTOR_MIN)
    return out
