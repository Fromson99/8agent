"""Single bootstrap for repository paths during the v1 -> v2 layout migration.

Only this module is allowed to discover the repository by walking parent
directories.  Callers resolve a logical root ID instead of counting
``Path(__file__).parents`` or spelling ``data/`` and ``docs/`` themselves.

The default remains v1 until a separately validated activation receipt changes
``LAWRAG_LAYOUT_VERSION``.  Merely creating the numbered v2 directories cannot
silently redirect production data.

Migration is deliberately one-way copy-only: ``copy-verify-0`` publishes a
verified copy, ``dual-read-compare`` checks both locations, and
``final-verify`` issues the only receipt that may be bound to activation.
Legacy-source retirement is outside this module.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "workspace-layout-v2"
LAYOUT_ENV = "LAWRAG_LAYOUT_VERSION"
ROOT_ENV = "LAWRAG_WORKSPACE_ROOT"
MANIFEST = Path("00_SYSTEM") / "WORKSPACE.json"
ACTIVATION_RECEIPT_ENV = "LAWRAG_LAYOUT_ACTIVATION_RECEIPT"
ACTIVATION_RECEIPT_SCHEMA = "workspace-layout-activation-v1"
MIGRATION_PLAN_SCHEMA = "workspace-copy-plan-v1"
MIGRATION_RECEIPT_SCHEMA = "workspace-migration-phase-receipt-v1"
MIGRATION_SEQUENCE = (
    "copy-verify-0",
    "dual-read-compare",
    "final-verify",
)
_ALLOWED_LAYOUTS = frozenset({"v1", "v2"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HASH_CHUNK_BYTES = 1024 * 1024
_RENAME_NOREPLACE = 1
_AT_FDCWD = -100


class LayoutError(ValueError):
    """The workspace manifest or requested logical path is invalid."""


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _migration_relative_path(value: object, *, field: str) -> str:
    """Normalize a migration path without accepting platform-specific escapes."""

    raw = str(value or "")
    if raw != raw.strip() or "\\" in raw or "\x00" in raw:
        raise LayoutError(f"{field} must be a canonical POSIX relative path")
    parts = raw.split("/")
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise LayoutError(f"{field} must be a safe relative path: {value!r}")
    return path.as_posix()


def _path_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _checked_workspace_path(
    root: Path,
    relative_path: object,
    *,
    field: str,
    require_leaf: bool,
) -> tuple[str, Path]:
    """Resolve lexically below root and reject every symlink already present."""

    relative = _migration_relative_path(relative_path, field=field)
    current = root.resolve()
    parts = PurePosixPath(relative).parts
    for position, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if require_leaf:
                raise LayoutError(f"{field} does not exist: {relative}")
            break
        if stat.S_ISLNK(info.st_mode):
            raise LayoutError(f"{field} traverses a symlink: {relative}")
        if position < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise LayoutError(f"{field} parent is not a directory: {relative}")
    return relative, root.resolve().joinpath(*parts)


def _paths_overlap(left: str, right: str) -> bool:
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    common = min(len(left_parts), len(right_parts))
    return left_parts[:common] == right_parts[:common]


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _stream_file_details(path: Path) -> tuple[str, int, str]:
    """Hash one regular file without following a symlink or loading it in RAM."""

    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise LayoutError(f"migration source is not a regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise LayoutError(f"cannot open migration file safely: {path}: {exc}") from exc
    digest = hashlib.sha256()
    total = 0
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise LayoutError(f"migration source changed type: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
                total += len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if _stat_identity(before) != _stat_identity(opened):
        raise LayoutError(f"migration source changed before hashing: {path}")
    if _stat_identity(opened) != _stat_identity(after) or total != after.st_size:
        raise LayoutError(f"migration source changed while hashing: {path}")
    return digest.hexdigest(), total, f"{stat.S_IMODE(after.st_mode):04o}"


def stream_file_sha256(path: str | Path) -> str:
    """Return the streaming SHA-256 of a stable, non-symlink regular file."""

    digest, _size, _mode = _stream_file_details(Path(path))
    return digest


@dataclass(frozen=True)
class ArtifactFingerprint:
    kind: str
    mode: str
    bytes: int
    content_sha256: str
    merkle_sha256: str
    file_count: int
    directory_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "mode": self.mode,
            "bytes": self.bytes,
            "content_sha256": self.content_sha256,
            "merkle_sha256": self.merkle_sha256,
            "file_count": self.file_count,
            "directory_count": self.directory_count,
        }


def _fingerprint_node(path: Path, logical_path: str) -> ArtifactFingerprint:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode):
        raise LayoutError(f"symlinks are not migration artifacts: {path}")
    if stat.S_ISREG(before.st_mode):
        content_sha256, size, mode = _stream_file_details(path)
        payload = {
            "kind": "file",
            "path": logical_path,
            "mode": mode,
            "size": size,
            "content_sha256": content_sha256,
        }
        return ArtifactFingerprint(
            kind="file",
            mode=mode,
            bytes=size,
            content_sha256=content_sha256,
            merkle_sha256=_canonical_sha256(payload),
            file_count=1,
            directory_count=0,
        )
    if not stat.S_ISDIR(before.st_mode):
        raise LayoutError(f"special files are not migration artifacts: {path}")

    children: list[dict[str, Any]] = []
    total_bytes = 0
    file_count = 0
    directory_count = 1
    try:
        entries = sorted(path.iterdir(), key=lambda child: os.fsencode(child.name))
    except OSError as exc:
        raise LayoutError(f"cannot enumerate migration directory: {path}: {exc}") from exc
    for child in entries:
        child_logical = (
            child.name if logical_path == "." else f"{logical_path}/{child.name}"
        )
        child_fingerprint = _fingerprint_node(child, child_logical)
        children.append(
            {
                "name": child.name,
                "kind": child_fingerprint.kind,
                "mode": child_fingerprint.mode,
                "size": child_fingerprint.bytes,
                "merkle_sha256": child_fingerprint.merkle_sha256,
            }
        )
        total_bytes += child_fingerprint.bytes
        file_count += child_fingerprint.file_count
        directory_count += child_fingerprint.directory_count
    after = path.lstat()
    if _stat_identity(before) != _stat_identity(after):
        raise LayoutError(f"migration directory changed while hashing: {path}")
    mode = f"{stat.S_IMODE(after.st_mode):04o}"
    payload = {
        "kind": "directory",
        "path": logical_path,
        "mode": mode,
        "size": total_bytes,
        "children": children,
    }
    merkle_sha256 = _canonical_sha256(payload)
    return ArtifactFingerprint(
        kind="directory",
        mode=mode,
        bytes=total_bytes,
        content_sha256=merkle_sha256,
        merkle_sha256=merkle_sha256,
        file_count=file_count,
        directory_count=directory_count,
    )


def _fingerprint_path(path: Path) -> ArtifactFingerprint:
    return _fingerprint_node(path, ".")


def discover_root(start: str | Path | None = None) -> Path:
    """Find the workspace without assuming this module's directory depth."""

    configured = os.environ.get(ROOT_ENV)
    if configured:
        root = Path(configured).expanduser().resolve()
        if not (root / MANIFEST).is_file():
            raise LayoutError(f"{ROOT_ENV} has no {MANIFEST}: {root}")
        return root

    seeds = [Path(start).resolve()] if start is not None else [Path.cwd().resolve()]
    module_path = Path(__file__).resolve()
    if module_path not in seeds:
        seeds.append(module_path)
    seen: set[Path] = set()
    for seed in seeds:
        current = seed if seed.is_dir() else seed.parent
        for candidate in (current, *current.parents):
            if candidate in seen:
                continue
            seen.add(candidate)
            if (candidate / MANIFEST).is_file():
                return candidate
    raise LayoutError(f"cannot discover workspace containing {MANIFEST}")


def _relative_path(value: object, *, field: str, allow_null: bool = False) -> str | None:
    if value is None and allow_null:
        return None
    text = str(value or "").strip()
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise LayoutError(f"{field} must be a safe relative path: {value!r}")
    return path.as_posix()


@dataclass(frozen=True)
class RootSpec:
    id: str
    canonical_path: str
    legacy_path: str | None
    state: str


@dataclass(frozen=True)
class WorkspaceLayout:
    root: Path
    mode: str
    default_layout_version: str
    canonical_root_pattern: str
    roots: Mapping[str, RootSpec]
    legacy_top_level_directories: tuple[str, ...]
    root_file_policy: Mapping[str, tuple[str, ...]]
    invariants: tuple[str, ...]
    manifest_sha256: str

    def _validate_environment_activation(self) -> None:
        receipt_value = os.environ.get(ACTIVATION_RECEIPT_ENV, "").strip()
        if not receipt_value:
            raise LayoutError(
                f"v2 environment activation requires {ACTIVATION_RECEIPT_ENV}"
            )
        receipt_path = Path(receipt_value).expanduser()
        if not receipt_path.is_absolute():
            receipt_path = self.root / receipt_path
        try:
            receipt_raw = _stable_regular_bytes(receipt_path)
            receipt = json.loads(receipt_raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LayoutError(f"cannot read layout activation receipt: {exc}") from exc
        if not isinstance(receipt, Mapping):
            raise LayoutError("layout activation receipt must be an object")
        errors: list[str] = []
        if receipt.get("schema_version") != ACTIVATION_RECEIPT_SCHEMA:
            errors.append("schema_version")
        if receipt.get("status") != "active":
            errors.append("status")
        if receipt.get("layout_version") != "v2":
            errors.append("layout_version")
        if receipt.get("workspace_manifest_sha256") != self.manifest_sha256:
            errors.append("workspace_manifest_sha256")
        if not _SHA256.fullmatch(str(receipt.get("validation_receipt_sha256") or "")):
            errors.append("validation_receipt_sha256")
        if not _SHA256.fullmatch(str(receipt.get("validation_record_sha256") or "")):
            errors.append("validation_record_sha256")
        if not _SHA256.fullmatch(str(receipt.get("migration_plan_sha256") or "")):
            errors.append("migration_plan_sha256")
        try:
            _migration_relative_path(
                receipt.get("validation_receipt_path"),
                field="validation_receipt_path",
            )
        except LayoutError:
            errors.append("validation_receipt_path")
        if not str(receipt.get("activation_id") or "").strip():
            errors.append("activation_id")
        if errors:
            raise LayoutError(
                "invalid layout activation receipt fields: " + ", ".join(errors)
            )
        _validate_bound_final_receipt(self, receipt)

    def path(self, root_id: str, *, layout_version: str | None = None) -> Path:
        """Resolve a logical root under an explicitly selected layout version."""

        try:
            spec = self.roots[root_id]
        except KeyError as exc:
            raise LayoutError(f"unknown workspace root id: {root_id}") from exc
        if layout_version is None:
            version = os.environ.get(LAYOUT_ENV, self.default_layout_version)
            if (
                version == "v2"
                and self.mode == "bridge"
                and self.default_layout_version == "v1"
            ):
                self._validate_environment_activation()
        else:
            # Explicit selection is used by migration/audit tools to inspect a
            # path.  It does not change the process-wide production layout.
            version = layout_version
        if version not in _ALLOWED_LAYOUTS:
            raise LayoutError(f"unsupported {LAYOUT_ENV}: {version!r}")
        if version == "v1" and spec.legacy_path:
            return self.root / spec.legacy_path
        return self.root / spec.canonical_path

    def canonical_path(self, root_id: str) -> Path:
        return self.path(root_id, layout_version="v2")

    def legacy_path(self, root_id: str) -> Path | None:
        spec = self.roots.get(root_id)
        if spec is None:
            raise LayoutError(f"unknown workspace root id: {root_id}")
        return self.root / spec.legacy_path if spec.legacy_path else None

    @property
    def allowed_root_files(self) -> frozenset[str]:
        return frozenset(
            name for values in self.root_file_policy.values() for name in values
        )


@dataclass(frozen=True)
class MigrationItem:
    source: str
    target: str
    fingerprint: ArtifactFingerprint

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "fingerprint": self.fingerprint.as_dict(),
        }


@dataclass(frozen=True)
class MigrationPlan:
    workspace_manifest_sha256: str
    items: tuple[MigrationItem, ...]
    plan_sha256: str
    schema_version: str = MIGRATION_PLAN_SCHEMA
    sequence: tuple[str, ...] = MIGRATION_SEQUENCE

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workspace_manifest_sha256": self.workspace_manifest_sha256,
            "sequence": list(self.sequence),
            "items": [item.as_dict() for item in self.items],
            "source_deletion_supported": False,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "plan_sha256": self.plan_sha256}


@dataclass(frozen=True)
class MigrationPhaseItem:
    source: str
    target: str
    status: str
    fingerprint: ArtifactFingerprint

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "status": self.status,
            "fingerprint": self.fingerprint.as_dict(),
        }


@dataclass(frozen=True)
class MigrationReceipt:
    phase: str
    workspace_manifest_sha256: str
    plan_sha256: str
    completed_phases: tuple[str, ...]
    prior_receipt_sha256s: tuple[str, ...]
    items: tuple[MigrationPhaseItem, ...]
    receipt_sha256: str
    schema_version: str = MIGRATION_RECEIPT_SCHEMA
    sequence: tuple[str, ...] = MIGRATION_SEQUENCE

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "phase": self.phase,
            "workspace_manifest_sha256": self.workspace_manifest_sha256,
            "plan_sha256": self.plan_sha256,
            "sequence": list(self.sequence),
            "completed_phases": list(self.completed_phases),
            "prior_receipt_sha256s": list(self.prior_receipt_sha256s),
            "items": [item.as_dict() for item in self.items],
            "source_deleted": False,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "receipt_sha256": self.receipt_sha256}


def _plan_hash(
    workspace_manifest_sha256: str,
    items: tuple[MigrationItem, ...],
) -> str:
    provisional = MigrationPlan(
        workspace_manifest_sha256=workspace_manifest_sha256,
        items=items,
        plan_sha256="",
    )
    return _canonical_sha256(provisional.unsigned_dict())


def _validate_fingerprint(fingerprint: ArtifactFingerprint) -> bool:
    return (
        fingerprint.kind in {"file", "directory"}
        and isinstance(fingerprint.mode, str)
        and bool(re.fullmatch(r"[0-7]{4}", fingerprint.mode))
        and isinstance(fingerprint.bytes, int)
        and fingerprint.bytes >= 0
        and isinstance(fingerprint.file_count, int)
        and fingerprint.file_count >= 0
        and isinstance(fingerprint.directory_count, int)
        and fingerprint.directory_count >= 0
        and isinstance(fingerprint.content_sha256, str)
        and bool(_SHA256.fullmatch(fingerprint.content_sha256))
        and isinstance(fingerprint.merkle_sha256, str)
        and bool(_SHA256.fullmatch(fingerprint.merkle_sha256))
        and (fingerprint.file_count == 1 if fingerprint.kind == "file" else True)
        and (fingerprint.directory_count == 0 if fingerprint.kind == "file" else True)
    )


def _validate_plan_integrity(plan: MigrationPlan, layout: WorkspaceLayout) -> None:
    errors: list[str] = []
    if plan.schema_version != MIGRATION_PLAN_SCHEMA:
        errors.append("schema_version")
    if plan.sequence != MIGRATION_SEQUENCE:
        errors.append("sequence")
    if plan.workspace_manifest_sha256 != layout.manifest_sha256:
        errors.append("workspace_manifest_sha256")
    if not plan.items:
        errors.append("items")
    safe_pairs: list[tuple[str, str]] = []
    for position, item in enumerate(plan.items):
        try:
            source = _migration_relative_path(
                item.source, field=f"items[{position}].source"
            )
            target = _migration_relative_path(
                item.target, field=f"items[{position}].target"
            )
            safe_pairs.append((source, target))
        except LayoutError:
            errors.append(f"items[{position}].path")
        if not _validate_fingerprint(item.fingerprint):
            errors.append(f"items[{position}].fingerprint")
    try:
        normalized = _validate_pair_boundaries(safe_pairs)
        if tuple(safe_pairs) != normalized:
            errors.append("item_order")
    except LayoutError:
        errors.append("item_boundaries")
    if plan.plan_sha256 != _plan_hash(plan.workspace_manifest_sha256, plan.items):
        errors.append("plan_sha256")
    if errors:
        raise LayoutError("invalid immutable migration plan: " + ", ".join(errors))


def _validate_pair_boundaries(
    pairs: Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    normalized = tuple(sorted(pairs, key=lambda pair: (pair[1], pair[0])))
    sources = [source for source, _target in normalized]
    targets = [target for _source, target in normalized]
    for position, source in enumerate(sources):
        for other in sources[position + 1 :]:
            if _paths_overlap(source, other):
                raise LayoutError(
                    f"migration sources must not overlap: {source!r}, {other!r}"
                )
    for position, target in enumerate(targets):
        for other in targets[position + 1 :]:
            if _paths_overlap(target, other):
                raise LayoutError(
                    f"migration targets must not overlap: {target!r}, {other!r}"
                )
    for source in sources:
        for target in targets:
            if _paths_overlap(source, target):
                raise LayoutError(
                    f"migration source and target must not overlap: {source!r}, {target!r}"
                )
    return normalized


def build_migration_plan(
    layout: WorkspaceLayout,
    paths: Mapping[str, str] | Iterable[tuple[str, str]],
) -> MigrationPlan:
    """Freeze copy-only source/target pairs and their exact source bytes.

    Existing targets are accepted only when their complete fingerprint already
    equals the source.  The API intentionally has no move or source-delete mode.
    """

    raw_pairs = list(paths.items()) if isinstance(paths, Mapping) else list(paths)
    if not raw_pairs:
        raise LayoutError("migration plan must contain at least one path")
    safe_pairs: list[tuple[str, str]] = []
    resolved: dict[tuple[str, str], tuple[Path, Path]] = {}
    for position, pair in enumerate(raw_pairs):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise LayoutError(f"migration paths[{position}] must be source/target")
        source, source_path = _checked_workspace_path(
            layout.root,
            pair[0],
            field=f"migration paths[{position}].source",
            require_leaf=True,
        )
        target, target_path = _checked_workspace_path(
            layout.root,
            pair[1],
            field=f"migration paths[{position}].target",
            require_leaf=False,
        )
        safe_pairs.append((source, target))
        resolved[(source, target)] = (source_path, target_path)
    normalized = _validate_pair_boundaries(safe_pairs)

    items: list[MigrationItem] = []
    for source, target in normalized:
        source_path, target_path = resolved[(source, target)]
        fingerprint = _fingerprint_path(source_path)
        if _path_exists(target_path):
            try:
                if os.path.samefile(source_path, target_path):
                    raise LayoutError(
                        f"migration source and target are the same inode: {source}"
                    )
            except OSError as exc:
                raise LayoutError(f"cannot compare migration paths: {exc}") from exc
            if _fingerprint_path(target_path) != fingerprint:
                raise LayoutError(
                    f"existing migration target differs from source: {target}"
                )
        items.append(MigrationItem(source, target, fingerprint))
    frozen_items = tuple(items)
    return MigrationPlan(
        workspace_manifest_sha256=layout.manifest_sha256,
        items=frozen_items,
        plan_sha256=_plan_hash(layout.manifest_sha256, frozen_items),
    )


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_directory_chain(root: Path, relative_parent: PurePosixPath) -> Path:
    current = root.resolve()
    for part in relative_parent.parts:
        candidate = current / part
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            os.mkdir(candidate, 0o755)
            _fsync_directory(current)
            info = candidate.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise LayoutError(f"migration target parent is unsafe: {candidate}")
        current = candidate
    return current


def _copy_regular_file(source: Path, target: Path) -> None:
    source_before = source.lstat()
    if not stat.S_ISREG(source_before.st_mode):
        raise LayoutError(f"copy source is not a regular file: {source}")
    source_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        source_flags |= os.O_NOFOLLOW
    source_descriptor = os.open(source, source_flags)
    target_descriptor: int | None = None
    try:
        source_opened = os.fstat(source_descriptor)
        if _stat_identity(source_before) != _stat_identity(source_opened):
            raise LayoutError(f"copy source changed before opening: {source}")
        target_descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        while True:
            chunk = os.read(source_descriptor, _HASH_CHUNK_BYTES)
            if not chunk:
                break
            view = memoryview(chunk)
            while view:
                written = os.write(target_descriptor, view)
                if written <= 0:
                    raise LayoutError(f"short write while staging: {target}")
                view = view[written:]
        os.fchmod(target_descriptor, stat.S_IMODE(source_opened.st_mode))
        os.fsync(target_descriptor)
        source_after = os.fstat(source_descriptor)
        if _stat_identity(source_opened) != _stat_identity(source_after):
            raise LayoutError(f"copy source changed while reading: {source}")
    finally:
        if target_descriptor is not None:
            os.close(target_descriptor)
        os.close(source_descriptor)


def _copy_tree(source: Path, target: Path) -> None:
    before = source.lstat()
    if stat.S_ISLNK(before.st_mode):
        raise LayoutError(f"symlinks are not migration artifacts: {source}")
    if stat.S_ISREG(before.st_mode):
        _copy_regular_file(source, target)
        return
    if not stat.S_ISDIR(before.st_mode):
        raise LayoutError(f"special files are not migration artifacts: {source}")
    os.mkdir(target, 0o700)
    entries = sorted(source.iterdir(), key=lambda child: os.fsencode(child.name))
    for child in entries:
        _copy_tree(child, target / child.name)
    after = source.lstat()
    if _stat_identity(before) != _stat_identity(after):
        raise LayoutError(f"copy source directory changed while reading: {source}")
    os.chmod(target, stat.S_IMODE(after.st_mode), follow_symlinks=False)
    _fsync_directory(target)


def _atomic_publish_no_replace(staging: Path, target: Path) -> None:
    """Publish without replacing any target inode.

    Linux filesystems with ``renameat2`` get a single atomic rename.  Some WSL
    and mounted filesystems return ``EINVAL``/``EOPNOTSUPP`` for that flag.  A
    regular file then uses atomic hard-link creation; a directory atomically
    reserves the target name and remains invalid (extra marker) until every
    staged child is durable.  Consumers compare the full frozen fingerprint,
    so a crash-retained partial directory is fail-closed and never activated.
    """

    if os.name != "posix":
        raise LayoutError("atomic no-replace publish requires a POSIX host")
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    unsupported = {errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP}
    if renameat2 is not None:
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            _AT_FDCWD,
            os.fsencode(staging),
            _AT_FDCWD,
            os.fsencode(target),
            _RENAME_NOREPLACE,
        )
        if result == 0:
            return
        error_number = ctypes.get_errno()
        if error_number == errno.EEXIST:
            raise FileExistsError(error_number, os.strerror(error_number), target)
        if error_number not in unsupported:
            raise LayoutError(
                f"atomic migration publish failed: {os.strerror(error_number)}"
            )

    staging_info = staging.lstat()
    if stat.S_ISREG(staging_info.st_mode):
        try:
            os.link(staging, target, follow_symlinks=False)
        except FileExistsError:
            raise
        except OSError as exc:
            raise LayoutError(f"hard-link publication failed: {exc}") from exc
        staging.unlink()
        _fsync_directory(target.parent)
        return
    if not stat.S_ISDIR(staging_info.st_mode):
        raise LayoutError("fallback publication supports only files/directories")

    try:
        target.mkdir(mode=0o700)
    except FileExistsError:
        raise
    marker = target / ".LAWRAG_PUBLICATION_INCOMPLETE"
    marker_descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(marker_descriptor, b"workspace-copy-v1\n")
        os.fsync(marker_descriptor)
    finally:
        os.close(marker_descriptor)
    _fsync_directory(target)
    try:
        for child in sorted(staging.iterdir(), key=lambda value: os.fsencode(value.name)):
            os.rename(child, target / child.name)
        _fsync_directory(target)
        os.chmod(target, stat.S_IMODE(staging_info.st_mode), follow_symlinks=False)
        marker.unlink()
        _fsync_directory(target)
        _fsync_directory(target.parent)
        staging.rmdir()
    except Exception as exc:
        raise LayoutError(
            f"reserved migration target is incomplete and retained: {target}: {exc}"
        ) from exc


def _discard_staging(container: Path) -> None:
    """Remove only the private staging directory created by this module."""

    if not _path_exists(container):
        return
    info = container.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise LayoutError(f"refusing to clean unsafe staging path: {container}")
    shutil.rmtree(container)


def _publish_copy(
    layout: WorkspaceLayout,
    item: MigrationItem,
) -> tuple[str, ArtifactFingerprint]:
    _source, source_path = _checked_workspace_path(
        layout.root, item.source, field="migration source", require_leaf=True
    )
    _target, target_path = _checked_workspace_path(
        layout.root, item.target, field="migration target", require_leaf=False
    )
    if _fingerprint_path(source_path) != item.fingerprint:
        raise LayoutError(f"migration source no longer matches plan: {item.source}")
    if _path_exists(target_path):
        try:
            if os.path.samefile(source_path, target_path):
                raise LayoutError(
                    f"migration source and target are the same inode: {item.source}"
                )
        except OSError as exc:
            raise LayoutError(f"cannot compare migration paths: {exc}") from exc
        current = _fingerprint_path(target_path)
        if current != item.fingerprint:
            raise LayoutError(f"existing migration target differs: {item.target}")
        return "already-present", current

    parent = _ensure_directory_chain(
        layout.root, PurePosixPath(item.target).parent
    )
    # A private same-filesystem container makes the final rename atomic.
    container = Path(
        tempfile.mkdtemp(prefix=f".{target_path.name}.migration-", dir=parent)
    )
    staging = container / "payload"
    published = False
    try:
        _copy_tree(source_path, staging)
        staged_fingerprint = _fingerprint_path(staging)
        if staged_fingerprint != item.fingerprint:
            raise LayoutError(f"staging verification failed: {item.target}")
        if _fingerprint_path(source_path) != item.fingerprint:
            raise LayoutError(f"migration source changed after staging: {item.source}")
        try:
            _atomic_publish_no_replace(staging, target_path)
            published = True
            status = "published"
        except FileExistsError:
            existing = _fingerprint_path(target_path)
            if existing != item.fingerprint:
                raise LayoutError(
                    f"migration target appeared with different bytes: {item.target}"
                )
            status = "already-present-race"
        _fsync_directory(parent)
        final_fingerprint = _fingerprint_path(target_path)
        if final_fingerprint != item.fingerprint:
            raise LayoutError(f"published migration target failed verification: {item.target}")
        return status, final_fingerprint
    finally:
        # renameat2 leaves only an empty container after successful publication.
        # On failure, cleanup is restricted to the private staging container;
        # neither a source nor a published target is ever removed here.
        if published:
            container.rmdir()
        else:
            _discard_staging(container)


def _receipt_hash(
    *,
    phase: str,
    plan: MigrationPlan,
    completed_phases: tuple[str, ...],
    prior_receipt_sha256s: tuple[str, ...],
    items: tuple[MigrationPhaseItem, ...],
) -> str:
    provisional = MigrationReceipt(
        phase=phase,
        workspace_manifest_sha256=plan.workspace_manifest_sha256,
        plan_sha256=plan.plan_sha256,
        completed_phases=completed_phases,
        prior_receipt_sha256s=prior_receipt_sha256s,
        items=items,
        receipt_sha256="",
    )
    return _canonical_sha256(provisional.unsigned_dict())


def _make_receipt(
    plan: MigrationPlan,
    *,
    phase: str,
    previous: MigrationReceipt | None,
    items: tuple[MigrationPhaseItem, ...],
) -> MigrationReceipt:
    try:
        phase_index = MIGRATION_SEQUENCE.index(phase)
    except ValueError as exc:
        raise LayoutError(f"unknown migration phase: {phase}") from exc
    if phase_index == 0:
        if previous is not None:
            raise LayoutError("copy-verify-0 must not have a previous receipt")
        prior_hashes: tuple[str, ...] = ()
    else:
        if previous is None:
            raise LayoutError(f"{phase} requires the previous phase receipt")
        expected_previous = MIGRATION_SEQUENCE[phase_index - 1]
        _validate_receipt_integrity(previous, plan, expected_phase=expected_previous)
        prior_hashes = (
            *previous.prior_receipt_sha256s,
            previous.receipt_sha256,
        )
    completed = MIGRATION_SEQUENCE[: phase_index + 1]
    digest = _receipt_hash(
        phase=phase,
        plan=plan,
        completed_phases=completed,
        prior_receipt_sha256s=prior_hashes,
        items=items,
    )
    return MigrationReceipt(
        phase=phase,
        workspace_manifest_sha256=plan.workspace_manifest_sha256,
        plan_sha256=plan.plan_sha256,
        completed_phases=completed,
        prior_receipt_sha256s=prior_hashes,
        items=items,
        receipt_sha256=digest,
    )


def _validate_receipt_integrity(
    receipt: MigrationReceipt,
    plan: MigrationPlan,
    *,
    expected_phase: str,
) -> None:
    phase_index = MIGRATION_SEQUENCE.index(expected_phase)
    expected_hash = _canonical_sha256(receipt.unsigned_dict())
    errors: list[str] = []
    if receipt.schema_version != MIGRATION_RECEIPT_SCHEMA:
        errors.append("schema_version")
    if receipt.phase != expected_phase:
        errors.append("phase")
    if receipt.sequence != MIGRATION_SEQUENCE:
        errors.append("sequence")
    if receipt.completed_phases != MIGRATION_SEQUENCE[: phase_index + 1]:
        errors.append("completed_phases")
    if len(receipt.prior_receipt_sha256s) != phase_index or not all(
        isinstance(value, str) and _SHA256.fullmatch(value)
        for value in receipt.prior_receipt_sha256s
    ):
        errors.append("prior_receipt_sha256s")
    if receipt.workspace_manifest_sha256 != plan.workspace_manifest_sha256:
        errors.append("workspace_manifest_sha256")
    if receipt.plan_sha256 != plan.plan_sha256:
        errors.append("plan_sha256")
    if receipt.receipt_sha256 != expected_hash:
        errors.append("receipt_sha256")
    if len(receipt.items) != len(plan.items):
        errors.append("items")
    else:
        allowed_statuses = {
            "copy-verify-0": {
                "published",
                "already-present",
                "already-present-race",
            },
            "dual-read-compare": {"matched"},
            "final-verify": {"verified"},
        }[expected_phase]
        for position, (row, planned) in enumerate(zip(receipt.items, plan.items)):
            if (
                row.source != planned.source
                or row.target != planned.target
                or row.fingerprint != planned.fingerprint
                or row.status not in allowed_statuses
            ):
                errors.append(f"items[{position}]")
    if errors:
        raise LayoutError("invalid migration phase receipt: " + ", ".join(errors))


def execute_copy_verify_zero(
    layout: WorkspaceLayout,
    plan: MigrationPlan,
) -> MigrationReceipt:
    """Copy to fsynced staging, verify, and atomically publish each target."""

    _validate_plan_integrity(plan, layout)
    rows: list[MigrationPhaseItem] = []
    for item in plan.items:
        status, fingerprint = _publish_copy(layout, item)
        rows.append(
            MigrationPhaseItem(
                source=item.source,
                target=item.target,
                status=status,
                fingerprint=fingerprint,
            )
        )
    return _make_receipt(
        plan,
        phase="copy-verify-0",
        previous=None,
        items=tuple(rows),
    )


def _compare_plan_paths(
    layout: WorkspaceLayout,
    plan: MigrationPlan,
    *,
    status: str,
) -> tuple[MigrationPhaseItem, ...]:
    rows: list[MigrationPhaseItem] = []
    for item in plan.items:
        _source, source_path = _checked_workspace_path(
            layout.root, item.source, field="migration source", require_leaf=True
        )
        _target, target_path = _checked_workspace_path(
            layout.root, item.target, field="migration target", require_leaf=True
        )
        source_fingerprint = _fingerprint_path(source_path)
        target_fingerprint = _fingerprint_path(target_path)
        if source_fingerprint != item.fingerprint:
            raise LayoutError(f"migration source drifted: {item.source}")
        if target_fingerprint != item.fingerprint:
            raise LayoutError(f"migration target drifted: {item.target}")
        rows.append(
            MigrationPhaseItem(
                source=item.source,
                target=item.target,
                status=status,
                fingerprint=target_fingerprint,
            )
        )
    return tuple(rows)


def compare_dual_read(
    layout: WorkspaceLayout,
    plan: MigrationPlan,
    copy_receipt: MigrationReceipt,
) -> MigrationReceipt:
    """Read both v1 and v2 copies and require exact planned fingerprints."""

    _validate_plan_integrity(plan, layout)
    _validate_receipt_integrity(
        copy_receipt, plan, expected_phase="copy-verify-0"
    )
    return _make_receipt(
        plan,
        phase="dual-read-compare",
        previous=copy_receipt,
        items=_compare_plan_paths(layout, plan, status="matched"),
    )


def verify_final_migration(
    layout: WorkspaceLayout,
    plan: MigrationPlan,
    dual_read_receipt: MigrationReceipt,
) -> MigrationReceipt:
    """Issue the final validation receipt without deleting any legacy source."""

    _validate_plan_integrity(plan, layout)
    _validate_receipt_integrity(
        dual_read_receipt, plan, expected_phase="dual-read-compare"
    )
    return _make_receipt(
        plan,
        phase="final-verify",
        previous=dual_read_receipt,
        items=_compare_plan_paths(layout, plan, status="verified"),
    )


def _validate_serialized_receipt(receipt: Mapping[str, Any]) -> None:
    unsigned = dict(receipt)
    recorded_hash = str(unsigned.pop("receipt_sha256", ""))
    errors: list[str] = []
    if receipt.get("schema_version") != MIGRATION_RECEIPT_SCHEMA:
        errors.append("schema_version")
    if receipt.get("phase") != "final-verify":
        errors.append("phase")
    if receipt.get("sequence") != list(MIGRATION_SEQUENCE):
        errors.append("sequence")
    if receipt.get("completed_phases") != list(MIGRATION_SEQUENCE):
        errors.append("completed_phases")
    if receipt.get("source_deleted") is not False:
        errors.append("source_deleted")
    if not _SHA256.fullmatch(str(receipt.get("workspace_manifest_sha256") or "")):
        errors.append("workspace_manifest_sha256")
    if not _SHA256.fullmatch(str(receipt.get("plan_sha256") or "")):
        errors.append("plan_sha256")
    if not _SHA256.fullmatch(recorded_hash) or recorded_hash != _canonical_sha256(
        unsigned
    ):
        errors.append("receipt_sha256")
    prior = receipt.get("prior_receipt_sha256s")
    if not isinstance(prior, list) or len(prior) != 2 or not all(
        isinstance(value, str) and _SHA256.fullmatch(value) for value in prior
    ):
        errors.append("prior_receipt_sha256s")
    items = receipt.get("items")
    if not isinstance(items, list) or not items:
        errors.append("items")
    else:
        safe_pairs: list[tuple[str, str]] = []
        for position, item in enumerate(items):
            if not isinstance(item, Mapping):
                errors.append(f"items[{position}]")
                continue
            try:
                source = _migration_relative_path(
                    item.get("source"), field=f"items[{position}].source"
                )
                target = _migration_relative_path(
                    item.get("target"), field=f"items[{position}].target"
                )
                safe_pairs.append((source, target))
            except LayoutError:
                errors.append(f"items[{position}].path")
            if item.get("status") != "verified":
                errors.append(f"items[{position}].status")
            fingerprint = item.get("fingerprint")
            if not isinstance(fingerprint, Mapping):
                errors.append(f"items[{position}].fingerprint")
            else:
                integer_fields = ("bytes", "file_count", "directory_count")
                if (
                    fingerprint.get("kind") not in {"file", "directory"}
                    or not re.fullmatch(r"[0-7]{4}", str(fingerprint.get("mode") or ""))
                    or any(
                        not isinstance(fingerprint.get(field), int)
                        or fingerprint[field] < 0
                        for field in integer_fields
                    )
                    or not all(
                        _SHA256.fullmatch(str(fingerprint.get(field) or ""))
                        for field in ("content_sha256", "merkle_sha256")
                    )
                ):
                    errors.append(f"items[{position}].fingerprint")
        try:
            _validate_pair_boundaries(safe_pairs)
        except LayoutError:
            errors.append("item_boundaries")
    if errors:
        raise LayoutError(
            "invalid final migration validation receipt: " + ", ".join(errors)
        )


def _stable_regular_bytes(path: Path) -> bytes:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise LayoutError(f"record is not a non-symlink regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    chunks: list[bytes] = []
    try:
        opened = os.fstat(descriptor)
        if _stat_identity(before) != _stat_identity(opened):
            raise LayoutError(f"record changed before reading: {path}")
        while True:
            chunk = os.read(descriptor, _HASH_CHUNK_BYTES)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    if _stat_identity(opened) != _stat_identity(after) or len(raw) != after.st_size:
        raise LayoutError(f"record changed while reading: {path}")
    return raw


def _validate_bound_final_receipt(
    layout: WorkspaceLayout,
    activation: Mapping[str, Any],
) -> None:
    relative, validation_path = _checked_workspace_path(
        layout.root,
        activation.get("validation_receipt_path"),
        field="validation_receipt_path",
        require_leaf=True,
    )
    try:
        raw = _stable_regular_bytes(validation_path)
        validation = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LayoutError(
            f"cannot read bound validation receipt {relative}: {exc}"
        ) from exc
    if not isinstance(validation, Mapping):
        raise LayoutError("bound validation receipt must be an object")
    _validate_serialized_receipt(validation)
    errors: list[str] = []
    if hashlib.sha256(raw).hexdigest() != activation.get(
        "validation_receipt_sha256"
    ):
        errors.append("validation_receipt_sha256")
    if validation.get("receipt_sha256") != activation.get(
        "validation_record_sha256"
    ):
        errors.append("validation_record_sha256")
    if validation.get("workspace_manifest_sha256") != layout.manifest_sha256:
        errors.append("workspace_manifest_sha256")
    if validation.get("migration_plan_sha256") is not None:
        # Reject a confusing near-match key instead of silently accepting it.
        errors.append("unexpected migration_plan_sha256")
    if validation.get("plan_sha256") != activation.get("migration_plan_sha256"):
        errors.append("migration_plan_sha256")
    if errors:
        raise LayoutError(
            "activation is not bound to the exact workspace validation: "
            + ", ".join(errors)
        )


def persist_immutable_migration_record(
    layout: WorkspaceLayout,
    relative_path: str,
    record: MigrationPlan | MigrationReceipt,
) -> str:
    """Write a plan/receipt once and return the exact file SHA-256.

    An existing byte-identical record is idempotent; every other collision is
    rejected.  This function never removes or overwrites a source or record.
    """

    if isinstance(record, MigrationPlan):
        _validate_plan_integrity(record, layout)
    elif isinstance(record, MigrationReceipt):
        unsigned = record.unsigned_dict()
        if record.receipt_sha256 != _canonical_sha256(unsigned):
            raise LayoutError("migration receipt hash is invalid")
        if record.workspace_manifest_sha256 != layout.manifest_sha256:
            raise LayoutError("migration receipt workspace manifest does not match")
    else:
        raise LayoutError("record must be a MigrationPlan or MigrationReceipt")
    relative, target = _checked_workspace_path(
        layout.root,
        relative_path,
        field="migration record path",
        require_leaf=False,
    )
    raw = _canonical_json_bytes(record.as_dict()) + b"\n"
    digest = hashlib.sha256(raw).hexdigest()
    if _path_exists(target):
        if _stable_regular_bytes(target) == raw:
            return digest
        raise LayoutError(f"immutable migration record already differs: {relative}")

    parent = _ensure_directory_chain(layout.root, PurePosixPath(relative).parent)
    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{target.name}.record-", dir=parent
    )
    staging = Path(staging_name)
    published = False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            _atomic_publish_no_replace(staging, target)
            published = True
        except FileExistsError:
            if _stable_regular_bytes(target) != raw:
                raise LayoutError(
                    f"immutable migration record raced with different bytes: {relative}"
                )
        _fsync_directory(parent)
        if _stable_regular_bytes(target) != raw:
            raise LayoutError(f"immutable migration record failed verification: {relative}")
        return digest
    finally:
        if not published and _path_exists(staging):
            staging.unlink()


def _parse_manifest(
    blob: Mapping[str, Any], root: Path, *, manifest_sha256: str
) -> WorkspaceLayout:
    if blob.get("schema_version") != SCHEMA_VERSION:
        raise LayoutError(f"unsupported workspace schema: {blob.get('schema_version')!r}")
    mode = str(blob.get("mode") or "")
    if mode not in {"bridge", "v2-only"}:
        raise LayoutError(f"unsupported workspace mode: {mode!r}")
    default = str(blob.get("default_layout_version") or "")
    if default not in _ALLOWED_LAYOUTS:
        raise LayoutError(f"invalid default_layout_version: {default!r}")
    pattern = str(blob.get("canonical_root_pattern") or "")
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise LayoutError(f"invalid canonical_root_pattern: {exc}") from exc

    specs: dict[str, RootSpec] = {}
    canonical_paths: set[str] = set()
    for position, row in enumerate(blob.get("roots") or []):
        if not isinstance(row, Mapping):
            raise LayoutError(f"roots[{position}] must be an object")
        root_id = str(row.get("id") or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", root_id) or root_id in specs:
            raise LayoutError(f"invalid or duplicate root id: {root_id!r}")
        canonical = _relative_path(
            row.get("canonical_path"), field=f"roots[{position}].canonical_path"
        )
        assert canonical is not None
        if "/" in canonical or not compiled.fullmatch(canonical):
            raise LayoutError(f"non-canonical top-level root: {canonical!r}")
        if canonical in canonical_paths:
            raise LayoutError(f"duplicate canonical root: {canonical}")
        canonical_paths.add(canonical)
        legacy = _relative_path(
            row.get("legacy_path"),
            field=f"roots[{position}].legacy_path",
            allow_null=True,
        )
        state = str(row.get("state") or "")
        if state not in {"active", "bridge", "retired"}:
            raise LayoutError(f"invalid root state for {root_id}: {state!r}")
        specs[root_id] = RootSpec(root_id, canonical, legacy, state)
    if not specs:
        raise LayoutError("workspace roots cannot be empty")

    root_policy: dict[str, tuple[str, ...]] = {}
    for group, values in (blob.get("root_file_policy") or {}).items():
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise LayoutError(f"root_file_policy.{group} must be a string list")
        root_policy[str(group)] = tuple(values)

    legacy_dirs = tuple(str(v) for v in blob.get("legacy_top_level_directories") or [])
    return WorkspaceLayout(
        root=root,
        mode=mode,
        default_layout_version=default,
        canonical_root_pattern=pattern,
        roots=specs,
        legacy_top_level_directories=legacy_dirs,
        root_file_policy=root_policy,
        invariants=tuple(str(v) for v in blob.get("invariants") or []),
        manifest_sha256=manifest_sha256,
    )


def load_layout(root: str | Path | None = None) -> WorkspaceLayout:
    workspace = discover_root(root)
    path = workspace / MANIFEST
    try:
        raw = path.read_bytes()
        blob = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LayoutError(f"cannot read workspace manifest {path}: {exc}") from exc
    if not isinstance(blob, Mapping):
        raise LayoutError("workspace manifest root must be an object")
    return _parse_manifest(
        blob, workspace, manifest_sha256=hashlib.sha256(raw).hexdigest()
    )


def audit_top_level(layout: WorkspaceLayout | None = None) -> dict[str, Any]:
    """Report migration state without pretending bridge paths are already moved."""

    layout = layout or load_layout()
    canonical = {spec.canonical_path for spec in layout.roots.values()}
    actual_dirs = {
        path.name
        for path in layout.root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    }
    missing_canonical = sorted(canonical - actual_dirs)
    legacy_present = sorted(actual_dirs & set(layout.legacy_top_level_directories))
    unknown_dirs = sorted(actual_dirs - canonical - set(layout.legacy_top_level_directories))
    actual_files = {
        path.name
        for path in layout.root.iterdir()
        if path.is_file() and not path.name.startswith(".")
    }
    loose_files = sorted(actual_files - layout.allowed_root_files)
    activation_blockers: list[str] = []
    if layout.mode != "v2-only":
        activation_blockers.append("workspace mode is not v2-only")
    if layout.default_layout_version != "v2":
        activation_blockers.append("default layout is not v2")
    non_active = sorted(
        spec.id for spec in layout.roots.values() if spec.state != "active"
    )
    if non_active:
        activation_blockers.append("non-active roots: " + ", ".join(non_active))
    if missing_canonical:
        activation_blockers.append("canonical roots are missing")
    if legacy_present:
        activation_blockers.append("legacy roots remain")
    if unknown_dirs:
        activation_blockers.append("unknown roots remain")
    if loose_files:
        activation_blockers.append("unclassified root files remain")
    return {
        "schema_version": "workspace-layout-audit-v1",
        "mode": layout.mode,
        "default_layout_version": layout.default_layout_version,
        "canonical_roots": sorted(canonical),
        "missing_canonical_roots": missing_canonical,
        "legacy_roots_present": legacy_present,
        "unknown_top_level_directories": unknown_dirs,
        "unclassified_root_files": loose_files,
        "activation_blockers": activation_blockers,
        "target_ready": not activation_blockers,
    }
