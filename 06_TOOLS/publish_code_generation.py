#!/usr/bin/env python3
"""Publish and locally activate an immutable v2 backend/tool generation.

The migration receipt contract still addresses the retired logical sources
``lawrag`` and ``scripts``.  This publisher stages short-lived, exact copies of
the editable v2 trees at those names, runs the normal three receipt phases,
creates retirement evidence, and removes only the staging roots it created.
Python caches and test caches are never part of an immutable generation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.platform import workspace  # noqa: E402


def _write_once(path: Path, value: dict) -> str:
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise RuntimeError(f"immutable record already differs: {path}")
    else:
        try:
            os.write(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return hashlib.sha256(raw).hexdigest()


def _copy_source(source: Path, staging: Path) -> None:
    if staging.exists():
        raise RuntimeError(f"legacy staging root already exists: {staging}")
    shutil.copytree(
        source,
        staging,
        symlinks=True,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".pytest_cache", "*.orig", "research", "corpus"
        ),
    )


def publish(generation: str) -> None:
    if not generation or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in generation):
        raise RuntimeError("generation must be lowercase kebab-case")
    layout = workspace.load_layout(ROOT)
    activation_rel = f"00_SYSTEM/MIGRATION/ACTIVATIONS/{generation}.json"
    retirement_rel = f"00_SYSTEM/MIGRATION/RETIREMENTS/{generation}.json"
    if layout.activation_receipt != activation_rel or layout.retirement_receipt != retirement_rel:
        raise RuntimeError("WORKSPACE.json lifecycle does not name this generation")

    pairs = {
        "lawrag": f"02_BACKEND/GENERATIONS/{generation}/lawrag",
        "scripts": f"06_TOOLS/GENERATIONS/{generation}/LEGACY_SCRIPTS",
    }
    staging_sources = [ROOT / "lawrag", ROOT / "scripts"]
    created: list[Path] = []
    try:
        _copy_source(ROOT / "02_BACKEND/lawrag", staging_sources[0])
        created.append(staging_sources[0])
        _copy_source(ROOT / "06_TOOLS/LEGACY_SCRIPTS", staging_sources[1])
        created.append(staging_sources[1])

        plan = workspace.build_migration_plan(layout, pairs)
        copied = workspace.execute_copy_verify_zero(layout, plan)
        dual = workspace.compare_dual_read(layout, plan, copied)
        final = workspace.verify_final_migration(
            layout,
            plan,
            dual,
            already_canonical_root_ids=layout.roots,
        )
        record_root = "00_SYSTEM/MIGRATION"
        workspace.persist_immutable_migration_record(
            layout, f"{record_root}/PLANS/{generation}.json", plan
        )
        workspace.persist_immutable_migration_record(
            layout, f"{record_root}/RECEIPTS/{generation}.copy-verify-0.json", copied
        )
        workspace.persist_immutable_migration_record(
            layout, f"{record_root}/RECEIPTS/{generation}.dual-read-compare.json", dual
        )
        final_rel = f"{record_root}/RECEIPTS/{generation}.final-verify.json"
        final_file_sha = workspace.persist_immutable_migration_record(
            layout, final_rel, final
        )
        activation = {
            "schema_version": workspace.ACTIVATION_RECEIPT_SCHEMA,
            "status": "active",
            "layout_version": "v2",
            "workspace_manifest_sha256": layout.manifest_sha256,
            "validation_receipt_path": final_rel,
            "validation_receipt_sha256": final_file_sha,
            "validation_record_sha256": final.receipt_sha256,
            "migration_plan_sha256": plan.plan_sha256,
            "activation_id": generation,
        }
        _write_once(ROOT / activation_rel, activation)
        retirement = workspace.create_legacy_retirement_receipt(
            layout, ROOT / activation_rel, retirement_id=f"retire-{generation}"
        )
        workspace.persist_immutable_migration_record(layout, retirement_rel, retirement)
    finally:
        for path in reversed(created):
            if path.parent != ROOT or path.name not in {"lawrag", "scripts"}:
                raise RuntimeError(f"refusing unsafe staging cleanup: {path}")
            shutil.rmtree(path)

    verified = workspace.load_layout(ROOT).validate_activation()
    print(json.dumps({
        "generation": generation,
        "items": len(verified["items"]),
        "backend": pairs["lawrag"],
        "tools": pairs["scripts"],
    }, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation", required=True)
    args = parser.parse_args()
    publish(args.generation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
