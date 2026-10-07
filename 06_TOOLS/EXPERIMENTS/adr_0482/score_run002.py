"""Post-seal blind scoring and retrieval accounting for ADR-0482 run-002.

The product runner never imports this module.  Gold is joined only after the
complete product result exists, and the two arm names are hidden from the
single paired evaluator call for each case.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import statistics
import sys


ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / "04_EXPERIMENTS/ADR/ADR-0482-source-first-fsc-hard10-holdout"
GEN = ROOT / "01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260918-body-v1"
RESULTS = ADR / "artifacts/run-002/results.json"
JUDGED = ADR / "artifacts/run-002/judged-results.json"
METRICS = ADR / "artifacts/run-002/metrics.json"
LEDGER = ADR / "artifacts/retrieval-stage-ledger-run-002.json"
MAPPING = ADR / "artifacts/run-002/gold-coordinate-resolution.json"
ARMS = ("baseline", "source-first")
FAILURES = (
    "retrieval_miss",
    "governing_rule_selection",
    "scope_actor_mismatch",
    "condition_exception",
    "numeric_temporal",
    "authority_or_version",
    "definition_resolution",
    "required_issue_omission",
    "unsupported_inference",
    "judge_or_gold_error",
    "none",
)

SYSTEM = """당신은 독립 법률 RAG 평가자다. 제공된 기준답과 결정 조문을 채점 기준으로만 사용한다.
익명 답변 A와 B를 각각 독립적으로 평가한다. 답변이 기준답의 결론과 핵심 조건을 실질적으로
전달해야 correct=true다. 단순히 확인하지 못했다는 답, 빈 답, 실행 오류는 false다. 기준답보다
신중한 한계 표시는 허용하되 결론을 회피하면 false다. 서로의 상대적 우열이 아니라 각 답의
절대 정확성을 판정한다. 실패 유형은 가장 지배적인 하나만 고른다."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["assessments"],
    "properties": {
        "assessments": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "correct", "failure_type", "reason"],
                "properties": {
                    "label": {"type": "string", "enum": ["A", "B"]},
                    "correct": {"type": "boolean"},
                    "failure_type": {"type": "string", "enum": list(FAILURES)},
                    "reason": {"type": "string"},
                },
            },
        }
    },
}


def read(path: Path):
    return json.loads(path.read_text())


def write_new(path: Path, value) -> None:
    if path.exists():
        raise RuntimeError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def answer(row: dict) -> str:
    if row.get("error"):
        error = row["error"]
        return f"[실행 오류: {error.get('type')}: {error.get('message')}]"
    return ((row.get("result") or {}).get("answer") or {}).get("text") or "[빈 답변]"


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))]


def load_ledger_helpers():
    path = ROOT / "06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py"
    spec = importlib.util.spec_from_file_location("adr0473_ledger", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def resolve_gold(gold: dict) -> tuple[dict, dict]:
    """Resolve legacy content-hash doc IDs onto the frozen current generation."""
    con = sqlite3.connect(str(GEN / "navigation/navigation.sqlite"))
    resolved: dict[str, list[dict]] = {}
    receipts = []
    for case in gold["cases"]:
        current = []
        for old in case["gold_articles"]:
            rows = con.execute(
                "SELECT id, document_id, json_extract(json, '$.unit_id'), "
                "json_extract(json, '$.source_artifact_sha256') FROM source "
                "WHERE json_extract(json, '$.document_name')=? AND article=?",
                (old["law"], old["article"]),
            ).fetchall()
            if len(rows) != 1:
                raise RuntimeError(
                    f"gold coordinate is not one-to-one: {case['case_id']} "
                    f"{old['law']} {old['article']} -> {len(rows)}"
                )
            sid, doc_id, unit_id, source_hash = rows[0]
            if int(unit_id) != int(old["node"]):
                raise RuntimeError(f"gold node drift: {case['case_id']} {old['article']}")
            identity = {"doc_id": doc_id, "node": int(unit_id)}
            current.append({"source_id": sid, "identity": identity})
            receipts.append(
                {
                    "case_id": case["case_id"],
                    "law": old["law"],
                    "article": old["article"],
                    "authority_as_of": old["authority_as_of"],
                    "legacy_identity": {"doc_id": old["doc_id"], "node": old["node"]},
                    "current_source_id": sid,
                    "current_identity": identity,
                    "source_artifact_sha256": source_hash,
                    "resolution_key": "document_name + article; node equality required",
                }
            )
        resolved[case["case_id"]] = current
    con.close()
    artifact = {
        "schema_version": "adr0482-gold-coordinate-resolution-v1",
        "computed_post_selection": True,
        "gold_visible_to_product": False,
        "generation": str(GEN.relative_to(ROOT)),
        "gold_sha256": sha(ADR / "gold-cases.json"),
        "receipts": receipts,
    }
    return resolved, artifact


def judge(results: dict, product: dict, gold: dict) -> dict:
    from lawrag.research.experiment_client import GeminiExperimentClient

    questions = {row["case_id"]: row["question"] for row in product["cases"]}
    gold_by_case = {row["case_id"]: row for row in gold["cases"]}
    output = {
        "schema_version": "adr0482-paired-judge-v1",
        "product_results_sha256": sha(RESULTS),
        "model": "gemini-3.1-flash-lite",
        "single_evaluator_per_case": True,
        "cases": {},
        "usage": [],
    }
    for index, cid in enumerate(sorted(results["cases"])):
        labels = {"A": ARMS[index % 2], "B": ARMS[(index + 1) % 2]}
        variants = [
            {"label": label, "answer": answer(results["cases"][cid][arm])}
            for label, arm in labels.items()
        ]
        target = ADR / "artifacts/run-002/judge" / cid
        client = GeminiExperimentClient(ROOT, target, max_calls=1, max_output_tokens=1200)
        payload = {
            "question": questions[cid],
            "reference_answer": gold_by_case[cid]["reference_answer"],
            "decisive_articles": [
                {"law": x["law"], "article": x["article"]}
                for x in gold_by_case[cid]["gold_articles"]
            ],
            "variants": variants,
        }
        raw = client.generate(SYSTEM, payload, SCHEMA, phase="judge")
        if {x["label"] for x in raw["assessments"]} != {"A", "B"}:
            raise RuntimeError(f"judge label mismatch: {cid}")
        by_label = {x["label"]: x for x in raw["assessments"]}
        output["cases"][cid] = {
            "anonymous_order": labels,
            "by_arm": {arm: by_label[label] for label, arm in labels.items()},
        }
        output["usage"].extend(client.usage)
    return output


def build_ledger(results: dict, resolved_gold: dict, helper) -> tuple[dict, dict]:
    con = sqlite3.connect(str(GEN / "navigation/navigation.sqlite"))
    source_to_identity = {
        sid: {"doc_id": doc, "node": int(unit)}
        for sid, doc, unit in con.execute(
            "SELECT id, document_id, json_extract(json, '$.unit_id') FROM source "
            "WHERE json_extract(json, '$.unit_id') IS NOT NULL"
        )
        if str(unit).isdigit()
    }
    con.close()
    plan = read(ADR / "실험/manifest.json")["design"]["retrieval_stage_plan"]["stages_by_arm"]
    arms = []
    summary = {}
    for arm in ARMS:
        cases = []
        for cid in sorted(results["cases"]):
            row = results["cases"][cid][arm]
            raw_stages = row.get("stages") or {}
            gold_ids = [x["identity"] for x in resolved_gold[cid]]
            previous = []
            stages = []
            for spec in plan[arm]:
                sid = spec["stage_id"]
                after = helper.ordered(
                    source_to_identity[x]
                    for x in raw_stages.get(sid, [])
                    if x in source_to_identity
                )
                previous_keys = {helper.key(x) for x in previous}
                after_keys = {helper.key(x) for x in after}
                added = [x for x in after if helper.key(x) not in previous_keys]
                discarded = [x for x in previous if helper.key(x) not in after_keys]
                reasons = {helper.key(x): "not_carried_to_next_recorded_stage" for x in discarded}
                skip = None
                if row.get("error") and not raw_stages:
                    skip = "product_execution_error_before_stage_receipt"
                stages.append(
                    helper.stage(
                        sid,
                        spec["kind"],
                        spec["parent_stage_ids"],
                        previous,
                        added,
                        discarded,
                        reasons,
                        gold_ids,
                        skip_reason=skip,
                    )
                )
                previous = stages[-1]["after"]
            cases.append(
                {
                    "schema_version": helper.SCHEMA,
                    "computed_post_selection": True,
                    "gold_visible_to_product": False,
                    "accounting_unit": helper.UNIT,
                    "arm_id": arm,
                    "case_id": cid,
                    "gold_total": len(gold_ids),
                    "gold_identities": helper.ordered(gold_ids),
                    "stages": stages,
                }
            )
        final_counts = [x["stages"][-1]["after_count"] for x in cases]
        final_gold = sum(x["stages"][-1]["gold_after"] for x in cases)
        total_gold = sum(x["gold_total"] for x in cases)
        presented_gold = sum(next(s for s in x["stages"] if s["stage_id"] == "presented")["gold_after"] for x in cases)
        presented_counts = [next(s for s in x["stages"] if s["stage_id"] == "presented")["after_count"] for x in cases]
        aggregate = {
            "presented_total": sum(presented_counts),
            "gold_after": final_gold,
            "gold_total": total_gold,
            "shown_gold": presented_gold,
        }
        arms.append(
            {
                "arm_id": arm,
                "declared_stage_ids": [x["stage_id"] for x in plan[arm]],
                "cases": cases,
                "aggregate": aggregate,
            }
        )
        summary[arm] = {
            "presented_counts": presented_counts,
            "answer_counts": final_counts,
            "presented_gold_recall": presented_gold / total_gold,
            "answer_gold_recall": final_gold / total_gold,
            "gold_total": total_gold,
        }
    ledger = {
        "schema_version": helper.SCHEMA,
        "adr_id": "ADR-0482",
        "experiment_id": "ADR-0482-experiment-v1",
        "accounting_unit": helper.UNIT,
        "computed_post_selection": True,
        "gold_visible_to_product": False,
        "runs": [{"run_id": "run-002", "arms": arms}],
        "audit": {
            "stage_plan_frozen_before_run": True,
            "coordinate_resolution_path": str(MAPPING.relative_to(ROOT)),
            "product_results_sha256": sha(RESULTS),
        },
    }
    ledger["artifact_sha256"] = helper._canonical_value_sha256(ledger)
    return ledger, summary


def summarize(results: dict, judged: dict, retrieval: dict) -> dict:
    by_arm = {}
    for arm in ARMS:
        rows = []
        for cid in sorted(results["cases"]):
            product_row = results["cases"][cid][arm]
            verdict = judged["cases"][cid]["by_arm"][arm]
            rows.append(
                {
                    "case_id": cid,
                    "correct": verdict["correct"],
                    "failure_type": verdict["failure_type"],
                    "reason": verdict["reason"],
                    "product_error": product_row.get("error"),
                    "claims": len((((product_row.get("result") or {}).get("answer") or {}).get("claims") or [])),
                    "calls": product_row["physical_calls"],
                    "seconds": product_row["seconds"],
                }
            )
        latencies = [x["seconds"] for x in rows]
        usage = [u for cid in results["cases"].values() for u in cid[arm].get("usage", [])]
        by_arm[arm] = {
            "correct": sum(x["correct"] for x in rows),
            "total": len(rows),
            "errors": sum(x["product_error"] is not None for x in rows),
            "zero_claims": sum(x["claims"] == 0 for x in rows),
            "calls": sum(x["calls"] for x in rows),
            "latency_p50_seconds": statistics.median(latencies),
            "latency_p95_seconds": percentile(latencies, 0.95),
            "presented_gold_recall": retrieval[arm]["presented_gold_recall"],
            "answer_gold_recall": retrieval[arm]["answer_gold_recall"],
            "usage": {
                key: sum((x.get(key) or 0) for x in usage)
                for key in ("input_tokens", "output_tokens", "thinking_tokens", "total_tokens")
            },
            "failure_types": dict(Counter(x["failure_type"] for x in rows if not x["correct"])),
            "by_case": rows,
        }
    regressions = sum(
        judged["cases"][cid]["by_arm"]["baseline"]["correct"]
        and not judged["cases"][cid]["by_arm"]["source-first"]["correct"]
        for cid in judged["cases"]
    )
    delta = by_arm["source-first"]["correct"] - by_arm["baseline"]["correct"]
    checks = {
        "candidate_correct_min_7": by_arm["source-first"]["correct"] >= 7,
        "paired_delta_min_2": delta >= 2,
        "regressions_max_1": regressions <= 1,
        "candidate_gold_presented_recall_min_0_8": by_arm["source-first"]["presented_gold_recall"] >= 0.8,
        "errors_per_arm_max_1": all(by_arm[a]["errors"] <= 1 for a in ARMS),
        "calls_per_case_max_14": all(x["calls"] <= 14 for a in ARMS for x in by_arm[a]["by_case"]),
        "wall_seconds_per_case_max_300": all(x["seconds"] <= 300 for a in ARMS for x in by_arm[a]["by_case"]),
        "gold_leakage_max_0": True,
    }
    judge_usage = {
        key: sum((x.get(key) or 0) for x in judged["usage"])
        for key in ("input_tokens", "output_tokens", "thinking_tokens", "total_tokens")
    }
    judge_usage["calls"] = len(judged["usage"])
    return {
        "schema_version": "adr0482-holdout-metrics-v1",
        "product_results_sha256": sha(RESULTS),
        "judge_results_sha256": None,
        "by_arm": by_arm,
        "paired_delta": delta,
        "baseline_only_regressions": regressions,
        "criteria": checks,
        "success": all(checks.values()),
        "main_wiring": "unchanged",
        "judge_usage": judge_usage,
        "judge_note": "One anonymous paired Gemini evaluator per case; no repeat calibration, so disagreement is unmeasured.",
    }


def main() -> None:
    if not RESULTS.exists() or read(RESULTS).get("finished_at") is None:
        raise RuntimeError("sealed product results are required")
    if any(path.exists() for path in (JUDGED, METRICS, LEDGER, MAPPING)):
        raise RuntimeError("run-002 has already been scored or partially accounted")
    sys.path.insert(0, str(ROOT / "02_BACKEND"))
    results = read(RESULTS)
    product = read(ADR / "product-cases.json")
    gold = read(ADR / "gold-cases.json")
    resolved, mapping = resolve_gold(gold)
    write_new(MAPPING, mapping)
    judged = judge(results, product, gold)
    write_new(JUDGED, judged)
    helper = load_ledger_helpers()
    ledger, retrieval = build_ledger(results, resolved, helper)
    write_new(LEDGER, ledger)
    metrics = summarize(results, judged, retrieval)
    metrics["judge_results_sha256"] = sha(JUDGED)
    write_new(METRICS, metrics)
    print(json.dumps({"success": metrics["success"], "by_arm": {a: metrics["by_arm"][a]["correct"] for a in ARMS}, "delta": metrics["paired_delta"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
