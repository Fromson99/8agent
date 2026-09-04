#!/usr/bin/env python3
"""질문 구조가 명제 검증기와 기존 설명 합성기를 라우팅하는 51건 E2E."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_golden as review  # noqa: E402
from scripts.ask_e2e_golden import (  # noqa: E402
    _coords, _expected_article_coords, _semantic_grade,
)
from scripts.rag_frozen_retrieval_answer_control import _sections  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _evidence_coords, _usage, reconstruct_evidence, summarize,
)
from lawrag.core.rag import answer as answer_mod, legalissue  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text("utf-8"))
    retrieval_run = json.loads(args.retrieval.read_text("utf-8"))
    by_id = {str(row["id"]): row for row in suite.get("cases") or []}
    retrieved_by_id = {str(row["case_no"]): row
                       for row in retrieval_run.get("rows") or []}
    wanted = list(dict.fromkeys(
        case_id.strip() for value in args.case_id for case_id in value.split(",")
        if case_id.strip()))
    case_ids = wanted or list(by_id)
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
        retrieved = retrieved_by_id[case_id]
        evidence = reconstruct_evidence(index, retrieved.get("selected") or [])
        sections = _sections(evidence)
        expected = _expected_article_coords(case)
        retrieved_coords = _evidence_coords(evidence)
        log0 = len(llm.log)
        started = time.perf_counter()
        product_started = time.perf_counter()
        frame = legalissue.structure_question_typed(
            llm, str(case.get("question") or ""))
        question_type = str((frame or {}).get("question_type") or "rule_explanation")
        judgment_raw = judgment = None
        synthesized = None
        if question_type == "proposition_verification":
            judgment_raw = legalissue.judge_evidence(llm, frame or {}, evidence)
            judgment = legalissue.verify_judgment(judgment_raw, evidence, frame)
            answer = legalissue.render_answer(frame or {}, judgment)
            material_ids = list(dict.fromkeys(
                str(row.get("evidence_id") or "")
                for row in (judgment or {}).get("rule_findings") or []
                if row.get("evidence_id")))
            basis_ids = list(map(str, (judgment or {}).get(
                "controlling_evidence_ids") or []))
            outcome = str((judgment or {}).get("verdict") or "not_determined")
            material_coords = _evidence_coords(evidence, material_ids)
            basis_coords = _evidence_coords(evidence, basis_ids)
            route = "three_way_proposition_guard"
        else:
            synthesized = answer_mod.synthesize(
                llm, str(case.get("question") or ""), sections, spots=[])
            answer = synthesized.answer
            material_ids = [str(row["id"]) for row in evidence]
            basis_ids = list(material_ids)
            material_coords = basis_coords = _coords(synthesized.refs)
            outcome = "answered" if synthesized.answerable else "not_determined"
            route = "constructive_existing_synthesis"
        product_wall_ms = round((time.perf_counter() - product_started) * 1000)
        product_exchanges = list(llm.log)[log0:]
        semantic, semantic_usage = _semantic_grade(llm, case, answer)
        return {
            "case_no": case_id, "question": case.get("question"),
            "reference_answer": case.get("reference_answer"),
            "gold": list(case.get("expected_articles") or []),
            "gold_total": len(expected),
            "retrieval_gold_hits": len(expected & retrieved_coords),
            "retrieval_case_hit": bool(expected & retrieved_coords),
            "selected": list(retrieved.get("selected") or []),
            "evidence": [{key: value for key, value in row.items()
                          if key != "original_text"} | {
                              "chars": len(str(row.get("original_text") or ""))
                          } for row in evidence],
            "frame": frame, "route": route,
            "active_interpreters": legalissue.interpreter_instructions(frame or {}),
            "judgment_raw": judgment_raw, "judgment": judgment,
            "synthesis": ({"answerable": synthesized.answerable,
                           "refs": synthesized.refs} if synthesized else None),
            "verdict": outcome,
            "material_basis_ids": material_ids,
            "material_basis_gold_hits": len(expected & material_coords),
            "material_basis_case_hit": bool(expected & material_coords),
            "basis_ids": basis_ids,
            "basis_gold_hits": len(expected & basis_coords),
            "basis_case_hit": bool(expected & basis_coords),
            "answer": answer,
            "semantic_correct": bool((semantic or {}).get("correct")),
            "semantic_grade": semantic,
            "semantic_reason": str((semantic or {}).get("reason") or "")[:500],
            "usage": _usage(product_exchanges), "semantic_usage": semantic_usage,
            "retrieval_usage": dict(retrieved.get("usage") or {}),
            "retrieval_wall_ms": int(retrieved.get("wall_ms") or 0),
            "product_wall_ms": product_wall_ms,
            "wall_ms": round((time.perf_counter() - started) * 1000),
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
                "experiment": "legal-question-type-routed-answer-v3",
                "suite": str(args.suite), "retrieval_source": str(args.retrieval),
                "system_model": prototype.model,
                "semantic_eval_model": "claude-sonnet-5",
                "summary": summarize(rows, retrieval_run.get("summary") or {}),
                "rows": rows,
            }
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                                encoding="utf-8")
            if row.get("error"):
                print(f"[{position:02d}/{len(case_ids)}] {case_id} ERROR {row['error']}",
                      flush=True)
            else:
                mark = "○" if row["semantic_correct"] else "✗"
                print(f"[{position:02d}/{len(case_ids)}] {mark} {case_id} "
                      f"{row['route']} ret={row['retrieval_gold_hits']}/"
                      f"{row['gold_total']} status={row['verdict']} "
                      f"wall={row['wall_ms']}ms", flush=True)
    print(json.dumps(summarize(rows, retrieval_run.get("summary") or {}),
                     ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
