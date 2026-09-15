#!/usr/bin/env python3
"""Run frozen ADR-0149 proviso-span relationship/data evaluation."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
for key, value in (
    ("STRUCTURE_STORE", "01_DATA/structure"),
    ("STRUCTURE_CUSTOM_DIR", "01_DATA/custom"),
    ("GLOSSARY_STORE", "01_DATA/glossary.json"),
    ("RAG_LINKS_STORE", "01_DATA/links.json"),
    ("RAG_DELEGATION_STORE", "01_DATA/delegation.json"),
):
    os.environ.setdefault(key, str(ROOT / value))

from lawrag.core.rag.index import Index  # noqa: E402
from lawrag.core.rag import relations as baseline_relations  # noqa: E402
lexical_search = importlib.import_module("lawrag.core.rag.search")  # noqa: E402
import lawrag.core.domain_graph as domain_graph_package  # noqa: E402
import lawrag.core.rag as rag_package  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen candidate: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def install_frozen(revision_dir: Path):
    snapshot = revision_dir / "snapshot"
    req = load_module(
        snapshot / "lawrag/core/domain_graph/requirements.py",
        "lawrag.core.domain_graph.requirements")
    domain_graph_package.requirements = req
    rel = load_module(
        snapshot / "lawrag/core/rag/relations.py",
        "lawrag.core.rag.relations")
    rag_package.relations = rel
    nav = load_module(
        snapshot / "lawrag/core/rag/relation_navigation.py",
        "lawrag.core.rag.relation_navigation")
    rag_package.relation_navigation = nav
    return req, rel, nav


def section_keys(bundle) -> list[list[object]]:
    return [list(row.key) for row in bundle.sections]


def export_payload(index: Index, bundle) -> dict:
    documents = {
        doc_id: {"name": view.name, "kind": view.kind, "version": view.version}
        for doc_id, view in sorted(index.docs.items())
    }
    spans = [row.as_dict() for row in bundle.provisos]
    edges = [{
        "plane": row.plane, "kind": row.kind,
        "proviso_id": row.proviso_id,
        "src_doc": row.src_doc, "src_node": row.src_node,
        "src_block": row.src_block, "dst_kind": row.dst_kind,
        "dst_doc": row.dst_doc, "dst_node": row.dst_node,
        "props": row.props,
    } for row in bundle.proviso_relations]
    return {
        "schema_version": "proviso-relations-v1",
        "authority_generation": index.authority_generation,
        "authority_as_of": index.authority_as_of,
        "documents": documents, "provisos": spans, "relations": edges,
    }


def validate_payload(index: Index, bundle) -> dict:
    edge_by_id = {}
    for edge in bundle.proviso_relations:
        edge_by_id.setdefault(edge.proviso_id, []).append(edge)
    missing_physical, missing_effect, invalid_spans, dangling = [], [], [], []
    scope_status = Counter()
    effects, planes, routes = Counter(), Counter(), Counter()
    for span in bundle.provisos:
        scope_status[span.scope_status] += 1
        view = index.docs.get(span.doc_id)
        block = view.block_by_idx.get(span.block) if view else None
        text = str((block or {}).get("text") or "")
        valid = (
            0 <= span.cue_start < span.cue_end <= len(text)
            and 0 <= span.body_start <= span.body_end <= len(text)
            and 0 <= span.parent_start <= span.parent_end <= len(text)
            and text[span.cue_start:span.cue_end] == span.cue
            and text[span.body_start:span.body_end] == span.body
            and text[span.parent_start:span.parent_end] == span.parent_text
            and hashlib.sha256(text.encode("utf-8")).hexdigest() == span.source_sha256
        )
        if not valid:
            invalid_spans.append(span.proviso_id)
        edges = edge_by_id.get(span.proviso_id, ())
        if not any(row.plane == "PHYSICAL_LINK" and row.kind == "ATTACHED_TO"
                   for row in edges):
            missing_physical.append(span.proviso_id)
        if not any(row.plane == "LEGAL_EFFECT" and row.kind == span.effect_kind
                   for row in edges):
            missing_effect.append(span.proviso_id)
    for edge in bundle.proviso_relations:
        planes[edge.plane] += 1
        if edge.plane == "LEGAL_EFFECT":
            effects[edge.kind] += 1
        if edge.plane == "SEARCH_ROUTING":
            routes[edge.kind] += 1
        view = index.docs.get(edge.dst_doc)
        if view is None or (edge.dst_kind == "section" and edge.dst_node not in view.by_id):
            dangling.append(list(edge.key))
    return {
        "proviso_count": len(bundle.provisos),
        "proviso_relation_count": len(bundle.proviso_relations),
        "planes": dict(sorted(planes.items())),
        "legal_effects": dict(sorted(effects.items())),
        "search_routes": dict(sorted(routes.items())),
        "scope_status": dict(sorted(scope_status.items())),
        "invalid_span_count": len(invalid_spans),
        "missing_physical_count": len(missing_physical),
        "missing_legal_effect_count": len(missing_effect),
        "dangling_target_count": len(dangling),
        "samples": {
            "invalid_spans": invalid_spans[:20],
            "missing_physical": missing_physical[:20],
            "missing_legal_effect": missing_effect[:20],
            "dangling_targets": dangling[:20],
        },
    }


def cm_probe(index: Index, req, nav, known_case: dict) -> dict:
    source = tuple(known_case["source_article"])
    packages, meta = nav.proviso_packages(index, [source], cap=128)
    detail = tuple(known_case["direct_detail_article"])
    routed = {
        (target.get("doc_id"), target.get("node"))
        for package in packages for target in package.route_targets
        if target.get("node") is not None
    }
    evidence = [req.SlotEvidence(
        "E-third-party", "재무적투자자가 제3자배정으로 취득",
        predicates=("third_party_allotment",))]
    slots = [
        req.ConditionSlot("actor", "financial_investor", evidence_ids=("E-third-party",)),
        req.ConditionSlot("method", "non_offering_or_sale_method",
                          evidence_ids=("E-third-party",)),
    ]
    judgements = [row.__dict__ for row in req.validate_condition_slots(slots, evidence)]
    return {
        "source": list(source), "direct_detail": list(detail),
        "package_count": len(packages), "routing_meta": meta,
        "direct_detail_routed": detail in routed,
        "route_coordinates": [list(value) for value in sorted(routed)],
        "packages": [row.as_dict() for row in packages],
        "slot_judgements": judgements,
        "unsupported_method_equivalence_blocked": next(
            row["value"] == "unknown" for row in judgements if row["slot_id"] == "method"),
    }


def holdout_probe(index: Index, nav, lock: dict) -> list[dict]:
    gold = json.loads((ROOT / lock["structural_holdout"]["source"]).read_text("utf-8"))
    out = []
    for case_id in lock["structural_holdout"]["selected_case_ids"]:
        questions = [part["question"] for part in gold[case_id].get("parts", ())]
        seeds = []
        for question in questions:
            result = lexical_search.search(index, question)
            for hit in result.hits[:12]:
                coordinate = (hit.doc_id, hit.node)
                if coordinate not in seeds:
                    seeds.append(coordinate)
        packages, meta = nav.proviso_packages(index, seeds, cap=128)
        out.append({
            "case_id": case_id, "question_count": len(questions),
            "seed_count": len(seeds), "package_count": len(packages),
            "has_proviso_package": bool(packages), "meta": meta,
            "source_coordinates": [[p.source_doc_id, p.source_article] for p in packages],
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision-dir", type=Path, required=True)
    parser.add_argument("--input-lock", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--data-out", type=Path, required=True)
    parser.add_argument("--run-id", default="run-001")
    args = parser.parse_args()
    started = time.perf_counter()
    lock = json.loads(args.input_lock.read_text("utf-8"))
    index = Index.load(ROOT / "01_DATA/structure", ROOT / "01_DATA/glossary.json",
                       ROOT / "01_DATA/links.json")
    baseline = baseline_relations.build(
        index, delegation_file=ROOT / "01_DATA/delegation.json",
        law_index_file=ROOT / "01_DATA/law_index.json",
        include_requirements=True, use_cache=False)
    req, candidate_relations, nav = install_frozen(args.revision_dir.resolve())
    candidate = candidate_relations.build(
        index, delegation_file=ROOT / "01_DATA/delegation.json",
        law_index_file=ROOT / "01_DATA/law_index.json",
        include_requirements=True, use_cache=False)
    baseline_keys = section_keys(baseline)
    candidate_keys = section_keys(candidate)
    payload = export_payload(index, candidate)
    first = canonical_bytes(payload)
    second = canonical_bytes(export_payload(index, candidate))
    if first != second:
        raise RuntimeError("proviso derived data is not deterministic")
    args.data_out.parent.mkdir(parents=True, exist_ok=True)
    args.data_out.write_bytes(first)
    validation = validate_payload(index, candidate)
    holdout = holdout_probe(index, nav, lock)
    cm = cm_probe(index, req, nav, lock["known_case"])
    result = {
        "schema_version": "proviso-runtime-data-run-v1",
        "adr_id": "ADR-0149", "experiment_id": "ADR-0149-experiment-v1",
        "run_id": args.run_id,
        "input_lock": str(args.input_lock),
        "input_lock_sha256": sha256(args.input_lock),
        "candidate_revision_dir": str(args.revision_dir),
        "candidate_manifest_sha256": sha256(args.revision_dir.parent.parent / "candidate.json"),
        "baseline": {"section_relation_count": len(baseline_keys)},
        "candidate": {
            "section_relation_count": len(candidate_keys),
            "section_relation_key_loss": len(set(map(tuple, baseline_keys)) - set(map(tuple, candidate_keys))),
            "section_relation_key_gain": len(set(map(tuple, candidate_keys)) - set(map(tuple, baseline_keys))),
            "validation": validation,
            "derived_data_path": str(args.data_out),
            "derived_data_sha256": hashlib.sha256(first).hexdigest(),
            "repeat_sha256": hashlib.sha256(second).hexdigest(),
        },
        "cm003": cm,
        "structural_holdout": holdout,
        "criteria": {
            "no_section_relation_loss": set(map(tuple, baseline_keys)).issubset(set(map(tuple, candidate_keys))),
            "exact_spans": validation["invalid_span_count"] == 0,
            "physical_and_legal_complete": (
                validation["missing_physical_count"] == 0
                and validation["missing_legal_effect_count"] == 0),
            "no_dangling_targets": validation["dangling_target_count"] == 0,
            "deterministic": first == second,
            "cm_package_and_slot_guard": (
                bool(cm["package_count"])
                and cm["direct_detail_routed"]
                and cm["unsupported_method_equivalence_blocked"]),
            "holdout_packages": sum(row["has_proviso_package"] for row in holdout),
        },
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(canonical_bytes(result))
    print(json.dumps(result["criteria"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
