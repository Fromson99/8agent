#!/usr/bin/env python3
"""동결 51건에서 다중 채널 지배조문 후보 패널의 골든 포함률을 감사한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments.governing_anchor_selector import (  # noqa: E402
    governing_anchor_panel,
)
from lawrag.core.rag.experiments.typed_evidence_connections import (  # noqa: E402
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
    parser.add_argument("--max-candidates", type=int, default=8)
    args = parser.parse_args()

    _ = review
    suite = json.loads(args.suite.read_text("utf-8"))
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    retrieved_by_id = {str(row["case_no"]): row
                       for row in retrieval.get("rows") or []}
    index = index_mod.current()
    rows = []
    total_gold = panel_gold = first_gold = 0
    for case in suite.get("cases") or []:
        case_id = str(case["id"])
        selected = (((retrieved_by_id.get(case_id) or {}).get("variants") or {})
                    .get(args.variant) or {}).get("selected") or []
        evidence = reconstruct_evidence(index, list(selected))
        evidence = attach_typed_connections(
            index, str(case.get("question") or ""), evidence)
        panel = governing_anchor_panel(
            str(case.get("question") or ""), evidence,
            max_candidates=args.max_candidates)
        evidence_by_id = {str(row.get("id") or ""): row for row in evidence}
        expected = _expected_article_coords(case)
        total_gold += len(expected)
        panel_items = []
        case_panel_gold = 0
        for candidate in panel:
            source = evidence_by_id.get(candidate["evidence_id"]) or {}
            coords = _coords([{"doc": source.get("document"),
                               "path": source.get("path")}])
            is_gold = bool(coords & expected)
            case_panel_gold += len(coords & expected)
            panel_items.append({
                **candidate,
                "document": source.get("document"),
                "path": source.get("path"),
                "origin": source.get("role"),
                "connection_role": (source.get("typed_connection") or {}).get(
                    "connection_role"),
                "is_expected_article": is_gold,
            })
        case_panel_gold = min(case_panel_gold, len(expected))
        e1 = evidence[0] if evidence else {}
        e1_gold = bool(_coords([{"doc": e1.get("document"),
                                "path": e1.get("path")}]) & expected)
        first_gold += e1_gold
        panel_gold += case_panel_gold
        rows.append({
            "case_no": case_id,
            "question": case.get("question"),
            "expected_total": len(expected),
            "e1_is_expected": e1_gold,
            "panel_expected": case_panel_gold,
            "panel_all_expected": bool(expected)
            and case_panel_gold == len(expected),
            "panel": panel_items,
        })

    panel_sizes = [len(row["panel"]) for row in rows]
    summary = {
        "cases": len(rows),
        "max_candidates": args.max_candidates,
        "e1_gold_cases": first_gold,
        "e1_gold_case_rate": round(first_gold / len(rows), 4) if rows else 0,
        "gold_total": total_gold,
        "panel_gold": panel_gold,
        "panel_gold_recall": round(panel_gold / total_gold, 4) if total_gold else 0,
        "cases_all_gold_in_panel": sum(row["panel_all_expected"] for row in rows),
        "cases_gold_missing_from_panel": [
            row["case_no"] for row in rows if not row["panel_all_expected"]],
        "panel_size_mean": round(statistics.mean(panel_sizes), 3)
        if panel_sizes else 0,
    }
    blob = {
        "audit": "multi-channel-governing-anchor-panel-v1",
        "contract": {"llm_calls": 0, "main_wiring_changed": False,
                     "retrieval_frozen": True, "gold_visible_to_selector": False},
        "suite": str(args.suite), "summary": summary, "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
