#!/usr/bin/env python3
"""동결 LegalClosure 초안에 미배선 final verifier/repair를 붙여 전수 A/B한다."""

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
from lawrag.core.rag.experiments.legal_answer_repair import (  # noqa: E402
    should_preserve_interpretive_qualification, verify_and_repair,
)
from scripts import review_golden as review  # noqa: E402
from scripts.ask_e2e_golden import _semantic_grade  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


def _sum_usage(rows, key):
    names = ("calls", "input_tokens", "output_tokens", "duration_ms", "errors")
    return {name: sum(int((row.get(key) or {}).get(name, 0)) for row in rows)
            for name in names}


def _merge_usage(left, right):
    names = set(left) | set(right)
    return {name: (list(left.get(name) or []) + list(right.get(name) or []))
            if name == "truncation_stages"
            else int(left.get(name) or 0) + int(right.get(name) or 0)
            for name in names}


def _grade_with_retry(llm, case, answer):
    grade, usage = _semantic_grade(llm, case, answer)
    if grade:
        return grade, usage
    retried, retry_usage = _semantic_grade(llm, case, answer)
    return retried, _merge_usage(usage, retry_usage)


def _summary(rows):
    good = [row for row in rows if not row.get("error")]
    baseline = sum(bool(row.get("baseline_semantic_correct")) for row in good)
    candidate = sum(bool(row.get("semantic_correct")) for row in good)
    walls = [int(row.get("repair_wall_ms") or 0) for row in good]
    total_walls = [int(row.get("baseline_product_wall_ms") or 0)
                   + int(row.get("repair_wall_ms") or 0) for row in good]
    actions = Counter(str(row.get("action") or "missing") for row in good)
    paired = {
        "cases": len(good),
        "both_correct": sum(row.get("baseline_semantic_correct")
                            and row.get("semantic_correct") for row in good),
        "baseline_only_correct": sum(row.get("baseline_semantic_correct")
                                     and not row.get("semantic_correct") for row in good),
        "candidate_only_correct": sum(not row.get("baseline_semantic_correct")
                                      and row.get("semantic_correct") for row in good),
        "both_incorrect": sum(not row.get("baseline_semantic_correct")
                              and not row.get("semantic_correct") for row in good),
    }
    changed = [row for row in good if row.get("answer_changed")]
    return {
        "cases": len(rows),
        "completed": len(good),
        "baseline_regraded": {
            "semantic_correct": baseline,
            "semantic_accuracy": round(baseline / len(good), 4) if good else 0,
        },
        "candidate": {
            "semantic_correct": candidate,
            "semantic_accuracy": round(candidate / len(good), 4) if good else 0,
            "delta": candidate - baseline,
        },
        "paired": paired,
        "gate": {
            "actions": dict(sorted(actions.items())),
            "changed_answers": len(changed),
            "changed_improved": sum(not row.get("baseline_semantic_correct")
                                    and row.get("semantic_correct") for row in changed),
            "changed_regressed": sum(row.get("baseline_semantic_correct")
                                     and not row.get("semantic_correct") for row in changed),
            "changed_still_correct": sum(row.get("baseline_semantic_correct")
                                         and row.get("semantic_correct") for row in changed),
            "changed_still_incorrect": sum(not row.get("baseline_semantic_correct")
                                           and not row.get("semantic_correct") for row in changed),
        },
        "repair_cost": _sum_usage(good, "repair_usage"),
        "semantic_evaluator_cost": {
            "baseline": _sum_usage(good, "baseline_semantic_usage"),
            "candidate": _sum_usage(good, "semantic_usage"),
        },
        "repair_wall_ms_p50": _percentile(walls, .5),
        "repair_wall_ms_p95": _percentile(walls, .95),
        "repair_wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
        "draft_plus_repair_wall_ms_p50": _percentile(total_walls, .5),
        "draft_plus_repair_wall_ms_p95": _percentile(total_walls, .95),
        "draft_plus_repair_wall_ms_mean": round(
            statistics.mean(total_walls), 3) if total_walls else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--baseline-answers", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    parser.add_argument("--model", default="claude-opus-5")
    parser.add_argument("--effort", choices=("low", "medium", "high"),
                        default="medium")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--cases", default="",
                        help="쉼표로 구분한 case id만 실행")
    parser.add_argument("--normalize-existing", action="store_true",
                        help="기존 --out에서 동일 답변의 중복 채점 노이즈만 제거")
    args = parser.parse_args()

    if args.normalize_existing:
        result = json.loads(args.out.read_text("utf-8"))
        baseline_blob = json.loads(args.baseline_answers.read_text("utf-8"))
        baseline_by_id = {str(row["case_no"]): row
                          for row in baseline_blob.get("rows") or []}
        variant = str(result.get("variant") or args.variant)
        normalized = 0
        reguarded = 0
        for row in result.get("rows") or []:
            if row.get("error"):
                continue
            baseline_variant = ((baseline_by_id.get(str(row.get("case_no"))) or {})
                                .get("variants") or {}).get(variant) or {}
            row["baseline_product_wall_ms"] = int(
                baseline_variant.get("product_wall_ms") or 0)
            if (row.get("answer_changed")
                    and should_preserve_interpretive_qualification(
                        str(row.get("baseline_answer") or ""),
                        str(row.get("answer") or ""))):
                row["action"] = "keep"
                row["guard"] = "interpretive_qualification_keep_draft"
                row["answer"] = row.get("baseline_answer")
                row["answer_changed"] = False
                reguarded += 1
            if row.get("answer_changed"):
                continue
            if row.get("semantic_correct") != row.get("baseline_semantic_correct"):
                normalized += 1
            row["semantic_correct"] = bool(row.get("baseline_semantic_correct"))
            row["semantic_grade"] = row.get("baseline_semantic_grade")
            row["semantic_reason"] = row.get("baseline_semantic_reason")
            row["semantic_usage"] = {
                "calls": 0, "input_tokens": 0, "output_tokens": 0,
                "duration_ms": 0, "errors": 0,
            }
        result.setdefault("contract", {})[
            "identical_answer_shared_grade"] = True
        result["normalized_identical_rows"] = normalized
        result["reguarded_interpretive_rows"] = reguarded
        result["summary"] = _summary(result.get("rows") or [])
        args.out.write_text(
            json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
        return 0

    suite = json.loads(args.suite.read_text("utf-8"))
    baseline_blob = json.loads(args.baseline_answers.read_text("utf-8"))
    retrieval_blob = json.loads(args.retrieval_ablation.read_text("utf-8"))
    by_id = {str(row["id"]): row for row in suite.get("cases") or []}
    baseline_by_id = {str(row["case_no"]): row
                      for row in baseline_blob.get("rows") or []}
    retrieval_by_id = {str(row["case_no"]): row
                       for row in retrieval_blob.get("rows") or []}
    wanted = {value.strip() for value in args.cases.split(",") if value.strip()}
    case_ids = [str(row["id"]) for row in suite.get("cases") or []
                if not wanted or str(row["id"]) in wanted]
    missing = [case_id for case_id in case_ids
               if case_id not in baseline_by_id or case_id not in retrieval_by_id]
    if missing:
        raise SystemExit("baseline/retrieval에 없는 case: " + ", ".join(missing))
    prototype = review._llm()
    if prototype is None:
        raise SystemExit("LLM 설정이 없습니다")
    index = index_mod.current()
    local = threading.local()

    def evaluate(case_id):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case = by_id[case_id]
        baseline_row = baseline_by_id[case_id]
        baseline_variant = (baseline_row.get("variants") or {}).get(args.variant) or {}
        retrieval_variant = ((retrieval_by_id[case_id].get("variants") or {})
                             .get(args.variant) or {})
        draft = str(baseline_variant.get("answer") or "")
        evidence = reconstruct_evidence(
            index, list(retrieval_variant.get("selected") or []))
        log0 = len(llm.log)
        started = time.perf_counter()
        repaired = verify_and_repair(
            llm, str(case.get("question") or ""), evidence, draft,
            model=args.model, effort=args.effort)
        repair_wall_ms = round((time.perf_counter() - started) * 1000)
        repair_usage = _usage(list(llm.log)[log0:])
        answer = str(repaired.get("answer") or draft)

        # 답이 같으면 한 번만 채점해 같은 판정을 공유한다. 같은 문장을 두 번
        # 채점하면 평가 모델의 확률 변동이 가짜 회귀/개선으로 잡힌다.
        if answer == draft:
            baseline_grade, baseline_semantic_usage = _grade_with_retry(
                llm, case, draft)
            grade = baseline_grade
            semantic_usage = {
                "calls": 0, "input_tokens": 0, "output_tokens": 0,
                "duration_ms": 0, "errors": 0,
            }
        elif int(case_id.split("-")[-1]) % 2:
            baseline_grade, baseline_semantic_usage = _grade_with_retry(llm, case, draft)
            grade, semantic_usage = _grade_with_retry(llm, case, answer)
        else:
            grade, semantic_usage = _grade_with_retry(llm, case, answer)
            baseline_grade, baseline_semantic_usage = _grade_with_retry(llm, case, draft)
        return {
            "case_no": case_id,
            "question": case.get("question"),
            "reference_answer": case.get("reference_answer"),
            "selected_count": len(evidence),
            "baseline_answer": draft,
            "baseline_product_wall_ms": int(
                baseline_variant.get("product_wall_ms") or 0),
            "baseline_recorded_semantic_correct": bool(
                baseline_variant.get("semantic_correct")),
            "baseline_semantic_correct": bool((baseline_grade or {}).get("correct")),
            "baseline_semantic_grade": baseline_grade,
            "baseline_semantic_reason": str((baseline_grade or {}).get("reason") or "")[:500],
            "baseline_semantic_usage": baseline_semantic_usage,
            "action": repaired.get("action"),
            "guard": repaired.get("guard"),
            "verification": repaired.get("raw"),
            "answer": answer,
            "answer_changed": answer != draft,
            "semantic_correct": bool((grade or {}).get("correct")),
            "semantic_grade": grade,
            "semantic_reason": str((grade or {}).get("reason") or "")[:500],
            "repair_usage": repair_usage,
            "semantic_usage": semantic_usage,
            "repair_wall_ms": repair_wall_ms,
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
            result = {
                "experiment": "legal-answer-final-verifier-repair-v1",
                "contract": {
                    "main_wiring_changed": False,
                    "retrieval_frozen": True,
                    "draft_generation_frozen": True,
                    "gold_visible_to_product": False,
                    "baseline_and_candidate_regraded_in_same_run": True,
                },
                "suite": str(args.suite),
                "baseline_answers": str(args.baseline_answers),
                "retrieval_ablation": str(args.retrieval_ablation),
                "variant": args.variant,
                "draft_model": baseline_blob.get("system_model"),
                "repair_model": args.model,
                "repair_effort": args.effort,
                "semantic_eval_model": "claude-sonnet-5",
                "summary": _summary(rows),
                "rows": rows,
            }
            args.out.write_text(
                json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
            if row.get("error"):
                print(f"[{position:02d}/{len(case_ids)}] {case_id} ERROR {row['error']}",
                      flush=True)
            else:
                before = "○" if row["baseline_semantic_correct"] else "✗"
                after = "○" if row["semantic_correct"] else "✗"
                print(f"[{position:02d}/{len(case_ids)}] {case_id} {before}→{after} "
                      f"action={row['action']} wall={row['repair_wall_ms']}ms", flush=True)
    print(json.dumps(_summary(rows), ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
