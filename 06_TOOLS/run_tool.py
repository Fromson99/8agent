#!/usr/bin/env python3
"""Run one receipt-bound migrated tool after the lowercase scripts/ root retires."""
from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path


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
    final = json.loads(
        (root / activation["validation_receipt_path"]).read_text("utf-8")
    )

    def one(source: str) -> Path:
        matches = [row for row in final.get("items", []) if row.get("source") == source]
        if len(matches) != 1:
            raise SystemExit(f"active final receipt must bind one {source!r} target")
        return (root / matches[0]["target"]).resolve()

    return one("lawrag"), one("scripts")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: run_tool.py <tool filename> [arguments ...]")
    name = sys.argv[1]
    if not name or Path(name).name != name or name in {".", ".."}:
        raise SystemExit("tool must be a filename inside the active tools generation")
    root = Path(__file__).resolve().parents[1]
    backend, tools = _targets(root)
    sys.path.insert(0, str(backend.parent))
    from lawrag.platform.workspace import load_layout

    layout = load_layout(root)
    if layout.migration_target("lawrag") != backend:
        raise SystemExit("backend target verification failed")
    if layout.migration_target("scripts") != tools:
        raise SystemExit("tools target verification failed")
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
