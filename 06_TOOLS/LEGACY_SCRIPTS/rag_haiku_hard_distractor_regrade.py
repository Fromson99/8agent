#!/usr/bin/env python3
"""hard-distractor 실험의 핵심 조건과 전환 답변을 Haiku 3표결 재감사한다."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
from pathlib import Path
import sys
import threading


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.rag.experiments.haiku_hard_distractors import (  # noqa: E402
    HAIKU_MODEL, VARIANTS,
)
from scripts import review_golden as review  # noqa: E402
from scripts.rag_haiku_legal_methods_eval import _grade  # noqa: E402


def _dump(ex) -> dict:
    row = ex.dump()
    row["parsed"] = ex.parsed
    return row


def _summary(rows: list[dict]) -> dict:
    good = [row for row in rows if not row.get("error")]
    out = {"runs": {}, "graded_answers": 0}
    for row in good:
        run_name = row["run_name"]
        out["runs"].setdefault(run_name, {"cases": 0, "gold_correct": 0,
                                                "full_correct": 0,
                                                "gold_correct_full_wrong": 0,
                                                "gold_wrong_full_correct": 0})
        summary = out["runs"][run_name]
        summary["cases"] += 1
        gold = bool(row["grades"]["gold_only"]["correct"])
        full = bool(row["grades"]["full_original"]["correct"])
        summary["gold_correct"] += int(gold)
        summary["full_correct"] += int(full)
        summary["gold_correct_full_wrong"] += int(gold and not full)
        summary["gold_wrong_full_correct"] += int(not gold and full)
        out["graded_answers"] += len(row["grades"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()

    cases = {str(row["id"]): row for row in
             json.loads(args.suite.read_text("utf-8")).get("cases") or []}
    sources = []
    for path in args.run:
        blob = json.loads(path.read_text("utf-8"))
        for row in blob.get("rows") or []:
            if not row.get("error"):
                sources.append((path.stem, row))
    local = threading.local()

    def evaluate(item):
        run_name, source = item
        if not hasattr(local, "llm"):
            local.llm = review._llm()
            if local.llm.backend == "anthropic":
                local.llm.model = HAIKU_MODEL
        llm = local.llm
        case_id = str(source["case_no"])
        original_gold = bool(source["variants"]["gold_only"]["grade"]["correct"])
        selected = ["gold_only", "full_original"]
        selected += [variant for variant in VARIANTS[1:-1]
                     if bool(source["variants"][variant]["grade"]["correct"])
                     != original_gold]
        selected = list(dict.fromkeys(selected))
        grades = {}
        cache = {}
        for variant in selected:
            value = source["variants"][variant]
            answer = str(value["output"].get("answer") or "")
            cache_key = answer
            if cache_key not in cache:
                log0 = len(llm.log)
                correct, grade, votes, usage = _grade(
                    llm, cases[case_id], answer, 3, value["evidence"])
                exchanges = [_dump(ex) for ex in list(llm.log)[log0:]]
                cache[cache_key] = {
                    "correct": bool(correct), "grade": grade,
                    "votes": votes, "usage": usage,
                    "raw_exchanges": exchanges,
                }
            grades[variant] = cache[cache_key]
        return {
            "run_name": run_name, "case_no": case_id,
            "question": source["question"],
            "reference_answer": source["reference_answer"],
            "original_grades": {variant: bool(source["variants"][variant]["grade"]["correct"])
                                for variant in selected},
            "answers": {variant: source["variants"][variant]["output"]
                        for variant in selected},
            "grades": grades,
        }

    rows = []
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, item): item for item in sources}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            run_name, source = futures[future]
            case_id = str(source["case_no"])
            try:
                row = future.result()
            except Exception as exc:
                row = {"run_name": run_name, "case_no": case_id,
                       "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            rows.sort(key=lambda value: (value["run_name"], value["case_no"]))
            blob = {
                "experiment": "haiku-hard-distractor-core-and-switch-regrade3-v1",
                "contract": {
                    "answers_frozen": True, "all_models": HAIKU_MODEL,
                    "grade_repeats": 3, "main_wiring_changed": False,
                    "prompts_and_raw_responses_preserved": True,
                },
                "source_runs": [str(path) for path in args.run],
                "summary": _summary(rows), "rows": rows,
            }
            args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
            if row.get("error"):
                print(f"[{position:02d}/{len(sources)}] {run_name}/{case_id} ERROR "
                      f"{row['error']}", flush=True)
            else:
                marks = " ".join(f"{name}={'○' if value['correct'] else '✗'}"
                                 for name, value in row["grades"].items())
                print(f"[{position:02d}/{len(sources)}] {run_name}/{case_id} {marks}",
                      flush=True)
    print(json.dumps(_summary(rows), ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
