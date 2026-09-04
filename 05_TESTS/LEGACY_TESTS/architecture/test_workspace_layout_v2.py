from __future__ import annotations

import json
import re

import pytest

from lawrag.platform import paths as paths_mod
from lawrag.platform.workspace import LayoutError, audit_top_level, load_layout


def test_numbered_canonical_roots_exist_and_follow_policy():
    layout = load_layout()
    pattern = re.compile(layout.canonical_root_pattern)

    assert layout.mode == "bridge"
    assert len(layout.roots) == 12
    assert all(pattern.fullmatch(spec.canonical_path) for spec in layout.roots.values())
    assert all(
        layout.inspection_path(root_id, layout_version="v2").is_dir()
        for root_id in layout.roots
    )


def test_layout_version_changes_logical_path_without_silent_default_switch(monkeypatch):
    layout = load_layout()

    monkeypatch.delenv("LAWRAG_LAYOUT_VERSION", raising=False)
    assert layout.path("data") == layout.root / "data"
    assert layout.inspection_path("data", layout_version="v2") == layout.root / "01_DATA"
    with pytest.raises(LayoutError, match="inspection-only"):
        layout.path("data", layout_version="v2")

    monkeypatch.setenv("LAWRAG_LAYOUT_VERSION", "v3")
    with pytest.raises(LayoutError, match="unsupported LAWRAG_LAYOUT_VERSION"):
        layout.path("data")


def test_environment_cannot_activate_v2_without_a_hash_locked_receipt(
    monkeypatch, tmp_path
):
    layout = load_layout()
    monkeypatch.setenv("LAWRAG_LAYOUT_VERSION", "v2")
    monkeypatch.delenv("LAWRAG_LAYOUT_ACTIVATION_RECEIPT", raising=False)

    with pytest.raises(LayoutError, match="requires LAWRAG_LAYOUT_ACTIVATION_RECEIPT"):
        layout.path("data")

    receipt = tmp_path / "layout-activation.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "workspace-layout-activation-v2",
                "activation_id": "layout-v2-test",
                "layout_version": "v2",
                "status": "active",
                "workspace_manifest_sha256": layout.manifest_sha256,
                "validation_receipt_path": "var/out/structure/migration/missing.json",
                "validation_receipt_sha256": "a" * 64,
                "validation_record_sha256": "b" * 64,
                "migration_plan_sha256": "c" * 64,
            }
        ),
        "utf-8",
    )
    monkeypatch.setenv("LAWRAG_LAYOUT_ACTIVATION_RECEIPT", str(receipt))

    with pytest.raises(LayoutError, match="validation_receipt_path does not exist"):
        layout.path("data")


def test_bridge_audit_is_honest_about_legacy_roots():
    report = audit_top_level(load_layout())

    assert report["missing_canonical_roots"] == []
    assert "data" in report["legacy_roots_present"]
    assert "workspace mode is not v2-only" in report["activation_blockers"]
    assert report["target_ready"] is False


def test_logical_helpers_preserve_legacy_paths_by_default(monkeypatch):
    monkeypatch.delenv("LAWRAG_LAYOUT_VERSION", raising=False)
    monkeypatch.delenv("LAWRAG_LAYOUT_ACTIVATION_RECEIPT", raising=False)
    layout = load_layout()

    assert paths_mod.repository_root() == layout.root
    assert paths_mod.data_path("structure") == layout.root / "data" / "structure"
    assert paths_mod.runtime_path("out", "structure") == (
        layout.root / "var" / "out" / "structure"
    )


def test_logical_runtime_bucket_uses_canonical_uppercase_name(monkeypatch, tmp_path):
    root_specs = load_layout().roots

    class V2Layout:
        root = tmp_path
        roots = root_specs

        def path(self, root_id: str):
            return {
                "data": tmp_path / "01_DATA",
                "runtime": tmp_path / "90_RUNTIME",
            }[root_id]

    monkeypatch.setattr(paths_mod, "load_layout", lambda: V2Layout())

    assert paths_mod.data_path("structure") == tmp_path / "01_DATA" / "structure"
    assert paths_mod.runtime_path("out", "structure") == (
        tmp_path / "90_RUNTIME" / "OUT" / "structure"
    )
    assert paths_mod.runtime_path("custom", "x") == (
        tmp_path / "90_RUNTIME" / "custom" / "x"
    )
    assert paths_mod.runtime_path("eval", "e2e") == (
        tmp_path / "90_RUNTIME" / "OUT" / "eval" / "e2e"
    )
    assert paths_mod.persisted_data_path("data/corpus/law/body.xml") == (
        tmp_path / "01_DATA" / "corpus" / "law" / "body.xml"
    )
    assert paths_mod.persisted_data_path("01_DATA/review/golden.json") == (
        tmp_path / "01_DATA" / "review" / "golden.json"
    )
    with pytest.raises(ValueError, match="outside the data root"):
        paths_mod.persisted_data_path("docs/ARCHITECTURE.md")
    with pytest.raises(ValueError, match="safe relative path"):
        paths_mod.persisted_data_path("../outside")
