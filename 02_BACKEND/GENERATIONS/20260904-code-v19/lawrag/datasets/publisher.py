"""Receipt-oriented publication of the existing workspace into DatasetPackage v2.

This module is authoring-plane code.  It never recollects a source and never
calls an LLM, embedding provider, or network service.  Existing source
manifests remain authoritative for source-item accounting; publication copies
only hash-declared bytes into immutable package generations.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from lawrag.datasets.catalog import (
    DatasetContractError,
    InstalledCatalog,
    MaterializedSourceSet,
    UnifiedCorpusView,
    compose_source_set,
    installed_catalog_from_mapping,
    load_installed_catalog,
    load_package,
    load_source_set_lock,
    materialize_source_set,
)
from lawrag.platform.stored_paths import StoredPathError, resolve_stored_path


SOURCE_NAMES = (
    "expc",
    "forms",
    "fsc",
    "internal",
    "kofia",
    "krx",
    "law",
    "moleg",
    "prec",
)
RESTRICTED_SOURCES = frozenset({"forms", "internal"})
PACKAGE_SCHEMA = "dataset-package-v2"
CATALOG_SCHEMA = "installed-dataset-catalog-v1"
SOURCE_SET_SCHEMA = "source-set-v1"
COMPILER_PROFILE = "adr0177-hash-repackage-v1"
SEMANTIC_LAYOUT = "release-semantic-content-v1"
SEMANTIC_TREE_NAMES = ("domain_graph", "frames", "taxonomy", "lexicon", "wiki", "rules")
SEMANTIC_FILE_NAMES = ("aliases.json", "delegation.json", "law_index.json")


@dataclass(frozen=True)
class DeclaredFile:
    path: Path
    sha256: str
    document_id: str | None


@dataclass(frozen=True)
class SourceInventory:
    name: str
    manifest_path: Path
    manifest_sha256: str
    item_count: int
    files: tuple[DeclaredFile, ...]


@dataclass(frozen=True)
class Publication:
    workspace: Path
    packages: tuple[Path, ...]
    catalog: InstalledCatalog
    catalog_path: Path
    source_set_path: Path
    lock_path: Path
    materialized_path: Path
    view: UnifiedCorpusView
    materialized: MaterializedSourceSet

    def receipt(self) -> dict[str, Any]:
        def relative(path: Path) -> str:
            return path.relative_to(self.workspace).as_posix()

        return {
            "schema_version": "dataset-publication-v1",
            "packages": [relative(path) for path in self.packages],
            "package_count": len(self.packages),
            "catalog_path": relative(self.catalog_path),
            "catalog_sha256": self.catalog.catalog_sha256,
            "source_set_path": relative(self.source_set_path),
            "source_set_sha256": self.view.source_set_sha256,
            "lock_path": relative(self.lock_path),
            "lock_sha256": self.materialized.lock.lock_sha256,
            "materialized_path": relative(self.materialized_path),
            "materialization_receipt_sha256": self.materialized.receipt_sha256,
            "artifact_count": len(self.view.artifacts),
            "export_allowed": self.view.export_allowed,
            "external_calls": {"llm": 0, "embedding": 0, "network": 0},
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


def hash_tree(root: Path) -> str:
    """Hash file names and bytes so an immutable package seed binds the full tree."""
    rows = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        if path.is_symlink():
            raise DatasetContractError(f"package source cannot be a symlink: {path}")
        rows.append({"path": path.relative_to(root).as_posix(), "sha256": hash_file(path)})
    return digest(rows)


def _identifier(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def _media_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _document_id(item: Mapping[str, Any]) -> str | None:
    for key in ("doc_id", "case_no", "name", "law_id", "doc_no"):
        value = item.get(key)
        if value not in (None, ""):
            return _identifier("document", str(value))
    return None


def _declared_pairs(item: Mapping[str, Any]) -> Iterable[tuple[object, object]]:
    yield item.get("file"), item.get("sha256")
    yield item.get("body_file"), item.get("body_sha256")
    yield item.get("body_html_file"), item.get("body_html_sha256")
    attachments = item.get("attachments")
    if isinstance(attachments, list):
        for attachment in attachments:
            if isinstance(attachment, Mapping):
                yield attachment.get("file"), attachment.get("sha256")


def inventory_source(workspace: Path, name: str) -> SourceInventory:
    if name not in SOURCE_NAMES:
        raise DatasetContractError(f"unsupported source inventory: {name}")
    manifest_path = (
        workspace / "01_DATA" / "INBOX" / "AUTHORING" / "corpus" / name / "manifest.json"
    )
    try:
        blob = json.loads(manifest_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetContractError(f"cannot read source manifest {manifest_path}: {exc}") from exc
    if not isinstance(blob, Mapping) or not isinstance(blob.get("items"), list):
        raise DatasetContractError(f"source manifest has no item array: {manifest_path}")

    files: dict[Path, DeclaredFile] = {}
    for position, item in enumerate(blob["items"]):
        if not isinstance(item, Mapping):
            raise DatasetContractError(f"{name} items[{position}] must be an object")
        document_id = _document_id(item)
        declared = 0
        for stored, expected in _declared_pairs(item):
            if stored in (None, "") and expected in (None, ""):
                continue
            if not isinstance(stored, str) or not isinstance(expected, str):
                raise DatasetContractError(
                    f"{name} items[{position}] has an incomplete file/hash pair"
                )
            try:
                path = resolve_stored_path(workspace, stored)
            except StoredPathError as exc:
                raise DatasetContractError(str(exc)) from exc
            actual = hash_file(path)
            if actual != expected:
                raise DatasetContractError(
                    f"source hash mismatch: {stored}: expected {expected}, got {actual}"
                )
            previous = files.get(path)
            row = DeclaredFile(path=path, sha256=expected, document_id=document_id)
            if previous is not None and previous.sha256 != row.sha256:
                raise DatasetContractError(f"one source path has multiple hashes: {stored}")
            files[path] = previous or row
            declared += 1
        if declared == 0:
            raise DatasetContractError(f"{name} items[{position}] has no hash-declared file")

    return SourceInventory(
        name=name,
        manifest_path=manifest_path,
        manifest_sha256=hash_file(manifest_path),
        item_count=len(blob["items"]),
        files=tuple(files[path] for path in sorted(files)),
    )


def inventory_sources(workspace: Path) -> tuple[SourceInventory, ...]:
    return tuple(inventory_source(workspace, name) for name in SOURCE_NAMES)


def _copy_verified(source: Path, destination: Path, expected_sha256: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination, follow_symlinks=False)
    if hash_file(destination) != expected_sha256:
        raise DatasetContractError(f"copied artifact hash mismatch: {source}")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise DatasetContractError(f"immutable artifact already differs: {path}")
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _package_blob(
    *,
    package_id: str,
    dataset_id: str,
    generation_seed: str,
    source_origin: str,
    security_class: str,
    authority: str,
    code_revision: str,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    core: dict[str, Any] = {
        "schema_version": PACKAGE_SCHEMA,
        "package_id": package_id,
        "dataset_id": dataset_id,
        "version_id": f"v-{generation_seed[:16]}",
        "variant_id": "real",
        "generation_id": f"gen-{generation_seed[:24]}",
        "source_origin": source_origin,
        "security_class": security_class,
        "representation": "real",
        "authority": authority,
        "export_policy": {"allowed": security_class == "public"},
        "build": {
            "build_id": f"build-{generation_seed[:24]}",
            "execution_site": "outside",
            "code_revision": code_revision,
            "compiler_profile": COMPILER_PROFILE,
            "capabilities": sorted({str(row["role"]) for row in artifacts}),
        },
        "artifacts": artifacts,
    }
    core["manifest_sha256"] = digest(core)
    return core


def _publish_package_directory(
    package_root: Path,
    relative: Path,
    blob_factory: Any,
) -> Path:
    final = package_root / relative
    manifest_path = final / "manifest.json"
    if final.exists():
        load_package(manifest_path, verify_files=True)
        return manifest_path
    final.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.staging-", dir=final.parent))
    try:
        blob = blob_factory(staging)
        payload = json.dumps(blob, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
        (staging / "manifest.json").write_bytes(payload)
        load_package(staging / "manifest.json", verify_files=True)
        os.rename(staging, final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest_path


def publish_source_package(
    workspace: Path,
    inventory: SourceInventory,
    *,
    code_revision: str,
) -> Path:
    restricted = inventory.name in RESTRICTED_SOURCES
    package_id = f"source-{inventory.name}-{inventory.manifest_sha256[:16]}"
    generation = f"gen-{inventory.manifest_sha256[:24]}"
    relative = Path("EXTERNAL") / package_id / generation
    source_root = workspace / "01_DATA" / "INBOX" / "AUTHORING" / "corpus" / inventory.name

    def build(staging: Path) -> dict[str, Any]:
        artifacts: list[dict[str, Any]] = []
        manifest_target = staging / "ARTIFACTS" / "SOURCE_MANIFEST.json"
        _copy_verified(inventory.manifest_path, manifest_target, inventory.manifest_sha256)
        artifacts.append(
            {
                "logical_id": f"source:{inventory.name}:manifest",
                "role": "raw",
                "path": "ARTIFACTS/SOURCE_MANIFEST.json",
                "sha256": inventory.manifest_sha256,
                "media_type": "application/json",
            }
        )
        for row in inventory.files:
            try:
                source_relative = row.path.relative_to(source_root)
            except ValueError as exc:
                raise DatasetContractError(
                    f"declared source escapes {inventory.name}: {row.path}"
                ) from exc
            target_relative = Path("ARTIFACTS") / source_relative
            _copy_verified(row.path, staging / target_relative, row.sha256)
            artifact: dict[str, Any] = {
                "logical_id": _identifier(
                    f"source:{inventory.name}", source_relative.as_posix()
                ),
                "role": "raw",
                "path": target_relative.as_posix(),
                "sha256": row.sha256,
                "media_type": _media_type(row.path),
            }
            if row.document_id is not None:
                artifact["document_id"] = row.document_id
            artifacts.append(artifact)
        return _package_blob(
            package_id=package_id,
            dataset_id=f"source-{inventory.name}",
            generation_seed=inventory.manifest_sha256,
            source_origin="restricted_internal" if restricted else "public_external",
            security_class="restricted" if restricted else "public",
            authority="curated" if inventory.name == "forms" else "authoritative",
            code_revision=code_revision,
            artifacts=artifacts,
        )

    return _publish_package_directory(workspace / "01_DATA" / "PACKAGES", relative, build)


def _tree_artifacts(
    staging: Path,
    *,
    source_root: Path,
    target_prefix: str,
    logical_prefix: str,
    role: str,
    document_from_parent: bool = False,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
        if source.is_symlink():
            raise DatasetContractError(f"package source cannot be a symlink: {source}")
        relative = source.relative_to(source_root)
        target_relative = Path("ARTIFACTS") / target_prefix / relative
        sha256 = hash_file(source)
        _copy_verified(source, staging / target_relative, sha256)
        selected_role = role
        if logical_prefix == "ontology":
            if relative.parts and relative.parts[0] == "observations":
                selected_role = "observation"
            elif relative.parts and relative.parts[0] == "canonical" and (
                "relation" in relative.name or "taxonomy" in relative.name
            ):
                selected_role = "relation"
            elif relative.parts and relative.parts[0] in {"validation", "audit"}:
                selected_role = "evaluation"
        elif logical_prefix == "structure":
            if relative.name == "result.json":
                selected_role = "structure"
            elif relative.name == "meta.json":
                selected_role = "observation"
            else:
                selected_role = "raw"
        artifact: dict[str, Any] = {
            "logical_id": _identifier(
                f"{logical_prefix}:{target_prefix.lower()}", relative.as_posix()
            ),
            "role": selected_role,
            "path": target_relative.as_posix(),
            "sha256": sha256,
            "media_type": _media_type(source),
        }
        if document_from_parent and len(relative.parts) >= 2:
            artifact["document_id"] = _identifier("document", relative.parts[0])
        artifacts.append(artifact)
    return artifacts


def _single_artifact(
    staging: Path,
    *,
    source: Path,
    target: str,
    logical_id: str,
    role: str,
) -> dict[str, Any]:
    sha256 = hash_file(source)
    target_relative = Path("ARTIFACTS") / target
    _copy_verified(source, staging / target_relative, sha256)
    return {
        "logical_id": logical_id,
        "role": role,
        "path": target_relative.as_posix(),
        "sha256": sha256,
        "media_type": _media_type(source),
    }


def _structure_bundle_artifacts(
    staging: Path, *, structure_root: Path
) -> list[dict[str, Any]]:
    """Emit exactly one runtime-admissible structure artifact per document."""

    artifacts: list[dict[str, Any]] = []
    for document_root in sorted(path for path in structure_root.iterdir() if path.is_dir()):
        if document_root.is_symlink():
            raise DatasetContractError(f"structure document cannot be a symlink: {document_root}")
        document_id = document_root.name
        meta_path = document_root / "meta.json"
        result_path = document_root / "result.json"
        if not meta_path.is_file() or not result_path.is_file():
            raise DatasetContractError(f"structure document is incomplete: {document_id}")
        try:
            meta = json.loads(meta_path.read_text("utf-8"))
            result = json.loads(result_path.read_text("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DatasetContractError(f"invalid structure document {document_id}: {exc}") from exc
        if not isinstance(meta, Mapping) or not isinstance(result, Mapping):
            raise DatasetContractError(f"structure document must contain JSON objects: {document_id}")
        payload = canonical_bytes(
            {
                "schema_version": "rag-structure-artifact-v1",
                "document_id": document_id,
                "meta": dict(meta),
                "result": dict(result),
            }
        )
        sha256 = hashlib.sha256(payload).hexdigest()
        relative = Path("ARTIFACTS/STRUCTURE") / f"{document_id}.json"
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        artifacts.append(
            {
                "logical_id": f"structure:document:{document_id}",
                "role": "structure",
                "path": relative.as_posix(),
                "sha256": sha256,
                "media_type": "application/json",
                "document_id": document_id,
            }
        )
    return artifacts


def publish_ontology_package(workspace: Path, *, code_revision: str) -> Path:
    graph_pointer = json.loads((workspace / "01_DATA/legal_graph/CURRENT.json").read_text("utf-8"))
    definition_pointer = json.loads(
        (workspace / "01_DATA/PROJECTIONS/DEFINITIONS/CURRENT.json").read_text("utf-8")
    )
    graph_id = str(graph_pointer["generation_id"])
    definition_id = str(definition_pointer["generation_id"])
    graph_root = workspace / "01_DATA/legal_graph/generations" / graph_id
    definition_root = workspace / "01_DATA/PROJECTIONS/DEFINITIONS/generations" / definition_id
    structure_root = workspace / "01_DATA/INBOX/AUTHORING/structure"
    semantic_tree_roots = {
        name: (
            workspace / "01_DATA/INBOX/AUTHORING/frames"
            if name == "frames"
            else workspace / "01_DATA" / name
        )
        for name in SEMANTIC_TREE_NAMES
    }
    semantic_file_paths = {
        name: workspace / "01_DATA" / name for name in SEMANTIC_FILE_NAMES
    }
    seed = digest(
        {
            "semantic_layout": "release-semantic-content-v2",
            "graph_manifest_sha256": hash_file(graph_root / "manifest.json"),
            "definition_pointer_sha256": hash_file(
                workspace / "01_DATA/PROJECTIONS/DEFINITIONS/CURRENT.json"
            ),
            "structure_tree_sha256": hash_tree(structure_root),
            "semantic_trees": {
                name: hash_tree(path) for name, path in semantic_tree_roots.items()
            },
            "semantic_files": {
                name: hash_file(path) for name, path in semantic_file_paths.items()
            },
            "scopes_sha256": hash_file(workspace / "01_DATA/FEEDBACK/CONFIG/scopes.yml"),
        }
    )
    package_id = f"ontology-operational-{seed[:16]}"
    relative = Path("EXTERNAL") / package_id / f"gen-{seed[:24]}"

    def build(staging: Path) -> dict[str, Any]:
        artifacts = [
            _single_artifact(
                staging,
                source=workspace / "01_DATA/legal_graph/CURRENT.json",
                target="SEMANTICS/legal_graph/CURRENT.json",
                logical_id="ontology:legal-graph:pointer",
                role="semantic",
            ),
            _single_artifact(
                staging,
                source=workspace / "01_DATA/PROJECTIONS/DEFINITIONS/CURRENT.json",
                target="SEMANTICS/PROJECTIONS/DEFINITIONS/CURRENT.json",
                logical_id="definition:projection:pointer",
                role="semantic",
            ),
        ]
        artifacts.extend(_tree_artifacts(
            staging,
            source_root=graph_root,
            target_prefix=f"SEMANTICS/legal_graph/generations/{graph_id}",
            logical_prefix="ontology",
            role="semantic",
        ))
        artifacts.extend(
            _tree_artifacts(
                staging,
                source_root=definition_root,
                target_prefix=(
                    f"SEMANTICS/PROJECTIONS/DEFINITIONS/generations/{definition_id}"
                ),
                logical_prefix="definition",
                role="semantic",
            )
        )
        artifacts.extend(_structure_bundle_artifacts(staging, structure_root=structure_root))
        for name, source_root in semantic_tree_roots.items():
            artifacts.extend(
                _tree_artifacts(
                    staging,
                    source_root=source_root,
                    target_prefix=f"SEMANTICS/{name}",
                    logical_prefix=f"semantic-{name}",
                    role="semantic",
                )
            )
        for name, source in semantic_file_paths.items():
            artifacts.append(
                _single_artifact(
                    staging,
                    source=source,
                    target=f"SEMANTICS/{name}",
                    logical_id=f"semantic:{name}",
                    role="semantic",
                )
            )
        artifacts.append(
            _single_artifact(
                staging,
                source=workspace / "01_DATA/FEEDBACK/CONFIG/scopes.yml",
                target="SEMANTICS/scopes.yml",
                logical_id="semantic:rag-scopes",
                role="semantic",
            )
        )
        return _package_blob(
            package_id=package_id,
            dataset_id="ontology-operational",
            generation_seed=seed,
            source_origin="curated_shared",
            security_class="restricted",
            authority="curated",
            code_revision=code_revision,
            artifacts=artifacts,
        )

    return _publish_package_directory(workspace / "01_DATA" / "PACKAGES", relative, build)


def _catalog_blob(package_root: Path, manifest_paths: Iterable[Path]) -> dict[str, Any]:
    rows = []
    for path in manifest_paths:
        package = load_package(path, verify_files=True)
        rows.append(
            {
                "package_id": package.package_id,
                "manifest_path": path.relative_to(package_root).as_posix(),
                "manifest_sha256": package.manifest_sha256,
            }
        )
    core: dict[str, Any] = {
        "schema_version": CATALOG_SCHEMA,
        "packages": sorted(rows, key=lambda row: row["package_id"]),
    }
    core["catalog_sha256"] = digest(core)
    return core


def publish_workspace(workspace: Path) -> Publication:
    workspace = workspace.resolve()
    activation_path = workspace / "00_SYSTEM/MIGRATION/ACTIVATIONS/20260904-code-v13.json"
    code_revision = hash_file(activation_path)
    inventories = inventory_sources(workspace)
    manifests = [
        publish_source_package(workspace, inventory, code_revision=code_revision)
        for inventory in inventories
    ]
    manifests.append(publish_ontology_package(workspace, code_revision=code_revision))

    package_root = workspace / "01_DATA/PACKAGES"
    catalog_blob = _catalog_blob(package_root, manifests)
    catalog_generation = f"catalog-{catalog_blob['catalog_sha256'][:24]}"
    catalog_path = workspace / "01_DATA/CATALOG" / f"{catalog_generation}.json"
    _atomic_write(
        catalog_path,
        json.dumps(catalog_blob, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n",
    )
    catalog = load_installed_catalog(catalog_path, package_root=package_root)

    source_set_core: dict[str, Any] = {
        "schema_version": SOURCE_SET_SCHEMA,
        "source_set_id": "local-operational-v2",
        "generation_id": f"sourceset-{catalog.catalog_sha256[:24]}",
        "conflict_policy": "error",
        "cross_dataset_relations": True,
        "members": [
            {"package_id": row.package_id, "priority": position + 1}
            for position, row in enumerate(catalog.packages)
        ],
    }
    source_set_path = (
        workspace
        / "01_DATA/SOURCE_SETS/local-operational-v2"
        / f"{source_set_core['generation_id']}.json"
    )
    _atomic_write(
        source_set_path,
        json.dumps(source_set_core, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n",
    )
    view = catalog.open(source_set_core)
    lock = view.lock()
    lock_path = source_set_path.with_name(f"{source_set_core['generation_id']}.lock.json")
    _atomic_write(
        lock_path,
        json.dumps(lock.receipt(), ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n",
    )
    loaded_lock = load_source_set_lock(lock_path)
    catalog.resolve_lock(
        loaded_lock,
        expected_source_set_sha256=view.source_set_sha256,
        expected_lock_sha256=lock.lock_sha256,
    )
    materialized_path = (
        workspace
        / "01_DATA/SOURCE_SETS/MATERIALIZED/local-operational-v2"
        / source_set_core["generation_id"]
    )
    trusted_materialization_root = workspace / "01_DATA/SOURCE_SETS/MATERIALIZED"
    trusted_materialization_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(trusted_materialization_root, 0o700)
    materialized = materialize_source_set(
        view,
        materialized_path,
        lock=loaded_lock,
        relation_policy_enforced=True,
        allow_cross_dataset_relations=True,
        trusted_root=trusted_materialization_root,
    )
    return Publication(
        workspace=workspace,
        packages=tuple(manifests),
        catalog=catalog,
        catalog_path=catalog_path,
        source_set_path=source_set_path,
        lock_path=lock_path,
        materialized_path=materialized_path,
        view=view,
        materialized=materialized,
    )


def verify_publication(workspace: Path, receipt: Mapping[str, Any]) -> dict[str, Any]:
    package_root = workspace / "01_DATA/PACKAGES"
    package_paths = [workspace / str(path) for path in receipt.get("packages", [])]
    packages = [load_package(path, verify_files=True) for path in package_paths]
    catalog_path = workspace / str(receipt["catalog_path"])
    catalog: InstalledCatalog = load_installed_catalog(catalog_path, package_root=package_root)
    source_set_path = workspace / str(receipt["source_set_path"])
    source_set_blob = json.loads(source_set_path.read_text("utf-8"))
    view = compose_source_set(source_set_blob, packages)
    lock_path = workspace / str(receipt["lock_path"])
    lock = load_source_set_lock(lock_path)
    catalog.resolve_lock(
        lock,
        expected_source_set_sha256=view.source_set_sha256,
        expected_lock_sha256=lock.lock_sha256,
    )
    materialized_path = workspace / str(receipt["materialized_path"])
    materialized = materialize_source_set(
        view,
        materialized_path,
        lock=lock,
        relation_policy_enforced=True,
        allow_cross_dataset_relations=True,
        trusted_root=workspace / "01_DATA/SOURCE_SETS/MATERIALIZED",
    )
    return {
        "schema_version": "dataset-publication-verification-v1",
        "result": "pass",
        "package_count": len(packages),
        "artifact_count": len(view.artifacts),
        "catalog_sha256": catalog.catalog_sha256,
        "source_set_sha256": view.source_set_sha256,
        "lock_sha256": lock.lock_sha256,
        "materialization_receipt_sha256": materialized.receipt_sha256,
        "export_allowed": view.export_allowed,
        "external_calls": {"llm": 0, "embedding": 0, "network": 0},
    }
