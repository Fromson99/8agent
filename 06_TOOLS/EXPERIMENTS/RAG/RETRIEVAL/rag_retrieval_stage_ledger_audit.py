#!/usr/bin/env python3
"""Backfill a retrieval-stage recall ledger from frozen ADR-0068/0076 data.

This is an offline audit runner.  It never calls the product retriever, an
LLM, or a provider.  Candidate snapshots are captured first without gold;
the frozen gold coordinates are joined only after every capture exists.

The frozen artifacts do not contain candidate-level membership after the
bundle closure/dominance screens.  Consequently this runner records the
exact evaluated-union and exact winning-union boundaries, but labels the
internal feasibility-versus-objective attribution as incomplete.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable, Mapping, Sequence

from workspace_paths import resolve_stored_path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.runtime.retrieval_stage_ledger import (  # noqa: E402
    StageLedgerRecorder,
    build_experiment_artifact,
    build_run_artifact,
    grade_capture,
    validate_capture,
    validate_graded_ledger,
)


ADR_ID = "ADR-0081"
EXPERIMENT_ID = "ADR-0081-experiment-v1"
RUN_ID = "run-001"
CANDIDATE_ARM = "stage-ledger-v1"
BASELINE_ARM = "baseline"

ADR_DIR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0081-retrieval-stage-recall-discard-ledger"
MANIFEST = ADR_DIR / "실험/manifest.json"
OUTPUT = ADR_DIR / "artifacts/run-001.json"

ADR76_RUN_STORED = "docs/adr/ADR-0076-bounded-global-augmenting-basis/artifacts/run-001.json"
ADR76_RUN = resolve_stored_path(ROOT, ADR76_RUN_STORED)
ADR76_RUN_SHA256 = (
    "8d954148b47c16976c24907f311ba0490f59005a54a9aa933fea1ef0ea63ffd5"
)
ADR68_RUN_STORED = "docs/adr/ADR-0068-recall-first-orthogonal-union/artifacts/run-001.json"
ADR68_RUN = resolve_stored_path(ROOT, ADR68_RUN_STORED)
ADR68_RUN_SHA256 = (
    "d751f88febc98a1537083dd5a4e93ebc2cfc40b40137a451fa359badc648d38b"
)

CORPUS_ARTICLE_ROOTS = 12019
EXPECTED_CASES = 61
EXPECTED_SCORABLE_CASES = 60
EXPECTED_GOLD = 83

# ``after_count`` is canonical identity count.  ``occurrence_count`` retains
# the two pre-canonical parent list sizes without treating alias collapse as
# retrieval discard or gold loss.
EXPECTED_CANDIDATE_STAGES: dict[str, dict[str, int]] = {
    "raw-pool": {
        "after_count": 3492,
        "occurrence_count": 3620,
        "gold_after": 68,
        "all_gold_cases": 48,
    },
    "canonical-pool": {
        "after_count": 3492,
        "occurrence_count": 3492,
        "gold_after": 68,
        "all_gold_cases": 48,
    },
    "raw-incumbent": {
        "after_count": 1112,
        "occurrence_count": 1155,
        "gold_after": 65,
        "all_gold_cases": 45,
    },
    "canonical-b0": {
        "after_count": 1112,
        "occurrence_count": 1112,
        "gold_after": 65,
        "all_gold_cases": 45,
    },
    "baseline-core": {
        "after_count": 1036,
        "occurrence_count": 1036,
        "gold_after": 64,
        "all_gold_cases": 44,
    },
    "b0-plus-admissible": {
        "after_count": 2585,
        "occurrence_count": 2585,
        "gold_after": 68,
        "all_gold_cases": 48,
    },
    "b0-plus-evaluated": {
        "after_count": 1861,
        "occurrence_count": 1861,
        "gold_after": 68,
        "all_gold_cases": 48,
    },
    "winner-pre-eviction": {
        "after_count": 1255,
        "occurrence_count": 1255,
        "gold_after": 65,
        "all_gold_cases": 45,
    },
    "final-selected": {
        "after_count": 1210,
        "occurrence_count": 1210,
        "gold_after": 65,
        "all_gold_cases": 45,
    },
}

EXPECTED_BASELINE_STAGES: dict[str, dict[str, int]] = {
    "parent-source": {
        "after_count": 1210,
        "occurrence_count": 1210,
        "gold_after": 66,
        "all_gold_cases": 46,
    },
    "parent-final": {
        "after_count": 1210,
        "occurrence_count": 1210,
        "gold_after": 66,
        "all_gold_cases": 46,
    }
}

EXPECTED_STAGE_PLAN: dict[str, list[dict[str, Any]]] = {
    BASELINE_ARM: [
        {
            "stage_id": "parent-source",
            "kind": "source",
            "parent_stage_ids": [],
        },
        {
            "stage_id": "parent-final",
            "kind": "present",
            "parent_stage_ids": ["parent-source"],
        },
    ],
    CANDIDATE_ARM: [
        {
            "stage_id": "raw-pool",
            "kind": "source",
            "parent_stage_ids": [],
        },
        {
            "stage_id": "canonical-pool",
            "kind": "canonicalize",
            "parent_stage_ids": ["raw-pool"],
        },
        {
            "stage_id": "raw-incumbent",
            "kind": "select",
            "parent_stage_ids": ["canonical-pool"],
        },
        {
            "stage_id": "canonical-b0",
            "kind": "canonicalize",
            "parent_stage_ids": ["raw-incumbent"],
        },
        {
            "stage_id": "baseline-core",
            "kind": "select",
            "parent_stage_ids": ["canonical-pool"],
        },
        {
            "stage_id": "b0-plus-admissible",
            "kind": "expand",
            "parent_stage_ids": ["canonical-b0"],
        },
        {
            "stage_id": "b0-plus-evaluated",
            "kind": "filter",
            "parent_stage_ids": ["b0-plus-admissible"],
        },
        {
            "stage_id": "winner-pre-eviction",
            "kind": "rerank",
            "parent_stage_ids": ["b0-plus-evaluated"],
        },
        {
            "stage_id": "final-selected",
            "kind": "present",
            "parent_stage_ids": ["winner-pre-eviction"],
        },
    ],
}

Coordinate = tuple[str, object]


def _working_source_path(value: object) -> Path:
    """Resolve a frozen code reference against the current editable tree."""

    relative = Path(str(value))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"unsafe working source path: {value!r}")
    mappings = {
        "lawrag": ROOT / "02_BACKEND/lawrag",
        "scripts": ROOT / "06_TOOLS/COMMANDS",
        "tests": ROOT / "05_TESTS/REGRESSION",
    }
    if relative.parts[:2] == ("docs", "adr"):
        return ROOT / "04_EXPERIMENTS/LEGACY_ADR" / Path(*relative.parts[2:])
    base = mappings.get(relative.parts[0])
    return base.joinpath(*relative.parts[1:]) if base else ROOT / relative


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _coordinate(value: Mapping[str, Any]) -> Coordinate:
    embedded = value.get("coordinate")
    if isinstance(embedded, (list, tuple)) and len(embedded) == 2:
        return str(embedded[0]), embedded[1]
    return str(value.get("doc_id") or ""), value.get("node")


def _coordinate_json(coordinate: Coordinate) -> list[object]:
    return [coordinate[0], coordinate[1]]


def _coordinate_key(coordinate: Coordinate) -> tuple[str, str]:
    return coordinate[0], repr(coordinate[1])


def _sorted_coordinates(values: Iterable[Coordinate]) -> list[Coordinate]:
    return sorted(set(values), key=_coordinate_key)


def _identity_canonicalizer(value: object) -> Coordinate:
    if isinstance(value, Mapping):
        return _coordinate(value)
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return str(value[0]), value[1]
    raise ValueError(f"invalid coordinate: {value!r}")


def _candidate_id(coordinate: Coordinate) -> str:
    digest = hashlib.sha256(
        f"{coordinate[0]}:{coordinate[1]}".encode("utf-8")
    ).hexdigest()
    return f"C-{digest[:16]}"


def _percentile(values: Sequence[int], ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    position = min(
        len(ordered) - 1,
        max(0, round((len(ordered) - 1) * ratio)),
    )
    return int(ordered[position])


def _validate_manifest(
    path: Path,
    *,
    expected_sha256: str,
) -> tuple[dict[str, Any], str]:
    if not expected_sha256 or expected_sha256 == "PENDING":
        raise ValueError("a frozen ADR manifest SHA-256 is required")
    actual_sha256 = _sha256(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            "ADR manifest hash mismatch: "
            f"expected={expected_sha256} actual={actual_sha256}"
        )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("adr_id") != ADR_ID:
        raise ValueError("ADR manifest id mismatch")
    if manifest.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("experiment id mismatch")
    if (manifest.get("design") or {}).get(
        "criteria_frozen_before_run"
    ) is not True:
        raise ValueError("criteria were not frozen before the audit run")
    actual_stage_plan = (manifest.get("design") or {}).get(
        "backfill_stage_plan"
    )
    if actual_stage_plan != EXPECTED_STAGE_PLAN:
        raise ValueError(
            "ADR-0081 backfill stage plan mismatch: expected exact ordered "
            "stage ids, kinds, and parent ids"
        )
    if (manifest.get("llm_policy") or {}).get("llm_calls") != []:
        raise ValueError("ADR-0081 backfill must declare zero LLM calls")

    dataset = manifest.get("dataset") or {}
    if (
        dataset.get("frozen_source") != ADR76_RUN_STORED
        or dataset.get("sha256") != ADR76_RUN_SHA256
        or int(dataset.get("cases") or 0) != EXPECTED_CASES
        or int(dataset.get("corpus_present_gold") or 0) != EXPECTED_GOLD
    ):
        raise ValueError("ADR-0081 frozen dataset contract mismatch")

    runs = {row.get("id"): row for row in manifest.get("runs") or ()}
    run = runs.get(RUN_ID) or {}
    if set(run.get("arm_ids") or ()) != {BASELINE_ARM, CANDIDATE_ARM}:
        raise ValueError("ADR-0081 run arm contract mismatch")
    if run.get("status") not in {"planned", "running", "complete"}:
        raise ValueError("ADR-0081 run is not executable or complete")
    if run.get("artifact_path") != "docs/adr/ADR-0081-retrieval-stage-recall-discard-ledger/artifacts/run-001.json":
        raise ValueError("ADR-0081 artifact path mismatch")
    runner_path = str(run.get("runner_path") or "")
    if runner_path != "scripts/rag_retrieval_stage_ledger_audit.py":
        raise ValueError("ADR-0081 runner path mismatch")
    if run.get("runner_sha256") != _sha256(Path(__file__).resolve()):
        raise ValueError("ADR-0081 runner hash mismatch")
    for group in ("implementation_sha256", "test_sha256"):
        frozen = run.get(group)
        if not isinstance(frozen, Mapping) or not frozen:
            raise ValueError(f"ADR-0081 {group} hash gate is missing")
        for relative, digest in frozen.items():
            candidate = _working_source_path(relative).resolve()
            if ROOT != candidate and ROOT not in candidate.parents:
                raise ValueError(f"ADR-0081 {group} path escapes repository")
            if not candidate.is_file() or _sha256(candidate) != digest:
                raise ValueError(
                    f"ADR-0081 {group} mismatch: {relative}"
                )
    return manifest, actual_sha256


def _load_frozen_sources() -> tuple[dict[str, Any], dict[str, Any]]:
    expected = (
        (ADR76_RUN, ADR76_RUN_SHA256),
        (ADR68_RUN, ADR68_RUN_SHA256),
    )
    for path, digest in expected:
        actual = _sha256(path)
        if actual != digest:
            raise ValueError(
                f"frozen source hash mismatch: {path}: {actual}"
            )

    adr76 = json.loads(ADR76_RUN.read_text(encoding="utf-8"))
    adr68 = json.loads(ADR68_RUN.read_text(encoding="utf-8"))
    if len(adr76.get("rows") or ()) != EXPECTED_CASES:
        raise ValueError("ADR-0076 row count changed")
    if len(adr68.get("rows") or ()) != EXPECTED_CASES:
        raise ValueError("ADR-0068 row count changed")
    lineage = adr76.get("source_lineage") or {}
    if (
        lineage.get("parent_68_run_path") != ADR68_RUN_STORED
        or lineage.get("parent_68_run_sha256") != ADR68_RUN_SHA256
    ):
        raise ValueError("ADR-0076 to ADR-0068 lineage mismatch")
    if int((adr76.get("summary") or {}).get("corpus_article_roots") or 0) \
            != CORPUS_ARTICLE_ROOTS:
        raise ValueError("frozen corpus article-root count changed")
    return adr76, adr68


def _case_rows(
    adr76: Mapping[str, Any],
    adr68: Mapping[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    parent_by_case = {
        str(row.get("case_id") or ""): row
        for row in adr68.get("rows") or ()
    }
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen: set[str] = set()
    for row76 in adr76.get("rows") or ():
        case_id = str(row76.get("case_id") or "")
        if not case_id or case_id in seen or case_id not in parent_by_case:
            raise ValueError(f"case lineage mismatch: {case_id!r}")
        seen.add(case_id)
        row68 = parent_by_case[case_id]
        if row76.get("question") != row68.get("question"):
            raise ValueError(f"question mismatch: {case_id}")
        pairs.append((row76, row68))
    if len(pairs) != EXPECTED_CASES:
        raise ValueError("frozen case pairing is incomplete")
    return pairs


def _extract_gold_free_case(
    row76: Mapping[str, Any],
    row68: Mapping[str, Any],
) -> dict[str, Any]:
    """Extract only candidate identities and receipts; never read gold."""

    case_id = str(row76.get("case_id") or "")
    arms76 = row76.get("arms") or {}
    candidate = arms76.get("bounded-global-augmenting-basis") or {}
    parent_final = arms76.get("baseline") or {}
    arms68 = row68.get("arms") or {}
    parent_union = arms68.get("recall-first-union") or {}
    parent_core = arms68.get("baseline") or {}
    meta = candidate.get("retrieval_meta") or {}
    audit = meta.get("candidate_audit") or {}

    raw_pool_rows = list(parent_union.get("internal_pool") or ())
    raw_incumbent_rows = list(parent_union.get("selected") or ())
    pool = set(map(_coordinate, candidate.get("internal_pool") or ()))
    final = set(map(_coordinate, candidate.get("selected") or ()))
    promoted = set(map(_coordinate, meta.get("promoted") or ()))
    evicted = set(map(_coordinate, meta.get("evicted") or ()))
    b0 = (final - promoted) | evicted
    core = set(map(_coordinate, parent_core.get("selected") or ()))
    baseline_final = set(
        map(_coordinate, parent_final.get("selected") or ())
    )

    admissible_ids = set(audit.get("admissible_candidate_ids") or ())
    evaluated_ids = set(audit.get("evaluated_candidate_ids") or ())
    screened_by_id = audit.get("structurally_screened_candidates") or {}
    by_id = {_candidate_id(coordinate): coordinate for coordinate in pool}
    admissible = {
        by_id[candidate_id]
        for candidate_id in admissible_ids
        if candidate_id in by_id
    }
    evaluated = {
        by_id[candidate_id]
        for candidate_id in evaluated_ids
        if candidate_id in by_id
    }
    screened = {
        by_id[candidate_id]
        for candidate_id in screened_by_id
        if candidate_id in by_id
    }
    screened_reasons = {
        by_id[candidate_id]: ";".join(
            sorted(str(reason) for reason in reasons)
        )
        for candidate_id, reasons in screened_by_id.items()
        if candidate_id in by_id
    }
    admissible_union = b0 | admissible
    evaluated_union = b0 | evaluated
    winner_pre_eviction = b0 | promoted

    if len(pool) != int(meta.get("canonical_pool_count") or -1):
        raise ValueError(f"{case_id}: canonical pool count mismatch")
    if len(b0) != int(meta.get("canonical_incumbent_count") or -1):
        raise ValueError(f"{case_id}: reconstructed B0 count mismatch")
    if len(core) != int(meta.get("canonical_core_count") or -1):
        raise ValueError(f"{case_id}: baseline core count mismatch")
    if len(admissible) != int(audit.get("admissible_candidate_count") or 0):
        raise ValueError(f"{case_id}: admissible id mapping is incomplete")
    if evaluated | screened != admissible or evaluated & screened:
        raise ValueError(f"{case_id}: evaluated/screened partition mismatch")
    if final != (b0 - evicted) | promoted:
        raise ValueError(f"{case_id}: addition/eviction equation failed")
    if not (
        b0 <= pool
        and admissible <= pool
        and evaluated <= admissible
        and promoted <= evaluated
        and final <= pool
    ):
        raise ValueError(f"{case_id}: stage subset invariant failed")
    if meta.get("gold_fields_received") is not False:
        raise ValueError(f"{case_id}: selector gold boundary is not clean")

    incumbent_discard_reasons = {
        coordinate: (
            "parent_incumbent_not_selected_but_retained_for_solver"
            if coordinate in admissible
            else "parent_incumbent_not_selected_and_not_admissible"
        )
        for coordinate in pool - b0
    }
    baseline_core_discard_reasons = {
        coordinate: "parent_baseline_core_not_selected"
        for coordinate in pool - core
    }
    winner_discard_reasons = {
        coordinate: (
            "unresolved_bundle_feasibility_or_objective_from_frozen_trace"
        )
        for coordinate in evaluated_union - winner_pre_eviction
    }
    eviction_discard_reasons = {
        coordinate: "global_bundle_cap_eviction"
        for coordinate in winner_pre_eviction - final
    }

    return {
        "case_id": case_id,
        "raw_pool_coordinates": tuple(map(_coordinate, raw_pool_rows)),
        "raw_incumbent_coordinates": tuple(
            map(_coordinate, raw_incumbent_rows)
        ),
        "pool": pool,
        "b0": b0,
        "core": core,
        "admissible": admissible,
        "evaluated": evaluated,
        "screened": screened,
        "screened_reasons": screened_reasons,
        "admissible_union": admissible_union,
        "evaluated_union": evaluated_union,
        "promoted": promoted,
        "evicted": evicted,
        "winner_pre_eviction": winner_pre_eviction,
        "final": final,
        "parent_final": baseline_final,
        "incumbent_discard_reasons": incumbent_discard_reasons,
        "baseline_core_discard_reasons": baseline_core_discard_reasons,
        "winner_discard_reasons": winner_discard_reasons,
        "eviction_discard_reasons": eviction_discard_reasons,
        "bundle_accounting": dict(audit.get("search_accounting") or {}),
        "candidate_evaluations": dict(
            audit.get("candidate_evaluations") or {}
        ),
    }


def _gold_catalog(row76: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidate = (
        (row76.get("arms") or {}).get("bounded-global-augmenting-basis")
        or {}
    )
    out: list[dict[str, Any]] = []
    for value in candidate.get("gold_results") or ():
        if value.get("scorable") is not True:
            continue
        out.append(
            {
                "coordinate": [value.get("doc_id"), value.get("node")],
                "law": value.get("law"),
                "article": value.get("article"),
                "corpus_status": value.get("corpus_status"),
                "document_revision": value.get("document_revision"),
                "document_enforcement": value.get("document_enforcement"),
            }
        )
    return out


def _record_candidate_capture(fact: Mapping[str, Any]) -> dict[str, Any]:
    recorder = StageLedgerRecorder(
        case_id=str(fact["case_id"]),
        arm_id=CANDIDATE_ARM,
        canonicalizer=_identity_canonicalizer,
    )
    pool = _sorted_coordinates(fact["pool"])
    b0 = _sorted_coordinates(fact["b0"])
    core = _sorted_coordinates(fact["core"])
    admissible_union = _sorted_coordinates(fact["admissible_union"])
    evaluated_union = _sorted_coordinates(fact["evaluated_union"])
    winner = _sorted_coordinates(fact["winner_pre_eviction"])
    final = _sorted_coordinates(fact["final"])

    recorder.record_stage(
        "raw-pool",
        "source",
        pool,
        after_occurrence_count=len(fact["raw_pool_coordinates"]),
    )
    recorder.record_stage(
        "canonical-pool",
        "canonicalize",
        pool,
        parent_stage_ids=("raw-pool",),
        before_coordinates=pool,
        before_occurrence_count=len(fact["raw_pool_coordinates"]),
        after_occurrence_count=len(pool),
    )
    recorder.record_stage(
        "raw-incumbent",
        "select",
        b0,
        parent_stage_ids=("canonical-pool",),
        before_coordinates=pool,
        before_occurrence_count=len(pool),
        after_occurrence_count=len(fact["raw_incumbent_coordinates"]),
        discard_reasons=fact["incumbent_discard_reasons"],
    )
    recorder.record_stage(
        "canonical-b0",
        "canonicalize",
        b0,
        parent_stage_ids=("raw-incumbent",),
        before_coordinates=b0,
        before_occurrence_count=len(fact["raw_incumbent_coordinates"]),
        after_occurrence_count=len(b0),
    )
    recorder.record_stage(
        "baseline-core",
        "select",
        core,
        parent_stage_ids=("canonical-pool",),
        before_coordinates=pool,
        discard_reasons=fact["baseline_core_discard_reasons"],
    )
    recorder.record_stage(
        "b0-plus-admissible",
        "expand",
        admissible_union,
        parent_stage_ids=("canonical-b0",),
        before_coordinates=b0,
    )
    recorder.record_stage(
        "b0-plus-evaluated",
        "filter",
        evaluated_union,
        parent_stage_ids=("b0-plus-admissible",),
        before_coordinates=admissible_union,
        discard_reasons=fact["screened_reasons"],
    )
    recorder.record_stage(
        "winner-pre-eviction",
        "rerank",
        winner,
        parent_stage_ids=("b0-plus-evaluated",),
        before_coordinates=evaluated_union,
        discard_reasons=fact["winner_discard_reasons"],
    )
    recorder.record_stage(
        "final-selected",
        "present",
        final,
        parent_stage_ids=("winner-pre-eviction",),
        before_coordinates=winner,
        discard_reasons=fact["eviction_discard_reasons"],
    )
    capture = recorder.capture()
    validate_capture(capture)
    return capture


def _record_baseline_capture(fact: Mapping[str, Any]) -> dict[str, Any]:
    recorder = StageLedgerRecorder(
        case_id=str(fact["case_id"]),
        arm_id=BASELINE_ARM,
        canonicalizer=_identity_canonicalizer,
    )
    parent_final = _sorted_coordinates(fact["parent_final"])
    recorder.record_stage(
        "parent-source",
        "source",
        parent_final,
        after_occurrence_count=len(parent_final),
    )
    recorder.record_stage(
        "parent-final",
        "present",
        parent_final,
        parent_stage_ids=("parent-source",),
        before_coordinates=parent_final,
    )
    capture = recorder.capture()
    validate_capture(capture)
    return capture


def _gold_coordinates(catalog: Sequence[Mapping[str, Any]]) \
        -> list[Coordinate]:
    return [
        (str(value["coordinate"][0]), value["coordinate"][1])
        for value in catalog
    ]


def _stage_map(ledger: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(stage.get("stage_id") or ""): stage
        for stage in ledger.get("stages") or ()
    }


def _stage_summary(
    ledgers: Sequence[Mapping[str, Any]],
    stage_id: str,
) -> dict[str, Any]:
    stages = [_stage_map(ledger)[stage_id] for ledger in ledgers]
    counts = [int(stage.get("after_count") or 0) for stage in stages]
    occurrence_counts = [
        int(
            ((stage.get("occurrence_counts") or {}).get("after"))
            if (stage.get("occurrence_counts") or {}).get("after") is not None
            else stage.get("after_count") or 0
        )
        for stage in stages
    ]
    gold_total = sum(int(stage.get("gold_total") or 0) for stage in stages)
    gold_after = sum(int(stage.get("gold_after") or 0) for stage in stages)
    scorable_stages = [
        stage for stage in stages if int(stage.get("gold_total") or 0) > 0
    ]
    all_gold_cases = sum(
        int(stage.get("gold_after") or 0)
        == int(stage.get("gold_total") or 0)
        for stage in scorable_stages
    )
    reason_counts: Counter[str] = Counter()
    for stage in stages:
        reason_counts.update(stage.get("discard_reason_counts") or {})
    return {
        "stage_id": stage_id,
        "cases": len(stages),
        "scorable_cases": len(scorable_stages),
        "after_count": sum(counts),
        "occurrence_count": sum(occurrence_counts),
        "after_mean": round(statistics.mean(counts), 3) if counts else 0,
        "after_p50": _percentile(counts, 0.5),
        "after_p95": _percentile(counts, 0.95),
        "gold_total": gold_total,
        "gold_after": gold_after,
        "golden_recall": (
            round(gold_after / gold_total, 6) if gold_total else None
        ),
        "all_gold_cases": all_gold_cases,
        "mean_selectivity": round(
            sum(counts) / len(stages) / CORPUS_ARTICLE_ROOTS, 8
        ) if stages else 0,
        "discard_reason_counts": dict(sorted(reason_counts.items())),
    }


def _gold_fates(
    fact: Mapping[str, Any],
    catalog: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    stage_sets = {
        "raw-pool": set(fact["pool"]),
        "canonical-pool": set(fact["pool"]),
        "raw-incumbent": set(fact["b0"]),
        "canonical-b0": set(fact["b0"]),
        "baseline-core": set(fact["core"]),
        "b0-plus-admissible": set(fact["admissible_union"]),
        "b0-plus-evaluated": set(fact["evaluated_union"]),
        "winner-pre-eviction": set(fact["winner_pre_eviction"]),
        "final-selected": set(fact["final"]),
        "parent-final": set(fact["parent_final"]),
    }
    out: list[dict[str, Any]] = []
    for value in catalog:
        coordinate = (
            str(value["coordinate"][0]),
            value["coordinate"][1],
        )
        membership = {
            stage_id: coordinate in coordinates
            for stage_id, coordinates in stage_sets.items()
        }
        if not membership["raw-pool"]:
            fate = "not_generated_upstream"
            discard_reason = "absent_from_frozen_raw_pool"
        elif (
            membership["b0-plus-evaluated"]
            and not membership["winner-pre-eviction"]
        ):
            fate = "rejected_in_unresolved_bundle_or_objective_interval"
            discard_reason = (
                "feasibility_vs_objective_not_distinguishable_from_"
                "frozen_trace"
            )
        elif membership["winner-pre-eviction"] \
                and not membership["final-selected"]:
            fate = "evicted_after_winner_addition"
            discard_reason = "global_bundle_cap_eviction"
        elif membership["final-selected"]:
            fate = "retained_in_candidate_final"
            discard_reason = None
        else:
            fate = "not_selected_before_evaluated_union"
            discard_reason = "stage_membership_trace"
        out.append(
            {
                **dict(value),
                "candidate_id": _candidate_id(coordinate),
                "membership": membership,
                "fate": fate,
                "discard_reason": discard_reason,
                "parent_only_regression": (
                    membership["parent-final"]
                    and not membership["final-selected"]
                ),
            }
        )
    return out


def _assert_expected_summary(summary: Mapping[str, Any]) -> None:
    candidate = summary.get("candidate_stages") or {}
    baseline = summary.get("baseline_stages") or {}
    for stage_id, expected in EXPECTED_CANDIDATE_STAGES.items():
        actual = candidate.get(stage_id) or {}
        for key, value in expected.items():
            if actual.get(key) != value:
                raise ValueError(
                    f"candidate stage aggregate mismatch: {stage_id}.{key}: "
                    f"expected={value} actual={actual.get(key)}"
                )
    for stage_id, expected in EXPECTED_BASELINE_STAGES.items():
        actual = baseline.get(stage_id) or {}
        for key, value in expected.items():
            if actual.get(key) != value:
                raise ValueError(
                    f"baseline stage aggregate mismatch: {stage_id}.{key}: "
                    f"expected={value} actual={actual.get(key)}"
                )
    if summary.get("gold_total") != EXPECTED_GOLD:
        raise ValueError("gold denominator changed")
    if summary.get("scorable_cases") != EXPECTED_SCORABLE_CASES:
        raise ValueError("scorable case denominator changed")


def build_report(
    adr76: Mapping[str, Any],
    adr68: Mapping[str, Any],
    *,
    manifest_path: Path,
    manifest_sha256: str,
) -> dict[str, Any]:
    pairs = _case_rows(adr76, adr68)

    # Phase 1: product-state snapshots only.  This loop never calls
    # ``_gold_catalog`` and every helper capture asserts gold invisibility.
    facts = [
        _extract_gold_free_case(row76, row68)
        for row76, row68 in pairs
    ]
    candidate_captures = [
        _record_candidate_capture(fact) for fact in facts
    ]
    baseline_captures = [
        _record_baseline_capture(fact) for fact in facts
    ]
    if any(capture.get("gold_visible_to_product") is not False
           for capture in [*candidate_captures, *baseline_captures]):
        raise ValueError("gold leaked into a product-state capture")

    # Phase 2: offline gold join, after all captures are complete.
    catalogs = [_gold_catalog(row76) for row76, _row68 in pairs]
    if sum(len(values) for values in catalogs) != EXPECTED_GOLD:
        raise ValueError("frozen gold coordinate count changed")
    if sum(bool(values) for values in catalogs) != EXPECTED_SCORABLE_CASES:
        raise ValueError("frozen scorable case count changed")

    candidate_ledgers = [
        grade_capture(capture, _gold_coordinates(catalog))
        for capture, catalog in zip(candidate_captures, catalogs)
    ]
    baseline_ledgers = [
        grade_capture(capture, _gold_coordinates(catalog))
        for capture, catalog in zip(baseline_captures, catalogs)
    ]
    for ledger in [*candidate_ledgers, *baseline_ledgers]:
        validate_graded_ledger(ledger)

    candidate_stage_ids = list(EXPECTED_CANDIDATE_STAGES)
    baseline_stage_ids = list(EXPECTED_BASELINE_STAGES)
    candidate_summaries = {
        stage_id: _stage_summary(candidate_ledgers, stage_id)
        for stage_id in candidate_stage_ids
    }
    baseline_summaries = {
        stage_id: _stage_summary(baseline_ledgers, stage_id)
        for stage_id in baseline_stage_ids
    }
    gold_fates = [
        {
            "case_id": str(fact["case_id"]),
            "gold": _gold_fates(fact, catalog),
        }
        for fact, catalog in zip(facts, catalogs)
    ]
    flat_fates = [
        gold
        for case in gold_fates
        for gold in case["gold"]
    ]
    fate_counts = Counter(str(value["fate"]) for value in flat_fates)
    parent_only = [
        {
            "case_id": case["case_id"],
            "coordinate": value["coordinate"],
            "law": value["law"],
            "article": value["article"],
        }
        for case in gold_fates
        for value in case["gold"]
        if value["parent_only_regression"]
    ]

    bundle_totals: Counter[str] = Counter()
    for fact in facts:
        for key in (
            "evaluated_bundles",
            "feasible_bundles",
            "closure_screened_bundles",
            "dominance_screened_bundles",
            "objective_bound_bundles_screened",
            "extra_eviction_bundles_screened",
        ):
            bundle_totals[key] += int(
                (fact.get("bundle_accounting") or {}).get(key) or 0
            )

    summary = {
        "cases": len(facts),
        "scorable_cases": sum(bool(values) for values in catalogs),
        "gold_total": sum(len(values) for values in catalogs),
        "corpus_article_roots": CORPUS_ARTICLE_ROOTS,
        "candidate_stages": candidate_summaries,
        "baseline_stages": baseline_summaries,
        "fate_counts": dict(sorted(fate_counts.items())),
        "parent_only_regressions": parent_only,
        "bundle_totals": dict(sorted(bundle_totals.items())),
    }
    _assert_expected_summary(summary)

    # Let the common helper build and validate the canonical v4 payload.  The
    # outer report below is a run receipt that adds only frozen-lineage and
    # reconstruction-limit diagnostics.
    run_ledger = build_run_artifact(
        RUN_ID,
        [*baseline_ledgers, *candidate_ledgers],
        {
            BASELINE_ARM: baseline_stage_ids,
            CANDIDATE_ARM: candidate_stage_ids,
        },
    )
    stage_ledger = build_experiment_artifact(
        ADR_ID,
        EXPERIMENT_ID,
        [run_ledger],
    )

    # The artifact root remains the exact canonical helper ledger consumed by
    # ``adr_structure.py``.  The validator permits one extension key only, so
    # every receipt and diagnostic lives below ``audit``.  Then discard the
    # helper projection hash and seal the complete enriched root.
    report: dict[str, Any] = dict(stage_ledger)
    report["audit"] = {
        "receipt_schema_version": "retrieval-stage-ledger-audit-v1",
        "run_id": RUN_ID,
        "manifest_path": str(manifest_path.relative_to(ROOT)),
        "manifest_sha256": manifest_sha256,
        "runner": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": _sha256(Path(__file__).resolve()),
        "source_lineage": {
            "adr76_run_path": str(ADR76_RUN.relative_to(ROOT)),
            "adr76_run_sha256": ADR76_RUN_SHA256,
            "adr68_run_path": str(ADR68_RUN.relative_to(ROOT)),
            "adr68_run_sha256": ADR68_RUN_SHA256,
        },
        "contract": {
            "offline_backfill": True,
            "computed_post_selection": True,
            "gold_visible_to_product": False,
            "llm_calls": 0,
            "provider_calls": 0,
            "main_wiring": "unchanged",
            "raw_counts_are_occurrences": True,
            "canonical_counts_are_unique_article_roots": True,
        },
        "reconstruction": {
            "status": "incomplete",
            "exact_boundaries": [
                "raw pool occurrence and canonical pool snapshot",
                "raw incumbent occurrence and canonical B0 snapshot",
                "baseline core",
                "B0 plus admissible",
                "B0 plus evaluated",
                "winning additions before eviction",
                "final selection after eviction",
                "ADR-0073 parent final replay",
            ],
            "unavailable_boundaries": [
                {
                    "from_stage": "b0-plus-evaluated",
                    "to_stage": "feasible-candidate-union",
                    "status": "incomplete",
                    "reason": (
                        "the frozen artifact stores aggregate feasible, "
                        "closure-screened, and dominance-screened bundle "
                        "counts but no candidate ids for each partition"
                    ),
                },
                {
                    "from_stage": "feasible-candidate-union",
                    "to_stage": "winner-pre-eviction",
                    "status": "incomplete",
                    "reason": (
                        "the frozen artifact stores only the winning bundle "
                        "and no per-candidate feasible objective rank"
                    ),
                },
            ],
            "coarse_transition": {
                "from_stage": "b0-plus-evaluated",
                "to_stage": "winner-pre-eviction",
                "boundary_sets_exact": True,
                "internal_discard_attribution": "incomplete",
                "discard_reason": (
                    "unresolved_bundle_feasibility_or_objective_from_"
                    "frozen_trace"
                ),
            },
        },
        "gold_catalog_by_case": [
            {
                "case_id": str(fact["case_id"]),
                "gold": catalog,
            }
            for fact, catalog in zip(facts, catalogs)
        ],
        "gold_fates_by_case": gold_fates,
        "raw_occurrence_diagnostics": [
            {
                "case_id": str(fact["case_id"]),
                "raw_pool_occurrence_count": len(
                    fact["raw_pool_coordinates"]
                ),
                "canonical_pool_count": len(fact["pool"]),
                "raw_pool_coordinates": [
                    _coordinate_json(value)
                    for value in fact["raw_pool_coordinates"]
                ],
                "raw_incumbent_occurrence_count": len(
                    fact["raw_incumbent_coordinates"]
                ),
                "canonical_b0_count": len(fact["b0"]),
                "raw_incumbent_coordinates": [
                    _coordinate_json(value)
                    for value in fact["raw_incumbent_coordinates"]
                ],
                "alias_mapping_status": "unavailable_in_frozen_artifacts",
            }
            for fact in facts
        ],
        "summary": summary,
    }
    report.pop("artifact_sha256", None)
    report["artifact_sha256"] = _json_sha256(report)
    return report


def _write_report(path: Path, report: Mapping[str, Any]) -> tuple[str, int]:
    payload = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
    return hashlib.sha256(payload).hexdigest(), len(payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument(
        "--manifest-sha256",
        required=True,
        help="SHA-256 frozen after ADR design and run fields are complete",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate hashes and all 61 reconstructed ledgers without writing",
    )
    args = parser.parse_args(argv)

    manifest_path = args.manifest.resolve()
    _manifest, manifest_sha256 = _validate_manifest(
        manifest_path,
        expected_sha256=str(args.manifest_sha256),
    )
    adr76, adr68 = _load_frozen_sources()
    report = build_report(
        adr76,
        adr68,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
    )
    if args.validate_only:
        summary = report["audit"]["summary"]
        print(
            json.dumps(
                {
                    "status": "valid",
                    "cases": summary["cases"],
                    "gold_total": summary["gold_total"],
                    "candidate_final_gold": summary
                    ["candidate_stages"]["final-selected"]["gold_after"],
                    "parent_final_gold": summary
                    ["baseline_stages"]["parent-final"]["gold_after"],
                    "would_write": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    output = args.output.resolve()
    digest, size = _write_report(output, report)
    summary = report["audit"]["summary"]
    print(
        json.dumps(
            {
                "status": "complete",
                "path": str(output),
                "sha256": digest,
                "bytes": size,
                "cases": summary["cases"],
                "gold_total": summary["gold_total"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
