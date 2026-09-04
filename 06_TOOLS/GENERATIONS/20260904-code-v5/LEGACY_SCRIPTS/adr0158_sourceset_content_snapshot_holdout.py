#!/usr/bin/env python3
"""Focused deterministic holdout for ADR-0158 SourceSet content snapshots.

The runner is intentionally self-contained.  It verifies an exact immutable
candidate revision before making that revision the only repository import root,
builds all mutable fixtures below a fresh POSIX directory in ``/tmp``, executes
the sixteen frozen cases exactly once, and publishes one O_EXCL JSON
receipt.  It never calls a product LLM and never imports ``lawrag`` from the
working tree.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shlex
import site
import stat
import struct
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import traceback
from typing import Any, Callable, Mapping
import zipfile


sys.dont_write_bytecode = True

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
CANDIDATE_ROOT = Path(__import__("lawrag").__file__).resolve().parent / "research/candidates/adr_0158/v2-runtime-activation"
CANDIDATE_MANIFEST = CANDIDATE_ROOT / "candidate.json"
INPUT_LOCK = (
    ROOT
    / "docs/adr/ADR-0158-v2-workspace-sourceset-genos-activation/artifacts"
    / "run-013-input-lock.json"
)
RUN012 = (
    ROOT
    / "docs/adr/ADR-0158-v2-workspace-sourceset-genos-activation/artifacts"
    / "run-012.json"
)
INPUT_LOCK_SHA256 = "12533dc31c356defbca673ea3a568b6bf0d9dda5a27908ca88202be7059711e0"
INPUT_LOCK_BYTES = 4196
RUN012_SHA256 = "0654ab629dfb7c31cc753b61cc8e314073a81a79e3b58dfc111beb07badeb3a8"
RUN012_BYTES = 330525
NOW = "2026-09-02T12:00:00Z"
RECEIPT_KINDS = ("schema", "hash", "acl", "smoke", "provenance")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")
RUN_ID_RE = re.compile(r"^run-[0-9]{3,}$")

CASE_IDS = (
    "legacy-off-byte-equivalence",
    "trusted-release-single-snapshot",
    "external-internal-unified-view",
    "artifact-byte-tamper-rejected",
    "stale-authority-lock-rejected",
    "duplicate-document-id-rejected",
    "unmapped-document-id-rejected",
    "index-content-fingerprint-bound",
    "vector-content-fingerprint-bound",
    "scoped-index-provenance-preserved",
    "hit-section-citation-provenance",
    "relation-evidence-provenance",
    "trace-and-tuple-provenance",
    "feedback-shortcut-generation-lock",
    "sealed-service-query-only",
    "release-and-main-rollback-coherence",
)

FIXED_PRODUCTION_PATHS = (
    "service.py",
    "scripts/serve.sh",
    "00_SYSTEM/WORKSPACE.json",
    "config/dataset_sync/profiles.json",
    "var/out/structure/main",
)

ENV_PATH_KEYS = (
    "LAWRAG_RELEASE_STORE",
    "LAWRAG_CODE_PACKAGE_ROOT",
    "RAG_MAIN_PIPELINE_MANIFEST",
    "RAG_MAIN_PROMOTION_RECEIPTS",
    "RAG_APPROVAL_RECEIPTS",
    "RAG_RULES_DIR",
    "RAG_ENGINE_RULES",
    "RAG_DELEGATION_STORE",
    "RAG_LAW_INDEX_STORE",
    "RAG_SCOPES_FILE",
    "LEGAL_GRAPH_STORE",
    "RAG_DOMAIN_GRAPH",
    "RAG_CONCEPT_REGISTRY",
    "RAG_ALIASES_STORE",
    "RAG_ALIASES",
    "RAG_FRAMES_DIR",
    "RAG_TAXONOMY_DIR",
    "RAG_LEXICON_DIR",
    "WIKI_STORE",
    "RAG_ASSERTION_SHORTCUT_STORE",
    "LAWRAG_FEEDBACK_ROOT",
    "LAWRAG_QUERY_SHORTCUT_STORE",
    "RAG_QUERY_SHORTCUT_STORE",
    "STRUCTURE_STORE",
    "STRUCTURE_CUSTOM_DIR",
    "GLOSSARY_STORE",
    "RAG_LINKS_STORE",
    "RAG_VECTOR_STORE",
    "EMBED_MODEL_ARTIFACT_PATH",
    "RAG_LOG_DIR",
    "RAG_EVENTS_LOG",
    "LOG_DIR",
    "OPS_DIR",
    "OPS_INBOX_DIR",
    "LAWRAG_SECRET_BINDING_ROOT",
)


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


def h(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def deterministic_vector_npz() -> bytes:
    """Return a valid one-row float32 NPZ with fixed ZIP metadata."""

    header = "{'descr': '<f4', 'fortran_order': False, 'shape': (1, 8), }"
    prefix_length = len(b"\x93NUMPY\x01\x00") + 2
    padding = (16 - ((prefix_length + len(header) + 1) % 16)) % 16
    header_raw = (header + (" " * padding) + "\n").encode("ascii")
    npy = b"".join(
        (
            b"\x93NUMPY\x01\x00",
            len(header_raw).to_bytes(2, "little"),
            header_raw,
            struct.pack("<8f", 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
    )
    output = io.BytesIO()
    info = zipfile.ZipInfo("v.npy", date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o600 << 16
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(info, npy)
    return output.getvalue()


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
    """Read a stable regular file without following a symbolic link."""

    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError(f"expected non-symlink regular file: {path}")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise RuntimeError("holdout requires O_NOFOLLOW")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_BINARY", 0) | no_follow,
    )
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
    return sha256_bytes(stable_regular_bytes(path))


def write_regular(path: Path, raw: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise RuntimeError("holdout requires O_NOFOLLOW")
    descriptor = os.open(path, flags | no_follow, mode)
    try:
        total = 0
        while total < len(raw):
            total += os.write(descriptor, raw[total:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def overwrite_probe_file(path: Path, raw: bytes) -> None:
    """Replace bytes of one known /tmp fixture file without following links."""

    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"probe target is not a regular file: {path}")
    path.chmod(0o600)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        total = 0
        while total < len(raw):
            total += os.write(descriptor, raw[total:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    path.chmod(0o400)


@dataclasses.dataclass(frozen=True)
class CandidateIdentity:
    manifest: Mapping[str, Any]
    revision: Mapping[str, Any]
    manifest_sha256: str
    revision_id: str
    revision_sha256: str
    revision_root: Path
    files: tuple[Mapping[str, Any], ...]
    target_paths: tuple[Path, ...]


def _safe_target_path(raw: object) -> Path:
    text = str(raw or "")
    relative = Path(text)
    if not text or relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"unsafe candidate target path: {text!r}")
    if relative.as_posix() != text:
        raise RuntimeError(f"non-canonical candidate target path: {text!r}")
    return ROOT / relative


def _manifested_revision_files(
    revision: Mapping[str, Any], revision_root: Path
) -> dict[Path, Mapping[str, Any]]:
    rows = revision.get("files")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("candidate revision has no files")
    expected: dict[Path, Mapping[str, Any]] = {}
    root = Path(os.path.abspath(revision_root))
    for row in rows:
        if not isinstance(row, Mapping):
            raise RuntimeError("candidate revision file row must be an object")
        raw_path = Path(str(row.get("frozen_path") or ""))
        path = raw_path if raw_path.is_absolute() else ROOT / raw_path
        path = Path(os.path.abspath(path))
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise RuntimeError(f"frozen candidate path escapes revision: {path}") from exc
        if path in expected:
            raise RuntimeError(f"duplicate frozen candidate path: {path}")
        expected[path] = row
    return expected


def _verify_exact_revision_tree(
    revision_root: Path, expected: Mapping[Path, Mapping[str, Any]]
) -> None:
    allowed_directories = {revision_root}
    for path in expected:
        parent = path.parent
        while parent != revision_root:
            allowed_directories.add(parent)
            parent = parent.parent
    seen_files: set[Path] = set()
    pending = [revision_root]
    while pending:
        directory = pending.pop()
        info = directory.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise RuntimeError(f"candidate revision directory is unsafe: {directory}")
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


def verify_candidate(
    revision_id: str,
    revision_sha256: str,
    candidate_manifest_sha256: str,
    run_id: str,
) -> CandidateIdentity:
    if not REVISION_ID_RE.fullmatch(revision_id):
        raise RuntimeError("--revision-id is not canonical")
    if not SHA256_RE.fullmatch(revision_sha256):
        raise RuntimeError("--revision-sha256 must be lowercase SHA-256")
    if not SHA256_RE.fullmatch(candidate_manifest_sha256):
        raise RuntimeError("--candidate-manifest-sha256 must be lowercase SHA-256")
    raw = stable_regular_bytes(CANDIDATE_MANIFEST)
    if sha256_bytes(raw) != candidate_manifest_sha256:
        raise RuntimeError("candidate manifest hash changed")
    manifest = json.loads(raw)
    if not isinstance(manifest, Mapping):
        raise RuntimeError("candidate manifest must be an object")
    if manifest.get("schema_version") != "adr-code-candidate-v2":
        raise RuntimeError("candidate manifest must use adr-code-candidate-v2")
    if run_id not in (manifest.get("run_ids") or []):
        raise RuntimeError(f"candidate manifest is not linked to {run_id}")
    revisions = [
        row
        for row in manifest.get("revisions", [])
        if isinstance(row, Mapping) and row.get("revision_id") == revision_id
    ]
    if len(revisions) != 1:
        raise RuntimeError("candidate revision ID is absent or ambiguous")
    revision = revisions[0]
    if revision.get("revision_sha256") != revision_sha256:
        raise RuntimeError("candidate revision identity changed")
    core = {key: value for key, value in revision.items() if key != "revision_sha256"}
    if canonical_sha256(core) != revision_sha256:
        raise RuntimeError("candidate revision canonical hash is invalid")
    revision_root = CANDIDATE_ROOT / "revisions" / revision_id / "snapshot"
    revision_root = Path(os.path.abspath(revision_root))
    expected = _manifested_revision_files(revision, revision_root)
    _verify_exact_revision_tree(revision_root, expected)

    manifest_rows = manifest.get("files")
    if not isinstance(manifest_rows, list) or not manifest_rows:
        raise RuntimeError("candidate manifest has no file provenance")
    by_snapshot: dict[str, Mapping[str, Any]] = {}
    targets: list[Path] = []
    for row in manifest_rows:
        if not isinstance(row, Mapping):
            raise RuntimeError("candidate file provenance row must be an object")
        snapshot_path = str(row.get("snapshot_path") or "")
        if not snapshot_path or snapshot_path in by_snapshot:
            raise RuntimeError("candidate snapshot paths must be non-empty and unique")
        by_snapshot[snapshot_path] = row
        targets.append(_safe_target_path(row.get("target_path")))
    revision_by_snapshot = {
        str(row.get("snapshot_path") or ""): row
        for row in revision.get("files", [])
        if isinstance(row, Mapping)
    }
    if set(by_snapshot) != set(revision_by_snapshot):
        raise RuntimeError("candidate manifest and frozen revision file sets differ")

    verified_rows: list[Mapping[str, Any]] = []
    for path, row in sorted(expected.items(), key=lambda item: str(item[0])):
        raw_file = stable_regular_bytes(path)
        actual_sha = sha256_bytes(raw_file)
        if row.get("snapshot_sha256") != actual_sha or row.get("bytes") != len(raw_file):
            raise RuntimeError(f"frozen candidate file changed: {path}")
        snapshot_path = str(row.get("snapshot_path") or "")
        manifest_row = by_snapshot[snapshot_path]
        if (
            manifest_row.get("snapshot_sha256") != actual_sha
            or manifest_row.get("bytes") != len(raw_file)
            or path != revision_root / str(manifest_row.get("target_path") or "")
        ):
            raise RuntimeError(f"candidate provenance mismatch: {path}")
        verified_rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": actual_sha,
                "bytes": len(raw_file),
            }
        )
    return CandidateIdentity(
        manifest=manifest,
        revision=revision,
        manifest_sha256=candidate_manifest_sha256,
        revision_id=revision_id,
        revision_sha256=revision_sha256,
        revision_root=revision_root,
        files=tuple(verified_rows),
        target_paths=tuple(sorted(set(targets), key=str)),
    )


def verify_input_lock(expected_sha256: str, expected_bytes: int) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(expected_sha256):
        raise RuntimeError("--input-lock-sha256 must be lowercase SHA-256")
    if expected_bytes <= 0:
        raise RuntimeError("--input-lock-bytes must be positive")
    if (
        expected_sha256 != INPUT_LOCK_SHA256
        or expected_bytes != INPUT_LOCK_BYTES
    ):
        raise RuntimeError("run-013 immutable input-lock identity changed")
    raw = stable_regular_bytes(INPUT_LOCK)
    if len(raw) != expected_bytes or sha256_bytes(raw) != expected_sha256:
        raise RuntimeError("run-013 input lock changed")
    blob = json.loads(raw)
    if not isinstance(blob, Mapping):
        raise RuntimeError("run-013 input lock must be an object")
    rows = blob.get("cases")
    if (
        blob.get("schema_version") != "adr0158-serving-holdout-input-v1"
        or blob.get("run_id") != "run-013"
        or blob.get("frozen_before_implementation") is not True
        or not isinstance(rows, list)
    ):
        raise RuntimeError("run-013 input lock contract is invalid")
    actual_ids = tuple(
        str(row.get("case_id") or "") if isinstance(row, Mapping) else ""
        for row in rows
    )
    if actual_ids != CASE_IDS or len(set(actual_ids)) != len(CASE_IDS):
        raise RuntimeError("run-013 case IDs or order changed")
    if any(not isinstance(row.get("expected"), str) or not row["expected"] for row in rows):
        raise RuntimeError("run-013 case expectation is missing")
    return {
        "path": INPUT_LOCK.relative_to(ROOT).as_posix(),
        "run_id": "run-013",
        "sha256": expected_sha256,
        "bytes": expected_bytes,
        "case_ids": list(actual_ids),
        "expectations": {
            str(row["case_id"]): str(row["expected"])
            for row in rows
        },
    }


def verify_run012() -> dict[str, Any]:
    raw = stable_regular_bytes(RUN012)
    actual = sha256_bytes(raw)
    if len(raw) != RUN012_BYTES or actual != RUN012_SHA256:
        raise RuntimeError("immutable run-012 artifact changed")
    return {
        "path": RUN012.relative_to(ROOT).as_posix(),
        "sha256": actual,
        "bytes": len(raw),
    }


def isolate_import_path(revision_root: Path) -> list[str]:
    existing = sorted(
        name for name in sys.modules if name == "lawrag" or name.startswith("lawrag.")
    )
    if existing:
        raise RuntimeError(f"lawrag was imported before candidate isolation: {existing}")
    original = list(sys.path)
    dependency_roots = {
        Path(value).resolve()
        for value in (
            *site.getsitepackages(),
            *(
                sysconfig.get_paths().get(key, "")
                for key in ("stdlib", "platstdlib", "purelib", "platlib")
            ),
        )
        if value
    }
    safe: list[str] = []
    for raw in original:
        if not raw:
            continue
        absolute = Path(os.path.abspath(raw))
        try:
            absolute.relative_to(ROOT)
        except ValueError:
            safe.append(raw)
            continue
        if any(
            absolute == dependency_root
            or dependency_root in absolute.parents
            for dependency_root in dependency_roots
        ):
            safe.append(raw)
    sys.path[:] = [str(revision_root), *safe]
    importlib.invalidate_caches()
    return original


def candidate_module_provenance(revision_root: Path) -> list[dict[str, Any]]:
    allowed = revision_root.resolve()
    rows: list[dict[str, Any]] = []
    for name in sorted(
        key
        for key in sys.modules
        if key == "lawrag" or key.startswith("lawrag.") or key == "service"
    ):
        module = sys.modules[name]
        raw_file = getattr(module, "__file__", None)
        if raw_file is None:
            rows.append({"module": name, "file": None, "namespace": True})
            continue
        path = Path(raw_file).resolve()
        try:
            relative = path.relative_to(allowed)
        except ValueError as exc:
            raise RuntimeError(f"working-tree or installed product import leaked: {name}={path}") from exc
        rows.append({"module": name, "file": relative.as_posix(), "namespace": False})
    if not any(row["module"] == "lawrag.core.rag.index" for row in rows):
        raise RuntimeError("candidate RAG index was not imported")
    return rows


def _path_state(path: Path) -> dict[str, Any]:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"kind": "absent"}
    mode = stat.S_IMODE(info.st_mode)
    identity = {
        "device": info.st_dev,
        "inode": info.st_ino,
        "mode": mode,
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
    }
    if stat.S_ISLNK(info.st_mode):
        return {"kind": "symlink", **identity, "target": os.readlink(path)}
    if stat.S_ISREG(info.st_mode):
        raw = stable_regular_bytes(path)
        return {
            "kind": "file",
            **identity,
            "bytes": len(raw),
            "sha256": sha256_bytes(raw),
        }
    if not stat.S_ISDIR(info.st_mode):
        return {"kind": "special", **identity, "rdev": info.st_rdev}
    rows: dict[str, Any] = {".": {"kind": "directory", **identity}}
    pending = [(path, Path("."))]
    while pending:
        current, relative = pending.pop()
        with os.scandir(current) as entries:
            for entry in sorted(entries, key=lambda value: os.fsencode(value.name)):
                child = Path(entry.path)
                rel = relative / entry.name
                child_info = entry.stat(follow_symlinks=False)
                child_identity = {
                    "device": child_info.st_dev,
                    "inode": child_info.st_ino,
                    "mode": stat.S_IMODE(child_info.st_mode),
                    "size": child_info.st_size,
                    "mtime_ns": child_info.st_mtime_ns,
                    "ctime_ns": child_info.st_ctime_ns,
                }
                key = rel.as_posix()
                if stat.S_ISLNK(child_info.st_mode):
                    rows[key] = {
                        "kind": "symlink",
                        **child_identity,
                        "target": os.readlink(child),
                    }
                elif stat.S_ISDIR(child_info.st_mode):
                    rows[key] = {"kind": "directory", **child_identity}
                    pending.append((child, rel))
                elif stat.S_ISREG(child_info.st_mode):
                    raw = stable_regular_bytes(child)
                    rows[key] = {
                        "kind": "file",
                        **child_identity,
                        "bytes": len(raw),
                        "sha256": sha256_bytes(raw),
                    }
                else:
                    rows[key] = {
                        "kind": "special",
                        **child_identity,
                        "rdev": child_info.st_rdev,
                    }
    return {"kind": "tree", "entries": dict(sorted(rows.items()))}


def monitored_paths(candidate: CandidateIdentity, output: Path) -> tuple[Path, ...]:
    values = set(candidate.target_paths)
    values.update(ROOT / row for row in FIXED_PRODUCTION_PATHS)
    values.update(
        {
            Path(__file__).resolve(),
            CANDIDATE_MANIFEST,
            candidate.revision_root,
            INPUT_LOCK,
            RUN012,
        }
    )
    for key in ENV_PATH_KEYS:
        raw = os.environ.get(key, "").strip()
        if not raw:
            continue
        path = Path(raw)
        if not path.is_absolute():
            continue
        absolute = Path(os.path.abspath(path))
        try:
            absolute.relative_to(ROOT)
        except ValueError:
            continue
        values.add(absolute)
    output_abs = Path(os.path.abspath(output))
    for path in values:
        absolute = Path(os.path.abspath(path))
        if output_abs == absolute:
            raise RuntimeError("output path is monitored production state")
        if absolute.exists() and absolute.is_dir():
            try:
                output_abs.relative_to(absolute)
            except ValueError:
                pass
            else:
                raise RuntimeError("output path is inside monitored production state")
    return tuple(sorted(values, key=str))


def production_state(paths: tuple[Path, ...]) -> dict[str, Any]:
    return {str(Path(os.path.abspath(path))): _path_state(path) for path in paths}


def copy_tree_preserving_modes(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f"copy destination already exists: {destination}")
    source_info = source.lstat()
    if stat.S_ISLNK(source_info.st_mode) or not stat.S_ISDIR(source_info.st_mode):
        raise RuntimeError(f"copy source is not a safe directory: {source}")
    destination.mkdir(parents=True, mode=0o700)
    pending = [(source, destination)]
    directories: list[tuple[Path, int]] = [
        (destination, stat.S_IMODE(source_info.st_mode))
    ]
    while pending:
        src, dst = pending.pop()
        with os.scandir(src) as entries:
            for entry in sorted(entries, key=lambda value: os.fsencode(value.name)):
                child = Path(entry.path)
                target = dst / entry.name
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    raise RuntimeError(f"fixture tree contains symlink: {child}")
                if stat.S_ISDIR(info.st_mode):
                    target.mkdir(mode=0o700)
                    directories.append((target, stat.S_IMODE(info.st_mode)))
                    pending.append((child, target))
                elif stat.S_ISREG(info.st_mode):
                    write_regular(target, stable_regular_bytes(child), 0o600)
                    target.chmod(stat.S_IMODE(info.st_mode))
                else:
                    raise RuntimeError(f"fixture tree contains special entry: {child}")
    for path, mode in reversed(directories):
        path.chmod(mode)


def structure_payload(
    document_id: str,
    *,
    name: str,
    title: str,
    surface: str,
    text: str,
    kind: str,
    authority_generation: str,
) -> dict[str, Any]:
    return {
        "schema_version": "rag-structure-artifact-v1",
        "document_id": document_id,
        "meta": {
            "name": name,
            "kind": kind,
            "authority_generation": authority_generation,
            "status": "현행",
            "canonical": True,
            "enforce": "20260901",
        },
        "result": {
            "nodes": [
                {
                    "id": 1,
                    "parent": None,
                    "level": 1,
                    "surface": surface,
                    "title": title,
                    "span": [0, 1],
                    "page": 1,
                }
            ],
            "blocks": [{"idx": 0, "node": 1, "page": 1, "text": text}],
        },
    }


def write_dataset_package(
    catalog,
    packages_root: Path,
    *,
    package_id: str,
    dataset_id: str,
    version_id: str,
    restricted: bool,
    artifacts: list[dict[str, Any]],
):
    package_root = packages_root / package_id
    package_root.mkdir(parents=True, exist_ok=False)
    artifact_rows = []
    for row in artifacts:
        path = package_root / str(row["path"])
        raw = canonical_bytes(row["payload"])
        write_regular(path, raw)
        artifact_row: dict[str, Any] = {
            "logical_id": row["logical_id"],
            "role": row["role"],
            "path": row["path"],
            "sha256": sha256_bytes(raw),
            "media_type": "application/json",
        }
        if row.get("document_id") is not None:
            artifact_row["document_id"] = row["document_id"]
        artifact_rows.append(artifact_row)
    blob: dict[str, Any] = {
        "schema_version": "dataset-package-v2",
        "package_id": package_id,
        "dataset_id": dataset_id,
        "version_id": version_id,
        "variant_id": "real",
        "generation_id": f"generation-{package_id}",
        "source_origin": "restricted_internal" if restricted else "public_external",
        "security_class": "restricted" if restricted else "public",
        "representation": "real",
        "authority": "authoritative",
        "export_policy": {"allowed": not restricted},
        "build": {
            "build_id": f"build-{package_id}",
            "execution_site": "genos" if restricted else "outside",
            "code_revision": "adr0158-fixture-revision",
            "compiler_profile": "adr0158-fixture-profile",
            "capabilities": ["structure"],
        },
        "artifacts": artifact_rows,
    }
    manifest_path = package_root / "package.json"
    parsed = catalog.package_from_mapping(blob, manifest_path=manifest_path)
    blob["manifest_sha256"] = parsed.manifest_sha256
    write_regular(manifest_path, canonical_bytes(blob))
    return catalog.load_package(manifest_path), manifest_path


def expect_error(
    expected_type: type[BaseException], operation: Callable[[], Any]
) -> BaseException:
    try:
        operation()
    except expected_type as exc:
        return exc
    except BaseException as exc:
        raise AssertionError(
            f"expected {expected_type.__name__}, got {type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(f"expected {expected_type.__name__}, got success")


@dataclasses.dataclass
class Fixture:
    root: Path
    candidate: CandidateIdentity
    catalog_mod: Any
    release_mod: Any
    snapshot_mod: Any
    index_mod: Any
    search_mod: Any
    answer_mod: Any
    llm_mod: Any
    llm_structured_original: Any
    llm_calls: list[Mapping[str, Any]]
    network_calls: list[str]
    external: Any
    internal: Any
    external_manifest: Path
    internal_manifest: Path
    external_structure_path: Path
    source_set_blob: Mapping[str, Any]
    view: Any
    lock: Any
    materialized_stage: Any
    installed_catalog: Any
    catalog_artifact_path: Path
    catalog_sha256: str
    catalog_artifact_sha256: str
    lock_artifact_path: Path
    lock_artifact_sha256: str
    materialization_sha256: str
    store: Any
    off_store: Any
    release_off: Any
    binding_off: Any
    off_release_main_path: Path
    release_a: Any
    release_b: Any
    refs_a: tuple[Any, ...]
    refs_b: tuple[Any, ...]
    binding_a: Any
    binding_b: Any
    lexical_fingerprint: Any
    vector_fingerprint: Any
    model_fingerprint: str
    model_artifact_path: Path
    model_artifact_sha256: str
    llm_descriptor: Mapping[str, Any]
    encoder_descriptor: Mapping[str, Any]
    qdrant_url: str
    qdrant_collection: str
    qdrant_config_sha256: str
    pointer_b: Any
    snapshot: Any
    materialized_b: Any
    runtime_paths_b: Mapping[str, str]
    runtime_artifacts_b: Mapping[str, str]
    main_a: Mapping[str, Any]
    main_b: Mapping[str, Any]
    main_plan_a_sha256: str
    main_plan_b_sha256: str
    main_receipt_a_sha256: str
    main_receipt_b_sha256: str
    main_a_path: Path
    main_b_path: Path
    off_main_path: Path
    feedback_root: Path
    feedback_root_sha256: str
    feedback_trust_policy_id: str
    secret_binding_root: Path
    qdrant_secret_file_sha256: str
    reviewed_shortcut_path: Path
    reviewed_shortcut_sha256: str
    retrieval_runtime: Mapping[str, Any] | None = None
    index: Any = None


def _main_state(generation: int, *, adapter_on: bool) -> dict[str, Any]:
    if generation == 0:
        return {
            "schema_version": "main-rag-pipeline-v1",
            "pipeline_id": "legalclosure-v2",
            "runtime_profile": "legalclosure-v2",
            "generation": 0,
            "active_promotion_id": None,
            "active_promotions": [],
            "switches": {},
            "code_artifacts": [],
            "updated_at": None,
        }
    promotions = [
        {
            "promotion_id": f"run013-main-{position}",
            "adr_id": "ADR-0158",
            "experiment_id": "ADR-0158-experiment-v1",
            "arm_id": "v2-candidate",
            "source_manifest_sha256": h(f"run013-source-{position}"),
            "applied_at": NOW,
            "applied_by": "adr0158-run013",
        }
        for position in range(1, generation + 1)
    ]
    return {
        "schema_version": "main-rag-pipeline-v1",
        "pipeline_id": "legalclosure-v2",
        "runtime_profile": "legalclosure-v2",
        "generation": generation,
        "active_promotion_id": (
            promotions[-1]["promotion_id"] if promotions else None
        ),
        "active_promotions": promotions,
        "switches": {
            "sourceset_content_snapshot": adapter_on,
            "memory_entry": adapter_on,
        },
        "code_artifacts": [],
        "updated_at": NOW,
    }


def _main_promotion_plan(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    promotion_id = str(after.get("active_promotion_id") or "")
    if not promotion_id:
        raise RuntimeError("promoted MAIN fixture requires an active promotion ID")
    promotions = [
        row
        for row in (after.get("active_promotions") or [])
        if isinstance(row, Mapping) and row.get("promotion_id") == promotion_id
    ]
    if len(promotions) != 1:
        raise RuntimeError("promoted MAIN fixture has no unique active promotion")
    promotion = promotions[0]
    before_switches = dict(before.get("switches") or {})
    after_switches = dict(after.get("switches") or {})
    switch_changes = {
        key: value
        for key, value in after_switches.items()
        if before_switches.get(key) is not value
    }
    source = {
        "adr_id": promotion["adr_id"],
        "experiment_id": promotion["experiment_id"],
        "arm_id": promotion["arm_id"],
        "manifest_path": "frozen-run013-fixture",
        "manifest_sha256": promotion["source_manifest_sha256"],
    }
    return {
        "schema_version": "main-rag-promotion-plan-v1",
        "promotion_id": promotion_id,
        "created_at": NOW,
        "created_by": "adr0158-run013",
        "source": source,
        "target": {
            "pipeline_id": before["pipeline_id"],
            "expected_generation": before["generation"],
            "expected_state_sha256": canonical_sha256(before),
        },
        "changes": {
            "switches": switch_changes,
            "runtime_profile": (
                after["runtime_profile"]
                if after.get("runtime_profile") != before.get("runtime_profile")
                else None
            ),
            "code_artifacts": [],
        },
        "validation_receipts": [
            {
                "path": f"frozen-run013/{promotion_id}/validation.json",
                "sha256": h(f"validation:{promotion_id}"),
                "bytes": 0,
            }
        ],
        "rollback": {
            "before_state": dict(before),
            "before_state_sha256": canonical_sha256(before),
        },
        "status": "ready",
    }


def _main_promotion_receipt(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    promotion_id = str(after.get("active_promotion_id") or "")
    source = plan.get("source")
    if (
        plan.get("promotion_id") != promotion_id
        or not isinstance(source, Mapping)
    ):
        raise RuntimeError("MAIN promotion plan does not match its transition")
    return {
        "schema_version": "main-rag-promotion-receipt-v2",
        "receipt_id": f"mpr-{promotion_id}",
        "action": "apply",
        "promotion_id": promotion_id,
        "at": NOW,
        "actor": "adr0158-run013",
        "approval_note": "frozen deterministic holdout fixture",
        "plan_sha256": canonical_sha256(plan),
        "promotion_plan": dict(plan),
        "source": dict(source),
        "before_state": dict(before),
        "before_state_sha256": canonical_sha256(before),
        "after_state_sha256": canonical_sha256(after),
    }


def _validate_main_transition_chain(
    path: Path,
    *,
    state: Mapping[str, Any],
    main_promotion: Any,
) -> str:
    raw = stable_regular_bytes(path)
    value = json.loads(raw)
    if not isinstance(value, Mapping):
        raise RuntimeError("MAIN transition chain is not an object")
    errors = main_promotion.validate_transition_chain(value, state)
    if errors:
        raise RuntimeError("MAIN transition chain is invalid: " + "; ".join(errors))
    return sha256_bytes(raw)


def _write_catalog_artifact(catalog, packages_root: Path, rows: list[tuple[Any, Path]], path: Path):
    blob: dict[str, Any] = {
        "schema_version": "installed-dataset-catalog-v1",
        "packages": [
            {
                "package_id": package.package_id,
                "manifest_path": manifest.relative_to(packages_root).as_posix(),
                "manifest_sha256": package.manifest_sha256,
            }
            for package, manifest in rows
        ],
    }
    parsed = catalog.installed_catalog_from_mapping(blob, package_root=packages_root)
    blob["catalog_sha256"] = parsed.catalog_sha256
    write_regular(path, canonical_bytes(blob))
    return catalog.load_installed_catalog(
        path,
        package_root=packages_root,
        expected_artifact_sha256=sha256_file(path),
    )


def _release_fixture(
    fixture_root: Path,
    candidate: CandidateIdentity,
    catalog,
    release,
    lock,
    materialized_stage,
    catalog_artifact_path: Path,
    packages_root: Path,
    semantic_content_path: Path,
    *,
    release_id: str,
    main_state: Mapping[str, Any],
    main_promotion_plan_path: Path | None,
    main_promotion_plan_sha256: str | None,
    main_promotion_receipt_path: Path | None,
    main_promotion_receipt_sha256: str | None,
    source_binding: Any,
    semantics: Any,
    lexical_fingerprint: Any,
    vector_fingerprint: Any,
    model_fingerprint: str,
    lexical_identity_raw: bytes,
    vector_files: Mapping[str, bytes],
    acl_runtime_services: Mapping[str, Any],
    store,
):
    stage = fixture_root / "release-stage" / release_id
    stage.mkdir(parents=True, exist_ok=False)
    paths = {
        "main.state": stage / "main/pipeline.json",
        "source_set.lock": stage / "source/source-set.lock.json",
        "source_set.materialization": stage / "source/materialized",
        "source_set.catalog": stage / "source/catalog.json",
        "semantics.content": stage / "semantics/content",
        "index.lexical": stage / "indexes/lexical.json",
        "index.vector": stage / "indexes/vector",
    }
    write_regular(paths["main.state"], canonical_bytes(main_state))
    if int(main_state["generation"]) > 0:
        if (
            main_promotion_plan_path is None
            or main_promotion_plan_sha256 is None
            or main_promotion_receipt_path is None
            or main_promotion_receipt_sha256 is None
        ):
            raise RuntimeError("promoted MAIN fixture requires plan and receipt")
        paths["main.promotion_plan"] = stage / "main/promotion-plan.json"
        paths["main.promotion_receipt"] = stage / "main/promotion-receipt.json"
        write_regular(
            paths["main.promotion_plan"],
            stable_regular_bytes(main_promotion_plan_path),
        )
        write_regular(
            paths["main.promotion_receipt"],
            stable_regular_bytes(main_promotion_receipt_path),
        )
    elif any(
        value is not None
        for value in (
            main_promotion_plan_path,
            main_promotion_plan_sha256,
            main_promotion_receipt_path,
            main_promotion_receipt_sha256,
        )
    ):
        raise RuntimeError("generation-zero MAIN cannot carry promotion evidence")
    write_regular(paths["source_set.lock"], canonical_bytes(lock.receipt()))
    copy_tree_preserving_modes(materialized_stage.path, paths["source_set.materialization"])
    write_regular(paths["source_set.catalog"], stable_regular_bytes(catalog_artifact_path))
    copy_tree_preserving_modes(semantic_content_path, paths["semantics.content"])
    write_regular(paths["index.lexical"], lexical_identity_raw)
    paths["index.vector"].mkdir(parents=True)
    for relative, raw in sorted(vector_files.items()):
        write_regular(paths["index.vector"] / relative, raw)
    hashes = {key: release.runtime_artifact_sha256(path) for key, path in paths.items()}
    if hashes["source_set.lock"] != source_binding.lock_artifact_sha256:
        raise RuntimeError("release lock fixture drifted")
    if (
        main_promotion_plan_sha256 is not None
        and hashes["main.promotion_plan"] != main_promotion_plan_sha256
    ):
        raise RuntimeError("release MAIN promotion plan fixture drifted")
    if (
        main_promotion_receipt_sha256 is not None
        and hashes["main.promotion_receipt"] != main_promotion_receipt_sha256
    ):
        raise RuntimeError("release MAIN promotion receipt fixture drifted")
    if hashes["source_set.materialization"] != source_binding.materialization_sha256:
        raise RuntimeError("release materialization fixture drifted")
    if hashes["source_set.catalog"] != source_binding.catalog_artifact_sha256:
        raise RuntimeError("release catalog fixture drifted")
    if hashes["semantics.content"] != semantics.content_sha256:
        raise RuntimeError("release semantic fixture drifted")

    blob: dict[str, Any] = {
        "schema_version": "release-manifest-v1",
        "release_id": release_id,
        "target": "genos",
        "layout_version": "v2",
        "created_at": NOW,
        "code": {
            "revision": candidate.revision_sha256,
            "package_sha256": release.runtime_artifact_sha256(candidate.revision_root),
        },
        "main": {
            "pipeline_id": main_state["pipeline_id"],
            "runtime_profile": main_state["runtime_profile"],
            "generation": main_state["generation"],
            "state_sha256": hashes["main.state"],
            "promotion_plan_sha256": main_promotion_plan_sha256,
            "promotion_receipt_sha256": main_promotion_receipt_sha256,
        },
        "source_set": {
            "id": source_binding.source_set_id,
            "generation_id": source_binding.generation_id,
            "sha256": source_binding.sha256,
            "export_allowed": source_binding.export_allowed,
            "lock_sha256": source_binding.lock_sha256,
            "lock_artifact_sha256": source_binding.lock_artifact_sha256,
            "materialization_sha256": source_binding.materialization_sha256,
            "materialization_receipt_sha256": (
                source_binding.materialization_receipt_sha256
            ),
            "catalog_sha256": source_binding.catalog_sha256,
            "catalog_artifact_sha256": source_binding.catalog_artifact_sha256,
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
                "artifact_id": "lexical-fixture-v1",
                "artifact_sha256": hashes["index.lexical"],
                "source_set_sha256": source_binding.sha256,
                "semantic_generation": semantics.generation_id,
                "build_fingerprint": lexical_fingerprint.build_fingerprint,
                "embedding_model_fingerprint": None,
            },
            {
                "kind": "vector",
                "artifact_id": "vector-fixture-v1",
                "artifact_sha256": hashes["index.vector"],
                "source_set_sha256": source_binding.sha256,
                "semantic_generation": semantics.generation_id,
                "build_fingerprint": vector_fingerprint.build_fingerprint,
                "embedding_model_fingerprint": model_fingerprint,
            },
        ],
    }
    parsed = release.release_from_mapping(blob)
    blob["manifest_sha256"] = parsed.manifest_sha256
    installed = store.install_manifest(blob)
    runtime_root = store.runtime_root(release_id, create=True)
    runtime_artifact_paths: dict[str, str] = {}
    for key, source in paths.items():
        relative = {
            "main.state": "main/pipeline.json",
            "main.promotion_plan": "main/promotion-plan.json",
            "main.promotion_receipt": "main/promotion-receipt.json",
            "source_set.lock": "source/source-set.lock.json",
            "source_set.materialization": "source/materialized",
            "source_set.catalog": "source/catalog.json",
            "semantics.content": "semantics/content",
            "index.lexical": "indexes/lexical.json",
            "index.vector": "indexes/vector",
        }[key]
        destination = runtime_root / relative
        if source.is_dir():
            copy_tree_preserving_modes(source, destination)
        else:
            write_regular(destination, stable_regular_bytes(source))
        runtime_artifact_paths[key] = relative
    for package_id in ("public-external", "restricted-internal"):
        copy_tree_preserving_modes(
            packages_root / package_id,
            runtime_root / "source" / package_id,
        )
    runtime_catalog = catalog.load_installed_catalog(
        runtime_root / "source/catalog.json",
        expected_artifact_sha256=source_binding.catalog_artifact_sha256,
    )
    if runtime_catalog.catalog_sha256 != source_binding.catalog_sha256:
        raise RuntimeError("release catalog canonical identity drifted")
    runtime_catalog.resolve_lock(
        lock,
        expected_source_set_sha256=source_binding.sha256,
        expected_lock_sha256=source_binding.lock_sha256,
    )
    (runtime_root / "query/structure").mkdir(parents=True)
    (runtime_root / "query/custom").mkdir()
    write_regular(runtime_root / "query/glossary.json", canonical_bytes({"terms": []}))
    write_regular(
        runtime_root / "query/links.json",
        canonical_bytes({"links": [], "rel_fixes": []}),
    )
    runtime_paths = {
        "STRUCTURE_STORE": "query/structure",
        "STRUCTURE_CUSTOM_DIR": "query/custom",
        "GLOSSARY_STORE": "query/glossary.json",
        "RAG_LINKS_STORE": "query/links.json",
        "RAG_VECTOR_STORE": "indexes/vector",
    }
    binding = store.install_runtime_binding(
        release_id,
        paths=runtime_paths,
        artifact_paths=runtime_artifact_paths,
        created_at=NOW,
    )
    references = []
    for kind in RECEIPT_KINDS:
        result: Mapping[str, Any] = {
            "passed": True,
            "kind": kind,
            "release_id": release_id,
        }
        details: Mapping[str, Any] = {"validator": "adr0158-run013-holdout-v1"}
        if kind == "provenance":
            result = binding.provenance_result()
            details = binding.provenance_details()
        elif kind == "acl":
            result = {
                "schema_version": "runtime-services-admission-v1",
                "runtime_services": dict(acl_runtime_services),
            }
            details = {
                "validator": "adr0158-run013-holdout-v1",
                "runtime_services": dict(acl_runtime_services),
            }
        receipt = release.create_validation_receipt(
            kind=kind,
            receipt_id=f"{kind}-{release_id}",
            release=installed,
            created_at=NOW,
            result=result,
            details=details,
        )
        references.append(store.install_validation_receipt(receipt))
    return installed, tuple(references), binding, paths["main.state"]


def build_fixture(root: Path, candidate: CandidateIdentity) -> Fixture:
    if root.parent != Path("/tmp") or root.is_symlink() or not root.is_dir():
        raise RuntimeError("fixture root is not a fresh direct child of /tmp")
    probe = root / "posix-mode-probe"
    write_regular(probe, b"posix\n", 0o600)
    if stat.S_IMODE(probe.lstat().st_mode) != 0o600:
        raise RuntimeError("fixture filesystem does not preserve POSIX modes")
    probe.unlink()
    feedback_root = root / "feedback-output"
    feedback_root.mkdir(mode=0o700)
    feedback_root.chmod(0o700)
    secret_binding_root = root / "deployment-secrets"
    secret_binding_root.mkdir(mode=0o700)
    secret_binding_root.chmod(0o700)
    qdrant_secret_binding = {
        "schema_version": "runtime-secret-binding-v1",
        "binding_id": "run013-qdrant-key-slot",
        "binding_version": "fixture-v1",
    }
    qdrant_secret_path = secret_binding_root / (
        canonical_sha256(qdrant_secret_binding) + ".secret"
    )
    write_regular(
        qdrant_secret_path,
        b"run013-fixture-credential",
        mode=0o400,
    )
    qdrant_secret_path.chmod(0o400)
    qdrant_secret_file_sha256 = sha256_file(qdrant_secret_path)

    catalog = importlib.import_module("lawrag.datasets.catalog")
    release = importlib.import_module("lawrag.platform.release")
    snapshot_mod = importlib.import_module("lawrag.core.rag.content_snapshot")
    index_mod = importlib.import_module("lawrag.core.rag.index")
    search_mod = importlib.import_module("lawrag.core.rag.search")
    answer_mod = importlib.import_module("lawrag.core.rag.answer")
    embedding_mod = importlib.import_module("lawrag.core.embedding")
    runtime_services = importlib.import_module("lawrag.platform.runtime_services")
    llm_mod = importlib.import_module("lawrag.core.llm")
    llm_calls: list[Mapping[str, Any]] = []
    llm_structured_original = llm_mod.LLM.structured

    def forbid_product_llm(_self, *args, **kwargs):
        llm_calls.append(
            {
                "kind": str(args[0] if args else kwargs.get("kind") or "unknown"),
            }
        )
        raise AssertionError("product LLM call is forbidden in run-013")

    llm_mod.LLM.structured = forbid_product_llm

    authority_generation = "authority-fixture-v1"
    packages_root = root / "packages"
    packages_root.mkdir()
    external_payload = structure_payload(
        "doc-public",
        name="공개 외부 규정",
        title="외부 의무",
        surface="제1조",
        text="누구든지 외부 의무를 준수하여야 한다. 단, 내부 예외에 해당하면 제외한다.",
        kind="krx-rule",
        authority_generation=authority_generation,
    )
    internal_payload = structure_payload(
        "doc-internal",
        name="제한 내부 규정",
        title="내부 예외",
        surface="제2조",
        text="내부 적용 대상은 외부 의무에서 제외한다.",
        kind="internal",
        authority_generation=authority_generation,
    )
    links_payload = {
        "links": [
            {
                "src_doc": "doc-public",
                "src": 1,
                "dst_doc": "doc-internal",
                "dst": 1,
                "surface": "내부 예외",
                "key": ["내부", "예외"],
                "rel": "위임",
            }
        ],
        "rel_fixes": [],
    }
    external, external_manifest = write_dataset_package(
        catalog,
        packages_root,
        package_id="public-external",
        dataset_id="legal-corpus",
        version_id="public-v1",
        restricted=False,
        artifacts=[
            {
                "logical_id": "documents/public",
                "role": "structure",
                "path": "external-structure.json",
                "document_id": "doc-public",
                "payload": external_payload,
            },
            {
                "logical_id": "global/relations",
                "role": "relation",
                "path": "links.json",
                "payload": links_payload,
            },
        ],
    )
    internal, internal_manifest = write_dataset_package(
        catalog,
        packages_root,
        package_id="restricted-internal",
        dataset_id="internal-legal-corpus",
        version_id="internal-v1",
        restricted=True,
        artifacts=[
            {
                "logical_id": "documents/internal",
                "role": "structure",
                "path": "internal-structure.json",
                "document_id": "doc-internal",
                "payload": internal_payload,
            }
        ],
    )
    source_set_blob = {
        "schema_version": "source-set-v1",
        "source_set_id": "combined-serving-source",
        "generation_id": "combined-serving-generation-v1",
        "conflict_policy": "error",
        # The relation artifact below crosses the external/internal dataset
        # boundary.  Its permission is immutable SourceSet state rather than a
        # caller-controlled materialization flag.
        "cross_dataset_relations": True,
        "members": [
            {"package_id": external.package_id, "priority": 10},
            {"package_id": internal.package_id, "priority": 20},
        ],
    }
    view = catalog.compose_source_set(source_set_blob, [external, internal])
    lock = view.lock()

    catalog_artifact_path = root / "authority/installed-catalog.json"
    installed_catalog = _write_catalog_artifact(
        catalog,
        packages_root,
        [(external, external_manifest), (internal, internal_manifest)],
        catalog_artifact_path,
    )
    lock_artifact_path = root / "authority/source-set.lock.json"
    write_regular(lock_artifact_path, canonical_bytes(lock.receipt()))
    lock_artifact_sha256 = release.runtime_artifact_sha256(lock_artifact_path)
    catalog_artifact_sha256 = release.runtime_artifact_sha256(catalog_artifact_path)
    catalog_sha256 = installed_catalog.catalog_sha256
    resolved_packages = installed_catalog.resolve_lock(
        lock,
        expected_source_set_sha256=lock.source_set_sha256,
        expected_lock_sha256=lock.lock_sha256,
    )
    if {row.package_id for row in resolved_packages} != {
        external.package_id,
        internal.package_id,
    }:
        raise RuntimeError("installed catalog did not resolve the exact SourceSet")
    materialized_stage = catalog.materialize_source_set(
        view,
        root / "authority/materialized",
        lock=lock,
        for_export=False,
        trusted_root=root,
    )
    materialization_sha256 = release.runtime_artifact_sha256(materialized_stage.path)

    model_artifact_path = root / "encoder-model"
    model_artifact_path.mkdir(mode=0o700)
    model_config = model_artifact_path / "config.json"
    model_weights = model_artifact_path / "weights.fixture"
    write_regular(
        model_config,
        canonical_bytes(
            {
                "model_id": "fixture-encoder",
                "revision": "fixture-weights-v1",
                "dimensions": 8,
            }
        ),
        mode=0o400,
    )
    write_regular(model_weights, b"adr0158 deterministic encoder fixture\n", mode=0o400)
    model_artifact_path.chmod(0o500)
    model_artifact_sha256 = embedding_mod.local_model_artifact_sha256(
        model_artifact_path
    )
    if not SHA256_RE.fullmatch(model_artifact_sha256):
        raise RuntimeError("candidate local encoder returned an invalid artifact hash")
    os.environ["EMBED_MODEL_ARTIFACT_PATH"] = str(model_artifact_path)
    os.environ["EMBED_MODEL_SHA256"] = model_artifact_sha256

    semantic_content_path = root / "authority/semantics"
    semantic_content_path.mkdir(parents=True, exist_ok=False)
    (semantic_content_path / "runtime").mkdir()
    llm_descriptor_core = {
        "schema_version": "runtime-llm-binding-v1",
        "backend": "disabled",
        "model_id": "claude-haiku-4-5-20251001",
        "model_revision": None,
        "model_artifact_sha256": None,
        "endpoint": None,
        "serving_id": None,
        "tenant_id": None,
        "credential_binding_id": None,
        "credential_binding_version": None,
        "trust_policy_id": None,
        "trust_zone": "none",
        "temperature": 0,
        "json_mode": "json_schema",
    }
    llm_descriptor_path = semantic_content_path / "runtime/llm.json"
    write_regular(
        llm_descriptor_path,
        canonical_bytes(
            {
                **llm_descriptor_core,
                "descriptor_sha256": canonical_sha256(llm_descriptor_core),
            }
        ),
    )
    llm_descriptor = runtime_services.load_llm_descriptor(llm_descriptor_path)
    (semantic_content_path / "domain_graph").mkdir()
    write_regular(
        semantic_content_path / "domain_graph/canonical.json",
        canonical_bytes(
            {
                "schema_version": 1,
                "concepts": [],
                "relations": [],
                "assertions": [],
            }
        ),
    )
    write_regular(semantic_content_path / "aliases.json", canonical_bytes({}))
    write_regular(
        semantic_content_path / "delegation.json",
        canonical_bytes(
            {
                "edges": [
                    {
                        "kind": "시행규칙",
                        "src": {
                            "doc_id": "doc-public",
                            "node": 1,
                            "anchor": "제1조",
                        },
                        "dst": {
                            "doc_id": "doc-internal",
                            "node": 1,
                            "name": "제한 내부 규정",
                            "jo": "제2조",
                        },
                        "link": "내부 예외",
                    }
                ]
            }
        ),
    )
    write_regular(semantic_content_path / "law_index.json", canonical_bytes({}))
    for relative in ("frames", "taxonomy", "lexicon", "wiki/wiki", "rules"):
        (semantic_content_path / relative).mkdir(parents=True)
    write_regular(
        semantic_content_path / "rules/engine.json",
        canonical_bytes({"switches": {}}),
    )
    write_regular(
        semantic_content_path / "assertion_shortcuts.disabled.json",
        canonical_bytes({"records": []}),
    )
    write_regular(
        semantic_content_path / "scopes.yml",
        b"scopes: []\n",
    )
    semantic_sha = release.runtime_artifact_sha256(semantic_content_path)
    source_binding = release.SourceSetBinding(
        source_set_id=lock.source_set_id,
        generation_id=lock.generation_id,
        sha256=lock.source_set_sha256,
        export_allowed=lock.export_allowed,
        lock_sha256=lock.lock_sha256,
        lock_artifact_sha256=lock_artifact_sha256,
        materialization_sha256=materialization_sha256,
        materialization_receipt_sha256=materialized_stage.receipt_sha256,
        catalog_sha256=catalog_sha256,
        catalog_artifact_sha256=catalog_artifact_sha256,
    )
    semantics = release.SemanticBinding(
        generation_id="semantic-fixture-v1",
        authority_generation=authority_generation,
        content_sha256=semantic_sha,
        source_set_sha256=lock.source_set_sha256,
        runtime_wired=True,
    )
    input_artifacts = {
        **{row.qualified_id: row.sha256 for row in lock.artifacts},
        "semantic-content": semantic_sha,
    }
    lexical_fingerprint = release.create_index_build_fingerprint(
        kind="lexical",
        source_set=source_binding,
        semantics=semantics,
        builder_id="lexical-fixture-builder",
        builder_revision="a" * 40,
        input_artifacts=input_artifacts,
        configuration={"tokenizer": "fixture-v1", "normalization": "space-casefold"},
    )
    model_fingerprint = release.embedding_model_fingerprint(
        backend="local",
        model_id="fixture-encoder",
        model_revision="fixture-weights-v1",
        model_artifact_sha256=model_artifact_sha256,
        dimensions=8,
        normalized=True,
        document_profile="lawrag-shared-encode-v1",
        query_profile="lawrag-shared-encode-v1",
    )
    qdrant_core = {
        "schema_version": "rag-qdrant-runtime-binding-v1",
        "url": "http://127.0.0.1:6333",
        "collection": "adr0158_run013",
        "credential_binding_id": "run013-qdrant-key-slot",
        "credential_binding_version": "fixture-v1",
        "trust_policy_id": "restricted-internal-only-v1",
        "trust_zone": "internal",
    }
    qdrant_config_sha256 = canonical_sha256(qdrant_core)
    qdrant_raw = canonical_bytes(
        {**qdrant_core, "config_sha256": qdrant_config_sha256}
    )
    qdrant_config = {**qdrant_core, "config_sha256": qdrant_config_sha256}
    feedback_trust_policy_id = "restricted-feedback-output-v1"
    feedback_projection = runtime_services.feedback_acl_projection(
        root=feedback_root,
        trust_zone="internal",
        trust_policy_id=feedback_trust_policy_id,
        export_allowed=lock.export_allowed,
    )
    runtime_acl_services = {
        "qdrant": runtime_services.qdrant_acl_projection(qdrant_config),
        "feedback": feedback_projection,
    }
    vector_fingerprint = release.create_index_build_fingerprint(
        kind="vector",
        source_set=source_binding,
        semantics=semantics,
        builder_id="vector-fixture-builder",
        builder_revision="b" * 40,
        input_artifacts=input_artifacts,
        configuration={
            "metric": "cosine",
            "dimensions": 8,
            "backend": "qdrant",
            "qdrant_config_sha256": qdrant_config_sha256,
            "qdrant_trust_zone": "internal",
        },
        model_fingerprint=model_fingerprint,
    )
    structure_rows = [
        {
            "document_id": row.document_id,
            "qualified_id": row.qualified_id,
            "sha256": row.sha256,
        }
        for row in lock.artifacts
        if row.role == "structure"
    ]
    structure_rows.sort(key=lambda row: str(row["document_id"]))
    lexical_core = {
        "schema_version": "rag-lexical-index-identity-v1",
        "artifact_id": "lexical-fixture-v1",
        "source_set_id": lock.source_set_id,
        "source_set_generation": lock.generation_id,
        "source_set_sha256": lock.source_set_sha256,
        "semantic_generation": semantics.generation_id,
        "authority_generation": semantics.authority_generation,
        "build_fingerprint": lexical_fingerprint.build_fingerprint,
        "document_ids": ["doc-internal", "doc-public"],
        "structure_artifacts": structure_rows,
        "entry_count": 2,
    }
    lexical_identity_raw = canonical_bytes(
        {**lexical_core, "identity_sha256": canonical_sha256(lexical_core)}
    )
    vector_meta_raw = b'{"doc_id":"doc-public","node":1}\n'
    vector_values_raw = deterministic_vector_npz()
    vector_identity_core = {
        "schema_version": "rag-vector-index-identity-v1",
        "source_set_id": lock.source_set_id,
        "source_set_generation": lock.generation_id,
        "source_set_sha256": lock.source_set_sha256,
        "semantic_generation": semantics.generation_id,
        "authority_generation": semantics.authority_generation,
        "index_build_fingerprint": vector_fingerprint.build_fingerprint,
        "embedding_model_fingerprint": model_fingerprint,
        "meta_sha256": sha256_bytes(vector_meta_raw),
        "vectors_sha256": sha256_bytes(vector_values_raw),
        "row_count": 1,
    }
    encoder_descriptor_core = {
        "schema_version": "runtime-embedding-binding-v1",
        "backend": "local",
        "model_id": "fixture-encoder",
        "model_revision": "fixture-weights-v1",
        "model_artifact_sha256": model_artifact_sha256,
        "endpoint": None,
        "serving_id": None,
        "tenant_id": None,
        "credential_binding_id": None,
        "credential_binding_version": None,
        "trust_policy_id": None,
        "trust_zone": "local",
        "dimensions": 8,
        "normalized": True,
        "document_profile": "lawrag-shared-encode-v1",
        "query_profile": "lawrag-shared-encode-v1",
    }
    encoder_descriptor_path = root / "authority/encoder.json"
    encoder_descriptor_raw = canonical_bytes(
        {
            **encoder_descriptor_core,
            "descriptor_sha256": canonical_sha256(encoder_descriptor_core),
        }
    )
    write_regular(encoder_descriptor_path, encoder_descriptor_raw)
    encoder_descriptor = runtime_services.load_embedding_descriptor(
        encoder_descriptor_path
    )
    vector_files = {
        "identity.json": canonical_bytes(
            {
                **vector_identity_core,
                "identity_sha256": canonical_sha256(vector_identity_core),
            }
        ),
        "meta.jsonl": vector_meta_raw,
        "vectors.npz": vector_values_raw,
        "qdrant.json": qdrant_raw,
        "encoder.json": encoder_descriptor_raw,
    }

    store = release.ReleaseStore(
        root / "release-store",
        target="genos",
        code_package_root=candidate.revision_root,
        clock=lambda: NOW,
    )
    main_zero = _main_state(0, adapter_on=False)
    main_a = _main_state(1, adapter_on=True)
    main_b = _main_state(2, adapter_on=True)
    main_plan_a = _main_promotion_plan(main_zero, main_a)
    main_plan_b = _main_promotion_plan(main_a, main_b)
    main_plan_root = root / "authority/main-promotion-plans"
    main_plan_root.mkdir(parents=True)
    main_plan_a_path = main_plan_root / "generation-1.json"
    main_plan_b_path = main_plan_root / "generation-2.json"
    write_regular(main_plan_a_path, canonical_bytes(main_plan_a))
    write_regular(main_plan_b_path, canonical_bytes(main_plan_b))
    main_plan_a_sha256 = sha256_file(main_plan_a_path)
    main_plan_b_sha256 = sha256_file(main_plan_b_path)
    main_promotion_mod = importlib.import_module(
        "lawrag.core.rag.main_promotion"
    )
    receipt_a = _main_promotion_receipt(
        main_zero, main_a, plan=main_plan_a
    )
    receipt_b = _main_promotion_receipt(
        main_a, main_b, plan=main_plan_b
    )
    for plan_blob, receipt_blob, state in (
        (main_plan_a, receipt_a, main_a),
        (main_plan_b, receipt_b, main_b),
    ):
        transition_errors = main_promotion_mod.validate_transition_receipt(
            receipt_blob, state
        )
        plan_errors = main_promotion_mod.validate_runtime_promotion_plan(
            plan_blob, receipt_blob, state
        )
        if transition_errors or plan_errors:
            raise RuntimeError(
                "MAIN promotion fixture is invalid: "
                + "; ".join((*transition_errors, *plan_errors))
            )
    main_chain_a = main_promotion_mod.build_transition_chain(
        [receipt_a], main_a
    )
    main_chain_b = main_promotion_mod.build_transition_chain(
        [receipt_a, receipt_b], main_b
    )
    main_receipt_root = root / "authority/main-transition-chains"
    main_receipt_root.mkdir(parents=True)
    main_receipt_a_path = main_receipt_root / "generation-1.json"
    main_receipt_b_path = main_receipt_root / "generation-2.json"
    write_regular(main_receipt_a_path, canonical_bytes(main_chain_a))
    write_regular(main_receipt_b_path, canonical_bytes(main_chain_b))
    main_receipt_a_sha256 = _validate_main_transition_chain(
        main_receipt_a_path,
        state=main_a,
        main_promotion=main_promotion_mod,
    )
    main_receipt_b_sha256 = _validate_main_transition_chain(
        main_receipt_b_path,
        state=main_b,
        main_promotion=main_promotion_mod,
    )
    if (
        main_promotion_mod.transition_chain_tip(main_chain_a)[
            "promotion_plan"
        ]
        != main_plan_a
        or main_promotion_mod.transition_chain_tip(main_chain_b)[
            "promotion_plan"
        ]
        != main_plan_b
    ):
        raise RuntimeError("MAIN chain tip does not embed its standalone plan")
    if main_promotion_mod.validate_state(main_zero):
        raise RuntimeError("generation-zero MAIN fixture is not canonical")
    off_store = release.ReleaseStore(
        root / "release-store-off",
        target="genos",
        code_package_root=candidate.revision_root,
        clock=lambda: NOW,
    )
    release_off, refs_off, binding_off, _ = _release_fixture(
        root,
        candidate,
        catalog,
        release,
        lock,
        materialized_stage,
        catalog_artifact_path,
        packages_root,
        semantic_content_path,
        release_id="release-content-off",
        main_state=main_zero,
        main_promotion_plan_path=None,
        main_promotion_plan_sha256=None,
        main_promotion_receipt_path=None,
        main_promotion_receipt_sha256=None,
        source_binding=source_binding,
        semantics=semantics,
        lexical_fingerprint=lexical_fingerprint,
        vector_fingerprint=vector_fingerprint,
        model_fingerprint=model_fingerprint,
        lexical_identity_raw=lexical_identity_raw,
        vector_files=vector_files,
        acl_runtime_services=runtime_acl_services,
        store=off_store,
    )
    off_activation = off_store.prepare_activation(
        release_off.release_id,
        activation_id="activate-content-off",
        validation_receipts=refs_off,
        created_at=NOW,
    )
    off_store.activate(
        off_activation,
        actor="adr0158-run013",
        note="activate canonical SourceSet OFF release",
        confirm=True,
    )
    off_pointer, loaded_off, loaded_off_binding = off_store.load_active_runtime()
    if (
        loaded_off != release_off
        or loaded_off_binding != binding_off
        or off_pointer.action != "activate"
    ):
        raise RuntimeError("SourceSet OFF release did not round-trip")
    off_release_main_path = Path(
        binding_off.resolved_artifacts(
            off_store.runtime_root(release_off.release_id)
        )["main.state"]
    )
    release_a, refs_a, binding_a, main_a_stage = _release_fixture(
        root,
        candidate,
        catalog,
        release,
        lock,
        materialized_stage,
        catalog_artifact_path,
        packages_root,
        semantic_content_path,
        release_id="release-content-a",
        main_state=main_a,
        main_promotion_plan_path=main_plan_a_path,
        main_promotion_plan_sha256=main_plan_a_sha256,
        main_promotion_receipt_path=main_receipt_a_path,
        main_promotion_receipt_sha256=main_receipt_a_sha256,
        source_binding=source_binding,
        semantics=semantics,
        lexical_fingerprint=lexical_fingerprint,
        vector_fingerprint=vector_fingerprint,
        model_fingerprint=model_fingerprint,
        lexical_identity_raw=lexical_identity_raw,
        vector_files=vector_files,
        acl_runtime_services=runtime_acl_services,
        store=store,
    )
    plan_a = store.prepare_activation(
        release_a.release_id,
        activation_id="activate-content-a",
        validation_receipts=refs_a,
        created_at=NOW,
    )
    store.activate(plan_a, actor="adr0158-run013", note="activate A", confirm=True)
    release_b, refs_b, binding_b, main_b_stage = _release_fixture(
        root,
        candidate,
        catalog,
        release,
        lock,
        materialized_stage,
        catalog_artifact_path,
        packages_root,
        semantic_content_path,
        release_id="release-content-b",
        main_state=main_b,
        main_promotion_plan_path=main_plan_b_path,
        main_promotion_plan_sha256=main_plan_b_sha256,
        main_promotion_receipt_path=main_receipt_b_path,
        main_promotion_receipt_sha256=main_receipt_b_sha256,
        source_binding=source_binding,
        semantics=semantics,
        lexical_fingerprint=lexical_fingerprint,
        vector_fingerprint=vector_fingerprint,
        model_fingerprint=model_fingerprint,
        lexical_identity_raw=lexical_identity_raw,
        vector_files=vector_files,
        acl_runtime_services=runtime_acl_services,
        store=store,
    )
    plan_b = store.prepare_activation(
        release_b.release_id,
        activation_id="activate-content-b",
        validation_receipts=refs_b,
        created_at=NOW,
    )
    store.activate(plan_b, actor="adr0158-run013", note="activate B", confirm=True)
    pointer_b, active_b, loaded_binding_b = store.load_active_runtime()
    if active_b != release_b or loaded_binding_b != binding_b:
        raise RuntimeError("active release B did not round-trip")
    runtime_root_b = store.runtime_root(release_b.release_id)
    runtime_paths_b = binding_b.resolved_paths(runtime_root_b)
    runtime_artifacts_b = binding_b.resolved_artifacts(runtime_root_b)
    loaded_lock = catalog.load_source_set_lock(
        runtime_artifacts_b["source_set.lock"],
        expected_artifact_sha256=release_b.source_set.lock_artifact_sha256,
    )
    materialized_b = catalog.open_materialized_source_set(
        runtime_artifacts_b["source_set.materialization"],
        loaded_lock,
        trusted_root=runtime_root_b,
    )
    snapshot = snapshot_mod.create_content_snapshot(
        pointer=pointer_b,
        release=release_b,
        runtime_binding=binding_b,
        source_set_lock=loaded_lock,
        catalog_sha256=catalog_sha256,
        catalog_artifact_sha256=catalog_artifact_sha256,
        materialized=materialized_b,
        runtime_paths=runtime_paths_b,
        runtime_artifact_paths=runtime_artifacts_b,
    )
    deployment_controls = root / "deployment-controls"
    deployment_controls.mkdir(mode=0o700)
    reviewed_shortcut_path = deployment_controls / "reviewed-candidates.json"
    reviewed_shortcut_row = {
        "qkey": index_mod.norm("외부 의무"),
        "surfaces": ["외부 의무"],
        "doc_id": "doc-public",
        "node": 1,
        "via": "run-013-reviewed-feedback",
        "count": 1,
        "first": NOW,
        "last": NOW,
        "status": "활성",
        "cards": [],
        "issues": [],
        "content_snapshot": snapshot.compact_receipt(),
        "content_provenance": snapshot.provenance_for_document(
            "doc-public"
        ).receipt(),
    }
    write_regular(
        reviewed_shortcut_path,
        canonical_bytes({"candidates": [reviewed_shortcut_row]}),
        mode=0o400,
    )
    reviewed_shortcut_sha256 = sha256_file(reviewed_shortcut_path)
    main_a_path = Path(binding_a.resolved_artifacts(store.runtime_root(release_a.release_id))["main.state"])
    main_b_path = Path(runtime_artifacts_b["main.state"])
    if json.loads(stable_regular_bytes(main_a_path)) != main_a:
        raise RuntimeError("release A MAIN state drifted")
    if json.loads(stable_regular_bytes(main_b_path)) != main_b:
        raise RuntimeError("release B MAIN state drifted")
    off_main_path = root / "legacy/main-off.json"
    write_regular(off_main_path, canonical_bytes(_main_state(0, adapter_on=False)))
    return Fixture(
        root=root,
        candidate=candidate,
        catalog_mod=catalog,
        release_mod=release,
        snapshot_mod=snapshot_mod,
        index_mod=index_mod,
        search_mod=search_mod,
        answer_mod=answer_mod,
        llm_mod=llm_mod,
        llm_structured_original=llm_structured_original,
        llm_calls=llm_calls,
        network_calls=[],
        external=external,
        internal=internal,
        external_manifest=external_manifest,
        internal_manifest=internal_manifest,
        external_structure_path=packages_root / "public-external/external-structure.json",
        source_set_blob=source_set_blob,
        view=view,
        lock=lock,
        materialized_stage=materialized_stage,
        installed_catalog=installed_catalog,
        catalog_artifact_path=catalog_artifact_path,
        catalog_sha256=catalog_sha256,
        catalog_artifact_sha256=catalog_artifact_sha256,
        lock_artifact_path=lock_artifact_path,
        lock_artifact_sha256=lock_artifact_sha256,
        materialization_sha256=materialization_sha256,
        store=store,
        off_store=off_store,
        release_off=release_off,
        binding_off=binding_off,
        off_release_main_path=off_release_main_path,
        release_a=release_a,
        release_b=release_b,
        refs_a=refs_a,
        refs_b=refs_b,
        binding_a=binding_a,
        binding_b=binding_b,
        lexical_fingerprint=lexical_fingerprint,
        vector_fingerprint=vector_fingerprint,
        model_fingerprint=model_fingerprint,
        model_artifact_path=model_artifact_path,
        model_artifact_sha256=model_artifact_sha256,
        llm_descriptor=llm_descriptor,
        encoder_descriptor=encoder_descriptor,
        qdrant_url=qdrant_core["url"],
        qdrant_collection=qdrant_core["collection"],
        qdrant_config_sha256=qdrant_config_sha256,
        pointer_b=pointer_b,
        snapshot=snapshot,
        materialized_b=materialized_b,
        runtime_paths_b=runtime_paths_b,
        runtime_artifacts_b=runtime_artifacts_b,
        main_a=main_a,
        main_b=main_b,
        main_plan_a_sha256=main_plan_a_sha256,
        main_plan_b_sha256=main_plan_b_sha256,
        main_receipt_a_sha256=main_receipt_a_sha256,
        main_receipt_b_sha256=main_receipt_b_sha256,
        main_a_path=main_a_path,
        main_b_path=main_b_path,
        off_main_path=off_main_path,
        feedback_root=feedback_root,
        feedback_root_sha256=str(feedback_projection["root_sha256"]),
        feedback_trust_policy_id=feedback_trust_policy_id,
        secret_binding_root=secret_binding_root,
        qdrant_secret_file_sha256=qdrant_secret_file_sha256,
        reviewed_shortcut_path=reviewed_shortcut_path,
        reviewed_shortcut_sha256=reviewed_shortcut_sha256,
    )


def configure_fixture_environment(root: Path) -> None:
    values = {
        "LOG_DIR": root / "feedback-output/logs",
        "RAG_EVENTS_LOG": root / "feedback-output/logs/rag_events.jsonl",
        "RAG_LOG_DIR": root / "feedback-output",
        "RAG_RULES_DIR": root / "rules",
        "RAG_ENGINE_RULES": root / "rules/engine.json",
        "RAG_DELEGATION_STORE": root / "query/delegation.json",
        "RAG_LAW_INDEX_STORE": root / "query/law-index.json",
        "RAG_SCOPES_FILE": root / "query/scopes.yml",
        "RAG_MAIN_PROMOTION_RECEIPTS": root / "main/promotion-receipts.jsonl",
        "STRUCTURE_STORE": root / "legacy/structure",
        "STRUCTURE_CUSTOM_DIR": root / "legacy/custom",
        "GLOSSARY_STORE": root / "legacy/glossary.json",
        "RAG_LINKS_STORE": root / "legacy/links.json",
        "RAG_VECTOR_STORE": root / "legacy/vector",
        "OPS_DIR": root / "ops-disabled",
        "LAWRAG_SECRET_BINDING_ROOT": root / "deployment-secrets",
    }
    for key, value in values.items():
        os.environ[key] = str(value)
    os.environ.update(
        {
            "STRUCTURE_PREHEAT": "0",
            "RAG_RULES_MODE": "off",
            "RAG_VECTOR": "1",
            "RAG_LEXICON_DOCS": "",
            "RAG_SPOT_MAX_TOKENS": "1000",
            "RAG_QUERY_GUIDE_MENTIONS_MAX": "12",
            "RAG_QUERY_GUIDE_READINGS_MAX": "12",
            "RAG_QUERY_GUIDE_PROMPT_CHARS": "12000",
            "RAG_VECTOR_MIN": "0.45",
            "RAG_REF_DEPTH": "3",
            "RAG_RECOVER_MIN_CONF": "0.50",
            "RAG_TAXONOMY_WORKERS": "1",
            "RAG_FRAMES_WORKERS": "1",
            "RAG_FRAMES_MAX_TOKENS": "4000",
            "MAX_UPLOAD_MB": "40",
            "STRUCTURE_RENDER_SCALE": "2.0",
            "OPS_INBOX_POLL": "10",
            "OPS_INBOX_DIR": "",
            "OPS_RECORD": "0",
            "OPS_ALLOW_RESTORE": "0",
            "RAG_RECOVER_MODEL": "claude-haiku-4-5-20251001",
            "RAG_FRAMES_MODEL": "claude-haiku-4-5-20251001",
            "RAG_TAXONOMY_MODEL": "claude-haiku-4-5-20251001",
            "RAG_LEGALCLOSURE_ASSERTION_MODEL": (
                "claude-haiku-4-5-20251001"
            ),
            "LOG_LEVEL": "WARNING",
            "LAWRAG_RELEASE_REQUIRED": "1",
            "LAWRAG_SERVING_SEALED": "0",
            "LAWRAG_FEEDBACK_TRUST_ZONE": "internal",
            "EMBED_BACKEND": "local",
            "EMBED_MODEL": "fixture-encoder",
            "EMBED_MODEL_REVISION": "fixture-weights-v1",
            "EMBED_MODEL_SHA256": "",
            "EMBED_DIMENSIONS": "8",
            "GENOS_EMBED_MODEL_SHA256": "",
            "LLM_BACKEND": "",
            "LOCAL_LLM_URL": "",
            "LOCAL_LLM_KEY": "",
            "LOCAL_LLM_MODEL": "",
            "LOCAL_LLM_TEMPERATURE": "",
            "LOCAL_LLM_JSON_MODE": "",
            "GENOS_LLM_URL": "",
            "GENOS_BASE_URL": "",
            "GENOS_LLM_SERVING_ID": "",
            "GENOS_LLM_PROFILE": "",
            "GENOS_LLM_KEY": "",
            "OPEN_ROUTER": "",
            "OPENROUTER_URL": "",
            "OPENROUTER_MODEL": "",
            "OPENROUTER_TEMPERATURE": "",
            "OPENROUTER_JSON_MODE": "",
            "ANTHROPIC_MODEL": "",
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "QDRANT_API_KEY": "",
        }
    )


def activate_fixture_environment(fixture: Fixture) -> None:
    os.environ["LAWRAG_RELEASE_STORE"] = str(fixture.store.root)
    os.environ["LAWRAG_CODE_PACKAGE_ROOT"] = str(fixture.candidate.revision_root)
    os.environ["RAG_MAIN_PIPELINE_MANIFEST"] = str(fixture.main_b_path)
    os.environ["RAG_EMBEDDING_MODEL_FINGERPRINT"] = fixture.model_fingerprint
    os.environ["LAWRAG_ADMITTED_LLM_DESCRIPTOR_SHA256"] = (
        fixture.llm_descriptor["descriptor_sha256"]
    )
    os.environ["LAWRAG_ADMITTED_ENCODER_DESCRIPTOR_SHA256"] = (
        fixture.encoder_descriptor["descriptor_sha256"]
    )
    os.environ["LAWRAG_ADMITTED_QDRANT_DESCRIPTOR_SHA256"] = (
        fixture.qdrant_config_sha256
    )
    os.environ["EMBED_MODEL_ARTIFACT_PATH"] = str(fixture.model_artifact_path)
    os.environ["EMBED_MODEL_SHA256"] = fixture.model_artifact_sha256
    os.environ["EMBED_LOCAL_FILES_ONLY"] = "1"
    os.environ["EMBED_DEVICE"] = "cpu"
    os.environ["EMBED_CPU_THREADS"] = "4"
    os.environ["LAWRAG_EMBEDDING_DISABLED"] = "0"
    os.environ["QDRANT_URL"] = fixture.qdrant_url
    os.environ["QDRANT_COLLECTION"] = fixture.qdrant_collection
    os.environ["QDRANT_CREDENTIAL_BINDING_ID"] = "run013-qdrant-key-slot"
    os.environ["QDRANT_CREDENTIAL_BINDING_VERSION"] = "fixture-v1"
    os.environ["QDRANT_TRUST_POLICY_ID"] = "restricted-internal-only-v1"
    os.environ["QDRANT_TRUST_ZONE"] = "internal"
    os.environ["QDRANT_API_KEY"] = ""
    os.environ["LAWRAG_SECRET_BINDING_ROOT"] = str(
        fixture.secret_binding_root
    )
    os.environ["QDRANT_TIMEOUT"] = "30"
    os.environ["LAWRAG_SERVING_SEALED"] = "1"
    for key, value in fixture.runtime_paths_b.items():
        os.environ[key] = value
    semantic_root = Path(fixture.runtime_artifacts_b["semantics.content"])
    semantic_paths = {
        "LEGAL_GRAPH_STORE": semantic_root,
        "RAG_DOMAIN_GRAPH": semantic_root / "domain_graph/graph.sqlite",
        "RAG_CONCEPT_REGISTRY": semantic_root / "domain_graph/canonical.json",
        "RAG_DELEGATION_STORE": semantic_root / "delegation.json",
        "RAG_LAW_INDEX_STORE": semantic_root / "law_index.json",
        "RAG_ALIASES_STORE": semantic_root / "aliases.json",
        "RAG_ALIASES": semantic_root / "aliases.json",
        "RAG_FRAMES_DIR": semantic_root / "frames",
        "RAG_TAXONOMY_DIR": semantic_root / "taxonomy",
        "RAG_LEXICON_DIR": semantic_root / "lexicon",
        "WIKI_STORE": semantic_root / "wiki",
        "RAG_RULES_DIR": semantic_root / "rules",
        "RAG_ENGINE_RULES": semantic_root / "rules/engine.json",
        "RAG_ASSERTION_SHORTCUT_STORE": (
            semantic_root / "assertion_shortcuts.disabled.json"
        ),
        "RAG_SCOPES_FILE": semantic_root / "scopes.yml",
    }
    for key, value in semantic_paths.items():
        os.environ[key] = str(value)
    os.environ["LAWRAG_FEEDBACK_ROOT"] = str(fixture.feedback_root)
    os.environ["LAWRAG_FEEDBACK_TRUST_ZONE"] = "internal"
    os.environ["LAWRAG_ADMITTED_FEEDBACK_ROOT_SHA256"] = (
        fixture.feedback_root_sha256
    )
    os.environ["LAWRAG_FEEDBACK_TRUST_POLICY_ID"] = (
        fixture.feedback_trust_policy_id
    )
    os.environ["RAG_LOG_DIR"] = str(fixture.feedback_root)
    os.environ["LOG_DIR"] = str(fixture.feedback_root / "logs")
    os.environ["RAG_EVENTS_LOG"] = str(
        fixture.feedback_root / "logs/rag_events.jsonl"
    )
    os.environ["RAG_APPROVAL_RECEIPTS"] = str(
        fixture.feedback_root / "approval_receipts.jsonl"
    )
    os.environ["LAWRAG_QUERY_SHORTCUT_STORE"] = str(
        fixture.reviewed_shortcut_path
    )
    os.environ["RAG_QUERY_SHORTCUT_STORE"] = str(fixture.reviewed_shortcut_path)
    os.environ["LAWRAG_QUERY_SHORTCUT_STORE_SHA256"] = (
        fixture.reviewed_shortcut_sha256
    )
    os.environ["LAWRAG_FEEDBACK_DISABLED"] = "0"
    os.environ["LAWRAG_QUERY_SHORTCUTS_DISABLED"] = "0"
    os.environ["RAG_DOMAIN"] = "law"
    os.environ["RAG_LEXICON_COMPILE_MISSING"] = "0"
    os.environ["RAG_VECTOR_BACKEND"] = "qdrant"


def ensure_snapshot(fixture: Fixture) -> None:
    activate_fixture_environment(fixture)
    switches_mod = importlib.import_module("lawrag.core.rag.switches")
    switches_mod.bind_sealed_promotion_overrides(
        dict(fixture.main_b["switches"]),
        main_state_sha256=fixture.release_b.main.state_sha256,
    )
    fixture.snapshot_mod.bind_content_snapshot(fixture.snapshot)
    embedding_mod = importlib.import_module("lawrag.core.embedding")
    encoder_identity = embedding_mod.runtime_identity()
    if embedding_mod.runtime_fingerprint() != fixture.model_fingerprint:
        raise AssertionError("fixture encoder runtime identity is not release-bound")
    receipt = fixture.snapshot_mod.create_retrieval_runtime_receipt(
        fixture.snapshot,
        llm_runtime={
            "enabled": False,
            "backend": "disabled",
            "model": "claude-haiku-4-5-20251001",
            "model_revision": None,
            "model_artifact_sha256": None,
            "endpoint": None,
            "serving_id": None,
            "tenant_id": None,
            "descriptor_sha256": fixture.llm_descriptor[
                "descriptor_sha256"
            ],
            "credential_binding_id": None,
            "credential_binding_version": None,
            "trust_policy_id": None,
            "credential_presence": {},
            "trust_zone": "none",
            "export_allowed": fixture.release_b.source_set.export_allowed,
        },
        vector_runtime={
            "enabled": True,
            "backend": "qdrant",
            "config_sha256": fixture.qdrant_config_sha256,
            "query_timeout_seconds": 30,
            "trust_zone": "internal",
            "url": fixture.qdrant_url,
            "collection": fixture.qdrant_collection,
            "credential_binding_id": "run013-qdrant-key-slot",
            "credential_binding_version": "fixture-v1",
            "trust_policy_id": "restricted-internal-only-v1",
            "credential_configured": True,
            "encoder": {
                "backend": "local",
                "endpoint": None,
                "serving_id": None,
                "tenant_id": None,
                "trust_zone": "local",
                "model_id": encoder_identity["model_id"],
                "model_revision": encoder_identity["model_revision"],
                "model_artifact_sha256": encoder_identity[
                    "model_artifact_sha256"
                ],
                "dimensions": encoder_identity["dimensions"],
                "descriptor_sha256": fixture.encoder_descriptor[
                    "descriptor_sha256"
                ],
                "credential_binding_id": None,
                "credential_binding_version": None,
                "trust_policy_id": None,
                "local_artifact_verified": True,
                "credential_presence": {},
            },
        },
        shortcut_runtime={
            "enabled": True,
            "sha256": fixture.reviewed_shortcut_sha256,
        },
    )
    fixture.snapshot_mod.bind_retrieval_runtime_receipt(receipt)
    if fixture.retrieval_runtime is not None and fixture.retrieval_runtime != receipt:
        raise AssertionError("fixture retrieval runtime receipt changed")
    fixture.retrieval_runtime = receipt
    if fixture.index is None:
        fixture.index = fixture.index_mod.Index.load(content_snapshot=fixture.snapshot)


def _contains_key(value: object, prefix: str) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).startswith(prefix) or _contains_key(child, prefix)
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_key(child, prefix) for child in value)
    return False


def case_legacy_off_byte_equivalence(fixture: Fixture) -> Mapping[str, Any]:
    fixture.snapshot_mod.reset_content_snapshot_for_tests()
    os.environ["RAG_MAIN_PIPELINE_MANIFEST"] = str(fixture.off_main_path)
    os.environ["LAWRAG_SERVING_SEALED"] = "0"
    legacy_store = fixture.root / "legacy/structure"
    document = legacy_store / "doc-legacy"
    document.mkdir(parents=True, exist_ok=True)
    payload = structure_payload(
        "doc-legacy",
        name="레거시 공개 규정",
        title="외부 의무",
        surface="제1조",
        text="누구든지 외부 의무를 준수하여야 한다.",
        kind="krx-rule",
        authority_generation="",
    )
    write_regular(document / "meta.json", canonical_bytes(payload["meta"]))
    write_regular(document / "result.json", canonical_bytes(payload["result"]))
    glossary = fixture.root / "legacy/glossary.json"
    links = fixture.root / "legacy/links.json"
    write_regular(glossary, canonical_bytes({"terms": []}))
    write_regular(links, canonical_bytes({"links": [], "rel_fixes": []}))
    legacy = fixture.index_mod.Index.load(
        store=legacy_store,
        terms_file=glossary,
        links_file=links,
        content_snapshot=None,
    )
    rag_router = importlib.import_module("lawrag.api.routers.rag")
    original_current = rag_router.index_mod.current
    original_apply = rag_router.scopes_mod.apply
    rag_router.index_mod.current = lambda: legacy
    rag_router.scopes_mod.apply = lambda index, _scope, _default: (index, {})
    try:
        response = rag_router.rag_search(q="외부 의무", mode="auto", scope="")
    finally:
        rag_router.index_mod.current = original_current
        rag_router.scopes_mod.apply = original_apply
    expected = {
        "query": "외부 의무",
        "mode": "정확",
        "ladder": [
            {
                "stage": "정확 일치",
                "count": 1,
                "note": "색인값이 질의 안에 통째로 있음 — 부분 일치는 돌지 않음",
            }
        ],
        "hits": [
            {
                "kind": "제목",
                "value": "외부 의무",
                "score": 1.0,
                "match": "정확",
                "reasons": ["질의에 '외부 의무' 포함"],
                "doc_id": "doc-legacy",
                "doc": "레거시 공개 규정",
                "node": 1,
                "block": None,
                "occurrences": 0,
            }
        ],
        "scope": None,
        "documents": 1,
        "entries": 1,
    }
    expected_raw = canonical_bytes(expected)
    actual_raw = canonical_bytes(response)
    if actual_raw != expected_raw:
        raise AssertionError("legacy API projection is not byte-equivalent")
    if _contains_key(response, "content_"):
        raise AssertionError("legacy OFF response gained content snapshot fields")
    if (
        legacy.content_snapshot is not None
        or legacy.content_snapshot_sha256
        or legacy.content_fingerprint
        or legacy.docs["doc-legacy"].content_provenance is not None
    ):
        raise AssertionError("legacy index gained snapshot state")
    release_off = fixture.release_off
    semantic_snapshot = {
        "generation_id": release_off.semantics.generation_id,
        "authority_generation": release_off.semantics.authority_generation,
        "content_sha256": release_off.semantics.content_sha256,
        "source_set_sha256": release_off.semantics.source_set_sha256,
        "runtime_wired": True,
    }
    index_snapshots = {
        row.kind: {
            "artifact_id": row.artifact_id,
            "artifact_sha256": row.artifact_sha256,
            "source_set_sha256": row.source_set_sha256,
            "semantic_generation": row.semantic_generation,
            "build_fingerprint": row.build_fingerprint,
            "embedding_model_fingerprint": row.embedding_model_fingerprint,
        }
        for row in release_off.indexes
    }
    canonical_zero = _main_state(0, adapter_on=False)
    fixture.release_mod.validate_release_bindings(
        release_off,
        view=fixture.view,
        main_state=canonical_zero,
        main_promotion_receipt_sha256=None,
        main_promotion_plan_sha256=None,
        semantic_snapshot=semantic_snapshot,
        index_snapshots=index_snapshots,
    )
    invalid_zero_states = {
        "switch": {**canonical_zero, "switches": {"memory_entry": False}},
        "runtime_profile": {
            **canonical_zero,
            "runtime_profile": "unproved-runtime-profile",
        },
        "history": {
            **canonical_zero,
            "active_promotions": [{"promotion_id": "unproved-history"}],
        },
        "artifact": {
            **canonical_zero,
            "code_artifacts": [
                {
                    "path": "unproved.py",
                    "sha256": h("unproved-code-artifact"),
                    "bytes": 1,
                    "guard_switch": "memory_entry",
                }
            ],
        },
    }
    invalid_zero_errors = {}
    for name, state in invalid_zero_states.items():
        exc = expect_error(
            fixture.release_mod.ReleaseContractError,
            lambda state=state: fixture.release_mod.validate_release_bindings(
                release_off,
                view=fixture.view,
                main_state=state,
                main_promotion_receipt_sha256=None,
                main_promotion_plan_sha256=None,
                semantic_snapshot=semantic_snapshot,
                index_snapshots=index_snapshots,
            ),
        )
        if "generation-zero MAIN state must equal the canonical default" not in str(
            exc
        ):
            raise AssertionError(f"generation-zero {name} drift was not diagnosed")
        invalid_zero_errors[name] = str(exc)
    original_off_main = stable_regular_bytes(fixture.off_release_main_path)
    original_off_main_mode = stat.S_IMODE(
        fixture.off_release_main_path.lstat().st_mode
    )
    sealed_zero_rejections = {}
    try:
        for name, state in invalid_zero_states.items():
            overwrite_probe_file(
                fixture.off_release_main_path, canonical_bytes(state)
            )
            os.chmod(
                fixture.off_release_main_path,
                original_off_main_mode,
                follow_symlinks=False,
            )
            rejected = _off_release_service_subprocess(fixture)
            rejected_ping = rejected.get("ping") or {}
            if (
                rejected_ping.get("ready") is not False
                or rejected_ping.get("release_error")
                not in {"ReleaseContractError", "ValueError", "RuntimeError"}
                or rejected.get("search") is not None
            ):
                raise AssertionError(
                    f"sealed bootstrap accepted generation-zero {name} drift"
                )
            sealed_zero_rejections[name] = rejected_ping["release_error"]
    finally:
        overwrite_probe_file(fixture.off_release_main_path, original_off_main)
        os.chmod(
            fixture.off_release_main_path,
            original_off_main_mode,
            follow_symlinks=False,
        )
    if (
        sha256_file(fixture.off_release_main_path) != release_off.main.state_sha256
        or stat.S_IMODE(fixture.off_release_main_path.lstat().st_mode)
        != original_off_main_mode
    ):
        raise AssertionError("SourceSet OFF MAIN fixture was not exactly restored")
    clean_off = _off_release_service_subprocess(fixture)
    clean_ping = clean_off.get("ping") or {}
    clean_search = clean_off.get("search") or {}
    clean_vector = clean_off.get("vector_runtime") or {}
    if (
        clean_ping.get("ready") is not True
        or clean_ping.get("release_mode") != "release"
        or clean_search.get("status") != 200
        or clean_vector.get("enabled") is not False
        or clean_vector.get("backend") != "file"
        or clean_vector.get("encoder") is not None
        or clean_off.get("retrieval_runtime") is not None
        or clean_off.get("network_calls")
    ):
        raise AssertionError("clean SourceSet OFF release did not serve vector-free retrieval")
    ambient_rejections = {}
    for key in ("EMBED_MODEL", "GENOS_EMBED_URL", "QDRANT_URL"):
        rejected = _off_release_service_subprocess(
            fixture, ambient_intent=(key, "unproved-runtime-intent")
        )
        rejected_ping = rejected.get("ping") or {}
        if (
            rejected_ping.get("ready") is not False
            or rejected_ping.get("release_error") != "RuntimeError"
            or rejected.get("search") is not None
        ):
            raise AssertionError(f"SourceSet OFF accepted ambient intent: {key}")
        ambient_rejections[key] = rejected_ping["release_error"]
    return {
        "baseline_sha256": sha256_bytes(expected_raw),
        "actual_sha256": sha256_bytes(actual_raw),
        "bytes": len(actual_raw),
        "adapter_enabled": False,
        "content_fields_present": False,
        "canonical_generation_zero": canonical_zero,
        "generation_zero_drift_errors": invalid_zero_errors,
        "sealed_generation_zero_rejections": sealed_zero_rejections,
        "off_release_id": release_off.release_id,
        "off_first_query_status": clean_search["status"],
        "off_vector_runtime": clean_vector,
        "ambient_vector_intent_rejections": ambient_rejections,
    }


def case_trusted_release_single_snapshot(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    pointer, release, binding = fixture.store.load_active_runtime()
    runtime_root = fixture.store.runtime_root(release.release_id)
    paths = binding.resolved_paths(runtime_root)
    artifacts = binding.resolved_artifacts(runtime_root)
    lock = fixture.catalog_mod.load_source_set_lock(
        artifacts["source_set.lock"],
        expected_artifact_sha256=release.source_set.lock_artifact_sha256,
    )
    materialized = fixture.catalog_mod.open_materialized_source_set(
        artifacts["source_set.materialization"], lock, trusted_root=runtime_root
    )
    rebuilt = fixture.snapshot_mod.create_content_snapshot(
        pointer=pointer,
        release=release,
        runtime_binding=binding,
        source_set_lock=lock,
        catalog_sha256=release.source_set.catalog_sha256,
        catalog_artifact_sha256=release.source_set.catalog_artifact_sha256,
        materialized=materialized,
        runtime_paths=paths,
        runtime_artifact_paths=artifacts,
    )
    if rebuilt != fixture.snapshot or rebuilt.compact_receipt() != fixture.snapshot.compact_receipt():
        raise AssertionError("trusted authorities did not resolve one snapshot")
    runtime_receipt = fixture.snapshot_mod.current_retrieval_runtime_receipt(
        required=True
    )
    if runtime_receipt != fixture.retrieval_runtime:
        raise AssertionError("trusted release did not resolve one retrieval runtime")
    compact_receipt = rebuilt.compact_receipt()
    if (
        compact_receipt.get("export_allowed")
        is not release.source_set.export_allowed
        or compact_receipt.get("main_promotion_plan_sha256")
        != release.main.promotion_plan_sha256
        or compact_receipt.get("main_promotion_receipt_sha256")
        != release.main.promotion_receipt_sha256
        or (runtime_receipt.get("llm") or {}).get("export_allowed")
        is not release.source_set.export_allowed
    ):
        raise AssertionError(
            "snapshot/runtime receipts did not preserve release export or MAIN proof"
        )
    semantic_snapshot = {
        "generation_id": release.semantics.generation_id,
        "authority_generation": release.semantics.authority_generation,
        "content_sha256": release.semantics.content_sha256,
        "source_set_sha256": release.semantics.source_set_sha256,
        "runtime_wired": True,
    }
    index_snapshots = {
        row.kind: {
            "artifact_id": row.artifact_id,
            "artifact_sha256": row.artifact_sha256,
            "source_set_sha256": row.source_set_sha256,
            "semantic_generation": row.semantic_generation,
            "build_fingerprint": row.build_fingerprint,
            "embedding_model_fingerprint": row.embedding_model_fingerprint,
        }
        for row in release.indexes
    }
    fixture.release_mod.validate_release_bindings(
        release,
        view=fixture.view,
        main_state=fixture.main_b,
        main_promotion_receipt_sha256=fixture.main_receipt_b_sha256,
        main_promotion_plan_sha256=fixture.main_plan_b_sha256,
        semantic_snapshot=semantic_snapshot,
        index_snapshots=index_snapshots,
    )
    return {
        "release_id": release.release_id,
        "release_generation": pointer.generation,
        "release_manifest_sha256": release.manifest_sha256,
        "runtime_binding_sha256": binding.binding_sha256,
        "content_snapshot_sha256": rebuilt.content_snapshot_sha256,
        "retrieval_runtime_sha256": runtime_receipt[
            "retrieval_runtime_sha256"
        ],
        "main_state_sha256": release.main.state_sha256,
        "main_promotion_plan_sha256": release.main.promotion_plan_sha256,
        "main_promotion_receipt_sha256": (
            release.main.promotion_receipt_sha256
        ),
        "main_transition_chain_sha256": (
            release.main.promotion_receipt_sha256
        ),
        "source_set_sha256": release.source_set.sha256,
        "export_allowed": compact_receipt["export_allowed"],
        "semantic_generation": release.semantics.generation_id,
        "index_kinds": sorted(index_snapshots),
    }


def case_external_internal_unified_view(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    packages = fixture.installed_catalog.resolve_lock(
        fixture.lock,
        expected_source_set_sha256=fixture.release_b.source_set.sha256,
        expected_lock_sha256=fixture.release_b.source_set.lock_sha256,
    )
    package_rows = {
        row.package_id: {
            "dataset_id": row.dataset_id,
            "version_id": row.version_id,
            "build_id": row.build_id,
            "source_origin": row.source_origin,
            "security_class": row.security_class,
            "export_allowed": row.export_allowed,
            "manifest_sha256": row.manifest_sha256,
        }
        for row in packages
    }
    expected = {
        "public-external": ("public_external", "public", True),
        "restricted-internal": ("restricted_internal", "restricted", False),
    }
    for package_id, values in expected.items():
        row = package_rows[package_id]
        if (row["source_origin"], row["security_class"], row["export_allowed"]) != values:
            raise AssertionError(f"package policy changed during composition: {package_id}")
    if fixture.view.export_allowed or fixture.lock.export_allowed:
        raise AssertionError("restricted union became exportable")
    if not fixture.lock.cross_dataset_relations:
        raise AssertionError("cross-dataset relation policy was not locked")
    if set(fixture.index.docs) != {"doc-public", "doc-internal"}:
        raise AssertionError("unified index did not expose both documents")
    artifacts = {
        row.document_id: row.receipt()
        for row in fixture.lock.artifacts
        if row.role == "structure"
    }
    if set(artifacts) != {"doc-public", "doc-internal"}:
        raise AssertionError("document provenance was not one-to-one")
    return {
        "source_set_id": fixture.view.source_set_id,
        "source_set_sha256": fixture.view.source_set_sha256,
        "export_allowed": fixture.view.export_allowed,
        "cross_dataset_relations": fixture.lock.cross_dataset_relations,
        "packages": package_rows,
        "document_artifacts": artifacts,
    }


def case_artifact_byte_tamper_rejected(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    path = fixture.external_structure_path
    original = stable_regular_bytes(path)
    original_mode = stat.S_IMODE(path.lstat().st_mode)
    try:
        path.chmod(original_mode | stat.S_IWUSR)
        path.write_bytes(original + b"\n")
        exc = expect_error(
            fixture.catalog_mod.DatasetContractError,
            lambda: fixture.installed_catalog.lookup(
                fixture.external.package_id, fixture.external.manifest_sha256
            ),
        )
    finally:
        path.write_bytes(original)
        path.chmod(original_mode)
    restored = fixture.installed_catalog.lookup(
        fixture.external.package_id, fixture.external.manifest_sha256
    )
    if restored.manifest_sha256 != fixture.external.manifest_sha256:
        raise AssertionError("package did not restore after isolated tamper probe")
    return {
        "boundary": "InstalledCatalog.lookup",
        "error": type(exc).__name__,
        "message": str(exc),
        "expected_artifact_sha256": next(
            row.sha256 for row in fixture.external.artifacts if row.role == "structure"
        ),
        "restored": True,
    }


def case_stale_authority_lock_rejected(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    stale_blob = dict(fixture.source_set_blob)
    stale_blob["generation_id"] = "combined-serving-generation-stale"
    stale_view = fixture.catalog_mod.compose_source_set(
        stale_blob, [fixture.external, fixture.internal]
    )
    stale_lock = stale_view.lock()
    if stale_lock.lock_sha256 == fixture.lock.lock_sha256:
        raise AssertionError("stale lock fixture did not change identity")
    exc = expect_error(
        fixture.catalog_mod.DatasetContractError,
        lambda: fixture.installed_catalog.resolve_lock(
            stale_lock,
            expected_source_set_sha256=fixture.release_b.source_set.sha256,
            expected_lock_sha256=fixture.release_b.source_set.lock_sha256,
        ),
    )
    return {
        "trusted_source_set_sha256": fixture.release_b.source_set.sha256,
        "trusted_lock_sha256": fixture.release_b.source_set.lock_sha256,
        "stale_source_set_sha256": stale_lock.source_set_sha256,
        "stale_lock_sha256": stale_lock.lock_sha256,
        "error": type(exc).__name__,
        "message": str(exc),
    }


def case_duplicate_document_id_rejected(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    root = fixture.root / "duplicate-packages"
    root.mkdir()
    payload_a = structure_payload(
        "duplicate-document",
        name="중복 A",
        title="중복 규정 A",
        surface="제1조",
        text="중복 A",
        kind="krx-rule",
        authority_generation="authority-fixture-v1",
    )
    payload_b = structure_payload(
        "duplicate-document",
        name="중복 B",
        title="중복 규정 B",
        surface="제2조",
        text="중복 B",
        kind="internal",
        authority_generation="authority-fixture-v1",
    )
    left, _ = write_dataset_package(
        fixture.catalog_mod,
        root,
        package_id="duplicate-left",
        dataset_id="duplicate-data",
        version_id="left-v1",
        restricted=False,
        artifacts=[
            {
                "logical_id": "documents/left",
                "role": "structure",
                "path": "left.json",
                "document_id": "duplicate-document",
                "payload": payload_a,
            }
        ],
    )
    right, _ = write_dataset_package(
        fixture.catalog_mod,
        root,
        package_id="duplicate-right",
        dataset_id="duplicate-data",
        version_id="right-v1",
        restricted=True,
        artifacts=[
            {
                "logical_id": "documents/right",
                "role": "structure",
                "path": "right.json",
                "document_id": "duplicate-document",
                "payload": payload_b,
            }
        ],
    )
    source_set = {
        "schema_version": "source-set-v1",
        "source_set_id": "duplicate-document-source",
        "generation_id": "duplicate-document-generation",
        "conflict_policy": "error",
        "cross_dataset_relations": False,
        "members": [
            {"package_id": left.package_id, "priority": 10},
            {"package_id": right.package_id, "priority": 20},
        ],
    }
    view = fixture.catalog_mod.compose_source_set(source_set, [left, right])
    lock = view.lock()
    exc = expect_error(
        fixture.catalog_mod.DatasetContractError,
        lambda: fixture.catalog_mod.materialize_source_set(
            view,
            fixture.root / "duplicate-materialized",
            lock=lock,
            trusted_root=fixture.root,
        ),
    )
    return {
        "claiming_packages": [left.package_id, right.package_id],
        "document_id": "duplicate-document",
        "error": type(exc).__name__,
        "message": str(exc),
    }


def case_unmapped_document_id_rejected(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    ghost = structure_payload(
        "doc-ghost",
        name="미매핑 규정",
        title="미매핑 조문",
        surface="제9조",
        text="미매핑 본문",
        kind="krx-rule",
        authority_generation="authority-fixture-v1",
    )
    exc_index = expect_error(
        fixture.snapshot_mod.ContentSnapshotError,
        lambda: fixture.index_mod.Index.from_docs(
            [("doc-ghost", ghost["meta"], ghost["result"])],
            document_provenance={},
            content_snapshot=fixture.snapshot,
        ),
    )
    exc_snapshot = expect_error(
        fixture.snapshot_mod.ContentSnapshotError,
        lambda: fixture.snapshot.provenance_for_document("doc-ghost"),
    )
    return {
        "document_id": "doc-ghost",
        "index_error": str(exc_index),
        "snapshot_error": str(exc_snapshot),
        "mapped_document_ids": list(fixture.snapshot.document_ids()),
    }


def case_index_content_fingerprint_bound(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    lexical = next(row for row in fixture.release_b.indexes if row.kind == "lexical")
    fixture.release_mod.validate_index_build_fingerprint(
        lexical,
        fixture.lexical_fingerprint,
        source_set=fixture.release_b.source_set,
        semantics=fixture.release_b.semantics,
    )
    expected = fixture.snapshot.content_fingerprint("lexical")
    if fixture.index.content_fingerprint != expected:
        raise AssertionError("loaded lexical index lacks snapshot content fingerprint")
    other = dataclasses.replace(
        fixture.snapshot,
        content_snapshot_sha256=h("other-release-snapshot"),
    )
    if other.content_fingerprint("lexical") == expected:
        raise AssertionError("release snapshot identity does not affect lexical fingerprint")
    inputs = dict(fixture.lexical_fingerprint.input_artifacts)
    structure_ids = {row.qualified_id for row in fixture.lock.artifacts}
    if not structure_ids.issubset(inputs):
        raise AssertionError("lexical build fingerprint omits SourceSet artifacts")
    return {
        "content_fingerprint": expected,
        "build_fingerprint": lexical.build_fingerprint,
        "release_manifest_sha256": fixture.snapshot.release_manifest_sha256,
        "source_set_sha256": fixture.snapshot.source_set_sha256,
        "semantic_generation": fixture.snapshot.semantic_generation,
        "input_artifact_ids": sorted(inputs),
    }


def case_vector_content_fingerprint_bound(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    vector_mod = importlib.import_module("lawrag.core.rag.vector")
    vector_binding = next(row for row in fixture.release_b.indexes if row.kind == "vector")
    runtime_model_fingerprint = vector_mod.runtime_embedding_model_fingerprint()
    if runtime_model_fingerprint != fixture.model_fingerprint:
        raise AssertionError("query encoder runtime fingerprint is not release-bound")
    fixture.release_mod.validate_index_build_fingerprint(
        vector_binding,
        fixture.vector_fingerprint,
        source_set=fixture.release_b.source_set,
        semantics=fixture.release_b.semantics,
        runtime_model_fingerprint=fixture.model_fingerprint,
    )
    release_vector_dir = Path(fixture.runtime_artifacts_b["index.vector"])
    bound_identity = vector_mod.load_vector_identity(
        release_vector_dir,
        snapshot=fixture.snapshot,
        model_fingerprint=fixture.model_fingerprint,
    )
    if release_vector_dir.resolve() != Path(
        fixture.runtime_paths_b["RAG_VECTOR_STORE"]
    ).resolve():
        raise AssertionError("runtime vector path is not the release-proved artifact")
    canonical_index = vector_mod.current(content_snapshot=fixture.snapshot)
    if canonical_index is None:
        raise AssertionError("release-proved vector matrix was not loadable")
    numpy_mod = importlib.import_module("numpy")
    query_vector = numpy_mod.asarray(
        [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        dtype=numpy_mod.float32,
    )
    canonical_hits = canonical_index.search(query_vector, topk=1, minimum=0.0)
    if canonical_hits != [("doc-public", 1, 1.0)]:
        raise AssertionError("deterministic local vector matrix changed")
    qdrant_mod = importlib.import_module("lawrag.core.rag.qdrant_store")
    embedding_mod = importlib.import_module("lawrag.core.embedding")
    qdrant_config = qdrant_mod.load_bound_config(fixture.snapshot)
    if (
        qdrant_config is None
        or qdrant_config.get("config_sha256")
        != fixture.qdrant_config_sha256
        or qdrant_config.get("trust_zone") != "internal"
    ):
        raise AssertionError("release did not bind the restricted Qdrant service")
    runtime_services = importlib.import_module("lawrag.platform.runtime_services")
    acl_receipt = fixture.store.load_active_validation_receipt(kind="acl")
    qdrant_acl = runtime_services.qdrant_acl_projection(qdrant_config)
    runtime_services.require_acl_projection(
        acl_receipt,
        service_name="qdrant",
        expected=qdrant_acl,
    )
    qdrant_identity = qdrant_mod._snapshot_identity(
        fixture.snapshot,
        vector_identity_sha256=bound_identity["identity_sha256"],
        qdrant_config_sha256=fixture.qdrant_config_sha256,
    )
    real_session = qdrant_mod._session()
    try:
        if (
            real_session.trust_env is not False
            or "api-key" in real_session.headers
        ):
            raise AssertionError(
                "in-process Qdrant session inherited ambient transport credentials"
            )
    finally:
        real_session.close()

    class FakeResponse:
        def __init__(self, payload: Mapping[str, Any]) -> None:
            self.status_code = 200
            self._payload = dict(payload)

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return json.loads(canonical_bytes(self._payload).decode("utf-8"))

    class FakeQdrantSession:
        def __init__(
            self,
            *,
            identity: Mapping[str, Any],
            row_identity: Mapping[str, Any] | None = None,
            score: float = 1.0,
        ) -> None:
            self.identity = dict(identity)
            self.row_identity = dict(row_identity or qdrant_identity)
            self.score = score
            self.calls: list[dict[str, Any]] = []

        def get(
            self,
            url: str,
            *,
            timeout: float,
            allow_redirects: bool,
        ) -> FakeResponse:
            if allow_redirects is not False or timeout != 5.0 or url != (
                f"{fixture.qdrant_url}/collections/"
                f"{fixture.qdrant_collection}/points/"
                f"{qdrant_mod._IDENTITY_POINT_ID}"
            ):
                raise AssertionError(
                    "Qdrant identity probe escaped its fixed transport contract"
                )
            self.calls.append(
                {
                    "method": "GET",
                    "url": url,
                    "timeout": timeout,
                    "allow_redirects": allow_redirects,
                }
            )
            return FakeResponse(
                {
                    "result": {
                        "payload": {"record_kind": "identity", **self.identity}
                    }
                }
            )

        def post(
            self,
            url: str,
            *,
            json: Mapping[str, Any],
            timeout: tuple[int, float],
            allow_redirects: bool,
        ) -> FakeResponse:
            if allow_redirects is not False or timeout != (5, 30.0) or url != (
                f"{fixture.qdrant_url}/collections/"
                f"{fixture.qdrant_collection}/points/search"
            ):
                raise AssertionError(
                    "Qdrant query escaped its fixed transport contract"
                )
            self.calls.append(
                {
                    "method": "POST",
                    "url": url,
                    "timeout": list(timeout),
                    "allow_redirects": allow_redirects,
                    "body_sha256": canonical_sha256(json),
                }
            )
            return FakeResponse(
                {
                    "result": [
                        {
                            "score": self.score,
                            "payload": {
                                "record_kind": "section",
                                **self.row_identity,
                                "doc_id": "doc-public",
                                "node": 1,
                            },
                        }
                    ]
                }
            )

    original_backend = os.environ.get("RAG_VECTOR_BACKEND")
    original_available = embedding_mod.available
    original_query_vector = vector_mod._query_vector
    original_qdrant_session = qdrant_mod._session
    try:
        os.environ["RAG_VECTOR_BACKEND"] = "qdrant"
        embedding_mod.available = lambda: True
        vector_mod._query_vector = lambda _query: query_vector
        exact_session = FakeQdrantSession(identity=qdrant_identity)
        qdrant_mod._session = lambda: exact_session
        qdrant_verified = vector_mod.search(
            "deterministic qdrant verification", topk=1, minimum=0.0
        )
        if qdrant_verified != canonical_hits:
            raise AssertionError("Qdrant verification replaced canonical results")
        stale_identity = dict(qdrant_identity)
        stale_identity["source_set_sha256"] = h("stale-qdrant-source-set")
        qdrant_mod._session = lambda: FakeQdrantSession(
            identity=stale_identity
        )
        qdrant_identity_mismatch = expect_error(
            fixture.snapshot_mod.ContentSnapshotError,
            lambda: qdrant_mod.search(
                query_vector,
                topk=1,
                minimum=0.0,
                content_snapshot=fixture.snapshot,
            ),
        )
        qdrant_mod._session = lambda: FakeQdrantSession(
            identity=qdrant_identity,
            row_identity=stale_identity,
        )
        qdrant_row_mismatch = expect_error(
            fixture.snapshot_mod.ContentSnapshotError,
            lambda: qdrant_mod.search(
                query_vector,
                topk=1,
                minimum=0.0,
                content_snapshot=fixture.snapshot,
            ),
        )
        qdrant_mod._session = lambda: FakeQdrantSession(
            identity=qdrant_identity,
            score=0.5,
        )
        qdrant_mismatch = expect_error(
            fixture.snapshot_mod.ContentSnapshotError,
            lambda: vector_mod.search(
                "deterministic qdrant mismatch", topk=1, minimum=0.0
            ),
        )
    finally:
        if original_backend is None:
            os.environ.pop("RAG_VECTOR_BACKEND", None)
        else:
            os.environ["RAG_VECTOR_BACKEND"] = original_backend
        embedding_mod.available = original_available
        vector_mod._query_vector = original_query_vector
        qdrant_mod._session = original_qdrant_session
    vector_dir = fixture.root / "vector-identity"
    vector_dir.mkdir()
    write_regular(vector_dir / "meta.jsonl", b'{"doc_id":"doc-public","node":1}\n')
    write_regular(vector_dir / "vectors.npz", b"fixture-npz-bytes\n")
    identity = vector_mod.build_vector_identity(
        snapshot=fixture.snapshot,
        vector_dir=vector_dir,
        row_count=1,
        model_fingerprint=fixture.model_fingerprint,
    )
    write_regular(vector_dir / "identity.json", canonical_bytes(identity))
    loaded = vector_mod.load_vector_identity(
        vector_dir,
        snapshot=fixture.snapshot,
        model_fingerprint=fixture.model_fingerprint,
    )
    failures = {}
    variants = {
        "source_set": dataclasses.replace(
            fixture.snapshot,
            source_set_sha256=h("stale-source-set"),
            content_snapshot_sha256=h("stale-source-snapshot"),
        ),
        "semantic": dataclasses.replace(
            fixture.snapshot,
            semantic_generation="semantic-stale-v1",
            content_snapshot_sha256=h("stale-semantic-snapshot"),
        ),
        "index": dataclasses.replace(
            fixture.snapshot,
            indexes=tuple(
                dataclasses.replace(row, build_fingerprint=h("stale-vector-build"))
                if row.kind == "vector"
                else row
                for row in fixture.snapshot.indexes
            ),
            content_snapshot_sha256=h("stale-index-snapshot"),
        ),
    }
    for name, snapshot in variants.items():
        exc = expect_error(
            fixture.snapshot_mod.ContentSnapshotError,
            lambda snapshot=snapshot: vector_mod.load_vector_identity(
                vector_dir,
                snapshot=snapshot,
                model_fingerprint=fixture.model_fingerprint,
            ),
        )
        failures[name] = str(exc)
    wrong_model = h("wrong-model")
    exc = expect_error(
        fixture.snapshot_mod.ContentSnapshotError,
        lambda: vector_mod.load_vector_identity(
            vector_dir,
            snapshot=fixture.snapshot,
            model_fingerprint=wrong_model,
        ),
    )
    failures["model"] = str(exc)
    return {
        "bound_identity_sha256": bound_identity["identity_sha256"],
        "identity_sha256": loaded["identity_sha256"],
        "vector_content_fingerprint": fixture.snapshot.content_fingerprint("vector"),
        "build_fingerprint": vector_binding.build_fingerprint,
        "model_fingerprint": fixture.model_fingerprint,
        "runtime_model_fingerprint": runtime_model_fingerprint,
        "qdrant_config_sha256": fixture.qdrant_config_sha256,
        "qdrant_trust_zone": qdrant_config["trust_zone"],
        "qdrant_acl_projection": qdrant_acl,
        "qdrant_verified_against_local_matrix": qdrant_verified,
        "qdrant_http_contract": exact_session.calls,
        "qdrant_requests_trust_env": False,
        "qdrant_ambient_api_key": False,
        "qdrant_identity_mismatch_error": str(qdrant_identity_mismatch),
        "qdrant_row_mismatch_error": str(qdrant_row_mismatch),
        "qdrant_mismatch_error": str(qdrant_mismatch),
        "rejections": failures,
    }


def case_scoped_index_provenance_preserved(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    scoped = fixture.index.scoped({"doc-public"}, "public-only")
    if scoped.content_snapshot is not fixture.index.content_snapshot:
        raise AssertionError("scoped index replaced the immutable snapshot")
    if (
        scoped.content_snapshot_sha256 != fixture.index.content_snapshot_sha256
        or scoped.content_fingerprint != fixture.index.content_fingerprint
    ):
        raise AssertionError("scoped index lost content identity")
    for document_id in fixture.index.docs:
        if scoped.docs[document_id].content_provenance != fixture.index.docs[document_id].content_provenance:
            raise AssertionError(f"scoped document provenance changed: {document_id}")
    visible = [row for row in scoped.entries if row.doc_id]
    if not visible or any(row.doc_id != "doc-public" or row.content_provenance is None for row in visible):
        raise AssertionError("scoped entry provenance is incomplete")
    return {
        "scope": sorted(scoped.scope),
        "content_snapshot_sha256": scoped.content_snapshot_sha256,
        "content_fingerprint": scoped.content_fingerprint,
        "document_provenance": {
            key: value.content_provenance.receipt()
            for key, value in scoped.docs.items()
        },
    }


def _public_hit_and_section(fixture: Fixture):
    result = fixture.search_mod.search(fixture.index, "외부 의무")
    hit = next(row for row in result.hits if row.doc_id == "doc-public")
    sections = fixture.answer_mod.assemble(fixture.index, result)
    section = next(row for row in sections if row.doc_id == "doc-public")
    return result, hit, section


def case_hit_section_citation_provenance(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    result, hit, section = _public_hit_and_section(fixture)
    rag_router = importlib.import_module("lawrag.api.routers.rag")
    hit_row = rag_router._hit_row(hit)
    context_row = rag_router._ctx_row(fixture.index, section)
    citation = section.cite()
    expected = fixture.snapshot.provenance_for_document("doc-public").receipt()
    observed = [
        hit.content_provenance.receipt(),
        section.content_provenance.receipt(),
        hit_row["content_provenance"],
        context_row["content_provenance"],
        citation["content_provenance"],
    ]
    if any(row != expected for row in observed):
        raise AssertionError("hit/section/citation provenance diverged")
    if result.content_snapshot is not fixture.snapshot:
        raise AssertionError("search result lost request-wide content snapshot")
    artifact_required = {
        "qualified_id",
        "package_id",
        "dataset_id",
        "version_id",
        "build_id",
        "manifest_sha256",
        "logical_id",
        "role",
        "artifact_sha256",
        "document_id",
    }
    snapshot_receipt = result.content_snapshot.compact_receipt()
    snapshot_required = {
        "release_id",
        "release_manifest_sha256",
        "source_set_id",
        "source_set_generation",
        "source_set_sha256",
        "semantic_generation",
        "authority_generation",
        "content_snapshot_sha256",
    }
    if not artifact_required.issubset(expected):
        raise AssertionError("artifact receipt lacks required coordinates")
    if not snapshot_required.issubset(snapshot_receipt):
        raise AssertionError("request snapshot lacks release/SourceSet coordinates")
    return {
        "content_snapshot": snapshot_receipt,
        "content_provenance": expected,
        "hit_projection_sha256": canonical_sha256(hit_row),
        "context_projection_sha256": canonical_sha256(context_row),
        "citation_sha256": canonical_sha256(citation),
    }


def case_relation_evidence_provenance(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    relations = importlib.import_module("lawrag.core.rag.relations")
    evidence_mod = importlib.import_module("lawrag.core.rag.legal_evidence")
    coordinates = importlib.import_module("lawrag.core.rag.legal_coordinates")
    presenter = importlib.import_module("lawrag.api.legalclosure_presenter")
    bundle = relations.build(
        fixture.index,
        include_requirements=True,
        use_cache=False,
    )
    relation = next(
        row
        for row in bundle.sections
        if row.kind == "DELEGATES_TO"
        and row.src_doc == "doc-public"
        and row.dst_doc == "doc-internal"
    )
    if relation.props.get("provenance") != ["law.go.kr:lsDelegated"]:
        raise AssertionError("relation did not use release-bound delegation authority")
    endpoint_provenance = relation.props.get("content_provenance")
    if not isinstance(relation.props.get("provenance"), list):
        raise AssertionError("relation-discovery provenance changed shape")
    if not isinstance(endpoint_provenance, Mapping) or set(endpoint_provenance) != {"source", "target"}:
        raise AssertionError("relation endpoint provenance is incomplete")
    expected_endpoints = {
        "source": fixture.snapshot.provenance_for_document("doc-public").receipt(),
        "target": fixture.snapshot.provenance_for_document("doc-internal").receipt(),
    }
    if endpoint_provenance != expected_endpoints:
        raise AssertionError("relation endpoint provenance targets are wrong")
    branch = coordinates.article_branch(
        fixture.index,
        "doc-public",
        1,
        ("외부", "의무"),
        origin="run013",
        reason="fixture",
    )
    if branch is None:
        raise AssertionError("could not construct legal evidence branch")
    annotations = evidence_mod.annotate(fixture.index, "외부 의무 조건", [branch])
    expected = expected_endpoints["source"]
    if annotations["rows"][0].get("content_provenance") != expected:
        raise AssertionError("legal evidence lost artifact provenance")
    public = presenter.public_meta(
        {
            "strategy": "fixture",
            "cap": 1,
            "legal_annotations": annotations,
            "content_snapshot": fixture.snapshot.compact_receipt(),
        }
    )
    preserved = public["legal_annotations"].get("content_provenance")
    if not preserved or preserved[0]["content_provenance"] != expected:
        raise AssertionError("presenter lost legal evidence provenance")
    return {
        "relation_kind": relation.kind,
        "discovery_provenance": relation.props["provenance"],
        "content_provenance": endpoint_provenance,
        "requirement_count": len(bundle.requirements),
        "evidence_content_snapshot": annotations["content_snapshot"],
        "presenter_sha256": canonical_sha256(public),
    }


def case_trace_and_tuple_provenance(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    trace_mod = importlib.import_module("lawrag.core.rag.search_trace")
    reach_mod = importlib.import_module("lawrag.core.rag.article_reachability")
    tuples_mod = importlib.import_module("lawrag.core.rag.tuples")
    presenter = importlib.import_module("lawrag.api.legalclosure_presenter")
    rag_router = importlib.import_module("lawrag.api.routers.rag")
    _result, _hit, section = _public_hit_and_section(fixture)
    trace = trace_mod.SearchTrace(
        "외부 의무",
        corpus_fingerprint=fixture.index.content_fingerprint,
        trace_id="run013-trace",
        content_snapshot=fixture.snapshot,
    )
    trace.observe_coordinate(("doc-public", 1), origin="exact", observation_depth=0)
    trace.observe_coordinate(("doc-internal", 1), origin="relation", observation_depth=1)
    trace.record_edge(
        ("doc-public", 1),
        ("doc-internal", 1),
        relation="DELEGATES_TO",
        direction="forward",
        provenance="source_text:reference",
    )
    trace.mark_selected([("doc-public", 1)], stage="present", reason="fixture")
    summary = trace.summary()
    reach = reach_mod.ArticleReachabilityTrace(
        fixture.index,
        "run013-trace-case",
        arm_id="content-snapshot",
        content_snapshot=fixture.snapshot,
    )
    reach.stage("source", "source", [("doc-public", 1)])
    reach.event(
        "A_EXACT",
        "retrieve",
        "selected",
        "selected",
        raw_coordinate=("doc-public", 1),
        article_coordinate=("doc-public", 1),
        source_coordinate=("doc-public", 1),
    )
    reach.stage(
        "present",
        "present",
        [("doc-public", 1)],
        parent_stage_ids=("source",),
    )
    capture = reach.capture()
    reach_mod.validate_capture(capture)
    context_row = rag_router._ctx_row(fixture.index, section)
    public = presenter.public_meta(
        {
            "strategy": "fixture",
            "cap": 1,
            "legal_annotations": {
                "rows": [
                    {
                        "doc_id": "doc-public",
                        "node": 1,
                        "content_provenance": context_row["content_provenance"],
                    }
                ]
            },
            "content_snapshot": fixture.snapshot.compact_receipt(),
        }
    )
    out = {
        "question": "외부 의무",
        "mode": "정확",
        "ladder": [],
        "filter": None,
        "answerable": True,
        "answer": "결정론적 fixture",
        "context": [context_row],
        "cited": [1],
        "refs": [
            {
                **section.cite(),
                "kind": section.kind,
                "matched": section.matched,
            }
        ],
        "content_snapshot": fixture.snapshot.compact_receipt(),
        "retrieval_runtime": fixture.retrieval_runtime,
    }
    if fixture.retrieval_runtime is None:
        raise AssertionError("fixture retrieval runtime is not bound")
    attached = rag_router._attach_content_snapshot(
        {"probe": "run013"}, fixture.index
    )
    if (
        attached.get("content_snapshot")
        != fixture.snapshot.compact_receipt()
        or attached.get("retrieval_runtime") != fixture.retrieval_runtime
    ):
        raise AssertionError("API projection lost its retrieval runtime receipt")
    ask_events: list[dict[str, Any]] = []
    original_rag_event = rag_router.logbook.rag_event
    rag_router.logbook.rag_event = lambda kind, **payload: ask_events.append(
        {"kind": kind, **payload}
    )
    try:
        rag_router._ask_event(out, 7)
    finally:
        rag_router.logbook.rag_event = original_rag_event
    if (
        len(ask_events) != 1
        or ask_events[0].get("content_snapshot")
        != fixture.snapshot.compact_receipt()
        or ask_events[0].get("retrieval_runtime") != fixture.retrieval_runtime
    ):
        raise AssertionError("ask event lost content or retrieval runtime identity")
    original_now = tuples_mod._now
    tuples_mod._now = lambda: NOW
    try:
        qid = tuples_mod.log_ask(out)
        feedback = tuples_mod.log_feedback(
            qid,
            "정답",
            expected={
                "doc_id": "doc-public",
                "node": 1,
                "content_provenance": context_row["content_provenance"],
            },
            note="run013 deterministic receipt probe",
        )
        stored = tuples_mod.find(qid)
    finally:
        tuples_mod._now = original_now
    tuple_dir_mode = stat.S_IMODE(tuples_mod.tuples_dir().lstat().st_mode)
    tuple_ledger = tuples_mod._month_file(NOW)
    tuple_ledger_mode = stat.S_IMODE(tuple_ledger.lstat().st_mode)
    if tuple_dir_mode != 0o700 or tuple_ledger_mode != 0o600:
        raise AssertionError("sealed tuple directory or ledger mode is unsafe")
    sentinel = fixture.root / "tuple-symlink-sentinel.jsonl"
    sentinel_raw = b"sealed feedback symlink sentinel\n"
    write_regular(sentinel, sentinel_raw, mode=0o600)
    tuple_symlink = tuples_mod.tuples_dir() / "209901.jsonl"
    tuple_symlink.symlink_to(sentinel)
    try:
        try:
            tuples_mod._append(
                {
                    "kind": "security-probe",
                    "qid": "symlink-rejected",
                    "ts": "2099-01-01T00:00:00Z",
                }
            )
        except (OSError, fixture.snapshot_mod.ContentSnapshotError) as exc:
            symlink_error = exc
        else:
            raise AssertionError("sealed tuple append followed a symlink")
    finally:
        tuple_symlink.unlink(missing_ok=True)
    if stable_regular_bytes(sentinel) != sentinel_raw:
        raise AssertionError("sealed tuple symlink probe modified its target")
    expected_snapshot = fixture.snapshot.compact_receipt()
    expected_public = fixture.snapshot.provenance_for_document("doc-public").receipt()
    expected_internal = fixture.snapshot.provenance_for_document("doc-internal").receipt()
    if stored is None or stored.get("content_snapshot") != expected_snapshot:
        raise AssertionError("durable ask tuple lost content snapshot")
    if (
        stored.get("retrieval_runtime") != fixture.retrieval_runtime
        or feedback.get("retrieval_runtime") != fixture.retrieval_runtime
    ):
        raise AssertionError("durable ask/feedback tuple lost retrieval runtime")
    if stored["refs"][0].get("content_provenance") != context_row["content_provenance"]:
        raise AssertionError("durable ask tuple lost citation provenance")
    if summary.get("content_snapshot") != expected_snapshot:
        raise AssertionError("search trace lost content snapshot")
    if capture.get("content_snapshot") != expected_snapshot:
        raise AssertionError("reachability trace lost content snapshot")
    if summary.get("content_provenance") != {
        "doc-internal": expected_internal,
        "doc-public": expected_public,
    }:
        raise AssertionError("search trace lost endpoint artifact provenance")
    if capture.get("content_provenance") != {"doc-public": expected_public}:
        raise AssertionError("reachability trace lost artifact provenance")
    if (
        public.get("content_snapshot") != expected_snapshot
        or public["legal_annotations"]["content_provenance"][0][
            "content_provenance"
        ]
        != expected_public
    ):
        raise AssertionError("runtime presentation metadata lost content identity")
    return {
        "search_trace_sha256": canonical_sha256(summary),
        "reachability_capture_sha256": capture["capture_sha256"],
        "tuple_record_sha256": canonical_sha256(
            {key: value for key, value in stored.items() if key not in {"qid", "ts"}}
        ),
        "api_context_sha256": canonical_sha256(context_row),
        "api_projection_sha256": canonical_sha256(attached),
        "ask_event_sha256": canonical_sha256(ask_events[0]),
        "presenter_sha256": canonical_sha256(public),
        "content_snapshot_sha256": expected_snapshot["content_snapshot_sha256"],
        "retrieval_runtime_sha256": fixture.retrieval_runtime[
            "retrieval_runtime_sha256"
        ],
        "tuple_symlink_error": type(symlink_error).__name__,
        "tuple_symlink_target_unchanged": True,
        "tuple_directory_mode": f"{tuple_dir_mode:04o}",
        "tuple_ledger_mode": f"{tuple_ledger_mode:04o}",
        "content_provenance": context_row["content_provenance"],
    }


def case_feedback_shortcut_generation_lock(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    tuples_mod = importlib.import_module("lawrag.core.rag.tuples")
    promote_mod = importlib.import_module("lawrag.core.rag.promote")
    question = "외부 의무"
    snapshot_receipt = fixture.snapshot.compact_receipt()
    artifact_receipt = fixture.snapshot.provenance_for_document(
        "doc-public"
    ).receipt()
    coordinate = {
        "doc_id": "doc-public",
        "node": 1,
        "via": "run-013-reviewed-feedback",
        "content_snapshot": snapshot_receipt,
        "content_provenance": artifact_receipt,
    }
    candidate_path = fixture.reviewed_shortcut_path
    if tuples_mod.candidates_path() != candidate_path:
        raise AssertionError("promote consumer is not reading the pinned reviewed store")
    pinned_before = stable_regular_bytes(candidate_path)
    pinned_identity_before = _stat_identity(candidate_path.lstat())
    if sha256_bytes(pinned_before) != fixture.reviewed_shortcut_sha256:
        raise AssertionError("reviewed shortcut deployment hash changed")
    active_rows = promote_mod.active()
    if len(active_rows) != 1:
        raise AssertionError("current snapshot did not expose one active candidate")
    active_row = active_rows[0]
    if (
        active_row.get("content_snapshot") != snapshot_receipt
        or active_row.get("content_provenance") != artifact_receipt
    ):
        raise AssertionError("active feedback row lost its snapshot receipts")
    expected_hit = {
        "doc_id": "doc-public",
        "node": 1,
        "via": "질문 기억",
        "why": "같은 질문 (승인 연결)",
        "score": 1.0,
    }
    exact_hits = promote_mod.direct_hits(question, cap=1, index=fixture.index)
    if exact_hits != [expected_hit]:
        raise AssertionError("current generation did not use the approved direct hit")

    def clone(value: object) -> Any:
        return json.loads(canonical_bytes(value).decode("utf-8"))

    def stale_observation(
        name: str,
        mutate: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        stale_row = clone(active_row)
        mutate(stale_row)
        stale_path = candidate_path.with_name(f"stale-{name}.json")
        write_regular(
            stale_path,
            canonical_bytes({"candidates": [stale_row]}),
            mode=0o400,
        )
        stale_sha256 = sha256_file(stale_path)
        original_store = os.environ["RAG_QUERY_SHORTCUT_STORE"]
        original_deployment_store = os.environ["LAWRAG_QUERY_SHORTCUT_STORE"]
        original_deployment_sha256 = os.environ[
            "LAWRAG_QUERY_SHORTCUT_STORE_SHA256"
        ]
        os.environ["RAG_QUERY_SHORTCUT_STORE"] = str(stale_path)
        os.environ["LAWRAG_QUERY_SHORTCUT_STORE"] = str(stale_path)
        os.environ["LAWRAG_QUERY_SHORTCUT_STORE_SHA256"] = stale_sha256
        promote_mod._qvec_cache.clear()
        try:
            shortcut_hits = promote_mod.direct_hits(
                question, cap=1, index=fixture.index
            )
            if shortcut_hits:
                raise AssertionError(f"stale {name} feedback row was reused")
            fallback = fixture.search_mod.search(fixture.index, question)
            if not fallback.hits:
                raise AssertionError(
                    f"normal retrieval did not continue after stale {name} row"
                )
        finally:
            os.environ["RAG_QUERY_SHORTCUT_STORE"] = original_store
            os.environ["LAWRAG_QUERY_SHORTCUT_STORE"] = (
                original_deployment_store
            )
            os.environ["LAWRAG_QUERY_SHORTCUT_STORE_SHA256"] = (
                original_deployment_sha256
            )
            promote_mod._qvec_cache.clear()
        return {
            "store_sha256": stale_sha256,
            "direct_hit_count": len(shortcut_hits),
            "fallback_mode": fallback.mode,
            "fallback_hit_count": len(fallback.hits),
        }

    def stale_release(row: dict[str, Any]) -> None:
        row["content_snapshot"]["release_manifest_sha256"] = h(
            "stale-release-manifest"
        )

    def stale_source_set(row: dict[str, Any]) -> None:
        row["content_snapshot"]["source_set_sha256"] = h("stale-source-set")

    def stale_semantic(row: dict[str, Any]) -> None:
        row["content_snapshot"]["semantic_generation"] = "semantic-stale-v1"

    def stale_index(row: dict[str, Any]) -> None:
        # Index bindings are transitively committed by this snapshot digest.
        row["content_snapshot"]["content_snapshot_sha256"] = h(
            "stale-index-bound-content-snapshot"
        )

    def stale_artifact(row: dict[str, Any]) -> None:
        row["content_provenance"]["artifact_sha256"] = h(
            "stale-structure-artifact"
        )

    def stale_deployment_store(row: dict[str, Any]) -> None:
        # Receipts intentionally remain current.  Only the deployment bytes
        # change, so the process-pinned retrieval-runtime SHA must reject it.
        row["via"] = "unreviewed replacement with current content receipts"

    stale_results = {
        "release": stale_observation("release", stale_release),
        "source_set": stale_observation("source-set", stale_source_set),
        "semantic": stale_observation("semantic", stale_semantic),
        "index": stale_observation("index", stale_index),
        "artifact": stale_observation("artifact-provenance", stale_artifact),
        "retrieval_runtime_store": stale_observation(
            "retrieval-runtime-store", stale_deployment_store
        ),
    }

    original_now = tuples_mod._now
    tuples_mod._now = lambda: NOW
    try:
        observed = tuples_mod.record_candidates(question, [coordinate], cap=1)
        approval_error = expect_error(
            PermissionError,
            lambda: promote_mod.approve(
                fixture.index_mod.norm(question),
                "doc-public",
                1,
                note="forbidden query-time approval",
            ),
        )
        barrier = threading.Barrier(3)
        result_lock = threading.Lock()
        concurrent_results: list[int] = []
        concurrent_errors: list[str] = []

        def record_concurrently() -> None:
            barrier.wait()
            try:
                value = tuples_mod.record_candidates(
                    question, [coordinate], cap=1
                )
            except BaseException as exc:
                with result_lock:
                    concurrent_errors.append(
                        f"{type(exc).__name__}: {exc}"
                    )
            else:
                with result_lock:
                    concurrent_results.append(value)

        workers = [
            threading.Thread(target=record_concurrently)
            for _ in range(2)
        ]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(timeout=10)
        if any(worker.is_alive() for worker in workers):
            raise AssertionError("candidate update lock did not make progress")
        if concurrent_errors or sorted(concurrent_results) != [0, 0]:
            raise AssertionError(
                "concurrent candidate updates failed: "
                + repr(
                    {
                        "results": concurrent_results,
                        "errors": concurrent_errors,
                    }
                )
            )
    finally:
        tuples_mod._now = original_now
    observation_path = tuples_mod.candidate_observations_path()
    if observed != 1 or observation_path == candidate_path:
        raise AssertionError("query-time candidate did not enter the external ledger")
    observation_blob = json.loads(stable_regular_bytes(observation_path))
    observation_rows = observation_blob.get("candidates", [])
    candidate_mode = stat.S_IMODE(observation_path.lstat().st_mode)
    candidate_lock = fixture.feedback_root / ".candidates.lock"
    candidate_lock_mode = stat.S_IMODE(candidate_lock.lstat().st_mode)
    leftover_temporaries = sorted(
        path.name
        for path in fixture.feedback_root.glob(".candidates.json.*.tmp")
    )
    if (
        len(observation_rows) != 1
        or observation_rows[0].get("status") != "잠정"
        or observation_rows[0].get("count") != 3
        or observation_rows[0].get("content_snapshot") != snapshot_receipt
        or observation_rows[0].get("content_provenance") != artifact_receipt
        or observation_rows[0].get("observed_retrieval_runtime")
        != fixture.retrieval_runtime
        or candidate_mode != 0o600
        or candidate_lock_mode != 0o600
        or leftover_temporaries
    ):
        raise AssertionError("external feedback observation lost its generation lock")
    pinned_after = stable_regular_bytes(candidate_path)
    pinned_identity_after = _stat_identity(candidate_path.lstat())
    runtime_after = fixture.snapshot_mod.current_retrieval_runtime_receipt(
        required=True
    )
    if (
        pinned_after != pinned_before
        or pinned_identity_after != pinned_identity_before
        or sha256_bytes(pinned_after) != fixture.reviewed_shortcut_sha256
        or runtime_after != fixture.retrieval_runtime
    ):
        raise AssertionError(
            "query-time observation mutated the reviewed store/runtime receipt"
        )
    restored_hits = promote_mod.direct_hits(question, cap=1, index=fixture.index)
    if restored_hits != [expected_hit]:
        raise AssertionError("exact direct hit did not recover with current receipts")
    return {
        "consumer": "lawrag.core.rag.promote.direct_hits",
        "reviewed_store_sha256": fixture.reviewed_shortcut_sha256,
        "reviewed_store_mode": f"{stat.S_IMODE(candidate_path.lstat().st_mode):04o}",
        "content_snapshot": snapshot_receipt,
        "content_provenance": artifact_receipt,
        "selected_landing": exact_hits[0],
        "stale_results": stale_results,
        "query_observation_count": len(observation_rows),
        "query_observation_landing_count": observation_rows[0]["count"],
        "concurrent_candidate_updates": sorted(concurrent_results),
        "candidate_file_mode": f"{candidate_mode:04o}",
        "candidate_lock_mode": f"{candidate_lock_mode:04o}",
        "leftover_atomic_temporaries": leftover_temporaries,
        "query_observation_sha256": sha256_file(observation_path),
        "observed_retrieval_runtime_sha256": fixture.retrieval_runtime[
            "retrieval_runtime_sha256"
        ],
        "query_time_approval_error": str(approval_error),
        "reviewed_store_unchanged": True,
        "restored": restored_hits == exact_hits,
    }


def _sealed_service_subprocess(fixture: Fixture) -> Mapping[str, Any]:
    """Boot the frozen service as the first product import in an isolated child."""

    child = r'''
import asyncio
import json
import os
from pathlib import Path
import site
import socket
import sys
import sysconfig

revision_root = Path(sys.argv[1]).resolve()
repository_root = Path(sys.argv[2]).resolve()
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
safe_paths = []
for raw in sys.path:
    if not raw:
        continue
    path = Path(raw).resolve()
    try:
        path.relative_to(repository_root)
    except ValueError:
        safe_paths.append(raw)
        continue
    if any(
        path == dependency_root or dependency_root in path.parents
        for dependency_root in dependency_roots
    ):
        safe_paths.append(raw)
sys.path[:] = [str(revision_root), *safe_paths]
sys.dont_write_bytecode = True

network_calls = []
original_connect = socket.socket.connect
def forbid_connect(_socket, address):
    network_calls.append(repr(address))
    raise AssertionError("network access is forbidden in run-013")
socket.socket.connect = forbid_connect

import service

from lawrag.core import llm as llm_mod
llm_calls = []
original_structured = llm_mod.LLM.structured
def forbid_llm(_self, *args, **kwargs):
    llm_calls.append(str(args[0] if args else kwargs.get("kind") or "unknown"))
    raise AssertionError("product LLM call is forbidden in run-013")
llm_mod.LLM.structured = forbid_llm

async def probe():
    ping = await service.service({}, {"op": "ping"})
    health = await service.service(
        {}, {"op": "call", "method": "GET", "path": "/health"}
    )
    search = await service.service(
        {},
        {
            "op": "call",
            "method": "GET",
            "path": "/v1/rag/search",
            "params": {"q": "외부 의무", "mode": "auto", "scope": ""},
        },
    )
    valid_post = await service.service(
        {},
        {
            "op": "call",
            "method": "POST",
            "path": "/v1/rag/ask",
            "json": {
                "question": "외부 의무",
                "filter": False,
                "recover": False,
                "mode": "legacy-auto",
                "scope": "",
            },
        },
    )
    post_validation = await service.service(
        {},
        {
            "op": "call",
            "method": "POST",
            "path": "/v1/rag/ask",
            "json": {},
        },
    )
    service._require_query_only_call(
        {"op": "call", "method": "POST", "path": "/v1/rag/ask"}
    )
    blocked_inputs = {
        "upload": {"op": "upload", "filename": "mutation.pdf", "file_b64": "AA=="},
        "apply": {"op": "apply", "tar_b64": "AA=="},
        "apply-from": {"op": "apply_from", "path": "/tmp/mutation.tar"},
        "snapshot": {"op": "snapshot"},
        "snapshot-to": {"op": "snapshot_to", "path": "/tmp/mutation.tar"},
        "report": {"op": "report"},
        "ls": {"op": "ls", "path": "/tmp"},
        "feedback": {
            "op": "call", "method": "POST", "path": "/v1/rag/feedback"
        },
        "link-pick": {
            "op": "call", "method": "POST", "path": "/v1/rag/links/pick"
        },
        "docs": {"op": "call", "method": "GET", "path": "/docs"},
        "put": {"op": "call", "method": "PUT", "path": "/v1/rag/search"},
    }
    blocked = {
        name: await service.service({}, request)
        for name, request in blocked_inputs.items()
    }
    bound_secret = os.environ.get("QDRANT_API_KEY", "")
    if not bound_secret:
        raise AssertionError("service did not resolve the Qdrant secret binding")
    os.environ["QDRANT_API_KEY"] = bound_secret + "-tampered"
    try:
        secret_tamper = await service.service({}, {"op": "ping"})
    finally:
        os.environ["QDRANT_API_KEY"] = bound_secret
    frames_model = os.environ.get("RAG_FRAMES_MODEL", "")
    os.environ["RAG_FRAMES_MODEL"] = "ambient-model-is-forbidden"
    try:
        semantic_value_tamper = await service.service({}, {"op": "ping"})
    finally:
        os.environ["RAG_FRAMES_MODEL"] = frames_model
    module_rows = []
    for name in sorted(
        key for key in sys.modules
        if key == "service" or key == "lawrag" or key.startswith("lawrag.")
    ):
        module = sys.modules[name]
        raw_file = getattr(module, "__file__", None)
        if raw_file is None:
            module_rows.append({"module": name, "file": None})
            continue
        path = Path(raw_file).resolve()
        try:
            relative = path.relative_to(revision_root)
        except ValueError as exc:
            raise AssertionError(f"product import escaped frozen revision: {name}") from exc
        module_rows.append({"module": name, "file": relative.as_posix()})
    binding = service._RELEASE_BINDING or {}
    ops_mod = sys.modules.get("lawrag.api.ops")
    ops_routes = sorted(
        str(getattr(route, "path", ""))
        for route in service._app().routes
        if str(getattr(route, "path", "")).startswith("/v1/ops")
    )
    ops_state = {
        "inbox": None if ops_mod is None else getattr(ops_mod, "INBOX_DIR", None),
        "watcher_started": (
            None if ops_mod is None else getattr(ops_mod, "_WATCHER_STARTED", None)
        ),
        "routes": ops_routes,
    }
    removed_entrypoints = [
        name for name in ("_do_upload", "_do_snapshot", "_do_apply")
        if hasattr(service, name)
    ]
    return {
        "ping": ping,
        "health": health,
        "search": search,
        "valid_post": valid_post,
        "post_validation": post_validation,
        "blocked": blocked,
        "retrieval_runtime": binding.get("retrieval_runtime"),
        "control_planes": binding.get("control_planes"),
        "vector_runtime": binding.get("vector_runtime"),
        "module_provenance": module_rows,
        "removed_entrypoints": removed_entrypoints,
        "ops_state": ops_state,
        "qdrant_secret_injected": bool(bound_secret),
        "qdrant_secret_tamper": secret_tamper,
        "semantic_value_tamper": semantic_value_tamper,
        "llm_calls": llm_calls,
        "network_calls": network_calls,
    }

try:
    result = asyncio.run(probe())
finally:
    llm_mod.LLM.structured = original_structured
    socket.socket.connect = original_connect
print("ADR0158_CHILD_JSON=" + json.dumps(
    result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
))
'''
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            child,
            str(fixture.candidate.revision_root),
            str(ROOT),
        ],
        cwd="/tmp",
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    marker = "ADR0158_CHILD_JSON="
    rows = [
        line[len(marker):]
        for line in completed.stdout.splitlines()
        if line.startswith(marker)
    ]
    if completed.returncode != 0 or len(rows) != 1:
        raise AssertionError(
            "fresh sealed service subprocess failed: "
            f"returncode={completed.returncode}; stdout={completed.stdout!r}; "
            f"stderr={completed.stderr!r}"
        )
    value = json.loads(rows[0])
    if not isinstance(value, Mapping):
        raise AssertionError("sealed service subprocess returned a non-object")
    return value


def _no_release_service_subprocess(fixture: Fixture) -> Mapping[str, Any]:
    """Prove the frozen GenOS service cannot fall back without a release."""

    child = r'''
import asyncio
import json
from pathlib import Path
import site
import sys
import sysconfig

revision_root = Path(sys.argv[1]).resolve()
repository_root = Path(sys.argv[2]).resolve()
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
safe_paths = []
for raw in sys.path:
    if not raw:
        continue
    path = Path(raw).resolve()
    try:
        path.relative_to(repository_root)
    except ValueError:
        safe_paths.append(raw)
        continue
    if any(
        path == dependency_root or dependency_root in path.parents
        for dependency_root in dependency_roots
    ):
        safe_paths.append(raw)
sys.path[:] = [str(revision_root), *safe_paths]
sys.dont_write_bytecode = True

import service

result = asyncio.run(service.service({}, {"op": "ping"}))
print("ADR0158_NO_RELEASE_JSON=" + json.dumps(
    result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
))
'''
    environment = dict(os.environ)
    environment.pop("LAWRAG_RELEASE_STORE", None)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["LAWRAG_RELEASE_REQUIRED"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            child,
            str(fixture.candidate.revision_root),
            str(ROOT),
        ],
        cwd="/tmp",
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    marker = "ADR0158_NO_RELEASE_JSON="
    rows = [
        line[len(marker):]
        for line in completed.stdout.splitlines()
        if line.startswith(marker)
    ]
    if completed.returncode != 0 or len(rows) != 1:
        raise AssertionError(
            "no-release service subprocess failed: "
            f"returncode={completed.returncode}; stdout={completed.stdout!r}; "
            f"stderr={completed.stderr!r}"
        )
    value = json.loads(rows[0])
    if not isinstance(value, Mapping):
        raise AssertionError("no-release service probe returned a non-object")
    return value


def _off_release_service_subprocess(
    fixture: Fixture, *, ambient_intent: tuple[str, str] | None = None
) -> Mapping[str, Any]:
    """Boot the canonical generation-zero release in a clean environment."""

    child = r'''
import asyncio
import json
from pathlib import Path
import site
import socket
import sys
import sysconfig

revision_root = Path(sys.argv[1]).resolve()
repository_root = Path(sys.argv[2]).resolve()
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
safe_paths = []
for raw in sys.path:
    if not raw:
        continue
    path = Path(raw).resolve()
    try:
        path.relative_to(repository_root)
    except ValueError:
        safe_paths.append(raw)
        continue
    if any(
        path == dependency_root or dependency_root in path.parents
        for dependency_root in dependency_roots
    ):
        safe_paths.append(raw)
sys.path[:] = [str(revision_root), *safe_paths]
sys.dont_write_bytecode = True
network_calls = []
def forbid_connect(_socket, address):
    network_calls.append(repr(address))
    raise AssertionError("network access is forbidden in run-013")
socket.socket.connect = forbid_connect
import service

async def probe():
    ping = await service.service({}, {"op": "ping"})
    search = None
    if ping.get("ready"):
        search = await service.service({}, {
            "op": "call", "method": "GET", "path": "/v1/rag/search",
            "params": {"q": "외부 의무", "mode": "auto", "scope": ""},
        })
    binding = service._RELEASE_BINDING or {}
    return {
        "ping": ping,
        "search": search,
        "network_calls": network_calls,
        "vector_runtime": binding.get("vector_runtime"),
        "retrieval_runtime": binding.get("retrieval_runtime"),
    }

print("ADR0158_OFF_JSON=" + json.dumps(
    asyncio.run(probe()), ensure_ascii=False, sort_keys=True, separators=(",", ":")
))
'''
    environment = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "LAWRAG_RELEASE_REQUIRED": "1",
        "LAWRAG_SERVING_SEALED": "1",
        "LAWRAG_RELEASE_STORE": str(fixture.off_store.root),
        "LAWRAG_CODE_PACKAGE_ROOT": str(fixture.candidate.revision_root),
        "RAG_MAIN_PIPELINE_MANIFEST": str(fixture.off_release_main_path),
        "LAWRAG_ADMITTED_LLM_DESCRIPTOR_SHA256": str(
            fixture.llm_descriptor["descriptor_sha256"]
        ),
        "RAG_VECTOR": "0",
        "RAG_VECTOR_BACKEND": "file",
        "LAWRAG_EMBEDDING_DISABLED": "1",
    }
    if ambient_intent is not None:
        environment[ambient_intent[0]] = ambient_intent[1]
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            child,
            str(fixture.candidate.revision_root),
            str(ROOT),
        ],
        cwd="/tmp",
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    marker = "ADR0158_OFF_JSON="
    rows = [
        line[len(marker):]
        for line in completed.stdout.splitlines()
        if line.startswith(marker)
    ]
    if completed.returncode != 0 or len(rows) != 1:
        raise AssertionError(
            "SourceSet OFF service subprocess failed: "
            f"returncode={completed.returncode}; stdout={completed.stdout!r}; "
            f"stderr={completed.stderr!r}"
        )
    value = json.loads(rows[0])
    if not isinstance(value, Mapping):
        raise AssertionError("SourceSet OFF service probe returned a non-object")
    return value


def case_sealed_service_query_only(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    activate_fixture_environment(fixture)
    semantic_root = fixture.snapshot.runtime_artifact_path("semantics.content")
    canonical_registry = fixture.snapshot.semantic_path(
        "domain_graph", "canonical.json"
    )
    conventional_components = (
        "runtime/llm.json",
        "aliases.json",
        "delegation.json",
        "law_index.json",
        "frames",
        "taxonomy",
        "lexicon",
        "wiki/wiki",
        "rules/engine.json",
        "assertion_shortcuts.disabled.json",
        "scopes.yml",
    )
    if (
        not semantic_root.is_dir()
        or not canonical_registry.is_file()
        or any(
            not fixture.snapshot.semantic_path(*relative.split("/")).exists()
            for relative in conventional_components
        )
    ):
        raise AssertionError("release semantic directory is incomplete")
    tier1_mod = importlib.import_module("lawrag.core.domain_graph.tier1")
    registry = tier1_mod.Tier1Registry.load(canonical_registry)
    if registry.concepts or registry.relations or registry.assertions:
        raise AssertionError("fixture Tier-1 registry is not the declared empty registry")
    semantic_sha256 = fixture.release_mod.runtime_artifact_sha256(semantic_root)
    if semantic_sha256 != fixture.release_b.semantics.content_sha256:
        raise AssertionError("mounted semantic directory differs from release proof")
    secret_files = sorted(fixture.secret_binding_root.glob("*.secret"))
    if (
        stat.S_IMODE(fixture.secret_binding_root.lstat().st_mode) != 0o700
        or len(secret_files) != 1
        or stat.S_IMODE(secret_files[0].lstat().st_mode) != 0o400
        or sha256_file(secret_files[0]) != fixture.qdrant_secret_file_sha256
        or os.environ.get("QDRANT_API_KEY", "")
    ):
        raise AssertionError("Qdrant secret binding fixture is not sealed")
    no_release = _no_release_service_subprocess(fixture)
    if (
        no_release.get("ready") is not False
        or no_release.get("release_mode") != "release"
        or no_release.get("release_error") != "RuntimeError"
    ):
        raise AssertionError("GenOS service fell back without an active release store")
    probe = _sealed_service_subprocess(fixture)
    ping = probe["ping"]
    health = probe["health"]
    search = probe["search"]
    valid_post = probe["valid_post"]
    post_validation = probe["post_validation"]
    blocked = probe["blocked"]
    fixture.llm_calls.extend(
        {"kind": str(kind), "process": "sealed-service-child"}
        for kind in (probe.get("llm_calls") or [])
    )
    fixture.network_calls.extend(
        str(value) for value in (probe.get("network_calls") or [])
    )
    if probe.get("llm_calls") or probe.get("network_calls"):
        raise AssertionError("sealed service attempted LLM or network access")
    if probe.get("removed_entrypoints"):
        raise AssertionError("sealed service retained a removed mutation entrypoint")
    secret_tamper = probe.get("qdrant_secret_tamper") or {}
    if (
        probe.get("qdrant_secret_injected") is not True
        or "sealed credential changed after bootstrap"
        not in str(secret_tamper.get("error") or "")
    ):
        raise AssertionError("sealed service did not revalidate its bound secret")
    if "active semantic value changed after bootstrap: RAG_FRAMES_MODEL" not in str(
        (probe.get("semantic_value_tamper") or {}).get("error") or ""
    ):
        raise AssertionError("sealed service did not revalidate product-role models")
    if probe.get("ops_state") != {
        "inbox": None,
        "watcher_started": False,
        "routes": [],
    }:
        raise AssertionError("sealed service retained an ops mutation surface")
    if not ping.get("ready") or ping.get("release_mode") != "release":
        raise AssertionError("sealed service did not boot the active release")
    if not health.get("ok") or health.get("status") != 200:
        raise AssertionError("approved GET query route did not serve")
    if post_validation.get("status") != 422:
        raise AssertionError("approved POST query route did not reach validation")
    valid_post_json = valid_post.get("json") or {}
    if (
        not valid_post.get("ok")
        or valid_post.get("status") != 200
        or valid_post_json.get("question") != "외부 의무"
        or not valid_post_json.get("context")
        or valid_post_json.get("content_snapshot")
        != fixture.snapshot.compact_receipt()
        or valid_post_json.get("retrieval_runtime")
        != fixture.retrieval_runtime
    ):
        raise AssertionError("approved POST query route did not execute retrieval")
    if (
        not search.get("ok")
        or search.get("status") != 200
        or (search.get("json") or {}).get("content_snapshot")
        != fixture.snapshot.compact_receipt()
    ):
        raise AssertionError("approved retrieval GET did not use the pinned snapshot")
    if any("error" not in value or "PermissionError" not in str(value["error"]) for value in blocked.values()):
        raise AssertionError("sealed service exposed a mutation or unapproved route")
    health_snapshot = (health.get("json") or {}).get("content_snapshot")
    if health_snapshot != fixture.snapshot.compact_receipt():
        raise AssertionError("sealed service health exposed another content snapshot")
    expected_runtime = fixture.retrieval_runtime
    if expected_runtime is None:
        raise AssertionError("fixture retrieval runtime was not established")
    if (
        ping.get("retrieval_runtime") != expected_runtime
        or (health.get("json") or {}).get("retrieval_runtime")
        != expected_runtime
        or (search.get("json") or {}).get("retrieval_runtime")
        != expected_runtime
        or probe.get("retrieval_runtime") != expected_runtime
    ):
        raise AssertionError("service/API retrieval runtime receipt diverged")
    vector_runtime = probe.get("vector_runtime") or {}
    encoder_runtime = vector_runtime.get("encoder") or {}
    if (
        vector_runtime.get("backend") != "qdrant"
        or vector_runtime.get("config_sha256")
        != fixture.qdrant_config_sha256
        or vector_runtime.get("query_timeout_seconds") != 30
        or vector_runtime.get("trust_zone") != "internal"
        or vector_runtime.get("credential_configured") is not True
        or encoder_runtime.get("descriptor_sha256")
        != fixture.encoder_descriptor["descriptor_sha256"]
        or encoder_runtime.get("model_artifact_sha256")
        != fixture.model_artifact_sha256
        or encoder_runtime.get("local_artifact_verified") is not True
    ):
        raise AssertionError("service did not bind exact vector/encoder authorities")
    control_planes = probe.get("control_planes") or {}
    feedback_binding = control_planes.get("feedback") or {}
    shortcut_binding = control_planes.get("shortcuts") or {}
    expected_semantic_values = {
        "RAG_DOMAIN": "law",
        "RAG_RULES_MODE": "off",
        "RAG_LEXICON_COMPILE_MISSING": "0",
        "RAG_LEXICON_DOCS": "",
        "RAG_SPOT_MAX_TOKENS": "1000",
        "RAG_RECOVER_MODEL": "claude-haiku-4-5-20251001",
        "RAG_LEGALCLOSURE_ASSERTION_MODEL": (
            "claude-haiku-4-5-20251001"
        ),
        "RAG_FRAMES_MODEL": "claude-haiku-4-5-20251001",
        "RAG_TAXONOMY_MODEL": "claude-haiku-4-5-20251001",
    }
    if (
        control_planes.get("semantic_values") != expected_semantic_values
        or feedback_binding.get("root")
        != str(fixture.feedback_root.resolve())
        or feedback_binding.get("trust_zone") != "internal"
        or feedback_binding.get("root_sha256") != fixture.feedback_root_sha256
        or feedback_binding.get("trust_policy_id")
        != fixture.feedback_trust_policy_id
        or shortcut_binding.get("path")
        != str(fixture.reviewed_shortcut_path.resolve())
        or shortcut_binding.get("sha256") != fixture.reviewed_shortcut_sha256
    ):
        raise AssertionError("service startup did not pin feedback/shortcut planes")
    return {
        "release": ping.get("release"),
        "health_status": health["status"],
        "health_content_snapshot": health_snapshot,
        "retrieval_runtime": expected_runtime,
        "llm_descriptor_sha256": fixture.llm_descriptor[
            "descriptor_sha256"
        ],
        "encoder_descriptor_sha256": fixture.encoder_descriptor[
            "descriptor_sha256"
        ],
        "qdrant_config_sha256": fixture.qdrant_config_sha256,
        "qdrant_secret_file_sha256": fixture.qdrant_secret_file_sha256,
        "qdrant_secret_root_mode": "0700",
        "qdrant_secret_file_mode": "0400",
        "qdrant_secret_tamper_rejected": True,
        "semantic_value_tamper_rejected": True,
        "feedback_root_sha256": fixture.feedback_root_sha256,
        "feedback_trust_policy_id": fixture.feedback_trust_policy_id,
        "search_status": search["status"],
        "search_hit_count": len((search.get("json") or {}).get("hits") or []),
        "post_query_status": valid_post["status"],
        "post_query_context_count": len(valid_post_json["context"]),
        "post_query_validation_status": post_validation["status"],
        "fresh_service_first_import": True,
        "no_release_fail_closed": no_release,
        "removed_entrypoints": probe["removed_entrypoints"],
        "ops_state": probe["ops_state"],
        "semantic_values": expected_semantic_values,
        "service_module_provenance": probe["module_provenance"],
        "network_calls": probe["network_calls"],
        "semantic_artifact_kind": "directory",
        "semantic_content_sha256": semantic_sha256,
        "semantic_components": [
            "domain_graph/canonical.json", *conventional_components
        ],
        "approved_post_guard": "/v1/rag/ask",
        "control_planes": {
            "feedback_enabled": feedback_binding.get("enabled"),
            "feedback_external": True,
            "shortcuts_enabled": shortcut_binding.get("enabled"),
            "shortcut_sha256": shortcut_binding.get("sha256"),
            "shortcut_rows": shortcut_binding.get("rows"),
            "feedback_trust_zone": feedback_binding.get("trust_zone"),
            "stores_separated": (
                feedback_binding.get("root") != shortcut_binding.get("path")
            ),
        },
        "vector_runtime": {
            "backend": vector_runtime.get("backend"),
            "qdrant_config_sha256": vector_runtime.get("config_sha256"),
            "qdrant_trust_zone": vector_runtime.get("trust_zone"),
            "query_timeout_seconds": vector_runtime.get(
                "query_timeout_seconds"
            ),
            "encoder_descriptor_sha256": encoder_runtime.get(
                "descriptor_sha256"
            ),
            "model_artifact_sha256": encoder_runtime.get(
                "model_artifact_sha256"
            ),
            "credential_configured": vector_runtime.get(
                "credential_configured"
            ),
        },
        "blocked": {name: value["error"] for name, value in blocked.items()},
    }


def _snapshot_for_active(fixture: Fixture, pointer, release, binding):
    runtime_root = fixture.store.runtime_root(release.release_id)
    paths = binding.resolved_paths(runtime_root)
    artifacts = binding.resolved_artifacts(runtime_root)
    lock = fixture.catalog_mod.load_source_set_lock(
        artifacts["source_set.lock"],
        expected_artifact_sha256=release.source_set.lock_artifact_sha256,
    )
    materialized = fixture.catalog_mod.open_materialized_source_set(
        artifacts["source_set.materialization"], lock, trusted_root=runtime_root
    )
    return fixture.snapshot_mod.create_content_snapshot(
        pointer=pointer,
        release=release,
        runtime_binding=binding,
        source_set_lock=lock,
        catalog_sha256=release.source_set.catalog_sha256,
        catalog_artifact_sha256=release.source_set.catalog_artifact_sha256,
        materialized=materialized,
        runtime_paths=paths,
        runtime_artifact_paths=artifacts,
    )


def case_release_and_main_rollback_coherence(fixture: Fixture) -> Mapping[str, Any]:
    ensure_snapshot(fixture)
    main_promotion = importlib.import_module("lawrag.core.rag.main_promotion")
    active_transition_chain = json.loads(
        stable_regular_bytes(
            Path(fixture.runtime_artifacts_b["main.promotion_receipt"])
        )
    )
    chain_errors = main_promotion.validate_transition_chain(
        active_transition_chain, fixture.main_b
    )
    if chain_errors:
        raise AssertionError(
            "active MAIN transition chain is invalid: "
            + "; ".join(chain_errors)
        )
    active_apply_receipt = main_promotion.transition_chain_tip(
        active_transition_chain
    )
    active_promotion_plan = json.loads(
        stable_regular_bytes(
            Path(fixture.runtime_artifacts_b["main.promotion_plan"])
        )
    )
    if active_apply_receipt.get("promotion_plan") != active_promotion_plan:
        raise AssertionError("chain tip and standalone MAIN plan differ")
    original_main = active_apply_receipt.get("before_state")
    if not isinstance(original_main, dict):
        raise AssertionError("active MAIN apply receipt has no original state")
    rollback_main = {
        **original_main,
        "generation": int(fixture.main_b["generation"]) + 1,
        "updated_at": NOW,
    }
    rollback_receipt = {
        "schema_version": "main-rag-promotion-receipt-v2",
        "receipt_id": "mpr-run013-main-rollback",
        "action": "rollback",
        "promotion_id": active_apply_receipt["promotion_id"],
        "at": NOW,
        "actor": "adr0158-run013",
        "note": "frozen deterministic rollback probe",
        "before_state": dict(fixture.main_b),
        "before_state_sha256": canonical_sha256(fixture.main_b),
        "after_state_sha256": canonical_sha256(rollback_main),
        "rolled_back_apply_receipt": active_apply_receipt,
        "rolled_back_apply_receipt_sha256": canonical_sha256(
            active_apply_receipt
        ),
    }
    transition_errors = main_promotion.validate_transition_receipt(
        rollback_receipt, rollback_main
    )
    if transition_errors:
        raise AssertionError(
            "self-contained MAIN rollback receipt was rejected: "
            + "; ".join(transition_errors)
        )
    rollback_plan_errors = main_promotion.validate_runtime_promotion_plan(
        active_promotion_plan, rollback_receipt, rollback_main
    )
    if rollback_plan_errors:
        raise AssertionError(
            "release-proved MAIN plan did not validate rollback: "
            + "; ".join(rollback_plan_errors)
        )
    rollback_chain = main_promotion.build_transition_chain(
        [*active_transition_chain["transitions"], rollback_receipt],
        rollback_main,
    )
    if main_promotion.validate_transition_chain(rollback_chain, rollback_main):
        raise AssertionError("valid MAIN rollback chain did not replay")
    chain_tamper_cases = {}
    dropped = json.loads(canonical_bytes(rollback_chain))
    dropped["transitions"] = dropped["transitions"][1:]
    dropped["transition_count"] = len(dropped["transitions"])
    chain_tamper_cases["drop"] = dropped
    reordered = json.loads(canonical_bytes(rollback_chain))
    reordered["transitions"][0], reordered["transitions"][1] = (
        reordered["transitions"][1],
        reordered["transitions"][0],
    )
    chain_tamper_cases["reorder"] = reordered
    intermediate = json.loads(canonical_bytes(rollback_chain))
    intermediate["transitions"][1]["before_state"] = _main_state(
        0, adapter_on=False
    )
    chain_tamper_cases["intermediate-before"] = intermediate
    embedded_plan = json.loads(canonical_bytes(rollback_chain))
    embedded = embedded_plan["transitions"][1]["promotion_plan"]
    embedded["changes"]["switches"]["memory_entry"] = False
    embedded_plan["transitions"][1]["plan_sha256"] = canonical_sha256(
        embedded
    )
    chain_tamper_cases["embedded-plan"] = embedded_plan
    chain_tamper_errors = {}
    for name, tampered_chain in chain_tamper_cases.items():
        errors = main_promotion.validate_transition_chain(
            tampered_chain, rollback_main
        )
        if not errors:
            raise AssertionError(f"MAIN transition chain accepted {name} tamper")
        chain_tamper_errors[name] = errors
    tampered_receipt = {
        **rollback_receipt,
        "rolled_back_apply_receipt_sha256": h("tampered-apply-receipt"),
    }
    if not main_promotion.validate_transition_receipt(
        tampered_receipt, rollback_main
    ):
        raise AssertionError("tampered embedded MAIN apply receipt was accepted")
    plan = fixture.store.prepare_rollback(
        activation_id="rollback-content-b-to-a",
        validation_receipts=fixture.refs_a,
        created_at=NOW,
    )
    result = fixture.store.rollback(
        plan,
        actor="adr0158-run013",
        note="rollback B to A",
        confirm=True,
    )
    pointer_a, release_a, binding_a = fixture.store.load_active_runtime()
    if release_a.release_id != fixture.release_a.release_id or pointer_a.action != "rollback":
        raise AssertionError("explicit rollback did not restore release A")
    snapshot_a = _snapshot_for_active(fixture, pointer_a, release_a, binding_a)
    main_path = Path(binding_a.resolved_artifacts(fixture.store.runtime_root(release_a.release_id))["main.state"])
    main_state = json.loads(stable_regular_bytes(main_path))
    if (
        main_state != fixture.main_a
        or fixture.release_mod.runtime_artifact_sha256(main_path) != release_a.main.state_sha256
        or release_a.main.promotion_plan_sha256
        != fixture.main_plan_a_sha256
        or release_a.main.promotion_receipt_sha256
        != fixture.main_receipt_a_sha256
        or snapshot_a.main_generation != main_state["generation"]
        or snapshot_a.main_state_sha256 != release_a.main.state_sha256
    ):
        raise AssertionError("rollback release and MAIN binding are incoherent")
    exc = expect_error(
        fixture.snapshot_mod.ContentSnapshotError,
        lambda: fixture.snapshot_mod.bind_content_snapshot(snapshot_a),
    )
    current = fixture.snapshot_mod.current_content_snapshot(required=True)
    current_runtime = fixture.snapshot_mod.current_retrieval_runtime_receipt(
        required=True
    )
    if current.content_snapshot_sha256 != fixture.snapshot.content_snapshot_sha256:
        raise AssertionError("running process silently mixed rollback generations")
    if current_runtime != fixture.retrieval_runtime:
        raise AssertionError("running process silently mixed retrieval runtimes")
    return {
        "rollback_pointer_sha256": result.pointer.pointer_sha256,
        "active_release_id": release_a.release_id,
        "active_generation": pointer_a.generation,
        "main_generation": main_state["generation"],
        "main_state_sha256": release_a.main.state_sha256,
        "main_promotion_plan_sha256": release_a.main.promotion_plan_sha256,
        "main_promotion_receipt_sha256": (
            release_a.main.promotion_receipt_sha256
        ),
        "main_transition_action": rollback_receipt["action"],
        "main_transition_receipt_sha256": canonical_sha256(rollback_receipt),
        "main_transition_chain_sha256": canonical_sha256(rollback_chain),
        "main_transition_chain_tamper_errors": chain_tamper_errors,
        "main_transition_generation": rollback_main["generation"],
        "main_transition_plan_sha256": canonical_sha256(
            active_promotion_plan
        ),
        "main_transition_tamper_rejected": True,
        "restored_content_snapshot_sha256": snapshot_a.content_snapshot_sha256,
        "running_content_snapshot_sha256": current.content_snapshot_sha256,
        "running_retrieval_runtime_sha256": current_runtime[
            "retrieval_runtime_sha256"
        ],
        "restart_required_error": str(exc),
    }


CASE_FUNCTIONS: Mapping[str, Callable[[Fixture], Mapping[str, Any]]] = {
    "legacy-off-byte-equivalence": case_legacy_off_byte_equivalence,
    "trusted-release-single-snapshot": case_trusted_release_single_snapshot,
    "external-internal-unified-view": case_external_internal_unified_view,
    "artifact-byte-tamper-rejected": case_artifact_byte_tamper_rejected,
    "stale-authority-lock-rejected": case_stale_authority_lock_rejected,
    "duplicate-document-id-rejected": case_duplicate_document_id_rejected,
    "unmapped-document-id-rejected": case_unmapped_document_id_rejected,
    "index-content-fingerprint-bound": case_index_content_fingerprint_bound,
    "vector-content-fingerprint-bound": case_vector_content_fingerprint_bound,
    "scoped-index-provenance-preserved": case_scoped_index_provenance_preserved,
    "hit-section-citation-provenance": case_hit_section_citation_provenance,
    "relation-evidence-provenance": case_relation_evidence_provenance,
    "trace-and-tuple-provenance": case_trace_and_tuple_provenance,
    "feedback-shortcut-generation-lock": case_feedback_shortcut_generation_lock,
    "sealed-service-query-only": case_sealed_service_query_only,
    "release-and-main-rollback-coherence": case_release_and_main_rollback_coherence,
}


def execute_cases(
    fixture: Fixture | None,
    setup_error: BaseException | None,
    expectations: Mapping[str, str],
) -> list[dict[str, Any]]:
    if tuple(CASE_FUNCTIONS) != CASE_IDS or set(CASE_FUNCTIONS) != set(CASE_IDS):
        raise RuntimeError("case function registry differs from frozen input lock")
    if tuple(expectations) != CASE_IDS:
        raise RuntimeError("case expectations differ from frozen input lock")
    counts = {case_id: 0 for case_id in CASE_IDS}
    results: list[dict[str, Any]] = []
    for case_id in CASE_IDS:
        counts[case_id] += 1
        started = time.perf_counter()
        try:
            if setup_error is not None:
                raise RuntimeError(
                    f"fixture setup failed: {type(setup_error).__name__}: {setup_error}"
                ) from setup_error
            if fixture is None:
                raise RuntimeError("fixture is unavailable")
            evidence = dict(CASE_FUNCTIONS[case_id](fixture))
            result = {
                "case_id": case_id,
                "expected": expectations[case_id],
                "invocations": counts[case_id],
                "passed": True,
                "evidence": evidence,
            }
        except BaseException as exc:
            result = {
                "case_id": case_id,
                "expected": expectations[case_id],
                "invocations": counts[case_id],
                "passed": False,
                "error": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        results.append(result)
    if any(value != 1 for value in counts.values()):
        raise RuntimeError(f"case invocation count is not exactly one: {counts}")
    return results


def execution_metadata(output: Path) -> dict[str, Any]:
    original_argv = list(getattr(sys, "orig_argv", [sys.executable, *sys.argv]))
    statvfs = os.statvfs("/tmp")
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
            "dont_write_bytecode": sys.dont_write_bytecode,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "tmp": {
            "path": "/tmp",
            "device": Path("/tmp").stat().st_dev,
            "block_size": statvfs.f_bsize,
            "name_max": statvfs.f_namemax,
        },
        "output": str(Path(os.path.abspath(output))),
    }


def write_new_output(path: Path, value: Mapping[str, Any]) -> None:
    path = Path(os.path.abspath(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise RuntimeError("holdout requires O_NOFOLLOW")
    descriptor = os.open(path, flags | no_follow, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(raw)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--revision-sha256", required=True)
    parser.add_argument("--candidate-manifest-sha256", required=True)
    parser.add_argument(
        "--input-lock-sha256", default=INPUT_LOCK_SHA256
    )
    parser.add_argument(
        "--input-lock-bytes", type=int, default=INPUT_LOCK_BYTES
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not RUN_ID_RE.fullmatch(args.run_id):
        parser.error("--run-id must use canonical run-NNN form")
    output = Path(os.path.abspath(args.output))
    if os.path.lexists(output):
        parser.error(f"refusing to overwrite existing output: {output}")

    runner_raw = stable_regular_bytes(Path(__file__))
    input_lock = verify_input_lock(
        args.input_lock_sha256, args.input_lock_bytes
    )
    run012_before = verify_run012()
    candidate = verify_candidate(
        args.revision_id,
        args.revision_sha256,
        args.candidate_manifest_sha256,
        args.run_id,
    )
    paths = monitored_paths(candidate, output)
    environment_before = dict(os.environ)
    production_before = production_state(paths)
    original_sys_path = list(sys.path)
    started = time.perf_counter()
    fixture: Fixture | None = None
    setup_error: BaseException | None = None
    cases: list[dict[str, Any]] = []
    module_rows: list[dict[str, Any]] = []
    fixture_metadata: dict[str, Any] = {}
    original_umask = os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(
            prefix="adr0158-run013-", dir="/tmp"
        ) as raw_root:
            fixture_root = Path(raw_root)
            configure_fixture_environment(fixture_root)
            isolate_import_path(candidate.revision_root)
            try:
                fixture = build_fixture(fixture_root, candidate)
                os.environ["RAG_MAIN_PIPELINE_MANIFEST"] = str(fixture.off_main_path)
                fixture_metadata = {
                    "root_parent": str(fixture_root.parent),
                    "root_device": fixture_root.stat().st_dev,
                    "source_set_sha256": fixture.lock.source_set_sha256,
                    "lock_sha256": fixture.lock.lock_sha256,
                    "lock_artifact_sha256": fixture.lock_artifact_sha256,
                    "materialization_sha256": fixture.materialization_sha256,
                    "materialization_receipt_sha256": (
                        fixture.materialized_stage.receipt_sha256
                    ),
                    "catalog_sha256": fixture.catalog_sha256,
                    "catalog_artifact_sha256": fixture.catalog_artifact_sha256,
                    "semantic_generation": fixture.release_b.semantics.generation_id,
                    "semantic_content_sha256": fixture.release_b.semantics.content_sha256,
                    "semantic_artifact_kind": "directory",
                    "reviewed_shortcut_sha256": fixture.reviewed_shortcut_sha256,
                    "lexical_artifact_sha256": fixture.snapshot.index_binding(
                        "lexical"
                    ).artifact_sha256,
                    "lexical_build_fingerprint": fixture.snapshot.index_binding(
                        "lexical"
                    ).build_fingerprint,
                    "vector_artifact_sha256": fixture.snapshot.index_binding(
                        "vector"
                    ).artifact_sha256,
                    "vector_build_fingerprint": fixture.snapshot.index_binding(
                        "vector"
                    ).build_fingerprint,
                    "embedding_model_artifact_sha256": (
                        fixture.model_artifact_sha256
                    ),
                    "embedding_model_artifact_mode": f"{stat.S_IMODE(fixture.model_artifact_path.lstat().st_mode):04o}",
                    "embedding_model_fingerprint": fixture.model_fingerprint,
                    "llm_descriptor_sha256": fixture.llm_descriptor[
                        "descriptor_sha256"
                    ],
                    "encoder_descriptor_sha256": fixture.encoder_descriptor[
                        "descriptor_sha256"
                    ],
                    "qdrant_config_sha256": fixture.qdrant_config_sha256,
                    "qdrant_trust_zone": "internal",
                    "qdrant_secret_file_sha256": (
                        fixture.qdrant_secret_file_sha256
                    ),
                    "qdrant_secret_root_mode": f"{stat.S_IMODE(fixture.secret_binding_root.lstat().st_mode):04o}",
                    "feedback_root_sha256": fixture.feedback_root_sha256,
                    "feedback_trust_policy_id": (
                        fixture.feedback_trust_policy_id
                    ),
                    "main_promotion_receipt_sha256": (
                        fixture.main_receipt_b_sha256
                    ),
                    "main_transition_chain_sha256": (
                        fixture.main_receipt_b_sha256
                    ),
                    "main_promotion_plan_sha256": (
                        fixture.main_plan_b_sha256
                    ),
                    "runtime_main_promotion_receipt_sha256": (
                        fixture.release_mod.runtime_artifact_sha256(
                            Path(
                                fixture.runtime_artifacts_b[
                                    "main.promotion_receipt"
                                ]
                            )
                        )
                    ),
                    "runtime_main_transition_chain_sha256": (
                        fixture.release_mod.runtime_artifact_sha256(
                            Path(
                                fixture.runtime_artifacts_b[
                                    "main.promotion_receipt"
                                ]
                            )
                        )
                    ),
                    "runtime_main_promotion_plan_sha256": (
                        fixture.release_mod.runtime_artifact_sha256(
                            Path(
                                fixture.runtime_artifacts_b[
                                    "main.promotion_plan"
                                ]
                            )
                        )
                    ),
                    "release_manifest_sha256": fixture.release_b.manifest_sha256,
                    "runtime_binding_sha256": fixture.binding_b.binding_sha256,
                    "content_snapshot_sha256": (
                        fixture.snapshot.content_snapshot_sha256
                    ),
                    "retrieval_runtime_sha256": None,
                }
            except BaseException as exc:
                setup_error = exc
            cases = execute_cases(
                fixture,
                setup_error,
                input_lock["expectations"],
            )
            module_rows = candidate_module_provenance(candidate.revision_root)
            if fixture is not None:
                if fixture.retrieval_runtime is not None:
                    fixture_metadata["retrieval_runtime_sha256"] = (
                        fixture.retrieval_runtime[
                            "retrieval_runtime_sha256"
                        ]
                    )
                fixture.llm_mod.LLM.structured = fixture.llm_structured_original
                fixture.snapshot_mod.reset_content_snapshot_for_tests()
    finally:
        os.umask(original_umask)
        sys.path[:] = original_sys_path
        os.environ.clear()
        os.environ.update(environment_before)

    environment_after = dict(os.environ)
    production_after = production_state(paths)
    run012_after = verify_run012()
    environment_unchanged = environment_after == environment_before
    production_unchanged = production_after == production_before
    run012_unchanged = run012_after == run012_before
    case_passed = sum(1 for row in cases if row.get("passed"))
    product_llm_calls = len(fixture.llm_calls) if fixture is not None else 0
    network_calls = len(fixture.network_calls) if fixture is not None else 0
    exact_once = (
        len(cases) == len(CASE_IDS)
        and [row.get("case_id") for row in cases] == list(CASE_IDS)
        and all(row.get("invocations") == 1 for row in cases)
    )
    passed = (
        case_passed == len(CASE_IDS)
        and exact_once
        and production_unchanged
        and environment_unchanged
        and run012_unchanged
        and product_llm_calls == 0
        and network_calls == 0
        and setup_error is None
    )
    result: dict[str, Any] = {
        "schema_version": "adr0158-sourceset-content-snapshot-holdout-v1",
        "run_id": args.run_id,
        "candidate": {
            "candidate_id": candidate.manifest.get("candidate_id"),
            "manifest_path": CANDIDATE_MANIFEST.relative_to(ROOT).as_posix(),
            "manifest_sha256": candidate.manifest_sha256,
            "revision_id": candidate.revision_id,
            "revision_sha256": candidate.revision_sha256,
            "revision_root": candidate.revision_root.relative_to(ROOT).as_posix(),
            "files": list(candidate.files),
        },
        "input_lock": input_lock,
        "prior_run_artifact": {
            **run012_after,
            "unchanged": run012_unchanged,
        },
        "controls": {
            "product_llm_calls": product_llm_calls,
            "network_calls_requested": network_calls,
            "fixture_root": "fresh direct child of /tmp",
            "production_import": False,
            "output_publish": "O_CREAT|O_EXCL|O_NOFOLLOW",
        },
        "fixture": fixture_metadata,
        "cases": cases,
        "summary": {
            "passed": passed,
            "cases_passed": case_passed,
            "cases_total": len(CASE_IDS),
            "cases_exactly_once": exact_once,
            "focused_regressions_failed": len(CASE_IDS) - case_passed,
            "production_paths_modified": not production_unchanged,
            "environment_modified": not environment_unchanged,
            "main_wiring_changed": not production_unchanged,
            "llm_calls": product_llm_calls,
            "network_calls": network_calls,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        },
        "production_monitor": {
            "paths": [str(path) for path in paths],
            "unchanged": production_unchanged,
            "before_sha256": canonical_sha256(production_before),
            "after_sha256": canonical_sha256(production_after),
            "environment_unchanged": environment_unchanged,
            "environment_before_sha256": canonical_sha256(environment_before),
            "environment_after_sha256": canonical_sha256(environment_after),
        },
        "module_provenance": module_rows,
        "runner": {
            "path": Path(__file__).relative_to(ROOT).as_posix(),
            "sha256": sha256_bytes(runner_raw),
            "bytes": len(runner_raw),
        },
        "execution": execution_metadata(output),
    }
    if setup_error is not None:
        result["fixture_setup_error"] = {
            "error": type(setup_error).__name__,
            "message": str(setup_error),
            "traceback": "".join(
                traceback.format_exception(
                    type(setup_error), setup_error, setup_error.__traceback__
                )
            ),
        }
    result["result_sha256"] = canonical_sha256(result)
    write_new_output(output, result)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
