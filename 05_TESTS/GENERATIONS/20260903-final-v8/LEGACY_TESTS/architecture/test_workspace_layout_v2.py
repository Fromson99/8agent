from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
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
    persist_immutable_migration_record,
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


def _activated_backend_layout(tmp_path: Path, monkeypatch):
    roots = (
        RootSpec("system", "00_SYSTEM", None, "active"),
        RootSpec("backend", "02_BACKEND", "lawrag", "bridge"),
    )
    for path in ("00_SYSTEM", "02_BACKEND", "lawrag"):
        (tmp_path / path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "lawrag/__init__.py").write_text("VERSION = 2\n", "utf-8")
    layout = _test_layout(tmp_path, roots)
    plan, dual = _run_to_dual(
        layout,
        (("lawrag", "02_BACKEND/GENERATIONS/test/lawrag"),),
    )
    final = verify_final_migration(
        layout,
        plan,
        dual,
        already_canonical_root_ids=("system",),
    )
    final_relative = "00_SYSTEM/final.json"
    final_file_sha256 = persist_immutable_migration_record(
        layout, final_relative, final
    )
    activation = {
        "schema_version": "workspace-layout-activation-v2",
        "status": "active",
        "layout_version": "v2",
        "workspace_manifest_sha256": layout.manifest_sha256,
        "validation_receipt_path": final_relative,
        "validation_receipt_sha256": final_file_sha256,
        "validation_record_sha256": final.receipt_sha256,
        "migration_plan_sha256": plan.plan_sha256,
        "activation_id": "test-receipt-bound-backend",
    }
    activation_path = tmp_path / "activation.json"
    activation_path.write_text(
        json.dumps(activation, ensure_ascii=False, sort_keys=True) + "\n",
        "utf-8",
    )
    assert hashlib.sha256(activation_path.read_bytes()).hexdigest()
    monkeypatch.setenv("LAWRAG_LAYOUT_VERSION", "v2")
    monkeypatch.setenv("LAWRAG_LAYOUT_ACTIVATION_RECEIPT", str(activation_path))
    return layout


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


def test_manifest_default_activation_is_used_without_environment(
    monkeypatch, tmp_path
):
    layout = _activated_backend_layout(tmp_path, monkeypatch)
    layout = replace(layout, activation_receipt="activation.json")
    monkeypatch.delenv("LAWRAG_LAYOUT_ACTIVATION_RECEIPT", raising=False)

    assert layout.path("backend") == tmp_path / "02_BACKEND"


def test_loaded_layout_and_runtime_routing_validation_are_process_cached(monkeypatch):
    import lawrag.platform.workspace as workspace_mod

    assert load_layout() is load_layout()
    layout = load_layout()
    monkeypatch.setenv("LAWRAG_LAYOUT_VERSION", "v2")
    monkeypatch.setenv(
        "LAWRAG_LAYOUT_ACTIVATION_RECEIPT",
        "00_SYSTEM/MIGRATION/ACTIVATION_CANDIDATES/20260903-receipt-bound-v2-v7.json",
    )
    calls = 0
    original = workspace_mod._load_bound_final_receipt

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(workspace_mod, "_load_bound_final_receipt", counted)
    assert layout.path("data") == layout.root / "01_DATA"
    assert layout.path("runtime") == layout.root / "90_RUNTIME"
    assert calls == 1


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


def test_migration_target_resolves_exact_receipt_bound_generation(
    tmp_path, monkeypatch
):
    layout = _activated_backend_layout(tmp_path, monkeypatch)

    assert layout.migration_target("lawrag") == (
        tmp_path / "02_BACKEND/GENERATIONS/test/lawrag"
    )
    with pytest.raises(LayoutError, match="exactly one migration target"):
        layout.migration_target("missing-source")


def test_migration_target_is_v2_only_and_rejects_live_target_drift(
    tmp_path, monkeypatch
):
    layout = _activated_backend_layout(tmp_path, monkeypatch)
    target = tmp_path / "02_BACKEND/GENERATIONS/test/lawrag/__init__.py"
    target.write_text("VERSION = 999\n", "utf-8")

    with pytest.raises(LayoutError, match="no longer matches final receipt"):
        layout.migration_target("lawrag")

    monkeypatch.setenv("LAWRAG_LAYOUT_VERSION", "v1")
    with pytest.raises(LayoutError, match="runtime-visible only in v2"):
        layout.migration_target("lawrag")


def test_runtime_routing_is_lightweight_but_full_activation_audit_detects_drift(
    tmp_path, monkeypatch
):
    layout = _activated_backend_layout(tmp_path, monkeypatch)
    target = tmp_path / "02_BACKEND/GENERATIONS/test/lawrag/__init__.py"
    target.write_text("VERSION = 999\n", "utf-8")

    assert layout.path("backend") == tmp_path / "02_BACKEND"
    with pytest.raises(LayoutError, match="target no longer matches receipt"):
        layout.validate_activation()


def test_runtime_routing_still_rejects_final_receipt_byte_tampering(
    tmp_path, monkeypatch
):
    layout = _activated_backend_layout(tmp_path, monkeypatch)
    final_path = tmp_path / "00_SYSTEM/final.json"
    final = json.loads(final_path.read_text("utf-8"))
    final["receipt_sha256"] = "f" * 64
    final_path.write_text(json.dumps(final, sort_keys=True) + "\n", "utf-8")

    with pytest.raises(LayoutError, match="receipt_sha256"):
        layout.path("backend")


def test_v2_serve_bootstrap_uses_receipt_bound_backend_target():
    serve = (Path(__file__).parents[2] / "scripts/serve.sh").read_text("utf-8")

    assert 'migration_target("lawrag").parent' in serve
    assert 'PYTHONPATH="$workspace_root${PYTHONPATH:+:$PYTHONPATH}"' in serve
    assert 'backend_app_dir="$workspace_root/02_BACKEND"' not in serve
