#!/usr/bin/env python3
"""Check every configured engine's pinned code before an expensive GENOS request."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[2]


def check(root: Path) -> tuple[int, int, list[str]]:
    root = root.resolve()
    pipeline = json.loads((root / "00_SYSTEM/PIPELINE.json").read_text(encoding="utf-8"))
    actual: dict[str, str | None] = {}
    errors: dict[str, str] = {}
    native_queries = False

    def digest(relative: str) -> str | None:
        if relative in actual:
            return actual[relative]
        source = root / relative
        candidate = source.resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            errors[relative] = f"INVALID PATH {relative}"
            actual[relative] = None
            return None
        if not candidate.is_file() or source.is_symlink():
            actual[relative] = None
            return None
        actual[relative] = hashlib.sha256(candidate.read_bytes()).hexdigest()
        return actual[relative]

    for engine, binding in sorted(pipeline["engines"].items()):
        manifest_path = binding["manifest"]
        observed = digest(manifest_path)
        expected = binding["sha256"]
        if observed != expected:
            errors.setdefault(manifest_path, f"{manifest_path}: expected {expected}, got {observed or 'MISSING'}")
            continue
        manifest = json.loads((root / manifest_path).read_text(encoding="utf-8"))
        native_queries |= "02_BACKEND/semantic_runtime/oracle_query_native.py" in manifest["files"]
        for relative, expected in sorted(manifest["files"].items()):
            observed = digest(relative)
            if observed != expected:
                errors.setdefault(relative, f"{relative}: expected {expected}, got {observed or 'MISSING'}")
    if native_queries:
        catalogue = "02_BACKEND/semantic_runtime/oracle_query_plans.py"
        try:
            tree = ast.parse((root / catalogue).read_text(encoding="utf-8"))
            sources = next(ast.literal_eval(node.value) for node in tree.body
                           if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SOURCES" for t in node.targets))
            for relative, expected in sources.items():
                if digest(relative) != expected:
                    errors.setdefault(relative, f"ORACLE QUERY CATALOGUE STALE {relative}: regenerate prepared queries")
        except (OSError, SyntaxError, ValueError, StopIteration, TypeError) as exc:
            errors[catalogue] = f"INVALID ORACLE QUERY CATALOGUE {type(exc).__name__}"
    # Serving reads Oracle navigation rows only from registered compiler versions
    # (semantic_runtime/navigation_compatibility.py). Code without the registry
    # predates it and keeps the exact-bytes rule.
    registry_path = "00_SYSTEM/ORACLE/navigation_compatibility.json"
    if (root / registry_path).is_file():
        try:
            registry = json.loads((root / registry_path).read_text(encoding="utf-8"))
            current = {name: digest(relative) for name, relative in registry["modules"].items()}
            known = [v["modules"] for group in registry["groups"] for v in group["versions"]]
            if current not in known:
                errors[registry_path] = ("NAVIGATION COMPATIBILITY UNREGISTERED: run "
                                         "06_TOOLS/maintenance/navigation_compatibility.py register --code-root <root> --source <why>")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors[registry_path] = f"INVALID NAVIGATION COMPATIBILITY REGISTRY {type(exc).__name__}"
    return len(pipeline["engines"]), len(actual), list(errors.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    engines, files, errors = check(args.code_root)
    if errors:
        print(f"ENGINE_PREFLIGHT FAIL engines={engines} files={files} mismatches={len(errors)}")
        for error in errors:
            print(error)
        return 1
    print(f"ENGINE_PREFLIGHT PASS engines={engines} files={files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
