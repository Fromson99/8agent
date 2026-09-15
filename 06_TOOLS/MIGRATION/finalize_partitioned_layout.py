#!/usr/bin/env python3
"""Publish and verify one complete, partition-aware workspace migration.

The legacy roots remain untouched.  Nested legacy roots are migrated by their
own logical root, while direct children of the parent root are represented as
independent plan items.  Generated frontend build/cache directories are the
only declared exclusions.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from lawrag.platform.workspace import (
    build_migration_plan,
    compare_dual_read,
    execute_copy_verify_zero,
    load_layout,
    persist_immutable_migration_record,
    verify_final_migration,
)


DEFAULT_RECORD_PREFIX = (
    "00_SYSTEM/MIGRATION/RECEIPTS/20260903-workspace-partition-final-v10"
)
GENERATION = "20260903-final-v9"
ADR_V2_GENERATION = "20260903-final-v2"
ADR_V3_GENERATION = "20260903-final-v3"
ADR_V5_GENERATION = "20260903-final-v5"
ADR_V6_GENERATION = "20260903-final-v10"
SCRIPT_GENERATION = "20260903-final-v10"
ARTIFACT_GENERATION = "20260903-final"
FRONTEND_EXCLUSION_NAMES = frozenset(
    {".git", ".next", ".vinext", ".wrangler", "dist", "node_modules"}
)


def _direct_children(root: Path, relative: str) -> tuple[str, ...]:
    directory = root / relative
    return tuple(
        f"{relative}/{entry.name}"
        for entry in sorted(os.scandir(directory), key=lambda row: os.fsencode(row.name))
        if not (
            entry.name == ".LAWRAG_PUBLICATION_INCOMPLETE"
            or (
                entry.name.startswith(".")
                and entry.name.endswith(".LAWRAG_PUBLICATION_INCOMPLETE")
            )
        )
    )


def migration_pairs(root: Path) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []

    for source in _direct_children(root, "data"):
        name = Path(source).name
        if name == "_archive":
            continue
        target_name = "LEGACY_README.md" if name == "README.md" else name
        pairs.append((source, f"01_DATA/{target_name}"))

    pairs.append(
        (
            "lawrag",
            f"02_BACKEND/GENERATIONS/{GENERATION}/lawrag",
        )
    )

    for source in _direct_children(root, "experiment-studio"):
        name = Path(source).name
        if name in FRONTEND_EXCLUSION_NAMES:
            continue
        pairs.append((source, f"03_FRONTEND/APPS/experiment-studio/{name}"))

    for source in _direct_children(root, "docs/adr"):
        name = Path(source).name
        if name == "ADR-0160-v2-physical-layout-cutover":
            target = f"04_EXPERIMENTS/GENERATIONS/{ADR_V2_GENERATION}/{name}"
        elif name in {
            "ADR-0161-receipt-bound-content-projection",
        }:
            target = f"04_EXPERIMENTS/GENERATIONS/{ADR_V3_GENERATION}/{name}"
        elif name in {
            "ADR-0162-activation-runtime-validation-split",
        }:
            target = f"04_EXPERIMENTS/GENERATIONS/{ADR_V5_GENERATION}/{name}"
        elif name in {
            "ADR-0163-v2-permanent-cutover-rag-genos-retirement",
            "EXPERIMENT_GRAPH.json",
            "EXPERIMENT_GRAPH.md",
            "README.md",
        }:
            target = f"04_EXPERIMENTS/GENERATIONS/{ADR_V6_GENERATION}/{name}"
        else:
            target = f"04_EXPERIMENTS/LEGACY_ADR/{name}"
        pairs.append((source, target))

    pairs.extend(
        (
            ("benchmarks", "04_EXPERIMENTS/BENCHMARKS"),
            (
                "tests",
                f"05_TESTS/GENERATIONS/{GENERATION}/LEGACY_TESTS",
            ),
            (
                "scripts",
                f"06_TOOLS/GENERATIONS/{SCRIPT_GENERATION}/LEGACY_SCRIPTS",
            ),
        )
    )

    for source in _direct_children(root, "docs"):
        name = Path(source).name
        if name == "adr":
            continue
        pairs.append((source, f"07_DOCS/REFERENCE/{name}"))

    pairs.extend(
        (
            ("config", "08_DEPLOYMENT/CONFIG"),
            (
                "artifacts",
                f"09_ARTIFACTS/GENERATIONS/{ARTIFACT_GENERATION}/LEGACY_ARTIFACTS",
            ),
            (
                "var",
                f"90_RUNTIME/GENERATIONS/{GENERATION}/LEGACY_VAR",
            ),
            ("data/_archive", "99_ARCHIVE/LEGACY_DATA_ARCHIVE"),
            (
                "ADR-0043-smoke-probe",
                "99_ARCHIVE/EXPERIMENTS/ROOT_ORPHANS/ADR-0043-smoke-probe",
            ),
            (
                "ADR-0047-order-safe",
                "99_ARCHIVE/EXPERIMENTS/ROOT_ORPHANS/ADR-0047-order-safe",
            ),
            (
                "CM_MAJOR_LEGAL_QUESTIONS_260819.docx",
                "01_DATA/INBOX/CM_MAJOR_LEGAL_QUESTIONS_260819.docx",
            ),
            (
                "adr_notion_import.csv",
                "99_ARCHIVE/IMPORTS/adr_notion_import.csv",
            ),
            (
                "ax-experiment-studio-social-preview.png",
                "09_ARTIFACTS/MEDIA/ax-experiment-studio-social-preview.png",
            ),
            (
                "genos-jupyterlab-commands-20260901.txt",
                "08_DEPLOYMENT/GENOS/RUNBOOKS/jupyterlab-commands-20260901.txt",
            ),
        )
    )
    return tuple(pairs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-prefix", default=DEFAULT_RECORD_PREFIX)
    args = parser.parse_args()

    layout = load_layout()
    pairs = migration_pairs(layout.root)
    exclusions = {
        "frontend": tuple(
            f"experiment-studio/{name}"
            for name in sorted(FRONTEND_EXCLUSION_NAMES)
            if (layout.root / "experiment-studio" / name).is_dir()
        )
    }

    print(f"freezing {len(pairs)} non-overlapping migration items", flush=True)
    plan = build_migration_plan(layout, pairs)
    prefix = args.record_prefix
    plan_file_sha256 = persist_immutable_migration_record(
        layout, f"{prefix}.plan.json", plan
    )
    print(f"plan persisted sha256={plan_file_sha256}", flush=True)

    copied = execute_copy_verify_zero(layout, plan)
    copy_file_sha256 = persist_immutable_migration_record(
        layout, f"{prefix}.copy-verify-0.json", copied
    )
    print(f"copy verified sha256={copy_file_sha256}", flush=True)

    dual = compare_dual_read(layout, plan, copied)
    dual_file_sha256 = persist_immutable_migration_record(
        layout, f"{prefix}.dual-read-compare.json", dual
    )
    print(f"dual read verified sha256={dual_file_sha256}", flush=True)

    already_canonical = (
        tuple(sorted(layout.roots))
        if layout.mode == "v2-only"
        else ("system",)
    )
    final = verify_final_migration(
        layout,
        plan,
        dual,
        already_canonical_root_ids=already_canonical,
        excluded_legacy_sources={} if layout.mode == "v2-only" else exclusions,
    )
    final_file_sha256 = persist_immutable_migration_record(
        layout, f"{prefix}.final-verify.json", final
    )
    print(
        "final verified "
        f"plan={plan.plan_sha256} receipt={final.receipt_sha256} "
        f"file_sha256={final_file_sha256}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
