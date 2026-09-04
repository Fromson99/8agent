#!/usr/bin/env python3
"""LegalClosure control과 D 제거 후보를 같은 51건 답변·채점 모델로 A/B한다."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
from pathlib import Path
import statistics
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import answer as answer_mod  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from scripts import review_golden as review  # noqa: E402
from scripts.ask_e2e_golden import (  # noqa: E402
    _coords, _expected_article_coords, _semantic_grade,
)
from scripts.rag_frozen_retrieval_answer_control import _sections  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


VARIANTS = ("control_d_then_verifier", "abc_then_verifier")


def _sum_usage(rows, variant, key):
    return {name: sum(int(((row.get("variants") or {}).get(variant) or {})
                         .get(key, {}).get(name, 0)) for row in rows)
            for name in ("calls", "input_tokens", "output_tokens",
                         "duration_ms", "errors")}


def _summary(rows):
    out = {}
    for variant in VARIANTS:
        values = [(row.get("variants") or {}).get(variant) or {} for row in rows]
        good = [row for row in values if not row.get("error")]
        correct = sum(bool(row.get("semantic_correct")) for row in good)
        product_ms = [int(row.get("product_wall_ms") or 0) for row in good]
        out[variant] = {
            "cases": len(values), "completed": len(good),
            "semantic_correct": correct,
            "semantic_accuracy": round(correct / len(good), 4) if good else 0,
            "basis_case_hits": sum(bool(row.get("basis_case_hit")) for row in good),
            "product_cost": _sum_usage(rows, variant, "usage"),
            "semantic_evaluator_cost": _sum_usage(rows, variant, "semantic_usage"),
            "product_wall_ms_p50": _percentile(product_ms, .5),
            "product_wall_ms_p95": _percentile(product_ms, .95),
            "product_wall_ms_mean": round(statistics.mean(product_ms), 3)
            if product_ms else 0,
        }
    control = out["control_d_then_verifier"]
    candidate = out[VARIANTS[1]]
    candidate["versus_control"] = {
        "semantic_correct_delta": (
            candidate["semantic_correct"] - control["semantic_correct"]),
        "input_tokens_delta": (
            candidate["product_cost"]["input_tokens"]
            - control["product_cost"]["input_tokens"]),
        "input_tokens_reduction": round(
            1 - candidate["product_cost"]["input_tokens"]
            / control["product_cost"]["input_tokens"], 4)
            if control["product_cost"]["input_tokens"] else 0,
        "duration_ms_delta": (
            candidate["product_cost"]["duration_ms"]
            - control["product_cost"]["duration_ms"]),
    }
    paired = [row for row in rows if all(
        not ((row.get("variants") or {}).get(name) or {}).get("error")
        for name in VARIANTS)]
    out["paired"] = {
        "cases": len(paired),
        "both_correct": sum(all(row["variants"][name]["semantic_correct"]
                                for name in VARIANTS) for row in paired),
        "control_only_correct": sum(
            row["variants"][VARIANTS[0]]["semantic_correct"]
            and not row["variants"][VARIANTS[1]]["semantic_correct"]
            for row in paired),
        "candidate_only_correct": sum(
            row["variants"][VARIANTS[1]]["semantic_correct"]
            and not row["variants"][VARIANTS[0]]["semantic_correct"]
            for row in paired),
        "both_incorrect": sum(not any(row["variants"][name]["semantic_correct"]
                                      for name in VARIANTS) for row in paired),
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--ablation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--candidate", default="abc_then_verifier",
                        help="control과 비교할 ablation variant")
    parser.add_argument("--cases", default="",
                        help="쉼표로 구분한 case id만 재실행")
    args = parser.parse_args()

    global VARIANTS
    VARIANTS = ("control_d_then_verifier", args.candidate)

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    ablation = json.loads(args.ablation.read_text(encoding="utf-8"))
    cases = list(suite.get("cases") or [])
    wanted = {value.strip() for value in args.cases.split(",") if value.strip()}
    if wanted:
        cases = [case for case in cases if str(case.get("id")) in wanted]
    retrieval = {str(row["case_no"]): row for row in ablation.get("rows") or []}
    prototype = review._llm()
    if prototype is None:
        raise SystemExit("LLM 설정이 없습니다")
    index = index_mod.current()
    local = threading.local()

    def evaluate(case):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case_no = str(case["id"])
        frozen = retrieval[case_no]["variants"]
        order = VARIANTS if int(case_no.split("-")[-1]) % 2 else tuple(reversed(VARIANTS))
        values = {}
        expected = _expected_article_coords(case)
        for variant in order:
            selected = frozen[variant]["selected"]
            evidence = reconstruct_evidence(index, selected)
            sections = _sections(evidence)
            log0 = len(llm.log)
            started = time.perf_counter()
            answer = answer_mod.synthesize(
                llm, str(case.get("question") or ""), sections, spots=[])
            product_ms = round((time.perf_counter() - started) * 1000)
            usage = _usage(list(llm.log)[log0:])
            semantic, semantic_usage = _semantic_grade(llm, case, answer.answer)
            cited = _coords(answer.refs)
            values[variant] = {
                "selected_count": len(selected),
                "answerable": answer.answerable, "answer": answer.answer,
                "basis_case_hit": bool(expected & cited),
                "semantic_correct": bool((semantic or {}).get("correct")),
                "semantic_grade": semantic,
                "semantic_reason": str((semantic or {}).get("reason") or "")[:500],
                "usage": usage, "semantic_usage": semantic_usage,
                "product_wall_ms": product_ms,
            }
        return {"case_no": case_no, "question": case.get("question"),
                "reference_answer": case.get("reference_answer"), "variants": values}

    rows = []
    order = {str(case["id"]): pos for pos, case in enumerate(cases)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, case): str(case["id"]) for case in cases}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_no = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": case_no, "variants": {
                    name: {"error": f"{type(exc).__name__}: {exc}"} for name in VARIANTS}}
            rows.append(row)
            rows.sort(key=lambda value: order[value["case_no"]])
            result = {
                "experiment": "legalclosure-d-removal-answer-ab-v1",
                "suite": str(args.suite), "ablation": str(args.ablation),
                "system_model": prototype.model, "summary": _summary(rows), "rows": rows,
            }
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                                encoding="utf-8")
            marks = row.get("variants") or {}
            print(f"[{position:02d}/{len(cases)}] {case_no} "
                  + " ".join(f"{name}={'○' if value.get('semantic_correct') else '✗'}"
                             for name, value in marks.items()), flush=True)
    print(json.dumps(_summary(rows), ensure_ascii=False, indent=1))
    return 1 if any(value.get("error") for row in rows
                    for value in (row.get("variants") or {}).values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
