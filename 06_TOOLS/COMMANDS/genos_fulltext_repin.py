#!/usr/bin/env python3
"""Refresh only the three fulltext patch code hashes in pinned engine manifests."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PATCHED = (
    "02_BACKEND/semantic_runtime/fulltext.py",
    "02_BACKEND/semantic_runtime/term_agent.py",
    "02_BACKEND/semantic_runtime/term_index.py",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(raw: str, before: str, after: str, path: Path) -> str:
    if raw.count(before) != 1:
        raise ValueError(f"expected one hash binding in {path}: {before}")
    return raw.replace(before, after)


def repin(root: Path) -> int:
    root = root.resolve(strict=True)
    pipeline_path = root / "00_SYSTEM/PIPELINE.json"
    pipeline_raw = pipeline_path.read_text("utf-8")
    pipeline = json.loads(pipeline_raw)
    changed = 0
    for engine_id, binding in pipeline["engines"].items():
        manifest_path = root / binding["manifest"]
        manifest_raw = manifest_path.read_text("utf-8")
        manifest = json.loads(manifest_raw)
        for relative in PATCHED:
            if relative not in manifest["files"]:
                continue
            old = manifest["files"][relative]
            new = sha(root / relative)
            if old == new:
                continue
            manifest_raw = replace_once(manifest_raw,
                f'"{relative}": "{old}"', f'"{relative}": "{new}"', manifest_path)
        if manifest_raw == manifest_path.read_text("utf-8"):
            continue
        manifest_path.write_text(manifest_raw, encoding="utf-8")
        new_hash = sha(manifest_path)
        old_hash = binding["sha256"]
        pipeline_raw = replace_once(pipeline_raw,
            f'"sha256": "{old_hash}"', f'"sha256": "{new_hash}"', pipeline_path)
        changed += 1
        print(f"REPinned {engine_id}")
    if changed:
        pipeline_path.write_text(pipeline_raw, encoding="utf-8")
    print(f"PATCHED_ENGINE_MANIFESTS={changed}")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--code-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    repin(args.code_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
