#!/usr/bin/env python3
"""Deterministic, stdlib-only contract runner for ADR-0158 frozen candidates.

The runner executes only verified source bytes from the exact frozen candidate
revision.  It never reads or writes bytecode beside that revision.  Service
startup scenarios execute again under ``python -I -S`` so an installed or
checkout ``lawrag`` package cannot satisfy an accidental import.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import types
from typing import Any, Callable, Mapping


sys.dont_write_bytecode = True


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
CANDIDATE_ROOT = Path(__import__("lawrag").__file__).resolve().parent / "research/candidates/adr_0158/v2-runtime-activation"
CANDIDATE_MANIFEST = CANDIDATE_ROOT / "candidate.json"
CANDIDATE_MANIFEST_SHA256 = "533e419284c8fa915bdffef2ab9d33f9e1d05ca513f4058aee7cba09e85b0818"
REVISION_ID = "rev-010"
REVISION_SHA256 = "81d028b4f16ded9b453e1c74d771fa541e9734eb94a054d9bccc395d2b8eff9f"
REVISION_ROOT = CANDIDATE_ROOT / "revisions" / REVISION_ID / "snapshot"
WORKSPACE_MODULE = REVISION_Path(__import__("lawrag").__file__).resolve().parent / "platform/workspace.py"
CATALOG_MODULE = REVISION_Path(__import__("lawrag").__file__).resolve().parent / "datasets/catalog.py"
RELEASE_MODULE = REVISION_Path(__import__("lawrag").__file__).resolve().parent / "platform/release.py"
SERVICE_MODULE = REVISION_ROOT / "service.py"
SCHEMA_ROOT = REVISION_ROOT / "00_SYSTEM/SCHEMAS"
CANDIDATE_SCHEMA_FILES = {
    "dataset-package-v2": SCHEMA_ROOT / "dataset-package-v2.schema.json",
    "workspace-layout-activation-v2": (
        SCHEMA_ROOT / "workspace-layout-activation-v2.schema.json"
    ),
    "workspace-copy-plan-v1": SCHEMA_ROOT / "workspace-copy-plan-v1.schema.json",
    "workspace-migration-phase-receipt-v4": (
        SCHEMA_ROOT / "workspace-migration-phase-receipt-v4.schema.json"
    ),
    "workspace-canonical-root-readiness-v2": (
        SCHEMA_ROOT / "workspace-canonical-root-readiness-v2.schema.json"
    ),
    "workspace-legacy-retirement-authorization-v1": (
        SCHEMA_ROOT / "workspace-legacy-retirement-authorization-v1.schema.json"
    ),
}
NOW = "2026-09-02T12:00:00Z"
RECEIPT_KINDS = ("schema", "hash", "acl", "smoke", "provenance")
RUNTIME_KEYS = (
    "STRUCTURE_STORE",
    "STRUCTURE_CUSTOM_DIR",
    "GLOSSARY_STORE",
    "RAG_LINKS_STORE",
    "RAG_VECTOR_STORE",
)
PRODUCT_CODE_PATHS = (
    "lawrag/core/rag/index.py",
    "lawrag/core/rag/vector.py",
    "lawrag/core/terms/embed_sections.py",
    "lawrag/datasets/catalog.py",
    "lawrag/platform/release.py",
    "lawrag/platform/workspace.py",
    "scripts/data_ship.sh",
    "scripts/genos_preflight.py",
    "service.py",
    "lawrag/core/rag/main_promotion.py",
    "scripts/rag_main_promotion.py",
    "lawrag/runtime",
    "lawrag/runtime/__init__.py",
    "lawrag/runtime/registry.py",
    "lawrag/runtime/components/__init__.py",
    "lawrag/runtime/components/legalclosure_v2.py",
    "lawrag/core/rag/switches.py",
    "00_SYSTEM/WORKSPACE.json",
    "config/dataset_sync/profiles.json",
    "var/out/structure/main",
)
MONITORED_ENV_KEYS = (
    "LAWRAG_LAYOUT_VERSION",
    "LAWRAG_LAYOUT_ACTIVATION_RECEIPT",
    "LAWRAG_LAYOUT_RETIREMENT_RECEIPT",
    "LAWRAG_WORKSPACE_ROOT",
    "LAWRAG_RELEASE_STORE",
    "LAWRAG_RELEASE_REQUIRED",
    "RAG_MAIN_PIPELINE_MANIFEST",
    "RAG_MAIN_PROMOTION_RECEIPTS",
    "STRUCTURE_STORE",
)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def stable_regular_bytes(path: Path) -> bytes:
    """Read one regular file without following a symlink or accepting drift."""

    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError(f"expected non-symlink regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    chunks: list[bytes] = []
    try:
        opened = os.fstat(descriptor)
        if _stat_identity(before) != _stat_identity(opened):
            raise RuntimeError(f"file changed before read: {path}")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    if _stat_identity(opened) != _stat_identity(after) or len(raw) != after.st_size:
        raise RuntimeError(f"file changed while read: {path}")
    return raw


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError(f"expected non-symlink regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if _stat_identity(before) != _stat_identity(opened):
            raise RuntimeError(f"file changed before hashing: {path}")
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if _stat_identity(opened) != _stat_identity(after) or total != after.st_size:
        raise RuntimeError(f"file changed while hashing: {path}")
    return digest.hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return sha256_bytes(canonical_bytes(value))


def h(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def _candidate_manifest() -> dict[str, Any]:
    raw = stable_regular_bytes(CANDIDATE_MANIFEST)
    if sha256_bytes(raw) != CANDIDATE_MANIFEST_SHA256:
        raise RuntimeError("candidate manifest hash changed")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("candidate manifest must be an object")
    return value


def _candidate_revision(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    revisions = [
        row
        for row in manifest.get("revisions", [])
        if isinstance(row, Mapping) and row.get("revision_id") == REVISION_ID
    ]
    if len(revisions) != 1 or revisions[0].get("revision_sha256") != REVISION_SHA256:
        raise RuntimeError("candidate revision identity changed")
    revision = revisions[0]
    payload = {key: value for key, value in revision.items() if key != "revision_sha256"}
    if canonical_sha256(payload) != REVISION_SHA256:
        raise RuntimeError("candidate revision manifest hash is invalid")
    return revision


def _manifested_revision_files(
    revision: Mapping[str, Any],
) -> dict[Path, Mapping[str, Any]]:
    expected: dict[Path, Mapping[str, Any]] = {}
    for row in revision.get("files", []):
        if not isinstance(row, Mapping):
            raise RuntimeError("candidate revision file record must be an object")
        raw_path = Path(str(row.get("frozen_path") or ""))
        path = raw_path if raw_path.is_absolute() else ROOT / raw_path
        path = Path(os.path.abspath(path))
        try:
            path.relative_to(REVISION_ROOT)
        except ValueError as exc:
            raise RuntimeError(f"frozen candidate path escapes revision: {path}") from exc
        if path in expected:
            raise RuntimeError(f"duplicate frozen candidate path: {path}")
        expected[path] = row
    if not expected:
        raise RuntimeError("candidate revision has no files")
    return expected


def _verify_exact_revision_tree(expected: Mapping[Path, Mapping[str, Any]]) -> None:
    """Reject every unmanifested entry and every symlink/special entry."""

    allowed_directories = {REVISION_ROOT}
    for path in expected:
        parent = path.parent
        while parent != REVISION_ROOT:
            allowed_directories.add(parent)
            parent = parent.parent
    seen_files: set[Path] = set()
    pending = [REVISION_ROOT]
    while pending:
        directory = pending.pop()
        info = directory.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise RuntimeError(f"candidate revision directory is not regular: {directory}")
        if directory not in allowed_directories:
            raise RuntimeError(f"unmanifested candidate directory: {directory}")
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                entry_info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(entry_info.st_mode):
                    raise RuntimeError(f"candidate revision contains symlink: {path}")
                if stat.S_ISDIR(entry_info.st_mode):
                    if path not in allowed_directories:
                        raise RuntimeError(f"unmanifested candidate directory: {path}")
                    pending.append(path)
                elif stat.S_ISREG(entry_info.st_mode):
                    if path not in expected:
                        raise RuntimeError(f"unmanifested candidate file: {path}")
                    seen_files.add(path)
                else:
                    raise RuntimeError(f"candidate revision contains special entry: {path}")
    if seen_files != set(expected):
        missing = sorted(str(path) for path in set(expected) - seen_files)
        raise RuntimeError(f"manifested candidate files are missing: {missing}")


def _verified_source_bytes(path: Path) -> bytes:
    manifest = _candidate_manifest()
    revision = _candidate_revision(manifest)
    expected = _manifested_revision_files(revision)
    _verify_exact_revision_tree(expected)
    normalized = Path(os.path.abspath(path))
    row = expected.get(normalized)
    if row is None:
        raise RuntimeError(f"module is not in frozen candidate manifest: {path}")
    raw = stable_regular_bytes(normalized)
    if len(raw) != row.get("bytes") or sha256_bytes(raw) != row.get("snapshot_sha256"):
        raise RuntimeError(f"frozen candidate source changed: {normalized}")
    return raw


def load_module(name: str, path: Path):
    raw = _verified_source_bytes(path)
    code = compile(raw, str(path), "exec", dont_inherit=True)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__cached__ = None
    module.__loader__ = None
    module.__package__ = name.rpartition(".")[0]
    module.__spec__ = None
    sys.modules[name] = module
    try:
        exec(code, module.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _synthetic_package(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__path__ = []  # type: ignore[attr-defined]
    module.__package__ = name
    sys.modules[name] = module
    return module


def install_isolated_candidate_modules():
    existing = sorted(
        name for name in sys.modules if name == "lawrag" or name.startswith("lawrag.")
    )
    if existing:
        raise RuntimeError(f"lawrag modules existed before isolation: {existing}")
    for name in ("lawrag", "lawrag.datasets", "lawrag.platform", "lawrag.runtime"):
        _synthetic_package(name)
    registry = types.ModuleType("lawrag.runtime.registry")

    def validate_profile_id(profile_id: str) -> None:
        if profile_id != "legalclosure-v2":
            raise ValueError(f"unregistered fixture profile: {profile_id}")

    registry.validate_profile_id = validate_profile_id  # type: ignore[attr-defined]
    registry.__synthetic__ = True  # type: ignore[attr-defined]
    sys.modules["lawrag.runtime.registry"] = registry
    catalog = load_module("lawrag.datasets.catalog", CATALOG_MODULE)
    release = load_module("lawrag.platform.release", RELEASE_MODULE)
    workspace = load_module("lawrag.platform.workspace", WORKSPACE_MODULE)
    return workspace, catalog, release


def module_provenance() -> list[dict[str, Any]]:
    rows = []
    allowed_root = REVISION_ROOT.resolve()
    for name in sorted(
        key for key in sys.modules if key == "lawrag" or key.startswith("lawrag.")
    ):
        module = sys.modules[name]
        raw_file = getattr(module, "__file__", None)
        synthetic = bool(getattr(module, "__synthetic__", False)) or raw_file is None
        if raw_file is not None:
            path = Path(raw_file).resolve()
            try:
                path.relative_to(allowed_root)
            except ValueError as exc:
                raise RuntimeError(f"product module leaked into runner: {name}={path}") from exc
            shown = path.relative_to(ROOT).as_posix()
        else:
            shown = None
        rows.append({"module": name, "file": shown, "synthetic": synthetic})
    return rows


def verify_candidate() -> dict[str, Any]:
    manifest = _candidate_manifest()
    if manifest.get("schema_version") != "adr-code-candidate-v2":
        raise RuntimeError("candidate manifest must use adr-code-candidate-v2")
    if "run-012" not in manifest.get("run_ids", []):
        raise RuntimeError("candidate manifest is not linked to run-012")
    revision = _candidate_revision(manifest)
    expected = _manifested_revision_files(revision)
    _verify_exact_revision_tree(expected)
    manifest_rows = manifest.get("files")
    if not isinstance(manifest_rows, list) or not manifest_rows:
        raise RuntimeError("candidate manifest has no file provenance rows")
    by_snapshot: dict[str, Mapping[str, Any]] = {}
    target_rows: list[dict[str, Any]] = []
    for row in manifest_rows:
        if not isinstance(row, Mapping):
            raise RuntimeError("candidate file provenance row must be an object")
        raw_snapshot = str(row.get("snapshot_path") or "")
        raw_target = str(row.get("target_path") or "")
        target = Path(raw_target)
        if (
            not raw_target
            or target.is_absolute()
            or ".." in target.parts
            or target.as_posix() != raw_target
        ):
            raise RuntimeError(f"candidate target path is unsafe: {raw_target}")
        if raw_snapshot in by_snapshot:
            raise RuntimeError(f"duplicate candidate snapshot provenance: {raw_snapshot}")
        by_snapshot[raw_snapshot] = row
        state = row.get("upstream_state")
        initial_hash = row.get("initial_snapshot_sha256")
        if not isinstance(initial_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", initial_hash):
            raise RuntimeError(f"candidate initial snapshot hash is invalid: {raw_target}")
        if state == "present":
            if (
                row.get("upstream_path") != raw_target
                or row.get("upstream_sha256") != initial_hash
                or "upstream_absence_verified_at" in row
            ):
                raise RuntimeError(f"candidate present provenance is invalid: {raw_target}")
        elif state == "absent":
            verified_at = row.get("upstream_absence_verified_at")
            if (
                row.get("upstream_path") is not None
                or row.get("upstream_sha256") is not None
                or not isinstance(verified_at, str)
                or not re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z",
                    verified_at,
                )
            ):
                raise RuntimeError(f"candidate absent provenance is invalid: {raw_target}")
        else:
            raise RuntimeError(f"candidate upstream_state is invalid: {raw_target}")
        target_rows.append({
            "target_path": raw_target,
            "upstream_state": state,
            "initial_snapshot_sha256": initial_hash,
        })
    if len({row["target_path"] for row in target_rows}) != len(target_rows):
        raise RuntimeError("candidate target paths are not unique")
    revision_rows = {
        str(row.get("snapshot_path") or ""): row
        for row in revision.get("files", [])
        if isinstance(row, Mapping)
    }
    if set(revision_rows) != set(by_snapshot):
        raise RuntimeError("candidate manifest files do not exactly match frozen revision")
    files = []
    for path, row in sorted(expected.items(), key=lambda item: str(item[0])):
        actual = sha256_file(path)
        if actual != row["snapshot_sha256"] or path.stat().st_size != row["bytes"]:
            raise RuntimeError(f"frozen candidate file changed: {path}")
        manifest_row = by_snapshot[str(row.get("snapshot_path") or "")]
        if (
            manifest_row.get("snapshot_sha256") != actual
            or manifest_row.get("bytes") != path.stat().st_size
            or path != REVISION_ROOT / str(manifest_row.get("target_path") or "")
        ):
            raise RuntimeError(f"candidate manifest/revision provenance mismatch: {path}")
        files.append({
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": actual,
            "bytes": path.stat().st_size,
        })
    return {
        "candidate_id": manifest["candidate_id"],
        "manifest_path": CANDIDATE_MANIFEST.relative_to(ROOT).as_posix(),
        "manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "revision_id": REVISION_ID,
        "revision_sha256": REVISION_SHA256,
        "target_provenance": sorted(target_rows, key=lambda row: row["target_path"]),
        "files": files,
    }


def _shown_path(path: Path) -> str:
    absolute = Path(os.path.abspath(path))
    try:
        return absolute.relative_to(ROOT).as_posix()
    except ValueError:
        return str(absolute)


def _configured_path(environment_key: str, fallback: Path | None = None) -> Path | None:
    value = os.environ.get(environment_key, "").strip()
    if value:
        path = Path(value).expanduser()
        return path if path.is_absolute() else Path.cwd() / path
    return fallback


def monitored_production_paths() -> tuple[Path, ...]:
    """Return the fixed code and discoverable production control-state paths."""

    paths = {ROOT / value for value in PRODUCT_CODE_PATHS}
    manifest = _candidate_manifest()
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise RuntimeError("candidate files must be a list")
    for row in rows:
        if not isinstance(row, Mapping):
            raise RuntimeError("candidate file row must be an object")
        raw_target = row.get("target_path", row.get("upstream_path"))
        if not isinstance(raw_target, str) or not raw_target:
            raise RuntimeError("candidate target path is missing")
        target = Path(raw_target)
        if target.is_absolute() or ".." in target.parts:
            raise RuntimeError(f"candidate target path is unsafe: {raw_target}")
        paths.add(ROOT / target)
    workspace_root = _configured_path("LAWRAG_WORKSPACE_ROOT", ROOT)
    if workspace_root is not None:
        paths.add(workspace_root / "00_SYSTEM/WORKSPACE.json")
    activation_receipt = _configured_path("LAWRAG_LAYOUT_ACTIVATION_RECEIPT")
    if activation_receipt is not None:
        paths.add(activation_receipt)
    retirement_receipt = _configured_path("LAWRAG_LAYOUT_RETIREMENT_RECEIPT")
    if retirement_receipt is not None:
        paths.add(retirement_receipt)

    repository_main = ROOT / "90_RUNTIME/LEGACY_VAR/out/structure/main/pipeline.json"
    paths.add(repository_main)
    paths.add(repository_main.with_name("promotion_receipts.jsonl"))
    structure_store = _configured_path("STRUCTURE_STORE", ROOT / "90_RUNTIME/LEGACY_VAR/out/structure/viewer")
    assert structure_store is not None
    default_main = structure_store.parent / "main/pipeline.json"
    main_manifest = _configured_path("RAG_MAIN_PIPELINE_MANIFEST", default_main)
    assert main_manifest is not None
    paths.add(main_manifest)
    main_receipts = _configured_path(
        "RAG_MAIN_PROMOTION_RECEIPTS",
        main_manifest.with_name("promotion_receipts.jsonl"),
    )
    assert main_receipts is not None
    paths.add(main_receipts)

    release_store = _configured_path("LAWRAG_RELEASE_STORE")
    if release_store is not None:
        paths.add(release_store)
        for relative in (
            "ACTIVE_RELEASE.json",
            "ACTIVATION_EVENTS",
            "MANIFESTS",
            "RELEASES",
            "VALIDATION_RECEIPTS",
            "RUNTIMES",
        ):
            paths.add(release_store / relative)
    return tuple(sorted((Path(os.path.abspath(path)) for path in paths), key=str))


def _entry_state(path: Path) -> dict[str, Any]:
    """Hash bytes and directory entries without following links or exposing content."""

    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"kind": "absent"}
    except OSError as exc:
        return {"kind": "unreadable", "error": type(exc).__name__, "errno": exc.errno}
    mode = f"{stat.S_IMODE(info.st_mode):04o}"
    if stat.S_ISLNK(info.st_mode):
        try:
            target = os.readlink(path)
        except OSError as exc:
            return {
                "kind": "symlink-unreadable",
                "mode": mode,
                "error": type(exc).__name__,
                "errno": exc.errno,
            }
        return {"kind": "symlink", "mode": mode, "target": target}
    if stat.S_ISREG(info.st_mode):
        try:
            return {
                "kind": "file",
                "mode": mode,
                "bytes": info.st_size,
                "sha256": sha256_file(path),
            }
        except (OSError, RuntimeError) as exc:
            return {
                "kind": "unreadable-file",
                "mode": mode,
                "bytes": info.st_size,
                "error": type(exc).__name__,
                "errno": getattr(exc, "errno", None),
            }
    if stat.S_ISDIR(info.st_mode):
        rows: list[dict[str, Any]] = []
        pending = [(path, "")]
        try:
            while pending:
                directory, prefix = pending.pop()
                with os.scandir(directory) as entries:
                    ordered = sorted(entries, key=lambda entry: entry.name)
                for entry in ordered:
                    relative = f"{prefix}/{entry.name}" if prefix else entry.name
                    child = Path(entry.path)
                    child_info = entry.stat(follow_symlinks=False)
                    child_mode = f"{stat.S_IMODE(child_info.st_mode):04o}"
                    if stat.S_ISDIR(child_info.st_mode):
                        rows.append({"path": relative, "kind": "directory", "mode": child_mode})
                        pending.append((child, relative))
                    elif stat.S_ISREG(child_info.st_mode):
                        rows.append({
                            "path": relative,
                            "kind": "file",
                            "mode": child_mode,
                            "bytes": child_info.st_size,
                            "sha256": sha256_file(child),
                        })
                    elif stat.S_ISLNK(child_info.st_mode):
                        rows.append({
                            "path": relative,
                            "kind": "symlink",
                            "mode": child_mode,
                            "target": os.readlink(child),
                        })
                    else:
                        rows.append({
                            "path": relative,
                            "kind": "special",
                            "mode": child_mode,
                            "device": child_info.st_rdev,
                        })
        except (OSError, RuntimeError) as exc:
            return {
                "kind": "unreadable-directory",
                "mode": mode,
                "error": type(exc).__name__,
                "errno": getattr(exc, "errno", None),
            }
        rows.sort(key=lambda row: row["path"])
        return {
            "kind": "directory",
            "mode": mode,
            "entry_count": len(rows),
            "tree_sha256": canonical_sha256(rows),
        }
    return {
        "kind": "special",
        "mode": mode,
        "device": info.st_rdev,
        "size": info.st_size,
    }


def production_state(paths: tuple[Path, ...]) -> dict[str, dict[str, Any]]:
    return {_shown_path(path): _entry_state(path) for path in paths}


def expected_upstream_hashes() -> dict[str, str | None]:
    manifest = _candidate_manifest()
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise RuntimeError("candidate upstream files must be a list")
    expected: dict[str, str | None] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise RuntimeError("candidate upstream row must be an object")
        raw_target = row.get("target_path", row.get("upstream_path"))
        if not isinstance(raw_target, str) or not raw_target:
            raise RuntimeError("candidate target path is missing")
        if raw_target in expected:
            raise RuntimeError(f"duplicate candidate target path: {raw_target}")
        state = row.get("upstream_state", "present")
        if state == "present":
            upstream_path = row.get("upstream_path")
            upstream_hash = row.get("upstream_sha256")
            if upstream_path != raw_target or not isinstance(upstream_hash, str):
                raise RuntimeError(f"invalid present upstream provenance: {raw_target}")
            expected[raw_target] = upstream_hash
        elif state == "absent":
            if row.get("upstream_path") is not None or row.get("upstream_sha256") is not None:
                raise RuntimeError(f"invalid absent upstream provenance: {raw_target}")
            expected[raw_target] = None
        else:
            raise RuntimeError(f"invalid upstream state: {raw_target}={state}")
    return expected


def observed_upstream_hashes(
    state: Mapping[str, Mapping[str, Any]],
    expected: Mapping[str, str | None],
) -> dict[str, str | None]:
    return {
        path: (
            str(state.get(path, {}).get("sha256"))
            if state.get(path, {}).get("kind") == "file"
            else (
                None
                if state.get(path, {}).get("kind") == "absent"
                else f"<{state.get(path, {}).get('kind', 'unmonitored')}>"
            )
        )
        for path in expected
    }


class Audit:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def check(self, name: str, condition: bool, **details: Any) -> None:
        passed = bool(condition)
        self.checks.append({"name": name, "passed": passed, "details": details})
        if not passed:
            raise AssertionError(name)

    def expect(
        self,
        name: str,
        error_type: type[BaseException],
        operation: Callable[[], Any],
        contains: str | None = None,
    ) -> BaseException:
        try:
            operation()
        except error_type as exc:
            if contains is not None and contains not in str(exc):
                self.check(name, False, expected_message=contains, actual=str(exc))
            self.check(name, True, error=type(exc).__name__, message=str(exc))
            return exc
        except BaseException as exc:
            self.check(
                name,
                False,
                expected=error_type.__name__,
                actual=type(exc).__name__,
                message=str(exc),
            )
            raise
        self.check(name, False, expected=error_type.__name__, actual="no error")
        raise AssertionError(name)


def _json_value_equal(left: object, right: object) -> bool:
    return canonical_bytes(left) == canonical_bytes(right)


def _resolve_candidate_schema_ref(
    reference: str,
    document: Mapping[str, Any],
    documents: Mapping[str, Mapping[str, Any]],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    location, separator, fragment = reference.partition("#")
    target_document = document if not location else documents.get(location)
    if not isinstance(target_document, Mapping):
        raise ValueError(f"unknown candidate schema reference: {reference}")
    target: object = target_document
    if separator and fragment:
        if not fragment.startswith("/"):
            raise ValueError(f"unsupported candidate schema fragment: {reference}")
        for raw_part in fragment[1:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, Mapping) or part not in target:
                raise ValueError(f"unresolved candidate schema reference: {reference}")
            target = target[part]
    if not isinstance(target, Mapping):
        raise ValueError(f"candidate schema reference is not an object: {reference}")
    return target, target_document


def _candidate_schema_errors(
    value: object,
    schema: Mapping[str, Any],
    *,
    document: Mapping[str, Any],
    documents: Mapping[str, Mapping[str, Any]],
    path: str = "$",
) -> list[str]:
    """Validate only the deterministic JSON Schema subset used by this audit."""

    errors: list[str] = []
    reference = schema.get("$ref")
    if reference is not None:
        if not isinstance(reference, str):
            return [f"{path}: $ref must be a string"]
        try:
            target, target_document = _resolve_candidate_schema_ref(
                reference, document, documents
            )
        except ValueError as exc:
            return [f"{path}: {exc}"]
        errors.extend(
            _candidate_schema_errors(
                value,
                target,
                document=target_document,
                documents=documents,
                path=path,
            )
        )

    if "const" in schema and not _json_value_equal(value, schema["const"]):
        errors.append(f"{path}: const mismatch")
    allowed = schema.get("enum")
    if isinstance(allowed, list) and not any(
        _json_value_equal(value, candidate) for candidate in allowed
    ):
        errors.append(f"{path}: enum mismatch")

    expected_type = schema.get("type")
    type_matches = True
    if expected_type == "object":
        type_matches = isinstance(value, dict)
    elif expected_type == "array":
        type_matches = isinstance(value, list)
    elif expected_type == "string":
        type_matches = isinstance(value, str)
    elif expected_type == "integer":
        type_matches = isinstance(value, int) and not isinstance(value, bool)
    elif expected_type == "boolean":
        type_matches = isinstance(value, bool)
    elif expected_type is not None:
        errors.append(f"{path}: unsupported schema type {expected_type!r}")
    if not type_matches:
        errors.append(f"{path}: expected {expected_type}")
        return errors

    if isinstance(value, dict):
        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            required = schema.get("required", [])
            if isinstance(required, list):
                for field in required:
                    if field not in value:
                        errors.append(f"{path}: missing {field}")
            if schema.get("additionalProperties") is False:
                for field in sorted(set(value) - set(properties)):
                    errors.append(f"{path}: additional property {field}")
            for field, child in properties.items():
                if field in value and isinstance(child, Mapping):
                    errors.extend(
                        _candidate_schema_errors(
                            value[field],
                            child,
                            document=document,
                            documents=documents,
                            path=f"{path}.{field}",
                        )
                    )

    if isinstance(value, list):
        minimum_items = schema.get("minItems")
        maximum_items = schema.get("maxItems")
        if isinstance(minimum_items, int) and len(value) < minimum_items:
            errors.append(f"{path}: fewer than minItems")
        if isinstance(maximum_items, int) and len(value) > maximum_items:
            errors.append(f"{path}: more than maxItems")
        if schema.get("uniqueItems") is True:
            encoded = [canonical_bytes(item) for item in value]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{path}: duplicate items")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for position, item in enumerate(value):
                errors.extend(
                    _candidate_schema_errors(
                        item,
                        item_schema,
                        document=document,
                        documents=documents,
                        path=f"{path}[{position}]",
                    )
                )

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            errors.append(f"{path}: shorter than minLength")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            errors.append(f"{path}: pattern mismatch")

    if isinstance(value, int) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, int) and value < minimum:
            errors.append(f"{path}: below minimum")

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for position, branch in enumerate(all_of):
            if not isinstance(branch, Mapping):
                errors.append(f"{path}: allOf[{position}] is not an object")
                continue
            errors.extend(
                _candidate_schema_errors(
                    value,
                    branch,
                    document=document,
                    documents=documents,
                    path=path,
                )
            )
    condition = schema.get("if")
    consequence = schema.get("then")
    if isinstance(condition, Mapping) and isinstance(consequence, Mapping):
        condition_errors = _candidate_schema_errors(
            value,
            condition,
            document=document,
            documents=documents,
            path=path,
        )
        if not condition_errors:
            errors.extend(
                _candidate_schema_errors(
                    value,
                    consequence,
                    document=document,
                    documents=documents,
                    path=path,
                )
            )
    return errors


def _schema_declaration_errors(schema: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, list):
            for position, child in enumerate(node):
                walk(child, f"{path}[{position}]")
            return
        if not isinstance(node, Mapping):
            return
        if node.get("type") == "object":
            properties = node.get("properties")
            required = node.get("required")
            if not isinstance(properties, Mapping):
                errors.append(f"{path}: object properties must be an object")
            if not isinstance(required, list) or len(required) != len(set(required)):
                errors.append(f"{path}: object required must be a unique list")
            elif isinstance(properties, Mapping) and not set(required).issubset(properties):
                errors.append(f"{path}: required is not a subset of properties")
            if node.get("additionalProperties") is not False:
                errors.append(f"{path}: additionalProperties must be false")
        for key, child in node.items():
            if key != "$ref":
                walk(child, f"{path}.{key}")

    walk(schema, "$")
    return errors


def _schema_reference_errors(
    schema: Mapping[str, Any],
    documents: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []

    def walk(
        node: object,
        document: Mapping[str, Any],
        path: str,
        stack: frozenset[int],
    ) -> None:
        if isinstance(node, list):
            for position, child in enumerate(node):
                walk(child, document, f"{path}[{position}]", stack)
            return
        if not isinstance(node, Mapping):
            return
        reference = node.get("$ref")
        if reference is not None:
            if not isinstance(reference, str):
                errors.append(f"{path}: $ref must be a string")
            else:
                try:
                    target, target_document = _resolve_candidate_schema_ref(
                        reference, document, documents
                    )
                except ValueError as exc:
                    errors.append(f"{path}: {exc}")
                else:
                    target_identity = id(target)
                    if target_identity in stack:
                        errors.append(f"{path}: cyclic $ref {reference}")
                    else:
                        walk(
                            target,
                            target_document,
                            f"{path}->$ref({reference})",
                            stack | {target_identity},
                        )
        for key, child in node.items():
            if key != "$ref":
                walk(child, document, f"{path}.{key}", stack)

    walk(schema, schema, "$", frozenset({id(schema)}))
    return errors


def schema_contract_audit(workspace, catalog, audit: Audit) -> dict[str, Any]:
    """Audit the frozen candidate schemas with a stdlib-only schema subset."""

    expected_constants = {
        "dataset-package-v2": catalog.PACKAGE_SCHEMA,
        "workspace-layout-activation-v2": workspace.ACTIVATION_RECEIPT_SCHEMA,
        "workspace-copy-plan-v1": workspace.MIGRATION_PLAN_SCHEMA,
        "workspace-migration-phase-receipt-v4": workspace.MIGRATION_RECEIPT_SCHEMA,
        "workspace-canonical-root-readiness-v2": (
            workspace.CANONICAL_ROOT_BINDING_SCHEMA
        ),
        "workspace-legacy-retirement-authorization-v1": (
            workspace.RETIREMENT_RECEIPT_SCHEMA
        ),
    }
    expected_fields = {
        "dataset-package-v2": (
            {
                "schema_version",
                "package_id",
                "dataset_id",
                "version_id",
                "variant_id",
                "generation_id",
                "source_origin",
                "security_class",
                "representation",
                "authority",
                "export_policy",
                "build",
                "artifacts",
            },
            {
                "schema_version",
                "package_id",
                "dataset_id",
                "version_id",
                "variant_id",
                "generation_id",
                "source_origin",
                "security_class",
                "representation",
                "authority",
                "export_policy",
                "build",
                "artifacts",
                "manifest_sha256",
            },
        ),
        "workspace-layout-activation-v2": (
            {
                "schema_version",
                "status",
                "layout_version",
                "workspace_manifest_sha256",
                "validation_receipt_path",
                "validation_receipt_sha256",
                "validation_record_sha256",
                "migration_plan_sha256",
                "activation_id",
            },
            {
                "schema_version",
                "status",
                "layout_version",
                "workspace_manifest_sha256",
                "validation_receipt_path",
                "validation_receipt_sha256",
                "validation_record_sha256",
                "migration_plan_sha256",
                "activation_id",
            },
        ),
        "workspace-copy-plan-v1": (
            {
                "schema_version",
                "workspace_manifest_sha256",
                "sequence",
                "items",
                "source_deletion_supported",
                "plan_sha256",
            },
            {
                "schema_version",
                "workspace_manifest_sha256",
                "sequence",
                "items",
                "source_deletion_supported",
                "plan_sha256",
            },
        ),
        "workspace-migration-phase-receipt-v4": (
            {
                "schema_version",
                "phase",
                "workspace_manifest_sha256",
                "plan_sha256",
                "sequence",
                "completed_phases",
                "prior_receipt_sha256s",
                "items",
                "canonical_root_bindings",
                "source_deleted",
                "receipt_sha256",
            },
            {
                "schema_version",
                "phase",
                "workspace_manifest_sha256",
                "plan_sha256",
                "sequence",
                "completed_phases",
                "prior_receipt_sha256s",
                "items",
                "canonical_root_bindings",
                "source_deleted",
                "receipt_sha256",
            },
        ),
        "workspace-canonical-root-readiness-v2": (
            {
                "schema_version",
                "root_id",
                "canonical_path",
                "root_state",
                "completion_kind",
                "expected_kind",
                "evidence_targets",
                "readiness_sha256",
            },
            {
                "schema_version",
                "root_id",
                "canonical_path",
                "root_state",
                "completion_kind",
                "expected_kind",
                "evidence_targets",
                "readiness_sha256",
            },
        ),
        "workspace-legacy-retirement-authorization-v1": (
            {
                "schema_version",
                "status",
                "retirement_id",
                "workspace_manifest_sha256",
                "activation_receipt_path",
                "activation_receipt_sha256",
                "activation_id",
                "validation_receipt_path",
                "validation_receipt_sha256",
                "validation_record_sha256",
                "plan_sha256",
                "sources",
                "source_deletion_performed",
                "source_absence_authorized",
                "receipt_sha256",
            },
            {
                "schema_version",
                "status",
                "retirement_id",
                "workspace_manifest_sha256",
                "activation_receipt_path",
                "activation_receipt_sha256",
                "activation_id",
                "validation_receipt_path",
                "validation_receipt_sha256",
                "validation_record_sha256",
                "plan_sha256",
                "sources",
                "source_deletion_performed",
                "source_absence_authorized",
                "receipt_sha256",
            },
        ),
    }

    schemas: dict[str, Mapping[str, Any]] = {}
    documents: dict[str, Mapping[str, Any]] = {}
    file_records: list[dict[str, Any]] = []
    for expected_id, path in CANDIDATE_SCHEMA_FILES.items():
        raw = _verified_source_bytes(path)
        parsed = json.loads(raw)
        audit.check(
            f"schemas.{expected_id}.json-object",
            isinstance(parsed, dict),
            path=path.relative_to(REVISION_ROOT).as_posix(),
        )
        schema = parsed
        assert isinstance(schema, dict)
        schemas[expected_id] = schema
        documents[path.name] = schema
        documents[expected_id] = schema
        required, properties = expected_fields[expected_id]
        declaration_errors = _schema_declaration_errors(schema)
        audit.check(
            f"schemas.{expected_id}.closed-shape",
            schema.get("$schema")
            == "https://json-schema.org/draft/2020-12/schema"
            and schema.get("$id") == expected_id
            and schema.get("type") == "object"
            and schema.get("additionalProperties") is False
            and set(schema.get("required", [])) == required
            and set(schema.get("properties", {})) == properties
            and schema.get("properties", {})
            .get("schema_version", {})
            .get("const")
            == expected_id
            and not declaration_errors,
            declaration_errors=declaration_errors,
            required=sorted(schema.get("required", [])),
            properties=sorted(schema.get("properties", {})),
        )
        file_records.append(
            {
                "path": path.relative_to(REVISION_ROOT).as_posix(),
                "schema_id": expected_id,
                "sha256": sha256_bytes(raw),
                "bytes": len(raw),
            }
        )

    audit.check(
        "schemas.code-constants.match-candidate-ids",
        expected_constants == {schema_id: schema_id for schema_id in schemas}
        and schemas["workspace-legacy-retirement-authorization-v1"].get(
            "x-source-evidence-schema-id"
        )
        == workspace.RETIREMENT_SOURCE_EVIDENCE_SCHEMA,
        constants={
            **expected_constants,
            "retirement_source_evidence": (
                workspace.RETIREMENT_SOURCE_EVIDENCE_SCHEMA
            ),
        },
    )
    for schema_id, schema in schemas.items():
        reference_errors = _schema_reference_errors(schema, documents)
        audit.check(
            f"schemas.{schema_id}.references-resolve",
            not reference_errors,
            errors=reference_errors,
        )

    digest_a = h("schema-a")
    digest_b = h("schema-b")
    digest_c = h("schema-c")
    fingerprint = {
        "kind": "file",
        "mode": "0644",
        "bytes": 5,
        "content_sha256": digest_a,
        "merkle_sha256": digest_b,
        "file_count": 1,
        "directory_count": 0,
    }
    root_binding = {
        "schema_version": "workspace-canonical-root-readiness-v2",
        "root_id": "data",
        "canonical_path": "01_DATA",
        "root_state": "active",
        "completion_kind": "already-canonical",
        "expected_kind": "directory",
        "evidence_targets": ["01_DATA"],
        "readiness_sha256": digest_c,
    }
    phase_item = {
        "source": "legacy/data",
        "target": "01_DATA/data",
        "status": "verified",
        "publish_strategy": "renameat2",
        "fingerprint": fingerprint,
    }
    valid_payloads: dict[str, dict[str, Any]] = {
        "dataset-package-v2": {
            "schema_version": "dataset-package-v2",
            "package_id": "package-a",
            "dataset_id": "dataset-a",
            "version_id": "version-a",
            "variant_id": "variant-a",
            "generation_id": "generation-a",
            "source_origin": "public_external",
            "security_class": "public",
            "representation": "real",
            "authority": "authoritative",
            "export_policy": {"allowed": True},
            "build": {
                "build_id": "build-a",
                "execution_site": "outside",
                "code_revision": "revision-a",
                "compiler_profile": "profile-a",
                "capabilities": ["structure"],
            },
            "artifacts": [
                {
                    "logical_id": "document-a",
                    "role": "structure",
                    "path": "document-a.json",
                    "sha256": digest_a,
                    "media_type": "application/json",
                    "document_id": "document-a",
                }
            ],
        },
        "workspace-layout-activation-v2": {
            "schema_version": "workspace-layout-activation-v2",
            "status": "active",
            "layout_version": "v2",
            "workspace_manifest_sha256": digest_a,
            "validation_receipt_path": "00_SYSTEM/RECEIPTS/final.json",
            "validation_receipt_sha256": digest_b,
            "validation_record_sha256": digest_c,
            "migration_plan_sha256": digest_a,
            "activation_id": "activation-a",
        },
        "workspace-copy-plan-v1": {
            "schema_version": "workspace-copy-plan-v1",
            "workspace_manifest_sha256": digest_a,
            "sequence": ["copy-verify-0", "dual-read-compare", "final-verify"],
            "items": [
                {
                    "source": "legacy/data",
                    "target": "01_DATA/data",
                    "fingerprint": fingerprint,
                }
            ],
            "source_deletion_supported": False,
            "plan_sha256": digest_b,
        },
        "workspace-migration-phase-receipt-v4": {
            "schema_version": "workspace-migration-phase-receipt-v4",
            "phase": "final-verify",
            "workspace_manifest_sha256": digest_a,
            "plan_sha256": digest_b,
            "sequence": ["copy-verify-0", "dual-read-compare", "final-verify"],
            "completed_phases": [
                "copy-verify-0",
                "dual-read-compare",
                "final-verify",
            ],
            "prior_receipt_sha256s": [digest_a, digest_b],
            "items": [phase_item],
            "canonical_root_bindings": [root_binding],
            "source_deleted": False,
            "receipt_sha256": digest_c,
        },
        "workspace-canonical-root-readiness-v2": root_binding,
        "workspace-legacy-retirement-authorization-v1": {
            "schema_version": "workspace-legacy-retirement-authorization-v1",
            "status": "authorized",
            "retirement_id": "retirement-a",
            "workspace_manifest_sha256": digest_a,
            "activation_receipt_path": "00_SYSTEM/RECEIPTS/activation.json",
            "activation_receipt_sha256": digest_b,
            "activation_id": "activation-a",
            "validation_receipt_path": "00_SYSTEM/RECEIPTS/final.json",
            "validation_receipt_sha256": digest_c,
            "validation_record_sha256": digest_a,
            "plan_sha256": digest_b,
            "sources": [
                {
                    "source": "legacy/data",
                    "target": "01_DATA/data",
                    "fingerprint": fingerprint,
                    "final_item_sha256": digest_c,
                    "provenance_sha256": digest_a,
                }
            ],
            "source_deletion_performed": False,
            "source_absence_authorized": True,
            "receipt_sha256": digest_c,
        },
    }

    validation_records: list[dict[str, Any]] = []
    for schema_id, valid in valid_payloads.items():
        schema = schemas[schema_id]
        valid_errors = _candidate_schema_errors(
            valid,
            schema,
            document=schema,
            documents=documents,
        )
        missing = json.loads(json.dumps(valid))
        missing.pop(sorted(expected_fields[schema_id][0])[0])
        missing_errors = _candidate_schema_errors(
            missing,
            schema,
            document=schema,
            documents=documents,
        )
        additional = json.loads(json.dumps(valid))
        additional["unexpected"] = True
        additional_errors = _candidate_schema_errors(
            additional,
            schema,
            document=schema,
            documents=documents,
        )
        wrong_version = json.loads(json.dumps(valid))
        wrong_version["schema_version"] = "wrong-schema-version"
        wrong_version_errors = _candidate_schema_errors(
            wrong_version,
            schema,
            document=schema,
            documents=documents,
        )
        audit.check(
            f"schemas.{schema_id}.representative-valid-invalid",
            not valid_errors
            and bool(missing_errors)
            and bool(additional_errors)
            and bool(wrong_version_errors),
            valid_errors=valid_errors,
            missing_errors=missing_errors,
            additional_errors=additional_errors,
            wrong_version_errors=wrong_version_errors,
        )
        validation_records.append(
            {
                "schema_id": schema_id,
                "valid_error_count": len(valid_errors),
                "invalid_cases_rejected": sum(
                    bool(errors)
                    for errors in (
                        missing_errors,
                        additional_errors,
                        wrong_version_errors,
                    )
                ),
            }
        )

    package_without_document = json.loads(
        json.dumps(valid_payloads["dataset-package-v2"])
    )
    package_without_document["artifacts"][0].pop("document_id")
    invalid_document = json.loads(json.dumps(valid_payloads["dataset-package-v2"]))
    invalid_document["artifacts"][0]["document_id"] = "INVALID DOCUMENT"
    package_schema = schemas["dataset-package-v2"]
    audit.check(
        "schemas.dataset-package-v2.document-id-optional",
        not _candidate_schema_errors(
            package_without_document,
            package_schema,
            document=package_schema,
            documents=documents,
        )
        and bool(
            _candidate_schema_errors(
                invalid_document,
                package_schema,
                document=package_schema,
                documents=documents,
            )
        ),
    )

    invalid_phase = json.loads(
        json.dumps(valid_payloads["workspace-migration-phase-receipt-v4"])
    )
    invalid_phase["completed_phases"] = ["copy-verify-0"]
    phase_schema = schemas["workspace-migration-phase-receipt-v4"]
    invalid_completion = json.loads(
        json.dumps(valid_payloads["workspace-canonical-root-readiness-v2"])
    )
    invalid_completion["completion_kind"] = "migrated-legacy-root"
    binding_schema = schemas["workspace-canonical-root-readiness-v2"]
    audit.check(
        "schemas.workspace-lifecycle.conditionals",
        bool(
            _candidate_schema_errors(
                invalid_phase,
                phase_schema,
                document=phase_schema,
                documents=documents,
            )
        )
        and bool(
            _candidate_schema_errors(
                invalid_completion,
                binding_schema,
                document=binding_schema,
                documents=documents,
            )
        ),
    )

    def clone_payload(schema_id: str) -> dict[str, Any]:
        return json.loads(json.dumps(valid_payloads[schema_id]))

    copy_phase = clone_payload("workspace-migration-phase-receipt-v4")
    copy_phase.update(
        {
            "phase": "copy-verify-0",
            "completed_phases": ["copy-verify-0"],
            "prior_receipt_sha256s": [],
            "canonical_root_bindings": [],
        }
    )
    copy_phase["items"][0]["status"] = "published"
    dual_phase = clone_payload("workspace-migration-phase-receipt-v4")
    dual_phase.update(
        {
            "phase": "dual-read-compare",
            "completed_phases": ["copy-verify-0", "dual-read-compare"],
            "prior_receipt_sha256s": [digest_a],
            "canonical_root_bindings": [],
        }
    )
    dual_phase["items"][0]["status"] = "matched"
    bridge_binding = clone_payload("workspace-canonical-root-readiness-v2")
    bridge_binding.update(
        {
            "root_state": "bridge",
            "completion_kind": "migrated-legacy-root",
            "evidence_targets": ["01_DATA/data"],
        }
    )
    focused_valid = {
        "phase-copy": ("workspace-migration-phase-receipt-v4", copy_phase),
        "phase-dual": ("workspace-migration-phase-receipt-v4", dual_phase),
        "binding-bridge": (
            "workspace-canonical-root-readiness-v2",
            bridge_binding,
        ),
    }

    focused_invalid: dict[str, tuple[str, dict[str, Any]]] = {}

    def invalid_case(
        name: str,
        schema_id: str,
        path: tuple[object, ...],
        replacement: object,
    ) -> None:
        payload = clone_payload(schema_id)
        target: object = payload
        for part in path[:-1]:
            target = target[part]  # type: ignore[index]
        target[path[-1]] = replacement  # type: ignore[index]
        focused_invalid[name] = (schema_id, payload)

    invalid_case(
        "dataset-export-bool",
        "dataset-package-v2",
        ("export_policy", "allowed"),
        0,
    )
    invalid_case(
        "dataset-build-extra",
        "dataset-package-v2",
        ("build", "unexpected"),
        True,
    )
    invalid_case(
        "dataset-artifact-extra",
        "dataset-package-v2",
        ("artifacts", 0, "unexpected"),
        True,
    )
    invalid_case(
        "dataset-restricted-export",
        "dataset-package-v2",
        ("security_class",),
        "restricted",
    )
    invalid_case(
        "dataset-restricted-internal-export",
        "dataset-package-v2",
        ("source_origin",),
        "restricted_internal",
    )
    invalid_case(
        "dataset-noncanonical-dot-path",
        "dataset-package-v2",
        ("artifacts", 0, "path"),
        "./document-a.json",
    )
    invalid_case(
        "dataset-noncanonical-inner-dot-path",
        "dataset-package-v2",
        ("artifacts", 0, "path"),
        "nested/./document-a.json",
    )
    invalid_case(
        "dataset-noncanonical-trailing-slash",
        "dataset-package-v2",
        ("artifacts", 0, "path"),
        "document-a.json/",
    )
    invalid_case(
        "dataset-noncanonical-leading-space",
        "dataset-package-v2",
        ("artifacts", 0, "path"),
        " document-a.json",
    )
    invalid_case(
        "dataset-noncanonical-trailing-space",
        "dataset-package-v2",
        ("artifacts", 0, "path"),
        "document-a.json ",
    )
    invalid_case(
        "dataset-control-character-path",
        "dataset-package-v2",
        ("artifacts", 0, "path"),
        "document\t-a.json",
    )
    invalid_case(
        "dataset-empty-media-type",
        "dataset-package-v2",
        ("artifacts", 0, "media_type"),
        "",
    )
    duplicate_capability = clone_payload("dataset-package-v2")
    duplicate_capability["build"]["capabilities"] = ["structure", "structure"]
    focused_invalid["dataset-duplicate-capability"] = (
        "dataset-package-v2",
        duplicate_capability,
    )
    invalid_case(
        "plan-empty-items",
        "workspace-copy-plan-v1",
        ("items",),
        [],
    )
    invalid_case(
        "plan-fingerprint-bool-bytes",
        "workspace-copy-plan-v1",
        ("items", 0, "fingerprint", "bytes"),
        True,
    )
    invalid_case(
        "plan-parent-path",
        "workspace-copy-plan-v1",
        ("items", 0, "source"),
        "../legacy",
    )
    invalid_case(
        "activation-untrimmed-id",
        "workspace-layout-activation-v2",
        ("activation_id",),
        " activation-a",
    )
    invalid_case(
        "phase-final-empty-bindings",
        "workspace-migration-phase-receipt-v4",
        ("canonical_root_bindings",),
        [],
    )
    copy_bad_prior = json.loads(json.dumps(copy_phase))
    copy_bad_prior["prior_receipt_sha256s"] = [digest_a]
    focused_invalid["phase-copy-has-prior"] = (
        "workspace-migration-phase-receipt-v4",
        copy_bad_prior,
    )
    dual_bad_status = json.loads(json.dumps(dual_phase))
    dual_bad_status["items"][0]["status"] = "verified"
    focused_invalid["phase-dual-wrong-status"] = (
        "workspace-migration-phase-receipt-v4",
        dual_bad_status,
    )
    invalid_case(
        "phase-final-wrong-prior-count",
        "workspace-migration-phase-receipt-v4",
        ("prior_receipt_sha256s",),
        [digest_a],
    )
    invalid_case(
        "phase-item-extra",
        "workspace-migration-phase-receipt-v4",
        ("items", 0, "unexpected"),
        True,
    )
    invalid_case(
        "phase-external-ref-digest",
        "workspace-migration-phase-receipt-v4",
        ("canonical_root_bindings", 0, "readiness_sha256"),
        "not-a-sha256",
    )
    invalid_case(
        "binding-active-wrong-completion",
        "workspace-canonical-root-readiness-v2",
        ("completion_kind",),
        "migrated-legacy-root",
    )
    bridge_bad_completion = json.loads(json.dumps(bridge_binding))
    bridge_bad_completion["completion_kind"] = "already-canonical"
    focused_invalid["binding-bridge-wrong-completion"] = (
        "workspace-canonical-root-readiness-v2",
        bridge_bad_completion,
    )
    invalid_case(
        "binding-too-many-evidence-targets",
        "workspace-canonical-root-readiness-v2",
        ("evidence_targets",),
        ["01_DATA", "01_DATA/data"],
    )
    invalid_case(
        "retirement-empty-sources",
        "workspace-legacy-retirement-authorization-v1",
        ("sources",),
        [],
    )
    invalid_case(
        "retirement-source-extra",
        "workspace-legacy-retirement-authorization-v1",
        ("sources", 0, "unexpected"),
        True,
    )
    invalid_case(
        "retirement-deletion-performed",
        "workspace-legacy-retirement-authorization-v1",
        ("source_deletion_performed",),
        True,
    )
    invalid_case(
        "retirement-absence-bool",
        "workspace-legacy-retirement-authorization-v1",
        ("source_absence_authorized",),
        1,
    )

    focused_valid_errors = {
        name: _candidate_schema_errors(
            payload,
            schemas[schema_id],
            document=schemas[schema_id],
            documents=documents,
        )
        for name, (schema_id, payload) in focused_valid.items()
    }
    focused_invalid_errors = {
        name: _candidate_schema_errors(
            payload,
            schemas[schema_id],
            document=schemas[schema_id],
            documents=documents,
        )
        for name, (schema_id, payload) in focused_invalid.items()
    }
    audit.check(
        "schemas.focused-valid-invalid-matrix",
        all(not errors for errors in focused_valid_errors.values())
        and all(bool(errors) for errors in focused_invalid_errors.values()),
        valid_errors=focused_valid_errors,
        invalid_errors=focused_invalid_errors,
    )

    def dataset_runtime_error(payload: Mapping[str, Any]) -> str | None:
        try:
            catalog.package_from_mapping(payload)
        except catalog.DatasetContractError as exc:
            return str(exc)
        return None

    dataset_cross_cases: dict[str, tuple[dict[str, Any], bool]] = {
        "valid": (clone_payload("dataset-package-v2"), True),
        "optional-document-id": (package_without_document, True),
    }
    for name, path, replacement, expected_accept in (
        ("identifier-minimum", ("package_id",), "a0", True),
        (
            "identifier-punctuation",
            ("package_id",),
            "a.b_c:d/e-f",
            True,
        ),
        ("identifier-maximum", ("package_id",), "a" * 128, True),
        ("identifier-non-string", ("package_id",), 7, False),
        ("identifier-leading-space", ("package_id",), " package-a", False),
        ("identifier-trailing-space", ("package_id",), "package-a ", False),
        ("identifier-too-short", ("package_id",), "a", False),
        ("identifier-too-long", ("package_id",), "a" * 129, False),
        ("identifier-uppercase", ("package_id",), "Package-a", False),
        (
            "identifier-invalid-punctuation",
            ("package_id",),
            "package@a",
            False,
        ),
        ("identifier-final-newline", ("package_id",), "package-a\n", False),
        ("enum-non-string", ("source_origin",), 7, False),
        ("nested-enum-non-string", ("build", "execution_site"), 7, False),
        (
            "code-revision-internal-space",
            ("build", "code_revision"),
            "revision a",
            True,
        ),
        ("code-revision-non-string", ("build", "code_revision"), 7, False),
        (
            "code-revision-leading-space",
            ("build", "code_revision"),
            " revision-a",
            False,
        ),
        (
            "code-revision-next-line-edge",
            ("build", "code_revision"),
            "revision-a\u0085",
            False,
        ),
        (
            "code-revision-bom-edge",
            ("build", "code_revision"),
            "\ufeffrevision-a",
            False,
        ),
        (
            "compiler-profile-trailing-space",
            ("build", "compiler_profile"),
            "profile-a ",
            False,
        ),
        (
            "code-revision-final-newline",
            ("build", "code_revision"),
            "revision-a\n",
            False,
        ),
        (
            "compiler-profile-non-string",
            ("build", "compiler_profile"),
            7,
            False,
        ),
        ("compiler-profile-empty", ("build", "compiler_profile"), "", False),
        ("artifact-sha-non-string", ("artifacts", 0, "sha256"), 7, False),
        (
            "artifact-sha-final-newline",
            ("artifacts", 0, "sha256"),
            digest_a + "\n",
            False,
        ),
        (
            "artifact-path-leading-space",
            ("artifacts", 0, "path"),
            " doc.json",
            False,
        ),
    ):
        payload = clone_payload("dataset-package-v2")
        target: object = payload
        for part in path[:-1]:
            target = target[part]  # type: ignore[index]
        target[path[-1]] = replacement  # type: ignore[index]
        dataset_cross_cases[name] = (payload, expected_accept)

    missing_build_string = clone_payload("dataset-package-v2")
    missing_build_string["build"].pop("code_revision")
    dataset_cross_cases["code-revision-missing"] = (missing_build_string, False)

    dataset_cross_results: dict[str, dict[str, Any]] = {}
    for name, (payload, expected_accept) in dataset_cross_cases.items():
        schema_errors = _candidate_schema_errors(
            payload,
            package_schema,
            document=package_schema,
            documents=documents,
        )
        runtime_error = dataset_runtime_error(payload)
        schema_accepts = not schema_errors
        runtime_accepts = runtime_error is None
        dataset_cross_results[name] = {
            "expected_accept": expected_accept,
            "schema_accepts": schema_accepts,
            "runtime_accepts": runtime_accepts,
            "schema_errors": schema_errors,
            "runtime_error": runtime_error,
        }
    audit.check(
        "schemas.dataset-package-v2.runtime-language-equivalent",
        all(
            row["schema_accepts"] == row["runtime_accepts"] == row["expected_accept"]
            for row in dataset_cross_results.values()
        )
        and package_schema["properties"]["build"]["properties"][
            "code_revision"
        ]["pattern"]
        == catalog._CANONICAL_TEXT_PATTERN
        and package_schema["properties"]["build"]["properties"][
            "compiler_profile"
        ]["pattern"]
        == catalog._CANONICAL_TEXT_PATTERN,
        runtime_canonical_text_pattern=catalog._CANONICAL_TEXT_PATTERN,
        cases=dataset_cross_results,
    )

    dataset_path_schema = package_schema.get("$defs", {}).get("relative_path")
    if not isinstance(dataset_path_schema, Mapping):
        raise RuntimeError("dataset package schema has no relative_path definition")
    dataset_path_cross_results: dict[str, dict[str, Any]] = {}
    for case_name, value, expected_accept in (
        ("simple", "document.json", True),
        ("internal-space", "folder/file name.json", True),
        ("korean", "법규/원문.json", True),
        ("non-string", 7, False),
        ("empty", "", False),
        ("absolute", "/document.json", False),
        ("backslash", "folder\\document.json", False),
        ("dot", ".", False),
        ("leading-dot", "./document.json", False),
        ("inner-dot", "folder/./document.json", False),
        ("parent", "folder/../document.json", False),
        ("empty-segment", "folder//document.json", False),
        ("trailing-slash", "folder/", False),
        ("leading-space", " document.json", False),
        ("trailing-space", "document.json ", False),
        ("tab", "folder/file\tname.json", False),
        ("newline", "folder/file\nname.json", False),
        ("next-line", "folder/file\u0085name.json", False),
        ("no-break-space", "folder/file\u00a0name.json", False),
        ("bom", "folder/file\ufeffname.json", False),
    ):
        schema_errors = _candidate_schema_errors(
            value,
            dataset_path_schema,
            document=package_schema,
            documents=documents,
        )
        try:
            catalog._relative(value, "probe")
        except catalog.DatasetContractError as exc:
            runtime_error = str(exc)
        else:
            runtime_error = None
        dataset_path_cross_results[case_name] = {
            "expected_accept": expected_accept,
            "schema_accepts": not schema_errors,
            "runtime_accepts": runtime_error is None,
            "schema_errors": schema_errors,
            "runtime_error": runtime_error,
        }
    audit.check(
        "schemas.dataset-relative-path.runtime-language-equivalent",
        all(
            row["schema_accepts"] == row["runtime_accepts"] == row["expected_accept"]
            for row in dataset_path_cross_results.values()
        )
        and dataset_path_schema.get("pattern") == catalog._RELATIVE_PATH_PATTERN,
        runtime_pattern=catalog._RELATIVE_PATH_PATTERN,
        cases=dataset_path_cross_results,
    )

    workspace_schema_ids = tuple(
        schema_id
        for schema_id in CANDIDATE_SCHEMA_FILES
        if schema_id != "dataset-package-v2"
    )
    workspace_path_cases: tuple[tuple[str, object, bool], ...] = (
        ("root", "01_DATA", True),
        ("nested-punctuation", "01_DATA/a:b_c.d-e", True),
        ("nested-korean", "01_DATA/법규", True),
        ("non-string", 7, False),
        ("empty", "", False),
        ("absolute", "/01_DATA", False),
        ("backslash", "01_DATA\\x", False),
        ("dot", ".", False),
        ("leading-dot-segment", "./x", False),
        ("inner-dot-segment", "x/./y", False),
        ("parent", "..", False),
        ("inner-parent", "x/../y", False),
        ("empty-segment", "x//y", False),
        ("trailing-slash", "x/", False),
        ("leading-space", " x", False),
        ("trailing-space", "x ", False),
        ("tab", "x\ty", False),
        ("newline", "x\ny", False),
        ("no-break-space", "x\u00a0y", False),
    )
    workspace_path_cross_results: dict[str, dict[str, Any]] = {}
    workspace_path_patterns: dict[str, object] = {}
    for schema_id in workspace_schema_ids:
        schema = schemas[schema_id]
        path_schema = schema.get("$defs", {}).get("relative_path")
        if not isinstance(path_schema, Mapping):
            raise RuntimeError(f"{schema_id} has no relative_path definition")
        workspace_path_patterns[schema_id] = path_schema.get("pattern")
        for case_name, value, expected_accept in workspace_path_cases:
            schema_errors = _candidate_schema_errors(
                value,
                path_schema,
                document=schema,
                documents=documents,
            )
            try:
                workspace._migration_relative_path(value, field="probe")
            except workspace.LayoutError as exc:
                runtime_error = str(exc)
            else:
                runtime_error = None
            key = f"{schema_id}:{case_name}"
            workspace_path_cross_results[key] = {
                "expected_accept": expected_accept,
                "schema_accepts": not schema_errors,
                "runtime_accepts": runtime_error is None,
                "schema_errors": schema_errors,
                "runtime_error": runtime_error,
            }
    audit.check(
        "schemas.workspace-relative-path.runtime-language-equivalent",
        all(
            row["schema_accepts"] == row["runtime_accepts"] == row["expected_accept"]
            for row in workspace_path_cross_results.values()
        )
        and all(
            pattern == workspace._MIGRATION_RELATIVE_PATH_PATTERN
            for pattern in workspace_path_patterns.values()
        ),
        patterns=workspace_path_patterns,
        runtime_pattern=workspace._MIGRATION_RELATIVE_PATH_PATTERN,
        cases=workspace_path_cross_results,
    )

    canonical_text_schemas = {
        "activation.activation_id": (
            schemas["workspace-layout-activation-v2"],
            schemas["workspace-layout-activation-v2"]["properties"][
                "activation_id"
            ],
        ),
        "retirement.retirement_id": (
            schemas["workspace-legacy-retirement-authorization-v1"],
            schemas["workspace-legacy-retirement-authorization-v1"][
                "properties"
            ]["retirement_id"],
        ),
        "retirement.activation_id": (
            schemas["workspace-legacy-retirement-authorization-v1"],
            schemas["workspace-legacy-retirement-authorization-v1"][
                "properties"
            ]["activation_id"],
        ),
    }
    canonical_text_cases: tuple[tuple[str, object, bool], ...] = (
        ("simple", "activation-a", True),
        ("internal-space", "activation a", True),
        ("non-string", 7, False),
        ("empty", "", False),
        ("leading-space", " activation-a", False),
        ("trailing-space", "activation-a ", False),
        ("final-newline", "activation-a\n", False),
        ("next-line-edge", "activation-a\u0085", False),
        ("bom-edge", "\ufeffactivation-a", False),
    )
    canonical_text_cross_results: dict[str, dict[str, Any]] = {}
    for field_name, (schema, field_schema) in canonical_text_schemas.items():
        if not isinstance(field_schema, Mapping):
            raise RuntimeError(f"{field_name} schema is not an object")
        for case_name, value, expected_accept in canonical_text_cases:
            schema_errors = _candidate_schema_errors(
                value,
                field_schema,
                document=schema,
                documents=documents,
            )
            runtime_accepts = isinstance(value, str) and bool(
                workspace._CANONICAL_TEXT.fullmatch(value)
            )
            canonical_text_cross_results[f"{field_name}:{case_name}"] = {
                "expected_accept": expected_accept,
                "schema_accepts": not schema_errors,
                "runtime_accepts": runtime_accepts,
                "schema_errors": schema_errors,
            }
    audit.check(
        "schemas.workspace-canonical-text.runtime-language-equivalent",
        all(
            row["schema_accepts"] == row["runtime_accepts"] == row["expected_accept"]
            for row in canonical_text_cross_results.values()
        )
        and all(
            field_schema.get("pattern") == workspace._CANONICAL_TEXT_PATTERN
            for _schema, field_schema in canonical_text_schemas.values()
        ),
        runtime_pattern=workspace._CANONICAL_TEXT_PATTERN,
        cases=canonical_text_cross_results,
    )

    workspace_sha_cross_results: dict[str, dict[str, Any]] = {}
    for schema_id in workspace_schema_ids:
        schema = schemas[schema_id]
        sha_schema = schema.get("$defs", {}).get("sha256")
        if not isinstance(sha_schema, Mapping):
            raise RuntimeError(f"{schema_id} has no sha256 definition")
        for case_name, value, expected_accept in (
            ("valid", digest_a, True),
            ("non-string", int("1" * 64), False),
            ("short", digest_a[:-1], False),
            ("uppercase", "A" * 64, False),
            ("final-newline", digest_a + "\n", False),
        ):
            schema_errors = _candidate_schema_errors(
                value,
                sha_schema,
                document=schema,
                documents=documents,
            )
            runtime_accepts = workspace._is_sha256(value)
            workspace_sha_cross_results[f"{schema_id}:{case_name}"] = {
                "expected_accept": expected_accept,
                "schema_accepts": not schema_errors,
                "runtime_accepts": runtime_accepts,
                "schema_errors": schema_errors,
            }
    audit.check(
        "schemas.workspace-sha256.runtime-language-equivalent",
        all(
            row["schema_accepts"] == row["runtime_accepts"] == row["expected_accept"]
            for row in workspace_sha_cross_results.values()
        ),
        cases=workspace_sha_cross_results,
    )

    fingerprint_schema_ids = (
        "workspace-copy-plan-v1",
        "workspace-migration-phase-receipt-v4",
        "workspace-legacy-retirement-authorization-v1",
    )
    fingerprint_cases: dict[str, tuple[dict[str, Any], bool]] = {}
    file_fingerprint = json.loads(json.dumps(fingerprint))
    fingerprint_cases["file"] = (file_fingerprint, True)
    directory_fingerprint = json.loads(json.dumps(fingerprint))
    directory_fingerprint.update(
        {"kind": "directory", "file_count": 0, "directory_count": 1}
    )
    fingerprint_cases["directory"] = (directory_fingerprint, True)
    for name, kind, file_count, directory_count, expected_accept in (
        ("file-no-files", "file", 0, 0, False),
        ("file-with-directory", "file", 1, 1, False),
        ("directory-zero-count", "directory", 0, 0, False),
        ("special-kind", "fifo", 0, 0, False),
        ("negative-file-count", "directory", -1, 1, False),
        ("bool-file-count", "directory", True, 1, False),
    ):
        candidate_fingerprint = json.loads(json.dumps(fingerprint))
        candidate_fingerprint.update(
            {
                "kind": kind,
                "file_count": file_count,
                "directory_count": directory_count,
            }
        )
        fingerprint_cases[name] = (candidate_fingerprint, expected_accept)

    fingerprint_cross_results: dict[str, dict[str, Any]] = {}
    for schema_id in fingerprint_schema_ids:
        schema = schemas[schema_id]
        fingerprint_schema = schema.get("$defs", {}).get("fingerprint")
        if not isinstance(fingerprint_schema, Mapping):
            raise RuntimeError(f"{schema_id} has no fingerprint definition")
        for case_name, (value, expected_accept) in fingerprint_cases.items():
            schema_errors = _candidate_schema_errors(
                value,
                fingerprint_schema,
                document=schema,
                documents=documents,
            )
            try:
                workspace._fingerprint_from_mapping(value, field="probe")
            except workspace.LayoutError as exc:
                runtime_error = str(exc)
            else:
                runtime_error = None
            key = f"{schema_id}:{case_name}"
            fingerprint_cross_results[key] = {
                "expected_accept": expected_accept,
                "schema_accepts": not schema_errors,
                "runtime_accepts": runtime_error is None,
                "schema_errors": schema_errors,
                "runtime_error": runtime_error,
            }
    audit.check(
        "schemas.workspace-fingerprint.runtime-language-equivalent",
        all(
            row["schema_accepts"] == row["runtime_accepts"] == row["expected_accept"]
            for row in fingerprint_cross_results.values()
        ),
        cases=fingerprint_cross_results,
    )

    retirement_schema = schemas[
        "workspace-legacy-retirement-authorization-v1"
    ]

    def retirement_with_sources(
        source_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = clone_payload(
            "workspace-legacy-retirement-authorization-v1"
        )
        payload["sources"] = source_rows
        unsigned = dict(payload)
        unsigned.pop("receipt_sha256", None)
        unsigned["sources"] = sorted(
            source_rows,
            key=lambda row: (
                row["target"],
                row["source"],
                canonical_bytes(row),
            ),
        )
        payload["receipt_sha256"] = workspace._canonical_sha256(unsigned)
        return payload

    retirement_source_a = json.loads(
        json.dumps(
            valid_payloads[
                "workspace-legacy-retirement-authorization-v1"
            ]["sources"][0]
        )
    )
    retirement_source_a.update(
        {"source": "legacy/a", "target": "01_DATA/a"}
    )
    retirement_source_b = json.loads(json.dumps(retirement_source_a))
    retirement_source_b.update(
        {
            "source": "legacy/b",
            "target": "01_DATA/b",
            "final_item_sha256": h("retirement-final-b"),
            "provenance_sha256": h("retirement-provenance-b"),
        }
    )
    same_coordinate_different_evidence = json.loads(
        json.dumps(retirement_source_a)
    )
    same_coordinate_different_evidence.update(
        {
            "final_item_sha256": h("retirement-final-alternate"),
            "provenance_sha256": h("retirement-provenance-alternate"),
        }
    )
    retirement_source_cases = {
        "sorted": (
            retirement_with_sources([retirement_source_a, retirement_source_b]),
            True,
        ),
        "reversed-canonicalized": (
            retirement_with_sources([retirement_source_b, retirement_source_a]),
            True,
        ),
        "exact-duplicate": (
            retirement_with_sources([retirement_source_a, retirement_source_a]),
            False,
        ),
        "same-coordinate-different-evidence": (
            retirement_with_sources(
                [retirement_source_a, same_coordinate_different_evidence]
            ),
            True,
        ),
    }
    retirement_source_cross_results: dict[str, dict[str, Any]] = {}
    for name, (payload, expected_accept) in retirement_source_cases.items():
        schema_errors = _candidate_schema_errors(
            payload,
            retirement_schema,
            document=retirement_schema,
            documents=documents,
        )
        try:
            parsed_retirement = workspace._retirement_receipt_from_mapping(payload)
        except workspace.LayoutError as exc:
            runtime_error = str(exc)
            normalized_sources = None
        else:
            runtime_error = None
            normalized_sources = [
                [row.target, row.source] for row in parsed_retirement.sources
            ]
        retirement_source_cross_results[name] = {
            "expected_accept": expected_accept,
            "schema_accepts": not schema_errors,
            "runtime_accepts": runtime_error is None,
            "runtime_error": runtime_error,
            "schema_errors": schema_errors,
            "normalized_sources": normalized_sources,
        }
    audit.check(
        "schemas.workspace-retirement-sources.runtime-language-equivalent",
        all(
            row["schema_accepts"] == row["runtime_accepts"] == row["expected_accept"]
            for row in retirement_source_cross_results.values()
        )
        and retirement_source_cross_results["sorted"]["normalized_sources"]
        == retirement_source_cross_results["reversed-canonicalized"][
            "normalized_sources"
        ],
        cases=retirement_source_cross_results,
    )
    return {
        "schema_count": len(schemas),
        "files": file_records,
        "representative_payloads": validation_records,
        "dataset_runtime_cross_cases": dataset_cross_results,
        "dataset_path_runtime_cross_cases": dataset_path_cross_results,
        "workspace_path_runtime_cross_cases": workspace_path_cross_results,
        "workspace_canonical_text_runtime_cross_cases": (
            canonical_text_cross_results
        ),
        "workspace_sha256_runtime_cross_cases": workspace_sha_cross_results,
        "workspace_fingerprint_runtime_cross_cases": fingerprint_cross_results,
        "retirement_source_runtime_cross_cases": (
            retirement_source_cross_results
        ),
        "validator": "stdlib-json-schema-subset-v1",
    }


class _InjectedRenameat2Failure:
    def __init__(self) -> None:
        self.argtypes: list[Any] | None = None
        self.restype: Any = None

    def __call__(self, *_args: Any) -> int:
        return -1


class _InjectedLibC:
    def __init__(self) -> None:
        self.renameat2 = _InjectedRenameat2Failure()


def _with_renameat2_errno(
    candidate_module,
    error_number: int,
    operation: Callable[[], Any],
) -> Any:
    """Force one documented renameat2 fallback without changing the candidate."""

    original_cdll = candidate_module.ctypes.CDLL
    original_get_errno = candidate_module.ctypes.get_errno
    candidate_module.ctypes.CDLL = lambda *_args, **_kwargs: _InjectedLibC()
    candidate_module.ctypes.get_errno = lambda: error_number
    try:
        return operation()
    finally:
        candidate_module.ctypes.CDLL = original_cdll
        candidate_module.ctypes.get_errno = original_get_errno


def _with_os_override(
    candidate_module,
    name: str,
    replacement_factory: Callable[[Callable[..., Any]], Callable[..., Any]],
    operation: Callable[[], Any],
) -> Any:
    original = getattr(candidate_module.os, name)
    setattr(candidate_module.os, name, replacement_factory(original))
    try:
        return operation()
    finally:
        setattr(candidate_module.os, name, original)


def _with_module_override(
    candidate_module,
    name: str,
    replacement_factory: Callable[[Callable[..., Any]], Callable[..., Any]],
    operation: Callable[[], Any],
) -> Any:
    """Temporarily wrap one candidate helper for deterministic fault observation."""

    original = getattr(candidate_module, name)
    setattr(candidate_module, name, replacement_factory(original))
    try:
        return operation()
    finally:
        setattr(candidate_module, name, original)


def _legacy_contract_sha256(active: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {
            "schema_version": "dataset-overlay-contract-v1",
            "items": [
                {"logical_id": row["logical_id"], "contract": row["contract"]}
                for row in active["items"]
            ],
        }
    )


def workspace_audit(workspace, audit: Audit) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="adr0158-workspace-") as raw_root:
        root = Path(raw_root)
        legacy_root = root / "legacy-data"
        source_tree = legacy_root / "tree"
        source_tree.mkdir(parents=True)
        (source_tree / "a.txt").write_text("alpha\n", "utf-8")
        (source_tree / "nested").mkdir()
        (source_tree / "nested/b.json").write_text('{"b":2}\n', "utf-8")
        source_file = legacy_root / "single.json"
        source_file.write_text('{"single":true}\n', "utf-8")
        (root / "legacy").mkdir()
        layout = workspace.WorkspaceLayout(
            root=root,
            mode="bridge",
            default_layout_version="v1",
            canonical_root_pattern=r"^[0-9]{2}_[A-Z][A-Z0-9_]*$",
            roots={
                "data": workspace.RootSpec(
                    "data", "01_DATA", "legacy-data", "bridge"
                ),
                "backend": workspace.RootSpec(
                    "backend", "02_BACKEND", None, "active"
                ),
                "frontend": workspace.RootSpec(
                    "frontend", "03_FRONTEND", None, "active"
                ),
            },
            legacy_top_level_directories=("legacy-data",),
            root_file_policy={},
            invariants=("copy-only",),
            manifest_sha256=h("workspace-manifest"),
        )

        class InjectedLstatFailure:
            def __init__(self, error_number: int) -> None:
                self.error_number = error_number

            def lstat(self):
                raise OSError(self.error_number, "injected lstat failure")

        audit.check(
            "workspace.path-exists.regular-file",
            workspace._path_exists(source_file),
        )
        audit.check(
            "workspace.path-exists.absent",
            not workspace._path_exists(legacy_root / "absent.json"),
        )
        audit.check(
            "workspace.path-exists.non-directory-component",
            not workspace._path_exists(
                source_file / workspace.PUBLICATION_INCOMPLETE_MARKER
            ),
        )
        for error_number in (errno.EACCES, errno.ELOOP, errno.EIO):
            audit.expect(
                f"workspace.path-exists.{errno.errorcode[error_number].lower()}-propagates",
                OSError,
                lambda value=error_number: workspace._path_exists(
                    InjectedLstatFailure(value)
                ),
                "injected lstat failure",
            )

        fallback_strategies: dict[str, dict[str, str]] = {}
        for error_number in (errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP):
            error_name = errno.errorcode[error_number].lower()
            fallback_source = root / f"fallback-source/{error_name}"
            fallback_source.mkdir(parents=True)
            (fallback_source / "file.json").write_text(
                json.dumps({"errno": error_name}) + "\n", "utf-8"
            )
            (fallback_source / "tree").mkdir()
            (fallback_source / "tree/member.txt").write_text(
                f"tree:{error_name}\n", "utf-8"
            )
            fallback_plan = workspace.build_migration_plan(
                layout,
                [
                    (
                        f"fallback-source/{error_name}/file.json",
                        f"01_DATA/FALLBACK/{error_name}/file.json",
                    ),
                    (
                        f"fallback-source/{error_name}/tree",
                        f"01_DATA/FALLBACK/{error_name}/tree",
                    ),
                ],
            )
            fallback_receipt = _with_renameat2_errno(
                workspace,
                error_number,
                lambda plan=fallback_plan: workspace.execute_copy_verify_zero(
                    layout, plan
                ),
            )
            strategies = {
                row.source: row.publish_strategy for row in fallback_receipt.items
            }
            fallback_strategies[error_name] = strategies
            audit.check(
                f"workspace.fallback.{error_name}.strategies",
                strategies[f"fallback-source/{error_name}/file.json"] == "hardlink"
                and strategies[f"fallback-source/{error_name}/tree"]
                == "reserved-directory"
                and all(
                    workspace.inspect_publication(layout, row.target).ready
                    for row in fallback_receipt.items
                ),
                strategies=strategies,
            )

        crash_parent = root / "crash-fixtures"
        crash_parent.mkdir()
        sidecar_staging = crash_parent / ".sidecar-staging"
        sidecar_staging.mkdir()
        (sidecar_staging / "member.txt").write_text("sidecar\n", "utf-8")
        sidecar_target = crash_parent / "sidecar-crash"

        def fail_sidecar_target_mkdir(original):
            def injected(path, mode=0o777, *, dir_fd=None):
                if Path(path) == sidecar_target:
                    raise OSError(errno.EIO, "injected post-reservation mkdir crash")
                if dir_fd is None:
                    return original(path, mode)
                return original(path, mode, dir_fd=dir_fd)

            return injected

        audit.expect(
            "workspace.fallback.crash.sidecar-retained",
            OSError,
            lambda: _with_renameat2_errno(
                workspace,
                errno.EINVAL,
                lambda: _with_os_override(
                    workspace,
                    "mkdir",
                    fail_sidecar_target_mkdir,
                    lambda: workspace._atomic_publish_no_replace(
                        sidecar_staging, sidecar_target
                    ),
                ),
            ),
            "post-reservation",
        )
        sidecar_relative = "crash-fixtures/sidecar-crash"
        audit.expect(
            "workspace.fallback.crash.sidecar-readiness-rejected",
            workspace.LayoutError,
            lambda: workspace.assert_publication_ready(sidecar_target),
            "incomplete publication",
        )
        sidecar_state = _entry_state(crash_parent)
        sidecar_inspection = workspace.inspect_publication(
            layout, sidecar_relative
        )
        sidecar_quarantine = workspace.plan_publication_quarantine(
            layout,
            sidecar_relative,
            "99_ARCHIVE/sidecar-crash",
        )
        audit.check(
            "workspace.quarantine-plan.read-only",
            not sidecar_inspection.ready
            and bool(sidecar_inspection.marker_paths)
            and not sidecar_quarantine.as_dict()["executed"]
            and sidecar_state == _entry_state(crash_parent),
            inspection=sidecar_inspection.as_dict(),
            plan=sidecar_quarantine.as_dict(),
        )

        internal_staging = crash_parent / ".internal-staging"
        internal_staging.mkdir()
        (internal_staging / "member.txt").write_text("internal\n", "utf-8")
        internal_target = crash_parent / "internal-crash"

        def fail_first_child_rename(original):
            def injected(source, target, *args, **kwargs):
                if Path(target).parent == internal_target:
                    raise OSError(errno.EIO, "injected child publication crash")
                return original(source, target, *args, **kwargs)

            return injected

        audit.expect(
            "workspace.fallback.crash.internal-marker-retained",
            workspace.LayoutError,
            lambda: _with_renameat2_errno(
                workspace,
                errno.EINVAL,
                lambda: _with_os_override(
                    workspace,
                    "rename",
                    fail_first_child_rename,
                    lambda: workspace._atomic_publish_no_replace(
                        internal_staging, internal_target
                    ),
                ),
            ),
            "incomplete and retained",
        )
        audit.check(
            "workspace.fallback.crash.markers-present",
            (internal_target / workspace.PUBLICATION_INCOMPLETE_MARKER).is_file()
            and workspace._publication_sidecar(internal_target).is_file(),
        )
        audit.expect(
            "workspace.fallback.crash.internal-readiness-rejected",
            workspace.LayoutError,
            lambda: workspace.assert_publication_ready(internal_target),
            "incomplete publication",
        )

        reserved_source = root / "legacy/reserved"
        reserved_source.mkdir()
        (reserved_source / workspace.PUBLICATION_INCOMPLETE_MARKER).write_text(
            "reserved\n", "utf-8"
        )
        audit.expect(
            "workspace.reserved-marker.source-rejected",
            workspace.LayoutError,
            lambda: workspace.build_migration_plan(
                layout,
                [("legacy/reserved", "01_DATA/reserved")],
            ),
            "incomplete publication",
        )
        canonical_directories = tuple(
            root / layout.roots[root_id].canonical_path
            for root_id in sorted(layout.roots)
        )
        for canonical_directory in canonical_directories:
            canonical_directory.mkdir(exist_ok=True)
        audit.check(
            "workspace.canonical-roots.prepared-no-follow",
            all(
                stat.S_ISDIR(canonical_directory.lstat().st_mode)
                and not stat.S_ISLNK(canonical_directory.lstat().st_mode)
                for canonical_directory in canonical_directories
            ),
            paths=[str(path.relative_to(root)) for path in canonical_directories],
        )
        source_before = {
            "tree/a.txt": sha256_file(source_tree / "a.txt"),
            "tree/nested/b.json": sha256_file(source_tree / "nested/b.json"),
            "single": sha256_file(source_file),
        }
        plan = workspace.build_migration_plan(
            layout,
            [("legacy-data", "01_DATA/LEGACY")],
        )
        audit.check(
            "workspace.plan.sequence",
            plan.sequence == ("copy-verify-0", "dual-read-compare", "final-verify"),
            plan_sha256=plan.plan_sha256,
        )
        plan_file_sha = workspace.persist_immutable_migration_record(
            layout, "04_EXPERIMENTS/ADR-0158/plan.json", plan
        )
        audit.check(
            "workspace.record.idempotent",
            workspace.persist_immutable_migration_record(
                layout, "04_EXPERIMENTS/ADR-0158/plan.json", plan
            ) == plan_file_sha,
            file_sha256=plan_file_sha,
        )
        copied = workspace.execute_copy_verify_zero(layout, plan)
        dual = workspace.compare_dual_read(layout, plan, copied)
        empty_legacy = root / "empty-legacy"
        empty_canonical = root / "04_EMPTY"
        empty_legacy.mkdir()
        empty_canonical.mkdir()
        empty_bridge_layout = dataclasses.replace(
            layout,
            roots={
                **layout.roots,
                "empty": workspace.RootSpec(
                    "empty", "04_EMPTY", "empty-legacy", "bridge"
                ),
            },
        )
        audit.expect(
            "workspace.receipt.empty-bridge-root.rejected",
            workspace.LayoutError,
            lambda: workspace.verify_final_migration(
                empty_bridge_layout,
                plan,
                dual,
                already_canonical_root_ids=("backend", "frontend"),
            ),
            "whole legacy root",
        )
        audit.expect(
            "workspace.receipt.active-root-without-explicit-policy.rejected",
            workspace.LayoutError,
            lambda: workspace.verify_final_migration(layout, plan, dual),
            "explicit already-canonical policy",
        )
        final = workspace.verify_final_migration(
            layout,
            plan,
            dual,
            already_canonical_root_ids=("backend", "frontend"),
        )
        canonical_root_bindings = [
            binding.as_dict() for binding in final.canonical_root_bindings
        ]
        bindings_by_id = {
            row["root_id"]: row for row in canonical_root_bindings
        }
        expected_binding_ids = sorted(layout.roots)
        audit.check(
            "workspace.receipt.canonical-root-bindings.exact-coverage",
            len(canonical_root_bindings) == len(expected_binding_ids)
            and [row["root_id"] for row in canonical_root_bindings]
            == expected_binding_ids
            and {
                row["root_id"]: row["canonical_path"]
                for row in canonical_root_bindings
            }
            == {
                root_id: layout.roots[root_id].canonical_path
                for root_id in expected_binding_ids
            }
            and bindings_by_id["data"]["completion_kind"]
            == "migrated-legacy-root"
            and bindings_by_id["data"]["evidence_targets"]
            == ["01_DATA/LEGACY"]
            and all(
                bindings_by_id[root_id]["completion_kind"]
                == "already-canonical"
                and bindings_by_id[root_id]["evidence_targets"]
                == [layout.roots[root_id].canonical_path]
                for root_id in ("backend", "frontend")
            )
            and all(
                row["expected_kind"] == "directory"
                and row["root_state"] == layout.roots[row["root_id"]].state
                and row["completion_kind"]
                in {"migrated-legacy-root", "already-canonical"}
                and isinstance(row["evidence_targets"], list)
                and row["evidence_targets"]
                and isinstance(row["readiness_sha256"], str)
                and len(row["readiness_sha256"]) == 64
                for row in canonical_root_bindings
            ),
            bindings=canonical_root_bindings,
        )
        receipt_hashes = []
        final_receipt_file_sha = ""
        for name, receipt in (("copy", copied), ("dual", dual), ("final", final)):
            receipt_file_sha = workspace.persist_immutable_migration_record(
                layout, f"04_EXPERIMENTS/ADR-0158/{name}.json", receipt
            )
            receipt_hashes.append(receipt_file_sha)
            if name == "final":
                final_receipt_file_sha = receipt_file_sha
        audit.check(
            "workspace.receipt.chain",
            final.prior_receipt_sha256s
            == (copied.receipt_sha256, dual.receipt_sha256),
            final_receipt_sha256=final.receipt_sha256,
        )
        audit.check(
            "workspace.receipt.publish-strategy-propagated",
            tuple(row.publish_strategy for row in copied.items)
            == tuple(row.publish_strategy for row in dual.items)
            == tuple(row.publish_strategy for row in final.items)
            and all(row.publish_strategy for row in final.items),
            strategies=[row.publish_strategy for row in final.items],
        )
        audit.check(
            "workspace.source.preserved",
            source_file.exists()
            and source_tree.exists()
            and source_before["single"] == sha256_file(source_file)
            and source_before["tree/a.txt"] == sha256_file(source_tree / "a.txt")
            and source_before["tree/nested/b.json"]
            == sha256_file(source_tree / "nested/b.json"),
        )
        audit.check(
            "workspace.target.verified",
            sha256_file(root / "01_DATA/LEGACY/single.json")
            == source_before["single"]
            and sha256_file(root / "01_DATA/LEGACY/tree/nested/b.json")
            == source_before["tree/nested/b.json"],
        )
        activation_path = root / "activation.json"
        activation_path.write_text(
            json.dumps(
                {
                    "schema_version": workspace.ACTIVATION_RECEIPT_SCHEMA,
                    "status": "active",
                    "layout_version": "v2",
                    "workspace_manifest_sha256": layout.manifest_sha256,
                    "validation_receipt_path": "04_EXPERIMENTS/ADR-0158/final.json",
                    "validation_receipt_sha256": final_receipt_file_sha,
                    "validation_record_sha256": final.receipt_sha256,
                    "migration_plan_sha256": plan.plan_sha256,
                    "activation_id": "adr0158-live-drift",
                },
                sort_keys=True,
            )
            + "\n",
            "utf-8",
        )
        retirement = workspace.create_legacy_retirement_receipt(
            layout,
            activation_path,
            retirement_id="adr0158-retire-legacy-data",
        )
        retirement_relative = "04_EXPERIMENTS/ADR-0158/retirement.json"
        retirement_file_sha = workspace.persist_immutable_migration_record(
            layout,
            retirement_relative,
            retirement,
        )
        retirement_path = root / retirement_relative
        audit.check(
            "workspace.retirement.receipt.binds-all-final-sources",
            len(retirement.sources) == len(final.items)
            and [(row.target, row.source) for row in retirement.sources]
            == sorted((row.target, row.source) for row in final.items)
            and retirement.activation_receipt_sha256 == sha256_file(activation_path)
            and retirement.validation_receipt_sha256 == final_receipt_file_sha
            and retirement.as_dict()["source_deletion_performed"] is False
            and retirement.as_dict()["source_absence_authorized"] is True,
            receipt_sha256=retirement.receipt_sha256,
            file_sha256=retirement_file_sha,
        )
        bad_retirement = json.loads(json.dumps(retirement.as_dict()))
        bad_retirement["sources"][0]["target"] = "01_DATA/WRONG-EVIDENCE"
        bad_retirement_unsigned = dict(bad_retirement)
        bad_retirement_unsigned.pop("receipt_sha256")
        bad_retirement_unsigned["sources"] = sorted(
            bad_retirement_unsigned["sources"],
            key=lambda row: (
                row["target"],
                row["source"],
                canonical_bytes(row),
            ),
        )
        bad_retirement["receipt_sha256"] = canonical_sha256(
            bad_retirement_unsigned
        )
        bad_retirement_path = root / "retirement-bad-evidence.json"
        bad_retirement_path.write_text(
            json.dumps(
                bad_retirement,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            "utf-8",
        )

        duplicate_coordinate_retirement = json.loads(
            json.dumps(retirement.as_dict())
        )
        alternate_source_evidence = json.loads(
            json.dumps(duplicate_coordinate_retirement["sources"][0])
        )
        alternate_source_evidence["final_item_sha256"] = h(
            "alternate-final-item"
        )
        alternate_source_evidence["provenance_sha256"] = h(
            "alternate-source-provenance"
        )
        duplicate_coordinate_retirement["sources"].append(
            alternate_source_evidence
        )
        duplicate_coordinate_unsigned = dict(duplicate_coordinate_retirement)
        duplicate_coordinate_unsigned.pop("receipt_sha256")
        duplicate_coordinate_unsigned["sources"] = sorted(
            duplicate_coordinate_unsigned["sources"],
            key=lambda row: (
                row["target"],
                row["source"],
                canonical_bytes(row),
            ),
        )
        duplicate_coordinate_retirement["receipt_sha256"] = canonical_sha256(
            duplicate_coordinate_unsigned
        )
        duplicate_coordinate_path = root / "retirement-duplicate-coordinate.json"
        duplicate_coordinate_path.write_text(
            json.dumps(
                duplicate_coordinate_retirement,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            "utf-8",
        )

        tamper_receipt_root = root / "04_EXPERIMENTS/ADR-0158/tampered"
        tamper_receipt_root.mkdir()

        def write_tampered_activation(
            case: str,
            validation_receipt: dict[str, Any],
        ) -> Path:
            unsigned = dict(validation_receipt)
            unsigned.pop("receipt_sha256", None)
            validation_receipt["receipt_sha256"] = canonical_sha256(unsigned)
            validation_relative = (
                f"04_EXPERIMENTS/ADR-0158/tampered/final-{case}.json"
            )
            validation_path = root / validation_relative
            validation_path.write_text(
                json.dumps(
                    validation_receipt,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                "utf-8",
            )
            tampered_activation = root / f"activation-{case}.json"
            tampered_activation.write_text(
                json.dumps(
                    {
                        "schema_version": workspace.ACTIVATION_RECEIPT_SCHEMA,
                        "status": "active",
                        "layout_version": "v2",
                        "workspace_manifest_sha256": layout.manifest_sha256,
                        "validation_receipt_path": validation_relative,
                        "validation_receipt_sha256": sha256_file(validation_path),
                        "validation_record_sha256": validation_receipt[
                            "receipt_sha256"
                        ],
                        "migration_plan_sha256": plan.plan_sha256,
                        "activation_id": f"adr0158-{case}",
                    },
                    sort_keys=True,
                )
                + "\n",
                "utf-8",
            )
            return tampered_activation

        missing_binding_receipt = json.loads(json.dumps(final.as_dict()))
        missing_binding_receipt["canonical_root_bindings"].pop()
        missing_binding_activation = write_tampered_activation(
            "missing-root-binding", missing_binding_receipt
        )

        duplicate_binding_receipt = json.loads(json.dumps(final.as_dict()))
        duplicate_binding_receipt["canonical_root_bindings"][-1] = dict(
            duplicate_binding_receipt["canonical_root_bindings"][0]
        )
        duplicate_binding_activation = write_tampered_activation(
            "duplicate-root-binding", duplicate_binding_receipt
        )

        path_binding_receipt = json.loads(json.dumps(final.as_dict()))
        path_binding = path_binding_receipt["canonical_root_bindings"][0]
        path_binding["canonical_path"] = f'{path_binding["canonical_path"]}_TAMPERED'
        path_binding_unsigned = dict(path_binding)
        path_binding_unsigned.pop("readiness_sha256")
        path_binding["readiness_sha256"] = workspace._canonical_root_readiness_hash(
            layout.manifest_sha256,
            path_binding_unsigned,
        )
        path_binding_activation = write_tampered_activation(
            "root-binding-path", path_binding_receipt
        )

        readiness_binding_receipt = json.loads(json.dumps(final.as_dict()))
        readiness_binding = readiness_binding_receipt["canonical_root_bindings"][0]
        readiness_hash = readiness_binding["readiness_sha256"]
        readiness_binding["readiness_sha256"] = (
            ("0" if readiness_hash[0] != "0" else "1") + readiness_hash[1:]
        )
        readiness_binding_activation = write_tampered_activation(
            "root-binding-readiness", readiness_binding_receipt
        )

        evidence_binding_receipt = json.loads(json.dumps(final.as_dict()))
        evidence_binding = next(
            row
            for row in evidence_binding_receipt["canonical_root_bindings"]
            if row["root_id"] == "data"
        )
        evidence_binding["evidence_targets"] = ["01_DATA/WRONG-EVIDENCE"]
        evidence_binding_unsigned = dict(evidence_binding)
        evidence_binding_unsigned.pop("readiness_sha256")
        evidence_binding["readiness_sha256"] = (
            workspace._canonical_root_readiness_hash(
                layout.manifest_sha256,
                evidence_binding_unsigned,
            )
        )
        evidence_binding_activation = write_tampered_activation(
            "root-binding-evidence", evidence_binding_receipt
        )

        state_binding_receipt = json.loads(json.dumps(final.as_dict()))
        state_binding = next(
            row
            for row in state_binding_receipt["canonical_root_bindings"]
            if row["root_id"] == "data"
        )
        state_binding["root_state"] = "active"
        state_binding["completion_kind"] = "already-canonical"
        state_binding["evidence_targets"] = ["01_DATA"]
        state_binding_unsigned = dict(state_binding)
        state_binding_unsigned.pop("readiness_sha256")
        state_binding["readiness_sha256"] = (
            workspace._canonical_root_readiness_hash(
                layout.manifest_sha256,
                state_binding_unsigned,
            )
        )
        state_binding_activation = write_tampered_activation(
            "root-binding-state", state_binding_receipt
        )

        previous_layout = os.environ.get(workspace.LAYOUT_ENV)
        previous_activation = os.environ.get(workspace.ACTIVATION_RECEIPT_ENV)
        previous_retirement = os.environ.get(workspace.RETIREMENT_RECEIPT_ENV)
        try:
            os.environ.pop(workspace.LAYOUT_ENV, None)
            os.environ.pop(workspace.ACTIVATION_RECEIPT_ENV, None)
            os.environ.pop(workspace.RETIREMENT_RECEIPT_ENV, None)
            bridge_default_v2 = dataclasses.replace(
                layout, default_layout_version="v2"
            )
            audit.expect(
                "workspace.bridge-default-v2.without-receipt.rejected",
                workspace.LayoutError,
                lambda: bridge_default_v2.path("data"),
                workspace.ACTIVATION_RECEIPT_ENV,
            )
            os.environ[workspace.LAYOUT_ENV] = "v1"
            v2_only_layout = dataclasses.replace(
                layout,
                mode="v2-only",
                default_layout_version="v2",
            )
            audit.expect(
                "workspace.v2-only.explicit-v1.rejected",
                workspace.LayoutError,
                lambda: v2_only_layout.path("data"),
                "cannot resolve the v1 layout",
            )
            audit.expect(
                "workspace.runtime.explicit-layout-version.rejected",
                workspace.LayoutError,
                lambda: layout.path("data", layout_version="v2"),
                "inspection-only",
            )
            os.environ.pop(workspace.LAYOUT_ENV, None)
            audit.expect(
                "workspace.canonical-path.without-receipt.rejected",
                workspace.LayoutError,
                lambda: layout.canonical_path("data"),
                workspace.ACTIVATION_RECEIPT_ENV,
            )
            audit.check(
                "workspace.inspection-path.explicit-v2.accepted",
                layout.inspection_path("data", layout_version="v2")
                == root / "01_DATA",
            )

            os.environ[workspace.LAYOUT_ENV] = "v2"
            os.environ[workspace.ACTIVATION_RECEIPT_ENV] = str(activation_path)
            audit.check(
                "workspace.v2-path.live-receipt.accepted",
                layout.path("data") == root / "01_DATA",
            )
            audit.check(
                "workspace.v2-canonical-path.live-receipt.accepted",
                layout.canonical_path("data") == root / "01_DATA",
            )

            frontend_root = root / "03_FRONTEND"
            frontend_root.rmdir()
            try:
                audit.expect(
                    "workspace.v2-path.canonical-root-missing.rejected",
                    workspace.LayoutError,
                    lambda: layout.path("data"),
                    "does not exist",
                )
            finally:
                frontend_root.mkdir()

            canonical_symlink_target = crash_parent / "canonical-symlink-target"
            canonical_symlink_target.mkdir()
            frontend_root.rmdir()
            frontend_root.symlink_to(
                canonical_symlink_target,
                target_is_directory=True,
            )
            try:
                audit.expect(
                    "workspace.v2-path.canonical-root-symlink.rejected",
                    workspace.LayoutError,
                    lambda: layout.path("data"),
                    "symlink",
                )
            finally:
                frontend_root.unlink()
                frontend_root.mkdir()

            canonical_sidecar = workspace._publication_sidecar(frontend_root)
            canonical_sidecar.write_text("incomplete\n", "utf-8")
            try:
                audit.expect(
                    "workspace.v2-path.canonical-root-sidecar.rejected",
                    workspace.LayoutError,
                    lambda: layout.path("data"),
                    "incomplete publication",
                )
            finally:
                canonical_sidecar.unlink()

            canonical_internal = (
                frontend_root / workspace.PUBLICATION_INCOMPLETE_MARKER
            )
            canonical_internal.write_text("incomplete\n", "utf-8")
            try:
                audit.expect(
                    "workspace.v2-path.canonical-root-internal-marker.rejected",
                    workspace.LayoutError,
                    lambda: layout.path("data"),
                    "incomplete publication",
                )
            finally:
                canonical_internal.unlink()

            canonical_fifo = frontend_root / "blocked.fifo"
            os.mkfifo(canonical_fifo)
            try:
                audit.expect(
                    "workspace.v2-path.canonical-root-fifo.rejected",
                    workspace.LayoutError,
                    lambda: layout.path("data"),
                    "special file",
                )
            finally:
                canonical_fifo.unlink()

            target_ancestor = root / "01_DATA/LEGACY"
            ancestor_internal = (
                target_ancestor / workspace.PUBLICATION_INCOMPLETE_MARKER
            )
            ancestor_internal.write_text("incomplete\n", "utf-8")
            try:
                audit.expect(
                    "workspace.v2-path.target-ancestor-internal-marker.rejected",
                    workspace.LayoutError,
                    lambda: layout.path("data"),
                    "incomplete publication",
                )
            finally:
                ancestor_internal.unlink()
            ancestor_sidecar = workspace._publication_sidecar(target_ancestor)
            ancestor_sidecar.write_text("incomplete\n", "utf-8")
            try:
                audit.expect(
                    "workspace.v2-path.target-ancestor-sidecar.rejected",
                    workspace.LayoutError,
                    lambda: layout.path("data"),
                    "incomplete publication",
                )
            finally:
                ancestor_sidecar.unlink()

            for name, tampered_activation, message in (
                (
                    "missing",
                    missing_binding_activation,
                    "exactly cover workspace roots",
                ),
                (
                    "duplicate",
                    duplicate_binding_activation,
                    "canonical_root_binding_order",
                ),
                (
                    "path",
                    path_binding_activation,
                    "does not match manifest",
                ),
                (
                    "readiness-hash",
                    readiness_binding_activation,
                    "canonical_root_bindings[0]",
                ),
                (
                    "evidence",
                    evidence_binding_activation,
                    "invalid migration evidence",
                ),
                (
                    "state",
                    state_binding_activation,
                    "does not match manifest",
                ),
            ):
                os.environ[workspace.ACTIVATION_RECEIPT_ENV] = str(
                    tampered_activation
                )
                audit.expect(
                    f"workspace.receipt.canonical-root-bindings.{name}.rejected",
                    workspace.LayoutError,
                    lambda: layout.path("data"),
                    message,
                )
            os.environ[workspace.ACTIVATION_RECEIPT_ENV] = str(activation_path)

            os.environ[workspace.RETIREMENT_RECEIPT_ENV] = str(
                bad_retirement_path
            )
            audit.expect(
                "workspace.retirement.wrong-evidence.rejected",
                workspace.LayoutError,
                lambda: layout.path("data"),
                "exact activation and final migration evidence: sources",
            )
            os.environ[workspace.RETIREMENT_RECEIPT_ENV] = str(
                duplicate_coordinate_path
            )
            audit.expect(
                "workspace.retirement.duplicate-coordinate-evidence.rejected",
                workspace.LayoutError,
                lambda: layout.path("data"),
                "exact activation and final migration evidence: sources",
            )
            os.environ.pop(workspace.RETIREMENT_RECEIPT_ENV, None)

            source_file.write_text("source-drift\n", "utf-8")
            audit.expect(
                "workspace.v2-path.source-drift.rejected",
                workspace.LayoutError,
                lambda: layout.path("data"),
                "source no longer matches receipt",
            )
            source_file.write_text('{"single":true}\n', "utf-8")
            audit.check(
                "workspace.v2-path.source-restore.accepted",
                layout.path("data") == root / "01_DATA",
            )
            target_file = root / "01_DATA/LEGACY/single.json"
            target_file.write_text("target-drift\n", "utf-8")
            audit.expect(
                "workspace.v2-path.target-drift.rejected",
                workspace.LayoutError,
                lambda: layout.path("data"),
                "target no longer matches receipt",
            )
            target_file.write_text('{"single":true}\n', "utf-8")
            audit.check(
                "workspace.v2-path.target-restore.accepted",
                layout.path("data") == root / "01_DATA",
            )

            retired_source_hold = root / "retired-source-hold"
            legacy_root.rename(retired_source_hold)
            try:
                audit.expect(
                    "workspace.retirement.source-missing-without-receipt.rejected",
                    workspace.LayoutError,
                    lambda: layout.path("data"),
                    "source does not exist",
                )
                os.environ[workspace.RETIREMENT_RECEIPT_ENV] = str(
                    retirement_path
                )
                restart_layout = dataclasses.replace(layout)
                audit.check(
                    "workspace.retirement.source-absent-restart.accepted",
                    restart_layout.path("data") == root / "01_DATA"
                    and not legacy_root.exists(),
                )
                target_file.write_text("retired-target-drift\n", "utf-8")
                audit.expect(
                    "workspace.retirement.target-drift-still-rejected",
                    workspace.LayoutError,
                    lambda: restart_layout.path("data"),
                    "target no longer matches receipt",
                )
                target_file.write_text('{"single":true}\n', "utf-8")
                audit.check(
                    "workspace.retirement.target-restore.accepted",
                    restart_layout.path("data") == root / "01_DATA",
                )
            finally:
                if retired_source_hold.exists() and not legacy_root.exists():
                    retired_source_hold.rename(legacy_root)
        finally:
            if previous_layout is None:
                os.environ.pop(workspace.LAYOUT_ENV, None)
            else:
                os.environ[workspace.LAYOUT_ENV] = previous_layout
            if previous_activation is None:
                os.environ.pop(workspace.ACTIVATION_RECEIPT_ENV, None)
            else:
                os.environ[workspace.ACTIVATION_RECEIPT_ENV] = previous_activation
            if previous_retirement is None:
                os.environ.pop(workspace.RETIREMENT_RECEIPT_ENV, None)
            else:
                os.environ[workspace.RETIREMENT_RECEIPT_ENV] = previous_retirement

        top_level_audit_root = root / "top-level-audit-fixture"
        top_level_canonical = top_level_audit_root / "01_DATA"
        top_level_canonical.mkdir(parents=True)
        top_level_layout = workspace.WorkspaceLayout(
            root=top_level_audit_root,
            mode="v2-only",
            default_layout_version="v2",
            canonical_root_pattern=r"^[0-9]{2}_[A-Z][A-Z0-9_]*$",
            roots={
                "data": workspace.RootSpec(
                    "data", "01_DATA", None, "active"
                )
            },
            legacy_top_level_directories=(),
            root_file_policy={},
            invariants=("copy-only",),
            manifest_sha256=h("top-level-audit-workspace-manifest"),
        )
        clean_top_level_report = workspace.audit_top_level(top_level_layout)
        audit.check(
            "workspace.audit-top-level.clean-ready",
            clean_top_level_report["activation_ready"]
            and clean_top_level_report["retirement_ready"]
            and clean_top_level_report["target_ready"],
            report=clean_top_level_report,
        )
        retained_legacy = top_level_audit_root / "legacy-hold"
        retained_legacy.mkdir()
        try:
            retained_layout = dataclasses.replace(
                top_level_layout,
                legacy_top_level_directories=("legacy-hold",),
            )
            retained_report = workspace.audit_top_level(retained_layout)
            audit.check(
                "workspace.audit-top-level.activation-retirement-separated",
                retained_report["activation_ready"]
                and not retained_report["retirement_ready"]
                and not retained_report["target_ready"]
                and retained_report["activation_blockers"] == []
                and retained_report["retirement_blockers"]
                == ["legacy roots remain"],
                report=retained_report,
            )
        finally:
            retained_legacy.rmdir()
        top_level_symlink_target = root / "top-level-audit-symlink-target"
        top_level_symlink_target.mkdir()
        top_level_canonical.rmdir()
        top_level_canonical.symlink_to(
            top_level_symlink_target,
            target_is_directory=True,
        )
        try:
            symlink_report = workspace.audit_top_level(top_level_layout)
            audit.check(
                "workspace.audit-top-level.canonical-symlink.not-ready",
                not symlink_report["target_ready"]
                and "01_DATA:symlink"
                in symlink_report["unsafe_top_level_entries"],
                report=symlink_report,
            )
        finally:
            top_level_canonical.unlink()
            top_level_canonical.mkdir()
        hidden_marker = top_level_audit_root / (
            f".orphan{workspace.PUBLICATION_INCOMPLETE_MARKER}"
        )
        hidden_marker.write_text("incomplete\n", "utf-8")
        try:
            hidden_marker_report = workspace.audit_top_level(top_level_layout)
            audit.check(
                "workspace.audit-top-level.hidden-marker.not-ready",
                not hidden_marker_report["target_ready"]
                and f"{hidden_marker.name}:publication-marker"
                in hidden_marker_report["unsafe_top_level_entries"],
                report=hidden_marker_report,
            )
        finally:
            hidden_marker.unlink()

        outside = root / "outside.txt"
        outside.write_text("outside\n", "utf-8")
        (root / "legacy/link").symlink_to(outside)
        audit.expect(
            "workspace.symlink.rejected",
            workspace.LayoutError,
            lambda: workspace.build_migration_plan(
                layout, [("legacy/link", "01_DATA/PACKAGES/link")]
            ),
            "symlink",
        )
        outside_directory = root / "outside-directory"
        outside_directory.mkdir()
        (root / "target-link").symlink_to(
            outside_directory, target_is_directory=True
        )
        audit.expect(
            "workspace.target-ancestor-symlink.rejected",
            workspace.LayoutError,
            lambda: workspace.build_migration_plan(
                layout,
                [("legacy-data/single.json", "target-link/copied.json")],
            ),
            "symlink",
        )
        frontend_root.rmdir()
        frontend_root.symlink_to(outside_directory, target_is_directory=True)
        try:
            audit.expect(
                "workspace.public-leaf-symlink.rejected",
                workspace.LayoutError,
                lambda: layout.inspection_path("frontend", layout_version="v2"),
                "symlink",
            )
        finally:
            frontend_root.unlink()
            frontend_root.mkdir()
        overlap = root / "legacy/overlap"
        overlap.mkdir()
        (overlap / "member.txt").write_text("member\n", "utf-8")
        audit.expect(
            "workspace.overlap.rejected",
            workspace.LayoutError,
            lambda: workspace.build_migration_plan(
                layout,
                [
                    ("legacy/overlap", "01_DATA/A"),
                    ("legacy/overlap/member.txt", "01_DATA/B"),
                ],
            ),
            "overlap",
        )
        return {
            "plan_sha256": plan.plan_sha256,
            "plan_file_sha256": plan_file_sha,
            "receipt_file_sha256s": receipt_hashes,
            "final_receipt_sha256": final.receipt_sha256,
            "retirement_receipt_sha256": retirement.receipt_sha256,
            "retirement_receipt_file_sha256": retirement_file_sha,
            "fallback_publish_strategies": fallback_strategies,
            "item_count": len(plan.items),
            "source_deleted": False,
        }


def _write_package(
    catalog,
    root: Path,
    *,
    package_id: str,
    dataset_id: str,
    version_id: str,
    representation: str,
    restricted: bool,
    logical_id: str,
    content: str,
    document_id: str | None = None,
):
    package_root = root / package_id
    package_root.mkdir(parents=True)
    artifact = package_root / "artifact.json"
    artifact.write_text(content, "utf-8")
    artifact_row: dict[str, Any] = {
        "logical_id": logical_id,
        "role": "structure",
        "path": "artifact.json",
        "sha256": sha256_file(artifact),
        "media_type": "application/json",
    }
    if document_id is not None:
        artifact_row["document_id"] = document_id
    blob: dict[str, Any] = {
        "schema_version": "dataset-package-v2",
        "package_id": package_id,
        "dataset_id": dataset_id,
        "version_id": version_id,
        "variant_id": representation,
        "generation_id": f"generation-{package_id}",
        "source_origin": "restricted_internal" if restricted else "public_external",
        "security_class": "restricted" if restricted else "public",
        "representation": representation,
        "authority": "authoritative",
        "export_policy": {"allowed": not restricted},
        "build": {
            "build_id": f"build-{package_id}",
            "execution_site": "genos" if restricted else "outside",
            "code_revision": "fixture-revision",
            "compiler_profile": "fixture-profile",
            "capabilities": ["structure"],
        },
        "artifacts": [artifact_row],
    }
    parsed = catalog.package_from_mapping(blob, manifest_path=package_root / "package.json")
    blob["manifest_sha256"] = parsed.manifest_sha256
    manifest = package_root / "package.json"
    manifest.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return catalog.load_package(manifest), manifest


def _rewrite_materialization_receipt(
    catalog,
    path: Path,
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    receipt = json.loads(path.read_text("utf-8"))
    mutation(receipt)
    core = dict(receipt)
    core.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = catalog._digest(core)
    path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n",
        "utf-8",
    )


def _rehash_source_set_lock(catalog, lock):
    """Keep a malicious lock internally consistent so package checks are tested."""

    source_identity = {
        "source_set_id": lock.source_set_id,
        "generation_id": lock.generation_id,
        "conflict_policy": lock.conflict_policy,
        "cross_dataset_relations": lock.cross_dataset_relations,
        "members": [member.receipt() for member in lock.members],
        "artifacts": [
            {
                "qualified_id": artifact.qualified_id,
                "package_id": artifact.package_id,
                "dataset_id": artifact.dataset_id,
                "version_id": artifact.version_id,
                "build_id": artifact.build_id,
                "manifest_sha256": artifact.manifest_sha256,
                "sha256": artifact.sha256,
                "contributors": list(artifact.contributors),
            }
            for artifact in lock.artifacts
        ],
    }
    with_source_identity = dataclasses.replace(
        lock,
        source_set_sha256=catalog._digest(source_identity),
    )
    lock_core = with_source_identity.receipt()
    lock_core.pop("lock_sha256", None)
    return dataclasses.replace(
        with_source_identity,
        lock_sha256=catalog._digest(lock_core),
    )


def catalog_audit(catalog, audit: Audit) -> dict[str, Any]:
    # The ambient Windows desktop environment can point TMPDIR at drvfs,
    # which intentionally does not implement POSIX FIFOs.  This catalog audit
    # includes a special-file rejection fixture, so keep its otherwise
    # isolated temporary tree on WSL's Linux filesystem.
    with tempfile.TemporaryDirectory(
        prefix="adr0158-catalog-", dir="/tmp"
    ) as raw_root:
        root = Path(raw_root)

        def exact_mode(path: Path) -> int:
            return stat.S_IMODE(path.lstat().st_mode)

        def is_regular_no_follow(path: Path) -> bool:
            try:
                return stat.S_ISREG(path.lstat().st_mode)
            except OSError:
                return False

        def exact_mode_tree(path: Path) -> dict[str, dict[str, Any]]:
            """Record a no-follow tree shape and modes for publication comparison."""

            rows: dict[str, dict[str, Any]] = {}
            pending = [(path, ".")]
            while pending:
                current, relative = pending.pop()
                info = current.lstat()
                if stat.S_ISDIR(info.st_mode):
                    kind = "directory"
                elif stat.S_ISREG(info.st_mode):
                    kind = "file"
                elif stat.S_ISLNK(info.st_mode):
                    kind = "symlink"
                else:
                    kind = "special"
                rows[relative] = {
                    "kind": kind,
                    "mode": stat.S_IMODE(info.st_mode),
                }
                if kind == "directory":
                    with os.scandir(current) as entries:
                        children = sorted(entries, key=lambda entry: entry.name)
                    for entry in reversed(children):
                        child_relative = (
                            entry.name
                            if relative == "."
                            else f"{relative}/{entry.name}"
                        )
                        pending.append((Path(entry.path), child_relative))
            return rows

        def rewrite_restricted_receipt(
            path: Path,
            mutation: Callable[[dict[str, Any]], None],
        ) -> None:
            original_mode = exact_mode(path)
            path.chmod(0o600, follow_symlinks=False)
            try:
                _rewrite_materialization_receipt(catalog, path, mutation)
            finally:
                path.chmod(original_mode, follow_symlinks=False)

        (root / "legacy/raw").mkdir(parents=True)
        (root / "legacy/structure/doc-a").mkdir(parents=True)
        (root / "legacy/raw/source.txt").write_text("source\n", "utf-8")
        (root / "legacy/structure/doc-a/meta.json").write_text(
            '{"doc":"a"}\n', "utf-8"
        )
        result_path = root / "legacy/structure/doc-a/result.json"
        result_original = '{"units":[1]}\n'
        result_path.write_text(result_original, "utf-8")
        contract = {
            "kind": "legal-source",
            "format_family": "structured-json",
            "version_role": "current",
            "artifact_roles": ["primary", "structure"],
        }
        contract_core = {
            "schema_version": "dataset-overlay-contract-v1",
            "items": [{"logical_id": "legal/doc-a", "contract": contract}],
        }
        active: dict[str, Any] = {
            "schema_version": "active-dataset-overlay-v1",
            "overlay_id": "external-mock-v1",
            "representation": "mock",
            "contract_sha256": canonical_sha256(contract_core),
            "items": [
                {
                    "logical_id": "legal/doc-a",
                    "contract": contract,
                    "representation": "mock",
                    "doc_id": "doc-a",
                    "files": [
                        {"path": "legacy/raw/source.txt", "role": "primary"},
                        {
                            "path": "legacy/structure/doc-a/meta.json",
                            "role": "structure",
                        },
                        {
                            "path": "legacy/structure/doc-a/result.json",
                            "role": "structure",
                        },
                    ],
                }
            ],
        }
        active_path = root / "ACTIVE_DATASET.json"
        active_path.write_text(json.dumps(active, ensure_ascii=False, indent=2) + "\n", "utf-8")
        external = catalog.package_from_legacy_overlay(
            active_path,
            root=root,
            package_id="legacy-external",
            dataset_id="legal-data",
            version_id="external-v1",
            export_allowed=True,
        )
        audit.check(
            "catalog.legacy.expanded-files",
            len(external.artifacts) == 3
            and len({item.logical_key for item in external.artifacts}) == 3
            and {item.document_id for item in external.artifacts} == {"doc-a"},
            manifest_sha256=external.manifest_sha256,
        )
        audit.check(
            "catalog.legacy.meta-result-bound",
            {Path(item.path).name for item in external.artifacts if item.role == "structure"}
            == {"meta.json", "result.json"},
        )

        def invalid_legacy_overlay(
            name: str,
            mutation: Callable[[dict[str, Any]], None],
        ) -> Path:
            candidate = json.loads(json.dumps(active))
            mutation(candidate)
            candidate["contract_sha256"] = _legacy_contract_sha256(candidate)
            path = root / f"ACTIVE_DATASET_{name}.json"
            path.write_text(
                json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
                "utf-8",
            )
            return path

        def remove_primary(candidate: dict[str, Any]) -> None:
            item = candidate["items"][0]
            item["contract"]["artifact_roles"] = ["structure"]
            item["files"] = [row for row in item["files"] if row["role"] != "primary"]

        def remove_structure(candidate: dict[str, Any]) -> None:
            item = candidate["items"][0]
            item["contract"]["artifact_roles"] = ["primary"]
            item["files"] = [row for row in item["files"] if row["role"] != "structure"]

        without_primary = invalid_legacy_overlay("without-primary", remove_primary)
        audit.expect(
            "catalog.legacy.primary.valid-rehash-still-rejected",
            catalog.DatasetContractError,
            lambda: catalog.package_from_legacy_overlay(
                without_primary, root=root
            ),
            "must include primary and structure",
        )
        without_structure = invalid_legacy_overlay(
            "without-structure", remove_structure
        )
        audit.expect(
            "catalog.legacy.structure.valid-rehash-still-rejected",
            catalog.DatasetContractError,
            lambda: catalog.package_from_legacy_overlay(
                without_structure, root=root
            ),
            "must include primary and structure",
        )

        def remove_document_id(candidate: dict[str, Any]) -> None:
            candidate["items"][0].pop("doc_id")

        without_doc_id = invalid_legacy_overlay("without-doc-id", remove_document_id)
        audit.expect(
            "catalog.legacy.doc-id.rejected",
            catalog.DatasetContractError,
            lambda: catalog.package_from_legacy_overlay(
                without_doc_id, root=root
            ),
            "doc_id",
        )
        result_path.write_text('{"units":[2]}\n', "utf-8")
        changed = catalog.package_from_legacy_overlay(
            active_path,
            root=root,
            package_id="legacy-external",
            dataset_id="legal-data",
            version_id="external-v1",
            export_allowed=True,
        )
        audit.check(
            "catalog.legacy.result-affects-identity",
            changed.manifest_sha256 != external.manifest_sha256,
            before=external.manifest_sha256,
            after=changed.manifest_sha256,
        )
        result_path.write_text(result_original, "utf-8")
        bad_active = dict(active)
        bad_active["contract_sha256"] = "0" * 64
        active_path.write_text(json.dumps(bad_active, ensure_ascii=False) + "\n", "utf-8")
        audit.expect(
            "catalog.legacy.contract-tamper.rejected",
            catalog.DatasetContractError,
            lambda: catalog.package_from_legacy_overlay(active_path, root=root),
            "contract_sha256 mismatch",
        )
        active_path.write_text(json.dumps(active, ensure_ascii=False, indent=2) + "\n", "utf-8")

        internal, _ = _write_package(
            catalog,
            root,
            package_id="internal-rules",
            dataset_id="legal-data",
            version_id="internal-v1",
            representation="real",
            restricted=True,
            logical_id="internal/rule-a",
            content='{"rule":"private"}\n',
        )
        source_set = {
            "schema_version": "source-set-v1",
            "source_set_id": "combined-source",
            "generation_id": "combined-generation",
            "conflict_policy": "error",
            "cross_dataset_relations": False,
            "members": [
                {"package_id": external.package_id, "priority": 10},
                {"package_id": internal.package_id, "priority": 20},
            ],
        }
        view = catalog.compose_source_set(source_set, [external, internal])
        lock = view.lock()
        audit.check(
            "catalog.sourceset.lock",
            lock.source_set_sha256 == view.source_set_sha256
            and lock == catalog.lock_source_set(view)
            and len(lock.members) == 2,
            source_set_sha256=view.source_set_sha256,
            lock_sha256=lock.lock_sha256,
        )
        destination = root / "runtime/combined"
        materialized = catalog.materialize_source_set(
            view,
            destination,
            lock=lock,
            for_export=False,
            trusted_root=root,
        )
        audit.check(
            "catalog.sourceset.materialized",
            materialized.path == destination.resolve()
            and materialized.receipt["lock"] == lock.receipt()
            and not materialized.receipt["export_allowed"]
            and materialized.receipt["publish_strategy"]
            in {"renameat2", "reserved-directory"},
            receipt_sha256=materialized.receipt_sha256,
        )
        materialized_artifact_paths = [
            destination / str(row["materialized_path"])
            for row in materialized.receipt["artifacts"]
        ]
        audit.check(
            "catalog.restricted.materialization.exact-modes",
            exact_mode(destination) == 0o700
            and exact_mode(destination / "ARTIFACTS") == 0o500
            and exact_mode(destination / "receipt.json") == 0o400
            and all(exact_mode(path) == 0o400 for path in materialized_artifact_paths),
            root_mode=oct(exact_mode(destination)),
            artifacts_mode=oct(exact_mode(destination / "ARTIFACTS")),
            receipt_mode=oct(exact_mode(destination / "receipt.json")),
            artifact_modes=[oct(exact_mode(path)) for path in materialized_artifact_paths],
        )
        verified_open = catalog.open_materialized_source_set(
            destination,
            lock,
            trusted_root=root,
        )
        audit.check(
            "catalog.materialization.verified-open",
            verified_open.receipt_sha256 == materialized.receipt_sha256
            and all(
                materialized.verified_artifact_path(artifact.qualified_id).is_file()
                for artifact in lock.artifacts
            ),
        )
        document_artifact = next(
            artifact for artifact in lock.artifacts if artifact.document_id is not None
        )
        document_provenance = materialized.verified_artifact_provenance(
            document_artifact.qualified_id
        )
        audit.check(
            "catalog.materialization.verified-provenance-complete",
            document_provenance
            == {
                "qualified_id": document_artifact.qualified_id,
                "package_id": document_artifact.package_id,
                "dataset_id": document_artifact.dataset_id,
                "version_id": document_artifact.version_id,
                "build_id": document_artifact.build_id,
                "manifest_sha256": document_artifact.manifest_sha256,
                "logical_id": document_artifact.logical_id,
                "role": document_artifact.role,
                "source_path": document_artifact.path,
                "sha256": document_artifact.sha256,
                "contributors": list(document_artifact.contributors),
                "document_id": document_artifact.document_id,
            },
            provenance=document_provenance,
        )
        permission_destination = root / "runtime/permission-drift"
        permission_materialized = catalog.materialize_source_set(
            view,
            permission_destination,
            lock=lock,
            trusted_root=root,
        )
        permission_artifact = permission_materialized.verified_artifact_path(
            lock.artifacts[0].qualified_id
        )
        permission_cases = (
            ("root", permission_destination, 0o755),
            ("artifacts-directory", permission_destination / "ARTIFACTS", 0o700),
            ("receipt", permission_destination / "receipt.json", 0o644),
            ("artifact", permission_artifact, 0o644),
        )
        for label, path, unsafe_mode in permission_cases:
            safe_mode = exact_mode(path)
            path.chmod(unsafe_mode, follow_symlinks=False)
            try:
                audit.expect(
                    f"catalog.restricted.permissions.{label}.tamper-rejected",
                    catalog.DatasetContractError,
                    lambda: catalog.open_materialized_source_set(
                        permission_destination,
                        lock,
                        trusted_root=root,
                    ),
                    "unsafe permissions",
                )
                if label == "artifact":
                    audit.expect(
                        "catalog.restricted.permissions.artifact.lookup-rejected",
                        catalog.DatasetContractError,
                        lambda: permission_materialized.verified_artifact_path(
                            lock.artifacts[0].qualified_id
                        ),
                        "unsafe permissions",
                    )
            finally:
                path.chmod(safe_mode, follow_symlinks=False)
        audit.check(
            "catalog.restricted.permissions.restore-verified",
            catalog.open_materialized_source_set(
                permission_destination,
                lock,
                trusted_root=root,
            ).receipt_sha256
            == permission_materialized.receipt_sha256,
        )
        catalog_fallback_strategies: dict[str, str] = {}
        for error_number in (errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP):
            error_name = errno.errorcode[error_number].lower()
            fallback_destination = root / f"runtime/fallback-{error_name}"
            fallback_materialized = _with_renameat2_errno(
                catalog,
                error_number,
                lambda destination=fallback_destination: catalog.materialize_source_set(
                    view,
                    destination,
                    lock=lock,
                    trusted_root=root,
                ),
            )
            strategy = str(fallback_materialized.receipt["publish_strategy"])
            catalog_fallback_strategies[error_name] = strategy
            reopened_fallback = catalog.open_materialized_source_set(
                fallback_destination,
                lock,
                trusted_root=root,
            )
            fallback_artifact_paths = [
                fallback_destination / str(row["materialized_path"])
                for row in fallback_materialized.receipt["artifacts"]
            ]
            audit.check(
                f"catalog.fallback.{error_name}.reserved-directory",
                strategy == "reserved-directory"
                and reopened_fallback.receipt_sha256
                == fallback_materialized.receipt_sha256
                and not catalog._materialization_markers(fallback_destination)
                and exact_mode(fallback_destination) == 0o700
                and exact_mode(fallback_destination / "ARTIFACTS") == 0o500
                and exact_mode(fallback_destination / "receipt.json") == 0o400
                and all(
                    exact_mode(path) == 0o400 for path in fallback_artifact_paths
                ),
                publish_strategy=strategy,
                root_mode=oct(exact_mode(fallback_destination)),
                artifacts_mode=oct(
                    exact_mode(fallback_destination / "ARTIFACTS")
                ),
                receipt_mode=oct(exact_mode(fallback_destination / "receipt.json")),
                artifact_modes=[
                    oct(exact_mode(path)) for path in fallback_artifact_paths
                ],
            )

        unrestricted_source_set = {
            "schema_version": "source-set-v1",
            "source_set_id": "unrestricted-fallback-source",
            "generation_id": "unrestricted-fallback-generation",
            "conflict_policy": "error",
            "cross_dataset_relations": False,
            "members": [
                {"package_id": external.package_id, "priority": 10},
            ],
        }
        unrestricted_view = catalog.compose_source_set(
            unrestricted_source_set,
            [external],
        )
        unrestricted_lock = unrestricted_view.lock()
        unrestricted_destination = root / "runtime/fallback-unrestricted"
        unrestricted_observation: dict[str, Any] = {"calls": 0}

        def observe_unrestricted_directory_move(original):
            def injected(source, target):
                source_path = Path(source)
                target_path = Path(target)
                unrestricted_observation["calls"] += 1
                unrestricted_observation["staging_modes"] = exact_mode_tree(
                    source_path.parent
                )
                unrestricted_observation["source_mode"] = exact_mode(source_path)
                source_info = source_path.lstat()
                result = original(source, target)
                target_info = target_path.lstat()
                unrestricted_observation["target_mode"] = exact_mode(target_path)
                unrestricted_observation["identity_preserved"] = (
                    source_info.st_dev,
                    source_info.st_ino,
                ) == (
                    target_info.st_dev,
                    target_info.st_ino,
                )
                return result

            return injected

        unrestricted_materialized = _with_renameat2_errno(
            catalog,
            errno.EINVAL,
            lambda: _with_module_override(
                catalog,
                "_rename_reserved_directory_preserving_mode",
                observe_unrestricted_directory_move,
                lambda: catalog.materialize_source_set(
                    unrestricted_view,
                    unrestricted_destination,
                    lock=unrestricted_lock,
                    trusted_root=root,
                ),
            ),
        )
        unrestricted_reopened = catalog.open_materialized_source_set(
            unrestricted_destination,
            unrestricted_lock,
            trusted_root=root,
        )
        unrestricted_final_modes = exact_mode_tree(unrestricted_destination)
        audit.check(
            "catalog.fallback.unrestricted.final-modes-preserved",
            unrestricted_lock.export_allowed
            and unrestricted_materialized.receipt["publish_strategy"]
            == "reserved-directory"
            and unrestricted_reopened.receipt_sha256
            == unrestricted_materialized.receipt_sha256
            and unrestricted_observation["calls"] == 1
            and unrestricted_observation["identity_preserved"]
            and unrestricted_observation["source_mode"]
            == unrestricted_observation["target_mode"]
            == unrestricted_final_modes["ARTIFACTS"]["mode"]
            and unrestricted_observation["staging_modes"]
            == unrestricted_final_modes
            and not catalog._materialization_markers(unrestricted_destination),
            observed=unrestricted_observation,
            final_modes=unrestricted_final_modes,
        )

        def check_failed_reserved_publication(
            label: str,
            failed_destination: Path,
            *,
            artifacts_published: bool,
        ) -> None:
            sidecar = catalog._publication_sidecar(failed_destination)
            internal_marker = (
                failed_destination / catalog.PUBLICATION_INCOMPLETE_MARKER
            )
            inspection = catalog.inspect_materialization(
                failed_destination,
                lock,
                trusted_root=root,
            )
            marker_paths = set(inspection.marker_paths)
            audit.check(
                f"{label}.both-markers-retained",
                is_regular_no_follow(sidecar)
                and is_regular_no_follow(internal_marker)
                and not inspection.ready
                and sidecar in marker_paths
                and internal_marker in marker_paths,
                inspection=inspection.receipt(),
            )
            audit.check(
                f"{label}.private-staging-cleaned",
                not any(
                    failed_destination.parent.glob(
                        f".{failed_destination.name}.staging-*"
                    )
                ),
            )
            artifacts_path = failed_destination / "ARTIFACTS"
            receipt_path = failed_destination / "receipt.json"
            artifact_state_matches = (
                artifacts_path.is_dir()
                and not artifacts_path.is_symlink()
                and exact_mode(artifacts_path) == 0o500
                if artifacts_published
                else not os.path.lexists(artifacts_path)
            )
            audit.check(
                f"{label}.partial-shape-fail-closed",
                artifact_state_matches and not os.path.lexists(receipt_path),
                artifacts_published=artifacts_published,
                artifacts_state=_entry_state(artifacts_path),
                receipt_state=_entry_state(receipt_path),
            )
            audit.expect(
                f"{label}.readiness-rejected",
                catalog.DatasetContractError,
                lambda: catalog.open_materialized_source_set(
                    failed_destination,
                    lock,
                    trusted_root=root,
                ),
                "incomplete publication marker",
            )

        before_rename_destination = (
            root / "runtime/catalog-owner-write-before-rename-crash"
        )
        before_rename_observation: dict[str, Any] = {"calls": 0}

        def fail_after_owner_write_before_rename(original):
            def injected(source, target, *args, **kwargs):
                if Path(target) == before_rename_destination / "ARTIFACTS":
                    before_rename_observation["calls"] += 1
                    before_rename_observation["source_mode"] = exact_mode(
                        Path(source)
                    )
                    raise OSError(
                        errno.EIO,
                        "injected after owner-write before directory rename",
                    )
                return original(source, target, *args, **kwargs)

            return injected

        audit.expect(
            "catalog.fallback.crash.owner-write-before-rename.injected",
            catalog.DatasetContractError,
            lambda: _with_renameat2_errno(
                catalog,
                errno.EINVAL,
                lambda: _with_os_override(
                    catalog,
                    "rename",
                    fail_after_owner_write_before_rename,
                    lambda: catalog.materialize_source_set(
                        view,
                        before_rename_destination,
                        lock=lock,
                        trusted_root=root,
                    ),
                ),
            ),
            "incomplete and retained",
        )
        audit.check(
            "catalog.fallback.crash.owner-write-before-rename.phase-observed",
            before_rename_observation == {"calls": 1, "source_mode": 0o700},
            observed=before_rename_observation,
        )
        check_failed_reserved_publication(
            "catalog.fallback.crash.owner-write-before-rename",
            before_rename_destination,
            artifacts_published=False,
        )

        before_restore_destination = (
            root / "runtime/catalog-renamed-before-mode-restore-crash"
        )
        before_restore_observation: dict[str, Any] = {"calls": 0}

        def fail_after_rename_before_mode_restore(original):
            def injected(source, target, *args, **kwargs):
                if Path(target) == before_restore_destination / "ARTIFACTS":
                    source_info = Path(source).lstat()
                    original(source, target, *args, **kwargs)
                    target_info = Path(target).lstat()
                    before_restore_observation["calls"] += 1
                    before_restore_observation["target_mode"] = stat.S_IMODE(
                        target_info.st_mode
                    )
                    before_restore_observation["identity_preserved"] = (
                        source_info.st_dev,
                        source_info.st_ino,
                    ) == (
                        target_info.st_dev,
                        target_info.st_ino,
                    )
                    raise OSError(
                        errno.EIO,
                        "injected after directory rename before mode restore",
                    )
                return original(source, target, *args, **kwargs)

            return injected

        audit.expect(
            "catalog.fallback.crash.renamed-before-mode-restore.injected",
            catalog.DatasetContractError,
            lambda: _with_renameat2_errno(
                catalog,
                errno.EINVAL,
                lambda: _with_os_override(
                    catalog,
                    "rename",
                    fail_after_rename_before_mode_restore,
                    lambda: catalog.materialize_source_set(
                        view,
                        before_restore_destination,
                        lock=lock,
                        trusted_root=root,
                    ),
                ),
            ),
            "incomplete and retained",
        )
        audit.check(
            "catalog.fallback.crash.renamed-before-mode-restore.phase-observed",
            before_restore_observation
            == {
                "calls": 1,
                "target_mode": 0o700,
                "identity_preserved": True,
            },
            observed=before_restore_observation,
        )
        check_failed_reserved_publication(
            "catalog.fallback.crash.renamed-before-mode-restore",
            before_restore_destination,
            artifacts_published=True,
        )

        before_receipt_destination = (
            root / "runtime/catalog-restored-before-receipt-crash"
        )
        before_receipt_observation: dict[str, Any] = {"calls": 0}

        def fail_after_restore_before_receipt(original):
            def injected(source, target, *args, **kwargs):
                if Path(target) == before_receipt_destination / "receipt.json":
                    before_receipt_observation["calls"] += 1
                    before_receipt_observation["artifacts_mode"] = exact_mode(
                        before_receipt_destination / "ARTIFACTS"
                    )
                    before_receipt_observation["source_receipt_mode"] = exact_mode(
                        Path(source)
                    )
                    raise OSError(
                        errno.EIO,
                        "injected after mode restore before receipt move",
                    )
                return original(source, target, *args, **kwargs)

            return injected

        audit.expect(
            "catalog.fallback.crash.restored-before-receipt.injected",
            catalog.DatasetContractError,
            lambda: _with_renameat2_errno(
                catalog,
                errno.EINVAL,
                lambda: _with_os_override(
                    catalog,
                    "rename",
                    fail_after_restore_before_receipt,
                    lambda: catalog.materialize_source_set(
                        view,
                        before_receipt_destination,
                        lock=lock,
                        trusted_root=root,
                    ),
                ),
            ),
            "incomplete and retained",
        )
        audit.check(
            "catalog.fallback.crash.restored-before-receipt.phase-observed",
            before_receipt_observation
            == {
                "calls": 1,
                "artifacts_mode": 0o500,
                "source_receipt_mode": 0o400,
            },
            observed=before_receipt_observation,
        )
        check_failed_reserved_publication(
            "catalog.fallback.crash.restored-before-receipt",
            before_receipt_destination,
            artifacts_published=True,
        )

        sidecar_destination = root / "runtime/catalog-sidecar-crash"

        def fail_catalog_target_mkdir(original):
            def injected(path, mode=0o777, *, dir_fd=None):
                if Path(path) == sidecar_destination:
                    raise OSError(
                        errno.EIO,
                        "injected catalog post-reservation mkdir crash",
                    )
                if dir_fd is None:
                    return original(path, mode)
                return original(path, mode, dir_fd=dir_fd)

            return injected

        audit.expect(
            "catalog.fallback.crash.sidecar-retained",
            OSError,
            lambda: _with_renameat2_errno(
                catalog,
                errno.EINVAL,
                lambda: _with_os_override(
                    catalog,
                    "mkdir",
                    fail_catalog_target_mkdir,
                    lambda: catalog.materialize_source_set(
                        view,
                        sidecar_destination,
                        lock=lock,
                        trusted_root=root,
                    ),
                ),
            ),
            "post-reservation",
        )
        audit.expect(
            "catalog.fallback.crash.sidecar-readiness-rejected",
            catalog.DatasetContractError,
            lambda: catalog.open_materialized_source_set(
                sidecar_destination,
                lock,
                trusted_root=root,
            ),
            "incomplete publication marker",
        )
        catalog_runtime_state = _entry_state(root / "runtime")
        sidecar_inspection = catalog.inspect_materialization(
            sidecar_destination,
            lock,
            trusted_root=root,
        )
        sidecar_quarantine = catalog.plan_materialization_quarantine(
            sidecar_destination,
            root / "quarantine/catalog-sidecar-crash",
            lock,
            trusted_root=root,
        )
        audit.check(
            "catalog.quarantine-plan.read-only",
            not sidecar_inspection.ready
            and bool(sidecar_inspection.marker_paths)
            and not sidecar_quarantine.receipt()["executed"]
            and catalog_runtime_state == _entry_state(root / "runtime"),
            inspection=sidecar_inspection.receipt(),
            plan=sidecar_quarantine.receipt(),
        )

        internal_destination = root / "runtime/catalog-internal-crash"

        def fail_catalog_child_rename(original):
            def injected(source, target, *args, **kwargs):
                if Path(target).parent == internal_destination:
                    raise OSError(
                        errno.EIO,
                        "injected catalog child publication crash",
                    )
                return original(source, target, *args, **kwargs)

            return injected

        audit.expect(
            "catalog.fallback.crash.internal-marker-retained",
            catalog.DatasetContractError,
            lambda: _with_renameat2_errno(
                catalog,
                errno.EINVAL,
                lambda: _with_os_override(
                    catalog,
                    "rename",
                    fail_catalog_child_rename,
                    lambda: catalog.materialize_source_set(
                        view,
                        internal_destination,
                        lock=lock,
                        trusted_root=root,
                    ),
                ),
            ),
            "incomplete and retained",
        )
        audit.check(
            "catalog.fallback.crash.markers-present",
            (internal_destination / catalog.PUBLICATION_INCOMPLETE_MARKER).is_file()
            and catalog._publication_sidecar(internal_destination).is_file()
            and not any(
                internal_destination.parent.glob(
                    f".{internal_destination.name}.staging-*"
                )
            ),
        )
        audit.expect(
            "catalog.fallback.crash.internal-readiness-rejected",
            catalog.DatasetContractError,
            lambda: catalog.open_materialized_source_set(
                internal_destination,
                lock,
                trusted_root=root,
            ),
            "incomplete publication marker",
        )

        reserved_destination = root / "runtime/catalog-reserved"
        catalog._publication_sidecar(reserved_destination).write_text(
            "reserved\n", "utf-8"
        )
        audit.expect(
            "catalog.reserved-marker.destination-rejected",
            catalog.DatasetContractError,
            lambda: catalog.materialize_source_set(
                view,
                reserved_destination,
                lock=lock,
                trusted_root=root,
            ),
            "incomplete publication marker",
        )

        marker_parent = root / "ancestor-marker-fixtures"
        marker_destination = marker_parent / "existing"
        marker_materialized = catalog.materialize_source_set(
            view,
            marker_destination,
            lock=lock,
            trusted_root=root,
        )
        marker_qualified_id = lock.artifacts[0].qualified_id
        for marker_location in ("sidecar", "internal"):
            for marker_kind in ("regular", "dangling-symlink"):
                marker_name = f"{marker_location}-{marker_kind}"
                marker_path = (
                    catalog._publication_sidecar(marker_parent)
                    if marker_location == "sidecar"
                    else marker_parent / catalog.PUBLICATION_INCOMPLETE_MARKER
                )
                attempted_destination = marker_parent / f"new-{marker_name}"
                if marker_kind == "regular":
                    marker_path.write_text("incomplete\n", "utf-8")
                else:
                    marker_path.symlink_to(marker_parent / "missing-marker-target")
                try:
                    audit.expect(
                        f"catalog.ancestor-marker.{marker_name}.open-rejected",
                        catalog.DatasetContractError,
                        lambda: catalog.open_materialized_source_set(
                            marker_destination,
                            lock,
                            trusted_root=root,
                        ),
                        "incomplete publication marker",
                    )
                    audit.expect(
                        f"catalog.ancestor-marker.{marker_name}.lookup-rejected",
                        catalog.DatasetContractError,
                        lambda: marker_materialized.verified_artifact_path(
                            marker_qualified_id
                        ),
                        "incomplete publication marker",
                    )
                    audit.expect(
                        f"catalog.ancestor-marker.{marker_name}.materialize-rejected",
                        catalog.DatasetContractError,
                        lambda destination=attempted_destination: (
                            catalog.materialize_source_set(
                                view,
                                destination,
                                lock=lock,
                                trusted_root=root,
                            )
                        ),
                        "incomplete publication marker",
                    )
                    existing_inspection = catalog.inspect_materialization(
                        marker_destination,
                        lock,
                        trusted_root=root,
                    )
                    absent_inspection = catalog.inspect_materialization(
                        attempted_destination,
                        lock,
                        trusted_root=root,
                    )
                    audit.check(
                        f"catalog.ancestor-marker.{marker_name}.inspection-fail-closed",
                        not existing_inspection.ready
                        and marker_path in existing_inspection.marker_paths
                        and not absent_inspection.exists
                        and not absent_inspection.ready
                        and marker_path in absent_inspection.marker_paths
                        and not os.path.lexists(attempted_destination),
                        existing=existing_inspection.receipt(),
                        absent=absent_inspection.receipt(),
                    )
                finally:
                    marker_path.unlink(missing_ok=True)

        audit.expect(
            "catalog.materialization.explicit-trusted-root.required",
            catalog.DatasetContractError,
            lambda: catalog.materialize_source_set(
                view, root / "runtime/no-trusted-root", lock=lock
            ),
            "explicit trusted_root",
        )
        export_destination = root / "never-created/export"
        audit.expect(
            "catalog.restricted.export.rejected",
            catalog.DatasetContractError,
            lambda: catalog.materialize_source_set(
                view,
                export_destination,
                lock=lock,
                for_export=True,
                trusted_root=root,
            ),
            "cannot be exported",
        )
        audit.check(
            "catalog.restricted.export.destination-not-created",
            not export_destination.exists()
            and not export_destination.parent.exists(),
        )
        wrong_lock = dataclasses.replace(lock, lock_sha256="0" * 64)
        audit.expect(
            "catalog.wrong-lock.rejected",
            catalog.DatasetContractError,
            lambda: catalog.materialize_source_set(
                view,
                root / "runtime/wrong-lock",
                lock=wrong_lock,
                trusted_root=root,
            ),
            "does not match",
        )
        provenance_destination = root / "runtime/provenance-tamper"
        catalog.materialize_source_set(
            view,
            provenance_destination,
            lock=lock,
            trusted_root=root,
        )
        rewrite_restricted_receipt(
            provenance_destination / "receipt.json",
            lambda receipt: receipt["artifacts"][0].__setitem__(
                "package_id", "forged-package"
            ),
        )
        audit.expect(
            "catalog.materialization.provenance-tamper.rejected",
            catalog.DatasetContractError,
            lambda: catalog.open_materialized_source_set(
                provenance_destination,
                lock,
                trusted_root=root,
            ),
            "artifact mismatch",
        )

        duplicate_path_destination = root / "runtime/duplicate-path"
        catalog.materialize_source_set(
            view,
            duplicate_path_destination,
            lock=lock,
            trusted_root=root,
        )

        def duplicate_materialized_path(receipt: dict[str, Any]) -> None:
            receipt["artifacts"][1]["materialized_path"] = receipt["artifacts"][0][
                "materialized_path"
            ]

        rewrite_restricted_receipt(
            duplicate_path_destination / "receipt.json",
            duplicate_materialized_path,
        )
        audit.expect(
            "catalog.materialization.duplicate-path.rejected",
            catalog.DatasetContractError,
            lambda: catalog.open_materialized_source_set(
                duplicate_path_destination,
                lock,
                trusted_root=root,
            ),
            "materialized_path is not one-to-one",
        )

        shape_destination = root / "runtime/shape-validation"
        shape_materialized = catalog.materialize_source_set(
            view,
            shape_destination,
            lock=lock,
            trusted_root=root,
        )
        extra_directory = shape_destination / "EXTRA"
        extra_directory.mkdir()
        extra_directory.chmod(0o500, follow_symlinks=False)
        audit.expect(
            "catalog.materialization.extra-directory.rejected",
            catalog.DatasetContractError,
            lambda: catalog.open_materialized_source_set(
                shape_destination,
                lock,
                trusted_root=root,
            ),
            "undeclared directories",
        )
        extra_directory.rmdir()
        extra_file = shape_destination / "extra.txt"
        extra_file.write_text("extra\n", "utf-8")
        extra_file.chmod(0o400, follow_symlinks=False)
        audit.expect(
            "catalog.materialization.extra-file.rejected",
            catalog.DatasetContractError,
            lambda: catalog.open_materialized_source_set(
                shape_destination,
                lock,
                trusted_root=root,
            ),
            "undeclared files",
        )
        extra_file.unlink()
        extra_symlink = shape_destination / "extra-link"
        extra_symlink.symlink_to(shape_destination / "receipt.json")
        audit.expect(
            "catalog.materialization.symlink-member.rejected",
            catalog.DatasetContractError,
            lambda: catalog.open_materialized_source_set(
                shape_destination,
                lock,
                trusted_root=root,
            ),
            "contains a symlink",
        )
        extra_symlink.unlink()
        extra_fifo = shape_destination / "extra.fifo"
        os.mkfifo(extra_fifo)
        audit.expect(
            "catalog.materialization.fifo-member.rejected",
            catalog.DatasetContractError,
            lambda: catalog.open_materialized_source_set(
                shape_destination,
                lock,
                trusted_root=root,
            ),
            "contains a special file",
        )
        extra_fifo.unlink()
        shape_reopened = catalog.open_materialized_source_set(
            shape_destination,
            lock,
            trusted_root=root,
        )
        audit.check(
            "catalog.materialization.shape-restore.verified-open",
            shape_reopened.receipt_sha256 == shape_materialized.receipt_sha256,
        )

        outside_runtime = root / "outside-runtime"
        outside_runtime.mkdir()
        ancestor_link = root / "runtime-link"
        ancestor_link.symlink_to(outside_runtime, target_is_directory=True)
        audit.expect(
            "catalog.materialization.ancestor-symlink.rejected",
            catalog.DatasetContractError,
            lambda: catalog.materialize_source_set(
                view,
                ancestor_link / "through-link",
                lock=lock,
                trusted_root=root,
            ),
            "traverses a symlink",
        )
        leaf_link = root / "runtime/leaf-link"
        leaf_link.symlink_to(outside_runtime, target_is_directory=True)
        audit.expect(
            "catalog.materialization.leaf-symlink.rejected",
            catalog.DatasetContractError,
            lambda: catalog.open_materialized_source_set(
                leaf_link,
                lock,
                trusted_root=root,
            ),
            "traverses a symlink",
        )
        trusted_root_link = root / "trusted-root-link"
        trusted_root_link.symlink_to(root, target_is_directory=True)
        audit.expect(
            "catalog.materialization.trusted-root-symlink.rejected",
            catalog.DatasetContractError,
            lambda: catalog.materialize_source_set(
                view,
                trusted_root_link / "runtime/through-trusted-root-link",
                lock=lock,
                trusted_root=trusted_root_link,
            ),
            "non-symlink directory",
        )

        collision_left, _ = _write_package(
            catalog,
            root,
            package_id="aa:bb",
            dataset_id="collision-data",
            version_id="collision-left-v1",
            representation="mock",
            restricted=False,
            logical_id="cc",
            content='{"identity":"left"}\n',
        )
        collision_right, _ = _write_package(
            catalog,
            root,
            package_id="aa",
            dataset_id="collision-data",
            version_id="collision-right-v1",
            representation="mock",
            restricted=False,
            logical_id="bb:cc",
            content='{"identity":"right"}\n',
        )
        collision_source_set = {
            "schema_version": "source-set-v1",
            "source_set_id": "qualified-id-collision",
            "generation_id": "qualified-id-collision-generation",
            "conflict_policy": "error",
            "cross_dataset_relations": False,
            "members": [
                {"package_id": collision_left.package_id, "priority": 10},
                {"package_id": collision_right.package_id, "priority": 10},
            ],
        }
        collision_view = catalog.compose_source_set(
            collision_source_set,
            [collision_left, collision_right],
        )
        collision_lock = collision_view.lock()
        collision_old_joined_ids = [
            f"{artifact.package_id}:{artifact.logical_id}:{artifact.role}"
            for artifact in collision_lock.artifacts
        ]
        collision_qualified_ids = [
            artifact.qualified_id for artifact in collision_lock.artifacts
        ]
        audit.check(
            "catalog.qualified-id.colon-collision.injective",
            len(collision_lock.artifacts) == 2
            and len(set(collision_old_joined_ids)) == 1
            and len(set(collision_qualified_ids)) == 2
            and len(
                {
                    artifact.identity_key
                    for artifact in collision_lock.artifacts
                }
            )
            == 2,
            old_joined_ids=collision_old_joined_ids,
            qualified_ids=collision_qualified_ids,
        )
        collision_materialized = catalog.materialize_source_set(
            collision_view,
            root / "runtime/qualified-id-collision",
            lock=collision_lock,
            trusted_root=root,
        )
        collision_paths = {
            artifact.package_id: collision_materialized.verified_artifact_path(
                artifact.qualified_id
            )
            for artifact in collision_lock.artifacts
        }
        audit.check(
            "catalog.qualified-id.colon-collision.lookups-one-to-one",
            collision_paths["aa:bb"].read_text("utf-8")
            == '{"identity":"left"}\n'
            and collision_paths["aa"].read_text("utf-8")
            == '{"identity":"right"}\n'
            and len(
                {
                    row["qualified_id"]
                    for row in collision_materialized.receipt["artifacts"]
                }
            )
            == 2,
            paths={key: str(value) for key, value in collision_paths.items()},
        )

        installed_root = root / "installed-catalog"
        installed_low, installed_low_manifest = _write_package(
            catalog,
            installed_root,
            package_id="installed-low",
            dataset_id="installed-data",
            version_id="installed-low-v1",
            representation="real",
            restricted=True,
            logical_id="shared/rule",
            content='{"winner":"low"}\n',
            document_id="installed-document",
        )
        installed_high, installed_high_manifest = _write_package(
            catalog,
            installed_root,
            package_id="installed-high",
            dataset_id="installed-data",
            version_id="installed-high-v1",
            representation="real",
            restricted=False,
            logical_id="shared/rule",
            content='{"winner":"high"}\n',
            document_id="installed-document",
        )
        installed_unique, installed_unique_manifest = _write_package(
            catalog,
            installed_root,
            package_id="installed-unique",
            dataset_id="installed-data",
            version_id="installed-unique-v1",
            representation="real",
            restricted=False,
            logical_id="unique/rule",
            content='{"unique":true}\n',
            document_id="installed-unique-document",
        )
        installed_packages = (installed_low, installed_high, installed_unique)
        installed_manifests = (
            installed_low_manifest,
            installed_high_manifest,
            installed_unique_manifest,
        )
        installed_catalog_blob = {
            "schema_version": "installed-dataset-catalog-v1",
            "packages": [
                {
                    "package_id": package.package_id,
                    "manifest_path": manifest.relative_to(installed_root).as_posix(),
                    "manifest_sha256": package.manifest_sha256,
                }
                for package, manifest in zip(
                    installed_packages,
                    installed_manifests,
                    strict=True,
                )
            ],
        }
        installed_catalog = catalog.installed_catalog_from_mapping(
            installed_catalog_blob,
            package_root=installed_root,
        )
        installed_source_set = {
            "schema_version": "source-set-v1",
            "source_set_id": "installed-source",
            "generation_id": "installed-generation",
            "conflict_policy": "explicit_priority",
            "cross_dataset_relations": False,
            "members": [
                {"package_id": installed_low.package_id, "priority": 10},
                {"package_id": installed_high.package_id, "priority": 30},
                {"package_id": installed_unique.package_id, "priority": 20},
            ],
        }
        installed_view = installed_catalog.open(installed_source_set)
        installed_lock = installed_view.lock()

        def resolve_installed(candidate_lock, authority_lock):
            return installed_catalog.resolve_lock(
                candidate_lock,
                expected_source_set_sha256=authority_lock.source_set_sha256,
                expected_lock_sha256=authority_lock.lock_sha256,
            )

        installed_resolved = resolve_installed(installed_lock, installed_lock)
        installed_shared = next(
            artifact
            for artifact in installed_lock.artifacts
            if artifact.logical_id == "shared/rule"
        )
        installed_unique_lock = next(
            artifact
            for artifact in installed_lock.artifacts
            if artifact.logical_id == "unique/rule"
        )
        audit.check(
            "catalog.installed.resolve-lock.exact-recomposition",
            tuple(package.package_id for package in installed_resolved)
            == tuple(member.package_id for member in installed_lock.members)
            and installed_shared.package_id == installed_high.package_id
            and installed_shared.contributors
            == tuple(sorted((installed_low.package_id, installed_high.package_id)))
            and installed_shared.document_id == "installed-document"
            and not installed_lock.export_allowed,
            lock=installed_lock.receipt(),
        )
        audit.expect(
            "catalog.installed.serving-authority.required",
            TypeError,
            lambda: installed_catalog.resolve_lock(installed_lock),
            "expected_source_set_sha256",
        )
        audit.expect(
            "catalog.installed.serving-authority.source-required",
            TypeError,
            lambda: installed_catalog.resolve_lock(
                installed_lock,
                expected_lock_sha256=installed_lock.lock_sha256,
            ),
            "expected_source_set_sha256",
        )
        audit.expect(
            "catalog.installed.serving-authority.lock-required",
            TypeError,
            lambda: installed_catalog.resolve_lock(
                installed_lock,
                expected_source_set_sha256=installed_lock.source_set_sha256,
            ),
            "expected_lock_sha256",
        )
        for name, source_hash, lock_hash, expected_message in (
            (
                "source-hash-non-string",
                7,
                installed_lock.lock_sha256,
                "expected_source_set_sha256",
            ),
            (
                "source-hash-uppercase",
                "A" * 64,
                installed_lock.lock_sha256,
                "expected_source_set_sha256",
            ),
            (
                "lock-hash-non-string",
                installed_lock.source_set_sha256,
                7,
                "expected_lock_sha256",
            ),
            (
                "lock-hash-short",
                installed_lock.source_set_sha256,
                installed_lock.lock_sha256[:-1],
                "expected_lock_sha256",
            ),
            (
                "source-hash-mismatch",
                h("unapproved-source-set"),
                installed_lock.lock_sha256,
                "trusted serving authority",
            ),
            (
                "lock-hash-mismatch",
                installed_lock.source_set_sha256,
                h("unapproved-lock"),
                "trusted serving authority",
            ),
        ):
            audit.expect(
                f"catalog.installed.serving-authority.{name}.rejected",
                catalog.DatasetContractError,
                lambda source_hash=source_hash, lock_hash=lock_hash: (
                    installed_catalog.resolve_lock(
                        installed_lock,
                        expected_source_set_sha256=source_hash,
                        expected_lock_sha256=lock_hash,
                    )
                ),
                expected_message,
            )

        priority_source_set = json.loads(json.dumps(installed_source_set))
        for member in priority_source_set["members"]:
            if member["package_id"] == installed_low.package_id:
                member["priority"] = 40
        priority_forged_lock = installed_catalog.open(priority_source_set).lock()
        priority_forged_shared = next(
            artifact
            for artifact in priority_forged_lock.artifacts
            if artifact.logical_id == "shared/rule"
        )
        catalog._validate_source_set_lock_packages(
            priority_forged_lock,
            installed_packages,
        )
        audit.check(
            "catalog.installed.self-consistent-priority-forgery.precondition",
            priority_forged_lock.source_set_sha256
            != installed_lock.source_set_sha256
            and priority_forged_lock.lock_sha256 != installed_lock.lock_sha256
            and priority_forged_shared.package_id == installed_low.package_id,
            original_lock=installed_lock.receipt(),
            forged_lock=priority_forged_lock.receipt(),
        )
        audit.expect(
            "catalog.installed.self-consistent-priority-forgery.authority-rejected",
            catalog.DatasetContractError,
            lambda: resolve_installed(priority_forged_lock, installed_lock),
            "trusted serving authority",
        )

        policy_source_set = json.loads(json.dumps(installed_source_set))
        policy_source_set["cross_dataset_relations"] = True
        policy_forged_lock = installed_catalog.open(policy_source_set).lock()
        catalog._validate_source_set_lock_packages(
            policy_forged_lock,
            installed_packages,
        )
        audit.expect(
            "catalog.installed.self-consistent-policy-forgery.authority-rejected",
            catalog.DatasetContractError,
            lambda: resolve_installed(policy_forged_lock, installed_lock),
            "trusted serving authority",
        )
        for name, operation in (
            (
                "lookup",
                lambda: installed_catalog.lookup(
                    installed_high.package_id,
                    installed_high.manifest_sha256,
                    verify_files=False,
                ),
            ),
            (
                "open",
                lambda: installed_catalog.open(
                    installed_source_set,
                    verify_files=False,
                ),
            ),
            (
                "resolve-lock",
                lambda: installed_catalog.resolve_lock(
                    installed_lock,
                    expected_source_set_sha256=installed_lock.source_set_sha256,
                    expected_lock_sha256=installed_lock.lock_sha256,
                    verify_files=False,
                ),
            ),
        ):
            audit.expect(
                f"catalog.installed.{name}.verify-files-bypass-rejected",
                TypeError,
                operation,
                "verify_files",
            )

        omitted_lock = _rehash_source_set_lock(
            catalog,
            dataclasses.replace(
                installed_lock,
                artifacts=tuple(
                    artifact
                    for artifact in installed_lock.artifacts
                    if artifact.qualified_id != installed_unique_lock.qualified_id
                ),
            ),
        )
        audit.expect(
            "catalog.installed.incomplete-artifact-lock.rejected",
            catalog.DatasetContractError,
            lambda: resolve_installed(omitted_lock, omitted_lock),
            "deterministic package composition",
        )

        low_artifact = installed_low.artifacts[0]
        forged_low_winner = dataclasses.replace(
            installed_shared,
            package_id=low_artifact.package_id,
            dataset_id=low_artifact.dataset_id,
            version_id=low_artifact.version_id,
            build_id=low_artifact.build_id,
            manifest_sha256=installed_low.manifest_sha256,
            logical_id=low_artifact.logical_id,
            role=low_artifact.role,
            path=low_artifact.path,
            sha256=low_artifact.sha256,
            document_id=low_artifact.document_id,
        )
        lower_priority_lock = _rehash_source_set_lock(
            catalog,
            dataclasses.replace(
                installed_lock,
                artifacts=tuple(
                    forged_low_winner
                    if artifact.qualified_id == installed_shared.qualified_id
                    else artifact
                    for artifact in installed_lock.artifacts
                ),
            ),
        )
        audit.expect(
            "catalog.installed.lower-priority-winner.rejected",
            catalog.DatasetContractError,
            lambda: resolve_installed(lower_priority_lock, lower_priority_lock),
            "deterministic package composition",
        )

        contributor_lock = _rehash_source_set_lock(
            catalog,
            dataclasses.replace(
                installed_lock,
                artifacts=tuple(
                    dataclasses.replace(
                        artifact,
                        contributors=(artifact.package_id,),
                    )
                    if artifact.qualified_id == installed_shared.qualified_id
                    else artifact
                    for artifact in installed_lock.artifacts
                ),
            ),
        )
        audit.expect(
            "catalog.installed.contributor-set.rejected",
            catalog.DatasetContractError,
            lambda: resolve_installed(contributor_lock, contributor_lock),
            "deterministic package composition",
        )

        export_lock = _rehash_source_set_lock(
            catalog,
            dataclasses.replace(installed_lock, export_allowed=True),
        )
        audit.expect(
            "catalog.installed.export-policy-forgery.rejected",
            catalog.DatasetContractError,
            lambda: resolve_installed(export_lock, export_lock),
            "export policy",
        )

        provenance_values = {
            "dataset_id": "forged-dataset",
            "version_id": "forged-version",
            "build_id": "forged-build",
            "manifest_sha256": h("forged-manifest"),
        }
        for field, forged_value in provenance_values.items():
            forged_members = tuple(
                dataclasses.replace(member, **{field: forged_value})
                if member.package_id == installed_shared.package_id
                else member
                for member in installed_lock.members
            )
            forged_artifacts = tuple(
                dataclasses.replace(artifact, **{field: forged_value})
                if artifact.package_id == installed_shared.package_id
                else artifact
                for artifact in installed_lock.artifacts
            )
            forged_lock = _rehash_source_set_lock(
                catalog,
                dataclasses.replace(
                    installed_lock,
                    members=forged_members,
                    artifacts=forged_artifacts,
                ),
            )
            audit.expect(
                f"catalog.installed.provenance.{field}.tamper-rejected",
                catalog.DatasetContractError,
                lambda candidate=forged_lock: resolve_installed(candidate, candidate),
                "installed" if field == "manifest_sha256" else "package manifest",
            )

        for field, forged_value in (
            ("document_id", "forged-document"),
            ("path", "forged-artifact.json"),
        ):
            forged_lock = _rehash_source_set_lock(
                catalog,
                dataclasses.replace(
                    installed_lock,
                    artifacts=tuple(
                        dataclasses.replace(artifact, **{field: forged_value})
                        if artifact.qualified_id == installed_shared.qualified_id
                        else artifact
                        for artifact in installed_lock.artifacts
                    ),
                ),
            )
            audit.expect(
                f"catalog.installed.provenance.{field}.tamper-rejected",
                catalog.DatasetContractError,
                lambda candidate=forged_lock: resolve_installed(candidate, candidate),
                "package manifest",
            )

        high_artifact_path = installed_high_manifest.parent / installed_high.artifacts[0].path
        high_artifact_original = high_artifact_path.read_bytes()
        high_artifact_path.write_bytes(high_artifact_original + b"tampered\n")
        try:
            audit.expect(
                "catalog.installed.live-artifact-tamper.rejected",
                catalog.DatasetContractError,
                lambda: resolve_installed(installed_lock, installed_lock),
                "artifact hash mismatch",
            )
        finally:
            high_artifact_path.write_bytes(high_artifact_original)
        audit.check(
            "catalog.installed.live-artifact-restore.resolves",
            resolve_installed(installed_lock, installed_lock) == installed_resolved,
        )

        other, _ = _write_package(
            catalog,
            root,
            package_id="other-public",
            dataset_id="other-data",
            version_id="other-v1",
            representation="mock",
            restricted=False,
            logical_id="other/doc",
            content='{"other":true}\n',
        )
        cross_blob = {
            "schema_version": "source-set-v1",
            "source_set_id": "cross-source",
            "generation_id": "cross-generation",
            "conflict_policy": "error",
            "cross_dataset_relations": False,
            "members": [
                {"package_id": external.package_id, "priority": 10},
                {"package_id": other.package_id, "priority": 10},
            ],
        }
        cross_destinations: list[Path] = []
        for declared_relations in (False, True):
            declared_blob = dict(cross_blob)
            declared_blob["source_set_id"] = (
                f"cross-source-declared-{str(declared_relations).lower()}"
            )
            declared_blob["cross_dataset_relations"] = declared_relations
            declared_view = catalog.compose_source_set(
                declared_blob,
                [external, other],
            )
            for relation_policy_enforced in (False, True):
                for allow_cross_dataset_relations in (False, True):
                    case_name = (
                        f"declared-{int(declared_relations)}"
                        f"-policy-{int(relation_policy_enforced)}"
                        f"-allow-{int(allow_cross_dataset_relations)}"
                    )
                    cross_destination = root / f"runtime/cross-{case_name}"
                    cross_destinations.append(cross_destination)
                    audit.expect(
                        f"catalog.cross-dataset.{case_name}.fail-closed",
                        catalog.DatasetContractError,
                        lambda current_view=declared_view,
                        destination=cross_destination,
                        policy=relation_policy_enforced,
                        allow=allow_cross_dataset_relations: (
                            catalog.materialize_source_set(
                                current_view,
                                destination,
                                relation_policy_enforced=policy,
                                allow_cross_dataset_relations=allow,
                                trusted_root=root,
                            )
                        ),
                        "no verified runtime capability contract",
                    )
        audit.check(
            "catalog.cross-dataset.denial-before-destination",
            all(not os.path.lexists(path) for path in cross_destinations),
            destinations=[str(path) for path in cross_destinations],
        )
        keep_blob = dict(cross_blob)
        keep_blob["source_set_id"] = "keep-namespaced-source"
        keep_blob["conflict_policy"] = "keep_namespaced"
        keep_view = catalog.compose_source_set(keep_blob, [external, other])
        audit.expect(
            "catalog.keep-namespaced.runtime.rejected",
            catalog.DatasetContractError,
            lambda: catalog.materialize_source_set(
                keep_view,
                root / "runtime/keep",
                relation_policy_enforced=True,
                trusted_root=root,
            ),
            "namespace-aware",
        )

        bad_blob = {
            "schema_version": "dataset-package-v2",
            "package_id": "bad-path",
            "dataset_id": "bad-data",
            "version_id": "bad-version",
            "variant_id": "mock",
            "generation_id": "bad-generation",
            "source_origin": "synthetic",
            "security_class": "public",
            "representation": "mock",
            "authority": "evaluation",
            "export_policy": {"allowed": True},
            "build": {
                "build_id": "bad-build",
                "execution_site": "outside",
                "code_revision": "fixture",
                "compiler_profile": "fixture",
                "capabilities": [],
            },
            "artifacts": [
                {
                    "logical_id": "bad/artifact",
                    "role": "raw",
                    "path": "bad\\path.json",
                    "sha256": "0" * 64,
                    "media_type": "application/json",
                }
            ],
        }
        audit.expect(
            "catalog.non-posix-path.rejected",
            catalog.DatasetContractError,
            lambda: catalog.package_from_mapping(bad_blob, manifest_path=root / "bad.json"),
            "safe relative path",
        )
        valid_contract_blob = json.loads(json.dumps(bad_blob))
        valid_contract_blob["artifacts"][0]["path"] = "artifact.json"

        duplicate_capability_blob = json.loads(json.dumps(valid_contract_blob))
        duplicate_capability_blob["build"]["capabilities"] = [
            "structure",
            "structure",
        ]
        audit.expect(
            "catalog.package.duplicate-capability.rejected",
            catalog.DatasetContractError,
            lambda: catalog.package_from_mapping(
                duplicate_capability_blob,
                manifest_path=root / "duplicate-capability.json",
            ),
            "must not contain duplicates",
        )

        empty_media_type_blob = json.loads(json.dumps(valid_contract_blob))
        empty_media_type_blob["artifacts"][0]["media_type"] = ""
        audit.expect(
            "catalog.package.empty-media-type.rejected",
            catalog.DatasetContractError,
            lambda: catalog.package_from_mapping(
                empty_media_type_blob,
                manifest_path=root / "empty-media-type.json",
            ),
            "non-empty string",
        )

        for name, invalid_path in (
            ("dot-segment", "./artifact.json"),
            ("inner-dot-segment", "nested/./artifact.json"),
            ("trailing-slash", "artifact.json/"),
            ("leading-space", " artifact.json"),
            ("trailing-space", "artifact.json "),
            ("control-character", "artifact\t.json"),
        ):
            invalid_path_blob = json.loads(json.dumps(valid_contract_blob))
            invalid_path_blob["artifacts"][0]["path"] = invalid_path
            audit.expect(
                f"catalog.package.noncanonical-path.{name}.rejected",
                catalog.DatasetContractError,
                lambda candidate=invalid_path_blob: catalog.package_from_mapping(
                    candidate,
                    manifest_path=root / f"noncanonical-{name}.json",
                ),
                "safe relative path",
            )

        duplicate_logical_key_blob = json.loads(json.dumps(valid_contract_blob))
        duplicate_artifact = json.loads(
            json.dumps(duplicate_logical_key_blob["artifacts"][0])
        )
        duplicate_artifact["path"] = "second-artifact.json"
        duplicate_logical_key_blob["artifacts"].append(duplicate_artifact)
        audit.expect(
            "catalog.package.logical-role-uniqueness.runtime-rejected",
            catalog.DatasetContractError,
            lambda: catalog.package_from_mapping(
                duplicate_logical_key_blob,
                manifest_path=root / "duplicate-logical-key.json",
            ),
            "duplicate artifact logical key",
        )

        for name, field, value in (
            ("security-class", "security_class", "restricted"),
            ("source-origin", "source_origin", "restricted_internal"),
        ):
            invalid_export_blob = json.loads(json.dumps(valid_contract_blob))
            invalid_export_blob[field] = value
            audit.expect(
                f"catalog.package.{name}.export-true.rejected",
                catalog.DatasetContractError,
                lambda candidate=invalid_export_blob: catalog.package_from_mapping(
                    candidate,
                    manifest_path=root / f"invalid-export-{name}.json",
                ),
                "cannot be exportable",
            )
        return {
            "legacy_package_sha256": external.manifest_sha256,
            "source_set_sha256": view.source_set_sha256,
            "source_set_lock_sha256": lock.lock_sha256,
            "installed_source_set_lock_sha256": installed_lock.lock_sha256,
            "materialization_receipt_sha256": materialized.receipt_sha256,
            "fallback_publish_strategies": catalog_fallback_strategies,
            "package_count": len(view.packages),
            "artifact_count": len(view.artifacts),
            "export_allowed": view.export_allowed,
        }


_RELEASE_ARTIFACT_RELATIVE_PATHS = {
    "main.state": "artifacts/main-state.json",
    "source_set.content": "artifacts/source-set.json",
    "semantics.content": "artifacts/semantics.json",
    "index.lexical": "indexes/lexical.bin",
    "index.vector": "vectors.bin",
}


def _copy_regular_tree(source: Path, destination: Path) -> None:
    """Copy a symlink-free fixture tree without importing mutable helpers."""

    destination.mkdir(parents=True, exist_ok=False)
    pending = [source]
    while pending:
        current = pending.pop()
        for child in sorted(current.iterdir(), key=lambda value: os.fsencode(value.name)):
            relative = child.relative_to(source)
            target = destination / relative
            info = child.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise RuntimeError(f"fixture code tree contains a symlink: {child}")
            if stat.S_ISDIR(info.st_mode):
                target.mkdir()
                pending.append(child)
            elif stat.S_ISREG(info.st_mode):
                target.write_bytes(stable_regular_bytes(child))
            else:
                raise RuntimeError(f"fixture code tree contains a special file: {child}")


def _stage_release_artifacts(
    release,
    stage_root: Path,
    release_id: str,
    *,
    seed: str,
) -> dict[str, Path]:
    """Write the exact bytes named by a fixture release before its manifest."""

    stage = stage_root / release_id
    stage.mkdir(parents=True, exist_ok=False)
    payloads = {
        "main.state": canonical_bytes({
            "generation": 0,
            "pipeline_id": "legalclosure-v2",
            "runtime_profile": "legalclosure-v2",
        }),
        "source_set.content": canonical_bytes({
            "release_id": release_id,
            "seed": seed,
            "source_set_id": f"source-{seed}",
        }),
        "semantics.content": canonical_bytes({
            "authority_generation": f"authority-{seed}",
            "generation_id": f"semantic-{seed}",
            "release_id": release_id,
        }),
        "index.lexical": canonical_bytes({
            "index": "lexical",
            "release_id": release_id,
            "seed": seed,
        }),
        "index.vector": f"vectors:{release_id}:{seed}\n".encode("utf-8"),
    }
    staged: dict[str, Path] = {}
    for key, relative in _RELEASE_ARTIFACT_RELATIVE_PATHS.items():
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payloads[key])
        # Compute through the candidate helper here so a fixture cannot drift
        # from the release contract's file/directory hashing semantics.
        release.runtime_artifact_sha256(path)
        staged[key] = path
    return staged


def _index_records(
    release,
    *,
    source_sha: str,
    semantic_content_sha: str,
    semantic_generation: str,
    seed: str,
):
    source = release.SourceSetBinding(
        source_set_id=f"source-{seed}",
        generation_id=f"source-generation-{seed}",
        sha256=source_sha,
        export_allowed=False,
    )
    semantics = release.SemanticBinding(
        generation_id=semantic_generation,
        authority_generation=f"authority-{seed}",
        content_sha256=semantic_content_sha,
        source_set_sha256=source_sha,
        runtime_wired=True,
    )
    model = release.embedding_model_fingerprint(
        backend="fixture",
        model_id="fixture-encoder",
        model_revision=f"weights-{seed}",
        dimensions=8,
        normalized=True,
        document_profile="document-v1",
        query_profile="query-v1",
    )
    inputs = {
        f"source-set-{seed}": source_sha,
        f"semantics-{seed}": semantic_content_sha,
    }
    lexical = release.create_index_build_fingerprint(
        kind="lexical",
        source_set=source,
        semantics=semantics,
        builder_id="lexical-builder",
        builder_revision="a" * 40,
        input_artifacts=inputs,
        configuration={"tokenizer": "fixture-v1"},
    )
    vector = release.create_index_build_fingerprint(
        kind="vector",
        source_set=source,
        semantics=semantics,
        builder_id="vector-builder",
        builder_revision="b" * 40,
        input_artifacts=inputs,
        configuration={"metric": "cosine"},
        model_fingerprint=model,
    )
    return source, semantics, lexical, vector, model


def release_manifest(
    release,
    release_id: str,
    *,
    seed: str,
    artifact_paths: Mapping[str, Path],
) -> tuple[dict[str, Any], Any, Any]:
    if set(artifact_paths) != set(_RELEASE_ARTIFACT_RELATIVE_PATHS):
        raise RuntimeError("release fixture artifact set is incomplete")
    artifact_sha256 = {
        key: release.runtime_artifact_sha256(path)
        for key, path in artifact_paths.items()
    }
    source_sha = artifact_sha256["source_set.content"]
    semantic_generation = f"semantic-{seed}"
    source, semantics, lexical, vector, model = _index_records(
        release,
        source_sha=source_sha,
        semantic_content_sha=artifact_sha256["semantics.content"],
        semantic_generation=semantic_generation,
        seed=seed,
    )
    blob: dict[str, Any] = {
        "schema_version": "release-manifest-v1",
        "release_id": release_id,
        "target": "genos",
        "layout_version": "v2",
        "created_at": NOW,
        "code": {
            "revision": REVISION_SHA256,
            "package_sha256": release.runtime_artifact_sha256(REVISION_ROOT),
        },
        "main": {
            "pipeline_id": "legalclosure-v2",
            "runtime_profile": "legalclosure-v2",
            "generation": 0,
            "state_sha256": artifact_sha256["main.state"],
            "promotion_receipt_sha256": None,
        },
        "source_set": {
            "id": source.source_set_id,
            "generation_id": source.generation_id,
            "sha256": source.sha256,
            "export_allowed": source.export_allowed,
        },
        "semantics": {
            "generation_id": semantics.generation_id,
            "authority_generation": semantics.authority_generation,
            "content_sha256": semantics.content_sha256,
            "source_set_sha256": semantics.source_set_sha256,
            "runtime_wired": True,
        },
        "indexes": [
            {
                "kind": "lexical",
                "artifact_id": f"lexical-{seed}",
                "artifact_sha256": artifact_sha256["index.lexical"],
                "source_set_sha256": source.sha256,
                "semantic_generation": semantics.generation_id,
                "build_fingerprint": lexical.build_fingerprint,
                "embedding_model_fingerprint": None,
            },
            {
                "kind": "vector",
                "artifact_id": f"vector-{seed}",
                "artifact_sha256": artifact_sha256["index.vector"],
                "source_set_sha256": source.sha256,
                "semantic_generation": semantics.generation_id,
                "build_fingerprint": vector.build_fingerprint,
                "embedding_model_fingerprint": model,
            },
        ],
    }
    parsed = release.release_from_mapping(blob)
    blob["manifest_sha256"] = parsed.manifest_sha256
    return blob, lexical, vector


def _materialize_release_runtime(
    store,
    release_id: str,
    staged_artifacts: Mapping[str, Path],
) -> tuple[Path, dict[str, str], dict[str, str]]:
    runtime_root = store.runtime_root(release_id, create=True)
    artifact_paths: dict[str, str] = {}
    for key, relative in _RELEASE_ARTIFACT_RELATIVE_PATHS.items():
        destination = runtime_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(stable_regular_bytes(staged_artifacts[key]))
        artifact_paths[key] = relative
    (runtime_root / "structure").mkdir()
    (runtime_root / "structure/doc.json").write_text(
        json.dumps({"release": release_id}) + "\n", "utf-8"
    )
    (runtime_root / "custom").mkdir()
    (runtime_root / "glossary.json").write_text("{}\n", "utf-8")
    (runtime_root / "links.json").write_text("{}\n", "utf-8")
    paths = {
        "STRUCTURE_STORE": "structure",
        "STRUCTURE_CUSTOM_DIR": "custom",
        "GLOSSARY_STORE": "glossary.json",
        "RAG_LINKS_STORE": "links.json",
        "RAG_VECTOR_STORE": "vectors.bin",
    }
    return runtime_root, paths, artifact_paths


def _install_unbound_release_fixture(
    release,
    store,
    release_id: str,
    *,
    seed: str,
):
    staged_artifacts = _stage_release_artifacts(
        release,
        store.root.parent / "fixture-stage",
        release_id,
        seed=seed,
    )
    blob, lexical_fingerprint, vector_fingerprint = release_manifest(
        release,
        release_id,
        seed=seed,
        artifact_paths=staged_artifacts,
    )
    installed = store.install_release(blob)
    runtime_root, paths, artifact_paths = _materialize_release_runtime(
        store, release_id, staged_artifacts
    )
    return (
        installed,
        runtime_root,
        paths,
        artifact_paths,
        lexical_fingerprint,
        vector_fingerprint,
    )


def install_release_bundle(
    release,
    store,
    release_id: str,
    *,
    seed: str,
    valid_provenance: bool = True,
):
    (
        installed,
        _runtime_root,
        paths,
        artifact_paths,
        lexical_fingerprint,
        vector_fingerprint,
    ) = _install_unbound_release_fixture(
        release, store, release_id, seed=seed
    )
    binding = store.install_runtime_binding(
        release_id,
        paths=paths,
        artifact_paths=artifact_paths,
        created_at=NOW,
    )
    references = []
    for kind in RECEIPT_KINDS:
        details = {"validator": "adr0158-isolated-v1"}
        result = {"passed": True, "kind": kind, "seed": seed}
        if kind == "provenance":
            if valid_provenance:
                result = binding.provenance_result()
                details = binding.provenance_details()
            else:
                details["runtime_binding_sha256"] = binding.binding_sha256
        document = release.create_validation_receipt(
            kind=kind,
            receipt_id=f"{kind}-{seed}",
            release=installed,
            created_at=NOW,
            result=result,
            details=details,
        )
        references.append(store.install_validation_receipt(document))
    return installed, tuple(references), binding, lexical_fingerprint, vector_fingerprint


def _tamper_sealed_runtime_artifact(store, release_id: str, key: str) -> Path:
    target = store.runtime_root(release_id) / _RELEASE_ARTIFACT_RELATIVE_PATHS[key]
    original_mode = stat.S_IMODE(target.lstat().st_mode)
    target.chmod(original_mode | stat.S_IWUSR)
    target.write_bytes(stable_regular_bytes(target) + b"tampered\n")
    target.chmod(original_mode & ~0o222)
    return target


def _activate(release, store, installed, references, activation_id: str):
    plan = store.prepare_activation(
        installed.release_id,
        activation_id=activation_id,
        validation_receipts=references,
        created_at=NOW,
    )
    return plan, store.activate(
        plan,
        actor="adr0158-runner",
        note=f"activate {installed.release_id}",
        confirm=True,
    )


def release_audit(release, audit: Audit) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="adr0158-release-", dir="/tmp"
    ) as raw_root:
        root = Path(raw_root)
        store = release.ReleaseStore(
            root / "store",
            target="genos",
            code_package_root=REVISION_ROOT,
            clock=lambda: NOW,
        )
        release_a, refs_a, binding_a, lex_a, vec_a = install_release_bundle(
            release, store, "release-aa", seed="aa"
        )
        release_b, refs_b, binding_b, _lex_b, _vec_b = install_release_bundle(
            release, store, "release-bb", seed="bb"
        )
        proof_by_key = {row.key: row for row in binding_a.artifacts}
        manifest_index_by_kind = {row.kind: row for row in release_a.indexes}
        audit.check(
            "release.runtime-binding.physical-artifact-proofs",
            release_a.code_package_sha256
            == release.runtime_artifact_sha256(REVISION_ROOT)
            == binding_a.code_package_sha256
            and proof_by_key["main.state"].content_sha256
            == release_a.main.state_sha256
            and proof_by_key["source_set.content"].content_sha256
            == release_a.source_set.sha256
            and proof_by_key["semantics.content"].content_sha256
            == release_a.semantics.content_sha256
            and proof_by_key["index.lexical"].content_sha256
            == manifest_index_by_kind["lexical"].artifact_sha256
            and proof_by_key["index.vector"].content_sha256
            == manifest_index_by_kind["vector"].artifact_sha256,
            code_package_sha256=binding_a.code_package_sha256,
            artifact_sha256={
                key: row.content_sha256 for key, row in proof_by_key.items()
            },
        )

        self_attested_store = release.ReleaseStore(
            root / "self-attested-store",
            target="genos",
            code_package_root=REVISION_ROOT,
            clock=lambda: NOW,
        )
        self_attested, self_attested_refs, _binding, _lex, _vec = (
            install_release_bundle(
                release,
                self_attested_store,
                "self-attested",
                seed="self-attested",
                valid_provenance=False,
            )
        )
        audit.expect(
            "release.provenance.self-attested.rejected",
            release.ReleaseContractError,
            lambda: self_attested_store.prepare_activation(
                self_attested.release_id,
                activation_id="self-attested-activation",
                validation_receipts=self_attested_refs,
                created_at=NOW,
            ),
            "does not attest the verified runtime bytes",
        )

        bad_code_store = release.ReleaseStore(
            root / "bad-code-store",
            target="genos",
            code_package_root=REVISION_ROOT,
            clock=lambda: NOW,
        )
        bad_code_artifacts = _stage_release_artifacts(
            release,
            root / "bad-code-stage",
            "bad-code",
            seed="bad-code",
        )
        bad_code_blob, _lex, _vec = release_manifest(
            release,
            "bad-code",
            seed="bad-code",
            artifact_paths=bad_code_artifacts,
        )
        bad_code_blob.pop("manifest_sha256")
        bad_code_blob["code"]["package_sha256"] = "0" * 64
        bad_code_blob["manifest_sha256"] = release.release_from_mapping(
            bad_code_blob
        ).manifest_sha256
        bad_code_store.install_release(bad_code_blob)
        _runtime, bad_code_paths, bad_code_proofs = _materialize_release_runtime(
            bad_code_store, "bad-code", bad_code_artifacts
        )
        audit.expect(
            "release.code-package.self-attested-hash.rejected",
            release.ReleaseContractError,
            lambda: bad_code_store.install_runtime_binding(
                "bad-code",
                paths=bad_code_paths,
                artifact_paths=bad_code_proofs,
                created_at=NOW,
            ),
            "deployed code package bytes do not match",
        )
        tampered_code_root = root / "tampered-code-package"
        _copy_regular_tree(REVISION_ROOT, tampered_code_root)
        tampered_code_file = tampered_code_root / "service.py"
        tampered_code_file.write_bytes(
            stable_regular_bytes(tampered_code_file) + b"\n# injected tamper\n"
        )
        audit.expect(
            "release.code-package.bytes-tamper.rejected",
            release.ReleaseContractError,
            lambda: release.runtime_binding_from_mapping(
                binding_a.as_mapping(),
                release=release_a,
                runtime_root=store.runtime_root(release_a.release_id),
                code_package_root=tampered_code_root,
                verify_paths=True,
            ),
            "deployed code package fingerprint mismatch",
        )

        unsealed_store = release.ReleaseStore(
            root / "unsealed-store",
            target="genos",
            code_package_root=REVISION_ROOT,
            clock=lambda: NOW,
        )
        (
            unsealed,
            unsealed_root,
            unsealed_paths,
            unsealed_proofs,
            _lex,
            _vec,
        ) = _install_unbound_release_fixture(
            release, unsealed_store, "unsealed", seed="unsealed"
        )
        audit.expect(
            "release.runtime-binding.writable-tree.rejected",
            release.ReleaseContractError,
            lambda: release.create_runtime_binding(
                release=unsealed,
                runtime_root=unsealed_root,
                paths=unsealed_paths,
                artifact_paths=unsealed_proofs,
                code_package_root=REVISION_ROOT,
                created_at=NOW,
            ),
            "remains writable",
        )

        tamper_errors: dict[str, str] = {}
        for position, key in enumerate(_RELEASE_ARTIFACT_RELATIVE_PATHS, 1):
            tamper_store = release.ReleaseStore(
                root / f"tamper-{position}",
                target="genos",
                code_package_root=REVISION_ROOT,
                clock=lambda: NOW,
            )
            tamper_release, _refs, _binding, _lex, _vec = install_release_bundle(
                release,
                tamper_store,
                f"tamper-{position}",
                seed=f"tamper-{position}",
            )
            _tamper_sealed_runtime_artifact(
                tamper_store, tamper_release.release_id, key
            )
            error = audit.expect(
                f"release.runtime-artifact.{key}.tamper-rejected",
                release.ReleaseContractError,
                lambda current_store=tamper_store, current_id=tamper_release.release_id: (
                    current_store.load_runtime_binding(current_id)
                ),
            )
            tamper_errors[key] = str(error)

        index_by_kind = {item.kind: item for item in release_a.indexes}
        release.validate_index_build_fingerprint(
            index_by_kind["lexical"],
            lex_a,
            source_set=release_a.source_set,
            semantics=release_a.semantics,
        )
        release.validate_index_build_fingerprint(
            index_by_kind["vector"],
            vec_a,
            source_set=release_a.source_set,
            semantics=release_a.semantics,
            runtime_model_fingerprint=vec_a.embedding_model_fingerprint,
        )
        audit.check(
            "release.index.fingerprints",
            index_by_kind["lexical"].build_fingerprint == lex_a.build_fingerprint
            and index_by_kind["vector"].build_fingerprint == vec_a.build_fingerprint,
            lexical=lex_a.build_fingerprint,
            vector=vec_a.build_fingerprint,
        )
        audit.expect(
            "release.vector.model-mismatch.rejected",
            release.ReleaseContractError,
            lambda: release.validate_index_build_fingerprint(
                index_by_kind["vector"],
                vec_a,
                source_set=release_a.source_set,
                semantics=release_a.semantics,
                runtime_model_fingerprint="0" * 64,
            ),
            "runtime_model_fingerprint",
        )
        plan_a = store.prepare_activation(
            release_a.release_id,
            activation_id="activate-aa",
            validation_receipts=refs_a,
            created_at=NOW,
        )
        stale_b = store.prepare_activation(
            release_b.release_id,
            activation_id="activate-bb-stale",
            validation_receipts=refs_b,
            created_at=NOW,
        )
        active_a = store.activate(
            plan_a,
            actor="adr0158-runner",
            note="initial release",
            confirm=True,
        )
        audit.check(
            "release.activate.generation-1",
            active_a.pointer.generation == 1
            and active_a.pointer.release_id == release_a.release_id,
            pointer_sha256=active_a.pointer.pointer_sha256,
        )
        before_stale = store.load_active()
        audit.expect(
            "release.stale-cas.rejected",
            release.ReleaseContractError,
            lambda: store.activate(
                stale_b,
                actor="adr0158-runner",
                note="stale",
                confirm=True,
            ),
            "stale or incompatible",
        )
        audit.check(
            "release.stale-cas.pointer-preserved",
            store.load_active().pointer_sha256 == before_stale.pointer_sha256,
        )
        fresh_b, active_b = _activate(
            release, store, release_b, refs_b, "activate-bb-fresh"
        )
        audit.check(
            "release.activate.generation-2",
            active_b.pointer.generation == 2
            and active_b.pointer.previous_release_id == release_a.release_id,
            pointer_sha256=active_b.pointer.pointer_sha256,
        )
        rollback_plan = store.prepare_rollback(
            activation_id="rollback-aa",
            validation_receipts=refs_a,
            created_at=NOW,
        )
        audit.check(
            "release.rollback-plan.action-bound",
            rollback_plan.action == "rollback",
            plan_sha256=rollback_plan.plan_sha256,
        )
        before_misuse = store.load_active()
        audit.expect(
            "release.rollback-plan.activate-misuse.rejected",
            release.ReleaseContractError,
            lambda: store.activate(
                rollback_plan,
                actor="adr0158-runner",
                note="wrong method",
                confirm=True,
            ),
            "cannot be used",
        )
        audit.check(
            "release.rollback-plan.misuse-pointer-preserved",
            store.load_active().pointer_sha256 == before_misuse.pointer_sha256,
        )
        rolled_back = store.rollback(
            rollback_plan,
            actor="adr0158-runner",
            note="rollback to aa",
            confirm=True,
        )
        audit.check(
            "release.rollback.generation-3",
            rolled_back.pointer.generation == 3
            and rolled_back.pointer.release_id == release_a.release_id
            and rolled_back.pointer.previous_release_id == release_b.release_id,
            pointer_sha256=rolled_back.pointer.pointer_sha256,
        )
        tamper_plan = store.prepare_activation(
            release_b.release_id,
            activation_id="tampered-object-plan",
            validation_receipts=refs_b,
            created_at=NOW,
        )
        tampered_object = dataclasses.replace(tamper_plan, release_id=release_a.release_id)
        audit.expect(
            "release.dataclass-plan-hash.revalidated",
            release.ReleaseContractError,
            lambda: store.activate(
                tampered_object,
                actor="adr0158-runner",
                note="tampered dataclass",
                confirm=True,
            ),
            "plan_sha256 mismatch",
        )
        audit.expect(
            "release.explicit-confirm.required",
            release.ReleaseContractError,
            lambda: store.activate(
                tamper_plan,
                actor="adr0158-runner",
                note="no confirmation",
                confirm=False,
            ),
            "confirm=True",
        )
        duplicate_artifacts = _stage_release_artifacts(
            release,
            root / "duplicate-stage",
            release_a.release_id,
            seed="different-aa",
        )
        duplicate_blob, _lex, _vec = release_manifest(
            release,
            release_a.release_id,
            seed="different-aa",
            artifact_paths=duplicate_artifacts,
        )
        audit.expect(
            "release.id-immutability",
            release.ReleaseContractError,
            lambda: store.install_release(duplicate_blob),
            "another manifest",
        )
        pointer, active_release, active_binding = store.load_active_runtime()
        audit.check(
            "release.runtime-binding.active",
            pointer.release_id == active_release.release_id == release_a.release_id
            and active_binding.binding_sha256 == binding_a.binding_sha256,
            runtime_binding_sha256=active_binding.binding_sha256,
        )
        read_only_store = release.ReleaseStore(
            store.root,
            target="genos",
            code_package_root=REVISION_ROOT,
            read_only=True,
            clock=lambda: NOW,
        )
        read_pointer, read_release, read_binding = (
            read_only_store.load_active_runtime()
        )
        audit.check(
            "release.read-only.load-active-runtime",
            read_pointer.pointer_sha256 == pointer.pointer_sha256
            and read_release.manifest_sha256 == active_release.manifest_sha256
            and read_binding.binding_sha256 == active_binding.binding_sha256,
            pointer_sha256=read_pointer.pointer_sha256,
        )
        audit.expect(
            "release.read-only.install-rejected",
            release.ReleaseContractError,
            lambda: read_only_store.install_release(duplicate_blob),
            "forbids mutation",
        )
        audit.expect(
            "release.read-only.recovery-rejected",
            release.ReleaseContractError,
            read_only_store.recover_incomplete_activation,
            "forbids mutation",
        )
        event_names = [event["event"] for event in store.activation_events()]
        audit.check(
            "release.events.atomic-chain",
            event_names == ["prepared", "committed"] * 3,
            event_count=len(event_names),
        )

        crash_store = release.ReleaseStore(
            root / "crash-store",
            target="genos",
            code_package_root=REVISION_ROOT,
            clock=lambda: NOW,
        )
        crash_a, crash_refs_a, _binding, _lex, _vec = install_release_bundle(
            release, crash_store, "crash-aa", seed="crash-aa"
        )
        crash_b, crash_refs_b, _binding, _lex, _vec = install_release_bundle(
            release, crash_store, "crash-bb", seed="crash-bb"
        )
        _plan, crash_active_a = _activate(
            release, crash_store, crash_a, crash_refs_a, "crash-activate-aa"
        )
        crash_plan = crash_store.prepare_activation(
            crash_b.release_id,
            activation_id="crash-before-commit",
            validation_receipts=crash_refs_b,
            created_at=NOW,
        )
        real_append = crash_store._append_event

        def abrupt_commit(event: Mapping[str, Any]):
            if event.get("event") == "committed":
                raise SystemExit("injected abrupt stop")
            return real_append(event)

        crash_store._append_event = abrupt_commit
        audit.expect(
            "release.crash-window.injected",
            SystemExit,
            lambda: crash_store.activate(
                crash_plan,
                actor="adr0158-runner",
                note="crash injection",
                confirm=True,
            ),
            "abrupt stop",
        )
        audit.expect(
            "release.crash-window.fail-closed-before-recovery",
            release.ReleaseContractError,
            crash_store.load_active,
            "exactly one committed",
        )
        recovered_store = release.ReleaseStore(
            root / "crash-store",
            target="genos",
            code_package_root=REVISION_ROOT,
            clock=lambda: NOW,
        )
        recovery = recovered_store.recover_incomplete_activation()
        recovered = recovered_store.load_active()
        audit.check(
            "release.crash-window.restored-previous",
            recovery["recovered"]
            and recovered.pointer_sha256 == crash_active_a.pointer.pointer_sha256
            and recovered.release_id == crash_a.release_id,
            recovery=recovery,
        )

        io_store = release.ReleaseStore(
            root / "io-store",
            target="genos",
            code_package_root=REVISION_ROOT,
            clock=lambda: NOW,
        )
        io_a, io_refs_a, _binding, _lex, _vec = install_release_bundle(
            release, io_store, "io-aa", seed="io-aa"
        )
        io_b, io_refs_b, _binding, _lex, _vec = install_release_bundle(
            release, io_store, "io-bb", seed="io-bb"
        )
        _plan, io_active_a = _activate(
            release, io_store, io_a, io_refs_a, "io-activate-aa"
        )
        io_plan = io_store.prepare_activation(
            io_b.release_id,
            activation_id="io-activate-bb",
            validation_receipts=io_refs_b,
            created_at=NOW,
        )
        real_atomic = io_store._atomic_write
        injected = {"done": False}

        def fail_after_replace(path: Path, raw: bytes) -> None:
            real_atomic(path, raw)
            if path == io_store.active_path and not injected["done"]:
                injected["done"] = True
                raise OSError("injected post-replace fsync failure")

        io_store._atomic_write = fail_after_replace
        audit.expect(
            "release.post-replace-error.injected",
            OSError,
            lambda: io_store.activate(
                io_plan,
                actor="adr0158-runner",
                note="post replace failure",
                confirm=True,
            ),
            "post-replace",
        )
        audit.check(
            "release.post-replace-error.pointer-preserved",
            io_store.load_active().pointer_sha256
            == io_active_a.pointer.pointer_sha256,
        )

        event_store = release.ReleaseStore(
            root / "event-store",
            target="genos",
            code_package_root=REVISION_ROOT,
            clock=lambda: NOW,
        )
        event_a, event_refs_a, _binding, _lex, _vec = install_release_bundle(
            release, event_store, "event-aa", seed="event-aa"
        )
        event_b, event_refs_b, _binding, _lex, _vec = install_release_bundle(
            release, event_store, "event-bb", seed="event-bb"
        )
        _plan, _active = _activate(
            release,
            event_store,
            event_a,
            event_refs_a,
            "event-activate-aa",
        )
        event_plan = event_store.prepare_activation(
            event_b.release_id,
            activation_id="event-activate-bb",
            validation_receipts=event_refs_b,
            created_at=NOW,
        )
        real_event_append = event_store._append_event
        real_event_fsync_directory = event_store._fsync_directory
        event_failure = {"committing": False, "raised": False}

        def fail_commit_event_directory_fsync(path: Path) -> None:
            if (
                event_failure["committing"]
                and path == event_store.ledger_path
                and not event_failure["raised"]
            ):
                event_failure["raised"] = True
                raise OSError("injected commit-event post-replace fsync failure")
            real_event_fsync_directory(path)

        def append_in_commit_window(event: Mapping[str, Any]):
            committing = event.get("event") == "committed"
            event_failure["committing"] = committing
            try:
                return real_event_append(event)
            finally:
                event_failure["committing"] = False

        event_store._fsync_directory = fail_commit_event_directory_fsync
        event_store._append_event = append_in_commit_window
        event_active_b = event_store.activate(
            event_plan,
            actor="adr0158-runner",
            note="commit event fsync retry",
            confirm=True,
        )
        event_history = event_store.activation_events()
        latest_event = event_history[-1]
        audit.check(
            "release.commit-event.post-replace-fsync.reconciled",
            event_failure["raised"]
            and event_active_b.pointer.release_id == event_b.release_id
            and event_store.load_active().pointer_sha256
            == event_active_b.pointer.pointer_sha256
            and latest_event["event"] == "committed"
            and latest_event["activation_id"] == event_plan.activation_id
            and latest_event["after_pointer_sha256"]
            == event_active_b.pointer.pointer_sha256,
            pointer_sha256=event_active_b.pointer.pointer_sha256,
            event_sha256=latest_event["event_sha256"],
        )
        reused_activation = event_store.prepare_activation(
            event_a.release_id,
            activation_id=event_plan.activation_id,
            validation_receipts=event_refs_a,
            created_at=NOW,
        )
        audit.expect(
            "release.commit-event.duplicate-activation-id.rejected",
            release.ReleaseContractError,
            lambda: event_store.activate(
                reused_activation,
                actor="adr0158-runner",
                note="duplicate activation id",
                confirm=True,
            ),
            "already used",
        )
        return {
            "release_a_manifest_sha256": release_a.manifest_sha256,
            "release_b_manifest_sha256": release_b.manifest_sha256,
            "runtime_binding_a_sha256": binding_a.binding_sha256,
            "runtime_binding_b_sha256": binding_b.binding_sha256,
            "final_generation": rolled_back.pointer.generation,
            "final_release_id": rolled_back.pointer.release_id,
            "event_count": len(event_names),
            "crash_recovery": recovery,
            "runtime_tamper_errors": tamper_errors,
            "commit_event_reconciled": event_failure["raised"],
        }


def _clean_service_environment() -> None:
    for key in (
        "LAWRAG_RELEASE_STORE",
        "LAWRAG_RELEASE_REQUIRED",
        "LAWRAG_CODE_PACKAGE_ROOT",
        *RUNTIME_KEYS,
    ):
        os.environ.pop(key, None)


def _load_service(name: str):
    return load_module(name, SERVICE_MODULE)


def _stub_service_ops(service_module) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    fixture = types.SimpleNamespace(
        _rev=lambda: "isolated-fixture-rev",
        RECORD="isolated-record",
        _OPS_FILE=Path("/nonexistent/ops.jsonl"),
        _read_ops=lambda _path: [],
    )

    def checked_ops():
        service_module._require_ready()
        return fixture

    async def recorded_call(data: dict[str, Any]) -> dict[str, Any]:
        calls.append(dict(data))
        return {
            "status": 200,
            "ok": True,
            "json": {
                "method": str(data.get("method") or "GET").upper(),
                "path": data.get("path") or "/",
            },
        }

    service_module._ops = checked_ops
    service_module._do_call = recorded_call
    return calls


def service_scenario(name: str) -> dict[str, Any]:
    candidate = verify_candidate()
    _workspace, _catalog, release = install_isolated_candidate_modules()
    _clean_service_environment()
    if name == "legacy":
        service_module = _load_service("adr0158_service_legacy")
        _stub_service_ops(service_module)
        ping = asyncio.run(service_module.service({}, {"op": "ping"}))
        ok = (
            ping["ready"] is True
            and ping["release_mode"] == "legacy"
            and ping["release"] is None
            and service_module._RELEASE_BOOTSTRAP_ERROR is None
        )
        return {
            "scenario": name,
            "passed": ok,
            "ping": ping,
            "module_provenance": module_provenance(),
            "candidate": candidate,
        }
    if name == "invalid-strict":
        with tempfile.TemporaryDirectory(
            prefix="adr0158-service-invalid-", dir="/tmp"
        ) as raw:
            store = Path(raw) / "store"
            control_store = release.ReleaseStore(
                store,
                target="genos",
                code_package_root=REVISION_ROOT,
                clock=lambda: NOW,
            )
            control_store.load_active()
            control_store.active_path.write_text("{invalid\n", "utf-8")
            os.environ["LAWRAG_RELEASE_STORE"] = str(control_store.root.resolve())
            os.environ["LAWRAG_RELEASE_REQUIRED"] = "1"
            service_module = _load_service("adr0158_service_invalid")
            ping = asyncio.run(service_module.service({}, {"op": "ping"}))
            non_ping = asyncio.run(
                service_module.service({}, {"op": "call", "path": "/"})
            )
            legacy_defaults_absent = all(key not in os.environ for key in RUNTIME_KEYS)
            ok = (
                ping["ready"] is False
                and ping["release_mode"] == "release"
                and ping["release_error"] == "ReleaseContractError"
                and non_ping.get("op") == "call"
                and "bootstrap failed" in non_ping.get("error", "")
                and legacy_defaults_absent
            )
            return {
                "scenario": name,
                "passed": ok,
                "ping": ping,
                "non_ping": non_ping,
                "legacy_defaults_absent": legacy_defaults_absent,
                "module_provenance": module_provenance(),
                "candidate": candidate,
            }
    if name == "active-pin":
        with tempfile.TemporaryDirectory(
            prefix="adr0158-service-active-", dir="/tmp"
        ) as raw:
            store = release.ReleaseStore(
                Path(raw) / "store",
                target="genos",
                code_package_root=REVISION_ROOT,
                clock=lambda: NOW,
            )
            release_a, refs_a, binding_a, _lex, _vec = install_release_bundle(
                release, store, "service-aa", seed="service-aa"
            )
            _plan, active_a = _activate(
                release, store, release_a, refs_a, "service-activate-aa"
            )
            os.environ["LAWRAG_RELEASE_STORE"] = str(store.root.resolve())
            os.environ["LAWRAG_RELEASE_REQUIRED"] = "1"
            service_module = _load_service("adr0158_service_active_a")
            recorded_calls = _stub_service_ops(service_module)
            first = asyncio.run(service_module.service({}, {"op": "ping"}))
            serving_store_read_only = bool(
                service_module._RELEASE_STORE is not None
                and service_module._RELEASE_STORE.read_only
            )
            allowed_requests = (
                {"op": "call", "method": "GET", "path": "/v1/rag/search"},
                {
                    "op": "call",
                    "method": "GET",
                    "path": "/v1/knowledge/neighborhood",
                },
                {"op": "call", "method": "POST", "path": "/v1/rag/ask", "json": {}},
            )
            allowed_results = [
                asyncio.run(service_module.service({}, request))
                for request in allowed_requests
            ]
            blocked_requests = (
                {"op": "upload", "file_b64": "AA=="},
                {"op": "apply", "tar_b64": ""},
                {"op": "apply_from", "path": raw},
                {"op": "snapshot_to", "path": str(Path(raw) / "snapshot.tar.gz")},
                {"op": "report", "path": str(Path(raw) / "report.html")},
                {
                    "op": "call",
                    "method": "POST",
                    "path": "/v1/rag/compare",
                    "json": {},
                },
                {
                    "op": "call",
                    "method": "POST",
                    "path": "/v1/rag/general-search",
                    "json": {},
                },
                {
                    "op": "call",
                    "method": "POST",
                    "path": "/v1/rag/hybrid-search",
                    "json": {},
                },
                {
                    "op": "call",
                    "method": "POST",
                    "path": "/v1/review",
                    "json": {"text": "fixture"},
                },
                {
                    "op": "call",
                    "method": "GET",
                    "path": "/v1/ops/snapshot",
                },
                {
                    "op": "call",
                    "method": "GET",
                    "path": "/v1/ops/outbox/export",
                },
                {
                    "op": "call",
                    "method": "GET",
                    "path": "/v1/structure/document-id/pdf",
                },
                {
                    "op": "call",
                    "method": "GET",
                    "path": "/v1/structure/document-id/page/1",
                },
                {
                    "op": "call",
                    "method": "HEAD",
                    "path": "/v1/rag/search",
                },
                {
                    "op": "call",
                    "method": "OPTIONS",
                    "path": "/v1/rag/search",
                },
                {
                    "op": "call",
                    "method": "POST",
                    "path": "/v1/rag/feedback",
                    "json": {},
                },
                {
                    "op": "call",
                    "method": "POST",
                    "path": "/v1/structure/documents",
                    "json": {},
                },
                {
                    "op": "call",
                    "method": "PATCH",
                    "path": "/v1/structure/document",
                    "json": {},
                },
                {
                    "op": "call",
                    "method": "DELETE",
                    "path": "/v1/structure/document",
                },
                {
                    "op": "call",
                    "method": "POST",
                    "path": "/v1/ops/apply",
                    "json": {},
                },
                {
                    "op": "call",
                    "method": "POST",
                    "path": "/v1/review",
                    "json": {"text": "fixture", "asset": "document.pdf"},
                },
                {
                    "op": "call",
                    "method": "POST",
                    "path": "/v1/review",
                    "json": {"text": "fixture", "asset": "   "},
                },
                {
                    "op": "call",
                    "method": "POST",
                    "path": "/v1/review",
                    "body_b64": "AA==",
                },
            )
            blocked_results = [
                asyncio.run(service_module.service({}, request))
                for request in blocked_requests
            ]
            query_only_policy = (
                all(result.get("ok") is True for result in allowed_results)
                and all(
                    "PermissionError" in result.get("error", "")
                    for result in blocked_results
                )
                and len(recorded_calls) == len(allowed_requests)
            )
            release_b, refs_b, binding_b, _lex, _vec = install_release_bundle(
                release, store, "service-bb", seed="service-bb"
            )
            _plan, active_b = _activate(
                release, store, release_b, refs_b, "service-activate-bb"
            )
            second = asyncio.run(service_module.service({}, {"op": "ping"}))
            export_blocked = asyncio.run(
                service_module.service({}, {"op": "ls", "path": raw})
            )
            pinned = (
                first["release"]["release_id"] == release_a.release_id
                and second["release"] == first["release"]
                and first["release"]["runtime_binding_sha256"]
                == binding_a.binding_sha256
                and store.load_active().pointer_sha256 == active_b.pointer.pointer_sha256
                and "PermissionError" in export_blocked.get("error", "")
                and serving_store_read_only
            )
            tampered_runtime_path = _tamper_sealed_runtime_artifact(
                store, release_a.release_id, "main.state"
            )
            tampered_ping = asyncio.run(
                service_module.service({}, {"op": "ping"})
            )
            runtime_tamper_rejected = (
                tampered_ping.get("op") == "ping"
                and "ReleaseContractError" in tampered_ping.get("error", "")
                and "fingerprint" in tampered_ping.get("error", "")
            )
            for key in (*RUNTIME_KEYS, "LAWRAG_CODE_PACKAGE_ROOT"):
                os.environ.pop(key, None)
            fresh_module = _load_service("adr0158_service_active_b")
            _stub_service_ops(fresh_module)
            fresh = asyncio.run(fresh_module.service({}, {"op": "ping"}))
            expected_fresh_paths = binding_b.resolved_paths(
                store.runtime_root(release_b.release_id)
            )
            ok = (
                pinned
                and query_only_policy
                and runtime_tamper_rejected
                and fresh["release"]["release_id"] == release_b.release_id
                and fresh["release"]["runtime_binding_sha256"]
                == binding_b.binding_sha256
                and fresh["store"] == expected_fresh_paths["STRUCTURE_STORE"]
                and bool(
                    fresh_module._RELEASE_STORE is not None
                    and fresh_module._RELEASE_STORE.read_only
                )
                and active_a.pointer.generation == 1
                and active_b.pointer.generation == 2
            )
            return {
                "scenario": name,
                "passed": ok,
                "first_ping": first,
                "second_ping_same_process": second,
                "fresh_import_ping": fresh,
                "export_blocked": export_blocked,
                "query_only_policy": {
                    "passed": query_only_policy,
                    "allowed_results": allowed_results,
                    "blocked_results": blocked_results,
                    "forwarded_call_count": len(recorded_calls),
                },
                "serving_store_read_only": serving_store_read_only,
                "tampered_runtime_path": str(tampered_runtime_path),
                "tampered_runtime_ping": tampered_ping,
                "module_provenance": module_provenance(),
                "candidate": candidate,
            }
    raise ValueError(f"unknown service scenario: {name}")


def run_service_subprocesses() -> dict[str, Any]:
    results = []
    for scenario in ("legacy", "invalid-strict", "active-pin"):
        command = [
            sys.executable,
            "-I",
            "-S",
            str(Path(__file__).resolve()),
            "--service-scenario",
            scenario,
        ]
        env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "LANG", "LC_ALL", "TMPDIR", "TZ"}
        }
        completed = subprocess.run(
            command,
            cwd=tempfile.gettempdir(),
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"service scenario {scenario} failed rc={completed.returncode}: "
                f"{completed.stderr[-2000:]}"
            )
        value = json.loads(completed.stdout)
        if not value.get("passed"):
            raise AssertionError(f"service scenario failed: {scenario}")
        value["command"] = command
        value["returncode"] = completed.returncode
        results.append(value)
    return {
        "scenario_count": len(results),
        "passed": all(row["passed"] for row in results),
        "scenarios": results,
    }


def _decode_mount_field(value: str) -> str:
    return (
        value.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def _mount_metadata(path: Path) -> dict[str, Any] | None:
    mountinfo = Path("/proc/self/mountinfo")
    if not mountinfo.is_file():
        return None
    anchor = Path(os.path.abspath(path))
    while not anchor.exists() and anchor != anchor.parent:
        anchor = anchor.parent
    matches: list[tuple[int, dict[str, Any]]] = []
    try:
        # procfs reports size zero for this generated record, so the regular
        # file stability helper used for candidate bytes is intentionally not
        # applicable here.
        lines = mountinfo.read_text("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    for line in lines:
        left, separator, right = line.partition(" - ")
        if not separator:
            continue
        left_fields = left.split()
        right_fields = right.split()
        if len(left_fields) < 6 or len(right_fields) < 3:
            continue
        mount_point = Path(_decode_mount_field(left_fields[4]))
        try:
            anchor.relative_to(mount_point)
        except ValueError:
            continue
        matches.append((
            len(mount_point.parts),
            {
                "mount_point": str(mount_point),
                "filesystem_type": right_fields[0],
                "mount_source": _decode_mount_field(right_fields[1]),
                "mount_options": left_fields[5].split(","),
                "super_options": right_fields[2].split(","),
            },
        ))
    return max(matches, key=lambda item: item[0])[1] if matches else None


def _filesystem_metadata(path: Path) -> dict[str, Any]:
    requested = Path(os.path.abspath(path))
    anchor = requested
    while not anchor.exists() and anchor != anchor.parent:
        anchor = anchor.parent
    try:
        info = anchor.stat()
        values = os.statvfs(anchor)
    except OSError as exc:
        return {
            "requested_path": str(requested),
            "anchor_path": str(anchor),
            "error": type(exc).__name__,
            "errno": exc.errno,
        }
    return {
        "requested_path": str(requested),
        "anchor_path": str(anchor),
        "device": info.st_dev,
        "block_size": values.f_bsize,
        "fragment_size": values.f_frsize,
        "name_max": values.f_namemax,
        "flags": values.f_flag,
        "mount": _mount_metadata(anchor),
    }


def execution_metadata(output: Path) -> dict[str, Any]:
    original_argv = list(getattr(sys, "orig_argv", [sys.executable, *sys.argv]))
    filesystem_paths = {
        "workspace": ROOT,
        "output_parent": Path(os.path.abspath(output)).parent,
        "temporary_root": Path(tempfile.gettempdir()),
    }
    return {
        "command": {
            "orig_argv": original_argv,
            "argv": list(sys.argv),
            "shell_escaped": shlex.join(original_argv),
            "cwd": os.getcwd(),
        },
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "implementation": sys.implementation.name,
            "cache_tag": sys.implementation.cache_tag,
            "dont_write_bytecode": sys.dont_write_bytecode,
        },
        "kernel": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "filesystem": {
            name: _filesystem_metadata(path)
            for name, path in filesystem_paths.items()
        },
        "relevant_environment": {
            key: os.environ.get(key) for key in MONITORED_ENV_KEYS
        },
    }


def write_new_output(path: Path, raw: str) -> None:
    """Publish a run receipt once; never replace an existing path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--service-scenario",
        choices=("legacy", "invalid-strict", "active-pin"),
    )
    args = parser.parse_args()
    if args.service_scenario:
        try:
            result = service_scenario(args.service_scenario)
        except BaseException as exc:
            result = {
                "scenario": args.service_scenario,
                "passed": False,
                "error": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("passed") else 1
    if args.output is None:
        parser.error("--output is required")
    if os.path.lexists(args.output):
        parser.error(f"refusing to overwrite existing output: {args.output}")

    started = time.perf_counter()
    runner_sha = sha256_file(Path(__file__))
    metadata = execution_metadata(args.output)
    monitored_paths = monitored_production_paths()
    output_path = Path(os.path.abspath(args.output))
    for monitored_path in monitored_paths:
        if output_path == monitored_path:
            parser.error(f"output path is monitored production state: {args.output}")
        if monitored_path.is_dir():
            try:
                output_path.relative_to(monitored_path)
            except ValueError:
                pass
            else:
                parser.error(
                    f"output path is inside monitored production state: {args.output}"
                )
    monitored_environment_before = {
        key: os.environ.get(key) for key in MONITORED_ENV_KEYS
    }
    before = production_state(monitored_paths)
    candidate: dict[str, Any] | None = None
    audit = Audit()
    sections: dict[str, Any] = {}
    provenance: list[dict[str, Any]] = []
    failure: BaseException | None = None
    failure_traceback: str | None = None
    try:
        candidate = verify_candidate()
        workspace, catalog, release = install_isolated_candidate_modules()
        sections = {
            "schemas": schema_contract_audit(workspace, catalog, audit),
            "workspace": workspace_audit(workspace, audit),
            "catalog": catalog_audit(catalog, audit),
            "release": release_audit(release, audit),
            "service": run_service_subprocesses(),
        }
        provenance = module_provenance()
    except BaseException as exc:
        failure = exc
        failure_traceback = traceback.format_exc()

    after = production_state(monitored_paths)
    monitored_environment_after = {
        key: os.environ.get(key) for key in MONITORED_ENV_KEYS
    }
    monitoring_complete = all(
        not str(record.get("kind", "")).startswith("unreadable")
        for record in (*before.values(), *after.values())
    )
    production_paths_modified = before != after
    main_wiring_unchanged = (
        monitoring_complete
        and not production_paths_modified
        and monitored_environment_before == monitored_environment_after
    )
    audit.checks.append({
        "name": "isolation.production-monitor-complete",
        "passed": monitoring_complete,
        "details": {
            "before_unreadable": sorted(
                path
                for path, record in before.items()
                if str(record.get("kind", "")).startswith("unreadable")
            ),
            "after_unreadable": sorted(
                path
                for path, record in after.items()
                if str(record.get("kind", "")).startswith("unreadable")
            ),
        },
    })
    audit.checks.append({
        "name": "isolation.production-files-unchanged",
        "passed": not production_paths_modified,
        "details": {"before": before, "after": after},
    })
    audit.checks.append({
        "name": "isolation.production-environment-unchanged",
        "passed": monitored_environment_before == monitored_environment_after,
        "details": {
            "before": monitored_environment_before,
            "after": monitored_environment_after,
        },
    })
    try:
        expected_upstream = expected_upstream_hashes()
        observed_upstream_before = observed_upstream_hashes(before, expected_upstream)
        observed_upstream_after = observed_upstream_hashes(after, expected_upstream)
        upstream_unchanged = (
            observed_upstream_before == expected_upstream
            and observed_upstream_after == expected_upstream
        )
        upstream_details: dict[str, Any] = {
            "expected": expected_upstream,
            "before": observed_upstream_before,
            "after": observed_upstream_after,
        }
    except BaseException as exc:
        observed_upstream_before = {}
        observed_upstream_after = {}
        upstream_unchanged = False
        upstream_details = {
            "error": type(exc).__name__,
            "message": str(exc),
        }
        if failure is None:
            failure = exc
            failure_traceback = traceback.format_exc()
    audit.checks.append({
        "name": "isolation.upstream-still-baseline",
        "passed": upstream_unchanged,
        "details": upstream_details,
    })

    if failure is None and not main_wiring_unchanged:
        failure = AssertionError("monitored production state changed")
        failure_traceback = "monitored production path or environment comparison failed"
    if failure is None and not upstream_unchanged:
        failure = AssertionError("candidate upstream baseline changed")
        failure_traceback = "candidate upstream hash comparison failed"

    payload = {
        "schema_version": "adr0158-v2-runtime-activation-run-v1",
        "experiment_id": "ADR-0158-experiment-v1",
        "run_id": "run-012",
        "arm_id": "v2-candidate",
        "status": "passed" if failure is None else "failed",
        "candidate": candidate,
        "runner_path": Path(__file__).resolve().relative_to(ROOT).as_posix(),
        "runner_sha256": runner_sha,
        "execution": metadata,
        "inputs": {
            "workspace_fixture": "isolated-deterministic-v1",
            "dataset_fixture": "legacy-plus-public-restricted-v1",
            "release_fixture": "two-release-cas-rollback-v1",
            "service_fixture": "isolated-subprocess-v1",
        },
        "sections": sections,
        "checks": audit.checks,
        "summary": {
            "check_count": len(audit.checks),
            "passed_count": sum(row["passed"] for row in audit.checks),
            "failed_count": sum(not row["passed"] for row in audit.checks),
        },
        "module_provenance": provenance,
        "monitored_production_paths": [_shown_path(path) for path in monitored_paths],
        "production_hashes_before": observed_upstream_before,
        "production_hashes_after": observed_upstream_after,
        "production_state_before": before,
        "production_state_after": after,
        "monitored_environment_before": monitored_environment_before,
        "monitored_environment_after": monitored_environment_after,
        "production_paths_modified": production_paths_modified,
        "main_wiring_unchanged": main_wiring_unchanged,
        "llm_calls": 0,
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }
    if failure is not None:
        payload.update({
            "error": type(failure).__name__,
            "message": str(failure),
            "traceback": failure_traceback,
        })
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    write_new_output(args.output, raw)
    print(raw, end="")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
