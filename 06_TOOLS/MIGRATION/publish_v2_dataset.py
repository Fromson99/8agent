#!/usr/bin/env python3
"""Publish or verify the receipt-bound v2 local dataset."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from lawrag.datasets.publisher import inventory_sources, publish_workspace, verify_publication


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("audit", "publish", "verify"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()

    if args.command == "audit":
        rows = inventory_sources(root)
        result = {
            "schema_version": "source-package-audit-v1",
            "result": "pass",
            "sources": [
                {
                    "name": row.name,
                    "manifest_sha256": row.manifest_sha256,
                    "item_count": row.item_count,
                    "declared_file_count": len(row.files),
                }
                for row in rows
            ],
            "item_count": sum(row.item_count for row in rows),
            "declared_file_count": sum(len(row.files) for row in rows),
            "external_calls": {"llm": 0, "embedding": 0, "network": 0},
        }
    elif args.command == "publish":
        result = publish_workspace(root).receipt()
    else:
        if args.receipt is None:
            parser.error("verify requires --receipt")
        result = verify_publication(root, json.loads(args.receipt.read_text("utf-8")))
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
