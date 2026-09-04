"""Composable, provenance-preserving dataset packages.

The same manifest is used for packages built outside and inside GenOS.  Build
location, source origin, security classification, and real/mock representation
are intentionally orthogonal fields.  Composition never copies or silently
merges files; it produces a logical ``UnifiedCorpusView`` with exact receipts.
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


PACKAGE_SCHEMA = "dataset-package-v2"
SOURCE_SET_SCHEMA = "source-set-v1"
SOURCE_SET_LOCK_SCHEMA = "source-set-lock-v1"
INSTALLED_CATALOG_SCHEMA = "installed-dataset-catalog-v1"
MATERIALIZATION_RECEIPT_SCHEMA = "source-set-materialization-receipt-v1"
LEGACY_OVERLAY_SCHEMA = "active-dataset-overlay-v1"
_ID = re.compile(r"^[a-z0-9][a-z0-9._:/-]{1,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_ORIGINS = frozenset(
    {"public_external", "restricted_internal", "curated_shared", "synthetic"}
)
_SECURITY_CLASSES = frozenset({"public", "internal", "restricted"})
_REPRESENTATIONS = frozenset({"real", "mock"})
_AUTHORITIES = frozenset({"authoritative", "curated", "observation", "evaluation"})
_EXECUTION_SITES = frozenset({"outside", "genos"})
_ARTIFACT_ROLES = frozenset(
    {
        "raw",
        "structure",
        "observation",
        "semantic",
        "relation",
        "lexical_index",
        "vector_index",
        "evaluation",
    }
)
_CONFLICT_POLICIES = frozenset({"error", "keep_namespaced", "explicit_priority"})
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_LEGACY_ROLE_MAP = {
    "primary": "raw",
    "structure": "structure",
    "frame": "observation",
    "taxonomy": "observation",
}


class DatasetContractError(ValueError):
    """A package or source-set would lose identity, provenance, or access policy."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _identifier(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not _ID.fullmatch(text):
        raise DatasetContractError(f"invalid {field}: {text!r}")
    return text


def _enum(value: object, allowed: frozenset[str], field: str) -> str:
    text = str(value or "")
    if text not in allowed:
        raise DatasetContractError(f"invalid {field}: {text!r}")
    return text


def _reject_unknown(
    blob: Mapping[str, Any], allowed: frozenset[str], field: str
) -> None:
    unknown = sorted(set(blob) - allowed)
    if unknown:
        raise DatasetContractError(
            f"unknown {field} fields: {', '.join(str(value) for value in unknown)}"
        )


def _relative(value: object, field: str) -> str:
    raw = str(value or "")
    text = raw.strip()
    path = PurePosixPath(text)
    if (
        not text
        or raw != text
        or "\x00" in text
        or "\\" in text
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != text
    ):
        raise DatasetContractError(f"{field} must be a safe relative path: {text!r}")
    return path.as_posix()


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _hash_file(path: Path) -> str:
    try:
        before = path.lstat()
    except OSError as exc:
        raise DatasetContractError(f"cannot stat artifact {path}: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise DatasetContractError(f"artifact is not a regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise DatasetContractError(f"cannot safely open artifact {path}: {exc}") from exc
    digest = hashlib.sha256()
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _stat_identity(before) != _stat_identity(opened):
            raise DatasetContractError(f"artifact changed before hashing: {path}")
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(descriptor)
        if _stat_identity(opened) != _stat_identity(after):
            raise DatasetContractError(f"artifact changed while hashing: {path}")
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_publish_directory_no_replace(staging: Path, target: Path) -> None:
    """Publish a SourceSet with an atomic no-clobber readiness boundary."""

    if os.name != "posix":
        raise DatasetContractError("atomic SourceSet publish requires a POSIX host")
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
            raise DatasetContractError(
                f"atomic SourceSet publish failed: {os.strerror(error_number)}"
            )

    try:
        target.mkdir(mode=0o700)
    except FileExistsError:
        raise
    marker = target / ".LAWRAG_PUBLICATION_INCOMPLETE"
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, b"source-set-materialization-v1\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(target)
    try:
        # The receipt is the logical readiness record and therefore moves last.
        children = sorted(
            staging.iterdir(),
            key=lambda value: (value.name == "receipt.json", os.fsencode(value.name)),
        )
        for child in children:
            os.rename(child, target / child.name)
        _fsync_directory(target)
        marker.unlink()
        _fsync_directory(target)
        _fsync_directory(target.parent)
        staging.rmdir()
    except Exception as exc:
        raise DatasetContractError(
            f"reserved SourceSet target is incomplete and retained: {target}: {exc}"
        ) from exc


def _resolve_contained(
    root: Path,
    relative: str,
    *,
    field: str,
    require_file: bool = False,
) -> Path:
    """Resolve one relative member without following a package-internal symlink.

    ``Path.resolve`` alone is insufficient because it silently follows symlinks.
    The lexical walk rejects every existing symlink first, then the resolved
    containment check protects missing-leaf and race-independent path shapes.
    """

    safe = _relative(relative, field)
    package_root = root.resolve()
    candidate = package_root
    for part in Path(safe).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise DatasetContractError(f"{field} contains a symlink: {safe!r}")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(package_root)
    except ValueError as exc:
        raise DatasetContractError(
            f"{field} escapes package root: {safe!r}"
        ) from exc
    if require_file and not resolved.is_file():
        raise DatasetContractError(f"missing file for {field}: {safe!r}")
    return resolved


def _derived_identifier(value: object, *, prefix: str) -> str:
    """Create a stable contract identifier without accepting unsafe characters."""

    raw = str(value or "").strip()
    slug = re.sub(r"[^a-z0-9._/-]+", "-", raw.lower()).strip("-./")
    if not slug:
        slug = prefix
    candidate = f"{prefix}-{slug}"
    if len(candidate) > 96:
        candidate = f"{candidate[:79].rstrip('-./')}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"
    return _identifier(candidate, prefix)


def _legacy_member_logical_id(logical_id: str, member_path: str) -> str:
    """Namespace one expanded legacy file by a readable, collision-safe path."""

    base = _identifier(logical_id, "legacy logical_id")
    safe_path = _relative(member_path, "legacy member path")
    readable = re.sub(r"[^a-z0-9._/-]+", "-", safe_path.lower()).strip("-./")
    readable = re.sub(r"/+", "/", readable) or "member"
    suffix = hashlib.sha256(safe_path.encode("utf-8")).hexdigest()[:16]
    # Preserve a useful path fragment while the digest prevents case, Unicode,
    # truncation, and normalization collisions.
    budget = 127 - len("/member/-") - len(suffix)
    base_budget = max(2, min(len(base), budget // 2))
    readable_budget = max(1, budget - base_budget)
    value = f"{base[:base_budget].rstrip('-./')}/member/{readable[:readable_budget].rstrip('-./')}-{suffix}"
    return _identifier(value, "legacy member logical_id")


@dataclass(frozen=True)
class Artifact:
    package_id: str
    dataset_id: str
    version_id: str
    build_id: str
    logical_id: str
    role: str
    path: str
    sha256: str
    media_type: str
    base_path: Path | None = None

    @property
    def logical_key(self) -> tuple[str, str]:
        return self.logical_id, self.role

    @property
    def qualified_id(self) -> str:
        return f"{self.package_id}:{self.logical_id}:{self.role}"

    def resolved_path(self) -> Path | None:
        if self.base_path is None:
            return None
        return _resolve_contained(
            self.base_path,
            self.path,
            field=f"artifact {self.qualified_id} path",
        )


@dataclass(frozen=True)
class DatasetPackage:
    package_id: str
    dataset_id: str
    version_id: str
    variant_id: str
    generation_id: str
    source_origin: str
    security_class: str
    representation: str
    authority: str
    export_allowed: bool
    build_id: str
    execution_site: str
    code_revision: str
    compiler_profile: str
    capabilities: tuple[str, ...]
    artifacts: tuple[Artifact, ...]
    manifest_sha256: str
    manifest_path: Path | None = None

    def receipt(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "dataset_id": self.dataset_id,
            "version_id": self.version_id,
            "variant_id": self.variant_id,
            "generation_id": self.generation_id,
            "source_origin": self.source_origin,
            "security_class": self.security_class,
            "representation": self.representation,
            "authority": self.authority,
            "export_allowed": self.export_allowed,
            "build_id": self.build_id,
            "execution_site": self.execution_site,
            "manifest_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True)
class SourceSetMember:
    package_id: str
    priority: int


@dataclass(frozen=True)
class SourceSetLockMember:
    package_id: str
    manifest_sha256: str
    priority: int

    def receipt(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "manifest_sha256": self.manifest_sha256,
            "priority": self.priority,
        }


@dataclass(frozen=True)
class SourceSetArtifactLock:
    package_id: str
    logical_id: str
    role: str
    path: str
    sha256: str
    contributors: tuple[str, ...]

    @property
    def qualified_id(self) -> str:
        return f"{self.package_id}:{self.logical_id}:{self.role}"

    def receipt(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "logical_id": self.logical_id,
            "role": self.role,
            "path": self.path,
            "sha256": self.sha256,
            "contributors": list(self.contributors),
        }


@dataclass(frozen=True)
class SourceSetLock:
    """Immutable identity of one fully resolved SourceSet selection."""

    source_set_id: str
    generation_id: str
    source_set_sha256: str
    conflict_policy: str
    cross_dataset_relations: bool
    export_allowed: bool
    members: tuple[SourceSetLockMember, ...]
    artifacts: tuple[SourceSetArtifactLock, ...]
    lock_sha256: str

    def receipt(self) -> dict[str, Any]:
        return {
            "schema_version": SOURCE_SET_LOCK_SCHEMA,
            "source_set_id": self.source_set_id,
            "generation_id": self.generation_id,
            "source_set_sha256": self.source_set_sha256,
            "conflict_policy": self.conflict_policy,
            "cross_dataset_relations": self.cross_dataset_relations,
            "export_allowed": self.export_allowed,
            "members": [member.receipt() for member in self.members],
            "artifacts": [artifact.receipt() for artifact in self.artifacts],
            "lock_sha256": self.lock_sha256,
        }


@dataclass(frozen=True)
class UnifiedArtifact:
    selected: Artifact
    contributors: tuple[str, ...]

    @property
    def logical_key(self) -> tuple[str, str]:
        return self.selected.logical_key


@dataclass(frozen=True)
class UnifiedCorpusView:
    source_set_id: str
    generation_id: str
    conflict_policy: str
    cross_dataset_relations: bool
    packages: tuple[DatasetPackage, ...]
    artifacts: tuple[UnifiedArtifact, ...]
    conflicts: tuple[dict[str, Any], ...]
    source_set_sha256: str
    export_allowed: bool
    members: tuple[SourceSetMember, ...] = ()

    def resolve(self, logical_id: str, role: str) -> tuple[UnifiedArtifact, ...]:
        return tuple(
            artifact
            for artifact in self.artifacts
            if artifact.selected.logical_id == logical_id
            and artifact.selected.role == role
        )

    def receipt(self) -> dict[str, Any]:
        return {
            "schema_version": "unified-corpus-receipt-v1",
            "source_set_id": self.source_set_id,
            "generation_id": self.generation_id,
            "source_set_sha256": self.source_set_sha256,
            "conflict_policy": self.conflict_policy,
            "cross_dataset_relations": self.cross_dataset_relations,
            "export_allowed": self.export_allowed,
            "packages": [package.receipt() for package in self.packages],
            "artifact_count": len(self.artifacts),
            "conflicts": list(self.conflicts),
        }

    def lock(self) -> SourceSetLock:
        return lock_source_set(self)


@dataclass(frozen=True)
class InstalledPackage:
    package_id: str
    manifest_path: str
    manifest_sha256: str

    def receipt(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "manifest_path": self.manifest_path,
            "manifest_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True)
class InstalledCatalog:
    """Exact, path-safe lookup table for immutable installed package manifests."""

    packages: tuple[InstalledPackage, ...]
    catalog_sha256: str
    package_root: Path
    catalog_path: Path | None = None

    def registration(self, package_id: str) -> InstalledPackage:
        expected_id = _identifier(package_id, "package_id")
        matches = [row for row in self.packages if row.package_id == expected_id]
        if not matches:
            raise DatasetContractError(f"unknown installed package: {expected_id}")
        if len(matches) != 1:
            raise DatasetContractError(
                f"ambiguous installed package registration: {expected_id}"
            )
        return matches[0]

    def lookup(
        self,
        package_id: str,
        manifest_sha256: str,
        *,
        verify_files: bool = True,
    ) -> DatasetPackage:
        expected_id = _identifier(package_id, "package_id")
        if not _SHA256.fullmatch(str(manifest_sha256 or "")):
            raise DatasetContractError("manifest_sha256 must be an exact SHA-256")
        matches = [
            row
            for row in self.packages
            if row.package_id == expected_id
            and row.manifest_sha256 == manifest_sha256
        ]
        if not matches:
            same_id = [row for row in self.packages if row.package_id == expected_id]
            if same_id:
                raise DatasetContractError(
                    f"installed package manifest hash mismatch: {expected_id}"
                )
            raise DatasetContractError(f"unknown installed package: {expected_id}")
        if len(matches) != 1:
            raise DatasetContractError(
                f"ambiguous installed package registration: {expected_id}"
            )
        registration = matches[0]
        target = _resolve_contained(
            self.package_root,
            registration.manifest_path,
            field=f"installed package {expected_id} manifest_path",
            require_file=True,
        )
        package = load_package(target, verify_files=verify_files)
        if package.package_id != expected_id:
            raise DatasetContractError(
                f"installed manifest package_id mismatch: {expected_id}"
            )
        if package.manifest_sha256 != manifest_sha256:
            raise DatasetContractError(
                f"installed manifest content mismatch: {expected_id}"
            )
        return package

    def open(
        self, source_set: Mapping[str, Any], *, verify_files: bool = True
    ) -> UnifiedCorpusView:
        members = _source_set_members(source_set)
        packages = []
        for member in members:
            registration = self.registration(member.package_id)
            packages.append(
                self.lookup(
                    registration.package_id,
                    registration.manifest_sha256,
                    verify_files=verify_files,
                )
            )
        return compose_source_set(source_set, packages)

    def resolve_lock(
        self, lock: SourceSetLock, *, verify_files: bool = True
    ) -> tuple[DatasetPackage, ...]:
        return tuple(
            self.lookup(
                member.package_id,
                member.manifest_sha256,
                verify_files=verify_files,
            )
            for member in lock.members
        )

    def receipt(self) -> dict[str, Any]:
        return {
            "schema_version": INSTALLED_CATALOG_SCHEMA,
            "catalog_sha256": self.catalog_sha256,
            "packages": [row.receipt() for row in self.packages],
        }


@dataclass(frozen=True)
class MaterializedSourceSet:
    path: Path
    lock: SourceSetLock
    receipt_sha256: str
    receipt: Mapping[str, Any]


class DatasetRegistry:
    """In-memory package registry used by one release/source-set selection."""

    def __init__(self, packages: Iterable[DatasetPackage] = ()) -> None:
        self._packages: dict[str, DatasetPackage] = {}
        for package in packages:
            self.register(package)

    def register(self, package: DatasetPackage) -> None:
        current = self._packages.get(package.package_id)
        if current is not None and current.manifest_sha256 != package.manifest_sha256:
            raise DatasetContractError(
                f"package ID has multiple manifests: {package.package_id}"
            )
        self._packages[package.package_id] = package

    def package(self, package_id: str) -> DatasetPackage:
        try:
            return self._packages[package_id]
        except KeyError as exc:
            raise DatasetContractError(f"unknown dataset package: {package_id}") from exc

    def open(self, source_set: Mapping[str, Any]) -> UnifiedCorpusView:
        return compose_source_set(source_set, self._packages.values())

    def receipt(self) -> list[dict[str, Any]]:
        return [self._packages[key].receipt() for key in sorted(self._packages)]


def installed_catalog_from_mapping(
    blob: Mapping[str, Any],
    *,
    catalog_path: str | Path | None = None,
    package_root: str | Path | None = None,
) -> InstalledCatalog:
    if blob.get("schema_version") != INSTALLED_CATALOG_SCHEMA:
        raise DatasetContractError(
            f"unsupported installed catalog schema: {blob.get('schema_version')!r}"
        )
    _reject_unknown(
        blob,
        frozenset({"schema_version", "packages", "catalog_sha256"}),
        "installed catalog",
    )
    raw_catalog_path = Path(catalog_path) if catalog_path is not None else None
    if raw_catalog_path is not None and raw_catalog_path.is_symlink():
        raise DatasetContractError("installed catalog manifest cannot be a symlink")
    resolved_catalog_path = (
        raw_catalog_path.resolve() if raw_catalog_path is not None else None
    )
    if package_root is None and resolved_catalog_path is None:
        raise DatasetContractError(
            "installed catalog requires catalog_path or an explicit package_root"
        )
    resolved_root = (
        Path(package_root).resolve()
        if package_root is not None
        else resolved_catalog_path.parent  # type: ignore[union-attr]
    )
    rows = blob.get("packages")
    if not isinstance(rows, list) or not rows:
        raise DatasetContractError("installed catalog packages must be non-empty")
    packages: list[InstalledPackage] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for position, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise DatasetContractError(f"packages[{position}] must be an object")
        _reject_unknown(
            row,
            frozenset({"package_id", "manifest_path", "manifest_sha256"}),
            f"packages[{position}]",
        )
        package_id = _identifier(
            row.get("package_id"), f"packages[{position}].package_id"
        )
        manifest_path = _relative(
            row.get("manifest_path"), f"packages[{position}].manifest_path"
        )
        manifest_sha256 = str(row.get("manifest_sha256") or "")
        if not _SHA256.fullmatch(manifest_sha256):
            raise DatasetContractError(
                f"invalid packages[{position}].manifest_sha256"
            )
        if package_id in seen_ids:
            raise DatasetContractError(
                f"duplicate installed catalog package_id: {package_id}"
            )
        if manifest_path in seen_paths:
            raise DatasetContractError(
                f"duplicate installed catalog manifest_path: {manifest_path}"
            )
        seen_ids.add(package_id)
        seen_paths.add(manifest_path)
        # Verify containment and any existing symlink now; file existence and
        # manifest content are checked by exact lookup so catalog discovery can
        # remain separate from package activation.
        _resolve_contained(
            resolved_root,
            manifest_path,
            field=f"packages[{position}].manifest_path",
        )
        packages.append(
            InstalledPackage(package_id, manifest_path, manifest_sha256)
        )
    normalized = dict(blob)
    normalized.pop("catalog_sha256", None)
    catalog_sha256 = _digest(normalized)
    declared = blob.get("catalog_sha256")
    if declared is not None and declared != catalog_sha256:
        raise DatasetContractError("installed catalog_sha256 mismatch")
    return InstalledCatalog(
        packages=tuple(packages),
        catalog_sha256=catalog_sha256,
        package_root=resolved_root,
        catalog_path=resolved_catalog_path,
    )


def load_installed_catalog(
    path: str | Path, *, package_root: str | Path | None = None
) -> InstalledCatalog:
    raw_path = Path(path)
    if raw_path.is_symlink():
        raise DatasetContractError("installed catalog manifest cannot be a symlink")
    catalog_path = raw_path.resolve()
    try:
        blob = json.loads(catalog_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetContractError(
            f"cannot read installed catalog {catalog_path}: {exc}"
        ) from exc
    if not isinstance(blob, Mapping):
        raise DatasetContractError("installed catalog root must be an object")
    return installed_catalog_from_mapping(
        blob,
        catalog_path=catalog_path,
        package_root=package_root,
    )


def package_from_mapping(
    blob: Mapping[str, Any], *, manifest_path: str | Path | None = None
) -> DatasetPackage:
    if blob.get("schema_version") != PACKAGE_SCHEMA:
        raise DatasetContractError(
            f"unsupported dataset package schema: {blob.get('schema_version')!r}"
        )
    _reject_unknown(
        blob,
        frozenset(
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
            }
        ),
        "dataset package",
    )
    package_id = _identifier(blob.get("package_id"), "package_id")
    dataset_id = _identifier(blob.get("dataset_id"), "dataset_id")
    version_id = _identifier(blob.get("version_id"), "version_id")
    variant_id = _identifier(blob.get("variant_id"), "variant_id")
    generation_id = _identifier(blob.get("generation_id"), "generation_id")
    source_origin = _enum(blob.get("source_origin"), _SOURCE_ORIGINS, "source_origin")
    security_class = _enum(
        blob.get("security_class"), _SECURITY_CLASSES, "security_class"
    )
    representation = _enum(
        blob.get("representation"), _REPRESENTATIONS, "representation"
    )
    authority = _enum(blob.get("authority"), _AUTHORITIES, "authority")
    export_policy = blob.get("export_policy")
    if not isinstance(export_policy, Mapping) or not isinstance(
        export_policy.get("allowed"), bool
    ):
        raise DatasetContractError("export_policy.allowed must be boolean")
    _reject_unknown(export_policy, frozenset({"allowed"}), "export_policy")
    export_allowed = bool(export_policy["allowed"])
    if security_class == "restricted" and export_allowed:
        raise DatasetContractError("restricted package cannot be exportable")
    if source_origin == "restricted_internal" and export_allowed:
        raise DatasetContractError("restricted_internal package cannot be exportable")

    build = blob.get("build")
    if not isinstance(build, Mapping):
        raise DatasetContractError("build must be an object")
    _reject_unknown(
        build,
        frozenset(
            {
                "build_id",
                "execution_site",
                "code_revision",
                "compiler_profile",
                "capabilities",
            }
        ),
        "build",
    )
    build_id = _identifier(build.get("build_id"), "build.build_id")
    execution_site = _enum(
        build.get("execution_site"), _EXECUTION_SITES, "build.execution_site"
    )
    code_revision = str(build.get("code_revision") or "").strip()
    compiler_profile = str(build.get("compiler_profile") or "").strip()
    if not code_revision or not compiler_profile:
        raise DatasetContractError("build code_revision and compiler_profile are required")
    raw_capabilities = build.get("capabilities") or []
    if not isinstance(raw_capabilities, list):
        raise DatasetContractError("build.capabilities must be a list")
    capabilities = tuple(sorted({_identifier(v, "capability") for v in raw_capabilities}))

    raw_source_path = Path(manifest_path) if manifest_path is not None else None
    if raw_source_path is not None and raw_source_path.is_symlink():
        raise DatasetContractError("dataset package manifest cannot be a symlink")
    source_path = raw_source_path.resolve() if raw_source_path is not None else None
    base_path = source_path.parent if source_path is not None else None
    artifacts: list[Artifact] = []
    seen: set[tuple[str, str]] = set()
    rows = blob.get("artifacts")
    if not isinstance(rows, list) or not rows:
        raise DatasetContractError("artifacts must be a non-empty list")
    for position, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise DatasetContractError(f"artifacts[{position}] must be an object")
        _reject_unknown(
            row,
            frozenset({"logical_id", "role", "path", "sha256", "media_type"}),
            f"artifacts[{position}]",
        )
        logical_id = _identifier(row.get("logical_id"), f"artifacts[{position}].logical_id")
        role = _enum(row.get("role"), _ARTIFACT_ROLES, f"artifacts[{position}].role")
        key = (logical_id, role)
        if key in seen:
            raise DatasetContractError(f"duplicate artifact logical key: {key}")
        seen.add(key)
        sha256 = str(row.get("sha256") or "")
        if not _SHA256.fullmatch(sha256):
            raise DatasetContractError(f"invalid artifact sha256 at position {position}")
        artifacts.append(
            Artifact(
                package_id=package_id,
                dataset_id=dataset_id,
                version_id=version_id,
                build_id=build_id,
                logical_id=logical_id,
                role=role,
                path=_relative(row.get("path"), f"artifacts[{position}].path"),
                sha256=sha256,
                media_type=str(row.get("media_type") or "application/octet-stream"),
                base_path=base_path,
            )
        )

    normalized = dict(blob)
    normalized.pop("manifest_sha256", None)
    manifest_sha256 = _digest(normalized)
    declared = blob.get("manifest_sha256")
    if declared is not None and declared != manifest_sha256:
        raise DatasetContractError("dataset package manifest_sha256 mismatch")
    return DatasetPackage(
        package_id=package_id,
        dataset_id=dataset_id,
        version_id=version_id,
        variant_id=variant_id,
        generation_id=generation_id,
        source_origin=source_origin,
        security_class=security_class,
        representation=representation,
        authority=authority,
        export_allowed=export_allowed,
        build_id=build_id,
        execution_site=execution_site,
        code_revision=code_revision,
        compiler_profile=compiler_profile,
        capabilities=capabilities,
        artifacts=tuple(artifacts),
        manifest_sha256=manifest_sha256,
        manifest_path=source_path,
    )


def load_package(path: str | Path, *, verify_files: bool = True) -> DatasetPackage:
    raw_manifest_path = Path(path)
    if raw_manifest_path.is_symlink():
        raise DatasetContractError("dataset package manifest cannot be a symlink")
    manifest_path = raw_manifest_path.resolve()
    try:
        blob = json.loads(manifest_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetContractError(f"cannot read dataset package {manifest_path}: {exc}") from exc
    if not isinstance(blob, Mapping):
        raise DatasetContractError("dataset package root must be an object")
    package = package_from_mapping(blob, manifest_path=manifest_path)
    if verify_files:
        for artifact in package.artifacts:
            target = artifact.resolved_path()
            if target is None or not target.is_file():
                raise DatasetContractError(f"missing artifact file: {artifact.path}")
            actual = _hash_file(target)
            if actual != artifact.sha256:
                raise DatasetContractError(
                    f"artifact hash mismatch: {artifact.qualified_id}"
                )
    return package


def _media_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".html": "text/html",
        ".json": "application/json",
        ".jsonl": "application/x-ndjson",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".xml": "application/xml",
    }.get(suffix, "application/octet-stream")


def package_from_legacy_overlay(
    active_manifest_path: str | Path,
    *,
    root: str | Path | None = None,
    package_id: str | None = None,
    dataset_id: str | None = None,
    version_id: str = "legacy-v1",
    export_allowed: bool = False,
    verify_files: bool = True,
) -> DatasetPackage:
    """Adapt an expanded ``ACTIVE_DATASET.json`` to a file-level package.

    A legacy ``structure`` entry represents a directory but the active overlay
    records every expanded file.  Each file therefore receives a logical ID
    containing a readable path fragment plus a path digest.  This avoids the
    historical ``(logical_id, role)`` collision and ensures both ``meta.json``
    and ``result.json`` participate in the immutable package identity.
    """

    raw_manifest = Path(active_manifest_path)
    if raw_manifest.is_symlink():
        raise DatasetContractError("legacy active manifest cannot be a symlink")
    manifest_path = raw_manifest.resolve()
    install_root = (
        Path(root).resolve()
        if root is not None
        else (
            manifest_path.parents[2]
            if len(manifest_path.parents) >= 3
            else manifest_path.parent
        )
    )
    try:
        manifest_relative = manifest_path.relative_to(install_root).as_posix()
    except ValueError as exc:
        raise DatasetContractError("legacy active manifest escapes install root") from exc
    _resolve_contained(
        install_root,
        manifest_relative,
        field="legacy active manifest",
        require_file=True,
    )
    try:
        blob = json.loads(manifest_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetContractError(
            f"cannot read legacy active manifest {manifest_path}: {exc}"
        ) from exc
    if not isinstance(blob, Mapping):
        raise DatasetContractError("legacy active manifest root must be an object")
    if blob.get("schema_version") != LEGACY_OVERLAY_SCHEMA:
        raise DatasetContractError(
            f"unsupported legacy overlay schema: {blob.get('schema_version')!r}"
        )
    _reject_unknown(
        blob,
        frozenset(
            {
                "schema_version",
                "overlay_id",
                "representation",
                "contract_sha256",
                "items",
            }
        ),
        "legacy active manifest",
    )
    representation = _enum(
        blob.get("representation"), _REPRESENTATIONS, "legacy representation"
    )
    contract_sha256 = str(blob.get("contract_sha256") or "")
    if not _SHA256.fullmatch(contract_sha256):
        raise DatasetContractError("legacy contract_sha256 must be SHA-256")
    overlay_id = _identifier(blob.get("overlay_id"), "legacy overlay_id")
    if representation == "real" and export_allowed:
        raise DatasetContractError("real legacy overlay cannot be exportable")

    rows = blob.get("items")
    if not isinstance(rows, list) or not rows:
        raise DatasetContractError("legacy active items must be a non-empty list")
    artifacts: list[dict[str, Any]] = []
    contract_items: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    seen_paths: set[str] = set()
    seen_logical_keys: set[tuple[str, str]] = set()
    for item_position, item in enumerate(rows):
        if not isinstance(item, Mapping):
            raise DatasetContractError(
                f"legacy items[{item_position}] must be an object"
            )
        _reject_unknown(
            item,
            frozenset(
                {
                    "logical_id",
                    "contract",
                    "representation",
                    "doc_id",
                    "files",
                }
            ),
            f"legacy items[{item_position}]",
        )
        logical_id = _identifier(
            item.get("logical_id"), f"legacy items[{item_position}].logical_id"
        )
        if logical_id in seen_items:
            raise DatasetContractError(f"duplicate legacy logical_id: {logical_id}")
        seen_items.add(logical_id)
        contract = item.get("contract")
        if not isinstance(contract, Mapping):
            raise DatasetContractError(
                f"legacy item contract must be an object: {logical_id}"
            )
        _reject_unknown(
            contract,
            frozenset({"kind", "format_family", "version_role", "artifact_roles"}),
            f"legacy item {logical_id} contract",
        )
        for field in ("kind", "format_family", "version_role"):
            if not str(contract.get(field) or "").strip():
                raise DatasetContractError(
                    f"legacy item contract.{field} is required: {logical_id}"
                )
        contract_roles = contract.get("artifact_roles")
        if (
            not isinstance(contract_roles, list)
            or not contract_roles
            or any(str(value or "") not in _LEGACY_ROLE_MAP for value in contract_roles)
            or len(contract_roles) != len(set(str(value) for value in contract_roles))
        ):
            raise DatasetContractError(
                f"legacy item contract.artifact_roles is invalid: {logical_id}"
            )
        contract_items.append(
            {"logical_id": logical_id, "contract": dict(contract)}
        )
        if item.get("representation") not in (None, representation):
            raise DatasetContractError(
                f"legacy item representation mismatch: {logical_id}"
            )
        files = item.get("files")
        if not isinstance(files, list) or not files:
            raise DatasetContractError(f"legacy item has no files: {logical_id}")
        structure_names: set[str] = set()
        observed_roles: set[str] = set()
        for file_position, file_row in enumerate(files):
            if not isinstance(file_row, Mapping):
                raise DatasetContractError(
                    f"legacy {logical_id} files[{file_position}] must be an object"
                )
            _reject_unknown(
                file_row,
                frozenset({"path", "role"}),
                f"legacy {logical_id} files[{file_position}]",
            )
            member_path = _relative(
                file_row.get("path"),
                f"legacy {logical_id} files[{file_position}].path",
            )
            if member_path in seen_paths:
                raise DatasetContractError(
                    f"duplicate legacy expanded member path: {member_path}"
                )
            seen_paths.add(member_path)
            legacy_role = str(file_row.get("role") or "")
            try:
                role = _LEGACY_ROLE_MAP[legacy_role]
            except KeyError as exc:
                raise DatasetContractError(
                    f"unsupported legacy artifact role: {legacy_role!r}"
                ) from exc
            observed_roles.add(legacy_role)
            target = _resolve_contained(
                install_root,
                member_path,
                field=f"legacy member {logical_id}",
                require_file=verify_files,
            )
            if legacy_role == "structure":
                structure_names.add(Path(member_path).name)
            member_logical_id = _legacy_member_logical_id(logical_id, member_path)
            key = (member_logical_id, role)
            if key in seen_logical_keys:
                raise DatasetContractError(
                    f"legacy member logical key collision: {key}"
                )
            seen_logical_keys.add(key)
            if not target.is_file():
                raise DatasetContractError(
                    f"cannot hash missing legacy member: {member_path}"
                )
            artifacts.append(
                {
                    "logical_id": member_logical_id,
                    "role": role,
                    "path": member_path,
                    "sha256": _hash_file(target),
                    "media_type": _media_type(member_path),
                }
            )
        if structure_names and not {"meta.json", "result.json"}.issubset(
            structure_names
        ):
            raise DatasetContractError(
                f"legacy structure must bind meta.json and result.json: {logical_id}"
            )
        if observed_roles != set(str(value) for value in contract_roles):
            raise DatasetContractError(
                f"legacy file roles do not match contract: {logical_id}"
            )

    expected_contract_sha256 = _digest(
        {
            "schema_version": "dataset-overlay-contract-v1",
            "items": contract_items,
        }
    )
    if contract_sha256 != expected_contract_sha256:
        raise DatasetContractError("legacy overlay contract_sha256 mismatch")

    active_sha256 = _hash_file(manifest_path)
    final_package_id = (
        _identifier(package_id, "package_id")
        if package_id is not None
        else _derived_identifier(overlay_id, prefix="legacy-package")
    )
    final_dataset_id = (
        _identifier(dataset_id, "dataset_id")
        if dataset_id is not None
        else _derived_identifier(overlay_id, prefix="legacy-dataset")
    )
    package_blob: dict[str, Any] = {
        "schema_version": PACKAGE_SCHEMA,
        "package_id": final_package_id,
        "dataset_id": final_dataset_id,
        "version_id": _identifier(version_id, "version_id"),
        "variant_id": representation,
        "generation_id": f"gen-{active_sha256[:24]}",
        "source_origin": (
            "restricted_internal" if representation == "real" else "synthetic"
        ),
        "security_class": "restricted" if representation == "real" else "public",
        "representation": representation,
        "authority": "curated",
        "export_policy": {"allowed": bool(export_allowed)},
        "build": {
            "build_id": f"legacy-{active_sha256[:24]}",
            "execution_site": "genos" if representation == "real" else "outside",
            "code_revision": "legacy-overlay-adapter-v1",
            "compiler_profile": "legacy-overlay-file-v1",
            "capabilities": sorted({row["role"] for row in artifacts}),
        },
        "artifacts": artifacts,
    }
    # A virtual manifest under the install root gives every adapted artifact
    # the same containment boundary without materializing a mutable manifest.
    return package_from_mapping(
        package_blob,
        manifest_path=install_root / ".legacy-overlay-package.json",
    )


def _source_set_members(blob: Mapping[str, Any]) -> tuple[SourceSetMember, ...]:
    rows = blob.get("members")
    if not isinstance(rows, list) or not rows:
        raise DatasetContractError("source set members must be a non-empty list")
    members: list[SourceSetMember] = []
    seen: set[str] = set()
    for position, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise DatasetContractError(f"members[{position}] must be an object")
        _reject_unknown(
            row,
            frozenset({"package_id", "priority"}),
            f"members[{position}]",
        )
        package_id = _identifier(row.get("package_id"), f"members[{position}].package_id")
        if package_id in seen:
            raise DatasetContractError(f"duplicate source-set package: {package_id}")
        seen.add(package_id)
        priority = row.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise DatasetContractError(f"members[{position}].priority must be integer")
        members.append(SourceSetMember(package_id, priority))
    return tuple(members)


def compose_source_set(
    blob: Mapping[str, Any], packages: Iterable[DatasetPackage]
) -> UnifiedCorpusView:
    """Validate and logically compose selected packages without losing provenance."""

    if blob.get("schema_version") != SOURCE_SET_SCHEMA:
        raise DatasetContractError(
            f"unsupported source-set schema: {blob.get('schema_version')!r}"
        )
    _reject_unknown(
        blob,
        frozenset(
            {
                "schema_version",
                "source_set_id",
                "generation_id",
                "conflict_policy",
                "members",
                "cross_dataset_relations",
            }
        ),
        "source set",
    )
    source_set_id = _identifier(blob.get("source_set_id"), "source_set_id")
    generation_id = _identifier(blob.get("generation_id"), "generation_id")
    conflict_policy = _enum(
        blob.get("conflict_policy"), _CONFLICT_POLICIES, "conflict_policy"
    )
    cross_dataset_relations = blob.get("cross_dataset_relations", False)
    if not isinstance(cross_dataset_relations, bool):
        raise DatasetContractError("cross_dataset_relations must be boolean")
    members = _source_set_members(blob)
    available: dict[str, DatasetPackage] = {}
    for package in packages:
        current = available.get(package.package_id)
        if current is not None and current.manifest_sha256 != package.manifest_sha256:
            raise DatasetContractError(
                f"package ID has multiple manifests: {package.package_id}"
            )
        available[package.package_id] = package
    selected: list[tuple[SourceSetMember, DatasetPackage]] = []
    for member in members:
        package = available.get(member.package_id)
        if package is None:
            raise DatasetContractError(f"source set package is unavailable: {member.package_id}")
        selected.append((member, package))

    # A real and mock variant for the same dataset/version is never an implicit
    # union.  The caller must create separate source sets.
    variants: dict[tuple[str, str], set[str]] = {}
    for _, package in selected:
        variants.setdefault((package.dataset_id, package.version_id), set()).add(
            package.representation
        )
    mixed = [key for key, values in variants.items() if len(values) > 1]
    if mixed:
        raise DatasetContractError(f"real/mock variants cannot coexist: {sorted(mixed)}")

    grouped: dict[tuple[str, str], list[tuple[int, Artifact]]] = {}
    for member, package in selected:
        for artifact in package.artifacts:
            grouped.setdefault(artifact.logical_key, []).append((member.priority, artifact))

    unified: list[UnifiedArtifact] = []
    conflicts: list[dict[str, Any]] = []
    for key in sorted(grouped):
        rows = sorted(grouped[key], key=lambda row: (-row[0], row[1].package_id))
        hashes = {artifact.sha256 for _, artifact in rows}
        contributors = tuple(sorted({artifact.package_id for _, artifact in rows}))
        if len(hashes) == 1:
            unified.append(UnifiedArtifact(rows[0][1], contributors))
            continue
        conflict = {
            "logical_id": key[0],
            "role": key[1],
            "packages": list(contributors),
            "sha256": sorted(hashes),
            "candidates": [
                {
                    "package_id": artifact.package_id,
                    "priority": priority,
                    "sha256": artifact.sha256,
                }
                for priority, artifact in rows
            ],
        }
        conflicts.append(conflict)
        if conflict_policy == "error":
            raise DatasetContractError(
                f"conflicting logical artifact requires an explicit policy: {key}"
            )
        if conflict_policy == "keep_namespaced":
            conflict["resolution"] = "keep_namespaced"
            conflict["selected_package_ids"] = list(contributors)
            unified.extend(
                UnifiedArtifact(artifact, (artifact.package_id,)) for _, artifact in rows
            )
            continue
        highest = rows[0][0]
        winners = [artifact for priority, artifact in rows if priority == highest]
        if len(winners) != 1:
            raise DatasetContractError(f"priority tie for conflicting artifact: {key}")
        conflict["resolution"] = "explicit_priority"
        conflict["selected_package_ids"] = [winners[0].package_id]
        unified.append(UnifiedArtifact(winners[0], contributors))

    selected_packages = tuple(package for _, package in selected)
    export_allowed = all(package.export_allowed for package in selected_packages)
    receipt_core = {
        "source_set_id": source_set_id,
        "generation_id": generation_id,
        "conflict_policy": conflict_policy,
        "cross_dataset_relations": cross_dataset_relations,
        "members": [
            {
                "package_id": member.package_id,
                "priority": member.priority,
                "manifest_sha256": package.manifest_sha256,
            }
            for member, package in selected
        ],
        "artifacts": [
            {
                "qualified_id": item.selected.qualified_id,
                "sha256": item.selected.sha256,
                "contributors": list(item.contributors),
            }
            for item in unified
        ],
    }
    return UnifiedCorpusView(
        source_set_id=source_set_id,
        generation_id=generation_id,
        conflict_policy=conflict_policy,
        cross_dataset_relations=cross_dataset_relations,
        packages=selected_packages,
        artifacts=tuple(unified),
        conflicts=tuple(conflicts),
        source_set_sha256=_digest(receipt_core),
        export_allowed=export_allowed,
        members=members,
    )


def lock_source_set(view: UnifiedCorpusView) -> SourceSetLock:
    """Freeze ordered package selection and every selected artifact hash."""

    if not view.members:
        raise DatasetContractError(
            "SourceSet member priorities are required to create an immutable lock"
        )
    packages = {package.package_id: package for package in view.packages}
    if len(packages) != len(view.packages):
        raise DatasetContractError("SourceSet contains duplicate package IDs")
    locked_members: list[SourceSetLockMember] = []
    for member in view.members:
        package = packages.get(member.package_id)
        if package is None:
            raise DatasetContractError(
                f"SourceSet member is absent from view: {member.package_id}"
            )
        locked_members.append(
            SourceSetLockMember(
                package_id=package.package_id,
                manifest_sha256=package.manifest_sha256,
                priority=member.priority,
            )
        )
    locked_artifacts = tuple(
        SourceSetArtifactLock(
            package_id=item.selected.package_id,
            logical_id=item.selected.logical_id,
            role=item.selected.role,
            path=item.selected.path,
            sha256=item.selected.sha256,
            contributors=item.contributors,
        )
        for item in view.artifacts
    )
    source_identity = {
        "source_set_id": view.source_set_id,
        "generation_id": view.generation_id,
        "conflict_policy": view.conflict_policy,
        "cross_dataset_relations": view.cross_dataset_relations,
        "members": [member.receipt() for member in locked_members],
        "artifacts": [
            {
                "qualified_id": artifact.qualified_id,
                "sha256": artifact.sha256,
                "contributors": list(artifact.contributors),
            }
            for artifact in locked_artifacts
        ],
    }
    if _digest(source_identity) != view.source_set_sha256:
        raise DatasetContractError("SourceSet view identity does not match its contents")
    lock_core = {
        "schema_version": SOURCE_SET_LOCK_SCHEMA,
        "source_set_id": view.source_set_id,
        "generation_id": view.generation_id,
        "source_set_sha256": view.source_set_sha256,
        "conflict_policy": view.conflict_policy,
        "cross_dataset_relations": view.cross_dataset_relations,
        "export_allowed": view.export_allowed,
        "members": [member.receipt() for member in locked_members],
        "artifacts": [artifact.receipt() for artifact in locked_artifacts],
    }
    return SourceSetLock(
        source_set_id=view.source_set_id,
        generation_id=view.generation_id,
        source_set_sha256=view.source_set_sha256,
        conflict_policy=view.conflict_policy,
        cross_dataset_relations=view.cross_dataset_relations,
        export_allowed=view.export_allowed,
        members=tuple(locked_members),
        artifacts=locked_artifacts,
        lock_sha256=_digest(lock_core),
    )


def _validate_runtime_policy(
    view: UnifiedCorpusView,
    *,
    for_export: bool,
    relation_policy_enforced: bool,
    allow_cross_dataset_relations: bool,
) -> None:
    if for_export and not view.export_allowed:
        raise DatasetContractError("restricted SourceSet cannot be exported")
    if view.conflict_policy == "keep_namespaced":
        raise DatasetContractError(
            "keep_namespaced is unsafe until runtime coordinates are namespace-aware"
        )
    dataset_ids = {package.dataset_id for package in view.packages}
    if len(dataset_ids) <= 1:
        return
    if view.cross_dataset_relations:
        if not allow_cross_dataset_relations:
            raise DatasetContractError(
                "cross-dataset relations require an explicit runtime capability"
            )
    elif not relation_policy_enforced:
        raise DatasetContractError(
            "cross-dataset isolation is not enforced by this runtime"
        )


def _verify_materialized_source_set(
    destination: Path, lock: SourceSetLock
) -> MaterializedSourceSet:
    if destination.is_symlink() or not destination.is_dir():
        raise DatasetContractError("materialized SourceSet path is not a safe directory")
    receipt_path = _resolve_contained(
        destination,
        "receipt.json",
        field="materialization receipt",
        require_file=True,
    )
    try:
        blob = json.loads(receipt_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetContractError(f"invalid materialization receipt: {exc}") from exc
    if not isinstance(blob, Mapping):
        raise DatasetContractError("materialization receipt must be an object")
    _reject_unknown(
        blob,
        frozenset(
            {
                "schema_version",
                "lock",
                "export_allowed",
                "artifacts",
                "receipt_sha256",
            }
        ),
        "materialization receipt",
    )
    if blob.get("schema_version") != MATERIALIZATION_RECEIPT_SCHEMA:
        raise DatasetContractError("unsupported materialization receipt schema")
    declared = str(blob.get("receipt_sha256") or "")
    core = dict(blob)
    core.pop("receipt_sha256", None)
    if not _SHA256.fullmatch(declared) or _digest(core) != declared:
        raise DatasetContractError("materialization receipt hash mismatch")
    if blob.get("lock") != lock.receipt():
        raise DatasetContractError("materialized SourceSet lock mismatch")
    rows = blob.get("artifacts")
    if not isinstance(rows, list) or len(rows) != len(lock.artifacts):
        raise DatasetContractError("materialized artifact set is incomplete")
    declared_files = {"receipt.json"}
    for position, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise DatasetContractError(
                f"materialized artifacts[{position}] must be an object"
            )
        _reject_unknown(
            row,
            frozenset(
                {
                    "qualified_id",
                    "package_id",
                    "logical_id",
                    "role",
                    "source_path",
                    "sha256",
                    "contributors",
                    "materialized_path",
                }
            ),
            f"materialized artifacts[{position}]",
        )
        target_rel = _relative(
            row.get("materialized_path"),
            f"materialized artifacts[{position}].materialized_path",
        )
        target = _resolve_contained(
            destination,
            target_rel,
            field=f"materialized artifacts[{position}]",
            require_file=True,
        )
        expected = lock.artifacts[position]
        expected_fields = {
            "qualified_id": expected.qualified_id,
            "package_id": expected.package_id,
            "logical_id": expected.logical_id,
            "role": expected.role,
            "source_path": expected.path,
            "sha256": expected.sha256,
            "contributors": list(expected.contributors),
        }
        if any(row.get(key) != value for key, value in expected_fields.items()) or (
            _hash_file(target) != expected.sha256
        ):
            raise DatasetContractError(
                f"materialized artifact mismatch: {expected.qualified_id}"
            )
        declared_files.add(target_rel)
    observed_files: set[str] = set()
    for path in destination.rglob("*"):
        if path.is_symlink():
            raise DatasetContractError("materialized SourceSet contains a symlink")
        if path.is_file():
            observed_files.add(path.relative_to(destination).as_posix())
    if observed_files != declared_files:
        raise DatasetContractError("materialized SourceSet has undeclared files")
    return MaterializedSourceSet(destination, lock, declared, blob)


def materialize_source_set(
    view: UnifiedCorpusView,
    destination: str | Path,
    *,
    lock: SourceSetLock | None = None,
    for_export: bool = False,
    relation_policy_enforced: bool = False,
    allow_cross_dataset_relations: bool = False,
) -> MaterializedSourceSet:
    """Copy a verified SourceSet to a staging tree and atomically publish it."""

    _validate_runtime_policy(
        view,
        for_export=for_export,
        relation_policy_enforced=relation_policy_enforced,
        allow_cross_dataset_relations=allow_cross_dataset_relations,
    )
    expected_lock = view.lock()
    selected_lock = lock or expected_lock
    if selected_lock != expected_lock:
        raise DatasetContractError("provided SourceSet lock does not match the view")
    final_path = Path(destination).resolve(strict=False)
    if Path(destination).is_symlink():
        raise DatasetContractError("materialization destination cannot be a symlink")
    if final_path.exists():
        return _verify_materialized_source_set(final_path, selected_lock)
    parent = final_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{final_path.name}.staging-", dir=parent)
    )
    published = False
    try:
        artifact_rows: list[dict[str, Any]] = []
        if len(view.artifacts) != len(selected_lock.artifacts):
            raise DatasetContractError("SourceSet artifact lock is incomplete")
        for position, (item, artifact_lock) in enumerate(
            zip(view.artifacts, selected_lock.artifacts, strict=True)
        ):
            artifact = item.selected
            if (
                artifact.qualified_id != artifact_lock.qualified_id
                or artifact.sha256 != artifact_lock.sha256
                or artifact.path != artifact_lock.path
            ):
                raise DatasetContractError("SourceSet artifact changed after locking")
            source = artifact.resolved_path()
            if source is None or not source.is_file():
                raise DatasetContractError(
                    f"missing SourceSet artifact: {artifact.qualified_id}"
                )
            if _hash_file(source) != artifact.sha256:
                raise DatasetContractError(
                    f"SourceSet artifact hash mismatch: {artifact.qualified_id}"
                )
            suffix = Path(artifact.path).suffix.lower()
            if not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix):
                suffix = ""
            target_rel = f"ARTIFACTS/{position:08d}-{artifact.sha256[:16]}{suffix}"
            target = staging / target_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target, follow_symlinks=False)
            if _hash_file(target) != artifact.sha256:
                raise DatasetContractError(
                    f"staged artifact hash mismatch: {artifact.qualified_id}"
                )
            artifact_rows.append(
                {
                    "qualified_id": artifact.qualified_id,
                    "package_id": artifact.package_id,
                    "logical_id": artifact.logical_id,
                    "role": artifact.role,
                    "source_path": artifact.path,
                    "sha256": artifact.sha256,
                    "contributors": list(item.contributors),
                    "materialized_path": target_rel,
                }
            )
        receipt_core: dict[str, Any] = {
            "schema_version": MATERIALIZATION_RECEIPT_SCHEMA,
            "lock": selected_lock.receipt(),
            "export_allowed": view.export_allowed,
            "artifacts": artifact_rows,
        }
        receipt = dict(receipt_core)
        receipt["receipt_sha256"] = _digest(receipt_core)
        receipt_path = staging / "receipt.json"
        payload = (
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        with receipt_path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Staging is a sibling, so renameat2 is same-filesystem and atomic.  It
        # explicitly refuses to replace even an empty directory published by a
        # competing writer.
        _atomic_publish_directory_no_replace(staging, final_path)
        published = True
        _fsync_directory(parent)
        return _verify_materialized_source_set(final_path, selected_lock)
    except FileExistsError:
        if final_path.is_dir():
            return _verify_materialized_source_set(final_path, selected_lock)
        raise
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


def load_source_set(
    path: str | Path,
    packages: Iterable[DatasetPackage],
) -> UnifiedCorpusView:
    source_path = Path(path)
    try:
        blob = json.loads(source_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetContractError(f"cannot read source set {source_path}: {exc}") from exc
    if not isinstance(blob, Mapping):
        raise DatasetContractError("source-set root must be an object")
    return compose_source_set(blob, packages)
