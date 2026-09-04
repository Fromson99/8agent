#!/usr/bin/env python3
"""Haiku mixed 관계 추출과 법률 관계군 분리 추출의 반복 안정성을 비교한다."""

from __future__ import annotations

import argparse
import concurrent.futures
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL  # noqa: E402
from lawrag.core.rag.experiments.haiku_source_relation_families import (  # noqa: E402
    RELATION_FAMILIES,
    compile_source_relation_families,
)
from lawrag.core.rag.experiments.haiku_source_relations import (  # noqa: E402
    compile_source_relations,
)
from scripts import review_golden as review  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


def _packed(value):
    return "".join(character for character in str(value or "").casefold()
                   if character.isalnum())


def _fingerprint(relation, inventory):
    by_id = {row["evidence_id"]: row for row in inventory}
    source = by_id.get(str(relation.get("source_id") or "")) or {}
    target = by_id.get(str(relation.get("target_id") or "")) or {}
    return (
        str(relation.get("relation_type") or ""),
        _packed(source.get("document")), _packed(source.get("path")),
        _packed(target.get("document")), _packed(target.get("path")),
        _packed(relation.get("target_value")),
        _packed(relation.get("defined_term")),
    )


def _row_fingerprints(row):
    return {_fingerprint(relation, row.get("inventory") or [])
            for relation in row.get("published") or []}


def _variant_summary(rows, variant, repetitions):
    good = [row for row in rows
            if row.get("variant") == variant and not row.get("error")]
    published = [relation for row in good for relation in row.get("published") or []]
    rejected = [relation for row in good for relation in row.get("rejected") or []]
    usage = {name: sum(int((row.get("usage") or {}).get(name, 0)) for row in good)
             for name in ("calls", "input_tokens", "output_tokens",
                          "duration_ms", "errors")}
    walls = [int(row.get("wall_ms") or 0) for row in good]
    by_repeat = {}
    for repetition in range(1, repetitions + 1):
        repeat_rows = [row for row in good if row.get("repetition") == repetition]
        fingerprints = {(row["case_no"], fingerprint)
                        for row in repeat_rows
                        for fingerprint in _row_fingerprints(row)}
        by_repeat[str(repetition)] = {
            "cases": len(repeat_rows),
            "published": sum(len(row.get("published") or []) for row in repeat_rows),
            "rejected": sum(len(row.get("rejected") or []) for row in repeat_rows),
            "unique_case_relations": len(fingerprints),
            "relation_types": dict(sorted(Counter(
                relation.get("relation_type") for row in repeat_rows
                for relation in row.get("published") or []).items())),
        }

    paired_jaccards = []
    stable, union = set(), set()
    case_ids = sorted({row["case_no"] for row in good})
    for case_id in case_ids:
        sets = []
        for repetition in range(1, repetitions + 1):
            row = next((value for value in good
                        if value["case_no"] == case_id
                        and value["repetition"] == repetition), None)
            sets.append(_row_fingerprints(row or {}))
        if not sets:
            continue
        case_union = set().union(*sets)
        case_stable = set.intersection(*sets) if sets else set()
        union.update((case_id, value) for value in case_union)
        stable.update((case_id, value) for value in case_stable)
        paired_jaccards.append(
            len(case_stable) / len(case_union) if case_union else 1.0)

    def path(row, evidence_id):
        return str(next((item.get("path") for item in row.get("inventory") or []
                         if item.get("evidence_id") == evidence_id), ""))

    cm009_bad, cm036_actor, cm045_version = [], [], []
    for row in good:
        for relation in row.get("published") or []:
            relation_type = relation.get("relation_type")
            if (row["case_no"] == "cm-009" and relation_type == "EXCEPTION_TO"
                    and "제16조" in path(row, relation.get("source_id"))
                    and "제13조" in path(row, relation.get("target_id"))):
                cm009_bad.append((row["repetition"], relation.get("relation_id")))
            if (row["case_no"] == "cm-036" and relation_type == "GOVERNS_ACTOR"
                    and "제8조" in path(row, relation.get("source_id"))
                    and any(value in str(relation.get("target_value") or "")
                            for value in ("대표자", "상근이사", "업무를 집행"))):
                cm036_actor.append((row["repetition"], relation.get("target_value")))
            if row["case_no"] == "cm-045" and relation_type == "CURRENT_VERSION_OF":
                cm045_version.append((row["repetition"], relation.get("relation_id")))

    candidate_count = len(published) + len(rejected)
    return {
        "case_runs": len(good),
        "candidates": candidate_count,
        "published": len(published),
        "rejected": len(rejected),
        "guard_acceptance_rate": round(len(published) / candidate_count, 4)
        if candidate_count else 0,
        "usage": usage,
        "wall_ms_p50": _percentile(walls, .5),
        "wall_ms_p95": _percentile(walls, .95),
        "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
        "by_repeat": by_repeat,
        "stability": {
            "stable_case_relations": len(stable),
            "union_case_relations": len(union),
            "all_repeat_capture_rate": round(len(stable) / len(union), 4)
            if union else 1.0,
            "mean_case_jaccard": round(statistics.mean(paired_jaccards), 4)
            if paired_jaccards else 1.0,
        },
        "guard_checks": {
            "all_calls_haiku": all(row.get("model") == HAIKU_MODEL for row in good),
            "published_validation_rate_100pct": all(
                not relation.get("validation_errors") for relation in published),
            "invalid_candidates_not_published": all(
                relation.get("validation_errors") for relation in rejected),
            "cm009_no_false_exception_16_to_13": not cm009_bad,
            "cm036_actor_found_in_every_repeat": len({value[0] for value in cm036_actor})
            == repetitions,
            "cm045_no_fake_version": not cm045_version,
        },
        "known_case_observations": {
            "cm009_false_exception": cm009_bad,
            "cm036_actor": cm036_actor,
            "cm045_version": cm045_version,
        },
    }


def summarize(rows, repetitions):
    mixed = _variant_summary(rows, "mixed", repetitions)
    families = _variant_summary(rows, "families", repetitions)
    good = [row for row in rows if not row.get("error")]

    def all_keys(variant):
        return {(row["case_no"], row["repetition"], fingerprint)
                for row in good if row["variant"] == variant
                for fingerprint in _row_fingerprints(row)}

    mixed_keys, family_keys = all_keys("mixed"), all_keys("families")

    def ratio(numerator, denominator):
        return round(numerator / denominator, 4) if denominator else None

    return {
        "mixed": mixed,
        "families": families,
        "comparison": {
            "shared_published_case_run_relations": len(mixed_keys & family_keys),
            "mixed_only_published_case_run_relations": len(mixed_keys - family_keys),
            "families_only_published_case_run_relations": len(family_keys - mixed_keys),
            "families_to_mixed_input_token_ratio": ratio(
                families["usage"]["input_tokens"], mixed["usage"]["input_tokens"]),
            "families_to_mixed_output_token_ratio": ratio(
                families["usage"]["output_tokens"], mixed["usage"]["output_tokens"]),
            "families_to_mixed_call_ratio": ratio(
                families["usage"]["calls"], mixed["usage"]["calls"]),
            "families_to_mixed_wall_mean_ratio": ratio(
                families["wall_ms_mean"], mixed["wall_ms_mean"]),
            "stability_delta": round(
                families["stability"]["all_repeat_capture_rate"]
                - mixed["stability"]["all_repeat_capture_rate"], 4),
        },
        "contract": {
            "all_models_haiku": all(row.get("model") == HAIKU_MODEL for row in good),
            "question_in_product_input": False,
            "case_id_in_product_input": False,
            "gold_in_product_input": False,
            "reference_answer_in_product_input": False,
            "main_wiring_changed": False,
            "canonical_changed": False,
            "families": {name: list(values)
                         for name, values in RELATION_FAMILIES.items()},
        },
        "errors": [row for row in rows if row.get("error")],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    parser.add_argument("--repetitions", type=int, choices=range(2, 6), default=2)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()

    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    selected_by_id = {str(row["case_no"]): row
                      for row in retrieval.get("rows") or []}
    case_ids = [value.strip() for value in args.cases.split(",") if value.strip()]
    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU_MODEL:
        raise SystemExit("Haiku LLM 설정이 필요합니다")
    index = index_mod.current()
    local = threading.local()

    frozen_evidence = {}
    for case_id in case_ids:
        selected = (((selected_by_id[case_id].get("variants") or {})
                    .get(args.variant) or {}).get("selected") or [])
        evidence = reconstruct_evidence(index, list(selected))
        for row in evidence:
            view = index.docs.get(str(row.get("doc_id") or ""))
            if view is not None:
                row.update({
                    "document_revision": str(getattr(view, "revised", "") or ""),
                    "document_enforcement": str(getattr(view, "enforce", "") or ""),
                    "document_current": bool(getattr(view, "is_current", True)),
                })
        frozen_evidence[case_id] = evidence

    def evaluate(case_id, repetition, experiment_variant):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        evidence = frozen_evidence[case_id]
        log0 = len(llm.log)
        started = time.perf_counter()
        if experiment_variant == "mixed":
            result = compile_source_relations(llm, evidence)
            validation = result["validation"]
            published = validation["published"]
            rejected = validation["rejected"]
            unresolved = list((result.get("raw") or {}).get("unresolved") or [])
            family_counts = {}
        else:
            result = compile_source_relation_families(llm, evidence)
            published = result["published"]
            rejected = result["rejected"]
            unresolved = result["unresolved"]
            family_counts = {
                value["family"]: {
                    "published": value["validation"]["published_count"],
                    "rejected": value["validation"]["rejected_count"],
                } for value in result["family_results"]
            }
        wall_ms = round((time.perf_counter() - started) * 1000)
        usage = _usage(list(llm.log)[log0:])
        prompt_contract = json.dumps({
            "inventory": result["inventory"], "cards": result["cards"]},
            ensure_ascii=False, sort_keys=True)
        return {
            "case_no": case_id,
            "repetition": repetition,
            "variant": experiment_variant,
            "model": HAIKU_MODEL,
            "product_input_sha256": hashlib.sha256(
                prompt_contract.encode("utf-8")).hexdigest(),
            "inventory": result["inventory"],
            "published": published,
            "rejected": rejected,
            "unresolved": unresolved,
            "family_counts": family_counts,
            "usage": usage,
            "wall_ms": wall_ms,
        }

    specs = [(case_id, repetition, variant)
             for repetition in range(1, args.repetitions + 1)
             for case_id in case_ids for variant in ("mixed", "families")]
    positions = {spec: position for position, spec in enumerate(specs)}
    rows = []
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, *spec): spec for spec in specs}
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            spec = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": spec[0], "repetition": spec[1],
                       "variant": spec[2],
                       "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            rows.sort(key=lambda value: positions[
                (value["case_no"], value["repetition"], value["variant"])])
            blob = {
                "experiment": "haiku-source-relation-family-split-repeat-v1",
                "source_retrieval": str(args.retrieval_ablation),
                "repetitions": args.repetitions,
                "case_ids": case_ids,
                "summary": summarize(rows, args.repetitions),
                "rows": rows,
            }
            args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n",
                                "utf-8")
            status = "ERROR" if row.get("error") else (
                f"published={len(row['published'])} rejected={len(row['rejected'])}")
            print(f"[{completed:02d}/{len(specs)}] r{spec[1]} {spec[0]} "
                  f"{spec[2]} {status}", flush=True)
    final = summarize(rows, args.repetitions)
    print(json.dumps(final, ensure_ascii=False, indent=1))
    return 1 if final["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
