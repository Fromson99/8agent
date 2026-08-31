#!/usr/bin/env python3
"""ADR-0130 Golden61 A/B/C runner with no semantic judge."""
from __future__ import annotations

import argparse
import concurrent.futures
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import statistics
import sys
import threading
import time
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import rag_proposition_first_evidence_golden_61 as parent  # noqa: E402
from lawrag.core.rag import evidence_slot_nondropping as slot  # noqa: E402
from lawrag.core.rag import proposition_first_evidence_research as proposition  # noqa: E402
from lawrag.core.rag.evidence_confusion import (  # noqa: E402
    EvidenceConfusion,
    aggregate_evidence_confusions,
    difficulty_balanced_score,
)
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402
from lawrag.core.rag.legal_proposition_compiler import compile_legal_review  # noqa: E402


base = parent.base
ADR_ID = "ADR-0130"
EXPERIMENT_ID = "ADR-0130-experiment-v1"
RUN_ID = "run-001"
BASELINE_ARM = "baseline"
SLOT_ONLY_ARM = slot.PROFILE_SLOT_ONLY
TARGETED_ARM = slot.PROFILE_SLOT_TARGETED
ARMS = (BASELINE_ARM, SLOT_ONLY_ARM, TARGETED_ARM)
ADR = ROOT / "docs/adr/ADR-0130-evidence-slot-nondropping-compiler-golden-61"
PARENT_ADR = ROOT / "docs/adr/ADR-0129-proposition-first-evidence-preserving-compiler-golden-61"
PARENT_CAPTURES = PARENT_ADR / "artifacts/product-captures/run-001"
PARENT_SEAL = PARENT_ADR / "artifacts/product-capture-seal-run-001.json"
PARENT_SEAL_SHA256 = "17bf75c1f87664788103c1db05dec316b240268220fd8afbbeb4f8ddc3c28bb4"
PARENT_TARGETED_ARM = "proposition-first-evidence-v1"
CM_V3 = ROOT / "data/review/cm_core_e2e_v3.json"
FSC_V3 = ROOT / "data/review/fsc_hard_retrieval_v3.json"
CORPUS_SIZE = 16_506


STAGE_PLAN = {
    BASELINE_ARM: (
        ("question-source", "source", ()),
        ("inherited-parent-evidence", "retrieve", ("question-source",)),
        ("inherited-identity-filter", "filter", ("inherited-parent-evidence",)),
        ("compiled-evidence-present", "present", ("inherited-identity-filter",)),
    ),
    SLOT_ONLY_ARM: (
        ("question-source", "source", ()),
        ("inherited-parent-evidence", "retrieve", ("question-source",)),
        ("evidence-slot-compile", "select", ("inherited-parent-evidence",)),
        ("slot-evidence-present", "present", ("evidence-slot-compile",)),
    ),
    TARGETED_ARM: (
        ("question-source", "source", ()),
        ("inherited-parent-evidence", "retrieve", ("question-source",)),
        ("evidence-slot-compile", "select", ("inherited-parent-evidence",)),
        ("missing-role-targeted-retrieve", "retrieve", ("evidence-slot-compile",)),
        ("provenance-canonicalize", "canonicalize", ("missing-role-targeted-retrieve",)),
        ("slot-evidence-present", "present", ("provenance-canonicalize",)),
    ),
}


def _stage_rows(arm: str) -> tuple[dict[str, Any], ...]:
    return tuple({
        "stage_id": stage_id, "kind": kind, "parent_stage_ids": tuple(parents),
    } for stage_id, kind, parents in STAGE_PLAN[arm])


def _install_identity() -> None:
    base.__file__ = __file__
    base.ADR_ID = ADR_ID
    base.EXPERIMENT_ID = EXPERIMENT_ID
    base.RUN_ID = RUN_ID
    base.ADR = ADR
    base.BASELINE_ARM = BASELINE_ARM
    base.CANDIDATE_ARM = TARGETED_ARM
    base.ARMS = ARMS
    base.STAGE_PLAN = {arm: _stage_rows(arm) for arm in ARMS}
    base.PUBLIC_FIXTURE_NAME = "public-questions-run-001.json"
    base.SCORING_FIXTURE_NAME = "scoring-fixture-run-001.json"
    base.SEAL_NAME = "product-capture-seal-run-001.json"
    base.RUN_ARTIFACT_NAME = "run-001.json"
    base.LEDGER_NAME = "retrieval-stage-ledger-run-001.json"


_install_identity()


def runtime_adapter_contract(retrieve=None) -> dict[str, Any]:
    del retrieve
    ready = (
        PARENT_SEAL.is_file()
        and base._sha256(PARENT_SEAL) == PARENT_SEAL_SHA256
        and len(list(PARENT_CAPTURES.glob("*.json"))) == 61
    )
    return {
        "ready": ready,
        "missing": [] if ready else ["hash-verified ADR-0129 sealed captures"],
        "baseline_result_sharing": True,
        "baseline_raw_stage_capture": {
            "ready": ready, "reason": "",
            "observed": list(_stage_rows(BASELINE_ARM)),
        },
        "required_call": (
            "reuse sealed ADR-0129 initial/final compiler outputs; call only the "
            "slot-only and targeted non-dropping answer roles"
        ),
    }


def _parent_receipts() -> dict[str, Mapping[str, Any]]:
    if base._sha256(PARENT_SEAL) != PARENT_SEAL_SHA256:
        raise base.BoundaryError("ADR-0129 parent seal hash changed")
    seal = base._read_json(PARENT_SEAL)
    if seal.get("case_count") != 61 or seal.get("gold_visible_to_product") is not False:
        raise base.BoundaryError("ADR-0129 parent seal contract mismatch")
    return {str(row["case_id"]): row for row in seal["case_receipts"]}


_PARENT_RECEIPTS: dict[str, Mapping[str, Any]] | None = None


def _parent_capture(case: Mapping[str, Any]) -> dict[str, Any]:
    global _PARENT_RECEIPTS
    if _PARENT_RECEIPTS is None:
        _PARENT_RECEIPTS = _parent_receipts()
    case_id = str(case["case_id"])
    receipt = _PARENT_RECEIPTS[case_id]
    path = PARENT_CAPTURES / f"{case_id}.json"
    if base._sha256(path) != receipt["sha256"]:
        raise base.BoundaryError(f"ADR-0129 parent capture changed: {case_id}")
    value = base._read_json(path)
    if value.get("capture_sha256") != receipt.get("capture_sha256"):
        raise base.BoundaryError(f"ADR-0129 parent self hash mismatch: {case_id}")
    return value


def _clean_section(row: Mapping[str, Any]) -> Any:
    section = parent._section(row)
    meta = dict(section.legal_meta or {})
    meta.pop("legal_compilation", None)
    section.legal_meta = meta
    return section


def _sections(rows: Sequence[Mapping[str, Any]], limit: int | None = None) -> list[Any]:
    output = [_clean_section(row) for row in (rows[:limit] if limit is not None else rows)]
    for number, section in enumerate(output, 1):
        section.n = number
    return output


def _compiler_result(question: str, sections: Sequence[Any], receipt: Mapping[str, Any]):
    evidence = proposition.evidence_from_sections(sections)
    return compile_legal_review(question, evidence, receipt.get("raw_output"))


def _capture_stages(index: Any, case_id: str, arm: str, initial, final) -> dict[str, Any]:
    initial_coordinates = [(row.doc_id, int(row.node)) for row in initial]
    final_coordinates = [(row.doc_id, int(row.node)) for row in final]
    recorder = ledger.StageLedgerRecorder(
        case_id, arm, ledger.index_article_root_canonicalizer(index),
    )
    for stage_id, kind, parents in STAGE_PLAN[arm]:
        if stage_id == "question-source":
            after = []
        elif stage_id in {"inherited-parent-evidence", "inherited-identity-filter", "evidence-slot-compile"}:
            after = initial_coordinates
        else:
            after = final_coordinates
        recorder.record_stage(stage_id, kind, after, parent_stage_ids=parents)
    return recorder.capture()


def _answer_payload(answer: Any) -> dict[str, Any]:
    return {
        "answer": answer.answer,
        "answerable": bool(answer.answerable),
        "error": answer.error,
        "refs": base._jsonable(answer.refs),
        "wiki": base._jsonable(answer.wiki),
        "conclusion_strength": answer.conclusion_strength,
        "evidence_ids": list(answer.evidence_ids),
        "issue_results": base._jsonable(answer.issue_results),
        "gate_violation": bool(answer.gate_violation),
    }


def _metrics(sections, packet, result, answer_result, parent_meta, wall_ms: float) -> dict[str, Any]:
    verified = sum(not bool((row.legal_meta or {}).get("verification_error")) for row in sections)
    packet_violations = slot.packet_integrity(packet)
    answer_violations = list(answer_result.violations)
    ids = {proposition._candidate_id(row) for row in sections}
    bound_ids = {
        str(value) for row in packet.get("slots") or ()
        if row.get("state") == "SATISFIED" for value in row.get("evidence_ids") or ()
    }
    closed = sorted(bound_ids - ids)
    return {
        "integrated_total_ms": round(wall_ms, 3),
        "planner_provider_ms": 0.0,
        "deterministic_planning_ms": 0.0,
        "presented_evidence_count": len(sections),
        "verified_evidence_count": verified,
        "verified_rate": round(verified / len(sections), 6) if sections else 0.0,
        "closed_id_violations": closed,
        "closed_id_violation_count": len(closed),
        "generation_violations": [],
        "generation_violation_count": 0,
        "verified_evidence_violations": [],
        "verified_evidence_violation_count": 0,
        "slot_total": len(packet.get("slots") or ()),
        "slot_satisfied": len(packet.get("satisfied_slot_ids") or ()),
        "slot_missing": len(packet.get("missing_slot_ids") or ()),
        "slot_bound_evidence_count": len(bound_ids),
        "slot_packet_violations": packet_violations,
        "slot_packet_violation_count": len(packet_violations),
        "answer_slot_violations": answer_violations,
        "answer_slot_violation_count": len(answer_violations),
        "unresolved_evidence_id_count": len(closed),
        "global_block_count": 0,
        "floor_preserved": True,
        "targeted_probe_count": int(parent_meta.get("targeted_probe_count") or 0),
        "targeted_added_count": int(parent_meta.get("targeted_added_count") or 0),
        "compiler_status": str(result.status),
    }


def _baseline_metrics(product: Mapping[str, Any]) -> dict[str, Any]:
    metrics = deepcopy(dict(product.get("execution_metrics") or {}))
    presented = len((product.get("retrieval") or {}).get("sections") or ())
    metrics.update({
        "slot_total": 0, "slot_satisfied": 0, "slot_missing": 0,
        "slot_bound_evidence_count": len((product.get("answer") or {}).get("evidence_ids") or ()),
        "slot_packet_violations": [], "slot_packet_violation_count": 0,
        "answer_slot_violations": [], "answer_slot_violation_count": 0,
        "unresolved_evidence_id_count": 0, "global_block_count": 0,
        "floor_preserved": True, "targeted_probe_count": 0,
        "targeted_added_count": 0, "compiler_status": "INHERITED",
    })
    metrics.setdefault("presented_evidence_count", presented)
    return metrics


def _execute_arm(*, arm_id: str, index: Any, case: Mapping[str, Any], real_llm: Any, baseline_result=None):
    started = time.perf_counter()
    parent_capture = _parent_capture(case)
    if arm_id == BASELINE_ARM:
        product = deepcopy(parent_capture["arms"][BASELINE_ARM])
        product["execution_metrics"] = _baseline_metrics(product)
        product["inherited_parent"] = {
            "adr_id": "ADR-0129", "run_id": "run-001", "arm_id": BASELINE_ARM,
            "capture_sha256": parent_capture["capture_sha256"],
        }
        initial = _sections(product["retrieval"]["sections"])
        return product, {"parent": parent_capture, "initial": initial}

    if baseline_result is None:
        raise base.BoundaryError("slot candidate requires baseline context")
    parent_candidate = parent_capture["arms"][PARENT_TARGETED_ARM]
    parent_meta = dict(parent_candidate["retrieval"]["meta"]["proposition_first_evidence"])
    initial = deepcopy(baseline_result["initial"])
    if arm_id == SLOT_ONLY_ARM:
        sections = initial
        compiler_receipt = parent_meta["initial_compiler_receipt"]
        kind = "rag.evidence_slot_nondropping.slot_only_answer"
        effective_parent_meta = {"targeted_probe_count": 0, "targeted_added_count": 0}
    else:
        sections = _sections(parent_candidate["retrieval"]["sections"])
        compiler_receipt = parent_meta["final_compiler_receipt"]
        kind = "rag.evidence_slot_nondropping.targeted_answer"
        effective_parent_meta = parent_meta
    result = _compiler_result(str(case["question"]), sections, compiler_receipt)
    recording = base.RecordingLLM(real_llm)
    answer_result = slot.synthesize_slot_answer(
        recording, str(case["question"]), result, sections, kind=kind,
    )
    wall_ms = round((time.perf_counter() - started) * 1000, 3)
    packet = dict(answer_result.packet)
    stage_capture = _capture_stages(index, str(case["case_id"]), arm_id, initial, sections)
    metrics = _metrics(
        sections, packet, result, answer_result, effective_parent_meta, wall_ms,
    )
    calls = deepcopy(recording.audit)
    product = {
        "arm_id": arm_id,
        "status": "complete",
        "error": "",
        "baseline_retrieval_shared": True,
        "retrieval": {
            "sections": base._section_rows(sections),
            "meta": {
                "evidence_slot": {
                    "profile": arm_id,
                    "slot_packet": packet,
                    "parent_compiler_validation_errors": list(result.validation_errors),
                    "parent_targeted_probe_count": metrics["targeted_probe_count"],
                    "parent_targeted_added_count": metrics["targeted_added_count"],
                },
                "parent_capture_sha256": parent_capture["capture_sha256"],
            },
            "stage_capture": stage_capture,
        },
        "execution_metrics": metrics,
        "answer": _answer_payload(answer_result.answer),
        "provider_calls": calls,
        "retrieval_provider_calls": [],
        "answer_provider_calls": calls,
        "usage": base._usage(calls),
        "wall_ms": wall_ms,
        "retrieval_wall_ms": 0.0,
        "answer_wall_ms": wall_ms,
        "inherited_parent": {
            "adr_id": "ADR-0129", "run_id": "run-001",
            "arm_id": PARENT_TARGETED_ARM,
            "capture_sha256": parent_capture["capture_sha256"],
            "compiler_receipt": "initial" if arm_id == SLOT_ONLY_ARM else "final",
        },
    }
    return product, None


def _validate_execution_metrics(arm: Mapping[str, Any]) -> None:
    metrics = arm.get("execution_metrics") or {}
    sections = list((arm.get("retrieval") or {}).get("sections") or ())
    if int(metrics.get("presented_evidence_count") or -1) != len(sections):
        raise base.BoundaryError("presented evidence metric mismatch")
    for name in (
        "slot_total", "slot_satisfied", "slot_missing", "slot_bound_evidence_count",
        "slot_packet_violation_count", "answer_slot_violation_count",
        "unresolved_evidence_id_count", "global_block_count", "targeted_probe_count",
        "targeted_added_count",
    ):
        value = metrics.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise base.BoundaryError(f"invalid execution metric: {name}")
    for rows, count in (
        ("slot_packet_violations", "slot_packet_violation_count"),
        ("answer_slot_violations", "answer_slot_violation_count"),
    ):
        if not isinstance(metrics.get(rows), list) or len(set(metrics[rows])) != metrics[count]:
            raise base.BoundaryError(f"slot violation metric mismatch: {rows}")


def _account_arm(arm: dict[str, Any], baseline: Mapping[str, Any], *, is_baseline: bool) -> None:
    if is_baseline:
        arm["accounting"] = {
            "marginal": {"usage": deepcopy(arm["usage"]), "wall_ms": arm["wall_ms"]},
            "inclusive": {"usage": deepcopy(arm["usage"]), "wall_ms": arm["wall_ms"]},
            "shared_baseline_retrieval_added": False,
            "baseline_answer_added": False,
        }
        return
    shared_usage = base._usage(baseline.get("retrieval_provider_calls") or ())
    shared_wall = float(baseline.get("retrieval_wall_ms") or 0)
    arm["accounting"] = {
        "marginal": {"usage": deepcopy(arm["usage"]), "wall_ms": arm["wall_ms"]},
        "inclusive": {
            "usage": base._usage_add(arm["usage"], shared_usage),
            "wall_ms": round(float(arm["wall_ms"]) + shared_wall, 3),
        },
        "shared_baseline_retrieval_added": True,
        "shared_baseline_retrieval_usage": shared_usage,
        "shared_baseline_retrieval_wall_ms": shared_wall,
        "baseline_answer_added": False,
        "criteria_accounting": "inclusive",
    }


def _validate_accounting(arms: Mapping[str, Any]) -> None:
    baseline = arms[BASELINE_ARM]
    if baseline["accounting"]["marginal"] != baseline["accounting"]["inclusive"]:
        raise base.BoundaryError("baseline accounting mismatch")
    for arm_id in (SLOT_ONLY_ARM, TARGETED_ARM):
        arm = arms[arm_id]
        accounting = arm.get("accounting") or {}
        if accounting.get("marginal") != {"usage": arm["usage"], "wall_ms": arm["wall_ms"]}:
            raise base.BoundaryError(f"candidate marginal accounting mismatch: {arm_id}")
        expected_usage = base._usage_add(
            arm["usage"], base._usage(baseline.get("retrieval_provider_calls") or ()),
        )
        if (accounting.get("inclusive") or {}).get("usage") != expected_usage:
            raise base.BoundaryError(f"candidate inclusive usage mismatch: {arm_id}")


def execute_product_case(index, case, real_llm, corpus_total, corpus_fingerprint, run_environment_hash):
    baseline, context = _execute_arm(
        arm_id=BASELINE_ARM, index=index, case=case, real_llm=real_llm,
    )
    slot_only, _ = _execute_arm(
        arm_id=SLOT_ONLY_ARM, index=index, case=case, real_llm=real_llm,
        baseline_result=context,
    )
    targeted, _ = _execute_arm(
        arm_id=TARGETED_ARM, index=index, case=case, real_llm=real_llm,
        baseline_result=context,
    )
    _account_arm(baseline, baseline, is_baseline=True)
    _account_arm(slot_only, baseline, is_baseline=False)
    _account_arm(targeted, baseline, is_baseline=False)
    value = {
        "schema_version": "adr-0114-gold-free-product-capture-v1",
        "adr_id": ADR_ID, "experiment_id": EXPERIMENT_ID, "run_id": RUN_ID,
        "number": int(case["number"]), "case_id": str(case["case_id"]),
        "suite": str(case["suite"]), "question": str(case["question"]),
        "model": base.MODEL, "gold_visible_to_product": False,
        "authority_generation": str(index.authority_generation),
        "authority_as_of": str(index.authority_as_of),
        "corpus_fingerprint": corpus_fingerprint,
        "run_environment_hash": run_environment_hash,
        "corpus_article_roots": int(corpus_total),
        "arms": {BASELINE_ARM: baseline, SLOT_ONLY_ARM: slot_only, TARGETED_ARM: targeted},
        "captured_at": base._now(), "complete": True,
    }
    base._forbid_product_gold(value)
    value["capture_sha256"] = base._self_hash(value, "capture_sha256")
    base.validate_product_capture(value)
    return value


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


def _sets(product: Mapping[str, Any]) -> tuple[set[str], set[str], set[str], list[str]]:
    sections = list((product.get("retrieval") or {}).get("sections") or ())
    presented = {f"{row['doc_id']}:{row['node']}" for row in sections}
    id_map = {}
    for row in sections:
        research = dict((row.get("legal_meta") or {}).get("integrated_research") or {})
        evidence_id = str(research.get("candidate_id") or "")
        if evidence_id:
            id_map[evidence_id] = f"{row['doc_id']}:{row['node']}"
    declared_ids = {str(value) for value in (product.get("answer") or {}).get("evidence_ids") or ()}
    unresolved = sorted(declared_ids - set(id_map))
    declared = {id_map[value] for value in declared_ids if value in id_map}
    packet = dict(((product.get("retrieval") or {}).get("meta") or {}).get("evidence_slot") or {}).get("slot_packet") or {}
    bound_ids = {
        str(value) for row in packet.get("slots") or () if row.get("state") == "SATISFIED"
        for value in row.get("evidence_ids") or ()
    }
    bound = {id_map[value] for value in bound_ids if value in id_map}
    if not packet:
        bound = set(declared)
    unresolved.extend(sorted(bound_ids - set(id_map)))
    return presented, bound, declared, sorted(set(unresolved))


def _aggregate(rows, arm: str) -> dict[str, Any]:
    gold = _gold_cases()
    detail = []
    for capture in rows:
        case_id = str(capture["case_id"])
        presented, bound, declared, unresolved = _sets(capture["arms"][arm])
        required = gold[case_id]["required"]
        detail.append({
            "case_id": case_id, "suite": gold[case_id]["suite"],
            "presented": EvidenceConfusion.from_sets(required, presented, universe_size=CORPUS_SIZE),
            "bound": EvidenceConfusion.from_sets(required, bound, universe_size=CORPUS_SIZE),
            "declared": EvidenceConfusion.from_sets(required, declared, universe_size=CORPUS_SIZE),
            "unresolved": unresolved,
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
        "bound": summarize("bound"),
        "declared": summarize("declared"),
        "unresolved_evidence_ids": sum(len(row["unresolved"]) for row in detail),
        "case_rows": [{
            "case_id": row["case_id"], "suite": row["suite"],
            "presented": row["presented"].to_dict(),
            "bound": row["bound"].to_dict(),
            "declared": row["declared"].to_dict(),
            "unresolved_evidence_ids": row["unresolved"],
        } for row in detail],
    }


def _percentile(values, fraction):
    rows = sorted(float(value) for value in values)
    if not rows:
        return 0.0
    return round(rows[min(len(rows) - 1, max(0, round((len(rows) - 1) * fraction)))], 3)


def _paired(metric_by_arm, candidate: str, key: str = "declared") -> dict[str, Any]:
    baseline = {row["case_id"]: row[key] for row in metric_by_arm[BASELINE_ARM]["case_rows"]}
    other = {row["case_id"]: row[key] for row in metric_by_arm[candidate]["case_rows"]}
    counts = Counter()
    gained, lost = [], []
    for case_id in baseline:
        before = int(baseline[case_id]["fn"]) == 0
        after = int(other[case_id]["fn"]) == 0
        label = "both_complete" if before and after else "both_incomplete"
        if after and not before:
            label = "candidate_only_complete"; gained.append(case_id)
        elif before and not after:
            label = "baseline_only_complete"; lost.append(case_id)
        counts[label] += 1
    return {"counts": dict(counts), "gained": gained, "lost": lost}


def build_report(captures: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    evidence = {arm: _aggregate(captures, arm) for arm in ARMS}
    runtime = {}
    for arm in ARMS:
        products = [row["arms"][arm] for row in captures]
        metrics = [row.get("execution_metrics") or {} for row in products]
        inclusive_usage = {key: sum(int((row["accounting"]["inclusive"]["usage"]).get(key) or 0) for row in products) for key in ("calls", "input_tokens", "output_tokens", "provider_duration_ms", "errors")}
        runtime[arm] = {
            "complete_cases": sum(row.get("status") == "complete" for row in products),
            "error_cases": [capture["case_id"] for capture, product in zip(captures, products) if product.get("status") != "complete"],
            "presented_max": max(len(row["retrieval"]["sections"]) for row in products),
            "product_p50_ms": _percentile((row["accounting"]["inclusive"]["wall_ms"] for row in products), .50),
            "product_p95_ms": _percentile((row["accounting"]["inclusive"]["wall_ms"] for row in products), .95),
            "inclusive_usage": inclusive_usage,
            "slot_packet_violations": sum(int(row.get("slot_packet_violation_count") or 0) for row in metrics),
            "answer_slot_violations": sum(int(row.get("answer_slot_violation_count") or 0) for row in metrics),
            "unresolved_evidence_ids": evidence[arm]["unresolved_evidence_ids"],
            "global_blocks": sum(int(row.get("global_block_count") or 0) for row in metrics),
            "floor_preserved_cases": sum(bool(row.get("floor_preserved")) for row in metrics),
            "targeted_probes": sum(int(row.get("targeted_probe_count") or 0) for row in metrics),
            "targeted_additions": sum(int(row.get("targeted_added_count") or 0) for row in metrics),
        }
    paired_b = _paired(evidence, SLOT_ONLY_ARM)
    paired_c = _paired(evidence, TARGETED_ARM)
    bdecl = evidence[SLOT_ONLY_ARM]["declared"]["groups"]
    cdecl = evidence[TARGETED_ARM]["declared"]["groups"]
    cpresent = evidence[TARGETED_ARM]["presented"]["groups"]
    criteria_b = {
        "declared_tp_at_least_67": bdecl["all"]["tp"] >= 67,
        "declared_complete_at_least_29": bdecl["all"]["complete_cases"] >= 29,
        "hard_declared_recall_at_least_baseline": bdecl["hard"]["recall"] >= .666666,
        "baseline_only_regressions_zero": not paired_b["lost"],
        "binding_violations_zero": runtime[SLOT_ONLY_ARM]["slot_packet_violations"] == 0 and runtime[SLOT_ONLY_ARM]["answer_slot_violations"] == 0,
    }
    criteria_c = {
        "presented_tp_at_least_105": cpresent["all"]["tp"] >= 105,
        "presented_complete_at_least_55": cpresent["all"]["complete_cases"] >= 55,
        "declared_tp_at_least_105": cdecl["all"]["tp"] >= 105,
        "declared_complete_at_least_55": cdecl["all"]["complete_cases"] >= 55,
        "hard_declared_recall_at_least_080": cdecl["hard"]["recall"] >= .80,
        "baseline_only_regressions_zero": not paired_c["lost"],
        "integrity_zero": runtime[TARGETED_ARM]["slot_packet_violations"] == 0 and runtime[TARGETED_ARM]["answer_slot_violations"] == 0 and runtime[TARGETED_ARM]["unresolved_evidence_ids"] == 0,
        "global_blocks_zero": runtime[TARGETED_ARM]["global_blocks"] == 0,
        "all_61_complete": runtime[TARGETED_ARM]["complete_cases"] == 61,
        "cap_at_most_32": runtime[TARGETED_ARM]["presented_max"] <= 32,
        "p95_at_most_240000_ms": runtime[TARGETED_ARM]["product_p95_ms"] <= 240000,
        "input_tokens_at_most_24000000": runtime[TARGETED_ARM]["inclusive_usage"]["input_tokens"] <= 24000000,
    }
    criteria_b["all_met"] = all(criteria_b.values())
    criteria_c["all_met"] = all(criteria_c.values())
    return {
        "schema_version": "adr-0130-deterministic-evidence-run-v1",
        "adr_id": ADR_ID, "experiment_id": EXPERIMENT_ID, "run_id": RUN_ID,
        "evaluation_mode": "sealed evidence set-containment; semantic judge calls 0",
        "judge_calls": 0, "cases": len(captures),
        "evidence": evidence, "runtime": runtime,
        "paired": {SLOT_ONLY_ARM: paired_b, TARGETED_ARM: paired_c},
        "criteria": {SLOT_ONLY_ARM: criteria_b, TARGETED_ARM: criteria_c},
        "selected_structure": TARGETED_ARM if criteria_c["all_met"] else "ADR-0118-experiment-v1/integrated-atomic-claim-v4b",
    }


def write_ledger(captures, scoring, path: Path) -> dict[str, Any]:
    score_by_id = {str(row["case_id"]): row for row in scoring["cases"]}
    graded = []
    for capture in captures:
        gold = [(str(row["doc_id"]), int(row["node"])) for row in score_by_id[capture["case_id"]]["gold_articles"]]
        for arm in ARMS:
            graded.append(ledger.grade_capture(capture["arms"][arm]["retrieval"]["stage_capture"], gold))
    declared = {arm: [row[0] for row in STAGE_PLAN[arm]] for arm in ARMS}
    run = ledger.build_run_artifact(RUN_ID, graded, declared)
    value = ledger.build_experiment_artifact(ADR_ID, EXPERIMENT_ID, [run])
    base._write_json(path, value)
    return value


def _run_products(public, paths, *, workers: int, resume: bool):
    return base.run_products(public, paths, workers=workers, resume=resume)


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
        print(json.dumps(value, ensure_ascii=False, indent=2)); return 0
    if args.preflight_only:
        value = base.preflight_receipt(adr=ADR, input_lock=base.INPUT_LOCK, cm_source=base.CM_SOURCE)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0 if value["status"] == "ready" else 1
    preflight = base.preflight_receipt(adr=ADR, input_lock=base.INPUT_LOCK, cm_source=base.CM_SOURCE)
    if preflight["status"] != "ready":
        raise base.BoundaryError(json.dumps(preflight, ensure_ascii=False))
    public = base._read_json(paths["public"])
    if not (args.resume and paths["seal"].exists()):
        _run_products(public, paths, workers=args.workers, resume=args.resume)
    seal = base.validate_product_seal(paths["seal"], paths["public"], paths["captures"], metadata_only=False)
    scoring = base.open_scoring_fixture(
        paths["scoring"], paths["seal"], paths["public"], paths["captures"],
        input_lock=base.INPUT_LOCK, cm_source=base.CM_SOURCE,
        prevalidated_seal=seal,
    )
    captures = [base._read_json(paths["captures"] / f"{case['case_id']}.json") for case in public["cases"]]
    report = build_report(captures)
    report.update({
        "product_seal_sha256": base._sha256(paths["seal"]),
        "scoring_fixture_sha256": base._sha256(paths["scoring"]),
        "completed_at": base._now(),
    })
    report["artifact_sha256"] = base._self_hash(report, "artifact_sha256")
    base._write_json(paths["run"], report)
    write_ledger(captures, scoring, paths["ledger"])
    print(json.dumps({
        "selected_structure": report["selected_structure"],
        "criteria": report["criteria"],
        "evidence": {arm: {
            key: report["evidence"][arm][key]["groups"]["all"]
            for key in ("presented", "bound", "declared")
        } for arm in ARMS},
        "runtime": report["runtime"],
        "judge_calls": 0,
    }, ensure_ascii=False, indent=2))
    return 0


base.runtime_adapter_contract = runtime_adapter_contract
base.baseline_raw_stage_contract = lambda: runtime_adapter_contract()["baseline_raw_stage_capture"]
base._execute_arm = _execute_arm
base._validate_execution_metrics = _validate_execution_metrics
base._validate_accounting = _validate_accounting
base.execute_product_case = execute_product_case


if __name__ == "__main__":
    raise SystemExit(main())
