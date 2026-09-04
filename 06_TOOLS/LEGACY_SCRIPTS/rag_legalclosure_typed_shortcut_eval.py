#!/usr/bin/env python3
"""Canonical ROLE:Concept 부품으로 LegalClosure Assertion shortcut을 평가한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.domain_graph import grounding, spanparts  # noqa: E402
from lawrag.core.rag import (  # noqa: E402
    assertionfirst, conceptfirst, legal_coordinates, legalclosure,
)
from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.assertion_shortcuts import ShortcutProof  # noqa: E402
from lawrag.core.rag.experiments.typed_assertion_shortcuts import (  # noqa: E402
    TypedShortcutEntry,
    TypedShortcutIndex,
)
from scripts.rag_legalclosure_assertion_shortcut_eval import (  # noqa: E402
    _grounded_assertions,
    _root,
    _summary,
)
from scripts.ask_e2e_golden import _coords, _expected_article_coords  # noqa: E402


_IGNORED_EVIDENCE = {"concept-relation", "facet-conflict"}


def _hit_parts(registry, hit) -> tuple[str, ...]:
    """질문에 직접 걸린 정본 Concept을 Assertion의 저장된 역할과 결합한다."""
    assertion = registry.active_assertions_by_id.get(hit.assertion_id)
    if assertion is None:
        return ()
    direct_ids = {
        str(row.get("concept_id") or "")
        for row in hit.evidence
        if row.get("kind") not in _IGNORED_EVIDENCE and row.get("concept_id")
    }
    parts = []
    for role, concept_ids in sorted(assertion.roles.items()):
        for concept_id in concept_ids:
            if concept_id in direct_ids:
                parts.append(f"{role}:{concept_id}")
    return tuple(dict.fromkeys(parts))


def _compile(index, registry, finder, assertion_rows, raw_by_id,
             corpus_fingerprint: str):
    started = time.perf_counter()
    eligible, matches_by_id = _grounded_assertions(index, registry, raw_by_id)
    entries = []
    selected_targets = compiled_targets = 0
    rejections = []
    for row in assertion_rows:
        case_no = str(row.get("case_no") or "")
        question = str(row.get("question") or "")
        anchors = spanparts.resolve_structure(index, question)
        scope, _ = assertionfirst.structure_scope(index, anchors)
        hits = finder.search(index, question, scope=scope)
        hits_by_root: dict[tuple[str, object], list] = {}
        for hit in hits:
            root = _root(index, hit.coordinate)
            parts = _hit_parts(registry, hit)
            if root is not None and hit.assertion_id in eligible and parts:
                hits_by_root.setdefault(root, []).append((hit, parts))

        targets = []
        for item in row.get("selected") or []:
            target = _root(index, (item.get("doc_id"), item.get("node")))
            if target is not None and target not in targets:
                targets.append(target)
        selected_targets += len(targets)
        missing = [target for target in targets if not hits_by_root.get(target)]
        if not targets or missing:
            rejections.append({
                "case_no": case_no,
                "reason": "no_target" if not targets else "target_without_typed_grounded_proof",
                "missing_targets": [list(value) for value in missing],
            })
            continue

        proofs = []
        required_parts = []
        for target in targets:
            # 강한 직접 Concept 부품이 많은 증명을 택한다. 질문 문자열은 저장하지 않는다.
            hit, parts = sorted(
                hits_by_root[target], key=lambda item: (-len(item[1]), -item[0].strength,
                                                        item[0].assertion_id))[0]
            for part in parts:
                if part not in required_parts:
                    required_parts.append(part)
            proofs.append(ShortcutProof(
                assertion_id=hit.assertion_id,
                coordinate=target,
                slots={role: match.as_dict()
                       for role, match in matches_by_id[hit.assertion_id].items()},
            ))
        # 역할 없는 cue-only 경로 또는 한 개의 느슨한 표면형은 지름길로 발행하지 않는다.
        content_roles = {part.split(":", 1)[0] for part in required_parts}
        if len(required_parts) < 2 or not content_roles.intersection(
                {"ACTOR", "SUBJECT", "PREDICATE", "OBJECT", "TARGET"}):
            rejections.append({"case_no": case_no, "reason": "insufficient_typed_parts",
                               "parts": required_parts})
            continue
        entries.append(TypedShortcutEntry(
            required_parts=tuple(required_parts), targets=tuple(targets),
            proofs=tuple(proofs), corpus_fingerprint=corpus_fingerprint,
            source_trace=case_no,
        ))
        compiled_targets += len(targets)
    return TypedShortcutIndex(entries), {
        "proof_profile": "evidence_spans",
        "key": "ROLE:canonical-concept",
        "active_grounded_assertions": len(eligible),
        "traces": len(assertion_rows),
        "compiled_traces": len(entries),
        "rejected_traces": len(rejections),
        "selected_targets": selected_targets,
        "compiled_targets": compiled_targets,
        "compile_seconds": round(time.perf_counter() - started, 3),
        "rejections": rejections,
    }


def _scenario(index, registry, case, primary_row, assertion_row, baseline_row,
              shortcut_index, finder, *, exclude_own: bool):
    started = time.perf_counter()
    question = str(case.get("question") or "")
    anchors = spanparts.resolve_structure(index, question)
    scope, _ = assertionfirst.structure_scope(index, anchors)
    assertion_hits = finder.search(index, question, scope=scope)
    parts = tuple(dict.fromkeys(
        part for hit in assertion_hits for part in _hit_parts(registry, hit)))
    shortcut_hits = shortcut_index.lookup(
        parts, cap=legalclosure.ASSERTION_CAP,
        exclude_traces={str(case.get("case_no"))} if exclude_own else None)
    lookup_ms = round((time.perf_counter() - started) * 1000, 3)

    shortcut_items = [{"doc_id": hit.target[0], "node": hit.target[1]}
                      for hit in shortcut_hits]
    used_shortcut = bool(shortcut_items)
    assertion_items = shortcut_items if used_shortcut else assertion_row.get("selected") or []
    terms = tuple((primary_row.get("term_plan") or {}).get("used_terms") or ())
    primary = legal_coordinates.branches_from_rows(
        index, primary_row.get("selected"), terms, "exact-structural")
    assertion = legal_coordinates.branches_from_rows(
        index, assertion_items, terms,
        "typed-assertion-shortcut" if used_shortcut else "assertion-tree")
    keyword = legal_coordinates.branches_from_rows(
        index, (baseline_row.get("keyword") or {}).get("article_candidates"),
        terms, "keyword-bm25")
    closure = legal_coordinates.branches_from_rows(
        index, baseline_row.get("closure"), terms, "supplemental-closure")
    selected = legal_coordinates.merge(20, primary, assertion, keyword, closure)
    public = [{"doc_id": item.doc_id, "node": item.node, "doc": item.doc,
               "path": item.path, "origin": item.origin} for item in selected]
    coordinates = _coords(public)
    gold = [{"law": law, "article": article,
             "selected": (law, article) in coordinates}
            for law, article in sorted(_expected_article_coords(case))]
    old_ms = int(assertion_row.get("wall_ms") or 0)
    effective_ms = lookup_ms + (0 if used_shortcut else old_ms)
    primary_ms = int(primary_row.get("wall_ms") or 0)
    frozen_other_ms = int(baseline_row.get("wall_ms") or 0)
    usage = assertion_row.get("usage") or {}
    return {
        "used_shortcut": used_shortcut,
        "query_part_count": len(parts),
        "shortcut_targets": shortcut_items,
        "shortcut_target_count": len(shortcut_items),
        "lookup_ms": lookup_ms,
        "assertion_old_ms": old_ms,
        "assertion_effective_ms": round(effective_ms, 3),
        "retrieval_old_estimated_ms": primary_ms + old_ms + frozen_other_ms,
        "retrieval_effective_estimated_ms": round(
            primary_ms + effective_ms + frozen_other_ms, 3),
        "saved_calls": int(usage.get("calls") or 0) if used_shortcut else 0,
        "saved_input_tokens": int(usage.get("input_tokens") or 0) if used_shortcut else 0,
        "selected_count": len(selected),
        "gold": gold,
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
    finder.search(index, "Typed Assertion shortcut 초기화")
    shortcut_index, compile_meta = _compile(
        index, registry, finder, list(assertion_blob["rows"]), raw_by_id,
        hashlib.sha256(canonical_bytes).hexdigest())

    rows = []
    for pos, case in enumerate(cases, 1):
        case_no = case["case_no"]
        row = {
            "case_no": case_no,
            "question": case.get("question"),
            "warm": _scenario(index, registry, case, primary[case_no], assertion[case_no],
                              frozen[case_no], shortcut_index, finder, exclude_own=False),
            "cross_question": _scenario(
                index, registry, case, primary[case_no], assertion[case_no], frozen[case_no],
                shortcut_index, finder, exclude_own=True),
        }
        rows.append(row)
        print(f"[{pos:02d}/{len(cases)}] {case_no} "
              f"warm={row['warm']['used_shortcut']} "
              f"cross={row['cross_question']['used_shortcut']}", flush=True)

    result = {
        "experiment": "legalclosure-canonical-typed-assertion-shortcut-shadow-v1",
        "baseline": str(args.baseline),
        "contract": {
            "legalclosure_is_main": True,
            "changed_channel": "Assertion only",
            "shortcut_key": "ROLE:canonical-concept; no question text or embedding",
            "proof": "all compiled targets need same-source evidence_spans grounding",
            "ambiguity_gate": "different target sets force original Assertion fallback",
            "shortcut_cap": legalclosure.ASSERTION_CAP,
            "miss": "recorded original Assertion tree fallback",
            "other_channels": "frozen A/C/D from 68/70 baseline",
            "gold_used_for_compilation": False,
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
    print(json.dumps({"compile": compile_meta, "summary": result["summary"]},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
