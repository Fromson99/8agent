#!/usr/bin/env python3
"""mixed pass 대비 Haiku EXCEPTION_TO 2-pass 표적 복구를 평가한다."""

from __future__ import annotations

import argparse
import concurrent.futures
from collections import Counter, defaultdict
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
from lawrag.core.rag.experiments.haiku_exception_rescue import (  # noqa: E402
    compile_exception_rescue,
)
from lawrag.core.rag.experiments.haiku_legal_methods import HAIKU_MODEL  # noqa: E402
from scripts import review_golden as review  # noqa: E402
from scripts.rag_haiku_source_relations_consensus import (  # noqa: E402
    relation_fingerprint,
)
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


def _path(inventory, evidence_id):
    return str(next((row.get("path") for row in inventory
                     if row.get("evidence_id") == evidence_id), ""))


def _record(case_no, pass_name, relation, inventory):
    return {
        "case_no": case_no,
        "pass_name": pass_name,
        "fingerprint": relation_fingerprint(relation, inventory, normalized=True),
        "relation": relation,
        "inventory": inventory,
        "source_path": _path(inventory, relation.get("source_id")),
        "target_path": _path(inventory, relation.get("target_id")),
    }


def load_mixed_records(paths, case_ids):
    """단일 다반복 artifact 또는 반복별 artifact를 같은 pass record로 읽는다."""
    records, usage, walls, hashes, pass_names = [], Counter(), [], {}, set()
    wanted = set(case_ids)
    for path in paths:
        artifact = json.loads(path.read_text("utf-8"))
        for row in artifact.get("rows") or []:
            if row.get("error") or row.get("case_no") not in wanted:
                continue
            if row.get("variant") and row.get("variant") != "mixed":
                continue
            suffix = f":r{row['repetition']}" if row.get("repetition") else ""
            pass_name = f"{path.stem}{suffix}"
            pass_names.add(pass_name)
            case_no = str(row["case_no"])
            hashes[(pass_name, case_no)] = str(row.get("product_input_sha256") or "")
            row_usage = row.get("usage") or {}
            for name in ("calls", "input_tokens", "output_tokens",
                         "duration_ms", "errors"):
                usage[name] += int(row_usage.get(name) or 0)
            walls.append(int(row.get("wall_ms") or 0))
            inventory = list(row.get("inventory") or [])
            for relation in row.get("published") or []:
                if relation.get("relation_type") == "EXCEPTION_TO":
                    records.append(_record(case_no, pass_name, relation, inventory))
    return {"records": records, "usage": dict(usage), "walls": walls,
            "hashes": hashes, "pass_names": sorted(pass_names)}


def aggregate(records, pass_names):
    values = {}
    for record in records:
        key = (record["case_no"], record["fingerprint"])
        item = values.setdefault(key, {"passes": set(), "records": []})
        item["passes"].add(record["pass_name"])
        item["records"].append(record)
    union, stable = [], []
    for (case_no, fingerprint), item in values.items():
        representative = item["records"][0]
        row = {
            "case_no": case_no,
            "fingerprint": json.dumps(fingerprint, ensure_ascii=False,
                                      separators=(",", ":")),
            "support_count": len(item["passes"]),
            "passes": sorted(item["passes"]),
            "source_path": representative["source_path"],
            "target_path": representative["target_path"],
            "relation": representative["relation"],
        }
        union.append(row)
        if len(item["passes"]) == len(pass_names):
            stable.append(row)
    union.sort(key=lambda row: (row["case_no"], row["fingerprint"]))
    stable.sort(key=lambda row: (row["case_no"], row["fingerprint"]))
    return {"union": union, "stable": stable,
            "union_count": len(union), "stable_count": len(stable),
            "stable_rate": round(len(stable) / len(union), 4) if union else 1.0}


def _keys(rows):
    return {(row["case_no"], row["fingerprint"]) for row in rows}


def _wall_summary(walls):
    return {
        "p50": _percentile(walls, .5), "p95": _percentile(walls, .95),
        "mean": round(statistics.mean(walls), 3) if walls else 0,
    }


def summarize(rescue_rows, mixed, repetitions):
    good = [row for row in rescue_rows if not row.get("error")]
    rescue_records = [
        _record(row["case_no"], f"rescue:r{row['repetition']}", relation,
                row.get("inventory") or [])
        for row in good for relation in row.get("published") or []]
    rescue_passes = [f"rescue:r{value}" for value in range(1, repetitions + 1)]
    mixed_agg = aggregate(mixed["records"], mixed["pass_names"])
    rescue_agg = aggregate(rescue_records, rescue_passes)
    mixed_union = _keys(mixed_agg["union"])
    rescue_union = _keys(rescue_agg["union"])
    rescue_stable = _keys(rescue_agg["stable"])
    usage = {name: sum(int((row.get("usage") or {}).get(name, 0)) for row in good)
             for name in ("calls", "input_tokens", "output_tokens",
                          "duration_ms", "errors")}
    rejected = [relation for row in good for relation in row.get("rejected") or []]
    published = [relation for row in good for relation in row.get("published") or []]
    walls = [int(row.get("wall_ms") or 0) for row in good]

    false_cm009 = [row for row in rescue_agg["union"]
                   if row["case_no"] == "cm-009"
                   and "제16조" in row["source_path"]
                   and "제13조" in row["target_path"]]
    hashes_match = all(
        row.get("evidence_input_sha256")
        in {value for (pass_name, case_no), value in mixed["hashes"].items()
            if case_no == row["case_no"]}
        for row in good)

    one_mixed_input = (mixed["usage"].get("input_tokens", 0)
                       / max(len(mixed["pass_names"]), 1))
    one_mixed_calls = (mixed["usage"].get("calls", 0)
                       / max(len(mixed["pass_names"]), 1))
    return {
        "mixed_exception": {**mixed_agg, "usage": mixed["usage"],
                            "wall_ms": _wall_summary(mixed["walls"]),
                            "passes": mixed["pass_names"]},
        "targeted_rescue": {
            **rescue_agg,
            "candidate_count": len(published) + len(rejected),
            "published_occurrences": len(published),
            "rejected_occurrences": len(rejected),
            "usage": usage, "wall_ms": _wall_summary(walls),
        },
        "increment": {
            "rescue_union_not_in_mixed_union": len(rescue_union - mixed_union),
            "rescue_stable_not_in_mixed_union": len(rescue_stable - mixed_union),
            "mixed_union_missed_by_rescue": len(mixed_union - rescue_union),
            "combined_mixed_union_plus_rescue_stable": len(
                mixed_union | rescue_stable),
            "additional_input_tokens": usage["input_tokens"],
            "additional_calls": usage["calls"],
            "additional_input_vs_one_mixed_pass": round(
                usage["input_tokens"] / one_mixed_input, 4)
            if one_mixed_input else None,
            "additional_calls_vs_one_mixed_pass": round(
                usage["calls"] / one_mixed_calls, 4)
            if one_mixed_calls else None,
        },
        "guards": {
            "all_calls_haiku": all(row.get("model") == HAIKU_MODEL for row in good),
            "same_frozen_evidence_as_mixed": hashes_match,
            "published_validation_rate_100pct": all(
                not relation.get("validation_errors") for relation in published),
            "invalid_candidates_not_published": all(
                relation.get("validation_errors") for relation in rejected),
            "cm009_no_false_exception_16_to_13": not false_cm009,
        },
        "errors": [row for row in rescue_rows if row.get("error")],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--mixed-inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--retrieval-variant", default="control_d_then_verifier")
    parser.add_argument("--repetitions", type=int, choices=range(2, 6), default=2)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()

    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    selected_by_id = {str(row["case_no"]): row
                      for row in retrieval.get("rows") or []}
    case_ids = [value.strip() for value in args.cases.split(",") if value.strip()]
    mixed = load_mixed_records(args.mixed_inputs, case_ids)
    if len(mixed["pass_names"]) != args.repetitions:
        raise SystemExit(f"mixed pass 수 불일치: {mixed['pass_names']}")
    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU_MODEL:
        raise SystemExit("Haiku LLM 설정이 필요합니다")
    index = index_mod.current()
    local = threading.local()
    evidence_by_case = {}
    for case_id in case_ids:
        selected = (((selected_by_id[case_id].get("variants") or {})
                    .get(args.retrieval_variant) or {}).get("selected") or [])
        evidence = reconstruct_evidence(index, list(selected))
        for row in evidence:
            view = index.docs.get(str(row.get("doc_id") or ""))
            if view is not None:
                row.update({
                    "document_revision": str(getattr(view, "revised", "") or ""),
                    "document_enforcement": str(getattr(view, "enforce", "") or ""),
                    "document_current": bool(getattr(view, "is_current", True)),
                })
        evidence_by_case[case_id] = evidence

    def evaluate(case_no, repetition):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        log0 = len(llm.log)
        started = time.perf_counter()
        result = compile_exception_rescue(llm, evidence_by_case[case_no])
        wall_ms = round((time.perf_counter() - started) * 1000)
        validation = result["validation"]
        evidence_contract = json.dumps({"inventory": result["inventory"],
                                        "cards": result["cards"]},
                                       ensure_ascii=False, sort_keys=True)
        product = str(result.get("product_input") or "")
        return {
            "case_no": case_no, "repetition": repetition, "model": HAIKU_MODEL,
            "product_input_sha256": hashlib.sha256(product.encode()).hexdigest(),
            "evidence_input_sha256": hashlib.sha256(
                evidence_contract.encode()).hexdigest(),
            "inventory": result["inventory"],
            "candidate_menu": result.get("candidates") or [],
            "published": validation["published"],
            "rejected": validation["rejected"],
            "unresolved": list((result.get("raw") or {}).get("unresolved") or []),
            "usage": _usage(list(llm.log)[log0:]), "wall_ms": wall_ms,
        }

    specs = [(case_no, repetition) for repetition in range(1, args.repetitions + 1)
             for case_no in case_ids]
    positions = {spec: index for index, spec in enumerate(specs)}
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
            rows.sort(key=lambda value: positions[
                (value["case_no"], value["repetition"])])
            summary = summarize(rows, mixed, args.repetitions)
            artifact = {
                "experiment": "haiku-exception-to-targeted-rescue-v1",
                "dataset": args.dataset_name,
                "contract": {
                    "model": HAIKU_MODEL, "repetitions": args.repetitions,
                    "question_in_product_input": False,
                    "case_id_in_product_input": False,
                    "gold_in_product_input": False,
                    "reference_answer_in_product_input": False,
                    "main_wiring_changed": False, "canonical_changed": False,
                },
                "cases": case_ids, "mixed_inputs": [str(p) for p in args.mixed_inputs],
                "summary": summary, "rows": rows,
            }
            args.out.write_text(json.dumps(artifact, ensure_ascii=False, indent=1) + "\n",
                                "utf-8")
            status = "ERROR" if row.get("error") else (
                f"published={len(row['published'])} rejected={len(row['rejected'])}")
            print(f"[{completed:02d}/{len(specs)}] r{spec[1]} {spec[0]} {status}",
                  flush=True)
    final = summarize(rows, mixed, args.repetitions)
    print(json.dumps(final, ensure_ascii=False, indent=1))
    return 1 if final["errors"] or not all(final["guards"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
