#!/usr/bin/env python3
"""Stable entrypoint for the hash-pinned ADR-0359 contract runner."""
from pathlib import Path
import runpy

ROOT = next(path for path in Path(__file__).resolve().parents
            if (path / "00_SYSTEM" / "WORKSPACE.json").is_file())
runpy.run_path(str(ROOT / "04_EXPERIMENTS/ADR/ADR-0359-deterministic-lawxml-semantic-hints/artifacts/run_contracts.py"),
               run_name="__main__")
