#!/usr/bin/env python3
"""Haiku IMPLEMENTS 후보를 기존 원문 ref edge(수임/근거/인용)와 대조한다."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _key, _value in (("STRUCTURE_STORE", "data/structure"),
                     ("STRUCTURE_CUSTOM_DIR", "data/custom"),
                     ("GLOSSARY_STORE", "data/glossary.json"),
                     ("RAG_LINKS_STORE", "data/links.json")):
    os.environ.setdefault(_key, str(ROOT / _value))

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag import legal_coordinates as coordinates  # noqa: E402
from lawrag.core.rag.experiments.haiku_legal_methods import provenance_path  # noqa: E402


def _coordinate_map(index):
    out: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for doc_id, view in index.docs.items():
        for node in view.by_id:
            path = provenance_path(view.path(node))[0]
            out.setdefault((view.name, path), []).append((doc_id, node))
    return out


def _edge_relations(index, sources, targets):
    target_set = set(targets)
    found = []
    for source_doc, source_node in sources:
        source_view = index.docs[source_doc]
        source_root = coordinates.article_root(source_view, source_node)
        for edge in index.ref_edges().get(source_doc, ()):
            if edge.get("src") != source_root:
                continue
            target_root = coordinates.article_root(source_view, edge.get("dst"))
            if (source_doc, target_root) in target_set:
                found.append({"rel": edge.get("rel"), "surface": edge.get("surface"),
                              "kind": "intra"})
        for edge in index.cross_from(source_doc):
            if edge.get("src") != source_root:
                continue
            target_doc = edge.get("dst_doc")
            target_view = index.docs.get(target_doc)
            if target_view is None:
                continue
            target_root = coordinates.article_root(target_view, edge.get("dst"))
            if (target_doc, target_root) in target_set:
                found.append({"rel": edge.get("rel"), "surface": edge.get("surface"),
                              "kind": "cross"})
    return found


def classify_reference_support(edges):
    relations = {str(edge.get("rel") or "") for edge in edges}
    if "수임" in relations:
        return "formal_reception_proven"
    if relations & {"근거", "인용", "준용", "배제", "의제"}:
        return "reference_but_not_implementation"
    return "no_matching_reference_edge"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--relations", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    artifact = json.loads(args.relations.read_text("utf-8"))
    index = index_mod.current()
    coord_map = _coordinate_map(index)
    retrieval_path = args.retrieval_ablation or Path(str(artifact.get("source_retrieval") or ""))
    selected_by_case = {}
    if retrieval_path.is_file():
        retrieval = json.loads(retrieval_path.read_text("utf-8"))
        for case in retrieval.get("rows") or []:
            selected = (((case.get("variants") or {}).get("control_d_then_verifier")
                         or {}).get("selected") or [])
            selected_by_case[str(case.get("case_no") or "")] = selected
    rows = []
    for case in artifact.get("rows") or []:
        case_coordinates = {}
        for selected in selected_by_case.get(str(case.get("case_no") or ""), []):
            key = (str(selected.get("doc") or ""),
                   provenance_path(str(selected.get("path") or ""))[0])
            case_coordinates.setdefault(key, []).append(
                (str(selected.get("doc_id") or ""), int(selected.get("node") or 0)))
        inventory = {row["evidence_id"]: row for row in case.get("inventory") or []}
        candidates = [
            ("published", relation) for relation in case.get("published") or []
            if relation.get("relation_type") == "IMPLEMENTS"
        ] + [
            ("rejected", relation) for relation in case.get("rejected") or []
            if relation.get("relation_type") == "IMPLEMENTS"
        ]
        for current_status, relation in candidates:
            source = inventory.get(relation.get("source_id")) or {}
            target = inventory.get(relation.get("target_id")) or {}
            source_key = (str(source.get("document") or ""),
                          provenance_path(str(source.get("path") or ""))[0])
            target_key = (str(target.get("document") or ""),
                          provenance_path(str(target.get("path") or ""))[0])
            sources = [value for value in case_coordinates.get(source_key) or []
                       if value[0] in index.docs]
            targets = [value for value in case_coordinates.get(target_key) or []
                       if value[0] in index.docs]
            sources = sources or coord_map.get(source_key) or []
            targets = targets or coord_map.get(target_key) or []
            edges = _edge_relations(index, sources, targets) if sources and targets else []
            support = classify_reference_support(edges)
            rows.append({
                "case_no": case.get("case_no"), "current_status": current_status,
                "relation_id": relation.get("relation_id"),
                "source_id": relation.get("source_id"), "target_id": relation.get("target_id"),
                "source": source, "target": target,
                "validator_errors": relation.get("validation_errors") or [],
                "source_coordinate_matches": len(sources),
                "target_coordinate_matches": len(targets),
                "reference_edges": edges, "reference_support": support,
                "proof_quotes": relation.get("proof_quotes") or [],
            })
    statuses = Counter(row["reference_support"] for row in rows)
    rejected_lineage = [row for row in rows if row["current_status"] == "rejected"
                        and "implementation_document_lineage_unproven"
                        in row["validator_errors"]]
    summary = {
        "index_docs": len(index.docs),
        "index_document_names_sample": sorted({view.name for view in index.docs.values()})[:10],
        "candidates": len(rows),
        "reference_support": dict(sorted(statuses.items())),
        "lineage_rejected": len(rejected_lineage),
        "lineage_rejected_formal_reception_proven": sum(
            row["reference_support"] == "formal_reception_proven"
            for row in rejected_lineage),
        "lineage_rejected_nonimplementation_reference": sum(
            row["reference_support"] == "reference_but_not_implementation"
            for row in rejected_lineage),
        "generation_model": artifact.get("contract", {}).get("all_models"),
        "question_gold_reference_in_generation": False,
        "canonical_changed": False,
        "main_wiring_changed": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "experiment": "source-relation-reference-edge-audit-v1",
        "source": str(args.relations), "summary": summary, "rows": rows,
    }, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
