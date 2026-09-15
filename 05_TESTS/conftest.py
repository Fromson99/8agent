"""Permanent-v2 pytest bootstrap.

The historical regression suite imports tool modules through the old ``scripts``
package name.  Keep that import surface test-only while resolving the modules
from the canonical tools root; production code must use ``06_TOOLS/run_tool.py``.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_TOOL_ROOT = WORKSPACE_ROOT / "06_TOOLS" / "EXPERIMENTS"
TOOL_ROOTS = (
    WORKSPACE_ROOT / "06_TOOLS" / "COMMANDS",
    *sorted(path for path in EXPERIMENT_TOOL_ROOT.rglob("*") if path.is_dir()),
)
REGRESSION_TESTS_ROOT = WORKSPACE_ROOT / "05_TESTS" / "REGRESSION"

os.environ.setdefault("LAWRAG_WORKSPACE_ROOT", str(WORKSPACE_ROOT))
os.environ.setdefault("LAWRAG_TOOL_WORKSPACE_ROOT", str(WORKSPACE_ROOT))

for tool_root in reversed(TOOL_ROOTS):
    if str(tool_root) not in sys.path:
        sys.path.insert(0, str(tool_root))

scripts = types.ModuleType("scripts")
scripts.__path__ = [str(path) for path in TOOL_ROOTS]
scripts.__package__ = "scripts"
sys.modules.setdefault("scripts", scripts)

tests = types.ModuleType("tests")
tests.__path__ = [str(REGRESSION_TESTS_ROOT)]
tests.__package__ = "tests"
sys.modules.setdefault("tests", tests)
