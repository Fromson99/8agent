#!/usr/bin/env python3
"""원문 span 기반 구성요건 qualifier의 코퍼스·51골든 coverage를 잰다."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_golden as review  # noqa: E402,F401 — store 환경
from scripts.ask_e2e_golden import _expected_article_coords  # noqa: E402
from lawrag.core.domain_graph import requirements  # noqa: E402
from lawrag.core.rag import conceptfirst, index as index_mod, termexplore, wikictx  # noqa: E402


def _article_map(index):
    out = {}
    for doc_id, view in index.docs.items():
        for node in view.nodes:
            if not termexplore._ARTICLE.fullmatch(
                    str(node.get("surface") or "").strip()):
                continue
            if "부칙" in (view.path(node.get("id")) or ""):
                continue
            key = (wikictx._pack(view.name), str(node.get("surface") or "").strip())
            out.setdefault(key, []).append((doc_id, node.get("id")))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.run.read_text(encoding="utf-8"))
    questions = list(source.get("rows") or [])[:51]
    canonical = json.loads(conceptfirst.registry_path().read_text(encoding="utf-8"))
    index = index_mod.current()
    coordinates = []
    seen = set()
    for assertion in canonical.get("assertions") or []:
        if assertion.get("status") != "active" or not assertion.get("candidate_basis"):
            continue
        source_row = assertion.get("source") or {}
        coordinate = (str(source_row.get("doc_id") or ""), source_row.get("node"))
        if coordinate not in seen:
            seen.add(coordinate)
            coordinates.append(coordinate)

    started = time.perf_counter()
    by_coordinate = {}
    kind_counts = Counter()
    samples = {kind: [] for kind in requirements.KINDS}
    text_chars = 0
    for doc_id, node in coordinates:
        view = index.docs.get(doc_id)
        if view is None or node not in view.by_id:
            continue
        text = view.section_text(view.by_id[node], cap=10**9)
        text_chars += len(text)
        spans = requirements.extract(text)
        by_coordinate[(doc_id, node)] = spans
        kind_counts.update(row.kind for row in spans)
        for row in spans:
            if len(samples[row.kind]) < 12:
                samples[row.kind].append({
                    "doc": view.name, "doc_id": doc_id, "node": node,
                    "path": view.path(node), **row.as_dict(),
                })
    elapsed = time.perf_counter() - started

    article_map = _article_map(index)
    requested = Counter()
    covered = Counter()
    cases = []
    for question in questions:
        asked = requirements.requested_kinds(str(question.get("question") or ""))
        expected = _expected_article_coords(question)
        gold_coordinates = [coordinate for key in expected
                            for coordinate in article_map.get(key, ())]
        gold_kinds = set()
        for doc_id, article in gold_coordinates:
            view = index.docs[doc_id]
            root = view.by_id[article]
            text = view.section_text(root, cap=10**9)
            gold_kinds.update(row.kind for row in requirements.extract(text))
        requested.update(asked)
        covered.update(kind for kind in asked if kind in gold_kinds)
        cases.append({
            "case_no": question.get("case_no"), "requested": list(asked),
            "gold_kinds": sorted(gold_kinds),
            "covered": [kind for kind in asked if kind in gold_kinds],
        })

    result = {
        "experiment": "source-span-normative-requirement-audit-v1",
        "contract": {
            "generation": False,
            "same_source_offsets": True,
            "automatic_canonical_publish": False,
            "gold_used_for_extraction": False,
            "gold_metric": "requested facet cue has at least one same-kind span in a gold article; coverage proxy, not semantic accuracy",
        },
        "summary": {
            "active_frame_source_coordinates": len(coordinates),
            "audited_coordinates": len(by_coordinate),
            "text_chars": text_chars,
            "elapsed_seconds": round(elapsed, 3),
            "coordinates_per_second": round(len(by_coordinate) / elapsed, 2)
                if elapsed else 0,
            "spans": sum(kind_counts.values()),
            "spans_by_kind": dict(kind_counts),
            "coordinates_with_any": sum(bool(rows) for rows in by_coordinate.values()),
            "spans_per_coordinate_median": statistics.median(
                [len(rows) for rows in by_coordinate.values()]) if by_coordinate else 0,
            "gold_question_requested": dict(requested),
            "gold_question_covered": dict(covered),
            "gold_question_coverage": {
                kind: round(covered[kind] / count, 4) if count else 0
                for kind, count in requested.items()
            },
        },
        "samples": samples,
        "rows": cases,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

