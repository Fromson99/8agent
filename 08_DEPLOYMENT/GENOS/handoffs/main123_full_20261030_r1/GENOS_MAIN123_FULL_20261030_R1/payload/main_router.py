"""Select external Python workflow/SSE or direct in-process JSON chat."""
from __future__ import annotations

import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from genos_diagnostics import install as install_system_logging

install_system_logging("router")


sys.path.insert(0, str(ROOT / "08_DEPLOYMENT/GENOS"))

REQUESTED_MODE = os.getenv("GENOS_MAIN_MODE", "workflow").strip().lower()
# R1's name is retained as an alias for the external workflow backend.
MODE = "workflow" if REQUESTED_MODE == "existing" else REQUESTED_MODE
if MODE == "workflow":
    from main_workflow import app
elif MODE == "integrated":
    from main import app
else:
    raise RuntimeError("GENOS_MAIN_MODE must be workflow or integrated (existing aliases workflow)")


if __name__ == "__main__":
    sys.modules.setdefault("main_router", sys.modules[__name__])
    from start_sse import main as start

    start(["--app", "main_router:app", *sys.argv[1:]])
