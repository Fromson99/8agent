from __future__ import annotations

import json
from pathlib import Path

import pytest

from lawrag.platform.workspace import LayoutError, audit_top_level, load_layout


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def retirement_receipt(monkeypatch):
    manifest = json.loads((ROOT / "00_SYSTEM/WORKSPACE.json").read_text("utf-8"))
    relative = manifest["lifecycle"]["retirement_receipt"]
    monkeypatch.setenv("LAWRAG_LAYOUT_RETIREMENT_RECEIPT", str(ROOT / relative))


def test_permanent_v2_layout_and_receipts():
    layout = load_layout(ROOT)
    final = layout.validate_activation()

    assert layout.mode == "v2-only"
    assert layout.default_layout_version == "v2"
    assert layout.path("data") == ROOT / "01_DATA"
    assert len(final["canonical_root_bindings"]) == 12
    assert layout.migration_target("lawrag").is_dir()
    assert layout.migration_target("scripts").is_dir()


def test_v1_runtime_is_permanently_rejected(monkeypatch):
    monkeypatch.setenv("LAWRAG_LAYOUT_VERSION", "v1")
    with pytest.raises(LayoutError, match="v2-only"):
        load_layout(ROOT).path("data")


def test_legacy_roots_are_retired():
    report = audit_top_level(load_layout(ROOT))
    assert report["legacy_roots_present"] == []
    assert report["unknown_top_level_directories"] == []
    assert report["unclassified_root_files"] == []
    assert report["retirement_ready"] is True


def test_stable_entrypoints_exist():
    assert (ROOT / "06_TOOLS/serve.sh").is_file()
    assert (ROOT / "06_TOOLS/run_tool.py").is_file()
    assert (ROOT / "00_SYSTEM/WORKSPACE.json").is_file()
