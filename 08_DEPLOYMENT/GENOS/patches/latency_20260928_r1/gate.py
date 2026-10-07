#!/usr/bin/env python3
"""Fail closed when a GENOS code ZIP, Git checkout, and generation diverge.

Run after committing the code and before pushing/deploying it. The gate does not
push, deploy, change the generation, or call a model. A PASS proves the local
checkout and selected generation, not the later code-serving revision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import zipfile


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def compare_zip_to_checkout(archive_path: Path, deploy_root: Path) -> dict:
    """Check every packaged byte against the committed deployment checkout."""
    root = deploy_root.resolve(strict=True)
    git_root = Path(git(root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if git_root != root:
        raise ValueError(f"deploy root is not the Git root: {root}")
    changed = git(root, "status", "--porcelain=v1", "--untracked-files=no")
    if changed:
        raise ValueError("deployment checkout has uncommitted tracked changes")
    tracked = set(git(root, "ls-files", "-z").split("\0"))
    mismatches = []
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "CODE_MANIFEST.json" not in names:
            raise ValueError("code ZIP has duplicate paths or no CODE_MANIFEST.json")
        manifest_raw = archive.read("CODE_MANIFEST.json")
        manifest = json.loads(manifest_raw)
        if manifest.get("format") != "8agent-code/1":
            raise ValueError("unsupported code ZIP manifest")
        rows = manifest.get("files")
        if not isinstance(rows, list):
            raise ValueError("code ZIP has no file inventory")
        expected = {}
        for row in rows:
            name = row["path"]
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts or "\\" in name or str(pure) != name:
                raise ValueError(f"unsafe code ZIP path: {name}")
            if name in expected:
                raise ValueError(f"duplicate manifest path: {name}")
            expected[name] = row
        if set(names) - {"CODE_MANIFEST.json"} != set(expected):
            raise ValueError("code ZIP files differ from its manifest")
        for name, row in expected.items():
            raw = archive.read(name)
            expected_sha = row["sha256"]
            if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != expected_sha:
                raise ValueError(f"code ZIP content differs from its manifest: {name}")
            target = root / name
            if name not in tracked:
                mismatches.append(f"not committed: {name}")
            elif not target.is_file() or target.is_symlink() or sha(target) != expected_sha:
                mismatches.append(f"different bytes: {name}")
    if mismatches:
        detail = "; ".join(mismatches[:12])
        raise ValueError(f"ZIP/deployment checkout mismatch ({len(mismatches)} files): {detail}")
    return {"code_files": len(expected), "commit": git(root, "rev-parse", "HEAD"),
            "code_zip_sha256": sha(archive_path), "code_manifest_sha256":
            hashlib.sha256(manifest_raw).hexdigest()}


def check_generation(root: Path, generation: Path) -> None:
    selected = generation.resolve(strict=True)
    if not selected.is_dir() or generation.is_symlink():
        raise ValueError("generation must be a real directory")
    env = os.environ.copy()
    env["GENOS_GENERATION"] = str(selected)
    env["PYTHONPATH"] = str(root / "02_BACKEND")
    command = [sys.executable, str(root / "06_TOOLS/COMMANDS/genos_generation_e2e.py"),
               "--code-root", str(root), "--generation", str(selected)]
    subprocess.run(command, check=True, cwd=root, env=env)
    script = ("import sys; from lawrag.pipeline.term_serving_bundle import verify_assets; "
              "result=verify_assets(sys.argv[1]); "
              "assert result['verified'] is True; print('VERIFY_ASSETS PASS')")
    subprocess.run([sys.executable, "-c", script, str(selected)],
                   check=True, cwd=root, env=env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--code-zip", required=True, type=Path)
    parser.add_argument("--deploy-root", required=True, type=Path,
                        help="committed Git checkout used to build the code-serving revision")
    parser.add_argument("--generation", type=Path,
                        help="exact GENOS_GENERATION; required unless --code-only")
    parser.add_argument("--code-only", action="store_true")
    args = parser.parse_args(argv)
    if not args.code_only and args.generation is None:
        parser.error("--generation is required unless --code-only")
    try:
        root = args.deploy_root.resolve(strict=True)
        receipt = compare_zip_to_checkout(args.code_zip.resolve(strict=True), root)
        print("CODE_CHECK PASS", json.dumps(receipt, ensure_ascii=False), flush=True)
        if not args.code_only:
            check_generation(root, args.generation)
            print("GENERATION_CHECK PASS", flush=True)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError,
            zipfile.BadZipFile) as exc:
        print("GENOS_RELEASE_GATE FAIL", type(exc).__name__, str(exc), flush=True)
        return 1
    print("GENOS_RELEASE_GATE PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
