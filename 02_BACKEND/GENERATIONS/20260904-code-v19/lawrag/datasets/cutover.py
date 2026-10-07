"""Full DatasetPackage/SourceSet cutover helpers.

The module never recollects or regenerates source data.  It only composes
installed immutable packages, emits policy-specific locks/materializations,
and writes hash-bound operational control records.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from lawrag.datasets.catalog import (
    InstalledCatalog,
    MaterializedSourceSet,
    UnifiedCorpusView,
    load_installed_catalog,
    load_package,
    load_source_set_lock,
    materialize_source_set,
    open_materialized_source_set,
)


SOURCE_SET_SCHEMA = "source-set-v1"
CUTOVER_RECEIPT_SCHEMA = "full-v2-cutover-receipt-v1"
POLICIES: Mapping[str, tuple[str, ...]] = {
    "external-public-v1": ("public",),
    "internal-restricted-v1": ("public", "restricted", "ontology"),
    "experiment-sandbox-v1": ("public", "ontology"),
    "local-operational-v2": ("public", "restricted", "ontology"),
}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def write_immutable_json(path: Path, value: Mapping[str, Any]) -> Path:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != raw:
            raise RuntimeError(f"immutable record already differs: {path}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists():
        raise RuntimeError(f"temporary path already exists: {temporary}")
    temporary.write_bytes(raw)
    os.chmod(temporary, 0o440)
    os.replace(temporary, path)
    return path


def _package_classes(catalog: InstalledCatalog) -> dict[str, str]:
    classes: dict[str, str] = {}
    for row in catalog.packages:
        package = catalog.lookup(row.package_id, row.manifest_sha256)
        if package.dataset_id == "ontology-operational":
            classes[row.package_id] = "ontology"
        else:
            classes[row.package_id] = package.security_class
    return classes


def publish_policy_source_sets(
    workspace: Path,
    *,
    catalog_path: Path,
) -> dict[str, dict[str, Any]]:
    """Publish and re-open four exact policy views from one installed catalog."""

    workspace = workspace.resolve()
    package_root = workspace / "01_DATA/PACKAGES"
    catalog = load_installed_catalog(catalog_path, package_root=package_root)
    classes = _package_classes(catalog)
    output: dict[str, dict[str, Any]] = {}
    trusted_root = workspace / "01_DATA/SOURCE_SETS/MATERIALIZED"
    trusted_root.mkdir(parents=True, exist_ok=True)
    os.chmod(trusted_root, 0o700)

    for policy_id, allowed in POLICIES.items():
        selected = [
            row for row in catalog.packages if classes[row.package_id] in allowed
        ]
        if policy_id == "experiment-sandbox-v1":
            selected = [
                row
                for row in catalog.packages
                if classes[row.package_id] == "ontology"
                or (
                    classes[row.package_id] == "public"
                    and any(
                        token in row.package_id
                        for token in ("source-law-", "source-moleg-", "source-prec-")
                    )
                )
            ]
        if not selected:
            raise RuntimeError(f"policy selected no packages: {policy_id}")
        generation_seed = digest(
            {
                "catalog_sha256": catalog.catalog_sha256,
                "policy_id": policy_id,
                "packages": [row.receipt() for row in selected],
            }
        )
        source_set: dict[str, Any] = {
            "schema_version": SOURCE_SET_SCHEMA,
            "source_set_id": policy_id,
            "generation_id": f"sourceset-{generation_seed[:24]}",
            "conflict_policy": "error",
            "cross_dataset_relations": policy_id != "external-public-v1",
            "members": [
                {"package_id": row.package_id, "priority": position + 1}
                for position, row in enumerate(selected)
            ],
        }
        view: UnifiedCorpusView = catalog.open(source_set)
        source_dir = workspace / "01_DATA/SOURCE_SETS" / policy_id
        source_path = source_dir / f"{source_set['generation_id']}.json"
        write_immutable_json(source_path, source_set)
        lock = view.lock()
        lock_path = source_dir / f"{source_set['generation_id']}.lock.json"
        write_immutable_json(lock_path, lock.receipt())
        loaded_lock = load_source_set_lock(lock_path)
        catalog.resolve_lock(
            loaded_lock,
            expected_source_set_sha256=view.source_set_sha256,
            expected_lock_sha256=lock.lock_sha256,
        )
        materialized_path = trusted_root / policy_id / source_set["generation_id"]
        materialized: MaterializedSourceSet = materialize_source_set(
            view,
            materialized_path,
            lock=loaded_lock,
            relation_policy_enforced=True,
            allow_cross_dataset_relations=source_set["cross_dataset_relations"],
            trusted_root=trusted_root,
        )
        output[policy_id] = {
            "source_set_id": policy_id,
            "generation_id": source_set["generation_id"],
            "source_set_path": source_path.relative_to(workspace).as_posix(),
            "source_set_sha256": view.source_set_sha256,
            "lock_path": lock_path.relative_to(workspace).as_posix(),
            "lock_sha256": lock.lock_sha256,
            "lock_artifact_sha256": hash_file(lock_path),
            "materialized_path": materialized_path.relative_to(workspace).as_posix(),
            "materialization_receipt_sha256": materialized.receipt_sha256,
            "catalog_path": catalog_path.relative_to(workspace).as_posix(),
            "catalog_sha256": catalog.catalog_sha256,
            "catalog_artifact_sha256": hash_file(catalog_path),
            "package_count": len(view.packages),
            "artifact_count": len(view.artifacts),
            "export_allowed": view.export_allowed,
        }
    return output


def publish_lexical_index(
    workspace: Path,
    *,
    source_set: Mapping[str, Any],
    semantic_generation: str,
    authority_generation: str,
) -> dict[str, Any]:
    """Publish an immutable lexical artifact bound to one SourceSet generation."""

    lock = load_source_set_lock(workspace / str(source_set["lock_path"]))
    materialized = open_materialized_source_set(
        workspace / str(source_set["materialized_path"]),
        lock,
        trusted_root=workspace / "01_DATA/SOURCE_SETS/MATERIALIZED",
    )
    materialized_paths = materialized.verified_artifact_paths()
    structures = [
        {
            "document_id": row.document_id,
            "qualified_id": row.qualified_id,
            "sha256": row.sha256,
        }
        for row in lock.artifacts
        if row.role == "structure"
    ]
    structures.sort(key=lambda row: str(row["document_id"]))
    document_ids = sorted(str(row["document_id"]) for row in structures)
    docs: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for row in lock.artifacts:
        if row.role != "structure" or row.document_id is None:
            continue
        payload = json.loads(materialized_paths[row.qualified_id].read_text("utf-8"))
        if (
            payload.get("schema_version") != "rag-structure-artifact-v1"
            or payload.get("document_id") != row.document_id
            or not isinstance(payload.get("meta"), Mapping)
            or not isinstance(payload.get("result"), Mapping)
        ):
            raise RuntimeError(f"invalid runtime structure artifact: {row.qualified_id}")
        docs.append((row.document_id, dict(payload["meta"]), dict(payload["result"])))
    from lawrag.core.rag.index import Index

    entry_count = len(Index.from_docs(docs, apply_structure_fixes=False).entries)
    descriptor = {
        "schema_version": "source-set-index-build-v1",
        "kind": "lexical",
        "source_set_id": source_set["source_set_id"],
        "source_set_generation": source_set["generation_id"],
        "source_set_sha256": source_set["source_set_sha256"],
        "semantic_generation": semantic_generation,
        "authority_generation": authority_generation,
        "structure_artifact_sha256s": [row["sha256"] for row in structures],
        "entry_count": entry_count,
        "builder": "sourceset-structure-identity-v1",
    }
    build_fingerprint = digest(descriptor)
    index_id = f"lexical-{build_fingerprint[:24]}"
    identity_core = {
        "schema_version": "rag-lexical-index-identity-v1",
        "artifact_id": index_id,
        "source_set_id": source_set["source_set_id"],
        "source_set_generation": source_set["generation_id"],
        "source_set_sha256": source_set["source_set_sha256"],
        "semantic_generation": semantic_generation,
        "authority_generation": authority_generation,
        "build_fingerprint": build_fingerprint,
        "document_ids": document_ids,
        "structure_artifacts": structures,
        "entry_count": entry_count,
    }
    identity = {**identity_core, "identity_sha256": digest(identity_core)}
    artifact_raw = canonical_bytes(identity)
    source_sha = hashlib.sha256(artifact_raw).hexdigest()
    root = (
        workspace
        / "01_DATA/INDEXES"
        / str(source_set["source_set_id"])
        / index_id
    )
    artifact = root / "lexical.json"
    if artifact.exists():
        if hash_file(artifact) != source_sha:
            raise RuntimeError(f"immutable lexical index differs: {artifact}")
    else:
        root.mkdir(parents=True, exist_ok=True)
        temporary = root / ".lexical.json.tmp"
        temporary.write_bytes(artifact_raw)
        if hash_file(temporary) != source_sha:
            raise RuntimeError("lexical index copy verification failed")
        os.chmod(temporary, 0o440)
        os.replace(temporary, artifact)
    manifest = {
        **descriptor,
        "index_id": index_id,
        "artifact_path": artifact.relative_to(workspace).as_posix(),
        "artifact_sha256": source_sha,
        "build_fingerprint": build_fingerprint,
        "embedding_model_fingerprint": None,
    }
    manifest_path = write_immutable_json(root / "manifest.json", manifest)
    pointer = {
        "schema_version": "active-source-set-index-v1",
        "source_set_id": source_set["source_set_id"],
        "source_set_generation": source_set["generation_id"],
        "source_set_sha256": source_set["source_set_sha256"],
        "index_id": index_id,
        "manifest_path": manifest_path.relative_to(
            workspace / "01_DATA/INDEXES"
        ).as_posix(),
        "manifest_sha256": hash_file(manifest_path),
    }
    pointer_path = workspace / "01_DATA/INDEXES" / str(source_set["source_set_id"]) / "CURRENT.json"
    raw = json.dumps(pointer, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    if pointer_path.exists() and pointer_path.read_bytes() != raw:
        os.chmod(pointer_path, 0o640)
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_bytes(raw)
    return {**manifest, "manifest_path": manifest_path.relative_to(workspace).as_posix()}


def publish_quarantine_receipt(
    workspace: Path,
    *,
    catalog_path: Path,
    source_sets: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Verify every installed package and publish failures as quarantine entries."""

    catalog_blob = json.loads(catalog_path.read_text("utf-8"))
    entries: list[dict[str, Any]] = []
    for row in catalog_blob["packages"]:
        path = workspace / "01_DATA/PACKAGES" / row["manifest_path"]
        try:
            load_package(path, verify_files=True)
        except Exception as exc:  # receipt captures fail-closed admission errors
            entries.append(
                {
                    "package_id": row["package_id"],
                    "manifest_path": path.relative_to(workspace).as_posix(),
                    "manifest_sha256": row["manifest_sha256"],
                    "reason": type(exc).__name__,
                    "message": str(exc),
                }
            )
    core = {
        "schema_version": "package-quarantine-v1",
        "catalog_path": catalog_path.relative_to(workspace).as_posix(),
        "catalog_artifact_sha256": hash_file(catalog_path),
        "source_set_sha256s": {
            key: value["source_set_sha256"] for key, value in sorted(source_sets.items())
        },
        "entries": entries,
        "admitted_package_count": len(catalog_blob["packages"]) - len(entries),
        "quarantined_package_count": len(entries),
    }
    generation = f"quarantine-{digest(core)[:24]}"
    manifest = {**core, "generation_id": generation, "created_at": utc_now()}
    path = write_immutable_json(
        workspace / "01_DATA/QUARANTINE/generations" / generation / "manifest.json",
        manifest,
    )
    return {**manifest, "manifest_path": path.relative_to(workspace).as_posix(), "manifest_sha256": hash_file(path)}


def inventory_retirement_roots(
    workspace: Path, roots: Iterable[str]
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    total = 0
    for name in roots:
        root = workspace / "01_DATA" / name
        files = []
        if root.is_dir() and not root.is_symlink():
            for path in sorted(p for p in root.rglob("*") if p.is_file()):
                if path.is_symlink():
                    raise RuntimeError(f"retirement root contains symlink: {path}")
                size = path.stat().st_size
                total += size
                files.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "bytes": size,
                        "sha256": hash_file(path),
                    }
                )
        rows.append(
            {
                "legacy_root": f"01_DATA/{name}",
                "exists": root.is_dir(),
                "file_count": len(files),
                "tree_sha256": digest(files),
                "files": files,
            }
        )
    return rows, total


def publish_recovery_manifest(
    workspace: Path,
    *,
    source_sets: Mapping[str, Mapping[str, Any]],
    indexes: Mapping[str, Mapping[str, Any]],
    quarantine: Mapping[str, Any],
    main_before: Mapping[str, Any],
    retirement_roots: Iterable[str] = ("corpus", "structure", "frames", "rag"),
) -> dict[str, Any]:
    root_rows, total = inventory_retirement_roots(workspace, retirement_roots)
    core = {
        "schema_version": "cutover-recovery-manifest-v1",
        "retention_policy": {
            "minimum_generations": 2,
            "minimum_days": 30,
            "delete_only_after_next_release_verified": True,
        },
        "main_before": dict(main_before),
        "source_sets": dict(source_sets),
        "indexes": dict(indexes),
        "quarantine_manifest_sha256": quarantine["manifest_sha256"],
        "legacy_roots": root_rows,
        "legacy_bytes": total,
        "recovery_order": [
            "rollback MAIN pointer",
            "rollback ACTIVE release pointer",
            "restore semantic/query state from immutable release runtime",
            "restore corpus and structure bytes from DatasetPackage manifests",
            "verify every recorded SHA-256 before exposing paths",
        ],
    }
    generation = f"recovery-{digest(core)[:24]}"
    manifest = {**core, "generation_id": generation, "created_at": utc_now()}
    path = write_immutable_json(
        workspace / "01_DATA/BACKUPS/recovery-manifests" / f"{generation}.json",
        manifest,
    )
    return {**manifest, "manifest_path": path.relative_to(workspace).as_posix(), "manifest_sha256": hash_file(path)}
