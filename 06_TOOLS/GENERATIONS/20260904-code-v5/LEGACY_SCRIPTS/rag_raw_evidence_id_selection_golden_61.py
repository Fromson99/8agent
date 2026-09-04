#!/usr/bin/env python3
"""ADR-0131: 28 raw provisions plus explicit answer-time evidence IDs."""

from __future__ import annotations

import argparse
from collections import Counter
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

from scripts import rag_proposition_first_evidence_golden_61 as parent  # noqa: E402
from lawrag.core.rag import raw_evidence_selection as raw  # noqa: E402
from lawrag.core.rag.evidence_confusion import (  # noqa: E402
    EvidenceConfusion,
    aggregate_evidence_confusions,
    difficulty_balanced_score,
)
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402


base = parent.base
ADR_ID = "ADR-0131"
EXPERIMENT_ID = "ADR-0131-experiment-v1"
RUN_ID = "run-001"
BASELINE_ARM = "baseline"
CANDIDATE_ARM = raw.PROFILE
ARMS = (BASELINE_ARM, CANDIDATE_ARM)
ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0131-raw-evidence-id-selection-golden-61"
PARENT_ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0118-integrated-atomic-claim-compiler-golden-61"
PARENT_CAPTURES = PARENT_ADR / "artifacts/product-captures/run-002"
PARENT_SEAL = PARENT_ADR / "artifacts/product-capture-seal-run-002.json"
PARENT_SEAL_SHA256 = "2b50d2b2e13bbc96cf144ec8b93a6d0ccf16bf3fe4b34011f4b019c7d4ba3ba4"
PARENT_ARM = "integrated-atomic-claim-v4b"
PARENT_RAW_ARM = "baseline"
CM_V3 = ROOT / "01_DATA/review/cm_core_e2e_v3.json"
FSC_V3 = ROOT / "01_DATA/review/fsc_hard_retrieval_v3.json"
CORPUS_SIZE = 16_506

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
    base.BASELINE_ARM = BASELINE_ARM
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
        PARENT_SEAL.is_file()
        and base._sha256(PARENT_SEAL) == PARENT_SEAL_SHA256
        and len(list(PARENT_CAPTURES.glob("*.json"))) == 61
    )
    observed = [
        {**row, "parent_stage_ids": list(row["parent_stage_ids"])}
        for row in STAGE_PLAN[BASELINE_ARM]
    ]
    return {
        "ready": ready,
        "missing": [] if ready else ["hash-verified ADR-0118 run-002 product seal"],
        "baseline_result_sharing": True,
        "baseline_raw_stage_capture": {
            "ready": ready,
            "reason": "",
            "observed": observed,
        },
        "required_call": (
            "reuse the exact sealed ADR-0118 baseline 28 sections; issue exactly one "
            "compiler-free Haiku answer call per question"
        ),
    }


_PARENT_RECEIPTS: dict[str, Mapping[str, Any]] | None = None


def _parent_receipts() -> dict[str, Mapping[str, Any]]:
    if base._sha256(PARENT_SEAL) != PARENT_SEAL_SHA256:
        raise base.BoundaryError("ADR-0118 parent seal hash changed")
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
    global _PARENT_RECEIPTS
    if _PARENT_RECEIPTS is None:
        _PARENT_RECEIPTS = _parent_receipts()
    case_id = str(case["case_id"])
    receipt = _PARENT_RECEIPTS.get(case_id)
    path = PARENT_CAPTURES / f"{case_id}.json"
    if receipt is None or not path.is_file() or base._sha256(path) != receipt["sha256"]:
        raise base.BoundaryError(f"sealed parent capture mismatch: {case_id}")
    value = base._read_json(path)
    if (
        value.get("capture_sha256") != receipt.get("capture_sha256")
        or base._self_hash(value, "capture_sha256") != value.get("capture_sha256")
    ):
        raise base.BoundaryError(f"parent capture content mismatch: {case_id}")
    expected = {
        "number": int(case["number"]),
        "case_id": case_id,
        "suite": str(case["suite"]),
        "question": str(case["question"]),
    }
    if {key: value.get(key) for key in expected} != expected:
        raise base.BoundaryError(f"parent question identity mismatch: {case_id}")
    return value


def _clean_sections(parent_capture: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = list(parent_capture["arms"][PARENT_RAW_ARM]["retrieval"]["sections"])
    clean = [
        {
            "rank": number,
            "doc_id": str(row["doc_id"]),
            "node": int(row["node"]),
            "doc": str(row.get("doc") or ""),
            "path": str(row.get("path") or ""),
            "page": row.get("page"),
            "text": str(row.get("text") or ""),
        }
        for number, row in enumerate(rows, 1)
    ]
    if len(clean) != 28:
        raise base.BoundaryError(f"parent raw evidence count is not 28: {len(clean)}")
    raw.evidence_rows(clean)
    return clean


def _parent_evidence_map(parent_capture: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    output = {}
    for row in parent_capture["arms"][PARENT_ARM]["retrieval"]["sections"]:
        research = dict((row.get("legal_meta") or {}).get("integrated_research") or {})
        evidence_id = str(research.get("candidate_id") or "")
        if evidence_id:
            output[evidence_id] = {"doc_id": str(row["doc_id"]), "node": int(row["node"])}
    if len(output) != 28:
        raise base.BoundaryError(f"parent evidence ID map is not 28: {len(output)}")
    return output


def _stage_capture(index: Any, case_id: str, arm_id: str, sections) -> dict[str, Any]:
    coordinates = [(str(row["doc_id"]), int(row["node"])) for row in sections]
    recorder = ledger.StageLedgerRecorder(
        case_id, arm_id, ledger.index_article_root_canonicalizer(index),
    )
    recorder.record_stage("question-source", "source", [])
    recorder.record_stage(
        "inherited-28-present", "present", coordinates,
        parent_stage_ids=("question-source",),
    )
    return recorder.capture()


def validate_declared_capture(capture: Mapping[str, Any], case_id: str, arm_id: str):
    ledger.validate_capture(capture)
    if capture.get("case_id") != case_id or capture.get("arm_id") != arm_id:
        raise base.BoundaryError("stage capture identity mismatch")
    observed = tuple({
        "stage_id": str(row["stage_id"]),
        "kind": str(row["kind"]),
        "parent_stage_ids": tuple(row.get("parent_stage_ids") or ()),
    } for row in capture.get("stages") or ())
    if observed != STAGE_PLAN[arm_id]:
        raise base.BoundaryError(f"stage plan mismatch: {arm_id}")
    if capture.get("gold_visible_to_product") is not False:
        raise base.BoundaryError("stage capture product boundary violation")
    return deepcopy(dict(capture))


def _answer_refs(result: Mapping[str, Any], identifier_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"evidence_id": value, **identifier_map[value]}
        for value in result.get("evidence_ids") or () if value in identifier_map
    ]


def _baseline_product(index, case, parent_capture, sections):
    inherited = parent_capture["arms"][PARENT_ARM]
    identifier_map = _parent_evidence_map(parent_capture)
    answer = deepcopy(dict(inherited["answer"]))
    return {
        "arm_id": BASELINE_ARM,
        "status": "complete",
        "error": "",
        "baseline_retrieval_shared": True,
        "retrieval": {
            "sections": deepcopy(sections),
            "meta": {
                "evidence_id_map": identifier_map,
                "inherited_parent_capture_sha256": parent_capture["capture_sha256"],
                "input_profile": "ADR-0118 integrated-atomic-claim-v4b inherited declaration",
            },
            "stage_capture": _stage_capture(index, str(case["case_id"]), BASELINE_ARM, sections),
        },
        "execution_metrics": {
            "presented_evidence_count": 28,
            "input_identity_match": True,
            "compiler_fields_in_candidate_input": 0,
            "wiki_entries_in_candidate_input": 0,
            "invalid_evidence_id_count": 0,
            "unresolved_evidence_id_count": 0,
        },
        "answer": answer,
        "provider_calls": [],
        "retrieval_provider_calls": [],
        "answer_provider_calls": [],
        "usage": base._usage([]),
        "wall_ms": 0.0,
        "retrieval_wall_ms": 0.0,
        "answer_wall_ms": 0.0,
        "inherited_parent": {
            "adr_id": "ADR-0118", "run_id": "run-002", "arm_id": PARENT_ARM,
            "capture_sha256": parent_capture["capture_sha256"],
        },
        "accounting": {
            "marginal": {"usage": base._usage([]), "wall_ms": 0.0},
            "inclusive": {"usage": base._usage([]), "wall_ms": 0.0},
            "criteria_accounting": "new_calls_only",
            "sealed_parent_reuse": True,
        },
    }


def _candidate_product(index, case, real_llm, parent_capture, sections):
    started = time.perf_counter()
    recording = base.RecordingLLM(real_llm)
    result, request = raw.select_and_answer(recording, str(case["question"]), sections)
    wall_ms = round((time.perf_counter() - started) * 1000, 3)
    calls = deepcopy(recording.audit)
    usage = base._usage(calls)
    answer = {
        "answer": result["answer"],
        "answerable": result["answerable"],
        "error": result["error"],
        "evidence_ids": list(result["evidence_ids"]),
        "declared_evidence_ids_raw": list(result["declared_evidence_ids_raw"]),
        "invalid_evidence_ids": list(result["invalid_evidence_ids"]),
        "refs": _answer_refs(result, request["evidence_id_map"]),
        "wiki": [],
    }
    return {
        "arm_id": CANDIDATE_ARM,
        "status": "complete",
        "error": "",
        "baseline_retrieval_shared": True,
        "retrieval": {
            "sections": deepcopy(sections),
            "meta": {
                "evidence_id_map": deepcopy(request["evidence_id_map"]),
                "inherited_parent_capture_sha256": parent_capture["capture_sha256"],
                "input_profile": CANDIDATE_ARM,
                "input_sha256": request["input_sha256"],
                "input_fields": ["question", "evidence_id", "document", "doc_id", "node", "path", "page", "text"],
                "excluded_fields": ["compiler", "wiki", "issue", "role", "claim", "coverage", "score", "retrieval_origin", "definition_context"],
            },
            "stage_capture": _stage_capture(index, str(case["case_id"]), CANDIDATE_ARM, sections),
        },
        "execution_metrics": {
            "presented_evidence_count": 28,
            "input_identity_match": True,
            "compiler_fields_in_candidate_input": 0,
            "wiki_entries_in_candidate_input": 0,
            "invalid_evidence_id_count": len(result["invalid_evidence_ids"]),
            "unresolved_evidence_id_count": len(result["invalid_evidence_ids"]),
            "output_contract_valid": bool(result["valid"]),
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
            "adr_id": "ADR-0118", "run_id": "run-002", "arm_id": PARENT_RAW_ARM,
            "capture_sha256": parent_capture["capture_sha256"],
        },
        "accounting": {
            "marginal": {"usage": deepcopy(usage), "wall_ms": wall_ms},
            "inclusive": {"usage": deepcopy(usage), "wall_ms": wall_ms},
            "criteria_accounting": "new_calls_only",
            "sealed_parent_reuse": True,
        },
    }


def execute_product_case(index, case, real_llm, corpus_total, corpus_fingerprint, run_environment_hash):
    parent_capture = _parent_capture(case)
    sections = _clean_sections(parent_capture)
    baseline = _baseline_product(index, case, parent_capture, sections)
    candidate = _candidate_product(index, case, real_llm, parent_capture, sections)
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
        "authority_generation": str(parent_capture["authority_generation"]),
        "authority_as_of": str(parent_capture["authority_as_of"]),
        "corpus_fingerprint": str(parent_capture["corpus_fingerprint"]),
        "run_environment_hash": str(parent_capture["run_environment_hash"]),
        "runtime_observation": {
            "current_corpus_article_roots": int(corpus_total),
            "current_corpus_fingerprint": corpus_fingerprint,
            "current_run_environment_hash": run_environment_hash,
        },
        "corpus_article_roots": int(parent_capture["corpus_article_roots"]),
        "arms": {BASELINE_ARM: baseline, CANDIDATE_ARM: candidate},
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
        "compiler_fields_in_candidate_input", "wiki_entries_in_candidate_input",
        "invalid_evidence_id_count", "unresolved_evidence_id_count",
    ):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise base.BoundaryError(f"invalid execution metric: {key}")


def _validate_accounting(arms: Mapping[str, Any]) -> None:
    if arms[BASELINE_ARM]["usage"] != base._usage([]):
        raise base.BoundaryError("inherited baseline must add no new calls")
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
        actual = {key: value.get(key) for key in expected}
        if actual != expected:
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
        expected_calls = 0 if arm_id == BASELINE_ARM else 1
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
    candidate = arms[CANDIDATE_ARM]
    meta = candidate["retrieval"]["meta"]
    if meta.get("excluded_fields") != [
        "compiler", "wiki", "issue", "role", "claim", "coverage", "score",
        "retrieval_origin", "definition_context",
    ]:
        raise base.BoundaryError("raw input exclusion contract mismatch")
    _validate_accounting(arms)


def _gold_cases() -> dict[str, dict[str, Any]]:
    output = {}
    for suite, path, key in (
        ("core", CM_V3, "evidence_articles"),
        ("hard", FSC_V3, "current_evidence_articles"),
    ):
        for case in json.loads(path.read_text("utf-8"))["cases"]:
            output[str(case["id"])] = {
                "suite": suite,
                "required": {f"{row['doc_id']}:{row['node']}" for row in case[key]},
            }
    return output


def _sets(product: Mapping[str, Any]):
    sections = list(product["retrieval"]["sections"])
    presented = {f"{row['doc_id']}:{row['node']}" for row in sections}
    id_map = {
        str(key): f"{value['doc_id']}:{value['node']}"
        for key, value in product["retrieval"]["meta"]["evidence_id_map"].items()
    }
    declared_ids = {str(value) for value in product["answer"].get("evidence_ids") or ()}
    unresolved = sorted(declared_ids - set(id_map))
    declared = {id_map[value] for value in declared_ids if value in id_map}
    return presented, declared, unresolved


def _aggregate(captures, arm_id: str) -> dict[str, Any]:
    gold = _gold_cases()
    detail = []
    for capture in captures:
        case_id = str(capture["case_id"])
        presented, declared, unresolved = _sets(capture["arms"][arm_id])
        required = gold[case_id]["required"]
        detail.append({
            "case_id": case_id,
            "suite": gold[case_id]["suite"],
            "presented": EvidenceConfusion.from_sets(required, presented, universe_size=CORPUS_SIZE),
            "declared": EvidenceConfusion.from_sets(required, declared, universe_size=CORPUS_SIZE),
            "unresolved": unresolved,
        })

    def summarize(key: str):
        groups = {}
        for name, subset in (
            ("all", detail),
            ("core", [row for row in detail if row["suite"] == "core"]),
            ("hard", [row for row in detail if row["suite"] == "hard"]),
        ):
            groups[name] = aggregate_evidence_confusions([row[key] for row in subset])
        return {
            "groups": groups,
            "difficulty_balanced_score": difficulty_balanced_score({"core": groups["core"], "hard": groups["hard"]}),
        }

    return {
        "presented": summarize("presented"),
        "declared": summarize("declared"),
        "unresolved_evidence_ids": sum(len(row["unresolved"]) for row in detail),
        "case_rows": [{
            "case_id": row["case_id"], "suite": row["suite"],
            "presented": row["presented"].to_dict(),
            "declared": row["declared"].to_dict(),
            "unresolved_evidence_ids": row["unresolved"],
        } for row in detail],
    }


def _percentile(values, ratio):
    rows = sorted(float(value) for value in values)
    return round(rows[min(len(rows) - 1, round((len(rows) - 1) * ratio))], 3) if rows else 0.0


def _paired(evidence):
    baseline = {row["case_id"]: row["declared"] for row in evidence[BASELINE_ARM]["case_rows"]}
    candidate = {row["case_id"]: row["declared"] for row in evidence[CANDIDATE_ARM]["case_rows"]}
    counts = Counter()
    gained, lost = [], []
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
    paired = _paired(evidence)
    candidate_products = [row["arms"][CANDIDATE_ARM] for row in captures]
    candidate_calls = [call for product in candidate_products for call in product["provider_calls"]]
    provider_latencies = [float((call.get("provider") or {}).get("dur_ms") or 0) for call in candidate_calls]
    usage = base._usage(candidate_calls)
    runtime = {
        "baseline": {"new_product_calls": 0, "sealed_parent_reuse": True},
        CANDIDATE_ARM: {
            "complete_cases": len(candidate_products),
            "new_product_calls": len(candidate_calls),
            "usage": usage,
            "provider_p50_ms": _percentile(provider_latencies, .50),
            "provider_p95_ms": _percentile(provider_latencies, .95),
            "answer_wall_p50_ms": _percentile((row["answer_wall_ms"] for row in candidate_products), .50),
            "answer_wall_p95_ms": _percentile((row["answer_wall_ms"] for row in candidate_products), .95),
            "invalid_evidence_ids": sum(int(row["execution_metrics"]["invalid_evidence_id_count"]) for row in candidate_products),
            "compiler_fields_in_input": sum(int(row["execution_metrics"]["compiler_fields_in_candidate_input"]) for row in candidate_products),
            "wiki_entries_in_input": sum(int(row["execution_metrics"]["wiki_entries_in_candidate_input"]) for row in candidate_products),
            "input_identity_match_cases": sum(bool(row["execution_metrics"]["input_identity_match"]) for row in candidate_products),
            "presented_max": max(len(row["retrieval"]["sections"]) for row in candidate_products),
        },
    }
    declared = evidence[CANDIDATE_ARM]["declared"]
    groups = declared["groups"]
    criteria = {
        "tp_at_least_67": groups["all"]["tp"] >= 67,
        "complete_at_least_29": groups["all"]["complete_cases"] >= 29,
        "precision_at_least_04820": groups["all"]["precision"] >= .4820,
        "hard_recall_at_least_06667": groups["hard"]["recall"] >= .6667,
        "difficulty_score_at_least_52_63897": declared["difficulty_balanced_score"] >= 52.63897,
        "baseline_only_regressions_at_most_3": len(paired["lost"]) <= 3,
        "all_61_complete": runtime[CANDIDATE_ARM]["complete_cases"] == 61,
        "exactly_61_product_calls": runtime[CANDIDATE_ARM]["new_product_calls"] == 61,
        "input_tokens_at_most_9000000": usage["input_tokens"] <= 9_000_000,
        "provider_p95_at_most_45000_ms": runtime[CANDIDATE_ARM]["provider_p95_ms"] <= 45_000,
        "invalid_ids_zero": runtime[CANDIDATE_ARM]["invalid_evidence_ids"] == 0,
        "compiler_and_wiki_leakage_zero": runtime[CANDIDATE_ARM]["compiler_fields_in_input"] == 0 and runtime[CANDIDATE_ARM]["wiki_entries_in_input"] == 0,
        "input_identity_61_of_61": runtime[CANDIDATE_ARM]["input_identity_match_cases"] == 61 and runtime[CANDIDATE_ARM]["presented_max"] == 28,
        "judge_calls_zero": True,
    }
    criteria["all_met"] = all(criteria.values())
    strong = {
        "tp_at_least_72": groups["all"]["tp"] >= 72,
        "complete_at_least_34": groups["all"]["complete_cases"] >= 34,
        "candidate_gains_exceed_regressions": len(paired["gained"]) > len(paired["lost"]),
        "noninferiority_all_met": criteria["all_met"],
    }
    strong["all_met"] = all(strong.values())
    return {
        "schema_version": "adr-0131-raw-evidence-id-selection-v1",
        "adr_id": ADR_ID, "experiment_id": EXPERIMENT_ID, "run_id": RUN_ID,
        "evaluation_mode": "sealed evidence set-containment; semantic judge calls 0",
        "judge_calls": 0,
        "cases": len(captures),
        "evidence": evidence,
        "paired": paired,
        "runtime": runtime,
        "criteria": {"noninferiority": criteria, "strong_compiler_misdirection": strong},
        "selected_structure": CANDIDATE_ARM if criteria["all_met"] else "ADR-0118-experiment-v1/integrated-atomic-claim-v4b",
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
    seal = base.validate_product_seal(
        paths["seal"], paths["public"], paths["captures"], metadata_only=False,
    )
    base.open_scoring_fixture(
        paths["scoring"], paths["seal"], paths["public"], paths["captures"],
        input_lock=base.INPUT_LOCK, cm_source=base.CM_SOURCE,
        prevalidated_seal=seal,
    )
    captures = [base._read_json(paths["captures"] / f"{case['case_id']}.json") for case in public["cases"]]
    report = build_report(captures)
    report.update({
        "product_seal_sha256": base._sha256(paths["seal"]),
        "scoring_fixture_sha256": base._sha256(paths["scoring"]),
        "parent_product_seal_sha256": PARENT_SEAL_SHA256,
        "completed_at": base._now(),
    })
    report["artifact_sha256"] = base._self_hash(report, "artifact_sha256")
    base._write_json(paths["run"], report)
    print(json.dumps({
        "selected_structure": report["selected_structure"],
        "criteria": report["criteria"],
        "evidence": {
            arm: report["evidence"][arm]["declared"]["groups"]["all"] for arm in ARMS
        },
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
