#!/usr/bin/env python3
"""Build and audit ADR-0154's research-only minimum-unit proviso graph."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = (
    ROOT / "lawrag/research/candidates/adr_0154/minimum-unit-proviso-graph/revisions/rev-002/snapshot"
    "/lawrag/research/candidates/adr_0150/proviso-schema-slot-gate/revisions/rev-002"
    "/snapshot/lawrag/core/domain_graph/requirements.py"
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_candidate():
    spec = importlib.util.spec_from_file_location("adr0154_candidate", CANDIDATE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load candidate: {CANDIDATE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_documents(structure: Path) -> dict[str, dict[str, Any]]:
    documents = {}
    for path in sorted(structure.glob("*/result.json")):
        value = json.loads(path.read_text("utf-8"))
        documents[path.parent.name] = value
    return documents


def audit(graph: dict[str, Any], documents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    units = graph["units"]
    provisos = graph["provisos"]
    components = graph["components"]
    edges = graph["edges"]
    routes = graph["routes"]
    unit_ids = {row["unit_id"] for row in units}
    component_ids = {row["component_id"] for row in components}
    edge_tuples = {(row["kind"], row["src"], row["dst"]) for row in edges}
    source_node_count = sum(len(value.get("nodes", ())) for value in documents.values())
    dangling_parents = sum(
        1 for row in units
        if row["parent_unit_id"] is not None and row["parent_unit_id"] not in unit_ids
    )
    missing_required = []
    offset_errors = []
    block_by_key = {
        (doc_id, int(block.get("idx", -1))): str(block.get("text") or "")
        for doc_id, document in documents.items()
        for block in document.get("blocks", ())
        if block.get("idx") is not None
    }
    for row in provisos:
        required = (
            ("ATTACHED_TO", row["proviso_id"], row["source_unit_id"]),
            ("HAS_CONDITION", row["proviso_id"], row["condition_id"]),
            ("HAS_OUTCOME", row["proviso_id"], row["outcome_id"]),
            (row["legal_effect_family"], row["outcome_id"], row["source_unit_id"]),
        )
        if any(item not in edge_tuples for item in required):
            missing_required.append(row["proviso_id"])
        text = block_by_key.get((row["doc_id"], int(row["block"])), "")
        if (text[row["cue_start"]:row["cue_end"]] != row["cue"] or
                text[row["body_start"]:row["body_end"]] != row["body"] or
                hashlib.sha256(text.encode("utf-8")).hexdigest() != row["source_sha256"]):
            offset_errors.append(row["proviso_id"])
    route_errors = [
        row["proviso_id"] for row in routes
        if row["status"] == "RESOLVED" and (
            row["target_unit_id"] not in unit_ids or row["candidate_count"] != 1)
    ]
    cm = [
        row for row in routes
        if row["source_locator"].replace(" ", "") == "제26조제1항제3호단서"
        and row["source_unit_id"].startswith("unit:")
    ]
    cm_exact = any(
        row["status"] == "RESOLVED"
        and row["target_doc_id"] == "eae25aa6e8a83c58"
        and row["target_node"] == 218
        for row in cm
    )
    return {
        "source_node_count": source_node_count,
        "unit_count": len(units),
        "unit_coverage": len(units) / source_node_count if source_node_count else 0,
        "dangling_parent_count": dangling_parents,
        "proviso_count": len(provisos),
        "component_count": len(components),
        "condition_count": sum(row["kind"] == "CONDITION" for row in components),
        "outcome_count": sum(row["kind"] == "OUTCOME" for row in components),
        "edge_count": len(edges),
        "route_count": len(routes),
        "route_status": {
            key: sum(row["status"] == key for row in routes)
            for key in ("RESOLVED", "AMBIGUOUS", "UNRESOLVED")
        },
        "missing_required_edge_count": len(missing_required),
        "offset_or_hash_error_count": len(offset_errors),
        "resolved_route_error_count": len(route_errors),
        "component_reference_error_count": sum(
            row["condition_id"] not in component_ids or row["outcome_id"] not in component_ids
            for row in provisos
        ),
        "cm_003_exact_route": cm_exact,
        "cm_003_routes": cm,
    }


def taxonomy_examples(graph: dict[str, Any], limit: int = 3) -> dict[str, list[dict[str, Any]]]:
    examples: dict[str, list[dict[str, Any]]] = {}
    for row in graph["provisos"]:
        bucket = examples.setdefault(row["outcome_kind"], [])
        if len(bucket) < limit:
            bucket.append({
                "doc_id": row["doc_id"], "source_locator": row["source_locator"],
                "cue": row["cue"], "body": row["body"],
            })
    return dict(sorted(examples.items()))


def write_gzip(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            stream.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--structure", type=Path, default=ROOT / "data/structure")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    started = time.perf_counter()
    candidate = load_candidate()
    documents = load_documents(args.structure)
    graph = candidate.build_minimum_unit_proviso_graph(documents)
    payload = canonical_bytes(graph)
    graph_hash = sha256_bytes(payload)
    validation = audit(graph, documents)
    summary = {
        "schema_version": "minimum-unit-proviso-run-v1",
        "candidate_path": CANDIDATE.relative_to(ROOT).as_posix(),
        "document_count": len(documents),
        "graph_sha256": graph_hash,
        "graph_uncompressed_bytes": len(payload),
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "taxonomy": graph["taxonomy"],
        "taxonomy_examples": taxonomy_examples(graph),
        "validation": validation,
        "llm_calls": 0,
        "production_paths_modified": False,
    }
    write_gzip(args.output, payload)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    failures = (
        validation["unit_coverage"] != 1
        or validation["dangling_parent_count"] != 0
        or validation["missing_required_edge_count"] != 0
        or validation["offset_or_hash_error_count"] != 0
        or validation["resolved_route_error_count"] != 0
        or validation["component_reference_error_count"] != 0
        or not validation["cm_003_exact_route"]
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
