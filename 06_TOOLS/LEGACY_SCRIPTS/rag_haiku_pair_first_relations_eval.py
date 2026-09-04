#!/usr/bin/env python3
"""결정론적 pair-first+Haiku 관계 판정의 반복 안정성과 mixed 추출을 비교한다."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import concurrent.futures
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
from lawrag.core.rag.experiments.haiku_legal_methods import provenance_path  # noqa: E402
from lawrag.core.rag.experiments.haiku_pair_first_relations import (  # noqa: E402
    MAX_PAIRS_PER_CASE,
    MAX_PAIRS_PER_RELATION,
    PAIR_RELATIONS,
    compile_pair_first_relations,
)
from scripts import review_golden as review  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


def _packed(value):
    return "".join(character for character in str(value or "").casefold()
                   if character.isalnum())


def _fingerprint(relation, inventory):
    by_id = {str(row.get("evidence_id") or row.get("id") or ""): row
             for row in inventory}
    source = by_id.get(str(relation.get("source_id") or "")) or {}
    target = by_id.get(str(relation.get("target_id") or "")) or {}
    relation_type = str(relation.get("relation_type") or "")
    target_value = "" if relation_type in PAIR_RELATIONS else relation.get("target_value")
    return (
        relation_type,
        _packed(source.get("document")),
        _packed(provenance_path(str(source.get("path") or ""))[0]),
        _packed(target.get("document")),
        _packed(provenance_path(str(target.get("path") or ""))[0]),
        _packed(target_value),
        _packed(relation.get("defined_term")),
    )


def _row_set(row, relation_type=None):
    return {_fingerprint(relation, row.get("inventory") or [])
            for relation in row.get("published") or []
            if relation_type is None
            or relation.get("relation_type") == relation_type}


def _stability(rows, repetitions):
    result = {}
    for relation_type in (*PAIR_RELATIONS, "ALL"):
        stable, union, case_jaccards = set(), set(), []
        for case_id in sorted({row["case_no"] for row in rows}):
            sets = []
            for repetition in range(1, repetitions + 1):
                row = next((value for value in rows
                            if value["case_no"] == case_id
                            and value["repetition"] == repetition), {})
                if relation_type == "ALL":
                    sets.append(set().union(*(
                        _row_set(row, value) for value in PAIR_RELATIONS)))
                else:
                    sets.append(_row_set(row, relation_type))
            case_union = set().union(*sets)
            case_stable = set.intersection(*sets) if sets else set()
            union.update((case_id, value) for value in case_union)
            stable.update((case_id, value) for value in case_stable)
            case_jaccards.append(
                len(case_stable) / len(case_union) if case_union else 1.0)
        result[relation_type] = {
            "intersection": len(stable), "union": len(union),
            "intersection_over_union": round(len(stable) / len(union), 4)
            if union else 1.0,
            "mean_case_jaccard": round(statistics.mean(case_jaccards), 4)
            if case_jaccards else 1.0,
        }
    return result


def _load_mixed(paths, case_ids):
    selected = []
    fallback_repetition = 0
    for path in paths:
        blob = json.loads(path.read_text("utf-8"))
        source_rows = list(blob.get("rows") or [])
        has_repetitions = any(row.get("repetition") is not None for row in source_rows)
        if not has_repetitions:
            fallback_repetition += 1
        for row in source_rows:
            if row.get("case_no") not in case_ids or row.get("error"):
                continue
            if row.get("variant") and row.get("variant") != "mixed":
                continue
            copy = dict(row)
            copy["repetition"] = int(row.get("repetition") or fallback_repetition or 1)
            selected.append(copy)
    # Duplicate artifacts may contain the same case/repetition; last path wins.
    unique = {(row["case_no"], row["repetition"]): row for row in selected}
    return list(unique.values())


def _usage_summary(rows):
    usage = {name: sum(int((row.get("usage") or {}).get(name, 0)) for row in rows)
             for name in ("calls", "input_tokens", "output_tokens",
                          "duration_ms", "errors")}
    walls = [int(row.get("wall_ms") or 0) for row in rows]
    return {
        "usage": usage,
        "wall_ms_p50": _percentile(walls, .5),
        "wall_ms_p95": _percentile(walls, .95),
        "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
    }


def summarize(rows, repetitions, mixed_rows):
    good = [row for row in rows if not row.get("error")]
    published = [relation for row in good for relation in row.get("published") or []]
    rejected = [relation for row in good for relation in row.get("rejected") or []]
    overflow = [relation for row in good for relation in row.get("overflow") or []]
    pair_count = sum(int(row.get("pair_count") or 0) for row in good)
    pair_keys = defaultdict(set)
    mixed_keys = defaultdict(set)
    for row in good:
        for fingerprint in _row_set(row):
            pair_keys[fingerprint[0]].add((row["case_no"], fingerprint))
    for row in mixed_rows:
        for fingerprint in _row_set(row):
            if fingerprint[0] in PAIR_RELATIONS:
                mixed_keys[fingerprint[0]].add((row["case_no"], fingerprint))

    comparison = {}
    for relation_type in PAIR_RELATIONS:
        left, right = pair_keys[relation_type], mixed_keys[relation_type]
        relation_union = left | right
        comparison[relation_type] = {
            "pair_first_union": len(left), "mixed_union": len(right),
            "intersection": len(left & right),
            "pair_first_only": len(left - right),
            "mixed_only": len(right - left),
            "jaccard": round(len(left & right) / len(relation_union), 4)
            if relation_union else 1.0,
        }

    invalid_published = [relation for relation in published
                         if relation.get("validation_errors")]
    partial_proof = [relation for relation in published
                     if not {quote["quote_id"] for quote in relation["proof_quotes"]
                             if quote.get("kind") == "source"}.issubset(
                         set((relation.get("decision") or {}).get("quote_ids") or []))]
    product_hash_stability = {}
    for case_id in sorted({row["case_no"] for row in good}):
        hashes = {row.get("product_input_sha256") for row in good
                  if row["case_no"] == case_id}
        product_hash_stability[case_id] = len(hashes) == 1

    pair_usage = _usage_summary(good)
    mixed_usage = _usage_summary(mixed_rows)
    pair_tokens = pair_usage["usage"]["input_tokens"]
    mixed_tokens = mixed_usage["usage"]["input_tokens"]
    return {
        "case_runs": len(good),
        "cases": len({row["case_no"] for row in good}),
        "repetitions": repetitions,
        "closed_pairs": pair_count,
        "published": len(published),
        "model_or_guard_rejected": len(rejected),
        "overflow_fail_closed": len(overflow),
        "candidate_relation_types": dict(sorted(Counter(
            relation.get("relation_type") for row in good
            for relation in row.get("pairs") or []).items())),
        "published_relation_types": dict(sorted(Counter(
            relation.get("relation_type") for relation in published).items())),
        "guard_acceptance_rate": round(len(published) / pair_count, 4)
        if pair_count else 1.0,
        "pair_first": {**pair_usage, "stability": _stability(good, repetitions)},
        "mixed_control": {
            **mixed_usage,
            "case_runs": len(mixed_rows),
            "stability": _stability(mixed_rows, repetitions) if mixed_rows else {},
        },
        "pair_first_to_mixed_input_token_ratio": round(pair_tokens / mixed_tokens, 4)
        if mixed_tokens else None,
        "method_comparison_by_relation": comparison,
        "precision_guard": {
            "published_validation_rate_100pct": not invalid_published,
            "published_used_all_mandatory_source_quotes": not partial_proof,
            "all_invalid_or_none_not_published": all(
                relation not in published for relation in rejected),
            "complete_decision_contract_every_run": all(
                row.get("complete_decision_contract") for row in good),
            "pair_caps_respected": all(
                int(row.get("pair_count") or 0) <= MAX_PAIRS_PER_CASE
                and all(count <= MAX_PAIRS_PER_RELATION
                        for count in (row.get("pair_counts") or {}).values())
                for row in good),
        },
        "contract": {
            "all_llm_calls_haiku": all(
                not row.get("llm_called") or row.get("model") == HAIKU_MODEL
                for row in good),
            "product_input_same_across_repetitions": all(
                product_hash_stability.values()),
            "question_in_product_input": False,
            "case_id_in_product_input": False,
            "gold_in_product_input": False,
            "reference_answer_in_product_input": False,
            "pair_cap_per_relation": MAX_PAIRS_PER_RELATION,
            "pair_cap_per_case": MAX_PAIRS_PER_CASE,
            "overflow_policy": "drop_and_record_fail_closed",
            "main_wiring_changed": False,
            "canonical_changed": False,
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
    parser.add_argument("--mixed-artifact", type=Path, action="append", default=[])
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    case_ids = [value.strip() for value in args.cases.split(",") if value.strip()]
    mixed_rows = _load_mixed(args.mixed_artifact, set(case_ids))
    if args.report_only:
        blob = json.loads(args.out.read_text("utf-8"))
        rows = list(blob.get("rows") or [])
        blob["mixed_artifacts"] = [str(path) for path in args.mixed_artifact]
        blob["summary"] = summarize(rows, args.repetitions, mixed_rows)
        args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n",
                            "utf-8")
        print(json.dumps(blob["summary"], ensure_ascii=False, indent=1))
        return 0

    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    selected_by_id = {str(row["case_no"]): row
                      for row in retrieval.get("rows") or []}
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

    def evaluate(case_id, repetition):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        log0 = len(llm.log)
        started = time.perf_counter()
        result = compile_pair_first_relations(llm, frozen_evidence[case_id])
        wall_ms = round((time.perf_counter() - started) * 1000)
        build, validation = result["pair_build"], result["validation"]
        inventory = [{
            "evidence_id": str(row.get("id") or f"E{position}"),
            "document": str(row.get("document") or ""),
            "path": str(row.get("path") or ""),
        } for position, row in enumerate(frozen_evidence[case_id], 1)]
        product = json.dumps(build["pairs"], ensure_ascii=False, sort_keys=True)
        return {
            "case_no": case_id, "repetition": repetition,
            "model": HAIKU_MODEL, "llm_called": result["llm_called"],
            "product_input_sha256": hashlib.sha256(product.encode()).hexdigest(),
            "inventory": inventory,
            "pair_count": build["pair_count"], "pair_counts": build["counts"],
            "raw_candidate_count": build["raw_candidate_count"],
            "pairs": build["pairs"], "overflow": build["overflow"],
            "published": validation["published"],
            "rejected": validation["rejected"],
            "complete_decision_contract": validation["complete_decision_contract"],
            "usage": _usage(list(llm.log)[log0:]), "wall_ms": wall_ms,
        }

    specs = [(case_id, repetition) for repetition in range(1, args.repetitions + 1)
             for case_id in case_ids]
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
                       "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            rows.sort(key=lambda value: positions[(value["case_no"], value["repetition"])])
            blob = {
                "experiment": "haiku-pair-first-source-relations-repeat-v1",
                "source_retrieval": str(args.retrieval_ablation),
                "mixed_artifacts": [str(path) for path in args.mixed_artifact],
                "case_ids": case_ids, "repetitions": args.repetitions,
                "summary": summarize(rows, args.repetitions, mixed_rows),
                "rows": rows,
            }
            args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n",
                                "utf-8")
            status = "ERROR" if row.get("error") else (
                f"pairs={row['pair_count']} published={len(row['published'])}")
            print(f"[{completed:02d}/{len(specs)}] r{spec[1]} {spec[0]} {status}",
                  flush=True)
    final = summarize(rows, args.repetitions, mixed_rows)
    print(json.dumps(final, ensure_ascii=False, indent=1))
    return 1 if final["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
