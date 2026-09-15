#!/usr/bin/env python3
"""Run ADR-0155 terminal-effect orientation invariants."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
BASE_RUNNER = ROOT / "06_TOOLS/EXPERIMENTS/RAG/PROVISO/rag_minimum_unit_proviso_graph.py"
CANDIDATE = (
    Path(__import__("lawrag").__file__).resolve().parent / "research/candidates/adr_0155/terminal-aware-proviso-graph"
    "/revisions/rev-001/snapshot/lawrag/research/candidates/adr_0154"
    "/minimum-unit-proviso-graph/revisions/rev-002/snapshot/lawrag/research"
    "/candidates/adr_0150/proviso-schema-slot-gate/revisions/rev-002/snapshot"
    "/lawrag/core/domain_graph/requirements.py"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def terminal_audit(graph):
    components = {row["component_id"]: row for row in graph["components"]}
    terminal_count = 0
    errors = []
    for row in graph["provisos"]:
        cue = row["cue"].replace(" ", "")
        if not ("제외한다" in cue or "예외로한다" in cue or "그러하지아니" in cue):
            continue
        terminal_count += 1
        condition = components[row["condition_id"]]
        outcome = components[row["outcome_id"]]
        checks = {
            "outcome_kind": row["outcome_kind"] == "EXCLUDES_APPLICATION",
            "outcome_is_cue": outcome["text"] == row["cue"],
            "outcome_offset": outcome["start"] == row["cue_start"] and outcome["end"] == row["cue_end"],
            "condition_before_cue": condition["end"] is None or condition["end"] <= row["cue_start"],
        }
        if not all(checks.values()):
            errors.append({"proviso_id": row["proviso_id"], "checks": checks})
    cm = next(row for row in graph["provisos"]
              if row["doc_id"] == "3521c3aaa5a735fd"
              and row["source_locator"] == "제26조제1항제3호"
              and row["cue"].startswith("다만"))
    cm_condition = components[cm["condition_id"]]
    cm_outcome = components[cm["outcome_id"]]
    cm_route = next(row for row in graph["routes"] if row["proviso_id"] == cm["proviso_id"])
    cm_ok = (
        cm_condition["text"] == "세칙으로 정하는 경우는"
        and cm_outcome["text"] == "제외한다."
        and cm_route["status"] == "RESOLVED"
        and cm_route["target_doc_id"] == "eae25aa6e8a83c58"
        and cm_route["target_node"] == 218
        and len(cm_route["member_unit_ids"]) == 8
    )
    return {
        "terminal_count": terminal_count,
        "terminal_invariant_error_count": len(errors),
        "terminal_invariant_error_examples": errors[:10],
        "cm_003_regression_ok": cm_ok,
        "cm_003": {"proviso": cm, "condition": cm_condition,
                   "outcome": cm_outcome, "route": cm_route},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--structure", type=Path, default=ROOT / "01_DATA/structure")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    base = load_module("adr0155_base_runner", BASE_RUNNER)
    candidate = load_module("adr0155_candidate", CANDIDATE)
    documents = base.load_documents(args.structure)
    graph = candidate.build_minimum_unit_proviso_graph(documents)
    payload = base.canonical_bytes(graph)
    structural = base.audit(graph, documents)
    semantic = terminal_audit(graph)
    summary = {
        "schema_version": "terminal-proviso-orientation-run-v1",
        "candidate_path": CANDIDATE.relative_to(ROOT).as_posix(),
        "document_count": len(documents),
        "graph_sha256": base.sha256_bytes(payload),
        "graph_uncompressed_bytes": len(payload),
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "taxonomy": graph["taxonomy"],
        "structural_validation": structural,
        "semantic_validation": semantic,
        "llm_calls": 0,
        "production_paths_modified": False,
    }
    base.write_gzip(args.output, payload)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    fail = (
        structural["unit_count"] != 170931
        or structural["proviso_count"] != 14203
        or structural["dangling_parent_count"] != 0
        or structural["missing_required_edge_count"] != 0
        or structural["offset_or_hash_error_count"] != 0
        or not structural["cm_003_exact_route"]
        or semantic["terminal_invariant_error_count"] != 0
        or not semantic["cm_003_regression_ok"]
    )
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
