#!/usr/bin/env python3
"""동결 12건에 quote-first 닫힌 법률 판단 답변을 생성해 고정한다."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys
import time


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments.haiku_quote_decision import (  # noqa: E402
    HAIKU_MODEL, quote_decision_answer,
)
from scripts import review_golden as review  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


HOLDOUT12 = (
    "cm-022", "cm-023", "cm-019", "cm-041", "cm-037", "cm-011",
    "cm-026", "cm-043", "cm-016", "cm-012", "cm-009", "cm-027",
)


def summarize(rows: list[dict]) -> dict:
    good = [row for row in rows if not row.get("error")]
    usages = [row.get("usage") or {} for row in good]
    walls = [int(row.get("wall_ms") or 0) for row in good]
    return {
        "cases": len(good),
        "errors": [row.get("error") for row in rows if row.get("error")],
        "actions": dict(Counter(str(row.get("action") or "missing") for row in good)),
        "guards": dict(Counter(str(row.get("guard") or "missing") for row in good)),
        "valid_final_plans": sum(bool(((row.get("validations") or {}).get("final") or {})
                                      .get("valid")) for row in good),
        "valid_certificates": sum(bool((row.get("certificate") or {}).get("valid"))
                                  for row in good),
        "tiebreak_cases": sum(bool(row.get("tiebreak")) for row in good),
        "always_three_plan_calls_saved": sum(
            int(row.get("always_three_calls_saved") or 0) for row in good),
        "raw_candidate_critical_flags": sum(
            bool((row.get("critical_value_audit") or {}).get("flagged")) for row in good),
        "unsupported_value_count": sum(
            len((row.get("critical_value_audit") or {}).get("unsupported_values") or [])
            for row in good),
        "product_usage": {key: sum(int(usage.get(key) or 0) for usage in usages)
                          for key in ("calls", "input_tokens", "output_tokens",
                                      "duration_ms", "errors")},
        "wall_ms_p50": _percentile(walls, .5),
        "wall_ms_p95": _percentile(walls, .95),
        "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--baseline-answers", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text("utf-8"))
    baselines = json.loads(args.baseline_answers.read_text("utf-8"))
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    cases = {str(row["id"]): row for row in suite.get("cases") or []}
    answer_rows = {str(row["case_no"]): row for row in baselines.get("rows") or []}
    retrieval_rows = {str(row["case_no"]): row for row in retrieval.get("rows") or []}
    missing = [case_id for case_id in HOLDOUT12
               if case_id not in cases or case_id not in answer_rows
               or case_id not in retrieval_rows]
    if missing:
        raise SystemExit("동결 입력 누락: " + ", ".join(missing))
    llm = review._llm()
    if llm is None or llm.model != HAIKU_MODEL:
        raise SystemExit("모든 제품 LLM은 Haiku여야 합니다")
    index = index_mod.current()
    rows = []
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for position, case_id in enumerate(HOLDOUT12, 1):
        try:
            case = cases[case_id]
            base = ((answer_rows[case_id].get("variants") or {}).get(args.variant) or {})
            selected = ((retrieval_rows[case_id].get("variants") or {})
                        .get(args.variant) or {}).get("selected") or []
            evidence = reconstruct_evidence(index, list(selected))
            for row in evidence:
                view = index.docs.get(str(row.get("doc_id") or ""))
                if view is not None:
                    row.update({
                        "document_revision": str(getattr(view, "revised", "") or ""),
                        "document_enforcement": str(getattr(view, "enforce", "") or ""),
                        "document_current": bool(getattr(view, "is_current", True)),
                    })
            log0 = len(llm.log)
            started = time.perf_counter()
            result = quote_decision_answer(
                llm, str(case.get("question") or ""), evidence,
                str(base.get("answer") or ""))
            wall_ms = round((time.perf_counter() - started) * 1000)
            row = {
                "case_no": case_id, "question": case.get("question"),
                "baseline_answer": str(base.get("answer") or ""),
                "selected_count": len(evidence), "wall_ms": wall_ms,
                "usage": _usage(list(llm.log)[log0:]), **result,
            }
        except Exception as exc:
            row = {"case_no": case_id, "error": f"{type(exc).__name__}: {exc}"}
        rows.append(row)
        blob = {
            "experiment": "haiku-quote-first-closed-decision-shadow-v1",
            "contract": {
                "all_product_models": HAIKU_MODEL, "retrieval_frozen": True,
                "baseline_answers_frozen": True, "gold_visible_to_product": False,
                "wiki_answer_context": False, "case_specific_rules": False,
                "main_wiring_changed": False, "canonical_changed": False,
                "answers_frozen_grade_pending": True,
            },
            "suite": str(args.suite), "baseline_answers": str(args.baseline_answers),
            "retrieval_ablation": str(args.retrieval_ablation),
            "holdout_case_ids": list(HOLDOUT12), "summary": summarize(rows),
            "rows": rows,
        }
        args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"[{position:02d}/{len(HOLDOUT12)}] {case_id} "
              f"{'ERROR' if row.get('error') else row.get('action')} "
              f"calls={((row.get('usage') or {}).get('calls') or 0)}", flush=True)
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=1))
    summary = summarize(rows)
    return 1 if summary["errors"] or summary["product_usage"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
