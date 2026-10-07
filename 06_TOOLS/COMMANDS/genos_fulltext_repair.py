#!/usr/bin/env python3
"""Build a fulltext-bound copy of one published GENOS generation.

The input generation and its share receipt are never modified. The output is a
new immutable package containing generation/ and share-receipt.json. Select the
printed generation path in a new code-serving revision only after the E2E gate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02_BACKEND"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-generation", type=Path,
                        help="published generation; defaults to GENOS_GENERATION")
    parser.add_argument("--output-root", type=Path,
                        help="existing NFS directory for a new package; defaults to the source term-releases directory")
    parser.add_argument("--package-name", help="new, unused package directory name")
    parser.add_argument("--workers", type=int, default=2, help="PeCab worker processes")
    parser.add_argument("--rebuild", action="store_true", help="replace only the new copy's fulltext using PeCab; preserve the source")
    parser.add_argument("--document-scope", type=Path, help="explicit JSON document IDs for a partial build; default is the complete corpus")
    parser.add_argument("--scratch-root", type=Path,
                        help="existing local disk directory for fulltext build before NFS copy")
    args = parser.parse_args(argv)
    from semantic_runtime.contracts import sha, write
    from semantic_runtime.fulltext import build
    from lawrag.pipeline.term_serving_bundle import verify_assets

    configured = args.source_generation or os.environ.get("GENOS_GENERATION")
    if not configured:
        parser.error("set GENOS_GENERATION or pass --source-generation")
    source_input = Path(configured)
    source = source_input.resolve(strict=True)
    if source.name != "generation" or source_input.is_symlink():
        parser.error("source must be a real generation directory")
    if args.workers < 1:
        parser.error("--workers must be positive")
    if args.output_root is None:
        if source.parent.name not in {"reviewed", "unreviewed"}:
            parser.error("pass --output-root for a nonstandard source layout")
        output_root = source.parents[2]
    else:
        output_root = args.output_root.resolve(strict=True)
    if not output_root.is_dir():
        parser.error("output root must be an existing directory")
    scratch_root = args.scratch_root.resolve(strict=True) if args.scratch_root else None
    if scratch_root is not None and not scratch_root.is_dir():
        parser.error("scratch root must be an existing directory")
    manifest_path = source / "manifest.json"
    source_manifest = json.loads(manifest_path.read_text("utf-8"))
    old_fulltext = source_manifest.get("fulltext") is not None or (source / "fulltext").exists()
    if old_fulltext and not args.rebuild:
        parser.error("source already has fulltext; preserve it and diagnose its binding")
    document_ids = None
    if args.document_scope is not None:
        scope = json.loads(args.document_scope.read_text("utf-8"))
        document_ids = scope if isinstance(scope, list) else scope.get("document_version_ids")
        if not isinstance(document_ids, list) or not all(isinstance(d, str) for d in document_ids):
            parser.error("document scope must contain an explicit document_version_ids list")
    original_hash = sha(manifest_path)
    name = args.package_name or ("fulltext-repair-" +
           datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + original_hash[:8])
    if name in {"", ".", ".."} or "/" in name or "\\" in name:
        parser.error("--package-name must be one directory name")
    target = output_root / name
    if target.exists():
        parser.error(f"output already exists: {target}")

    # Check the actual interpreter before copying a potentially large NFS generation.
    try:
        from semantic_runtime.term_morph import tokenize
        tokenize("용어 색인 확인")
    except Exception as exc:
        parser.error(
            f"{sys.executable} cannot initialize pecab ({type(exc).__name__}: {exc}); "
            "install the versions pinned in requirements.txt in this interpreter"
        )

    print("FULLTEXT REPAIR verify source", flush=True)
    verify_assets(source, verify_fulltext=not (old_fulltext and args.rebuild))
    if old_fulltext:
        previous_fulltext = json.loads((source / "fulltext/manifest.json").read_text())
        if previous_fulltext.get("fulltext_sha256") != sha(source / "fulltext/fulltext.sqlite"):
            raise ValueError("old fulltext hash mismatch; refusing rebuild from an unverified source")
        nav = json.loads((source / source_manifest['navigation']['path'] / 'manifest.json').read_text())
        if (previous_fulltext.get('source_store_sha256') != source_manifest['store_sha256'] or
                previous_fulltext.get('navigation_index_sha256') != nav['index_sha256']):
            raise ValueError('old fulltext source/navigation binding mismatch')
        binding = source_manifest.get('fulltext')
        if binding is not None and binding.get('manifest_sha256') != sha(source / 'fulltext/manifest.json'):
            raise ValueError('old generation fulltext manifest binding mismatch')
    if sha(manifest_path) != original_hash:
        raise ValueError("source generation manifest changed during verification")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"source generation contains a symlink: {path}")

    scratch = None
    if scratch_root is not None:
        scratch = Path(tempfile.mkdtemp(prefix="." + name + "-", dir=scratch_root))
    stage = None
    try:
        if scratch is not None:
            local_navigation = scratch / "navigation"
            local_navigation.mkdir()
            for filename in ("manifest.json", "navigation.sqlite"):
                shutil.copy2(source / "navigation" / filename, local_navigation / filename)
            print(f"FULLTEXT REPAIR building on local scratch: {scratch}", flush=True)
            ft = build(local_navigation, scratch / "fulltext", workers=args.workers, document_ids=document_ids)
        stage = Path(tempfile.mkdtemp(prefix="." + name + "-", dir=output_root))
        generation = stage / "generation"
        print(f"FULLTEXT REPAIR copying source to staging: {generation}", flush=True)
        shutil.copytree(source, generation, ignore=(lambda directory, names: {"fulltext"} if
                        args.rebuild and Path(directory) == source else set()))
        if sha(manifest_path) != original_hash:
            raise ValueError("source generation manifest changed during copy")
        if scratch is None:
            print("FULLTEXT REPAIR building fulltext on NFS", flush=True)
            ft = build(generation / "navigation", generation / "fulltext", workers=args.workers, document_ids=document_ids)
        else:
            shutil.copytree(scratch / "fulltext", generation / "fulltext")
        repaired = json.loads((generation / "manifest.json").read_text("utf-8"))
        repaired["fulltext"] = {
            "path": "fulltext",
            "manifest_sha256": sha(generation / "fulltext/manifest.json"),
            "navigation_index_sha256": ft["navigation_index_sha256"],
        }
        repaired["fulltext_derivation"] = {"source_manifest_sha256": original_hash,
            "operation": "PeCab rebuild" if args.rebuild else "PeCab missing-index build",
            "previous_fulltext_manifest_sha256": sha(source / "fulltext/manifest.json") if old_fulltext else None,
            "complete_navigation_corpus": document_ids is None}
        (generation / "manifest.json").write_text(
            json.dumps(repaired, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("FULLTEXT REPAIR verifying complete generation", flush=True)
        verify_assets(generation)
        files = {str(path.relative_to(generation)): sha(path)
                 for path in sorted(generation.rglob("*")) if path.is_file()}
        write(stage / "share-receipt.json", {
            "schema_version": "term-fulltext-repair-shared-generation-v1",
            "source_generation": str(source),
            "source_manifest_sha256": original_hash,
            "manifest_sha256": sha(generation / "manifest.json"),
            "files": files,
        })
        if target.exists():
            raise ValueError("output package appeared during repair")
        os.rename(stage, target)
    except BaseException:
        if stage is not None:
            shutil.rmtree(stage)
        raise
    finally:
        if scratch is not None:
            shutil.rmtree(scratch)
    print(f"GENOS_GENERATION={target / 'generation'}", flush=True)
    print(f"SHARE_RECEIPT={target / 'share-receipt.json'}", flush=True)
    print("NEXT: deploy the aligned code revision with the printed GENOS_GENERATION; run the generation E2E gate.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
