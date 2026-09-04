#!/usr/bin/env python3
"""Build ADR-0149 retrieval stage accounting from frozen run-002 coordinates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger


def capture(arm: str, stages: list[tuple[str, str, tuple[str, ...], list[tuple[str, int]]]],
            *, case_id: str = "cm003", gold=()):
    recorder = ledger.StageLedgerRecorder(case_id, arm, ledger.identity_canonicalizer)
    for stage_id, kind, parents, after in stages:
        recorder.record_stage(stage_id, kind, after, parent_stage_ids=parents)
    return ledger.grade_capture(recorder.capture(), gold or (
        [("3521c3aaa5a735fd", 282), ("eae25aa6e8a83c58", 202)]
        if case_id == "cm003" else []))


def _empty_case(arm: str, declarations: list[str]):
    kinds = {
        "source": "source", "article-relations": "retrieve",
        "proviso-parse": "expand", "physical-route": "expand",
        "legal-effect": "select", "scoped-block-select": "select",
        "present": "present",
    }
    stages = []
    for index, stage_id in enumerate(declarations):
        parents = () if index == 0 else (declarations[index - 1],)
        stages.append((stage_id, kinds[stage_id], parents, []))
    return capture(arm, stages, case_id="proviso-structural-holdout", gold=[])


def _candidate_case(*, include_detail: bool):
    source = ("3521c3aaa5a735fd", 282)
    after = [source, ("eae25aa6e8a83c58", 202)] if include_detail else [source]
    return capture("proviso-runtime-data", [
        ("source", "source", (), []),
        ("proviso-parse", "expand", ("source",), [source]),
        ("physical-route", "expand", ("proviso-parse",), [source]),
        ("legal-effect", "select", ("physical-route",), [source]),
        ("scoped-block-select", "select", ("legal-effect",), after),
        ("present", "present", ("scoped-block-select",), after),
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = ("3521c3aaa5a735fd", 282)
    old_routes = [source, ("3521c3aaa5a735fd", 349), ("7687ac5d901e9a4a", 95)]
    detail = ("eae25aa6e8a83c58", 202)
    baseline = capture("baseline", [
        ("source", "source", (), []),
        ("article-relations", "retrieve", ("source",), old_routes),
        ("present", "present", ("article-relations",), old_routes),
    ])
    declarations = {
        "baseline": ["source", "article-relations", "present"],
        "proviso-runtime-data": ["source", "proviso-parse", "physical-route",
                                 "legal-effect", "scoped-block-select", "present"],
    }
    run1 = ledger.build_run_artifact("run-001", [
        baseline, _empty_case("baseline", declarations["baseline"]),
        _candidate_case(include_detail=False),
        _empty_case("proviso-runtime-data", declarations["proviso-runtime-data"]),
    ], declarations)
    run2 = ledger.build_run_artifact("run-002", [
        baseline, _empty_case("baseline", declarations["baseline"]),
        _candidate_case(include_detail=True),
        _empty_case("proviso-runtime-data", declarations["proviso-runtime-data"]),
    ], declarations)
    run3_declarations = {
        "proviso-runtime-data": declarations["proviso-runtime-data"]}
    run3 = ledger.build_run_artifact(
        "run-003", [_candidate_case(include_detail=True),
                    _empty_case("proviso-runtime-data",
                                declarations["proviso-runtime-data"])], {
            "proviso-runtime-data": declarations["proviso-runtime-data"]})
    artifact = ledger.build_experiment_artifact(
        "ADR-0149", "ADR-0149-experiment-v1", [run1, run2, run3])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
