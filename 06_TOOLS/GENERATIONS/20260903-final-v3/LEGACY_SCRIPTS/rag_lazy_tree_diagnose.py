#!/usr/bin/env python3
"""저장된 51개 E2E Span을 재생해 지연 트리의 정답 누락 단계를 측정한다.

답변 생성과 LLM 가지 선택을 호출하지 않는다. 동일 질문의 저장된 Span을 사용해
정답 조문이 canonical Assertion, 역할 호환 좌표, 벡터 후보, Span 상한, 생존 트리,
최종 LLM 메뉴 중 어디에서 처음 사라지는지 기록한다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.domain_graph import spanparts  # noqa: E402
from lawrag.core.rag import combinations, conceptfirst, controls, exploration  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from scripts.ask_e2e_golden import _coords, _expected_article_coords  # noqa: E402


EXPERIMENTAL_ROLE_HYPOTHESES: dict[str, tuple[str, ...]] = {
    "actor": ("actor", "subject"),
    "subject": ("subject", "actor", "object"),
    "object": ("object", "target", "subject"),
    "target": ("target", "object"),
    "predicate": ("predicate", "effect"),
    "effect": ("effect", "predicate"),
    "condition": ("condition", "method"),
    "method": ("method", "condition"),
    "modality": ("modality", "effect"),
}


def _stored_spans(row: dict) -> list[spanparts.QuerySpan]:
    runtime = row.get("runtime") or {}
    combination = runtime.get("combination") or {}
    return [spanparts.QuerySpan(
        str(item.get("span") or ""), int(item.get("start") or 0),
        int(item.get("end") or 0), str(item.get("role") or "unknown"),
        tuple(str(value) for value in item.get("reading_ids") or ()),
    ) for item in combination.get("spans") or [] if item.get("span")]


def _coordinate_articles(index, coordinates) -> set[tuple[str, str]]:
    rows = []
    for doc_id, node in coordinates:
        view = index.docs.get(doc_id)
        if view is None or node not in view.by_id:
            continue
        rows.append({"doc": view.name, "path": view.path(node) or view.name})
    return _coords(rows)


def _candidate_articles(index, candidates) -> set[tuple[str, str]]:
    return _coordinate_articles(
        index, {coordinate for row in candidates for coordinate in row.coordinates})


def _prepare(index, registry, lexicon, row: dict, *, adaptive: bool,
             projection: tuple[int, int, int] | None = None,
             recall_probe: bool = False) -> dict:
    from lawrag.core.rag import queryguide

    question = str(row.get("question") or "")
    spans = _stored_spans(row)
    anchors = spanparts.resolve_structure(index, question)
    guide = queryguide.build(index, question, registry, anchors)
    selected_docs = set(anchors.doc_ids) | queryguide.selected_document_ids(
        guide, spans, ())
    anchors = combinations._rebind_selected_documents(
        index, question, anchors, selected_docs)
    anchors = spanparts.resolve_named_structure(index, anchors, spans)
    scope, scope_kind = combinations._structure_scope(index, anchors)
    candidate_limit = ({
        "resolved-structure": 10,
        "resolved-document": 20,
        "none": 30,
    }[scope_kind] if adaptive else combinations.CANDIDATES_PER_PART_MAX)
    if recall_probe:
        candidate_limit *= 2
    groups, audit = combinations._candidate_groups(
        index, registry, guide, spans, lexicon, scope=scope,
        candidate_limit=candidate_limit,
        role_hypotheses=EXPERIMENTAL_ROLE_HYPOTHESES if adaptive else None,
        vector_neighbors_max=(200 if recall_probe else
                              combinations.LEXICON_NEIGHBORS_MAX),
        vector_min_cos=0.20 if recall_probe else 0.40)
    nodes, counts, ordered = combinations.build_lazy_tree(
        groups, scope_coordinates=scope)
    structural_roots = frozenset(anchors.source_coordinates) \
        if anchors.source_coordinates and anchors.resolved else frozenset()
    projection = projection or (
        combinations.NODES_TO_EXPAND_MAX,
        combinations.COORDINATES_PER_NODE_MAX,
        combinations.LLM_RANGES_MAX,
    )
    coordinate_options = combinations._tree_options(
        index, question, nodes, scope_coordinates=scope,
        structural_roots=structural_roots,
        nodes_to_expand_max=projection[0],
        coordinates_per_node_max=projection[1], ranges_max=projection[2])
    menu = exploration.build(index, coordinate_options)

    assertion_coordinates = {
        (str(assertion.source.get("doc_id") or ""), assertion.source.get("node"))
        for assertion in registry.active_assertions
        if assertion.source.get("doc_id") and assertion.source.get("node") is not None
    }
    role_names = {
        role.upper()
        for span in spans if span.role in spanparts.PART_ROLES
        for role in (combinations.ROLE_HYPOTHESES.get(span.role, (span.role,))
                     if adaptive else (span.role,))
    }
    role_coordinates = {
        (str(assertion.source.get("doc_id") or ""), assertion.source.get("node"))
        for assertion in registry.active_assertions
        if any(role in role_names for role in assertion.roles)
        and assertion.source.get("doc_id") and assertion.source.get("node") is not None
    }
    uncapped = [candidate for group in groups
                for candidate in audit[group.id].get("_uncapped") or ()]
    capped = [candidate for group in groups for candidate in group.candidates]
    tree_coordinates = {coordinate for node in nodes for coordinate in node.coordinates}
    return {
        "scope_kind": scope_kind,
        "candidate_limit": candidate_limit,
        "group_count": len(groups),
        "uncapped_count": len(uncapped),
        "capped_count": len(capped),
        "tree_nodes": len(nodes),
        "tree_pruned": counts.pruned_states,
        "tree_depth": len(ordered),
        "menu_count": len(menu.ranges),
        "projection": list(projection),
        "assertion": _coordinate_articles(index, assertion_coordinates),
        "role": _coordinate_articles(index, role_coordinates),
        "vector": _candidate_articles(index, uncapped),
        "cap": _candidate_articles(index, capped),
        "tree": _coordinate_articles(index, tree_coordinates),
        "menu": _coords(menu.ranges),
    }


def _first_missing(expected: tuple[str, str], stages: dict) -> str:
    for stage in ("corpus", "assertion", "role", "vector", "cap", "tree", "menu"):
        if expected not in stages[stage]:
            return {
                "corpus": "corpus_missing",
                "assertion": "canonical_assertion_missing",
                "role": "role_mismatch",
                "vector": "role_vector_miss",
                "cap": "candidate_cap_pruned",
                "tree": "lazy_tree_pruned",
                "menu": "menu_projection_pruned",
            }[stage]
    return "menu_hit"


def _saved_policy(index, registry, rows: list[dict]) -> dict:
    corpus = _coordinate_articles(index, {
        (doc_id, node) for doc_id, view in index.docs.items() for node in view.by_id
    })
    article_roles: dict[tuple[str, str], set[str]] = {}
    for assertion in registry.active_assertions:
        pair = (str(assertion.source.get("doc_id") or ""),
                assertion.source.get("node"))
        for article in _coordinate_articles(index, {pair}):
            article_roles.setdefault(article, set()).update(assertion.roles)
    counts = Counter()
    details = []
    for row in rows:
        expected = _expected_article_coords(row)
        spans = _stored_spans(row)
        strict_roles = {span.role.upper() for span in spans
                        if span.role in spanparts.PART_ROLES}
        adaptive_roles = {
            role.upper() for span in spans if span.role in spanparts.PART_ROLES
            for role in EXPERIMENTAL_ROLE_HYPOTHESES.get(span.role, (span.role,))
        }
        combination = (row.get("runtime") or {}).get("combination") or {}
        menu_rows = [item
                     for doc in ((combination.get("exploration") or {})
                                 .get("documents") or [])
                     for item in doc.get("ranges") or []]
        menu = _coords(menu_rows)
        selected = _coords(combination.get("selected") or [])
        gold_rows = []
        for gold in sorted(expected):
            canonical_roles = article_roles.get(gold, set())
            result = (
                "corpus_missing" if gold not in corpus else
                "canonical_assertion_missing" if not canonical_roles else
                "strict_role_mismatch" if not (canonical_roles & strict_roles) else
                "candidate_or_projection_miss" if gold not in menu else
                "selector_miss" if gold not in selected else
                "selected"
            )
            counts[result] += 1
            counts["corpus"] += int(gold in corpus)
            counts["assertion"] += int(bool(canonical_roles))
            counts["strict_role"] += int(bool(canonical_roles & strict_roles))
            counts["adaptive_role"] += int(bool(canonical_roles & adaptive_roles))
            counts["menu"] += int(gold in menu)
            counts["selected_total"] += int(gold in selected)
            gold_rows.append({
                "law": gold[0], "article": gold[1], "result": result,
                "canonical_roles": sorted(canonical_roles),
                "strict_roles": sorted(strict_roles),
                "adaptive_roles": sorted(adaptive_roles),
            })
        details.append({"case_no": row.get("case_no"), "gold": gold_rows})
    return {
        "summary": {
            "cases": len(rows),
            "gold": sum(len(_expected_article_coords(row)) for row in rows),
            "stage_hits": {key: counts[key] for key in (
                "corpus", "assertion", "strict_role", "adaptive_role",
                "menu", "selected_total")},
            "first_missing": {key: value for key, value in counts.items()
                              if key not in {"corpus", "assertion", "strict_role",
                                             "adaptive_role", "menu",
                                             "selected_total"}},
        },
        "rows": details,
    }


def _policy(index, registry, lexicon, rows: list[dict], adaptive: bool,
            corpus: set[tuple[str, str]], *,
            projection: tuple[int, int, int] | None = None,
            recall_probe: bool = False) -> dict:
    started = time.perf_counter()
    details = []
    failures = Counter()
    stage_hits = Counter()
    totals = Counter()
    for pos, row in enumerate(rows, 1):
        expected = _expected_article_coords(row)
        prepared = _prepare(
            index, registry, lexicon, row, adaptive=adaptive,
            projection=projection, recall_probe=recall_probe)
        stages = {"corpus": corpus, **{
            key: prepared[key]
            for key in ("assertion", "role", "vector", "cap", "tree", "menu")
        }}
        reasons = []
        for gold in sorted(expected):
            reason = _first_missing(gold, stages)
            failures[reason] += 1
            reasons.append({"law": gold[0], "article": gold[1], "result": reason})
            for stage in stages:
                stage_hits[stage] += int(gold in stages[stage])
        totals["gold"] += len(expected)
        totals["cases"] += 1
        totals["menu_cases"] += int(bool(expected & stages["menu"]))
        details.append({
            "case_no": row.get("case_no"), "question": row.get("question"),
            **{key: value for key, value in prepared.items()
               if not isinstance(value, set)},
            "gold": reasons,
        })
        print(f"  [{pos}/{len(rows)}] {row.get('case_no')} "
              f"menu {len(expected & stages['menu'])}/{len(expected)}")
    return {
        "policy": (("adaptive-recall-probe" if recall_probe else
                    "adaptive-wide-projection" if projection else
                    "adaptive-role-hypotheses") if adaptive else
                   "strict-role-cap10"),
        "summary": {
            "cases": totals["cases"], "gold": totals["gold"],
            "menu_cases": totals["menu_cases"],
            "stage_hits": dict(stage_hits),
            "first_missing": dict(failures),
            "elapsed_sec": round(time.perf_counter() - started, 1),
        },
        "rows": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, required=True,
                        help="Span이 저장된 ask E2E raw.json")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--saved-only", action="store_true",
                        help="벡터를 재계산하지 않고 저장된 메뉴와 정본 역할만 진단")
    args = parser.parse_args()
    source = json.loads(args.run.read_text(encoding="utf-8"))
    rows = list(source.get("rows") or [])
    index = index_mod.current()
    registry = conceptfirst.load_registry()
    if args.saved_only:
        control_rows = controls.snapshot()
        result = {
            "source": str(args.run), "saved": _saved_policy(index, registry, rows),
            "controls": {"fingerprint": controls.fingerprint(control_rows),
                         "values": control_rows},
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(result, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        print(result["saved"]["summary"])
        return 0
    lexicon = spanparts.cached_term_lexicon()
    corpus = _coordinate_articles(index, {
        (doc_id, node) for doc_id, view in index.docs.items() for node in view.by_id
    })
    print(f"지연 트리 회수 진단 {len(rows)}건")
    baseline = _policy(index, registry, lexicon, rows, adaptive=False,
                       corpus=corpus)
    adaptive = _policy(index, registry, lexicon, rows, adaptive=True,
                       corpus=corpus)
    adaptive_wide = _policy(
        index, registry, lexicon, rows, adaptive=True, corpus=corpus,
        projection=(72, 3, 80))
    adaptive_recall = _policy(
        index, registry, lexicon, rows, adaptive=True, corpus=corpus,
        projection=(72, 3, 80), recall_probe=True)
    control_rows = controls.snapshot()
    result = {
        "source": str(args.run), "baseline": baseline, "adaptive": adaptive,
        "adaptive_wide": adaptive_wide,
        "adaptive_recall": adaptive_recall,
        "controls": {"fingerprint": controls.fingerprint(control_rows),
                     "values": control_rows},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("baseline", baseline["summary"])
    print("adaptive", adaptive["summary"])
    print("adaptive_wide", adaptive_wide["summary"])
    print("adaptive_recall", adaptive_recall["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
