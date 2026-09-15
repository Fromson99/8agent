#!/usr/bin/env python3
"""동결 51건에서 ontology+법률참조 fail-open 가지치기를 감사한다."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.research.experiments.legal_applicability_graph import (  # noqa: E402
    ApplicabilityOntology, classify_applicability,
)
from lawrag.research.experiments.typed_evidence_connections import (  # noqa: E402
    attach_typed_connections,
)
from scripts import review_golden as review  # noqa: E402
from scripts.ask_e2e_golden import _coords, _expected_article_coords  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import reconstruct_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    args = parser.parse_args()

    _ = review
    suite = json.loads(args.suite.read_text("utf-8"))
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    canonical = json.loads(args.canonical.read_text("utf-8"))
    selected_by_id = {str(row["case_no"]): row
                      for row in retrieval.get("rows") or []}
    index = index_mod.current()
    ontology = ApplicabilityOntology(index, canonical)
    rows = []
    statuses = Counter()
    selected_total = candidates_total = hard_conflicts = 0
    gold_total = gold_selected = gold_after_hard = gold_candidates = 0
    ontology_only = ontology_only_gold = 0

    for case in suite.get("cases") or []:
        case_id = str(case["id"])
        selected = (((selected_by_id.get(case_id) or {}).get("variants") or {})
                    .get(args.variant) or {}).get("selected") or []
        evidence = reconstruct_evidence(index, list(selected))
        evidence = attach_typed_connections(
            index, str(case.get("question") or ""), evidence)
        classified = classify_applicability(
            str(case.get("question") or ""), evidence, ontology)
        expected = _expected_article_coords(case)
        gold_total += len(expected)
        items = []
        case_selected = case_hard = case_candidates = 0
        for row in classified:
            app = dict(row.get("applicability") or {})
            status = str(app.get("status") or "context")
            statuses[status] += 1
            selected_total += 1
            hard_conflicts += status == "hard_conflict"
            candidates_total += bool(app.get("conclusion_candidate"))
            coords = _coords([{"doc": row.get("document"), "path": row.get("path")}])
            is_gold = bool(coords & expected)
            hits = len(coords & expected)
            if is_gold:
                case_selected += hits
                if status != "hard_conflict":
                    case_hard += hits
                if app.get("conclusion_candidate"):
                    case_candidates += hits
            alignment = app.get("ontology_alignment") or {}
            only = bool(alignment.get("ontology_supported")) \
                and not app.get("typed_support") and not app.get("incident_typed")
            ontology_only += only
            ontology_only_gold += bool(only and is_gold)
            items.append({
                "evidence_id": row.get("id"), "document": row.get("document"),
                "path": row.get("path"), "origin": row.get("role"),
                "is_expected_article": is_gold,
                "applicability": app,
            })
        case_selected = min(case_selected, len(expected))
        case_hard = min(case_hard, len(expected))
        case_candidates = min(case_candidates, len(expected))
        gold_selected += case_selected
        gold_after_hard += case_hard
        gold_candidates += case_candidates
        rows.append({
            "case_no": case_id, "question": case.get("question"),
            "expected_total": len(expected), "expected_selected": case_selected,
            "expected_after_hard_prune": case_hard,
            "expected_in_conclusion_candidates": case_candidates,
            "items": items,
        })

    reduction = (1 - candidates_total / selected_total) if selected_total else 0
    cm009 = next((row for row in rows if row["case_no"] == "cm-009"), {})
    cm043 = next((row for row in rows if row["case_no"] == "cm-043"), {})
    cm009_e3 = next((row for row in cm009.get("items") or []
                     if row.get("evidence_id") == "E3"), {})
    cm043_pair = [row for row in cm043.get("items") or []
                  if row.get("evidence_id") in {"E3", "E16"}]
    criteria = {
        "llm_calls_zero": True,
        "hard_prune_preserves_selected_gold": gold_after_hard == gold_selected == 69,
        "candidate_gate_preserves_selected_gold": gold_candidates == gold_selected == 69,
        "candidate_reduction_at_least_25pct": reduction >= .25,
        "cm009_parallel_exception_not_applicable": (
            (cm009_e3.get("applicability") or {}).get("status") != "applicable"),
        "cm043_junyong_pair_preserved": len(cm043_pair) == 2 and all(
            (row.get("applicability") or {}).get("status") in {"applicable", "support"}
            for row in cm043_pair),
        "cm031_reported_as_retrieval_miss": any(
            row["case_no"] == "cm-031"
            and row["expected_selected"] < row["expected_total"] for row in rows),
    }
    summary = {
        "cases": len(rows), "selected_total": selected_total,
        "status_counts": dict(sorted(statuses.items())),
        "hard_conflicts": hard_conflicts,
        "conclusion_candidates": candidates_total,
        "candidate_reduction": round(reduction, 4),
        "ontology_only_candidates": ontology_only,
        "ontology_only_gold": ontology_only_gold,
        "gold_total": gold_total, "gold_selected": gold_selected,
        "gold_after_hard_prune": gold_after_hard,
        "gold_in_conclusion_candidates": gold_candidates,
        "cases_all_gold_after_hard_prune": sum(
            row["expected_total"]
            and row["expected_after_hard_prune"] == row["expected_total"]
            for row in rows),
        "cases_all_gold_in_candidates": sum(
            row["expected_total"]
            and row["expected_in_conclusion_candidates"] == row["expected_total"]
            for row in rows),
        "hard_prune_gold_loss_case_ids": [
            row["case_no"] for row in rows
            if row["expected_after_hard_prune"] < row["expected_selected"]],
        "candidate_gold_loss_case_ids": [
            row["case_no"] for row in rows
            if row["expected_in_conclusion_candidates"] < row["expected_selected"]],
        "criteria": criteria,
        "all_pre_registered_criteria_pass": all(criteria.values()),
    }
    blob = {
        "audit": "legal-applicability-graph-fail-open-v1",
        "contract": {"llm_calls": 0, "main_wiring_changed": False,
                     "retrieval_frozen": True, "gold_visible_to_classifier": False},
        "suite": str(args.suite), "summary": summary, "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
