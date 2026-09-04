#!/usr/bin/env python3
"""Audit the numbered workspace layout without mutating it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# This is the one pre-install bootstrap CLI.  It searches for the workspace
# marker instead of assuming a fixed parent depth; installed entry points do
# not need this bridge.
for _candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
    if (_candidate / "00_SYSTEM" / "WORKSPACE.json").is_file():
        sys.path.insert(0, str(_candidate))
        break

from lawrag.platform.workspace import audit_top_level, load_layout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict-target",
        action="store_true",
        help="fail while any legacy or unknown top-level directory remains",
    )
    args = parser.parse_args()
    report = audit_top_level(load_layout())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["missing_canonical_roots"]:
        return 2
    if args.strict_target and not report["target_ready"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
