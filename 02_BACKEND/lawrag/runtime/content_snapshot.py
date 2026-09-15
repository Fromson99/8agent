"""Runtime-owned immutable release/SourceSet identity carried through one RAG process.

This module contains no legacy path discovery.  A trusted bootstrap resolves a
release and its SourceSet first, creates :class:`ContentSnapshot`, and pins it
before the RAG router is imported.  Downstream loaders may either see no
snapshot (the explicit legacy rollback mode) or this exact immutable object;
they must never synthesize a partial identity from environment variables.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import stat
from threading import RLock
from typing import Any, Mapping

from lawrag.datasets.catalog import (
    DatasetContractError,
    MaterializedSourceSet,
    SourceSetArtifactLock,
    SourceSetLock,
    source_set_lock_from_mapping,
)
from lawrag.platform.release import (
    ActiveReleasePointer,
    ReleaseManifest,
    RuntimeBindingDocument,
)


SCHEMA_VERSION = "rag-content-snapshot-v1"
COMPACT_SCHEMA_VERSION = "rag-content-snapshot-compact-v1"
ARTIFACT_PROVENANCE_SCHEMA = "rag-artifact-provenance-v1"
INDEX_PROVENANCE_SCHEMA = "rag-index-provenance-v1"
RETRIEVAL_RUNTIME_SCHEMA = "rag-retrieval-runtime-v1"


class ContentSnapshotError(RuntimeError):
    """A request attempted to mix data from different immutable generations."""


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


@dataclass(frozen=True)
class ArtifactProvenance:
    """Stable coordinate for one selected SourceSet artifact."""

    qualified_id: str
    package_id: str
    dataset_id: str
    version_id: str
    build_id: str
    manifest_sha256: str
    logical_id: str
    role: str
    source_path: str
    artifact_sha256: str
    contributors: tuple[str, ...]
    document_id: str | None
    # Deployment location is deliberately outside the content identity.  The
    # runtime binding authenticates its root; artifact SHA-256 authenticates the
    # bytes.  Absolute paths can differ between local and GenOS installations.
    materialized_path: str | None = field(default=None, compare=False, repr=False)

    @classmethod
    def from_lock(
        cls,
        artifact: SourceSetArtifactLock,
        *,
        materialized_path: Path | None = None,
    ) -> "ArtifactProvenance":
        return cls(
            qualified_id=artifact.qualified_id,
            package_id=artifact.package_id,
            dataset_id=artifact.dataset_id,
            version_id=artifact.version_id,
            build_id=artifact.build_id,
            manifest_sha256=artifact.manifest_sha256,
            logical_id=artifact.logical_id,
            role=artifact.role,
            source_path=artifact.path,
            artifact_sha256=artifact.sha256,
            contributors=artifact.contributors,
            document_id=artifact.document_id,
            materialized_path=(
                str(materialized_path.absolute())
                if materialized_path is not None
                else None
            ),
        )

    def receipt(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": ARTIFACT_PROVENANCE_SCHEMA,
            "qualified_id": self.qualified_id,
            "package_id": self.package_id,
            "dataset_id": self.dataset_id,
            "version_id": self.version_id,
            "build_id": self.build_id,
            "manifest_sha256": self.manifest_sha256,
            "logical_id": self.logical_id,
            "role": self.role,
            "source_path": self.source_path,
            "artifact_sha256": self.artifact_sha256,
            "contributors": list(self.contributors),
        }
        if self.document_id is not None:
            value["document_id"] = self.document_id
        return value

    def verified_bytes(self) -> bytes:
        """Read the pinned regular file and reject replacement or mutation."""

        if self.materialized_path is None:
            raise ContentSnapshotError(
                f"artifact has no verified materialized location: {self.qualified_id}"
            )
        path = Path(self.materialized_path)
        try:
            before = path.lstat()
        except OSError as exc:
            raise ContentSnapshotError(
                f"cannot stat materialized artifact {self.qualified_id}: {exc}"
            ) from exc
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise ContentSnapshotError(
                f"materialized artifact is not a regular file: {self.qualified_id}"
            )
        no_follow = getattr(os, "O_NOFOLLOW", None)
        if no_follow is None:
            raise ContentSnapshotError("artifact reads require no-follow file opens")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | no_follow
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ContentSnapshotError(
                f"cannot safely open materialized artifact {self.qualified_id}: {exc}"
            ) from exc
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
                raise ContentSnapshotError(
                    f"materialized artifact changed before read: {self.qualified_id}"
                )
            chunks: list[bytes] = []
            digest = hashlib.sha256()
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                digest.update(chunk)
            after = os.fstat(descriptor)
            if identity(opened) != identity(after):
                raise ContentSnapshotError(
                    f"materialized artifact changed during read: {self.qualified_id}"
                )
        finally:
            os.close(descriptor)
        if digest.hexdigest() != self.artifact_sha256:
            raise ContentSnapshotError(
                f"materialized artifact hash mismatch: {self.qualified_id}"
            )
        return b"".join(chunks)

    def verified_json(self) -> Mapping[str, Any]:
        try:
            value = json.loads(self.verified_bytes().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContentSnapshotError(
                f"materialized artifact is not valid UTF-8 JSON: {self.qualified_id}"
            ) from exc
        if not isinstance(value, Mapping):
            raise ContentSnapshotError(
                f"materialized JSON artifact root must be an object: {self.qualified_id}"
            )
        return value


@dataclass(frozen=True)
class SnapshotIndexBinding:
    """Release-declared identity of one query index."""

    kind: str
    artifact_id: str
    artifact_sha256: str
    build_fingerprint: str
    embedding_model_fingerprint: str | None

    def receipt(self) -> dict[str, Any]:
        return {
            "schema_version": INDEX_PROVENANCE_SCHEMA,
            "kind": self.kind,
            "artifact_id": self.artifact_id,
            "artifact_sha256": self.artifact_sha256,
            "build_fingerprint": self.build_fingerprint,
            "embedding_model_fingerprint": self.embedding_model_fingerprint,
        }


@dataclass(frozen=True)
class ContentSnapshot:
    """The complete data/code/index identity pinned for retrieval."""

    release_id: str
    release_generation: int
    release_manifest_sha256: str
    active_pointer_sha256: str
    source_set_id: str
    source_set_generation: str
    source_set_sha256: str
    cross_dataset_relations: bool
    export_allowed: bool
    source_set_lock_sha256: str
    source_set_lock_artifact_sha256: str
    source_set_materialization_sha256: str
    source_set_materialization_receipt_sha256: str
    catalog_sha256: str
    catalog_artifact_sha256: str
    semantic_generation: str
    authority_generation: str
    semantic_content_sha256: str
    runtime_binding_sha256: str
    main_generation: int
    main_state_sha256: str
    main_promotion_receipt_sha256: str | None
    main_promotion_plan_sha256: str | None
    indexes: tuple[SnapshotIndexBinding, ...]
    artifacts: tuple[ArtifactProvenance, ...]
    runtime_paths: tuple[tuple[str, str], ...] = field(compare=False, repr=False)
    runtime_artifact_paths: tuple[tuple[str, str], ...] = field(
        compare=False, repr=False
    )
    content_snapshot_sha256: str

    def _core_receipt(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "release_id": self.release_id,
            "release_generation": self.release_generation,
            "release_manifest_sha256": self.release_manifest_sha256,
            "active_pointer_sha256": self.active_pointer_sha256,
            "source_set_id": self.source_set_id,
            "source_set_generation": self.source_set_generation,
            "source_set_sha256": self.source_set_sha256,
            "cross_dataset_relations": self.cross_dataset_relations,
            "export_allowed": self.export_allowed,
            "source_set_lock_sha256": self.source_set_lock_sha256,
            "source_set_lock_artifact_sha256": self.source_set_lock_artifact_sha256,
            "source_set_materialization_sha256": self.source_set_materialization_sha256,
            "source_set_materialization_receipt_sha256": (
                self.source_set_materialization_receipt_sha256
            ),
            "catalog_sha256": self.catalog_sha256,
            "catalog_artifact_sha256": self.catalog_artifact_sha256,
            "semantic_generation": self.semantic_generation,
            "authority_generation": self.authority_generation,
            "semantic_content_sha256": self.semantic_content_sha256,
            "runtime_binding_sha256": self.runtime_binding_sha256,
            "main_generation": self.main_generation,
            "main_state_sha256": self.main_state_sha256,
            "main_promotion_receipt_sha256": (
                self.main_promotion_receipt_sha256
            ),
            "main_promotion_plan_sha256": self.main_promotion_plan_sha256,
            "indexes": [
                row.receipt() for row in self.indexes
            ],
            "artifacts": [row.receipt() for row in self.artifacts],
        }

    def receipt(self) -> dict[str, Any]:
        value = self._core_receipt()
        value["content_snapshot_sha256"] = self.content_snapshot_sha256
        return value

    def provenance_for_document(self, document_id: str) -> ArtifactProvenance:
        rows = list(self.provenances_for_document(document_id))
        structure_rows = [row for row in rows if row.role == "structure"]
        if len(structure_rows) == 1:
            return structure_rows[0]
        raise ContentSnapshotError(
            f"document has no unique canonical structure artifact: {document_id}"
        )

    def provenances_for_document(
        self, document_id: str
    ) -> tuple[ArtifactProvenance, ...]:
        rows = tuple(row for row in self.artifacts if row.document_id == document_id)
        if not rows:
            raise ContentSnapshotError(
                f"document is not mapped by the active SourceSet: {document_id}"
            )
        return rows

    def document_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    row.document_id
                    for row in self.artifacts
                    if row.role == "structure" and row.document_id is not None
                }
            )
        )

    def index_binding(self, kind: str) -> SnapshotIndexBinding:
        rows = [row for row in self.indexes if row.kind == kind]
        if len(rows) != 1:
            raise ContentSnapshotError(
                f"release has no unique {kind!r} index binding"
            )
        return rows[0]

    def content_fingerprint(self, kind: str) -> str:
        """Deterministic cache identity for a release-bound retrieval index."""

        binding = self.index_binding(kind)
        return _digest(
            {
                "schema_version": "rag-content-fingerprint-v1",
                "content_snapshot_sha256": self.content_snapshot_sha256,
                "source_set_sha256": self.source_set_sha256,
                "semantic_generation": self.semantic_generation,
                "authority_generation": self.authority_generation,
                "index": binding.receipt(),
                "artifacts": [
                    {
                        "qualified_id": row.qualified_id,
                        "sha256": row.artifact_sha256,
                        "role": row.role,
                        "document_id": row.document_id,
                    }
                    for row in self.artifacts
                ],
            }
        )

    def require_materialized(self) -> None:
        missing = [row.qualified_id for row in self.artifacts if row.materialized_path is None]
        if missing:
            raise ContentSnapshotError(
                "content snapshot has no materialized artifact paths: "
                + ", ".join(missing[:5])
            )

    def runtime_path(self, key: str) -> Path:
        matches = [Path(path) for name, path in self.runtime_paths if name == key]
        if len(matches) != 1:
            raise ContentSnapshotError(f"runtime binding path is unavailable: {key}")
        return matches[0]

    def runtime_artifact_path(self, key: str) -> Path:
        """Return a release-proof artifact location, never an ambient path."""

        matches = [
            Path(path) for name, path in self.runtime_artifact_paths if name == key
        ]
        if len(matches) != 1:
            raise ContentSnapshotError(
                f"runtime artifact binding is unavailable: {key}"
            )
        return matches[0]

    def semantic_path(self, *parts: str) -> Path:
        """Resolve one conventional component below the proved semantic tree.

        The complete tree is already hashed by ``semantics.content``.  Fixed
        relative component names let consumers share that authority without
        adding mutable environment paths or a second, competing manifest.
        """

        root = self.runtime_artifact_path("semantics.content")
        if root.is_symlink() or not root.is_dir():
            raise ContentSnapshotError(
                "release semantic content must be a directory"
            )
        if any(
            not isinstance(part, str)
            or not part
            or Path(part).is_absolute()
            or part in {".", ".."}
            or len(Path(part).parts) != 1
            for part in parts
        ):
            raise ContentSnapshotError("invalid semantic component path")
        target = root.joinpath(*parts)
        current = root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise ContentSnapshotError(
                    "semantic component path contains a symlink"
                )
        try:
            target.resolve(strict=False).relative_to(root.resolve())
        except ValueError as exc:
            raise ContentSnapshotError(
                "semantic component path escapes the release artifact"
            ) from exc
        return target

    def _location_key(self) -> tuple[tuple[str, str], ...]:
        artifact_paths = tuple(
            sorted(
                (row.qualified_id, str(row.materialized_path or ""))
                for row in self.artifacts
            )
        )
        return (
            tuple(sorted(self.runtime_paths))
            + tuple(sorted(self.runtime_artifact_paths))
            + artifact_paths
        )

    def compact_receipt(self) -> dict[str, Any]:
        """Small request-level identity; artifact details stay on evidence rows."""

        return {
            "schema_version": COMPACT_SCHEMA_VERSION,
            "release_id": self.release_id,
            "release_generation": self.release_generation,
            "release_manifest_sha256": self.release_manifest_sha256,
            "source_set_id": self.source_set_id,
            "source_set_generation": self.source_set_generation,
            "source_set_sha256": self.source_set_sha256,
            "cross_dataset_relations": self.cross_dataset_relations,
            "export_allowed": self.export_allowed,
            "source_set_lock_sha256": self.source_set_lock_sha256,
            "source_set_lock_artifact_sha256": self.source_set_lock_artifact_sha256,
            "source_set_materialization_sha256": self.source_set_materialization_sha256,
            "source_set_materialization_receipt_sha256": (
                self.source_set_materialization_receipt_sha256
            ),
            "catalog_sha256": self.catalog_sha256,
            "catalog_artifact_sha256": self.catalog_artifact_sha256,
            "semantic_generation": self.semantic_generation,
            "authority_generation": self.authority_generation,
            "runtime_binding_sha256": self.runtime_binding_sha256,
            "main_generation": self.main_generation,
            "main_state_sha256": self.main_state_sha256,
            "main_promotion_receipt_sha256": (
                self.main_promotion_receipt_sha256
            ),
            "main_promotion_plan_sha256": self.main_promotion_plan_sha256,
            "content_snapshot_sha256": self.content_snapshot_sha256,
        }


def create_content_snapshot(
    *,
    pointer: ActiveReleasePointer,
    release: ReleaseManifest,
    runtime_binding: RuntimeBindingDocument,
    source_set_lock: SourceSetLock,
    catalog_sha256: str,
    catalog_artifact_sha256: str,
    materialized: MaterializedSourceSet | None = None,
    runtime_paths: Mapping[str, str | Path] | None = None,
    runtime_artifact_paths: Mapping[str, str | Path] | None = None,
) -> ContentSnapshot:
    """Cross-check all trusted authorities and derive one immutable identity."""

    try:
        parsed_lock = source_set_lock_from_mapping(source_set_lock.receipt())
    except DatasetContractError as exc:
        raise ContentSnapshotError(f"SourceSet lock is invalid: {exc}") from exc
    if parsed_lock != source_set_lock:
        raise ContentSnapshotError("SourceSet lock is not canonical")

    mismatches: list[str] = []
    if pointer.release_id != release.release_id:
        mismatches.append("pointer.release_id")
    if pointer.target != release.target:
        mismatches.append("pointer.target")
    if pointer.release_manifest_sha256 != release.manifest_sha256:
        mismatches.append("pointer.release_manifest_sha256")
    if runtime_binding.release_id != release.release_id:
        mismatches.append("runtime_binding.release_id")
    if runtime_binding.release_manifest_sha256 != release.manifest_sha256:
        mismatches.append("runtime_binding.release_manifest_sha256")
    if runtime_binding.source_set_sha256 != release.source_set.sha256:
        mismatches.append("runtime_binding.source_set_sha256")
    if not runtime_binding.sealed:
        mismatches.append("runtime_binding.sealed")
    if runtime_binding.code_package_sha256 != release.code_package_sha256:
        mismatches.append("runtime_binding.code_package_sha256")
    if source_set_lock.source_set_id != release.source_set.source_set_id:
        mismatches.append("source_set_id")
    if source_set_lock.generation_id != release.source_set.generation_id:
        mismatches.append("source_set_generation")
    if source_set_lock.source_set_sha256 != release.source_set.sha256:
        mismatches.append("source_set_sha256")
    if source_set_lock.export_allowed is not release.source_set.export_allowed:
        mismatches.append("source_set.export_allowed")
    if release.semantics.source_set_sha256 != release.source_set.sha256:
        mismatches.append("semantics.source_set_sha256")
    for index in release.indexes:
        if index.source_set_sha256 != release.source_set.sha256:
            mismatches.append(f"index.{index.kind}.source_set_sha256")
        if index.semantic_generation != release.semantics.generation_id:
            mismatches.append(f"index.{index.kind}.semantic_generation")
    runtime_proofs = {row.key: row for row in runtime_binding.artifacts}
    main_proof = runtime_proofs.get("main.state")
    if main_proof is None or main_proof.content_sha256 != release.main.state_sha256:
        mismatches.append("runtime.main.state")
    semantic_proof = runtime_proofs.get("semantics.content")
    if (
        semantic_proof is None
        or semantic_proof.content_sha256 != release.semantics.content_sha256
    ):
        mismatches.append("runtime.semantics.content")
    promotion_proof = runtime_proofs.get("main.promotion_receipt")
    promotion_plan_proof = runtime_proofs.get("main.promotion_plan")
    if release.main.generation > 0:
        if (
            promotion_proof is None
            or promotion_proof.content_sha256
            != release.main.promotion_receipt_sha256
        ):
            mismatches.append("runtime.main.promotion_receipt")
        if (
            promotion_plan_proof is None
            or promotion_plan_proof.content_sha256
            != release.main.promotion_plan_sha256
        ):
            mismatches.append("runtime.main.promotion_plan")
    elif promotion_proof is not None or promotion_plan_proof is not None:
        mismatches.append("runtime.main.promotion_evidence.unexpected")
    for index in release.indexes:
        proof = runtime_proofs.get(f"index.{index.kind}")
        if proof is None:
            mismatches.append(f"runtime.index.{index.kind}.missing")
        elif (
            proof.content_sha256 != index.artifact_sha256
            or proof.build_fingerprint != index.build_fingerprint
            or proof.embedding_model_fingerprint != index.embedding_model_fingerprint
        ):
            mismatches.append(f"runtime.index.{index.kind}.identity")

    source_binding = release.source_set
    serving_field_names = (
        "lock_sha256",
        "lock_artifact_sha256",
        "materialization_sha256",
        "materialization_receipt_sha256",
        "catalog_sha256",
        "catalog_artifact_sha256",
    )
    serving_values = {
        name: getattr(source_binding, name, None) for name in serving_field_names
    }
    serving_bound = any(value is not None for value in serving_values.values())
    if not serving_bound:
        mismatches.append("source_set.serving_proofs.missing")
    elif not all(value is not None for value in serving_values.values()):
        mismatches.append("source_set.serving_proofs.incomplete")
    if serving_bound:
        if serving_values["lock_sha256"] != source_set_lock.lock_sha256:
            mismatches.append("source_set.lock_sha256")
        if serving_values["catalog_sha256"] != catalog_sha256:
            mismatches.append("source_set.catalog_sha256")
        if serving_values["catalog_artifact_sha256"] != catalog_artifact_sha256:
            mismatches.append("source_set.catalog_artifact_sha256")
        if materialized is None:
            mismatches.append("source_set.materialization.missing")
        elif (
            serving_values["materialization_receipt_sha256"]
            != materialized.receipt_sha256
        ):
            mismatches.append("source_set.materialization_receipt_sha256")
        for proof_key, field_name in (
            ("source_set.lock", "lock_artifact_sha256"),
            ("source_set.materialization", "materialization_sha256"),
            ("source_set.catalog", "catalog_artifact_sha256"),
        ):
            proof = runtime_proofs.get(proof_key)
            if proof is None:
                mismatches.append(f"runtime.{proof_key}.missing")
            elif proof.content_sha256 != serving_values[field_name]:
                mismatches.append(f"runtime.{proof_key}.identity")
        if runtime_paths is None:
            mismatches.append("runtime.paths.missing")
        if runtime_artifact_paths is None:
            mismatches.append("runtime.artifact_paths.missing")
    if mismatches:
        raise ContentSnapshotError(
            "active content authorities disagree: " + ", ".join(mismatches)
        )

    normalized_runtime_paths: tuple[tuple[str, str], ...] = ()
    if runtime_paths is not None:
        expected_path_keys = {row.key for row in runtime_binding.paths}
        if set(runtime_paths) != expected_path_keys:
            raise ContentSnapshotError("resolved runtime paths are incomplete or unexpected")
        normalized_runtime_paths = tuple(
            sorted(
                (
                    str(key),
                    str(Path(value).absolute()),
                )
                for key, value in runtime_paths.items()
            )
        )
    normalized_runtime_artifact_paths: tuple[tuple[str, str], ...] = ()
    if runtime_artifact_paths is not None:
        expected_artifact_keys = {row.key for row in runtime_binding.artifacts}
        if set(runtime_artifact_paths) != expected_artifact_keys:
            raise ContentSnapshotError(
                "resolved runtime artifact paths are incomplete or unexpected"
            )
        normalized_runtime_artifact_paths = tuple(
            sorted(
                (str(key), str(Path(value).absolute()))
                for key, value in runtime_artifact_paths.items()
            )
        )

    if not isinstance(catalog_sha256, str) or len(catalog_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in catalog_sha256
    ):
        raise ContentSnapshotError("catalog_sha256 must be an exact lowercase SHA-256")
    if (
        not isinstance(catalog_artifact_sha256, str)
        or len(catalog_artifact_sha256) != 64
        or any(char not in "0123456789abcdef" for char in catalog_artifact_sha256)
    ):
        raise ContentSnapshotError(
            "catalog_artifact_sha256 must be an exact lowercase SHA-256"
        )

    materialized_paths: Mapping[str, Path] = {}
    if materialized is not None:
        if materialized.lock != source_set_lock:
            raise ContentSnapshotError("materialized SourceSet uses another lock")
        materialized_paths = materialized.verified_artifact_paths()
        if set(materialized_paths) != {
            artifact.qualified_id for artifact in source_set_lock.artifacts
        }:
            raise ContentSnapshotError("materialized SourceSet artifact map is incomplete")

    artifact_rows = tuple(
        sorted(
            (
                ArtifactProvenance.from_lock(
                    row, materialized_path=materialized_paths.get(row.qualified_id)
                )
                for row in source_set_lock.artifacts
            ),
            key=lambda row: row.qualified_id,
        )
    )
    qualified = [row.qualified_id for row in artifact_rows]
    if len(qualified) != len(set(qualified)):
        raise ContentSnapshotError("SourceSet contains duplicate qualified artifacts")
    unmapped_structure = [
        row.qualified_id
        for row in artifact_rows
        if row.role == "structure" and row.document_id is None
    ]
    if unmapped_structure:
        raise ContentSnapshotError(
            "SourceSet contains unmapped structure artifacts: "
            + ", ".join(unmapped_structure[:5])
        )
    document_structures: dict[str, list[str]] = {}
    for row in artifact_rows:
        if row.role == "structure" and row.document_id is not None:
            document_structures.setdefault(row.document_id, []).append(row.qualified_id)
    duplicates = sorted(
        document_id
        for document_id, structures in document_structures.items()
        if len(structures) != 1
    )
    if duplicates:
        raise ContentSnapshotError(
            "SourceSet has duplicate structure artifacts for document IDs: "
            + ", ".join(duplicates)
        )

    index_rows = tuple(
        sorted(
            (
                SnapshotIndexBinding(
                    kind=row.kind,
                    artifact_id=row.artifact_id,
                    artifact_sha256=row.artifact_sha256,
                    build_fingerprint=row.build_fingerprint,
                    embedding_model_fingerprint=row.embedding_model_fingerprint,
                )
                for row in release.indexes
            )
            ,
            key=lambda row: row.kind,
        )
    )
    provisional = ContentSnapshot(
        release_id=release.release_id,
        release_generation=pointer.generation,
        release_manifest_sha256=release.manifest_sha256,
        active_pointer_sha256=pointer.pointer_sha256,
        source_set_id=source_set_lock.source_set_id,
        source_set_generation=source_set_lock.generation_id,
        source_set_sha256=source_set_lock.source_set_sha256,
        cross_dataset_relations=source_set_lock.cross_dataset_relations,
        export_allowed=source_set_lock.export_allowed,
        source_set_lock_sha256=source_set_lock.lock_sha256,
        source_set_lock_artifact_sha256=str(
            serving_values["lock_artifact_sha256"]
        ),
        source_set_materialization_sha256=str(
            serving_values["materialization_sha256"]
        ),
        source_set_materialization_receipt_sha256=str(
            serving_values["materialization_receipt_sha256"]
        ),
        catalog_sha256=catalog_sha256,
        catalog_artifact_sha256=catalog_artifact_sha256,
        semantic_generation=release.semantics.generation_id,
        authority_generation=release.semantics.authority_generation,
        semantic_content_sha256=release.semantics.content_sha256,
        runtime_binding_sha256=runtime_binding.binding_sha256,
        main_generation=release.main.generation,
        main_state_sha256=release.main.state_sha256,
        main_promotion_receipt_sha256=(
            release.main.promotion_receipt_sha256
        ),
        main_promotion_plan_sha256=release.main.promotion_plan_sha256,
        indexes=index_rows,
        artifacts=artifact_rows,
        runtime_paths=normalized_runtime_paths,
        runtime_artifact_paths=normalized_runtime_artifact_paths,
        content_snapshot_sha256="",
    )
    return ContentSnapshot(
        **{
            **provisional.__dict__,
            "content_snapshot_sha256": _digest(provisional._core_receipt()),
        }
    )


_PIN_LOCK = RLock()
_PINNED: ContentSnapshot | None = None
_RUNTIME_PINNED: dict[str, Any] | None = None


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_retrieval_runtime_core(value: Mapping[str, Any]) -> None:
    if set(value) != {
        "schema_version",
        "content_snapshot_sha256",
        "llm",
        "vector",
        "query_shortcuts",
    }:
        raise ContentSnapshotError("retrieval runtime receipt has unexpected fields")
    if value.get("schema_version") != RETRIEVAL_RUNTIME_SCHEMA:
        raise ContentSnapshotError("unsupported retrieval runtime receipt")
    snapshot = current_content_snapshot(required=True)
    assert snapshot is not None
    if value.get("content_snapshot_sha256") != snapshot.content_snapshot_sha256:
        raise ContentSnapshotError("retrieval runtime binds a different content snapshot")

    llm = value.get("llm")
    if not isinstance(llm, Mapping) or set(llm) != {
        "enabled",
        "backend",
        "model",
        "model_revision",
        "model_artifact_sha256",
        "endpoint",
        "serving_id",
        "tenant_id",
        "descriptor_sha256",
        "credential_binding_id",
        "credential_binding_version",
        "trust_policy_id",
        "credential_configured",
        "trust_zone",
        "export_allowed",
    }:
        raise ContentSnapshotError("retrieval runtime has an invalid LLM binding")
    if (
        not isinstance(llm.get("enabled"), bool)
        or not isinstance(llm.get("export_allowed"), bool)
        or not isinstance(llm.get("credential_configured"), bool)
    ):
        raise ContentSnapshotError("retrieval runtime LLM flags must be boolean")
    if llm.get("export_allowed") is not snapshot.export_allowed:
        raise ContentSnapshotError(
            "retrieval runtime export policy differs from the SourceSet"
        )
    if llm.get("backend") not in {
        "disabled", "anthropic", "local", "genos", "openrouter"
    }:
        raise ContentSnapshotError("retrieval runtime has an unsupported LLM backend")
    if llm.get("model") != "claude-haiku-4-5-20251001":
        raise ContentSnapshotError("retrieval runtime has an unsupported product model")
    if not _is_sha256(llm.get("descriptor_sha256")):
        raise ContentSnapshotError("retrieval runtime has no LLM descriptor proof")
    if bool(llm["enabled"]) != (llm["backend"] != "disabled"):
        raise ContentSnapshotError("retrieval runtime LLM enablement is inconsistent")
    endpoint = llm.get("endpoint")
    if llm["enabled"] and (not isinstance(endpoint, str) or not endpoint):
        raise ContentSnapshotError("enabled retrieval LLM has no endpoint")
    if not llm["enabled"] and endpoint is not None:
        raise ContentSnapshotError("disabled retrieval LLM cannot have an endpoint")
    if llm["backend"] == "disabled" and (
        llm.get("serving_id") is not None
        or llm.get("tenant_id") is not None
        or llm.get("model_revision") is not None
        or llm.get("model_artifact_sha256") is not None
        or llm.get("credential_binding_id") is not None
        or llm.get("credential_binding_version") is not None
        or llm.get("trust_policy_id") is not None
        or llm.get("credential_configured") is not False
        or llm.get("trust_zone") != "none"
    ):
        raise ContentSnapshotError("disabled retrieval LLM binding is inconsistent")
    if llm["enabled"] and (
        not isinstance(llm.get("model_revision"), str)
        or not llm["model_revision"]
        or not _is_sha256(llm.get("model_artifact_sha256"))
        or any(
            not isinstance(llm.get(field), str) or not llm[field]
            for field in (
                "credential_binding_id",
                "credential_binding_version",
                "trust_policy_id",
            )
        )
        or llm.get("credential_configured") is not True
    ):
        raise ContentSnapshotError("enabled retrieval LLM identity is incomplete")
    if llm["backend"] == "genos":
        if (
            not isinstance(llm.get("serving_id"), str)
            or not llm["serving_id"].isdigit()
            or not isinstance(llm.get("tenant_id"), str)
            or not llm["tenant_id"]
            or llm.get("trust_zone") not in {"internal", "external"}
        ):
            raise ContentSnapshotError("GenOS LLM binding is inconsistent")
    elif llm["backend"] != "disabled" and (
        llm.get("serving_id") is not None or llm.get("tenant_id") is not None
    ):
        raise ContentSnapshotError("non-GenOS LLM cannot bind GenOS identity")
    if llm["backend"] in {"anthropic", "openrouter"} and (
        llm.get("trust_zone") != "external"
    ):
        raise ContentSnapshotError("external LLM trust-zone binding is inconsistent")
    if llm["backend"] == "local" and llm.get("trust_zone") not in {
        "local", "internal", "external"
    }:
        raise ContentSnapshotError("local LLM trust-zone binding is invalid")
    if not llm["export_allowed"] and llm.get("trust_zone") == "external":
        raise ContentSnapshotError("restricted content binds an external LLM")

    vector = value.get("vector")
    if not isinstance(vector, Mapping) or set(vector) != {
        "enabled",
        "backend",
        "embedding_model_fingerprint",
        "query_timeout_seconds",
        "trust_zone",
        "encoder",
        "qdrant",
    }:
        raise ContentSnapshotError("retrieval runtime has an invalid vector binding")
    if not isinstance(vector.get("enabled"), bool) or vector.get("backend") not in {
        "file", "qdrant"
    }:
        raise ContentSnapshotError("retrieval runtime vector flags are invalid")
    fingerprint = vector.get("embedding_model_fingerprint")
    if vector["enabled"] and not _is_sha256(fingerprint):
        raise ContentSnapshotError("enabled vector runtime has no model fingerprint")
    if not vector["enabled"] and fingerprint is not None:
        raise ContentSnapshotError("disabled vector runtime has a model fingerprint")
    encoder = vector.get("encoder")
    encoder_fields = {
        "backend",
        "endpoint",
        "serving_id",
        "tenant_id",
        "trust_zone",
        "model_id",
        "model_revision",
        "model_artifact_sha256",
        "dimensions",
        "descriptor_sha256",
        "credential_binding_id",
        "credential_binding_version",
        "trust_policy_id",
        "local_artifact_verified",
        "credential_configured",
    }
    if vector["enabled"]:
        if not isinstance(encoder, Mapping) or set(encoder) != encoder_fields:
            raise ContentSnapshotError("enabled vector runtime has no encoder binding")
        if encoder.get("backend") not in {"local", "genos"}:
            raise ContentSnapshotError("retrieval runtime encoder backend is invalid")
        if (
            not isinstance(encoder.get("model_id"), str)
            or not encoder["model_id"]
            or not isinstance(encoder.get("model_revision"), str)
            or not encoder["model_revision"]
            or not _is_sha256(encoder.get("model_artifact_sha256"))
            or not _is_sha256(encoder.get("descriptor_sha256"))
            or isinstance(encoder.get("dimensions"), bool)
            or not isinstance(encoder.get("dimensions"), int)
            or encoder["dimensions"] <= 0
            or not isinstance(encoder.get("local_artifact_verified"), bool)
            or not isinstance(encoder.get("credential_configured"), bool)
        ):
            raise ContentSnapshotError("retrieval runtime encoder identity is invalid")
        if encoder["backend"] == "local":
            if (
                encoder.get("endpoint") is not None
                or encoder.get("serving_id") is not None
                or encoder.get("tenant_id") is not None
                or encoder.get("trust_zone") != "local"
                or encoder.get("local_artifact_verified") is not True
                or encoder.get("credential_binding_id") is not None
                or encoder.get("credential_binding_version") is not None
                or encoder.get("trust_policy_id") is not None
                or encoder.get("credential_configured") is not False
            ):
                raise ContentSnapshotError("local encoder binding is inconsistent")
        elif (
            not isinstance(encoder.get("endpoint"), str)
            or not encoder["endpoint"]
            or not isinstance(encoder.get("serving_id"), str)
            or not encoder["serving_id"].isdigit()
            or not isinstance(encoder.get("tenant_id"), str)
            or not encoder["tenant_id"]
            or encoder.get("trust_zone") not in {"internal", "external"}
            or encoder.get("local_artifact_verified") is not False
            or any(
                not isinstance(encoder.get(field), str) or not encoder[field]
                for field in (
                    "credential_binding_id",
                    "credential_binding_version",
                    "trust_policy_id",
                )
            )
            or encoder.get("credential_configured") is not True
        ):
            raise ContentSnapshotError("GenOS encoder binding is inconsistent")
        if not llm["export_allowed"] and encoder.get("trust_zone") == "external":
            raise ContentSnapshotError("restricted content binds an external encoder")
    elif encoder is not None:
        raise ContentSnapshotError("disabled vector runtime cannot bind an encoder")
    qdrant = vector.get("qdrant")
    timeout = vector.get("query_timeout_seconds")
    qdrant_fields = {
        "descriptor_sha256",
        "endpoint",
        "collection",
        "credential_binding_id",
        "credential_binding_version",
        "trust_policy_id",
        "trust_zone",
        "credential_configured",
    }
    if vector["backend"] == "qdrant":
        if not isinstance(qdrant, Mapping) or set(qdrant) != qdrant_fields:
            raise ContentSnapshotError("Qdrant runtime has no exact service binding")
        if (
            not _is_sha256(qdrant.get("descriptor_sha256"))
            or not isinstance(qdrant.get("endpoint"), str)
            or not qdrant["endpoint"]
            or not isinstance(qdrant.get("collection"), str)
            or not qdrant["collection"]
            or any(
                not isinstance(qdrant.get(field), str) or not qdrant[field]
                for field in (
                    "credential_binding_id",
                    "credential_binding_version",
                    "trust_policy_id",
                )
            )
            or qdrant.get("trust_zone") != vector.get("trust_zone")
            or qdrant.get("credential_configured") is not True
        ):
            raise ContentSnapshotError("Qdrant service identity is incomplete")
    elif qdrant is not None:
        raise ContentSnapshotError("file vector runtime cannot bind Qdrant")
    if vector["backend"] == "qdrant" and (
        isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0
    ):
        raise ContentSnapshotError("Qdrant runtime has an invalid query timeout")
    if vector["backend"] == "file" and timeout is not None:
        raise ContentSnapshotError("file vector runtime cannot bind a Qdrant timeout")
    expected_vector_zone = "local" if vector["backend"] == "file" else (
        vector.get("trust_zone")
    )
    if vector.get("trust_zone") != expected_vector_zone or expected_vector_zone not in {
        "local", "internal", "external"
    }:
        raise ContentSnapshotError("retrieval runtime vector trust zone is invalid")
    if not llm["export_allowed"] and vector.get("trust_zone") == "external":
        raise ContentSnapshotError("restricted content binds an external vector store")

    shortcuts = value.get("query_shortcuts")
    if not isinstance(shortcuts, Mapping) or set(shortcuts) != {
        "enabled", "store_sha256"
    } or not isinstance(shortcuts.get("enabled"), bool):
        raise ContentSnapshotError("retrieval runtime has an invalid shortcut binding")
    shortcut_sha = shortcuts.get("store_sha256")
    if bool(shortcuts["enabled"]) != _is_sha256(shortcut_sha):
        raise ContentSnapshotError("retrieval runtime shortcut SHA is inconsistent")


def create_retrieval_runtime_receipt(
    snapshot: ContentSnapshot,
    *,
    llm_runtime: Mapping[str, Any],
    vector_runtime: Mapping[str, Any],
    shortcut_runtime: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind non-content services that can still change a query result.

    Credentials and filesystem locations are intentionally omitted.  Their
    stable public identities are carried beside (not inside) ContentSnapshot,
    avoiding a self-hash cycle for the reviewed shortcut store.
    """

    vector_enabled = bool(vector_runtime.get("enabled"))
    vector_binding = None
    if vector_enabled:
        vector_binding = snapshot.index_binding("vector")
    core = {
        "schema_version": RETRIEVAL_RUNTIME_SCHEMA,
        "content_snapshot_sha256": snapshot.content_snapshot_sha256,
        "llm": {
            "enabled": bool(llm_runtime.get("enabled")),
            "backend": str(llm_runtime.get("backend") or "disabled"),
            "model": str(llm_runtime.get("model") or ""),
            "model_revision": llm_runtime.get("model_revision"),
            "model_artifact_sha256": llm_runtime.get(
                "model_artifact_sha256"
            ),
            "endpoint": llm_runtime.get("endpoint"),
            "serving_id": llm_runtime.get("serving_id"),
            "tenant_id": llm_runtime.get("tenant_id"),
            "descriptor_sha256": llm_runtime.get("descriptor_sha256"),
            "credential_binding_id": llm_runtime.get(
                "credential_binding_id"
            ),
            "credential_binding_version": llm_runtime.get(
                "credential_binding_version"
            ),
            "trust_policy_id": llm_runtime.get("trust_policy_id"),
            "credential_configured": any(
                bool(item)
                for item in (
                    llm_runtime.get("credential_presence") or {}
                ).values()
            ),
            "trust_zone": str(llm_runtime.get("trust_zone") or "none"),
            "export_allowed": bool(llm_runtime.get("export_allowed")),
        },
        "vector": {
            "enabled": vector_enabled,
            "backend": str(vector_runtime.get("backend") or "file"),
            "embedding_model_fingerprint": (
                vector_binding.embedding_model_fingerprint
                if vector_binding is not None else None
            ),
            "query_timeout_seconds": vector_runtime.get(
                "query_timeout_seconds"
            ),
            "trust_zone": str(vector_runtime.get("trust_zone") or "local"),
            "encoder": (
                {
                    "backend": (vector_runtime.get("encoder") or {}).get("backend"),
                    "endpoint": (vector_runtime.get("encoder") or {}).get("endpoint"),
                    "serving_id": (vector_runtime.get("encoder") or {}).get("serving_id"),
                    "tenant_id": (vector_runtime.get("encoder") or {}).get("tenant_id"),
                    "trust_zone": (vector_runtime.get("encoder") or {}).get("trust_zone"),
                    "model_id": (vector_runtime.get("encoder") or {}).get("model_id"),
                    "model_revision": (vector_runtime.get("encoder") or {}).get("model_revision"),
                    "model_artifact_sha256": (vector_runtime.get("encoder") or {}).get("model_artifact_sha256"),
                    "dimensions": (vector_runtime.get("encoder") or {}).get("dimensions"),
                    "descriptor_sha256": (vector_runtime.get("encoder") or {}).get("descriptor_sha256"),
                    "credential_binding_id": (vector_runtime.get("encoder") or {}).get("credential_binding_id"),
                    "credential_binding_version": (vector_runtime.get("encoder") or {}).get("credential_binding_version"),
                    "trust_policy_id": (vector_runtime.get("encoder") or {}).get("trust_policy_id"),
                    "local_artifact_verified": bool(
                        (vector_runtime.get("encoder") or {}).get(
                            "local_artifact_verified"
                        )
                    ),
                    "credential_configured": any(
                        bool(value)
                        for value in (
                            (vector_runtime.get("encoder") or {}).get(
                                "credential_presence"
                            ) or {}
                        ).values()
                    ),
                }
                if vector_enabled else None
            ),
            "qdrant": (
                {
                    "descriptor_sha256": vector_runtime.get("config_sha256"),
                    "endpoint": vector_runtime.get("url"),
                    "collection": vector_runtime.get("collection"),
                    "credential_binding_id": vector_runtime.get(
                        "credential_binding_id"
                    ),
                    "credential_binding_version": vector_runtime.get(
                        "credential_binding_version"
                    ),
                    "trust_policy_id": vector_runtime.get("trust_policy_id"),
                    "trust_zone": vector_runtime.get("trust_zone"),
                    "credential_configured": bool(
                        vector_runtime.get("credential_configured")
                    ),
                }
                if vector_runtime.get("backend") == "qdrant" else None
            ),
        },
        "query_shortcuts": {
            "enabled": bool(shortcut_runtime.get("enabled")),
            "store_sha256": shortcut_runtime.get("sha256"),
        },
    }
    _validate_retrieval_runtime_core(core)
    return {**core, "retrieval_runtime_sha256": _digest(core)}


def bind_retrieval_runtime_receipt(receipt: Mapping[str, Any]) -> None:
    """Pin one exact result-affecting runtime receipt for the process."""

    global _RUNTIME_PINNED
    value = deepcopy(dict(receipt))
    declared = value.pop("retrieval_runtime_sha256", None)
    _validate_retrieval_runtime_core(value)
    if not isinstance(declared, str) or _digest(value) != declared:
        raise ContentSnapshotError("retrieval runtime receipt hash mismatch")
    normalized = deepcopy({**value, "retrieval_runtime_sha256": declared})
    with _PIN_LOCK:
        if _RUNTIME_PINNED is not None and _RUNTIME_PINNED != normalized:
            raise ContentSnapshotError(
                "cannot replace the process retrieval runtime binding"
            )
        _RUNTIME_PINNED = normalized


def current_retrieval_runtime_receipt(*, required: bool = False) -> dict[str, Any] | None:
    with _PIN_LOCK:
        value = None if _RUNTIME_PINNED is None else deepcopy(_RUNTIME_PINNED)
    if required and value is None:
        raise ContentSnapshotError("sealed RAG requires a retrieval runtime receipt")
    if value is not None:
        core = deepcopy(value)
        declared = core.pop("retrieval_runtime_sha256", None)
        _validate_retrieval_runtime_core(core)
        if not isinstance(declared, str) or _digest(core) != declared:
            raise ContentSnapshotError("pinned retrieval runtime receipt was mutated")
    return value


def bind_content_snapshot(snapshot: ContentSnapshot | None) -> None:
    """Pin once per process; a different generation requires a fresh process."""

    global _PINNED
    with _PIN_LOCK:
        if snapshot is None:
            if _PINNED is not None:
                raise ContentSnapshotError(
                    "cannot downgrade a pinned release process to legacy mode"
                )
            return
        if _PINNED is not None and (
            _PINNED.content_snapshot_sha256 != snapshot.content_snapshot_sha256
        ):
            raise ContentSnapshotError(
                "cannot replace the process content snapshot with another generation"
            )
        if _PINNED is not None and _PINNED._location_key() != snapshot._location_key():
            raise ContentSnapshotError(
                "cannot relocate a pinned content snapshot inside one process"
            )
        _PINNED = snapshot


def current_content_snapshot(*, required: bool = False) -> ContentSnapshot | None:
    with _PIN_LOCK:
        snapshot = _PINNED
    if required and snapshot is None:
        raise ContentSnapshotError("RAG SourceSet adapter requires a content snapshot")
    return snapshot


def artifact_provenance_receipt(value: ArtifactProvenance | None) -> dict[str, Any] | None:
    return None if value is None else value.receipt()


def reset_content_snapshot_for_tests() -> None:
    """Testing seam; production code must restart rather than rebind a process."""

    global _PINNED, _RUNTIME_PINNED
    with _PIN_LOCK:
        _PINNED = None
        _RUNTIME_PINNED = None
