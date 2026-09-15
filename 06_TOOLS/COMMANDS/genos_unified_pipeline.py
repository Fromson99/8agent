#!/usr/bin/env python3
"""Run the GENOS external/internal raw ingress and common pipeline CLI."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
BACKEND = ROOT / "02_BACKEND"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from lawrag.pipeline.genos_unified import main as common_main  # noqa: E402


def main(argv=None):
    # Only this explicit subcommand selects GENOS; all older commands are unchanged.
    import argparse
    argv = list(sys.argv[1:] if argv is None else argv)
    probe = argparse.ArgumentParser(add_help=False)
    probe.add_argument('--data-root')
    probe.add_argument('--json', action='store_true')
    _, remaining = probe.parse_known_args(argv)
    if remaining and remaining[0] == 'e2e':
        from lawrag.pipeline.genos_e2e import main as e2e_main
        return e2e_main(argv)
    if remaining and remaining[0] == 'build':
        from lawrag.pipeline.genos_build import main as build_main
        return build_main(argv)
    return common_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
