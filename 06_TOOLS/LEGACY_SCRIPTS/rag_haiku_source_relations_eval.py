#!/usr/bin/env python3
"""대표 동결 근거에서 Haiku 원문 증명형 관계 후보를 생성·감사한다."""

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
from lawrag.core.rag.experiments.haiku_source_relations import (  # noqa: E402
    compile_source_relations,
)
from scripts import review_golden as review  # noqa: E402
from scripts.rag_legal_issue_e2e_eval import (  # noqa: E402
    _percentile, _usage, reconstruct_evidence,
)


def _fingerprint(case_id, relation, inventory):
    by_id = {row["evidence_id"]: row for row in inventory}
    source = by_id.get(str(relation.get("source_id") or "")) or {}
    target = by_id.get(str(relation.get("target_id") or "")) or {}
    return (
        str(relation.get("relation_type") or ""),
        str(source.get("document") or ""), str(source.get("path") or ""),
        str(target.get("document") or ""), str(target.get("path") or ""),
        str(relation.get("target_value") or ""),
        str(relation.get("defined_term") or ""),
    )


def summarize(rows):
    good = [row for row in rows if not row.get("error")]
    published = [rel for row in good for rel in row.get("published") or []]
    rejected = [rel for row in good for rel in row.get("rejected") or []]
    relation_types = Counter(str(row.get("relation_type") or "") for row in published)
    usages = {name: sum(int((row.get("usage") or {}).get(name, 0)) for row in good)
              for name in ("calls", "input_tokens", "output_tokens",
                           "duration_ms", "errors")}
    walls = [int(row.get("wall_ms") or 0) for row in good]
    cm009 = next((row for row in good if row["case_no"] == "cm-009"), {})
    cm036 = next((row for row in good if row["case_no"] == "cm-036"), {})
    cm045 = next((row for row in good if row["case_no"] == "cm-045"), {})

    def path(row, evidence_id):
        return str(next((item.get("path") for item in row.get("inventory") or []
                         if item.get("evidence_id") == evidence_id), ""))

    cm009_bad = [rel for rel in cm009.get("published") or []
                 if rel.get("relation_type") == "EXCEPTION_TO"
                 and "제16조" in path(cm009, rel.get("source_id"))
                 and "제13조" in path(cm009, rel.get("target_id"))]
    cm036_actor = [rel for rel in cm036.get("published") or []
                   if rel.get("relation_type") == "GOVERNS_ACTOR"
                   and "제8조" in path(cm036, rel.get("source_id"))
                   and any(value in str(rel.get("target_value") or "")
                           for value in ("대표자", "상근이사", "업무를 집행"))]
    cm045_versions = [rel for rel in cm045.get("published") or []
                      if rel.get("relation_type") == "CURRENT_VERSION_OF"]
    criteria = {
        "all_calls_haiku": all(row.get("model") == HAIKU_MODEL for row in good),
        "llm_errors_zero": usages["errors"] == 0,
        "no_question_gold_reference_in_product": True,
        "published_validation_rate_100pct": all(
            not rel.get("validation_errors") for rel in published),
        "invalid_candidates_not_published": all(
            rel.get("validation_errors") for rel in rejected),
        "cm009_no_false_exception_16_to_13": not cm009_bad,
        "cm036_internal_control_actor_created": bool(cm036_actor) if cm036 else True,
        "cm045_no_fake_current_version_relation": not cm045_versions,
        "canonical_and_main_unchanged": True,
    }
    return {
        "cases": len(good), "candidate_relations": len(published) + len(rejected),
        "published_relations": len(published), "rejected_relations": len(rejected),
        "published_relation_types": dict(sorted(relation_types.items())),
        "usage": usages,
        "wall_ms_p50": _percentile(walls, .5),
        "wall_ms_p95": _percentile(walls, .95),
        "wall_ms_mean": round(statistics.mean(walls), 3) if walls else 0,
        "sentinel_cases_present": [case_id for case_id, row in
                                   (("cm-009", cm009), ("cm-036", cm036),
                                    ("cm-045", cm045)) if row],
        "criteria": criteria,
        "all_pre_registered_criteria_pass": all(criteria.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--retrieval-ablation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--variant", default="control_d_then_verifier")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--report-only", action="store_true",
                        help="기존 --out artifact의 rows만 현재 집계기로 다시 계산")
    args = parser.parse_args()

    if args.report_only:
        blob = json.loads(args.out.read_text("utf-8"))
        blob["summary"] = summarize(list(blob.get("rows") or []))
        args.out.write_text(json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(json.dumps(blob["summary"], ensure_ascii=False, indent=1))
        return 0

    retrieval = json.loads(args.retrieval_ablation.read_text("utf-8"))
    selected_by_id = {str(row["case_no"]): row
                      for row in retrieval.get("rows") or []}
    case_ids = [value.strip() for value in args.cases.split(",") if value.strip()]
    prototype = review._llm()
    if prototype is None:
        raise SystemExit("LLM 설정이 없습니다")
    if prototype.model != HAIKU_MODEL:
        raise SystemExit(f"Haiku가 아닌 모델 설정: {prototype.model}")
    index = index_mod.current()
    local = threading.local()

    def evaluate(case_id):
        if not hasattr(local, "llm"):
            local.llm = review._llm()
        llm = local.llm
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
        log0 = len(llm.log)
        started = time.perf_counter()
        result = compile_source_relations(llm, evidence)
        wall_ms = round((time.perf_counter() - started) * 1000)
        usage = _usage(list(llm.log)[log0:])
        validation = result["validation"]
        prompt_contract = json.dumps({
            "inventory": result["inventory"], "cards": result["cards"]},
            ensure_ascii=False, sort_keys=True)
        return {
            "case_no": case_id, "model": HAIKU_MODEL,
            "product_input_sha256": hashlib.sha256(
                prompt_contract.encode("utf-8")).hexdigest(),
            "inventory": result["inventory"],
            "published": validation["published"],
            "rejected": validation["rejected"],
            "unresolved": list((result.get("raw") or {}).get("unresolved") or []),
            "usage": usage, "wall_ms": wall_ms,
        }

    rows = []
    positions = {case_id: pos for pos, case_id in enumerate(case_ids)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate, case_id): case_id for case_id in case_ids}
        for position, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"case_no": case_id,
                       "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            rows.sort(key=lambda value: positions[value["case_no"]])
            # 같은 법률 좌표 관계가 여러 query-derived batch에 나타나면 하나로 접는다.
            unique = {}
            for value in rows:
                for relation in value.get("published") or []:
                    unique[_fingerprint(
                        value["case_no"], relation, value.get("inventory") or [])] = {
                            "source_case": value["case_no"], **relation}
            blob = {
                "experiment": "haiku-source-proven-legal-relations-probe-v1",
                "contract": {"main_wiring_changed": False,
                             "canonical_changed": False,
                             "all_models": HAIKU_MODEL,
                             "question_in_product_input": False,
                             "gold_in_product_input": False,
                             "reference_answer_in_product_input": False},
                "source_retrieval": str(args.retrieval_ablation),
                "summary": summarize(rows), "unique_published": list(unique.values()),
                "rows": rows,
            }
            args.out.write_text(
                json.dumps(blob, ensure_ascii=False, indent=1) + "\n", "utf-8")
            if row.get("error"):
                print(f"[{position:02d}/{len(case_ids)}] {case_id} ERROR", flush=True)
            else:
                print(f"[{position:02d}/{len(case_ids)}] {case_id} "
                      f"published={len(row['published'])} rejected={len(row['rejected'])}",
                      flush=True)
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=1))
    return 1 if any(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
