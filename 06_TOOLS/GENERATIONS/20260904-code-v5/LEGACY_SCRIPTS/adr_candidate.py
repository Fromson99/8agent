#!/usr/bin/env python3
"""Create and validate minimal, hash-pinned ADR code snapshots."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import sys
import tempfile
from typing import Any

from workspace_paths import StoredPathError, resolve_stored_path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
CANDIDATE_ROOT = Path(__import__("lawrag").__file__).resolve().parent / "research" / "candidates"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
ADR_ID_RE = re.compile(r"^ADR-(\d{4})$")
PROMOTION_CONTRACT = {
    "copy_to": "lawrag/runtime/components/",
    "register_in": "lawrag/runtime/registry.py",
    "requires_main_promotion": True,
}
CANDIDATE_SCHEMA_V1 = "adr-code-candidate-v1"
CANDIDATE_SCHEMA_V2 = "adr-code-candidate-v2"
UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stored_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _resolve_stored_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    try:
        return resolve_stored_path(ROOT, raw, require_exists=False)
    except StoredPathError:
        # Validation callers still need a concrete missing path so they can
        # report the record error instead of aborting the whole audit.
        return ROOT / path


def _is_within(path: Path, boundary: Path) -> bool:
    try:
        path.resolve().relative_to(boundary.resolve())
    except ValueError:
        return False
    return True


def _adr_number(value: Any) -> int | None:
    match = ADR_ID_RE.fullmatch(str(value or ""))
    return int(match.group(1)) if match else None


def _relative_file(raw: str) -> tuple[Path, Path]:
    path = (ROOT / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
    try:
        relative = path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"source must stay inside workspace: {path}") from exc
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"source must be a regular file: {relative}")
    if relative.name.startswith(".env") or relative.suffix in {".key", ".pem"}:
        raise ValueError(f"secret-like source is forbidden: {relative}")
    return path, relative


def _target_relative(raw: str) -> Path:
    """Return one normalized, non-secret repository target path."""
    pure = PurePosixPath(raw)
    if (not raw or "\\" in raw or pure.is_absolute() or pure.as_posix() != raw or
            any(part in {"", ".", ".."} for part in pure.parts)):
        raise ValueError(f"target must be a normalized workspace-relative path: {raw}")
    relative = Path(*pure.parts)
    target = ROOT / relative
    if not _is_within(target, ROOT):
        raise ValueError(f"target must stay inside workspace: {raw}")
    if relative.name.startswith(".env") or relative.suffix in {".key", ".pem"}:
        raise ValueError(f"secret-like target is forbidden: {relative}")
    return relative


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _path_lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _upgrade_rows_to_v2(value: dict[str, Any]) -> None:
    """Upgrade present-upstream v1 rows without inventing new provenance."""
    if value.get("schema_version") == CANDIDATE_SCHEMA_V2:
        return
    if value.get("schema_version") != CANDIDATE_SCHEMA_V1:
        raise ValueError("unsupported candidate schema_version")
    for row in value.get("files") or ():
        if not isinstance(row, dict):
            raise ValueError("candidate file rows must be objects")
        upstream_path = str(row.get("upstream_path") or "")
        _target_relative(upstream_path)
        row["target_path"] = upstream_path
        row["upstream_state"] = "present"
    value["schema_version"] = CANDIDATE_SCHEMA_V2


def register_file(path: Path, target: str, *, upstream_state: str) -> Path:
    """Register an existing mutable snapshot file with truthful provenance.

    ``present`` binds the row to the current canonical file bytes. ``absent``
    requires the canonical target not to exist and records no upstream hash.
    The proposal file must already live at ``snapshot/<target>``.
    """
    manifest_path = path / "candidate.json" if path.is_dir() else path
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError(f"candidate manifest missing or symlink: {manifest_path}")
    value = json.loads(manifest_path.read_text("utf-8"))
    schema_version = value.get("schema_version")
    if schema_version not in {CANDIDATE_SCHEMA_V1, CANDIDATE_SCHEMA_V2}:
        raise ValueError("unsupported candidate schema_version")
    _upgrade_rows_to_v2(value)
    candidate_dir = manifest_path.parent
    number = _adr_number(value.get("adr_id"))
    candidate_id = str(value.get("candidate_id") or "")
    if number is not None and number >= 138:
        expected = CANDIDATE_ROOT / f"adr_{number:04d}" / candidate_id
        if manifest_path.resolve() != (expected / "candidate.json").resolve():
            raise ValueError("candidate manifest must stay under exact ADR candidate root")

    relative = _target_relative(target)
    snapshot_path = candidate_dir / "snapshot" / relative
    if (not _is_within(snapshot_path, candidate_dir / "snapshot") or
            not snapshot_path.is_file() or snapshot_path.is_symlink() or
            snapshot_path.stat().st_size == 0):
        raise ValueError(
            f"proposal must be an existing non-empty regular snapshot file: {snapshot_path}")
    rows = value.get("files")
    if not isinstance(rows, list):
        raise ValueError("candidate files must be a list")
    stored_snapshot = _stored_path(snapshot_path)
    if any(
        isinstance(row, dict) and (
            row.get("target_path") == relative.as_posix() or
            row.get("snapshot_path") == stored_snapshot
        )
        for row in rows
    ):
        raise ValueError(f"candidate target is already registered: {relative}")

    canonical = ROOT / relative
    current_hash = sha256(snapshot_path)
    if upstream_state == "present":
        if (not canonical.is_file() or canonical.is_symlink()):
            raise ValueError(f"present upstream must be a regular file: {relative}")
        upstream_hash: str | None = sha256(canonical)
        initial_hash = upstream_hash
        upstream_path: str | None = relative.as_posix()
        absence_verified_at: str | None = None
    elif upstream_state == "absent":
        if _path_lexists(canonical):
            raise ValueError(f"absent upstream target already exists: {relative}")
        upstream_hash = None
        initial_hash = current_hash
        upstream_path = None
        absence_verified_at = _utc_now()
    else:
        raise ValueError("upstream_state must be present or absent")

    row: dict[str, Any] = {
        "target_path": relative.as_posix(),
        "upstream_state": upstream_state,
        "upstream_path": upstream_path,
        "upstream_sha256": upstream_hash,
        "initial_snapshot_sha256": initial_hash,
        "snapshot_path": stored_snapshot,
        "snapshot_sha256": current_hash,
        "bytes": snapshot_path.stat().st_size,
    }
    if absence_verified_at is not None:
        row["upstream_absence_verified_at"] = absence_verified_at
    rows.append(row)
    rows.sort(key=lambda item: str(item.get("target_path") or ""))
    value["updated_at"] = _utc_now()
    manifest_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    return manifest_path


def import_present_file(path: Path, target: str) -> Path:
    """Copy one stable canonical file into an existing mutable candidate.

    The destination is published only after the canonical file identity and
    bytes remain unchanged across the copy.  ``register_file`` then records
    the normal present-upstream provenance row.
    """

    manifest_path = path / "candidate.json" if path.is_dir() else path
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError(f"candidate manifest missing or symlink: {manifest_path}")
    relative = _target_relative(target)
    canonical = ROOT / relative
    if not canonical.is_file() or canonical.is_symlink():
        raise ValueError(f"present upstream must be a regular file: {relative}")
    snapshot = manifest_path.parent / "snapshot" / relative
    if _path_lexists(snapshot):
        raise ValueError(f"candidate snapshot target already exists: {relative}")
    snapshot.parent.mkdir(parents=True, exist_ok=True)

    before = canonical.lstat()
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    source_hash = sha256(canonical)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{snapshot.name}.candidate-import-",
        dir=snapshot.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(canonical, temporary, follow_symlinks=False)
        after = canonical.lstat()
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if before_identity != after_identity or sha256(canonical) != source_hash:
            raise ValueError(f"present upstream changed during import: {relative}")
        if sha256(temporary) != source_hash:
            raise ValueError(f"candidate import copy mismatch: {relative}")
        os.replace(temporary, snapshot)
    finally:
        if _path_lexists(temporary):
            temporary.unlink()
    return register_file(manifest_path, relative.as_posix(), upstream_state="present")


def refresh(path: Path) -> Path:
    """Refresh mutable snapshot hashes without rewriting upstream provenance.

    Only files already registered in ``candidate.json`` are accepted.  This is
    intentionally not a discovery operation: an unregistered file remains an
    error so a candidate cannot silently expand its promotion scope.
    """

    manifest_path = path / "candidate.json" if path.is_dir() else path
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError(f"candidate manifest missing or symlink: {manifest_path}")
    value = json.loads(manifest_path.read_text("utf-8"))
    if value.get("schema_version") != CANDIDATE_SCHEMA_V2:
        raise ValueError("candidate refresh requires schema_version v2")
    candidate_dir = manifest_path.parent
    rows = value.get("files")
    if not isinstance(rows, list) or not rows:
        raise ValueError("candidate files must be a non-empty list")

    declared: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("candidate file rows must be objects")
        target_path = _target_relative(str(row.get("target_path") or ""))
        snapshot_path = _resolve_stored_path(str(row.get("snapshot_path") or ""))
        expected = candidate_dir / "snapshot" / target_path
        if (snapshot_path.resolve() != expected.resolve() or
                not _is_within(snapshot_path, candidate_dir / "snapshot") or
                not snapshot_path.is_file() or snapshot_path.is_symlink() or
                snapshot_path.stat().st_size == 0):
            raise ValueError(
                f"registered snapshot is not a non-empty contained file: {snapshot_path}")
        stored = _stored_path(snapshot_path)
        if stored in declared:
            raise ValueError(f"duplicate snapshot path: {stored}")
        declared.add(stored)

    discovered: set[str] = set()
    snapshot_root = candidate_dir / "snapshot"
    if not snapshot_root.is_dir() or snapshot_root.is_symlink():
        raise ValueError("candidate snapshot root must be a real directory")
    for child in snapshot_root.rglob("*"):
        if child.is_symlink():
            raise ValueError(f"candidate snapshot contains a symlink: {child}")
        if child.is_file():
            discovered.add(_stored_path(child))
        elif child.exists() and not child.is_dir():
            raise ValueError(f"candidate snapshot contains a special file: {child}")
    if discovered != declared:
        raise ValueError("candidate snapshot inventory does not match manifest files")

    for row in rows:
        snapshot_path = _resolve_stored_path(str(row["snapshot_path"]))
        row["snapshot_sha256"] = sha256(snapshot_path)
        row["bytes"] = snapshot_path.stat().st_size
    value["updated_at"] = _utc_now()
    manifest_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    return manifest_path


def snapshot(
    adr: Path,
    candidate_id: str,
    sources: list[str],
    *,
    experiment_id: str | None = None,
    arm_id: str | None = None,
    run_ids: list[str] | None = None,
) -> Path:
    if not ID_RE.fullmatch(candidate_id):
        raise ValueError("candidate-id must be lower kebab-case")
    adr = adr.resolve()
    claim_path = adr / "claim.json"
    if not claim_path.is_file():
        raise ValueError(f"ADR claim.json missing: {adr}")
    claim = json.loads(claim_path.read_text("utf-8"))
    match = re.fullmatch(r"ADR-(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*", adr.name)
    if match is None:
        raise ValueError(f"invalid ADR directory name: {adr.name}")
    number = int(match.group(1))
    adr_id = str(claim.get("adr_id") or "")
    if adr_id != f"ADR-{number:04d}":
        raise ValueError("claim ADR ID must match candidate ADR directory")

    experiment_path = adr / "실험" / "manifest.json"
    if not experiment_path.is_file():
        raise ValueError(f"ADR experiment manifest missing: {experiment_path}")
    experiment = json.loads(experiment_path.read_text("utf-8"))
    declared_experiment_id = str(experiment.get("experiment_id") or "")
    strict = number >= 138
    if strict and not experiment_id:
        raise ValueError("ADR-0138+ snapshot requires --experiment-id")
    experiment_id = experiment_id or declared_experiment_id
    if experiment_id != declared_experiment_id:
        raise ValueError("candidate experiment_id must match ADR experiment manifest")

    run_id_list = list(run_ids or [])
    if strict and not arm_id:
        raise ValueError("ADR-0138+ snapshot requires --arm-id")
    if strict and not run_id_list:
        raise ValueError("ADR-0138+ snapshot requires at least one --run-id")
    if len(run_id_list) != len(set(run_id_list)):
        raise ValueError("candidate run IDs must be unique")

    arms = {
        str(row.get("id")): row
        for row in experiment.get("design", {}).get("arms", [])
        if isinstance(row, dict)
    }
    if arm_id:
        arm = arms.get(arm_id)
        if not isinstance(arm, dict) or arm.get("role") != "candidate":
            raise ValueError("candidate arm_id must reference role=candidate")
    runs = {
        str(row.get("id")): row
        for row in experiment.get("runs", [])
        if isinstance(row, dict)
    }
    for run_id in run_id_list:
        run = runs.get(run_id)
        if not isinstance(run, dict) or arm_id not in run.get("arm_ids", []):
            raise ValueError(f"candidate run_id must execute arm {arm_id}: {run_id}")

    target = CANDIDATE_ROOT / f"adr_{number:04d}" / candidate_id
    if not _is_within(target, CANDIDATE_ROOT):
        raise ValueError(f"candidate target escapes research root: {target}")
    if target.exists():
        raise ValueError(f"candidate snapshot already exists: {target}")
    resolved = [_relative_file(raw) for raw in sources]
    if not resolved:
        raise ValueError("at least one --source is required")
    relative_paths = [relative.as_posix() for _, relative in resolved]
    if len(relative_paths) != len(set(relative_paths)):
        raise ValueError("candidate sources must be unique")

    rows = []
    for source, relative in resolved:
        copied = target / "snapshot" / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, copied)
        copied_hash = sha256(copied)
        rows.append({
            "target_path": relative.as_posix(),
            "upstream_state": "present",
            "upstream_path": relative.as_posix(),
            "upstream_sha256": sha256(source),
            "initial_snapshot_sha256": copied_hash,
            "snapshot_path": _stored_path(copied),
            "snapshot_sha256": copied_hash,
            "bytes": copied.stat().st_size,
        })
    created_at = _utc_now()
    manifest = {
        "schema_version": CANDIDATE_SCHEMA_V2,
        "adr_id": adr_id,
        "adr_path": _stored_path(adr),
        "experiment_id": experiment_id,
        "arm_id": arm_id,
        "run_ids": run_id_list,
        "candidate_id": candidate_id,
        "created_at": created_at,
        "updated_at": created_at,
        "status": "research-only",
        "production_loadable": False,
        "files": rows,
        "revisions": [],
        "promotion_contract": dict(PROMOTION_CONTRACT),
    }
    (target / "candidate.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    return target


def validate(path: Path) -> list[str]:
    manifest_path = path / "candidate.json" if path.is_dir() else path
    if not manifest_path.is_file():
        return [f"candidate manifest missing: {manifest_path}"]
    value = json.loads(manifest_path.read_text("utf-8"))
    errors: list[str] = []
    schema_version = value.get("schema_version")
    if schema_version not in {CANDIDATE_SCHEMA_V1, CANDIDATE_SCHEMA_V2}:
        errors.append("unsupported schema_version")
    if value.get("production_loadable") is not False:
        errors.append("research snapshot must set production_loadable=false")

    number = _adr_number(value.get("adr_id"))
    strict = number is not None and number >= 138
    candidate_id = str(value.get("candidate_id") or "")
    candidate_dir = manifest_path.parent
    if strict:
        expected_dir = CANDIDATE_ROOT / f"adr_{number:04d}" / candidate_id
        if not ID_RE.fullmatch(candidate_id):
            errors.append("candidate_id must be lower kebab-case")
        if (manifest_path.is_symlink() or candidate_dir.is_symlink() or
                manifest_path.resolve() != (expected_dir / "candidate.json").resolve()):
            errors.append("candidate manifest must stay under exact ADR candidate root")
        if value.get("status") != "research-only":
            errors.append("candidate status must be research-only")
        if value.get("promotion_contract") != PROMOTION_CONTRACT:
            errors.append("candidate promotion contract is invalid")

        adr_path = _resolve_stored_path(str(value.get("adr_path") or ""))
        experiment_path = adr_path / "실험" / "manifest.json"
        if not experiment_path.is_file():
            errors.append(f"candidate ADR experiment manifest missing: {experiment_path}")
        else:
            experiment = json.loads(experiment_path.read_text("utf-8"))
            experiment_id = str(value.get("experiment_id") or "")
            arm_id = str(value.get("arm_id") or "")
            run_ids = value.get("run_ids")
            if experiment_id != experiment.get("experiment_id"):
                errors.append("candidate experiment_id linkage mismatch")
            arms = {
                str(row.get("id")): row
                for row in experiment.get("design", {}).get("arms", [])
                if isinstance(row, dict)
            }
            if arms.get(arm_id, {}).get("role") != "candidate":
                errors.append("candidate arm_id must reference role=candidate")
            if (not isinstance(run_ids, list) or not run_ids or
                    len(run_ids) != len(set(run_ids))):
                errors.append("candidate run_ids must be a non-empty unique list")
            else:
                runs = {
                    str(row.get("id")): row
                    for row in experiment.get("runs", [])
                    if isinstance(row, dict)
                }
                for run_id in run_ids:
                    run = runs.get(str(run_id))
                    if not isinstance(run, dict) or arm_id not in run.get("arm_ids", []):
                        errors.append(
                            f"candidate run_id must execute arm {arm_id}: {run_id}")

    rows = value.get("files")
    if not isinstance(rows, list) or (strict and not rows):
        errors.append("candidate files must be a non-empty list")
        rows = []
    seen_paths: set[str] = set()
    seen_targets: set[str] = set()
    current_hashes: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            errors.append("candidate file rows must be objects")
            continue
        raw_path = str(row.get("snapshot_path") or "")
        if raw_path in seen_paths:
            errors.append(f"duplicate snapshot path: {raw_path}")
            continue
        seen_paths.add(raw_path)
        snapshot_path = _resolve_stored_path(raw_path)
        if strict and (not raw_path or not _is_within(snapshot_path, candidate_dir) or
                       snapshot_path.is_symlink()):
            errors.append(f"snapshot escapes candidate root or is symlink: {raw_path}")
            continue
        if not snapshot_path.is_file():
            errors.append(f"snapshot missing: {snapshot_path}")
            continue
        if strict and snapshot_path.stat().st_size == 0:
            errors.append(f"snapshot must not be empty: {snapshot_path}")
        actual_hash = sha256(snapshot_path)
        current_hashes[raw_path] = actual_hash
        if actual_hash != row.get("snapshot_sha256"):
            errors.append(f"snapshot hash mismatch: {snapshot_path}")
        if (strict or "bytes" in row) and row.get("bytes") != snapshot_path.stat().st_size:
            errors.append(f"snapshot byte size mismatch: {snapshot_path}")
        if strict and schema_version == CANDIDATE_SCHEMA_V2:
            raw_target = str(row.get("target_path") or "")
            try:
                target_path = _target_relative(raw_target)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if raw_target in seen_targets:
                errors.append(f"duplicate candidate target path: {raw_target}")
            seen_targets.add(raw_target)
            expected_snapshot = candidate_dir / "snapshot" / target_path
            if snapshot_path.resolve() != expected_snapshot.resolve():
                errors.append(
                    f"snapshot path does not match candidate target: {raw_path}")
            state = row.get("upstream_state")
            initial_hash = str(row.get("initial_snapshot_sha256") or "")
            if not re.fullmatch(r"[0-9a-f]{64}", initial_hash):
                errors.append(f"initial snapshot provenance hash is invalid: {raw_path}")
            if state == "present":
                upstream_path = str(row.get("upstream_path") or "")
                upstream_hash = str(row.get("upstream_sha256") or "")
                if upstream_path != raw_target:
                    errors.append(f"present upstream path must equal target path: {raw_path}")
                if (not re.fullmatch(r"[0-9a-f]{64}", upstream_hash) or
                        initial_hash != upstream_hash):
                    errors.append(f"present upstream provenance hash is invalid: {raw_path}")
                if "upstream_absence_verified_at" in row:
                    errors.append(
                        f"present upstream must not carry absence evidence: {raw_path}")
            elif state == "absent":
                if row.get("upstream_path") is not None:
                    errors.append(f"absent upstream path must be null: {raw_path}")
                if row.get("upstream_sha256") is not None:
                    errors.append(f"absent upstream hash must be null: {raw_path}")
                verified_at = str(row.get("upstream_absence_verified_at") or "")
                if not UTC_TIMESTAMP_RE.fullmatch(verified_at):
                    errors.append(
                        f"absent upstream verification time is invalid: {raw_path}")
            else:
                errors.append(f"upstream_state must be present or absent: {raw_path}")
        elif strict:
            initial_hash = str(row.get("initial_snapshot_sha256") or "")
            upstream_hash = str(row.get("upstream_sha256") or "")
            if (not re.fullmatch(r"[0-9a-f]{64}", initial_hash) or
                    initial_hash != upstream_hash):
                errors.append(f"initial snapshot provenance hash is invalid: {raw_path}")

    if strict and schema_version == CANDIDATE_SCHEMA_V2:
        snapshot_root = candidate_dir / "snapshot"
        discovered: set[str] = set()
        if not snapshot_root.is_dir() or snapshot_root.is_symlink():
            errors.append("candidate snapshot root must be a real directory")
        else:
            for child in snapshot_root.rglob("*"):
                if child.is_symlink():
                    errors.append(f"candidate snapshot contains a symlink: {child}")
                elif child.is_file():
                    discovered.add(_stored_path(child))
                elif child.exists() and not child.is_dir():
                    errors.append(f"candidate snapshot contains a special file: {child}")
        missing_rows = sorted(discovered - seen_paths)
        missing_files = sorted(seen_paths - discovered)
        for raw_path in missing_rows:
            errors.append(f"unregistered candidate snapshot file: {raw_path}")
        for raw_path in missing_files:
            errors.append(f"registered candidate snapshot file not discovered: {raw_path}")

    revisions = value.get("revisions")
    if revisions is None and not strict:
        revisions = []
    elif not isinstance(revisions, list):
        errors.append("candidate revisions must be a list")
        revisions = []
    if strict and not revisions:
        errors.append("frozen revision required")
    latest_hashes: dict[str, str] = {}
    for index, revision in enumerate(revisions, 1):
        if not isinstance(revision, dict):
            errors.append("candidate revisions must be objects")
            continue
        expected_id = f"rev-{index:03d}"
        if revision.get("revision_id") != expected_id:
            errors.append(f"frozen revision ID must be {expected_id}")
        payload = {key: item for key, item in revision.items()
                   if key != "revision_sha256"}
        if revision.get("revision_sha256") != canonical_sha256(payload):
            errors.append(f"frozen revision hash mismatch: {expected_id}")
        revision_rows = revision.get("files")
        if not isinstance(revision_rows, list):
            errors.append(f"frozen revision files must be a list: {expected_id}")
            continue
        revision_hashes: dict[str, str] = {}
        for row in revision_rows:
            if not isinstance(row, dict):
                errors.append(f"frozen revision file must be an object: {expected_id}")
                continue
            raw_snapshot = str(row.get("snapshot_path") or "")
            frozen_path = _resolve_stored_path(str(row.get("frozen_path") or ""))
            if strict and (not _is_within(frozen_path, candidate_dir) or
                           frozen_path.is_symlink()):
                errors.append(f"frozen file escapes candidate root: {frozen_path}")
                continue
            if not frozen_path.is_file():
                errors.append(f"frozen file missing: {frozen_path}")
                continue
            if sha256(frozen_path) != row.get("snapshot_sha256"):
                errors.append(f"frozen file hash mismatch: {frozen_path}")
            if row.get("bytes") != frozen_path.stat().st_size:
                errors.append(f"frozen file byte size mismatch: {frozen_path}")
            revision_hashes[raw_snapshot] = str(row.get("snapshot_sha256") or "")
        if index == len(revisions):
            latest_hashes = revision_hashes
    if strict and revisions and latest_hashes != current_hashes:
        errors.append("latest frozen revision does not match current snapshot")
    return errors


def freeze(path: Path) -> Path:
    """Freeze an immutable revision while preserving initial upstream provenance."""
    manifest_path = path / "candidate.json" if path.is_dir() else path
    if not manifest_path.is_file():
        raise ValueError(f"candidate manifest missing: {manifest_path}")
    value = json.loads(manifest_path.read_text("utf-8"))
    schema_version = value.get("schema_version")
    if schema_version not in {CANDIDATE_SCHEMA_V1, CANDIDATE_SCHEMA_V2}:
        raise ValueError("unsupported candidate schema_version")
    number = _adr_number(value.get("adr_id"))
    strict = number is not None and number >= 138
    if value.get("production_loadable") is not False:
        raise ValueError("only research-only candidates can be frozen")
    if strict and value.get("status") != "research-only":
        raise ValueError("candidate status must be research-only")
    if strict and value.get("promotion_contract") != PROMOTION_CONTRACT:
        raise ValueError("candidate promotion contract is invalid")

    candidate_dir = manifest_path.parent
    if schema_version == CANDIDATE_SCHEMA_V2:
        snapshot_root = candidate_dir / "snapshot"
        declared = {
            str(row.get("snapshot_path") or "")
            for row in value.get("files") or ()
            if isinstance(row, dict)
        }
        discovered: set[str] = set()
        if not snapshot_root.is_dir() or snapshot_root.is_symlink():
            raise ValueError("candidate snapshot root must be a real directory")
        for child in snapshot_root.rglob("*"):
            if child.is_symlink():
                raise ValueError(f"candidate snapshot contains a symlink: {child}")
            if child.is_file():
                discovered.add(_stored_path(child))
            elif child.exists() and not child.is_dir():
                raise ValueError(f"candidate snapshot contains a special file: {child}")
        if discovered != declared:
            raise ValueError("candidate snapshot inventory does not match manifest files")
    revisions = value.setdefault("revisions", [])
    if not isinstance(revisions, list):
        raise ValueError("candidate revisions must be a list")
    revision_id = f"rev-{len(revisions) + 1:03d}"
    revision_dir = candidate_dir / "revisions" / revision_id
    if revision_dir.exists():
        raise ValueError(f"frozen revision path already exists: {revision_dir}")

    frozen_at = _utc_now()
    revision_files = []
    for row in value.get("files") or ():
        raw_path = str(row.get("snapshot_path") or "")
        snapshot_path = _resolve_stored_path(raw_path)
        if (not snapshot_path.is_file() or snapshot_path.is_symlink() or
                snapshot_path.stat().st_size == 0 or
                not _is_within(snapshot_path, candidate_dir)):
            raise ValueError(f"snapshot is not a non-empty contained file: {snapshot_path}")
        if schema_version == CANDIDATE_SCHEMA_V2:
            target_path = _target_relative(str(row.get("target_path") or ""))
            state = row.get("upstream_state")
            canonical = ROOT / target_path
            if state == "present":
                expected_hash = str(row.get("upstream_sha256") or "")
                if (str(row.get("upstream_path") or "") != target_path.as_posix() or
                        not canonical.is_file() or canonical.is_symlink() or
                        sha256(canonical) != expected_hash):
                    raise ValueError(
                        f"present upstream changed before candidate freeze: {target_path}")
            elif state == "absent":
                if (row.get("upstream_path") is not None or
                        row.get("upstream_sha256") is not None or
                        _path_lexists(canonical)):
                    raise ValueError(
                        f"absent upstream appeared before candidate freeze: {target_path}")
            else:
                raise ValueError(f"invalid upstream_state for candidate freeze: {state}")
        else:
            target_path = Path(str(row.get("upstream_path") or ""))
        frozen_path = revision_dir / "snapshot" / target_path
        if target_path.is_absolute() or not _is_within(frozen_path, revision_dir):
            raise ValueError(f"target path escapes frozen revision: {target_path}")
        frozen_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot_path, frozen_path)
        current_hash = sha256(snapshot_path)
        row.setdefault(
            "initial_snapshot_sha256",
            str(row.get("upstream_sha256") or row.get("snapshot_sha256") or ""),
        )
        row["snapshot_sha256"] = current_hash
        row["bytes"] = snapshot_path.stat().st_size
        revision_files.append({
            "snapshot_path": raw_path,
            "frozen_path": _stored_path(frozen_path),
            "snapshot_sha256": current_hash,
            "bytes": frozen_path.stat().st_size,
        })
    if not revision_files:
        raise ValueError("candidate must contain at least one file")
    revision_files.sort(key=lambda row: row["snapshot_path"])
    revision = {
        "revision_id": revision_id,
        "frozen_at": frozen_at,
        "files": revision_files,
    }
    revision["revision_sha256"] = canonical_sha256(revision)
    revisions.append(revision)
    value["updated_at"] = frozen_at
    manifest_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("snapshot")
    create.add_argument("--adr", type=Path, required=True)
    create.add_argument("--candidate-id", required=True)
    create.add_argument("--experiment-id")
    create.add_argument("--arm-id")
    create.add_argument("--run-id", action="append", default=[])
    create.add_argument("--source", action="append", default=[])
    check = sub.add_parser("validate")
    check.add_argument("path", type=Path)
    freeze_parser = sub.add_parser("freeze")
    freeze_parser.add_argument("path", type=Path)
    register_parser = sub.add_parser("register")
    register_parser.add_argument("path", type=Path)
    register_parser.add_argument("--target", required=True)
    register_parser.add_argument(
        "--upstream-state", choices=("present", "absent"), required=True)
    import_parser = sub.add_parser("import-present")
    import_parser.add_argument("path", type=Path)
    import_parser.add_argument("--target", required=True)
    refresh_parser = sub.add_parser("refresh")
    refresh_parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            target = snapshot(
                args.adr,
                args.candidate_id,
                args.source,
                experiment_id=args.experiment_id,
                arm_id=args.arm_id,
                run_ids=args.run_id,
            )
            print(target)
            return 0
        if args.command == "freeze":
            print(freeze(args.path))
            return 0
        if args.command == "register":
            print(register_file(
                args.path,
                args.target,
                upstream_state=args.upstream_state,
            ))
            return 0
        if args.command == "import-present":
            print(import_present_file(args.path, args.target))
            return 0
        if args.command == "refresh":
            print(refresh(args.path))
            return 0
        errors = validate(args.path)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        print("candidate snapshot valid")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
