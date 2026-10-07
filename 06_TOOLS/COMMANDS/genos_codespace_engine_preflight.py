#!/usr/bin/env python3
"""Check every configured engine's pinned code before an expensive GENOS request."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[2]


def check(root: Path) -> tuple[int, int, list[str]]:
    root = root.resolve()
    pipeline = json.loads((root / "00_SYSTEM/PIPELINE.json").read_text(encoding="utf-8"))
    actual: dict[str, str | None] = {}
    errors: dict[str, str] = {}

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
        for relative, expected in sorted(manifest["files"].items()):
            observed = digest(relative)
            if observed != expected:
                errors.setdefault(relative, f"{relative}: expected {expected}, got {observed or 'MISSING'}")
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
