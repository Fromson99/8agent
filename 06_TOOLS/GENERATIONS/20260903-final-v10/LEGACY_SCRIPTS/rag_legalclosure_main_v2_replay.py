#!/usr/bin/env python3
"""동결 LegalClosure 채널에 v2 규범 참조 검증·메타 배선을 재생한다."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STRUCTURE_STORE", "data/structure")
os.environ.setdefault("GLOSSARY_STORE", "data/glossary.json")

from lawrag.core.rag import (  # noqa: E402
    legal_coordinates, legal_evidence, legal_references, legalclosure,
)
from lawrag.core.rag import index as index_mod  # noqa: E402
from scripts.ask_e2e_golden import _coords  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    primary_blob = json.loads(Path(baseline["primary_run"]).read_text(encoding="utf-8"))
    primary_by_case = {row["case_no"]: row for row in primary_blob["rows"]}
    index = index_mod.current().scoped(None)
    rows = []
    annotation_ms = []
    for row in baseline["rows"]:
        case_no = row["case_no"]
        question = row["question"]
        terms = tuple((row.get("term_plan") or {}).get("used_terms") or ())
        primary = legal_coordinates.branches_from_rows(
            index, primary_by_case[case_no].get("selected"), terms, "exact-structural")
        assertion = legal_coordinates.branches_from_rows(
            index, row.get("assertion_selected"), terms, "assertion-tree")
        keyword = legal_coordinates.branches_from_rows(
            index, (row.get("keyword") or {}).get("article_candidates"),
            terms, "keyword-bm25")
        closure = legal_coordinates.branches_from_rows(
            index, row.get("closure"), terms, "supplemental-closure")
        before = legal_coordinates.merge(20, primary, assertion, keyword, closure)
        rescue, rescue_meta = legal_references.requirement_rescue(
            index, question, assertion, terms, cap=max(0, 20 - len(before)),
            question_terms=legalclosure._question_terms(question))
        selected = legal_coordinates.merge(
            20, primary, assertion, keyword, closure, rescue)
        started = time.perf_counter()
        annotations = legal_evidence.annotate(index, question, selected)
        annotation_ms.append((time.perf_counter() - started) * 1000)
        coords = _coords([{"doc_id": item.doc_id, "node": item.node,
                           "doc": item.doc, "path": item.path}
                          for item in selected])
        gold = [{**item, "selected_v2": (item["law"], item["article"]) in coords}
                for item in row.get("gold") or []]
        rows.append({
            "case_no": case_no, "question": question,
            "selected_count_v1": len(before), "selected_count_v2": len(selected),
            "reference_verifier": rescue_meta,
            "annotation_rows": len(annotations["rows"]),
            "legal_warnings": annotations["warnings"],
            "gold": gold,
        })
    total = sum(len(row["gold"]) for row in rows)
    hits = sum(item["selected_v2"] for row in rows for item in row["gold"])
    old_hits = baseline["summary"]["selected_hits"]
    sorted_ms = sorted(annotation_ms)
    result = {
        "experiment": "legalclosure-main-v2-frozen-channel-replay",
        "baseline": str(args.baseline),
        "contract": {
            "production_topology_preserved": True,
            "existing_candidates_removed": False,
            "reference_rescue": "unique heading match from selected incorporation provision",
            "proof_shortcut": "runtime-wired but no unapproved store used in replay",
            "normative_and_validity": "metadata only",
        },
        "summary": {
            "cases": len(rows), "gold": total,
            "v1_hits": old_hits, "v2_hits": hits,
            "v2_recall": round(hits / total, 4) if total else 0,
            "case_hits": sum(any(item["selected_v2"] for item in row["gold"])
                             for row in rows),
            "reference_rescue_cases": sum(bool(
                row["reference_verifier"]["selected"]) for row in rows),
            "annotation_ms_p50": round(sorted_ms[len(sorted_ms) // 2], 3),
            "annotation_ms_max": round(max(annotation_ms), 3),
            "regression": hits < old_hits,
        },
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
