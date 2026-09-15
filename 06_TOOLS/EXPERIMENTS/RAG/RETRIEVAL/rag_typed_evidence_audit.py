#!/usr/bin/env python3
"""동결 51건 선택 근거를 타입 간선으로 분류하고 골든 보존율을 감사한다."""

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
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    args = parser.parse_args()

    # review import가 평가 데이터 루트를 먼저 고정한다.
    _ = review
    suite = json.loads(args.suite.read_text("utf-8"))
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    cases = {str(row["id"]): row for row in suite.get("cases") or []}
    rows_by_id = {str(row["case_no"]): row for row in retrieval.get("rows") or []}
    index = index_mod.current()
    rows = []
    roles = Counter()
    tiers = Counter()
    selected_total = eligible_total = support_total = 0
    gold_total = gold_selected = gold_eligible = gold_support = 0

    for case_id, case in cases.items():
        selected = (((rows_by_id.get(case_id) or {}).get("variants") or {})
                    .get(args.variant) or {}).get("selected") or []
        evidence = reconstruct_evidence(index, list(selected))
        typed = attach_typed_connections(index, str(case.get("question") or ""), evidence)
        expected = _expected_article_coords(case)
        gold_total += len(expected)
        items = []
        case_selected_gold = case_eligible_gold = case_support_gold = 0
        for row in typed:
            connection = dict(row.get("typed_connection") or {})
            role = str(connection.get("connection_role") or "unclassified")
            roles[role] += 1
            eligible = bool(connection.get("conclusion_eligible"))
            support = bool(connection.get("support_eligible"))
            tier = str(connection.get("evidence_tier") or "C_context_only")
            tiers[tier] += 1
            coordinate = _coords([{
                "doc": row.get("document"), "path": row.get("path")
            }])
            is_gold = bool(coordinate & expected)
            if is_gold:
                case_selected_gold += len(coordinate & expected)
                if eligible:
                    case_eligible_gold += len(coordinate & expected)
                if support:
                    case_support_gold += len(coordinate & expected)
            items.append({
                "evidence_id": row.get("id"), "document": row.get("document"),
                "path": row.get("path"), "origin": row.get("role"),
                "connection_role": role, "conclusion_eligible": eligible,
                "support_eligible": support, "evidence_tier": tier,
                "support_reasons": connection.get("support_reasons") or [],
                "title_alignment": connection.get("title_alignment") or 0,
                "direct_relations": connection.get("direct_relations") or [],
                "is_expected_article": is_gold,
            })
        case_selected_gold = min(case_selected_gold, len(expected))
        case_eligible_gold = min(case_eligible_gold, len(expected))
        case_support_gold = min(case_support_gold, len(expected))
        selected_total += len(items)
        eligible_count = sum(bool(row["conclusion_eligible"]) for row in items)
        eligible_total += eligible_count
        support_count = sum(bool(row["support_eligible"]) for row in items)
        support_total += support_count
        gold_selected += case_selected_gold
        gold_eligible += case_eligible_gold
        gold_support += case_support_gold
        rows.append({
            "case_no": case_id, "question": case.get("question"),
            "selected_count": len(items), "eligible_count": eligible_count,
            "support_count": support_count,
            "context_count": len(items) - eligible_count,
            "strict_context_count": len(items) - support_count,
            "expected_total": len(expected),
            "expected_selected": case_selected_gold,
            "expected_eligible": case_eligible_gold,
            "expected_support": case_support_gold,
            "items": items,
        })

    eligible_counts = sorted(row["eligible_count"] for row in rows)
    context_rates = sorted(
        row["context_count"] / row["selected_count"] if row["selected_count"] else 0
        for row in rows)
    middle = len(rows) // 2
    summary = {
        "cases": len(rows),
        "selected_total": selected_total,
        "eligible_total": eligible_total,
        "context_only_total": selected_total - eligible_total,
        "eligible_rate": round(eligible_total / selected_total, 4)
        if selected_total else 0,
        "eligible_per_case_p50": eligible_counts[middle] if eligible_counts else 0,
        "support_total": support_total,
        "support_rate": round(support_total / selected_total, 4)
        if selected_total else 0,
        "strict_context_total": selected_total - support_total,
        "context_rate_per_case_p50": round(context_rates[middle], 4)
        if context_rates else 0,
        "gold_total": gold_total,
        "gold_selected": gold_selected,
        "gold_eligible": gold_eligible,
        "gold_support": gold_support,
        "gold_selection_recall": round(gold_selected / gold_total, 4)
        if gold_total else 0,
        "gold_eligibility_recall": round(gold_eligible / gold_total, 4)
        if gold_total else 0,
        "gold_support_recall": round(gold_support / gold_total, 4)
        if gold_total else 0,
        "cases_all_gold_selected": sum(
            row["expected_total"] and row["expected_selected"] == row["expected_total"]
            for row in rows),
        "cases_any_gold_missing": sum(
            row["expected_selected"] < row["expected_total"] for row in rows),
        "cases_all_gold_eligible": sum(
            row["expected_total"] and row["expected_eligible"] == row["expected_total"]
            for row in rows),
        "cases_any_gold_eligible": sum(
            row["expected_eligible"] > 0 for row in rows),
        "cases_all_gold_supported": sum(
            row["expected_total"] and row["expected_support"] == row["expected_total"]
            for row in rows),
        "cases_gold_selected_but_ineligible": sum(
            row["expected_selected"] > row["expected_eligible"] for row in rows),
        "gold_missing_case_ids": [
            row["case_no"] for row in rows
            if row["expected_selected"] < row["expected_total"]],
        "gold_selected_but_ineligible_case_ids": [
            row["case_no"] for row in rows
            if row["expected_selected"] > row["expected_eligible"]],
        "gold_selected_but_unsupported_case_ids": [
            row["case_no"] for row in rows
            if row["expected_selected"] > row["expected_support"]],
        "connection_roles": dict(sorted(roles.items())),
        "evidence_tiers": dict(sorted(tiers.items())),
    }
    blob = {
        "audit": "typed-evidence-connection-audit-v1",
        "contract": {"llm_calls": 0, "main_wiring_changed": False,
                     "retrieval_frozen": True},
        "suite": str(args.suite), "summary": summary, "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
