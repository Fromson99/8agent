#!/usr/bin/env python3
"""지배조문 패널 A/B 불일치 답변을 Haiku 3표결로 재채점한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL  # noqa: E402
from lawrag.core.rag.experiments.legal_applicability_graph import (  # noqa: E402
    ApplicabilityOntology,
)
from lawrag.core.rag.experiments.typed_evidence_connections import (  # noqa: E402
    attach_typed_connections,
)
from scripts import review_golden as review  # noqa: E402
from scripts.rag_governing_anchor_answer_ab import panel_evidence  # noqa: E402
from scripts.rag_haiku_legal_methods_eval import _grade  # noqa: E402
from scripts.rag_legal_applicability_answer_ab import gated_evidence  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import reconstruct_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--retrieval-variant", default="control_d_then_verifier")
    parser.add_argument("--candidate-variant",
                        choices=("anchor_panel", "applicability_gate"),
                        default="anchor_panel")
    parser.add_argument("--canonical", type=Path)
    parser.add_argument("--repeats", type=int, choices=(3,), default=3)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text("utf-8"))
    run = json.loads(args.run.read_text("utf-8"))
    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    cases = {str(row["id"]): row for row in suite.get("cases") or []}
    retrieved = {str(row["case_no"]): row for row in retrieval.get("rows") or []}
    llm = review._llm()
    if llm is None:
        raise SystemExit("LLM 설정이 없습니다")
    if llm.model != HAIKU_MODEL:
        raise SystemExit(f"Haiku가 아닌 모델 설정: {llm.model}")
    index = index_mod.current()
    ontology = None
    if args.candidate_variant == "applicability_gate":
        if args.canonical is None:
            raise SystemExit("applicability gate 재채점에는 --canonical이 필요합니다")
        ontology = ApplicabilityOntology(
            index, json.loads(args.canonical.read_text("utf-8")))
    rows = []
    for row in run.get("rows") or []:
        values = row.get("variants") or {}
        before = bool((values.get("full_context") or {}).get("semantic_correct"))
        after = bool((values.get(args.candidate_variant) or {}).get("semantic_correct"))
        if before == after:
            continue
        case_id = str(row["case_no"])
        case = cases[case_id]
        selected = (((retrieved[case_id].get("variants") or {})
                    .get(args.retrieval_variant) or {}).get("selected") or [])
        full = reconstruct_evidence(index, list(selected))
        full = attach_typed_connections(index, str(case.get("question") or ""), full)
        if args.candidate_variant == "anchor_panel":
            candidate, _ = panel_evidence(
                str(case.get("question") or ""), full,
                int(run.get("max_candidates") or 10))
        else:
            candidate = gated_evidence(
                str(case.get("question") or ""), full, ontology)
        evidence = {"full_context": full, args.candidate_variant: candidate}
        grades = {}
        for variant in ("full_context", args.candidate_variant):
            correct, grade, votes, usage = _grade(
                llm, case, str(values[variant].get("answer") or ""),
                args.repeats, evidence[variant])
            grades[variant] = {
                "correct": correct, "grade": grade,
                "votes": votes, "usage": usage,
            }
        rows.append({
            "case_no": case_id,
            "original": {"full_context": before, args.candidate_variant: after},
            "repeat_grades": grades,
        })
        print(case_id, " ".join(
            f"{name}={'○' if value['correct'] else '✗'}"
            for name, value in grades.items()), flush=True)

    summary = {
        "cases": len(rows),
        "full_correct": sum(row["repeat_grades"]["full_context"]["correct"]
                            for row in rows),
        "candidate_variant": args.candidate_variant,
        "candidate_correct": sum(
            row["repeat_grades"][args.candidate_variant]["correct"] for row in rows),
        "full_only_correct": sum(
            row["repeat_grades"]["full_context"]["correct"]
            and not row["repeat_grades"][args.candidate_variant]["correct"]
            for row in rows),
        "candidate_only_correct": sum(
            row["repeat_grades"][args.candidate_variant]["correct"]
            and not row["repeat_grades"]["full_context"]["correct"]
            for row in rows),
    }
    blob = {
        "experiment": "governing-anchor-panel-disagreement-regrade-v1",
        "contract": {"all_models": HAIKU_MODEL, "answers_frozen": True,
                     "main_wiring_changed": False},
        "source_run": str(args.run), "repeats": args.repeats,
        "summary": summary, "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
