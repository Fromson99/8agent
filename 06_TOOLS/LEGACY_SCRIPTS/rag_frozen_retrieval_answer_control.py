#!/usr/bin/env python3
"""같은 고정 구조검색 본문을 기존 답변 합성기에 넣는 51건 대조군."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import threading
import time
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import review_golden as review  # noqa: E402
from scripts.ask_e2e_golden import (  # noqa: E402
    _coords, _expected_article_coords, _semantic_grade,
)
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)
from lawrag.core.rag import answer as answer_mod  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402


def _sections(evidence):
    return [answer_mod.Section(
        n=position, doc_id=str(row["doc_id"]), doc=str(row["document"]),
        node=row["node"], path=str(row["path"]), page=None,
        kind="구조적용어탐색", matched=str(row.get("role") or ""),
        text=str(row.get("original_text") or ""),
    ) for position, row in enumerate(evidence, 1)]


def _sum_usage(rows, key):
    return {name: sum(int((row.get(key) or {}).get(name, 0)) for row in rows)
            for name in ("calls", "input_tokens", "output_tokens",
                         "duration_ms", "errors")}


def _summary(rows, retrieval_summary):
    good = [row for row in rows if not row.get("error")]
    hit = [row for row in good if row.get("retrieval_case_hit")]
    empty = [row for row in good if not row.get("selected")]
    semantic = lambda values: sum(bool(row.get("semantic_correct")) for row in values)
    product = _sum_usage(good, "usage")
    retrieval = {name: int(retrieval_summary.get(name) or 0)
                 for name in ("calls", "input_tokens", "output_tokens",
                              "duration_ms", "errors")}
    return {
        "cases": len(rows), "completed": len(good),
        "semantic_correct": semantic(good),
        "semantic_accuracy": round(semantic(good) / len(good), 4) if good else 0,
        "retrieval_case_hits": len(hit),
        "semantic_correct_when_retrieval_hit": semantic(hit),
        "semantic_accuracy_when_retrieval_hit": round(semantic(hit) / len(hit), 4)
        if hit else 0,
        "empty_evidence_cases": len(empty),
        "semantic_correct_with_empty_evidence": semantic(empty),
        "basis_case_hits": sum(bool(row.get("basis_case_hit")) for row in good),
        "product_cost": product,
        "semantic_evaluator_cost": _sum_usage(good, "semantic_usage"),
        "system_end_to_end_cost": {
            name: retrieval[name] + product[name] for name in retrieval
        },
        "product_wall_ms_p50": _percentile(
            (row.get("product_wall_ms", 0) for row in good), .5),
        "product_wall_ms_p95": _percentile(
            (row.get("product_wall_ms", 0) for row in good), .95),
        "system_end_to_end_wall_ms_p50": _percentile(
            (int(row.get("retrieval_wall_ms") or 0)
             + int(row.get("product_wall_ms") or 0) for row in good), .5),
        "system_end_to_end_wall_ms_p95": _percentile(
            (int(row.get("retrieval_wall_ms") or 0)
             + int(row.get("product_wall_ms") or 0) for row in good), .95),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--regrade-errors", action="store_true",
                        help="기존 --out의 의미 채점 오류 행만 다시 채점")
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text("utf-8"))
    retrieval_run = json.loads(args.retrieval.read_text("utf-8"))
    cases = list(suite.get("cases") or [])
    retrieval = {str(row["case_no"]): row
                 for row in retrieval_run.get("rows") or []}
    prototype = review._llm()
    if prototype is None:
        raise SystemExit("LLM 설정이 없습니다")
    if args.regrade_errors:
        result = json.loads(args.out.read_text("utf-8"))
        by_id = {str(case["id"]): case for case in cases}
        for row in result.get("rows") or []:
            if not int((row.get("semantic_usage") or {}).get("errors") or 0):
                continue
            semantic, semantic_usage = _semantic_grade(
                prototype, by_id[str(row["case_no"])], str(row.get("answer") or ""))
            row["semantic_correct"] = bool((semantic or {}).get("correct"))
            row["semantic_grade"] = semantic
            row["semantic_reason"] = str((semantic or {}).get("reason") or "")[:500]
            row["semantic_usage"] = semantic_usage
            print(f"regraded {row['case_no']} errors={semantic_usage.get('errors', 0)}")
        result["summary"] = _summary(
            result.get("rows") or [], retrieval_run.get("summary") or {})
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
        print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
        return 1 if int(result["summary"]["semantic_evaluator_cost"]["errors"]) else 0
    index = index_mod.current()
    local = threading.local()

    def evaluate(case):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case_id = str(case["id"])
        retrieved = retrieval[case_id]
        evidence = reconstruct_evidence(index, retrieved.get("selected") or [])
        sections = _sections(evidence)
        expected = _expected_article_coords(case)
        retrieved_coords = _coords(sections)
        log0 = len(llm.log)
        started = time.perf_counter()
        result = answer_mod.synthesize(
            llm, str(case.get("question") or ""), sections, spots=[])
        product_ms = round((time.perf_counter() - started) * 1000)
        product_usage = _usage(list(llm.log)[log0:])
        semantic, semantic_usage = _semantic_grade(llm, case, result.answer)
        cited = _coords(result.refs)
        return {
            "case_no": case_id, "question": case.get("question"),
            "reference_answer": case.get("reference_answer"),
            "selected": retrieved.get("selected") or [],
            "retrieval_gold_hits": len(expected & retrieved_coords),
            "gold_total": len(expected),
            "retrieval_case_hit": bool(expected & retrieved_coords),
            "basis_gold_hits": len(expected & cited),
            "basis_case_hit": bool(expected & cited),
            "answerable": result.answerable, "answer": result.answer,
            "semantic_correct": bool((semantic or {}).get("correct")),
            "semantic_grade": semantic,
            "semantic_reason": str((semantic or {}).get("reason") or "")[:500],
            "usage": product_usage, "semantic_usage": semantic_usage,
            "retrieval_wall_ms": int(retrieved.get("wall_ms") or 0),
            "product_wall_ms": product_ms,
        }

    rows = []
    order = {str(case["id"]): pos for pos, case in enumerate(cases)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, case): str(case["id"]) for case in cases}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": case_id,
                       "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            rows.sort(key=lambda value: order[value["case_no"]])
            result = {
                "experiment": "frozen-structural-retrieval-current-answer-control-v1",
                "suite": str(args.suite), "retrieval_source": str(args.retrieval),
                "system_model": prototype.model,
                "summary": _summary(rows, retrieval_run.get("summary") or {}),
                "rows": rows,
            }
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                                encoding="utf-8")
            if row.get("error"):
                print(f"[{position:02d}/{len(cases)}] {case_id} ERROR {row['error']}",
                      flush=True)
            else:
                mark = "○" if row["semantic_correct"] else "✗"
                print(f"[{position:02d}/{len(cases)}] {mark} {case_id} "
                      f"ret={row['retrieval_gold_hits']}/{row['gold_total']} "
                      f"calls={row['usage']['calls']} wall={row['product_wall_ms']}ms",
                      flush=True)
    print(json.dumps(_summary(rows, retrieval_run.get("summary") or {}),
                     ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
