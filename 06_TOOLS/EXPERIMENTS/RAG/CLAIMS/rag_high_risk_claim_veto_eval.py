#!/usr/bin/env python3
"""고정 Haiku 답변에서 고위험 명제 veto의 오류 탐지 정밀도·재현율을 평가한다."""

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


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.research.experiments.high_risk_claim_veto import audit_answer  # noqa: E402
from lawrag.research.experiments.haiku_legal_methods import HAIKU_MODEL  # noqa: E402
from lawrag.research.experiments.typed_evidence_connections import (  # noqa: E402
    attach_typed_connections,
)
from scripts import review_golden as review  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


def summarize(rows):
    good = [row for row in rows if not row.get("error")]
    decisions = Counter(str(row.get("decision") or "") for row in good)
    vetoed = [row for row in good if row.get("decision") == "veto"]
    wrong = [row for row in good if not row.get("truth_correct")]
    true_veto = sum(not row.get("truth_correct") for row in vetoed)
    false_veto = sum(bool(row.get("truth_correct")) for row in vetoed)
    caught = sum(row.get("decision") == "veto" for row in wrong)
    usages = {name: sum(int((row.get("usage") or {}).get(name, 0)) for row in good)
              for name in ("calls", "input_tokens", "output_tokens",
                           "duration_ms", "errors")}
    walls = [int(row.get("wall_ms") or 0) for row in good]
    return {
        "cases": len(good), "truth_correct": sum(row.get("truth_correct") for row in good),
        "truth_wrong": len(wrong), "decisions": dict(sorted(decisions.items())),
        "true_veto": true_veto, "false_veto": false_veto,
        "veto_precision": round(true_veto / len(vetoed), 4) if vetoed else None,
        "wrong_answer_recall": round(caught / len(wrong), 4) if wrong else None,
        "usage": usages,
        "wall_ms_p50": _percentile(walls, .5),
        "wall_ms_p95": _percentile(walls, .95),
        "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--regrade", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--answer-variant", default="full_context")
    parser.add_argument("--retrieval-variant", default="control_d_then_verifier")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text("utf-8"))
    answers = json.loads(args.answers.read_text("utf-8"))
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    regrade = json.loads(args.regrade.read_text("utf-8")) if args.regrade else {}
    cases = {str(row["id"]): row for row in suite.get("cases") or []}
    retrieved = {str(row["case_no"]): row for row in retrieval.get("rows") or []}
    repeat_truth = {
        str(row["case_no"]): bool(row["repeat_grades"][args.answer_variant]["correct"])
        for row in regrade.get("rows") or []}
    prototype = review._llm()
    if prototype is None:
        raise SystemExit("LLM 설정이 없습니다")
    if prototype.model != HAIKU_MODEL:
        raise SystemExit(f"Haiku가 아닌 모델 설정: {prototype.model}")
    index = index_mod.current()
    local = threading.local()
    answer_rows = list(answers.get("rows") or [])

    def evaluate(answer_row):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case_id = str(answer_row["case_no"])
        case = cases[case_id]
        value = (answer_row.get("variants") or {})[args.answer_variant]
        original_truth = bool(value.get("semantic_correct"))
        truth = repeat_truth.get(case_id, original_truth)
        selected = (((retrieved[case_id].get("variants") or {})
                    .get(args.retrieval_variant) or {}).get("selected") or [])
        evidence = reconstruct_evidence(index, list(selected))
        evidence = attach_typed_connections(
            index, str(case.get("question") or ""), evidence)
        log0 = len(llm.log)
        started = time.perf_counter()
        result = audit_answer(
            llm, str(case.get("question") or ""),
            str(value.get("answer") or ""), evidence)
        wall_ms = round((time.perf_counter() - started) * 1000)
        usage = _usage(list(llm.log)[log0:])
        return {
            "case_no": case_id, "question": case.get("question"),
            "answer": value.get("answer"),
            "truth_correct": truth,
            "truth_source": "repeat3" if case_id in repeat_truth else "single_grade",
            "decision": result.get("decision"), "guard": result.get("guard"),
            "claims": result.get("claims"),
            "validation": result.get("validation"),
            "usage": usage, "wall_ms": wall_ms,
        }

    rows = []
    order = {str(row["case_no"]): pos for pos, row in enumerate(answer_rows)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, row): str(row["case_no"])
                   for row in answer_rows}
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
                "experiment": "haiku-high-risk-claim-veto-shadow-v1",
                "contract": {"answers_frozen": True, "retrieval_frozen": True,
                             "main_wiring_changed": False,
                             "all_models": HAIKU_MODEL,
                             "gold_visible_to_product": False},
                "source_answers": str(args.answers),
                "summary": summarize(rows), "rows": rows,
            }
            args.out.write_text(
                json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
            if row.get("error"):
                print(f"[{position:02d}/{len(answer_rows)}] {case_id} ERROR", flush=True)
            else:
                truth = "correct" if row["truth_correct"] else "wrong"
                print(f"[{position:02d}/{len(answer_rows)}] {case_id} "
                      f"truth={truth} decision={row['decision']}", flush=True)
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
