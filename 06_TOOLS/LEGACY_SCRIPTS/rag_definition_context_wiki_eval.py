#!/usr/bin/env python3
"""ADR-0038: 동결 51건에서 정의 근거 분리·정의 부록·Wiki 위생을 재생한다."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import sys


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.rag import answer, definitions, legal_coordinates, legal_references  # noqa: E402
from lawrag.core.rag import legalclosure, wikictx  # noqa: E402
from lawrag.core.rag.answer import Section  # noqa: E402
from lawrag.core.rag import index as index_mod  # noqa: E402
from scripts.ask_e2e_golden import _coords  # noqa: E402
from scripts.rag_legalclosure_stage_ablation import (  # noqa: E402
    _branches, _closure_branches,
)


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def _legacy_wiki_pick(question: str, doc_names: set[str]) -> list[dict]:
    """ADR 직전 일반 Wiki 선택기 — 질문 낱말 하나도 약신호로 허용."""
    scored = []
    words = set(wikictx._WORD_RE.findall(question))
    for row in wikictx._rows():
        if row["slug"].startswith(wikictx.ISSUE_DIR + "/"):
            continue
        why, score = [], 0
        for doc_name in sorted(doc_names):
            if doc_name and wikictx._pack(doc_name) in wikictx._pack(row["text"]):
                score += 2
                why.append(doc_name)
        hits = sorted(word for word in words if word in row["head"])
        score += len(hits)
        why.extend(hits)
        if score:
            scored.append((score, row, why))
    scored.sort(key=lambda item: -item[0])
    return [{"slug": row["slug"], "title": row["title"],
             "text": row["text"][:wikictx.ARTICLE_MAX_CHARS],
             "why": why[:6], "score": score}
            for score, row, why in scored[:wikictx.PICK_LIMIT]]


def _sections(index, selected, question, eligible_doc_ids):
    sections = []
    for position, row in enumerate(selected, 1):
        view = index.docs[row.doc_id]
        sections.append(Section(
            n=position, doc_id=row.doc_id, doc=row.doc, node=row.node,
            path=row.path, page=view.by_id[row.node].get("page"),
            kind="법률좌표폐쇄", matched=row.origin,
            text=legal_coordinates.subtree_text(view, row.node, cap=None)))
    appendix = legalclosure._attach_definition_context(
        index, question, sections, eligible_doc_ids=set(eligible_doc_ids))
    return sections, appendix


def _public(row):
    return {"doc_id": row.doc_id, "node": row.node, "doc": row.doc,
            "path": row.path, "origin": row.origin}


def _summary(rows):
    gold_total = sum(len(row["gold"]) for row in rows)
    baseline_hits = sum(item["baseline"] for row in rows for item in row["gold"])
    candidate_hits = sum(item["candidate"] for row in rows for item in row["gold"])
    baseline_counts = [row["baseline"]["selected_count"] for row in rows]
    candidate_counts = [row["candidate"]["selected_count"] for row in rows]
    appendix_counts = [row["candidate"]["definition_appendix_count"] for row in rows]
    return {
        "cases": len(rows), "gold": gold_total,
        "baseline_hits": baseline_hits,
        "baseline_recall": round(baseline_hits / gold_total, 4) if gold_total else 0,
        "candidate_hits": candidate_hits,
        "candidate_recall": round(candidate_hits / gold_total, 4) if gold_total else 0,
        "case_hits": sum(all(item["candidate"] for item in row["gold"])
                         for row in rows),
        "definition_filter": {
            "cases_with_drops": sum(bool(row["candidate"]["definition_dropped"])
                                    for row in rows),
            "coordinate_occurrences_dropped": sum(
                len(row["candidate"]["definition_dropped"]) for row in rows),
            "unique_channel_coordinates_dropped": sum(
                len({(item["doc_id"], item["node"])
                     for item in row["candidate"]["definition_dropped"]})
                for row in rows),
            "baseline_final_definition_sections": sum(
                row["baseline"]["definition_sections"] for row in rows),
            "baseline_cases_with_final_definition_sections": sum(
                row["baseline"]["definition_sections"] > 0 for row in rows),
            "candidate_final_definition_sections": 0,
            "baseline_selected_mean": round(statistics.mean(baseline_counts), 3),
            "candidate_selected_mean": round(statistics.mean(candidate_counts), 3),
        },
        "definition_appendix": {
            "cases": sum(count > 0 for count in appendix_counts),
            "entries": sum(appendix_counts),
            "entries_mean_all_cases": round(statistics.mean(appendix_counts), 3),
            "chars": sum(row["candidate"]["definition_appendix_chars"] for row in rows),
            "documents": sum(row["candidate"]["definition_appendix_documents"]
                             for row in rows),
        },
        "wiki": {
            "legacy_picks": sum(len(row["wiki"]["legacy"]) for row in rows),
            "candidate_picks": sum(len(row["wiki"]["candidate"]) for row in rows),
            "blocked_picks": sum(len(row["wiki"]["blocked"]) for row in rows),
            "cases_with_blocked_picks": sum(bool(row["wiki"]["blocked"]) for row in rows),
            "provenance_chars_removed": sum(
                row["wiki"]["provenance_chars_removed"] for row in rows),
            "legacy_prompt_chars": sum(row["wiki"]["legacy_prompt_chars"]
                                       for row in rows),
            "candidate_prompt_chars": sum(row["wiki"]["candidate_prompt_chars"]
                                          for row in rows),
        },
        "body_chars": {
            "baseline": sum(row["baseline"]["body_chars"] for row in rows),
            "candidate": sum(row["candidate"]["body_chars"] for row in rows),
        },
        "modeled_context_chars": {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--baseline", type=Path,
        default=ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_legal_coordinate_closure_normative_51.json")
    parser.add_argument(
        "--control", type=Path,
        default=ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/cm_core_legalclosure_stage_ablation_51.json")
    parser.add_argument(
        "--out", type=Path,
        default=ROOT / "90_RUNTIME/LEGACY_VAR/eval/e2e/ADR-0038/definition_context_wiki_51.json")
    parser.add_argument(
        "--artifact-dir", type=Path,
        default=ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0038-definition-context-wiki-hygiene/artifacts")
    args = parser.parse_args()

    baseline = json.loads(args.baseline.read_text("utf-8"))
    control = json.loads(args.control.read_text("utf-8"))
    primary_blob = json.loads(_resolve(baseline["primary_run"]).read_text("utf-8"))
    primary_by_case = {row["case_no"]: row for row in primary_blob["rows"]}
    control_by_case = {row["case_no"]: row for row in control["rows"]}
    index = index_mod.current().scoped(None)
    rows = []

    for source in baseline["rows"]:
        case_no, question = source["case_no"], source["question"]
        terms = tuple((source.get("term_plan") or {}).get("used_terms") or ())
        primary = _branches(
            index, primary_by_case[case_no].get("selected"), terms, "exact-structural")
        assertion = _branches(
            index, source.get("assertion_selected"), terms, "assertion-tree")
        keyword = _branches(
            index, (source.get("keyword") or {}).get("article_candidates"),
            terms, "keyword-bm25")
        closure = _closure_branches(index, source.get("closure"), terms)

        dropped = []
        groups = []
        for group in (primary, assertion, keyword, closure):
            kept, removed = legalclosure._without_definition_articles(
                index, question, group)
            groups.append(kept)
            dropped.extend(removed)
        primary, assertion, keyword, closure = groups
        before = legal_coordinates.merge(20, primary, assertion, keyword, closure)
        rescue, _ = legal_references.requirement_rescue(
            index, question, assertion, terms,
            cap=max(0, 20 - len(before)),
            question_terms=legalclosure.question_terms(question))
        rescue, removed = legalclosure._without_definition_articles(
            index, question, rescue)
        dropped.extend(removed)
        candidate = legal_coordinates.merge(
            20, primary, assertion, keyword, closure, rescue)

        baseline_public = (control_by_case[case_no]["variants"]
                           ["control_d_then_verifier"]["selected"])
        baseline_coords = _coords(baseline_public)
        candidate_coords = _coords([_public(row) for row in candidate])
        gold = [{"law": item["law"], "article": item["article"],
                 "baseline": (item["law"], item["article"]) in baseline_coords,
                 "candidate": (item["law"], item["article"]) in candidate_coords}
                for item in source.get("gold") or []]

        sections, appendix = _sections(
            index, candidate, question,
            {row["doc_id"] for row in dropped})
        appendix_text = answer._definition_context_text(sections)
        body_chars = sum(len(section.text) for section in sections)
        docs = {row.doc for row in candidate}
        legacy = _legacy_wiki_pick(question, docs)
        current = wikictx.pick(question, docs)
        current_slugs = {row["slug"] for row in current}
        blocked = [{"slug": row["slug"], "title": row["title"],
                    "why": row["why"]} for row in legacy
                   if row["slug"] not in current_slugs]
        provenance_removed = sum(
            max(0, len(row["text"]) - len(wikictx.prompt_text(row["text"])))
            for row in legacy)

        baseline_body_chars = int(control_by_case[case_no]["variants"]
                                  ["control_d_then_verifier"]["body_chars"])
        baseline_definition_sections = 0
        for item in baseline_public:
            view = index.docs.get(item["doc_id"])
            if view is not None and definitions.is_definition_node(view, item["node"]):
                baseline_definition_sections += 1
        rows.append({
            "case_no": case_no, "question": question, "gold": gold,
            "baseline": {
                "selected_count": len(baseline_public),
                "body_chars": baseline_body_chars,
                "definition_sections": baseline_definition_sections,
            },
            "candidate": {
                "selected": [_public(row) for row in candidate],
                "selected_count": len(candidate), "body_chars": body_chars,
                "definition_dropped": dropped,
                "definition_appendix": appendix,
                "definition_appendix_count": len(appendix),
                "definition_appendix_chars": len(appendix_text),
                "definition_appendix_documents": len({row["doc_id"] for row in appendix}),
            },
            "wiki": {
                "legacy": [{"slug": row["slug"], "title": row["title"],
                            "why": row["why"]} for row in legacy],
                "candidate": [{"slug": row["slug"], "title": row["title"],
                               "why": row["why"]} for row in current],
                "blocked": blocked,
                "provenance_chars_removed": provenance_removed,
                "legacy_prompt_chars": sum(len(row["text"]) for row in legacy),
                "candidate_prompt_chars": sum(len(row["text"]) for row in current),
            },
        })

    summary = _summary(rows)
    baseline_context = (summary["body_chars"]["baseline"]
                        + summary["wiki"]["legacy_prompt_chars"])
    candidate_context = (summary["body_chars"]["candidate"]
                         + summary["definition_appendix"]["chars"]
                         + summary["wiki"]["candidate_prompt_chars"])
    summary["modeled_context_chars"] = {
        "baseline": baseline_context, "candidate": candidate_context,
        "delta": candidate_context - baseline_context,
        "reduction": round(1 - candidate_context / baseline_context, 4)
        if baseline_context else 0,
        "scope": "statute bodies + general Wiki + definition appendix; methods/spots excluded",
    }
    result = {
        "experiment": "ADR-0038-definition-context-wiki-hygiene-v1",
        "date": "2026-08-26",
        "model_calls": 0,
        "model_policy_if_called": "claude-haiku-4-5-20251001",
        "contract": {
            "frozen_channels": True, "gold_used_for_selection": False,
            "final_cap": 20,
            "note": "동결 A/B/C/D 채널을 운영과 같은 순서로 재병합한 결정론 replay",
        },
        "sources": {"baseline": str(args.baseline), "control": str(args.control)},
        "summary": summary, "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", "utf-8")
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.artifact_dir / "manifest.json"
    manifest = (json.loads(manifest_path.read_text("utf-8"))
                if manifest_path.exists() else {})
    manifest.update({
        "raw_result": str(args.out.relative_to(ROOT)),
        "sha256": digest, "bytes": args.out.stat().st_size,
        "summary": result["summary"],
    })
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")

    samples = ["# 선택 규정 정의 부록 샘플", ""]
    for row in rows:
        picked = [item for item in row["candidate"]["definition_appendix"]
                  if item["doc"] == "증권 인수업무 등에 관한 규정"]
        if not picked:
            continue
        samples.extend([f"## {row['case_no']}", "", row["question"], ""])
        for item in picked:
            samples.extend([
                f"- 용어: {item['term']}",
                f"  - 위치: {item['path']}",
                f"  - 원문: {item['quote']}",
            ])
        samples.append("")
    (args.artifact_dir / "definition_samples.md").write_text(
        "\n".join(samples).rstrip() + "\n", "utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    print(f"raw={args.out} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
