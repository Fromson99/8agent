#!/usr/bin/env python3
"""원문 증명형 관계의 RAG utility를 동결 결과에서 정적으로 감사한다.

관계 생성은 이미 끝난 artifact만 읽는다. 질문은 query-alignment 모의실험에,
gold는 사후 평가에만 사용하며 어느 것도 관계 생성 입력으로 돌아가지 않는다.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import re
from pathlib import Path


VARIANT = "control_d_then_verifier"
ARTICLE_RELATIONS = {"EXCEPTION_TO", "IMPLEMENTS", "DEFINED_BY", "CURRENT_VERSION_OF"}
MARKET_WORDS = {
    "KOSDAQ": ("코스닥",),
    "KOSPI": ("코스피", "유가증권시장"),
    "KONEX": ("코넥스",),
}
_ARTICLE = re.compile(r"제\s*\d+\s*조(?:\s*의\s*\d+)?")
_SPACE_PUNCT = re.compile(r"[^0-9A-Za-z가-힣]")


def normalize(value: str) -> str:
    return _SPACE_PUNCT.sub("", str(value or "")).lower()


def articles(value: str) -> set[str]:
    return {normalize(match.group(0)) for match in _ARTICLE.finditer(str(value or ""))}


def is_gold_node(node: dict, gold: list[dict]) -> bool:
    doc = normalize(node.get("doc") or node.get("document"))
    path_articles = articles(node.get("path") or "")
    for expected in gold:
        if normalize(expected.get("law")) == doc and normalize(expected.get("article")) in path_articles:
            return True
    return False


def explicit_query_markets(question: str) -> set[str]:
    normalized = normalize(question)
    return {
        market for market, words in MARKET_WORDS.items()
        if any(normalize(word) in normalized for word in words)
    }


def relation_query_aligned(relation: dict, question: str, inventory: dict[str, dict]) -> bool:
    """관계가 추가한 값/방향이 질문 문면과 직접 맞닿는지만 본다."""
    kind = str(relation.get("relation_type") or "")
    q = normalize(question)
    if kind == "APPLIES_TO_MARKET":
        return str(relation.get("target_value") or "") in explicit_query_markets(question)
    if kind == "GOVERNS_ACTOR":
        value = normalize(relation.get("target_value"))
        return len(value) >= 2 and value in q
    if kind == "DEFINED_BY":
        term = normalize(relation.get("defined_term"))
        return len(term) >= 2 and term in q
    if kind in {"EXCEPTION_TO", "IMPLEMENTS", "CURRENT_VERSION_OF"}:
        target = inventory.get(str(relation.get("target_id") or ""), {})
        return bool(articles(question) & articles(target.get("path") or ""))
    return False


def _relation_nodes(relation: dict) -> set[str]:
    out = {str(relation.get("source_id") or "")}
    if relation.get("relation_type") in ARTICLE_RELATIONS and relation.get("target_id"):
        out.add(str(relation["target_id"]))
    return {value for value in out if value}


def relation_key(relation: dict) -> tuple[str, ...]:
    return (
        str(relation.get("relation_type") or ""),
        str(relation.get("source_id") or ""),
        str(relation.get("target_id") or ""),
        normalize(relation.get("target_value")),
        normalize(relation.get("defined_term")),
    )


def stable_coordinate(row: dict) -> tuple[str, tuple[str, ...]]:
    """조상 경로 문구가 달라져도 법령+말단 조문 좌표는 동일하게 본다."""
    document = normalize(row.get("doc") or row.get("document"))
    found = [normalize(match.group(0)) for match in _ARTICLE.finditer(
        str(row.get("path") or ""))]
    return document, tuple(found[-1:])


def _rank_metrics(nodes: list[dict], gold_flags: dict[str, bool], scores: dict[str, int]) -> dict:
    ordered = sorted(
        enumerate(nodes),
        key=lambda pair: (-scores.get(str(pair[1]["evidence_id"]), 0), pair[0]),
    )
    ranked = [str(node["evidence_id"]) for _, node in ordered]
    positions = [i + 1 for i, evidence_id in enumerate(ranked) if gold_flags[evidence_id]]
    return {
        "first_gold_rank": min(positions) if positions else None,
        "gold_at_3": sum(1 for position in positions if position <= 3),
        "gold_at_5": sum(1 for position in positions if position <= 5),
        "reciprocal_first_gold_rank": round(1 / min(positions), 6) if positions else 0,
    }


def audit_case(relation_row: dict, retrieval_row: dict, variant: str = VARIANT) -> dict:
    frozen = retrieval_row["variants"][variant]
    selected = frozen.get("selected") or []
    gold = frozen.get("gold") or []
    inventory_list = relation_row.get("inventory") or []
    inventory = {str(row["evidence_id"]): row for row in inventory_list}

    # 생성기의 E1..En 순서가 동결 selected와 일치하는지 좌표로 검증한다.
    selected_by_coordinate = {stable_coordinate(row): row for row in selected}
    coordinate_match = all(
        stable_coordinate(row) in selected_by_coordinate
        for row in inventory_list
    ) and len(inventory_list) == len(selected)

    gold_flags = {
        evidence_id: is_gold_node(row, gold) for evidence_id, row in inventory.items()
    }
    published_raw = relation_row.get("published") or []
    published = list({relation_key(row): row for row in published_raw}.values())
    incident = Counter()
    aligned = Counter()
    annotated_types: dict[str, set[str]] = defaultdict(set)
    structural_edges = []
    for relation in published:
        node_ids = _relation_nodes(relation)
        for evidence_id in node_ids:
            incident[evidence_id] += 1
            annotated_types[evidence_id].add(str(relation.get("relation_type") or ""))
        if relation_query_aligned(relation, retrieval_row.get("question") or "", inventory):
            for evidence_id in node_ids:
                aligned[evidence_id] += 1
        target_id = str(relation.get("target_id") or "")
        if relation.get("relation_type") in ARTICLE_RELATIONS and target_id:
            source_id = str(relation.get("source_id") or "")
            structural_edges.append({
                "relation_type": relation.get("relation_type"),
                "source_id": source_id,
                "target_id": target_id,
                "touches_gold": bool(gold_flags.get(source_id) or gold_flags.get(target_id)),
                "gold_to_non_gold": bool(gold_flags.get(source_id) != gold_flags.get(target_id)),
            })

    node_ids = list(inventory)
    selected_gold = sum(gold_flags.values())
    relation_nodes = {evidence_id for evidence_id in node_ids if incident[evidence_id]}
    aligned_nodes = {evidence_id for evidence_id in node_ids if aligned[evidence_id]}
    unannotated = set(node_ids) - relation_nodes
    distractors = {evidence_id for evidence_id in node_ids if not gold_flags[evidence_id]}
    inferred_markets = explicit_query_markets(retrieval_row.get("question") or "")
    conflicting_market_nodes = set()
    if len(inferred_markets) == 1:
        for relation in published:
            if relation.get("relation_type") != "APPLIES_TO_MARKET":
                continue
            target_market = str(relation.get("target_value") or "")
            if target_market and target_market not in inferred_markets:
                conflicting_market_nodes.add(str(relation.get("source_id") or ""))

    base_scores = {evidence_id: 0 for evidence_id in node_ids}
    incident_scores = {evidence_id: int(bool(incident[evidence_id])) for evidence_id in node_ids}
    aligned_scores = {evidence_id: 2 * aligned[evidence_id] + int(bool(incident[evidence_id]))
                      for evidence_id in node_ids}
    return {
        "case_no": relation_row.get("case_no"),
        "coordinate_match": coordinate_match,
        "selected_nodes": len(node_ids),
        "expected_gold_references": len(gold),
        "retrieved_gold_references": sum(bool(row.get("selected")) for row in gold),
        "selected_gold_nodes": selected_gold,
        "published_relations_raw": len(published_raw),
        "published_relations": len(published),
        "relation_types": dict(sorted(Counter(
            str(row.get("relation_type") or "") for row in published).items())),
        "relation_type_nodes": {
            relation_type: {
                "nodes": sum(relation_type in kinds for kinds in annotated_types.values()),
                "gold_nodes": sum(
                    relation_type in kinds and gold_flags[evidence_id]
                    for evidence_id, kinds in annotated_types.items()),
            }
            for relation_type in sorted({
                relation_type for kinds in annotated_types.values() for relation_type in kinds})
        },
        "relation_incident_nodes": len(relation_nodes),
        "relation_incident_gold_nodes": len(relation_nodes & {
            key for key, value in gold_flags.items() if value}),
        "query_aligned_nodes": len(aligned_nodes),
        "query_aligned_gold_nodes": len(aligned_nodes & {
            key for key, value in gold_flags.items() if value}),
        "unannotated_nodes": len(unannotated),
        "unannotated_distractors": len(unannotated & distractors),
        "structural_edges": structural_edges,
        "explicit_query_markets": sorted(inferred_markets),
        "conflicting_market_nodes": len(conflicting_market_nodes),
        "conflicting_market_gold_nodes": sum(gold_flags.get(x, False) for x in conflicting_market_nodes),
        "simulated_pruning": {
            "keep_relation_incident_only": {
                "kept": len(relation_nodes),
                "gold_kept": sum(gold_flags[x] for x in relation_nodes),
            },
            "drop_explicit_market_conflicts": {
                "kept": len(node_ids) - len(conflicting_market_nodes),
                "gold_kept": selected_gold - sum(gold_flags.get(x, False) for x in conflicting_market_nodes),
            },
        },
        "rerank": {
            "frozen_order": _rank_metrics(inventory_list, gold_flags, base_scores),
            "relation_incident_first": _rank_metrics(inventory_list, gold_flags, incident_scores),
            "query_aligned_then_incident": _rank_metrics(inventory_list, gold_flags, aligned_scores),
        },
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0


def summarize(rows: list[dict], retrieval_case_count: int) -> dict:
    selected = sum(row["selected_nodes"] for row in rows)
    expected_gold = sum(row["expected_gold_references"] for row in rows)
    retrieved_gold = sum(row["retrieved_gold_references"] for row in rows)
    gold = sum(row["selected_gold_nodes"] for row in rows)
    incident = sum(row["relation_incident_nodes"] for row in rows)
    incident_gold = sum(row["relation_incident_gold_nodes"] for row in rows)
    aligned = sum(row["query_aligned_nodes"] for row in rows)
    aligned_gold = sum(row["query_aligned_gold_nodes"] for row in rows)
    unannotated = sum(row["unannotated_nodes"] for row in rows)
    unannotated_distractors = sum(row["unannotated_distractors"] for row in rows)
    distractors = selected - gold
    structural_edges = [edge for row in rows for edge in row["structural_edges"]]
    kept_relation = sum(row["simulated_pruning"]["keep_relation_incident_only"]["kept"] for row in rows)
    gold_relation = sum(row["simulated_pruning"]["keep_relation_incident_only"]["gold_kept"] for row in rows)
    kept_market = sum(row["simulated_pruning"]["drop_explicit_market_conflicts"]["kept"] for row in rows)
    gold_market = sum(row["simulated_pruning"]["drop_explicit_market_conflicts"]["gold_kept"] for row in rows)

    def aggregate_rank(name: str) -> dict:
        values = [row["rerank"][name] for row in rows]
        return {
            "mean_reciprocal_first_gold_rank": round(
                sum(value["reciprocal_first_gold_rank"] for value in values) / len(values), 4
            ) if values else 0,
            "gold_at_3": sum(value["gold_at_3"] for value in values),
            "gold_at_5": sum(value["gold_at_5"] for value in values),
        }

    cases_with_relations = sum(bool(row["published_relations"]) for row in rows)
    cases_with_aligned = sum(bool(row["query_aligned_nodes"]) for row in rows)
    base_gold_rate = _ratio(gold, selected)
    incident_gold_rate = _ratio(incident_gold, incident)
    relation_type_signal = {}
    for relation_type in sorted({
            key for row in rows for key in row["relation_type_nodes"]}):
        type_nodes = sum(
            (row["relation_type_nodes"].get(relation_type) or {}).get("nodes", 0)
            for row in rows)
        type_gold = sum(
            (row["relation_type_nodes"].get(relation_type) or {}).get("gold_nodes", 0)
            for row in rows)
        relation_type_signal[relation_type] = {
            "cases": sum(relation_type in row["relation_types"] for row in rows),
            "nodes": type_nodes,
            "gold_nodes": type_gold,
            "gold_node_rate": _ratio(type_gold, type_nodes),
        }
    return {
        "scope": {
            "retrieval_cases": retrieval_case_count,
            "relation_artifact_cases": len(rows),
            "probe_share_of_51": _ratio(len(rows), retrieval_case_count),
            "cases_with_relations": cases_with_relations,
            "cases_without_relations": len(rows) - cases_with_relations,
            "cases_with_query_aligned_relations": cases_with_aligned,
        },
        "annotation_signal": {
            "selected_nodes": selected,
            "expected_gold_references": expected_gold,
            "retrieved_gold_references": retrieved_gold,
            "retrieval_gold_recall": _ratio(retrieved_gold, expected_gold),
            "selected_gold_nodes": gold,
            "base_gold_node_rate": base_gold_rate,
            "relation_incident_nodes": incident,
            "relation_incident_gold_nodes": incident_gold,
            "relation_incident_gold_recall": _ratio(incident_gold, gold),
            "relation_incident_gold_node_rate": incident_gold_rate,
            "gold_rate_lift_vs_base": round(incident_gold_rate / base_gold_rate, 4) if base_gold_rate else 0,
            "query_aligned_nodes": aligned,
            "query_aligned_gold_nodes": aligned_gold,
            "query_aligned_gold_recall": _ratio(aligned_gold, gold),
            "by_relation_type": relation_type_signal,
        },
        "distractor_signal": {
            "distractor_nodes": distractors,
            "unannotated_nodes_predicted_distractor": unannotated,
            "unannotated_true_distractors": unannotated_distractors,
            "precision": _ratio(unannotated_distractors, unannotated),
            "recall": _ratio(unannotated_distractors, distractors),
            "base_distractor_rate": _ratio(distractors, selected),
        },
        "path_signal": {
            "structural_edges": len(structural_edges),
            "edges_touching_gold": sum(edge["touches_gold"] for edge in structural_edges),
            "gold_to_non_gold_edges": sum(edge["gold_to_non_gold"] for edge in structural_edges),
            "edge_types": dict(sorted(Counter(edge["relation_type"] for edge in structural_edges).items())),
        },
        "simulated_pruning": {
            "keep_relation_incident_only": {
                "kept_nodes": kept_relation,
                "node_reduction": round(1 - kept_relation / selected, 4) if selected else 0,
                "gold_kept": gold_relation,
                "gold_recall": _ratio(gold_relation, gold),
            },
            "drop_explicit_market_conflicts": {
                "kept_nodes": kept_market,
                "node_reduction": round(1 - kept_market / selected, 4) if selected else 0,
                "gold_kept": gold_market,
                "gold_recall": _ratio(gold_market, gold),
            },
        },
        "rerank": {
            name: aggregate_rank(name) for name in (
                "frozen_order", "relation_incident_first", "query_aligned_then_incident")
        },
        "integrity": {
            "all_relation_inventory_coordinates_match_frozen_selected": all(
                row["coordinate_match"] for row in rows),
            "relation_generation_used_question": False,
            "relation_generation_used_gold": False,
            "audit_query_alignment_used_question": True,
            "audit_scoring_used_gold": True,
            "main_wiring_changed": False,
            "canonical_changed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--relations", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variant", default=VARIANT)
    args = parser.parse_args()

    relations = json.loads(args.relations.read_text("utf-8"))
    retrieval = json.loads(args.retrieval.read_text("utf-8"))
    retrieval_by_case = {str(row["case_no"]): row for row in retrieval.get("rows") or []}
    rows = []
    missing = []
    for relation_row in relations.get("rows") or []:
        case_no = str(relation_row.get("case_no") or "")
        if case_no not in retrieval_by_case:
            missing.append(case_no)
            continue
        rows.append(audit_case(relation_row, retrieval_by_case[case_no], args.variant))

    summary = summarize(rows, len(retrieval_by_case))
    result = {
        "experiment": "source-proven-relation-utility-static-audit-v1",
        "contract": {
            "relation_artifact_is_frozen": True,
            "question_and_gold_never_enter_relation_generation": True,
            "question_used_only_for_posthoc_query_alignment": True,
            "gold_used_only_for_posthoc_metrics": True,
            "selection_simulations_are_not_main_wiring": True,
            "main_wiring_changed": False,
            "canonical_changed": False,
        },
        "sources": {"relations": str(args.relations), "retrieval": str(args.retrieval)},
        "missing_relation_cases_in_retrieval": missing,
        "summary": summary,
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 1 if missing or not summary["integrity"]["all_relation_inventory_coordinates_match_frozen_selected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
