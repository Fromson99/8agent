#!/usr/bin/env python3
"""동결 51건에서 LegalClosure D 관계폐쇄와 verifier 순서를 ablation한다."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import json
import math
from pathlib import Path
import statistics
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import (  # noqa: E402
    legal_conditional_closure, legal_coordinates, legal_references, legalclosure,
)
from lawrag.core.rag import index as index_mod  # noqa: E402
from scripts.ask_e2e_golden import _coords  # noqa: E402


VARIANTS = (
    "control_d_then_verifier",
    "abc_only",
    "abc_then_verifier",
    "mandatory_d_then_verifier",
    "verifier_then_d",
    "verifier_then_conditional_d",
)


def _percentile(values, fraction: float):
    if not values:
        return 0
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def _distribution(values) -> dict:
    return {
        "min": min(values, default=0),
        "p50": round(statistics.median(values), 3) if values else 0,
        "p95": round(_percentile(values, .95), 3),
        "max": max(values, default=0),
        "mean": round(statistics.mean(values), 3) if values else 0,
        "sum": sum(values),
    }


def _branches(index, items, terms, origin):
    return legal_coordinates.branches_from_rows(index, items, terms, origin)


def _closure_branches(index, items, terms):
    out = []
    for item in items or []:
        row = legal_coordinates.article_branch(
            index, item.get("doc_id"), item.get("node"), terms,
            origin="supplemental-closure", reason=item.get("path") or "")
        if row is not None:
            out.append(replace(
                row, mandatory=bool(item.get("mandatory")),
                mandatory_reason="frozen-closure-mandatory"
                if item.get("mandatory") else ""))
    return out


def _rescue(index, question, assertion, terms, selected_count):
    return legal_references.requirement_rescue(
        index, question, assertion, terms,
        cap=max(0, 20 - selected_count),
        question_terms=legalclosure.question_terms(question))


def _select(index, question, terms, primary, assertion, keyword, closure):
    mandatory = [row for row in closure if row.mandatory]
    results = {}

    started = time.perf_counter()
    before = legal_coordinates.merge(20, primary, assertion, keyword, closure)
    rescue, audit = _rescue(index, question, assertion, terms, len(before))
    results["control_d_then_verifier"] = (
        legal_coordinates.merge(20, primary, assertion, keyword, closure, rescue), audit)

    results["abc_only"] = (
        legal_coordinates.merge(20, primary, assertion, keyword),
        {"selected": [], "fallback": "verifier_disabled_by_ablation"})

    abc = legal_coordinates.merge(20, primary, assertion, keyword)
    rescue, audit = _rescue(index, question, assertion, terms, len(abc))
    results["abc_then_verifier"] = (
        legal_coordinates.merge(20, primary, assertion, keyword, rescue), audit)

    before = legal_coordinates.merge(20, primary, assertion, keyword, mandatory)
    rescue, audit = _rescue(index, question, assertion, terms, len(before))
    results["mandatory_d_then_verifier"] = (
        legal_coordinates.merge(20, primary, assertion, keyword, mandatory, rescue), audit)

    abc = legal_coordinates.merge(20, primary, assertion, keyword)
    rescue, audit = _rescue(index, question, assertion, terms, len(abc))
    results["verifier_then_d"] = (
        legal_coordinates.merge(20, primary, assertion, keyword, rescue, closure), audit)

    abc_v = legal_coordinates.merge(20, primary, assertion, keyword, rescue)
    targeted, targeted_audit = legal_conditional_closure.select(
        index, question, abc_v, closure, cap=1)
    results["verifier_then_conditional_d"] = (
        legal_coordinates.merge(20, primary, assertion, keyword, rescue, targeted),
        {**audit, "conditional_d": targeted_audit})
    elapsed_ms = (time.perf_counter() - started) * 1000
    return results, elapsed_ms


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    primary_blob = json.loads(Path(baseline["primary_run"]).read_text(encoding="utf-8"))
    primary_by_case = {row["case_no"]: row for row in primary_blob["rows"]}
    index = index_mod.current().scoped(None)
    text_cache = {}
    rows = []
    replay_ms = []

    for source in baseline["rows"]:
        case_no = source["case_no"]
        question = source["question"]
        terms = tuple((source.get("term_plan") or {}).get("used_terms") or ())
        primary = _branches(
            index, primary_by_case[case_no].get("selected"), terms, "exact-structural")
        assertion = _branches(
            index, source.get("assertion_selected"), terms, "assertion-tree")
        keyword = _branches(
            index, (source.get("keyword") or {}).get("article_candidates"),
            terms, "keyword-bm25")
        closure = _closure_branches(index, source.get("closure"), terms)
        variants, elapsed_ms = _select(
            index, question, terms, primary, assertion, keyword, closure)
        replay_ms.append(elapsed_ms)
        expected = {(row["law"], row["article"]) for row in source.get("gold") or []}
        public = {}
        for name, (selected, audit) in variants.items():
            selected_public = [{
                "doc_id": row.doc_id, "node": row.node, "doc": row.doc,
                "path": row.path, "origin": row.origin,
            } for row in selected]
            coordinates = _coords(selected_public)
            body_chars = 0
            for branch in selected:
                if branch.coordinate not in text_cache:
                    text_cache[branch.coordinate] = legal_coordinates.subtree_text(
                        index.docs[branch.doc_id], branch.node, cap=None)
                body_chars += len(text_cache[branch.coordinate])
            public[name] = {
                "selected": selected_public,
                "selected_count": len(selected),
                "body_chars": body_chars,
                "full_cap": len(selected) >= 20,
                "verifier_selected": len(audit.get("selected") or []),
                "conditional_d_selected": len(
                    (audit.get("conditional_d") or {}).get("selected") or []),
                "gold": [{"law": law, "article": article,
                          "selected": (law, article) in coordinates}
                         for law, article in sorted(expected)],
                "origins": dict(Counter(row.origin for row in selected)),
            }
        rows.append({"case_no": case_no, "question": question, "variants": public})

    summary = {}
    for name in VARIANTS:
        values = [row["variants"][name] for row in rows]
        total = sum(len(row["gold"]) for row in values)
        hits = sum(gold["selected"] for row in values for gold in row["gold"])
        summary[name] = {
            "cases": len(values), "gold": total, "selected_hits": hits,
            "selected_recall": round(hits / total, 4) if total else 0,
            "case_hits": sum(any(gold["selected"] for gold in row["gold"])
                             for row in values),
            "selected_count": _distribution([row["selected_count"] for row in values]),
            "body_chars": _distribution([row["body_chars"] for row in values]),
            "full_cap_cases": sum(row["full_cap"] for row in values),
            "verifier_selected_cases": sum(bool(row["verifier_selected"]) for row in values),
            "conditional_d_selected_cases": sum(
                bool(row["conditional_d_selected"]) for row in values),
            "origin_counts": dict(sum(
                (Counter(row["origins"]) for row in values), Counter())),
        }
    control = summary["control_d_then_verifier"]
    for name, values in summary.items():
        values["versus_control"] = {
            "hit_delta": values["selected_hits"] - control["selected_hits"],
            "selected_count_delta": (
                values["selected_count"]["sum"] - control["selected_count"]["sum"]),
            "body_chars_delta": values["body_chars"]["sum"] - control["body_chars"]["sum"],
            "body_chars_reduction": round(
                1 - values["body_chars"]["sum"] / control["body_chars"]["sum"], 4)
                if control["body_chars"]["sum"] else 0,
        }
    result = {
        "experiment": "legalclosure-stage-d-verifier-ablation-v1",
        "baseline": str(args.baseline),
        "contract": {
            "frozen_channels": True, "gold_used_for_selection": False,
            "final_cap": 20, "main_wiring_changed": False,
            "latency_scope": "deterministic replay only; excludes frozen LLM channel time",
        },
        "summary": summary,
        "replay_ms": _distribution(replay_ms),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
