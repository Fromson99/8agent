#!/usr/bin/env python3
"""Run one receipt-bound migrated tool after the lowercase scripts/ root retires."""
from __future__ import annotations

import json
import hashlib
import os
import runpy
import sys
import types
from pathlib import Path


def _enforce_active_tool_policy(root: Path, name: str) -> None:
    policy_path = root / "06_TOOLS" / "ACTIVE_TOOLS.json"
    try:
        policy = json.loads(policy_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"active tool policy is unavailable: {exc}") from exc
    allowed = policy.get("tools")
    if policy.get("schema_version") != "active-tools-v1" or not isinstance(allowed, list):
        raise SystemExit("active tool policy is invalid")
    if name not in allowed:
        reason = (policy.get("retired") or {}).get(name)
        detail = f": {reason}" if isinstance(reason, str) else ""
        raise SystemExit(f"tool is historical or retired and cannot run: {name}{detail}")


def _targets(root: Path) -> tuple[Path, Path]:
    manifest = json.loads((root / "00_SYSTEM/WORKSPACE.json").read_text("utf-8"))
    lifecycle = manifest.get("lifecycle") or {}
    activation_value = lifecycle.get("activation_receipt")
    if not isinstance(activation_value, str) or not activation_value:
        raise SystemExit("workspace lifecycle.activation_receipt is not configured")
    retirement_value = lifecycle.get("retirement_receipt")
    if not isinstance(retirement_value, str) or not retirement_value:
        raise SystemExit("workspace lifecycle.retirement_receipt is not configured")
    os.environ["LAWRAG_LAYOUT_RETIREMENT_RECEIPT"] = str(root / retirement_value)
    activation = json.loads((root / activation_value).read_text("utf-8"))
    final_path = root / activation["validation_receipt_path"]
    final_raw = final_path.read_bytes()
    if hashlib.sha256(final_raw).hexdigest() != activation.get(
        "validation_receipt_sha256"
    ):
        raise SystemExit("active final receipt hash verification failed")
    final = json.loads(final_raw)

    def one(source: str) -> Path:
        matches = [row for row in final.get("items", []) if row.get("source") == source]
        if len(matches) != 1:
            raise SystemExit(f"active final receipt must bind one {source!r} target")
        return (root / matches[0]["target"]).resolve()

    return one("lawrag"), one("scripts")


def main() -> None:
    # Generated code trees are receipt-fingerprinted.  Import-time .pyc files
    # would mutate a verified tree before the target tool can run.
    sys.dont_write_bytecode = True
    if len(sys.argv) < 2:
        raise SystemExit("usage: run_tool.py <tool filename> [arguments ...]")
    name = sys.argv[1]
    if not name or Path(name).name != name or name in {".", ".."}:
        raise SystemExit("tool must be a filename inside the active tools generation")
    root = Path(__file__).resolve().parents[1]
    _enforce_active_tool_policy(root, name)
    if name == 'rag_main_promotion.py':
        pointer=json.loads((root/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
        if pointer.get('schema_version')=='semantic-runtime-active-v2':
            # MAIN management follows the active runtime; the retired MAIN state
            # must not be displayed as the operational generation.
            sys.path.insert(0,str(root/'02_BACKEND'))
            from semantic_runtime.control import main as semantic_main
            sys.argv=[sys.argv[0],*sys.argv[2:]]
            semantic_main()
            return
    if name in ('adr_structure.py', 'legal_agent_trace.py', 'legal_agent_contracts.py',
                'genos_preflight.py', 'genos_call.sh', 'genos_smoke.sh'):
        # Explicit working-code policy/contract tools and operator trace. Other
        # receipt-bound tools retain their selected generations.
        command_root = root / '06_TOOLS' / 'COMMANDS'
        target = command_root / name
        if not target.is_file() or target.is_symlink():
            raise SystemExit('working policy/contract tool unavailable')
        sys.path.insert(0, str(command_root))
        arguments = sys.argv[2:]
        if target.suffix == '.sh':
            os.execv('/usr/bin/bash', ['bash', str(target), *arguments])
        sys.argv = [str(target), *arguments]
        runpy.run_path(str(target), run_name='__main__')
        return
    backend, tools = _targets(root)
    sys.path.insert(0, str(backend.parent))
    from lawrag.platform.workspace import load_layout

    layout = load_layout(root)
    if layout.migration_target("lawrag") != backend:
        raise SystemExit("backend target verification failed")
    if layout.migration_target("scripts") != tools:
        raise SystemExit("tools target verification failed")
    # Historical tools import each other through ``scripts.*``.  Keep that
    # namespace virtual and receipt-bound; no retired top-level scripts tree is
    # recreated on disk.
    scripts_package = types.ModuleType("scripts")
    scripts_package.__path__ = [str(tools)]
    scripts_package.__package__ = "scripts"
    sys.modules["scripts"] = scripts_package
    sys.path.insert(0, str(tools))
    os.environ["LAWRAG_TOOL_WORKSPACE_ROOT"] = str(root)
    target = tools / name
    if not target.is_file() or target.is_symlink():
        raise SystemExit(f"active tool does not exist: {name}")
    sys.argv = [str(target), *sys.argv[2:]]
    if target.suffix == ".py":
        runpy.run_path(str(target), run_name="__main__")
        return
    if target.suffix == ".sh":
        os.execv("/usr/bin/bash", ["bash", str(target), *sys.argv[1:]])
    raise SystemExit("only .py and .sh tools are supported")


if __name__ == "__main__":
    main()
