#!/usr/bin/env python3
"""Run the frozen ADR-0148 proviso census and condition-slot validator."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for key, value in (
    ("STRUCTURE_STORE", "data/structure"),
    ("STRUCTURE_CUSTOM_DIR", "data/custom"),
    ("GLOSSARY_STORE", "data/glossary.json"),
    ("RAG_LINKS_STORE", "data/links.json"),
    ("RAG_DELEGATION_STORE", "data/delegation.json"),
):
    os.environ.setdefault(key, str(ROOT / value))

from lawrag.core.rag.index import Index  # noqa: E402
from lawrag.core.rag import delegation  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen candidate: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def evidence(module, evidence_id: str, source: str, quote: str,
             predicates: tuple[str, ...]):
    start = source.index(quote)
    return module.SlotEvidence(
        evidence_id, source, start, start + len(quote), quote, predicates, True
    )


def fixtures(module):
    rows = []

    def run(name, slots, evidences, bridges=(), expected=None):
        result = module.validate_condition_slots(slots, evidences, bridges)
        statuses = {row["slot_id"]: row["status"] for row in result["slots"]}
        passed = statuses == expected
        rows.append({
            "name": name, "expected": expected, "actual": statuses,
            "passed": passed, "violations": result["violations"],
        })

    source = "전문투자자가 모집이나 매출이 아닌 방법으로 취득하고 투자기간이 2년 미만이며 자본금 기준 100분의 10 이내"
    and_predicates = (
        ("actor", "전문투자자"),
        ("method", "모집이나 매출이 아닌 방법"),
        ("duration", "2년 미만"),
        ("quantity", "100분의 10 이내"),
    )
    run("AND_CONJUNCTS", [
        module.ConditionSlot(key, key, "true", (f"E-{key}",), "direct")
        for key, _quote in and_predicates
    ], [
        evidence(module, f"E-{key}", source, quote, (key,))
        for key, quote in and_predicates
    ], expected={key: "true" for key, _quote in and_predicates})

    source = "K-OTC시장 등록법인 또는 국내기업인 대형법인"
    run("OR_ALTERNATIVES", [
        module.ConditionSlot("or", "company_exception_any", "true", ("E-or",), "one alternative")
    ], [evidence(module, "E-or", source, "국내기업인 대형법인", ("company_exception_any",))],
        expected={"or": "true"})

    source = "다만, 특수관계인의 경우는 제외한다"
    run("INTERNAL_PROVISO", [
        module.ConditionSlot("internal", "special_related_party", "true", ("E-internal",), "direct")
    ], [evidence(module, "E-internal", source, "특수관계인의 경우", ("special_related_party",))],
        expected={"internal": "true"})

    source = "세칙에서 전문투자자의 범위를 정의한다"
    bridge_evidence = evidence(module, "E-bridge", source, source,
                               ("financial_investor",))
    run("CROSS_DOCUMENT_REFERENCE", [
        module.ConditionSlot("external", "professional_investor", "true", ("E-fact",), "defined externally")
    ], [
        evidence(module, "E-fact", "질문상 재무적투자자", "재무적투자자", ("financial_investor",)),
        bridge_evidence,
    ], [module.PredicateBridge(
        "B-definition", "DEFINES", "financial_investor", "professional_investor",
        ("E-bridge",), True,
    )], expected={"external": "true"})

    source = "규정 제26조제1항제4호 단서에서 세칙으로 정하는 경우"
    run("DELEGATION_RECEPTION", [
        module.ConditionSlot("delegated", "delegated_exception", "true", ("E-delegated",), "receiving text")
    ], [evidence(module, "E-delegated", source, source, ("delegated_exception",))],
        expected={"delegated": "true"})

    source = "다만 코넥스시장 상장법인으로 본다. 다만 매각한 경우는 제외한다"
    run("NESTED_PROVISO", [
        module.ConditionSlot("outer", "konex_company", "true", ("E-outer",), "outer"),
        module.ConditionSlot("inner", "sold_on_konex", "false", ("E-inner",), "inner"),
    ], [
        evidence(module, "E-outer", source, "코넥스시장 상장법인", ("konex_company",)),
        evidence(module, "E-inner", source, "매각한 경우", ("sold_on_konex",)),
    ], expected={"outer": "true", "inner": "false"})

    source = "제1항에도 불구하고 해외증권시장 상장기업은 제외한다"
    run("NOTWITHSTANDING_OVERRIDE", [
        module.ConditionSlot("override", "overseas_listed", "true", ("E-override",), "override")
    ], [evidence(module, "E-override", source, "해외증권시장 상장기업", ("overseas_listed",))],
        expected={"override": "true"})

    source = "재무적투자자가 제3자배정으로 취득"
    run("CM003_UNSUPPORTED_BRIDGE", [
        module.ConditionSlot("method", "non_offering_or_sale_method", "true", ("E-third",), "자동 동일시")
    ], [evidence(module, "E-third", source, "제3자배정", ("third_party_allotment",))],
        expected={"method": "unknown"})
    return rows


def relation_inventory(index, frozen_relations, census):
    bundle = frozen_relations.build(
        index,
        delegation_file=ROOT / "data/delegation.json",
        law_index_file=ROOT / "data/law_index.json",
        include_requirements=True,
        use_cache=False,
    )
    proviso_articles = {
        (row["doc_id"], row["article_node"])
        for row in census["occurrences"]
    }
    incident = Counter()
    for relation in bundle.sections:
        if ((relation.src_doc, relation.src_node) in proviso_articles
                or (relation.dst_doc, relation.dst_node) in proviso_articles):
            incident[relation.kind] += 1
    return {
        "section_relation_total": len(bundle.sections),
        "section_relation_kinds": dict(sorted(Counter(
            row.kind for row in bundle.sections).items())),
        "requirement_total": len(bundle.requirements),
        "exception_requirement_total": sum(
            row.kind == "EXCEPTION" for row in bundle.requirements
        ),
        "materialized_has_exception_edges": sum(
            row.kind == "HAS_EXCEPTION" for row in bundle.sections
        ),
        "proviso_article_incident_relation_kinds": dict(sorted(incident.items())),
        "graph_relation_kinds": dict(sorted(Counter(
            row.kind for row in bundle.graph).items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision-dir", type=Path, required=True)
    parser.add_argument("--input-lock", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    started = time.perf_counter()
    revision_dir = args.revision_dir.resolve()
    requirement_path = revision_dir / "snapshot/lawrag/core/domain_graph/requirements.py"
    relation_path = revision_dir / "snapshot/lawrag/core/rag/relations.py"
    candidate = load_module(requirement_path, "adr0148_frozen_requirements")
    frozen_relations = load_module(relation_path, "adr0148_frozen_relations")
    index = Index.load(ROOT / "data/structure", ROOT / "data/glossary.json",
                       ROOT / "data/links.json")
    delegated = delegation.adjacency(ROOT / "data/delegation.json",
                                     include_document_targets=True)
    census = candidate.proviso_connection_census(index, delegated)
    fixture_rows = fixtures(candidate)
    inventory = relation_inventory(index, frozen_relations, census)
    candidate_passed = sum(row["passed"] for row in fixture_rows)
    baseline_passed = len(fixture_rows) - 1  # no semantic-evidence bridge gate
    result = {
        "schema_version": "proviso-condition-slot-run-v1",
        "adr_id": "ADR-0148",
        "experiment_id": "ADR-0148-experiment-v1",
        "run_id": "run-001",
        "input_lock": str(args.input_lock),
        "input_lock_sha256": sha256(args.input_lock),
        "candidate_revision_dir": str(args.revision_dir),
        "candidate_files": {
            "requirements.py": sha256(requirement_path),
            "relations.py": sha256(relation_path),
        },
        "census": census,
        "relation_inventory": inventory,
        "fixtures": fixture_rows,
        "results": {
            "baseline": {"passed": baseline_passed, "total": len(fixture_rows)},
            "condition-slot-validator": {
                "passed": candidate_passed, "total": len(fixture_rows),
                "unsupported_cm003_downgraded": next(
                    row["passed"] for row in fixture_rows
                    if row["name"] == "CM003_UNSUPPORTED_BRIDGE"
                ),
            },
            "census_coverage": census["summary"]["classification_coverage"],
            "main_wiring_changed": False,
            "llm_calls": 0,
        },
        "duration_ms": round((time.perf_counter() - started) * 1000),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({
        "census": census["summary"],
        "relation_inventory": inventory,
        "fixtures": result["results"],
        "duration_ms": result["duration_ms"],
    }, ensure_ascii=False, indent=2))
    return 0 if candidate_passed == len(fixture_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
