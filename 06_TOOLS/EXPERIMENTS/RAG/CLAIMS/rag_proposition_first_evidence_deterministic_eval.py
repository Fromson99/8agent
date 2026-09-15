#!/usr/bin/env python3
"""Deterministically evaluate ADR-0129 sealed evidence without an LLM judge."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable, Mapping

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import rag_proposition_first_evidence_golden_61 as experiment  # noqa: E402
from lawrag.runtime import retrieval_stage_ledger as ledger  # noqa: E402


ADR = experiment.ADR
CAPTURES = ADR / "artifacts/product-captures/run-001"
SEAL = ADR / "artifacts/product-capture-seal-run-001.json"
SCORING = ADR / "artifacts/scoring-fixture-run-001.json"
OUTPUT = ADR / "artifacts/deterministic-evidence-evaluation-run-001.json"
LEDGER = ADR / "artifacts/retrieval-stage-ledger-run-001.json"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _self_hash(value: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(value))
    payload.pop("artifact_sha256", None)
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _percentile(values: Iterable[float], fraction: float) -> float:
    rows = sorted(float(value) for value in values)
    if not rows:
        return 0.0
    index = max(0, min(len(rows) - 1, int((len(rows) - 1) * fraction + .999999)))
    return round(rows[index], 3)


def _capture_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seal = _read(SEAL)
    if seal.get("case_count") != 61 or seal.get("gold_visible_to_product") is not False:
        raise RuntimeError("ADR-0129 product seal contract mismatch")
    rows: list[dict[str, Any]] = []
    captures: list[dict[str, Any]] = []
    for receipt in seal["case_receipts"]:
        case_id = str(receipt["case_id"])
        path = CAPTURES / f"{case_id}.json"
        if _sha256(path) != receipt["sha256"]:
            raise RuntimeError(f"sealed capture hash mismatch: {case_id}")
        capture = _read(path)
        captures.append(capture)
        rows.append({
            "case_id": case_id,
            "arms": {
                arm: {"product": capture["arms"][arm]}
                for arm in experiment.ARMS
            },
        })
    return rows, captures


def _paired(v3: Mapping[str, Any], key: str) -> dict[str, Any]:
    baseline = {
        row["case_id"]: row[key] for row in v3[experiment.BASELINE_ARM]["case_rows"]
    }
    candidate = {
        row["case_id"]: row[key] for row in v3[experiment.CANDIDATE_ARM]["case_rows"]
    }
    labels: Counter[str] = Counter()
    gained: list[str] = []
    lost: list[str] = []
    both_incomplete: list[str] = []
    for case_id in baseline:
        before = int(baseline[case_id]["fn"]) == 0
        after = int(candidate[case_id]["fn"]) == 0
        if after and not before:
            label = "candidate_only_complete"
            gained.append(case_id)
        elif before and not after:
            label = "baseline_only_complete"
            lost.append(case_id)
        elif before:
            label = "both_complete"
        else:
            label = "both_incomplete"
            both_incomplete.append(case_id)
        labels[label] += 1
    return {
        "counts": dict(labels),
        "candidate_only_complete_cases": gained,
        "baseline_only_complete_cases": lost,
        "both_incomplete_cases": both_incomplete,
    }


def _usage(captures: list[Mapping[str, Any]], arm: str) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
    for capture in captures:
        usage = capture["arms"][arm].get("usage") or {}
        totals["input_tokens"] += int(usage.get("input_tokens") or 0)
        totals["output_tokens"] += int(usage.get("output_tokens") or 0)
        totals["calls"] += len(capture["arms"][arm].get("provider_calls") or ())
    return totals


def build_report() -> dict[str, Any]:
    rows, captures = _capture_rows()
    v3 = {arm: experiment._aggregate_v3(rows, arm) for arm in experiment.ARMS}
    arm_runtime: dict[str, Any] = {}
    for arm in experiment.ARMS:
        products = [capture["arms"][arm] for capture in captures]
        metrics = [product.get("execution_metrics") or {} for product in products]
        arm_runtime[arm] = {
            "complete_cases": sum(product.get("status") == "complete" for product in products),
            "error_cases": [
                capture["case_id"] for capture, product in zip(captures, products)
                if product.get("status") != "complete"
            ],
            "presented_total": sum(len((product.get("retrieval") or {}).get("sections") or ()) for product in products),
            "presented_mean": round(statistics.mean(
                len((product.get("retrieval") or {}).get("sections") or ()) for product in products
            ), 6),
            "wall_ms_p50": _percentile((product.get("wall_ms") or 0 for product in products), .50),
            "wall_ms_p95": _percentile((product.get("wall_ms") or 0 for product in products), .95),
            "usage": _usage(captures, arm),
            "targeted_probe_count": sum(int(metric.get("targeted_probe_count") or 0) for metric in metrics),
            "targeted_added_count": sum(int(metric.get("targeted_added_count") or 0) for metric in metrics),
            "global_block_count": sum(int(metric.get("global_block_count") or 0) for metric in metrics),
            "floor_preserved_cases": sum(bool(metric.get("floor_preserved")) for metric in metrics),
            "integrity_violation_count": sum(
                int(metric.get(key.removesuffix("_violations") + "_violation_count") or 0)
                for metric in metrics for key in experiment._VIOLATION_KEYS
            ),
        }
    compact_v3 = {
        arm: {
            "presented": value["presented"],
            "declared": value["declared"],
            "unresolved_evidence_ids": value["unresolved_evidence_ids"],
            "case_rows": value["case_rows"],
        }
        for arm, value in v3.items()
    }
    result = {
        "schema_version": "adr-0129-deterministic-evidence-evaluation-v1",
        "adr_id": experiment.ADR_ID,
        "experiment_id": experiment.EXPERIMENT_ID,
        "run_id": experiment.RUN_ID,
        "evaluation_mode": "sealed set-containment; no LLM judge",
        "judge_calls_used_for_metrics": 0,
        "product_seal_path": str(SEAL.relative_to(ROOT)),
        "product_seal_sha256": _sha256(SEAL),
        "scoring_fixture_path": str(SCORING.relative_to(ROOT)),
        "scoring_fixture_sha256": _sha256(SCORING),
        "gold_opened_after_product_seal": True,
        "arms": arm_runtime,
        "golden_v3": compact_v3,
        "paired_presented_complete": _paired(v3, "presented"),
        "paired_declared_complete": _paired(v3, "declared"),
        "scope_note": (
            "This report measures evidence retrieval and answer-declared evidence coverage. "
            "It does not infer semantic legal-answer correctness from article identity alone."
        ),
    }
    result["artifact_sha256"] = _self_hash(result)
    return result


def write_stage_ledger() -> dict[str, Any]:
    """Grade the already sealed gold-free stage captures; never call a model."""

    _, captures = _capture_rows()
    score_by_id = {
        str(row["case_id"]): row for row in _read(SCORING)["cases"]
    }
    graded = []
    for capture in captures:
        score = score_by_id[str(capture["case_id"])]
        gold = [
            (str(row["doc_id"]), int(row["node"]))
            for row in score["gold_articles"]
        ]
        for arm in experiment.ARMS:
            graded.append(ledger.grade_capture(
                capture["arms"][arm]["retrieval"]["stage_capture"], gold,
            ))
    declared = {
        arm: [row["stage_id"] for row in experiment.STAGE_PLAN[arm]]
        for arm in experiment.ARMS
    }
    run = ledger.build_run_artifact(experiment.RUN_ID, graded, declared)
    value = ledger.build_experiment_artifact(
        experiment.ADR_ID, experiment.EXPERIMENT_ID, [run],
    )
    if LEDGER.exists():
        if _read(LEDGER) != value:
            raise RuntimeError(f"existing retrieval ledger differs: {LEDGER}")
    else:
        LEDGER.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--write-ledger", action="store_true")
    args = parser.parse_args()
    report = build_report()
    if args.write:
        if OUTPUT.exists():
            existing = _read(OUTPUT)
            if existing != report:
                raise RuntimeError(f"existing deterministic report differs: {OUTPUT}")
        else:
            OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    if args.write_ledger:
        write_stage_ledger()
    summary = {
        "evaluation_mode": report["evaluation_mode"],
        "judge_calls_used_for_metrics": 0,
        "arms": report["arms"],
        "golden_v3": {
            arm: {
                "presented": value["presented"],
                "declared": value["declared"],
                "unresolved_evidence_ids": value["unresolved_evidence_ids"],
            }
            for arm, value in report["golden_v3"].items()
        },
        "paired_presented_complete": report["paired_presented_complete"],
        "paired_declared_complete": report["paired_declared_complete"],
        "artifact_sha256": report["artifact_sha256"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
