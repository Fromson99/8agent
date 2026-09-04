#!/usr/bin/env python3
"""ADR-0078 run-002: deterministic pool-union accounting regrade.

Run-001 correctly preserved every incumbent coordinate, but its candidate arm
recorded only the ADR-0068 route pool in ``internal_pool``.  One incumbent
admitted by ADR-0072 was outside that route pool, so the audit incorrectly
reported ``candidate_subset_of_pool=false``.  This regrade unions incumbent and
route pool for every arm and performs no model or retrieval call.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import rag_verified_span_coverage_gate_golden_61 as run1


ADR_ID = "ADR-0078"
RUN_ID = "run-002"
SOURCE = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0078-verified-span-coverage-explore-gate/artifacts/run-001.json"
SOURCE_SHA256 = "8150ee77c0e891baaeac5b678a1ae34e60547d417ebeae720512bc37c32f152f"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _union_pool(selected: list[dict], pool: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple] = set()
    for value in [*selected, *pool]:
        key = (str(value.get("doc_id") or ""), value.get("node"))
        if key in seen:
            continue
        seen.add(key)
        row = deepcopy(value)
        row["rank"] = len(result) + 1
        result.append(row)
    return result


def _regrade_row(case: dict, source: dict) -> dict:
    row = deepcopy(source)
    shared_pool = _union_pool(
        row["arms"]["baseline"]["selected"],
        row["arms"]["baseline"]["internal_pool"],
    )
    for arm_id in run1.ARMS:
        arm = row["arms"][arm_id]
        arm["internal_pool"] = deepcopy(shared_pool)
        arm["internal_pool_count"] = len(shared_pool)
        gold, all_hit, pool_all_hit = run1.basis_runner._grade(
            case, arm["selected"], arm["internal_pool"])
        arm["gold_results"] = gold
        arm["case_all_gold_hit"] = all_hit
        arm["case_all_gold_internal_pool_hit"] = pool_all_hit
    candidate = row["arms"]["coverage-routed-explore"]
    base_coords = {(item["doc_id"], item["node"])
                   for item in row["arms"]["baseline"]["selected"]}
    candidate_coords = {(item["doc_id"], item["node"])
                        for item in candidate["selected"]}
    pool_coords = {(item["doc_id"], item["node"])
                   for item in candidate["internal_pool"]}
    candidate["append_only_audit"] = {
        "baseline_subset_of_candidate": base_coords <= candidate_coords,
        "candidate_subset_of_pool": candidate_coords <= pool_coords,
        "hard_deletes_zero": not (base_coords - candidate_coords),
        "passed": (base_coords <= candidate_coords
                   and candidate_coords <= pool_coords),
        "regraded_reason": "incumbent_union_route_pool",
    }
    row["paired"] = {
        "baseline__coverage-gate-only": run1.basis_runner._paired(
            row["arms"]["baseline"], row["arms"]["coverage-gate-only"]),
        "baseline__coverage-routed-explore": run1.basis_runner._paired(
            row["arms"]["baseline"], candidate),
        "coverage-gate-only__coverage-routed-explore":
            run1.basis_runner._paired(
                row["arms"]["coverage-gate-only"], candidate),
    }
    row["regrade"] = {
        "run_id": RUN_ID, "model_calls": 0,
        "change": "internal_pool := dedupe(incumbent + route_pool)",
        "answer_or_selection_changed": False,
    }
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adr", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    adr = args.adr if args.adr.is_absolute() else ROOT / args.adr
    out = args.out or adr / "artifacts/run-002.json"
    out = out if out.is_absolute() else ROOT / out
    if _sha(SOURCE) != SOURCE_SHA256:
        raise ValueError("run-001 source hash mismatch")
    manifest = json.loads((adr / "실험/manifest.json").read_text("utf-8"))
    run = next((item for item in manifest.get("runs") or ()
                if item.get("id") == RUN_ID), None)
    if not run or run.get("status") != "planned":
        raise ValueError("run-002 must be frozen as planned")
    if run.get("runner_sha256") != _sha(Path(__file__).resolve()):
        raise ValueError("run-002 runner hash mismatch")
    source = json.loads(SOURCE.read_text("utf-8"))
    frozen = json.loads(run1.FROZEN.read_text("utf-8"))
    by_case = {case["id"]: case for case in frozen["cases"]}
    rows = [_regrade_row(by_case[row["case_id"]], row)
            for row in source["rows"]]
    payload = {
        "schema_version": "verified-span-coverage-gate-regrade-v1",
        "adr_id": ADR_ID, "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_run": "artifacts/run-001.json",
        "source_sha256": SOURCE_SHA256,
        "runner": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": _sha(Path(__file__).resolve()),
        "model_calls": 0,
        "regrade_scope": "pool-union accounting and dependent append-only audit only",
        "summary": run1._summary(rows, int(source["summary"]["corpus_article_roots"])),
        "rows": rows,
    }
    if out.exists():
        raise FileExistsError(out)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
