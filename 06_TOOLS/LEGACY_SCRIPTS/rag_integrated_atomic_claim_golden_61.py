#!/usr/bin/env python3
"""ADR-0118 shared-retrieval Golden 61 runner.

Both arms receive the exact ADR-0114 integrated-seven-layer sections.  Only
the candidate attaches the non-destructive atomic claim compiler before the
answer call.  Product roles remain on the frozen Haiku model and gold is opened
only after the 61 product captures are sealed.
"""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import rag_scope_entailment_bundle_golden_61 as recovery  # noqa: E402
from lawrag.core.rag import integrated_atomic_claim_research as atomic  # noqa: E402
from lawrag.research import profiles as research_profiles  # noqa: E402


base = recovery.base
_legacy_summary = recovery.prior._legacy_summary
_legacy_metrics = recovery.prior._legacy_metrics
_legacy_validate_metrics = recovery.prior._legacy_validate_execution_metrics

ADR_ID = "ADR-0118"
EXPERIMENT_ID = "ADR-0118-experiment-v1"
BASELINE_ARM = "baseline"
RUN_ID = os.environ.get("ADR0118_RUN_ID", "run-002")
if RUN_ID not in {"run-001", "run-002"}:
    raise RuntimeError(f"unsupported ADR0118_RUN_ID: {RUN_ID}")
CANDIDATE_ARM = (
    "integrated-atomic-claim-v4"
    if RUN_ID == "run-001"
    else "integrated-atomic-claim-v4b"
)
COMPILER_MAX_TOKENS = 4000 if RUN_ID == "run-001" else 8000
ARMS = (BASELINE_ARM, CANDIDATE_ARM)
ADR = ROOT / "docs/adr/ADR-0118-integrated-atomic-claim-compiler-golden-61"

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
    ("shared-integrated-evidence", "retrieve", ("question-source",)),
    ("soft-issue-claim-compile", "select", ("shared-integrated-evidence",)),
    ("atomic-claim-bind", "select", ("soft-issue-claim-compile",)),
    ("scope-safe-claim-gate", "filter", ("atomic-claim-bind",)),
    ("compiled-evidence-present", "present", ("scope-safe-claim-gate",)),
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
    base.RUN_ID = RUN_ID
    base.PUBLIC_FIXTURE_NAME = f"public-questions-{RUN_ID}.json"
    base.SCORING_FIXTURE_NAME = f"scoring-fixture-{RUN_ID}.json"
    base.SEAL_NAME = f"product-capture-seal-{RUN_ID}.json"
    base.RUN_ARTIFACT_NAME = f"{RUN_ID}.json"
    base.LEDGER_NAME = f"retrieval-stage-ledger-{RUN_ID}.json"
    base.QUESTION_FORMAT_RECOVERY_ID = f"{RUN_ID}-attempt-001"
    recovery.ADR = ADR
    recovery.ADR_ID = ADR_ID
    recovery.EXPERIMENT_ID = EXPERIMENT_ID


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
    del retrieve
    return {
        "ready": True,
        "missing": [],
        "baseline_result_sharing": True,
        "baseline_raw_stage_capture": baseline_profile_contract(),
        "required_call": (
            "one ADR-0114 integrated-seven-layer retrieval cap32 shared by both arms; "
            "candidate adds one soft atomic claim compiler and an independent answer"
        ),
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
    compiler = meta.get("atomic_claim_compiler") or {}
    validation = compiler.get("validation") or {}
    for list_key, count_key in (
        ("claim_evidence_violations", "claim_evidence_violation_count"),
        ("atomic_claim_violations", "atomic_claim_violation_count"),
        ("scope_violations", "scope_violation_count"),
        ("coordinate_violations", "coordinate_violation_count"),
    ):
        rows = sorted(set(str(value) for value in validation.get(list_key) or ()))
        metrics[list_key] = rows
        metrics[count_key] = len(rows)
    metrics.update({
        "answer_gate_violations": [],
        "answer_gate_violation_count": 0,
        "compiler_wall_ms": float(compiler.get("compiler_wall_ms") or 0.0),
        "issue_count": int(compiler.get("issue_count") or 0),
        "unit_count": int(compiler.get("unit_count") or 0),
        "soft_unit_count": int(compiler.get("soft_unit_count") or 0),
        "context_unit_count": int(compiler.get("context_unit_count") or 0),
        "claim_count": int(compiler.get("claim_count") or 0),
        "invalid_issue_count": int(compiler.get("invalid_issue_count") or 0),
        "invalid_unit_count": int(compiler.get("invalid_unit_count") or 0),
        "scope_rejection_count": int(compiler.get("scope_rejection_count") or 0),
        "coordinates_unchanged": bool(compiler.get("coordinates_unchanged", True)),
    })
    return metrics


def _validate_execution_metrics(arm: Mapping[str, Any]) -> None:
    _legacy_validate_metrics(arm)
    metrics = arm["execution_metrics"]
    for list_key, count_key in (
        ("claim_evidence_violations", "claim_evidence_violation_count"),
        ("atomic_claim_violations", "atomic_claim_violation_count"),
        ("scope_violations", "scope_violation_count"),
        ("coordinate_violations", "coordinate_violation_count"),
        ("answer_gate_violations", "answer_gate_violation_count"),
    ):
        rows = metrics.get(list_key)
        if not isinstance(rows, list) or any(not isinstance(row, str) for row in rows):
            raise base.BoundaryError(f"execution metric {list_key} must be string array")
        if metrics.get(count_key) != len(set(rows)):
            raise base.BoundaryError(f"execution metric {count_key} mismatch")
    for key in (
        "issue_count", "unit_count", "soft_unit_count", "context_unit_count",
        "claim_count", "invalid_issue_count", "invalid_unit_count",
        "scope_rejection_count",
    ):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise base.BoundaryError(f"execution metric {key} must be nonnegative integer")


def _empty_metrics(error: str, count: int) -> dict[str, Any]:
    output = {
        "integrated_total_ms": 0.0, "planner_provider_ms": 0.0,
        "deterministic_planning_ms": 0.0, "compiler_wall_ms": 0.0,
        "verified_evidence_count": 0, "presented_evidence_count": count,
        "verified_rate": 0.0, "runtime_error_count": 1,
        "issue_count": 0, "unit_count": 0, "soft_unit_count": 0,
        "context_unit_count": 0, "claim_count": 0, "invalid_issue_count": 0,
        "invalid_unit_count": 0, "scope_rejection_count": 0,
        "coordinates_unchanged": False, "measurement_error": error,
    }
    for name in (
        "closed_id", "generation", "verified_evidence", "claim_evidence",
        "atomic_claim", "scope", "coordinate", "answer_gate",
    ):
        output[f"{name}_violations"] = []
        output[f"{name}_violation_count"] = 0
    return output


def _execute_arm(
    *, arm_id: str, index: Any, case: Mapping[str, Any], real_llm: Any,
    baseline_result=None,
):
    recording = base.RecordingLLM(real_llm)
    sections = []
    meta: dict[str, Any] = {}
    shared = False
    started = time.perf_counter()
    retrieval_started = started
    retrieval_call_count = 0
    error = ""
    try:
        if arm_id == BASELINE_ARM:
            trace = base.article_reachability.ArticleReachabilityTrace(
                index, case["case_id"], arm_id
            )
            sections, meta = base.legalclosure_runtime.retrieve(
                index, case["question"], llm=recording, assertion_llm=recording,
                cap=20, shortcut_enabled=False, feedback_enabled=False,
                graph_enabled=False, semantic_graph_enabled=False,
                reachability_trace=trace, integrated_research_enabled=True,
                integrated_cap=32, integrated_profile="legacy",
                research_profile=research_profiles.load("legacy"),
            )
            stage_capture = (meta.get("integrated_research") or {}).get("stage_capture")
            reusable = (deepcopy(list(sections)), deepcopy(meta))
        else:
            if baseline_result is None:
                raise base.BoundaryError("candidate requires shared integrated evidence")
            sections, meta = deepcopy(baseline_result)
            shared = True
            sections, compiler_meta = atomic.attach_compilation(
                index, case["question"], sections, llm=recording,
                case_id=case["case_id"], arm_id=arm_id,
                max_tokens=COMPILER_MAX_TOKENS,
            )
            meta["atomic_claim_compiler"] = compiler_meta
            stage_capture = compiler_meta["stage_capture"]
            reusable = None
        if len(sections) > 32:
            raise base.BoundaryError(f"{arm_id} evidence cap exceeded: {len(sections)}")
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
            "gate_violation": False,
        }
        execution_metrics = _empty_metrics(error, len(sections))
        reusable = None
    return {
        "arm_id": arm_id, "status": "error" if error else "complete",
        "error": error, "baseline_retrieval_shared": shared,
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
    }, reusable


def _summarize(rows, ledger_artifact):
    summary = _legacy_summary(rows, ledger_artifact)
    for arm in ARMS:
        metrics = [row["arms"][arm]["product"].get("execution_metrics") or {} for row in rows]
        target = summary["by_arm"][arm]
        for metric, output in (
            ("claim_evidence_violation_count", "claim_evidence_violations"),
            ("atomic_claim_violation_count", "atomic_claim_violations"),
            ("scope_violation_count", "scope_violations"),
            ("coordinate_violation_count", "coordinate_violations"),
            ("answer_gate_violation_count", "answer_gate_violations"),
            ("issue_count", "issue_count"), ("unit_count", "unit_count"),
            ("soft_unit_count", "soft_unit_count"),
            ("context_unit_count", "context_unit_count"),
            ("claim_count", "claim_count"),
            ("scope_rejection_count", "scope_rejection_count"),
        ):
            target[output] = sum(int(row.get(metric) or 0) for row in metrics)
        target["coordinates_unchanged_cases"] = sum(
            bool(row.get("coordinates_unchanged")) for row in metrics
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
        "answer_baseline_only_at_most_2": paired["baseline_only"] <= 2,
        "unsupported_noninferior": candidate["unsupported_definitive_conclusions"] <= baseline["unsupported_definitive_conclusions"],
        "candidate_unsupported_at_most_18": candidate["unsupported_definitive_conclusions"] <= 18,
        "decisive_exact_equality": candidate["decisive_gold_hits"] == baseline["decisive_gold_hits"] and decisive["candidate_only"] == 0 and decisive["baseline_only"] == 0,
        "all_gold_exact_equality": candidate["all_gold_cases"] == baseline["all_gold_cases"],
        "companion_exact_equality": candidate["required_companion_hits"] == baseline["required_companion_hits"] and companion["candidate_only"] == 0 and companion["baseline_only"] == 0,
        "closed_id_violations_zero": candidate["closed_id_violations"] == 0,
        "generation_violations_zero": candidate["generation_violations"] == 0,
        "source_span_violations_zero": candidate["verified_evidence_violations"] == 0,
        "claim_evidence_violations_zero": candidate["claim_evidence_violations"] == 0,
        "atomic_claim_violations_zero": candidate["atomic_claim_violations"] == 0,
        "scope_violations_zero": candidate["scope_violations"] == 0,
        "coordinate_violations_zero": candidate["coordinate_violations"] == 0,
        "answer_gate_violations_zero": candidate["answer_gate_violations"] == 0,
        "evidence_count_exact_equality": candidate["presented_total"] == baseline["presented_total"],
        "candidate_presented_max_within_32": candidate["presented_max"] <= 32,
        "candidate_provider_p95_within_20000_ms": candidate["provider_call_ms_p95"] <= 20_000,
        "candidate_product_p95_within_baseline_plus_25000_ms": candidate["product_wall_ms_p95"] <= baseline["product_wall_ms_p95"] + 25_000,
        "candidate_input_token_limit_met": ct <= bt * 1.25 or ct - bt <= 2_500_000,
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
base.run_products = recovery.run_products


if __name__ == "__main__":
    raise SystemExit(base.main())
