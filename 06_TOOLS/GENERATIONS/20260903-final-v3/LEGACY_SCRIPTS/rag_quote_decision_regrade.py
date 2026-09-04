#!/usr/bin/env python3
"""동결 baseline/raw/guarded quote-decision 답변을 Haiku 3표결한다."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments.haiku_quote_decision import HAIKU_MODEL  # noqa: E402
from scripts import review_golden as review  # noqa: E402
from scripts.rag_haiku_legal_methods_eval import _grade  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import reconstruct_evidence  # noqa: E402


VARIANTS = ("baseline", "raw_candidate", "guarded")


def summarize(rows: list[dict]) -> dict:
    good = [row for row in rows if not row.get("error")]
    out = {variant: {
        "cases": len(good),
        "correct": sum(bool((row.get("grades") or {}).get(variant, {}).get("correct"))
                       for row in good),
    } for variant in VARIANTS}
    for variant in VARIANTS:
        out[variant]["accuracy"] = round(out[variant]["correct"] / len(good), 4) \
            if good else 0
    for variant in ("raw_candidate", "guarded"):
        paired = Counter((bool(row["grades"]["baseline"]["correct"]),
                          bool(row["grades"][variant]["correct"])) for row in good)
        out[variant]["versus_baseline"] = {
            "both_correct": paired[(True, True)],
            "baseline_only_correct": paired[(True, False)],
            "candidate_only_correct": paired[(False, True)],
            "both_incorrect": paired[(False, False)],
            "delta": out[variant]["correct"] - out["baseline"]["correct"],
        }
    out["errors"] = [row.get("error") for row in rows if row.get("error")]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text("utf-8"))
    run = json.loads(args.run.read_text("utf-8"))
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    cases = {str(row["id"]): row for row in suite.get("cases") or []}
    selected = {str(row["case_no"]):
        (((row.get("variants") or {}).get(args.variant) or {}).get("selected") or [])
        for row in retrieval.get("rows") or []}
    llm = review._llm()
    if llm is None or llm.model != HAIKU_MODEL:
        raise SystemExit("모든 채점 LLM은 Haiku여야 합니다")
    index = index_mod.current()
    rows = []
    args.out.parent.mkdir(parents=True, exist_ok=True)
    source_rows = [row for row in run.get("rows") or [] if not row.get("error")]
    for position, source in enumerate(source_rows, 1):
        case_id = str(source.get("case_no") or "")
        try:
            evidence = reconstruct_evidence(index, selected[case_id])
            answers = {
                "baseline": str(source.get("baseline_answer") or ""),
                "raw_candidate": str(source.get("raw_candidate_answer") or
                                     source.get("baseline_answer") or ""),
                "guarded": str(source.get("answer") or ""),
            }
            cache = {}
            grades = {}
            for variant, answer in answers.items():
                if answer not in cache:
                    cache[answer] = _grade(llm, cases[case_id], answer, 3, evidence)
                correct, grade, votes, usage = cache[answer]
                if int((usage or {}).get("errors") or 0):
                    raise RuntimeError(f"{variant} semantic grade LLM error")
                grades[variant] = {"correct": bool(correct), "grade": grade,
                                   "votes": votes, "usage": usage}
            row = {"case_no": case_id, "answers": answers, "grades": grades,
                   "action": source.get("action"), "guard": source.get("guard")}
        except Exception as exc:
            row = {"case_no": case_id, "error": f"{type(exc).__name__}: {exc}"}
        rows.append(row)
        blob = {
            "experiment": "quote-first-closed-decision-frozen-answer-regrade3-v1",
            "contract": {
                "all_models": HAIKU_MODEL, "answers_frozen": True,
                "grade_repeats": 3, "gold_visible_only_to_evaluator": True,
                "main_wiring_changed": False, "canonical_changed": False,
            },
            "source_run": str(args.run), "summary": summarize(rows), "rows": rows,
        }
        args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"[{position:02d}/{len(source_rows)}] {case_id} "
              f"{'ERROR' if row.get('error') else 'done'}", flush=True)
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=1))
    return 1 if summarize(rows)["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
