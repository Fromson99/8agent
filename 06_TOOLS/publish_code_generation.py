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
from typing import Iterable


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


def _generation_name(value: str) -> str:
    if not value or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in value):
        raise RuntimeError("generation must be lowercase kebab-case")
    return value


def _verified_base_source(generation: str, source: str) -> tuple[Path, str]:
    """Resolve an earlier immutable generation through its sealed receipt."""
    receipt_path = ROOT / f"00_SYSTEM/MIGRATION/RECEIPTS/{generation}.final-verify.json"
    activation_path = ROOT / f"00_SYSTEM/MIGRATION/ACTIVATIONS/{generation}.json"
    receipt_raw = receipt_path.read_bytes()
    activation = json.loads(activation_path.read_text("utf-8"))
    if activation.get("validation_receipt_path") != str(receipt_path.relative_to(ROOT)):
        raise RuntimeError("base activation does not name its final receipt")
    if activation.get("validation_receipt_sha256") != hashlib.sha256(receipt_raw).hexdigest():
        raise RuntimeError("base activation/final receipt hash mismatch")
    receipt = json.loads(receipt_raw)
    rows = [row for row in receipt.get("items", []) if row.get("source") == source]
    if len(rows) != 1:
        raise RuntimeError(f"base receipt has no unique {source} target")
    row = rows[0]
    target = (ROOT / str(row["target"])).resolve()
    target.relative_to(ROOT.resolve())
    expected = workspace._fingerprint_from_mapping(
        row.get("fingerprint"), field=f"base {source} fingerprint"
    )
    if workspace._fingerprint_path(target) != expected:
        raise RuntimeError(f"base generation target changed: {target}")
    return target, hashlib.sha256(receipt_raw).hexdigest()


def _apply_overlays(paths: Iterable[str], staging: dict[str, Path]) -> list[dict]:
    prefixes = {
        "02_BACKEND/lawrag/": ("lawrag", Path("")),
        "06_TOOLS/COMMANDS/": ("scripts", Path("")),
    }
    records: list[dict] = []
    for raw in sorted(set(paths)):
        if not raw or Path(raw).is_absolute() or ".." in Path(raw).parts:
            raise RuntimeError(f"overlay must be a safe workspace-relative path: {raw}")
        match = next(
            ((prefix, key) for prefix, (key, _unused) in prefixes.items() if raw.startswith(prefix)),
            None,
        )
        if match is None:
            raise RuntimeError(f"overlay is outside supported code roots: {raw}")
        prefix, key = match
        source = (ROOT / raw).resolve()
        source.relative_to(ROOT.resolve())
        if not source.is_file() or source.is_symlink():
            raise RuntimeError(f"overlay must be a regular file: {raw}")
        relative = Path(raw.removeprefix(prefix))
        target = (staging[key] / relative).resolve()
        target.relative_to(staging[key].resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)
        records.append({
            "path": raw,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "bytes": source.stat().st_size,
        })
    return records


def publish(generation: str, *, base_generation: str | None = None,
            overlays: Iterable[str] = ()) -> None:
    generation = _generation_name(generation)
    layout = workspace.load_layout(ROOT)
    activation_rel = f"00_SYSTEM/MIGRATION/ACTIVATIONS/{generation}.json"
    retirement_rel = f"00_SYSTEM/MIGRATION/RETIREMENTS/{generation}.json"
    if layout.activation_receipt != activation_rel or layout.retirement_receipt != retirement_rel:
        raise RuntimeError("WORKSPACE.json lifecycle does not name this generation")

    pairs = {
        "lawrag": f"02_BACKEND/GENERATIONS/{generation}/lawrag",
        "scripts": f"06_TOOLS/GENERATIONS/{generation}/COMMANDS",
    }
    staging_sources = {"lawrag": ROOT / "lawrag", "scripts": ROOT / "scripts"}
    base_receipt_sha256 = None
    if base_generation:
        base_generation = _generation_name(base_generation)
        backend_source, backend_receipt_sha = _verified_base_source(base_generation, "lawrag")
        tools_source, tools_receipt_sha = _verified_base_source(base_generation, "scripts")
        if backend_receipt_sha != tools_receipt_sha:
            raise RuntimeError("base code targets are not bound to the same final receipt")
        source_roots = {"lawrag": backend_source, "scripts": tools_source}
        base_receipt_sha256 = backend_receipt_sha
    else:
        source_roots = {
            "lawrag": ROOT / "02_BACKEND/lawrag",
            "scripts": ROOT / "06_TOOLS/COMMANDS",
        }
    created: list[Path] = []
    overlay_records: list[dict] = []
    try:
        _copy_source(source_roots["lawrag"], staging_sources["lawrag"])
        created.append(staging_sources["lawrag"])
        _copy_source(source_roots["scripts"], staging_sources["scripts"])
        created.append(staging_sources["scripts"])
        overlay_records = _apply_overlays(overlays, staging_sources)

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
        _write_once(ROOT / f"00_SYSTEM/MIGRATION/OVERLAYS/{generation}.json", {
            "schema_version": "code-generation-overlay-v1",
            "generation": generation,
            "base_generation": base_generation,
            "base_final_receipt_sha256": base_receipt_sha256,
            "overlays": overlay_records,
        })
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
        "base_generation": base_generation,
        "overlays": len(overlay_records),
    }, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation", required=True)
    parser.add_argument("--base-generation")
    parser.add_argument(
        "--overlay", action="append", default=[],
        help="workspace-relative file to copy over the verified base generation",
    )
    args = parser.parse_args()
    publish(args.generation, base_generation=args.base_generation, overlays=args.overlay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
