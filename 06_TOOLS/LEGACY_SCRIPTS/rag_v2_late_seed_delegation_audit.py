#!/usr/bin/env python3
"""ADR-0093: audit late D seeds that could open an official companion edge."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402


ADR_ID = "ADR-0093"
EXPERIMENT_ID = "ADR-0093-experiment-v1"
RUN_ID = "run-001"
ARMS = ("baseline", "bounded-official-hop-oracle")
STAGES = {
    "baseline": ["frozen-present", "present"],
    "bounded-official-hop-oracle": [
        "frozen-present", "late-seed-identify",
        "official-delegation-expand", "present",
    ],
}
ELIGIBLE_KINDS = frozenset({"시행령", "시행규칙"})


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _coordinates(values: list[dict]) -> list[tuple[str, int]]:
    return [(str(value["doc_id"]), int(value["node"])) for value in values]


def _stage_after(source_row: dict, stage_id: str) -> list[tuple[str, int]]:
    stages = source_row["graded_trace"]["stage_ledger"]["stages"]
    stage = next(value for value in stages if value["stage_id"] == stage_id)
    return _coordinates(stage["after"])


def _public_case(source_row: dict) -> dict:
    """Copy only gold-free stage coordinates into the candidate boundary."""
    return {
        "case_id": str(source_row["case_id"]),
        "number": int(source_row["number"]),
        "suite": str(source_row["suite"]),
        "abc": _stage_after(source_row, "abc-union"),
        "d_selected": _stage_after(source_row, "d-relation-select"),
        "present": _stage_after(source_row, "present"),
    }


def _edge_index(delegation: dict) -> dict[tuple[str, int], list[dict]]:
    outgoing: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for edge_no, edge in enumerate(delegation["edges"]):
        if str(edge.get("kind") or "") not in ELIGIBLE_KINDS:
            continue
        src, dst = edge.get("src") or {}, edge.get("dst") or {}
        if (not src.get("doc_id") or not dst.get("doc_id")
                or src.get("node") is None or dst.get("node") is None):
            continue
        row = {
            "edge_no": edge_no,
            "kind": str(edge.get("kind") or ""),
            "link": str(edge.get("link") or ""),
            "src": {
                "doc_id": str(src["doc_id"]), "node": int(src["node"]),
                "name": str(src.get("name") or ""),
                "article": str(src.get("jo") or ""),
                "anchor": str(src.get("anchor") or ""),
            },
            "dst": {
                "doc_id": str(dst["doc_id"]), "node": int(dst["node"]),
                "name": str(dst.get("name") or ""),
                "article": str(dst.get("jo") or ""),
            },
        }
        outgoing[(row["src"]["doc_id"], row["src"]["node"])].append(row)
    for rows in outgoing.values():
        rows.sort(key=lambda row: (
            0 if row["kind"] == "시행령" else 1,
            row["dst"]["doc_id"], row["dst"]["node"], row["edge_no"],
        ))
    return outgoing


def _edges_for_seeds(
    seeds: list[tuple[str, int]],
    outgoing: dict[tuple[str, int], list[dict]],
) -> list[dict]:
    rows = []
    seen = set()
    for seed_rank, seed in enumerate(seeds, start=1):
        for edge in outgoing.get(seed, ()):  # already deterministic within seed
            coordinate = (edge["dst"]["doc_id"], edge["dst"]["node"])
            key = (seed, coordinate, edge["kind"])
            if key in seen:
                continue
            seen.add(key)
            rows.append({**edge, "seed_rank": seed_rank})
    return rows


def _add_only(
    floor: list[tuple[str, int]],
    additions: list[tuple[str, int]],
    cap: int = 20,
) -> list[tuple[str, int]]:
    result = list(dict.fromkeys(floor))
    seen = set(result)
    for coordinate in additions:
        if coordinate in seen:
            continue
        if len(result) >= cap:
            break
        seen.add(coordinate)
        result.append(coordinate)
    return result


def _execute(public: dict, outgoing: dict, arm: str) -> dict:
    started = time.perf_counter()
    floor = public["present"]
    abc_set = set(public["abc"])
    late_seeds = [row for row in public["d_selected"] if row not in abc_set]
    late_edges = _edges_for_seeds(late_seeds, outgoing)
    raw_additions = list(dict.fromkeys(
        (row["dst"]["doc_id"], row["dst"]["node"]) for row in late_edges
        if (row["dst"]["doc_id"], row["dst"]["node"]) not in set(floor)
    ))

    recorder = ledger.StageLedgerRecorder(
        public["case_id"], arm, ledger.identity_canonicalizer)
    recorder.record_stage("frozen-present", "source", floor)
    if arm == "baseline":
        final = list(floor)
        recorder.record_stage(
            "present", "present", final,
            parent_stage_ids=("frozen-present",))
    else:
        recorder.record_stage(
            "late-seed-identify", "select", floor,
            parent_stage_ids=("frozen-present",))
        raw = _add_only(floor, raw_additions, cap=len(floor) + len(raw_additions))
        recorder.record_stage(
            "official-delegation-expand", "expand", raw,
            parent_stage_ids=("late-seed-identify",))
        final = _add_only(floor, raw_additions, cap=20)
        recorder.record_stage(
            "present", "present", final,
            parent_stage_ids=("official-delegation-expand",),
            discard_reasons={
                coordinate: "final_cap_dropped"
                for coordinate in set(raw) - set(final)
            },
        )
    capture = recorder.capture()
    return {
        "case_id": public["case_id"],
        "number": public["number"],
        "suite": public["suite"],
        "arm_id": arm,
        "capture": capture,
        "candidate_inputs": {
            "abc_coordinate_count": len(public["abc"]),
            "d_selected_coordinate_count": len(public["d_selected"]),
            "present_coordinate_count": len(public["present"]),
            "late_seed_coordinates": [list(value) for value in late_seeds],
        },
        "eligible_edges": late_edges,
        "raw_added_coordinates": [list(value) for value in raw_additions],
        "final_coordinates": [list(value) for value in final],
        "final_added_coordinates": [
            list(value) for value in final if value not in set(floor)
        ],
        "baseline_preserved": all(value in final for value in floor),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "gold_visible_to_candidate": False,
    }


def _median(values: list[int | float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def run(adr: Path) -> None:
    started = time.perf_counter()
    lock_path = adr / "artifacts/input-lock.json"
    lock = json.loads(lock_path.read_text("utf-8"))
    expected_lock = "9b7199b1278b935e73356e1cf33a05d1664a6fdeb7382e88db56f935209734e7"
    if _sha(lock_path) != expected_lock:
        raise ValueError("input lock hash mismatch")
    for source in lock["sources"]:
        if _sha(ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")

    source_run = json.loads((ROOT / lock["sources"][0]["path"]).read_text("utf-8"))
    delegation = json.loads((ROOT / lock["sources"][1]["path"]).read_text("utf-8"))
    outgoing = _edge_index(delegation)

    # Candidate boundary is constructed without gold fields.
    public_cases = [_public_case(row) for row in source_run["rows"]]
    if len(public_cases) != lock["selection"]["case_count"]:
        raise ValueError("case count differs from frozen selection")
    product_rows = [
        _execute(case, outgoing, arm)
        for case in public_cases for arm in ARMS
    ]

    # Only now join current decisive gold and inspect structural opportunities.
    source_by_case = {row["case_id"]: row for row in source_run["rows"]}
    public_by_case = {row["case_id"]: row for row in public_cases}
    graded = []
    case_audits = []
    for case_id, public in public_by_case.items():
        source = source_by_case[case_id]
        gold = [
            (str(row["doc_id"]), int(row["node"]))
            for row in source["gold_results"]
        ]
        observed = set(public["present"])
        missing = [coordinate for coordinate in gold if coordinate not in observed]
        abc_edges = _edges_for_seeds(public["abc"], outgoing)
        abc_targets = {
            (row["dst"]["doc_id"], row["dst"]["node"]) for row in abc_edges
        }
        candidate = next(
            row for row in product_rows
            if row["case_id"] == case_id
            and row["arm_id"] == "bounded-official-hop-oracle"
        )
        late_targets = set(map(tuple, candidate["raw_added_coordinates"]))
        final_targets = set(map(tuple, candidate["final_coordinates"]))
        opportunities = [value for value in missing if value in late_targets]
        final_recovered = [value for value in opportunities if value in final_targets]
        earlier = [value for value in missing if value in abc_targets]
        opportunity_edges = [
            edge for edge in candidate["eligible_edges"]
            if (edge["dst"]["doc_id"], edge["dst"]["node"]) in set(opportunities)
        ]
        case_audits.append({
            "case_id": case_id,
            "number": public["number"],
            "suite": public["suite"],
            "gold_total": len(gold),
            "observed_gold_hits": sum(value in observed for value in gold),
            "observed_missing_gold": [list(value) for value in missing],
            "late_seed_count": len(candidate["candidate_inputs"]["late_seed_coordinates"]),
            "eligible_edge_count": len(candidate["eligible_edges"]),
            "raw_added_count": len(candidate["raw_added_coordinates"]),
            "final_added_count": len(candidate["final_added_coordinates"]),
            "late_seed_boundary_opportunities": [list(value) for value in opportunities],
            "late_seed_boundary_final_recovered": [list(value) for value in final_recovered],
            "earlier_seed_edge_misses": [list(value) for value in earlier],
            "opportunity_edges": opportunity_edges,
        })
        for arm in ARMS:
            row = next(
                value for value in product_rows
                if value["case_id"] == case_id and value["arm_id"] == arm
            )
            grade = ledger.grade_capture(
                row["capture"], gold,
                canonicalizer=ledger.identity_canonicalizer)
            ledger.validate_graded_ledger(
                grade, expected_stage_ids=STAGES[arm])
            row["grade"] = grade
            row["gold_hits"] = grade["stages"][-1]["gold_after"]
            row["gold_total"] = len(gold)
            graded.append(grade)

    run_ledger = ledger.build_run_artifact(RUN_ID, graded, STAGES)
    experiment_ledger = ledger.build_experiment_artifact(
        ADR_ID, EXPERIMENT_ID, [run_ledger])
    ledger_path = adr / "artifacts/retrieval-stage-ledger-run-001.json"
    _write(ledger_path, experiment_ledger)

    opportunities = [
        (row["case_id"], coordinate)
        for row in case_audits
        for coordinate in row["late_seed_boundary_opportunities"]
    ]
    recovered = [
        (row["case_id"], coordinate)
        for row in case_audits
        for coordinate in row["late_seed_boundary_final_recovered"]
    ]
    additional_cases = sorted({
        case_id for case_id, _ in opportunities if case_id != "fsc-hard-006"
    })
    baseline_rows = [row for row in product_rows if row["arm_id"] == "baseline"]
    candidate_rows = [
        row for row in product_rows
        if row["arm_id"] == "bounded-official-hop-oracle"
    ]
    raw_added_total = sum(len(row["raw_added_coordinates"]) for row in candidate_rows)
    final_added_total = sum(len(row["final_added_coordinates"]) for row in candidate_rows)
    opportunity_count = len(opportunities)
    final_recovered_count = len(recovered)
    total_elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    corpus_total = int(source_run["summary"]["corpus_article_roots"])

    summary = {
        "cases_audited": len(case_audits),
        "gold_audited": sum(row["gold_total"] for row in case_audits),
        "observed_gold_hits": sum(row["gold_hits"] for row in baseline_rows),
        "observed_missing_gold": sum(
            len(row["observed_missing_gold"]) for row in case_audits),
        "late_seed_boundary_opportunity_coordinates": opportunity_count,
        "late_seed_boundary_opportunity_cases": len({row[0] for row in opportunities}),
        "additional_cases_excluding_fsc_hard_006": additional_cases,
        "additional_case_count_excluding_fsc_hard_006": len(additional_cases),
        "late_seed_boundary_final_recovered": final_recovered_count,
        "reachable_final_recall": (
            final_recovered_count / opportunity_count if opportunity_count else 0.0
        ),
        "earlier_seed_edge_miss_coordinates": sum(
            len(row["earlier_seed_edge_misses"]) for row in case_audits),
        "raw_added_total": raw_added_total,
        "final_added_total": final_added_total,
        "raw_added_non_opportunity": raw_added_total - opportunity_count,
        "final_added_non_opportunity": final_added_total - final_recovered_count,
        "raw_opportunity_precision": (
            opportunity_count / raw_added_total if raw_added_total else 0.0
        ),
        "final_opportunity_precision": (
            final_recovered_count / final_added_total if final_added_total else 0.0
        ),
        "added_per_case_median": _median([
            len(row["final_added_coordinates"]) for row in candidate_rows
        ]),
        "added_per_affected_case_median": _median([
            len(row["final_added_coordinates"]) for row in candidate_rows
            if row["final_added_coordinates"]
        ]),
        "baseline_coordinates_lost": sum(not row["baseline_preserved"] for row in candidate_rows),
        "candidate_gold_hits": sum(row["gold_hits"] for row in candidate_rows),
        "candidate_golden_recall": (
            sum(row["gold_hits"] for row in candidate_rows)
            / sum(row["gold_total"] for row in candidate_rows)
        ),
        "presented_total": sum(len(row["final_coordinates"]) for row in candidate_rows),
        "presented_mean": statistics.mean(
            len(row["final_coordinates"]) for row in candidate_rows),
        "presented_p50": statistics.median(
            len(row["final_coordinates"]) for row in candidate_rows),
        "presented_p95": sorted(
            len(row["final_coordinates"]) for row in candidate_rows)[57],
        "selectivity": statistics.mean(
            len(row["final_coordinates"]) for row in candidate_rows) / corpus_total,
        "cap_20_passed": all(len(row["final_coordinates"]) <= 20 for row in candidate_rows),
        "candidate_gold_visible": False,
        "llm_calls": 0,
        "wall_ms": total_elapsed_ms,
    }
    paired = {"candidate_only": 0, "baseline_only": 0, "both": 0, "neither": 0}
    for case in case_audits:
        source_gold = [
            (str(row["doc_id"]), int(row["node"]))
            for row in source_by_case[case["case_id"]]["gold_results"]
        ]
        base = set(public_by_case[case["case_id"]]["present"])
        candidate = set(map(tuple, next(
            row for row in candidate_rows if row["case_id"] == case["case_id"]
        )["final_coordinates"]))
        for coordinate in source_gold:
            b, c = coordinate in base, coordinate in candidate
            key = "both" if b and c else "baseline_only" if b else (
                "candidate_only" if c else "neither")
            paired[key] += 1

    run_value = {
        "schema_version": "adr-0093-run-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input_lock_sha256": expected_lock,
        "gold_visible_to_candidate": False,
        "computed_post_selection": True,
        "corpus_article_roots": corpus_total,
        "eligible_edge_kinds": sorted(ELIGIBLE_KINDS),
        "summary": summary,
        "paired": paired,
        "case_audits": case_audits,
        "rows": product_rows,
        "stage_ledger": {
            "path": str(ledger_path.relative_to(ROOT)),
            "sha256": _sha(ledger_path),
        },
    }
    run_path = adr / "artifacts/run-001.json"
    _write(run_path, run_value)
    print(json.dumps({
        "run": str(run_path), "summary": summary, "paired": paired,
    }, ensure_ascii=False, indent=2))


def main() -> None:
    adr = ROOT / "docs/adr/ADR-0093-v2-late-seed-delegation-boundary-audit"
    run(adr)


if __name__ == "__main__":
    main()
