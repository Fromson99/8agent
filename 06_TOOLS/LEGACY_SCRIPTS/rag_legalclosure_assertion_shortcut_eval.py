#!/usr/bin/env python3
"""LegalClosure의 Assertion 채널 안에서 proof shortcut의 warm/cross 효과를 잰다."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.domain_graph import grounding, spanparts  # noqa: E402
from lawrag.core.rag import (  # noqa: E402
    assertionfirst, conceptfirst, legal_coordinates, legalclosure,
)
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.assertion_shortcuts import (  # noqa: E402
    ShortcutEntry,
    ShortcutIndex,
    ShortcutProof,
)
from scripts.ask_e2e_golden import _coords, _expected_article_coords  # noqa: E402


def _percentile(values: list[int | float], fraction: float):
    return sorted(values)[math.ceil(len(values) * fraction) - 1] if values else 0


def _distribution(values: list[int | float]) -> dict:
    return {
        "min": min(values, default=0),
        "median": round(statistics.median(values), 3) if values else 0,
        "p95": round(_percentile(values, .95), 3),
        "max": max(values, default=0),
        "mean": round(statistics.mean(values), 3) if values else 0,
    }


def _root(index, coordinate):
    doc_id, node = coordinate
    view = index.docs.get(doc_id)
    if view is None or node not in view.by_id:
        return None
    return doc_id, legal_coordinates.article_root(view, node)


def _source_text(index, raw: dict) -> str:
    source = raw.get("source") or {}
    view = index.docs.get(str(source.get("doc_id") or ""))
    node = source.get("node")
    return (view.section_text(view.by_id[node], cap=10**9)
            if view and node in view.by_id else "")


def _grounded_assertions(index, registry, raw_by_id) -> tuple[set[str], dict]:
    eligible = set()
    matches_by_id = {}
    for assertion in registry.active_assertions:
        raw = raw_by_id.get(assertion.id) or {}
        matches = grounding.grade_assertion(assertion=raw,
                                             source_text=_source_text(index, raw))
        matches_by_id[assertion.id] = matches
        if grounding.eligible(matches, "evidence_spans"):
            eligible.add(assertion.id)
    return eligible, matches_by_id


def _compile(index, registry, finder, assertion_rows, raw_by_id,
             corpus_fingerprint: str):
    started = time.perf_counter()
    eligible, matches_by_id = _grounded_assertions(index, registry, raw_by_id)
    entries = []
    selected_targets = compiled_targets = 0
    rejected_traces = []
    for row in assertion_rows:
        question = str(row.get("question") or "")
        anchors = spanparts.resolve_structure(index, question)
        scope, _ = assertionfirst.structure_scope(index, anchors)
        hits = finder.search(index, question, scope=scope)
        hits_by_root: dict[tuple[str, object], list] = {}
        for hit in hits:
            root = _root(index, hit.coordinate)
            if root is not None and hit.assertion_id in eligible:
                hits_by_root.setdefault(root, []).append(hit)

        targets = []
        for item in row.get("selected") or []:
            target = _root(index, (item.get("doc_id"), item.get("node")))
            if target is not None and target not in targets:
                targets.append(target)
        selected_targets += len(targets)
        if not targets:
            rejected_traces.append({"case_no": row.get("case_no"),
                                    "reason": "no_selected_target"})
            continue
        missing = [target for target in targets if not hits_by_root.get(target)]
        if missing:
            rejected_traces.append({
                "case_no": row.get("case_no"),
                "reason": "selected_target_without_full_grounding_proof",
                "missing_targets": [list(value) for value in missing],
            })
            continue

        proofs = []
        required = []
        for target in targets:
            hit = hits_by_root[target][0]
            if hit.assertion_id not in required:
                required.append(hit.assertion_id)
            proofs.append(ShortcutProof(
                assertion_id=hit.assertion_id,
                coordinate=target,
                slots={role: match.as_dict()
                       for role, match in matches_by_id[hit.assertion_id].items()},
            ))
        entries.append(ShortcutEntry(
            required_assertions=tuple(required), targets=tuple(targets),
            proofs=tuple(proofs), corpus_fingerprint=corpus_fingerprint,
            query_assertions=tuple(hit.assertion_id for hit in hits[:24]),
            source_trace=str(row.get("case_no") or ""),
        ))
        compiled_targets += len(targets)
    return ShortcutIndex(entries), {
        "profile": "evidence_spans",
        "active_grounded_assertions": len(eligible),
        "traces": len(assertion_rows),
        "compiled_traces": len(entries),
        "rejected_traces": len(rejected_traces),
        "selected_targets": selected_targets,
        "compiled_targets": compiled_targets,
        "compile_seconds": round(time.perf_counter() - started, 3),
        "rejections": rejected_traces,
    }


def _branches(index, items, terms, origin):
    return legal_coordinates.branches_from_rows(index, items, terms, origin)


def _scenario(index, case, primary_row, assertion_row, baseline_row,
              shortcut_index, finder, *, exclude_own: bool):
    started = time.perf_counter()
    question = str(case.get("question") or "")
    anchors = spanparts.resolve_structure(index, question)
    scope, _ = assertionfirst.structure_scope(index, anchors)
    assertion_hits = finder.search(index, question, scope=scope)
    shortcut_hits = shortcut_index.lookup(
        [hit.assertion_id for hit in assertion_hits], cap=legalclosure.ASSERTION_CAP,
        exclude_traces={str(case.get("case_no"))} if exclude_own else None,
        require_unambiguous=True, require_query_signature=True)
    lookup_ms = round((time.perf_counter() - started) * 1000, 3)

    shortcut_items = [{"doc_id": hit.target[0], "node": hit.target[1]}
                      for hit in shortcut_hits]
    used_shortcut = bool(shortcut_items)
    assertion_items = shortcut_items if used_shortcut else assertion_row.get("selected") or []
    terms = tuple((primary_row.get("term_plan") or {}).get("used_terms") or ())
    primary = _branches(index, primary_row.get("selected"), terms, "exact-structural")
    assertion = _branches(index, assertion_items, terms,
                          "assertion-shortcut" if used_shortcut else "assertion-tree")
    keyword = _branches(
        index, (baseline_row.get("keyword") or {}).get("article_candidates"),
        terms, "keyword-bm25")
    closure = _branches(index, baseline_row.get("closure"), terms,
                        "supplemental-closure")
    # 실제 운영 cap 20과 채널 우선순위를 그대로 재생한다.
    selected = legal_coordinates.merge(20, primary, assertion, keyword, closure)
    selected_public = [{"doc_id": item.doc_id, "node": item.node,
                        "doc": item.doc, "path": item.path,
                        "origin": item.origin} for item in selected]
    expected = _expected_article_coords(case)
    coordinates = _coords(selected_public)
    gold = [{"law": law, "article": article,
             "selected": (law, article) in coordinates}
            for law, article in sorted(expected)]

    old_ms = int(assertion_row.get("wall_ms") or 0)
    effective_ms = lookup_ms + (0 if used_shortcut else old_ms)
    primary_ms = int(primary_row.get("wall_ms") or 0)
    frozen_other_ms = int(baseline_row.get("wall_ms") or 0)
    usage = assertion_row.get("usage") or {}
    return {
        "used_shortcut": used_shortcut,
        "shortcut_targets": shortcut_items,
        "shortcut_target_count": len(shortcut_items),
        "lookup_ms": lookup_ms,
        "assertion_old_ms": old_ms,
        "assertion_effective_ms": round(effective_ms, 3),
        "retrieval_old_estimated_ms": primary_ms + old_ms + frozen_other_ms,
        "retrieval_effective_estimated_ms": round(
            primary_ms + effective_ms + frozen_other_ms, 3),
        "saved_calls": int(usage.get("calls") or 0) if used_shortcut else 0,
        "saved_input_tokens": int(usage.get("input_tokens") or 0)
            if used_shortcut else 0,
        "selected_count": len(selected),
        "gold": gold,
    }


def _summary(rows, key: str) -> dict:
    scenarios = [row[key] for row in rows]
    gold = sum(len(item["gold"]) for item in scenarios)
    hits = sum(gold_row["selected"] for item in scenarios for gold_row in item["gold"])
    old = [item["retrieval_old_estimated_ms"] for item in scenarios]
    effective = [item["retrieval_effective_estimated_ms"] for item in scenarios]
    return {
        "cases": len(rows), "gold": gold, "selected_hits": hits,
        "selected_recall": round(hits / gold, 4) if gold else 0,
        "case_hits": sum(any(gold_row["selected"] for gold_row in item["gold"])
                         for item in scenarios),
        "shortcut_hits": sum(item["used_shortcut"] for item in scenarios),
        "shortcut_hit_rate": round(sum(item["used_shortcut"] for item in scenarios)
                                   / len(scenarios), 4) if scenarios else 0,
        "shortcut_targets": _distribution(
            [item["shortcut_target_count"] for item in scenarios]),
        "lookup_ms": _distribution([item["lookup_ms"] for item in scenarios]),
        "assertion_old_ms": _distribution(
            [item["assertion_old_ms"] for item in scenarios]),
        "assertion_effective_ms": _distribution(
            [item["assertion_effective_ms"] for item in scenarios]),
        "retrieval_old_estimated_ms": _distribution(old),
        "retrieval_effective_estimated_ms": _distribution(effective),
        "mean_retrieval_reduction_ms": round(
            statistics.mean(a - b for a, b in zip(old, effective)), 3),
        "saved_calls": sum(item["saved_calls"] for item in scenarios),
        "saved_input_tokens": sum(item["saved_input_tokens"] for item in scenarios),
        "assertion_cap_violations": sum(
            item["shortcut_target_count"] > legalclosure.ASSERTION_CAP
            for item in scenarios),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    source = json.loads(Path(baseline["source"]).read_text(encoding="utf-8"))
    primary_blob = json.loads(Path(baseline["primary_run"]).read_text(encoding="utf-8"))
    assertion_blob = json.loads(Path(baseline["assertion_run"]).read_text(encoding="utf-8"))
    cases = list(source.get("rows") or [])[:51]
    primary = {row["case_no"]: row for row in primary_blob["rows"]}
    assertion = {row["case_no"]: row for row in assertion_blob["rows"]}
    frozen = {row["case_no"]: row for row in baseline["rows"]}

    index = index_mod.current().scoped(None)
    registry_path = conceptfirst.registry_path()
    canonical_bytes = registry_path.read_bytes()
    canonical = json.loads(canonical_bytes)
    raw_by_id = {str(row.get("id") or ""): row
                 for row in canonical.get("assertions") or []}
    registry = conceptfirst.load_registry(registry_path)
    finder = assertionfirst.current(registry)
    # Kiwi의 첫 질의 토큰화 초기화 비용과 결과 변동을 평가 행에서 분리한다.
    finder.search(index, "Assertion shortcut 초기화")
    shortcut_index, compile_meta = _compile(
        index, registry, finder, list(assertion_blob["rows"]), raw_by_id,
        hashlib.sha256(canonical_bytes).hexdigest())

    rows = []
    for pos, case in enumerate(cases, 1):
        case_no = case["case_no"]
        row = {
            "case_no": case_no, "question": case.get("question"),
            "warm": _scenario(index, case, primary[case_no], assertion[case_no],
                              frozen[case_no], shortcut_index, finder,
                              exclude_own=False),
            "cross_question": _scenario(
                index, case, primary[case_no], assertion[case_no], frozen[case_no],
                shortcut_index, finder, exclude_own=True),
        }
        rows.append(row)
        print(f"[{pos:02d}/{len(cases)}] {case_no} "
              f"warm={row['warm']['used_shortcut']} "
              f"cross={row['cross_question']['used_shortcut']} ", flush=True)

    result = {
        "experiment": "legalclosure-assertion-proof-shortcut-shadow-v1",
        "baseline": str(args.baseline),
        "contract": {
            "legalclosure_is_main": True,
            "changed_channel": "Assertion only",
            "query_text_or_embedding_cache": False,
            "shortcut_key": "deterministically matched grounded assertion ids",
            "route_signature": "top-24 deterministic Assertion ids; no question text/embedding",
            "ambiguity_gate": "different target sets force original Assertion fallback",
            "proof_profile": "all selected article targets require evidence_spans proof",
            "shortcut_cap": legalclosure.ASSERTION_CAP,
            "miss": "recorded original Assertion tree fallback",
            "other_channels": "frozen A/C/D from 68/70 baseline",
            "gold_used_for_compilation": False,
            "warm_is_same_relation_replay": True,
            "cross_question_excludes_own_trace": True,
        },
        "compile": compile_meta,
        "summary": {
            "baseline_selected_hits": baseline["summary"]["selected_hits"],
            "baseline_selected_recall": baseline["summary"]["selected_recall"],
            "warm": _summary(rows, "warm"),
            "cross_question": _summary(rows, "cross_question"),
        },
        "shortcuts": [entry.as_dict() for entry in shortcut_index.entries],
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(json.dumps({"compile": compile_meta,
                      "summary": result["summary"]},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
