#!/usr/bin/env python3
"""2-pass consensus claim으로 entailment matrix 답변을 만들고 baseline과 비교한다."""

from __future__ import annotations

import argparse
import concurrent.futures
from collections import Counter
import json
from pathlib import Path
import statistics
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_golden as review  # noqa: E402
from lawrag.core.rag import answer as answer_mod, index as index_mod  # noqa: E402
from lawrag.core.rag.experiments.haiku_claim_edges import (  # noqa: E402
    HAIKU_MODEL, align_claims, consensus_claims, entailment_matrix,
    render_matrix_answer,
)
from scripts.rag_frozen_retrieval_answer_control import _sections  # noqa: E402
from scripts.rag_haiku_legal_methods_eval import _grade  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


VARIANTS = ("full_context", "claim_matrix")


def summarize(rows: list[dict]) -> dict:
    good = [row for row in rows if not row.get("error")]
    out = {"coverage_cases": len(good), "errors": [row.get("error") for row in rows
                                                     if row.get("error")]}
    for variant in VARIANTS:
        values = [(row.get("variants") or {}).get(variant) or {} for row in good]
        correct = sum(bool(value.get("correct")) for value in values)
        walls = [int(value.get("wall_ms") or 0) for value in values]
        out[variant] = {
            "correct": correct,
            "accuracy": round(correct / len(values), 4) if values else 0,
            "usage": {key: sum(int((value.get("usage") or {}).get(key, 0))
                               for value in values)
                      for key in ("calls", "input_tokens", "output_tokens",
                                  "duration_ms", "errors")},
            "wall_ms_p50": _percentile(walls, .5),
            "wall_ms_p95": _percentile(walls, .95),
            "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
        }
    paired = Counter((bool(row["variants"]["full_context"].get("correct")),
                      bool(row["variants"]["claim_matrix"].get("correct")))
                     for row in good)
    out["claim_matrix"]["versus_full"] = {
        "both_correct": paired[(True, True)],
        "full_only_correct": paired[(True, False)],
        "matrix_only_correct": paired[(False, True)],
        "both_incorrect": paired[(False, False)],
        "delta": out["claim_matrix"]["correct"] - out["full_context"]["correct"],
    }
    out["valid_alignments"] = sum(bool(row.get("alignment", {}).get("valid"))
                                  for row in good)
    out["valid_matrix_renders"] = sum(bool(row.get("matrix_render", {}).get("valid"))
                                      for row in good)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--claim-artifact", type=Path, required=True)
    parser.add_argument("--baseline-answers", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    parser.add_argument("--cases", default="")
    parser.add_argument("--skip-grade", action="store_true")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text("utf-8"))
    cases = {str(case["id"]): case for case in suite.get("cases") or []}
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    retrieved = {str(row["case_no"]): row for row in retrieval.get("rows") or []}
    claim_blob = json.loads(args.claim_artifact.read_text("utf-8"))
    baseline_blob = (json.loads(args.baseline_answers.read_text("utf-8"))
                     if args.baseline_answers else None)
    baselines = ({str(row["case_no"]): row for row in baseline_blob.get("rows") or []}
                 if baseline_blob else {})
    claim_rows = {str(row["case_no"]): row for row in claim_blob.get("rows") or []
                  if not row.get("error") and consensus_claims(row.get("passes") or [])}
    case_ids = [case_id for case_id in (claim_blob.get("case_ids") or [])
                if case_id in claim_rows]
    wanted = {value.strip() for value in args.cases.split(",") if value.strip()}
    if wanted:
        case_ids = [case_id for case_id in case_ids if case_id in wanted]
    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU_MODEL:
        raise SystemExit("모든 답변·정렬·채점 LLM은 Haiku여야 합니다")
    index = index_mod.current()
    local = threading.local()

    def evaluate(case_id):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case = cases[case_id]
        selected = (((retrieved[case_id].get("variants") or {}).get(args.variant) or {})
                    .get("selected") or [])
        evidence = reconstruct_evidence(index, list(selected))
        claims = consensus_claims(claim_rows[case_id].get("passes") or [])

        # case 번호 parity로 생성 순서를 회전해 순서 효과를 한쪽에 몰지 않는다.
        values = {}
        if int(case_id.split("-")[-1]) % 2:
            order = ("claim_matrix", "full_context")
        else:
            order = ("full_context", "claim_matrix")
        alignment = matrix = matrix_render = None
        for variant in order:
            log0 = len(llm.log); started = time.perf_counter()
            if variant == "full_context":
                frozen = ((baselines.get(case_id, {}).get("variants") or {})
                          .get(args.variant) or {})
                if frozen.get("answer"):
                    answer = str(frozen["answer"])
                else:
                    answer = answer_mod.synthesize(
                        llm, str(case.get("question") or ""),
                        _sections(evidence), spots=[]).answer
            else:
                alignment = align_claims(llm, str(case.get("question") or ""), claims)
                if not alignment.get("valid"):
                    raise RuntimeError(f"invalid alignment: {alignment.get('errors')}")
                matrix = entailment_matrix(claims, alignment)
                matrix_render = render_matrix_answer(
                    llm, str(case.get("question") or ""), evidence, matrix)
                if not matrix_render.get("valid"):
                    raise RuntimeError(f"invalid matrix render: {matrix_render.get('errors')}")
                answer = matrix_render["answer"]
            wall_ms = round((time.perf_counter() - started) * 1000)
            usage = _usage(list(llm.log)[log0:])
            if int(usage.get("errors") or 0):
                raise RuntimeError(f"{variant} product LLM error")
            if args.skip_grade:
                correct, grade, votes, grade_usage = None, None, [], {}
            else:
                correct, grade, votes, grade_usage = _grade(
                    llm, case, answer, 3, evidence)
                if int((grade_usage or {}).get("errors") or 0):
                    raise RuntimeError(f"{variant} semantic grade LLM error")
            values[variant] = {
                "answer": answer, "correct": bool(correct), "grade": grade,
                "votes": votes, "grade_usage": grade_usage,
                "usage": usage, "wall_ms": wall_ms,
            }
        return {
            "case_no": case_id, "question": case.get("question"),
            "claims": claims, "alignment": alignment, "matrix": matrix,
            "matrix_render": matrix_render, "variants": values,
        }

    rows, order = [], {case_id: pos for pos, case_id in enumerate(case_ids)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, case_id): case_id for case_id in case_ids}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": case_id, "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row); rows.sort(key=lambda value: order[value["case_no"]])
            blob = {
                "experiment": "claim-entailment-matrix-answer-ab-v1",
                "contract": {
                    "all_models": HAIKU_MODEL, "retrieval_frozen": True,
                    "same_full_evidence": True, "gold_visible_to_product": False,
                    "claim_support_required": 2, "grade_repeats": 3,
                    "answers_frozen_grade_pending": args.skip_grade,
                    "main_wiring_changed": False, "canonical_changed": False,
                },
                "suite": str(args.suite), "claim_artifact": str(args.claim_artifact),
                "baseline_answers": str(args.baseline_answers) if args.baseline_answers else "",
                "eligible_case_ids": case_ids, "summary": summarize(rows), "rows": rows,
            }
            args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
            if row.get("error"):
                print(f"[{position:02d}/{len(case_ids)}] {case_id} ERROR {row['error']}", flush=True)
            else:
                print(f"[{position:02d}/{len(case_ids)}] {case_id} "
                      f"full={'○' if row['variants']['full_context']['correct'] else '✗'} "
                      f"matrix={'○' if row['variants']['claim_matrix']['correct'] else '✗'}",
                      flush=True)
    summary = summarize(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
