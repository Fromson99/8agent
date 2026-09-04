#!/usr/bin/env python3
"""동결 검색·답변 위에서 Haiku 법률 명제 컴파일러를 shadow 평가한다."""

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

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments.haiku_legal_compiler import (  # noqa: E402
    HAIKU_MODEL, compiled_answer,
)
from lawrag.core.rag.experiments.typed_evidence_connections import (  # noqa: E402
    attach_typed_connections,
)
from scripts import review_golden as review  # noqa: E402
from scripts.rag_haiku_legal_methods_eval import _grade  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


def summarize(rows):
    good = [row for row in rows if not row.get("error")]
    baseline = sum(bool((row.get("baseline_grade") or {}).get("correct"))
                   for row in good)
    candidate = sum(bool((row.get("candidate_grade") or {}).get("correct"))
                    for row in good)
    paired = Counter()
    for row in good:
        before = bool(row["baseline_grade"]["correct"])
        after = bool(row["candidate_grade"]["correct"])
        paired[(before, after)] += 1
    walls = [int(row.get("product_wall_ms") or 0) for row in good]
    product_names = ("calls", "input_tokens", "output_tokens", "duration_ms", "errors")
    product = {name: sum(int((row.get("usage") or {}).get(name, 0)) for row in good)
               for name in product_names}
    card_counts = [len(row.get("cards") or []) for row in good]
    return {
        "cases": len(good),
        "baseline_correct": baseline,
        "candidate_correct": candidate,
        "delta": candidate - baseline,
        "paired": {
            "both_correct": paired[(True, True)],
            "baseline_only_correct": paired[(True, False)],
            "candidate_only_correct": paired[(False, True)],
            "both_incorrect": paired[(False, False)],
        },
        "actions": dict(Counter(str(row.get("action") or "") for row in good)),
        "valid_compilations": sum(bool((row.get("validation") or {}).get("valid"))
                                  for row in good),
        "product_cost": product,
        "wall_ms_p50": _percentile(walls, .5),
        "wall_ms_p95": _percentile(walls, .95),
        "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
        "cards_p50": _percentile(card_counts, .5),
        "cards_p95": _percentile(card_counts, .95),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--baseline-answers", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    parser.add_argument("--cases", default="")
    parser.add_argument("--grade-repeats", type=int, choices=(1, 3), default=1)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--evidence-policy", choices=("strict", "three-tier"),
                        default="strict")
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text("utf-8"))
    baseline_blob = json.loads(args.baseline_answers.read_text("utf-8"))
    retrieval_blob = json.loads(args.retrieval_ablation.read_text("utf-8"))
    cases = {str(row["id"]): row for row in suite.get("cases") or []}
    baselines = {str(row["case_no"]): row for row in baseline_blob.get("rows") or []}
    retrievals = {str(row["case_no"]): row for row in retrieval_blob.get("rows") or []}
    wanted = {value.strip() for value in args.cases.split(",") if value.strip()}
    case_ids = [str(row["id"]) for row in suite.get("cases") or []
                if not wanted or str(row["id"]) in wanted]
    if review._llm() is None:
        raise SystemExit("LLM 설정이 없습니다")
    index = index_mod.current()
    local = threading.local()

    def evaluate(case_id):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case = cases[case_id]
        base = ((baselines[case_id].get("variants") or {}).get(args.variant) or {})
        retrieved = ((retrievals[case_id].get("variants") or {}).get(args.variant) or {})
        draft = str(base.get("answer") or "")
        evidence = reconstruct_evidence(index, list(retrieved.get("selected") or []))
        for row in evidence:
            view = index.docs.get(str(row.get("doc_id") or ""))
            if view is not None:
                row.update({
                    "document_revision": str(getattr(view, "revised", "") or ""),
                    "document_enforcement": str(getattr(view, "enforce", "") or ""),
                    "document_current": bool(getattr(view, "is_current", True)),
                })
        evidence = attach_typed_connections(
            index, str(case.get("question") or ""), evidence)
        log0 = len(llm.log)
        started = time.perf_counter()
        result = compiled_answer(
            llm, str(case.get("question") or ""), evidence, draft,
            evidence_policy=args.evidence_policy)
        wall_ms = round((time.perf_counter() - started) * 1000)
        usage = _usage(list(llm.log)[log0:])
        answer = str(result.get("answer") or draft)
        cache = {}
        for value in (draft, answer):
            if value not in cache:
                cache[value] = _grade(llm, case, value, args.grade_repeats, evidence)
        b_correct, b_grade, b_votes, b_usage = cache[draft]
        c_correct, c_grade, c_votes, c_usage = cache[answer]
        return {
            "case_no": case_id, "question": case.get("question"),
            "baseline_answer": draft, "candidate_answer": answer,
            "answer_changed": answer != draft,
            "action": result.get("action"), "guard": result.get("guard"),
            "inventory": result.get("inventory"), "cards": result.get("cards"),
            "compiled": result.get("compiled"),
            "validation": result.get("validation"), "render": result.get("render"),
            "usage": usage, "product_wall_ms": wall_ms,
            "baseline_grade": {"correct": b_correct, "grade": b_grade,
                               "votes": b_votes, "usage": b_usage},
            "candidate_grade": {"correct": c_correct, "grade": c_grade,
                                "votes": c_votes, "usage": c_usage},
        }

    rows = []
    order = {case_id: position for position, case_id in enumerate(case_ids)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, case_id): case_id for case_id in case_ids}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": case_id,
                       "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            rows.sort(key=lambda value: order[value["case_no"]])
            blob = {
                "experiment": "haiku-legal-proposition-compiler-shadow-v1",
                "contract": {
                    "main_wiring_changed": False,
                    "retrieval_frozen": True,
                    "draft_frozen": True,
                    "gold_visible_to_product": False,
                    "all_models": HAIKU_MODEL,
                },
                "suite": str(args.suite), "grade_repeats": args.grade_repeats,
                "evidence_policy": args.evidence_policy,
                "summary": summarize(rows), "rows": rows,
            }
            args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n",
                                "utf-8")
            if row.get("error"):
                print(f"[{position:02d}/{len(case_ids)}] {case_id} ERROR {row['error']}",
                      flush=True)
            else:
                before = "○" if row["baseline_grade"]["correct"] else "✗"
                after = "○" if row["candidate_grade"]["correct"] else "✗"
                print(f"[{position:02d}/{len(case_ids)}] {case_id} "
                      f"base={before} compiled={after} guard={row['guard']}", flush=True)
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
