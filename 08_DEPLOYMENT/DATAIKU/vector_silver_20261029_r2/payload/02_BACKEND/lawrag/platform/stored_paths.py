"""Receipt-bound resolver for immutable paths recorded before workspace v2."""
from __future__ import annotations

import json
import hashlib
from functools import lru_cache
from pathlib import Path, PurePosixPath


class StoredPathError(ValueError):
    """A stored path cannot be safely resolved in the active workspace."""


def _relative(value: object, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise StoredPathError(f"{field} must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise StoredPathError(f"{field} must stay inside the workspace: {value}")
    return path


def _json(path: Path, field: str) -> dict:
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoredPathError(f"cannot read {field}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StoredPathError(f"{field} must be a JSON object")
    return value


@lru_cache(maxsize=8)
def _bindings(root: Path) -> tuple[tuple[PurePosixPath, PurePosixPath], ...]:
    workspace = _json(root / "00_SYSTEM/WORKSPACE.json", "workspace manifest")
    activation_values = [
        (workspace.get("lifecycle") or {}).get("activation_receipt"),
        *(workspace.get("path_history_activation_receipts") or []),
    ]
    result = []
    seen = set()
    for activation_index, activation_value in enumerate(activation_values):
        activation_path = _relative(
            activation_value, f"activation_receipts[{activation_index}]"
        )
        activation = _json(root.joinpath(*activation_path.parts), "activation receipt")
        final_path = _relative(
            activation.get("validation_receipt_path"), "validation_receipt_path"
        )
        final_file = root.joinpath(*final_path.parts)
        try:
            final_raw = final_file.read_bytes()
        except OSError as exc:
            raise StoredPathError(f"cannot read final-verify receipt: {final_file}: {exc}") from exc
        if hashlib.sha256(final_raw).hexdigest() != activation.get("validation_receipt_sha256"):
            raise StoredPathError(f"final-verify receipt hash mismatch: {final_file}")
        final = _json(final_file, "final-verify receipt")
        rows = final.get("items")
        if not isinstance(rows, list):
            raise StoredPathError("final-verify receipt items must be an array")
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise StoredPathError(f"items[{index}] must be an object")
            pair = (
                _relative(row.get("source"), f"items[{index}].source"),
                _relative(row.get("target"), f"items[{index}].target"),
            )
            if pair[0] not in seen:
                result.append(pair)
                seen.add(pair[0])
    return tuple(sorted(result, key=lambda pair: len(pair[0].parts), reverse=True))


def resolve_stored_path(
    root: str | Path,
    stored: object,
    *,
    require_exists: bool = True,
) -> Path:
    """Resolve literal paths first, then the active receipt's longest prefix."""

    workspace = Path(root).resolve()
    relative = _relative(stored, "stored path")
    literal = workspace.joinpath(*relative.parts)
    if literal.exists() or not (workspace / "00_SYSTEM/WORKSPACE.json").is_file():
        target = literal
    else:
        target = None
        for source, destination in _bindings(workspace):
            try:
                remainder = relative.relative_to(source)
            except ValueError:
                continue
            target = workspace.joinpath(*destination.parts, *remainder.parts)
            break
        if target is None:
            raise StoredPathError(f"stored path has no active receipt binding: {relative}")
    try:
        target.resolve(strict=False).relative_to(workspace)
    except ValueError as exc:
        raise StoredPathError(f"resolved path escapes workspace: {relative}") from exc
    if require_exists and not target.exists():
        raise StoredPathError(f"resolved path does not exist: {relative} -> {target}")
    return target
