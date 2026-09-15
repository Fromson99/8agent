"""GENOS raw ingress adapters backed by one common batch pipeline.

External public data arrives as immutable DatasetPackages.  Internal rules
arrive as files uploaded by GenOS.  Those two ingress adapters only stage and
validate bytes; both call :func:`run_common` with the same stage list and the
same stores afterwards.

Historical observations, semantic generations, and authoring queues are not
inputs to this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
DEFAULT_SOURCE_SET = (
    ROOT
    / "01_DATA/SOURCE_SETS/external-public-v1"
    / "sourceset-489b3bcff1cf01fb0f5a97a4.json"
)
DEFAULT_PACKAGES_ROOT = ROOT / "01_DATA/PACKAGES/EXTERNAL"
COMMON_STAGES = "ingest,structure,delegation,terms,embed,scopes"
INTERNAL_FOLDER = "내규"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _data_root(value: str | Path | None = None) -> Path:
    configured = str(value or os.environ.get("GENOS_DATA_ROOT", "")).strip()
    root = Path(configured).expanduser() if configured else ROOT / "01_DATA/INBOX/AUTHORING"
    if not root.is_absolute():
        raise ValueError("GENOS_DATA_ROOT must be an absolute path")
    if root.is_symlink():
        raise ValueError("GENOS_DATA_ROOT must not be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def configure_data_root(value: str | Path | None = None) -> Path:
    """Bind all mutable pipeline paths below one persistent data root."""

    root = _data_root(value)
    defaults = {
        "STRUCTURE_STORE": root / "structure",
        "CORPUS_DIR": root / "corpus",
        "PIPELINE_DIR": root / "pipeline",
        "PIPELINE_INBOX": root / "inbox",
        "GLOSSARY_STORE": root / "glossary.json",
        "RAG_VECTOR_STORE": root / "embeddings/sections",
        "RAG_LOG_DIR": root / "rag",
        "RAG_RULES_DIR": root / "rules",
        "OPS_DIR": root / "ops",
    }
    for name, path in defaults.items():
        os.environ.setdefault(name, str(path))
    return root


def _package_manifest(packages_root: Path, package_id: str) -> Path:
    candidates = sorted((packages_root / package_id).glob("gen-*/manifest.json"))
    if len(candidates) != 1:
        raise ValueError(
            f"expected exactly one generation for {package_id}, found {len(candidates)}"
        )
    return candidates[0]


def _source_name(dataset_id: str) -> str:
    prefix = "source-"
    if not dataset_id.startswith(prefix) or len(dataset_id) == len(prefix):
        raise ValueError(f"external raw package has unexpected dataset_id: {dataset_id}")
    return dataset_id[len(prefix):]


def _rewrite_manifest_paths(value: Any, *, source: str, target: Path) -> Any:
    if isinstance(value, list):
        return [_rewrite_manifest_paths(row, source=source, target=target) for row in value]
    if isinstance(value, dict):
        return {
            key: _rewrite_manifest_paths(row, source=source, target=target)
            for key, row in value.items()
        }
    if not isinstance(value, str):
        return value
    for prefix in (f"data/corpus/{source}/", f"01_DATA/corpus/{source}/"):
        if value.startswith(prefix):
            return str((target / value[len(prefix):]).resolve())
    return value


def _install_file(source: Path, target: Path, expected_sha256: str) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"package artifact is not a regular file: {source}")
    if _sha(source) != expected_sha256:
        raise ValueError(f"package artifact hash mismatch: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_symlink() or not target.is_file() or _sha(target) != expected_sha256:
            raise ValueError(f"refusing to overwrite different external raw file: {target}")
        return
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copy2(source, temporary)
        if _sha(temporary) != expected_sha256:
            raise ValueError(f"copied artifact hash mismatch: {target}")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def bootstrap_external(
    *,
    data_root: str | Path | None = None,
    source_set: str | Path = DEFAULT_SOURCE_SET,
    packages_root: str | Path = DEFAULT_PACKAGES_ROOT,
) -> dict[str, Any]:
    """Verify public raw packages and materialize their source manifests."""

    root = configure_data_root(data_root)
    source_set_path = Path(source_set).resolve()
    package_root = Path(packages_root).resolve()
    from lawrag.datasets.catalog import load_package, load_source_set

    declaration = json.loads(source_set_path.read_text(encoding="utf-8"))
    members = declaration.get("members") or []
    if not members:
        raise ValueError("external SourceSet has no members")
    packages = []
    for member in members:
        package = load_package(
            _package_manifest(package_root, str(member["package_id"])),
            verify_files=True,
        )
        if (
            package.source_origin != "public_external"
            or package.security_class != "public"
            or package.representation != "real"
            or package.authority != "authoritative"
            or package.capabilities != ("raw",)
            or not package.export_allowed
        ):
            raise ValueError(f"package is not authoritative public raw: {package.package_id}")
        if any(artifact.role != "raw" for artifact in package.artifacts):
            raise ValueError(f"package includes a derived artifact: {package.package_id}")
        packages.append(package)
    view = load_source_set(source_set_path, packages)

    installed_files = 0
    installed_bytes = 0
    installed_sources: list[str] = []
    for package in packages:
        source = _source_name(package.dataset_id)
        target_root = root / "corpus" / source
        manifest_artifact = next(
            (
                row
                for row in package.artifacts
                if PurePosixPath(row.path).name == "SOURCE_MANIFEST.json"
            ),
            None,
        )
        if manifest_artifact is None:
            raise ValueError(f"SOURCE_MANIFEST.json missing: {package.package_id}")
        for artifact in package.artifacts:
            if artifact is manifest_artifact:
                continue
            relative = PurePosixPath(artifact.path)
            try:
                relative = relative.relative_to("ARTIFACTS")
            except ValueError as exc:
                raise ValueError(f"artifact is outside ARTIFACTS: {artifact.path}") from exc
            artifact_source = artifact.resolved_path()
            if artifact_source is None:
                raise ValueError(f"artifact has no package path: {artifact.path}")
            _install_file(artifact_source, target_root / Path(*relative.parts), artifact.sha256)
            installed_files += 1
            installed_bytes += artifact_source.stat().st_size

        manifest_source = manifest_artifact.resolved_path()
        if manifest_source is None:
            raise ValueError(f"source manifest has no package path: {package.package_id}")
        manifest = json.loads(manifest_source.read_text(encoding="utf-8"))
        manifest = _rewrite_manifest_paths(manifest, source=source, target=target_root)
        manifest_target = target_root / "manifest.json"
        manifest_target.parent.mkdir(parents=True, exist_ok=True)
        manifest_target.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        installed_sources.append(source)

    receipt = {
        "schema_version": "genos-external-raw-bootstrap-v1",
        "source_set_id": view.source_set_id,
        "generation_id": view.generation_id,
        "source_set_sha256": view.source_set_sha256,
        "sources": installed_sources,
        "package_ids": [package.package_id for package in packages],
        "files": installed_files,
        "bytes": installed_bytes,
        "data_root": str(root),
    }
    receipt_path = root / "receipts/external-bootstrap.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"ok": True, **receipt, "receipt": str(receipt_path)}


def _selected_stages(stages: str) -> list[str]:
    from lawrag.core import batch

    selected = [value.strip() for value in stages.split(",") if value.strip()]
    unknown = [value for value in selected if value not in batch.STAGES]
    if unknown:
        raise ValueError("unknown pipeline stages: " + ", ".join(unknown))
    return selected


def run_common(
    *, data_root: str | Path | None = None, stages: str = COMMON_STAGES,
    workers: int | None = None,
) -> dict[str, Any]:
    """Run the one shared post-ingress pipeline."""

    root = configure_data_root(data_root)
    from lawrag.core import batch

    selected = _selected_stages(stages)
    started = batch.RUNNER.start(selected, {"workers": workers} if workers else {})
    while batch.RUNNER.is_running():
        time.sleep(0.2)
    status = batch.RUNNER.status()
    return {
        "ok": status.get("status") == "done",
        "pipeline": "lawrag.common-batch-v1",
        "stages": selected,
        "data_root": str(root),
        "run_id": started["run_id"],
        "status": status,
    }


def process_external(
    *, data_root: str | Path | None = None, stages: str = COMMON_STAGES,
    source_set: str | Path = DEFAULT_SOURCE_SET,
    packages_root: str | Path = DEFAULT_PACKAGES_ROOT,
    workers: int | None = None,
) -> dict[str, Any]:
    ingress = bootstrap_external(
        data_root=data_root, source_set=source_set, packages_root=packages_root
    )
    result = run_common(data_root=data_root, stages=stages, workers=workers)
    return {**result, "ingress": "external-package", "bootstrap": ingress}


def _inside(path: Path, root: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"uploaded path is not a regular file: {path}")
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"uploaded file is outside GENOS_UPLOAD_ROOT: {path}") from exc
    return resolved


def process_internal(
    files: Iterable[str | Path], *, allowed_root: str | Path,
    data_root: str | Path | None = None, stages: str = COMMON_STAGES,
    workers: int | None = None,
) -> dict[str, Any]:
    """Stage verified GenOS uploads, then call the same common runner."""

    root = configure_data_root(data_root)
    upload_root = Path(allowed_root).expanduser()
    if not upload_root.is_absolute() or upload_root.is_symlink() or not upload_root.is_dir():
        raise ValueError("GENOS_UPLOAD_ROOT must be an existing absolute non-symlink directory")
    upload_root = upload_root.resolve()
    from lawrag.core import batch
    from lawrag.pipeline.onsite import ACCEPTED, _stage

    staged: list[str] = []
    for value in files:
        source = _inside(Path(value).expanduser(), upload_root)
        if source.suffix.lower() not in ACCEPTED:
            raise ValueError(f"unsupported internal rule file: {source.name}")
        staged.extend(str(path) for path in _stage(source, batch.inbox_path(), INTERNAL_FOLDER))
    if not staged:
        raise ValueError("no internal upload files were supplied")
    result = run_common(data_root=root, stages=stages, workers=workers)
    return {**result, "ingress": "genos-upload", "staged": staged}


def status(*, data_root: str | Path | None = None) -> dict[str, Any]:
    root = configure_data_root(data_root)
    from lawrag.core import batch

    documents = batch._store_docs()
    targets = batch.ingest_targets()
    current_path = root / "generations/CURRENT.json"
    current = None
    if current_path.is_file():
        current = json.loads(current_path.read_text(encoding="utf-8"))
    return {
        "ok": True,
        "pipeline": "lawrag.common-batch-v1",
        "common_stages": COMMON_STAGES.split(","),
        "data_root": str(root),
        "generation": current,
        "status": batch.RUNNER.status(),
        # Keep this endpoint raw-only.  The legacy all-stage lineup also
        # inspects graph/semantic generations, which are intentionally outside
        # this handoff and must not become a hidden prerequisite.
        "lineup": {
            "documents": len(documents),
            "ingest_total": len(targets),
            "ingest_pending": sum(not row["in_store"] for row in targets),
            "structure_quarantined": sum(
                not row.get("passed", True) or (row.get("score") or 1) < 0.70
                for row in documents.values()
            ),
        },
    }


def _source_hashes(root: Path) -> dict[str, str]:
    from lawrag.core import batch

    hashes: dict[str, str] = {}
    for target in batch.ingest_targets():
        body = Path(str(target["path"]))
        if body.is_symlink() or not body.is_file():
            raise ValueError(f"invalid ingested source body: {body}")
        sha256 = _sha(body)
        document_id = str(target["doc_id"])
        if len(sha256) != 64 or not sha256.startswith(document_id):
            raise ValueError(
                f"invalid ingested source coordinate: {body}: {document_id}"
            )
        previous = hashes.setdefault(document_id, sha256)
        if previous != sha256:
            raise ValueError(f"conflicting source hashes for {document_id}")
    return hashes


def _build_source_store(root: Path, *, allow_score_advisory: bool = False) -> tuple[Path, dict[str, Any]]:
    """Export current deterministic structure results to the semantic source schema."""

    structure = root / "structure"
    hashes = _source_hashes(root)
    documents: list[tuple[str, dict[str, Any], dict[str, Any], str]] = []
    for directory in sorted(structure.iterdir() if structure.is_dir() else []):
        if not directory.is_dir():
            continue
        meta_path, result_path = directory / "meta.json", directory / "result.json"
        if not meta_path.is_file() or not result_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        document_id = str(meta.get("doc_id") or directory.name)
        if document_id != directory.name or document_id not in hashes:
            raise ValueError(f"structure/source provenance mismatch: {directory}")
        if allow_score_advisory:
            # Opt-in offline builder only. Recheck coordinates instead of trusting
            # a persisted admission flag; the ordinary publisher keeps its gate.
            from .genos_admission import validate_structure
            admission = validate_structure(document_id, meta, result)
            if meta.get('structure_admission') != admission:
                raise ValueError(f'구조 무결성 승인 기록 불일치: {directory}')
        elif not meta.get("passed", True):
            continue
        documents.append((document_id, meta, result, hashes[document_id]))
    if not documents:
        raise ValueError("no passed structure documents are available to publish")

    stores = root / "source-stores"
    stores.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="source-", suffix=".sqlite", dir=stores, delete=False) as stream:
        temporary = Path(stream.name)
    db = sqlite3.connect(temporary)
    try:
        db.executescript(
            """
            CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT NOT NULL,source_artifact_sha256 TEXT NOT NULL,json TEXT NOT NULL);
            CREATE TABLE source_unit(document_id TEXT NOT NULL,unit_id TEXT NOT NULL,parent_id TEXT,json TEXT NOT NULL,PRIMARY KEY(document_id,unit_id));
            CREATE TABLE source_block(document_id TEXT NOT NULL,block_id TEXT NOT NULL,unit_id TEXT,text TEXT NOT NULL,source_artifact_sha256 TEXT NOT NULL,json TEXT NOT NULL,PRIMARY KEY(document_id,block_id));
            """
        )
        unit_counts = block_counts = 0
        for document_id, meta, result, source_sha256 in documents:
            nodes = result.get("nodes") or []
            blocks = result.get("blocks") or []
            unit_ids = {str(node["id"]) for node in nodes}
            if len(unit_ids) != len(nodes):
                raise ValueError(f"duplicate source unit in {document_id}")
            db.execute(
                "INSERT INTO document VALUES (?,?,?,?)",
                (
                    document_id,
                    str(meta.get("name") or meta.get("title") or document_id),
                    source_sha256,
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            for node in nodes:
                parent = node.get("parent")
                if parent is not None and str(parent) not in unit_ids:
                    raise ValueError(f"missing parent unit in {document_id}: {parent}")
                db.execute(
                    "INSERT INTO source_unit VALUES (?,?,?,?)",
                    (
                        document_id,
                        str(node["id"]),
                        None if parent is None else str(parent),
                        json.dumps(node, ensure_ascii=False, separators=(",", ":")),
                    ),
                )
            for block in blocks:
                unit = block.get("node")
                if unit is not None and str(unit) not in unit_ids:
                    raise ValueError(f"missing block unit in {document_id}: {unit}")
                db.execute(
                    "INSERT INTO source_block VALUES (?,?,?,?,?,?)",
                    (
                        document_id,
                        str(block["idx"]),
                        None if unit is None else str(unit),
                        str(block.get("text") or ""),
                        source_sha256,
                        json.dumps(block, ensure_ascii=False, separators=(",", ":")),
                    ),
                )
            unit_counts += len(nodes)
            block_counts += len(blocks)
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("source store integrity check failed")
    finally:
        db.close()

    source_sha256 = _sha(temporary)
    output = stores / f"source-{source_sha256[:20]}.sqlite"
    if output.exists():
        if _sha(output) != source_sha256:
            raise ValueError(f"immutable source store collision: {output}")
        temporary.unlink()
    else:
        os.replace(temporary, output)
    receipt = {
        "documents": len(documents),
        "units": unit_counts,
        "blocks": block_counts,
        "document_ids": [row[0] for row in documents],
        "source_store": str(output),
        "source_store_sha256": source_sha256,
        "source_fingerprint": hashlib.sha256(
            json.dumps(
                [(row[0], row[3]) for row in documents],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }
    return output, receipt


def publish_source_only(*, data_root: str | Path | None = None) -> dict[str, Any]:
    """Publish fresh lexical serving data without importing historical LLM output."""

    root = configure_data_root(data_root)
    source_store, receipt = _build_source_store(root)
    scope = {
        "source_set_sha256": receipt["source_fingerprint"],
        "authority_generation": f"genos-unified-raw-{receipt['source_fingerprint'][:16]}",
        "document_version_ids": receipt["document_ids"],
        "jurisdiction": "KR",
        "as_of": None,
    }
    generations = root / "generations"
    generations.mkdir(parents=True, exist_ok=True)
    output = generations / f"source-only-{receipt['source_store_sha256'][:20]}"
    from . import glossary_linking
    from .term_generation import build_generation
    glossary=glossary_linking.configured(ROOT,root)
    bundle=generations / f"term-source-{receipt['source_store_sha256'][:20]}"
    result=build_generation(source_store,glossary,bundle)
    output=bundle/'generation'
    manifest=json.loads((output/'manifest.json').read_text())
    pointer = {
        "schema_version": "genos-current-generation-v1",
        "generation_id": manifest["generation_id"],
        "path": str(output),
        "manifest_sha256": _sha(output / "manifest.json"),
    }
    pointer_path = generations / "CURRENT.json"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=generations, delete=False) as stream:
        json.dump(pointer, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, pointer_path)
    return {
        "ok": True,
        "generation": str(output),
        "pointer": str(pointer_path),
        "manifest": manifest,
        **receipt,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default=os.environ.get("GENOS_DATA_ROOT", ""))
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("external", "run"):
        command = sub.add_parser(name)
        command.add_argument("--stages", default=COMMON_STAGES)
        command.add_argument("--workers", type=int)
        if name == "external":
            command.add_argument("--source-set", default=str(DEFAULT_SOURCE_SET))
            command.add_argument("--packages-root", default=str(DEFAULT_PACKAGES_ROOT))
    bootstrap = sub.add_parser("bootstrap-external")
    bootstrap.add_argument("--source-set", default=str(DEFAULT_SOURCE_SET))
    bootstrap.add_argument("--packages-root", default=str(DEFAULT_PACKAGES_ROOT))
    internal = sub.add_parser("internal")
    internal.add_argument("files", nargs="+")
    internal.add_argument("--upload-root", default=os.environ.get("GENOS_UPLOAD_ROOT", ""))
    internal.add_argument("--stages", default=COMMON_STAGES)
    internal.add_argument("--workers", type=int)
    sub.add_parser("publish")
    sub.add_parser("status")
    args = parser.parse_args(argv)
    try:
        if args.command == "bootstrap-external":
            result = bootstrap_external(
                data_root=args.data_root or None,
                source_set=args.source_set,
                packages_root=args.packages_root,
            )
        elif args.command == "external":
            result = process_external(
                data_root=args.data_root or None,
                stages=args.stages,
                source_set=args.source_set,
                packages_root=args.packages_root,
                workers=args.workers,
            )
        elif args.command == "internal":
            result = process_internal(
                args.files,
                allowed_root=args.upload_root,
                data_root=args.data_root or None,
                stages=args.stages,
                workers=args.workers,
            )
        elif args.command == "run":
            result = run_common(
                data_root=args.data_root or None,
                stages=args.stages,
                workers=args.workers,
            )
        elif args.command == "publish":
            result = publish_source_only(data_root=args.data_root or None)
        else:
            result = status(data_root=args.data_root or None)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
