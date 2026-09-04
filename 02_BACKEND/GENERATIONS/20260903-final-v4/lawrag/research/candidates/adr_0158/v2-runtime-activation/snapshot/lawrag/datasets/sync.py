"""Resolve environment-specific documents through stable logical dataset IDs."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from lawrag.platform.workspace import load_layout


_LAYOUT = load_layout()
ROOT = _LAYOUT.root


def active_manifest_path() -> Path:
    return Path(os.environ.get(
        "DATASET_ACTIVE_MANIFEST",
        _LAYOUT.path("data") / "sync" / "ACTIVE_DATASET.json",
    ))


def sync_set_path() -> Path:
    return Path(os.environ.get(
        "DATASET_SYNC_SET", _LAYOUT.path("data") / "sync" / "SYNC_SET.json"
    ))


def load_active(path: Path | None = None) -> dict[str, Any]:
    target = path or active_manifest_path()
    value = json.loads(target.read_text("utf-8"))
    if value.get("schema_version") != "active-dataset-overlay-v1":
        raise ValueError(f"unsupported active dataset manifest: {target}")
    ids = [str(row.get("logical_id") or "") for row in value.get("items") or []]
    if not ids or len(ids) != len(set(ids)) or "" in ids:
        raise ValueError("active dataset logical IDs must be non-empty and unique")
    expected = os.environ.get("DATASET_OVERLAY_CONTRACT_SHA256")
    if expected and value.get("contract_sha256") != expected:
        raise ValueError("active dataset overlay contract does not match experiment lock")
    return value


def resolve(logical_id: str, *, path: Path | None = None) -> dict[str, Any]:
    active = load_active(path)
    for item in active["items"]:
        if item["logical_id"] == logical_id:
            return item
    raise KeyError(f"logical dataset ID is not active: {logical_id}")


def environment_receipt(
    *, active_path: Path | None = None, set_path: Path | None = None
) -> dict[str, Any]:
    active = load_active(active_path)
    target = set_path or sync_set_path()
    sync_set = json.loads(target.read_text("utf-8")) if target.is_file() else None
    return {
        "schema_version": "dataset-environment-receipt-v1",
        "environment": (sync_set or {}).get("environment"),
        "overlay_id": active["overlay_id"],
        "overlay_representation": active["representation"],
        "overlay_contract_sha256": active["contract_sha256"],
        "logical_ids": sorted(row["logical_id"] for row in active["items"]),
        "common_bundles": {
            row["bundle_id"]: row["content_sha256"]
            for row in (sync_set or {}).get("bundles") or []
            if str(row.get("bundle_id") or "").startswith("common-")
        },
    }
