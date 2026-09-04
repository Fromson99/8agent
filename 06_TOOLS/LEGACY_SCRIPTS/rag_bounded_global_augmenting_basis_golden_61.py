#!/usr/bin/env python3
"""ADR-0076: bounded global proof-basis augmentation on the frozen 61 cases.

The parent ADR-0073 ``proof-basis-exchange`` arm is replayed byte-for-byte as
the baseline retrieval state.  The candidate is rebuilt from the ADR-0068
pre-greedy projection and is graded only after the selector has returned.
No LLM or provider is called by this runner.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Iterable


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
for _key, _relative in (
    ("STRUCTURE_STORE", "01_DATA/structure"),
    ("STRUCTURE_CUSTOM_DIR", "01_DATA/custom"),
    ("GLOSSARY_STORE", "01_DATA/glossary.json"),
    ("RAG_LINKS_STORE", "01_DATA/links.json"),
    ("RAG_DELEGATION_STORE", "01_DATA/delegation.json"),
):
    os.environ.setdefault(_key, str(ROOT / _relative))

from lawrag.core.rag import proof_basis_augmenting
from scripts import rag_proof_basis_exchange_golden_61 as adr73_runner


ADR_ID = "ADR-0076"
RUN_ID = "run-001"
ARMS = ("baseline", "bounded-global-augmenting-basis")
CAP = 20
POOL_CAP = 96
BUNDLE_MAX = 4

FROZEN = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0064-feedback-explore-golden-61/artifacts/"
    "frozen-cases.json")
FROZEN_SHA256 = (
    "393ced7e9428aea5d6cbc7ed3383fe10dda199da1cc1bf7fcf0fd57edff9b0cb")
PARENT_68_RUN = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0068-recall-first-orthogonal-union/artifacts/"
    "run-001.json")
PARENT_68_RUN_SHA256 = (
    "d751f88febc98a1537083dd5a4e93ebc2cfc40b40137a451fa359badc648d38b")
PARENT_73_MANIFEST = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0073-proof-contribution-basis-exchange/실험/"
    "manifest.json")
PARENT_73_MANIFEST_SHA256 = (
    "21ca70dc6bcf8dfdee130c9f58bd71f891c8a0010a2aed13c2c40b22bc0098c6")
PARENT_73_RUN = (
    ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0073-proof-contribution-basis-exchange/artifacts/"
    "run-001.json")
PARENT_73_RUN_SHA256 = (
    "a277eab6190f95476d9cc9b88b4881c5d6c9947dceefb59fa843ceddf3dc6904")

IMPLEMENTATIONS = (
    Path(__import__("lawrag").__file__).resolve().parent / "core/rag/proof_basis_augmenting.py",
    Path(__import__("lawrag").__file__).resolve().parent / "core/rag/proof_basis_exchange.py",
    Path(__import__("lawrag").__file__).resolve().parent / "core/rag/grounded_witness.py",
    Path(__import__("lawrag").__file__).resolve().parent / "core/rag/legal_coordinates.py",
    Path(__import__("lawrag").__file__).resolve().parent / "core/rag/relations.py",
)

_BANNED_PRODUCT_KEYS = frozenset({
    "gold_results", "paired", "expected_articles", "reference_answer",
    "case_all_gold_hit", "case_all_gold_internal_pool_hit",
})


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1,
                max(0, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def _zero_usage() -> dict:
    return {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "duration_ms": 0,
        "errors": 0,
    }


def _contains_banned_key(value: object) -> bool:
    if isinstance(value, dict):
        return bool(set(value) & _BANNED_PRODUCT_KEYS) or any(
            _contains_banned_key(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_banned_key(item) for item in value)
    return False


def safe_projection(parent_68_row: dict) -> dict:
    """Return only the ADR-0068 fields permitted to reach the selector."""

    value = adr73_runner.safe_projection(parent_68_row)
    expected = {
        "number", "case_id", "suite", "question", "terms",
        "baseline_core", "incumbent", "evidence_pool", "cap", "pool_cap",
    }
    if set(value) != expected:
        raise AssertionError("ADR-0068 projection contract changed")
    if value["cap"] != CAP or value["pool_cap"] != POOL_CAP:
        raise AssertionError("presentation bounds changed")
    if _contains_banned_key(value):
        raise AssertionError("gold field crossed the selector boundary")
    return deepcopy(value)


def _load_sources() -> tuple[dict, dict, dict]:
    expected = (
        (FROZEN, FROZEN_SHA256),
        (PARENT_68_RUN, PARENT_68_RUN_SHA256),
        (PARENT_73_MANIFEST, PARENT_73_MANIFEST_SHA256),
        (PARENT_73_RUN, PARENT_73_RUN_SHA256),
    )
    for path, digest in expected:
        actual = _sha(path)
        if actual != digest:
            raise ValueError(f"frozen source hash mismatch: {path}: {actual}")

    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    parent_68 = json.loads(PARENT_68_RUN.read_text(encoding="utf-8"))
    parent_73 = json.loads(PARENT_73_RUN.read_text(encoding="utf-8"))
    if any(len(value.get("cases" if name == "frozen" else "rows") or ()) != 61
           for name, value in (
               ("frozen", frozen), ("parent_68", parent_68),
               ("parent_73", parent_73))):
        raise ValueError("ADR-0076 requires the exact frozen 61-case lineage")
    if (parent_73.get("source_lineage") or {}).get(
            "parent_68_run_sha256") != PARENT_68_RUN_SHA256:
        raise ValueError("ADR-0073 artifact does not descend from frozen ADR-0068")
    return frozen, parent_68, parent_73


def _validate_adr_manifest(adr: Path, *, require_frozen: bool) -> dict:
    manifest_path = adr / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("adr_id") != ADR_ID:
        raise ValueError(f"expected {ADR_ID} manifest")
    parents = (manifest.get("lineage") or {}).get("parents") or []
    actual_parents = {
        (row.get("experiment_id"), row.get("arm_id")):
            (row.get("relation"), row.get("manifest_sha256"))
        for row in parents
    }
    expected_parents = {
        ("ADR-0073-experiment-v1", "proof-basis-exchange"):
            ("forked_from", PARENT_73_MANIFEST_SHA256),
    }
    if actual_parents != expected_parents:
        raise ValueError("ADR-0076 parent lineage mismatch")

    arm_ids = {row.get("id") for row in
               (manifest.get("design") or {}).get("arms") or ()}
    if arm_ids != set(ARMS):
        raise ValueError("ADR-0076 arm mismatch")
    if (manifest.get("llm_policy") or {}).get("llm_calls") != []:
        raise ValueError("ADR-0076 performs no LLM calls")
    if len(manifest.get("questions") or ()) != 61:
        raise ValueError("ADR-0076 must freeze 61 questions")

    dataset = manifest.get("dataset") or {}
    if (dataset.get("sha256") != FROZEN_SHA256
            or dataset.get("pool_source_sha256") != PARENT_68_RUN_SHA256
            or dataset.get("parent_manifest_sha256")
            != PARENT_73_MANIFEST_SHA256
            or dataset.get("parent_run_sha256") != PARENT_73_RUN_SHA256):
        raise ValueError("ADR-0076 dataset lineage mismatch")

    run = next((row for row in manifest.get("runs") or ()
                if row.get("id") == RUN_ID), None)
    if not run or set(run.get("arm_ids") or ()) != set(ARMS):
        raise ValueError("ADR-0076 run/arm contract mismatch")
    if require_frozen:
        if not (manifest.get("design") or {}).get(
                "criteria_frozen_before_run"):
            raise ValueError("criteria must be frozen before run")
        if run.get("status") not in {"planned", "running"}:
            raise ValueError("run-001 must be planned or running")
        if run.get("runner_sha256") != _sha(Path(__file__).resolve()):
            raise ValueError("runner SHA is not frozen")
        expected_hashes = run.get("implementation_sha256") or {}
        for path in IMPLEMENTATIONS:
            relative = str(path.relative_to(ROOT))
            if expected_hashes.get(relative) != _sha(path):
                raise ValueError(
                    f"implementation SHA is not frozen: {relative}")
    return manifest


def _restore(index, values: list[dict], terms: tuple[str, ...], *,
             origin: str):
    return adr73_runner._restore(index, values, terms, origin=origin)


def _selected(rows: Iterable) -> list[dict]:
    return adr73_runner._selected(list(rows))


def _pool(rows: Iterable) -> list[dict]:
    return adr73_runner._pool(list(rows))


def _grade(case: dict, selected: list[dict], pool: list[dict]):
    """Post-selection exact grader; this is the only gold-reading function."""

    return adr73_runner._grade(case, selected, pool)


def _paired(left: dict, right: dict) -> dict:
    return adr73_runner._paired(left, right)


def _baseline_arm(case: dict, parent_73_arm: dict) -> dict:
    """Exact replay of ADR-0073's completed proof-basis-exchange arm."""

    selected = deepcopy(parent_73_arm.get("selected") or [])
    pool = deepcopy(parent_73_arm.get("internal_pool") or [])
    gold, all_hit, pool_all_hit = _grade(case, selected, pool)
    stored = [
        (row.get("doc_id"), row.get("node"), row.get("scorable"),
         row.get("hit"), row.get("rank"), row.get("internal_pool_hit"),
         row.get("internal_pool_rank"))
        for row in parent_73_arm.get("gold_results") or ()
    ]
    actual = [
        (row.get("doc_id"), row.get("node"), row.get("scorable"),
         row.get("hit"), row.get("rank"), row.get("internal_pool_hit"),
         row.get("internal_pool_rank"))
        for row in gold
    ]
    if stored != actual:
        raise ValueError(f"{case['id']}: ADR-0073 grading replay mismatch")
    if (all_hit != parent_73_arm.get("case_all_gold_hit")
            or pool_all_hit
            != parent_73_arm.get("case_all_gold_internal_pool_hit")):
        raise ValueError(f"{case['id']}: ADR-0073 case replay mismatch")

    value = deepcopy(parent_73_arm)
    value.update({
        "arm": "baseline",
        "replay_of": "ADR-0073/run-001/proof-basis-exchange",
        "parent_arm_state_sha256": _json_sha(parent_73_arm),
        "selected": selected,
        "selected_count": len(selected),
        "internal_pool": pool,
        "internal_pool_count": len(pool),
        "gold_results": gold,
        "case_all_gold_hit": all_hit,
        "case_all_gold_internal_pool_hit": pool_all_hit,
    })
    return value


def _select_candidate(index, projection: dict) -> dict:
    """Run the selector without access to a case, gold, reference, or pair."""

    if _contains_banned_key(projection):
        raise AssertionError("gold field crossed the selector boundary")
    terms = tuple(str(value) for value in projection.get("terms") or ())
    incumbent = _restore(
        index, projection["incumbent"], terms, origin="ADR-0068-selected")
    pool_rows = _restore(
        index, projection["evidence_pool"], terms, origin="ADR-0068-pool")
    core = _restore(
        index, projection["baseline_core"], terms,
        origin="ADR-0068-baseline-core")
    started = time.perf_counter()
    runtime_error = ""
    try:
        selected_rows, meta = proof_basis_augmenting.run(
            index,
            str(projection.get("question") or ""),
            incumbent,
            pool_rows,
            core,
            cap=CAP,
            bundle_max=BUNDLE_MAX,
        )
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
        selected_rows = incumbent
        meta = {
            "enabled": True,
            "ran": True,
            "status": "error",
            "reason": "runtime_error",
            "runtime_error": runtime_error,
            "registry_errors": [runtime_error],
            "canonical_source_witnesses_valid": False,
            "canonical_pool_preserved": False,
            "selected_subset_of_pool": False,
            "componentwise_non_decreasing": False,
            "unique_witness_losses": [],
            "typed_edge_receipts_validated": False,
            "selected_addition_closure_validated": False,
            "actions": [],
            "promoted": [],
            "evicted": [],
            "candidate_audit": {
                "admissible_candidate_ids": [],
                "hard_candidate_pretruncated_ids": [],
                "evaluated_or_structurally_screened_ids": [],
                "candidate_enumeration_complete": False,
                "ngram_only_admissions": [],
            },
            "gold_fields_received": False,
            "llm_calls": 0,
        }
    wall_ms = (time.perf_counter() - started) * 1000
    canonical_pool, pool_errors = proof_basis_augmenting.canonicalize(
        index, pool_rows)
    if pool_errors:
        meta.setdefault("registry_errors", []).extend(pool_errors)
    return {
        "selected_rows": selected_rows,
        "pool_rows": canonical_pool,
        "meta": meta,
        "wall_ms": round(wall_ms, 3),
        "runtime_error": runtime_error,
    }


def _grade_candidate(case: dict, raw: dict) -> dict:
    selected = _selected(raw["selected_rows"])
    pool = _pool(raw["pool_rows"])
    gold, all_hit, pool_all_hit = _grade(case, selected, pool)
    return {
        "arm": "bounded-global-augmenting-basis",
        "source": "ADR-0068 pre-greedy projection / ADR-0076 global solver",
        "selected": selected,
        "selected_count": len(selected),
        "internal_pool": pool,
        "internal_pool_count": len(pool),
        "gold_results": gold,
        "case_all_gold_hit": all_hit,
        "case_all_gold_internal_pool_hit": pool_all_hit,
        "retrieval_meta": raw["meta"],
        "llm_calls": [],
        "provider_usage": _zero_usage(),
        "incremental_provider_usage": _zero_usage(),
        "wall_ms": raw["wall_ms"],
        "runtime_error": raw["runtime_error"],
    }


def _arm_summary(rows: list[dict], arm: str, corpus: int) -> dict:
    return adr73_runner._arm_summary(rows, arm, corpus)


def _comparison(rows: list[dict], left: str, right: str) -> dict:
    return adr73_runner._comparison(rows, left, right)


def _summary(rows: list[dict], corpus: int) -> dict:
    arms = {arm: _arm_summary(rows, arm, corpus) for arm in ARMS}
    comparison = _comparison(rows, *ARMS)
    candidate_values = [row["arms"][ARMS[1]] for row in rows]
    metas = [value["retrieval_meta"] for value in candidate_values]
    actions = [action for meta in metas for action in meta.get("actions") or ()]
    additions_per_case = [
        sum(len(action.get("added") or ())
            for action in meta.get("actions") or ())
        for meta in metas
    ]
    evictions_per_case = [
        sum(len(action.get("evicted") or ())
            for action in meta.get("actions") or ())
        for meta in metas
    ]
    audits = [meta.get("candidate_audit") or {} for meta in metas]
    def audit_complete(audit: dict) -> bool:
        admissible = set(audit.get("admissible_candidate_ids") or ())
        accounted = set(
            audit.get("evaluated_or_structurally_screened_ids") or ())
        ledger = audit.get("candidate_evaluations") or {}
        search = audit.get("search_accounting") or {}
        if (audit.get("candidate_enumeration_complete") is not True
                or accounted != admissible or set(ledger) != admissible):
            return False
        if (search.get("evaluated_partition_complete") is not True
                or search.get("minimum_frontier_partition_complete") is not True
                or search.get("pruning_receipts_complete") is not True
                or int(search.get("evaluated_bundles") or 0) != (
                    int(search.get("feasible_bundles") or 0)
                    + int(search.get("closure_screened_bundles") or 0)
                    + int(search.get("dominance_screened_bundles") or 0))
                or int(search.get("minimum_eviction_frontier_bundles") or 0)
                != (int(search.get("evaluated_bundles") or 0)
                    + int(search.get("objective_bound_bundles_screened") or 0))):
            return False
        pruning_rules = {
            row.get("rule") for row in search.get("pruning_receipts") or ()
        }
        for candidate_id, value in ledger.items():
            if value.get("status") == "evaluated":
                if int(value.get("evaluated_bundle_count") or 0) <= 0:
                    return False
            elif value.get("status") == "structurally_screened":
                if not value.get("screen_reasons"):
                    return False
                for reason in value["screen_reasons"]:
                    if (reason == "lexicographic_floor_upper_bound"
                            and reason not in pruning_rules):
                        return False
                    if (reason == (
                            "no_feasible_bundle_within_cap_radius_or_"
                            "protected_frontier")
                            and int(search.get(
                                "max_additions_after_exact_locks") or 0) != 0):
                        return False
            else:
                return False
        return True

    enumeration_complete = all(audit_complete(audit) for audit in audits)
    search_accounting_valid = all(
        (audit.get("search_accounting") or {}).get(
            "evaluated_partition_complete") is True
        and (audit.get("search_accounting") or {}).get(
            "minimum_frontier_partition_complete") is True
        and (audit.get("search_accounting") or {}).get(
            "pruning_receipts_complete") is True
        for audit in audits
    )
    typed_edges_valid = all(
        meta.get("typed_edge_receipts_validated") is True
        and meta.get("selected_addition_closure_validated") is True
        for meta in metas
    ) and all(
        edge.get("edge_id") and edge.get("kind")
        and edge.get("dependency_class")
        for meta in metas
        for receipt in meta.get("selected_receipts") or ()
        for edge in receipt.get("edges") or ()
    )
    criteria = {
        "frozen_cases_exact_61": len(rows) == 61,
        "scorable_cases_exact_60": all(
            arms[arm]["scorable_cases"] == 60 for arm in ARMS),
        "gold_article_instances_exact_83": all(
            arms[arm]["gold_article_instances"] == 83 for arm in ARMS),
        "baseline_gold_hits_exact_66": (
            arms["baseline"]["gold_article_hits"] == 66),
        "baseline_all_gold_cases_exact_46": (
            arms["baseline"]["case_all_gold_hits"] == 46),
        "baseline_pool_gold_hits_exact_68": (
            arms["baseline"]["internal_pool_gold_hits"] == 68),
        "candidate_gold_hits_at_least_68": (
            arms[ARMS[1]]["gold_article_hits"] >= 68),
        "candidate_all_gold_cases_at_least_48": (
            arms[ARMS[1]]["case_all_gold_hits"] >= 48),
        "baseline_article_regression_zero": (
            comparison["baseline_only_articles"] == 0),
        "baseline_case_regression_zero": (
            comparison["baseline_only_cases"] == 0),
        "canonical_pool_gold_ceiling_preserved": (
            arms[ARMS[1]]["internal_pool_gold_hits"] == 68),
        "selected_cap_20": all(
            row["arms"][arm]["selected_count"] <= CAP
            for row in rows for arm in ARMS),
        "selected_subset_of_pool": all(
            meta.get("selected_subset_of_pool") is True for meta in metas),
        "canonical_pool_preserved": all(
            meta.get("canonical_pool_preserved") is True for meta in metas),
        "canonical_source_witnesses_valid": all(
            meta.get("canonical_source_witnesses_valid") is True
            for meta in metas),
        "typed_edge_receipts_valid": typed_edges_valid,
        "componentwise_non_decreasing": all(
            meta.get("componentwise_non_decreasing") is True
            and not meta.get("unique_witness_losses") for meta in metas),
        "bundle_additions_at_most_4": all(
            count <= BUNDLE_MAX for count in additions_per_case),
        "bundle_evictions_at_most_4": all(
            count <= BUNDLE_MAX for count in evictions_per_case),
        "hard_candidate_pretruncation_zero": all(
            not audit.get("hard_candidate_pretruncated_ids")
            for audit in audits),
        "candidate_enumeration_complete": enumeration_complete,
        "search_accounting_invariants_valid": search_accounting_valid,
        "incomplete_ngram_only_admission_zero": all(
            not audit.get("ngram_only_admissions") for audit in audits),
        "gold_boundary_clean": all(
            meta.get("gold_fields_received") is False for meta in metas),
        "runtime_and_registry_errors_zero": all(
            not value.get("runtime_error") and not meta.get("registry_errors")
            for value, meta in zip(candidate_values, metas)),
        "llm_calls_zero": all(meta.get("llm_calls") == 0 for meta in metas),
        "solver_latency_p95_at_most_1000ms": (
            arms[ARMS[1]]["wall_ms_p95"] <= 1000),
    }
    return {
        "cases": len(rows),
        "corpus_article_roots": corpus,
        "arms": arms,
        "comparisons": [comparison],
        "augmenting_accounting": {
            "actions": len(actions),
            "additions": sum(additions_per_case),
            "evictions": sum(evictions_per_case),
            "evaluated_bundles": sum(
                int((audit.get("search_accounting") or {}).get(
                    "evaluated_bundles") or 0)
                for audit in audits),
            "feasible_bundles": sum(
                int((audit.get("search_accounting") or {}).get(
                    "feasible_bundles") or 0)
                for audit in audits),
            "closure_screened_bundles": sum(
                int((audit.get("search_accounting") or {}).get(
                    "closure_screened_bundles") or 0)
                for audit in audits),
            "dominance_screened_bundles": sum(
                int((audit.get("search_accounting") or {}).get(
                    "dominance_screened_bundles") or 0)
                for audit in audits),
            "objective_bound_bundles_screened": sum(
                int((audit.get("search_accounting") or {}).get(
                    "objective_bound_bundles_screened") or 0)
                for audit in audits),
            "extra_eviction_bundles_screened": sum(
                int((audit.get("search_accounting") or {}).get(
                    "extra_eviction_bundles_screened") or 0)
                for audit in audits),
            "admissible_candidates": sum(
                len(audit.get("admissible_candidate_ids") or ())
                for audit in audits),
            "canonical_source_receipts": sum(
                len(meta.get("selected_receipts") or ()) for meta in metas),
            "lost_cells": sum(
                len(action.get("lost_cells") or ()) for action in actions),
            "ngram_only_admissions": sum(
                len(audit.get("ngram_only_admissions") or ())
                for audit in audits),
            "llm_calls": 0,
        },
        "criteria": criteria,
        "target_pass": bool(rows) and all(criteria.values()),
    }


def _bundle_preflight_counts(*, pool_count: int, incumbent_count: int,
                             selected_floor_count: int,
                             protected_selected_count: int | None = None,
                             cap: int = CAP,
                             bundle_max: int = BUNDLE_MAX) -> dict:
    """Count a structural superset of bundles without running the solver.

    Every non-incumbent pool coordinate is treated as potentially admissible.
    The count is therefore a deterministic upper bound, not an effectiveness
    result.  It mirrors the solver's minimum-eviction frontier.
    """

    if protected_selected_count is None:
        protected_selected_count = selected_floor_count
    if not (0 <= selected_floor_count <= protected_selected_count
            <= incumbent_count <= pool_count):
        raise ValueError("invalid canonical preflight counts")
    if incumbent_count > cap:
        raise ValueError("incumbent exceeds presentation cap")
    eligible_upper = pool_count - incumbent_count
    evictable_upper = incumbent_count - protected_selected_count
    vacancies = cap - incumbent_count
    max_additions = min(
        bundle_max, eligible_upper,
        vacancies + min(bundle_max, evictable_upper),
    )
    by_additions: dict[str, dict] = {}
    total = 0
    for addition_count in range(1, max_additions + 1):
        eviction_count = max(
            0, incumbent_count + addition_count - cap)
        if (eviction_count > bundle_max
                or eviction_count > evictable_upper):
            continue
        combinations = (
            math.comb(eligible_upper, addition_count)
            * math.comb(evictable_upper, eviction_count)
        )
        by_additions[str(addition_count)] = {
            "evictions": eviction_count,
            "structural_bundle_upper_bound": combinations,
        }
        total += combinations
    return {
        "canonical_pool": pool_count,
        "canonical_incumbent": incumbent_count,
        "selected_floor": selected_floor_count,
        "protected_selected": protected_selected_count,
        "nonincumbent_ground": eligible_upper,
        "evictable_upper_bound": evictable_upper,
        "max_additions": max_additions,
        "by_additions": by_additions,
        "structural_bundle_upper_bound": total,
    }


def _preflight_projection(index, projection: dict) -> dict:
    terms = tuple(str(value) for value in projection.get("terms") or ())
    pool = _restore(
        index, projection["evidence_pool"], terms, origin="validate-pool")
    incumbent = _restore(
        index, projection["incumbent"], terms, origin="validate-incumbent")
    core = _restore(
        index, projection["baseline_core"], terms, origin="validate-core")
    pool_coordinates = {row.coordinate for row in pool}
    incumbent_coordinates = {row.coordinate for row in incumbent}
    core_coordinates = {row.coordinate for row in core}
    if not incumbent_coordinates <= pool_coordinates:
        raise ValueError(
            f"{projection['case_id']}: incumbent is outside canonical pool")
    selected_floor = len(incumbent_coordinates & core_coordinates)
    value = _bundle_preflight_counts(
        pool_count=len(pool_coordinates),
        incumbent_count=len(incumbent_coordinates),
        selected_floor_count=selected_floor,
    )
    records, registry_errors = proof_basis_augmenting.build_registry(
        index, str(projection.get("question") or ""), pool)
    registry = {record.coordinate: record for record in records}
    selected_records = [registry[coordinate]
                        for coordinate in incumbent_coordinates
                        if coordinate in registry]
    floor_coordinates = core_coordinates & set(registry)
    selected_coordinates = {record.coordinate for record in selected_records}
    admissible = [
        record for record in records
        if record.coordinate not in selected_coordinates
        and proof_basis_augmenting._candidate_reasons(
            record, registry, selected_coordinates, floor_coordinates)
    ]
    before = proof_basis_augmenting._span_lattice(
        selected_records, floor_coordinates)
    edge_protections = proof_basis_augmenting._edge_eviction_protections(
        selected_records, before)
    static_protections = proof_basis_augmenting._static_eviction_protections(
        selected_records, admissible, before)
    protected_coordinates = (
        (selected_coordinates & floor_coordinates)
        | set(edge_protections) | set(static_protections)
    )
    admissible_upper = _bundle_preflight_counts(
        pool_count=len(selected_records) + len(admissible),
        incumbent_count=len(selected_records),
        selected_floor_count=len(selected_coordinates & floor_coordinates),
        protected_selected_count=len(protected_coordinates),
    )
    value["case_id"] = projection["case_id"]
    value["canonical_core"] = len(core_coordinates)
    value["admissible_candidates"] = len(admissible)
    value["admissible_bundle_upper_bound"] = (
        admissible_upper["structural_bundle_upper_bound"])
    value["edge_protected_incumbent"] = len(edge_protections)
    value["static_protected_incumbent"] = len(static_protections)
    value["protected_incumbent"] = len(protected_coordinates)
    value["evictable_after_exact_locks"] = (
        len(selected_records) - len(protected_coordinates))
    value["registry_errors"] = registry_errors
    return value


def _validate_only_report(index, projections: list[dict], *, corpus: int) -> dict:
    """Validate coordinates and count bundle upper bounds; never select/grade."""

    cases = [_preflight_projection(index, projection)
             for projection in projections]
    return {
        "valid": True,
        "cases": len(cases),
        "corpus_article_roots": corpus,
        "raw_parent_pool_coordinates": sum(
            len(projection["evidence_pool"]) for projection in projections),
        "canonical_parent_pool_coordinates": sum(
            value["canonical_pool"] for value in cases),
        "canonical_incumbent_coordinates": sum(
            value["canonical_incumbent"] for value in cases),
        "canonical_core_coordinates": sum(
            value["canonical_core"] for value in cases),
        "nonincumbent_ground_coordinates": sum(
            value["nonincumbent_ground"] for value in cases),
        "structural_bundle_upper_bound_total": sum(
            value["structural_bundle_upper_bound"] for value in cases),
        "structural_bundle_upper_bound_max_case": max(
            (value["structural_bundle_upper_bound"] for value in cases),
            default=0),
        "admissible_candidates": sum(
            value.get("admissible_candidates", 0) for value in cases),
        "admissible_bundle_upper_bound_total": sum(
            value.get("admissible_bundle_upper_bound", 0) for value in cases),
        "admissible_bundle_upper_bound_max_case": max(
            (value.get("admissible_bundle_upper_bound", 0)
             for value in cases), default=0),
        "edge_protected_incumbent_coordinates": sum(
            value.get("edge_protected_incumbent", 0) for value in cases),
        "static_protected_incumbent_coordinates": sum(
            value.get("static_protected_incumbent", 0) for value in cases),
        "evictable_after_exact_locks_max_case": max(
            (value.get("evictable_after_exact_locks", 0)
             for value in cases), default=0),
        "registry_errors": [
            {"case_id": value["case_id"], "errors": value["registry_errors"]}
            for value in cases if value.get("registry_errors")
        ],
        "preflight_by_case": cases,
        "solver_calls": 0,
        "grader_calls": 0,
        "llm_calls": 0,
    }


def _question_markdown(case: dict, row: dict, projection: dict,
                       *, corpus: int) -> str:
    baseline = row["arms"]["baseline"]
    candidate = row["arms"][ARMS[1]]
    paired = row["paired"][f"baseline__{ARMS[1]}"]
    failure = (
        "other/runtime_or_timeout" if candidate.get("runtime_error") else
        "retrieval_miss" if candidate.get("case_all_gold_hit") is False else
        "없음"
    )
    grader_input = {
        "expected_articles": case.get("expected_articles") or [],
        "reference_answer": case.get("reference_answer") or "",
    }
    grader_output = {
        arm: row["arms"][arm]["gold_results"] for arm in ARMS
    }
    selector_output = {
        "selected": candidate["selected"],
        "retrieval_meta": candidate["retrieval_meta"],
        "runtime_error": candidate.get("runtime_error") or "",
        "usage": candidate["provider_usage"],
        "wall_ms": candidate["wall_ms"],
    }
    return f"""# ADR-0076 질문 {case['number']:03d}: {case['id']}

## 1. 실행 메타

- case ID: `{case['id']}`
- run ID: `{RUN_ID}`
- arms: `baseline`, `{ARMS[1]}`
- 실행 시각: `{row['executed_at']}`
- 원본 상태: ADR-0073 run `{PARENT_73_RUN_SHA256}` exact replay
- 모델: 해당 없음 (결정론 selector와 exact grader, LLM 0)

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

{case.get('reference_answer') or '(기준답변 없음)'}

```json
{json.dumps(case.get('expected_articles') or [], ensure_ascii=False, indent=2)}
```

## 4. 제품 입력을 구성한 원값

`gold_results`, `paired`, `expected_articles`, `reference_answer`는 selector 입력에 없다.

```json
{json.dumps({'corpus_total': corpus, 'projection': projection}, ensure_ascii=False, indent=2)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

LLM/provider 호출은 없다. baseline은 부모 artifact exact replay이고 candidate는 아래
whitelist projection에 대한 서버 결정론 출력이다.

### baseline structured output

```json
{json.dumps({'selected': baseline['selected'], 'retrieval_meta': baseline['retrieval_meta'], 'usage': baseline.get('provider_usage'), 'wall_ms': baseline.get('wall_ms')}, ensure_ascii=False, indent=2)}
```

### {ARMS[1]} structured output

```json
{json.dumps(selector_output, ensure_ascii=False, indent=2)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

```json
[]
```

## 7. 채점 호출과 반복 판정

LLM judge 호출은 없다. 선택 완료 뒤 exact canonical article coordinate grader만
다음 채점 전용 입력을 읽었다.

### exact grader input

```json
{json.dumps(grader_input, ensure_ascii=False, indent=2)}
```

### exact grader output

```json
{json.dumps(grader_output, ensure_ascii=False, indent=2)}
```

## 8. 사례 최종 판정

| run | arm | all-gold | gold hit | runtime error |
|---|---|---:|---:|---|
| {RUN_ID} | baseline | {baseline['case_all_gold_hit']} | {sum(bool(value['hit']) for value in baseline['gold_results'] if value['scorable'])} | {baseline.get('runtime_error') or '없음'} |
| {RUN_ID} | {ARMS[1]} | {candidate['case_all_gold_hit']} | {sum(bool(value['hit']) for value in candidate['gold_results'] if value['scorable'])} | {candidate.get('runtime_error') or '없음'} |

- paired 분류: `{paired['case_all_gold']}`
- 신규 정답 article: `{sum(value['status'] == 'candidate_only' for value in paired['selected_articles'])}`
- 회귀 article: `{sum(value['status'] == 'baseline_only' for value in paired['selected_articles'])}`
- 실패 유형: `{failure}`
"""


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _atomic_save(path: Path, value: dict) -> None:
    _atomic_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def _artifact(rows: list[dict], corpus: int) -> dict:
    return {
        "schema_version": "bounded-global-augmenting-basis-golden-61-run-v1",
        "adr_id": ADR_ID,
        "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_lineage": {
            "frozen_path": str(FROZEN.relative_to(ROOT)),
            "frozen_sha256": FROZEN_SHA256,
            "parent_68_run_path": str(PARENT_68_RUN.relative_to(ROOT)),
            "parent_68_run_sha256": PARENT_68_RUN_SHA256,
            "parent_73_manifest_path": str(
                PARENT_73_MANIFEST.relative_to(ROOT)),
            "parent_73_manifest_sha256": PARENT_73_MANIFEST_SHA256,
            "parent_73_run_path": str(PARENT_73_RUN.relative_to(ROOT)),
            "parent_73_run_sha256": PARENT_73_RUN_SHA256,
        },
        "runner": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": _sha(Path(__file__).resolve()),
        "implementation_sha256": {
            str(path.relative_to(ROOT)): _sha(path)
            for path in IMPLEMENTATIONS
        },
        "model_policy": {
            "llm_calls": [],
            "judge": None,
            "deterministic_grader": "exact canonical article coordinate",
        },
        "contract": {
            "selected_cap": CAP,
            "parent_pool_cap": POOL_CAP,
            "bundle_max_additions": BUNDLE_MAX,
            "bundle_max_evictions": BUNDLE_MAX,
            "hard_candidate_pretruncation": False,
            "incomplete_ngram_only_admission": False,
            "direct_admission_proxy": (
                "same saved span full query-token string plus "
                "question-matched legal-role regex"),
            "article_root_normalization": True,
            "server_owned_span_ids": True,
            "typed_edge_ids": True,
            "gold_hidden_from_selector": True,
        },
        "summary": _summary(rows, corpus),
        "rows": rows,
    }


def _validate_resume(blob: dict, projections: list[dict]) -> list[dict]:
    if blob.get("schema_version") != (
            "bounded-global-augmenting-basis-golden-61-run-v1"):
        raise ValueError("resume artifact schema mismatch")
    if blob.get("adr_id") != ADR_ID or blob.get("run_id") != RUN_ID:
        raise ValueError("resume ADR/run mismatch")
    if blob.get("runner_sha256") != _sha(Path(__file__).resolve()):
        raise ValueError("resume runner SHA mismatch")
    expected_impl = {
        str(path.relative_to(ROOT)): _sha(path) for path in IMPLEMENTATIONS}
    if blob.get("implementation_sha256") != expected_impl:
        raise ValueError("resume implementation SHA mismatch")
    lineage = blob.get("source_lineage") or {}
    if (lineage.get("frozen_sha256") != FROZEN_SHA256
            or lineage.get("parent_68_run_sha256")
            != PARENT_68_RUN_SHA256
            or lineage.get("parent_73_manifest_sha256")
            != PARENT_73_MANIFEST_SHA256
            or lineage.get("parent_73_run_sha256")
            != PARENT_73_RUN_SHA256):
        raise ValueError("resume source lineage mismatch")
    rows = list(blob.get("rows") or ())
    if len(rows) > len(projections):
        raise ValueError("resume artifact has too many rows")
    ids = [row.get("case_id") for row in rows]
    expected_ids = [row["case_id"] for row in projections[:len(rows)]]
    if ids != expected_ids or len(ids) != len(set(ids)):
        raise ValueError("resume rows are not an exact frozen prefix")
    for row, projection in zip(rows, projections):
        if row.get("input_state_sha256") != _json_sha(projection):
            raise ValueError(f"resume input mismatch: {row.get('case_id')}")
    return rows


def _article_roots(index) -> int:
    return adr73_runner._article_roots(index)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adr", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    adr = args.adr if args.adr.is_absolute() else ROOT / args.adr
    out = args.out or adr / "artifacts/run-001.json"
    out = out if out.is_absolute() else ROOT / out
    frozen, parent_68, parent_73 = _load_sources()
    _validate_adr_manifest(adr, require_frozen=not args.validate_only)

    from lawrag.core.rag import index as index_mod
    index = index_mod.current().scoped(None)
    corpus = _article_roots(index)
    parent_68_by_case = {row["case_id"]: row for row in parent_68["rows"]}
    parent_73_by_case = {row["case_id"]: row for row in parent_73["rows"]}
    projections: list[dict] = []
    for case in frozen["cases"]:
        row_68 = parent_68_by_case.get(case["id"])
        row_73 = parent_73_by_case.get(case["id"])
        if (row_68 is None or row_73 is None
                or row_68.get("question") != case["question"]
                or row_73.get("question") != case["question"]):
            raise ValueError(f"parent case mismatch: {case['id']}")
        projections.append(safe_projection(row_68))

    if args.validate_only:
        print(json.dumps(
            _validate_only_report(index, projections, corpus=corpus),
            ensure_ascii=False,
            indent=2,
        ))
        return 0

    if out.exists() and not args.resume:
        raise FileExistsError(
            "refusing to overwrite completed/partial artifact without "
            f"--resume: {out}")
    rows: list[dict] = []
    if args.resume and out.exists():
        rows = _validate_resume(
            json.loads(out.read_text(encoding="utf-8")), projections)
    completed = {row["case_id"] for row in rows}

    for case, projection in zip(frozen["cases"], projections):
        if case["id"] in completed:
            continue
        parent_73_row = parent_73_by_case[case["id"]]
        baseline = _baseline_arm(
            case, parent_73_row["arms"]["proof-basis-exchange"])
        candidate_raw = _select_candidate(index, projection)
        candidate = _grade_candidate(case, candidate_raw)
        arms = {"baseline": baseline, ARMS[1]: candidate}
        pair_key = f"baseline__{ARMS[1]}"
        row = {
            "number": case["number"],
            "case_id": case["id"],
            "suite": case["suite"],
            "question": case["question"],
            "executed_at": datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"),
            "input_state_sha256": _json_sha(projection),
            "product_input_keys": sorted(projection),
            "arms": arms,
            "paired": {pair_key: _paired(baseline, candidate)},
        }
        question_path = adr / "실험" / (
            f"질문-{case['number']:03d}-{case['id']}.md")
        _atomic_text(
            question_path,
            _question_markdown(case, row, projection, corpus=corpus),
        )
        rows.append(row)
        rows.sort(key=lambda value: value["number"])
        _atomic_save(out, _artifact(rows, corpus))
        hits = {
            arm: sum(bool(gold["hit"])
                     for gold in arms[arm]["gold_results"]
                     if gold["scorable"])
            for arm in ARMS
        }
        actions = candidate["retrieval_meta"].get("actions") or []
        evaluated = sum(
            int(action.get("evaluated_bundles") or 0) for action in actions)
        print(
            f"[{case['number']:02d}/61] {case['id']} "
            f"baseline={hits['baseline']} candidate={hits[ARMS[1]]} "
            f"selected={candidate['selected_count']} "
            f"evaluated={evaluated} "
            f"status={candidate['retrieval_meta'].get('status')}",
            flush=True,
        )

    print(json.dumps(_summary(rows, corpus), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
