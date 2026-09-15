from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from lawrag.platform import stored_paths


def _write_json(path: Path, value: dict) -> str:
    raw = (json.dumps(value, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _activation(root: Path, name: str, bindings: list[tuple[str, str]]) -> str:
    final_rel = f"00_SYSTEM/MIGRATION/RECEIPTS/{name}.json"
    final_sha = _write_json(
        root / final_rel,
        {"items": [{"source": source, "target": target} for source, target in bindings]},
    )
    activation_rel = f"00_SYSTEM/MIGRATION/ACTIVATIONS/{name}.json"
    _write_json(
        root / activation_rel,
        {
            "validation_receipt_path": final_rel,
            "validation_receipt_sha256": final_sha,
        },
    )
    return activation_rel


def _workspace(root: Path, current: str, history: list[str] | None = None) -> None:
    _write_json(
        root / "00_SYSTEM/WORKSPACE.json",
        {
            "lifecycle": {"activation_receipt": current},
            "path_history_activation_receipts": history or [],
        },
    )
    stored_paths._bindings.cache_clear()


def test_resolver_uses_literal_then_current_then_history(tmp_path: Path) -> None:
    current = _activation(tmp_path, "current", [("lawrag", "02_BACKEND/current")])
    history = _activation(tmp_path, "history", [("docs", "04_EXPERIMENTS/legacy")])
    _workspace(tmp_path, current, [history])

    literal = tmp_path / "docs/literal.txt"
    literal.parent.mkdir(parents=True)
    literal.write_text("literal", "utf-8")
    current_file = tmp_path / "02_BACKEND/current/core.py"
    current_file.parent.mkdir(parents=True)
    current_file.write_text("current", "utf-8")
    history_file = tmp_path / "04_EXPERIMENTS/legacy/adr.json"
    history_file.parent.mkdir(parents=True)
    history_file.write_text("history", "utf-8")

    assert stored_paths.resolve_stored_path(tmp_path, "docs/literal.txt") == literal
    assert stored_paths.resolve_stored_path(tmp_path, "lawrag/core.py") == current_file
    assert stored_paths.resolve_stored_path(tmp_path, "docs/adr.json") == history_file


def test_resolver_fails_closed_for_unsafe_or_unsealed_paths(tmp_path: Path) -> None:
    current = _activation(tmp_path, "current", [("lawrag", "02_BACKEND/current")])
    _workspace(tmp_path, current)

    with pytest.raises(stored_paths.StoredPathError, match="stay inside"):
        stored_paths.resolve_stored_path(tmp_path, "../secret")
    with pytest.raises(stored_paths.StoredPathError, match="no active receipt binding"):
        stored_paths.resolve_stored_path(tmp_path, "unknown/file.json")


def test_resolver_rejects_tampered_final_receipt(tmp_path: Path) -> None:
    current = _activation(tmp_path, "current", [("lawrag", "02_BACKEND/current")])
    _workspace(tmp_path, current)
    final = tmp_path / "00_SYSTEM/MIGRATION/RECEIPTS/current.json"
    final.write_text('{"items": []}\n', "utf-8")
    stored_paths._bindings.cache_clear()

    with pytest.raises(stored_paths.StoredPathError, match="hash mismatch"):
        stored_paths.resolve_stored_path(tmp_path, "lawrag/core.py")
