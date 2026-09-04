"""Resolve immutable pre-v2 paths through the activated migration receipt.

Stored experiment and benchmark records retain their original relative paths so
their content hashes remain valid.  Consumers must translate those paths using
the exact source-to-target bindings sealed by the active final-verify receipt.
"""
from __future__ import annotations

import json
import hashlib
from functools import lru_cache
from pathlib import Path, PurePosixPath


class StoredPathError(ValueError):
    """A stored path or its receipt binding is unsafe or incomplete."""


def _relative(value: object, *, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise StoredPathError(f"{field} must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise StoredPathError(f"{field} must stay inside the workspace: {value}")
    return path


def _read_json(path: Path, *, field: str) -> dict:
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoredPathError(f"cannot read {field}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StoredPathError(f"{field} must be a JSON object: {path}")
    return value


@lru_cache(maxsize=8)
def receipt_bindings(root: Path) -> tuple[tuple[PurePosixPath, PurePosixPath], ...]:
    """Load longest-prefix bindings from the workspace's active receipt chain."""

    workspace = _read_json(root / "00_SYSTEM/WORKSPACE.json", field="workspace manifest")
    activation_values = [
        (workspace.get("lifecycle") or {}).get("activation_receipt"),
        *(workspace.get("path_history_activation_receipts") or []),
    ]
    bindings: list[tuple[PurePosixPath, PurePosixPath]] = []
    seen: set[PurePosixPath] = set()
    for activation_index, activation_value in enumerate(activation_values):
        activation_rel = _relative(
            activation_value, field=f"activation_receipts[{activation_index}]"
        )
        activation = _read_json(
            root.joinpath(*activation_rel.parts), field="activation receipt"
        )
        final_rel = _relative(
            activation.get("validation_receipt_path"), field="validation_receipt_path"
        )
        final_path = root.joinpath(*final_rel.parts)
        try:
            final_raw = final_path.read_bytes()
        except OSError as exc:
            raise StoredPathError(f"cannot read final-verify receipt: {final_path}: {exc}") from exc
        if hashlib.sha256(final_raw).hexdigest() != activation.get("validation_receipt_sha256"):
            raise StoredPathError(f"final-verify receipt hash mismatch: {final_path}")
        final = _read_json(final_path, field="final-verify receipt")
        rows = final.get("items")
        if not isinstance(rows, list):
            raise StoredPathError("final-verify receipt items must be an array")
        for position, row in enumerate(rows):
            if not isinstance(row, dict):
                raise StoredPathError(f"final-verify item {position} must be an object")
            source = _relative(row.get("source"), field=f"items[{position}].source")
            target = _relative(row.get("target"), field=f"items[{position}].target")
            if source not in seen:
                bindings.append((source, target))
                seen.add(source)
    bindings.sort(key=lambda pair: len(pair[0].parts), reverse=True)
    return tuple(bindings)


def resolve_stored_path(root: Path, stored: object, *, require_exists: bool = True) -> Path:
    """Resolve a legacy or canonical record path without rewriting its record.

    Literal paths win for synthetic fixtures and already-canonical records.  A
    missing literal path is translated only by a sealed receipt binding.
    """

    root = root.resolve()
    relative = _relative(stored, field="stored path")
    literal = root.joinpath(*relative.parts)
    if literal.exists() or not (root / "00_SYSTEM/WORKSPACE.json").is_file():
        resolved = literal
    else:
        resolved = None
        for source, target in receipt_bindings(root):
            try:
                remainder = relative.relative_to(source)
            except ValueError:
                continue
            resolved = root.joinpath(*target.parts, *remainder.parts)
            break
        if resolved is None:
            raise StoredPathError(f"stored path has no active receipt binding: {relative}")

    try:
        resolved.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise StoredPathError(f"resolved path escapes workspace: {relative}") from exc
    if require_exists and not resolved.exists():
        raise StoredPathError(f"resolved path does not exist: {relative} -> {resolved}")
    return resolved
