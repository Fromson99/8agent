#!/usr/bin/env python3
"""ADR-0115 paired Golden 61 runner.

The sealed/gold-blind machinery is reused from ADR-0114.  Both arms execute
their complete product path independently: the baseline reruns the accepted
ADR-0114 integrated profile and the candidate selects the isolated
coverage-preserving profile.  Nothing in this module changes MAIN switches.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Mapping, Sequence

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import rag_integrated_legal_research_golden_61 as base  # noqa: E402
from lawrag.research import profiles as research_profiles  # noqa: E402


ADR_ID = "ADR-0115"
EXPERIMENT_ID = "ADR-0115-experiment-v1"
BASELINE_ARM = "baseline"
CANDIDATE_ARM = "coverage-preserving-compiler"
ARMS = (BASELINE_ARM, CANDIDATE_ARM)
ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0115-coverage-preserving-legal-compiler-golden-61"

BASELINE_STAGES = (
    ("question-source", "source", ()),
    ("closed-grounding-retrieve", "retrieve", ("question-source",)),
    ("legal-system-route-retrieve", "retrieve", ("closed-grounding-retrieve",)),
    ("semantic-card-retrieve", "retrieve", ("legal-system-route-retrieve",)),
    ("baseline-floor-union", "union", ("semantic-card-retrieve",)),
    ("typed-legal-relation-expand", "expand", ("baseline-floor-union",)),
    ("wiki-method-dependency-expand", "expand", ("typed-legal-relation-expand",)),
    ("adaptive-gap-retrieve", "retrieve", ("wiki-method-dependency-expand",)),
    ("provenance-canonicalize", "canonicalize", ("adaptive-gap-retrieve",)),
    ("actor-scope-filter", "filter", ("provenance-canonicalize",)),
    ("verified-coverage-select", "select", ("actor-scope-filter",)),
    ("compiled-evidence-present", "present", ("verified-coverage-select",)),
)
CANDIDATE_STAGES = (
    ("question-source", "source", ()),
    ("closed-grounding-retrieve", "retrieve", ("question-source",)),
    ("legal-system-route-retrieve", "retrieve", ("closed-grounding-retrieve",)),
    ("semantic-card-retrieve", "retrieve", ("legal-system-route-retrieve",)),
    ("baseline-floor-union", "union", ("semantic-card-retrieve",)),
    ("typed-legal-relation-expand", "expand", ("baseline-floor-union",)),
    ("candidate-shortlist-filter", "filter", ("typed-legal-relation-expand",)),
    ("provenance-span-verify", "canonicalize", ("candidate-shortlist-filter",)),
    ("claim-span-coverage-select", "select", ("provenance-span-verify",)),
    ("targeted-gap-retrieve", "retrieve", ("claim-span-coverage-select",)),
    ("final-coverage-compile", "select", ("targeted-gap-retrieve",)),
    ("compiled-evidence-present", "present", ("final-coverage-compile",)),
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
    # The reused finalize routine spawns ``Path(module.__file__)``. Point that
    # recovery-only child at this identity wrapper, not the ADR-0114 module.
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
_legacy_metrics = base.integrated_execution_metrics
_legacy_summary = base._summarize
_legacy_validate_execution_metrics = base._validate_execution_metrics


def baseline_profile_contract() -> dict[str, Any]:
    """Bind preflight to the frozen ADR-0114 integrated lifecycle."""

    observed = _stage_rows(BASELINE_STAGES)
    return {
        "ready": observed == STAGE_PLAN[BASELINE_ARM],
        "reason": "",
        "observed": [
            {**row, "parent_stage_ids": list(row["parent_stage_ids"])}
            for row in observed
        ],
    }


def _answer_payload(result: base.answer_mod.Answer) -> dict[str, Any]:
    return {
        "answer": result.answer,
        "answerable": bool(result.answerable),
        "error": result.error,
        "refs": base._jsonable(result.refs),
        "wiki": base._jsonable(result.wiki),
        "conclusion_strength": result.conclusion_strength,
        "evidence_ids": list(result.evidence_ids),
        "gate_violation": bool(result.gate_violation),
    }


def integrated_execution_metrics(index: Any, sections, meta: Mapping[str, Any]):
    metrics = _legacy_metrics(index, sections, meta)
    integrated = meta.get("integrated_research") or {}
    validation = integrated.get("validation") or {}
    for list_key, count_key in (
        ("claim_evidence_violations", "claim_evidence_violation_count"),
        ("answer_gate_violations", "answer_gate_violation_count"),
    ):
        rows = sorted(set(str(value) for value in validation.get(list_key) or ()))
        metrics[list_key] = rows
        metrics[count_key] = len(rows)
    packet = integrated.get("evidence_packet") or {}
    metrics["coverage_binding_count"] = len(packet.get("coverage") or ())
    metrics["ready_assessment_count"] = int(packet.get("ready_assessment_count") or 0)
    metrics["profile"] = str(integrated.get("profile") or "legacy")
    return metrics


def _validate_execution_metrics(arm: Mapping[str, Any]) -> None:
    _legacy_validate_execution_metrics(arm)
    metrics = arm["execution_metrics"]
    for list_key, count_key in (
        ("claim_evidence_violations", "claim_evidence_violation_count"),
        ("answer_gate_violations", "answer_gate_violation_count"),
    ):
        rows = metrics.get(list_key)
        if not isinstance(rows, list) or any(not isinstance(row, str) for row in rows):
            raise base.BoundaryError(f"execution metric {list_key} must be a string array")
        if metrics.get(count_key) != len(set(rows)):
            raise base.BoundaryError(f"execution metric {count_key} does not match {list_key}")
    for key in ("coverage_binding_count", "ready_assessment_count"):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise base.BoundaryError(f"execution metric {key} must be a nonnegative integer")


def _execute_arm(
    *, arm_id: str, index: Any, case: Mapping[str, Any], real_llm: Any,
    baseline_result=None,
):
    del baseline_result  # each arm reruns its complete product path
    recording = base.RecordingLLM(real_llm)
    sections = []
    meta: dict[str, Any] = {}
    shared = False
    started = time.perf_counter()
    retrieval_started = started
    retrieval_call_count = 0
    error = ""
    execution_metrics: dict[str, Any] = {}
    try:
        trace = base.article_reachability.ArticleReachabilityTrace(
            index, case["case_id"], arm_id
        )
        profile = "legacy" if arm_id == BASELINE_ARM else "coverage-preserving-v1"
        cap = 32 if arm_id == BASELINE_ARM else 28
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
            integrated_cap=cap,
            integrated_profile=profile,
            research_profile=research_profiles.load(profile),
        )
        if len(sections) > cap:
            raise base.BoundaryError(
                f"{arm_id} evidence cap exceeded: {len(sections)} > {cap}"
            )
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
        retrieval_wall_ms = round(
            (time.perf_counter() - retrieval_started) * 1000, 3
        )
        retrieval_call_count = len(recording.audit)
        answer_started = time.perf_counter()
        answer = base.answer_mod.synthesize(
            recording, case["question"], list(sections)
        )
        answer_ms = round((time.perf_counter() - answer_started) * 1000, 3)
        answer_payload = _answer_payload(answer)
        if answer.gate_violation:
            execution_metrics["answer_gate_violations"] = ["answer-coerced"]
            execution_metrics["answer_gate_violation_count"] = 1
        reusable = None
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        retrieval_wall_ms = round(
            (time.perf_counter() - retrieval_started) * 1000, 3
        )
        retrieval_call_count = len(recording.audit)
        stage_capture = base.skipped_stage_capture(
            index, case["case_id"], arm_id, error
        )
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
            "closed_id_violations": [], "closed_id_violation_count": 0,
            "generation_violations": [], "generation_violation_count": 0,
            "verified_evidence_violations": [],
            "verified_evidence_violation_count": 0,
            "claim_evidence_violations": [],
            "claim_evidence_violation_count": 0,
            "answer_gate_violations": [], "answer_gate_violation_count": 0,
            "verified_evidence_count": 0,
            "presented_evidence_count": len(sections),
            "verified_rate": 0.0,
            "coverage_binding_count": 0,
            "ready_assessment_count": 0,
            "measurement_error": error,
        }
    wall_ms = round((time.perf_counter() - started) * 1000, 3)
    payload = {
        "arm_id": arm_id,
        "status": "error" if error else "complete",
        "error": error,
        "baseline_retrieval_shared": shared,
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
    }
    return payload, reusable


def _summarize(rows, ledger_artifact):
    summary = _legacy_summary(rows, ledger_artifact)
    for arm in ARMS:
        metrics = [
            row["arms"][arm]["product"].get("execution_metrics") or {}
            for row in rows
        ]
        answers = [row["arms"][arm]["product"].get("answer") or {} for row in rows]
        target = summary["by_arm"][arm]
        target["claim_evidence_violations"] = sum(
            int(row.get("claim_evidence_violation_count") or 0) for row in metrics
        )
        target["answer_gate_violations"] = sum(
            int(row.get("answer_gate_violation_count") or 0) for row in metrics
        )
        target["answer_gate_coercions"] = sum(
            bool(row.get("gate_violation")) for row in answers
        )
        target["coverage_binding_count"] = sum(
            int(row.get("coverage_binding_count") or 0) for row in metrics
        )
        target["ready_assessment_count"] = sum(
            int(row.get("ready_assessment_count") or 0) for row in metrics
        )

    baseline = summary["by_arm"][BASELINE_ARM]
    candidate = summary["by_arm"][CANDIDATE_ARM]
    paired = summary["paired_outcomes"]
    decisive = summary["decisive_coordinate_paired"]
    companion = summary["required_companion_paired"]
    baseline_tokens = baseline["product_usage_inclusive"]["input_tokens"]
    candidate_tokens = candidate["product_usage_inclusive"]["input_tokens"]
    criteria = {
        "candidate_answer_gain_at_least_3": (
            candidate["answer_correct"] >= baseline["answer_correct"] + 3
        ),
        "answer_baseline_only_at_most_2": paired["baseline_only"] <= 2,
        "unsupported_reduction_at_least_5": (
            baseline["unsupported_definitive_conclusions"]
            - candidate["unsupported_definitive_conclusions"] >= 5
        ),
        "candidate_unsupported_at_most_12": (
            candidate["unsupported_definitive_conclusions"] <= 12
        ),
        "decisive_hits_noninferior": (
            candidate["decisive_gold_hits"] >= baseline["decisive_gold_hits"]
        ),
        "all_gold_cases_noninferior": (
            candidate["all_gold_cases"] >= baseline["all_gold_cases"]
        ),
        "decisive_baseline_only_zero": decisive["baseline_only"] == 0,
        "required_companion_noninferior": (
            candidate["required_companion_hits"]
            >= baseline["required_companion_hits"]
        ),
        "companion_baseline_only_at_most_1": companion["baseline_only"] <= 1,
        "closed_id_violations_zero": candidate["closed_id_violations"] == 0,
        "generation_violations_zero": candidate["generation_violations"] == 0,
        "source_span_violations_zero": (
            candidate["verified_evidence_violations"] == 0
        ),
        "claim_evidence_violations_zero": (
            candidate["claim_evidence_violations"] == 0
        ),
        "answer_gate_violations_zero": candidate["answer_gate_violations"] == 0,
        "coverage_or_ready_at_least_1": (
            candidate["coverage_binding_count"] > 0
            or candidate["ready_assessment_count"] > 0
        ),
        "candidate_presented_max_within_28": candidate["presented_max"] <= 28,
        "candidate_presented_mean_within_22": candidate["presented_mean"] <= 22,
        "candidate_presented_p95_within_24": candidate["presented_p95"] <= 24,
        "candidate_planning_p95_within_800_ms": (
            candidate["deterministic_planning_ms_p95"] <= 800
        ),
        "candidate_provider_p95_within_20000_ms": (
            candidate["provider_call_ms_p95"] <= 20_000
        ),
        "candidate_input_token_limit_met": (
            candidate_tokens <= baseline_tokens * 1.25
            or candidate_tokens - baseline_tokens <= 2_000_000
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


base.baseline_raw_stage_contract = baseline_profile_contract
base._answer_payload = _answer_payload
base.integrated_execution_metrics = integrated_execution_metrics
base._validate_execution_metrics = _validate_execution_metrics
base._execute_arm = _execute_arm
base._summarize = _summarize


if __name__ == "__main__":
    raise SystemExit(base.main())
