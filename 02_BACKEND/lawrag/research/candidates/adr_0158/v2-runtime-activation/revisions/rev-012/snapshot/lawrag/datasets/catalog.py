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
from typing import Any, Callable, Iterable, Mapping


PACKAGE_SCHEMA = "dataset-package-v2"
SOURCE_SET_SCHEMA = "source-set-v1"
SOURCE_SET_LOCK_SCHEMA = "source-set-lock-v1"
INSTALLED_CATALOG_SCHEMA = "installed-dataset-catalog-v1"
MATERIALIZATION_RECEIPT_SCHEMA = "source-set-materialization-receipt-v2"
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
_CANONICAL_TEXT_PATTERN = (
    r"^(?![\u0000-\u0020\u007F-\u00A0\u1680\u2000-\u200A"
    r"\u2028-\u2029\u202F\u205F\u3000\uFEFF])"
    r"[\s\S]*[^\u0000-\u0020\u007F-\u00A0\u1680\u2000-\u200A"
    r"\u2028-\u2029\u202F\u205F\u3000\uFEFF](?![\s\S])"
)
_CANONICAL_TEXT = re.compile(_CANONICAL_TEXT_PATTERN)
_RELATIVE_PATH_PATTERN = (
    r"^(?![/\u0000-\u0020\u007F-\u00A0\u1680\u2000-\u200A"
    r"\u2028-\u2029\u202F\u205F\u3000\uFEFF])"
    r"(?!.*[\\\u0000-\u001F\u007F-\u00A0\u1680\u2000-\u200A"
    r"\u2028-\u2029\u202F\u205F\u3000\uFEFF])"
    r"(?!.*\x20(?![\s\S]))"
    r"(?!(?:.*/)?\.{1,2}(?:/|(?![\s\S])))"
    r"[^/]+(?:/[^/]+)*(?![\s\S])"
)
_RELATIVE_PATH = re.compile(_RELATIVE_PATH_PATTERN)
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
PUBLICATION_INCOMPLETE_MARKER = ".LAWRAG_PUBLICATION_INCOMPLETE"
_MATERIALIZATION_PUBLISH_STRATEGIES = frozenset(
    {"renameat2", "reserved-directory"}
)
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


def _artifact_identity(
    package_id: str,
    logical_id: str,
    role: str,
) -> tuple[str, str, str]:
    return package_id, logical_id, role


def _qualified_artifact_id(package_id: str, logical_id: str, role: str) -> str:
    """Encode an artifact tuple injectively even when components contain colons."""

    identity = _artifact_identity(package_id, logical_id, role)
    return "artifact-v1:" + _canonical_json(identity).decode("utf-8")


def _identifier(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not _ID.fullmatch(value)
    ):
        raise DatasetContractError(f"invalid {field}: {value!r}")
    return value


def _enum(value: object, allowed: frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise DatasetContractError(f"invalid {field}: {value!r}")
    return value


def _reject_unknown(
    blob: Mapping[str, Any], allowed: frozenset[str], field: str
) -> None:
    unknown = sorted(set(blob) - allowed)
    if unknown:
        raise DatasetContractError(
            f"unknown {field} fields: {', '.join(str(value) for value in unknown)}"
        )


def _relative(value: object, field: str) -> str:
    if not isinstance(value, str) or not _RELATIVE_PATH.fullmatch(value):
        raise DatasetContractError(f"{field} must be a safe relative path: {value!r}")
    return value


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


def _fsync_directory(path: Path, *, mode: int | None = None) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        if mode is not None:
            os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_regular_file(path: Path, *, mode: int | None = None) -> None:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise DatasetContractError(f"cannot fsync non-regular artifact: {path}")
        if mode is not None:
            os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _assert_exact_mode(path: Path, expected: int, *, field: str) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise DatasetContractError(f"cannot inspect {field} permissions: {path}: {exc}") from exc
    actual = stat.S_IMODE(info.st_mode)
    if actual != expected:
        raise DatasetContractError(
            f"restricted materialization {field} has unsafe permissions: "
            f"{path} mode={actual:04o}, expected={expected:04o}"
        )


def _remove_private_staging_tree(
    path: Path,
    *,
    expected_identity: tuple[int, int],
) -> None:
    """Make only the staging inode we created removable, then delete it safely."""

    if not getattr(shutil.rmtree, "avoids_symlink_attacks", False):
        raise DatasetContractError(
            "private staging cleanup requires symlink-safe directory removal"
        )
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise DatasetContractError(
            "private staging cleanup requires no-follow file opens"
        )
    try:
        root_info = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise DatasetContractError(
            f"cannot inspect private staging tree for cleanup: {path}: {exc}"
        ) from exc
    if (
        stat.S_ISLNK(root_info.st_mode)
        or not stat.S_ISDIR(root_info.st_mode)
        or (root_info.st_dev, root_info.st_ino) != expected_identity
    ):
        raise DatasetContractError(
            "refusing to clean a replaced private staging directory"
        )

    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | no_follow
    file_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | no_follow
    pending = [(path, expected_identity)]
    try:
        while pending:
            directory, directory_identity = pending.pop()
            before = directory.lstat()
            if (
                stat.S_ISLNK(before.st_mode)
                or not stat.S_ISDIR(before.st_mode)
                or (before.st_dev, before.st_ino) != directory_identity
            ):
                raise DatasetContractError(
                    "private staging directory changed during cleanup"
                )
            descriptor = os.open(directory, directory_flags)
            try:
                opened = os.fstat(descriptor)
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or _stat_identity(before) != _stat_identity(opened)
                ):
                    raise DatasetContractError(
                        "private staging directory changed before cleanup"
                    )
                os.fchmod(descriptor, 0o700)
                with os.scandir(descriptor) as entries:
                    children = [
                        (entry.name, entry.stat(follow_symlinks=False))
                        for entry in entries
                    ]
            finally:
                os.close(descriptor)

            for name, child_info in children:
                child = directory / name
                if stat.S_ISDIR(child_info.st_mode):
                    pending.append(
                        (child, (child_info.st_dev, child_info.st_ino))
                    )
                elif stat.S_ISREG(child_info.st_mode):
                    descriptor = os.open(child, file_flags)
                    try:
                        opened = os.fstat(descriptor)
                        if (
                            not stat.S_ISREG(opened.st_mode)
                            or _stat_identity(child_info) != _stat_identity(opened)
                        ):
                            raise DatasetContractError(
                                "private staging file changed before cleanup"
                            )
                        os.fchmod(descriptor, 0o600)
                    finally:
                        os.close(descriptor)

        current = path.lstat()
        if (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or (current.st_dev, current.st_ino) != expected_identity
        ):
            raise DatasetContractError(
                "private staging root changed before removal"
            )
        shutil.rmtree(path)
    except DatasetContractError:
        raise
    except OSError as exc:
        raise DatasetContractError(
            f"cannot safely remove private staging tree {path}: {exc}"
        ) from exc


def _publication_sidecar(path: Path) -> Path:
    return path.parent / f".{path.name}{PUBLICATION_INCOMPLETE_MARKER}"


def _is_reserved_publication_name(name: str) -> bool:
    return name == PUBLICATION_INCOMPLETE_MARKER or (
        name.startswith(".") and name.endswith(PUBLICATION_INCOMPLETE_MARKER)
    )


def _entry_exists_no_follow(path: Path, *, field: str) -> bool:
    """Return whether one directory entry exists without following its leaf."""

    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise DatasetContractError(f"cannot inspect {field}: {path}: {exc}") from exc
    return True


def _materialization_markers(
    path: Path,
    *,
    trusted_root: Path | None = None,
) -> tuple[Path, ...]:
    """Find target and ancestor readiness markers without following marker leaves."""

    markers: set[Path] = set()
    if trusted_root is None:
        ancestors = (path,)
    else:
        try:
            relative = path.relative_to(trusted_root)
        except ValueError as exc:
            raise DatasetContractError(
                "materialization marker inspection escapes trusted_root"
            ) from exc
        current = trusted_root
        ancestor_rows: list[Path] = []
        for part in relative.parts:
            current = current / part
            ancestor_rows.append(current)
        ancestors = tuple(ancestor_rows)

    for ancestor in ancestors:
        for marker in (
            _publication_sidecar(ancestor),
            ancestor / PUBLICATION_INCOMPLETE_MARKER,
        ):
            if _entry_exists_no_follow(marker, field="materialization marker"):
                markers.add(marker)

    try:
        path_info = path.lstat()
    except FileNotFoundError:
        return tuple(sorted(markers, key=lambda value: os.fsencode(str(value))))
    except OSError as exc:
        raise DatasetContractError(
            f"cannot inspect materialization readiness: {path}: {exc}"
        ) from exc
    if stat.S_ISLNK(path_info.st_mode) or not stat.S_ISDIR(path_info.st_mode):
        return tuple(sorted(markers, key=lambda value: os.fsencode(str(value))))
    pending = [path]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise DatasetContractError(
                f"cannot inspect materialization readiness: {directory}: {exc}"
            ) from exc
        for entry in entries:
            child = Path(entry.path)
            if _is_reserved_publication_name(entry.name):
                markers.add(child)
                continue
            try:
                entry_info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise DatasetContractError(
                    f"cannot inspect materialization member: {child}: {exc}"
                ) from exc
            if stat.S_ISDIR(entry_info.st_mode):
                pending.append(child)
    return tuple(sorted(markers, key=lambda value: os.fsencode(str(value))))


def _assert_materialization_ready(
    path: Path,
    *,
    trusted_root: Path | None = None,
) -> None:
    markers = _materialization_markers(path, trusted_root=trusted_root)
    if markers:
        raise DatasetContractError(
            "materialized SourceSet has an incomplete publication marker: "
            + ", ".join(str(marker) for marker in markers)
        )
    try:
        path_info = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise DatasetContractError(
            f"cannot inspect materialization readiness: {path}: {exc}"
        ) from exc
    if stat.S_ISLNK(path_info.st_mode):
        raise DatasetContractError("materialized SourceSet path is a symlink")
    if not stat.S_ISDIR(path_info.st_mode):
        raise DatasetContractError("materialized SourceSet path is not a directory")
    pending = [path]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise DatasetContractError(
                f"cannot inspect materialization readiness: {directory}: {exc}"
            ) from exc
        for entry in entries:
            child = Path(entry.path)
            if _is_reserved_publication_name(entry.name):
                raise DatasetContractError(
                    f"materialized SourceSet has an incomplete publication marker: {child}"
                )
            if entry.is_symlink():
                raise DatasetContractError(
                    f"materialized SourceSet contains a symlink: {child}"
                )
            try:
                if entry.is_dir(follow_symlinks=False):
                    pending.append(child)
            except OSError as exc:
                raise DatasetContractError(
                    f"cannot inspect materialization member: {child}: {exc}"
                ) from exc


def _trusted_materialization_destination(
    destination: str | Path,
    trusted_root: str | Path | None,
) -> tuple[Path, Path]:
    """Validate a lexical destination below an explicit, non-symlink root."""

    if trusted_root is None:
        raise DatasetContractError("materialization requires an explicit trusted_root")
    raw_root = Path(trusted_root)
    if not raw_root.is_absolute():
        raise DatasetContractError("trusted_root must be an absolute path")
    if any(part in {".", ".."} for part in raw_root.parts):
        raise DatasetContractError("trusted_root must be a canonical absolute path")
    try:
        root_info = raw_root.lstat()
    except OSError as exc:
        raise DatasetContractError(f"trusted_root is unavailable: {raw_root}: {exc}") from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise DatasetContractError("trusted_root must be an existing non-symlink directory")
    # Reject a symlink at any existing ancestor, including ancestors above the
    # trusted root.  This makes the caller's trust boundary explicit rather than
    # silently accepting Path.resolve() redirection.
    anchor = Path(raw_root.anchor)
    current = anchor
    for part in raw_root.parts[1:]:
        current = current / part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise DatasetContractError(f"trusted_root traverses a symlink: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise DatasetContractError(f"trusted_root ancestor is not a directory: {current}")
    root = raw_root

    raw_destination = Path(destination)
    candidate = raw_destination if raw_destination.is_absolute() else root / raw_destination
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise DatasetContractError("materialization destination escapes trusted_root") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise DatasetContractError("materialization destination must be below trusted_root")
    current = root
    for position, part in enumerate(relative.parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(info.st_mode):
            raise DatasetContractError(
                f"materialization destination traverses a symlink: {current}"
            )
        if position < len(relative.parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise DatasetContractError(
                f"materialization destination parent is not a directory: {current}"
            )
    return root, candidate


def _ensure_trusted_directory_chain(root: Path, relative_parent: Path) -> Path:
    current = root
    for part in relative_parent.parts:
        if part in {"", ".", ".."}:
            raise DatasetContractError("materialization parent is not canonical")
        candidate = current / part
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            try:
                os.mkdir(candidate, 0o755)
            except FileExistsError:
                pass
            _fsync_directory(current)
            info = candidate.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise DatasetContractError(
                f"materialization parent is not a safe directory: {candidate}"
            )
        current = candidate
    return current


def _rename_reserved_directory_preserving_mode(source: Path, target: Path) -> None:
    """Reparent one sealed directory while restoring its exact mode.

    Linux requires write permission on a directory whose ``..`` entry changes
    during reparenting.  Restricted SourceSet directories are already sealed
    read-only in staging, so the reserved-directory fallback grants owner write
    only while both publication markers make the target unreadable to serving.
    An open no-follow directory descriptor binds permission changes to the same
    inode before and after rename.
    """

    try:
        before = source.lstat()
    except OSError as exc:
        raise DatasetContractError(
            f"cannot inspect reserved SourceSet directory: {source}: {exc}"
        ) from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        raise DatasetContractError(
            f"reserved SourceSet child is not a directory: {source}"
        )
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise DatasetContractError(
            "reserved SourceSet directory reparenting requires no-follow opens"
        )
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | no_follow
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise DatasetContractError(
            f"cannot open reserved SourceSet directory: {source}: {exc}"
        ) from exc

    original_mode: int | None = None
    primary_error: BaseException | None = None
    restore_error: BaseException | None = None
    moved = False
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise DatasetContractError(
                "reserved SourceSet directory changed before reparenting"
            )
        original_mode = stat.S_IMODE(opened.st_mode)
        writable_mode = original_mode | stat.S_IWUSR
        if writable_mode != original_mode:
            os.fchmod(descriptor, writable_mode)
            os.fsync(descriptor)
        os.rename(source, target)
        moved = True
        moved_info = target.lstat()
        if (
            not stat.S_ISDIR(moved_info.st_mode)
            or (moved_info.st_dev, moved_info.st_ino)
            != (opened.st_dev, opened.st_ino)
        ):
            raise DatasetContractError(
                "reserved SourceSet directory changed while reparenting"
            )
    except BaseException as exc:
        primary_error = exc
    finally:
        try:
            if original_mode is not None:
                current = os.fstat(descriptor)
                if (
                    not stat.S_ISDIR(current.st_mode)
                    or (current.st_dev, current.st_ino)
                    != (before.st_dev, before.st_ino)
                ):
                    raise DatasetContractError(
                        "reserved SourceSet directory changed before mode restore"
                    )
                if stat.S_IMODE(current.st_mode) != original_mode:
                    os.fchmod(descriptor, original_mode)
                os.fsync(descriptor)
        except BaseException as exc:
            restore_error = exc
        finally:
            os.close(descriptor)

    if restore_error is not None:
        detail = (
            f" after {primary_error}" if primary_error is not None else ""
        )
        raise DatasetContractError(
            "cannot restore reserved SourceSet directory permissions"
            f"{detail}: {restore_error}"
        ) from restore_error
    if primary_error is not None:
        raise primary_error
    if not moved or original_mode is None:
        raise DatasetContractError("reserved SourceSet directory was not reparented")
    try:
        final_info = target.lstat()
    except OSError as exc:
        raise DatasetContractError(
            f"cannot inspect reparented SourceSet directory: {target}: {exc}"
        ) from exc
    if (
        not stat.S_ISDIR(final_info.st_mode)
        or (final_info.st_dev, final_info.st_ino) != (before.st_dev, before.st_ino)
        or stat.S_IMODE(final_info.st_mode) != original_mode
    ):
        raise DatasetContractError(
            "reparented SourceSet directory did not retain its identity and mode"
        )


def _atomic_publish_directory_no_replace(
    staging: Path,
    target: Path,
    *,
    prepare_receipt: Callable[[str], None],
) -> str:
    """Publish a SourceSet with an atomic no-clobber readiness boundary."""

    if os.name != "posix":
        raise DatasetContractError("atomic SourceSet publish requires a POSIX host")
    _assert_materialization_ready(staging)
    if _publication_sidecar(target).exists() or _publication_sidecar(target).is_symlink():
        raise DatasetContractError(
            f"SourceSet target has an incomplete publication marker: {_publication_sidecar(target)}"
        )
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
        prepare_receipt("renameat2")
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
            raise DatasetContractError(
                f"atomic SourceSet publish failed: {os.strerror(error_number)}"
            )

    prepare_receipt("reserved-directory")
    sidecar = _publication_sidecar(target)
    sidecar_descriptor: int | None = None
    try:
        sidecar_descriptor = os.open(
            sidecar,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.write(sidecar_descriptor, b"source-set-materialization-v2\n")
        os.fsync(sidecar_descriptor)
    except FileExistsError as exc:
        raise DatasetContractError(f"SourceSet target is already reserved: {sidecar}") from exc
    finally:
        if sidecar_descriptor is not None:
            os.close(sidecar_descriptor)
    _fsync_directory(target.parent)
    try:
        target.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise DatasetContractError(
            f"reserved SourceSet target appeared concurrently and is retained: {target}"
        ) from exc
    marker = target / PUBLICATION_INCOMPLETE_MARKER
    descriptor = os.open(
        marker,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.write(descriptor, b"source-set-materialization-v2\n")
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
            child_info = child.lstat()
            if stat.S_ISDIR(child_info.st_mode):
                _rename_reserved_directory_preserving_mode(
                    child, target / child.name
                )
            else:
                os.rename(child, target / child.name)
        _fsync_directory(target)
        marker.unlink()
        _fsync_directory(target)
        sidecar.unlink()
        _fsync_directory(target.parent)
        staging.rmdir()
        return "reserved-directory"
    except Exception as exc:
        raise DatasetContractError(
            "reserved SourceSet target is incomplete and retained with its "
            f"readiness marker: {target}: {exc}"
        ) from exc


def _checked_directory_root(root: str | Path, *, field: str) -> Path:
    absolute = Path(os.path.abspath(os.fspath(root)))
    if not absolute.is_absolute():
        raise DatasetContractError(f"{field} must be absolute")
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except OSError as exc:
            raise DatasetContractError(f"cannot inspect {field}: {current}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise DatasetContractError(f"{field} traverses a symlink: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise DatasetContractError(f"{field} is not a directory: {current}")
    return absolute


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
    package_root = _checked_directory_root(root, field=f"{field} root")
    candidate = package_root
    for part in PurePosixPath(safe).parts:
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
    document_id: str | None = None

    @property
    def logical_key(self) -> tuple[str, str]:
        return self.logical_id, self.role

    @property
    def identity_key(self) -> tuple[str, str, str]:
        return _artifact_identity(self.package_id, self.logical_id, self.role)

    @property
    def provenance_key(self) -> tuple[str, str, str, str]:
        return self.package_id, self.dataset_id, self.version_id, self.build_id

    @property
    def qualified_id(self) -> str:
        return _qualified_artifact_id(*self.identity_key)

    def resolved_path(self) -> Path | None:
        if self.base_path is None:
            return None
        return _resolve_contained(
            self.base_path,
            self.path,
            field=f"artifact {self.qualified_id} path",
            require_file=True,
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

    @property
    def provenance_key(self) -> tuple[str, str, str, str]:
        return self.package_id, self.dataset_id, self.version_id, self.build_id

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
    dataset_id: str
    version_id: str
    build_id: str
    manifest_sha256: str
    priority: int

    @property
    def provenance_key(self) -> tuple[str, str, str, str]:
        return self.package_id, self.dataset_id, self.version_id, self.build_id

    def receipt(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "dataset_id": self.dataset_id,
            "version_id": self.version_id,
            "build_id": self.build_id,
            "manifest_sha256": self.manifest_sha256,
            "priority": self.priority,
        }


@dataclass(frozen=True)
class SourceSetArtifactLock:
    package_id: str
    dataset_id: str
    version_id: str
    build_id: str
    manifest_sha256: str
    logical_id: str
    role: str
    path: str
    sha256: str
    contributors: tuple[str, ...]
    document_id: str | None = None

    @property
    def identity_key(self) -> tuple[str, str, str]:
        return _artifact_identity(self.package_id, self.logical_id, self.role)

    @property
    def provenance_key(self) -> tuple[str, str, str, str]:
        return self.package_id, self.dataset_id, self.version_id, self.build_id

    @property
    def qualified_id(self) -> str:
        return _qualified_artifact_id(*self.identity_key)

    def receipt(self) -> dict[str, Any]:
        receipt: dict[str, Any] = {
            "package_id": self.package_id,
            "dataset_id": self.dataset_id,
            "version_id": self.version_id,
            "build_id": self.build_id,
            "manifest_sha256": self.manifest_sha256,
            "logical_id": self.logical_id,
            "role": self.role,
            "path": self.path,
            "sha256": self.sha256,
            "contributors": list(self.contributors),
        }
        if self.document_id is not None:
            receipt["document_id"] = self.document_id
        return receipt


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


def source_set_lock_from_mapping(blob: Mapping[str, Any]) -> SourceSetLock:
    """Parse a persisted SourceSet lock without accepting partial/extra fields.

    A serving process must not rebuild a lock from mutable package discovery.  It
    receives the exact lock named by the release authority, parses every field,
    and then rederives both the lock and SourceSet content hashes before use.
    Installed package bytes are checked separately by
    :meth:`InstalledCatalog.resolve_lock`.
    """

    if not isinstance(blob, Mapping):
        raise DatasetContractError("SourceSet lock root must be an object")
    _reject_unknown(
        blob,
        frozenset(
            {
                "schema_version",
                "source_set_id",
                "generation_id",
                "source_set_sha256",
                "conflict_policy",
                "cross_dataset_relations",
                "export_allowed",
                "members",
                "artifacts",
                "lock_sha256",
            }
        ),
        "SourceSet lock",
    )
    if blob.get("schema_version") != SOURCE_SET_LOCK_SCHEMA:
        raise DatasetContractError("unsupported SourceSet lock schema")

    raw_cross = blob.get("cross_dataset_relations")
    raw_export = blob.get("export_allowed")
    if not isinstance(raw_cross, bool):
        raise DatasetContractError("cross_dataset_relations must be boolean")
    if not isinstance(raw_export, bool):
        raise DatasetContractError("export_allowed must be boolean")

    raw_members = blob.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        raise DatasetContractError("SourceSet lock members must be a non-empty list")
    members: list[SourceSetLockMember] = []
    for position, value in enumerate(raw_members):
        if not isinstance(value, Mapping):
            raise DatasetContractError(f"members[{position}] must be an object")
        _reject_unknown(
            value,
            frozenset(
                {
                    "package_id",
                    "dataset_id",
                    "version_id",
                    "build_id",
                    "manifest_sha256",
                    "priority",
                }
            ),
            f"members[{position}]",
        )
        priority = value.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise DatasetContractError(f"members[{position}].priority must be integer")
        manifest_sha256 = str(value.get("manifest_sha256") or "")
        if not _SHA256.fullmatch(manifest_sha256):
            raise DatasetContractError(
                f"members[{position}].manifest_sha256 must be SHA-256"
            )
        members.append(
            SourceSetLockMember(
                package_id=_identifier(
                    value.get("package_id"), f"members[{position}].package_id"
                ),
                dataset_id=_identifier(
                    value.get("dataset_id"), f"members[{position}].dataset_id"
                ),
                version_id=_identifier(
                    value.get("version_id"), f"members[{position}].version_id"
                ),
                build_id=_identifier(
                    value.get("build_id"), f"members[{position}].build_id"
                ),
                manifest_sha256=manifest_sha256,
                priority=priority,
            )
        )

    raw_artifacts = blob.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise DatasetContractError("SourceSet lock artifacts must be a non-empty list")
    artifacts: list[SourceSetArtifactLock] = []
    for position, value in enumerate(raw_artifacts):
        if not isinstance(value, Mapping):
            raise DatasetContractError(f"artifacts[{position}] must be an object")
        _reject_unknown(
            value,
            frozenset(
                {
                    "package_id",
                    "dataset_id",
                    "version_id",
                    "build_id",
                    "manifest_sha256",
                    "logical_id",
                    "role",
                    "path",
                    "sha256",
                    "contributors",
                    "document_id",
                }
            ),
            f"artifacts[{position}]",
        )
        manifest_sha256 = str(value.get("manifest_sha256") or "")
        artifact_sha256 = str(value.get("sha256") or "")
        if not _SHA256.fullmatch(manifest_sha256):
            raise DatasetContractError(
                f"artifacts[{position}].manifest_sha256 must be SHA-256"
            )
        if not _SHA256.fullmatch(artifact_sha256):
            raise DatasetContractError(f"artifacts[{position}].sha256 must be SHA-256")
        raw_contributors = value.get("contributors")
        if not isinstance(raw_contributors, list) or not raw_contributors:
            raise DatasetContractError(
                f"artifacts[{position}].contributors must be a non-empty list"
            )
        contributors = tuple(
            _identifier(item, f"artifacts[{position}].contributors")
            for item in raw_contributors
        )
        if len(contributors) != len(set(contributors)) or tuple(sorted(contributors)) != contributors:
            raise DatasetContractError(
                f"artifacts[{position}].contributors must be unique and sorted"
            )
        raw_document = value.get("document_id")
        artifacts.append(
            SourceSetArtifactLock(
                package_id=_identifier(
                    value.get("package_id"), f"artifacts[{position}].package_id"
                ),
                dataset_id=_identifier(
                    value.get("dataset_id"), f"artifacts[{position}].dataset_id"
                ),
                version_id=_identifier(
                    value.get("version_id"), f"artifacts[{position}].version_id"
                ),
                build_id=_identifier(
                    value.get("build_id"), f"artifacts[{position}].build_id"
                ),
                manifest_sha256=manifest_sha256,
                logical_id=_identifier(
                    value.get("logical_id"), f"artifacts[{position}].logical_id"
                ),
                role=_enum(
                    value.get("role"), _ARTIFACT_ROLES, f"artifacts[{position}].role"
                ),
                path=_relative(value.get("path"), f"artifacts[{position}].path"),
                sha256=artifact_sha256,
                contributors=contributors,
                document_id=(
                    _identifier(raw_document, f"artifacts[{position}].document_id")
                    if raw_document is not None
                    else None
                ),
            )
        )

    source_set_sha256 = str(blob.get("source_set_sha256") or "")
    lock_sha256 = str(blob.get("lock_sha256") or "")
    if not _SHA256.fullmatch(source_set_sha256):
        raise DatasetContractError("source_set_sha256 must be SHA-256")
    if not _SHA256.fullmatch(lock_sha256):
        raise DatasetContractError("lock_sha256 must be SHA-256")
    lock = SourceSetLock(
        source_set_id=_identifier(blob.get("source_set_id"), "source_set_id"),
        generation_id=_identifier(blob.get("generation_id"), "generation_id"),
        source_set_sha256=source_set_sha256,
        conflict_policy=_enum(
            blob.get("conflict_policy"), _CONFLICT_POLICIES, "conflict_policy"
        ),
        cross_dataset_relations=raw_cross,
        export_allowed=raw_export,
        members=tuple(members),
        artifacts=tuple(artifacts),
        lock_sha256=lock_sha256,
    )
    _validate_source_set_lock(lock)
    if lock.receipt() != dict(blob):
        raise DatasetContractError("SourceSet lock is not in canonical complete form")
    return lock


def load_source_set_lock(
    path: str | Path,
    *,
    expected_artifact_sha256: str | None = None,
) -> SourceSetLock:
    """Load and strictly authenticate a persisted SourceSet lock document."""

    source_path = Path(path)
    if expected_artifact_sha256 is not None:
        if not _SHA256.fullmatch(expected_artifact_sha256):
            raise DatasetContractError(
                "expected SourceSet lock artifact hash must be SHA-256"
            )
        if _hash_file(source_path) != expected_artifact_sha256:
            raise DatasetContractError("SourceSet lock artifact hash mismatch")
    try:
        blob = json.loads(source_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetContractError(
            f"cannot read SourceSet lock {source_path}: {exc}"
        ) from exc
    if not isinstance(blob, Mapping):
        raise DatasetContractError("SourceSet lock root must be an object")
    return source_set_lock_from_mapping(blob)


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


def _assert_artifact_package_provenance(
    artifact: Artifact,
    package: DatasetPackage,
) -> None:
    if artifact.provenance_key != package.provenance_key:
        raise DatasetContractError(
            f"artifact provenance does not match package manifest: {artifact.qualified_id}"
        )


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
    ) -> DatasetPackage:
        """Resolve one installed package and always revalidate its artifact bytes.

        InstalledCatalog is the serving boundary.  Manifest-only inspection remains
        available through ``load_package(..., verify_files=False)`` to authoring
        tools, but a serving caller cannot disable live content verification here.
        """

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
        package = load_package(target, verify_files=True)
        if package.package_id != expected_id:
            raise DatasetContractError(
                f"installed manifest package_id mismatch: {expected_id}"
            )
        if package.manifest_sha256 != manifest_sha256:
            raise DatasetContractError(
                f"installed manifest content mismatch: {expected_id}"
            )
        return package

    def open(self, source_set: Mapping[str, Any]) -> UnifiedCorpusView:
        """Compose caller-supplied policy for authoring or untrusted inspection.

        This method verifies installed package bytes but does not authenticate the
        caller's SourceSet policy.  Serving admission must use ``resolve_lock``
        with both expected hashes obtained from an independent trusted authority.
        """

        members = _source_set_members(source_set)
        packages = []
        for member in members:
            registration = self.registration(member.package_id)
            packages.append(
                self.lookup(
                    registration.package_id,
                    registration.manifest_sha256,
                )
            )
        return compose_source_set(source_set, packages)

    def resolve_lock(
        self,
        lock: SourceSetLock,
        *,
        expected_source_set_sha256: str,
        expected_lock_sha256: str,
    ) -> tuple[DatasetPackage, ...]:
        """Admit one serving lock against independently trusted exact hashes."""

        if (
            not isinstance(expected_source_set_sha256, str)
            or not _SHA256.fullmatch(expected_source_set_sha256)
        ):
            raise DatasetContractError(
                "expected_source_set_sha256 must be an exact lowercase SHA-256"
            )
        if (
            not isinstance(expected_lock_sha256, str)
            or not _SHA256.fullmatch(expected_lock_sha256)
        ):
            raise DatasetContractError(
                "expected_lock_sha256 must be an exact lowercase SHA-256"
            )
        if lock.source_set_sha256 != expected_source_set_sha256:
            raise DatasetContractError(
                "SourceSet identity does not match trusted serving authority"
            )
        if lock.lock_sha256 != expected_lock_sha256:
            raise DatasetContractError(
                "SourceSet lock does not match trusted serving authority"
            )

        _validate_source_set_lock(lock)
        packages = tuple(
            self.lookup(
                member.package_id,
                member.manifest_sha256,
            )
            for member in lock.members
        )
        _validate_source_set_lock_packages(lock, packages)
        return packages

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
    trusted_root: Path | None = None

    def _verified_artifact_record(
        self,
        qualified_id: str,
    ) -> tuple[MaterializedSourceSet, SourceSetArtifactLock, Mapping[str, Any]]:
        current = _verify_materialized_source_set(
            self.path,
            self.lock,
            trusted_root=self.trusted_root,
        )
        locked = [
            artifact
            for artifact in current.lock.artifacts
            if artifact.qualified_id == qualified_id
        ]
        matches = [
            row
            for row in current.receipt.get("artifacts", [])
            if isinstance(row, Mapping) and row.get("qualified_id") == qualified_id
        ]
        if len(locked) != 1 or len(matches) != 1:
            raise DatasetContractError(
                f"materialized artifact is missing or ambiguous: {qualified_id}"
            )
        return current, locked[0], matches[0]

    def verified_artifact_path(self, qualified_id: str) -> Path:
        """Return an artifact path only after revalidating the complete tree."""

        current, _locked, row = self._verified_artifact_record(qualified_id)
        relative = _relative(row.get("materialized_path"), "materialized_path")
        return _resolve_contained(
            current.path,
            relative,
            field=f"materialized artifact {qualified_id}",
            require_file=True,
        )

    def verified_artifact_paths(self) -> dict[str, Path]:
        """Return the complete qualified-ID map after one full-tree validation.

        Consumers loading a complete corpus must not call
        ``verified_artifact_path`` in a loop (which would validate N slightly
        different filesystem moments).  This method validates one materialized
        tree, then resolves every path from that same receipt snapshot.
        """

        current = _verify_materialized_source_set(
            self.path,
            self.lock,
            trusted_root=self.trusted_root,
        )
        rows = current.receipt.get("artifacts")
        if not isinstance(rows, list) or len(rows) != len(current.lock.artifacts):
            raise DatasetContractError("materialized artifact set is incomplete")
        resolved: dict[str, Path] = {}
        for locked, row in zip(current.lock.artifacts, rows):
            if not isinstance(row, Mapping) or row.get("qualified_id") != locked.qualified_id:
                raise DatasetContractError(
                    f"materialized artifact order mismatch: {locked.qualified_id}"
                )
            relative = _relative(row.get("materialized_path"), "materialized_path")
            target = _resolve_contained(
                current.path,
                relative,
                field=f"materialized artifact {locked.qualified_id}",
                require_file=True,
            )
            if locked.qualified_id in resolved:
                raise DatasetContractError(
                    f"materialized artifact is ambiguous: {locked.qualified_id}"
                )
            resolved[locked.qualified_id] = target
        if set(resolved) != {row.qualified_id for row in current.lock.artifacts}:
            raise DatasetContractError("materialized artifact map is incomplete")
        return resolved

    def verified_artifact_provenance(self, qualified_id: str) -> dict[str, Any]:
        """Return manifest-bound coordinates after revalidating the complete tree."""

        _current, locked, _row = self._verified_artifact_record(qualified_id)
        return {
            "qualified_id": locked.qualified_id,
            "package_id": locked.package_id,
            "dataset_id": locked.dataset_id,
            "version_id": locked.version_id,
            "build_id": locked.build_id,
            "manifest_sha256": locked.manifest_sha256,
            "logical_id": locked.logical_id,
            "role": locked.role,
            "source_path": locked.path,
            "sha256": locked.sha256,
            "contributors": list(locked.contributors),
            "document_id": locked.document_id,
        }


@dataclass(frozen=True)
class MaterializationInspection:
    path: Path
    exists: bool
    ready: bool
    marker_paths: tuple[Path, ...]
    issue: str | None

    def receipt(self) -> dict[str, Any]:
        return {
            "schema_version": "source-set-materialization-inspection-v1",
            "path": str(self.path),
            "exists": self.exists,
            "ready": self.ready,
            "marker_paths": [str(path) for path in self.marker_paths],
            "issue": self.issue,
            "mutates_storage": False,
        }


@dataclass(frozen=True)
class MaterializationQuarantinePlan:
    source: Path
    quarantine_target: Path
    inspection: MaterializationInspection

    def receipt(self) -> dict[str, Any]:
        return {
            "schema_version": "source-set-materialization-quarantine-plan-v1",
            "source": str(self.source),
            "quarantine_target": str(self.quarantine_target),
            "inspection": self.inspection.receipt(),
            "operation": "operator-reviewed-source-and-marker-move-no-replace",
            "executed": False,
        }


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
        Path(os.path.abspath(os.fspath(raw_catalog_path)))
        if raw_catalog_path is not None
        else None
    )
    if package_root is None and resolved_catalog_path is None:
        raise DatasetContractError(
            "installed catalog requires catalog_path or an explicit package_root"
        )
    resolved_root = _checked_directory_root(
        Path(package_root)
        if package_root is not None
        else resolved_catalog_path.parent,  # type: ignore[union-attr]
        field="installed package root",
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
    path: str | Path,
    *,
    package_root: str | Path | None = None,
    expected_artifact_sha256: str | None = None,
) -> InstalledCatalog:
    raw_path = Path(path)
    if raw_path.is_symlink():
        raise DatasetContractError("installed catalog manifest cannot be a symlink")
    catalog_path = Path(os.path.abspath(os.fspath(raw_path)))
    _checked_directory_root(catalog_path.parent, field="installed catalog parent")
    if expected_artifact_sha256 is not None:
        if not _SHA256.fullmatch(expected_artifact_sha256):
            raise DatasetContractError(
                "expected installed catalog artifact hash must be SHA-256"
            )
        if _hash_file(catalog_path) != expected_artifact_sha256:
            raise DatasetContractError("installed catalog artifact hash mismatch")
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
    code_revision = build.get("code_revision")
    compiler_profile = build.get("compiler_profile")
    if (
        not isinstance(code_revision, str)
        or not _CANONICAL_TEXT.fullmatch(code_revision)
        or not isinstance(compiler_profile, str)
        or not _CANONICAL_TEXT.fullmatch(compiler_profile)
    ):
        raise DatasetContractError(
            "build code_revision and compiler_profile must be non-empty canonical strings"
        )
    raw_capabilities = build.get("capabilities")
    if not isinstance(raw_capabilities, list):
        raise DatasetContractError("build.capabilities must be a list")
    capability_rows = tuple(_identifier(v, "capability") for v in raw_capabilities)
    if len(capability_rows) != len(set(capability_rows)):
        raise DatasetContractError("build.capabilities must not contain duplicates")
    capabilities = tuple(sorted(capability_rows))

    raw_source_path = Path(manifest_path) if manifest_path is not None else None
    if raw_source_path is not None and raw_source_path.is_symlink():
        raise DatasetContractError("dataset package manifest cannot be a symlink")
    source_path = (
        Path(os.path.abspath(os.fspath(raw_source_path)))
        if raw_source_path is not None
        else None
    )
    if source_path is not None:
        _checked_directory_root(source_path.parent, field="dataset package root")
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
            frozenset(
                {
                    "logical_id",
                    "role",
                    "path",
                    "sha256",
                    "media_type",
                    "document_id",
                }
            ),
            f"artifacts[{position}]",
        )
        logical_id = _identifier(row.get("logical_id"), f"artifacts[{position}].logical_id")
        role = _enum(row.get("role"), _ARTIFACT_ROLES, f"artifacts[{position}].role")
        key = (logical_id, role)
        if key in seen:
            raise DatasetContractError(f"duplicate artifact logical key: {key}")
        seen.add(key)
        sha256 = row.get("sha256")
        if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
            raise DatasetContractError(f"invalid artifact sha256 at position {position}")
        document_id = (
            _identifier(
                row.get("document_id"), f"artifacts[{position}].document_id"
            )
            if row.get("document_id") is not None
            else None
        )
        if "media_type" not in row:
            media_type = "application/octet-stream"
        else:
            raw_media_type = row.get("media_type")
            if not isinstance(raw_media_type, str) or not raw_media_type:
                raise DatasetContractError(
                    f"artifacts[{position}].media_type must be a non-empty string"
                )
            media_type = raw_media_type
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
                media_type=media_type,
                base_path=base_path,
                document_id=document_id,
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
    manifest_path = Path(os.path.abspath(os.fspath(raw_manifest_path)))
    _checked_directory_root(manifest_path.parent, field="dataset package root")
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
    manifest_path = Path(os.path.abspath(os.fspath(raw_manifest)))
    _checked_directory_root(manifest_path.parent, field="legacy manifest parent")
    install_root = (
        _checked_directory_root(root, field="legacy install root")
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
        document_id = _identifier(
            item.get("doc_id"), f"legacy items[{item_position}].doc_id"
        )
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
        normalized_contract_roles = {str(value) for value in contract_roles}
        if not {"primary", "structure"}.issubset(normalized_contract_roles):
            raise DatasetContractError(
                "legacy item contract must include primary and structure roles: "
                f"{logical_id}"
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
                structure_names.add(PurePosixPath(member_path).name)
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
                    "document_id": document_id,
                }
            )
        if not {"meta.json", "result.json"}.issubset(structure_names):
            raise DatasetContractError(
                f"legacy structure must bind meta.json and result.json: {logical_id}"
            )
        if observed_roles != normalized_contract_roles:
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
            _assert_artifact_package_provenance(artifact, package)
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
                "dataset_id": package.dataset_id,
                "version_id": package.version_id,
                "build_id": package.build_id,
                "priority": member.priority,
                "manifest_sha256": package.manifest_sha256,
            }
            for member, package in selected
        ],
        "artifacts": [
            {
                "qualified_id": item.selected.qualified_id,
                "package_id": item.selected.package_id,
                "dataset_id": item.selected.dataset_id,
                "version_id": item.selected.version_id,
                "build_id": item.selected.build_id,
                "manifest_sha256": available[
                    item.selected.package_id
                ].manifest_sha256,
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


def _build_source_set_lock(view: UnifiedCorpusView) -> SourceSetLock:
    """Build a lock from an already composed view without recursive validation."""

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
                dataset_id=package.dataset_id,
                version_id=package.version_id,
                build_id=package.build_id,
                manifest_sha256=package.manifest_sha256,
                priority=member.priority,
            )
        )
    locked_artifact_rows: list[SourceSetArtifactLock] = []
    for item in view.artifacts:
        artifact = item.selected
        package = packages.get(artifact.package_id)
        if package is None:
            raise DatasetContractError(
                f"SourceSet artifact package is absent from view: {artifact.package_id}"
            )
        _assert_artifact_package_provenance(artifact, package)
        locked_artifact_rows.append(
            SourceSetArtifactLock(
                package_id=artifact.package_id,
                dataset_id=artifact.dataset_id,
                version_id=artifact.version_id,
                build_id=artifact.build_id,
                manifest_sha256=package.manifest_sha256,
                logical_id=artifact.logical_id,
                role=artifact.role,
                path=artifact.path,
                sha256=artifact.sha256,
                contributors=item.contributors,
                document_id=artifact.document_id,
            )
        )
    locked_artifacts = tuple(locked_artifact_rows)
    source_identity = {
        "source_set_id": view.source_set_id,
        "generation_id": view.generation_id,
        "conflict_policy": view.conflict_policy,
        "cross_dataset_relations": view.cross_dataset_relations,
        "members": [member.receipt() for member in locked_members],
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


def lock_source_set(view: UnifiedCorpusView) -> SourceSetLock:
    """Freeze and rederive the exact package selection before returning a lock."""

    lock = _build_source_set_lock(view)
    _validate_source_set_lock_packages(lock, view.packages)
    return lock


def _validate_runtime_policy(
    view: UnifiedCorpusView,
    *,
    for_export: bool,
    relation_policy_enforced: bool,
    allow_cross_dataset_relations: bool,
) -> None:
    # Retained only for call compatibility.  Caller-supplied booleans are not a
    # cryptographic runtime capability and therefore cannot change the policy
    # hashed into the SourceSet itself.
    _ = (relation_policy_enforced, allow_cross_dataset_relations)
    if for_export and not view.export_allowed:
        raise DatasetContractError("restricted SourceSet cannot be exported")
    if view.conflict_policy == "keep_namespaced":
        raise DatasetContractError(
            "keep_namespaced is unsafe until runtime coordinates are namespace-aware"
        )
    # The v2 serving adapter preserves dataset provenance per document and
    # enforces ``cross_dataset_relations`` from the immutable lock.  Mixed
    # external/internal packages are therefore a supported logical union, but
    # their retrievable coordinates must remain globally unambiguous.
    structure_rows = [
        item.selected for item in view.artifacts if item.selected.role == "structure"
    ]
    if any(row.document_id is None for row in structure_rows):
        raise DatasetContractError(
            "runtime structure artifacts require document_id"
        )
    document_packages: dict[str, set[str]] = {}
    for row in structure_rows:
        assert row.document_id is not None
        document_packages.setdefault(row.document_id, set()).add(row.package_id)
    if any(len(packages) != 1 for packages in document_packages.values()):
        raise DatasetContractError(
            "runtime structure document IDs cannot collide across packages"
        )


def _materialized_artifact_path(
    position: int, artifact: SourceSetArtifactLock
) -> str:
    suffix = PurePosixPath(artifact.path).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix):
        suffix = ""
    return f"ARTIFACTS/{position:08d}-{artifact.sha256[:16]}{suffix}"


def _validate_source_set_lock(lock: SourceSetLock) -> None:
    receipt = lock.receipt()
    core = dict(receipt)
    declared = str(core.pop("lock_sha256", ""))
    if not _SHA256.fullmatch(declared) or _digest(core) != declared:
        raise DatasetContractError("SourceSet lock hash is invalid")
    if not _SHA256.fullmatch(lock.source_set_sha256):
        raise DatasetContractError("SourceSet identity hash is invalid")
    member_ids = [member.package_id for member in lock.members]
    if not member_ids or len(member_ids) != len(set(member_ids)):
        raise DatasetContractError("SourceSet lock members are empty or duplicated")
    members_by_id = {member.package_id: member for member in lock.members}
    artifact_keys = [artifact.identity_key for artifact in lock.artifacts]
    if not artifact_keys or len(artifact_keys) != len(set(artifact_keys)):
        raise DatasetContractError("SourceSet lock artifacts are empty or duplicated")
    artifact_ids = [artifact.qualified_id for artifact in lock.artifacts]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise DatasetContractError("SourceSet artifact identity encoding is ambiguous")
    if any(
        not _SHA256.fullmatch(member.manifest_sha256) for member in lock.members
    ) or any(
        not _SHA256.fullmatch(artifact.sha256)
        or not _SHA256.fullmatch(artifact.manifest_sha256)
        for artifact in lock.artifacts
    ):
        raise DatasetContractError("SourceSet lock contains an invalid content hash")
    for artifact in lock.artifacts:
        member = members_by_id.get(artifact.package_id)
        if (
            member is None
            or artifact.provenance_key != member.provenance_key
            or artifact.manifest_sha256 != member.manifest_sha256
            or artifact.package_id not in artifact.contributors
            or any(contributor not in members_by_id for contributor in artifact.contributors)
        ):
            raise DatasetContractError(
                f"SourceSet artifact provenance does not match its member manifest: "
                f"{artifact.qualified_id}"
            )
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
    if _digest(source_identity) != lock.source_set_sha256:
        raise DatasetContractError("SourceSet identity hash does not match its provenance")


def _validate_source_set_lock_packages(
    lock: SourceSetLock,
    packages: Iterable[DatasetPackage],
) -> None:
    """Recompose and cross-check a lock against its exact package manifests."""

    _validate_source_set_lock(lock)
    package_rows = tuple(packages)
    packages_by_id = {package.package_id: package for package in package_rows}
    if len(packages_by_id) != len(package_rows) or set(packages_by_id) != {
        member.package_id for member in lock.members
    }:
        raise DatasetContractError("SourceSet lock package manifests are incomplete")
    for member in lock.members:
        package = packages_by_id[member.package_id]
        if (
            member.provenance_key != package.provenance_key
            or member.manifest_sha256 != package.manifest_sha256
        ):
            raise DatasetContractError(
                f"SourceSet member provenance does not match package manifest: "
                f"{member.package_id}"
            )
        for artifact in package.artifacts:
            _assert_artifact_package_provenance(artifact, package)
    for artifact in lock.artifacts:
        package = packages_by_id[artifact.package_id]
        matches = [
            candidate
            for candidate in package.artifacts
            if candidate.identity_key == artifact.identity_key
        ]
        if len(matches) != 1:
            raise DatasetContractError(
                f"SourceSet artifact is not unique in package manifest: "
                f"{artifact.qualified_id}"
            )
        candidate = matches[0]
        if (
            artifact.provenance_key != candidate.provenance_key
            or artifact.manifest_sha256 != package.manifest_sha256
            or artifact.path != candidate.path
            or artifact.sha256 != candidate.sha256
            or artifact.document_id != candidate.document_id
        ):
            raise DatasetContractError(
                f"SourceSet artifact does not match package manifest: "
                f"{artifact.qualified_id}"
            )

    # A content hash only proves that a lock is internally self-consistent.  It
    # does not prove completeness, the conflict winner, contributor membership,
    # or the aggregate export policy.  Recompose those values from the installed
    # package manifests and the locked member priorities, then require the whole
    # deterministic lock to match.
    source_set = {
        "schema_version": SOURCE_SET_SCHEMA,
        "source_set_id": lock.source_set_id,
        "generation_id": lock.generation_id,
        "conflict_policy": lock.conflict_policy,
        "cross_dataset_relations": lock.cross_dataset_relations,
        "members": [
            {
                "package_id": member.package_id,
                "priority": member.priority,
            }
            for member in lock.members
        ],
    }
    expected_view = compose_source_set(source_set, package_rows)
    expected_lock = _build_source_set_lock(expected_view)
    if lock.export_allowed is not expected_lock.export_allowed:
        raise DatasetContractError(
            "SourceSet lock export policy does not match package manifests"
        )
    if lock.artifacts != expected_lock.artifacts:
        raise DatasetContractError(
            "SourceSet lock artifacts do not match deterministic package composition"
        )
    if lock != expected_lock:
        raise DatasetContractError(
            "SourceSet lock does not match deterministic package composition"
        )


def _verify_materialized_source_set(
    destination: Path,
    lock: SourceSetLock,
    *,
    trusted_root: Path | None = None,
) -> MaterializedSourceSet:
    _validate_source_set_lock(lock)
    destination = _checked_directory_root(
        destination, field="materialized SourceSet root"
    )
    _assert_materialization_ready(destination, trusted_root=trusted_root)
    if not destination.is_dir():
        raise DatasetContractError("materialized SourceSet path is not a safe directory")
    restricted = not lock.export_allowed
    if restricted:
        # Publication keeps the restricted root owner-private and writable
        # (0700).  Installing that already-verified tree into an immutable
        # release removes write bits from every directory, yielding 0500.
        # Both states preserve the confidentiality boundary; any broader or
        # group/other-readable mode is rejected.
        root_mode = stat.S_IMODE(destination.lstat().st_mode)
        if root_mode not in {0o700, 0o500}:
            raise DatasetContractError(
                "root mode mismatch: expected restricted 0700 or sealed 0500, "
                f"got {root_mode:04o}"
            )
    receipt_path = _resolve_contained(
        destination,
        "receipt.json",
        field="materialization receipt",
        require_file=True,
    )
    if restricted:
        _assert_exact_mode(receipt_path, 0o400, field="receipt")
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
                "publish_strategy",
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
    if blob.get("export_allowed") is not lock.export_allowed:
        raise DatasetContractError("materialized SourceSet export policy mismatch")
    if blob.get("publish_strategy") not in _MATERIALIZATION_PUBLISH_STRATEGIES:
        raise DatasetContractError("materialized SourceSet publish strategy is invalid")
    rows = blob.get("artifacts")
    if not isinstance(rows, list) or len(rows) != len(lock.artifacts):
        raise DatasetContractError("materialized artifact set is incomplete")
    declared_files = {"receipt.json"}
    declared_artifact_paths: set[str] = set()
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
                    "dataset_id",
                    "version_id",
                    "build_id",
                    "manifest_sha256",
                    "logical_id",
                    "role",
                    "source_path",
                    "sha256",
                    "contributors",
                    "materialized_path",
                    "document_id",
                }
            ),
            f"materialized artifacts[{position}]",
        )
        target_rel = _relative(
            row.get("materialized_path"),
            f"materialized artifacts[{position}].materialized_path",
        )
        expected = lock.artifacts[position]
        deterministic_rel = _materialized_artifact_path(position, expected)
        if target_rel != deterministic_rel or target_rel in declared_artifact_paths:
            raise DatasetContractError(
                f"materialized_path is not one-to-one: {target_rel}"
            )
        declared_artifact_paths.add(target_rel)
        target = _resolve_contained(
            destination,
            target_rel,
            field=f"materialized artifacts[{position}]",
            require_file=True,
        )
        if restricted:
            _assert_exact_mode(target, 0o400, field="artifact")
        expected_fields = {
            "qualified_id": expected.qualified_id,
            "package_id": expected.package_id,
            "dataset_id": expected.dataset_id,
            "version_id": expected.version_id,
            "build_id": expected.build_id,
            "manifest_sha256": expected.manifest_sha256,
            "logical_id": expected.logical_id,
            "role": expected.role,
            "source_path": expected.path,
            "sha256": expected.sha256,
            "contributors": list(expected.contributors),
        }
        if expected.document_id is not None:
            expected_fields["document_id"] = expected.document_id
        if ("document_id" in row) != (expected.document_id is not None):
            raise DatasetContractError(
                f"materialized document_id mismatch: {expected.qualified_id}"
            )
        if any(row.get(key) != value for key, value in expected_fields.items()) or (
            _hash_file(target) != expected.sha256
        ):
            raise DatasetContractError(
                f"materialized artifact mismatch: {expected.qualified_id}"
            )
        declared_files.add(target_rel)
    observed_files: set[str] = set()
    observed_directories: set[str] = set()
    pending = [destination]
    while pending:
        directory = pending.pop()
        for entry in os.scandir(directory):
            path = Path(entry.path)
            relative = path.relative_to(destination).as_posix()
            if entry.is_symlink():
                raise DatasetContractError("materialized SourceSet contains a symlink")
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                if restricted:
                    _assert_exact_mode(path, 0o500, field="artifact directory")
                observed_directories.add(relative)
                pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                if restricted:
                    _assert_exact_mode(path, 0o400, field="artifact or receipt")
                observed_files.add(relative)
            else:
                raise DatasetContractError(
                    f"materialized SourceSet contains a special file: {relative}"
                )
    if observed_files != declared_files:
        raise DatasetContractError("materialized SourceSet has undeclared files")
    if observed_directories != {"ARTIFACTS"}:
        raise DatasetContractError("materialized SourceSet has undeclared directories")
    return MaterializedSourceSet(
        destination,
        lock,
        declared,
        blob,
        trusted_root=trusted_root,
    )


def open_materialized_source_set(
    destination: str | Path,
    lock: SourceSetLock,
    *,
    trusted_root: str | Path | None,
    for_export: bool = False,
) -> MaterializedSourceSet:
    """Open only a complete, hash-verified materialization below a trusted root."""

    if for_export and not lock.export_allowed:
        raise DatasetContractError("restricted SourceSet cannot be exported")
    root, final_path = _trusted_materialization_destination(
        destination, trusted_root
    )
    _assert_materialization_ready(final_path, trusted_root=root)
    return _verify_materialized_source_set(
        final_path,
        lock,
        trusted_root=root,
    )


def inspect_materialization(
    destination: str | Path,
    lock: SourceSetLock,
    *,
    trusted_root: str | Path | None,
) -> MaterializationInspection:
    """Inspect a materialization without deleting, moving, or repairing it."""

    root, final_path = _trusted_materialization_destination(
        destination, trusted_root
    )
    markers = _materialization_markers(final_path, trusted_root=root)
    exists = _entry_exists_no_follow(final_path, field="materialization target")
    issue: str | None = None
    if markers:
        issue = "incomplete publication marker is present"
    elif not exists:
        issue = "materialization target does not exist"
    else:
        try:
            _verify_materialized_source_set(
                final_path,
                lock,
                trusted_root=root,
            )
        except (DatasetContractError, OSError) as exc:
            issue = str(exc)
    return MaterializationInspection(
        path=final_path,
        exists=exists,
        ready=exists and issue is None,
        marker_paths=markers,
        issue=issue,
    )


def plan_materialization_quarantine(
    destination: str | Path,
    quarantine_destination: str | Path,
    lock: SourceSetLock,
    *,
    trusted_root: str | Path | None,
) -> MaterializationQuarantinePlan:
    """Return an operator-reviewable no-replace plan without executing it."""

    root, source = _trusted_materialization_destination(destination, trusted_root)
    inspection = inspect_materialization(source, lock, trusted_root=root)
    if inspection.ready or not (inspection.exists or inspection.marker_paths):
        raise DatasetContractError(
            "only an observed incomplete materialization can be quarantined"
        )
    _same_root, quarantine = _trusted_materialization_destination(
        quarantine_destination, root
    )
    if source == quarantine or source in quarantine.parents or quarantine in source.parents:
        raise DatasetContractError("materialization and quarantine target must not overlap")
    if _entry_exists_no_follow(
        quarantine,
        field="materialization quarantine target",
    ) or _materialization_markers(quarantine, trusted_root=root):
        raise DatasetContractError("materialization quarantine target is not empty")
    return MaterializationQuarantinePlan(
        source=source,
        quarantine_target=quarantine,
        inspection=inspection,
    )


def _write_materialization_receipt(
    staging: Path,
    *,
    lock: SourceSetLock,
    export_allowed: bool,
    artifact_rows: list[dict[str, Any]],
    publish_strategy: str,
    restricted: bool,
) -> Mapping[str, Any]:
    if publish_strategy not in _MATERIALIZATION_PUBLISH_STRATEGIES:
        raise DatasetContractError("unsupported materialization publish strategy")
    receipt_core: dict[str, Any] = {
        "schema_version": MATERIALIZATION_RECEIPT_SCHEMA,
        "lock": lock.receipt(),
        "export_allowed": export_allowed,
        "publish_strategy": publish_strategy,
        "artifacts": artifact_rows,
    }
    receipt = dict(receipt_core)
    receipt["receipt_sha256"] = _digest(receipt_core)
    payload = (
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".receipt-", suffix=".json", dir=staging
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            if restricted:
                os.fchmod(stream.fileno(), 0o400)
            os.fsync(stream.fileno())
        os.replace(temporary, staging / "receipt.json")
        _fsync_directory(staging)
    finally:
        if temporary.exists():
            temporary.unlink()
    return receipt


def materialize_source_set(
    view: UnifiedCorpusView,
    destination: str | Path,
    *,
    lock: SourceSetLock | None = None,
    for_export: bool = False,
    relation_policy_enforced: bool = False,
    allow_cross_dataset_relations: bool = False,
    trusted_root: str | Path | None = None,
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
    _validate_source_set_lock(selected_lock)
    _validate_source_set_lock_packages(selected_lock, view.packages)
    restricted = not selected_lock.export_allowed
    trusted_path, final_path = _trusted_materialization_destination(
        destination, trusted_root
    )
    _assert_materialization_ready(final_path, trusted_root=trusted_path)
    if final_path.exists():
        return open_materialized_source_set(
            final_path, selected_lock, trusted_root=trusted_path
        )
    relative_parent = final_path.parent.relative_to(trusted_path)
    parent = _ensure_trusted_directory_chain(trusted_path, relative_parent)
    # Re-run the lexical walk after creating parents to reject a concurrent
    # symlink substitution before staging any restricted bytes.
    checked_root, checked_final = _trusted_materialization_destination(
        final_path, trusted_path
    )
    if checked_root != trusted_path or checked_final != final_path:
        raise DatasetContractError("materialization destination changed during setup")
    _assert_materialization_ready(final_path, trusted_root=trusted_path)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{final_path.name}.staging-", dir=parent)
    )
    staging_info = staging.lstat()
    staging_identity = (staging_info.st_dev, staging_info.st_ino)
    published = False
    primary_error: BaseException | None = None
    try:
        if restricted:
            _assert_exact_mode(staging, 0o700, field="root")
        artifact_rows: list[dict[str, Any]] = []
        if len(view.artifacts) != len(selected_lock.artifacts):
            raise DatasetContractError("SourceSet artifact lock is incomplete")
        for position, (item, artifact_lock) in enumerate(
            zip(view.artifacts, selected_lock.artifacts, strict=True)
        ):
            artifact = item.selected
            if (
                artifact.identity_key != artifact_lock.identity_key
                or artifact.provenance_key != artifact_lock.provenance_key
                or artifact.sha256 != artifact_lock.sha256
                or artifact.path != artifact_lock.path
                or artifact.document_id != artifact_lock.document_id
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
            target_rel = _materialized_artifact_path(position, artifact_lock)
            target = staging / target_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target, follow_symlinks=False)
            _fsync_regular_file(target, mode=0o400 if restricted else None)
            if _hash_file(target) != artifact.sha256:
                raise DatasetContractError(
                    f"staged artifact hash mismatch: {artifact.qualified_id}"
                )
            artifact_row: dict[str, Any] = {
                "qualified_id": artifact.qualified_id,
                "package_id": artifact.package_id,
                "dataset_id": artifact.dataset_id,
                "version_id": artifact.version_id,
                "build_id": artifact.build_id,
                "manifest_sha256": artifact_lock.manifest_sha256,
                "logical_id": artifact.logical_id,
                "role": artifact.role,
                "source_path": artifact.path,
                "sha256": artifact.sha256,
                "contributors": list(item.contributors),
                "materialized_path": target_rel,
            }
            if artifact.document_id is not None:
                artifact_row["document_id"] = artifact.document_id
            artifact_rows.append(artifact_row)

        artifacts_directory = staging / "ARTIFACTS"
        _fsync_directory(
            artifacts_directory,
            mode=0o500 if restricted else None,
        )

        prepared_receipt: Mapping[str, Any] | None = None

        def prepare_receipt(strategy: str) -> None:
            nonlocal prepared_receipt
            prepared_receipt = _write_materialization_receipt(
                staging,
                lock=selected_lock,
                export_allowed=view.export_allowed,
                artifact_rows=artifact_rows,
                publish_strategy=strategy,
                restricted=restricted,
            )

        # Staging is a sibling, so renameat2 is same-filesystem and atomic.  It
        # explicitly refuses to replace even an empty directory published by a
        # competing writer.
        _assert_materialization_ready(final_path, trusted_root=trusted_path)
        publish_strategy = _atomic_publish_directory_no_replace(
            staging,
            final_path,
            prepare_receipt=prepare_receipt,
        )
        if restricted:
            _assert_exact_mode(final_path, 0o700, field="root")
        published = True
        _fsync_directory(parent)
        materialized = open_materialized_source_set(
            final_path, selected_lock, trusted_root=trusted_path
        )
        if (
            prepared_receipt is None
            or materialized.receipt != prepared_receipt
            or materialized.receipt.get("publish_strategy") != publish_strategy
        ):
            raise DatasetContractError(
                "published SourceSet receipt does not bind its publication strategy"
            )
        return materialized
    except FileExistsError:
        try:
            return open_materialized_source_set(
                final_path, selected_lock, trusted_root=trusted_path
            )
        except BaseException as exc:
            primary_error = exc
            raise
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        if not published:
            try:
                _remove_private_staging_tree(
                    staging,
                    expected_identity=staging_identity,
                )
            except Exception as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.add_note(
                    f"private staging cleanup also failed: {cleanup_error}"
                )


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
