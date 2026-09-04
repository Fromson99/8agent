#!/usr/bin/env python3
"""Copy the immutable legacy ADR corpus into the v2 experiments root.

Run this only from the repository root.  The workspace migration API creates
an exact source fingerprint before copying, publishes without replacement,
and records copy and dual-read receipts.  It never moves or deletes the
legacy ``docs/adr`` source.
"""

from __future__ import annotations

import argparse

from lawrag.platform.workspace import (
    build_migration_plan,
    compare_dual_read,
    execute_copy_verify_zero,
    load_layout,
    persist_immutable_migration_record,
)


DEFAULT_RECORD_PREFIX = "00_SYSTEM/MIGRATION/RECEIPTS/20260903-adr-lineage-shadow"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-prefix", default=DEFAULT_RECORD_PREFIX)
    args = parser.parse_args()

    layout = load_layout()
    plan = build_migration_plan(
        layout,
        [("docs/adr", "04_EXPERIMENTS/LEGACY_ADR")],
    )
    prefix = args.record_prefix
    persist_immutable_migration_record(layout, f"{prefix}.plan.json", plan)
    copy_receipt = execute_copy_verify_zero(layout, plan)
    persist_immutable_migration_record(
        layout,
        f"{prefix}.copy-verify-0.json",
        copy_receipt,
    )
    dual_receipt = compare_dual_read(layout, plan, copy_receipt)
    persist_immutable_migration_record(
        layout,
        f"{prefix}.dual-read-compare.json",
        dual_receipt,
    )
    print(
        "completed "
        f"plan={plan.plan_sha256} dual_read={dual_receipt.receipt_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
