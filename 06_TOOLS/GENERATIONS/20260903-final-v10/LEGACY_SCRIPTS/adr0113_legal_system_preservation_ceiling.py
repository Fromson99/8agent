#!/usr/bin/env python3
"""Post-seal, no-LLM ceiling for ADR-0113 legal-system preservation.

This diagnostic opens run-003 gold only after its product capture was sealed.
It must never be imported by product routing and does not replace a live run.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for key, relative in (
    ("STRUCTURE_STORE", "data/structure"),
    ("STRUCTURE_CUSTOM_DIR", "data/custom"),
    ("GLOSSARY_STORE", "data/glossary.json"),
    ("RAG_LINKS_STORE", "data/links.json"),
    ("RAG_DELEGATION_STORE", "data/delegation.json"),
    ("RAG_LAW_INDEX_STORE", "data/law_index.json"),
    ("RAG_ENGINE_RULES", "data/rules/engine.json"),
):
    os.environ.setdefault(key, str(ROOT / relative))

from lawrag.core.rag.index import Index  # noqa: E402
from lawrag.core.rag.legal_research_atlas import LegalResearchAtlas  # noqa: E402
from lawrag.core.rag.legal_research_llm_selector import (  # noqa: E402
    branches_from_query_plan,
)
from lawrag.core.rag.legal_system_entry import (  # noqa: E402
    LegalSystemEntryPlanner,
    scope_alignment,
)


ADR = ROOT / "docs/adr/ADR-0113-legal-system-entry-routing-full-stack"
RUN = ADR / "artifacts/run-003.json"
LAW_LEDGER = ADR / "artifacts/law-route-ledger-run-003.json"
OUTPUT = ADR / "artifacts/posthoc-preservation-ceiling-run-004.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(value: object) -> None:
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)


def main() -> None:
    run = json.loads(RUN.read_text(encoding="utf-8"))
    law = json.loads(LAW_LEDGER.read_text(encoding="utf-8"))
    atlas = LegalResearchAtlas.from_index(Index.load())
    cases = []
    aggregate_by_limit = {str(limit): 0 for limit in (1, 2, 4, 8)}
    target_total = 0
    target_in_prior = 0
    for product_case in run["product_cases"]:
        case_id = product_case["case_id"]
        query_plan = product_case["query_plan"]
        branches = branches_from_query_plan(query_plan)
        plans = LegalSystemEntryPlanner(
            atlas, instrument_limit=8, entry_limit=8,
        ).plan(product_case["question"], query_plan, branches)
        scored = next(
            row for row in run["scored_cases"] if row["case_id"] == case_id
        )
        gold = set(scored["gold_coordinates"])
        law_case = next(
            row for row in law["cases"] if row["case_id"] == case_id
        )
        prior_laws = {
            instrument.instrument_id
            for plan in plans
            for instrument in plan.instruments
        }
        target_ids = {
            str(row["instrument_id"]) for row in law_case["target_laws"]
        }
        target_total += len(target_ids)
        target_in_prior += len(target_ids & prior_laws)
        by_limit = {}
        for limit in (1, 2, 4, 8):
            candidates = {}
            for plan in plans:
                for instrument in plan.instruments:
                    for point in instrument.entry_points[:limit]:
                        coordinate = f"{point.unit.instrument_id}:{point.unit.node_id}"
                        candidates[coordinate] = point
            accepted = set()
            rejected = {}
            for coordinate, point in candidates.items():
                view = atlas.current_index.entry_docs[point.unit.instrument_id]
                node = view.by_id[point.unit.node_id]
                text = str(view.section_text(dict(node), cap=10**9) or "")
                alignment = scope_alignment(query_plan, text)
                if alignment["numeric_only"] or alignment["wrong_actor_delegation"]:
                    rejected[coordinate] = alignment
                else:
                    accepted.add(coordinate)
            hits = sorted(gold & accepted)
            by_limit[str(limit)] = {
                "candidate_count": len(accepted),
                "gold_hits": len(hits),
                "gold_total": len(gold),
                "gold_coordinates": hits,
                "semantic_scope_rejected_count": len(rejected),
            }
            aggregate_by_limit[str(limit)] += len(hits)
        cases.append({
            "case_id": case_id,
            "target_law_total": len(target_ids),
            "target_law_in_top8_prior": len(target_ids & prior_laws),
            "missing_target_law_ids": sorted(target_ids - prior_laws),
            "by_protected_entry_limit": by_limit,
            "entry_plans": [plan.to_dict() for plan in plans],
        })
    artifact = {
        "schema_version": "adr-0113-posthoc-preservation-ceiling-v1",
        "classification": "post-seal in-sample diagnostic ceiling; not a live product run",
        "api_calls": 0,
        "gold_visible_to_product": False,
        "source_run": {"path": str(RUN.relative_to(ROOT)), "sha256": _sha(RUN)},
        "source_law_ledger": {
            "path": str(LAW_LEDGER.relative_to(ROOT)), "sha256": _sha(LAW_LEDGER),
        },
        "algorithm": {
            "instrument_prior_limit_per_branch": 8,
            "entry_limits": [1, 2, 4, 8],
            "preservation": "union current semantic entries across all prior laws",
            "scope_filter": "reject numeric-only and wrong-actor delegation collisions",
        },
        "aggregate": {
            "target_law_in_top8_prior": target_in_prior,
            "target_law_total": target_total,
            "gold_hits_by_protected_entry_limit": aggregate_by_limit,
            "gold_total": 36,
        },
        "cases": cases,
    }
    artifact["artifact_sha256"] = hashlib.sha256(
        json.dumps(
            artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    _write(artifact)
    print(json.dumps(artifact["aggregate"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
