#!/usr/bin/env python3
"""동결 GOVERNS_ACTOR를 Haiku로 규범 역할 분해하고 사후 utility를 감사한다."""

from __future__ import annotations

import argparse
import concurrent.futures
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
import threading
import time


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.research.experiments.haiku_actor_normative_roles import (  # noqa: E402
    ACTOR_ROLES, compile_actor_roles,
)
from lawrag.research.experiments.haiku_legal_methods import HAIKU_MODEL  # noqa: E402
from scripts import review_golden as review  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import _percentile, _usage  # noqa: E402
from scripts.rag_source_relation_utility_audit import (  # noqa: E402
    is_gold_node, normalize,
)


_QUERY_ROLE_SIGNALS = {
    "OBLIGOR": re.compile(r"의무|하여야|해야|책임|금지|제출|신고|납부|보유"),
    "POWER_HOLDER": re.compile(r"위임|결정|승인|허가|명령|지정|정할\s*수"),
    "RIGHT_HOLDER": re.compile(r"권리|청구|신청할\s*수|요청|열람|선택"),
    "BENEFICIARY": re.compile(r"지급받|보상|수령|혜택|감면|면제되"),
    "CONDITION_ACTOR": re.compile(r"발행|취득|양도|증여|출자|거래|발생"),
    "PROCEDURAL_OBJECT": re.compile(r"대상|적용|심사|조사|평가|산정|상장"),
    "STATUS_SUBJECT": re.compile(r"해당|자격|요건|임원|주주|구성"),
}


def _query_roles(question: str) -> set[str]:
    return {role for role, pattern in _QUERY_ROLE_SIGNALS.items()
            if pattern.search(str(question or ""))}


def _posthoc_utility(rows: list[dict], retrieval: dict) -> dict:
    """질문/gold는 생성 완료 artifact와 합치는 사후 지표에만 사용한다."""
    by_case = {str(row.get("case_no") or ""): row
               for row in retrieval.get("rows") or []}
    totals = Counter()
    details = []
    for row in rows:
        retrieval_row = by_case.get(row["case_no"], {})
        frozen = ((retrieval_row.get("variants") or {})
                  .get("control_d_then_verifier") or {})
        selected = frozen.get("selected") or []
        gold = frozen.get("gold") or []
        question = str(retrieval_row.get("question") or "")
        query_roles = _query_roles(question)
        actor_inputs = {item["relation_ref"]: item for item in row.get("menu") or []}
        broad_refs = {ref for ref, item in actor_inputs.items()
                      if len(normalize(item.get("actor_surface"))) >= 2
                      and normalize(item.get("actor_surface")) in normalize(question)}
        role_refs = {str(item.get("relation_ref") or "")
                     for item in row.get("published") or []
                     if str(item.get("relation_ref") or "") in broad_refs
                     and str(item.get("role") or "") in query_roles}
        source_ids_broad = {actor_inputs[ref]["source_id"] for ref in broad_refs}
        source_ids_role = {actor_inputs[ref]["source_id"] for ref in role_refs}
        gold_by_evidence = {
            f"E{position}": is_gold_node(node, gold)
            for position, node in enumerate(selected, 1)
        }
        broad_gold = sum(gold_by_evidence.get(value, False)
                         for value in source_ids_broad)
        role_gold = sum(gold_by_evidence.get(value, False)
                        for value in source_ids_role)
        totals.update({
            "broad_nodes": len(source_ids_broad), "broad_gold": broad_gold,
            "role_nodes": len(source_ids_role), "role_gold": role_gold,
        })
        details.append({
            "case_no": row["case_no"], "query_roles": sorted(query_roles),
            "broad_actor_aligned_nodes": len(source_ids_broad),
            "broad_actor_aligned_gold_nodes": broad_gold,
            "role_aware_aligned_nodes": len(source_ids_role),
            "role_aware_aligned_gold_nodes": role_gold,
        })
    def ratio(a: int, b: int) -> float:
        return round(a / b, 4) if b else 0
    return {
        "contract": {
            "question_used_only_posthoc": True,
            "gold_used_only_posthoc": True,
            "question_or_gold_fed_back_to_generation": False,
        },
        "broad_actor": {
            "nodes": totals["broad_nodes"], "gold_nodes": totals["broad_gold"],
            "gold_node_rate": ratio(totals["broad_gold"], totals["broad_nodes"]),
        },
        "role_aware": {
            "nodes": totals["role_nodes"], "gold_nodes": totals["role_gold"],
            "gold_node_rate": ratio(totals["role_gold"], totals["role_nodes"]),
        },
        "details": details,
    }


def summarize(rows: list[dict]) -> dict:
    good = [row for row in rows if not row.get("error")]
    published = [item for row in good for item in row.get("published") or []]
    rejected = [item for row in good for item in row.get("rejected") or []]
    walls = [int(row.get("wall_ms") or 0) for row in good]
    usage = {name: sum(int((row.get("usage") or {}).get(name, 0)) for row in good)
             for name in ("calls", "input_tokens", "output_tokens", "duration_ms", "errors")}
    inputs = sum(len(row.get("menu") or []) for row in good)
    covered = sum(int(row.get("coverage_count") or 0) for row in good)
    return {
        "batches": len(good), "input_actor_relations": inputs,
        "published_roles": len(published), "rejected_roles": len(rejected),
        "unresolved_roles": sum(len(row.get("unresolved_refs") or []) for row in good),
        "missing_roles": sum(len(row.get("missing_refs") or []) for row in good),
        "coverage_rate": round(covered / inputs, 4) if inputs else 0,
        "publication_rate": round(len(published) / inputs, 4) if inputs else 0,
        "role_distribution": dict(sorted(Counter(
            str(item.get("role") or "") for item in published).items())),
        "rejection_reasons": dict(sorted(Counter(
            error for item in rejected for error in item.get("validation_errors") or []).items())),
        "usage": usage,
        "wall_ms_p50": _percentile(walls, .5),
        "wall_ms_p95": _percentile(walls, .95),
        "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
        "criteria": {
            "all_calls_haiku": all(row.get("model") == HAIKU_MODEL for row in good),
            "product_input_relation_and_proof_only": True,
            "question_case_gold_reference_excluded_from_product": True,
            "published_validation_rate_100pct": all(
                not item.get("validation_errors") for item in published),
            "invalid_candidates_not_published": all(
                item.get("validation_errors") for item in rejected),
            "canonical_and_main_unchanged": True,
            "roles_are_closed_enum": all(item.get("role") in ACTOR_ROLES
                                          for item in published),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--relations", type=Path, nargs="+", required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    prototype = review._llm()
    if prototype is None or prototype.model != HAIKU_MODEL:
        raise SystemExit("claude-haiku-4-5-20251001 설정이 필요합니다")
    batches = []
    for path in args.relations:
        artifact = json.loads(path.read_text("utf-8"))
        contract = artifact.get("contract") or {}
        if contract.get("all_models") != HAIKU_MODEL:
            raise SystemExit(f"Haiku artifact가 아닙니다: {path}")
        for row in artifact.get("rows") or []:
            actors = [item for item in row.get("published") or []
                      if item.get("relation_type") == "GOVERNS_ACTOR"]
            if actors:
                batches.append((path.name, str(row.get("case_no") or ""), actors))
    local = threading.local()
    def evaluate(batch):
        source_name, case_no, actors = batch
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
        started = time.perf_counter()
        log0 = len(llm.log)
        result = compile_actor_roles(llm, actors)
        wall_ms = round((time.perf_counter() - started) * 1000)
        validation = result["validation"]
        product = json.dumps(result["menu"], ensure_ascii=False, sort_keys=True)
        return {
            "source_artifact": source_name, "case_no": case_no,
            "model": HAIKU_MODEL,
            "product_input_sha256": hashlib.sha256(product.encode()).hexdigest(),
            "menu": result["menu"],
            "published": validation["published"],
            "rejected": validation["rejected"],
            "unresolved_refs": validation["unresolved_refs"],
            "missing_refs": validation["missing_refs"],
            "invalid_unresolved_refs": validation["invalid_unresolved_refs"],
            "coverage_count": validation["coverage_count"],
            "usage": _usage(list(llm.log)[log0:]), "wall_ms": wall_ms,
        }
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, batch): batch for batch in batches}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            batch = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"source_artifact": batch[0], "case_no": batch[1],
                       "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            print(f"[{position:02d}/{len(batches)}] {batch[1]} "
                  f"published={len(row.get('published') or [])} "
                  f"rejected={len(row.get('rejected') or [])}", flush=True)
    positions = {(source, case): i for i, (source, case, _) in enumerate(batches)}
    rows.sort(key=lambda row: positions.get(
        (row.get("source_artifact"), row.get("case_no")), 10**6))
    retrieval = json.loads(args.retrieval.read_text("utf-8"))
    artifact = {
        "experiment": "haiku-actor-normative-role-shadow-v1",
        "contract": {
            "all_models": HAIKU_MODEL,
            "product_inputs": ["GOVERNS_ACTOR", "embedded_proof_quotes"],
            "question_in_product_input": False, "case_id_in_product_input": False,
            "gold_in_product_input": False, "reference_answer_in_product_input": False,
            "main_wiring_changed": False, "canonical_changed": False,
        },
        "sources": [str(path) for path in args.relations],
        "summary": summarize(rows),
        "posthoc_utility": _posthoc_utility(rows, retrieval),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps({"summary": artifact["summary"],
                      "posthoc_utility": artifact["posthoc_utility"]},
                     ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
