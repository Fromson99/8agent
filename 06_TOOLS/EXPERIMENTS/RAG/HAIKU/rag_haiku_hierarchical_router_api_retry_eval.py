#!/usr/bin/env python3
"""ADR-0109 safe entry point for the fixed hierarchical-router API probe.

The implementation remains shared with the ADR-0108 runner, but this entry
point switches every mutable output and artifact identity to ADR-0109 before
preflight or provider execution.  The shared runner then enforces that no
write target can escape the ADR-0109 directory and refuses to overwrite an
existing immutable run artifact.
"""

from __future__ import annotations

from typing import Sequence

import rag_haiku_hierarchical_router_api_eval as runner


def main(argv: Sequence[str] | None = None) -> int:
    runner.configure_for_adr_0109()
    return runner.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
