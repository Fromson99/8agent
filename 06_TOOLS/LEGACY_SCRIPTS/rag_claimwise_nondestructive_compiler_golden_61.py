#!/usr/bin/env python3
"""ADR-0121 claim-local non-destructive compiler Golden 61 runner."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from typing import Any, Mapping

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import rag_proposition_assessment_shadow_golden_61 as parent  # noqa: E402
from lawrag.core.rag import claimwise_nondestructive_compiler as claimwise  # noqa: E402
from lawrag.core.rag.legal_proposition_compiler import evidence_from_sections  # noqa: E402


base = parent.base
_legacy_summary = parent._legacy_summary
_legacy_validate_metrics = parent._legacy_validate_metrics

ADR_ID = "ADR-0121"
EXPERIMENT_ID = "ADR-0121-experiment-v1"
RUN_ID = "run-001"
BASELINE_ARM = "baseline"
CANDIDATE_ARM = claimwise.PROFILE
ARMS = (BASELINE_ARM, CANDIDATE_ARM)
ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0121-claimwise-nondestructive-legal-compiler-golden-61"
PARENT_ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0120-proposition-assessment-shadow-golden-61"
PARENT_CAPTURES = PARENT_ADR / "artifacts/product-captures/run-001"
PARENT_SEAL = PARENT_ADR / "artifacts/product-capture-seal-run-001.json"
PARENT_SEAL_FILE_SHA256 = "6628618299762522170179ab1abec4c59f2d39bc82264349df9c83489722ed2f"
PARENT_COMPILER_ARM = "proposition-assessment-shadow-v1"


def _stage_rows(arm_id: str):
    return tuple({
        "stage_id": stage_id,
        "kind": kind,
        "parent_stage_ids": parents,
    } for stage_id, kind, parents in claimwise.stage_specs(arm_id))


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
    parent.parent.recovery.ADR = ADR
    parent.parent.recovery.ADR_ID = ADR_ID
    parent.parent.recovery.EXPERIMENT_ID = EXPERIMENT_ID


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
        "missing": [] if ready else ["verified ADR-0120 run-001 parent captures"],
        "baseline_result_sharing": True,
        "baseline_raw_stage_capture": baseline_profile_contract(),
        "required_call": (
            "hash-verified ADR-0120 baseline answer/evidence and proposition packet; "
            "candidate adds only claim-local audit and deterministic patch merge"
        ),
    }


def _parent_seal_by_case() -> dict[str, Mapping[str, Any]]:
    if base._sha256(PARENT_SEAL) != PARENT_SEAL_FILE_SHA256:
        raise base.BoundaryError("ADR-0120 parent product seal hash changed")
    seal = base._read_json(PARENT_SEAL)
    if (
        seal.get("run_id") != "run-001"
        or seal.get("case_count") != 61
        or seal.get("gold_visible_to_product") is not False
        or seal.get("model") != base.MODEL
    ):
        raise base.BoundaryError("ADR-0120 parent seal contract mismatch")
    return {str(row["case_id"]): row for row in seal["case_receipts"]}


def _parent_capture(case: Mapping[str, Any]) -> dict[str, Any]:
    case_id = str(case["case_id"])
    receipt = _parent_seal_by_case().get(case_id)
    path = PARENT_CAPTURES / f"{case_id}.json"
    if receipt is None or not path.is_file():
        raise base.BoundaryError(f"missing sealed ADR-0120 capture: {case_id}")
    if base._sha256(path) != receipt["sha256"]:
        raise base.BoundaryError(f"ADR-0120 capture file hash mismatch: {case_id}")
    value = base._read_json(path)
    if value.get("capture_sha256") != receipt["capture_sha256"]:
        raise base.BoundaryError(f"ADR-0120 capture self hash mismatch: {case_id}")
    if base._self_hash(value, "capture_sha256") != value["capture_sha256"]:
        raise base.BoundaryError(f"ADR-0120 capture content hash mismatch: {case_id}")
    expected = {
        "number": int(case["number"]),
        "case_id": case_id,
        "suite": str(case["suite"]),
        "question": str(case["question"]),
    }
    if {key: value.get(key) for key in expected} != expected:
        raise base.BoundaryError(f"ADR-0120 question identity mismatch: {case_id}")
    if value.get("gold_visible_to_product") is not False:
        raise base.BoundaryError(f"gold-visible ADR-0120 capture: {case_id}")
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
    arm = value["arms"][BASELINE_ARM]
    sections = [_section(row) for row in arm["retrieval"]["sections"]]
    for number, section in enumerate(sections, 1):
        section.n = number
    return sections, deepcopy(dict(arm["retrieval"].get("meta") or {}))


_VIOLATION_KEYS = (
    "answer_span_violations",
    "closed_evidence_violations",
    "exact_quote_violations",
    "state_ground_violations",
    "overlap_violations",
    "patch_target_violations",
    "replacement_ground_violations",
    "untouched_text_violations",
    "global_block_violations",
)


def _metrics(parent_metrics: Mapping[str, Any], meta: Mapping[str, Any] | None) -> dict[str, Any]:
    metrics = deepcopy(dict(parent_metrics))
    value = dict(meta or {})
    validation = dict(value.get("validation") or {})
    for key in _VIOLATION_KEYS:
        rows = sorted(set(str(row) for row in validation.get(key) or ()))
        metrics[key] = rows
        metrics[key.removesuffix("_violations") + "_violation_count"] = len(rows)
    metrics.update({
        "claim_count": int(value.get("claim_count") or 0),
        "supported_count": int(value.get("supported_count") or 0),
        "conditional_count": int(value.get("conditional_count") or 0),
        "missing_count": int(value.get("missing_count") or 0),
        "conflicted_count": int(value.get("conflicted_count") or 0),
        "patch_count": int(value.get("patch_count") or 0),
        "global_block_count": int(value.get("global_block_count") or 0),
        "baseline_preserved_exactly": bool(
            value.get("baseline_preserved_exactly", True)
        ),
        "coordinates_unchanged": True,
    })
    return metrics


def _validate_execution_metrics(arm: Mapping[str, Any]) -> None:
    _legacy_validate_metrics(arm)
    metrics = arm["execution_metrics"]
    for key in _VIOLATION_KEYS:
        rows = metrics.get(key)
        count_key = key.removesuffix("_violations") + "_violation_count"
        if not isinstance(rows, list) or any(not isinstance(row, str) for row in rows):
            raise base.BoundaryError(f"execution metric {key} must be string array")
        if metrics.get(count_key) != len(set(rows)):
            raise base.BoundaryError(f"execution metric {count_key} mismatch")
    for key in (
        "claim_count", "supported_count", "conditional_count", "missing_count",
        "conflicted_count", "patch_count", "global_block_count",
    ):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise base.BoundaryError(f"execution metric {key} must be nonnegative integer")


def _compiler_calls(parent_candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        deepcopy(call) for call in parent_candidate.get("provider_calls") or ()
        if str(call.get("kind") or "") != "rag.answer"
    ]


def _provider_duration(calls) -> float:
    return float(sum(
        float((call.get("provider") or {}).get("dur_ms") or 0) for call in calls
    ))


def _execute_arm(
    *, arm_id: str, index: Any, case: Mapping[str, Any], real_llm: Any,
    baseline_result=None,
):
    started = time.perf_counter()
    capture = _parent_capture(case)
    parent_baseline = capture["arms"][BASELINE_ARM]
    sections, retrieval_meta = _sections_from_parent(capture)
    if arm_id == BASELINE_ARM:
        stage_capture = claimwise.capture_stages(
            index, str(case["case_id"]), BASELINE_ARM, sections,
        )
        stage_capture = base.validate_declared_capture(
            stage_capture, str(case["case_id"]), BASELINE_ARM,
        )
        provider_calls = deepcopy(list(parent_baseline.get("provider_calls") or ()))
        product = {
            "arm_id": BASELINE_ARM,
            "status": "complete",
            "error": "",
            "baseline_retrieval_shared": False,
            "retrieval": {
                "sections": base._section_rows(sections),
                "meta": base._jsonable(retrieval_meta),
                "stage_capture": stage_capture,
            },
            "execution_metrics": _metrics(
                parent_baseline.get("execution_metrics") or {}, None,
            ),
            "answer": deepcopy(parent_baseline["answer"]),
            "provider_calls": provider_calls,
            "retrieval_provider_calls": deepcopy(
                list(parent_baseline.get("retrieval_provider_calls") or ())
            ),
            "answer_provider_calls": deepcopy(
                list(parent_baseline.get("answer_provider_calls") or ())
            ),
            "usage": base._usage(provider_calls),
            "wall_ms": float(parent_baseline.get("wall_ms") or 0),
            "retrieval_wall_ms": float(parent_baseline.get("retrieval_wall_ms") or 0),
            "answer_wall_ms": float(parent_baseline.get("answer_wall_ms") or 0),
            "inherited_parent": {
                "adr_id": "ADR-0120",
                "experiment_id": "ADR-0120-experiment-v1",
                "run_id": "run-001",
                "arm_id": BASELINE_ARM,
                "capture_sha256": capture["capture_sha256"],
            },
        }
        return product, sections

    if baseline_result is None:
        raise base.BoundaryError("candidate requires inherited baseline product")
    parent_candidate = capture["arms"][PARENT_COMPILER_ARM]
    compiler_meta = (
        (parent_candidate.get("retrieval") or {}).get("meta") or {}
    ).get("proposition_assessment_shadow") or {}
    compiler_packet = compiler_meta.get("evidence_packet") or {}
    recording = base.RecordingLLM(real_llm)
    answer, meta = claimwise.compile_claimwise_answer(
        str(case["question"]),
        parent_baseline["answer"],
        evidence_from_sections(sections),
        compiler_packet,
        llm=recording,
    )
    stage_capture = claimwise.capture_stages(
        index, str(case["case_id"]), CANDIDATE_ARM, sections,
    )
    stage_capture = base.validate_declared_capture(
        stage_capture, str(case["case_id"]), CANDIDATE_ARM,
    )
    inherited_baseline_answer_calls = deepcopy(
        list(parent_baseline.get("answer_provider_calls") or ())
    )
    inherited_compiler_calls = _compiler_calls(parent_candidate)
    provider_calls = [
        *inherited_baseline_answer_calls,
        *inherited_compiler_calls,
        *deepcopy(recording.audit),
    ]
    compiler_wall_ms = _provider_duration(inherited_compiler_calls)
    wall_ms = round(
        float(parent_baseline.get("answer_wall_ms") or 0)
        + compiler_wall_ms
        + float(meta.get("elapsed_ms") or 0),
        3,
    )
    retrieval_meta["claimwise_nondestructive"] = deepcopy(meta)
    product = {
        "arm_id": CANDIDATE_ARM,
        "status": "complete",
        "error": "",
        "baseline_retrieval_shared": True,
        "retrieval": {
            "sections": base._section_rows(sections),
            "meta": base._jsonable(retrieval_meta),
            "stage_capture": stage_capture,
        },
        "execution_metrics": _metrics(
            parent_baseline.get("execution_metrics") or {}, meta,
        ),
        "answer": answer,
        "provider_calls": provider_calls,
        "retrieval_provider_calls": [],
        "answer_provider_calls": deepcopy(provider_calls),
        "usage": base._usage(provider_calls),
        "wall_ms": wall_ms,
        "retrieval_wall_ms": 0.0,
        "answer_wall_ms": round(
            float(parent_baseline.get("answer_wall_ms") or 0)
            + compiler_wall_ms
            + float(meta.get("elapsed_ms") or 0),
            3,
        ),
        "inherited_parent": {
            "adr_id": "ADR-0120",
            "experiment_id": "ADR-0120-experiment-v1",
            "run_id": "run-001",
            "baseline_arm_id": BASELINE_ARM,
            "compiler_arm_id": PARENT_COMPILER_ARM,
            "capture_sha256": capture["capture_sha256"],
        },
    }
    return product, sections


def _summarize(rows, ledger_artifact):
    summary = _legacy_summary(rows, ledger_artifact)
    for arm in ARMS:
        metric_rows = [
            row["arms"][arm]["product"].get("execution_metrics") or {}
            for row in rows
        ]
        target = summary["by_arm"][arm]
        for key in _VIOLATION_KEYS:
            output = key.removesuffix("_violations") + "_violations"
            count_key = key.removesuffix("_violations") + "_violation_count"
            target[output] = sum(int(row.get(count_key) or 0) for row in metric_rows)
        for key in (
            "claim_count", "supported_count", "conditional_count", "missing_count",
            "conflicted_count", "patch_count", "global_block_count",
        ):
            target[key] = sum(int(row.get(key) or 0) for row in metric_rows)
        target["baseline_preserved_cases"] = sum(
            bool(row.get("baseline_preserved_exactly")) for row in metric_rows
        )
        target["coordinates_unchanged_cases"] = sum(
            bool(row.get("coordinates_unchanged")) for row in metric_rows
        )

    baseline = summary["by_arm"][BASELINE_ARM]
    candidate = summary["by_arm"][CANDIDATE_ARM]
    paired = summary["paired_outcomes"]
    decisive = summary["decisive_coordinate_paired"]
    companion = summary["required_companion_paired"]
    invariant_total = sum(candidate.get(
        key.removesuffix("_violations") + "_violations", 0
    ) for key in _VIOLATION_KEYS)
    criteria = {
        "candidate_at_least_45": candidate["answer_correct"] >= 45,
        "candidate_gain_at_least_2": candidate["answer_correct"] >= baseline["answer_correct"] + 2,
        "baseline_only_at_most_3": paired["baseline_only"] <= 3,
        "unsupported_noninferior": candidate["unsupported_definitive_conclusions"] <= baseline["unsupported_definitive_conclusions"],
        "candidate_unsupported_at_most_14": candidate["unsupported_definitive_conclusions"] <= 14,
        "decisive_exact_equality": candidate["decisive_gold_hits"] == baseline["decisive_gold_hits"] and decisive["candidate_only"] == 0 and decisive["baseline_only"] == 0,
        "all_gold_exact_equality": candidate["all_gold_cases"] == baseline["all_gold_cases"],
        "companion_exact_equality": candidate["required_companion_hits"] == baseline["required_companion_hits"] and companion["candidate_only"] == 0 and companion["baseline_only"] == 0,
        "claim_patch_violations_zero": invariant_total == 0,
        "global_blocks_zero": candidate["global_block_count"] == 0,
        "evidence_exact_equality": candidate["presented_total"] == baseline["presented_total"],
        "candidate_input_tokens_within_32000000": candidate["product_usage_inclusive"]["input_tokens"] <= 32_000_000,
        "candidate_provider_p95_within_60000_ms": candidate["provider_call_ms_p95"] <= 60_000,
        "candidate_product_p95_within_350000_ms": candidate["product_wall_ms_p95"] <= 350_000,
        "all_61_receipts_and_executions_complete": summary["cases"] == 61 and baseline["execution_success"] == 61 and candidate["execution_success"] == 61 and baseline["product_call_errors"] == 0 and candidate["product_call_errors"] == 0,
    }
    criteria["all_frozen_criteria_met"] = all(criteria.values())
    summary["frozen_criteria_measurement"] = criteria
    return summary


base.baseline_raw_stage_contract = baseline_profile_contract
base.runtime_adapter_contract = runtime_adapter_contract
base._validate_execution_metrics = _validate_execution_metrics
base._execute_arm = _execute_arm
base._summarize = _summarize


if __name__ == "__main__":
    raise SystemExit(base.main())
