#!/usr/bin/env python3
"""동결된 full/matrix 답변을 Haiku 3표결로 재채점한다."""

from __future__ import annotations

import argparse
import concurrent.futures
from collections import Counter
import json
from pathlib import Path
import sys
import threading


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import review_golden as review  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments.haiku_claim_edges import HAIKU_MODEL  # noqa: E402
from scripts.rag_haiku_legal_methods_eval import _grade  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import reconstruct_evidence  # noqa: E402


VARIANTS = ("full_context", "claim_matrix")


def summarize(rows):
    good = [row for row in rows if not row.get("error")]
    out = {variant: {"correct": sum(bool(row["grades"][variant]["correct"])
                                    for row in good), "cases": len(good)}
           for variant in VARIANTS}
    paired = Counter((bool(row["grades"]["full_context"]["correct"]),
                      bool(row["grades"]["claim_matrix"]["correct"])) for row in good)
    out["claim_matrix"]["versus_full"] = {
        "both_correct": paired[(True, True)], "full_only_correct": paired[(True, False)],
        "matrix_only_correct": paired[(False, True)], "both_incorrect": paired[(False, False)],
        "delta": out["claim_matrix"]["correct"] - out["full_context"]["correct"],
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
    parser.add_argument("--workers", type=int, choices=range(1, 3), default=1)
    args = parser.parse_args()
    suite = json.loads(args.suite.read_text("utf-8"))
    cases = {str(case["id"]): case for case in suite.get("cases") or []}
    run = json.loads(args.run.read_text("utf-8"))
    source_rows = [row for row in run.get("rows") or [] if not row.get("error")]
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    selected = {str(row["case_no"]): (((row.get("variants") or {}).get(args.variant) or {})
                                      .get("selected") or [])
                for row in retrieval.get("rows") or []}
    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU_MODEL:
        raise SystemExit("모든 채점 LLM은 Haiku여야 합니다")
    index = index_mod.current(); local = threading.local()

    def evaluate(source):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm; case_id = str(source["case_no"])
        evidence = reconstruct_evidence(index, selected[case_id])
        grades = {}
        for variant in VARIANTS:
            answer = str(((source.get("variants") or {}).get(variant) or {}).get("answer") or "")
            correct, grade, votes, usage = _grade(llm, cases[case_id], answer, 3, evidence)
            if int((usage or {}).get("errors") or 0):
                raise RuntimeError(f"{variant} semantic grade LLM error")
            grades[variant] = {"correct": bool(correct), "grade": grade,
                               "votes": votes, "usage": usage}
        return {"case_no": case_id, "grades": grades}

    rows, order = [], {str(row["case_no"]): pos for pos, row in enumerate(source_rows)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, row): str(row["case_no"]) for row in source_rows}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_id = futures[future]
            try: row = future.result()
            except Exception as exc: row = {"case_no": case_id,
                                            "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row); rows.sort(key=lambda value: order[value["case_no"]])
            result = {"experiment": "claim-matrix-frozen-answer-regrade3-v1",
                      "contract": {"all_models": HAIKU_MODEL, "answers_frozen": True,
                                   "grade_repeats": 3, "main_wiring_changed": False},
                      "source_run": str(args.run), "summary": summarize(rows), "rows": rows}
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
            print(f"[{position:02d}/{len(source_rows)}] {case_id} "
                  f"{'ERROR' if row.get('error') else 'done'}", flush=True)
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=1))
    return 1 if summarize(rows)["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
