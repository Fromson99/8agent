#!/usr/bin/env python3
"""저장 골든에서 anchor 범위 교집합→구조 확장 본문 선택을 평가한다."""

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

from scripts import review_golden as review  # noqa: E402 — 데이터 경로 설정
from lawrag.core.rag import index as index_mod, termexplore  # noqa: E402
from scripts.ask_e2e_golden import _coords, _expected_article_coords  # noqa: E402


def _usage(exchanges) -> dict:
    return {
        "calls": len(exchanges),
        "input_tokens": sum(int((row.usage or {}).get("input_tokens", 0))
                            for row in exchanges),
        "output_tokens": sum(int((row.usage or {}).get("output_tokens", 0))
                             for row in exchanges),
        "duration_ms": sum(int(row.dur_ms) for row in exchanges),
        "errors": sum(bool(row.error) for row in exchanges),
    }


def _summary(rows: list[dict]) -> dict:
    gold = sum(len(row["gold"]) for row in rows)
    candidate_hits = sum(item["candidate"] for row in rows for item in row["gold"])
    mandatory_hits = sum(item["mandatory"] for row in rows for item in row["gold"])
    hits = sum(item["selected"] for row in rows for item in row["gold"])
    available = sum(item["available"] for row in rows for item in row["gold"])
    available_hits = sum(item["selected"] and item["available"]
                         for row in rows for item in row["gold"])

    def percentile(values, p):
        values = sorted(int(value) for value in values)
        if not values:
            return 0
        return values[max(0, min(len(values) - 1,
                                 round((len(values) - 1) * p)))]

    return {
        "cases": len(rows), "gold": gold,
        "candidate_hits": candidate_hits,
        "candidate_recall": round(candidate_hits / gold, 4) if gold else 0,
        "mandatory_hits": mandatory_hits,
        "mandatory_recall": round(mandatory_hits / gold, 4) if gold else 0,
        "selected_hits": hits,
        "selected_recall": round(hits / gold, 4) if gold else 0,
        "available_gold": available, "unavailable_gold": gold - available,
        "available_selected_hits": available_hits,
        "available_selected_recall": round(available_hits / available, 4)
        if available else 0,
        "case_hits": sum(any(item["selected"] for item in row["gold"])
                         for row in rows),
        "candidate_case_hits": sum(any(item["candidate"] for item in row["gold"])
                                   for row in rows),
        "calls": sum(row["usage"]["calls"] for row in rows),
        "input_tokens": sum(row["usage"]["input_tokens"] for row in rows),
        "output_tokens": sum(row["usage"]["output_tokens"] for row in rows),
        "duration_ms": sum(row["usage"]["duration_ms"] for row in rows),
        "errors": sum(row["usage"]["errors"] for row in rows),
        "wall_ms_p50": percentile((row["wall_ms"] for row in rows), .50),
        "wall_ms_p95": percentile((row["wall_ms"] for row in rows), .95),
        "anchor_branches_p50": percentile(
            (row["anchor_candidate_branches"] for row in rows), .50),
        "routed_branches_p50": percentile(
            (row["candidate_branches"] for row in rows), .50),
        "scoped_branches_p50": percentile(
            (row["scoped_candidate_branches"] for row in rows), .50),
        "seed_pool_branches_p50": percentile(
            (row["seed_pool_branches"] for row in rows), .50),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case-no", action="append")
    parser.add_argument("--limit", type=int, default=51)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--cap", type=int, default=12,
                        help="최종 조문 상한(기본 12; 후보 상한과 별개)")
    args = parser.parse_args()

    source = json.loads(args.run.read_text(encoding="utf-8"))
    pool_rows = (source.get("rows") or [])[:max(0, args.limit)]
    wanted = set(args.case_no or ())
    cases = ([row for row in pool_rows if row.get("case_no") in wanted]
             if wanted else pool_rows)
    if wanted:
        missing = wanted.difference(row.get("case_no") for row in cases)
        if missing:
            raise SystemExit(f"없는 case_no: {', '.join(sorted(missing))}")
    prototype = review._llm()
    if prototype is None:
        raise SystemExit("LLM 설정이 없습니다")
    index = index_mod.current()
    available_coords = set()
    for view in index.docs.values():
        for node in view.by_id:
            available_coords.update(_coords([
                {"doc": view.name, "path": view.path(node)}]))
    local = threading.local()

    def evaluate(case):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        start_log = len(llm.log)
        started = time.perf_counter()
        sections, meta = termexplore.retrieve(
            index, str(case.get("question") or ""), llm=llm, cap=args.cap)
        selected = _coords(sections)
        candidates = _coords(meta.get("review_candidates") or [])
        mandatory = _coords([row for row in meta.get("review_candidates") or []
                             if row.get("mandatory")])
        expected = _expected_article_coords(case)
        return {
            "case_no": case.get("case_no"), "question": case.get("question"),
            "gold": [{"law": law, "article": article,
                      "candidate": (law, article) in candidates,
                      "mandatory": (law, article) in mandatory,
                      "selected": (law, article) in selected,
                      "available": (law, article) in available_coords}
                     for law, article in sorted(expected)],
            "term_plan": meta["term_plan"],
            "anchor_candidate_branches": meta["anchor_candidate_branches"],
            "anchor_candidate_documents": meta["anchor_candidate_documents"],
            "candidate_branches": meta["candidate_branches"],
            "candidate_documents": meta["candidate_documents"],
            "selected_documents": meta["selected_documents"],
            "document_scoped_branches": meta["document_scoped_branches"],
            "scoped_candidate_branches": meta["scoped_candidate_branches"],
            "seed_pool_branches": meta["seed_pool_branches"],
            "seed_mode": meta["seed_mode"],
            "intersection": meta["intersection"],
            "scoped_intersection": meta["scoped_intersection"],
            "seeds": meta["seeds"], "expansion": meta["expansion"],
            "structure": meta["structure"],
            "review_candidates": meta["review_candidates"],
            "mandatory_candidates": meta["mandatory_candidates"],
            "selected": meta["selected"], "selection": meta["selection"],
            "usage": _usage(llm.log[start_log:]),
            "wall_ms": round((time.perf_counter() - started) * 1000),
        }

    rows = []
    order = {case.get("case_no"): pos for pos, case in enumerate(cases)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, case): case for case in cases}
        for pos, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row = future.result()
            rows.append(row)
            rows.sort(key=lambda item: order[item["case_no"]])
            result = {
                "experiment": "legal-coordinate-closure-mandatory-evidence-v3",
                "source": str(args.run), "model": prototype.model,
                "cap": args.cap,
                "summary": _summary(rows), "rows": rows,
            }
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
            hits = sum(item["selected"] for item in row["gold"])
            print(f"[{pos:02d}/{len(cases)}] {row['case_no']} "
                  f"candidate={sum(item['candidate'] for item in row['gold'])}/"
                  f"{len(row['gold'])} selected={hits}/{len(row['gold'])} "
                  f"terms={row['term_plan']['terms']} "
                  f"branches={row['anchor_candidate_branches']}→"
                  f"{row['scoped_candidate_branches']}→{row['seed_pool_branches']} "
                  f"calls={row['usage']['calls']} wall={row['wall_ms']}ms",
                  flush=True)
    print(json.dumps(_summary(rows), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
