#!/usr/bin/env python3
"""동결 51건에서 일반 법률 방법론 세 가지를 Haiku만으로 비교한다."""

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
from lawrag.research.experiments.haiku_legal_methods import (  # noqa: E402
    HAIKU_MODEL, METHODS, RUNNERS, compress_focused, evidence_payload,
)
from scripts import review_golden as review  # noqa: E402
from scripts.ask_e2e_golden import (  # noqa: E402
    SEMANTIC_SCHEMA, SEMANTIC_SYSTEM, _reference_answer,
)
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


def _sum_usage(rows, method, key="usage"):
    names = ("calls", "input_tokens", "output_tokens", "duration_ms", "errors")
    return {name: sum(int((((row.get("methods") or {}).get(method) or {})
                           .get(key) or {}).get(name, 0)) for row in rows)
            for name in names}


def _grade(llm, case, answer, repeats, evidence):
    votes, usages = [], []
    for _ in range(repeats):
        start = len(llm.log)
        verification = evidence_payload(compress_focused(
            str(case.get("question") or ""), evidence))
        grade = llm.structured(
            "eval.answer.semantic.haiku", SEMANTIC_SYSTEM +
            " 채점 순서: (1) 기준답변을 최소 필수명제로 분해하고, (2) 시스템 "
            "답변이 각 명제를 지지하는지 보고, (3) 반대 결론이나 중요한 수치 오류가 "
            "있는지만 확인한다. 기준답변에 없는 추가 설명은 그 자체로 오류가 아니며, "
            "오직 기준답변과 직접 모순될 때만 감점한다. '추가 내용', '더 자세함', "
            "'기준답변 범위 초과'만을 이유로 false로 판정하는 것은 금지한다. "
            " 법령 인용의 수식 범위를 문법대로 읽는다. 같은 항의 제1호를 설명한 뒤 "
            "이어지는 '제2호'는 다른 표시가 없으면 같은 항 제2호를 뜻하며, 앞서 "
            "괄호 안에서 인용한 다른 항의 제2호로 되돌아가지 않는다. 기준답변보다 "
            "구체적인 원문상 값을 밝혔다는 이유만으로 감점하지 않는다.",
            f"[질문]\n{case['question']}\n\n[기준답변]\n"
            f"{_reference_answer(case)}\n\n[시스템 답변]\n{answer[:8000]}\n\n"
            f"[검증 원문 — 기준답변의 인용 범위가 모호할 때만 확인]\n"
            f"{json.dumps(verification, ensure_ascii=False)}\n\n"
            "reason은 3문장 이내, missing_points는 최대 5개로 쓴다.",
            SEMANTIC_SCHEMA, max_tokens=1600, effort="low", model=HAIKU_MODEL)
        votes.append(dict(grade or {}))
        usages.append(_usage(list(llm.log)[start:]))
    yes = sum(bool(vote.get("correct")) for vote in votes)
    correct = yes > len(votes) // 2
    representative = next(
        (vote for vote in votes if bool(vote.get("correct")) == correct), {})
    names = ("calls", "input_tokens", "output_tokens", "duration_ms", "errors")
    usage = {name: sum(int(row.get(name, 0)) for row in usages) for name in names}
    return correct, representative, votes, usage


def _summary(rows, methods):
    good = [row for row in rows if not row.get("error")]
    out = {}
    baseline = sum(bool((row.get("grades") or {}).get("baseline", {}).get("correct"))
                   for row in good)
    out["baseline"] = {
        "cases": len(good), "semantic_correct": baseline,
        "semantic_accuracy": round(baseline / len(good), 4) if good else 0,
    }
    for method in methods:
        values = [(row.get("methods") or {}).get(method) or {} for row in good]
        candidate = sum(bool(value.get("semantic_correct")) for value in values)
        walls = [int(value.get("wall_ms") or 0) for value in values]
        paired = {
            "both_correct": 0, "baseline_only_correct": 0,
            "candidate_only_correct": 0, "both_incorrect": 0,
        }
        for row, value in zip(good, values):
            before = bool(row["grades"]["baseline"]["correct"])
            after = bool(value.get("semantic_correct"))
            key = ("both_correct" if before and after else
                   "baseline_only_correct" if before else
                   "candidate_only_correct" if after else "both_incorrect")
            paired[key] += 1
        actions = Counter(str(value.get("action") or "missing") for value in values)
        out[method] = {
            "cases": len(values), "semantic_correct": candidate,
            "semantic_accuracy": round(candidate / len(values), 4) if values else 0,
            "delta": candidate - baseline,
            "paired": paired,
            "actions": dict(sorted(actions.items())),
            "changed": sum(bool(value.get("answer_changed")) for value in values),
            "product_cost": _sum_usage(good, method),
            "wall_ms_p50": _percentile(walls, .5),
            "wall_ms_p95": _percentile(walls, .95),
            "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--baseline-answers", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    parser.add_argument("--methods", default=",".join(METHODS))
    parser.add_argument("--cases", default="")
    parser.add_argument("--grade-repeats", type=int, choices=(1, 3), default=1)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()

    methods = tuple(dict.fromkeys(value.strip() for value in args.methods.split(",")
                                  if value.strip()))
    unknown = [value for value in methods if value not in RUNNERS]
    if unknown:
        raise SystemExit("unknown methods: " + ", ".join(unknown))
    suite = json.loads(args.suite.read_text("utf-8"))
    baseline_blob = json.loads(args.baseline_answers.read_text("utf-8"))
    retrieval_blob = json.loads(args.retrieval_ablation.read_text("utf-8"))
    cases = {str(row["id"]): row for row in suite.get("cases") or []}
    baselines = {str(row["case_no"]): row for row in baseline_blob.get("rows") or []}
    retrievals = {str(row["case_no"]): row for row in retrieval_blob.get("rows") or []}
    wanted = {value.strip() for value in args.cases.split(",") if value.strip()}
    case_ids = [str(row["id"]) for row in suite.get("cases") or []
                if not wanted or str(row["id"]) in wanted]
    prototype = review._llm()
    if prototype is None:
        raise SystemExit("LLM 설정이 없습니다")
    index = index_mod.current()
    local = threading.local()

    def evaluate(case_id):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case = cases[case_id]
        base = ((baselines[case_id].get("variants") or {}).get(args.variant) or {})
        retrieved = ((retrievals[case_id].get("variants") or {})
                     .get(args.variant) or {})
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
        method_rows = {}
        # case 번호로 실행 순서를 회전해 특정 방법이 항상 먼저 호출되는 편향을 줄인다.
        offset = int(case_id.split("-")[-1]) % max(1, len(methods))
        run_order = methods[offset:] + methods[:offset]
        for method in run_order:
            log0 = len(llm.log)
            started = time.perf_counter()
            result = RUNNERS[method](llm, str(case.get("question") or ""),
                                     evidence, draft)
            wall_ms = round((time.perf_counter() - started) * 1000)
            method_rows[method] = {
                "action": result.get("action"), "guard": result.get("guard"),
                "answer": str(result.get("answer") or draft),
                "answer_changed": str(result.get("answer") or draft) != draft,
                "focused_ids": result.get("focused_ids"),
                "focused_chars": result.get("focused_chars"),
                "wiki": result.get("wiki"),
                "analysis": result.get("raw"), "matrix": result.get("matrix"),
                "usage": _usage(list(llm.log)[log0:]), "wall_ms": wall_ms,
            }

        # 동일 답은 한 번만 Haiku 채점하고 결과를 공유한다.
        cache = {}
        answers = {"baseline": draft} | {
            method: method_rows[method]["answer"] for method in methods}
        grades = {}
        for label, answer in answers.items():
            if answer not in cache:
                cache[answer] = _grade(
                    llm, case, answer, args.grade_repeats, evidence)
            correct, grade, votes, usage = cache[answer]
            grades[label] = {"correct": correct, "grade": grade,
                             "votes": votes, "usage": usage}
            if label in method_rows:
                method_rows[label]["semantic_correct"] = correct
                method_rows[label]["semantic_grade"] = grade
                method_rows[label]["semantic_votes"] = votes
                method_rows[label]["semantic_usage"] = usage
        return {
            "case_no": case_id, "question": case.get("question"),
            "reference_answer": _reference_answer(case), "selected_count": len(evidence),
            "baseline_answer": draft, "grades": grades, "methods": method_rows,
        }

    rows = []
    order = {case_id: pos for pos, case_id in enumerate(case_ids)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, case_id): case_id for case_id in case_ids}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": case_id, "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            rows.sort(key=lambda value: order[value["case_no"]])
            result = {
                "experiment": "haiku-only-general-legal-methods-v1",
                "contract": {
                    "main_wiring_changed": False, "retrieval_frozen": True,
                    "draft_frozen": True, "gold_visible_to_product": False,
                    "all_product_models": HAIKU_MODEL,
                    "semantic_evaluator_model": HAIKU_MODEL,
                    "case_specific_rules": False,
                },
                "suite": str(args.suite), "methods": list(methods),
                "grade_repeats": args.grade_repeats, "summary": _summary(rows, methods),
                "rows": rows,
            }
            args.out.write_text(
                json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
            if row.get("error"):
                print(f"[{position:02d}/{len(case_ids)}] {case_id} ERROR {row['error']}",
                      flush=True)
            else:
                before = "○" if row["grades"]["baseline"]["correct"] else "✗"
                marks = " ".join(
                    f"{method}={'○' if row['methods'][method]['semantic_correct'] else '✗'}"
                    for method in methods)
                print(f"[{position:02d}/{len(case_ids)}] {case_id} base={before} {marks}",
                      flush=True)
    print(json.dumps(_summary(rows, methods), ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
