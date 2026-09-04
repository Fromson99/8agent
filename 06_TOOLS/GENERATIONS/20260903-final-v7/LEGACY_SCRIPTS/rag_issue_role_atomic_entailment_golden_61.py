#!/usr/bin/env python3
"""ADR-0117 paired Golden 61 runner.

The ADR-0116 candidate is independently rerun as baseline.  The candidate is
the isolated issue-role/atomic-entailment v3 profile.  MAIN is untouched.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import rag_scope_entailment_bundle_golden_61 as prior  # noqa: E402
from lawrag.research import profiles as research_profiles  # noqa: E402


base = prior.base
ADR_ID = "ADR-0117"
EXPERIMENT_ID = "ADR-0117-experiment-v1"
BASELINE_ARM = "baseline"
CANDIDATE_ARM = "issue-role-atomic-entailment-v3"
ARMS = (BASELINE_ARM, CANDIDATE_ARM)
ADR = ROOT / "docs/adr/ADR-0117-issue-role-atomic-entailment-compiler-golden-61"

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
    ("issue-role-unit-compile", "select", ("provenance-span-verify",)),
    ("atomic-quota-select", "select", ("issue-role-unit-compile",)),
    ("proposition-entailment-gate", "select", ("atomic-quota-select",)),
    ("compiled-evidence-present", "present", ("proposition-entailment-gate",)),
)


def _stage_rows(rows: Sequence[tuple[str, str, tuple[str, ...]]]):
    return tuple({
        "stage_id": stage_id, "kind": kind, "parent_stage_ids": parents,
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
    # The inherited recovery-safe product loop resolves these globals from its
    # own module.  Rebind them to this append-only ADR receipt namespace.
    prior.ADR = ADR
    prior.ADR_ID = ADR_ID
    prior.EXPERIMENT_ID = EXPERIMENT_ID


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
    contract = prior.runtime_adapter_contract(retrieve)
    contract["baseline_result_sharing"] = False
    contract["required_call"] = (
        "two independent legalclosure_runtime.retrieve calls: "
        "scope-entailment-bundle-v2 cap=28 and "
        "issue-role-atomic-entailment-v3 hard cap=22"
    )
    return contract


def _answer_payload(result: base.answer_mod.Answer) -> dict[str, Any]:
    payload = prior.prior._answer_payload(result)
    payload["issue_results"] = base._jsonable(result.issue_results)
    return payload


def integrated_execution_metrics(index: Any, sections, meta: Mapping[str, Any]):
    metrics = prior.integrated_execution_metrics(index, sections, meta)
    integrated = meta.get("integrated_research") or {}
    validation = integrated.get("validation") or {}
    for list_key, count_key in (
        ("atomic_unit_violations", "atomic_unit_violation_count"),
        ("atomic_entailment_violations", "atomic_entailment_violation_count"),
        ("issue_coverage_violations", "issue_coverage_violation_count"),
    ):
        rows = sorted(set(str(value) for value in validation.get(list_key) or ()))
        metrics[list_key] = rows
        metrics[count_key] = len(rows)
    packet = integrated.get("evidence_packet") or {}
    metrics["issue_count"] = len(packet.get("issues") or ())
    metrics["requirement_count"] = sum(
        len(row.get("requirements") or ()) for row in packet.get("issues") or ()
    )
    metrics["missing_requirement_count"] = len(
        packet.get("missing_requirements") or ()
    )
    metrics["direct_entailment_count"] = sum(
        row.get("strength") == "DIRECT_TEXT"
        for row in packet.get("entailments") or ()
    )
    return metrics


def _validate_execution_metrics(arm: Mapping[str, Any]) -> None:
    prior._validate_execution_metrics(arm)
    metrics = arm["execution_metrics"]
    for list_key, count_key in (
        ("atomic_unit_violations", "atomic_unit_violation_count"),
        ("atomic_entailment_violations", "atomic_entailment_violation_count"),
        ("issue_coverage_violations", "issue_coverage_violation_count"),
    ):
        rows = metrics.get(list_key)
        if not isinstance(rows, list) or any(not isinstance(row, str) for row in rows):
            raise base.BoundaryError(f"execution metric {list_key} must be a string array")
        if metrics.get(count_key) != len(set(rows)):
            raise base.BoundaryError(f"execution metric {count_key} does not match {list_key}")
    for key in (
        "issue_count", "requirement_count", "missing_requirement_count",
        "direct_entailment_count",
    ):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise base.BoundaryError(f"execution metric {key} must be nonnegative integer")


def _empty_metrics(error: str, count: int) -> dict[str, Any]:
    output = {
        "integrated_total_ms": 0.0, "planner_provider_ms": 0.0,
        "deterministic_planning_ms": 0.0, "compiler_wall_ms": 0.0,
        "verified_evidence_count": 0, "presented_evidence_count": count,
        "verified_rate": 0.0, "coverage_binding_count": 0,
        "ready_assessment_count": 0, "decision_element_count": 0,
        "missing_element_count": 0, "protected_evidence_count": 0,
        "issue_count": 0, "requirement_count": 0,
        "missing_requirement_count": 0, "direct_entailment_count": 0,
        "measurement_error": error,
    }
    for name in (
        "closed_id", "generation", "verified_evidence", "claim_evidence",
        "answer_gate", "protected_bundle", "scope", "quote_entailment",
        "atomic_unit", "atomic_entailment", "issue_coverage",
    ):
        output[f"{name}_violations"] = []
        output[f"{name}_violation_count"] = 0
    return output


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
    try:
        trace = base.article_reachability.ArticleReachabilityTrace(
            index, case["case_id"], arm_id
        )
        profile = (
            "scope-entailment-bundle-v2" if arm_id == BASELINE_ARM
            else "issue-role-atomic-entailment-v3"
        )
        evidence_cap = 28 if arm_id == BASELINE_ARM else 22
        sections, meta = base.legalclosure_runtime.retrieve(
            index, case["question"], llm=recording, assertion_llm=recording,
            cap=20, shortcut_enabled=False, feedback_enabled=False,
            graph_enabled=False, semantic_graph_enabled=False,
            reachability_trace=trace, integrated_research_enabled=True,
            integrated_cap=evidence_cap, integrated_profile=profile,
            research_profile=research_profiles.load(profile),
        )
        if len(sections) > evidence_cap:
            raise base.BoundaryError(f"{arm_id} evidence cap exceeded: {len(sections)}")
        integrated = meta.get("integrated_research") or {}
        stage_capture = integrated.get("stage_capture")
        if not isinstance(stage_capture, Mapping):
            raise base.BoundaryError(f"{arm_id} needs stage_capture")
        stage_capture = base.validate_declared_capture(
            stage_capture, case["case_id"], arm_id
        )
        execution_metrics = integrated_execution_metrics(index, sections, meta)
        retrieval_wall_ms = round((time.perf_counter() - retrieval_started) * 1000, 3)
        retrieval_call_count = len(recording.audit)
        answer_started = time.perf_counter()
        answer = base.answer_mod.synthesize(recording, case["question"], list(sections))
        answer_ms = round((time.perf_counter() - answer_started) * 1000, 3)
        answer_payload = _answer_payload(answer)
        if answer.gate_violation:
            execution_metrics["answer_gate_violations"] = ["answer-coerced"]
            execution_metrics["answer_gate_violation_count"] = 1
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        retrieval_wall_ms = round((time.perf_counter() - retrieval_started) * 1000, 3)
        retrieval_call_count = len(recording.audit)
        stage_capture = base.skipped_stage_capture(index, case["case_id"], arm_id, error)
        answer_ms = 0.0
        answer_payload = {
            "answer": "", "answerable": False, "error": error, "refs": [],
            "wiki": [], "conclusion_strength": "", "evidence_ids": [],
            "issue_results": [], "gate_violation": False,
        }
        execution_metrics = _empty_metrics(error, len(sections))
    return {
        "arm_id": arm_id, "status": "error" if error else "complete",
        "error": error, "baseline_retrieval_shared": False,
        "retrieval": {
            "sections": base._section_rows(sections), "meta": base._jsonable(meta),
            "stage_capture": stage_capture,
        },
        "execution_metrics": execution_metrics,
        "answer": answer_payload,
        "provider_calls": deepcopy(recording.audit),
        "retrieval_provider_calls": deepcopy(recording.audit[:retrieval_call_count]),
        "answer_provider_calls": deepcopy(recording.audit[retrieval_call_count:]),
        "usage": base._usage(recording.audit),
        "wall_ms": round((time.perf_counter() - started) * 1000, 3),
        "retrieval_wall_ms": retrieval_wall_ms, "answer_wall_ms": answer_ms,
    }, None


def _summarize(rows, ledger_artifact):
    summary = prior.prior._legacy_summary(rows, ledger_artifact)
    for arm in ARMS:
        metrics = [row["arms"][arm]["product"].get("execution_metrics") or {} for row in rows]
        answers = [row["arms"][arm]["product"].get("answer") or {} for row in rows]
        target = summary["by_arm"][arm]
        for metric, output in (
            ("claim_evidence_violation_count", "claim_evidence_violations"),
            ("answer_gate_violation_count", "answer_gate_violations"),
            ("scope_violation_count", "scope_violations"),
            ("quote_entailment_violation_count", "quote_entailment_violations"),
            ("atomic_unit_violation_count", "atomic_unit_violations"),
            ("atomic_entailment_violation_count", "atomic_entailment_violations"),
            ("issue_coverage_violation_count", "issue_coverage_violations"),
            ("coverage_binding_count", "coverage_binding_count"),
            ("ready_assessment_count", "ready_assessment_count"),
            ("issue_count", "issue_count"),
            ("requirement_count", "requirement_count"),
            ("missing_requirement_count", "missing_requirement_count"),
            ("direct_entailment_count", "direct_entailment_count"),
        ):
            target[output] = sum(int(row.get(metric) or 0) for row in metrics)
        target["answer_gate_coercions"] = sum(
            int(row.get("answer_gate_violation_count") or 0) for row in metrics
        )
        target["all_gold_wrong"] = sum(
            bool(row["arms"][arm].get("all_gold_hit"))
            and not bool((row["arms"][arm].get("judge") or {}).get("correct"))
            for row in rows
        )

    baseline = summary["by_arm"][BASELINE_ARM]
    candidate = summary["by_arm"][CANDIDATE_ARM]
    paired = summary["paired_outcomes"]
    decisive = summary["decisive_coordinate_paired"]
    companion = summary["required_companion_paired"]
    bt = baseline["product_usage_inclusive"]["input_tokens"]
    ct = candidate["product_usage_inclusive"]["input_tokens"]
    criteria = {
        "candidate_answer_gain_at_least_3": candidate["answer_correct"] >= baseline["answer_correct"] + 3,
        "answer_baseline_only_at_most_3": paired["baseline_only"] <= 3,
        "unsupported_reduction_at_least_4": baseline["unsupported_definitive_conclusions"] - candidate["unsupported_definitive_conclusions"] >= 4,
        "candidate_unsupported_at_most_13": candidate["unsupported_definitive_conclusions"] <= 13,
        "decisive_hits_noninferior": candidate["decisive_gold_hits"] >= baseline["decisive_gold_hits"],
        "all_gold_cases_noninferior": candidate["all_gold_cases"] >= baseline["all_gold_cases"],
        "decisive_baseline_only_zero": decisive["baseline_only"] == 0,
        "required_companion_noninferior": candidate["required_companion_hits"] >= baseline["required_companion_hits"],
        "companion_baseline_only_at_most_1": companion["baseline_only"] <= 1,
        "all_gold_wrong_reduction_at_least_4": baseline["all_gold_wrong"] - candidate["all_gold_wrong"] >= 4,
        "closed_id_violations_zero": candidate["closed_id_violations"] == 0,
        "generation_violations_zero": candidate["generation_violations"] == 0,
        "source_span_violations_zero": candidate["verified_evidence_violations"] == 0,
        "claim_evidence_violations_zero": candidate["claim_evidence_violations"] == 0,
        "answer_gate_violations_zero": candidate["answer_gate_violations"] == 0,
        "atomic_unit_violations_zero": candidate["atomic_unit_violations"] == 0,
        "atomic_entailment_violations_zero": candidate["atomic_entailment_violations"] == 0,
        "issue_coverage_violations_zero": candidate["issue_coverage_violations"] == 0,
        "scope_violations_zero": candidate["scope_violations"] == 0,
        "quote_entailment_violations_zero": candidate["quote_entailment_violations"] == 0,
        "candidate_presented_max_within_22": candidate["presented_max"] <= 22,
        "candidate_presented_mean_within_22": candidate["presented_mean"] <= 22,
        "candidate_presented_p95_within_22": candidate["presented_p95"] <= 22,
        "candidate_provider_p95_within_20000_ms": candidate["provider_call_ms_p95"] <= 20_000,
        "candidate_product_p95_within_baseline_plus_10000_ms": candidate["product_wall_ms_p95"] <= baseline["product_wall_ms_p95"] + 10_000,
        "candidate_input_token_limit_met": ct <= bt * 1.10 or ct - bt <= 1_000_000,
        "all_61_receipts_and_executions_complete": summary["cases"] == 61 and baseline["execution_success"] == 61 and candidate["execution_success"] == 61 and baseline["product_call_errors"] == 0 and candidate["product_call_errors"] == 0,
    }
    criteria["all_frozen_criteria_met"] = all(criteria.values())
    summary["frozen_criteria_measurement"] = criteria
    return summary


base.baseline_raw_stage_contract = baseline_profile_contract
base.runtime_adapter_contract = runtime_adapter_contract
base._answer_payload = _answer_payload
base.integrated_execution_metrics = integrated_execution_metrics
base._validate_execution_metrics = _validate_execution_metrics
base._execute_arm = _execute_arm
base._summarize = _summarize
base.run_products = prior.run_products


if __name__ == "__main__":
    raise SystemExit(base.main())
