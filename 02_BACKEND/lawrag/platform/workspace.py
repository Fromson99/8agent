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
This module may authorize a later legacy-source retirement with an immutable
receipt, but it never deletes or moves a legacy source.
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
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "workspace-layout-v2"
LAYOUT_ENV = "LAWRAG_LAYOUT_VERSION"
ROOT_ENV = "LAWRAG_WORKSPACE_ROOT"
MANIFEST = Path("00_SYSTEM") / "WORKSPACE.json"
ACTIVATION_RECEIPT_ENV = "LAWRAG_LAYOUT_ACTIVATION_RECEIPT"
ACTIVATION_RECEIPT_SCHEMA = "workspace-layout-activation-v2"
RETIREMENT_RECEIPT_ENV = "LAWRAG_LAYOUT_RETIREMENT_RECEIPT"
RETIREMENT_RECEIPT_SCHEMA = "workspace-legacy-retirement-authorization-v1"
RETIREMENT_SOURCE_EVIDENCE_SCHEMA = "workspace-legacy-retirement-source-v1"
MIGRATION_PLAN_SCHEMA = "workspace-copy-plan-v1"
MIGRATION_RECEIPT_SCHEMA = "workspace-migration-phase-receipt-v4"
CANONICAL_ROOT_BINDING_SCHEMA = "workspace-canonical-root-readiness-v3"
MIGRATION_SEQUENCE = (
    "copy-verify-0",
    "dual-read-compare",
    "final-verify",
)
_ALLOWED_LAYOUTS = frozenset({"v1", "v2"})
_SHA256 = re.compile(r"^[0-9a-f]{64}(?![\s\S])")
_MIGRATION_RELATIVE_PATH_PATTERN = (
    r"^(?!.*[\\\u0000-\u0020\u007F-\u00A0\u1680\u2000-\u200A"
    r"\u2028-\u2029\u202F\u205F\u3000\uFEFF])"
    r"(?!(?:.*/)?\.{1,2}(?:/|(?![\s\S])))"
    r"[^/]+(?:/[^/]+)*(?![\s\S])"
)
_MIGRATION_RELATIVE_PATH = re.compile(_MIGRATION_RELATIVE_PATH_PATTERN)
_CANONICAL_TEXT_PATTERN = (
    r"^(?![\u0000-\u0020\u007F-\u00A0\u1680\u2000-\u200A"
    r"\u2028-\u2029\u202F\u205F\u3000\uFEFF])"
    r"[\s\S]*[^\u0000-\u0020\u007F-\u00A0\u1680\u2000-\u200A"
    r"\u2028-\u2029\u202F\u205F\u3000\uFEFF](?![\s\S])"
)
_CANONICAL_TEXT = re.compile(_CANONICAL_TEXT_PATTERN)
_HASH_CHUNK_BYTES = 1024 * 1024
_RENAME_NOREPLACE = 1
_AT_FDCWD = -100
PUBLICATION_INCOMPLETE_MARKER = ".LAWRAG_PUBLICATION_INCOMPLETE"
_PUBLISH_STRATEGIES = frozenset(
    {"renameat2", "hardlink", "reserved-directory", "already-present"}
)
_LAYOUT_CACHE: dict[tuple[str, str], "WorkspaceLayout"] = {}


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
    """Accept only the schema's canonical, whitespace-free POSIX path language."""

    if not isinstance(value, str) or not _MIGRATION_RELATIVE_PATH.fullmatch(value):
        raise LayoutError(f"{field} must be a canonical POSIX relative path")
    return value


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _sha256_value(value: object, *, field: str) -> str:
    if not _is_sha256(value):
        raise LayoutError(f"{field} must be an exact lowercase SHA-256")
    return value


def _path_exists(path: Path) -> bool:
    try:
        path.lstat()
    except OSError as exc:
        if exc.errno in {errno.ENOENT, errno.ENOTDIR}:
            return False
        raise
    return True


def _publication_sidecar(path: Path) -> Path:
    return path.parent / f".{path.name}{PUBLICATION_INCOMPLETE_MARKER}"


def _is_reserved_publication_name(name: str) -> bool:
    return name == PUBLICATION_INCOMPLETE_MARKER or (
        name.startswith(".") and name.endswith(PUBLICATION_INCOMPLETE_MARKER)
    )


def _publication_markers(
    path: Path,
    *,
    boundary: Path | None = None,
) -> tuple[Path, ...]:
    """Return target/subtree and ancestor readiness markers without symlink walks.

    ``boundary`` is a lexical trust boundary.  Its descendants are inspected up
    to, but not including, the boundary itself; the requested target is always
    included.  This catches both publication sidecars and in-directory markers
    left on an ancestor by the reserved-directory fallback.
    """

    target = Path(os.path.abspath(os.fspath(path)))
    stop = Path(os.path.abspath(os.fspath(boundary))) if boundary is not None else None
    if stop is not None:
        try:
            target.relative_to(stop)
        except ValueError as exc:
            raise LayoutError(
                f"publication path escapes readiness boundary: {target}"
            ) from exc

    markers: set[Path] = set()
    current = target
    while True:
        sidecar = _publication_sidecar(current)
        if _path_exists(sidecar):
            markers.add(sidecar)
        internal = current / PUBLICATION_INCOMPLETE_MARKER
        if _path_exists(internal):
            markers.add(internal)
        parent = current.parent
        if current == stop or parent == current or parent == stop:
            break
        current = parent

    if not _path_exists(target):
        return tuple(sorted(markers, key=lambda value: os.fsencode(str(value))))
    try:
        root_info = target.lstat()
    except OSError as exc:
        raise LayoutError(f"cannot inspect publication readiness: {target}: {exc}") from exc
    if stat.S_ISLNK(root_info.st_mode):
        raise LayoutError(f"publication path is a symlink: {target}")
    if stat.S_ISREG(root_info.st_mode):
        return tuple(sorted(markers, key=lambda value: os.fsencode(str(value))))
    if not stat.S_ISDIR(root_info.st_mode):
        raise LayoutError(f"publication path is a special file: {target}")

    pending = [target]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise LayoutError(
                f"cannot inspect publication readiness: {directory}: {exc}"
            ) from exc
        for entry in entries:
            child = Path(entry.path)
            if _is_reserved_publication_name(entry.name):
                markers.add(child)
                continue
            try:
                child_info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise LayoutError(
                    f"cannot inspect publication member: {child}: {exc}"
                ) from exc
            if stat.S_ISLNK(child_info.st_mode):
                raise LayoutError(f"publication tree contains a symlink: {child}")
            if stat.S_ISDIR(child_info.st_mode):
                pending.append(child)
            elif not stat.S_ISREG(child_info.st_mode):
                raise LayoutError(
                    f"publication tree contains a special file: {child}"
                )
    return tuple(sorted(markers, key=lambda value: os.fsencode(str(value))))


def assert_publication_ready(
    path: str | Path,
    *,
    field: str = "public path",
    boundary: str | Path | None = None,
) -> Path:
    """Reject any path whose no-clobber publication did not reach readiness."""

    target = Path(path)
    markers = _publication_markers(
        target,
        boundary=Path(boundary) if boundary is not None else None,
    )
    if markers:
        rendered = ", ".join(str(marker) for marker in markers)
        raise LayoutError(f"{field} is an incomplete publication: {rendered}")
    return target


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
    if _is_reserved_publication_name(path.name):
        raise LayoutError(f"reserved publication marker is not an artifact: {path}")
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


@dataclass(frozen=True)
class PublicationInspection:
    relative_path: str
    exists: bool
    ready: bool
    marker_paths: tuple[str, ...]
    fingerprint: ArtifactFingerprint | None
    issue: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "workspace-publication-inspection-v1",
            "relative_path": self.relative_path,
            "exists": self.exists,
            "ready": self.ready,
            "marker_paths": list(self.marker_paths),
            "fingerprint": (
                self.fingerprint.as_dict() if self.fingerprint is not None else None
            ),
            "issue": self.issue,
            "mutates_workspace": False,
        }


@dataclass(frozen=True)
class PublicationQuarantinePlan:
    source: str
    quarantine_target: str
    inspection: PublicationInspection

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "workspace-publication-quarantine-plan-v1",
            "source": self.source,
            "quarantine_target": self.quarantine_target,
            "inspection": self.inspection.as_dict(),
            "operation": "operator-reviewed-source-and-marker-move-no-replace",
            "executed": False,
        }


def inspect_publication(
    layout: "WorkspaceLayout",
    relative_path: object,
    *,
    expected_fingerprint: ArtifactFingerprint | None = None,
) -> PublicationInspection:
    """Inspect a possibly partial target without changing or cleaning it."""

    relative, path = _checked_workspace_path(
        layout.root,
        relative_path,
        field="publication inspection path",
        require_leaf=False,
    )
    markers = _publication_markers(path, boundary=layout.root)
    marker_paths = tuple(
        marker.relative_to(layout.root.resolve()).as_posix() for marker in markers
    )
    exists = _path_exists(path)
    fingerprint: ArtifactFingerprint | None = None
    issue: str | None = None
    if markers:
        issue = "incomplete publication marker is present"
    elif not exists:
        issue = "publication target does not exist"
    else:
        try:
            fingerprint = _fingerprint_path(path)
        except (LayoutError, OSError) as exc:
            issue = str(exc)
        if (
            issue is None
            and expected_fingerprint is not None
            and fingerprint != expected_fingerprint
        ):
            issue = "publication fingerprint does not match expected bytes"
    return PublicationInspection(
        relative_path=relative,
        exists=exists,
        ready=exists and issue is None,
        marker_paths=marker_paths,
        fingerprint=fingerprint,
        issue=issue,
    )


def plan_publication_quarantine(
    layout: "WorkspaceLayout",
    relative_path: object,
    quarantine_relative_path: object,
    *,
    expected_fingerprint: ArtifactFingerprint | None = None,
) -> PublicationQuarantinePlan:
    """Create a non-destructive operator plan; this function never moves data."""

    inspection = inspect_publication(
        layout,
        relative_path,
        expected_fingerprint=expected_fingerprint,
    )
    if inspection.ready or not (inspection.exists or inspection.marker_paths):
        raise LayoutError("only an observed partial publication can be quarantined")
    quarantine, quarantine_path = _checked_workspace_path(
        layout.root,
        quarantine_relative_path,
        field="publication quarantine target",
        require_leaf=False,
    )
    if _paths_overlap(inspection.relative_path, quarantine):
        raise LayoutError("publication and quarantine target must not overlap")
    if _path_exists(quarantine_path) or _publication_markers(
        quarantine_path, boundary=layout.root
    ):
        raise LayoutError("publication quarantine target already exists or is reserved")
    return PublicationQuarantinePlan(
        source=inspection.relative_path,
        quarantine_target=quarantine,
        inspection=inspection,
    )


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
    activation_receipt: str | None = None
    retirement_receipt: str | None = None
    _routing_cache: dict[tuple[object, ...], Mapping[str, Any]] = field(
        default_factory=dict, compare=False, repr=False
    )
    _inspection_cache: dict[tuple[object, ...], Path] = field(
        default_factory=dict, compare=False, repr=False
    )

    def _validate_environment_activation(self) -> Mapping[str, Any]:
        receipt_path, receipt_raw, receipt = _read_environment_activation(self)
        _validate_activation_receipt_fields(self, receipt)
        return _validate_bound_final_receipt(
            self,
            receipt,
            activation_path=receipt_path,
            activation_raw=receipt_raw,
        )

    def _validate_environment_routing(self) -> Mapping[str, Any]:
        """Validate immutable activation bindings without rehashing all payloads."""

        receipt_path, receipt_raw, receipt = _read_environment_activation(self)
        _validate_activation_receipt_fields(self, receipt)
        validation_relative, validation_path = _checked_workspace_path(
            self.root,
            receipt.get("validation_receipt_path"),
            field="validation_receipt_path",
            require_leaf=True,
        )
        cache_key = (
            hashlib.sha256(receipt_raw).hexdigest(),
            _stat_identity(receipt_path.stat()),
            validation_relative,
            _stat_identity(validation_path.stat()),
        )
        cached = self._routing_cache.get(cache_key)
        if cached is not None:
            return cached
        _relative, _validation_raw, validation = _load_bound_final_receipt(
            self, receipt
        )
        self._routing_cache.clear()
        self._routing_cache[cache_key] = validation
        return validation

    def validate_activation(self) -> Mapping[str, Any]:
        """Run the expensive full source/target audit for an activation gate."""

        return self._validate_environment_activation()

    def inspection_path(self, root_id: str, *, layout_version: str) -> Path:
        """Resolve an explicit layout only for migration/audit inspection.

        Runtime callers must use :meth:`path` or :meth:`canonical_path`; this
        explicit selector intentionally performs no activation transition.
        """

        try:
            spec = self.roots[root_id]
        except KeyError as exc:
            raise LayoutError(f"unknown workspace root id: {root_id}") from exc
        version = layout_version
        if version not in _ALLOWED_LAYOUTS:
            raise LayoutError(f"unsupported {LAYOUT_ENV}: {version!r}")
        if version == "v1" and spec.legacy_path:
            selected = self.root / spec.legacy_path
        else:
            selected = self.root / spec.canonical_path
        try:
            identity = _stat_identity(selected.stat())
        except OSError:
            identity = None
        cache_key = (root_id, version, identity)
        cached = self._inspection_cache.get(cache_key)
        if cached is not None:
            return cached
        if selected == self.root / spec.canonical_path:
            ready = _canonical_root_directory(
                self, root_id=root_id, canonical_path=spec.canonical_path
            )
        else:
            ready = assert_publication_ready(
                selected,
                field=f"workspace root {root_id!r} ({version})",
                boundary=self.root,
            )
        for stale_key in tuple(self._inspection_cache):
            if stale_key[:2] == cache_key[:2] and stale_key != cache_key:
                self._inspection_cache.pop(stale_key, None)
        self._inspection_cache[cache_key] = ready
        return ready

    def path(self, root_id: str, *, layout_version: str | None = None) -> Path:
        """Resolve a runtime logical root under the activated layout."""

        if layout_version is not None:
            raise LayoutError(
                "explicit layout_version is inspection-only; use inspection_path()"
            )
        version = os.environ.get(LAYOUT_ENV, self.default_layout_version)
        if version not in _ALLOWED_LAYOUTS:
            raise LayoutError(f"unsupported {LAYOUT_ENV}: {version!r}")
        if version == "v1" and self.mode == "v2-only":
            raise LayoutError("v2-only workspace cannot resolve the v1 layout")
        if version == "v2":
            self._validate_environment_routing()
        return self.inspection_path(root_id, layout_version=version)

    def canonical_path(self, root_id: str) -> Path:
        """Resolve a canonical runtime root only after v2 activation validation."""

        self._validate_environment_routing()
        return self.inspection_path(root_id, layout_version="v2")

    def migration_target(self, source: str) -> Path:
        """Resolve one exact source through the active final migration receipt.

        This is a content projection, not a canonical-root alias.  It is used
        when a versioned publication such as ``.../GENERATIONS/.../lawrag`` is
        the runnable payload below a stable canonical container.
        """

        version = os.environ.get(LAYOUT_ENV, self.default_layout_version)
        if version != "v2":
            raise LayoutError("migration targets are runtime-visible only in v2")
        safe_source = _migration_relative_path(
            source, field="migration target source"
        )
        activation_path, activation_raw, activation = _read_environment_activation(
            self
        )
        _validate_activation_receipt_fields(self, activation)
        _relative, _validation_raw, validation = _load_bound_final_receipt(
            self, activation
        )
        rows = validation.get("items")
        assert isinstance(rows, list)
        matches = [row for row in rows if row.get("source") == safe_source]
        if len(matches) != 1:
            raise LayoutError(
                "active final receipt must contain exactly one migration target "
                f"for source: {safe_source}"
            )
        row = matches[0]
        expected = _fingerprint_from_mapping(
            row.get("fingerprint"), field="migration target fingerprint"
        )
        target_relative, target = _checked_workspace_path(
            self.root,
            row.get("target"),
            field="migration target",
            require_leaf=True,
        )
        assert_publication_ready(
            target,
            field=f"migration target {target_relative!r}",
            boundary=self.root,
        )
        if _fingerprint_path(target) != expected:
            raise LayoutError(
                f"migration target no longer matches final receipt: {target_relative}"
            )
        if os.environ.get(RETIREMENT_RECEIPT_ENV, "").strip():
            _validate_bound_final_receipt(
                self,
                activation,
                activation_path=activation_path,
                activation_raw=activation_raw,
            )
        else:
            source_relative, source_path = _checked_workspace_path(
                self.root,
                safe_source,
                field="migration target source",
                require_leaf=True,
            )
            assert_publication_ready(
                source_path,
                field=f"migration source {source_relative!r}",
                boundary=self.root,
            )
            if _fingerprint_path(source_path) != expected:
                raise LayoutError(
                    "migration source no longer matches final receipt: "
                    f"{source_relative}"
                )
        return target

    def legacy_path(self, root_id: str) -> Path | None:
        """Return a legacy path for migration inspection, never runtime routing."""

        spec = self.roots.get(root_id)
        if spec is None:
            raise LayoutError(f"unknown workspace root id: {root_id}")
        if not spec.legacy_path:
            return None
        return assert_publication_ready(
            self.root / spec.legacy_path,
            field=f"legacy workspace root {root_id!r}",
            boundary=self.root,
        )

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
    publish_strategy: str = "unrecorded"

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "status": self.status,
            "publish_strategy": self.publish_strategy,
            "fingerprint": self.fingerprint.as_dict(),
        }


@dataclass(frozen=True)
class CanonicalRootBinding:
    root_id: str
    canonical_path: str
    root_state: str
    completion_kind: str
    expected_kind: str
    evidence_targets: tuple[str, ...]
    covered_sources: tuple[str, ...]
    delegated_sources: tuple[str, ...]
    excluded_sources: tuple[str, ...]
    readiness_sha256: str

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CANONICAL_ROOT_BINDING_SCHEMA,
            "root_id": self.root_id,
            "canonical_path": self.canonical_path,
            "root_state": self.root_state,
            "completion_kind": self.completion_kind,
            "expected_kind": self.expected_kind,
            "evidence_targets": list(self.evidence_targets),
            "covered_sources": list(self.covered_sources),
            "delegated_sources": list(self.delegated_sources),
            "excluded_sources": list(self.excluded_sources),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.unsigned_dict(),
            "readiness_sha256": self.readiness_sha256,
        }


@dataclass(frozen=True)
class MigrationReceipt:
    phase: str
    workspace_manifest_sha256: str
    plan_sha256: str
    completed_phases: tuple[str, ...]
    prior_receipt_sha256s: tuple[str, ...]
    items: tuple[MigrationPhaseItem, ...]
    canonical_root_bindings: tuple[CanonicalRootBinding, ...]
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
            "canonical_root_bindings": [
                binding.as_dict() for binding in self.canonical_root_bindings
            ],
            "source_deleted": False,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "receipt_sha256": self.receipt_sha256}


@dataclass(frozen=True)
class RetirementSourceEvidence:
    source: str
    target: str
    fingerprint: ArtifactFingerprint
    final_item_sha256: str
    provenance_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "fingerprint": self.fingerprint.as_dict(),
            "final_item_sha256": self.final_item_sha256,
            "provenance_sha256": self.provenance_sha256,
        }


def _retirement_source_sort_key(
    source: RetirementSourceEvidence,
) -> tuple[str, str, bytes]:
    return source.target, source.source, _canonical_json_bytes(source.as_dict())


@dataclass(frozen=True)
class RetirementReceipt:
    retirement_id: str
    workspace_manifest_sha256: str
    activation_receipt_path: str
    activation_receipt_sha256: str
    activation_id: str
    validation_receipt_path: str
    validation_receipt_sha256: str
    validation_record_sha256: str
    plan_sha256: str
    sources: tuple[RetirementSourceEvidence, ...]
    receipt_sha256: str
    schema_version: str = RETIREMENT_RECEIPT_SCHEMA
    status: str = "authorized"

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "retirement_id": self.retirement_id,
            "workspace_manifest_sha256": self.workspace_manifest_sha256,
            "activation_receipt_path": self.activation_receipt_path,
            "activation_receipt_sha256": self.activation_receipt_sha256,
            "activation_id": self.activation_id,
            "validation_receipt_path": self.validation_receipt_path,
            "validation_receipt_sha256": self.validation_receipt_sha256,
            "validation_record_sha256": self.validation_record_sha256,
            "plan_sha256": self.plan_sha256,
            "sources": [
                source.as_dict()
                for source in sorted(
                    self.sources,
                    key=_retirement_source_sort_key,
                )
            ],
            "source_deletion_performed": False,
            "source_absence_authorized": True,
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
        and not isinstance(fingerprint.bytes, bool)
        and fingerprint.bytes >= 0
        and isinstance(fingerprint.file_count, int)
        and not isinstance(fingerprint.file_count, bool)
        and fingerprint.file_count >= 0
        and isinstance(fingerprint.directory_count, int)
        and not isinstance(fingerprint.directory_count, bool)
        and fingerprint.directory_count >= 0
        and isinstance(fingerprint.content_sha256, str)
        and bool(_SHA256.fullmatch(fingerprint.content_sha256))
        and isinstance(fingerprint.merkle_sha256, str)
        and bool(_SHA256.fullmatch(fingerprint.merkle_sha256))
        and (
            (
                fingerprint.file_count == 1
                and fingerprint.directory_count == 0
            )
            if fingerprint.kind == "file"
            else fingerprint.directory_count >= 1
        )
    )


def _fingerprint_from_mapping(
    value: object, *, field: str
) -> ArtifactFingerprint:
    expected_fields = {
        "kind",
        "mode",
        "bytes",
        "content_sha256",
        "merkle_sha256",
        "file_count",
        "directory_count",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise LayoutError(f"{field} must contain the exact fingerprint fields")
    fingerprint = ArtifactFingerprint(
        kind=value.get("kind"),
        mode=value.get("mode"),
        bytes=value.get("bytes"),
        content_sha256=value.get("content_sha256"),
        merkle_sha256=value.get("merkle_sha256"),
        file_count=value.get("file_count"),
        directory_count=value.get("directory_count"),
    )
    if not _validate_fingerprint(fingerprint):
        raise LayoutError(f"{field} is invalid")
    return fingerprint


def _canonical_root_readiness_hash(
    workspace_manifest_sha256: str,
    unsigned_binding: Mapping[str, Any],
) -> str:
    return _canonical_sha256(
        {
            "workspace_manifest_sha256": workspace_manifest_sha256,
            "binding": dict(unsigned_binding),
        }
    )


def _is_strict_path_descendant(path: str, parent: str) -> bool:
    child_path = PurePosixPath(path)
    parent_path = PurePosixPath(parent)
    try:
        child_path.relative_to(parent_path)
    except ValueError:
        return False
    return child_path != parent_path


def _canonical_root_binding_from_mapping(
    value: object,
    *,
    workspace_manifest_sha256: str,
    field: str,
) -> CanonicalRootBinding:
    expected_fields = {
        "schema_version",
        "root_id",
        "canonical_path",
        "root_state",
        "completion_kind",
        "expected_kind",
        "evidence_targets",
        "covered_sources",
        "delegated_sources",
        "excluded_sources",
        "readiness_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise LayoutError(f"{field} must contain the exact root binding fields")
    root_id = value.get("root_id")
    if not isinstance(root_id, str) or not re.fullmatch(
        r"[a-z][a-z0-9_]*", root_id
    ):
        raise LayoutError(f"{field}.root_id is invalid")
    canonical_path = _migration_relative_path(
        value.get("canonical_path"), field=f"{field}.canonical_path"
    )
    root_state = value.get("root_state")
    if not isinstance(root_state, str) or root_state not in {"active", "bridge"}:
        raise LayoutError(f"{field}.root_state is invalid")
    completion_kind = value.get("completion_kind")
    if not isinstance(completion_kind, str) or completion_kind not in {
        "migrated-legacy-root",
        "migrated-legacy-partition",
        "already-canonical",
    }:
        raise LayoutError(f"{field}.completion_kind is invalid")
    raw_evidence_targets = value.get("evidence_targets")
    if not isinstance(raw_evidence_targets, list):
        raise LayoutError(f"{field}.evidence_targets must be a list")
    evidence_targets = tuple(
        _migration_relative_path(
            target,
            field=f"{field}.evidence_targets[{position}]",
        )
        for position, target in enumerate(raw_evidence_targets)
    )
    if evidence_targets != tuple(sorted(set(evidence_targets))):
        raise LayoutError(f"{field}.evidence_targets must be unique and sorted")

    def source_list(name: str) -> tuple[str, ...]:
        raw = value.get(name)
        if not isinstance(raw, list):
            raise LayoutError(f"{field}.{name} must be a list")
        parsed = tuple(
            _migration_relative_path(
                source,
                field=f"{field}.{name}[{position}]",
            )
            for position, source in enumerate(raw)
        )
        if parsed != tuple(sorted(set(parsed))):
            raise LayoutError(f"{field}.{name} must be unique and sorted")
        return parsed

    binding = CanonicalRootBinding(
        root_id=root_id,
        canonical_path=canonical_path,
        root_state=root_state,
        completion_kind=completion_kind,
        expected_kind=value.get("expected_kind"),
        evidence_targets=evidence_targets,
        covered_sources=source_list("covered_sources"),
        delegated_sources=source_list("delegated_sources"),
        excluded_sources=source_list("excluded_sources"),
        readiness_sha256=_sha256_value(
            value.get("readiness_sha256"),
            field=f"{field}.readiness_sha256",
        ),
    )
    if binding.expected_kind != "directory":
        raise LayoutError(f"{field}.expected_kind must be 'directory'")
    if value.get("schema_version") != CANONICAL_ROOT_BINDING_SCHEMA:
        raise LayoutError(f"{field}.schema_version is invalid")
    expected_hash = _canonical_root_readiness_hash(
        workspace_manifest_sha256,
        binding.unsigned_dict(),
    )
    if (
        not _SHA256.fullmatch(binding.readiness_sha256)
        or binding.readiness_sha256 != expected_hash
    ):
        raise LayoutError(f"{field}.readiness_sha256 is invalid")
    return binding


def _canonical_root_directory(
    layout: WorkspaceLayout,
    *,
    root_id: str,
    canonical_path: str,
) -> Path:
    relative, path = _checked_workspace_path(
        layout.root,
        canonical_path,
        field=f"canonical root {root_id!r}",
        require_leaf=True,
    )
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise LayoutError(
            f"canonical root {root_id!r} is not a no-follow directory: {relative}"
        )
    # A canonical root is a long-lived container, and some roots (notably
    # 90_RUNTIME) intentionally hold mutable files and test-created symlinks.
    # Deep no-follow verification belongs to each immutable publication target;
    # recursively scanning the container on every path lookup both rejected
    # valid runtime state and made a RAG request proportional to the whole repo.
    markers = tuple(
        marker
        for marker in (_publication_sidecar(path), path / PUBLICATION_INCOMPLETE_MARKER)
        if _path_exists(marker)
    )
    if markers:
        rendered = ", ".join(str(marker) for marker in markers)
        raise LayoutError(
            f"canonical root {root_id!r} is an incomplete publication: {rendered}"
        )
    return path


_GENERATED_MIGRATION_EXCLUSION_NAMES = frozenset({
    ".git",
    ".next",
    ".vinext",
    ".wrangler",
    "__pycache__",
    "dist",
    "node_modules",
})


def _direct_legacy_children(layout: WorkspaceLayout, legacy_path: str) -> tuple[str, ...]:
    _relative, directory = _checked_workspace_path(
        layout.root,
        legacy_path,
        field=f"legacy root {legacy_path!r}",
        require_leaf=True,
    )
    info = directory.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise LayoutError(f"legacy root is not a no-follow directory: {legacy_path}")
    return tuple(
        sorted(
            f"{legacy_path}/{entry.name}"
            for entry in os.scandir(directory)
            if not _is_reserved_publication_name(entry.name)
        )
    )


def _direct_nested_legacy_roots(
    layout: WorkspaceLayout,
    *,
    root_id: str,
    legacy_path: str,
) -> tuple[str, ...]:
    parent = PurePosixPath(legacy_path)
    nested: list[str] = []
    for other_id, other in layout.roots.items():
        if other_id == root_id or not other.legacy_path:
            continue
        candidate = PurePosixPath(other.legacy_path)
        try:
            remainder = candidate.relative_to(parent)
        except ValueError:
            continue
        if len(remainder.parts) == 1:
            nested.append(other.legacy_path)
    return tuple(sorted(nested))


def _normalized_partition_exclusions(
    layout: WorkspaceLayout,
    *,
    root_id: str,
    legacy_path: str,
    values: Iterable[str],
) -> tuple[str, ...]:
    exclusions = tuple(
        sorted(
            {
                _migration_relative_path(
                    value,
                    field=f"excluded_legacy_sources.{root_id}",
                )
                for value in values
            }
        )
    )
    legacy = PurePosixPath(legacy_path)
    for value in exclusions:
        path = PurePosixPath(value)
        try:
            remainder = path.relative_to(legacy)
        except ValueError as exc:
            raise LayoutError(
                f"partition exclusion is outside legacy root {root_id!r}: {value}"
            ) from exc
        if (
            len(remainder.parts) != 1
            or remainder.name not in _GENERATED_MIGRATION_EXCLUSION_NAMES
        ):
            raise LayoutError(
                f"partition exclusion is not an approved generated entry: {value}"
            )
        _relative, exclusion_path = _checked_workspace_path(
            layout.root,
            value,
            field=f"excluded legacy source {root_id!r}",
            require_leaf=True,
        )
        exclusion_info = exclusion_path.lstat()
        if stat.S_ISLNK(exclusion_info.st_mode) or not stat.S_ISDIR(
            exclusion_info.st_mode
        ):
            raise LayoutError(
                "partition exclusion must be a no-follow generated directory: "
                f"{value}"
            )
    return exclusions


def _root_binding_components(
    layout: WorkspaceLayout,
    *,
    root_id: str,
    pairs: Iterable[tuple[str, str]],
    excluded_sources: Iterable[str],
) -> tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    spec = layout.roots[root_id]
    pair_rows = tuple(pairs)
    if spec.state == "active":
        if spec.legacy_path is not None:
            raise LayoutError(
                f"active root {root_id!r} must not retain legacy_path"
            )
        if tuple(excluded_sources):
            raise LayoutError(
                f"active root {root_id!r} cannot exclude legacy sources"
            )
        return (
            "already-canonical",
            (spec.canonical_path,),
            (),
            (),
            (),
        )
    if spec.state != "bridge" or not spec.legacy_path:
        raise LayoutError(
            f"root {root_id!r} in state {spec.state!r} cannot be activated"
        )

    targeted = tuple(
        (source, target)
        for source, target in pair_rows
        if _is_strict_path_descendant(target, spec.canonical_path)
    )
    whole = tuple((source, target) for source, target in targeted
                  if source == spec.legacy_path)
    if whole:
        if len(whole) != 1:
            raise LayoutError(
                f"bridge root {root_id!r} has duplicate whole-root evidence"
            )
        if tuple(excluded_sources):
            raise LayoutError(
                f"whole-root migration {root_id!r} cannot declare exclusions"
            )
        source, target = whole[0]
        return (
            "migrated-legacy-root",
            (target,),
            (source,),
            (),
            (),
        )

    excluded = _normalized_partition_exclusions(
        layout,
        root_id=root_id,
        legacy_path=spec.legacy_path,
        values=excluded_sources,
    )
    delegated = _direct_nested_legacy_roots(
        layout,
        root_id=root_id,
        legacy_path=spec.legacy_path,
    )
    direct_children = set(_direct_legacy_children(layout, spec.legacy_path))
    covered_rows = tuple(
        (source, target)
        for source, target in targeted
        if PurePosixPath(source).parent == PurePosixPath(spec.legacy_path)
    )
    covered = tuple(sorted(source for source, _target in covered_rows))
    required = direct_children - set(delegated) - set(excluded)
    if set(covered) != required:
        missing = sorted(required - set(covered))
        unexpected = sorted(set(covered) - required)
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if unexpected:
            detail.append("unexpected=" + ",".join(unexpected))
        raise LayoutError(
            f"bridge root {root_id!r} partition is incomplete: " + "; ".join(detail)
        )
    targets_by_source = {source: target for source, target in covered_rows}
    evidence = tuple(sorted(targets_by_source[source] for source in covered))
    if not evidence:
        raise LayoutError(f"bridge root {root_id!r} has no migration evidence")
    return (
        "migrated-legacy-partition",
        evidence,
        covered,
        delegated,
        excluded,
    )


def _build_canonical_root_bindings(
    layout: WorkspaceLayout,
    final_items: tuple[MigrationPhaseItem, ...],
    *,
    already_canonical_root_ids: Iterable[str],
    excluded_legacy_sources: Mapping[str, Iterable[str]],
) -> tuple[CanonicalRootBinding, ...]:
    explicit_ids = tuple(already_canonical_root_ids)
    if len(explicit_ids) != len(set(explicit_ids)):
        raise LayoutError("already-canonical root policy contains duplicate root IDs")
    explicit = frozenset(explicit_ids)
    unknown = sorted(explicit - set(layout.roots))
    if unknown:
        raise LayoutError(
            "already-canonical root policy names unknown roots: " + ", ".join(unknown)
        )
    exclusion_ids = set(excluded_legacy_sources)
    unknown_exclusions = sorted(exclusion_ids - set(layout.roots))
    if unknown_exclusions:
        raise LayoutError(
            "partition exclusions name unknown roots: " + ", ".join(unknown_exclusions)
        )
    pairs = tuple((item.source, item.target) for item in final_items)
    bindings: list[CanonicalRootBinding] = []
    for root_id in sorted(layout.roots):
        spec = layout.roots[root_id]
        _canonical_root_directory(
            layout,
            root_id=root_id,
            canonical_path=spec.canonical_path,
        )
        if spec.state == "bridge" and root_id in explicit:
            raise LayoutError(
                f"bridge root {root_id!r} cannot use already-canonical policy"
            )
        if spec.state == "active" and root_id not in explicit:
            raise LayoutError(
                f"active root {root_id!r} requires explicit already-canonical policy"
            )
        (
            completion_kind,
            evidence_targets,
            covered_sources,
            delegated_sources,
            excluded_sources,
        ) = _root_binding_components(
            layout,
            root_id=root_id,
            pairs=pairs,
            excluded_sources=excluded_legacy_sources.get(root_id, ()),
        )
        provisional = CanonicalRootBinding(
            root_id=root_id,
            canonical_path=spec.canonical_path,
            root_state=spec.state,
            completion_kind=completion_kind,
            expected_kind="directory",
            evidence_targets=evidence_targets,
            covered_sources=covered_sources,
            delegated_sources=delegated_sources,
            excluded_sources=excluded_sources,
            readiness_sha256="",
        )
        bindings.append(
            CanonicalRootBinding(
                root_id=provisional.root_id,
                canonical_path=provisional.canonical_path,
                root_state=provisional.root_state,
                completion_kind=provisional.completion_kind,
                expected_kind=provisional.expected_kind,
                evidence_targets=provisional.evidence_targets,
                covered_sources=provisional.covered_sources,
                delegated_sources=provisional.delegated_sources,
                excluded_sources=provisional.excluded_sources,
                readiness_sha256=_canonical_root_readiness_hash(
                    layout.manifest_sha256,
                    provisional.unsigned_dict(),
                ),
            )
        )
    return tuple(bindings)


def _validate_live_canonical_root_bindings(
    layout: WorkspaceLayout,
    value: object,
    final_items: object,
) -> None:
    if not isinstance(value, list):
        raise LayoutError("canonical_root_bindings must be a list")
    expected_ids = sorted(layout.roots)
    if len(value) != len(expected_ids):
        raise LayoutError("canonical_root_bindings do not exactly cover workspace roots")
    if not isinstance(final_items, list):
        raise LayoutError("final migration receipt items must be a list")
    final_pairs: list[tuple[str, str]] = []
    for position, row in enumerate(final_items):
        if not isinstance(row, Mapping):
            raise LayoutError(f"items[{position}] must be an object")
        final_pairs.append(
            (
                _migration_relative_path(
                    row.get("source"), field=f"items[{position}].source"
                ),
                _migration_relative_path(
                    row.get("target"), field=f"items[{position}].target"
                ),
            )
        )
    observed_ids: list[str] = []
    for position, row in enumerate(value):
        binding = _canonical_root_binding_from_mapping(
            row,
            workspace_manifest_sha256=layout.manifest_sha256,
            field=f"canonical_root_bindings[{position}]",
        )
        observed_ids.append(binding.root_id)
        spec = layout.roots.get(binding.root_id)
        if (
            spec is None
            or binding.canonical_path != spec.canonical_path
            or binding.root_state != spec.state
        ):
            raise LayoutError(
                f"canonical root binding does not match manifest: {binding.root_id!r}"
            )
        expected = _root_binding_components(
            layout,
            root_id=binding.root_id,
            pairs=final_pairs,
            excluded_sources=binding.excluded_sources,
        )
        observed = (
            binding.completion_kind,
            binding.evidence_targets,
            binding.covered_sources,
            binding.delegated_sources,
            binding.excluded_sources,
        )
        if observed != expected:
            raise LayoutError(
                f"canonical root binding has invalid migration evidence: "
                f"{binding.root_id!r}"
            )
        _canonical_root_directory(
            layout,
            root_id=binding.root_id,
            canonical_path=binding.canonical_path,
        )
    if observed_ids != expected_ids:
        raise LayoutError(
            "canonical_root_bindings must be unique and sorted by root_id"
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
        assert_publication_ready(
            source_path,
            field=f"migration source {source!r}",
            boundary=layout.root,
        )
        assert_publication_ready(
            target_path,
            field=f"migration target {target!r}",
            boundary=layout.root,
        )
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


def _atomic_publish_no_replace(staging: Path, target: Path) -> str:
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
    staging_info = staging.lstat()
    if not stat.S_ISREG(staging_info.st_mode) and not stat.S_ISDIR(
        staging_info.st_mode
    ):
        raise LayoutError("publication supports only regular files/directories")
    if _is_reserved_publication_name(staging.name):
        raise LayoutError("reserved publication marker cannot be published")
    sidecar = _publication_sidecar(target)
    if _path_exists(sidecar):
        raise LayoutError(f"publication target has an incomplete marker: {sidecar}")
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
            _fsync_directory(target.parent)
            return "renameat2"
        error_number = ctypes.get_errno()
        if error_number == errno.EEXIST:
            raise FileExistsError(error_number, os.strerror(error_number), target)
        if error_number not in unsupported:
            raise LayoutError(
                f"atomic migration publish failed: {os.strerror(error_number)}"
            )

    if stat.S_ISREG(staging_info.st_mode):
        try:
            os.link(staging, target, follow_symlinks=False)
        except FileExistsError:
            raise
        except OSError as exc:
            raise LayoutError(f"hard-link publication failed: {exc}") from exc
        staging.unlink()
        _fsync_directory(target.parent)
        return "hardlink"

    # Reserve a sibling name *before* creating the visible target directory.
    # Consumers check both this marker and the in-directory marker, closing the
    # mkdir-before-marker crash window present in the legacy WSL fallback.
    sidecar_descriptor: int | None = None
    try:
        sidecar_descriptor = os.open(
            sidecar,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.write(sidecar_descriptor, b"workspace-copy-v2\n")
        os.fsync(sidecar_descriptor)
    except FileExistsError as exc:
        raise LayoutError(f"publication target is already reserved: {sidecar}") from exc
    finally:
        if sidecar_descriptor is not None:
            os.close(sidecar_descriptor)
    _fsync_directory(target.parent)
    try:
        target.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise LayoutError(
            f"reserved migration target appeared concurrently and is retained: {target}"
        ) from exc
    marker = target / PUBLICATION_INCOMPLETE_MARKER
    marker_descriptor = os.open(
        marker,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.write(marker_descriptor, b"workspace-copy-v2\n")
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
        sidecar.unlink()
        _fsync_directory(target.parent)
        staging.rmdir()
        return "reserved-directory"
    except Exception as exc:
        raise LayoutError(
            "reserved migration target is incomplete and retained with its "
            f"readiness marker: {target}: {exc}"
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
) -> tuple[str, ArtifactFingerprint, str]:
    _source, source_path = _checked_workspace_path(
        layout.root, item.source, field="migration source", require_leaf=True
    )
    _target, target_path = _checked_workspace_path(
        layout.root, item.target, field="migration target", require_leaf=False
    )
    assert_publication_ready(
        source_path,
        field=f"migration source {item.source!r}",
        boundary=layout.root,
    )
    assert_publication_ready(
        target_path,
        field=f"migration target {item.target!r}",
        boundary=layout.root,
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
        return "already-present", current, "already-present"

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
            publish_strategy = _atomic_publish_no_replace(staging, target_path)
            published = True
            status = "published"
        except FileExistsError:
            assert_publication_ready(
                target_path,
                field=f"migration target {item.target!r}",
                boundary=layout.root,
            )
            existing = _fingerprint_path(target_path)
            if existing != item.fingerprint:
                raise LayoutError(
                    f"migration target appeared with different bytes: {item.target}"
                )
            status = "already-present-race"
            publish_strategy = "already-present"
        _fsync_directory(parent)
        assert_publication_ready(
            target_path,
            field=f"migration target {item.target!r}",
            boundary=layout.root,
        )
        final_fingerprint = _fingerprint_path(target_path)
        if final_fingerprint != item.fingerprint:
            raise LayoutError(f"published migration target failed verification: {item.target}")
        return status, final_fingerprint, publish_strategy
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
    canonical_root_bindings: tuple[CanonicalRootBinding, ...],
) -> str:
    provisional = MigrationReceipt(
        phase=phase,
        workspace_manifest_sha256=plan.workspace_manifest_sha256,
        plan_sha256=plan.plan_sha256,
        completed_phases=completed_phases,
        prior_receipt_sha256s=prior_receipt_sha256s,
        items=items,
        canonical_root_bindings=canonical_root_bindings,
        receipt_sha256="",
    )
    return _canonical_sha256(provisional.unsigned_dict())


def _make_receipt(
    plan: MigrationPlan,
    *,
    phase: str,
    previous: MigrationReceipt | None,
    items: tuple[MigrationPhaseItem, ...],
    canonical_root_bindings: tuple[CanonicalRootBinding, ...] = (),
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
        if len(items) != len(previous.items) or any(
            current.publish_strategy != prior.publish_strategy
            for current, prior in zip(items, previous.items)
        ):
            raise LayoutError("migration publish strategy changed between phases")
        prior_hashes = (
            *previous.prior_receipt_sha256s,
            previous.receipt_sha256,
        )
    if phase == "final-verify":
        if not canonical_root_bindings:
            raise LayoutError("final-verify requires canonical root readiness bindings")
    elif canonical_root_bindings:
        raise LayoutError("canonical root bindings are allowed only on final-verify")
    completed = MIGRATION_SEQUENCE[: phase_index + 1]
    digest = _receipt_hash(
        phase=phase,
        plan=plan,
        completed_phases=completed,
        prior_receipt_sha256s=prior_hashes,
        items=items,
        canonical_root_bindings=canonical_root_bindings,
    )
    return MigrationReceipt(
        phase=phase,
        workspace_manifest_sha256=plan.workspace_manifest_sha256,
        plan_sha256=plan.plan_sha256,
        completed_phases=completed,
        prior_receipt_sha256s=prior_hashes,
        items=items,
        canonical_root_bindings=canonical_root_bindings,
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
                or row.publish_strategy not in _PUBLISH_STRATEGIES
            ):
                errors.append(f"items[{position}]")
            if expected_phase == "copy-verify-0" and (
                (row.status == "published" and row.publish_strategy == "already-present")
                or (
                    row.status in {"already-present", "already-present-race"}
                    and row.publish_strategy != "already-present"
                )
            ):
                errors.append(f"items[{position}].publish_strategy")
    if expected_phase == "final-verify":
        binding_ids: list[str] = []
        if not receipt.canonical_root_bindings:
            errors.append("canonical_root_bindings")
        for position, binding in enumerate(receipt.canonical_root_bindings):
            try:
                parsed = _canonical_root_binding_from_mapping(
                    binding.as_dict(),
                    workspace_manifest_sha256=plan.workspace_manifest_sha256,
                    field=f"canonical_root_bindings[{position}]",
                )
            except (AttributeError, LayoutError):
                errors.append(f"canonical_root_bindings[{position}]")
                continue
            binding_ids.append(parsed.root_id)
        if binding_ids != sorted(set(binding_ids)):
            errors.append("canonical_root_binding_order")
    elif receipt.canonical_root_bindings:
        errors.append("canonical_root_bindings")
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
        status, fingerprint, publish_strategy = _publish_copy(layout, item)
        rows.append(
            MigrationPhaseItem(
                source=item.source,
                target=item.target,
                status=status,
                fingerprint=fingerprint,
                publish_strategy=publish_strategy,
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
    previous_items: tuple[MigrationPhaseItem, ...],
) -> tuple[MigrationPhaseItem, ...]:
    rows: list[MigrationPhaseItem] = []
    if len(previous_items) != len(plan.items):
        raise LayoutError("previous migration receipt item count does not match plan")
    for item, previous_item in zip(plan.items, previous_items, strict=True):
        _source, source_path = _checked_workspace_path(
            layout.root, item.source, field="migration source", require_leaf=True
        )
        _target, target_path = _checked_workspace_path(
            layout.root, item.target, field="migration target", require_leaf=True
        )
        assert_publication_ready(
            source_path,
            field=f"migration source {item.source!r}",
            boundary=layout.root,
        )
        assert_publication_ready(
            target_path,
            field=f"migration target {item.target!r}",
            boundary=layout.root,
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
                publish_strategy=previous_item.publish_strategy,
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
        items=_compare_plan_paths(
            layout,
            plan,
            status="matched",
            previous_items=copy_receipt.items,
        ),
    )


def verify_final_migration(
    layout: WorkspaceLayout,
    plan: MigrationPlan,
    dual_read_receipt: MigrationReceipt,
    *,
    already_canonical_root_ids: Iterable[str] = (),
    excluded_legacy_sources: Mapping[str, Iterable[str]] | None = None,
) -> MigrationReceipt:
    """Issue the final validation receipt without deleting any legacy source."""

    _validate_plan_integrity(plan, layout)
    _validate_receipt_integrity(
        dual_read_receipt, plan, expected_phase="dual-read-compare"
    )
    final_items = _compare_plan_paths(
        layout,
        plan,
        status="verified",
        previous_items=dual_read_receipt.items,
    )
    return _make_receipt(
        plan,
        phase="final-verify",
        previous=dual_read_receipt,
        items=final_items,
        canonical_root_bindings=_build_canonical_root_bindings(
            layout,
            final_items,
            already_canonical_root_ids=already_canonical_root_ids,
            excluded_legacy_sources=excluded_legacy_sources or {},
        ),
    )


def _validate_serialized_receipt(receipt: Mapping[str, Any]) -> None:
    unsigned = dict(receipt)
    recorded_hash = unsigned.pop("receipt_sha256", None)
    errors: list[str] = []
    if set(receipt) != {
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
    }:
        errors.append("fields")
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
    if not _is_sha256(receipt.get("workspace_manifest_sha256")):
        errors.append("workspace_manifest_sha256")
    if not _is_sha256(receipt.get("plan_sha256")):
        errors.append("plan_sha256")
    if not _is_sha256(recorded_hash) or recorded_hash != _canonical_sha256(
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
            if set(item) != {
                "source",
                "target",
                "status",
                "publish_strategy",
                "fingerprint",
            }:
                errors.append(f"items[{position}].fields")
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
            if item.get("publish_strategy") not in _PUBLISH_STRATEGIES:
                errors.append(f"items[{position}].publish_strategy")
            try:
                _fingerprint_from_mapping(
                    item.get("fingerprint"),
                    field=f"items[{position}].fingerprint",
                )
            except LayoutError:
                errors.append(f"items[{position}].fingerprint")
        try:
            _validate_pair_boundaries(safe_pairs)
        except LayoutError:
            errors.append("item_boundaries")
    bindings = receipt.get("canonical_root_bindings")
    if not isinstance(bindings, list) or not bindings:
        errors.append("canonical_root_bindings")
    else:
        binding_ids: list[str] = []
        manifest_value = receipt.get("workspace_manifest_sha256")
        manifest_sha256 = manifest_value if isinstance(manifest_value, str) else ""
        for position, row in enumerate(bindings):
            try:
                binding = _canonical_root_binding_from_mapping(
                    row,
                    workspace_manifest_sha256=manifest_sha256,
                    field=f"canonical_root_bindings[{position}]",
                )
            except LayoutError:
                errors.append(f"canonical_root_bindings[{position}]")
                continue
            binding_ids.append(binding.root_id)
        if binding_ids != sorted(set(binding_ids)):
            errors.append("canonical_root_binding_order")
    if errors:
        raise LayoutError(
            "invalid final migration validation receipt: " + ", ".join(errors)
        )


def _validate_live_receipt_items(
    layout: WorkspaceLayout,
    receipt: Mapping[str, Any],
    *,
    verify_sources: bool = True,
) -> None:
    """Bind activation to the live bytes, not only to a historical receipt."""

    rows = receipt.get("items")
    if not isinstance(rows, list):
        raise LayoutError("final migration validation receipt has no live items")
    for position, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise LayoutError(f"final migration item {position} is not an object")
        expected = _fingerprint_from_mapping(
            row.get("fingerprint"), field=f"items[{position}].fingerprint"
        )
        coordinates = ("source", "target") if verify_sources else ("target",)
        for coordinate in coordinates:
            relative, path = _checked_workspace_path(
                layout.root,
                row.get(coordinate),
                field=f"items[{position}].{coordinate}",
                require_leaf=True,
            )
            assert_publication_ready(
                path,
                field=f"final migration {coordinate} {relative!r}",
                boundary=layout.root,
            )
            if _fingerprint_path(path) != expected:
                raise LayoutError(
                    f"final migration {coordinate} no longer matches receipt: {relative}"
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


def _read_environment_activation(
    layout: WorkspaceLayout,
) -> tuple[Path, bytes, Mapping[str, Any]]:
    receipt_value = (
        os.environ.get(ACTIVATION_RECEIPT_ENV, "").strip()
        or (layout.activation_receipt or "")
    )
    if not receipt_value:
        raise LayoutError(
            f"v2 environment activation requires {ACTIVATION_RECEIPT_ENV}"
        )
    receipt_path = Path(receipt_value).expanduser()
    if not receipt_path.is_absolute():
        receipt_path = layout.root / receipt_path
    try:
        assert_publication_ready(receipt_path, field="layout activation receipt")
        receipt_raw = _stable_regular_bytes(receipt_path)
        receipt = json.loads(receipt_raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LayoutError(f"cannot read layout activation receipt: {exc}") from exc
    if not isinstance(receipt, Mapping):
        raise LayoutError("layout activation receipt must be an object")
    return receipt_path, receipt_raw, receipt


def _validate_activation_receipt_fields(
    layout: WorkspaceLayout,
    receipt: Mapping[str, Any],
) -> None:
    errors: list[str] = []
    if set(receipt) != {
        "schema_version",
        "status",
        "layout_version",
        "workspace_manifest_sha256",
        "validation_receipt_path",
        "validation_receipt_sha256",
        "validation_record_sha256",
        "migration_plan_sha256",
        "activation_id",
    }:
        errors.append("fields")
    if receipt.get("schema_version") != ACTIVATION_RECEIPT_SCHEMA:
        errors.append("schema_version")
    if receipt.get("status") != "active":
        errors.append("status")
    if receipt.get("layout_version") != "v2":
        errors.append("layout_version")
    if receipt.get("workspace_manifest_sha256") != layout.manifest_sha256:
        errors.append("workspace_manifest_sha256")
    if not _is_sha256(receipt.get("validation_receipt_sha256")):
        errors.append("validation_receipt_sha256")
    if not _is_sha256(receipt.get("validation_record_sha256")):
        errors.append("validation_record_sha256")
    if not _is_sha256(receipt.get("migration_plan_sha256")):
        errors.append("migration_plan_sha256")
    try:
        _migration_relative_path(
            receipt.get("validation_receipt_path"),
            field="validation_receipt_path",
        )
    except LayoutError:
        errors.append("validation_receipt_path")
    activation_id = receipt.get("activation_id")
    if (
        not isinstance(activation_id, str)
        or not _CANONICAL_TEXT.fullmatch(activation_id)
    ):
        errors.append("activation_id")
    if errors:
        raise LayoutError(
            "invalid layout activation receipt fields: " + ", ".join(errors)
        )


def _workspace_record_path(
    layout: WorkspaceLayout,
    value: str | Path,
    *,
    field: str,
) -> tuple[str, Path]:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = layout.root / candidate
    absolute = Path(os.path.abspath(os.fspath(candidate)))
    workspace_root = layout.root.resolve()
    try:
        relative_value = absolute.relative_to(workspace_root).as_posix()
    except ValueError as exc:
        raise LayoutError(f"{field} must be inside the workspace") from exc
    return _checked_workspace_path(
        workspace_root,
        relative_value,
        field=field,
        require_leaf=True,
    )


def _read_json_record(
    layout: WorkspaceLayout,
    value: str | Path,
    *,
    field: str,
) -> tuple[str, Path, bytes, Mapping[str, Any]]:
    relative, path = _workspace_record_path(layout, value, field=field)
    try:
        assert_publication_ready(
            path,
            field=f"{field} {relative!r}",
            boundary=layout.root,
        )
        raw = _stable_regular_bytes(path)
        document = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LayoutError(f"cannot read {field} {relative}: {exc}") from exc
    if not isinstance(document, Mapping):
        raise LayoutError(f"{field} must be an object")
    return relative, path, raw, document


def _retirement_source_provenance_sha256(
    *,
    workspace_manifest_sha256: str,
    activation_receipt_sha256: str,
    activation_id: str,
    validation_receipt_sha256: str,
    validation_record_sha256: str,
    plan_sha256: str,
    source: str,
    target: str,
    fingerprint: ArtifactFingerprint,
    final_item_sha256: str,
) -> str:
    return _canonical_sha256(
        {
            "schema_version": RETIREMENT_SOURCE_EVIDENCE_SCHEMA,
            "workspace_manifest_sha256": workspace_manifest_sha256,
            "activation_receipt_sha256": activation_receipt_sha256,
            "activation_id": activation_id,
            "validation_receipt_sha256": validation_receipt_sha256,
            "validation_record_sha256": validation_record_sha256,
            "plan_sha256": plan_sha256,
            "source": source,
            "target": target,
            "fingerprint": fingerprint.as_dict(),
            "final_item_sha256": final_item_sha256,
        }
    )


def _build_retirement_source_evidence(
    *,
    layout: WorkspaceLayout,
    activation: Mapping[str, Any],
    activation_raw: bytes,
    validation_raw: bytes,
    validation: Mapping[str, Any],
) -> tuple[RetirementSourceEvidence, ...]:
    rows = validation.get("items")
    if not isinstance(rows, list) or not rows:
        raise LayoutError("retirement authorization requires final migration items")
    activation_receipt_sha256 = hashlib.sha256(activation_raw).hexdigest()
    validation_receipt_sha256 = hashlib.sha256(validation_raw).hexdigest()
    evidence: list[RetirementSourceEvidence] = []
    for position, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise LayoutError(f"items[{position}] must be an object")
        source = _migration_relative_path(
            row.get("source"), field=f"items[{position}].source"
        )
        target = _migration_relative_path(
            row.get("target"), field=f"items[{position}].target"
        )
        fingerprint = _fingerprint_from_mapping(
            row.get("fingerprint"), field=f"items[{position}].fingerprint"
        )
        final_item_sha256 = _canonical_sha256(dict(row))
        evidence.append(
            RetirementSourceEvidence(
                source=source,
                target=target,
                fingerprint=fingerprint,
                final_item_sha256=final_item_sha256,
                provenance_sha256=_retirement_source_provenance_sha256(
                    workspace_manifest_sha256=layout.manifest_sha256,
                    activation_receipt_sha256=activation_receipt_sha256,
                    activation_id=str(activation.get("activation_id")),
                    validation_receipt_sha256=validation_receipt_sha256,
                    validation_record_sha256=str(validation.get("receipt_sha256")),
                    plan_sha256=str(validation.get("plan_sha256")),
                    source=source,
                    target=target,
                    fingerprint=fingerprint,
                    final_item_sha256=final_item_sha256,
                ),
            )
        )
    return tuple(sorted(evidence, key=_retirement_source_sort_key))


def _retirement_source_from_mapping(
    value: object,
    *,
    field: str,
) -> RetirementSourceEvidence:
    if not isinstance(value, Mapping) or set(value) != {
        "source",
        "target",
        "fingerprint",
        "final_item_sha256",
        "provenance_sha256",
    }:
        raise LayoutError(f"{field} must contain exact source evidence fields")
    source = _migration_relative_path(value.get("source"), field=f"{field}.source")
    target = _migration_relative_path(value.get("target"), field=f"{field}.target")
    fingerprint = _fingerprint_from_mapping(
        value.get("fingerprint"), field=f"{field}.fingerprint"
    )
    final_item_sha256 = _sha256_value(
        value.get("final_item_sha256"),
        field=f"{field}.final_item_sha256",
    )
    provenance_sha256 = _sha256_value(
        value.get("provenance_sha256"),
        field=f"{field}.provenance_sha256",
    )
    return RetirementSourceEvidence(
        source=source,
        target=target,
        fingerprint=fingerprint,
        final_item_sha256=final_item_sha256,
        provenance_sha256=provenance_sha256,
    )


def _retirement_receipt_from_mapping(value: object) -> RetirementReceipt:
    expected_fields = {
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
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise LayoutError("retirement receipt must contain the exact fields")
    retirement_id = value.get("retirement_id")
    activation_id = value.get("activation_id")
    if (
        not isinstance(retirement_id, str)
        or not _CANONICAL_TEXT.fullmatch(retirement_id)
    ):
        raise LayoutError("retirement receipt retirement_id is invalid")
    if (
        not isinstance(activation_id, str)
        or not _CANONICAL_TEXT.fullmatch(activation_id)
    ):
        raise LayoutError("retirement receipt activation_id is invalid")
    sources_value = value.get("sources")
    if not isinstance(sources_value, list) or not sources_value:
        raise LayoutError("retirement receipt sources must be a non-empty list")
    sources = tuple(
        _retirement_source_from_mapping(row, field=f"sources[{position}]")
        for position, row in enumerate(sources_value)
    )
    canonical_rows = tuple(
        _canonical_json_bytes(source.as_dict()) for source in sources
    )
    if len(canonical_rows) != len(set(canonical_rows)):
        raise LayoutError("retirement receipt sources must be exact-row unique")
    # Source order is not expressible in JSON Schema.  Normalize it before both
    # receipt hashing and semantic comparison, so order carries no authority.
    sources = tuple(sorted(sources, key=_retirement_source_sort_key))
    receipt = RetirementReceipt(
        retirement_id=retirement_id,
        workspace_manifest_sha256=_sha256_value(
            value.get("workspace_manifest_sha256"),
            field="retirement receipt workspace_manifest_sha256",
        ),
        activation_receipt_path=_migration_relative_path(
            value.get("activation_receipt_path"),
            field="activation_receipt_path",
        ),
        activation_receipt_sha256=_sha256_value(
            value.get("activation_receipt_sha256"),
            field="retirement receipt activation_receipt_sha256",
        ),
        activation_id=activation_id,
        validation_receipt_path=_migration_relative_path(
            value.get("validation_receipt_path"),
            field="validation_receipt_path",
        ),
        validation_receipt_sha256=_sha256_value(
            value.get("validation_receipt_sha256"),
            field="retirement receipt validation_receipt_sha256",
        ),
        validation_record_sha256=_sha256_value(
            value.get("validation_record_sha256"),
            field="retirement receipt validation_record_sha256",
        ),
        plan_sha256=_sha256_value(
            value.get("plan_sha256"),
            field="retirement receipt plan_sha256",
        ),
        sources=sources,
        receipt_sha256=_sha256_value(
            value.get("receipt_sha256"),
            field="retirement receipt receipt_sha256",
        ),
        schema_version=value.get("schema_version"),
        status=value.get("status"),
    )
    if receipt.schema_version != RETIREMENT_RECEIPT_SCHEMA:
        raise LayoutError("retirement receipt schema_version is invalid")
    if receipt.status != "authorized":
        raise LayoutError("retirement receipt status is invalid")
    if value.get("source_deletion_performed") is not False:
        raise LayoutError("retirement receipt must not claim source deletion")
    if value.get("source_absence_authorized") is not True:
        raise LayoutError("retirement receipt must authorize source absence")
    if receipt.receipt_sha256 != _canonical_sha256(receipt.unsigned_dict()):
        raise LayoutError("retirement receipt hash is invalid")
    return receipt


def _load_bound_final_receipt(
    layout: WorkspaceLayout,
    activation: Mapping[str, Any],
) -> tuple[str, bytes, Mapping[str, Any]]:
    relative, validation_path = _checked_workspace_path(
        layout.root,
        activation.get("validation_receipt_path"),
        field="validation_receipt_path",
        require_leaf=True,
    )
    try:
        assert_publication_ready(
            validation_path,
            field=f"bound validation receipt {relative!r}",
            boundary=layout.root,
        )
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
    _validate_live_canonical_root_bindings(
        layout,
        validation.get("canonical_root_bindings"),
        validation.get("items"),
    )
    return relative, raw, validation


def _validate_retirement_binding(
    layout: WorkspaceLayout,
    value: object,
    *,
    activation: Mapping[str, Any],
    activation_path: Path,
    activation_raw: bytes,
    validation_relative: str,
    validation_raw: bytes,
    validation: Mapping[str, Any],
) -> RetirementReceipt:
    receipt = _retirement_receipt_from_mapping(value)
    activation_relative, _path = _workspace_record_path(
        layout,
        activation_path,
        field="activation receipt",
    )
    expected_sources = _build_retirement_source_evidence(
        layout=layout,
        activation=activation,
        activation_raw=activation_raw,
        validation_raw=validation_raw,
        validation=validation,
    )
    errors: list[str] = []
    if receipt.workspace_manifest_sha256 != layout.manifest_sha256:
        errors.append("workspace_manifest_sha256")
    if receipt.activation_receipt_path != activation_relative:
        errors.append("activation_receipt_path")
    if receipt.activation_receipt_sha256 != hashlib.sha256(activation_raw).hexdigest():
        errors.append("activation_receipt_sha256")
    if receipt.activation_id != activation.get("activation_id"):
        errors.append("activation_id")
    if receipt.validation_receipt_path != validation_relative:
        errors.append("validation_receipt_path")
    if receipt.validation_receipt_sha256 != hashlib.sha256(validation_raw).hexdigest():
        errors.append("validation_receipt_sha256")
    if receipt.validation_record_sha256 != validation.get("receipt_sha256"):
        errors.append("validation_record_sha256")
    if receipt.plan_sha256 != validation.get("plan_sha256"):
        errors.append("plan_sha256")
    if receipt.sources != expected_sources:
        errors.append("sources")
    if errors:
        raise LayoutError(
            "retirement receipt is not bound to the exact activation and final "
            "migration evidence: " + ", ".join(errors)
        )
    return receipt


def create_legacy_retirement_receipt(
    layout: WorkspaceLayout,
    activation_receipt_path: str | Path,
    *,
    retirement_id: str,
) -> RetirementReceipt:
    """Authorize external retirement after one final source+target verification.

    The returned receipt does not delete or move anything.  Runtime may omit
    source checks only while this exact receipt remains bound to the same
    activation and final-validation bytes; target checks always remain live.
    """

    activation_relative, _activation_path, activation_raw, activation = (
        _read_json_record(
            layout,
            activation_receipt_path,
            field="activation receipt",
        )
    )
    _validate_activation_receipt_fields(layout, activation)
    validation_relative, validation_raw, validation = _load_bound_final_receipt(
        layout,
        activation,
    )
    _validate_live_receipt_items(layout, validation, verify_sources=True)
    if (
        not isinstance(retirement_id, str)
        or not _CANONICAL_TEXT.fullmatch(retirement_id)
    ):
        raise LayoutError("retirement_id must be a non-empty canonical string")
    sources = _build_retirement_source_evidence(
        layout=layout,
        activation=activation,
        activation_raw=activation_raw,
        validation_raw=validation_raw,
        validation=validation,
    )
    provisional = RetirementReceipt(
        retirement_id=retirement_id,
        workspace_manifest_sha256=layout.manifest_sha256,
        activation_receipt_path=activation_relative,
        activation_receipt_sha256=hashlib.sha256(activation_raw).hexdigest(),
        activation_id=str(activation.get("activation_id")),
        validation_receipt_path=validation_relative,
        validation_receipt_sha256=hashlib.sha256(validation_raw).hexdigest(),
        validation_record_sha256=str(validation.get("receipt_sha256")),
        plan_sha256=str(validation.get("plan_sha256")),
        sources=sources,
        receipt_sha256="",
    )
    return RetirementReceipt(
        retirement_id=provisional.retirement_id,
        workspace_manifest_sha256=provisional.workspace_manifest_sha256,
        activation_receipt_path=provisional.activation_receipt_path,
        activation_receipt_sha256=provisional.activation_receipt_sha256,
        activation_id=provisional.activation_id,
        validation_receipt_path=provisional.validation_receipt_path,
        validation_receipt_sha256=provisional.validation_receipt_sha256,
        validation_record_sha256=provisional.validation_record_sha256,
        plan_sha256=provisional.plan_sha256,
        sources=provisional.sources,
        receipt_sha256=_canonical_sha256(provisional.unsigned_dict()),
    )


def _validate_bound_final_receipt(
    layout: WorkspaceLayout,
    activation: Mapping[str, Any],
    *,
    activation_path: Path,
    activation_raw: bytes,
) -> Mapping[str, Any]:
    validation_relative, validation_raw, validation = _load_bound_final_receipt(
        layout,
        activation,
    )
    retirement_value = (
        os.environ.get(RETIREMENT_RECEIPT_ENV, "").strip()
        or (layout.retirement_receipt or "")
    )
    if not retirement_value:
        _validate_live_receipt_items(layout, validation, verify_sources=True)
        return validation
    _retirement_relative, _retirement_path, _retirement_raw, retirement = (
        _read_json_record(
            layout,
            retirement_value,
            field="retirement receipt",
        )
    )
    _validate_retirement_binding(
        layout,
        retirement,
        activation=activation,
        activation_path=activation_path,
        activation_raw=activation_raw,
        validation_relative=validation_relative,
        validation_raw=validation_raw,
        validation=validation,
    )
    _validate_live_receipt_items(layout, validation, verify_sources=False)
    return validation


def persist_immutable_migration_record(
    layout: WorkspaceLayout,
    relative_path: str,
    record: MigrationPlan | MigrationReceipt | RetirementReceipt,
) -> str:
    """Write a migration/lifecycle record once and return its file SHA-256.

    An existing byte-identical record is idempotent; every other collision is
    rejected.  This function never removes or overwrites a source or record.
    """

    if isinstance(record, MigrationPlan):
        _validate_plan_integrity(record, layout)
    elif isinstance(record, MigrationReceipt):
        unsigned = record.unsigned_dict()
        if record.receipt_sha256 != _canonical_sha256(unsigned):
            raise LayoutError("migration receipt hash is invalid")
        if record.schema_version != MIGRATION_RECEIPT_SCHEMA:
            raise LayoutError("migration receipt schema is invalid")
        if record.phase not in MIGRATION_SEQUENCE:
            raise LayoutError("migration receipt phase is invalid")
        if record.workspace_manifest_sha256 != layout.manifest_sha256:
            raise LayoutError("migration receipt workspace manifest does not match")
        if any(
            item.publish_strategy not in _PUBLISH_STRATEGIES for item in record.items
        ):
            raise LayoutError("migration receipt publish strategy is invalid")
        if record.phase == "final-verify":
            serialized = record.as_dict()
            _validate_serialized_receipt(serialized)
            _validate_live_canonical_root_bindings(
                layout,
                serialized.get("canonical_root_bindings"),
                serialized.get("items"),
            )
        elif record.canonical_root_bindings:
            raise LayoutError(
                "canonical root bindings are allowed only on final-verify"
            )
    elif isinstance(record, RetirementReceipt):
        record = _retirement_receipt_from_mapping(record.as_dict())
        if record.workspace_manifest_sha256 != layout.manifest_sha256:
            raise LayoutError("retirement receipt workspace manifest does not match")
    else:
        raise LayoutError(
            "record must be a MigrationPlan, MigrationReceipt, or RetirementReceipt"
        )
    relative, target = _checked_workspace_path(
        layout.root,
        relative_path,
        field="migration record path",
        require_leaf=False,
    )
    raw = _canonical_json_bytes(record.as_dict()) + b"\n"
    digest = hashlib.sha256(raw).hexdigest()
    if _path_exists(target):
        assert_publication_ready(
            target,
            field=f"migration record {relative!r}",
            boundary=layout.root,
        )
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
            assert_publication_ready(
                target,
                field=f"migration record {relative!r}",
                boundary=layout.root,
            )
            if _stable_regular_bytes(target) != raw:
                raise LayoutError(
                    f"immutable migration record raced with different bytes: {relative}"
                )
        _fsync_directory(parent)
        assert_publication_ready(
            target,
            field=f"migration record {relative!r}",
            boundary=layout.root,
        )
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
    lifecycle = blob.get("lifecycle") or {}
    if not isinstance(lifecycle, Mapping):
        raise LayoutError("lifecycle must be an object")
    unexpected_lifecycle = set(lifecycle) - {
        "activation_receipt", "retirement_receipt"
    }
    if unexpected_lifecycle:
        raise LayoutError(
            "lifecycle contains unexpected fields: "
            + ", ".join(sorted(unexpected_lifecycle))
        )
    activation_receipt = _relative_path(
        lifecycle.get("activation_receipt"),
        field="lifecycle.activation_receipt",
        allow_null=True,
    )
    retirement_receipt = _relative_path(
        lifecycle.get("retirement_receipt"),
        field="lifecycle.retirement_receipt",
        allow_null=True,
    )
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
        activation_receipt=activation_receipt,
        retirement_receipt=retirement_receipt,
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
    manifest_sha256 = hashlib.sha256(raw).hexdigest()
    cache_key = (str(workspace.resolve()), manifest_sha256)
    cached = _LAYOUT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    parsed = _parse_manifest(
        blob, workspace, manifest_sha256=manifest_sha256
    )
    for stale_key in tuple(_LAYOUT_CACHE):
        if stale_key[0] == cache_key[0] and stale_key != cache_key:
            _LAYOUT_CACHE.pop(stale_key, None)
    _LAYOUT_CACHE[cache_key] = parsed
    return parsed


def audit_top_level(layout: WorkspaceLayout | None = None) -> dict[str, Any]:
    """Report migration state without pretending bridge paths are already moved."""

    layout = layout or load_layout()
    canonical = {spec.canonical_path for spec in layout.roots.values()}
    actual_dirs: set[str] = set()
    actual_files: set[str] = set()
    unsafe_entries: list[str] = []
    try:
        entries = list(os.scandir(layout.root))
    except OSError as exc:
        raise LayoutError(f"cannot audit workspace root {layout.root}: {exc}") from exc
    for entry in entries:
        if entry.name.startswith("."):
            if _is_reserved_publication_name(entry.name):
                unsafe_entries.append(f"{entry.name}:publication-marker")
            continue
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError as exc:
            unsafe_entries.append(f"{entry.name}:unreadable:{exc}")
            continue
        if stat.S_ISLNK(info.st_mode):
            unsafe_entries.append(f"{entry.name}:symlink")
        elif stat.S_ISDIR(info.st_mode):
            actual_dirs.add(entry.name)
        elif stat.S_ISREG(info.st_mode):
            actual_files.add(entry.name)
        else:
            unsafe_entries.append(f"{entry.name}:special")

    missing_canonical = sorted(canonical - actual_dirs)
    legacy_present = sorted(actual_dirs & set(layout.legacy_top_level_directories))
    unknown_dirs = sorted(actual_dirs - canonical - set(layout.legacy_top_level_directories))
    loose_files = sorted(actual_files - layout.allowed_root_files)
    canonical_readiness_issues: list[str] = []
    for root_id in sorted(layout.roots):
        spec = layout.roots[root_id]
        try:
            _canonical_root_directory(
                layout,
                root_id=root_id,
                canonical_path=spec.canonical_path,
            )
        except (LayoutError, OSError) as exc:
            canonical_readiness_issues.append(f"{root_id}: {exc}")

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
    if unknown_dirs:
        activation_blockers.append("unknown roots remain")
    if loose_files:
        activation_blockers.append("unclassified root files remain")
    if unsafe_entries:
        activation_blockers.append("unsafe top-level entries remain")
    if canonical_readiness_issues:
        activation_blockers.append("canonical roots are not publication-ready")
    retirement_blockers = list(activation_blockers)
    if legacy_present:
        retirement_blockers.append("legacy roots remain")
    activation_ready = not activation_blockers
    retirement_ready = not retirement_blockers
    return {
        "schema_version": "workspace-layout-audit-v2",
        "mode": layout.mode,
        "default_layout_version": layout.default_layout_version,
        "canonical_roots": sorted(canonical),
        "missing_canonical_roots": missing_canonical,
        "legacy_roots_present": legacy_present,
        "unknown_top_level_directories": unknown_dirs,
        "unclassified_root_files": loose_files,
        "unsafe_top_level_entries": sorted(unsafe_entries),
        "canonical_root_readiness_issues": canonical_readiness_issues,
        "activation_blockers": activation_blockers,
        "retirement_blockers": retirement_blockers,
        "activation_ready": activation_ready,
        "retirement_ready": retirement_ready,
        # Backward-compatible alias for the stricter fully-retired end state.
        "target_ready": retirement_ready,
    }
