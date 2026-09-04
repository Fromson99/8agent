#!/usr/bin/env python3
"""동일 전체 근거에 source 관계 주석만 추가해 Haiku 답변 paired A/B/C를 한다."""

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

from lawrag.core.rag import answer as answer_mod  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL  # noqa: E402
from lawrag.core.rag.experiments.typed_evidence_connections import (  # noqa: E402
    attach_typed_connections,
)
from scripts import review_golden as review  # noqa: E402
from scripts.ask_e2e_golden import _semantic_grade  # noqa: E402
from scripts.rag_frozen_retrieval_answer_control import _sections  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


VARIANTS = ("full_context", "structural_annotations", "all_relation_annotations")
STRUCTURAL = frozenset({"EXCEPTION_TO", "IMPLEMENTS", "DEFINED_BY", "CURRENT_VERSION_OF"})


def has_structural_relation(relation_row, relation_types=STRUCTURAL):
    return any(str(relation.get("relation_type") or "") in relation_types
               for relation in relation_row.get("published") or [])


def _relation_edge(relation, inventory):
    by_id = {str(row.get("evidence_id") or ""): row for row in inventory}
    source_id = str(relation.get("source_id") or "")
    target_id = str(relation.get("target_id") or "")
    relation_type = str(relation.get("relation_type") or "")
    source = by_id.get(source_id) or {}
    target = by_id.get(target_id) or {}
    target_text = (str(target.get("path") or "") if target_id else
                   str(relation.get("target_value") or ""))
    surface = str(relation.get("defined_term") or relation.get("target_value") or "")
    return source_id, {
        "id": str(relation.get("relation_id") or "SR?"),
        "from": str(source.get("path") or source_id),
        "relation": relation_type,
        "surface": surface[:160],
        "to": target_text[:240],
    }


def annotate_sections(sections, relation_row, *, structural_only: bool,
                      structural_types=STRUCTURAL):
    inventory = list(relation_row.get("inventory") or [])
    by_evidence = {f"E{position}": section
                   for position, section in enumerate(sections, 1)}
    attached = 0
    for relation in relation_row.get("published") or []:
        if structural_only and relation.get("relation_type") not in structural_types:
            continue
        source_id, edge = _relation_edge(relation, inventory)
        section = by_evidence.get(source_id)
        if section is None:
            continue
        section.edges.append(edge)
        attached += 1
    return sections, attached


def _sum_usage(rows, variant, key):
    return {name: sum(int((((row.get("variants") or {}).get(variant) or {})
                           .get(key) or {}).get(name, 0)) for row in rows)
            for name in ("calls", "input_tokens", "output_tokens", "duration_ms", "errors")}


def summarize(rows):
    out = {}
    for variant in VARIANTS:
        values = [(row.get("variants") or {}).get(variant) or {} for row in rows]
        good = [value for value in values if not value.get("error")]
        walls = [int(value.get("product_wall_ms") or 0) for value in good]
        correct = sum(bool(value.get("semantic_correct")) for value in good)
        out[variant] = {
            "cases": len(good), "semantic_correct": correct,
            "semantic_accuracy": round(correct / len(good), 4) if good else 0,
            "annotations": sum(int(value.get("annotations") or 0) for value in good),
            "product_cost": _sum_usage(rows, variant, "usage"),
            "semantic_evaluator_cost": _sum_usage(rows, variant, "semantic_usage"),
            "wall_ms_p50": _percentile(walls, .5),
            "wall_ms_p95": _percentile(walls, .95),
            "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
        }
    for variant in VARIANTS[1:]:
        paired = Counter()
        for row in rows:
            base = (row.get("variants") or {}).get("full_context") or {}
            other = (row.get("variants") or {}).get(variant) or {}
            if base.get("error") or other.get("error"):
                continue
            paired[(bool(base.get("semantic_correct")),
                    bool(other.get("semantic_correct")))] += 1
        out[variant]["versus_full"] = {
            "both_correct": paired[(True, True)],
            "full_only_correct": paired[(True, False)],
            "annotation_only_correct": paired[(False, True)],
            "both_incorrect": paired[(False, False)],
            "semantic_correct_delta": (out[variant]["semantic_correct"]
                                       - out["full_context"]["semantic_correct"]),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--relation-artifacts", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--retrieval-variant", default="control_d_then_verifier")
    parser.add_argument("--cases", default="")
    parser.add_argument(
        "--require-structural", action="store_true",
        help="구조 관계(EXCEPTION/IMPLEMENTS/DEFINED/CURRENT)가 있는 사례만 평가",
    )
    parser.add_argument(
        "--structural-types", default=",".join(sorted(STRUCTURAL)),
        help="structural_annotations에 포함할 관계 유형의 쉼표 목록",
    )
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    structural_types = frozenset(
        value.strip() for value in args.structural_types.split(",") if value.strip())
    unknown_types = structural_types - STRUCTURAL
    if not structural_types or unknown_types:
        raise SystemExit(f"invalid structural relation types: {sorted(unknown_types)}")

    suite = json.loads(args.suite.read_text("utf-8"))
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    retrieved = {str(row["case_no"]): row for row in retrieval.get("rows") or []}
    relation_rows = {}
    source_contracts = []
    for path in args.relation_artifacts:
        artifact = json.loads(path.read_text("utf-8"))
        source_contracts.append(artifact.get("contract") or {})
        for row in artifact.get("rows") or []:
            if row.get("published"):
                relation_rows[str(row.get("case_no") or "")] = row
    wanted = {value.strip() for value in args.cases.split(",") if value.strip()}
    cases = [case for case in suite.get("cases") or []
             if str(case.get("id") or "") in relation_rows
             and (not args.require_structural or has_structural_relation(
                 relation_rows[str(case.get("id") or "")], structural_types))
             and (not wanted or str(case.get("id") or "") in wanted)]
    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU_MODEL:
        raise SystemExit("모든 답변·채점 LLM은 Haiku여야 합니다")
    index = index_mod.current()
    local = threading.local()

    def evaluate(case):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case_id = str(case["id"])
        selected = (((retrieved[case_id].get("variants") or {})
                    .get(args.retrieval_variant) or {}).get("selected") or [])
        evidence = reconstruct_evidence(index, list(selected))
        evidence = attach_typed_connections(index, str(case.get("question") or ""), evidence)
        relation_row = relation_rows[case_id]
        sections_by_variant = {
            "full_context": _sections(evidence),
            "structural_annotations": annotate_sections(
                _sections(evidence), relation_row, structural_only=True,
                structural_types=structural_types)[0],
            "all_relation_annotations": annotate_sections(
                _sections(evidence), relation_row, structural_only=False)[0],
        }
        annotation_counts = {
            name: sum(len(section.edges) for section in sections)
            for name, sections in sections_by_variant.items()
        }
        values = {}
        rotate = int(case_id.split("-")[-1]) % len(VARIANTS)
        order = VARIANTS[rotate:] + VARIANTS[:rotate]
        for name in order:
            sections = sections_by_variant[name]
            log0 = len(llm.log)
            started = time.perf_counter()
            answer = answer_mod.synthesize(
                llm, str(case.get("question") or ""), sections, spots=[])
            wall_ms = round((time.perf_counter() - started) * 1000)
            usage = _usage(list(llm.log)[log0:])
            semantic, semantic_usage = _semantic_grade(llm, case, answer.answer)
            values[name] = {
                "answer": answer.answer, "answerable": answer.answerable,
                "annotations": annotation_counts[name],
                "semantic_correct": bool((semantic or {}).get("correct")),
                "semantic_grade": semantic,
                "semantic_reason": str((semantic or {}).get("reason") or "")[:500],
                "usage": usage, "semantic_usage": semantic_usage,
                "product_wall_ms": wall_ms,
            }
        return {"case_no": case_id, "question": case.get("question"),
                "reference_answer": case.get("reference_answer"), "variants": values}

    rows = []
    positions = {str(case["id"]): position for position, case in enumerate(cases)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, case): str(case["id"]) for case in cases}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": case_id, "variants": {
                    name: {"error": f"{type(exc).__name__}: {exc}"} for name in VARIANTS}}
            rows.append(row)
            rows.sort(key=lambda value: positions[value["case_no"]])
            blob = {
                "experiment": "source-relation-annotation-answer-abc-v1",
                "contract": {
                    "main_wiring_changed": False, "retrieval_frozen": True,
                    "all_models": HAIKU_MODEL, "gold_visible_to_product": False,
                    "same_evidence_all_variants": True,
                    "require_structural_relation": args.require_structural,
                    "structural_relation_types": sorted(structural_types),
                    "relation_generation_used_question_gold_reference": False,
                    "source_relation_contracts": source_contracts,
                },
                "suite": str(args.suite), "relation_artifacts": [
                    str(path) for path in args.relation_artifacts],
                "summary": summarize(rows), "rows": rows,
            }
            args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
            marks = row.get("variants") or {}
            print(f"[{position:02d}/{len(cases)}] {case_id} " + " ".join(
                f"{name}={'○' if value.get('semantic_correct') else '✗'}"
                for name, value in marks.items()), flush=True)
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=1))
    return 1 if any(value.get("error") for row in rows
                    for value in (row.get("variants") or {}).values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
