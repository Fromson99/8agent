#!/usr/bin/env python3
"""One-shot deterministic audit of the ADR-0159 legacy MAIN chain bridge.

The runner verifies and explicitly loads one frozen research candidate, copies
the byte-locked ADR-0133 MAIN fixture below ``/tmp``, and writes one O_EXCL
receipt.  It never rewrites the installed MAIN files and never calls an LLM or
the network.
"""
from __future__ import annotations

import argparse
import contextlib
from copy import deepcopy
import hashlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import site
import socket
import stat
import sys
import sysconfig
import tempfile
import time
from types import ModuleType
from typing import Any, Callable, Mapping
import uuid


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ROOT = (
    ROOT / "lawrag/research/candidates/adr_0159/legacy-main-chain-bridge"
)
CANDIDATE_MANIFEST = CANDIDATE_ROOT / "candidate.json"
BASE_CANDIDATE_ROOT = (
    ROOT / "lawrag/research/candidates/adr_0158/v2-runtime-activation"
)
BASE_CANDIDATE_MANIFEST = BASE_CANDIDATE_ROOT / "candidate.json"
BASE_CANDIDATE_MANIFEST_SHA256 = (
    "7aa381545aaa472f7b58e066ccae31d62bb946859b5eaefc2e2f24dc2b2bd2b4"
)
BASE_REVISION_ID = "rev-012"
BASE_REVISION_SHA256 = (
    "ea8d5ce937d59f94cdd17092ef88a746441f044cf79a2dba7ce8f2facf69e597"
)
STATE_PATH = ROOT / "var/out/structure/main/pipeline.json"
LEDGER_PATH = ROOT / "var/out/structure/main/promotion_receipts.jsonl"
PLAN_PATH = (
    ROOT
    / "docs/adr/ADR-0133-internal-rule-atomic-compliance-main/artifacts"
    / "main-promotion-plan.json"
)
FIXTURE_LOCK = {
    STATE_PATH: (
        "fc77ae663db09ef5472d04d600446c9d47aa528ad3a37ccfee3cf1ccb780c7e2",
        1654,
    ),
    LEDGER_PATH: (
        "83ecb3e15ff2a4e0808554f8c91a255a52a709cf651ed7fcf310ada70c7a9307",
        1189,
    ),
    PLAN_PATH: (
        "d9dc1615a375ebe61442e2c29b8919fd0f6d6efb8a133c48862f45b989bd0604",
        2512,
    ),
}
MONITORED_PRODUCTION = (
    STATE_PATH,
    LEDGER_PATH,
    PLAN_PATH,
    ROOT / "lawrag/core/rag/main_promotion.py",
    ROOT / "lawrag/platform/release.py",
    ROOT / "scripts/rag_main_promotion.py",
    ROOT / "service.py",
)
EXPECTED_TARGETS = {
    "lawrag/core/rag/main_promotion.py",
    "lawrag/platform/release.py",
    "scripts/rag_main_promotion.py",
    "service.py",
}
RUN_ID = "run-006"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


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


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def stable_regular_bytes(path: Path) -> bytes:
    """Read one stable regular file without following a symbolic link."""

    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError(f"expected non-symlink regular file: {path}")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise RuntimeError("ADR-0159 audit requires O_NOFOLLOW")
    descriptor = os.open(path, os.O_RDONLY | nofollow)
    chunks: list[bytes] = []
    try:
        opened = os.fstat(descriptor)
        if _identity(before) != _identity(opened):
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
    if _identity(opened) != _identity(after) or len(raw) != after.st_size:
        raise RuntimeError(f"file changed while read: {path}")
    return raw


def file_record(path: Path) -> dict[str, Any]:
    raw = stable_regular_bytes(path)
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
    }


def production_records() -> list[dict[str, Any]]:
    return [file_record(path) for path in MONITORED_PRODUCTION]


def _safe_relative(raw: object) -> Path:
    text = str(raw or "")
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts or path.as_posix() != text:
        raise RuntimeError(f"unsafe candidate target path: {text!r}")
    return path


def verify_candidate(
    *,
    run_id: str,
    revision_id: str,
    revision_sha256: str,
    manifest_sha256: str,
) -> dict[str, Any]:
    """Verify the exact manifest, revision record, and closed revision tree."""

    if run_id != RUN_ID:
        raise RuntimeError(f"ADR-0159 runner is locked to {RUN_ID}")
    if not REVISION_ID_RE.fullmatch(revision_id):
        raise RuntimeError("revision ID is not canonical")
    if not SHA256_RE.fullmatch(revision_sha256):
        raise RuntimeError("revision SHA-256 is not canonical")
    if not SHA256_RE.fullmatch(manifest_sha256):
        raise RuntimeError("candidate manifest SHA-256 is not canonical")

    raw_manifest = stable_regular_bytes(CANDIDATE_MANIFEST)
    if sha256_bytes(raw_manifest) != manifest_sha256:
        raise RuntimeError("candidate manifest hash changed")
    manifest = json.loads(raw_manifest)
    if not isinstance(manifest, dict):
        raise RuntimeError("candidate manifest must be an object")
    expected_identity = {
        "schema_version": "adr-code-candidate-v2",
        "adr_id": "ADR-0159",
        "experiment_id": "ADR-0159-experiment-v1",
        "arm_id": "legacy-chain-bridge",
        "candidate_id": "legacy-main-chain-bridge",
        "status": "research-only",
        "production_loadable": False,
    }
    for key, expected in expected_identity.items():
        if manifest.get(key) != expected:
            raise RuntimeError(f"candidate manifest {key} changed")
    if run_id not in (manifest.get("run_ids") or []):
        raise RuntimeError(f"candidate is not linked to {RUN_ID}")

    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, list) or not manifest_files:
        raise RuntimeError("candidate manifest has no files")
    by_target: dict[str, Mapping[str, Any]] = {}
    by_snapshot: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for row in manifest_files:
        if not isinstance(row, Mapping):
            raise RuntimeError("candidate file row must be an object")
        target = _safe_relative(row.get("target_path")).as_posix()
        if target in by_target:
            raise RuntimeError(f"duplicate candidate target: {target}")
        snapshot = _safe_relative(row.get("snapshot_path")).as_posix()
        expected_snapshot = (
            CANDIDATE_ROOT / "snapshot" / target
        ).relative_to(ROOT).as_posix()
        if snapshot != expected_snapshot:
            raise RuntimeError(f"candidate snapshot/target mismatch: {snapshot}")
        if snapshot in by_snapshot:
            raise RuntimeError(f"duplicate candidate snapshot: {snapshot}")
        by_target[target] = row
        by_snapshot[snapshot] = (target, row)
    if set(by_target) != EXPECTED_TARGETS:
        raise RuntimeError("candidate target set changed")

    revisions = [
        row
        for row in (manifest.get("revisions") or [])
        if isinstance(row, Mapping) and row.get("revision_id") == revision_id
    ]
    if len(revisions) != 1:
        raise RuntimeError("candidate revision is absent or ambiguous")
    revision = revisions[0]
    if revision.get("revision_sha256") != revision_sha256:
        raise RuntimeError("candidate revision identity changed")
    core = {key: value for key, value in revision.items() if key != "revision_sha256"}
    if canonical_sha256(core) != revision_sha256:
        raise RuntimeError("candidate revision canonical hash is invalid")

    revision_root = (CANDIDATE_ROOT / "revisions" / revision_id / "snapshot").resolve()
    revision_rows = revision.get("files")
    if not isinstance(revision_rows, list) or not revision_rows:
        raise RuntimeError("candidate revision has no files")
    expected_files: dict[
        Path, tuple[str, Mapping[str, Any], Mapping[str, Any]]
    ] = {}
    revision_snapshots: set[str] = set()
    for row in revision_rows:
        if not isinstance(row, Mapping):
            raise RuntimeError("candidate revision file row must be an object")
        snapshot = _safe_relative(row.get("snapshot_path")).as_posix()
        if snapshot in revision_snapshots:
            raise RuntimeError(f"duplicate revision snapshot: {snapshot}")
        joined = by_snapshot.get(snapshot)
        if joined is None:
            raise RuntimeError(f"revision snapshot is not in manifest: {snapshot}")
        target, manifest_row = joined
        revision_snapshots.add(snapshot)
        frozen = Path(str(row.get("frozen_path") or ""))
        frozen = (ROOT / frozen).resolve() if not frozen.is_absolute() else frozen.resolve()
        try:
            frozen.relative_to(revision_root)
        except ValueError as exc:
            raise RuntimeError(f"frozen path escapes revision: {frozen}") from exc
        if frozen in expected_files:
            raise RuntimeError(f"duplicate frozen path: {frozen}")
        expected_files[frozen] = (target, manifest_row, row)
    if revision_snapshots != set(by_snapshot):
        raise RuntimeError("candidate manifest and revision snapshot sets differ")

    allowed_dirs = {revision_root}
    for path in expected_files:
        parent = path.parent
        while parent != revision_root:
            allowed_dirs.add(parent)
            parent = parent.parent
    seen: set[Path] = set()
    pending = [revision_root]
    while pending:
        directory = pending.pop()
        info = directory.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise RuntimeError(f"unsafe candidate revision directory: {directory}")
        if directory not in allowed_dirs:
            raise RuntimeError(f"unmanifested candidate directory: {directory}")
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                entry_info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(entry_info.st_mode):
                    raise RuntimeError(f"candidate revision contains symlink: {path}")
                if stat.S_ISDIR(entry_info.st_mode):
                    if path not in allowed_dirs:
                        raise RuntimeError(f"unmanifested candidate directory: {path}")
                    pending.append(path)
                elif stat.S_ISREG(entry_info.st_mode):
                    if path not in expected_files:
                        raise RuntimeError(f"unmanifested candidate file: {path}")
                    seen.add(path)
                else:
                    raise RuntimeError(f"candidate revision has special entry: {path}")
    if seen != set(expected_files):
        raise RuntimeError("candidate revision is missing manifested files")

    verified_files: list[dict[str, Any]] = []
    revision_targets: set[str] = set()
    for path, joined in sorted(expected_files.items(), key=lambda item: str(item[0])):
        target, manifest_row, row = joined
        raw = stable_regular_bytes(path)
        digest = sha256_bytes(raw)
        revision_targets.add(target)
        if path != revision_root / target:
            raise RuntimeError(f"frozen target path mismatch: {target}")
        if any(
            candidate != digest
            for candidate in (
                row.get("snapshot_sha256"),
                manifest_row.get("snapshot_sha256"),
            )
        ) or any(
            candidate != len(raw)
            for candidate in (row.get("bytes"), manifest_row.get("bytes"))
        ):
            raise RuntimeError(f"candidate file hash/size mismatch: {target}")
        verified_files.append(
            {"path": path.relative_to(ROOT).as_posix(), "sha256": digest, "bytes": len(raw)}
        )
    if revision_targets != EXPECTED_TARGETS:
        raise RuntimeError("candidate revision target set changed")
    return {
        "manifest": manifest,
        "manifest_sha256": manifest_sha256,
        "revision": revision,
        "revision_id": revision_id,
        "revision_sha256": revision_sha256,
        "revision_root": revision_root,
        "files": verified_files,
        "frozen_by_target": {
            target: path
            for path, (target, _manifest_row, _revision_row) in expected_files.items()
        },
    }


def verify_base_candidate() -> dict[str, Any]:
    """Verify the exact ADR-0158 rev-012 dependency snapshot."""

    raw_manifest = stable_regular_bytes(BASE_CANDIDATE_MANIFEST)
    if sha256_bytes(raw_manifest) != BASE_CANDIDATE_MANIFEST_SHA256:
        raise RuntimeError("ADR-0158 candidate manifest hash changed")
    manifest = json.loads(raw_manifest)
    if not isinstance(manifest, dict):
        raise RuntimeError("ADR-0158 candidate manifest must be an object")
    identity = {
        "schema_version": "adr-code-candidate-v2",
        "adr_id": "ADR-0158",
        "experiment_id": "ADR-0158-experiment-v1",
        "arm_id": "v2-candidate",
        "candidate_id": "v2-runtime-activation",
        "status": "research-only",
        "production_loadable": False,
    }
    for key, expected in identity.items():
        if manifest.get(key) != expected:
            raise RuntimeError(f"ADR-0158 candidate {key} changed")

    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("ADR-0158 candidate manifest has no files")
    by_snapshot: dict[str, tuple[str, Mapping[str, Any]]] = {}
    targets: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise RuntimeError("ADR-0158 candidate file row must be an object")
        target = _safe_relative(row.get("target_path")).as_posix()
        snapshot = _safe_relative(row.get("snapshot_path")).as_posix()
        expected_snapshot = (
            BASE_CANDIDATE_ROOT / "snapshot" / target
        ).relative_to(ROOT).as_posix()
        if snapshot != expected_snapshot:
            raise RuntimeError(f"ADR-0158 snapshot/target mismatch: {snapshot}")
        if target in targets or snapshot in by_snapshot:
            raise RuntimeError("ADR-0158 candidate file identity is duplicated")
        targets.add(target)
        by_snapshot[snapshot] = (target, row)

    revisions = [
        row
        for row in (manifest.get("revisions") or [])
        if isinstance(row, Mapping) and row.get("revision_id") == BASE_REVISION_ID
    ]
    if len(revisions) != 1:
        raise RuntimeError("ADR-0158 rev-012 is absent or ambiguous")
    revision = revisions[0]
    if revision.get("revision_sha256") != BASE_REVISION_SHA256:
        raise RuntimeError("ADR-0158 rev-012 identity changed")
    core = {key: value for key, value in revision.items() if key != "revision_sha256"}
    if canonical_sha256(core) != BASE_REVISION_SHA256:
        raise RuntimeError("ADR-0158 rev-012 canonical hash is invalid")

    revision_root = (
        BASE_CANDIDATE_ROOT / "revisions" / BASE_REVISION_ID / "snapshot"
    ).resolve()
    revision_rows = revision.get("files")
    if not isinstance(revision_rows, list) or not revision_rows:
        raise RuntimeError("ADR-0158 rev-012 has no files")
    joined_by_path: dict[
        Path, tuple[str, Mapping[str, Any], Mapping[str, Any]]
    ] = {}
    seen_snapshots: set[str] = set()
    for revision_row in revision_rows:
        if not isinstance(revision_row, Mapping):
            raise RuntimeError("ADR-0158 revision file row must be an object")
        snapshot = _safe_relative(revision_row.get("snapshot_path")).as_posix()
        if snapshot in seen_snapshots:
            raise RuntimeError(f"duplicate ADR-0158 revision snapshot: {snapshot}")
        joined = by_snapshot.get(snapshot)
        if joined is None:
            raise RuntimeError(f"ADR-0158 revision snapshot is unmanifested: {snapshot}")
        target, manifest_row = joined
        frozen = Path(str(revision_row.get("frozen_path") or ""))
        frozen = (ROOT / frozen).resolve() if not frozen.is_absolute() else frozen.resolve()
        if frozen != revision_root / target:
            raise RuntimeError(f"ADR-0158 frozen target path mismatch: {target}")
        if frozen in joined_by_path:
            raise RuntimeError(f"duplicate ADR-0158 frozen path: {frozen}")
        seen_snapshots.add(snapshot)
        joined_by_path[frozen] = (target, manifest_row, revision_row)
    if seen_snapshots != set(by_snapshot):
        raise RuntimeError("ADR-0158 manifest and rev-012 file sets differ")

    allowed_dirs = {revision_root}
    for path in joined_by_path:
        parent = path.parent
        while parent != revision_root:
            allowed_dirs.add(parent)
            parent = parent.parent
    seen_files: set[Path] = set()
    pending = [revision_root]
    while pending:
        directory = pending.pop()
        info = directory.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise RuntimeError(f"unsafe ADR-0158 revision directory: {directory}")
        if directory not in allowed_dirs:
            raise RuntimeError(f"unmanifested ADR-0158 directory: {directory}")
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                entry_info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(entry_info.st_mode):
                    raise RuntimeError(f"ADR-0158 revision contains symlink: {path}")
                if stat.S_ISDIR(entry_info.st_mode):
                    if path not in allowed_dirs:
                        raise RuntimeError(f"unmanifested ADR-0158 directory: {path}")
                    pending.append(path)
                elif stat.S_ISREG(entry_info.st_mode):
                    if path not in joined_by_path:
                        raise RuntimeError(f"unmanifested ADR-0158 file: {path}")
                    seen_files.add(path)
                else:
                    raise RuntimeError(f"ADR-0158 revision has special entry: {path}")
    if seen_files != set(joined_by_path):
        raise RuntimeError("ADR-0158 rev-012 is missing manifested files")

    verified: list[dict[str, Any]] = []
    frozen_by_target: dict[str, Path] = {}
    for path, joined in sorted(joined_by_path.items(), key=lambda item: str(item[0])):
        target, manifest_row, revision_row = joined
        raw = stable_regular_bytes(path)
        digest = sha256_bytes(raw)
        if any(
            expected != digest
            for expected in (
                manifest_row.get("snapshot_sha256"),
                revision_row.get("snapshot_sha256"),
            )
        ) or any(
            expected != len(raw)
            for expected in (manifest_row.get("bytes"), revision_row.get("bytes"))
        ):
            raise RuntimeError(f"ADR-0158 rev-012 file changed: {target}")
        frozen_by_target[target] = path
        verified.append(
            {"path": path.relative_to(ROOT).as_posix(), "sha256": digest, "bytes": len(raw)}
        )
    return {
        "manifest_sha256": BASE_CANDIDATE_MANIFEST_SHA256,
        "revision_id": BASE_REVISION_ID,
        "revision_sha256": BASE_REVISION_SHA256,
        "revision_root": revision_root,
        "files": verified,
        "frozen_by_target": frozen_by_target,
    }


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise RuntimeError("ADR-0159 audit requires O_NOFOLLOW")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o400)
    try:
        total = 0
        while total < len(raw):
            total += os.write(descriptor, raw[total:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def build_overlay(
    temp_root: Path,
    base: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> tuple[Path, list[dict[str, Any]]]:
    """Materialize rev-012 plus exactly three ADR-0159 overrides."""

    overlay = temp_root / "code"
    base_files = dict(base["frozen_by_target"])
    overrides = dict(candidate["frozen_by_target"])
    if set(overrides) != EXPECTED_TARGETS:
        raise RuntimeError("ADR-0159 override set changed")
    if set(overrides) - set(base_files) != {"scripts/rag_main_promotion.py"}:
        raise RuntimeError("ADR-0159 has an unexpected rev-012 overlay delta")
    expected: dict[Path, tuple[str, str, int]] = {}
    records: list[dict[str, Any]] = []
    for target in sorted(set(base_files) | set(overrides)):
        source = overrides[target] if target in overrides else base_files[target]
        raw = stable_regular_bytes(source)
        destination = overlay / target
        _write_exclusive(destination, raw)
        digest = sha256_bytes(raw)
        origin = "ADR-0159" if target in overrides else "ADR-0158-rev-012"
        expected[destination] = (target, digest, len(raw))
        records.append(
            {
                "target_path": target,
                "origin": origin,
                "sha256": digest,
                "bytes": len(raw),
            }
        )

    allowed_dirs = {overlay}
    for path in expected:
        parent = path.parent
        while parent != overlay:
            allowed_dirs.add(parent)
            parent = parent.parent
    seen: set[Path] = set()
    pending = [overlay]
    while pending:
        directory = pending.pop()
        info = directory.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise RuntimeError(f"unsafe overlay directory: {directory}")
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                entry_info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(entry_info.st_mode):
                    raise RuntimeError(f"overlay contains symlink: {path}")
                if stat.S_ISDIR(entry_info.st_mode):
                    if path not in allowed_dirs:
                        raise RuntimeError(f"overlay has unexpected directory: {path}")
                    pending.append(path)
                elif stat.S_ISREG(entry_info.st_mode):
                    row = expected.get(path)
                    if row is None:
                        raise RuntimeError(f"overlay has unexpected file: {path}")
                    _target, digest, size = row
                    raw = stable_regular_bytes(path)
                    if sha256_bytes(raw) != digest or len(raw) != size:
                        raise RuntimeError(f"overlay copy verification failed: {path}")
                    seen.add(path)
                else:
                    raise RuntimeError(f"overlay has special entry: {path}")
    if seen != set(expected):
        raise RuntimeError("overlay is missing frozen files")
    return overlay, records


def isolate_import_path(overlay_root: Path) -> list[str]:
    """Keep stdlib/site-packages but remove every repository import path."""

    dependency_roots = {
        Path(value).resolve()
        for value in (
            *site.getsitepackages(),
            *(sysconfig.get_paths().get(key, "") for key in (
                "stdlib", "platstdlib", "purelib", "platlib"
            )),
        )
        if value
    }
    safe: list[str] = []
    for raw in sys.path:
        if not raw:
            continue
        path = Path(raw).resolve()
        try:
            path.relative_to(ROOT)
        except ValueError:
            safe.append(raw)
            continue
        if any(path == root or root in path.parents for root in dependency_roots):
            safe.append(raw)
    sys.path[:] = [str(overlay_root), *safe]
    importlib.invalidate_caches()
    return safe


def overlay_module_provenance(overlay_root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for name in sorted(
        key
        for key in sys.modules
        if key in {"service", "adr0159_overlay_main_cli"}
        or key == "lawrag"
        or key.startswith("lawrag.")
    ):
        module = sys.modules[name]
        raw_file = getattr(module, "__file__", None)
        if not raw_file:
            raise RuntimeError(f"repository module has no provenance: {name}")
        path = Path(raw_file).resolve()
        try:
            relative = path.relative_to(overlay_root)
        except ValueError as exc:
            raise RuntimeError(f"repository import escaped overlay: {name}") from exc
        rows.append({"module": name, "path": relative.as_posix()})
    names = {row["module"] for row in rows}
    if not {"lawrag", "service", "adr0159_overlay_main_cli"}.issubset(names):
        raise RuntimeError("overlay provenance is incomplete")
    return rows


def load_overlay_modules(
    overlay_root: Path,
) -> tuple[ModuleType, ModuleType, ModuleType, ModuleType]:
    preloaded = sorted(
        name
        for name in sys.modules
        if name == "service" or name == "lawrag" or name.startswith("lawrag.")
    )
    if preloaded:
        raise RuntimeError("repository modules were preloaded: " + ", ".join(preloaded))
    service_module = importlib.import_module("service")
    module = importlib.import_module("lawrag.core.rag.main_promotion")
    required = {
        "historical_default_state",
        "effective_runtime_profile",
        "normalize_legacy_apply_receipt",
        "normalize_transition_receipts",
        "build_transition_chain",
        "validate_transition_chain",
        "validate_transition_receipt",
        "validate_runtime_promotion_plan",
        "prepare_plan",
        "apply_plan",
        "rollback",
        "read_receipts",
        "fingerprint",
    }
    missing = sorted(name for name in required if not callable(getattr(module, name, None)))
    if missing:
        raise RuntimeError("candidate bridge APIs missing: " + ", ".join(missing))
    release_module = importlib.import_module("lawrag.platform.release")
    if not callable(
        getattr(release_module, "build_main_transition_chain_for_release", None)
    ):
        raise RuntimeError("candidate release bridge API is missing")
    cli_path = overlay_root / "scripts/rag_main_promotion.py"
    cli_spec = importlib.util.spec_from_file_location(
        "adr0159_overlay_main_cli", cli_path
    )
    if cli_spec is None or cli_spec.loader is None:
        raise RuntimeError("cannot load overlay MAIN CLI")
    cli_module = importlib.util.module_from_spec(cli_spec)
    sys.modules["adr0159_overlay_main_cli"] = cli_module
    cli_spec.loader.exec_module(cli_module)
    expected = {
        "service": overlay_root / "service.py",
        "lawrag.core.rag.main_promotion": (
            overlay_root / "lawrag/core/rag/main_promotion.py"
        ),
        "lawrag.platform.release": overlay_root / "lawrag/platform/release.py",
        "adr0159_overlay_main_cli": overlay_root / "scripts/rag_main_promotion.py",
    }
    for name, path in expected.items():
        loaded = sys.modules.get(name)
        if loaded is None or Path(str(getattr(loaded, "__file__", ""))).resolve() != path:
            raise RuntimeError(f"overlay module provenance mismatch: {name}")
    return module, release_module, service_module, cli_module


def build_release_chain(
    release_module: ModuleType,
    main_module: ModuleType,
    *,
    main_state: Mapping[str, Any],
    receipts: list[Mapping[str, Any]],
    plan_paths: list[Path],
) -> dict[str, Any]:
    """Inject only the verified candidate MAIN module into the release helper."""

    name = "lawrag.core.rag.main_promotion"
    sentinel = object()
    previous = sys.modules.get(name, sentinel)
    sys.modules[name] = main_module
    try:
        return release_module.build_main_transition_chain_for_release(
            main_state=main_state,
            receipts=receipts,
            legacy_promotion_plan_paths=plan_paths,
        )
    finally:
        if previous is sentinel:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def load_fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    raw_by_path: dict[Path, bytes] = {}
    for path, (expected_sha, expected_bytes) in FIXTURE_LOCK.items():
        raw = stable_regular_bytes(path)
        actual_sha = sha256_bytes(raw)
        if actual_sha != expected_sha or len(raw) != expected_bytes:
            raise RuntimeError(f"frozen ADR-0133 fixture changed: {path}")
        raw_by_path[path] = raw
        records.append(
            {"path": path.relative_to(ROOT).as_posix(), "sha256": actual_sha, "bytes": len(raw)}
        )
    state = json.loads(raw_by_path[STATE_PATH])
    plan = json.loads(raw_by_path[PLAN_PATH])
    lines = [line for line in raw_by_path[LEDGER_PATH].splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError("ADR-0133 fixture must contain exactly one legacy receipt")
    receipt = json.loads(lines[0])
    if not all(isinstance(value, dict) for value in (state, plan, receipt)):
        raise RuntimeError("ADR-0133 fixture values must be objects")
    return state, receipt, plan, records


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def accepted_source_fixture(root: Path) -> tuple[Path, Path]:
    adr = root / "ADR-9999-deterministic-followup"
    manifest_path = adr / "실험/manifest.json"
    readme = """---
status: Accepted
main_wiring: promotion-candidate
---

# Deterministic ADR-0159 follow-up fixture
"""
    (adr / "README.md").parent.mkdir(parents=True, exist_ok=True)
    (adr / "README.md").write_text(readme, encoding="utf-8")
    write_json(
        manifest_path,
        {
            "adr_id": "ADR-9999",
            "experiment_id": "ADR-9999-experiment-v1",
            "decision_eligible": True,
            "in_sample": False,
            "reservation": {"status": "completed"},
            "design": {"arms": [{"id": "followup"}]},
            "results": {"status": "complete"},
        },
    )
    validation = root / "validation.json"
    write_json(validation, {"schema_version": "deterministic-validation-v1", "passed": True})
    return manifest_path, validation


class _Sequence:
    def __init__(self, values: list[Any]) -> None:
        self._values = iter(values)

    def __call__(self) -> Any:
        return next(self._values)


def expect_error(label: str, call: Callable[[], object]) -> str:
    try:
        call()
    except (ValueError, RuntimeError) as exc:
        return str(exc)
    raise AssertionError(f"{label} was unexpectedly accepted")


def expect_chain_rejection(
    module: ModuleType,
    label: str,
    chain: Mapping[str, Any],
    state: Mapping[str, Any],
) -> list[str]:
    errors = module.validate_transition_chain(chain, state)
    if not errors:
        raise AssertionError(f"{label} tamper was unexpectedly accepted")
    return [str(value) for value in errors]


def _invoke_cli(cli_module: ModuleType, arguments: list[str]) -> dict[str, Any]:
    previous = list(sys.argv)
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        sys.argv = [str(Path(cli_module.__file__).resolve()), *arguments]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli_module.main()
    finally:
        sys.argv = previous
    return {"code": code, "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}


def audit_cli_forwarding(
    cli_module: ModuleType,
    module: ModuleType,
    root: Path,
    legacy_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Prove the standard CLI forwards only explicitly supplied plan objects."""

    root.mkdir(parents=True, exist_ok=True)
    dispatch_plan = root / "dispatch-plan.json"
    bad_plan = root / "bad-plan.json"
    write_json(dispatch_plan, {"schema_version": "dispatch-fixture-v1"})
    write_json(bad_plan, ["not", "an", "object"])
    originals = {
        name: getattr(module, name)
        for name in (
            "apply_plan", "rollback", "read_receipts", "load_state",
            "runtime_provenance",
        )
    }
    calls: list[dict[str, Any]] = []

    def plans_from(kwargs: Mapping[str, Any], command: str) -> tuple[dict[str, Any], ...]:
        plans = kwargs.get("legacy_promotion_plans")
        if not isinstance(plans, tuple):
            raise AssertionError(f"{command} CLI did not forward a tuple")
        calls.append(
            {
                "command": command,
                "count": len(plans),
                "sha256": [module.fingerprint(plan) for plan in plans],
            }
        )
        if not plans:
            raise ValueError("explicit legacy promotion plan required")
        if plans != (dict(legacy_plan),):
            raise AssertionError(f"{command} CLI forwarded another plan")
        return plans

    def apply_spy(_plan: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
        plans_from(kwargs, "apply")
        return {"command": "apply", "forwarded": True}

    def rollback_spy(_promotion_id: str, **kwargs: Any) -> dict[str, Any]:
        plans_from(kwargs, "rollback")
        return {"command": "rollback", "forwarded": True}

    def receipts_spy(**kwargs: Any) -> list[dict[str, Any]]:
        plans_from(kwargs, "status")
        return []

    module.apply_plan = apply_spy
    module.rollback = rollback_spy
    module.read_receipts = receipts_spy
    module.load_state = lambda: {"generation": 1}
    module.runtime_provenance = lambda: {"generation": 1}
    fallback_keys = (
        "RAG_MAIN_LEGACY_PROMOTION_PLAN",
        "LAWRAG_LEGACY_PROMOTION_PLAN",
        "RAG_MAIN_PROMOTION_PLAN",
    )
    previous_env = {key: os.environ.get(key) for key in fallback_keys}
    for key in fallback_keys:
        os.environ[key] = str(PLAN_PATH)
    commands = {
        "status": ["status"],
        "apply": [
            "apply", "--plan", str(dispatch_plan), "--actor", "audit",
            "--approval-note", "audit", "--confirm-main",
        ],
        "rollback": [
            "rollback", "--promotion-id", "fixture-promotion", "--actor", "audit",
            "--note", "audit", "--confirm-main",
        ],
    }
    results: dict[str, Any] = {}
    try:
        for command, base_arguments in commands.items():
            explicit = _invoke_cli(
                cli_module,
                [*base_arguments, "--legacy-promotion-plan", str(PLAN_PATH)],
            )
            if explicit["code"] != 0:
                raise AssertionError(f"{command} explicit CLI forwarding failed")
            missing = _invoke_cli(cli_module, list(base_arguments))
            if missing["code"] != 2:
                raise AssertionError(f"{command} missing legacy plan was accepted")
            before_loader_negatives = len(calls)
            duplicate = _invoke_cli(
                cli_module,
                [
                    *base_arguments,
                    "--legacy-promotion-plan", str(PLAN_PATH),
                    "--legacy-promotion-plan", str(PLAN_PATH),
                ],
            )
            non_object = _invoke_cli(
                cli_module,
                [*base_arguments, "--legacy-promotion-plan", str(bad_plan)],
            )
            if duplicate["code"] != 2 or non_object["code"] != 2:
                raise AssertionError(f"{command} accepted duplicate/bad legacy plan")
            if len(calls) != before_loader_negatives:
                raise AssertionError(f"{command} dispatched after plan loader rejection")
            results[command] = {
                "explicit_forwarded": True,
                "missing_rejected_without_env_fallback": True,
                "duplicate_rejected": True,
                "non_object_rejected": True,
                "missing_error": missing["stderr"].strip(),
                "duplicate_error": duplicate["stderr"].strip(),
                "non_object_error": non_object["stderr"].strip(),
            }
    finally:
        for name, value in originals.items():
            setattr(module, name, value)
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    expected_calls = [
        (command, count)
        for command in ("status", "apply", "rollback")
        for count in (1, 0)
    ]
    if [(row["command"], row["count"]) for row in calls] != expected_calls:
        raise AssertionError("CLI explicit/missing forwarding sequence changed")
    return {
        "commands": results,
        "forwarded_calls": calls,
        "explicit_plan_sha256": module.fingerprint(legacy_plan),
        "environment_fallback_disabled": True,
    }


def run_audit(
    module: ModuleType,
    release_module: ModuleType,
    cli_module: ModuleType,
    temp_root: Path,
) -> dict[str, Any]:
    legacy_state, legacy_receipt, legacy_plan, fixture_records = load_fixture()
    state_before = deepcopy(legacy_state)
    receipt_before = deepcopy(legacy_receipt)
    plan_before = deepcopy(legacy_plan)
    cli_audit = audit_cli_forwarding(
        cli_module, module, temp_root / "cli", legacy_plan
    )

    if legacy_receipt.get("schema_version") != "main-rag-promotion-receipt-v1":
        raise AssertionError("installed receipt is not the frozen legacy v1 fixture")
    if legacy_receipt.get("before_state") != module.historical_default_state():
        raise AssertionError("legacy receipt does not start at historical canonical root")
    if "runtime_profile" in legacy_state or "runtime_profile" in legacy_receipt["before_state"]:
        raise AssertionError("legacy fixture unexpectedly contains runtime_profile")
    if module.effective_runtime_profile(legacy_state) != module.PIPELINE_ID:
        raise AssertionError("legacy state runtime profile fallback changed")

    strict_errors = module.validate_transition_receipt(legacy_receipt, legacy_state)
    if not strict_errors:
        raise AssertionError("baseline v2-only receipt validator accepted legacy v1")
    no_plan_error = expect_error(
        "implicit legacy plan discovery",
        lambda: module.build_transition_chain([legacy_receipt], legacy_state),
    )
    duplicate_plan_error = expect_error(
        "ambiguous legacy plan candidates",
        lambda: module.build_transition_chain(
            [legacy_receipt],
            legacy_state,
            legacy_promotion_plans=[legacy_plan, deepcopy(legacy_plan)],
        ),
    )
    release_no_plan_error = expect_error(
        "release implicit legacy plan discovery",
        lambda: build_release_chain(
            release_module,
            module,
            main_state=legacy_state,
            receipts=[legacy_receipt],
            plan_paths=[],
        ),
    )
    release_duplicate_path_error = expect_error(
        "release duplicate legacy plan paths",
        lambda: build_release_chain(
            release_module,
            module,
            main_state=legacy_state,
            receipts=[legacy_receipt],
            plan_paths=[PLAN_PATH, PLAN_PATH],
        ),
    )

    normalized = module.normalize_legacy_apply_receipt(
        legacy_receipt, legacy_plan, legacy_state
    )
    expected_normalized = deepcopy(legacy_receipt)
    expected_normalized["schema_version"] = module.RECEIPT_SCHEMA
    expected_normalized["promotion_plan"] = legacy_plan
    expected_normalized["legacy_receipt"] = legacy_receipt
    expected_normalized["legacy_receipt_sha256"] = module.fingerprint(
        legacy_receipt
    )
    if normalized != expected_normalized:
        raise AssertionError("legacy normalization changed fields beyond schema/embedded plan")
    if module.fingerprint(legacy_plan) != legacy_receipt.get("plan_sha256"):
        raise AssertionError("exact ADR-0133 plan does not match legacy receipt")
    apply_errors = module.validate_transition_receipt(normalized, legacy_state)
    plan_errors = module.validate_runtime_promotion_plan(
        legacy_plan, normalized, legacy_state
    )
    if apply_errors or plan_errors:
        raise AssertionError(
            "normalized legacy receipt is invalid: "
            + "; ".join([*apply_errors, *plan_errors])
        )
    normalized_rows = module.normalize_transition_receipts(
        [legacy_receipt], legacy_state, legacy_promotion_plans=[legacy_plan]
    )
    if normalized_rows != [normalized]:
        raise AssertionError("batch normalization differs from single normalization")
    legacy_chain = module.build_transition_chain(
        [legacy_receipt], legacy_state, legacy_promotion_plans=[legacy_plan]
    )
    if legacy_chain != module.build_transition_chain(
        [legacy_receipt],
        legacy_state,
        legacy_promotion_plans=[deepcopy(legacy_plan)],
    ):
        raise AssertionError("legacy canonical chain is not deterministic")
    release_chain = build_release_chain(
        release_module,
        module,
        main_state=legacy_state,
        receipts=[legacy_receipt],
        plan_paths=[PLAN_PATH],
    )
    if release_chain != legacy_chain:
        raise AssertionError("release bridge differs from canonical MAIN bridge")
    chain_errors = module.validate_transition_chain(legacy_chain, legacy_state)
    if chain_errors:
        raise AssertionError("legacy canonical replay failed: " + "; ".join(chain_errors))
    if (
        legacy_chain.get("root_state_sha256")
        != module.fingerprint(module.historical_default_state())
        or legacy_chain.get("final_state_sha256") != module.fingerprint(legacy_state)
        or legacy_chain.get("transition_count") != 1
        or legacy_chain.get("transitions") != [normalized]
    ):
        raise AssertionError("legacy canonical chain identity changed")
    if (legacy_state, legacy_receipt, legacy_plan) != (
        state_before,
        receipt_before,
        plan_before,
    ):
        raise AssertionError("normalization mutated its immutable inputs")

    temp_state = temp_root / "main/pipeline.json"
    temp_ledger = temp_root / "main/promotion_receipts.jsonl"
    temp_state.parent.mkdir(parents=True, exist_ok=True)
    temp_state.write_bytes(stable_regular_bytes(STATE_PATH))
    write_jsonl(temp_ledger, [normalized])
    source_manifest, validation_receipt = accepted_source_fixture(temp_root / "source")
    os.environ["RAG_MAIN_PIPELINE_MANIFEST"] = str(temp_state)
    os.environ["RAG_MAIN_PROMOTION_RECEIPTS"] = str(temp_ledger)

    original_now = module._now
    original_uuid4 = module.uuid.uuid4
    module._now = _Sequence(
        [
            "2026-09-03T00:00:00.000001Z",
            "2026-09-03T00:00:00.000002Z",
            "2026-09-03T00:00:00.000003Z",
            "2026-09-03T00:00:00.000004Z",
            "2026-09-03T00:00:00.000005Z",
        ]
    )
    module.uuid.uuid4 = _Sequence(
        [
            uuid.UUID("11111111-1111-1111-1111-111111111159"),
            uuid.UUID("22222222-2222-2222-2222-222222222159"),
            uuid.UUID("33333333-3333-3333-3333-333333333159"),
        ]
    )
    try:
        followup_plan = module.prepare_plan(
            source_manifest,
            "followup",
            switch_changes={"sourceset_content_snapshot": True},
            runtime_profile=module.PIPELINE_ID,
            validation_receipts=[validation_receipt],
            actor="ADR-0159-audit",
        )
        applied = module.apply_plan(
            followup_plan,
            actor="ADR-0159-audit",
            approval_note="deterministic isolated follow-up",
            confirm_main=True,
        )
        applied_state = applied["state"]
        if (
            applied_state.get("generation") != 2
            or applied_state.get("runtime_profile") != module.PIPELINE_ID
            or applied_state.get("switches", {}).get("internal_compliance_compiler_v1") is not True
            or applied_state.get("switches", {}).get("sourceset_content_snapshot") is not True
            or len(applied_state.get("active_promotions", [])) != 2
        ):
            raise AssertionError("follow-up apply did not preserve and extend legacy MAIN")
        apply_chain_errors = module.validate_transition_chain(
            applied["transition_chain"], applied_state
        )
        if apply_chain_errors:
            raise AssertionError("follow-up apply chain failed: " + "; ".join(apply_chain_errors))

        rolled_back = module.rollback(
            followup_plan["promotion_id"],
            actor="ADR-0159-audit",
            note="deterministic isolated rollback",
            confirm_main=True,
        )
    finally:
        module._now = original_now
        module.uuid.uuid4 = original_uuid4

    rollback_state = rolled_back["state"]
    expected_rollback_state = deepcopy(legacy_state)
    expected_rollback_state["generation"] = 3
    expected_rollback_state["updated_at"] = rolled_back["receipt"]["at"]
    if rollback_state != expected_rollback_state:
        raise AssertionError("follow-up rollback did not restore exact legacy business state")
    if module.effective_runtime_profile(rollback_state) != module.PIPELINE_ID:
        raise AssertionError("rolled-back historical state lost effective runtime profile")
    final_chain = rolled_back["transition_chain"]
    final_errors = module.validate_transition_chain(final_chain, rollback_state)
    if final_errors:
        raise AssertionError("follow-up rollback chain failed: " + "; ".join(final_errors))
    ledger_rows = module.read_receipts()
    if len(ledger_rows) != 3 or module.build_transition_chain(
        ledger_rows, rollback_state
    ) != final_chain:
        raise AssertionError("persisted normalized ledger does not replay to rollback state")

    tamper_errors: dict[str, list[str]] = {}

    receipt_tamper = deepcopy(final_chain)
    receipt_tamper["transitions"][0]["after_state_sha256"] = "0" * 64
    tamper_errors["receipt"] = expect_chain_rejection(
        module, "receipt", receipt_tamper, rollback_state
    )

    plan_tamper = deepcopy(final_chain)
    plan_tamper["transitions"][0]["promotion_plan"]["status"] = "tampered"
    plan_tamper["transitions"][0]["plan_sha256"] = module.fingerprint(
        plan_tamper["transitions"][0]["promotion_plan"]
    )
    tamper_errors["plan"] = expect_chain_rejection(
        module, "plan", plan_tamper, rollback_state
    )

    state_tamper = deepcopy(rollback_state)
    state_tamper["switches"]["internal_compliance_compiler_v1"] = False
    tamper_errors["state"] = expect_chain_rejection(
        module, "state", final_chain, state_tamper
    )

    source_tamper = deepcopy(final_chain)
    source_tamper["transitions"][0]["source"]["arm_id"] = "tampered-arm"
    source_tamper["transitions"][0]["promotion_plan"]["source"]["arm_id"] = "tampered-arm"
    source_tamper["transitions"][0]["plan_sha256"] = module.fingerprint(
        source_tamper["transitions"][0]["promotion_plan"]
    )
    tamper_errors["source"] = expect_chain_rejection(
        module, "source", source_tamper, rollback_state
    )

    artifact_tamper = deepcopy(final_chain)
    artifacts = artifact_tamper["transitions"][0]["promotion_plan"]["changes"][
        "code_artifacts"
    ]
    if not artifacts:
        raise AssertionError("legacy plan has no artifact for tamper negative")
    artifacts[0]["sha256"] = "0" * 64
    artifact_tamper["transitions"][0]["plan_sha256"] = module.fingerprint(
        artifact_tamper["transitions"][0]["promotion_plan"]
    )
    tamper_errors["artifact"] = expect_chain_rejection(
        module, "artifact", artifact_tamper, rollback_state
    )

    order_tamper = deepcopy(final_chain)
    order_tamper["transitions"][1], order_tamper["transitions"][2] = (
        order_tamper["transitions"][2],
        order_tamper["transitions"][1],
    )
    tamper_errors["order"] = expect_chain_rejection(
        module, "order", order_tamper, rollback_state
    )

    if set(tamper_errors) != {"receipt", "plan", "state", "source", "artifact", "order"}:
        raise AssertionError("six frozen tamper classes were not all executed")

    return {
        "fixture": fixture_records,
        "standard_cli": cli_audit,
        "baseline": {
            "v2_only_rejected": True,
            "errors": [str(value) for value in strict_errors],
        },
        "explicit_plan_binding": {
            "fixed_plan_path": PLAN_PATH.relative_to(ROOT).as_posix(),
            "fixed_plan_sha256": FIXTURE_LOCK[PLAN_PATH][0],
            "implicit_discovery_rejected": True,
            "implicit_discovery_error": no_plan_error,
            "ambiguous_candidates_rejected": True,
            "ambiguous_candidates_error": duplicate_plan_error,
            "release_implicit_discovery_rejected": True,
            "release_implicit_discovery_error": release_no_plan_error,
            "release_duplicate_paths_rejected": True,
            "release_duplicate_paths_error": release_duplicate_path_error,
            "release_explicit_path_chain_equal": True,
        },
        "legacy_bridge": {
            "normalized_receipt_sha256": canonical_sha256(normalized),
            "chain_sha256": canonical_sha256(legacy_chain),
            "root_state_sha256": legacy_chain["root_state_sha256"],
            "final_state_sha256": legacy_chain["final_state_sha256"],
            "runtime_profile": module.effective_runtime_profile(legacy_state),
            "canonical_replay": True,
            "inputs_unchanged": True,
        },
        "followup": {
            "promotion_id": followup_plan["promotion_id"],
            "apply_generation": applied_state["generation"],
            "rollback_generation": rollback_state["generation"],
            "legacy_switch_preserved": True,
            "apply_chain_sha256": canonical_sha256(applied["transition_chain"]),
            "rollback_chain_sha256": canonical_sha256(final_chain),
            "rollback_restored_exact_business_state": True,
        },
        "tamper_negatives": {
            key: {"rejected": True, "errors": values}
            for key, values in sorted(tamper_errors.items())
        },
        "llm_calls": 0,
        "network_calls": 0,
    }


def write_new_output(path: Path, value: Mapping[str, Any]) -> None:
    path = Path(os.path.abspath(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise RuntimeError("ADR-0159 audit requires O_NOFOLLOW")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(raw)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--revision-sha256", required=True)
    parser.add_argument("--candidate-manifest-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = Path(os.path.abspath(args.output))
    if os.path.lexists(output):
        parser.error(f"refusing to overwrite existing output: {output}")

    runner_record = file_record(Path(__file__).resolve())
    production_before = production_records()
    candidate = verify_candidate(
        run_id=args.run_id,
        revision_id=args.revision_id,
        revision_sha256=args.revision_sha256,
        manifest_sha256=args.candidate_manifest_sha256,
    )
    base = verify_base_candidate()
    environment_before = dict(os.environ)
    sys_path_before = list(sys.path)
    cwd_before = Path.cwd()
    original_connect = socket.socket.connect
    network_attempts: list[str] = []

    def forbid_network(_socket: socket.socket, address: object) -> None:
        network_attempts.append(repr(address))
        raise AssertionError(f"network access is forbidden in ADR-0159 {RUN_ID}")

    started = time.perf_counter()
    original_umask = os.umask(0o077)
    overlay_records: list[dict[str, Any]] = []
    module_provenance: list[dict[str, str]] = []
    safe_import_paths: list[str] = []
    try:
        socket.socket.connect = forbid_network
        with tempfile.TemporaryDirectory(prefix="adr0159-run003-", dir="/tmp") as raw_root:
            temp_root = Path(raw_root)
            overlay_root, overlay_records = build_overlay(temp_root, base, candidate)
            safe_import_paths = isolate_import_path(overlay_root)
            os.chdir("/tmp")
            os.environ.pop("LAWRAG_RELEASE_STORE", None)
            os.environ.pop("LAWRAG_CODE_PACKAGE_ROOT", None)
            (
                module,
                release_module,
                _service_module,
                cli_module,
            ) = load_overlay_modules(overlay_root)
            audit = run_audit(
                module, release_module, cli_module, temp_root / "fixture"
            )
            module_provenance = overlay_module_provenance(overlay_root)
    finally:
        socket.socket.connect = original_connect
        os.umask(original_umask)
        sys.path[:] = sys_path_before
        os.chdir(cwd_before)
        os.environ.clear()
        os.environ.update(environment_before)

    if network_attempts:
        raise AssertionError(f"network attempts occurred: {network_attempts}")
    if sha256_bytes(stable_regular_bytes(CANDIDATE_MANIFEST)) != candidate[
        "manifest_sha256"
    ]:
        raise AssertionError("candidate manifest changed during audit")
    if (
        sha256_bytes(stable_regular_bytes(BASE_CANDIDATE_MANIFEST))
        != BASE_CANDIDATE_MANIFEST_SHA256
    ):
        raise AssertionError("ADR-0158 base candidate manifest changed during audit")
    production_after = production_records()
    if production_after != production_before:
        raise AssertionError("monitored production bytes changed during isolated audit")

    receipt = {
        "schema_version": "adr0159-legacy-main-chain-audit-v1",
        "run_id": args.run_id,
        "all_passed": True,
        "candidate": {
            "candidate_id": candidate["manifest"]["candidate_id"],
            "candidate_manifest_sha256": candidate["manifest_sha256"],
            "revision_id": candidate["revision_id"],
            "revision_sha256": candidate["revision_sha256"],
            "module_path": (
                candidate["revision_root"] / "lawrag/core/rag/main_promotion.py"
            ).relative_to(ROOT).as_posix(),
            "files": candidate["files"],
        },
        "dependency_base": {
            "candidate_id": "v2-runtime-activation",
            "candidate_manifest_sha256": base["manifest_sha256"],
            "revision_id": base["revision_id"],
            "revision_sha256": base["revision_sha256"],
            "file_count": len(base["files"]),
            "files_sha256": canonical_sha256(base["files"]),
        },
        "overlay": {
            "file_count": len(overlay_records),
            "files_sha256": canonical_sha256(overlay_records),
            "override_targets": sorted(EXPECTED_TARGETS),
            "module_provenance": module_provenance,
            "production_dependency_imports": 0,
            "preserved_import_paths": safe_import_paths,
        },
        "runner": runner_record,
        "audit": audit,
        "production": {
            "monitored_before": production_before,
            "monitored_after": production_after,
            "unchanged": True,
        },
        "execution": {
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "temporary_parent": "/tmp",
            "llm_calls": 0,
            "network_calls": 0,
        },
    }
    write_new_output(output, receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
