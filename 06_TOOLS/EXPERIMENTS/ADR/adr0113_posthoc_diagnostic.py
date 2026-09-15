#!/usr/bin/env python3
"""Post-seal diagnostics for ADR-0113; never imported by product routing."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
RUN = (
    ROOT
    / "docs/adr/ADR-0113-legal-system-entry-routing-full-stack"
    / "artifacts/run-003.json"
)


def main() -> None:
    run = json.loads(RUN.read_text(encoding="utf-8"))
    for case in run["product_cases"]:
        scored = next(
            row for row in run["scored_cases"]
            if row["case_id"] == case["case_id"]
        )
        gold = set(scored["gold_coordinates"])
        ranks: dict[str, int] = {}
        for plan in case["legal_system_entry_plan"]:
            for instrument in plan["instruments"]:
                for rank, point in enumerate(instrument["entry_points"], 1):
                    coordinate = f"{point['instrument_id']}:{point['node_id']}"
                    ranks[coordinate] = min(rank, ranks.get(coordinate, 10**9))
        hits = sorted((ranks[value], value) for value in gold if value in ranks)
        print(json.dumps({
            "case_id": case["case_id"],
            "gold_total": len(gold),
            "gold_in_top8_entry": len(hits),
            "ranked_hits": hits,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
