#!/usr/bin/env python3
"""Run the reusable ontology lifecycle CLI from an unpacked repository."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "02_BACKEND"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from lawrag.pipeline.ontology import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
