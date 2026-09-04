#!/usr/bin/env python3
"""Issue the immutable source-retirement authorization; never deletes data."""
from __future__ import annotations

import argparse

from lawrag.platform.workspace import (
    create_legacy_retirement_receipt,
    load_layout,
    persist_immutable_migration_record,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--activation",
        default="00_SYSTEM/MIGRATION/ACTIVATIONS/20260903-permanent-v2.json",
    )
    parser.add_argument(
        "--output",
        default="00_SYSTEM/MIGRATION/RETIREMENTS/20260903-legacy-roots.json",
    )
    parser.add_argument(
        "--retirement-id", default="20260903-legacy-roots-retirement"
    )
    args = parser.parse_args()
    layout = load_layout()
    receipt = create_legacy_retirement_receipt(
        layout, args.activation, retirement_id=args.retirement_id
    )
    file_sha256 = persist_immutable_migration_record(layout, args.output, receipt)
    print(
        f"authorized sources={len(receipt.sources)} "
        f"record={receipt.receipt_sha256} file={file_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
