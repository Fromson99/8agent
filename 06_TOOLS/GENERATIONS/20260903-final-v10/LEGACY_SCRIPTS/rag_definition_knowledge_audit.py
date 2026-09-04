#!/usr/bin/env python3
"""정의 용어·taxonomy·domain graph 연결층을 읽기 전용으로 감사한다."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_golden as review  # noqa: E402 — 저장소 환경 경로 고정
from lawrag.core.domain_graph.model import lexeme_id  # noqa: E402
from lawrag.core.domain_graph.store import GraphStore  # noqa: E402
from lawrag.core.rag import definitions, index as index_mod, taxonomy  # noqa: E402


def _counter(rows, key) -> dict:
    return dict(Counter(str(row.get(key) or "") for row in rows))


def _pack(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _taxonomy_stats(path: Path) -> dict:
    files = list(path.glob("*.jsonl"))
    rows, empty = [], 0
    for file in files:
        for line in file.read_text("utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("empty"):
                empty += 1
            else:
                rows.append(row)
    return {
        "files": len(files), "term_rows": len(rows), "empty_markers": empty,
        "hyponym_edges_raw": sum(len(row.get("hyponyms") or []) for row in rows),
        "hypernym_edges_raw": sum(len(row.get("hypernyms") or []) for row in rows),
        "terms_with_any_relation": sum(bool(row.get("hyponyms") or row.get("hypernyms"))
                                       for row in rows),
    }


def _canonical_stats(path: Path) -> dict:
    blob = json.loads(path.read_text("utf-8"))
    concepts = blob.get("concepts") or []
    relations = blob.get("relations") or []
    assertions = blob.get("assertions") or []
    return {
        "concepts": len(concepts), "concept_status": _counter(concepts, "status"),
        "concept_types": _counter(concepts, "type"),
        "concepts_with_definition_text": sum(bool(row.get("definitions"))
                                              for row in concepts),
        "relations": len(relations), "relation_status": _counter(relations, "status"),
        "relation_types": _counter(relations, "type"),
        "assertions": len(assertions), "assertion_status": _counter(assertions, "status"),
    }


def _runtime_definition_stats(index) -> tuple[dict, list[dict]]:
    rows = []
    docs_with_definitions = 0
    for doc_id, view in index.docs.items():
        found = definitions.defs(view)
        docs_with_definitions += int(bool(found))
        rows.extend({"doc_id": doc_id, "doc": view.name, **row} for row in found)
    packed = {re.sub(r"\s+", "", row["term"]).casefold() for row in rows}
    return ({
        "documents": len(index.docs), "documents_with_definitions": docs_with_definitions,
        "definition_rows": len(rows), "unique_terms_packed": len(packed),
        "kinds": _counter(rows, "kind"), "scopes": _counter(rows, "scope"),
        "rows_with_block": sum(row.get("block") is not None for row in rows),
        "rows_with_source": sum(bool(row.get("source")) for row in rows),
    }, rows)


def _glossary_stats(path: Path) -> tuple[dict, list[dict]]:
    terms = json.loads(path.read_text("utf-8")).get("terms") or []
    occurrences = [occ for term in terms for occ in term.get("occurrences") or []]
    suspicious = [term for term in terms
                  if re.search(r"(?:라\s*한다|이하|말한다)[)\s]*$", term.get("term") or "")]
    return ({
        "terms": len(terms), "status": _counter(terms, "status"),
        "source": _counter(terms, "source"), "confidence": _counter(terms, "confidence"),
        "terms_with_note": sum(bool(term.get("note")) for term in terms),
        "terms_with_occurrence": sum(bool(term.get("occurrences")) for term in terms),
        "occurrences": len(occurrences), "occurrence_via": _counter(occurrences, "via"),
        "definition_occurrences": sum(occ.get("via") == "정의" for occ in occurrences),
        "suspicious_declaration_tail_terms": len(suspicious),
        "suspicious_samples": [term.get("term") for term in suspicious[:20]],
    }, terms)


def _cm002(index, glossary_terms: list[dict]) -> dict:
    source = json.loads(
        (ROOT / "var/eval/e2e/ADR-0040/frame_only_answer_ab_51.json").read_text("utf-8"))
    row = next(item for item in source["rows"] if item["case_no"] == "cm-002")
    target = row["selected"][0]
    view = index.docs[target["doc_id"]]
    used = definitions.terms_in(view, target["node"], cap=50)
    contexts = definitions.context_entries(view, row["question"], [target["node"]], cap=50)
    glossary_by_key = {_pack(term.get("term")): term for term in glossary_terms}
    tx = taxonomy.current(index, None, {view.doc_id})
    public = []
    with GraphStore(ROOT / "data/domain_graph/graph.sqlite", readonly=True) as graph:
        for item in used:
            key = _pack(item["term"])
            lid = lexeme_id(item["term"])
            incoming_defines = graph.neighbors(lid, direction="in", kinds=("DEFINES",))
            parents = graph.neighbors(lid, direction="out", kinds=("IS_A",))
            children = graph.neighbors(lid, direction="in", kinds=("IS_A",))
            public.append({
                "term": item["term"], "kind": item["kind"], "node": item["node"],
                "path": view.path(item["node"]), "source": item.get("source"),
                "in_glossary": key in glossary_by_key,
                "taxonomy_hypernyms": tx.hypernyms(item["term"], grounded_only=False),
                "taxonomy_hyponyms": tx.hyponyms(item["term"], grounded_only=False),
                "graph_defining_sections": [edge["src"] for edge in incoming_defines],
                "graph_is_a_parents": [
                    (graph.get_node(edge["dst"]) or {}).get("label") for edge in parents],
                "graph_is_a_children": [
                    (graph.get_node(edge["src"]) or {}).get("label") for edge in children],
            })
    return {
        "question": row["question"], "governing_section": target,
        "terms_in_governing_section": public,
        "terms_in_count": len(public),
        "current_appendix_picker": contexts,
        "current_appendix_picker_count": len(contexts),
    }


def _cross_layer(runtime_rows: list[dict], glossary_terms: list[dict],
                 canonical_path: Path, taxonomy_path: Path) -> dict:
    runtime = {_pack(row["term"]) for row in runtime_rows}
    glossary = {_pack(row.get("term")) for row in glossary_terms
                if row.get("status") != "tombstone"}
    canonical_blob = json.loads(canonical_path.read_text("utf-8"))
    concepts = {_pack(row.get("label")) for row in canonical_blob.get("concepts") or []}
    taxonomy_terms = set()
    for path in taxonomy_path.glob("*.jsonl"):
        for line in path.read_text("utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not row.get("empty") and row.get("term"):
                taxonomy_terms.add(_pack(row["term"]))
    return {
        "runtime_definition_unique_terms": len(runtime),
        "runtime_terms_in_glossary": len(runtime & glossary),
        "runtime_to_glossary_coverage": round(len(runtime & glossary) / len(runtime), 4)
        if runtime else 0,
        "runtime_terms_in_canonical_concepts": len(runtime & concepts),
        "runtime_to_canonical_coverage": round(len(runtime & concepts) / len(runtime), 4)
        if runtime else 0,
        "runtime_terms_with_taxonomy_row": len(runtime & taxonomy_terms),
        "runtime_to_taxonomy_coverage": round(len(runtime & taxonomy_terms) / len(runtime), 4)
        if runtime else 0,
    }


def _suite_51(index, glossary_terms: list[dict]) -> dict:
    stage = json.loads(
        (ROOT / "var/eval/e2e/cm_core_legalclosure_stage_ablation_51.json").read_text("utf-8"))
    glossary = {_pack(row.get("term")) for row in glossary_terms
                if row.get("status") != "tombstone"}
    tx = taxonomy.current(index, None)
    section_count = definition_sections = 0
    usages = []
    case_counts = []
    for case in stage["rows"]:
        case_seen = set()
        selected = case["variants"]["control_d_then_verifier"]["selected"]
        section_count += len(selected)
        for section in selected:
            view = index.docs[section["doc_id"]]
            if definitions.is_definition_node(view, section["node"]):
                definition_sections += 1
                continue
            for row in definitions.terms_in(view, section["node"], cap=100):
                key = (section["doc_id"], row["node"], _pack(row["term"]))
                if key in case_seen:
                    continue
                case_seen.add(key)
                has_taxonomy = bool(tx.hypernyms(row["term"], grounded_only=False)
                                    or tx.hyponyms(row["term"], grounded_only=False))
                usages.append({"case_no": case["case_no"], "term": row["term"],
                               "in_glossary": _pack(row["term"]) in glossary,
                               "has_taxonomy": has_taxonomy})
        case_counts.append(len(case_seen))
    return {
        "cases": len(stage["rows"]), "selected_sections": section_count,
        "selected_definition_sections": definition_sections,
        "selected_substantive_sections": section_count - definition_sections,
        "cases_with_linked_definition_terms": sum(count > 0 for count in case_counts),
        "definition_term_usages_deduped_per_case": len(usages),
        "usage_terms_in_glossary": sum(row["in_glossary"] for row in usages),
        "usage_glossary_coverage": round(sum(row["in_glossary"] for row in usages)
                                           / len(usages), 4) if usages else 0,
        "usage_terms_with_taxonomy_relation": sum(row["has_taxonomy"] for row in usages),
        "usage_taxonomy_relation_coverage": round(
            sum(row["has_taxonomy"] for row in usages) / len(usages), 4) if usages else 0,
        "term_usages_per_case": {
            "min": min(case_counts), "max": max(case_counts),
            "mean": round(sum(case_counts) / len(case_counts), 3),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    index = index_mod.current().scoped(None)
    glossary_stats, glossary_terms = _glossary_stats(ROOT / "data/glossary.json")
    runtime_stats, runtime_rows = _runtime_definition_stats(index)
    with GraphStore(ROOT / "data/domain_graph/graph.sqlite", readonly=True) as store:
        graph_stats = store.counts()
    result = {
        "audit": "definition-knowledge-layers-v1", "llm_calls": 0,
        "glossary": glossary_stats, "runtime_definitions": runtime_stats,
        "taxonomy": _taxonomy_stats(ROOT / "data/taxonomy"),
        "canonical": _canonical_stats(ROOT / "data/domain_graph/canonical.json"),
        "property_graph": graph_stats,
        "cross_layer": _cross_layer(
            runtime_rows, glossary_terms, ROOT / "data/domain_graph/canonical.json",
            ROOT / "data/taxonomy"),
        "suite_51": _suite_51(index, glossary_terms),
        "cm002": _cm002(index, glossary_terms),
        "prompt_path_finding": {
            "current_definition_appendix_uses_glossary": False,
            "current_definition_appendix_uses_taxonomy": False,
            "current_definition_appendix_uses_property_graph": False,
            "current_definition_appendix_source": "rag.definitions.context_entries only",
        },
    }
    text = json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, "utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
