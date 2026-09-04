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
TOOLS_ROOT = WORKSPACE_ROOT / "06_TOOLS" / "LEGACY_SCRIPTS"
LEGACY_TESTS_ROOT = WORKSPACE_ROOT / "05_TESTS" / "LEGACY_TESTS"

os.environ.setdefault("LAWRAG_WORKSPACE_ROOT", str(WORKSPACE_ROOT))
os.environ.setdefault("LAWRAG_TOOL_WORKSPACE_ROOT", str(WORKSPACE_ROOT))

if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

scripts = types.ModuleType("scripts")
scripts.__path__ = [str(TOOLS_ROOT)]
scripts.__package__ = "scripts"
sys.modules.setdefault("scripts", scripts)

tests = types.ModuleType("tests")
tests.__path__ = [str(LEGACY_TESTS_ROOT)]
tests.__package__ = "tests"
sys.modules.setdefault("tests", tests)
