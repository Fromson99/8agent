#!/usr/bin/env python3
"""ADR-0129 proposition-first evidence-preserving Golden61 runner."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import rag_proposition_assessment_shadow_golden_61 as parent  # noqa: E402
from lawrag.core.rag import proposition_first_evidence_research as proposition  # noqa: E402
from lawrag.core.rag.evidence_confusion import (  # noqa: E402
    EvidenceConfusion,
    aggregate_evidence_confusions,
    difficulty_balanced_score,
)


base = parent.base
_legacy_summary = parent._legacy_summary
_legacy_metrics = parent._legacy_metrics
_legacy_validate_metrics = parent._legacy_validate_metrics

ADR_ID = "ADR-0129"
EXPERIMENT_ID = "ADR-0129-experiment-v1"
RUN_ID = "run-001"
BASELINE_ARM = "baseline"
CANDIDATE_ARM = proposition.PROFILE
ARMS = (BASELINE_ARM, CANDIDATE_ARM)
ADR = ROOT / "docs/adr/ADR-0129-proposition-first-evidence-preserving-compiler-golden-61"
PARENT_ADR = ROOT / "docs/adr/ADR-0118-integrated-atomic-claim-compiler-golden-61"
PARENT_CAPTURES = PARENT_ADR / "artifacts/product-captures/run-002"
PARENT_SEAL = PARENT_ADR / "artifacts/product-capture-seal-run-002.json"
PARENT_SEAL_FILE_SHA256 = "2b50d2b2e13bbc96cf144ec8b93a6d0ccf16bf3fe4b34011f4b019c7d4ba3ba4"
PARENT_ARM = "integrated-atomic-claim-v4b"
CM_V3 = ROOT / "data/review/cm_core_e2e_v3.json"
FSC_V3 = ROOT / "data/review/fsc_hard_retrieval_v3.json"
CORPUS_SIZE = 16_506


def _stage_rows(arm_id: str):
    return tuple({
        "stage_id": stage_id,
        "kind": kind,
        "parent_stage_ids": parents,
    } for stage_id, kind, parents in proposition.stage_specs(arm_id))


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
        "missing": [] if ready else ["verified ADR-0118 run-002 parent captures"],
        "baseline_result_sharing": True,
        "baseline_raw_stage_capture": baseline_profile_contract(),
        "required_call": (
            "hash-verified ADR-0118 v4b baseline; candidate compiles propositions, "
            "runs at most two missing-role probes, recompiles, and answers claim-locally"
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


_VIOLATION_KEYS = (
    "exact_quote_violations",
    "closed_evidence_violations",
    "floor_violations",
    "coordinate_violations",
    "evidence_cap_violations",
    "answer_claim_violations",
)


def _baseline_metrics(parent_arm: Mapping[str, Any], count: int) -> dict[str, Any]:
    metrics = deepcopy(dict(parent_arm.get("execution_metrics") or {}))
    metrics.setdefault("presented_evidence_count", count)
    for key in _VIOLATION_KEYS:
        metrics[key] = []
        metrics[key.removesuffix("_violations") + "_violation_count"] = 0
    metrics.update({
        "initial_issue_count": 0,
        "final_issue_count": 0,
        "initial_rule_count": 0,
        "final_rule_count": 0,
        "initial_missing_count": 0,
        "final_missing_count": 0,
        "targeted_probe_count": 0,
        "targeted_added_count": 0,
        "global_block_count": 0,
        "floor_preserved": True,
    })
    return metrics


def _candidate_metrics(index: Any, sections, meta: Mapping[str, Any]) -> dict[str, Any]:
    metrics = _legacy_metrics(index, sections, meta)
    compiler = dict(meta.get("proposition_first_evidence") or {})
    validation = dict(compiler.get("validation") or {})
    for key in _VIOLATION_KEYS:
        rows = sorted(set(str(value) for value in validation.get(key) or ()))
        metrics[key] = rows
        metrics[key.removesuffix("_violations") + "_violation_count"] = len(rows)
    for key in (
        "initial_issue_count", "final_issue_count", "initial_rule_count",
        "final_rule_count", "initial_missing_count", "final_missing_count",
        "targeted_probe_count", "targeted_added_count",
    ):
        metrics[key] = int(compiler.get(key) or 0)
    metrics.update({
        "global_block_count": 0,
        "floor_preserved": bool(compiler.get("floor_preserved")),
        "initial_compile_ms": float(compiler.get("initial_compile_ms") or 0.0),
        "final_compile_ms": float(compiler.get("final_compile_ms") or 0.0),
    })
    return metrics


def _validate_execution_metrics(arm: Mapping[str, Any]) -> None:
    _legacy_validate_metrics(arm)
    metrics = arm["execution_metrics"]
    for key in _VIOLATION_KEYS:
        rows = metrics.get(key)
        count_key = key.removesuffix("_violations") + "_violation_count"
        if not isinstance(rows, list) or any(not isinstance(row, str) for row in rows):
            raise base.BoundaryError(f"execution metric {key} must be a string array")
        if metrics.get(count_key) != len(set(rows)):
            raise base.BoundaryError(f"execution metric {count_key} mismatch")
    for key in (
        "initial_issue_count", "final_issue_count", "initial_rule_count",
        "final_rule_count", "initial_missing_count", "final_missing_count",
        "targeted_probe_count", "targeted_added_count", "global_block_count",
    ):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise base.BoundaryError(f"execution metric {key} must be nonnegative integer")


def _answer_payload(result: base.answer_mod.Answer) -> dict[str, Any]:
    return {
        "answer": result.answer,
        "answerable": bool(result.answerable),
        "error": result.error,
        "refs": base._jsonable(result.refs),
        "wiki": base._jsonable(result.wiki),
        "conclusion_strength": result.conclusion_strength,
        "evidence_ids": list(result.evidence_ids),
        "issue_results": base._jsonable(result.issue_results),
        "gate_violation": bool(result.gate_violation),
    }


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
        stage_capture = proposition.capture_stages(
            index, str(case["case_id"]), BASELINE_ARM, sections,
        )
        stage_capture = base.validate_declared_capture(
            stage_capture, str(case["case_id"]), BASELINE_ARM,
        )
        retrieval_calls = deepcopy(parent_baseline["retrieval_provider_calls"])
        inherited_calls = deepcopy(parent_candidate["provider_calls"])
        provider_calls = [*retrieval_calls, *inherited_calls]
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
            "answer_provider_calls": inherited_calls,
            "usage": base._usage(provider_calls),
            "wall_ms": round(float(parent_baseline["retrieval_wall_ms"]) + float(parent_candidate["wall_ms"]), 3),
            "retrieval_wall_ms": float(parent_baseline["retrieval_wall_ms"]),
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
    sections: list[Any] = []
    meta: dict[str, Any] = {}
    error = ""
    pre_answer_started = time.perf_counter()
    try:
        if baseline_result is None:
            raise base.BoundaryError("candidate requires inherited baseline evidence")
        sections, meta = deepcopy(baseline_result)
        sections, compiler_meta = proposition.attach_compilation(
            index, str(case["question"]), sections, llm=recording,
            case_id=str(case["case_id"]), arm_id=CANDIDATE_ARM,
        )
        meta["proposition_first_evidence"] = compiler_meta
        stage_capture = base.validate_declared_capture(
            compiler_meta["stage_capture"], str(case["case_id"]), CANDIDATE_ARM,
        )
        execution_metrics = _candidate_metrics(index, sections, meta)
        pre_answer_ms = round((time.perf_counter() - pre_answer_started) * 1000, 3)
        pre_answer_calls = len(recording.audit)
        answer_started = time.perf_counter()
        answer = proposition.synthesize_answer(
            recording, str(case["question"]), list(sections),
        )
        answer_ms = round((time.perf_counter() - answer_started) * 1000, 3)
        answer_payload = _answer_payload(answer)
        answer_violations = sorted(set(str(value) for value in answer.discards or ()))
        execution_metrics["answer_claim_violations"] = answer_violations
        execution_metrics["answer_claim_violation_count"] = len(answer_violations)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        pre_answer_ms = round((time.perf_counter() - pre_answer_started) * 1000, 3)
        pre_answer_calls = len(recording.audit)
        stage_capture = base.skipped_stage_capture(
            index, str(case["case_id"]), CANDIDATE_ARM, error,
        )
        answer_ms = 0.0
        answer_payload = {
            "answer": "", "answerable": False, "error": error, "refs": [],
            "wiki": [], "conclusion_strength": "", "evidence_ids": [],
            "issue_results": [], "gate_violation": False,
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
        "retrieval_provider_calls": deepcopy(recording.audit[:pre_answer_calls]),
        "answer_provider_calls": deepcopy(recording.audit[pre_answer_calls:]),
        "usage": base._usage(recording.audit),
        "wall_ms": round((time.perf_counter() - started) * 1000, 3),
        "retrieval_wall_ms": pre_answer_ms,
        "answer_wall_ms": answer_ms,
    }
    return product, None


def _gold_cases() -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for suite, path, evidence_key in (
        ("core", CM_V3, "evidence_articles"),
        ("hard", FSC_V3, "current_evidence_articles"),
    ):
        for case in json.loads(path.read_text("utf-8"))["cases"]:
            required = {
                f"{row['doc_id']}:{row['node']}" for row in case[evidence_key]
            }
            output[str(case["id"])] = {"suite": suite, "required": required}
    return output


def _evidence_sets(product: Mapping[str, Any]) -> tuple[set[str], set[str], list[str]]:
    sections = list((product.get("retrieval") or {}).get("sections") or ())
    presented = {f"{row['doc_id']}:{row['node']}" for row in sections}
    id_map: dict[str, str] = {}
    for row in sections:
        meta = dict(row.get("legal_meta") or {})
        research = dict(meta.get("integrated_research") or {})
        candidate_id = str(research.get("candidate_id") or "")
        if candidate_id:
            id_map[candidate_id] = f"{row['doc_id']}:{row['node']}"
    declared_ids = {str(value) for value in (product.get("answer") or {}).get("evidence_ids") or ()}
    unresolved = sorted(declared_ids - set(id_map))
    declared = {id_map[value] for value in declared_ids if value in id_map}
    return presented, declared, unresolved


def _aggregate_v3(rows, arm_id: str) -> dict[str, Any]:
    gold = _gold_cases()
    detail = []
    for row in rows:
        case_id = str(row["case_id"])
        product = row["arms"][arm_id]["product"]
        presented, declared, unresolved = _evidence_sets(product)
        required = gold[case_id]["required"]
        detail.append({
            "case_id": case_id,
            "suite": gold[case_id]["suite"],
            "presented": EvidenceConfusion.from_sets(required, presented, universe_size=CORPUS_SIZE),
            "declared": EvidenceConfusion.from_sets(required, declared, universe_size=CORPUS_SIZE),
            "unresolved_evidence_ids": unresolved,
        })

    def summarize(key: str) -> dict[str, Any]:
        groups = {}
        for name, subset in (
            ("all", detail),
            ("core", [row for row in detail if row["suite"] == "core"]),
            ("hard", [row for row in detail if row["suite"] == "hard"]),
        ):
            groups[name] = aggregate_evidence_confusions([row[key] for row in subset])
        return {
            "groups": groups,
            "difficulty_balanced_score": difficulty_balanced_score({
                "core": groups["core"], "hard": groups["hard"],
            }),
        }

    return {
        "presented": summarize("presented"),
        "declared": summarize("declared"),
        "unresolved_evidence_ids": sum(len(row["unresolved_evidence_ids"]) for row in detail),
        "case_rows": [{
            "case_id": row["case_id"],
            "suite": row["suite"],
            "presented": row["presented"].to_dict(),
            "declared": row["declared"].to_dict(),
            "unresolved_evidence_ids": row["unresolved_evidence_ids"],
        } for row in detail],
    }


def _summarize(rows, ledger_artifact):
    summary = _legacy_summary(rows, ledger_artifact)
    for arm in ARMS:
        metrics = [row["arms"][arm]["product"].get("execution_metrics") or {} for row in rows]
        target = summary["by_arm"][arm]
        for metric in (
            "initial_issue_count", "final_issue_count", "initial_rule_count",
            "final_rule_count", "initial_missing_count", "final_missing_count",
            "targeted_probe_count", "targeted_added_count", "global_block_count",
        ):
            target[metric] = sum(int(row.get(metric) or 0) for row in metrics)
        for key in _VIOLATION_KEYS:
            target[key] = sum(int(row.get(key.removesuffix("_violations") + "_violation_count") or 0) for row in metrics)
        target["floor_preserved_cases"] = sum(bool(row.get("floor_preserved")) for row in metrics)

    v3 = {arm: _aggregate_v3(rows, arm) for arm in ARMS}
    summary["golden_v3_evidence"] = v3
    baseline = summary["by_arm"][BASELINE_ARM]
    candidate = summary["by_arm"][CANDIDATE_ARM]
    paired = summary["paired_outcomes"]
    bdecl = v3[BASELINE_ARM]["declared"]["groups"]
    cdecl = v3[CANDIDATE_ARM]["declared"]["groups"]
    bpresent = v3[BASELINE_ARM]["presented"]["groups"]
    cpresent = v3[CANDIDATE_ARM]["presented"]["groups"]
    criteria = {
        "candidate_answer_gain_at_least_3": candidate["answer_correct"] >= baseline["answer_correct"] + 3,
        "baseline_only_at_most_3": paired["baseline_only"] <= 3,
        "declared_tp_gain_at_least_8": cdecl["all"]["tp"] >= bdecl["all"]["tp"] + 8,
        "hard_declared_recall_noninferior": cdecl["hard"]["recall"] >= bdecl["hard"]["recall"],
        "declared_complete_gain_at_least_5": cdecl["all"]["complete_cases"] >= bdecl["all"]["complete_cases"] + 5,
        "presented_tp_at_least_100": cpresent["all"]["tp"] >= 100,
        "presented_complete_noninferior": cpresent["all"]["complete_cases"] >= bpresent["all"]["complete_cases"],
        "inherited_presented_gold_preserved": cpresent["all"]["tp"] >= bpresent["all"]["tp"],
        "integrity_violations_zero": sum(candidate[key] for key in _VIOLATION_KEYS) == 0,
        "unresolved_evidence_ids_zero": v3[CANDIDATE_ARM]["unresolved_evidence_ids"] == 0,
        "global_blocks_zero": candidate["global_block_count"] == 0,
        "floor_preserved_61": candidate["floor_preserved_cases"] == 61,
        "targeted_probes_at_most_122": candidate["targeted_probe_count"] <= 122,
        "presented_max_at_most_32": candidate["presented_max"] <= 32,
        "product_p95_at_most_240000_ms": candidate["product_wall_ms_p95"] <= 240_000,
        "input_tokens_at_most_24000000": candidate["product_usage_inclusive"]["input_tokens"] <= 24_000_000,
        "all_61_complete": summary["cases"] == 61 and baseline["execution_success"] == 61 and candidate["execution_success"] == 61,
    }
    criteria["all_frozen_criteria_met"] = all(criteria.values())
    summary["frozen_criteria_measurement"] = criteria
    summary["stretch_90_measurement"] = {
        "presented_recall_at_least_105_of_116": cpresent["all"]["tp"] >= 105,
        "presented_complete_at_least_55_of_61": cpresent["all"]["complete_cases"] >= 55,
        "answer_correct_at_least_55_of_61": candidate["answer_correct"] >= 55,
    }
    summary["stretch_90_measurement"]["all_met"] = all(summary["stretch_90_measurement"].values())
    return summary


base.baseline_raw_stage_contract = baseline_profile_contract
base.runtime_adapter_contract = runtime_adapter_contract
base._answer_payload = _answer_payload
base.integrated_execution_metrics = _candidate_metrics
base._validate_execution_metrics = _validate_execution_metrics
base._execute_arm = _execute_arm
base._summarize = _summarize
base._summary_product_arm = parent._legacy_summary_product_arm
base.run_products = parent.parent.recovery.run_products


if __name__ == "__main__":
    raise SystemExit(base.main())
