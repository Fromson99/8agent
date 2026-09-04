#!/usr/bin/env python3
"""ADR-0132: selective non-binding legal guide over the sealed 28 provisions."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from scripts import rag_raw_evidence_id_selection_golden_61 as prior  # noqa: E402
from lawrag.core.rag import selective_legal_guide as selective  # noqa: E402


base = prior.base
ADR_ID = "ADR-0132"
EXPERIMENT_ID = "ADR-0132-experiment-v1"
RUN_ID = "run-001"
RAW_ARM = "raw-parent"
FULL_ARM = "full-compiler-parent"
CANDIDATE_ARM = selective.PROFILE
ARMS = (RAW_ARM, FULL_ARM, CANDIDATE_ARM)
ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0132-selective-legal-guide-evidence-selection-golden-61"
RAW_PARENT_ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0131-raw-evidence-id-selection-golden-61"
RAW_PARENT_CAPTURES = RAW_PARENT_ADR / "artifacts/product-captures/run-001"
RAW_PARENT_SEAL = RAW_PARENT_ADR / "artifacts/product-capture-seal-run-001.json"
RAW_PARENT_SEAL_SHA256 = "3fcc04ded3d0ca5da35881c9c4cdd26026bef37235751d7e956526c5c345df5a"
FULL_PARENT_ARM = prior.PARENT_ARM
RAW_PARENT_ARM = prior.CANDIDATE_ARM

STAGE_PLAN = {
    arm: (
        {"stage_id": "question-source", "kind": "source", "parent_stage_ids": ()},
        {"stage_id": "inherited-28-present", "kind": "present", "parent_stage_ids": ("question-source",)},
    )
    for arm in ARMS
}


def _install_identity() -> None:
    base.__file__ = __file__
    base.ADR_ID = ADR_ID
    base.EXPERIMENT_ID = EXPERIMENT_ID
    base.RUN_ID = RUN_ID
    base.ADR = ADR
    base.BASELINE_ARM = RAW_ARM
    base.CANDIDATE_ARM = CANDIDATE_ARM
    base.ARMS = ARMS
    base.STAGE_PLAN = STAGE_PLAN
    base.PUBLIC_FIXTURE_NAME = "public-questions-run-001.json"
    base.SCORING_FIXTURE_NAME = "scoring-fixture-run-001.json"
    base.SEAL_NAME = "product-capture-seal-run-001.json"
    base.RUN_ARTIFACT_NAME = "run-001.json"
    base.LEDGER_NAME = "inherited-retrieval-stage-ledger-run-002.json"


_install_identity()


def runtime_adapter_contract(retrieve=None) -> dict[str, Any]:
    del retrieve
    ready = (
        prior.PARENT_SEAL.is_file()
        and base._sha256(prior.PARENT_SEAL) == prior.PARENT_SEAL_SHA256
        and RAW_PARENT_SEAL.is_file()
        and base._sha256(RAW_PARENT_SEAL) == RAW_PARENT_SEAL_SHA256
        and len(list(prior.PARENT_CAPTURES.glob("*.json"))) == 61
        and len(list(RAW_PARENT_CAPTURES.glob("*.json"))) == 61
    )
    observed = [
        {**row, "parent_stage_ids": list(row["parent_stage_ids"])}
        for row in STAGE_PLAN[RAW_ARM]
    ]
    return {
        "ready": ready,
        "missing": [] if ready else ["hash-verified ADR-0118 and ADR-0131 product seals"],
        "baseline_result_sharing": True,
        "baseline_raw_stage_capture": {
            "ready": ready, "reason": "", "observed": observed,
        },
        "required_call": (
            "reuse sealed parent controls and issue exactly one selective-guide "
            "Haiku answer call per question"
        ),
    }


_RAW_RECEIPTS: dict[str, Mapping[str, Any]] | None = None


def _raw_parent_capture(case: Mapping[str, Any]) -> dict[str, Any]:
    global _RAW_RECEIPTS
    if base._sha256(RAW_PARENT_SEAL) != RAW_PARENT_SEAL_SHA256:
        raise base.BoundaryError("ADR-0131 parent seal hash changed")
    if _RAW_RECEIPTS is None:
        seal = base._read_json(RAW_PARENT_SEAL)
        if (
            seal.get("run_id") != "run-001" or seal.get("case_count") != 61
            or seal.get("gold_visible_to_product") is not False
            or seal.get("model") != base.MODEL
        ):
            raise base.BoundaryError("ADR-0131 parent seal contract mismatch")
        _RAW_RECEIPTS = {str(row["case_id"]): row for row in seal["case_receipts"]}
    case_id = str(case["case_id"])
    receipt = _RAW_RECEIPTS.get(case_id)
    path = RAW_PARENT_CAPTURES / f"{case_id}.json"
    if receipt is None or not path.is_file() or base._sha256(path) != receipt["sha256"]:
        raise base.BoundaryError(f"sealed ADR-0131 capture mismatch: {case_id}")
    value = base._read_json(path)
    prior.validate_product_capture(value, expected_case=case, require_success=True)
    return value


def _compiler_packet(full_capture: Mapping[str, Any]) -> Mapping[str, Any]:
    meta = full_capture["arms"][FULL_PARENT_ARM]["retrieval"]["meta"]
    packet = ((meta.get("atomic_claim_compiler") or {}).get("evidence_packet") or {})
    if not str(packet.get("schema_version") or "").startswith("integrated-atomic-claim"):
        raise base.BoundaryError("sealed compiler packet is missing")
    return packet


def _compiler_id_map(full_capture: Mapping[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    rows = full_capture["arms"][FULL_PARENT_ARM]["retrieval"]["sections"]
    for number, row in enumerate(rows, 1):
        research = dict((row.get("legal_meta") or {}).get("integrated_research") or {})
        value = str(research.get("candidate_id") or "")
        if value:
            output[value] = f"E{number:02d}"
    if len(output) != 28:
        raise base.BoundaryError(f"compiler closed ID map is not 28: {len(output)}")
    return output


def _stage_capture(index: Any, case_id: str, arm_id: str, sections):
    return prior._stage_capture(index, case_id, arm_id, sections)


def validate_declared_capture(capture: Mapping[str, Any], case_id: str, arm_id: str):
    prior.ledger.validate_capture(capture)
    if capture.get("case_id") != case_id or capture.get("arm_id") != arm_id:
        raise base.BoundaryError("stage capture identity mismatch")
    observed = tuple({
        "stage_id": str(row["stage_id"]), "kind": str(row["kind"]),
        "parent_stage_ids": tuple(row.get("parent_stage_ids") or ()),
    } for row in capture.get("stages") or ())
    if observed != STAGE_PLAN[arm_id]:
        raise base.BoundaryError(f"stage plan mismatch: {arm_id}")
    if capture.get("gold_visible_to_product") is not False:
        raise base.BoundaryError("stage capture product boundary violation")
    return deepcopy(dict(capture))


def _inherited_product(
    index, case, arm_id, source, sections, evidence_id_map,
    parent_ref, parent_capture_sha256,
):
    return {
        "arm_id": arm_id,
        "status": "complete",
        "error": "",
        "baseline_retrieval_shared": True,
        "retrieval": {
            "sections": deepcopy(sections),
            "meta": {
                "evidence_id_map": deepcopy(evidence_id_map),
                "input_profile": parent_ref,
                "inherited_parent_capture_sha256": parent_capture_sha256,
            },
            "stage_capture": _stage_capture(index, str(case["case_id"]), arm_id, sections),
        },
        "execution_metrics": {
            "presented_evidence_count": 28,
            "input_identity_match": True,
            "invalid_evidence_id_count": 0,
            "question_span_violation_count": 0,
            "quote_violation_count": 0,
            "dependency_violation_count": 0,
            "context_units_in_guide": 0,
            "candidate_deletion_count": 0,
        },
        "answer": deepcopy(dict(source["answer"])),
        "provider_calls": [],
        "retrieval_provider_calls": [],
        "answer_provider_calls": [],
        "usage": base._usage([]),
        "wall_ms": 0.0,
        "retrieval_wall_ms": 0.0,
        "answer_wall_ms": 0.0,
        "inherited_parent": parent_ref,
        "accounting": {
            "marginal": {"usage": base._usage([]), "wall_ms": 0.0},
            "inclusive": {"usage": base._usage([]), "wall_ms": 0.0},
            "criteria_accounting": "new_calls_only",
            "sealed_parent_reuse": True,
        },
    }


def _candidate_product(index, case, real_llm, full_capture, sections):
    started = time.perf_counter()
    recording = base.RecordingLLM(real_llm)
    packet = _compiler_packet(full_capture)
    compiler_map = _compiler_id_map(full_capture)
    result, request = selective.select_and_answer(
        recording, str(case["question"]), sections, packet, compiler_map,
    )
    wall_ms = round((time.perf_counter() - started) * 1000, 3)
    calls = deepcopy(recording.audit)
    usage = base._usage(calls)
    answer = {
        "answer": result["answer"],
        "answerable": result["answerable"],
        "error": result["error"],
        "evidence_ids": list(result["evidence_ids"]),
        "selections": deepcopy(result["selections"]),
        "rejected_near_matches": deepcopy(result["rejected_near_matches"]),
        "invalid_evidence_ids": list(result["invalid_evidence_ids"]),
        "refs": prior._answer_refs(result, request["evidence_id_map"]),
        "wiki": [],
    }
    guide = request["guide"]
    return {
        "arm_id": CANDIDATE_ARM,
        "status": "complete",
        "error": "",
        "baseline_retrieval_shared": True,
        "retrieval": {
            "sections": deepcopy(sections),
            "meta": {
                "evidence_id_map": deepcopy(request["evidence_id_map"]),
                "input_profile": CANDIDATE_ARM,
                "input_sha256": request["input_sha256"],
                "guide": deepcopy(guide),
                "guide_fields": ["issues", "units", "legal_links", "unresolved_issues", "non_binding"],
                "excluded_fields": [
                    "deterministic_context_units", "compiler_reason", "wiki", "score",
                    "generic_retrieval_origin", "gold", "hard_answer_gate",
                ],
                "inherited_parent_capture_sha256": full_capture["capture_sha256"],
            },
            "stage_capture": _stage_capture(index, str(case["case_id"]), CANDIDATE_ARM, sections),
        },
        "execution_metrics": {
            "presented_evidence_count": 28,
            "input_identity_match": True,
            "invalid_evidence_id_count": len(result["invalid_evidence_ids"]),
            "question_span_violation_count": int(result["question_span_violations"]),
            "quote_violation_count": int(result["quote_violations"]),
            "dependency_violation_count": int(result["dependency_violations"]),
            "output_contract_valid": bool(result["valid"]),
            "guide_issue_count": len(guide["issues"]),
            "guide_unit_count": len(guide["units"]),
            "guide_legal_link_count": len(guide["legal_links"]),
            "guide_unresolved_issue_count": len(guide["unresolved_issues"]),
            "context_units_in_guide": 0,
            "candidate_deletion_count": 0,
        },
        "answer": answer,
        "provider_calls": calls,
        "retrieval_provider_calls": [],
        "answer_provider_calls": calls,
        "usage": usage,
        "wall_ms": wall_ms,
        "retrieval_wall_ms": 0.0,
        "answer_wall_ms": wall_ms,
        "inherited_parent": {
            "adr_id": "ADR-0118", "run_id": "run-002", "arm_id": FULL_PARENT_ARM,
            "capture_sha256": full_capture["capture_sha256"],
        },
        "accounting": {
            "marginal": {"usage": deepcopy(usage), "wall_ms": wall_ms},
            "inclusive": {"usage": deepcopy(usage), "wall_ms": wall_ms},
            "criteria_accounting": "new_calls_only",
            "sealed_parent_reuse": True,
        },
    }


def execute_product_case(index, case, real_llm, corpus_total, corpus_fingerprint, run_environment_hash):
    full_capture = prior._parent_capture(case)
    raw_capture = _raw_parent_capture(case)
    sections = prior._clean_sections(full_capture)
    raw_source = raw_capture["arms"][RAW_PARENT_ARM]
    full_source = full_capture["arms"][FULL_PARENT_ARM]
    raw_product = _inherited_product(
        index, case, RAW_ARM, raw_source, sections,
        raw_source["retrieval"]["meta"]["evidence_id_map"],
        "ADR-0131-experiment-v1/raw-context-evidence-id-v1",
        raw_capture["capture_sha256"],
    )
    full_product = _inherited_product(
        index, case, FULL_ARM, full_source, sections,
        prior._parent_evidence_map(full_capture),
        "ADR-0118-experiment-v1/integrated-atomic-claim-v4b",
        full_capture["capture_sha256"],
    )
    candidate = _candidate_product(index, case, real_llm, full_capture, sections)
    value = {
        "schema_version": "adr-0114-gold-free-product-capture-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "number": int(case["number"]),
        "case_id": str(case["case_id"]),
        "suite": str(case["suite"]),
        "question": str(case["question"]),
        "model": base.MODEL,
        "gold_visible_to_product": False,
        "authority_generation": str(full_capture["authority_generation"]),
        "authority_as_of": str(full_capture["authority_as_of"]),
        "corpus_fingerprint": str(full_capture["corpus_fingerprint"]),
        "run_environment_hash": str(full_capture["run_environment_hash"]),
        "runtime_observation": {
            "current_corpus_article_roots": int(corpus_total),
            "current_corpus_fingerprint": corpus_fingerprint,
            "current_run_environment_hash": run_environment_hash,
        },
        "corpus_article_roots": int(full_capture["corpus_article_roots"]),
        "arms": {RAW_ARM: raw_product, FULL_ARM: full_product, CANDIDATE_ARM: candidate},
        "captured_at": base._now(),
        "complete": True,
    }
    base._forbid_product_gold(value)
    value["capture_sha256"] = base._self_hash(value, "capture_sha256")
    validate_product_capture(value, expected_case=case, require_success=True)
    return value


def _validate_execution_metrics(arm: Mapping[str, Any]) -> None:
    metrics = arm.get("execution_metrics") or {}
    if metrics.get("presented_evidence_count") != 28:
        raise base.BoundaryError("presented evidence count mismatch")
    for key in (
        "invalid_evidence_id_count", "question_span_violation_count",
        "quote_violation_count", "dependency_violation_count",
        "context_units_in_guide", "candidate_deletion_count",
    ):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise base.BoundaryError(f"invalid execution metric: {key}")


def _validate_accounting(arms: Mapping[str, Any]) -> None:
    for arm_id in (RAW_ARM, FULL_ARM):
        if arms[arm_id]["usage"] != base._usage([]):
            raise base.BoundaryError("inherited controls must add no new calls")
    candidate = arms[CANDIDATE_ARM]
    expected = {"usage": candidate["usage"], "wall_ms": candidate["wall_ms"]}
    if candidate["accounting"]["marginal"] != expected or candidate["accounting"]["inclusive"] != expected:
        raise base.BoundaryError("candidate accounting mismatch")


def validate_product_capture(
    value: Mapping[str, Any], *, expected_case: Mapping[str, Any] | None = None,
    require_success: bool = False, expected_runtime: Mapping[str, Any] | None = None,
) -> None:
    del expected_runtime
    if value.get("schema_version") != "adr-0114-gold-free-product-capture-v1":
        raise base.BoundaryError("unexpected product capture schema")
    if value.get("adr_id") != ADR_ID or value.get("experiment_id") != EXPERIMENT_ID:
        raise base.BoundaryError("product capture experiment mismatch")
    if value.get("run_id") != RUN_ID or value.get("model") != base.MODEL or value.get("complete") is not True:
        raise base.BoundaryError("product capture run/model mismatch")
    if value.get("gold_visible_to_product") is not False:
        raise base.BoundaryError("product gold boundary violation")
    if expected_case is not None:
        expected = {key: expected_case[key] for key in ("number", "case_id", "suite", "question")}
        if {key: value.get(key) for key in expected} != expected:
            raise base.BoundaryError("public question identity mismatch")
    if value.get("capture_sha256") != base._self_hash(value, "capture_sha256"):
        raise base.BoundaryError("capture self hash mismatch")
    arms = value.get("arms") or {}
    if set(arms) != set(ARMS):
        raise base.BoundaryError("product arm set mismatch")
    coordinates = None
    for arm_id in ARMS:
        arm = arms[arm_id]
        if arm.get("status") != "complete" or arm.get("arm_id") != arm_id:
            raise base.BoundaryError(f"incomplete arm: {arm_id}")
        sections = list(arm["retrieval"]["sections"])
        current = [(row["doc_id"], row["node"], row["text"]) for row in sections]
        if len(current) != 28 or (coordinates is not None and current != coordinates):
            raise base.BoundaryError("28-section identity mismatch")
        coordinates = current
        validate_declared_capture(arm["retrieval"]["stage_capture"], str(value["case_id"]), arm_id)
        calls = list(arm.get("provider_calls") or ())
        expected_calls = 1 if arm_id == CANDIDATE_ARM else 0
        if len(calls) != expected_calls:
            raise base.BoundaryError(f"unexpected new product calls: {arm_id}")
        if list(arm.get("retrieval_provider_calls") or ()) + list(arm.get("answer_provider_calls") or ()) != calls:
            raise base.BoundaryError("provider call partition mismatch")
        for call in calls:
            base._validate_provider_call(call, call_class="product")
            if require_success and (call.get("provider") or {}).get("error"):
                raise base.BoundaryError("provider error in successful arm")
        if arm.get("usage") != base._usage(calls):
            raise base.BoundaryError("usage mismatch")
        _validate_execution_metrics(arm)
    candidate_meta = arms[CANDIDATE_ARM]["retrieval"]["meta"]
    if candidate_meta.get("guide_fields") != [
        "issues", "units", "legal_links", "unresolved_issues", "non_binding",
    ]:
        raise base.BoundaryError("selective guide field contract mismatch")
    if any(
        str(row.get("role") or "") == "CONTEXT"
        for row in (candidate_meta.get("guide") or {}).get("units") or ()
    ):
        raise base.BoundaryError("CONTEXT unit leaked into guide")
    _validate_accounting(arms)


def _aggregate(captures, arm_id: str) -> dict[str, Any]:
    return prior._aggregate(captures, arm_id)


def _paired(evidence, baseline_arm: str) -> dict[str, Any]:
    baseline = {row["case_id"]: row["declared"] for row in evidence[baseline_arm]["case_rows"]}
    candidate = {row["case_id"]: row["declared"] for row in evidence[CANDIDATE_ARM]["case_rows"]}
    counts: Counter[str] = Counter()
    gained: list[str] = []
    lost: list[str] = []
    for case_id in baseline:
        before = int(baseline[case_id]["fn"]) == 0
        after = int(candidate[case_id]["fn"]) == 0
        label = "both_complete" if before and after else "both_incomplete"
        if after and not before:
            label = "candidate_only_complete"; gained.append(case_id)
        elif before and not after:
            label = "baseline_only_complete"; lost.append(case_id)
        counts[label] += 1
    return {"counts": dict(counts), "gained": gained, "lost": lost}


def build_report(captures: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    evidence = {arm: _aggregate(captures, arm) for arm in ARMS}
    paired = {
        "vs_raw": _paired(evidence, RAW_ARM),
        "vs_full_compiler": _paired(evidence, FULL_ARM),
    }
    products = [row["arms"][CANDIDATE_ARM] for row in captures]
    calls = [call for product in products for call in product["provider_calls"]]
    provider_latencies = [float((call.get("provider") or {}).get("dur_ms") or 0) for call in calls]
    usage = base._usage(calls)
    sums = lambda key: sum(int(row["execution_metrics"].get(key) or 0) for row in products)
    runtime = {
        RAW_ARM: {"new_product_calls": 0, "sealed_parent_reuse": True},
        FULL_ARM: {"new_product_calls": 0, "sealed_parent_reuse": True},
        CANDIDATE_ARM: {
            "complete_cases": len(products),
            "new_product_calls": len(calls),
            "usage": usage,
            "provider_p50_ms": prior._percentile(provider_latencies, .50),
            "provider_p95_ms": prior._percentile(provider_latencies, .95),
            "answer_wall_p50_ms": prior._percentile((row["answer_wall_ms"] for row in products), .50),
            "answer_wall_p95_ms": prior._percentile((row["answer_wall_ms"] for row in products), .95),
            "invalid_evidence_ids": sums("invalid_evidence_id_count"),
            "question_span_violations": sums("question_span_violation_count"),
            "quote_violations": sums("quote_violation_count"),
            "dependency_violations": sums("dependency_violation_count"),
            "guide_issues": sums("guide_issue_count"),
            "guide_units": sums("guide_unit_count"),
            "guide_legal_links": sums("guide_legal_link_count"),
            "guide_unresolved_issues": sums("guide_unresolved_issue_count"),
            "context_units_in_guide": sums("context_units_in_guide"),
            "candidate_deletions": sums("candidate_deletion_count"),
            "input_identity_match_cases": sum(bool(row["execution_metrics"]["input_identity_match"]) for row in products),
            "presented_max": max(len(row["retrieval"]["sections"]) for row in products),
        },
    }
    declared = evidence[CANDIDATE_ARM]["declared"]
    groups = declared["groups"]
    full_lost = paired["vs_full_compiler"]["lost"]
    criteria = {
        "difficulty_score_at_least_52_63897": declared["difficulty_balanced_score"] >= 52.63897,
        "tp_at_least_67": groups["all"]["tp"] >= 67,
        "complete_at_least_29": groups["all"]["complete_cases"] >= 29,
        "precision_at_least_050": groups["all"]["precision"] >= .50,
        "f1_at_least_053719008": groups["all"]["f1"] >= .53719008,
        "hard_recall_at_least_066666667": groups["hard"]["recall"] >= .66666667,
        "fp_at_most_66": groups["all"]["fp"] <= 66,
        "full_compiler_only_complete_regressions_at_most_3": len(full_lost) <= 3,
        "all_61_complete": len(products) == 61,
        "exactly_61_product_calls": len(calls) == 61,
        "judge_calls_zero": True,
        "input_tokens_at_most_5000000": usage["input_tokens"] <= 5_000_000,
        "provider_p95_at_most_15000_ms": runtime[CANDIDATE_ARM]["provider_p95_ms"] <= 15_000,
        "invalid_ids_zero": runtime[CANDIDATE_ARM]["invalid_evidence_ids"] == 0,
        "question_span_violations_zero": runtime[CANDIDATE_ARM]["question_span_violations"] == 0,
        "quote_violations_zero": runtime[CANDIDATE_ARM]["quote_violations"] == 0,
        "dependency_violations_zero": runtime[CANDIDATE_ARM]["dependency_violations"] == 0,
        "context_units_and_candidate_deletions_zero": (
            runtime[CANDIDATE_ARM]["context_units_in_guide"] == 0
            and runtime[CANDIDATE_ARM]["candidate_deletions"] == 0
        ),
        "input_identity_61_of_61": (
            runtime[CANDIDATE_ARM]["input_identity_match_cases"] == 61
            and runtime[CANDIDATE_ARM]["presented_max"] == 28
        ),
    }
    criteria["all_met"] = all(criteria.values())
    return {
        "schema_version": "adr-0132-selective-legal-guide-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "evaluation_mode": "sealed answer-declared evidence set comparison; semantic judge calls 0",
        "judge_calls": 0,
        "cases": len(captures),
        "evidence": evidence,
        "paired": paired,
        "runtime": runtime,
        "criteria": criteria,
        "selected_structure": (
            CANDIDATE_ARM if criteria["all_met"]
            else "ADR-0118-experiment-v1/integrated-atomic-claim-v4b"
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-fixtures", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args(argv)
    paths = base._artifact_paths(ADR)
    if args.prepare_fixtures:
        value = base.prepare_fixtures(
            input_lock=base.INPUT_LOCK, cm_source=base.CM_SOURCE,
            public_path=paths["public"], scoring_path=paths["scoring"],
        )
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    if args.preflight_only:
        value = base.preflight_receipt(adr=ADR, input_lock=base.INPUT_LOCK, cm_source=base.CM_SOURCE)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0 if value["status"] == "ready" else 1
    preflight = base.preflight_receipt(adr=ADR, input_lock=base.INPUT_LOCK, cm_source=base.CM_SOURCE)
    if preflight["status"] != "ready":
        raise base.BoundaryError(json.dumps(preflight, ensure_ascii=False))
    public = base._read_json(paths["public"])
    if not (args.resume and paths["seal"].exists()):
        base.run_products(public, paths, workers=args.workers, resume=args.resume)
    seal = base.validate_product_seal(paths["seal"], paths["public"], paths["captures"], metadata_only=False)
    base.open_scoring_fixture(
        paths["scoring"], paths["seal"], paths["public"], paths["captures"],
        input_lock=base.INPUT_LOCK, cm_source=base.CM_SOURCE, prevalidated_seal=seal,
    )
    captures = [base._read_json(paths["captures"] / f"{case['case_id']}.json") for case in public["cases"]]
    report = build_report(captures)
    report.update({
        "product_seal_sha256": base._sha256(paths["seal"]),
        "scoring_fixture_sha256": base._sha256(paths["scoring"]),
        "full_parent_product_seal_sha256": prior.PARENT_SEAL_SHA256,
        "raw_parent_product_seal_sha256": RAW_PARENT_SEAL_SHA256,
        "completed_at": base._now(),
    })
    report["artifact_sha256"] = base._self_hash(report, "artifact_sha256")
    base._write_json(paths["run"], report)
    print(json.dumps({
        "selected_structure": report["selected_structure"],
        "criteria": report["criteria"],
        "evidence": {arm: report["evidence"][arm]["declared"]["groups"]["all"] for arm in ARMS},
        "runtime": report["runtime"],
        "judge_calls": 0,
    }, ensure_ascii=False, indent=2))
    return 0


base.runtime_adapter_contract = runtime_adapter_contract
base.baseline_raw_stage_contract = lambda: runtime_adapter_contract()["baseline_raw_stage_capture"]
base.validate_declared_capture = validate_declared_capture
base.validate_product_capture = validate_product_capture
base._validate_execution_metrics = _validate_execution_metrics
base._validate_accounting = _validate_accounting
base.execute_product_case = execute_product_case


if __name__ == "__main__":
    raise SystemExit(main())
