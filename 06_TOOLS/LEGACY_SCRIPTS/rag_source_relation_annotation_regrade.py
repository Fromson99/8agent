#!/usr/bin/env python3
"""동결된 관계 주석 A/B/C 답변 전부를 Haiku 3표결로 재채점한다."""

from __future__ import annotations

import argparse
import concurrent.futures
from collections import Counter
import json
from pathlib import Path
import sys
import threading


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL  # noqa: E402
from lawrag.core.rag.experiments.typed_evidence_connections import (  # noqa: E402
    attach_typed_connections,
)
from scripts import review_golden as review  # noqa: E402
from scripts.rag_haiku_legal_methods_eval import _grade  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import reconstruct_evidence  # noqa: E402
from scripts.rag_source_relation_annotation_answer_ab import VARIANTS  # noqa: E402


def summarize(rows):
    out = {}
    for variant in VARIANTS:
        correct = sum(bool(row["grades"][variant]["correct"]) for row in rows)
        out[variant] = {"cases": len(rows), "correct": correct,
                        "accuracy": round(correct / len(rows), 4) if rows else 0}
    for variant in VARIANTS[1:]:
        paired = Counter((bool(row["grades"]["full_context"]["correct"]),
                          bool(row["grades"][variant]["correct"])) for row in rows)
        out[variant]["versus_full"] = {
            "both_correct": paired[(True, True)],
            "full_only_correct": paired[(True, False)],
            "annotation_only_correct": paired[(False, True)],
            "both_incorrect": paired[(False, False)],
            "delta": out[variant]["correct"] - out["full_context"]["correct"],
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--retrieval-variant", default="control_d_then_verifier")
    parser.add_argument("--repeats", type=int, choices=(3,), default=3)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text("utf-8"))
    run = json.loads(args.run.read_text("utf-8"))
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    cases = {str(case["id"]): case for case in suite.get("cases") or []}
    retrieved = {str(row["case_no"]): row for row in retrieval.get("rows") or []}
    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU_MODEL:
        raise SystemExit("모든 채점 LLM은 Haiku여야 합니다")
    index = index_mod.current()
    local = threading.local()

    def evaluate(source_row):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case_id = str(source_row["case_no"])
        case = cases[case_id]
        selected = (((retrieved[case_id].get("variants") or {})
                    .get(args.retrieval_variant) or {}).get("selected") or [])
        evidence = reconstruct_evidence(index, list(selected))
        evidence = attach_typed_connections(index, str(case.get("question") or ""), evidence)
        grades = {}
        for variant in VARIANTS:
            answer = str(source_row["variants"][variant].get("answer") or "")
            correct, grade, votes, usage = _grade(
                llm, case, answer, args.repeats, evidence)
            grades[variant] = {"correct": correct, "grade": grade,
                               "votes": votes, "usage": usage}
        return {"case_no": case_id, "grades": grades}

    rows = []
    source_rows = list(run.get("rows") or [])
    positions = {str(row["case_no"]): position
                 for position, row in enumerate(source_rows)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, row): str(row["case_no"])
                   for row in source_rows}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_id = futures[future]
            row = future.result()
            rows.append(row)
            rows.sort(key=lambda value: positions[value["case_no"]])
            print(f"[{position:02d}/{len(source_rows)}] {case_id} " + " ".join(
                f"{name}={'○' if row['grades'][name]['correct'] else '✗'}"
                for name in VARIANTS), flush=True)
    result = {
        "experiment": "source-relation-annotation-answer-abc-regrade3-v1",
        "contract": {"all_models": HAIKU_MODEL, "answers_frozen": True,
                     "gold_visible_to_product": False, "main_wiring_changed": False},
        "source_run": str(args.run), "repeats": args.repeats,
        "summary": summarize(rows), "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
