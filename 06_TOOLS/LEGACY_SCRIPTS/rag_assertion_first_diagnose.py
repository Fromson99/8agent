#!/usr/bin/env python3
"""51개 저장 질문에서 임베딩 없는 Assertion-first 시작점 회수율을 잰다.

답변 생성과 LLM 선택은 호출하지 않는다. 질문 원문에서 DB 역매칭된 명시
문서·조문을 하드 스코프로 삼고, canonical Concept/query_cue의 정확 구·형태소만
Assertion 간선을 따라간다. 골든은 색인이나 순위에 넣지 않고 사후 채점에만 쓴다.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.domain_graph import spanparts  # noqa: E402
from lawrag.core.rag import assertionfirst, conceptfirst, exploration  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from scripts.ask_e2e_golden import _coords, _expected_article_coords  # noqa: E402


PAGE_SIZE = assertionfirst.NAVIGATION_PAGE_SIZE
GATE_POLICIES = ("broad_or", "balanced_join", "strict_join")
POLICIES = (*GATE_POLICIES, "family_top8")


def _coordinate_articles(index, coordinates) -> set[tuple[str, str]]:
    rows = []
    for doc_id, node in coordinates:
        view = index.docs.get(doc_id)
        if view is None or node not in view.by_id:
            continue
        rows.append({"doc": view.name, "path": view.path(node) or view.name})
    return _coords(rows)


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    return sorted(values)[math.ceil(len(values) * fraction) - 1]


def _distribution(values: list[int]) -> dict:
    return {
        "min": min(values, default=0),
        "median": statistics.median(values) if values else 0,
        "p95": _percentile(values, 0.95),
        "max": max(values, default=0),
        "mean": round(statistics.mean(values), 2) if values else 0,
    }


def _hierarchy(index, coordinates) -> dict:
    by_doc: dict[str, set[object]] = {}
    for doc_id, node in coordinates:
        view = index.docs.get(doc_id)
        if view is None or node not in view.by_id:
            continue
        by_doc.setdefault(doc_id, set()).add(exploration.selection_root(view, node))
    roots = sum(len(rows) for rows in by_doc.values())
    # 모든 후보를 탈락 없이 작은 모델에 보여준다는 보수적 상한이다. 실제로는
    # 1단계에서 고른 문서의 2단계 페이지만 연다.
    exhaustive_pages = math.ceil(len(by_doc) / PAGE_SIZE) + sum(
        math.ceil(len(rows) / PAGE_SIZE) for rows in by_doc.values())
    return {
        "documents": len(by_doc),
        "selection_roots": roots,
        "max_roots_in_document": max((len(rows) for rows in by_doc.values()), default=0),
        "lossless_pages_upper_bound": exhaustive_pages,
    }


def _admitted(hit, finder, registry, policy: str) -> bool:
    if policy == "broad_or":
        return True
    assertion = registry.active_assertions_by_id[hit.assertion_id]
    direct = [row for row in hit.evidence
              if row["kind"] not in {
                  "concept-relation", "facet-match", "facet-conflict"}]
    concept_ids = {str(row.get("concept_id")) for row in direct
                   if row.get("concept_id")}
    roles = {role for role, ids in assertion.roles.items()
             if concept_ids.intersection(ids)}
    exact_cues = [row for row in direct if row["kind"] == "cue-exact"
                  and len(row["value"]) >= 4]
    exact_concepts = [row for row in direct if row["kind"] == "concept-exact"
                      and len(row["value"]) >= 3 and row.get("concept_id")]
    cue_tokens = [row for row in direct if row["kind"] == "cue-token"]

    if policy == "balanced_join":
        cue_exact_df, concept_degree, cue_token_df = 16, 8, 80
        role_join = len(roles) >= 2
    else:
        cue_exact_df, concept_degree, cue_token_df = 4, 4, 30
        role_join = len(roles) >= 2 and "PREDICATE" in roles
    exact_cue_anchor = any(
        len(finder.cue_phrases.get(row["value"], ())) <= cue_exact_df
        for row in exact_cues)
    rare_concept_anchor = any(
        len(registry.concept_assertions.get(str(row["concept_id"]), ()))
        <= concept_degree for row in exact_concepts)
    cue_concept_join = bool(concept_ids) and any(
        len(finder.cue_tokens.get(row["value"], ())) <= cue_token_df
        for row in cue_tokens)
    return exact_cue_anchor or rare_concept_anchor or role_join or cue_concept_join


def _case(index, corpus_articles, canonical_articles, finder, registry,
          row: dict) -> dict:
    question = str(row.get("question") or "")
    expected = _expected_article_coords(row)
    anchors = spanparts.resolve_structure(index, question)
    scope, scope_kind = assertionfirst.structure_scope(index, anchors)

    unscoped_hits = finder.search(index, question)
    scoped_hits = finder.search(index, question, scope=scope)
    unscoped_coordinates = {hit.coordinate for hit in unscoped_hits}
    hit_coordinates = {hit.coordinate for hit in scoped_hits}
    structural_coordinates = (
        set(anchors.source_coordinates) if anchors.resolved else set())
    policy_coordinates = {
        policy: ({hit.coordinate for hit in scoped_hits
                  if _admitted(hit, finder, registry, policy)}
                 | structural_coordinates)
        for policy in GATE_POLICIES
    }
    family_hits, family_route = assertionfirst._route_document_families(
        index, scoped_hits)
    policy_coordinates["family_top8"] = (
        {hit.coordinate for hit in family_hits} | structural_coordinates)
    combined_coordinates = policy_coordinates["broad_or"]

    unscoped_articles = _coordinate_articles(index, unscoped_coordinates)
    hit_articles = _coordinate_articles(index, hit_coordinates)
    structure_articles = _coordinate_articles(index, structural_coordinates)
    policy_articles = {
        policy: _coordinate_articles(index, coordinates)
        for policy, coordinates in policy_coordinates.items()
    }
    combined_articles = policy_articles["broad_or"]

    gold = []
    for law, article in sorted(expected):
        coordinate = (law, article)
        if coordinate not in corpus_articles:
            result = "corpus_missing"
        elif coordinate not in canonical_articles:
            result = "canonical_assertion_missing"
        elif coordinate in combined_articles:
            result = "candidate_hit"
        elif coordinate in unscoped_articles:
            result = "structure_scope_excluded"
        else:
            result = "expression_miss"
        gold.append({"law": law, "article": article, "result": result,
                     "unscoped": coordinate in unscoped_articles,
                     "scoped": coordinate in hit_articles,
                     "structure": coordinate in structure_articles,
                     "combined": coordinate in combined_articles,
                     "policy_hits": {policy: coordinate in articles
                                     for policy, articles in policy_articles.items()}})

    evidence = Counter(
        item["kind"] for hit in scoped_hits for item in hit.evidence)
    return {
        "case_no": row.get("case_no"),
        "question": question,
        "scope_kind": scope_kind,
        "resolved_documents": list(anchors.documents),
        "resolved_locators": list(anchors.locators),
        "unresolved_locators": list(anchors.unresolved_locators),
        "assertion_hits": len(scoped_hits),
        "candidate_coordinates": len(combined_coordinates),
        "hierarchy": _hierarchy(index, combined_coordinates),
        "policies": {
            policy: {
                "candidate_coordinates": len(coordinates),
                "hierarchy": _hierarchy(index, coordinates),
                **({"document_route": family_route}
                   if policy == "family_top8" else {}),
            } for policy, coordinates in policy_coordinates.items()
        },
        "evidence": dict(evidence),
        "gold": gold,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.run.read_text(encoding="utf-8"))
    rows = list(source.get("rows") or [])[:51]
    index = index_mod.current()
    registry = conceptfirst.load_registry()
    started = time.perf_counter()
    finder = assertionfirst.current(registry)
    build_seconds = time.perf_counter() - started
    canonical_articles = _coordinate_articles(index, {
        (str(item.source.get("doc_id") or ""), item.source.get("node"))
        for item in registry.active_assertions
    })
    corpus_articles = _coordinate_articles(index, {
        (doc_id, node) for doc_id, view in index.docs.items() for node in view.by_id
    })

    details = []
    search_started = time.perf_counter()
    for pos, row in enumerate(rows, 1):
        item = _case(index, corpus_articles, canonical_articles, finder, registry, row)
        details.append(item)
        hits = sum(gold["result"] == "candidate_hit" for gold in item["gold"])
        print(f"[{pos:02d}/{len(rows)}] {item['case_no']} "
              f"{hits}/{len(item['gold'])} candidates={item['candidate_coordinates']} "
              f"docs={item['hierarchy']['documents']}", flush=True)
    search_seconds = time.perf_counter() - search_started

    gold_results = Counter(
        gold["result"] for item in details for gold in item["gold"])
    total_gold = sum(gold_results.values())
    counts = [item["candidate_coordinates"] for item in details]
    documents = [item["hierarchy"]["documents"] for item in details]
    roots = [item["hierarchy"]["selection_roots"] for item in details]
    pages = [item["hierarchy"]["lossless_pages_upper_bound"] for item in details]
    scope_counts = Counter(item["scope_kind"] for item in details)
    case_hits = sum(any(gold["result"] == "candidate_hit" for gold in item["gold"])
                    for item in details)
    policies = {}
    for policy in POLICIES:
        policy_counts = [item["policies"][policy]["candidate_coordinates"]
                         for item in details]
        policy_docs = [item["policies"][policy]["hierarchy"]["documents"]
                       for item in details]
        policy_roots = [item["policies"][policy]["hierarchy"]["selection_roots"]
                        for item in details]
        policy_pages = [item["policies"][policy]["hierarchy"]
                        ["lossless_pages_upper_bound"] for item in details]
        hit_count = sum(gold["policy_hits"][policy]
                        for item in details for gold in item["gold"])
        policies[policy] = {
            "candidate_hits": hit_count,
            "candidate_recall": round(hit_count / total_gold, 4) if total_gold else 0,
            "case_hits": sum(any(gold["policy_hits"][policy]
                                 for gold in item["gold"]) for item in details),
            "candidate_coordinates": _distribution(policy_counts),
            "documents": _distribution(policy_docs),
            "selection_roots": _distribution(policy_roots),
            "lossless_pages_upper_bound": _distribution(policy_pages),
        }
    result = {
        "experiment": "assertion-first-no-embedding-v2-document-family",
        "source": str(args.run),
        "contract": {
            "query": "original question preserved",
            "structure": "deterministic DB reverse match; hard scope",
            "semantic_index": "active concept expressions + assertion query_cues",
            "matching": "exact packed phrase + Kiwi morphology + one-hop canonical relation",
            "coordinates": "Concept→Assertion and cue→Assertion only",
            "roles": "Assertion DB edges; normative facets rank but do not hard-filter",
            "embedding": False,
            "raw_law_bm25": False,
            "gold_used_for_retrieval": False,
            "navigation_page_size": PAGE_SIZE,
        },
        "summary": {
            "cases": len(details),
            "gold": total_gold,
            "candidate_hits": gold_results["candidate_hit"],
            "candidate_recall": round(gold_results["candidate_hit"] / total_gold, 4)
                if total_gold else 0,
            "case_hits": case_hits,
            "first_missing": dict(gold_results),
            "scope_kinds": dict(scope_counts),
            "candidate_coordinates": _distribution(counts),
            "documents": _distribution(documents),
            "selection_roots": _distribution(roots),
            "lossless_pages_upper_bound": _distribution(pages),
            "index_build_sec": round(build_seconds, 3),
            "search_51_sec": round(search_seconds, 3),
            "policies": policies,
        },
        "rows": details,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
