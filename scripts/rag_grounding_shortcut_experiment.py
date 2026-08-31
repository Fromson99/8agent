#!/usr/bin/env python3
"""source-grounded Assertion을 컴파일 shortcut으로 쓸 수 있는지 51문항에서 잰다."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.domain_graph import grounding, spanparts  # noqa: E402
from lawrag.core.rag import assertionfirst, conceptfirst  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from scripts.ask_e2e_golden import _coords, _expected_article_coords  # noqa: E402
from scripts.rag_assertion_first_diagnose import (  # noqa: E402
    _coordinate_articles,
    _distribution,
    _hierarchy,
)


PROFILES = (
    "unfiltered", "exact", "grounded", "tolerant_action", "evidence_spans",
    "predicate_pair",
)


def _source_text(index, doc_id: str, node) -> str:
    view = index.docs.get(doc_id)
    item = view.by_id.get(node) if view else None
    return view.section_text(item, cap=10**9) if item else ""


def _audit(index, registry, canonical_rows: list[dict]) \
        -> tuple[dict, dict[str, set[str]]]:
    slot_grades: dict[str, Counter] = {}
    methods = Counter()
    assertion_minimum = Counter()
    eligibility = {profile: set() for profile in PROFILES if profile != "unfiltered"}
    examples = []
    missing_basis = missing_source = 0
    cache: dict[tuple[str, object], str] = {}
    doc_text: dict[str, str] = {}

    raw_by_id = {str(row.get("id") or ""): row for row in canonical_rows}
    for assertion in registry.active_assertions:
        raw = raw_by_id.get(assertion.id) or {}
        slots = grounding.raw_slots(raw)
        if not slots:
            missing_basis += 1
            continue
        source = raw.get("source") or assertion.source
        doc_id = str(source.get("doc_id") or "")
        node = source.get("node")
        key = (doc_id, node)
        if key not in cache:
            cache[key] = _source_text(index, doc_id, node)
        if not cache[key]:
            missing_source += 1
        matches = grounding.grade_assertion(raw, cache[key])
        if matches:
            assertion_minimum[min(matches.values(), key=lambda x: grounding.GRADE_RANK[x.grade]).grade] += 1
        for role, match in matches.items():
            slot_grades.setdefault(role, Counter())[match.grade] += 1
            methods[match.method] += 1
            if match.grade == "G0" and len(examples) < 40:
                view = index.docs.get(doc_id)
                if doc_id not in doc_text and view:
                    doc_text[doc_id] = "\n".join(
                        str(block.get("text") or "") for block in view.blocks)
                same_doc = bool(view and grounding.grade_surface(
                    match.value, doc_text.get(doc_id, ""), role=role).grade != "G0")
                examples.append({
                    "assertion_id": assertion.id,
                    "doc_id": doc_id,
                    "doc": view.name if view else "",
                    "node": node,
                    "path": view.path(node) if view else "",
                    "role": role,
                    "value": match.value,
                    "scope": "wrong_source_same_document" if same_doc else "not_in_document",
                    "source_excerpt": cache[key][:300],
                })
        for profile in eligibility:
            if grounding.eligible(matches, profile):
                eligibility[profile].add(assertion.id)

    eligibility["unfiltered"] = {item.id for item in registry.active_assertions}
    slots_total = sum(sum(rows.values()) for rows in slot_grades.values())
    grade_total = Counter()
    for rows in slot_grades.values():
        grade_total.update(rows)
    summary = {
        "active_assertions": len(registry.active_assertions),
        "auditable_assertions": len(registry.active_assertions) - missing_basis,
        "missing_candidate_basis": missing_basis,
        "missing_source_node": missing_source,
        "slots": slots_total,
        "slot_grades": dict(sorted(grade_total.items())),
        "slot_grade_by_role": {
            role: dict(sorted(rows.items())) for role, rows in sorted(slot_grades.items())
        },
        "methods": dict(methods),
        "assertion_minimum_grade": dict(sorted(assertion_minimum.items())),
        "eligible_assertions": {
            profile: {
                "count": len(ids),
                "ratio": round(len(ids) / len(registry.active_assertions), 4)
                    if registry.active_assertions else 0,
            } for profile, ids in eligibility.items()
        },
        "g0_examples": examples,
    }
    return summary, eligibility


def _profile_case(index, hits, structural_coordinates, eligible_ids: set[str]) -> dict:
    admitted = [hit for hit in hits if hit.assertion_id in eligible_ids]
    assertion_coordinates = {hit.coordinate for hit in admitted}
    broad = assertion_coordinates | structural_coordinates
    routed, route_meta = assertionfirst._route_document_families(index, admitted)
    family = {hit.coordinate for hit in routed} | structural_coordinates
    return {
        "assertion_ids": {hit.assertion_id for hit in admitted},
        "assertion_coordinates": assertion_coordinates,
        "broad_coordinates": broad,
        "family_coordinates": family,
        "route": route_meta,
    }


def _case(index, finder, eligible, row: dict) -> dict:
    question = str(row.get("question") or "")
    expected = _expected_article_coords(row)
    anchors = spanparts.resolve_structure(index, question)
    scope, scope_kind = assertionfirst.structure_scope(index, anchors)
    hits = finder.search(index, question, scope=scope)
    structural = set(anchors.source_coordinates) if anchors.resolved else set()
    profiles = {
        profile: _profile_case(index, hits, structural, eligible[profile])
        for profile in PROFILES
    }
    article_sets = {
        profile: {
            "assertion_only": _coordinate_articles(index, result["assertion_coordinates"]),
            "broad": _coordinate_articles(index, result["broad_coordinates"]),
            "family_top8": _coordinate_articles(index, result["family_coordinates"]),
        } for profile, result in profiles.items()
    }
    gold = []
    for law, article in sorted(expected):
        coordinate = (law, article)
        gold.append({
            "law": law,
            "article": article,
            "hits": {
                profile: {route: coordinate in articles
                          for route, articles in article_sets[profile].items()}
                for profile in PROFILES
            },
        })
    return {
        "case_no": row.get("case_no"),
        "question": question,
        "scope_kind": scope_kind,
        "raw_assertion_hits": len(hits),
        "structure_coordinates": len(structural),
        "profiles": {
            profile: {
                "assertions": len(result["assertion_ids"]),
                "assertion_coordinates": len(result["assertion_coordinates"]),
                "broad_coordinates": len(result["broad_coordinates"]),
                "family_coordinates": len(result["family_coordinates"]),
                "broad_hierarchy": _hierarchy(index, result["broad_coordinates"]),
                "family_hierarchy": _hierarchy(index, result["family_coordinates"]),
                "route": result["route"],
            } for profile, result in profiles.items()
        },
        "gold": gold,
    }


def _retrieval_summary(rows: list[dict]) -> dict:
    total_gold = sum(len(row["gold"]) for row in rows)
    out = {}
    for profile in PROFILES:
        routes = {}
        for route in ("assertion_only", "broad", "family_top8"):
            gold_hits = sum(gold["hits"][profile][route]
                            for row in rows for gold in row["gold"])
            case_hits = sum(any(gold["hits"][profile][route] for gold in row["gold"])
                            for row in rows)
            coordinate_key = (
                "assertion_coordinates" if route == "assertion_only"
                else "broad_coordinates" if route == "broad"
                else "family_coordinates")
            widths = [row["profiles"][profile][coordinate_key] for row in rows]
            routes[route] = {
                "gold_hits": gold_hits,
                "gold_recall": round(gold_hits / total_gold, 4) if total_gold else 0,
                "case_hits": case_hits,
                "candidate_coordinates": _distribution(widths),
            }
        out[profile] = routes
    return {"cases": len(rows), "gold": total_gold, "profiles": out}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.run.read_text(encoding="utf-8"))
    questions = list(source.get("rows") or [])[:51]
    index = index_mod.current()
    registry = conceptfirst.load_registry()

    started = time.perf_counter()
    canonical_blob = json.loads(
        conceptfirst.registry_path().read_text(encoding="utf-8"))
    audit, eligible = _audit(
        index, registry, list(canonical_blob.get("assertions") or []))
    audit_seconds = time.perf_counter() - started
    finder = assertionfirst.current(registry)

    rows = []
    search_started = time.perf_counter()
    for pos, question in enumerate(questions, 1):
        row = _case(index, finder, eligible, question)
        rows.append(row)
        hits = sum(gold["hits"]["grounded"]["broad"] for gold in row["gold"])
        print(f"[{pos:02d}/{len(questions)}] {row['case_no']} grounded={hits}/{len(row['gold'])}",
              flush=True)
    search_seconds = time.perf_counter() - search_started

    result = {
        "experiment": "source-grounded-assertion-shortcut-shadow-v1",
        "source": str(args.run),
        "contract": {
            "mutation": False,
            "gold_used_for_retrieval": False,
            "grounding_scope": "same source.doc_id/node",
            "G3": "literal contiguous source span",
            "G2": "NFKC + casefold + whitespace/punctuation-insensitive contiguous span",
            "G1": "PREDICATE only; parenthetical insertion may be skipped",
            "G0": "not found in source node",
            "canonical_label_grounding": False,
            "shortcut_rule": "all extracted conditions remain source-grounded; predicate plus another role required",
            "fm_index": False,
        },
        "timing": {
            "audit_seconds": round(audit_seconds, 3),
            "search_51_seconds": round(search_seconds, 3),
        },
        "corpus_audit": audit,
        "retrieval": _retrieval_summary(rows),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(json.dumps({
        "timing": result["timing"],
        "corpus_audit": {k: v for k, v in audit.items() if k != "g0_examples"},
        "retrieval": result["retrieval"],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
