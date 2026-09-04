#!/usr/bin/env python3
"""ADR-0101 parent-vs-hardened Legal Graph closure replay.

The baseline is ADR-0099's sealed graph-closure output.  Candidate execution
receives only the question and ADR-0091 frozen floor coordinates.
Decisive and required-companion gold are joined only after every capture has
been sealed.  No product or judge model is called.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time


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
    ("LEGAL_GRAPH_STORE", "data/legal_graph"),
):
    os.environ.setdefault(key, str(ROOT / relative))

from lawrag.core.rag import legal_graph_closure, legal_graph_store  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402


ADR_ID = "ADR-0101"
EXPERIMENT_ID = "ADR-0101-experiment-v1"
RUN_ID = "run-001"
ARMS = ("baseline", "hardened-graph-closure")
STAGES = {
    "baseline": ["parent-graph-present", "present"],
    "hardened-graph-closure": [
        "frozen-present", "query-family-gate",
        "legal-graph-closure-expand", "closure-evidence-filter",
        "final-cap-select", "reachability-present-merge", "present",
    ],
}
EXPECTED = {
    "source_lock": "7636cc52ac0bd94a10baa1d75f3f381940981ff86beafa7f7ee91fedf9308452",
    "source_run": "bcfd5a45054d563d8ef8d00522278f860b6ae24b9e12c901578d45fb2b4d7b97",
    "source_ledger": "bf2d6a65d8e1de25b1f38a788b42dd8c95cea29c0a52c0795fc581cfdd92cd49",
    "parent_run": "e43b5120996207a3a9224c545af038e2fcb5dd7ccf3fa67ff006208f6a63a648",
    "cm": "d3c707caa114dec379201c2ba9d2177b0c6bc17ceb4ae9394df1397e9dbfccb1",
    "fsc": "981d4fa6fd4b77d70eeade73aa907243937dfe33b228826c71eadf438b813269",
    "graph_current": "87925cf693fa194e16033f1c678564350e06e5b33d8468777ae7c3b803308afa",
    "graph_manifest": "9ca7fed5e964adc61958064904be4f95dbc3f0cd324d5e4256e3f1e38c5aa7d2",
}
SOURCES = {
    "source_lock": ROOT / "docs/adr/ADR-0091-legalclosure-v2-article-reachability-ledger/artifacts/input-lock.json",
    "source_run": ROOT / "docs/adr/ADR-0091-legalclosure-v2-article-reachability-ledger/artifacts/run-002.json",
    "source_ledger": ROOT / "docs/adr/ADR-0091-legalclosure-v2-article-reachability-ledger/artifacts/retrieval-stage-ledger-run-002.json",
    "parent_run": ROOT / "docs/adr/ADR-0099-legal-graph-query-family-search-wiring/artifacts/run-001.json",
    "cm": ROOT / "data/review/cm_core_e2e_v2.json",
    "fsc": ROOT / "data/review/fsc_hard_retrieval_v2.json",
    "graph_current": ROOT / "data/legal_graph/CURRENT.json",
    "graph_manifest": ROOT / "data/legal_graph/generations/lgv1-a6c070b4bbd0411d193fb3ef/manifest.json",
}
IMPLEMENTATION_PATHS = (
    "lawrag/core/rag/legal_graph_store.py",
    "lawrag/core/rag/legal_graph_closure.py",
    "lawrag/core/rag/legalclosure_runtime.py",
    "lawrag/core/rag/switches.py",
    "scripts/rag_legal_graph_runtime_hardening_eval.py",
    "tests/rag/test_legal_graph_store_hardening.py",
    "tests/rag/test_legal_graph_closure_hardening.py",
    "tests/rag/test_legal_graph_search_wiring.py",
    "tests/rag/test_switches.py",
)


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


def _coordinates(values) -> list[tuple[str, int]]:
    return [(str(value["doc_id"]), int(value["node"])) for value in values]


def _stage_after(source_row: dict, stage_id: str) -> list[tuple[str, int]]:
    stages = source_row["graded_trace"]["stage_ledger"]["stages"]
    stage = next(value for value in stages if value["stage_id"] == stage_id)
    return _coordinates(stage["after"])


def _public_cases(
    source_run: dict,
    source_lock: dict,
    parent_run: dict,
) -> list[dict]:
    questions = {
        str(row["id"]): {
            "case_id": str(row["id"]),
            "number": int(row["number"]),
            "suite": str(row["suite"]),
            "question": str(row["question"]),
        }
        for row in source_lock["cases"]
    }
    parent_by_case = {
        str(row["case_id"]): [
            (str(value[0]), int(value[1])) for value in row["final_coordinates"]
        ]
        for row in parent_run["rows"]
        if row["arm_id"] == "graph-closure"
    }
    out = []
    for row in source_run["rows"]:
        public = dict(questions[str(row["case_id"])])
        public["floor"] = _stage_after(row, "present")
        public["parent_present"] = parent_by_case[public["case_id"]]
        out.append(public)
    return out


def _execute(public: dict, arm: str, index, snapshot) -> dict:
    started = time.perf_counter()
    floor = list(dict.fromkeys(public["floor"]))
    parent_present = list(dict.fromkeys(public["parent_present"]))
    recorder = ledger.StageLedgerRecorder(
        public["case_id"], arm, ledger.identity_canonicalizer
    )
    if arm == "baseline":
        final = parent_present
        graph_meta = {
            "enabled": True, "status": "parent-baseline", "added_count": 0,
            "gold_visible_to_candidate": False,
        }
        recorder.record_stage("parent-graph-present", "source", final)
        recorder.record_stage(
            "present", "present", final,
            parent_stage_ids=("parent-graph-present",),
        )
    else:
        recorder.record_stage("frozen-present", "source", floor)
        additions, graph_meta = legal_graph_closure.plan_coordinates(
            index,
            public["question"],
            floor,
            snapshot=snapshot,
            cap=20,
        )
        final = list(floor)
        for row in additions:
            coordinate = (str(row["coordinate"][0]), int(row["coordinate"][1]))
            if coordinate not in final:
                final.append(coordinate)
        recorder.record_stage(
            "query-family-gate", "select", floor,
            parent_stage_ids=("frozen-present",),
        )
        recorder.record_stage(
            "legal-graph-closure-expand", "expand", final,
            parent_stage_ids=("query-family-gate",),
        )
        recorder.record_stage(
            "closure-evidence-filter", "filter", final,
            parent_stage_ids=("legal-graph-closure-expand",),
        )
        recorder.record_stage(
            "final-cap-select", "select", final,
            parent_stage_ids=("closure-evidence-filter",),
        )
        recorder.record_stage(
            "reachability-present-merge", "union", final,
            parent_stage_ids=("final-cap-select",),
        )
        recorder.record_stage(
            "present", "present", final,
            parent_stage_ids=("reachability-present-merge",),
        )
    capture = recorder.capture()
    return {
        "case_id": public["case_id"],
        "number": public["number"],
        "suite": public["suite"],
        "arm_id": arm,
        "capture": capture,
        "final_coordinates": [list(value) for value in final],
        "final_added_coordinates": [
            list(value) for value in final if value not in set(floor)
        ],
        "baseline_preserved": all(value in final for value in floor),
        "parent_preserved": all(value in final for value in parent_present),
        "parent_coordinates_lost": [
            list(value) for value in parent_present if value not in set(final)
        ],
        "graph": graph_meta,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "gold_visible_to_candidate": False,
    }


def _percentile(values: list[int | float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    position = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[position]


def _companion_gold(cm: dict) -> dict[str, list[tuple[str, int]]]:
    return {
        str(row["id"]): [
            (str(item["doc_id"]), int(item["node"]))
            for item in row.get("required_companions") or ()
            if item.get("corpus_status") == "present"
        ]
        for row in cm["cases"]
    }


def run(adr: Path) -> dict:
    started = time.perf_counter()
    for key, path in SOURCES.items():
        actual = _sha(path)
        if actual != EXPECTED[key]:
            raise ValueError(f"frozen source hash mismatch: {key} {actual}")
    input_lock = json.loads((adr / "artifacts/input-lock.json").read_text("utf-8"))
    for row in input_lock["sources"]:
        path = ROOT / row["path"]
        if _sha(path) != row["sha256"]:
            raise ValueError(f"ADR-0101 input lock mismatch: {row['path']}")
    implementation_lock_path = adr / "artifacts/implementation-lock.json"
    implementation_lock = json.loads(implementation_lock_path.read_text("utf-8"))
    for row in implementation_lock["sources"]:
        path = ROOT / row["path"]
        if _sha(path) != row["sha256"]:
            raise ValueError(f"ADR-0101 implementation lock mismatch: {row['path']}")

    source_run = json.loads(SOURCES["source_run"].read_text("utf-8"))
    source_lock = json.loads(SOURCES["source_lock"].read_text("utf-8"))
    parent_run = json.loads(SOURCES["parent_run"].read_text("utf-8"))
    public_cases = _public_cases(source_run, source_lock, parent_run)
    if (
        len(public_cases) != 61
        or sum(len(row["floor"]) for row in public_cases) != 1000
        or sum(len(row["parent_present"]) for row in public_cases) != 1017
    ):
        raise ValueError("frozen 61-case present selection changed")

    index = index_mod.Index.load()
    legal_graph_store.reset_cache()
    load = legal_graph_store.current_for(index)
    if load.snapshot is None:
        raise ValueError(f"Legal Graph snapshot unavailable: {load.as_dict()}")
    snapshot = load.snapshot
    product_rows = [
        _execute(case, arm, index, snapshot)
        for case in public_cases for arm in ARMS
    ]

    # Candidate execution is now complete.  Join decisive and companion gold.
    gold_by_case = {
        str(row["id"]): [
            (str(item["doc_id"]), int(item["node"]))
            for item in row["gold_articles"]
            if item.get("corpus_status") == "present"
        ]
        for row in source_lock["cases"]
    }
    cm = json.loads(SOURCES["cm"].read_text("utf-8"))
    companions_by_case = _companion_gold(cm)
    graded = []
    for row in product_rows:
        gold = gold_by_case[row["case_id"]]
        grade = ledger.grade_capture(
            row["capture"], gold,
            canonicalizer=ledger.identity_canonicalizer,
        )
        ledger.validate_graded_ledger(
            grade, expected_stage_ids=STAGES[row["arm_id"]]
        )
        row["grade"] = grade
        row["gold_hits"] = grade["stages"][-1]["gold_after"]
        row["gold_total"] = len(gold)
        final = {tuple(value) for value in row["final_coordinates"]}
        companion_gold = companions_by_case.get(row["case_id"], [])
        row["companion_hits"] = sum(value in final for value in companion_gold)
        row["companion_total"] = len(companion_gold)
        graded.append(grade)

    run_ledger = ledger.build_run_artifact(RUN_ID, graded, STAGES)
    experiment_ledger = ledger.build_experiment_artifact(
        ADR_ID, EXPERIMENT_ID, [run_ledger]
    )
    ledger_path = adr / "artifacts/retrieval-stage-ledger-run-001.json"
    _write(ledger_path, experiment_ledger)

    by_arm_rows = {
        arm: [row for row in product_rows if row["arm_id"] == arm]
        for arm in ARMS
    }
    by_arm = {}
    for arm, rows in by_arm_rows.items():
        presented = [len(row["final_coordinates"]) for row in rows]
        additions = [len(row["final_added_coordinates"]) for row in rows]
        latencies = [row["elapsed_ms"] for row in rows]
        by_arm[arm] = {
            "cases": len(rows),
            "gold_hits": sum(row["gold_hits"] for row in rows),
            "gold_total": sum(row["gold_total"] for row in rows),
            "golden_recall": (
                sum(row["gold_hits"] for row in rows)
                / sum(row["gold_total"] for row in rows)
            ),
            "all_gold_cases": sum(
                row["gold_hits"] == row["gold_total"] for row in rows
            ),
            "companion_hits": sum(row["companion_hits"] for row in rows),
            "companion_total": sum(row["companion_total"] for row in rows),
            "presented_total": sum(presented),
            "presented_mean": statistics.mean(presented),
            "presented_p50": statistics.median(presented),
            "presented_p95": _percentile(presented, 0.95),
            "added_total": sum(additions),
            "added_mean": statistics.mean(additions),
            "added_p50": statistics.median(additions),
            "added_p95": _percentile(additions, 0.95),
            "added_max": max(additions),
            "latency_p50_ms": statistics.median(latencies),
            "latency_p95_ms": _percentile(latencies, 0.95),
            "selectivity": statistics.mean(presented) / 16506,
            "baseline_coordinates_lost": (
                0 if arm == "baseline" else sum(
                    len(row["parent_coordinates_lost"]) for row in rows
                )
            ),
            "floor_coordinates_lost": sum(
                0 if row["baseline_preserved"] else 1 for row in rows
            ),
            "cap_20_passed": all(value <= 20 for value in presented),
        }

    paired = {"candidate_only": 0, "baseline_only": 0, "both": 0, "neither": 0}
    base_by_case = {row["case_id"]: row for row in by_arm_rows["baseline"]}
    candidate_by_case = {
        row["case_id"]: row
        for row in by_arm_rows["hardened-graph-closure"]
    }
    for case_id, gold in gold_by_case.items():
        base = {tuple(value) for value in base_by_case[case_id]["final_coordinates"]}
        candidate = {
            tuple(value) for value in candidate_by_case[case_id]["final_coordinates"]
        }
        for coordinate in gold:
            baseline_hit, candidate_hit = coordinate in base, coordinate in candidate
            key = (
                "both" if baseline_hit and candidate_hit
                else "baseline_only" if baseline_hit
                else "candidate_only" if candidate_hit
                else "neither"
            )
            paired[key] += 1

    public_by_case = {row["case_id"]: row for row in public_cases}
    floor_candidate_only = 0
    for case_id, gold in gold_by_case.items():
        floor = set(public_by_case[case_id]["floor"])
        candidate = {
            tuple(value) for value in candidate_by_case[case_id]["final_coordinates"]
        }
        floor_candidate_only += sum(
            coordinate not in floor and coordinate in candidate for coordinate in gold
        )

    graph_rows = by_arm_rows["hardened-graph-closure"]
    additions_total = by_arm["hardened-graph-closure"]["added_total"]
    reason_counts = Counter()
    predicate_considered = Counter()
    predicate_activated = Counter()
    active_cases = 0
    for row in graph_rows:
        graph = row["graph"]
        reason_counts.update(graph.get("reason_counts") or {})
        if graph.get("active_family_ids"):
            active_cases += 1
        for decision in graph.get("decisions") or ():
            predicate_considered[str(decision.get("predicate") or "")] += 1
            if decision.get("activated"):
                predicate_activated[str(decision.get("predicate") or "")] += 1
    fsc_law_decree = {
        case_id: candidate_by_case[case_id]["final_coordinates"]
        for case_id in (
            "fsc-hard-003", "fsc-hard-005", "fsc-hard-006",
            "fsc-hard-008", "fsc-hard-009",
        )
    }
    target = ("33b5315a0bc2d899", 28)
    fsc_006_recovered = target in {
        tuple(value) for value in fsc_law_decree["fsc-hard-006"]
    }
    success_checks = {
        "cases_61_gold_90": (
            by_arm["hardened-graph-closure"]["cases"] == 61
            and by_arm["hardened-graph-closure"]["gold_total"] == 90
        ),
        "decisive_at_least_72": (
            by_arm["hardened-graph-closure"]["gold_hits"] >= 72
        ),
        "fsc_hard_006_decree_4": fsc_006_recovered,
        "parent_loss_zero": (
            by_arm["hardened-graph-closure"]["baseline_coordinates_lost"] == 0
        ),
        "floor_loss_zero": (
            by_arm["hardened-graph-closure"]["floor_coordinates_lost"] == 0
        ),
        "companion_at_least_12": (
            by_arm["hardened-graph-closure"]["companion_hits"] >= 12
        ),
        "additions_at_most_30": additions_total <= 30,
        "addition_p95_at_most_2": (
            by_arm["hardened-graph-closure"]["added_p95"] <= 2
        ),
        "addition_max_at_most_6": (
            by_arm["hardened-graph-closure"]["added_max"] <= 6
        ),
        "addition_precision_above_naive": (
            floor_candidate_only / additions_total > 0.0238095
            if additions_total else False
        ),
        "cap_20": by_arm["hardened-graph-closure"]["cap_20_passed"],
        "warm_p95_at_most_25ms": (
            by_arm["hardened-graph-closure"]["latency_p95_ms"] <= 25
        ),
        "cold_load_at_most_10s": snapshot.load_ms <= 10_000,
        "llm_zero": True,
        "gold_hidden": True,
    }
    summary = {
        "corpus_article_roots": 16506,
        "graph_cards": len(snapshot.ports_by_article),
        "graph_edges": len(snapshot.edge_by_projection_id),
        "graph_generation": snapshot.generation_id,
        "graph_content_sha256": snapshot.content_sha256,
        "cold_load_ms": snapshot.load_ms,
        "by_arm": by_arm,
        "paired": paired,
        "floor_candidate_only": floor_candidate_only,
        "floor_candidate_only_addition_precision": (
            floor_candidate_only / additions_total if additions_total else 0.0
        ),
        "active_cases": active_cases,
        "reason_counts": dict(sorted(reason_counts.items())),
        "predicate_considered_visible_trace": dict(sorted(predicate_considered.items())),
        "predicate_activated": dict(sorted(predicate_activated.items())),
        "fsc_law_and_decree_final": fsc_law_decree,
        "fsc_hard_006_decree_4_recovered": fsc_006_recovered,
        "success_checks": success_checks,
        "passed": all(success_checks.values()),
        "llm_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "wall_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    run_value = {
        "schema_version": "adr-0101-run-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input_lock_sha256": _sha(adr / "artifacts/input-lock.json"),
        "implementation_lock_sha256": _sha(implementation_lock_path),
        "computed_post_selection": True,
        "gold_visible_to_candidate": False,
        "product_calls": 0,
        "judge_calls": 0,
        "implementation_sha256": {
            relative: _sha(ROOT / relative) for relative in IMPLEMENTATION_PATHS
        },
        "load": load.as_dict(),
        "summary": summary,
        "rows": product_rows,
        "stage_ledger": {
            "path": str(ledger_path.relative_to(ROOT)),
            "sha256": _sha(ledger_path),
        },
    }
    run_path = adr / "artifacts/run-001.json"
    _write(run_path, run_value)
    return {"run": str(run_path), "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--adr",
        type=Path,
        default=ROOT / "docs/adr/ADR-0101-legal-graph-runtime-consumer-hardening",
    )
    args = parser.parse_args()
    result = run(args.adr.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
