from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import dataset_sync
from lawrag.datasets import sync as dataset_runtime


def _profiles_and_mock():
    profiles = dataset_sync._json(dataset_sync.DEFAULT_PROFILES)
    mock = dataset_sync.load_overlay(
        dataset_sync.ROOT / profiles["external_overlay"]
    )
    return profiles, mock


def test_common_profiles_exclude_internal_overlay_vectors_and_render_cache() -> None:
    profiles, mock = _profiles_and_mock()
    paths = {
        row["path"]
        for name in ("common-runtime", "common-evaluation")
        for row in dataset_sync.profile_entries(
            name, profiles, excluded_overlays=[mock]
        )
    }
    assert paths
    forbidden = (
        "data/corpus/internal/", "/pages/", "source.pdf", "parse.json",
        "data/embeddings/", ".npz",
    )
    assert not [path for path in paths if any(value in path for value in forbidden)]


def test_external_mock_overlay_is_locked_to_four_logical_contracts() -> None:
    _profiles, mock = _profiles_and_mock()
    contract = dataset_sync.overlay_contract(mock)
    assert mock["representation"] == "mock"
    assert mock["export_allowed"] is True
    assert len(contract["items"]) == 4
    assert contract["contract_sha256"] == (
        "4c49df90f51be57859c1e8fdf78d99b160c97d6e34a037678a5436e3500dc1d2"
    )


def test_internal_template_has_same_contract_but_cannot_be_packed() -> None:
    profiles, mock = _profiles_and_mock()
    template = dataset_sync.load_overlay(
        dataset_sync.ROOT / profiles["internal_overlay_template"],
        require_files=False,
    )
    assert dataset_sync.check_overlay_pair(mock, template) == (
        dataset_sync.overlay_contract(mock)
    )
    with pytest.raises(FileNotFoundError):
        dataset_sync.load_overlay(
            dataset_sync.ROOT / profiles["internal_overlay_template"]
        )


def test_overlay_contract_change_is_rejected() -> None:
    _profiles, mock = _profiles_and_mock()
    real = copy.deepcopy(mock)
    real["representation"] = "real"
    real["export_allowed"] = False
    real["items"][0]["contract"]["version_role"] = "changed"
    with pytest.raises(ValueError, match="different logical contracts"):
        dataset_sync.check_overlay_pair(mock, real)


def test_bundle_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("동일 데이터\n", "utf-8")
    entries = [{"source_path": source, "path": "data/example.txt"}]
    output = tmp_path / "bundle"
    manifest = dataset_sync.pack_bundle(
        output, "common-test", "shared-identical", entries, max_mb=2
    )
    assert dataset_sync.verify_bundle(output)["content_sha256"] == manifest[
        "content_sha256"
    ]
    shard = output / manifest["shards"][0]["file"]
    shard.write_bytes(shard.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="shard hash or size mismatch"):
        dataset_sync.verify_bundle(output)


def test_safe_relative_rejects_escape_and_secrets() -> None:
    for value in ("../escape", "/absolute", ".env", "keys/private.pem"):
        with pytest.raises(ValueError):
            dataset_sync._safe_relative(value)


def test_runtime_resolves_logical_id_and_emits_environment_receipt(tmp_path: Path) -> None:
    active = {
        "schema_version": "active-dataset-overlay-v1",
        "overlay_id": "mock-v1",
        "representation": "mock",
        "contract_sha256": "contract-hash",
        "items": [{"logical_id": "internal/rule", "doc_id": "mock-doc"}],
    }
    active_path = tmp_path / "ACTIVE_DATASET.json"
    active_path.write_text(json.dumps(active), "utf-8")
    set_path = tmp_path / "SYNC_SET.json"
    set_path.write_text(json.dumps({
        "environment": "external",
        "bundles": [{
            "bundle_id": "common-runtime", "content_sha256": "common-hash"
        }],
    }), "utf-8")

    assert dataset_runtime.resolve("internal/rule", path=active_path)["doc_id"] == (
        "mock-doc"
    )
    receipt = dataset_runtime.environment_receipt(
        active_path=active_path, set_path=set_path
    )
    assert receipt["environment"] == "external"
    assert receipt["common_bundles"] == {"common-runtime": "common-hash"}
