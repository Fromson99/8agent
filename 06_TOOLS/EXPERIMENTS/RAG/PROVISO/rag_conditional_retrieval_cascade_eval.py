#!/usr/bin/env python3
"""family-top8→조건부 broad cascade와 Wiki 검색계획을 51건에서 shadow 평가한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import time


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.rag import assertionfirst, conceptfirst, index as index_mod, wikictx  # noqa: E402
from lawrag.research.experiments.haiku_legal_methods import HAIKU_MODEL  # noqa: E402
from scripts import review_golden as review  # noqa: E402
from scripts.rag_assertion_first_diagnose import (  # noqa: E402
    _case, _coordinate_articles, _distribution,
)
from scripts.rag_legal_issue_e2e_eval import _usage  # noqa: E402


def fallback_reasons(row: dict) -> list[str]:
    """Gold와 무관한 fail-open 신호만 사용한다."""
    reasons = []
    if str(row.get("scope_kind") or "") in {"", "none"}:
        reasons.append("no_resolved_structure_scope")
    if row.get("unresolved_locators"):
        reasons.append("unresolved_locator")
    family = (row.get("policies") or {}).get("family_top8") or {}
    if int(family.get("candidate_coordinates") or 0) == 0:
        reasons.append("empty_family_candidates")
    return reasons


def cascade_row(row: dict) -> dict:
    reasons = fallback_reasons(row)
    route = "broad_or" if reasons else "family_top8"
    policy = (row.get("policies") or {}).get(route) or {}
    gold = list(row.get("gold") or [])
    return {
        "case_no": row.get("case_no"),
        "route": route,
        "fallback_reasons": reasons,
        "candidate_coordinates": int(policy.get("candidate_coordinates") or 0),
        "documents": int((policy.get("hierarchy") or {}).get("documents") or 0),
        "selection_roots": int(
            (policy.get("hierarchy") or {}).get("selection_roots") or 0),
        "lossless_pages_upper_bound": int(
            (policy.get("hierarchy") or {}).get("lossless_pages_upper_bound") or 0),
        "gold_hits": sum(bool((item.get("policy_hits") or {}).get(route))
                         for item in gold),
        "gold": len(gold),
    }


def summarize(rows: list[dict]) -> dict:
    total_gold = sum(int(row.get("gold") or 0) for row in rows)
    hits = sum(int(row.get("gold_hits") or 0) for row in rows)
    widths = [int(row.get("candidate_coordinates") or 0) for row in rows]
    documents = [int(row.get("documents") or 0) for row in rows]
    roots = [int(row.get("selection_roots") or 0) for row in rows]
    pages = [int(row.get("lossless_pages_upper_bound") or 0) for row in rows]
    return {
        "cases": len(rows), "gold": total_gold, "gold_hits": hits,
        "gold_recall": round(hits / total_gold, 4) if total_gold else 0,
        "broad_fallback_cases": sum(row.get("route") == "broad_or" for row in rows),
        "candidate_coordinates": _distribution(widths),
        "documents": _distribution(documents),
        "selection_roots": _distribution(roots),
        "lossless_pages_upper_bound": _distribution(pages),
        "suite_candidate_presentations": sum(widths),
        "suite_document_presentations": sum(documents),
    }


def _all_article_sets(index, registry):
    canonical = _coordinate_articles(index, {
        (str(item.source.get("doc_id") or ""), item.source.get("node"))
        for item in registry.active_assertions
    })
    corpus = _coordinate_articles(index, {
        (doc_id, node) for doc_id, view in index.docs.items() for node in view.by_id
    })
    return corpus, canonical


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--baseline-candidates", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--skip-wiki", action="store_true")
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text("utf-8"))
    baseline = json.loads(args.baseline_candidates.read_text("utf-8"))
    baseline_rows = [cascade_row(row) for row in baseline.get("rows") or []]
    result = {
        "experiment": "conditional-retrieval-cascade-and-wiki-plan-shadow-v1",
        "contract": {
            "main_wiring_changed": False, "canonical_changed": False,
            "gold_used_for_routing": False, "wiki_answer_context": False,
            "wiki_role": "search planning and terminology normalization only",
            "all_llm_models": HAIKU_MODEL,
        },
        "sources": {"suite": str(args.suite),
                    "baseline_candidates": str(args.baseline_candidates)},
        "baseline_cascade": {"summary": summarize(baseline_rows),
                             "rows": baseline_rows},
    }
    if args.skip_wiki:
        result["wiki_planning"] = {"skipped": True}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
        return 0

    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU_MODEL:
        raise SystemExit("Wiki 검색계획 LLM은 Haiku여야 합니다")
    llm = prototype
    index = index_mod.current()
    registry = conceptfirst.load_registry()
    finder = assertionfirst.current(registry)
    corpus_articles, canonical_articles = _all_article_sets(index, registry)
    rows = []
    started = time.perf_counter()
    for position, case in enumerate(suite.get("cases") or [], 1):
        case_id = str(case.get("id") or "")
        question = str(case.get("question") or "")
        log0 = len(llm.log)
        picks = wikictx.spot_llm(llm, question, sections=None, index=index)
        planner_failed = picks is None
        safe_picks = list(picks or [])
        expanded = wikictx.expand_query(question, safe_picks)
        source = dict(case)
        source["case_no"] = case_id
        source["question"] = expanded
        diagnosed = _case(
            index, corpus_articles, canonical_articles, finder, registry, source)
        diagnosed["question"] = question
        diagnosed["expanded_query"] = expanded
        diagnosed["wiki_picks"] = [{
            "slug": pick.get("slug"), "title": pick.get("title"),
            "why": pick.get("why"), "probe": pick.get("probe"),
        } for pick in safe_picks]
        diagnosed["planner_failed"] = planner_failed
        diagnosed["planner_usage"] = _usage(list(llm.log)[log0:])
        item = cascade_row(diagnosed)
        item.update({
            "expanded_query": expanded,
            "query_changed": expanded != question,
            "wiki_picks": diagnosed["wiki_picks"],
            "planner_failed": planner_failed,
            "planner_usage": diagnosed["planner_usage"],
        })
        rows.append(item)
        result["wiki_planning"] = {
            "summary": summarize(rows), "rows": rows,
            "planner_usage": {
                key: sum(int((row.get("planner_usage") or {}).get(key) or 0)
                         for row in rows)
                for key in ("calls", "input_tokens", "output_tokens",
                            "duration_ms", "errors")
            },
            "query_changed_cases": sum(bool(row.get("query_changed")) for row in rows),
            "planner_failed_cases": sum(bool(row.get("planner_failed")) for row in rows),
        }
        result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"[{position:02d}/{len(suite.get('cases') or [])}] {case_id} "
              f"route={item['route']} gold={item['gold_hits']}/{item['gold']} "
              f"wiki={len(safe_picks)}", flush=True)

    print(json.dumps({
        "baseline": result["baseline_cascade"]["summary"],
        "wiki": result["wiki_planning"]["summary"],
        "planner_usage": result["wiki_planning"]["planner_usage"],
    }, ensure_ascii=False, indent=1))
    return 1 if result["wiki_planning"]["planner_usage"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
