#!/usr/bin/env python3
"""Read-only GENOS serving-generation/fulltext E2E gate.

Run in the same code revision and Python environment as code-serving:
  python3 06_TOOLS/COMMANDS/genos_generation_e2e.py --generation /nfs-root/.../generation

The generation path may instead come from GENOS_GENERATION or GENOS_DATA_ROOT/CURRENT.
Only identities, hashes, readiness and selected run status are printed; no source text.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shlex
import sys
import sqlite3
import time


PROFILE_FOR_IMPLEMENTATION = {
    "legal-agent-v1": "legal-agent-rag-v1",
    "legal-agent-tools-v2": "legal-agent-rag-v2",
    "legal-agent-tools-v3": "legal-agent-rag-v3",
    "legal-agent-tools-v4": "legal-agent-rag-v4",
    "legal-agent-tools-v5": "legal-agent-rag-v5",
    "legal-agent-unified-v6": "legal-agent-rag-v6",
}


def sha256(path: Path, *, progress: bool = False) -> str:
    digest = hashlib.sha256()
    last_report = time.monotonic()
    count = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
            count += len(chunk)
            if progress and time.monotonic() - last_report >= 30:
                print(f"HASHING {path.name} bytes={count}", flush=True)
                last_report = time.monotonic()
    return digest.hexdigest()


def source_manifest_digest(manifest: dict) -> str:
    """Use the same stable source fields as the current TermIndex contract."""
    source = {key: value for key, value in manifest.items()
              if key not in {"navigation", "fulltext", "fulltext_derivation"}}
    raw = json.dumps(source, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def selected_generation(explicit: Path | None = None, *, settings=None) -> Path:
    settings = os.environ if settings is None else settings
    configured = settings.get("GENOS_GENERATION", "").strip()
    if explicit is not None:
        path = explicit.resolve(strict=True)
        if configured and path != Path(configured).resolve(strict=True):
            raise ValueError("--generation differs from GENOS_GENERATION in this environment")
        return path
    if configured:
        path = Path(configured)
        if not path.is_absolute() or path.is_symlink() or not path.is_dir():
            raise ValueError('GENOS_GENERATION must be an absolute non-symlink directory')
        path = path.resolve(strict=True)
        if json.loads((path / 'manifest.json').read_text()).get('schema_version') not in {'term-source-generation-v1','term-source-generation-v2'}:
            raise ValueError('GENOS_GENERATION has an unsupported manifest')
        return path
    data_root = settings.get("GENOS_DATA_ROOT", "").strip()
    if data_root:
        root = Path(data_root)
        if not root.is_absolute() or root.is_symlink():
            raise ValueError('GENOS_DATA_ROOT must be an absolute non-symlink path')
        root = root.resolve(strict=True)
        pointer = root / "generations/CURRENT.json"
        value = json.loads(pointer.read_text("utf-8"))
        if value.get('schema_version') != 'genos-current-generation-v1':
            raise ValueError('GENOS CURRENT has an unsupported schema')
        path = Path(value['path'])
        if not path.is_absolute() or path.is_symlink():
            raise ValueError('GENOS CURRENT path must be absolute and non-symlink')
        path = path.resolve(strict=True)
        path.relative_to(root)
        if sha256(path / "manifest.json") != value["manifest_sha256"]:
            raise ValueError("GENOS_DATA_ROOT CURRENT manifest hash mismatch")
        return path
    raise ValueError("specify --generation or set GENOS_GENERATION/GENOS_DATA_ROOT")


class GenerationUnavailable(ValueError):
    """Serving-only settings are unavailable in this offline codespace."""


def operator_generation(code_root: Path) -> Path:
    """Reuse existing settings/pointers; never choose a directory by date or name.

    Runtime selection remains unchanged. These extra sources only help offline
    installation when codespace does not inherit code-serving's environment.
    """
    root = code_root.resolve(strict=True)
    names = ('GENOS_GENERATION', 'GENOS_DATA_ROOT')
    settings = {key: os.environ[key] for key in names if key in os.environ}
    # Read just the two literal data settings, without executing a shell file or
    # expanding unrelated credential values. Existing environment wins.
    env_file = root / '.env'
    if env_file.is_file() and not env_file.is_symlink():
        for line in env_file.read_text('utf-8').splitlines():
            match = re.match(r'^\s*(?:export\s+)?(GENOS_GENERATION|GENOS_DATA_ROOT)\s*=(.*)$', line)
            if match and match[1] not in os.environ:
                try:
                    values = shlex.split(match[2], comments=True)
                except ValueError as exc:
                    raise ValueError('Invalid literal GENOS data setting in .env') from exc
                if len(values) > 1 or (values and '$' in values[0]):
                    raise ValueError('GENOS data setting must be one literal absolute path')
                settings[match[1]] = values[0] if values else ''
    if any(settings.get(key, '').strip() for key in names):
        return selected_generation(settings=settings)
    # These are the documented setup's data roots, never arbitrary generations.
    candidates = set()
    for data_root in (root / '01_DATA', root / 'GENOS_DATA'):
        if (data_root / 'generations/CURRENT.json').is_file():
            candidates.add(selected_generation(settings={'GENOS_DATA_ROOT': str(data_root)}))
    if not candidates:
        for receipt_path in (root / 'TRANSFER').glob('*/VERIFIED_CHECKOUT.json'):
            value = json.loads(receipt_path.read_text('utf-8'))
            if not value.get('code_root') or Path(value['code_root']).resolve() != root:
                continue
            path = selected_generation(settings={'GENOS_GENERATION': value['generation']})
            if sha256(path / 'manifest.json') != value['generation_manifest_sha256']:
                raise ValueError('Previously verified generation changed')
            candidates.add(path)
    if len(candidates) > 1:
        raise ValueError('Existing data bindings disagree; no generation was selected')
    if candidates:
        return candidates.pop()
    raise GenerationUnavailable('Code-serving settings are not present in this codespace; keep its existing deployment settings')


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    path.relative_to(root)
    return path


def audit(code_root: Path, generation: Path, *, progress: bool = False) -> dict:
    """Check the selected generation against the actual profile binding, without writes."""
    code_root = code_root.resolve(strict=True)
    generation = generation.resolve(strict=True)
    rows: list[dict[str, str]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        rows.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    pipeline = json.loads((code_root / "00_SYSTEM/PIPELINE.json").read_text("utf-8"))
    base = next(n["parameters"]["term_agent"] for n in pipeline["profiles"]["legal-rag"]["nodes"]
                if "term_agent" in n.get("parameters", {}))
    implementation = os.environ.get("GENOS_RAG_IMPLEMENTATION", "").strip() or base.get("implementation", "")
    profile_id = PROFILE_FOR_IMPLEMENTATION.get(implementation, "legal-rag")
    config = next(n["parameters"]["term_agent"] for n in pipeline["profiles"][profile_id]["nodes"]
                  if "term_agent" in n.get("parameters", {}))
    manifest_path = generation / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    record("generation", manifest.get("schema_version") in {"term-source-generation-v1","term-source-generation-v2"},
           f"path={generation} id={manifest.get('generation_id')} profile={profile_id}")
    nav_binding = manifest.get("navigation")
    if not isinstance(nav_binding, dict):
        record("navigation binding", False, "generation manifest has no navigation binding")
        return {"status": "FAIL", "generation_id": manifest.get("generation_id"), "checks": rows}
    nav_path = _inside(generation, nav_binding["path"])
    nav_manifest_path = nav_path / "manifest.json"
    nav_file = nav_path / "navigation.sqlite"
    nav_manifest = json.loads(nav_manifest_path.read_text("utf-8"))
    nav_sha = nav_manifest.get("index_sha256")
    record("navigation manifest", sha256(nav_manifest_path) == nav_binding.get("manifest_sha256"),
           f"selected_index_sha256={nav_sha}")
    record("navigation SQLite", nav_file.is_file(), f"exists={nav_file.is_file()}")
    record("navigation source", nav_manifest.get("source_store_sha256") == manifest.get("store_sha256"),
           "navigation source store matches selected generation")
    record("navigation source manifest",
           nav_manifest.get("source_manifest_sha256") == source_manifest_digest(manifest),
           "navigation source manifest matches selected generation")

    generation_binding = manifest.get("fulltext")
    binding = generation_binding if generation_binding is not None else config.get("fulltext")
    if not isinstance(binding, dict):
        record("fulltext binding", False, "selected profile has no fulltext binding")
        return {"status": "FAIL", "generation_id": manifest.get("generation_id"), "checks": rows}
    record("fulltext binding source", True,
           "generation manifest" if generation_binding is not None else "legacy code profile; generation has no fulltext binding")
    record("fulltext navigation pin", binding.get("navigation_index_sha256") == nav_sha,
           f"configured={binding.get('navigation_index_sha256')} selected={nav_sha}")
    fulltext = _inside(generation, binding["path"])
    ft_manifest_path = fulltext / "manifest.json"
    ft = json.loads(ft_manifest_path.read_text("utf-8")) if ft_manifest_path.is_file() else {}
    schema = ft.get('schema_version')
    unit_index = schema == 'semantic-unit-fulltext-v1'
    record('fulltext schema', schema in (None, 'semantic-fulltext-v2', 'semantic-unit-fulltext-v1'),
           f'schema={schema}')
    ft_file = fulltext / ('units.sqlite' if unit_index else 'fulltext.sqlite')
    ft_table = 'unit_fts' if unit_index else 'source_fts'
    if not ft_manifest_path.is_file() or not ft_file.is_file():
        record("fulltext files", False,
               f"manifest_exists={ft_manifest_path.is_file()} sqlite_exists={ft_file.is_file()}")
    else:
        if unit_index:
            record('fulltext generation', ft.get('generation_id') == manifest.get('generation_id'),
                   'unit index belongs to selected generation')
        record("fulltext manifest", sha256(ft_manifest_path) == binding.get("manifest_sha256"),
               f"configured={binding.get('manifest_sha256')} actual={sha256(ft_manifest_path)}")
        record("fulltext index binding", ft.get("navigation_index_sha256") == nav_sha
               and ft.get("source_store_sha256") == nav_manifest.get("source_store_sha256"),
               "fulltext navigation/source hashes match")
        record("fulltext SQLite hash", sha256(ft_file, progress=progress) == ft.get("index_sha256" if unit_index else "fulltext_sha256"),
               "fulltext SQLite matches its manifest")
        try:
            installed = importlib.metadata.version("pecab")
        except importlib.metadata.PackageNotFoundError:
            installed = None
        tokenizer = ft.get("tokenizer") or {}
        record("fulltext tokenizer", tokenizer.get("name") == "pecab"
               and installed == tokenizer.get("version"),
               f"installed pecab={installed} indexed={tokenizer.get('name')}@{tokenizer.get('version')}")
        try:
            with sqlite3.connect(ft_file.as_uri() + "?mode=ro", uri=True) as db:
                db.execute("PRAGMA query_only=ON")
                opened = db.execute("SELECT 1 FROM " + ft_table + " LIMIT 1").fetchone() is not None
            record("fulltext SQLite open", opened, "read-only " + ft_table + " query")
        except sqlite3.Error as exc:
            record("fulltext SQLite open", False, type(exc).__name__)

    # Hash large SQLite files only after the inexpensive binding/file checks.
    # A missing fulltext fails immediately on NFS instead of first reading a
    # multi-gigabyte navigation index that cannot affect the outcome.
    if nav_file.is_file() and ft_file.is_file() and ft_manifest_path.is_file():
        record("navigation SQLite hash", sha256(nav_file, progress=progress) == nav_sha,
               "navigation SQLite matches its manifest")

    receipt_path = generation.parent / "share-receipt.json"
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text("utf-8"))
        files = receipt.get("files") or {}
        record("shared receipt", receipt.get("manifest_sha256") == sha256(manifest_path),
               f"path={receipt_path} manifest_match={receipt.get('manifest_sha256') == sha256(manifest_path)}")
        for relative in (str(nav_manifest_path.relative_to(generation)), str(nav_file.relative_to(generation)),
                         str(ft_manifest_path.relative_to(generation)), str(ft_file.relative_to(generation))):
            path = generation / relative
            record("shared inventory " + relative,
                   path.is_file() and files.get(relative) == sha256(path, progress=progress),
                   "artifact listed with matching hash in immutable shared receipt")
    return {"status": "FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS",
            "generation_id": manifest.get("generation_id"), "checks": rows}


def run_status(release: Path | None, run_log: Path | None, generation: Path) -> tuple[list[str], bool]:
    lines = []
    release_ok = True
    if release is not None:
        path = release / "release.json" if release.is_dir() else release
        if path.is_file():
            data = json.loads(path.read_text("utf-8"))
            release_ok = data.get("completed") is True and data.get("manifest_sha256") == sha256(generation / "manifest.json")
            lines.append(("PASS" if release_ok else "FAIL") + " release: " + json.dumps({k: data.get(k) for k in
                ("schema_version", "completed", "stage", "stage_completed", "review_status", "manifest_sha256")},
                ensure_ascii=False))
        else:
            release_ok = False
            lines.append(f"FAIL release: missing {path}")
    if run_log is not None:
        if not run_log.is_file():
            lines.append(f"run_log: missing {run_log}")
        else:
            pattern = re.compile(r"(FAILED at|LOCAL_E2E|ModuleNotFoundError|health failed|publish-shared|INDEX:|GENERATION publish-generation)")
            selected = [(number, text.strip()) for number, text in
                        enumerate(run_log.open("r", encoding="utf-8", errors="replace"), 1)
                        if pattern.search(text)]
            lines.extend(f"run_log:{number}: {text[:300]}" for number, text in selected[-20:])
    return lines, release_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--generation", type=Path)
    parser.add_argument("--code-root", type=Path, default=Path.cwd())
    parser.add_argument('--auto', action='store_true', help='reuse existing local settings, CURRENT or verified binding')
    parser.add_argument('--resolve-only', action='store_true', help='print selected path without loading a model or index')
    parser.add_argument("--release", type=Path, help="optional document release directory or release.json")
    parser.add_argument("--run-log", type=Path, help="optional nightly run.log")
    args = parser.parse_args(argv)
    try:
        generation = operator_generation(args.code_root) if args.auto and args.generation is None else selected_generation(args.generation)
        if args.resolve_only:
            print(generation)
            return 0
        print(f"SELECTED_GENERATION={generation}", flush=True)
        result = audit(args.code_root, generation, progress=True)
    except GenerationUnavailable as exc:
        print('DATA_CHECK_PENDING:', str(exc), file=sys.stderr)
        return 3
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print("FAIL generation E2E:", type(exc).__name__, str(exc))
        return 1
    for row in result["checks"]:
        print(f"{row['status']} {row['check']}: {row['detail']}")
    status_lines, release_ok = run_status(args.release, args.run_log, generation)
    for line in status_lines:
        print(line)
    passed = result["status"] == "PASS" and release_ok
    print("GENERATION_E2E", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
