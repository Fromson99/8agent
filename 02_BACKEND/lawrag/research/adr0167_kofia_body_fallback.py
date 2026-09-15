#!/usr/bin/env python3
"""ADR-0167 frozen runner entry point kept inside the research boundary."""
from __future__ import annotations

import runpy
from pathlib import Path


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "00_SYSTEM/WORKSPACE.json").is_file()
)


if __name__ == "__main__":
    runpy.run_path(
        str(ROOT / "06_TOOLS/MIGRATION/validate_kofia_body_fallback.py"),
        run_name="__main__",
    )
