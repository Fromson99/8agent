#!/usr/bin/env python3
"""전체 회수와 ontology 적용관계 결론 후보를 같은 Haiku 답변기로 paired A/B한다."""

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

from lawrag.core.rag import answer as answer_mod  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL  # noqa: E402
from lawrag.core.rag.experiments.legal_applicability_graph import (  # noqa: E402
    ApplicabilityOntology, classify_applicability,
)
from lawrag.core.rag.experiments.typed_evidence_connections import (  # noqa: E402
    attach_typed_connections,
)
from scripts import review_golden as review  # noqa: E402
from scripts.ask_e2e_golden import (  # noqa: E402
    _coords, _expected_article_coords, _semantic_grade,
)
from scripts.rag_frozen_retrieval_answer_control import _sections  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


VARIANTS = ("full_context", "applicability_gate")


def gated_evidence(question, evidence, ontology):
    classified = classify_applicability(question, evidence, ontology)
    return [row for row in classified
            if (row.get("applicability") or {}).get("conclusion_candidate")]


def _sum_usage(rows, variant, key):
    return {name: sum(int(((((row.get("variants") or {}).get(variant) or {})
                            .get(key) or {}).get(name, 0))) for row in rows)
            for name in ("calls", "input_tokens", "output_tokens",
                         "duration_ms", "errors")}


def summarize(rows):
    out = {}
    for variant in VARIANTS:
        values = [(row.get("variants") or {}).get(variant) or {} for row in rows]
        good = [row for row in values if not row.get("error")]
        correct = sum(bool(row.get("semantic_correct")) for row in good)
        walls = [int(row.get("product_wall_ms") or 0) for row in good]
        out[variant] = {
            "cases": len(good), "semantic_correct": correct,
            "semantic_accuracy": round(correct / len(good), 4) if good else 0,
            "selected_count_total": sum(int(row.get("selected_count") or 0)
                                        for row in good),
            "product_cost": _sum_usage(rows, variant, "usage"),
            "semantic_evaluator_cost": _sum_usage(rows, variant, "semantic_usage"),
            "wall_ms_p50": _percentile(walls, .5),
            "wall_ms_p95": _percentile(walls, .95),
            "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
        }
    paired = Counter()
    for row in rows:
        values = row.get("variants") or {}
        if any((values.get(name) or {}).get("error") for name in VARIANTS):
            continue
        paired[(bool(values[VARIANTS[0]].get("semantic_correct")),
                bool(values[VARIANTS[1]].get("semantic_correct")))] += 1
    full = out[VARIANTS[0]]
    gated = out[VARIANTS[1]]
    out["paired"] = {
        "both_correct": paired[(True, True)],
        "full_only_correct": paired[(True, False)],
        "gate_only_correct": paired[(False, True)],
        "both_incorrect": paired[(False, False)],
    }
    gated["versus_full"] = {
        "semantic_correct_delta": gated["semantic_correct"] - full["semantic_correct"],
        "input_tokens_delta": (gated["product_cost"]["input_tokens"]
                               - full["product_cost"]["input_tokens"]),
        "input_tokens_reduction": round(
            1 - gated["product_cost"]["input_tokens"]
            / full["product_cost"]["input_tokens"], 4)
        if full["product_cost"]["input_tokens"] else 0,
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--retrieval-variant", default="control_d_then_verifier")
    parser.add_argument("--cases", default="")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text("utf-8"))
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    canonical = json.loads(args.canonical.read_text("utf-8"))
    retrieved = {str(row["case_no"]): row for row in retrieval.get("rows") or []}
    wanted = {value.strip() for value in args.cases.split(",") if value.strip()}
    cases = [row for row in suite.get("cases") or []
             if not wanted or str(row["id"]) in wanted]
    prototype = review._llm()
    if prototype is None:
        raise SystemExit("LLM 설정이 없습니다")
    if prototype.model != HAIKU_MODEL:
        raise SystemExit(f"Haiku가 아닌 모델 설정: {prototype.model}")
    index = index_mod.current()
    ontology = ApplicabilityOntology(index, canonical)
    local = threading.local()

    def evaluate(case):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case_id = str(case["id"])
        selected = (((retrieved[case_id].get("variants") or {})
                    .get(args.retrieval_variant) or {}).get("selected") or [])
        full = reconstruct_evidence(index, list(selected))
        full = attach_typed_connections(
            index, str(case.get("question") or ""), full)
        gated = gated_evidence(str(case.get("question") or ""), full, ontology)
        evidence_by_variant = {"full_context": full, "applicability_gate": gated}
        expected = _expected_article_coords(case)
        values = {}
        order = (VARIANTS if int(case_id.split("-")[-1]) % 2
                 else tuple(reversed(VARIANTS)))
        for name in order:
            evidence = evidence_by_variant[name]
            sections = _sections(evidence)
            log0 = len(llm.log)
            started = time.perf_counter()
            answer = answer_mod.synthesize(
                llm, str(case.get("question") or ""), sections, spots=[])
            wall_ms = round((time.perf_counter() - started) * 1000)
            usage = _usage(list(llm.log)[log0:])
            semantic, semantic_usage = _semantic_grade(llm, case, answer.answer)
            values[name] = {
                "selected_count": len(evidence),
                "retrieval_gold_hits": len(expected & _coords(sections)),
                "gold_total": len(expected),
                "answer": answer.answer, "answerable": answer.answerable,
                "basis_case_hit": bool(expected & _coords(answer.refs)),
                "semantic_correct": bool((semantic or {}).get("correct")),
                "semantic_grade": semantic,
                "semantic_reason": str((semantic or {}).get("reason") or "")[:500],
                "usage": usage, "semantic_usage": semantic_usage,
                "product_wall_ms": wall_ms,
            }
        return {"case_no": case_id, "question": case.get("question"),
                "reference_answer": case.get("reference_answer"), "variants": values}

    rows = []
    positions = {str(case["id"]): pos for pos, case in enumerate(cases)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, case): str(case["id"]) for case in cases}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": case_id, "variants": {
                    name: {"error": f"{type(exc).__name__}: {exc}"}
                    for name in VARIANTS}}
            rows.append(row)
            rows.sort(key=lambda value: positions[value["case_no"]])
            blob = {
                "experiment": "legal-applicability-graph-answer-ab-v1",
                "contract": {"main_wiring_changed": False,
                             "retrieval_frozen": True,
                             "all_models": HAIKU_MODEL,
                             "gold_visible_to_product": False},
                "suite": str(args.suite), "summary": summarize(rows), "rows": rows,
            }
            args.out.write_text(
                json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
            marks = row.get("variants") or {}
            print(f"[{position:02d}/{len(cases)}] {case_id} " + " ".join(
                f"{name}={'○' if value.get('semantic_correct') else '✗'}"
                for name, value in marks.items()), flush=True)
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=1))
    return 1 if any(value.get("error") for row in rows
                    for value in (row.get("variants") or {}).values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
