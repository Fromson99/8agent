from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from lawrag.platform import paths as paths_mod
from lawrag.platform.workspace import (
    LayoutError,
    RootSpec,
    WorkspaceLayout,
    audit_top_level,
    build_migration_plan,
    compare_dual_read,
    execute_copy_verify_zero,
    load_layout,
    verify_final_migration,
)


def _test_layout(tmp_path: Path, roots: tuple[RootSpec, ...]) -> WorkspaceLayout:
    return WorkspaceLayout(
        root=tmp_path,
        mode="bridge",
        default_layout_version="v1",
        canonical_root_pattern=r"^[0-9]{2}_[A-Z][A-Z0-9_]*$",
        roots={spec.id: spec for spec in roots},
        legacy_top_level_directories=(),
        root_file_policy={},
        invariants=(),
        manifest_sha256="a" * 64,
    )


def _run_to_dual(layout: WorkspaceLayout, pairs: tuple[tuple[str, str], ...]):
    plan = build_migration_plan(layout, pairs)
    copied = execute_copy_verify_zero(layout, plan)
    return plan, compare_dual_read(layout, plan, copied)


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


def test_final_receipt_covers_partition_and_delegates_nested_legacy_root(tmp_path):
    roots = (
        RootSpec("system", "00_SYSTEM", None, "active"),
        RootSpec("data", "01_DATA", "data", "bridge"),
        RootSpec("archive", "99_ARCHIVE", "data/_archive", "bridge"),
    )
    for path in ("00_SYSTEM", "01_DATA", "99_ARCHIVE", "data/_archive"):
        (tmp_path / path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "data/live.txt").write_text("live\n", "utf-8")
    (tmp_path / "data/_archive/old.txt").write_text("old\n", "utf-8")
    layout = _test_layout(tmp_path, roots)

    plan, dual = _run_to_dual(
        layout,
        (
            ("data/live.txt", "01_DATA/live.txt"),
            ("data/_archive", "99_ARCHIVE/LEGACY_DATA_ARCHIVE"),
        ),
    )
    final = verify_final_migration(
        layout,
        plan,
        dual,
        already_canonical_root_ids=("system",),
    )

    bindings = {binding.root_id: binding for binding in final.canonical_root_bindings}
    assert bindings["data"].completion_kind == "migrated-legacy-partition"
    assert bindings["data"].covered_sources == ("data/live.txt",)
    assert bindings["data"].delegated_sources == ("data/_archive",)
    assert bindings["data"].excluded_sources == ()
    assert bindings["archive"].completion_kind == "migrated-legacy-root"
    assert bindings["archive"].covered_sources == ("data/_archive",)


def test_final_receipt_rejects_incomplete_legacy_partition(tmp_path):
    roots = (
        RootSpec("system", "00_SYSTEM", None, "active"),
        RootSpec("data", "01_DATA", "data", "bridge"),
        RootSpec("archive", "99_ARCHIVE", "data/_archive", "bridge"),
    )
    for path in ("00_SYSTEM", "01_DATA", "99_ARCHIVE", "data/_archive"):
        (tmp_path / path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "data/uncovered.txt").write_text("missing\n", "utf-8")
    (tmp_path / "data/_archive/old.txt").write_text("old\n", "utf-8")
    layout = _test_layout(tmp_path, roots)
    plan, dual = _run_to_dual(
        layout,
        (("data/_archive", "99_ARCHIVE/LEGACY_DATA_ARCHIVE"),),
    )

    with pytest.raises(LayoutError, match=r"partition is incomplete: missing=data/uncovered.txt"):
        verify_final_migration(
            layout,
            plan,
            dual,
            already_canonical_root_ids=("system",),
        )


def test_final_receipt_allows_only_declared_generated_directory_exclusions(tmp_path):
    roots = (
        RootSpec("system", "00_SYSTEM", None, "active"),
        RootSpec("frontend", "03_FRONTEND", "frontend", "bridge"),
    )
    for path in ("00_SYSTEM", "03_FRONTEND", "frontend/app", "frontend/node_modules"):
        (tmp_path / path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "frontend/app/page.tsx").write_text("export default 1\n", "utf-8")
    (tmp_path / "frontend/node_modules/generated.js").write_text("generated\n", "utf-8")
    layout = _test_layout(tmp_path, roots)
    plan, dual = _run_to_dual(
        layout,
        (("frontend/app", "03_FRONTEND/project/app"),),
    )

    final = verify_final_migration(
        layout,
        plan,
        dual,
        already_canonical_root_ids=("system",),
        excluded_legacy_sources={"frontend": ("frontend/node_modules",)},
    )
    frontend = next(
        binding for binding in final.canonical_root_bindings
        if binding.root_id == "frontend"
    )
    assert frontend.excluded_sources == ("frontend/node_modules",)

    with pytest.raises(LayoutError, match="not an approved generated entry"):
        verify_final_migration(
            layout,
            plan,
            dual,
            already_canonical_root_ids=("system",),
            excluded_legacy_sources={"frontend": ("frontend/app",)},
        )
