#!/usr/bin/env python3
"""ADR-0091 run-002: deterministic correction of channel attribution only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import article_reachability  # noqa: E402
from lawrag.core.rag.experiments import retrieval_stage_ledger  # noqa: E402
from scripts import rag_legalclosure_article_reachability_golden_61 as runner  # noqa: E402


RUN_ID = "run-002"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adr", type=Path, required=True)
    args = parser.parse_args()
    adr = args.adr if args.adr.is_absolute() else ROOT / args.adr
    source_path = adr / "artifacts/run-001.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    frozen = json.loads((adr / "artifacts/input-lock.json").read_text(
        encoding="utf-8"))
    cases = {row["id"]: row for row in frozen["cases"]}
    manifest = json.loads((adr / "실험/manifest.json").read_text(
        encoding="utf-8"))

    rows = source["rows"]
    for row in rows:
        case = cases[row["case_id"]]
        row["graded_trace"] = article_reachability.grade_capture(
            row["product_capture"],
            [(gold["doc_id"], gold["node"])
             for gold in case["gold_articles"]])

    corpus_total = int(source["summary"]["corpus_article_roots"])
    summary = runner._summary(rows, corpus_total)
    declared = [stage["stage_id"] for stage in manifest["design"]
                ["retrieval_stage_plan"]["stages_by_arm"][runner.ARM_ID]]
    run_ledger = retrieval_stage_ledger.build_run_artifact(
        RUN_ID, [row["graded_trace"]["stage_ledger"] for row in rows],
        {runner.ARM_ID: declared})
    experiment_ledger = retrieval_stage_ledger.build_experiment_artifact(
        runner.ADR_ID, runner.EXPERIMENT_ID, [run_ledger])
    ledger_path = adr / "artifacts/retrieval-stage-ledger-run-002.json"
    runner._write(ledger_path, experiment_ledger)

    minimal_rows = [{
        "number": row["number"],
        "case_id": row["case_id"],
        "suite": row["suite"],
        "selected_count": row["selected_count"],
        "gold_results": row["gold_results"],
        "case_all_gold_hit": row["case_all_gold_hit"],
        "wall_ms": row["wall_ms"],
        "trace_elapsed_ms": row["trace_elapsed_ms"],
        "provider_usage": row["provider_usage"],
        "product_capture_sha256": row["product_capture"]["capture_sha256"],
        "graded_trace": row["graded_trace"],
    } for row in rows]
    output = {
        "schema_version": "legalclosure-v2-reachability-regrade-v1",
        "adr_id": runner.ADR_ID,
        "experiment_id": runner.EXPERIMENT_ID,
        "run_id": RUN_ID,
        "created_at": runner._now(),
        "purpose": "correct D/reference selected attribution base; no product rerun",
        "source_run": str(source_path.relative_to(ROOT)),
        "source_run_sha256": runner._sha(source_path),
        "product_calls": 0,
        "judge_calls": 0,
        "summary": summary,
        "stage_ledger": {
            "path": str(ledger_path.relative_to(ROOT)),
            "sha256": runner._sha(ledger_path),
            "artifact_sha256": experiment_ledger["artifact_sha256"],
        },
        "rows": minimal_rows,
    }
    out = adr / "artifacts/run-002.json"
    runner._write(out, output)
    runner._write(adr / "artifacts/channel-metrics-run-002.json",
                  summary["channels"])
    runner._write(adr / "artifacts/failure-metrics-run-002.json", {
        "gold_fates": summary["gold_fates"],
        "event_reason_counts": summary["event_reason_counts"],
    })
    (adr / "artifacts/reachability-report-run-002.md").write_text(
        runner._report_markdown(summary), encoding="utf-8")

    ledger_relative = str(ledger_path.relative_to(ROOT))
    for row in rows:
        case = cases[row["case_id"]]
        question = adr / "실험" / (
            f"질문-{case['number']:03d}-{case['id']}.md")
        prefix = (
            "> run-001의 제품 capture는 유효하지만 D selected attribution의 "
            "차집합 기준이 잘못돼 집계가 invalid였다. 아래 판정은 제품 재호출 없이 "
            "같은 capture를 run-002에서 재채점한 정정본이다.\n\n")
        question.write_text(
            prefix + runner._question_markdown(case, row, ledger_relative)
            .replace("`run-001` / `traced-v2`", "`run-002` / `traced-v2`"),
            encoding="utf-8")
    print(json.dumps({
        "run": RUN_ID,
        "path": str(out.relative_to(ROOT)),
        "sha256": runner._sha(out),
        "ledger": str(ledger_path.relative_to(ROOT)),
        "ledger_sha256": runner._sha(ledger_path),
        "summary": summary,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

