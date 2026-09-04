#!/usr/bin/env python3
"""Validate and inspect the standalone benchmark registry."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspace_paths import StoredPathError, resolve_stored_path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
REGISTRY_PATH = Path("benchmarks/registry.json")
ALLOWED_STATUSES = {"draft", "active", "frozen", "superseded", "retired"}
ALLOWED_SPECIALIZATIONS = {
    "question_only", "oracle_context", "model_knowledge_ceiling",
    "retrieval_only", "stress", "holdout", "product_isolated", "dual_judge",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
    temporary.replace(path)


def _resolve(root: Path, stored: Any, errors: list[str], label: str) -> Path | None:
    if not isinstance(stored, str) or not stored or "\\" in stored:
        errors.append(f"{label}: path must be a non-empty POSIX relative path")
        return None
    candidate = Path(stored)
    if candidate.is_absolute() or ".." in candidate.parts:
        errors.append(f"{label}: path must stay inside repository: {stored}")
        return None
    try:
        resolved = resolve_stored_path(root, stored)
    except StoredPathError as exc:
        errors.append(f"{label}: {exc}")
        return None
    return resolved


def _file_ref(
    root: Path,
    ref: dict[str, Any],
    errors: list[str],
    label: str,
    *,
    path_key: str = "path",
    sha_key: str = "sha256",
    bytes_key: str | None = "bytes",
) -> Path | None:
    path = _resolve(root, ref.get(path_key), errors, label)
    if path is None:
        return None
    if not path.is_file():
        errors.append(f"{label}: missing file {ref.get(path_key)}")
        return None
    actual_sha = _sha(path)
    if ref.get(sha_key) != actual_sha:
        errors.append(
            f"{label}: sha256 mismatch {ref.get(sha_key)} != {actual_sha}")
    if bytes_key is not None and ref.get(bytes_key) != path.stat().st_size:
        errors.append(
            f"{label}: byte mismatch {ref.get(bytes_key)} != {path.stat().st_size}")
    return path


def _validate_adr_ref(
    root: Path,
    ref: dict[str, Any],
    errors: list[str],
    label: str,
    *,
    path_key: str = "record_path",
    sha_key: str = "record_sha256",
    require_arm: bool,
) -> None:
    path = _file_ref(
        root, ref, errors, label, path_key=path_key, sha_key=sha_key, bytes_key=None)
    if path is None or not require_arm:
        return
    try:
        manifest = _read(path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label}: cannot read ADR manifest: {exc}")
        return
    experiment_id = ref.get("experiment_id")
    if manifest.get("experiment_id") != experiment_id:
        errors.append(f"{label}: experiment_id mismatch: {experiment_id}")
    raw_arm_ids = ref.get("arm_ids")
    if raw_arm_ids is None:
        raw_arm_ids = [ref.get("arm_id")]
    if (not isinstance(raw_arm_ids, list) or not raw_arm_ids
            or any(not isinstance(arm_id, str) or not arm_id for arm_id in raw_arm_ids)
            or len(raw_arm_ids) != len(set(raw_arm_ids))):
        errors.append(f"{label}: arm_id or unique non-empty arm_ids is required")
        return
    arms = {
        row.get("id") for row in (manifest.get("design", {}).get("arms") or [])
        if isinstance(row, dict)
    }
    for arm_id in raw_arm_ids:
        if arm_id not in arms:
            errors.append(f"{label}: unknown ADR arm: {experiment_id}/{arm_id}")


def _combined_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _validate_run(
    root: Path,
    benchmark: dict[str, Any],
    run_ref: dict[str, Any],
    errors: list[str],
    label: str,
) -> None:
    path = _file_ref(root, run_ref, errors, label)
    if path is None:
        return
    try:
        run = _read(path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label}: invalid run JSON: {exc}")
        return
    if run.get("schema_version") != "benchmark-run-v1":
        errors.append(f"{label}: schema_version must be benchmark-run-v1")
    if run.get("benchmark_id") != benchmark.get("benchmark_id"):
        errors.append(f"{label}: benchmark_id mismatch")
    if run.get("benchmark_version") != benchmark.get("version"):
        errors.append(f"{label}: benchmark_version mismatch")
    if run.get("run_id") != run_ref.get("run_id"):
        errors.append(f"{label}: run_id mismatch")
    if run.get("status") != run_ref.get("status"):
        errors.append(f"{label}: run status mismatch")
    adr_ref = run.get("adr_ref")
    if not isinstance(adr_ref, dict):
        errors.append(f"{label}: adr_ref must be an object")
    else:
        _validate_adr_ref(
            root, adr_ref, errors, f"{label}.adr_ref",
            path_key="manifest_path", sha_key="manifest_sha256", require_arm=True)
    artifacts = run.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append(f"{label}: artifacts must be a non-empty list")
        return
    roles: set[str] = set()
    paths: set[str] = set()
    for index, artifact in enumerate(artifacts):
        item_label = f"{label}.artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{item_label}: must be an object")
            continue
        role = artifact.get("role")
        stored = artifact.get("path")
        if not isinstance(role, str) or not role or role in roles:
            errors.append(f"{item_label}: role must be unique and non-empty")
        if not isinstance(stored, str) or stored in paths:
            errors.append(f"{item_label}: artifact path must be unique")
        roles.add(str(role))
        paths.add(str(stored))
        _file_ref(root, artifact, errors, item_label)


def _validate_benchmark(
    root: Path,
    entry: dict[str, Any],
    manifest: dict[str, Any],
    errors: list[str],
) -> None:
    label = str(entry.get("benchmark_id") or "benchmark")
    if manifest.get("schema_version") != "benchmark-v1":
        errors.append(f"{label}: schema_version must be benchmark-v1")
    for key in ("benchmark_id", "version", "status", "benchmark_class"):
        if manifest.get(key) != entry.get(key):
            errors.append(f"{label}: registry/manifest {key} mismatch")
    if manifest.get("status") not in ALLOWED_STATUSES:
        errors.append(f"{label}: invalid status {manifest.get('status')}")
    if not isinstance(manifest.get("version"), int) or manifest.get("version", 0) <= 0:
        errors.append(f"{label}: version must be a positive integer")
    specializations = manifest.get("specializations")
    if not isinstance(specializations, list) or len(specializations) != len(set(specializations)):
        errors.append(f"{label}: specializations must be a unique list")
        specializations = []
    unknown = sorted(set(specializations) - ALLOWED_SPECIALIZATIONS)
    if unknown:
        errors.append(f"{label}: unknown specializations: {', '.join(unknown)}")
    if specializations != entry.get("specializations"):
        errors.append(f"{label}: registry/manifest specializations mismatch")
    if not manifest.get("comparability_key"):
        errors.append(f"{label}: comparability_key is required")

    dataset = manifest.get("dataset")
    if not isinstance(dataset, dict):
        errors.append(f"{label}: dataset must be an object")
    else:
        sources = dataset.get("sources")
        source_paths: list[Path] = []
        if not isinstance(sources, list) or not sources:
            errors.append(f"{label}: dataset.sources must be non-empty")
        else:
            for index, source in enumerate(sources):
                source_label = f"{label}.dataset.sources[{index}]"
                if not isinstance(source, dict):
                    errors.append(f"{source_label}: must be an object")
                    continue
                path = _file_ref(root, source, errors, source_label)
                if path is not None:
                    source_paths.append(path)
            if len(source_paths) == len(sources):
                combined = _combined_hash(source_paths)
                if dataset.get("combined_sha256") != combined:
                    errors.append(
                        f"{label}: dataset combined_sha256 mismatch "
                        f"{dataset.get('combined_sha256')} != {combined}")
        if isinstance(sources, list):
            total = sum(int(row.get("case_count", 0)) for row in sources
                        if isinstance(row, dict))
            if dataset.get("case_count") != total:
                errors.append(f"{label}: dataset case_count must equal source total")

    for contract in ("input_contract", "scoring_contract", "isolation_contract"):
        if not isinstance(manifest.get(contract), dict):
            errors.append(f"{label}: {contract} must be an object")
    links = manifest.get("adr_links")
    if not isinstance(links, list) or not links:
        errors.append(f"{label}: adr_links must be non-empty")
    else:
        execution_links = 0
        for index, ref in enumerate(links):
            ref_label = f"{label}.adr_links[{index}]"
            if not isinstance(ref, dict):
                errors.append(f"{ref_label}: must be an object")
                continue
            require_arm = ref.get("relation") == "execution_provenance"
            execution_links += int(require_arm)
            _validate_adr_ref(root, ref, errors, ref_label, require_arm=require_arm)
        if execution_links == 0:
            errors.append(f"{label}: at least one execution_provenance ADR link is required")

    runs = manifest.get("runs")
    if not isinstance(runs, list) or not runs:
        errors.append(f"{label}: runs must be non-empty")
        return
    run_ids: set[str] = set()
    registered_paths: set[str] = set()
    for index, run_ref in enumerate(runs):
        run_label = f"{label}.runs[{index}]"
        if not isinstance(run_ref, dict):
            errors.append(f"{run_label}: must be an object")
            continue
        run_id = run_ref.get("run_id")
        if not isinstance(run_id, str) or not run_id or run_id in run_ids:
            errors.append(f"{run_label}: run_id must be unique and non-empty")
        run_ids.add(str(run_id))
        registered_paths.add(str(run_ref.get("path")))
        _validate_run(root, manifest, run_ref, errors, run_label)
    latest = entry.get("latest_run_id")
    if latest not in run_ids:
        errors.append(f"{label}: latest_run_id is not registered: {latest}")
    benchmark_root = resolve_stored_path(root, "benchmarks")
    manifest_dir = benchmark_root / str(manifest.get("benchmark_id")) / "runs"
    disk_runs = {
        f"benchmarks/{path.relative_to(benchmark_root).as_posix()}"
        for path in manifest_dir.glob("*.json")
    } if manifest_dir.is_dir() else set()
    for orphan in sorted(disk_runs - registered_paths):
        errors.append(f"{label}: orphan run manifest: {orphan}")


def validate_registry(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    try:
        registry_path = resolve_stored_path(root, REGISTRY_PATH.as_posix())
    except StoredPathError as exc:
        return {"ok": False, "errors": [f"missing {REGISTRY_PATH}: {exc}"], "counts": {}}
    try:
        registry = _read(registry_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"invalid registry JSON: {exc}"], "counts": {}}
    if registry.get("schema_version") != "benchmark-registry-v1":
        errors.append("registry schema_version must be benchmark-registry-v1")
    entries = registry.get("benchmarks")
    if not isinstance(entries, list):
        return {"ok": False, "errors": errors + ["registry benchmarks must be a list"],
                "counts": {}}
    ids: set[tuple[str, int]] = set()
    manifest_paths: set[str] = set()
    valid_manifests = 0
    for index, entry in enumerate(entries):
        label = f"registry.benchmarks[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label}: must be an object")
            continue
        identity = (str(entry.get("benchmark_id")), entry.get("version"))
        if identity in ids:
            errors.append(f"{label}: duplicate benchmark identity {identity}")
        ids.add(identity)
        stored = str(entry.get("manifest_path"))
        if stored in manifest_paths:
            errors.append(f"{label}: duplicate manifest path {stored}")
        manifest_paths.add(stored)
        path = _file_ref(
            root, entry, errors, label,
            path_key="manifest_path", sha_key="manifest_sha256", bytes_key="manifest_bytes")
        if path is None:
            continue
        try:
            manifest = _read(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{label}: invalid benchmark JSON: {exc}")
            continue
        valid_manifests += 1
        _validate_benchmark(root, entry, manifest, errors)

    benchmark_root = resolve_stored_path(root, "benchmarks")
    disk_manifests = {
        f"benchmarks/{path.relative_to(benchmark_root).as_posix()}"
        for path in benchmark_root.glob("*/benchmark.json")
    }
    for orphan in sorted(disk_manifests - manifest_paths):
        errors.append(f"orphan benchmark manifest: {orphan}")
    for missing in sorted(manifest_paths - disk_manifests):
        errors.append(f"registered benchmark manifest not found: {missing}")
    return {
        "ok": not errors,
        "errors": errors,
        "counts": {
            "registry_entries": len(entries),
            "benchmark_manifests": valid_manifests,
            "disk_manifests": len(disk_manifests),
        },
        "benchmark_ids": [entry.get("benchmark_id") for entry in entries
                          if isinstance(entry, dict)],
        "registry_sha256": _sha(registry_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate", "list", "show"])
    parser.add_argument("benchmark_id", nargs="?")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    report = validate_registry(root)
    if args.command == "validate":
        if args.receipt:
            receipt = {
                "schema_version": "benchmark-registry-validation-v1",
                "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                **report,
            }
            receipt_path = args.receipt if args.receipt.is_absolute() else root / args.receipt
            _write(receipt_path, receipt)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report["ok"] else 1)
    if not report["ok"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    registry = _read(resolve_stored_path(root, REGISTRY_PATH.as_posix()))
    if args.command == "list":
        rows = [{key: entry.get(key) for key in
                 ("benchmark_id", "version", "status", "benchmark_class", "latest_run_id")}
                for entry in registry["benchmarks"]]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not args.benchmark_id:
        parser.error("show requires benchmark_id")
    entry = next((row for row in registry["benchmarks"]
                  if row.get("benchmark_id") == args.benchmark_id), None)
    if entry is None:
        raise SystemExit(f"unknown benchmark: {args.benchmark_id}")
    print(json.dumps(
        _read(resolve_stored_path(root, entry["manifest_path"])),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
