#!/usr/bin/env python3
"""Build isolated domain/legal graph artifacts from frozen ADR-0149 code."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.rag.index import Index  # noqa: E402
import lawrag.core.domain_graph as domain_package  # noqa: E402
import lawrag.core.legal_graph as legal_package  # noqa: E402
import lawrag.core.rag as rag_package  # noqa: E402
from lawrag.core.domain_graph.canonical import CanonicalRegistry  # noqa: E402
from lawrag.core.domain_graph.store import GraphStore  # noqa: E402
from lawrag.core.legal_graph.validation import validate_generation  # noqa: E402


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(revision: Path):
    snap = revision / "snapshot/lawrag/core"
    req = load(snap / "domain_graph/requirements.py", "lawrag.core.domain_graph.requirements")
    domain_package.requirements = req
    rel = load(snap / "rag/relations.py", "lawrag.core.rag.relations")
    rag_package.relations = rel
    builder = load(snap / "domain_graph/builder.py", "lawrag.core.domain_graph.builder")
    domain_package.builder = builder
    compiler = load(snap / "legal_graph/compiler.py", "lawrag.core.legal_graph.compiler")
    legal_package.compiler = compiler
    return builder, compiler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision-dir", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    out_root = args.out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    builder_mod, compiler_mod = install(args.revision_dir.resolve())
    index = Index.load(ROOT / "data/structure", ROOT / "data/glossary.json",
                       ROOT / "data/links.json")
    registry = CanonicalRegistry.load(
        registry_path=ROOT / "data/domain_graph/canonical.json",
        glossary_path=ROOT / "data/glossary.json")
    domain_path = out_root / "domain-graph.sqlite"
    domain_result = builder_mod.GraphBuilder(
        index, data_dir=ROOT / "data", registry=registry,
        glossary_path=ROOT / "data/glossary.json").build(domain_path)
    with GraphStore(domain_path, readonly=True) as store:
        domain_counts = store.counts()
    legal_root = out_root / "legal-graph"
    legal_result = compiler_mod.build_generation(compiler_mod.BuildConfig(
        structure_store=ROOT / "data/structure",
        law_index_file=ROOT / "data/law_index.json",
        delegation_file=ROOT / "data/delegation.json",
        canonical_file=ROOT / "data/domain_graph/canonical.json",
        frames_store=ROOT / "data/frames",
        glossary_file=ROOT / "data/glossary.json",
        links_file=ROOT / "data/links.json",
        output_root=legal_root, publish_current=False))
    validation = validate_generation(
        legal_result.generation_path, structure_store=(ROOT / "data/structure"))
    validation = validation.to_dict() if hasattr(validation, "to_dict") else validation
    result = {
        "schema_version": "proviso-graph-validation-v1",
        "adr_id": "ADR-0149", "experiment_id": "ADR-0149-experiment-v1",
        "run_id": "run-004", "candidate_revision": "rev-002",
        "domain_graph": {
            "path": str(domain_path), "sha256": sha256(domain_path),
            "build": domain_result, "counts": domain_counts,
        },
        "legal_graph": {
            "generation_id": legal_result.generation_id,
            "generation_path": str(legal_result.generation_path),
            "manifest_path": str(legal_result.manifest_path),
            "content_sha256": legal_result.content_sha256,
            "validation": validation,
        },
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({
        "domain": domain_result.get("stats", domain_result),
        "legal_generation": legal_result.generation_id,
        "legal_valid": validation.get("valid", validation.get("ok")),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
