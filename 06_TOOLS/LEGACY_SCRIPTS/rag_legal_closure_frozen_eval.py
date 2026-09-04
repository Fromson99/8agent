#!/usr/bin/env python3
"""동결된 정확/Assertion 단계에 keyword+관계 폐쇄를 붙여 51건을 평가한다."""
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
from scripts.ask_e2e_golden import _coords, _expected_article_coords  # noqa: E402
from lawrag.core.rag import general_search, index as index_mod, legal_coordinates  # noqa: E402
from lawrag.core.rag import legalclosure  # noqa: E402


def _usage(exchanges) -> dict:
    return {
        "calls": len(exchanges),
        "input_tokens": sum(int((x.usage or {}).get("input_tokens", 0)) for x in exchanges),
        "output_tokens": sum(int((x.usage or {}).get("output_tokens", 0)) for x in exchanges),
        "duration_ms": sum(int(x.dur_ms) for x in exchanges),
        "errors": sum(bool(x.error) for x in exchanges),
    }


def _summary(rows, primary_summary, assertion_summary):
    gold = sum(len(row["gold"]) for row in rows)
    final_hits = sum(g["selected"] for row in rows for g in row["gold"])
    upper_hits = sum(g["candidate_upper"] for row in rows for g in row["gold"])
    keyword_usage = {key: sum(row["keyword_usage"][key] for row in rows)
                     for key in ("calls", "input_tokens", "output_tokens",
                                 "duration_ms", "errors")}
    counts = sorted(row["selected_count"] for row in rows)
    walls = sorted(row["wall_ms"] for row in rows)
    pct = lambda values, p: values[round((len(values) - 1) * p)] if values else 0
    return {
        "cases": len(rows), "gold": gold,
        "candidate_upper_hits": upper_hits,
        "candidate_upper_recall": round(upper_hits / gold, 4) if gold else 0,
        "selected_hits": final_hits,
        "selected_recall": round(final_hits / gold, 4) if gold else 0,
        "case_hits": sum(any(g["selected"] for g in row["gold"]) for row in rows),
        "selected_count_p50": pct(counts, .5), "selected_count_p95": pct(counts, .95),
        "wall_ms_p50": pct(walls, .5), "wall_ms_p95": pct(walls, .95),
        "stage_usage": {
            "exact_structural": {key: primary_summary.get(key, 0) for key in keyword_usage},
            "assertion_tree": {key: assertion_summary.get(key, 0) for key in keyword_usage},
            "keyword": keyword_usage,
        },
        "calls": (int(primary_summary.get("calls", 0))
                  + int(assertion_summary.get("calls", 0)) + keyword_usage["calls"]),
        "input_tokens": (int(primary_summary.get("input_tokens", 0))
                         + int(assertion_summary.get("input_tokens", 0))
                         + keyword_usage["input_tokens"]),
        "output_tokens": (int(primary_summary.get("output_tokens", 0))
                          + int(assertion_summary.get("output_tokens", 0))
                          + keyword_usage["output_tokens"]),
        "errors": (int(primary_summary.get("errors", 0))
                   + int(assertion_summary.get("errors", 0))
                   + keyword_usage["errors"]),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--primary-run", type=Path, required=True)
    ap.add_argument("--assertion-run", type=Path, required=True)
    ap.add_argument("--candidate-run", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    ap.add_argument("--cap", type=int, default=20)
    ap.add_argument("--case-no", action="append", default=[])
    args = ap.parse_args()

    source = json.loads(args.run.read_text("utf-8"))
    primary_blob = json.loads(args.primary_run.read_text("utf-8"))
    assertion_blob = json.loads(args.assertion_run.read_text("utf-8"))
    candidate_blob = json.loads(args.candidate_run.read_text("utf-8"))
    cases = list(source.get("rows") or [])[:51]
    if args.case_no:
        wanted = set(args.case_no)
        cases = [case for case in cases if case.get("case_no") in wanted]
    primary = {row["case_no"]: row for row in primary_blob["rows"]}
    assertion = {row["case_no"]: row for row in assertion_blob["rows"]}
    candidate = {row["case_no"]: row for row in candidate_blob["rows"]}
    prototype = review._llm()
    if prototype is None:
        raise SystemExit("LLM 설정이 없습니다")
    index = index_mod.current().scoped(None)
    # postings/_Corpus는 지연 생성 캐시다. 병렬 worker가 동시에 최초 생성하면
    # 사전 순회 중 크기가 바뀔 수 있으므로 메인 스레드에서 한 번 완성한다.
    general_search._corpus(index)
    local = threading.local()

    def evaluate(case):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        start_log = len(llm.log)
        started = time.perf_counter()
        case_no = case["case_no"]
        p, a, broad = primary[case_no], assertion[case_no], candidate[case_no]
        terms = tuple(p.get("term_plan", {}).get("used_terms") or ())
        primary_rows = [row for item in p.get("selected") or []
                        if (row := legal_coordinates.article_branch(
                            index, item["doc_id"], item["node"], terms,
                            origin="exact-structural")) is not None]
        assertion_rows = [row for item in a.get("selected") or []
                          if (row := legal_coordinates.article_branch(
                              index, item["doc_id"], item["node"], terms,
                              origin="assertion-tree")) is not None]
        plan = general_search.extract_keywords(None, case["question"])
        search_keywords = tuple(dict.fromkeys((
            *terms, *legalclosure._context_terms(case["question"]))))
        keyword_rows, keyword_meta = legalclosure._keyword_articles(
            index, case["question"], search_keywords)
        expansion_terms = search_keywords
        closure, expansion_meta = legalclosure._supplemental_closure(
            index, legal_coordinates.merge(
                legalclosure.ASSERTION_CAP + legalclosure.KEYWORD_ARTICLES_MAX,
                keyword_rows, assertion_rows), expansion_terms)
        selected = legal_coordinates.merge(
            args.cap, primary_rows, assertion_rows, keyword_rows, closure)
        selected_public = [{"doc_id": row.doc_id, "node": row.node,
                            "doc": row.doc, "path": row.path,
                            "origin": row.origin} for row in selected]
        selected_coords = _coords(selected_public)
        broad_gold = {(g["law"], g["article"]): bool(g.get("unscoped"))
                      for g in broad.get("gold") or []}
        primary_gold = {(g["law"], g["article"]): bool(g.get("candidate"))
                        for g in p.get("gold") or []}
        expected = _expected_article_coords(case)
        gold = [{
            "law": law, "article": article,
            "candidate_upper": (primary_gold.get((law, article), False)
                                or broad_gold.get((law, article), False)),
            "selected": (law, article) in selected_coords,
        } for law, article in sorted(expected)]
        return {
            "case_no": case_no, "question": case["question"], "gold": gold,
            "term_plan": p.get("term_plan") or {},
            "keyword_plan": plan.as_dict(), "keyword": keyword_meta,
            "assertion_selected": a.get("selected") or [],
            "closure": [{"doc_id": row.doc_id, "node": row.node,
                         "doc": row.doc, "path": row.path,
                         "mandatory": row.mandatory, "terms": list(row.terms)}
                        for row in closure],
            "expansion": expansion_meta, "selected": selected_public,
            "selected_count": len(selected),
            "keyword_usage": _usage(llm.log[start_log:]),
            "wall_ms": round((time.perf_counter() - started) * 1000),
        }

    rows, order = [], {case["case_no"]: i for i, case in enumerate(cases)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, case): case for case in cases}
        for pos, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row = future.result()
            rows.append(row)
            rows.sort(key=lambda item: order[item["case_no"]])
            summary = _summary(rows, primary_blob.get("summary") or {},
                               assertion_blob.get("summary") or {})
            result = {
                "experiment": "legal-coordinate-closure-hybrid-v1",
                "source": str(args.run), "primary_run": str(args.primary_run),
                "assertion_run": str(args.assertion_run),
                "candidate_run": str(args.candidate_run),
                "model": prototype.model, "assertion_model": assertion_blob.get("model"),
                "cap": args.cap, "summary": summary, "rows": rows,
            }
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
            hits = sum(g["selected"] for g in row["gold"])
            print(f"[{pos:02d}/{len(cases)}] {row['case_no']} "
                  f"selected={hits}/{len(row['gold'])} n={row['selected_count']} "
                  f"wall={row['wall_ms']}ms", flush=True)
    print(json.dumps(_summary(rows, primary_blob.get("summary") or {},
                              assertion_blob.get("summary") or {}),
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
