#!/usr/bin/env python3
"""51건 회수율을 corpus→후보→최종근거→답변입력 선택률과 함께 감사한다."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_ARTICLE = re.compile(r"^제\s*\d+(?:-\d+)?조(?:의\s*\d+)?$")


def ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _percentile(values: list[int], fraction: float) -> int:
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else 0


def distribution(values: list[int]) -> dict:
    return {
        "min": min(values, default=0),
        "p50": round(statistics.median(values), 3) if values else 0,
        "p95": _percentile(values, .95),
        "max": max(values, default=0),
        "mean": round(statistics.mean(values), 3) if values else 0,
        "sum": sum(values),
    }


def policy_selectivity(policy: dict, *, coordinate_universe: int,
                       document_universe: int) -> dict:
    coordinates = policy.get("candidate_coordinates") or {}
    documents = policy.get("documents") or {}
    return {
        **policy,
        "coordinate_universe": coordinate_universe,
        "coordinate_selectivity": {
            key: ratio(float(coordinates.get(key) or 0), coordinate_universe)
            for key in ("min", "median", "p95", "max", "mean")
        },
        "document_universe": document_universe,
        "document_selectivity": {
            key: ratio(float(documents.get(key) or 0), document_universe)
            for key in ("min", "median", "p95", "max", "mean")
        },
    }


def retrieval_selectivity(retrieval: dict, *, variant: str,
                          article_universe: int, article_chars: int) -> dict:
    rows = list(retrieval.get("rows") or [])
    values = [(row.get("variants") or {}).get(variant) or {} for row in rows]
    counts = [int(value.get("selected_count") or 0) for value in values]
    chars = [int(value.get("body_chars") or 0) for value in values]
    coordinates = {
        (str(item.get("doc_id") or ""), item.get("node"))
        for value in values for item in value.get("selected") or []
    }
    documents = {doc_id for doc_id, _ in coordinates}
    summary = (retrieval.get("summary") or {}).get(variant) or {}
    count_dist, char_dist = distribution(counts), distribution(chars)
    return {
        "variant": variant,
        "cases": len(values),
        "final_cap": int((retrieval.get("contract") or {}).get("final_cap") or 0),
        "gold_articles": int(summary.get("gold") or 0),
        "gold_hits": int(summary.get("selected_hits") or 0),
        "gold_recall": float(summary.get("selected_recall") or 0),
        "article_universe": article_universe,
        "selected_articles_per_query": count_dist,
        "article_selectivity_per_query": {
            key: ratio(float(count_dist[key]), article_universe)
            for key in ("min", "p50", "p95", "max", "mean")
        },
        "article_chars_universe": article_chars,
        "selected_body_chars_per_query": char_dist,
        "body_char_selectivity_per_query": {
            key: ratio(float(char_dist[key]), article_chars)
            for key in ("min", "p50", "p95", "max", "mean")
        },
        "suite_total_presentations": sum(counts),
        "suite_unique_selected_articles": len(coordinates),
        "suite_unique_selected_share": ratio(len(coordinates), article_universe),
        "suite_unique_selected_documents": len(documents),
    }


def navigation_exposure(primary: dict, assertion: dict) -> dict:
    primary_rows = list(primary.get("rows") or [])
    assertion_by_case = {str(row.get("case_no") or ""): row
                         for row in assertion.get("rows") or []}
    primary_options, primary_calls = [], []
    assertion_items, assertion_calls = [], []
    combined_items, combined_calls = [], []
    for row in primary_rows:
        case_id = str(row.get("case_no") or "")
        audits = list(row.get("selection") or [])
        p_options = sum(int(value.get("option_count") or 0) for value in audits)
        p_calls = len(audits)
        tree = (assertion_by_case.get(case_id) or {}).get("tree") or {}
        a_items = sum(int(tree.get(key) or 0)
                      for key in ("families", "documents", "provisions"))
        a_calls = int(tree.get("calls") or 0)
        primary_options.append(p_options); primary_calls.append(p_calls)
        assertion_items.append(a_items); assertion_calls.append(a_calls)
        combined_items.append(p_options + a_items); combined_calls.append(p_calls + a_calls)
    return {
        "cases": len(primary_rows),
        "exact_structural_recorded_option_slots_per_query": distribution(primary_options),
        "exact_structural_recorded_navigation_calls_per_query": distribution(primary_calls),
        "exact_structural_all_llm_calls": int((primary.get("summary") or {}).get("calls") or 0),
        "assertion_tree_recorded_menu_items_per_query": distribution(assertion_items),
        "assertion_tree_recorded_navigation_calls_per_query": distribution(assertion_calls),
        "combined_recorded_menu_item_exposures_per_query": distribution(combined_items),
        "combined_recorded_navigation_calls_per_query": distribution(combined_calls),
        "note": ("option/menu item 노출 합계는 계층별 반복 노출을 포함하며 unique corpus "
                 "선택률이 아니다. broad candidate 전체를 한 prompt에 넣지 않는다."),
    }
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--structure-store", type=Path, default=ROOT / "data/structure")
    parser.add_argument("--glossary-store", type=Path, default=ROOT / "data/glossary.json")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--answer", type=Path, required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    os.environ["STRUCTURE_STORE"] = str(args.structure_store.resolve())
    os.environ["GLOSSARY_STORE"] = str(args.glossary_store.resolve())

    from lawrag.core.rag import conceptfirst, exploration, index as index_mod  # noqa: E402
    from lawrag.core.rag import legal_coordinates  # noqa: E402

    index = index_mod.current()
    scoped = index.scoped(None)
    current_ids = set(scoped.scope or scoped.docs)
    current_views = [view for doc_id, view in index.docs.items() if doc_id in current_ids]
    articles = [
        (view, node.get("id")) for view in current_views for node in view.nodes
        if _ARTICLE.fullmatch(str(node.get("surface") or "").strip())
    ]
    article_chars = sum(len(legal_coordinates.subtree_text(view, node, cap=None))
                        for view, node in articles)

    registry = conceptfirst.load_registry()
    assertion_coordinates = {
        (str(assertion.source.get("doc_id") or ""), assertion.source.get("node"))
        for assertion in registry.active_assertions
    }
    assertion_coordinates = {
        (doc_id, node) for doc_id, node in assertion_coordinates
        if doc_id in index.docs and node in index.docs[doc_id].by_id
    }
    assertion_roots = {
        (doc_id, exploration.selection_root(index.docs[doc_id], node))
        for doc_id, node in assertion_coordinates
    }
    assertion_documents = {doc_id for doc_id, _ in assertion_coordinates}

    candidate = json.loads(args.candidate.read_text("utf-8"))
    retrieval = json.loads(args.retrieval.read_text("utf-8"))
    answer = json.loads(args.answer.read_text("utf-8"))
    frozen_baseline = json.loads(Path(retrieval["baseline"]).read_text("utf-8"))
    primary_navigation = json.loads(Path(frozen_baseline["primary_run"]).read_text("utf-8"))
    assertion_navigation = json.loads(Path(frozen_baseline["assertion_run"]).read_text("utf-8"))
    candidate_summary = candidate.get("summary") or {}
    policies = {
        name: policy_selectivity(
            policy, coordinate_universe=len(assertion_coordinates),
            document_universe=len(assertion_documents))
        for name, policy in (candidate_summary.get("policies") or {}).items()
    }
    candidate_rows = list(candidate.get("rows") or [])
    for name, policy in policies.items():
        if name == "broad_or":
            total_presentations = sum(int(row.get("candidate_coordinates") or 0)
                                      for row in candidate_rows)
        else:
            total_presentations = sum(int(((row.get("policies") or {}).get(name) or {})
                                          .get("candidate_coordinates") or 0)
                                      for row in candidate_rows)
        policy["suite_total_candidate_presentations"] = total_presentations
        policy["gold_hit_density_lower_bound"] = ratio(
            int(policy.get("candidate_hits") or 0), total_presentations)
        policy["density_note"] = "gold set이 불완전하므로 precision이 아니라 lower bound"
    final = retrieval_selectivity(
        retrieval, variant=args.variant, article_universe=len(articles),
        article_chars=article_chars)
    answer_summary = (answer.get("summary") or {}).get(args.variant) or {}
    product_cost = answer_summary.get("product_cost") or {}
    calls = int(product_cost.get("calls") or 0)
    final["answer_product_input"] = {
        "calls": calls,
        "input_tokens": int(product_cost.get("input_tokens") or 0),
        "input_tokens_per_call_mean": round(
            int(product_cost.get("input_tokens") or 0) / calls, 3) if calls else 0,
        "note": "system prompt와 질문을 포함한 실제 API input; evidence-only token은 아님",
    }
    final["gold_hit_density_lower_bound"] = ratio(
        final["gold_hits"], final["suite_total_presentations"])
    final["density_note"] = "gold set이 불완전하므로 precision이 아니라 lower bound"

    result = {
        "experiment": "retrieval-selectivity-funnel-v1",
        "contract": {
            "read_only_audit": True,
            "gold_used_for_selection": False,
            "main_wiring_changed": False,
            "canonical_changed": False,
            "candidate_denominator": "active assertion source coordinates",
            "final_denominator": "current article roots",
        },
        "sources": {
            "candidate": str(args.candidate), "retrieval": str(args.retrieval),
            "answer": str(args.answer), "structure_store": str(args.structure_store),
        },
        "corpus": {
            "all_documents": len(index.docs),
            "current_documents": len(current_views),
            "current_nodes": sum(len(view.nodes) for view in current_views),
            "current_blocks": sum(len(view.blocks) for view in current_views),
            "current_article_roots": len(articles),
            "current_article_subtree_chars": article_chars,
            "index_entries_current_scope": len(scoped.entries),
        },
        "assertion_candidate_universe": {
            "active_assertions": len(registry.active_assertions),
            "unique_source_coordinates": len(assertion_coordinates),
            "unique_selection_roots": len(assertion_roots),
            "documents": len(assertion_documents),
            "artifact_max_candidate_documents": int(
                ((candidate_summary.get("documents") or {}).get("max") or 0)),
            "snapshot_note": "candidate artifact와 현재 registry가 달라질 수 있어 분모를 함께 저장",
        },
        "candidate_stage": {
            "gold": int(candidate_summary.get("gold") or 0),
            "policies": policies,
        },
        "llm_navigation_exposure": navigation_exposure(
            primary_navigation, assertion_navigation),
        "final_answer_evidence": final,
        "interpretation": {
            "recall_without_selectivity_is_insufficient": True,
            "candidate_stage_touches_most_documents": (
                (policies.get("broad_or") or {}).get("document_selectivity", {})
                .get("median", 0) > .5),
            "final_evidence_is_small_fraction_of_article_universe": (
                final["article_selectivity_per_query"]["mean"] < .01),
            "do_not_compare_candidate_and_final_counts_without_denominator": True,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
