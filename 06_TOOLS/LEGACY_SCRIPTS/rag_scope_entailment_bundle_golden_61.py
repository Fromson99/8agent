#!/usr/bin/env python3
"""ADR-0116 paired Golden 61 runner.

The ADR-0115 candidate is rerun as the independent baseline.  The candidate
uses the isolated scope/entailment/protected-bundle profile.  MAIN remains
unchanged and all product-path roles stay on the frozen Haiku model.
"""
from __future__ import annotations

from copy import deepcopy
import concurrent.futures
import json
from pathlib import Path
import sys
import threading
import time
from typing import Any, Mapping, Sequence

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import rag_coverage_preserving_legal_compiler_golden_61 as prior  # noqa: E402
from lawrag.research import profiles as research_profiles  # noqa: E402


base = prior.base
_original_runtime_adapter_contract = base.runtime_adapter_contract
ADR_ID = "ADR-0116"
EXPERIMENT_ID = "ADR-0116-experiment-v1"
BASELINE_ARM = "baseline"
CANDIDATE_ARM = "scope-entailment-bundle-v2"
ARMS = (BASELINE_ARM, CANDIDATE_ARM)
ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0116-scope-entailment-bundle-compiler-golden-61"

BASELINE_STAGES = prior.CANDIDATE_STAGES
CANDIDATE_STAGES = (
    ("question-source", "source", ()),
    ("closed-grounding-retrieve", "retrieve", ("question-source",)),
    ("legal-system-route-retrieve", "retrieve", ("closed-grounding-retrieve",)),
    ("semantic-card-retrieve", "retrieve", ("legal-system-route-retrieve",)),
    ("baseline-floor-union", "union", ("semantic-card-retrieve",)),
    ("typed-legal-relation-expand", "expand", ("baseline-floor-union",)),
    ("scope-branch-partition", "filter", ("typed-legal-relation-expand",)),
    ("provenance-span-verify", "canonicalize", ("scope-branch-partition",)),
    ("protected-bundle-union", "union", ("provenance-span-verify",)),
    ("quote-entailment-select", "select", ("protected-bundle-union",)),
    ("decision-coverage-gate", "select", ("quote-entailment-select",)),
    ("compiled-evidence-present", "present", ("decision-coverage-gate",)),
)


def _stage_rows(rows: Sequence[tuple[str, str, tuple[str, ...]]]):
    return tuple({
        "stage_id": stage_id,
        "kind": kind,
        "parent_stage_ids": parents,
    } for stage_id, kind, parents in rows)


STAGE_PLAN = {
    BASELINE_ARM: _stage_rows(BASELINE_STAGES),
    CANDIDATE_ARM: _stage_rows(CANDIDATE_STAGES),
}


def _install_identity() -> None:
    base.__file__ = __file__
    base.ADR_ID = ADR_ID
    base.EXPERIMENT_ID = EXPERIMENT_ID
    base.ADR = ADR
    base.BASELINE_ARM = BASELINE_ARM
    base.CANDIDATE_ARM = CANDIDATE_ARM
    base.ARMS = ARMS
    base.STAGE_PLAN = STAGE_PLAN
    base.QUESTION_FORMAT_RECOVERY_ID = "run-001-attempt-001"


_install_identity()


def baseline_profile_contract() -> dict[str, Any]:
    observed = _stage_rows(BASELINE_STAGES)
    return {
        "ready": observed == STAGE_PLAN[BASELINE_ARM],
        "reason": "",
        "observed": [
            {**row, "parent_stage_ids": list(row["parent_stage_ids"])}
            for row in observed
        ],
    }


def runtime_adapter_contract(retrieve=None) -> dict[str, Any]:
    """Truthful preflight contract for two independent integrated profiles."""

    contract = _original_runtime_adapter_contract(retrieve)
    contract["baseline_result_sharing"] = False
    contract["required_call"] = (
        "two independent legalclosure_runtime.retrieve calls: "
        "coverage-preserving-v1 and scope-entailment-bundle-v2, cap=28"
    )
    return contract


def integrated_execution_metrics(index: Any, sections, meta: Mapping[str, Any]):
    metrics = prior.integrated_execution_metrics(index, sections, meta)
    integrated = meta.get("integrated_research") or {}
    validation = integrated.get("validation") or {}
    for list_key, count_key in (
        ("protected_bundle_violations", "protected_bundle_violation_count"),
        ("scope_violations", "scope_violation_count"),
        ("quote_entailment_violations", "quote_entailment_violation_count"),
    ):
        rows = sorted(set(str(value) for value in validation.get(list_key) or ()))
        metrics[list_key] = rows
        metrics[count_key] = len(rows)
    packet = integrated.get("evidence_packet") or {}
    metrics["decision_element_count"] = len(packet.get("decision_elements") or ())
    metrics["missing_element_count"] = len(packet.get("missing_elements") or ())
    metrics["protected_evidence_count"] = len(packet.get("protected_evidence_ids") or ())
    metrics["compiler_wall_ms"] = float(integrated.get("compiler_wall_ms") or 0.0)
    return metrics


def _validate_execution_metrics(arm: Mapping[str, Any]) -> None:
    prior._validate_execution_metrics(arm)
    metrics = arm["execution_metrics"]
    for list_key, count_key in (
        ("protected_bundle_violations", "protected_bundle_violation_count"),
        ("scope_violations", "scope_violation_count"),
        ("quote_entailment_violations", "quote_entailment_violation_count"),
    ):
        rows = metrics.get(list_key)
        if not isinstance(rows, list) or any(not isinstance(row, str) for row in rows):
            raise base.BoundaryError(f"execution metric {list_key} must be a string array")
        if metrics.get(count_key) != len(set(rows)):
            raise base.BoundaryError(f"execution metric {count_key} does not match {list_key}")
    for key in ("decision_element_count", "missing_element_count", "protected_evidence_count"):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise base.BoundaryError(f"execution metric {key} must be a nonnegative integer")


def _execute_arm(
    *, arm_id: str, index: Any, case: Mapping[str, Any], real_llm: Any,
    baseline_result=None,
):
    del baseline_result
    recording = base.RecordingLLM(real_llm)
    sections = []
    meta: dict[str, Any] = {}
    started = time.perf_counter()
    retrieval_started = started
    retrieval_call_count = 0
    error = ""
    execution_metrics: dict[str, Any] = {}
    try:
        trace = base.article_reachability.ArticleReachabilityTrace(
            index, case["case_id"], arm_id
        )
        profile = (
            "coverage-preserving-v1" if arm_id == BASELINE_ARM
            else "scope-entailment-bundle-v2"
        )
        sections, meta = base.legalclosure_runtime.retrieve(
            index,
            case["question"],
            llm=recording,
            assertion_llm=recording,
            cap=20,
            shortcut_enabled=False,
            feedback_enabled=False,
            graph_enabled=False,
            semantic_graph_enabled=False,
            reachability_trace=trace,
            integrated_research_enabled=True,
            integrated_cap=28,
            integrated_profile=profile,
            research_profile=research_profiles.load(profile),
        )
        if len(sections) > 28:
            raise base.BoundaryError(f"{arm_id} evidence cap exceeded: {len(sections)} > 28")
        integrated = meta.get("integrated_research") or {}
        stage_capture = integrated.get("stage_capture")
        if not isinstance(stage_capture, Mapping):
            raise base.BoundaryError(
                f"{arm_id} metadata needs integrated_research.stage_capture"
            )
        stage_capture = base.validate_declared_capture(
            stage_capture, case["case_id"], arm_id
        )
        execution_metrics = integrated_execution_metrics(index, sections, meta)
        retrieval_wall_ms = round((time.perf_counter() - retrieval_started) * 1000, 3)
        retrieval_call_count = len(recording.audit)
        answer_started = time.perf_counter()
        answer = base.answer_mod.synthesize(recording, case["question"], list(sections))
        answer_ms = round((time.perf_counter() - answer_started) * 1000, 3)
        answer_payload = prior._answer_payload(answer)
        if answer.gate_violation:
            execution_metrics["answer_gate_violations"] = ["answer-coerced"]
            execution_metrics["answer_gate_violation_count"] = 1
        reusable = None
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        retrieval_wall_ms = round((time.perf_counter() - retrieval_started) * 1000, 3)
        retrieval_call_count = len(recording.audit)
        stage_capture = base.skipped_stage_capture(index, case["case_id"], arm_id, error)
        answer_ms = 0.0
        answer_payload = {
            "answer": "", "answerable": False, "error": error,
            "refs": [], "wiki": [], "conclusion_strength": "",
            "evidence_ids": [], "gate_violation": False,
        }
        reusable = None
        execution_metrics = {
            "integrated_total_ms": 0.0,
            "planner_provider_ms": 0.0,
            "deterministic_planning_ms": 0.0,
            "compiler_wall_ms": 0.0,
            "closed_id_violations": [], "closed_id_violation_count": 0,
            "generation_violations": [], "generation_violation_count": 0,
            "verified_evidence_violations": [], "verified_evidence_violation_count": 0,
            "claim_evidence_violations": [], "claim_evidence_violation_count": 0,
            "answer_gate_violations": [], "answer_gate_violation_count": 0,
            "protected_bundle_violations": [], "protected_bundle_violation_count": 0,
            "scope_violations": [], "scope_violation_count": 0,
            "quote_entailment_violations": [], "quote_entailment_violation_count": 0,
            "verified_evidence_count": 0,
            "presented_evidence_count": len(sections),
            "verified_rate": 0.0,
            "coverage_binding_count": 0,
            "ready_assessment_count": 0,
            "decision_element_count": 0,
            "missing_element_count": 0,
            "protected_evidence_count": 0,
            "measurement_error": error,
        }
    wall_ms = round((time.perf_counter() - started) * 1000, 3)
    return {
        "arm_id": arm_id,
        "status": "error" if error else "complete",
        "error": error,
        "baseline_retrieval_shared": False,
        "retrieval": {
            "sections": base._section_rows(sections),
            "meta": base._jsonable(meta),
            "stage_capture": stage_capture,
        },
        "execution_metrics": execution_metrics,
        "answer": answer_payload,
        "provider_calls": deepcopy(recording.audit),
        "retrieval_provider_calls": deepcopy(recording.audit[:retrieval_call_count]),
        "answer_provider_calls": deepcopy(recording.audit[retrieval_call_count:]),
        "usage": base._usage(recording.audit),
        "wall_ms": wall_ms,
        "retrieval_wall_ms": retrieval_wall_ms,
        "answer_wall_ms": answer_ms,
    }, reusable


def _summarize(rows, ledger_artifact):
    summary = prior._legacy_summary(rows, ledger_artifact)
    for arm in ARMS:
        metrics = [row["arms"][arm]["product"].get("execution_metrics") or {} for row in rows]
        answers = [row["arms"][arm]["product"].get("answer") or {} for row in rows]
        target = summary["by_arm"][arm]
        for metric, output in (
            ("claim_evidence_violation_count", "claim_evidence_violations"),
            ("answer_gate_violation_count", "answer_gate_violations"),
            ("protected_bundle_violation_count", "protected_bundle_violations"),
            ("scope_violation_count", "scope_violations"),
            ("quote_entailment_violation_count", "quote_entailment_violations"),
            ("coverage_binding_count", "coverage_binding_count"),
            ("ready_assessment_count", "ready_assessment_count"),
            ("decision_element_count", "decision_element_count"),
            ("missing_element_count", "missing_element_count"),
            ("protected_evidence_count", "protected_evidence_count"),
        ):
            target[output] = sum(int(row.get(metric) or 0) for row in metrics)
        target["answer_gate_coercions"] = sum(
            bool(row.get("gate_violation")) for row in answers
        )

    baseline = summary["by_arm"][BASELINE_ARM]
    candidate = summary["by_arm"][CANDIDATE_ARM]
    paired = summary["paired_outcomes"]
    decisive = summary["decisive_coordinate_paired"]
    companion = summary["required_companion_paired"]
    baseline_tokens = baseline["product_usage_inclusive"]["input_tokens"]
    candidate_tokens = candidate["product_usage_inclusive"]["input_tokens"]
    criteria = {
        "candidate_answer_gain_at_least_3": candidate["answer_correct"] >= baseline["answer_correct"] + 3,
        "answer_baseline_only_at_most_3": paired["baseline_only"] <= 3,
        "unsupported_reduction_at_least_7": (
            baseline["unsupported_definitive_conclusions"]
            - candidate["unsupported_definitive_conclusions"] >= 7
        ),
        "candidate_unsupported_at_most_15": candidate["unsupported_definitive_conclusions"] <= 15,
        "decisive_hits_noninferior": candidate["decisive_gold_hits"] >= baseline["decisive_gold_hits"],
        "all_gold_cases_noninferior": candidate["all_gold_cases"] >= baseline["all_gold_cases"],
        "decisive_baseline_only_zero": decisive["baseline_only"] == 0,
        "required_companion_noninferior": candidate["required_companion_hits"] >= baseline["required_companion_hits"],
        "companion_baseline_only_at_most_1": companion["baseline_only"] <= 1,
        "closed_id_violations_zero": candidate["closed_id_violations"] == 0,
        "generation_violations_zero": candidate["generation_violations"] == 0,
        "source_span_violations_zero": candidate["verified_evidence_violations"] == 0,
        "claim_evidence_violations_zero": candidate["claim_evidence_violations"] == 0,
        "answer_gate_violations_zero": candidate["answer_gate_violations"] == 0,
        "protected_bundle_violations_zero": candidate["protected_bundle_violations"] == 0,
        "scope_violations_zero": candidate["scope_violations"] == 0,
        "quote_entailment_violations_zero": candidate["quote_entailment_violations"] == 0,
        "candidate_presented_max_within_28": candidate["presented_max"] <= 28,
        "candidate_presented_mean_within_22": candidate["presented_mean"] <= 22,
        "candidate_presented_p95_within_24": candidate["presented_p95"] <= 24,
        "candidate_provider_p95_within_20000_ms": candidate["provider_call_ms_p95"] <= 20_000,
        "candidate_product_p95_within_baseline_plus_20000_ms": (
            candidate["product_wall_ms_p95"] <= baseline["product_wall_ms_p95"] + 20_000
        ),
        "candidate_input_token_limit_met": (
            candidate_tokens <= baseline_tokens * 1.15
            or candidate_tokens - baseline_tokens <= 1_500_000
        ),
        "all_61_receipts_and_executions_complete": (
            summary["cases"] == 61
            and baseline["execution_success"] == 61
            and candidate["execution_success"] == 61
            and baseline["product_call_errors"] == 0
            and candidate["product_call_errors"] == 0
        ),
    }
    criteria["all_frozen_criteria_met"] = all(criteria.values())
    summary["frozen_criteria_measurement"] = criteria
    return summary


def run_products(
    public: Mapping[str, Any], paths: Mapping[str, Path], *, workers: int, resume: bool
) -> dict[str, Any]:
    """Persist successful futures independently and retry only transport failures.

    The inherited runner aborted its result-consumption loop on the first provider
    error, while the executor kept every other future running and then discarded
    their outputs.  Recovery attempts are append-only receipts and never replace a
    successful canonical capture.
    """

    if not resume and (paths["seal"].exists() or any(paths["captures"].glob("*.json"))):
        raise base.BoundaryError("existing product captures require --resume; overwrite is forbidden")
    index = base.index_mod.current().scoped(None)
    corpus_total = base._article_root_count(index)
    preload = base.integrated_legal_research.preload_resources(index)
    corpus_fingerprint = base._corpus_fingerprint(index)
    preload["corpus_fingerprint"] = corpus_fingerprint
    environment = {
        key: value for key, value in preload.items()
        if key not in {"elapsed_ms", "provider_calls", "run_environment_hash"}
    }
    preload["run_environment_hash"] = base._json_sha256(environment)
    print("[preload] " + json.dumps(preload, ensure_ascii=False, sort_keys=True), flush=True)
    local = threading.local()

    def work(case: Mapping[str, Any]) -> dict[str, Any]:
        if not hasattr(local, "llm"):
            local.llm = base._make_llm()
        return base.execute_product_case(
            index, case, local.llm, corpus_total,
            corpus_fingerprint, preload["run_environment_hash"],
        )

    pending = []
    for case in public["cases"]:
        existing = base._capture_file(paths["captures"], case["case_id"])
        if resume and existing.exists():
            base.validate_product_capture(
                base._read_json(existing), expected_case=case, require_success=True,
                expected_runtime=preload,
            )
            continue
        pending.append(case)

    recovery_root = ADR / "artifacts/product-recovery-attempts" / base.RUN_ID
    recovery_root.mkdir(parents=True, exist_ok=True)
    attempts = {}
    for case in pending:
        case_id = str(case["case_id"])
        existing_attempts = list(recovery_root.glob(f"{case_id}-attempt-*.json"))
        attempts[case_id] = len(existing_attempts)
    completed = 0
    maximum_attempts = 3
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, case): case for case in pending}
        while futures:
            future = next(concurrent.futures.as_completed(futures))
            case = futures.pop(future)
            capture = future.result()
            try:
                base.validate_product_capture(
                    capture, expected_case=case, require_success=True
                )
            except base.BoundaryError as exc:
                case_id = str(case["case_id"])
                attempts[case_id] += 1
                recovery = {
                    "schema_version": "adr-0116-product-recovery-attempt-v1",
                    "adr_id": ADR_ID,
                    "experiment_id": EXPERIMENT_ID,
                    "run_id": base.RUN_ID,
                    "case_id": case_id,
                    "attempt": attempts[case_id],
                    "reason": str(exc),
                    "capture": capture,
                }
                recovery["receipt_sha256"] = base._self_hash(
                    recovery, "receipt_sha256"
                )
                target = recovery_root / f"{case_id}-attempt-{attempts[case_id]:02d}.json"
                base._write_json(target, recovery)
                if attempts[case_id] >= maximum_attempts:
                    raise base.BoundaryError(
                        f"{case_id} failed after {maximum_attempts} recorded attempts: {exc}"
                    ) from exc
                print(
                    f"[product-retry {case_id} attempt={attempts[case_id]}] {exc}",
                    flush=True,
                )
                futures[pool.submit(work, case)] = case
                continue
            target = base._capture_file(paths["captures"], case["case_id"])
            base._write_json(target, capture)
            completed += 1
            print(f"[product {completed}/{len(pending)}] {case['case_id']}", flush=True)
    return base.build_product_seal(
        paths["public"], paths["captures"], paths["seal"], runtime_preload=preload
    )


base.baseline_raw_stage_contract = baseline_profile_contract
base.runtime_adapter_contract = runtime_adapter_contract
base._answer_payload = prior._answer_payload
base.integrated_execution_metrics = integrated_execution_metrics
base._validate_execution_metrics = _validate_execution_metrics
base._execute_arm = _execute_arm
base._summarize = _summarize
base.run_products = run_products


if __name__ == "__main__":
    raise SystemExit(base.main())
