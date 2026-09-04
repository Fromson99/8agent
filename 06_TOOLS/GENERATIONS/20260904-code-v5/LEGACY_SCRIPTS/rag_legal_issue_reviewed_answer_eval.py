#!/usr/bin/env python3
"""기존 합성 초안을 질문 유형별 원문 체크리스트로 교정하는 E2E 실험."""

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
from scripts.ask_e2e_golden import _coords, _expected_article_coords, _semantic_grade  # noqa: E402
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
    parser.add_argument("--review-scope", choices=("all", "proposition"),
                        default="all",
                        help="초안 검토를 모든 유형 또는 명제 검증에만 적용")
    parser.add_argument("--reguard-existing", action="store_true",
                        help="저장된 원응답에 현재 결정론적 guard만 적용하고 변경 행을 재채점")
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
    if args.reguard_existing:
        result = json.loads(args.out.read_text("utf-8"))
        changed = 0
        for row in result.get("rows") or []:
            if row.get("error") or not row.get("review_applied", True):
                continue
            evidence = reconstruct_evidence(index, row.get("selected") or [])
            frame = row.get("frame") or {}
            checked = legalissue.verify_typed_answer(
                row.get("review_raw"), frame, evidence)
            reviewed = legalissue.guard_reviewed_proposition(
                checked, frame, evidence)
            answer = legalissue.render_reviewed_answer(frame, reviewed)
            if answer != str(row.get("answer") or ""):
                row["answer_before_guard_v2"] = row.get("answer")
                semantic, semantic_usage = _semantic_grade(
                    prototype, by_id[str(row["case_no"])], answer)
                row["answer"] = answer
                row["semantic_correct"] = bool((semantic or {}).get("correct"))
                row["semantic_grade"] = semantic
                row["semantic_reason"] = str((semantic or {}).get("reason") or "")[:500]
                row["semantic_usage"] = semantic_usage
                changed += 1
                print(f"reguarded {row['case_no']} → {reviewed.get('status')}")
            row["reviewed"] = reviewed
            row["verdict"] = str((reviewed or {}).get("status") or "not_determined")
        result["guard_version"] = 2
        result["reguarded_rows"] = changed
        result["summary"] = summarize(
            result.get("rows") or [], retrieval_run.get("summary") or {})
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
        print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
        return 1 if any(row.get("error") for row in result.get("rows") or []) else 0
    local = threading.local()

    def evaluate(case_id):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case, retrieved = by_id[case_id], retrieved_by_id[case_id]
        evidence = reconstruct_evidence(index, retrieved.get("selected") or [])
        sections = _sections(evidence)
        expected = _expected_article_coords(case)
        retrieved_coords = _evidence_coords(evidence)
        log0 = len(llm.log)
        started = time.perf_counter()
        product_started = time.perf_counter()
        frame = legalissue.structure_question_typed(
            llm, str(case.get("question") or ""))
        draft_result = answer_mod.synthesize(
            llm, str(case.get("question") or ""), sections, spots=[])
        question_type = str((frame or {}).get("question_type") or "rule_explanation")
        review_applied = bool(
            frame and (args.review_scope == "all"
                       or question_type == "proposition_verification"))
        if review_applied:
            review_raw, reviewed = legalissue.review_draft_by_type(
                llm, frame or {}, evidence, draft_result.answer)
            answer = legalissue.render_reviewed_answer(frame or {}, reviewed)
            material_ids = list(dict.fromkeys(
                str(row.get("evidence_id") or "")
                for row in (reviewed or {}).get("findings") or []
                if row.get("evidence_id")))
            material_coords = _evidence_coords(evidence, material_ids)
            outcome = str((reviewed or {}).get("status") or "not_determined")
        else:
            review_raw = reviewed = None
            answer = draft_result.answer
            material_ids = [str(row["id"]) for row in evidence]
            material_coords = _coords(draft_result.refs)
            outcome = "answered" if draft_result.answerable else "not_determined"
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
            "frame": frame,
            "draft": draft_result.answer, "review_applied": review_applied,
            "draft_answerable": draft_result.answerable,
            "review_raw": review_raw, "reviewed": reviewed,
            "verdict": outcome,
            "material_basis_ids": material_ids,
            "material_basis_gold_hits": len(expected & material_coords),
            "material_basis_case_hit": bool(expected & material_coords),
            "basis_ids": material_ids,
            "basis_gold_hits": len(expected & material_coords),
            "basis_case_hit": bool(expected & material_coords),
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
                "experiment": ("typed-requirement-draft-review-v4"
                               if args.review_scope == "all"
                               else "proposition-only-draft-review-v5"),
                "suite": str(args.suite), "retrieval_source": str(args.retrieval),
                "system_model": prototype.model,
                "semantic_eval_model": "claude-sonnet-5",
                "guard_version": 2,
                "review_scope": args.review_scope,
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
                qtype = str((row.get("frame") or {}).get("question_type") or "?")
                print(f"[{position:02d}/{len(case_ids)}] {mark} {case_id} {qtype} "
                      f"ret={row['retrieval_gold_hits']}/{row['gold_total']} "
                      f"status={row['verdict']} wall={row['wall_ms']}ms", flush=True)
    print(json.dumps(summarize(rows, retrieval_run.get("summary") or {}),
                     ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
