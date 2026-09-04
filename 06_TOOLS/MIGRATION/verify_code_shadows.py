#!/usr/bin/env python3
"""Fingerprint and receipt already-synchronized v2 code/test/tool shadows.

This verifier never mutates a source or replaces a target.  The migration API
accepts the targets only when every byte, mode, and directory member already
matches, then emits immutable copy/dual-read records for the current generation.
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


DEFAULT_RECORD_PREFIX = (
    "00_SYSTEM/MIGRATION/RECEIPTS/20260903-code-shadows-refresh"
)
PAIRS = (
    ("lawrag", "02_BACKEND/lawrag"),
    ("tests", "05_TESTS/LEGACY_TESTS"),
    ("scripts", "06_TOOLS/LEGACY_SCRIPTS"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-prefix", default=DEFAULT_RECORD_PREFIX)
    args = parser.parse_args()

    layout = load_layout()
    plan = build_migration_plan(layout, PAIRS)
    prefix = args.record_prefix
    persist_immutable_migration_record(layout, f"{prefix}.plan.json", plan)
    copy_receipt = execute_copy_verify_zero(layout, plan)
    persist_immutable_migration_record(
        layout, f"{prefix}.copy-verify-0.json", copy_receipt
    )
    dual_receipt = compare_dual_read(layout, plan, copy_receipt)
    persist_immutable_migration_record(
        layout, f"{prefix}.dual-read-compare.json", dual_receipt
    )
    print(
        "completed "
        f"plan={plan.plan_sha256} dual_read={dual_receipt.receipt_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
