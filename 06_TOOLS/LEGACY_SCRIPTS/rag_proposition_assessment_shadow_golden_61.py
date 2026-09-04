#!/usr/bin/env python3
"""ADR-0120 sealed-evidence proposition/applicability Golden 61 runner.

The baseline is the hash-verified ADR-0118 run-002 v4b product/evidence capture.
The candidate receives the exact same Section coordinates/text and adds only
the ADR-0120 compact shadow compiler before a fresh Haiku answer.  Gold is
opened only after all new product captures are sealed.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import rag_integrated_atomic_claim_golden_61 as parent  # noqa: E402
from lawrag.core.rag import proposition_assessment_shadow as shadow  # noqa: E402


base = parent.base
_legacy_summary = parent._legacy_summary
_legacy_metrics = parent._legacy_metrics
_legacy_validate_metrics = parent._legacy_validate_metrics
_legacy_summary_product_arm = base._summary_product_arm

ADR_ID = "ADR-0120"
EXPERIMENT_ID = "ADR-0120-experiment-v1"
RUN_ID = "run-001"
BASELINE_ARM = "baseline"
CANDIDATE_ARM = shadow.PROFILE
ARMS = (BASELINE_ARM, CANDIDATE_ARM)
ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0120-proposition-assessment-shadow-golden-61"
PARENT_ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0118-integrated-atomic-claim-compiler-golden-61"
PARENT_CAPTURES = PARENT_ADR / "artifacts/product-captures/run-002"
PARENT_SEAL = PARENT_ADR / "artifacts/product-capture-seal-run-002.json"
PARENT_SEAL_FILE_SHA256 = "2b50d2b2e13bbc96cf144ec8b93a6d0ccf16bf3fe4b34011f4b019c7d4ba3ba4"
PARENT_ARM = "integrated-atomic-claim-v4b"


def _stage_rows(arm_id: str):
    return tuple({
        "stage_id": stage_id,
        "kind": kind,
        "parent_stage_ids": parents,
    } for stage_id, kind, parents in shadow.stage_specs(arm_id))


STAGE_PLAN = {arm: _stage_rows(arm) for arm in ARMS}


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
    base.PUBLIC_FIXTURE_NAME = "public-questions-run-001.json"
    base.SCORING_FIXTURE_NAME = "scoring-fixture-run-001.json"
    base.SEAL_NAME = "product-capture-seal-run-001.json"
    base.RUN_ARTIFACT_NAME = "run-001.json"
    base.LEDGER_NAME = "retrieval-stage-ledger-run-001.json"
    base.QUESTION_FORMAT_RECOVERY_ID = "run-001-attempt-001"
    parent.recovery.ADR = ADR
    parent.recovery.ADR_ID = ADR_ID
    parent.recovery.EXPERIMENT_ID = EXPERIMENT_ID


_install_identity()


def baseline_profile_contract() -> dict[str, Any]:
    return {
        "ready": True,
        "reason": "",
        "observed": [
            {**row, "parent_stage_ids": list(row["parent_stage_ids"])}
            for row in STAGE_PLAN[BASELINE_ARM]
        ],
    }


def runtime_adapter_contract(retrieve=None) -> dict[str, Any]:
    del retrieve
    ready = (
        PARENT_SEAL.is_file()
        and base._sha256(PARENT_SEAL) == PARENT_SEAL_FILE_SHA256
        and len(list(PARENT_CAPTURES.glob("*.json"))) == 61
    )
    return {
        "ready": ready,
        "missing": [] if ready else ["verified ADR-0118 run-002 parent captures"],
        "baseline_result_sharing": True,
        "baseline_raw_stage_capture": baseline_profile_contract(),
        "required_call": (
            "hash-verified ADR-0118 v4b sealed evidence and answer as baseline; "
            "candidate adds compact proposition/coverage/applicability shadow and answer"
        ),
    }


def _parent_seal_by_case() -> dict[str, Mapping[str, Any]]:
    if base._sha256(PARENT_SEAL) != PARENT_SEAL_FILE_SHA256:
        raise base.BoundaryError("ADR-0118 parent product seal hash changed")
    seal = base._read_json(PARENT_SEAL)
    if (
        seal.get("run_id") != "run-002"
        or seal.get("case_count") != 61
        or seal.get("gold_visible_to_product") is not False
        or seal.get("model") != base.MODEL
    ):
        raise base.BoundaryError("ADR-0118 parent seal contract mismatch")
    return {str(row["case_id"]): row for row in seal["case_receipts"]}


def _parent_capture(case: Mapping[str, Any]) -> dict[str, Any]:
    case_id = str(case["case_id"])
    receipt = _parent_seal_by_case().get(case_id)
    path = PARENT_CAPTURES / f"{case_id}.json"
    if receipt is None or not path.is_file():
        raise base.BoundaryError(f"missing sealed parent capture: {case_id}")
    if base._sha256(path) != receipt["sha256"]:
        raise base.BoundaryError(f"parent capture file hash mismatch: {case_id}")
    value = base._read_json(path)
    if value.get("capture_sha256") != receipt["capture_sha256"]:
        raise base.BoundaryError(f"parent capture self hash mismatch: {case_id}")
    if base._self_hash(value, "capture_sha256") != value["capture_sha256"]:
        raise base.BoundaryError(f"parent capture content hash mismatch: {case_id}")
    expected = {
        "number": int(case["number"]),
        "case_id": case_id,
        "suite": str(case["suite"]),
        "question": str(case["question"]),
    }
    if {key: value.get(key) for key in expected} != expected:
        raise base.BoundaryError(f"parent question identity mismatch: {case_id}")
    if value.get("gold_visible_to_product") is not False:
        raise base.BoundaryError(f"gold-visible parent capture: {case_id}")
    return value


def _section(row: Mapping[str, Any]) -> base.answer_mod.Section:
    return base.answer_mod.Section(
        n=int(row.get("rank") or 0),
        doc_id=str(row["doc_id"]),
        doc=str(row["doc"]),
        node=int(row["node"]) if row.get("node") is not None else None,
        path=str(row.get("path") or ""),
        page=int(row["page"]) if row.get("page") is not None else None,
        kind=str(row.get("kind") or ""),
        matched=str(row.get("matched") or ""),
        text=str(row.get("text") or ""),
        block=int(row["block"]) if row.get("block") is not None else None,
        ref_src=deepcopy(row.get("ref_src")),
        scope_out=bool(row.get("scope_out")),
        edges=deepcopy(list(row.get("edges") or ())),
        legal_meta=deepcopy(dict(row.get("legal_meta") or {})),
        definition_context=deepcopy(list(row.get("definition_context") or ())),
    )


def _sections_from_parent(value: Mapping[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    arm = value["arms"][PARENT_ARM]
    sections = [_section(row) for row in arm["retrieval"]["sections"]]
    for number, section in enumerate(sections, 1):
        section.n = number
    return sections, deepcopy(dict(arm["retrieval"].get("meta") or {}))


def _answer_payload(result: base.answer_mod.Answer) -> dict[str, Any]:
    return parent._answer_payload(result)


def _shadow_metrics(index: Any, sections, meta: Mapping[str, Any]) -> dict[str, Any]:
    metrics = _legacy_metrics(index, sections, meta)
    compiler = meta.get("proposition_assessment_shadow") or {}
    validation = compiler.get("validation") or {}
    for list_key, count_key in (
        ("exact_rule_violations", "exact_rule_violation_count"),
        ("closed_evidence_violations", "closed_evidence_violation_count"),
        ("rule_cap_violations", "rule_cap_violation_count"),
        ("context_claim_violations", "context_claim_violation_count"),
        ("coordinate_violations", "coordinate_violation_count"),
        ("missing_direct_violations", "missing_direct_violation_count"),
    ):
        rows = sorted(set(str(value) for value in validation.get(list_key) or ()))
        metrics[list_key] = rows
        metrics[count_key] = len(rows)
    metrics.update({
        "compiler_wall_ms": float(compiler.get("compile_ms") or 0.0),
        "coverage_retry_wall_ms": float(compiler.get("coverage_retry_ms") or 0.0),
        "verifier_wall_ms": float(compiler.get("verifier_ms") or 0.0),
        "issue_count": int(compiler.get("issue_count") or 0),
        "fact_count": int(compiler.get("fact_count") or 0),
        "rule_count": int(compiler.get("rule_count") or 0),
        "binding_count": int(compiler.get("binding_count") or 0),
        "context_claim_count": int(compiler.get("context_claim_count") or 0),
        "missing_coverage_count": int(compiler.get("missing_coverage_count") or 0),
        "unresolved_fact_count": int(compiler.get("unresolved_fact_count") or 0),
        "coverage_retry_attempted": bool(
            (compiler.get("coverage_retry_receipt") or {}).get("attempted")
        ),
        "applicability_verifier_attempted": bool(
            (compiler.get("verifier_receipt") or {}).get("attempted")
        ),
        "coordinates_unchanged": bool(compiler.get("coordinates_unchanged", True)),
    })
    return metrics


def _baseline_metrics(parent_arm: Mapping[str, Any], count: int) -> dict[str, Any]:
    metrics = deepcopy(dict(parent_arm.get("execution_metrics") or {}))
    metrics.setdefault("presented_evidence_count", count)
    for list_key, count_key in (
        ("exact_rule_violations", "exact_rule_violation_count"),
        ("closed_evidence_violations", "closed_evidence_violation_count"),
        ("rule_cap_violations", "rule_cap_violation_count"),
        ("context_claim_violations", "context_claim_violation_count"),
        ("coordinate_violations", "coordinate_violation_count"),
        ("missing_direct_violations", "missing_direct_violation_count"),
    ):
        metrics[list_key] = []
        metrics[count_key] = 0
    metrics.update({
        "compiler_wall_ms": 0.0,
        "coverage_retry_wall_ms": 0.0,
        "verifier_wall_ms": 0.0,
        "issue_count": 0,
        "fact_count": 0,
        "rule_count": 0,
        "binding_count": 0,
        "context_claim_count": int(metrics.get("context_unit_count") or 0),
        "missing_coverage_count": 0,
        "unresolved_fact_count": 0,
        "coverage_retry_attempted": False,
        "applicability_verifier_attempted": False,
        "coordinates_unchanged": True,
    })
    return metrics


def _validate_execution_metrics(arm: Mapping[str, Any]) -> None:
    _legacy_validate_metrics(arm)
    metrics = arm["execution_metrics"]
    for list_key, count_key in (
        ("exact_rule_violations", "exact_rule_violation_count"),
        ("closed_evidence_violations", "closed_evidence_violation_count"),
        ("rule_cap_violations", "rule_cap_violation_count"),
        ("context_claim_violations", "context_claim_violation_count"),
        ("coordinate_violations", "coordinate_violation_count"),
        ("missing_direct_violations", "missing_direct_violation_count"),
    ):
        rows = metrics.get(list_key)
        if not isinstance(rows, list) or any(not isinstance(row, str) for row in rows):
            raise base.BoundaryError(f"execution metric {list_key} must be string array")
        if metrics.get(count_key) != len(set(rows)):
            raise base.BoundaryError(f"execution metric {count_key} mismatch")
    for key in (
        "issue_count", "fact_count", "rule_count", "binding_count",
        "context_claim_count", "missing_coverage_count", "unresolved_fact_count",
    ):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise base.BoundaryError(f"execution metric {key} must be nonnegative integer")


def _execute_arm(
    *, arm_id: str, index: Any, case: Mapping[str, Any], real_llm: Any,
    baseline_result=None,
):
    started = time.perf_counter()
    if arm_id == BASELINE_ARM:
        capture = _parent_capture(case)
        parent_baseline = capture["arms"]["baseline"]
        parent_candidate = capture["arms"][PARENT_ARM]
        sections, meta = _sections_from_parent(capture)
        stage_capture = shadow.capture_stages(
            index, str(case["case_id"]), BASELINE_ARM, sections,
        )
        stage_capture = base.validate_declared_capture(
            stage_capture, str(case["case_id"]), BASELINE_ARM,
        )
        retrieval_calls = deepcopy(parent_baseline["retrieval_provider_calls"])
        candidate_calls = deepcopy(parent_candidate["provider_calls"])
        provider_calls = [*retrieval_calls, *candidate_calls]
        retrieval_wall_ms = float(parent_baseline["retrieval_wall_ms"])
        wall_ms = round(
            retrieval_wall_ms + float(parent_candidate["wall_ms"]), 3
        )
        product = {
            "arm_id": BASELINE_ARM,
            "status": "complete",
            "error": "",
            "baseline_retrieval_shared": False,
            "retrieval": {
                "sections": base._section_rows(sections),
                "meta": base._jsonable(meta),
                "stage_capture": stage_capture,
            },
            "execution_metrics": _baseline_metrics(parent_candidate, len(sections)),
            "answer": deepcopy(parent_candidate["answer"]),
            "provider_calls": provider_calls,
            "retrieval_provider_calls": retrieval_calls,
            "answer_provider_calls": candidate_calls,
            "usage": base._usage(provider_calls),
            "wall_ms": wall_ms,
            "retrieval_wall_ms": retrieval_wall_ms,
            "answer_wall_ms": float(parent_candidate["answer_wall_ms"]),
            "inherited_parent": {
                "adr_id": "ADR-0118",
                "experiment_id": "ADR-0118-experiment-v1",
                "run_id": "run-002",
                "arm_id": PARENT_ARM,
                "capture_sha256": capture["capture_sha256"],
            },
        }
        return product, (deepcopy(sections), deepcopy(meta))

    recording = base.RecordingLLM(real_llm)
    sections = []
    meta: dict[str, Any] = {}
    error = ""
    retrieval_started = time.perf_counter()
    try:
        if baseline_result is None:
            raise base.BoundaryError("candidate requires inherited baseline evidence")
        sections, meta = deepcopy(baseline_result)
        sections, compiler_meta = shadow.attach_shadow_compilation(
            index, str(case["question"]), sections, llm=recording,
            case_id=str(case["case_id"]), arm_id=CANDIDATE_ARM,
        )
        meta["proposition_assessment_shadow"] = compiler_meta
        stage_capture = base.validate_declared_capture(
            compiler_meta["stage_capture"], str(case["case_id"]), CANDIDATE_ARM,
        )
        execution_metrics = _shadow_metrics(index, sections, meta)
        retrieval_wall_ms = round((time.perf_counter() - retrieval_started) * 1000, 3)
        retrieval_call_count = len(recording.audit)
        answer_started = time.perf_counter()
        answer = base.answer_mod.synthesize(
            recording, str(case["question"]), list(sections),
        )
        answer_ms = round((time.perf_counter() - answer_started) * 1000, 3)
        answer_payload = _answer_payload(answer)
        if answer.gate_violation:
            execution_metrics["missing_direct_violations"] = sorted(set([
                *execution_metrics["missing_direct_violations"], "answer-coerced",
            ]))
            execution_metrics["missing_direct_violation_count"] = len(
                execution_metrics["missing_direct_violations"]
            )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        retrieval_wall_ms = round((time.perf_counter() - retrieval_started) * 1000, 3)
        retrieval_call_count = len(recording.audit)
        stage_capture = base.skipped_stage_capture(
            index, str(case["case_id"]), CANDIDATE_ARM, error,
        )
        answer_ms = 0.0
        answer_payload = {
            "answer": "", "answerable": False, "error": error, "refs": [],
            "wiki": [], "conclusion_strength": "", "evidence_ids": [],
            "gate_violation": False,
        }
        execution_metrics = _baseline_metrics({}, len(sections))
        execution_metrics["runtime_error_count"] = 1
        execution_metrics["measurement_error"] = error
    product = {
        "arm_id": CANDIDATE_ARM,
        "status": "error" if error else "complete",
        "error": error,
        "baseline_retrieval_shared": True,
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
        "wall_ms": round((time.perf_counter() - started) * 1000, 3),
        "retrieval_wall_ms": retrieval_wall_ms,
        "answer_wall_ms": answer_ms,
    }
    return product, None


def _summarize(rows, ledger_artifact):
    summary = _legacy_summary(rows, ledger_artifact)
    for arm in ARMS:
        metrics = [row["arms"][arm]["product"].get("execution_metrics") or {} for row in rows]
        target = summary["by_arm"][arm]
        for metric, output in (
            ("exact_rule_violation_count", "exact_rule_violations"),
            ("closed_evidence_violation_count", "closed_evidence_violations"),
            ("rule_cap_violation_count", "rule_cap_violations"),
            ("context_claim_violation_count", "context_claim_violations"),
            ("coordinate_violation_count", "coordinate_violations"),
            ("missing_direct_violation_count", "missing_direct_violations"),
            ("context_claim_count", "context_claim_count"),
            ("issue_count", "issue_count"),
            ("fact_count", "fact_count"),
            ("rule_count", "rule_count"),
            ("binding_count", "binding_count"),
            ("missing_coverage_count", "missing_coverage_count"),
            ("unresolved_fact_count", "unresolved_fact_count"),
        ):
            target[output] = sum(int(row.get(metric) or 0) for row in metrics)
        target["coverage_retry_cases"] = sum(
            bool(row.get("coverage_retry_attempted")) for row in metrics
        )
        target["applicability_verifier_cases"] = sum(
            bool(row.get("applicability_verifier_attempted")) for row in metrics
        )
        target["coordinates_unchanged_cases"] = sum(
            bool(row.get("coordinates_unchanged")) for row in metrics
        )

    baseline = summary["by_arm"][BASELINE_ARM]
    candidate = summary["by_arm"][CANDIDATE_ARM]
    paired = summary["paired_outcomes"]
    decisive = summary["decisive_coordinate_paired"]
    companion = summary["required_companion_paired"]
    candidate_tokens = candidate["product_usage_inclusive"]["input_tokens"]
    criteria = {
        "candidate_at_least_40": candidate["answer_correct"] >= 40,
        "candidate_gain_at_least_2": candidate["answer_correct"] >= baseline["answer_correct"] + 2,
        "baseline_only_at_most_3": paired["baseline_only"] <= 3,
        "unsupported_noninferior": candidate["unsupported_definitive_conclusions"] <= baseline["unsupported_definitive_conclusions"],
        "candidate_unsupported_at_most_18": candidate["unsupported_definitive_conclusions"] <= 18,
        "decisive_exact_equality": candidate["decisive_gold_hits"] == baseline["decisive_gold_hits"] and decisive["candidate_only"] == 0 and decisive["baseline_only"] == 0,
        "all_gold_exact_equality": candidate["all_gold_cases"] == baseline["all_gold_cases"],
        "companion_exact_equality": candidate["required_companion_hits"] == baseline["required_companion_hits"] and companion["candidate_only"] == 0 and companion["baseline_only"] == 0,
        "exact_rule_violations_zero": candidate["exact_rule_violations"] == 0,
        "closed_evidence_violations_zero": candidate["closed_evidence_violations"] == 0,
        "rule_cap_violations_zero": candidate["rule_cap_violations"] == 0,
        "context_claims_zero": candidate["context_claim_count"] == 0 and candidate["context_claim_violations"] == 0,
        "coordinate_violations_zero": candidate["coordinate_violations"] == 0,
        "missing_direct_violations_zero": candidate["missing_direct_violations"] == 0,
        "candidate_rule_atoms_within_12_per_case": candidate["rule_count"] <= 61 * 12,
        "evidence_exact_equality": candidate["presented_total"] == baseline["presented_total"],
        "candidate_input_tokens_within_parent_baseline": candidate_tokens <= 19_187_957,
        "candidate_provider_p95_within_20000_ms": candidate["provider_call_ms_p95"] <= 20_000,
        "candidate_product_p95_within_198800_ms": candidate["product_wall_ms_p95"] <= 198_800,
        "all_61_receipts_and_executions_complete": summary["cases"] == 61 and baseline["execution_success"] == 61 and candidate["execution_success"] == 61 and baseline["product_call_errors"] == 0 and candidate["product_call_errors"] == 0,
    }
    criteria["all_frozen_criteria_met"] = all(criteria.values())
    summary["frozen_criteria_measurement"] = criteria
    return summary


def _summary_product_arm(arm: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize the inherited baseline's identity retrieve-to-present path.

    ADR-0118's sealed baseline predates the finalizer invariant that every arm
    must expose one explicit filter stage. Its declared three-stage path is an
    identity path, so this creates a summary-only identity-filter view. The
    sealed product capture and retrieval-stage ledger remain unchanged.
    """

    stages = list(
        (((arm.get("retrieval") or {}).get("stage_capture") or {}).get("stages"))
        or ()
    )
    filter_stages = [stage for stage in stages if stage.get("kind") == "filter"]
    if filter_stages:
        return _legacy_summary_product_arm(arm)
    if [stage.get("kind") for stage in stages] != ["source", "retrieve", "present"]:
        raise base.BoundaryError(
            "filter-free product arm must be the inherited source/retrieve/present baseline"
        )
    retrieve_stage, present_stage = stages[1], stages[2]
    retrieve_after = int(retrieve_stage.get("after_count") or 0)
    if (
        int(present_stage.get("before_count") or 0) != retrieve_after
        or int(present_stage.get("after_count") or 0) != retrieve_after
    ):
        raise base.BoundaryError(
            "inherited baseline is not an identity retrieve-to-present path"
        )
    summary_view = deepcopy(dict(arm))
    summary_view["retrieval"]["stage_capture"]["stages"].insert(2, {
        "stage_id": "summary-only-inherited-identity-filter",
        "kind": "filter",
        "before_count": retrieve_after,
        "after_count": retrieve_after,
    })
    return _legacy_summary_product_arm(summary_view)


base.baseline_raw_stage_contract = baseline_profile_contract
base.runtime_adapter_contract = runtime_adapter_contract
base._answer_payload = _answer_payload
base.integrated_execution_metrics = _shadow_metrics
base._validate_execution_metrics = _validate_execution_metrics
base._execute_arm = _execute_arm
base._summarize = _summarize
base._summary_product_arm = _summary_product_arm
base.run_products = parent.recovery.run_products


if __name__ == "__main__":
    raise SystemExit(base.main())
