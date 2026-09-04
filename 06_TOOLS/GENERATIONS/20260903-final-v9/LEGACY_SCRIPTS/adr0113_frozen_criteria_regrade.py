#!/usr/bin/env python3
"""Regrade sealed ADR-0113 run-004 against its frozen domain criteria.

The inherited ADR-0108 scorer treats an article-wave cursor as global budget
starvation and counts only provider-menu law exposure.  ADR-0113 froze a
different meaning before run-004: corpus prior exposure and cross-case budget
isolation.  This deterministic regrade preserves the raw run unchanged.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs/adr/ADR-0113-legal-system-entry-routing-full-stack"
RUN = ADR / "artifacts/run-004.json"
LAW = ADR / "artifacts/law-route-ledger-run-004.json"
OUTPUT = ADR / "artifacts/frozen-criteria-regrade-run-004.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provider_usage(receipts):
    return {
        "calls": len(receipts),
        "input_tokens": sum(
            int((row.get("provider") or {}).get("usage", {}).get("input_tokens") or 0)
            for row in receipts
        ),
        "output_tokens": sum(
            int((row.get("provider") or {}).get("usage", {}).get("output_tokens") or 0)
            for row in receipts
        ),
    }


def main() -> None:
    run = json.loads(RUN.read_text(encoding="utf-8"))
    law = json.loads(LAW.read_text(encoding="utf-8"))
    product_by_case = {row["case_id"]: row for row in run["product_cases"]}
    prior_exposed = 0
    prior_rows = []
    for law_case in law["cases"]:
        case_id = law_case["case_id"]
        product_case = product_by_case[case_id]
        prior_ids = {
            str(instrument["instrument_id"])
            for plan in product_case["legal_system_entry_plan"]
            for instrument in plan["instruments"]
        }
        for target in law_case["target_laws"]:
            exposed = str(target["instrument_id"]) in prior_ids
            prior_exposed += int(exposed)
            prior_rows.append({
                "case_id": case_id,
                "instrument_id": target["instrument_id"],
                "system_prior_exposed": exposed,
                "provider_menu_exposed": target["candidate_exposed"],
                "final_route_selected": target["candidate_selected"],
            })

    scored = run["scored_cases"]
    instrument_route_gold = sum(
        int(row["candidate_instrument_route_gold_hits"]) for row in scored
    )
    observed_gold = sum(
        int(row["candidate_hierarchy_observed_gold_hits"]) for row in scored
    )
    present_gold = sum(int(row["candidate_present_gold_hits"]) for row in scored)
    case_budget = {}
    for case_id, product_case in product_by_case.items():
        receipts = product_case["provider_receipts"]
        article_calls = sum(
            1 for row in receipts if row.get("stage") == "ARTICLE_ROUTE"
        )
        usage = _provider_usage(receipts)
        case_budget[case_id] = {
            **usage,
            "article_calls": article_calls,
            "case_call_limit": 40,
            "case_input_token_limit": 250000,
            "cross_case_starved": article_calls == 0,
            "local_article_wave_cursor": (
                (product_case.get("research") or {}).get("stop_reason")
                == "ARTICLE_WAVE_BUDGET_EXHAUSTED_WITH_CURSOR"
            ),
        }

    summary = run["summary"]
    usage = summary["provider_usage"]
    checks = {
        "system_prior_target_law_exposure_at_least_9_of_12": prior_exposed >= 9,
        "final_target_law_selection_at_least_9_of_12": (
            law["aggregate"]["candidate_selected"] >= 9
        ),
        "instrument_route_gold_at_least_27_of_36": instrument_route_gold >= 27,
        "semantic_entry_observed_gold_at_least_24_of_36": observed_gold >= 24,
        "candidate_present_gold_at_least_18_of_36": present_gold >= 18,
        "every_case_received_article_calls": all(
            row["article_calls"] > 0 for row in case_budget.values()
        ),
        "cross_case_starvation_zero": all(
            not row["cross_case_starved"] for row in case_budget.values()
        ),
        "known_scope_false_positives_absent": not summary["forbidden_present"],
        "canonical_first_pass_validity_100pct": (
            summary["first_pass_validity"]["valid_rate"] == 1.0
        ),
        "page_cap_violations_zero": not summary["page_cap_violations"],
        "unapplied_waves_zero": not summary["unapplied_waves"],
        "product_calls_at_most_120": usage["calls"] <= 120,
        "input_tokens_at_most_750000": usage["input_tokens"] <= 750000,
        "output_tokens_at_most_150000": usage["output_tokens"] <= 150000,
        "call_p95_at_most_20000ms": usage["provider_duration_p95_ms"] <= 20000,
        "wall_at_most_720000ms": summary["wall_ms"] <= 720000,
        "transport_retry_zero": summary["success_checks"]["transport_retry_zero"],
        "gold_visible_to_product_false": summary["success_checks"][
            "gold_visible_to_product_false"
        ],
    }
    artifact = {
        "schema_version": "adr-0113-frozen-criteria-regrade-v1",
        "classification": "deterministic scoring correction; raw run unchanged",
        "api_calls": 0,
        "source_run": {"path": str(RUN.relative_to(ROOT)), "sha256": _sha(RUN)},
        "source_law_ledger": {"path": str(LAW.relative_to(ROOT)), "sha256": _sha(LAW)},
        "inherited_scorer_mismatch": {
            "law_exposure": "inherited scorer counts provider menu only; frozen ADR-0113 criterion counts closed-corpus system prior exposure",
            "budget": "inherited scorer rejects any local article-wave cursor; frozen ADR-0113 criterion rejects cross-case starvation",
        },
        "metrics": {
            "system_prior_target_law_exposed": prior_exposed,
            "provider_menu_target_law_exposed": law["aggregate"]["candidate_exposed"],
            "final_target_law_selected": law["aggregate"]["candidate_selected"],
            "target_law_total": law["target_law_total"],
            "instrument_route_gold": instrument_route_gold,
            "semantic_entry_observed_gold": observed_gold,
            "candidate_present_gold": present_gold,
            "gold_total": 36,
            "case_budget": case_budget,
            "provider_usage": usage,
            "wall_ms": summary["wall_ms"],
        },
        "target_law_rows": prior_rows,
        "checks": checks,
        "passed": all(checks.values()),
    }
    artifact["artifact_sha256"] = hashlib.sha256(
        json.dumps(
            artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    print(json.dumps({
        "passed": artifact["passed"],
        **artifact["metrics"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
