#!/usr/bin/env python3
"""Validate the real v2 packages against the promoted ontology runtime.

The check is deterministic and offline.  It reconstructs the release semantic
tree only from the verified ontology DatasetPackage, then compares the promoted
boundary outcomes with the current compatibility roots byte-for-byte.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from lawrag.core.rag.index import Index
from lawrag.datasets.catalog import load_package
from lawrag.platform import active_runtime_paths
from lawrag.runtime.components import ontology_rag_v1


CASES = (
    {
        "case_id": "unique-definition",
        "question": "적격기관투자자대상증권이 무엇인가?",
        "status": "used",
        "reason": "VERIFIED_DEFINITION_MATCH",
        "projection_id": "definition:ebb347364ffdab186682de27:v1",
        "coordinates": [["bda6629c14183265", 4]],
    },
    {
        "case_id": "ambiguous-definition",
        "question": "가명정보란?",
        "status": "fallback",
        "reason": "AMBIGUOUS_SURFACE",
        "projection_id": None,
        "coordinates": [],
    },
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _protected_hashes(root: Path) -> dict[str, str]:
    paths = (
        "00_SYSTEM/WORKSPACE.json",
        "01_DATA/legal_graph/CURRENT.json",
        "01_DATA/PROJECTIONS/DEFINITIONS/CURRENT.json",
        "90_RUNTIME/OUT/structure/main/pipeline.json",
        "90_RUNTIME/OUT/structure/main/promotion_receipts.jsonl",
    )
    return {path: _sha(root / path) for path in paths}


def _ontology_manifest(root: Path, receipt: dict[str, Any]) -> Path:
    matches = []
    for stored in receipt.get("packages", []):
        path = root / str(stored)
        package = load_package(path, verify_files=True)
        if package.dataset_id == "ontology-operational":
            matches.append(path)
    if len(matches) != 1:
        raise RuntimeError("publication must contain exactly one ontology package")
    return matches[0]


def _materialize_semantics(manifest: Path, target: Path) -> tuple[int, str]:
    package = load_package(manifest, verify_files=True)
    rows = [
        artifact
        for artifact in package.artifacts
        if artifact.path.startswith("ARTIFACTS/SEMANTICS/")
    ]
    if not rows:
        raise RuntimeError("ontology package has no release semantic artifacts")
    inventory = []
    for artifact in rows:
        source = artifact.resolved_path()
        if source is None:
            raise RuntimeError(f"unresolved package artifact: {artifact.logical_id}")
        relative = Path(artifact.path).relative_to("ARTIFACTS/SEMANTICS")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination, follow_symlinks=False)
        actual = _sha(destination)
        if actual != artifact.sha256:
            raise RuntimeError(f"semantic copy hash mismatch: {artifact.logical_id}")
        inventory.append({"path": relative.as_posix(), "sha256": actual})
    return len(rows), _canonical_sha(sorted(inventory, key=lambda row: row["path"]))


def _run_cases(index: Index, definitions: Path, graph: Path) -> list[dict[str, Any]]:
    ontology_rag_v1._clear_knowledge_cache()
    output = []
    for case in CASES:
        started = time.perf_counter()
        sections, meta = ontology_rag_v1.retrieve(
            index,
            case["question"],
            definition_root=definitions,
            legal_graph_root=graph,
            baseline_result=(
                [],
                {
                    "selected": [],
                    "runtime": {"effective_profile": "legalclosure-v2"},
                    "strategy": "legalclosure",
                },
            ),
        )
        trace = meta["ontology_rag"]
        output.append(
            {
                "case_id": case["case_id"],
                "status": trace.get("status"),
                "reason": trace.get("reason"),
                "projection_id": trace.get("projection_id"),
                "coordinates": [[row.doc_id, row.node] for row in sections],
                "added_count": trace.get("added_count"),
                "baseline_floor_preserved": trace.get("baseline_floor_preserved"),
                "knowledge_cache": trace.get("knowledge_cache"),
                "definition_generation": trace.get("definition_generation"),
                "graph_generation": trace.get("graph_generation"),
                "elapsed_seconds": round(time.perf_counter() - started, 6),
            }
        )
    return output


def _comparable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ignored = {"elapsed_seconds", "knowledge_cache"}
    return [{key: value for key, value in row.items() if key not in ignored} for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    root = args.root.resolve()
    receipt = json.loads(args.receipt.read_text("utf-8"))
    manifest = _ontology_manifest(root, receipt)
    protected_before = _protected_hashes(root)
    runtime_paths = active_runtime_paths(root, target="local")
    index = Index.load(
        runtime_paths["STRUCTURE_STORE"],
        runtime_paths["GLOSSARY_STORE"],
        runtime_paths["RAG_LINKS_STORE"],
    )
    baseline = _run_cases(
        index,
        root / "01_DATA/PROJECTIONS/DEFINITIONS",
        root / "01_DATA/legal_graph",
    )
    with tempfile.TemporaryDirectory(prefix="adr0177-semantic-") as temporary:
        semantic_root = Path(temporary) / "semantics"
        artifact_count, semantic_inventory_sha256 = _materialize_semantics(
            manifest, semantic_root
        )
        candidate = _run_cases(
            index,
            semantic_root / "PROJECTIONS/DEFINITIONS",
            semantic_root / "legal_graph",
        )
    expected = [
        {
            "case_id": row["case_id"],
            "status": row["status"],
            "reason": row["reason"],
            "projection_id": row["projection_id"],
            "coordinates": row["coordinates"],
        }
        for row in CASES
    ]
    observed = [
        {key: row[key] for key in expected[position]}
        for position, row in enumerate(candidate)
    ]
    exact_equivalence = _comparable(baseline) == _comparable(candidate)
    expected_outcomes = observed == expected
    pointer_unchanged = protected_before == _protected_hashes(root)
    cache_contract = [row["knowledge_cache"] for row in candidate] == ["miss", "hit"]
    passed = exact_equivalence and expected_outcomes and pointer_unchanged and cache_contract
    result = {
        "schema_version": "v2-dataset-sourceset-cutover-validation-v1",
        "result": "pass" if passed else "fail",
        "ontology_package_manifest": manifest.relative_to(root).as_posix(),
        "ontology_package_manifest_sha256": _sha(manifest),
        "semantic_artifact_count": artifact_count,
        "semantic_inventory_sha256": semantic_inventory_sha256,
        "index_documents": len(index.docs),
        "baseline": baseline,
        "candidate": candidate,
        "gates": {
            "exact_outcome_and_coordinate_equivalence": exact_equivalence,
            "inherited_adr0176_expected_outcomes": expected_outcomes,
            "knowledge_cache_miss_hit": cache_contract,
            "main_and_current_unchanged": pointer_unchanged,
        },
        "usage": {"llm_calls": 0, "embedding_calls": 0, "network_calls": 0},
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
