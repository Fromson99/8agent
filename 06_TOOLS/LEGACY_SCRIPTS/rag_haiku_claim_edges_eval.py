#!/usr/bin/env python3
"""동결 근거에서 Haiku claim edge를 2-pass 생성해 안정성과 guard를 평가한다."""

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
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments.haiku_claim_edges import (  # noqa: E402
    HAIKU_MODEL, compile_claim_edges, compile_closed_line_claims,
    consensus_claims, stability_summary,
)
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


def summarize(rows: list[dict]) -> dict:
    good = [row for row in rows if not row.get("error")]
    passes = [value for row in good for value in row.get("passes") or []]
    by_case = {str(row["case_no"]): list(row.get("passes") or []) for row in good}
    usage_keys = ("calls", "input_tokens", "output_tokens", "duration_ms", "errors")
    usage = {key: sum(int((value.get("usage") or {}).get(key, 0)) for value in passes)
             for key in usage_keys}
    walls = [int(value.get("wall_ms") or 0) for value in passes]
    consensus = [claim for row in good
                 for claim in consensus_claims(list(row.get("passes") or []))]
    return {
        "cases": len(good), "case_passes": len(passes),
        "cards": sum(len(value.get("cards") or []) for value in passes),
        "published": sum(len(value.get("published") or []) for value in passes),
        "rejected": sum(len(value.get("rejected") or []) for value in passes),
        "complete_decision_contracts": sum(
            bool(value.get("complete_decision_contract")) for value in passes),
        "consensus_claims": len(consensus),
        "consensus_kinds": dict(Counter(
            str(claim.get("claim_kind") or "") for claim in consensus)),
        "stability": stability_summary(by_case),
        "usage": usage,
        "wall_ms_p50": _percentile(walls, .5),
        "wall_ms_p95": _percentile(walls, .95),
        "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
        "all_calls_haiku": all(
            value.get("model") == HAIKU_MODEL for value in passes),
        "all_input_hashes_repeat": all(
            len({value.get("product_input_sha256") for value in row.get("passes") or []}) <= 1
            for row in good),
        "errors": [row.get("error") for row in rows if row.get("error")],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--repetitions", type=int, choices=(2,), default=2)
    parser.add_argument("--mode", choices=("open_span", "closed_line"),
                        default="open_span")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text("utf-8"))
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    retrieved = {str(row["case_no"]): row for row in retrieval.get("rows") or []}
    wanted = {value.strip() for value in args.cases.split(",") if value.strip()}
    cases = [case for case in suite.get("cases") or [] if str(case.get("id")) in wanted]
    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU_MODEL:
        raise SystemExit("모든 claim 생성 LLM은 Haiku여야 합니다")
    index = index_mod.current()
    local = threading.local()

    def evaluate(case):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case_id = str(case["id"])
        selected = (((retrieved[case_id].get("variants") or {}).get(args.variant) or {})
                    .get("selected") or [])
        evidence = reconstruct_evidence(index, list(selected))
        values = []
        for repetition in range(1, args.repetitions + 1):
            log0 = len(llm.log)
            started = time.perf_counter()
            compiler = (compile_closed_line_claims if args.mode == "closed_line"
                        else compile_claim_edges)
            result = compiler(llm, evidence)
            wall_ms = round((time.perf_counter() - started) * 1000)
            values.append({
                "repetition": repetition, "model": HAIKU_MODEL,
                "usage": _usage(list(llm.log)[log0:]), "wall_ms": wall_ms,
                **result,
            })
        return {"case_no": case_id, "question": case.get("question"),
                "selected_count": len(selected), "passes": values}

    rows, order = [], {str(case["id"]): pos for pos, case in enumerate(cases)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, case): str(case["id"]) for case in cases}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": case_id, "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row); rows.sort(key=lambda value: order[value["case_no"]])
            blob = {
                "experiment": f"haiku-claim-edges-{args.mode}-repeat2-v1",
                "contract": {
                    "all_models": HAIKU_MODEL, "retrieval_frozen": True,
                    "question_in_claim_extraction": False,
                    "gold_in_product_input": False,
                    "reference_answer_in_product_input": False,
                    "main_wiring_changed": False, "canonical_changed": False,
                },
                "suite": str(args.suite), "retrieval": str(args.retrieval_ablation),
                "variant": args.variant, "mode": args.mode,
                "case_ids": [str(case["id"]) for case in cases],
                "summary": summarize(rows), "rows": rows,
            }
            args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
            if row.get("error"):
                print(f"[{position:02d}/{len(cases)}] {case_id} ERROR {row['error']}", flush=True)
            else:
                counts = [len(value.get("published") or []) for value in row["passes"]]
                stable = len(consensus_claims(row["passes"]))
                print(f"[{position:02d}/{len(cases)}] {case_id} claims={counts} "
                      f"stable={stable}", flush=True)
    summary = summarize(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 1 if (summary["errors"] or summary["usage"]["errors"]
                 or not summary["all_calls_haiku"]
                 or summary["complete_decision_contracts"] != summary["case_passes"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
