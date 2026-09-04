#!/usr/bin/env python3
"""고정된 구조 탐색 결과에 IssueFrame 판정·답변을 붙여 51건을 E2E 채점한다.

검색기의 확률적 선택을 다시 실행하지 않는다. ``rag_term_explore_eval.py``가 저장한
최종 선택 좌표의 현재 코퍼스 원문을 복원하고, 질문 구조화 → 해석기 선택 → 3값 판정
→ 답변 렌더링 → 독립 의미 채점 순서만 새로 실행한다. 따라서 검색 변화와 답변 변화가
섞이지 않고, 기존 구조 탐색 51건과 정확히 같은 검색 결과에서 답변 품질을 비교한다.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import review_golden as review  # noqa: E402 — 데이터 환경을 먼저 연다
from scripts.ask_e2e_golden import (  # noqa: E402
    _coords,
    _expected_article_coords,
    _semantic_grade,
)
from lawrag.core.rag import exploration, legalissue  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402


def _usage(exchanges) -> dict[str, int]:
    return {
        "calls": len(exchanges),
        "input_tokens": sum(int((row.usage or {}).get("input_tokens", 0))
                            for row in exchanges),
        "output_tokens": sum(int((row.usage or {}).get("output_tokens", 0))
                             for row in exchanges),
        "duration_ms": sum(int(row.dur_ms) for row in exchanges),
        "errors": sum(bool(row.error) for row in exchanges),
    }


def _percentile(values, proportion: float) -> int:
    ordered = sorted(int(value) for value in values)
    if not ordered:
        return 0
    position = round((len(ordered) - 1) * proportion)
    return ordered[max(0, min(len(ordered) - 1, position))]


def _resolve_node(view, value):
    """JSON 왕복 뒤 node의 int/str 형식이 달라도 현재 트리 좌표를 찾는다."""
    if value in view.by_id:
        return value
    text = str(value)
    if text in view.by_id:
        return text
    try:
        number = int(text)
    except (TypeError, ValueError):
        return None
    return number if number in view.by_id else None


def reconstruct_evidence(index, selected: list[dict[str, Any]]) \
        -> list[dict[str, Any]]:
    """저장된 최종 선택 좌표를 그때와 같은 전체 subtree 원문으로 복원한다."""
    evidence = []
    for position, row in enumerate(selected, 1):
        doc_id = str(row.get("doc_id") or "")
        view = index.docs.get(doc_id)
        if view is None:
            continue
        node = _resolve_node(view, row.get("node"))
        if node is None:
            continue
        path = view.path(node) or str(row.get("path") or "")
        evidence.append({
            "id": f"E{position}",
            "doc_id": doc_id,
            "node": node,
            "document": view.name,
            "path": path,
            "role": str(row.get("origin") or "retrieved_final_selection"),
            "relation_reason": str(row.get("relation_reason") or ""),
            "original_text": exploration.subtree_text(view, node, cap=None),
        })
    return evidence


def _evidence_coords(evidence: list[dict[str, Any]], ids=None) \
        -> set[tuple[str, str]]:
    allowed = None if ids is None else {str(value) for value in ids}
    return _coords([
        {"doc": row.get("document"), "path": row.get("path")}
        for row in evidence
        if allowed is None or str(row.get("id")) in allowed
    ])


def _add_usage(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    names = ("calls", "input_tokens", "output_tokens", "duration_ms", "errors")
    return {name: sum(int((row.get(key) or {}).get(name, 0)) for row in rows)
            for name in names}


def summarize(rows: list[dict[str, Any]], retrieval_summary: dict[str, Any]) \
        -> dict[str, Any]:
    successful = [row for row in rows if not row.get("error")]
    product = _add_usage(successful, "usage")
    evaluator = _add_usage(successful, "semantic_usage")
    retrieval = {
        key: int(retrieval_summary.get(key) or 0)
        for key in ("calls", "input_tokens", "output_tokens", "duration_ms", "errors")
    }
    verdicts = Counter(str(row.get("verdict") or "missing") for row in successful)
    question_types = Counter(
        str((row.get("frame") or {}).get("question_type") or "missing")
        for row in successful)
    hit_rows = [row for row in successful if row.get("retrieval_case_hit")]
    miss_rows = [row for row in successful if not row.get("retrieval_case_hit")]
    empty_rows = [row for row in successful if not row.get("evidence")]

    def semantic_count(items):
        return sum(bool(row.get("semantic_correct")) for row in items)

    system_total = {name: retrieval[name] + product[name]
                    for name in retrieval}
    return {
        "cases": len(rows),
        "completed": len(successful),
        "failed": len(rows) - len(successful),
        "retrieval": dict(retrieval_summary),
        "answer": {
            "semantic_correct": semantic_count(successful),
            "semantic_accuracy": round(semantic_count(successful) / len(successful), 4)
            if successful else 0,
            "conclusion_correct": sum(bool((row.get("semantic_grade") or {}).get(
                "conclusion_correct")) for row in successful),
            "materially_complete": sum(bool((row.get("semantic_grade") or {}).get(
                "materially_complete")) for row in successful),
            "no_material_error": sum(bool((row.get("semantic_grade") or {}).get(
                "no_material_error")) for row in successful),
            "retrieval_case_hits": len(hit_rows),
            "semantic_correct_when_retrieval_hit": semantic_count(hit_rows),
            "semantic_accuracy_when_retrieval_hit": round(
                semantic_count(hit_rows) / len(hit_rows), 4) if hit_rows else 0,
            "retrieval_case_misses": len(miss_rows),
            "semantic_correct_when_retrieval_miss": semantic_count(miss_rows),
            "empty_evidence_cases": len(empty_rows),
            "semantic_correct_with_empty_evidence": semantic_count(empty_rows),
            "material_basis_case_hits": sum(bool(row.get("material_basis_case_hit"))
                                            for row in successful),
            "material_basis_gold_hits": sum(
                int(row.get("material_basis_gold_hits") or 0)
                for row in successful),
            "controlling_basis_case_hits": sum(bool(row.get("basis_case_hit"))
                                               for row in successful),
            "controlling_basis_gold_hits": sum(int(row.get("basis_gold_hits") or 0)
                                               for row in successful),
            "basis_gold_total": sum(int(row.get("gold_total") or 0)
                                    for row in successful),
            "verdicts": dict(sorted(verdicts.items())),
            "question_types": dict(sorted(question_types.items())),
        },
        "cost": {
            "retrieval_frozen": retrieval,
            "issue_frame_and_judge": product,
            "system_end_to_end": system_total,
            "semantic_evaluator_excluded_from_system": evaluator,
        },
        "latency": {
            "downstream_product_wall_ms_p50": _percentile(
                (row.get("product_wall_ms", 0) for row in successful), .50),
            "downstream_product_wall_ms_p95": _percentile(
                (row.get("product_wall_ms", 0) for row in successful), .95),
            "system_end_to_end_wall_ms_p50": _percentile(
                (int(row.get("retrieval_wall_ms") or 0)
                 + int(row.get("product_wall_ms") or 0) for row in successful), .50),
            "system_end_to_end_wall_ms_p95": _percentile(
                (int(row.get("retrieval_wall_ms") or 0)
                 + int(row.get("product_wall_ms") or 0) for row in successful), .95),
            "including_evaluator_wall_ms_p50": _percentile(
                (row.get("wall_ms", 0) for row in successful), .50),
            "including_evaluator_wall_ms_p95": _percentile(
                (row.get("wall_ms", 0) for row in successful), .95),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    retrieval_run = json.loads(args.retrieval.read_text(encoding="utf-8"))
    suite_by_id = {str(row["id"]): row for row in suite.get("cases") or []}
    retrieval_by_id = {
        str(row["case_no"]): row for row in retrieval_run.get("rows") or []
    }
    wanted = list(dict.fromkeys(
        case_id.strip()
        for value in args.case_id
        for case_id in value.split(",")
        if case_id.strip()
    ))
    case_ids = wanted or [str(row["id"]) for row in suite.get("cases") or []]
    missing = [case_id for case_id in case_ids
               if case_id not in suite_by_id or case_id not in retrieval_by_id]
    if missing:
        raise SystemExit("suite 또는 retrieval에 없는 case: " + ", ".join(missing))

    prototype = review._llm()
    if prototype is None:
        raise SystemExit("LLM 설정이 없습니다")
    index = index_mod.current()
    local = threading.local()

    def evaluate(case_id: str) -> dict[str, Any]:
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        case = suite_by_id[case_id]
        retrieved_row = retrieval_by_id[case_id]
        evidence = reconstruct_evidence(index, retrieved_row.get("selected") or [])
        expected = _expected_article_coords(case)
        retrieved_coords = _evidence_coords(evidence)
        product_log_start = len(llm.log)
        started = time.perf_counter()
        product_started = time.perf_counter()
        frame = legalissue.structure_question(llm, str(case.get("question") or ""))
        raw = legalissue.judge_evidence(llm, frame or {}, evidence) if frame else None
        judgment = legalissue.verify_judgment(raw, evidence, frame)
        answer = legalissue.render_answer(frame or {}, judgment)
        product_wall_ms = round((time.perf_counter() - product_started) * 1000)
        product_exchanges = list(llm.log)[product_log_start:]
        semantic, semantic_usage = _semantic_grade(llm, case, answer)
        basis_ids = (judgment or {}).get("controlling_evidence_ids") or []
        basis_coords = _evidence_coords(evidence, basis_ids)
        material_ids = list(dict.fromkeys(
            str(row.get("evidence_id") or "")
            for row in (judgment or {}).get("rule_findings") or []
            if row.get("evidence_id")
        ))
        material_coords = _evidence_coords(evidence, material_ids)
        return {
            "case_no": case_id,
            "question": str(case.get("question") or ""),
            "reference_answer": str(case.get("reference_answer") or ""),
            "gold": list(case.get("expected_articles") or []),
            "gold_total": len(expected),
            "retrieval_gold_hits": len(expected & retrieved_coords),
            "retrieval_case_hit": bool(expected & retrieved_coords),
            "selected": list(retrieved_row.get("selected") or []),
            "evidence": [{key: value for key, value in row.items()
                          if key != "original_text"} | {
                              "chars": len(str(row.get("original_text") or ""))
                          } for row in evidence],
            "frame": frame,
            "active_interpreters": legalissue.interpreter_instructions(frame or {}),
            "judgment_raw": raw,
            "judgment": judgment,
            "verdict": str((judgment or {}).get("verdict") or "not_determined"),
            "basis_ids": list(map(str, basis_ids)),
            "basis_gold_hits": len(expected & basis_coords),
            "basis_case_hit": bool(expected & basis_coords),
            "material_basis_ids": material_ids,
            "material_basis_gold_hits": len(expected & material_coords),
            "material_basis_case_hit": bool(expected & material_coords),
            "answer": answer,
            "semantic_correct": bool((semantic or {}).get("correct")),
            "semantic_grade": semantic,
            "semantic_reason": str((semantic or {}).get("reason") or "")[:500],
            "usage": _usage(product_exchanges),
            "semantic_usage": semantic_usage,
            "retrieval_usage": dict(retrieved_row.get("usage") or {}),
            "retrieval_wall_ms": int(retrieved_row.get("wall_ms") or 0),
            "product_wall_ms": product_wall_ms,
            "wall_ms": round((time.perf_counter() - started) * 1000),
        }

    rows: list[dict[str, Any]] = []
    order = {case_id: position for position, case_id in enumerate(case_ids)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, case_id): case_id for case_id in case_ids}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # 부분 결과를 남겨 실패 사례를 재현할 수 있게 한다.
                row = {"case_no": case_id,
                       "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            rows.sort(key=lambda item: order[item["case_no"]])
            result = {
                "experiment": "frozen-structural-retrieval-legal-issue-answer-v1",
                "suite": str(args.suite),
                "retrieval_source": str(args.retrieval),
                "system_model": prototype.model,
                "semantic_eval_model": "claude-sonnet-5",
                "summary": summarize(rows, retrieval_run.get("summary") or {}),
                "rows": rows,
            }
            args.out.write_text(
                json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
            if row.get("error"):
                print(f"[{position:02d}/{len(case_ids)}] {case_id} ERROR "
                      f"{row['error']}", flush=True)
            else:
                mark = "○" if row["semantic_correct"] else "✗"
                print(f"[{position:02d}/{len(case_ids)}] {mark} {case_id} "
                      f"ret={row['retrieval_gold_hits']}/{row['gold_total']} "
                      f"basis={row['material_basis_gold_hits']}/{row['gold_total']} "
                      f"verdict={row['verdict']} calls={row['usage']['calls']} "
                      f"wall={row['wall_ms']}ms", flush=True)

    print(json.dumps(summarize(rows, retrieval_run.get("summary") or {}),
                     ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
