#!/usr/bin/env python3
"""LegalClosure 오답이 새 검색 채널이 필요한 회수 실패인지 판별한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    rows = []
    counts = {"selected": 0, "selection_miss": 0, "retrieval_miss": 0}
    for row in baseline.get("rows") or []:
        for gold in row.get("gold") or []:
            if gold.get("selected"):
                classification = "selected"
            elif gold.get("candidate_upper"):
                classification = "selection_miss"
            else:
                classification = "retrieval_miss"
            counts[classification] += 1
            rows.append({
                "case_no": row.get("case_no"),
                "law": gold.get("law"),
                "article": gold.get("article"),
                "candidate_upper": bool(gold.get("candidate_upper")),
                "selected": bool(gold.get("selected")),
                "classification": classification,
                "dense_rescue_eligible": classification == "retrieval_miss",
            })
    total = sum(counts.values())
    result = {
        "experiment": "legalclosure-conditional-rescue-gate-v1",
        "baseline": str(args.baseline),
        "hypothesis": "Dense/ColBERT는 구조 후보 상한에도 없는 조문만 조건부로 구제한다.",
        "contract": {
            "main": "LegalClosure",
            "dense_runs_only_when": "gold-independent runtime signal shows no adequate structural candidate",
            "diagnostic_gold_use": "classification only; never routing or ranking",
            "selected_or_selection_miss": "do not add retrieval channel",
        },
        "summary": {
            "gold": total,
            **counts,
            "candidate_upper_recall": round(
                (counts["selected"] + counts["selection_miss"]) / total, 4) if total else 0,
            "dense_rescue_eligible": counts["retrieval_miss"],
            "decision": "do_not_add_dense_to_main_for_current_failures"
                if not counts["retrieval_miss"] else "evaluate_dense_on_retrieval_misses_only",
        },
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
