#!/usr/bin/env python3
"""ADR-0105 schema-constrained query-grounding API probe.

The candidate receives only the public question, the frozen ADR-0103 final
coordinates, the current corpus, and the approved Tier-1 registry.  It makes
exactly two product-path Haiku calls per case (planner, then closed-menu
binder), validates the result deterministically, and gives at most four new
article roots to the existing semantic closure.  Decisive coordinates and
reference answers are loaded only after every product capture has been sealed
and written.

This is an isolated experiment runner.  It does not mutate MAIN, search/API
wiring, feature switches, the Legal Graph pointer, or the Tier-1 registry.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for key, relative in (
    ("STRUCTURE_STORE", "data/structure"),
    ("STRUCTURE_CUSTOM_DIR", "data/custom"),
    ("GLOSSARY_STORE", "data/glossary.json"),
    ("RAG_LINKS_STORE", "data/links.json"),
    ("RAG_DELEGATION_STORE", "data/delegation.json"),
    ("RAG_LAW_INDEX_STORE", "data/law_index.json"),
    ("RAG_ENGINE_RULES", "data/rules/engine.json"),
):
    os.environ.setdefault(key, str(ROOT / relative))
# This probe is read-only.  An inherited batch setting must never compile and
# rewrite the frozen reverse-lexicon cache during prewarm.
os.environ["RAG_LEXICON_COMPILE_MISSING"] = "0"

from lawrag.core import embedding, llm as llm_mod  # noqa: E402
from lawrag.core.domain_graph import spanparts  # noqa: E402
from lawrag.core.rag import (  # noqa: E402
    conceptfirst,
    index as index_mod,
    legal_graph_store,
    legal_semantic_search,
    lexicon as lexicon_mod,
    query_grounding,
    vector as vector_mod,
)
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402


ADR_ID = "ADR-0105"
EXPERIMENT_ID = "ADR-0105-experiment-v1"
RUN_ID = "run-001"
MODEL = "claude-haiku-4-5-20251001"
ARMS = ("baseline", "schema-grounded-planner")
CASE_IDS = (
    "cm-004", "cm-008", "cm-011", "cm-016", "cm-025", "cm-030",
    "cm-031", "cm-033", "cm-039", "cm-043", "cm-048", "cm-049",
    "cm-050", "fsc-hard-004", "fsc-hard-006", "fsc-hard-009",
)
PROTECTED_PREFIX = 12
SEED_CAP = 4
FINAL_CAP = 20
MENU_CAP = 36
STAGES = {
    "baseline": ["baseline-source", "baseline-present"],
    "schema-grounded-planner": [
        "candidate-source", "reverse-match", "fulltext-match", "vector-match",
        "channel-union", "closed-candidate-bind", "signature-validate",
        "typed-closure", "bundle-rerank", "candidate-present",
    ],
}
SOURCES = {
    "dataset_lock": (
        ROOT / "docs/adr/ADR-0105-schema-constrained-query-grounding-api"
        / "artifacts/dataset-lock.json"
    ),
    "public_input": (
        ROOT / "docs/adr/ADR-0105-schema-constrained-query-grounding-api"
        / "artifacts/public-input-lock.json"
    ),
    "input_lock": (
        ROOT / "docs/adr/ADR-0091-legalclosure-v2-article-reachability-ledger"
        / "artifacts/input-lock.json"
    ),
    "parent_run": (
        ROOT / "docs/adr/ADR-0103-legal-semantic-entity-search-pipeline"
        / "artifacts/run-007.json"
    ),
    "cm": ROOT / "data/review/cm_core_e2e_v2.json",
    "fsc": ROOT / "data/review/fsc_hard_retrieval_v2.json",
}
EXPECTED = {
    "dataset_lock": "69db899d15bfa05af3a91e10f8a0e1187e0b4d8f8c93bd2052346c24c1f7acf6",
    "public_input": "9216e82e7a9a88decd400c88c7d6daf0eb9e0c8866b685e8936c2367162e378e",
    "input_lock": "7636cc52ac0bd94a10baa1d75f3f381940981ff86beafa7f7ee91fedf9308452",
    "parent_run": "3af551603b6fcacfaa7e628df1eb6e56133dfb331c1608f927a433ccd7e28fea",
    "cm": "d3c707caa114dec379201c2ba9d2177b0c6bc17ceb4ae9394df1397e9dbfccb1",
    "fsc": "981d4fa6fd4b77d70eeade73aa907243937dfe33b228826c71eadf438b813269",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_receipt(path: Path) -> dict[str, Any]:
    """Hash a directory using the algorithm frozen in dataset-lock.json."""

    digest = hashlib.sha256()
    count = 0
    size = 0
    files = sorted(
        (value for value in path.rglob("*") if value.is_file()),
        key=lambda value: value.relative_to(path).as_posix(),
    )
    for value in files:
        relative = value.relative_to(path).as_posix()
        file_sha = _sha(value)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_sha))
        count += 1
        size += value.stat().st_size
    return {
        "path": str(path.relative_to(ROOT)),
        "files": count,
        "bytes": size,
        "sha256": digest.hexdigest(),
    }


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True,
    ) + "\n"
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def _asset_receipt(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": (
            str(resolved.relative_to(ROOT))
            if resolved.is_relative_to(ROOT) else str(resolved)
        ),
        "exists": resolved.is_file(),
        "size": resolved.stat().st_size if resolved.is_file() else 0,
        "sha256": _sha(resolved) if resolved.is_file() else None,
    }


def _coordinates(values: Iterable[object]) -> list[tuple[str, object]]:
    output: list[tuple[str, object]] = []
    for value in values:
        if isinstance(value, Mapping):
            coordinate = (str(value["doc_id"]), value["node"])
        else:
            coordinate = (str(value[0]), value[1])  # type: ignore[index]
        if coordinate not in output:
            output.append(coordinate)
    return output


def _union(*groups: Iterable[tuple[str, object]]) -> list[tuple[str, object]]:
    output: list[tuple[str, object]] = []
    for group in groups:
        for value in group:
            coordinate = tuple(value)
            if coordinate not in output:
                output.append(coordinate)
    return output


def _percentile(values: Sequence[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    return ordered[max(0, math.ceil(ratio * len(ordered)) - 1)]


def _presented_p95(values: Sequence[float]) -> float:
    """Match the frozen ADR validator's small-sample percentile rule."""

    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * 0.95)))
    return ordered[index]


def _usage(calls: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    durations = [
        float((row.get("provider") or {}).get("dur_ms") or 0.0)
        for row in calls
    ]
    ttft = [
        float((row.get("provider") or {}).get("ttft_ms") or 0.0)
        for row in calls
    ]
    return {
        "calls": len(calls),
        "input_tokens": sum(
            int((row.get("provider") or {}).get("usage", {}).get(
                "input_tokens", 0,
            ))
            for row in calls
        ),
        "output_tokens": sum(
            int((row.get("provider") or {}).get("usage", {}).get(
                "output_tokens", 0,
            ))
            for row in calls
        ),
        "provider_duration_ms": sum(durations),
        "provider_duration_p50_ms": statistics.median(durations) if durations else 0.0,
        "provider_duration_p95_ms": _percentile(durations, 0.95),
        "ttft_p50_ms": statistics.median(ttft) if ttft else 0.0,
        "ttft_p95_ms": _percentile(ttft, 0.95),
        "errors": sum(bool((row.get("provider") or {}).get("error")) for row in calls),
    }


def _audit_call(
    kind: str,
    system: str,
    user: str,
    schema: dict[str, Any],
    max_tokens: int,
    effort: str | None,
    requested_model: str,
    result: dict[str, Any] | None,
    exchange: object,
) -> dict[str, Any]:
    provider = exchange.dump() if exchange is not None else {}
    return {
        "kind": kind,
        "system": system,
        "user": user,
        "schema": schema,
        "max_tokens": max_tokens,
        "effort": effort,
        "requested_model": requested_model,
        "provider": provider,
        "structured_output": result,
    }


class RecordingLLM:
    """One-call-through wrapper with complete structured exchange receipts."""

    def __init__(self, real: llm_mod.LLM):
        self.real = real
        self.model = MODEL
        self.backend = real.backend
        self.transport_max_retries = 0
        self.log = real.log
        self.audit: list[dict[str, Any]] = []

    def structured(
        self,
        kind: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int = 16000,
        effort: str | None = "high",
        images: list[str] | None = None,
        model: str | None = None,
    ) -> dict[str, Any] | None:
        requested = model or MODEL
        if requested != MODEL:
            raise RuntimeError(f"product model policy mismatch: {requested}")
        before = len(self.real.log)
        caught: Exception | None = None
        result: dict[str, Any] | None = None
        try:
            result = self.real.structured(
                kind,
                system,
                user,
                schema,
                max_tokens=max_tokens,
                effort=effort,
                images=images,
                model=MODEL,
            )
        except Exception as exc:  # preserve a receipt before propagating
            caught = exc
        exchange = self.real.log[before] if len(self.real.log) > before else None
        receipt = _audit_call(
            kind,
            system,
            user,
            schema,
            max_tokens,
            effort,
            requested,
            result,
            exchange,
        )
        receipt["backend"] = self.backend
        receipt["transport_max_retries"] = self.transport_max_retries
        receipt["wrapper_error"] = (
            f"{type(caught).__name__}: {caught}" if caught is not None else ""
        )
        self.audit.append(receipt)
        if caught is not None:
            raise caught
        if exchange is None or exchange.model != MODEL:
            raise RuntimeError(
                "provider model policy mismatch: "
                f"{getattr(exchange, 'model', None)}"
            )
        return result


def _verify_sources() -> dict[str, str]:
    hashes = {}
    for key, path in SOURCES.items():
        actual = _sha(path)
        if actual != EXPECTED[key]:
            raise ValueError(f"frozen source hash mismatch: {key} {actual}")
        hashes[key] = actual
    return hashes


def _verify_runtime_sources(graph_root: Path) -> dict[str, Any]:
    """Verify every artifact that can affect retrieval before provider use."""

    lock_path = SOURCES["dataset_lock"]
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("product_model") != MODEL:
        raise ValueError("dataset lock product model mismatch")
    if tuple(lock.get("case_ids") or ()) != CASE_IDS:
        raise ValueError("dataset lock case IDs mismatch")
    expected_graph_root = (ROOT / str(lock["graph"]["root"])).resolve()
    if graph_root.resolve() != expected_graph_root:
        raise ValueError(
            f"graph root outside frozen lock: {graph_root} != {expected_graph_root}"
        )

    file_receipts: dict[str, dict[str, Any]] = {}
    for key, frozen in sorted(lock["files"].items()):
        path = (ROOT / str(frozen["path"])).resolve()
        if not path.is_file():
            raise ValueError(f"frozen runtime file missing: {key} {path}")
        receipt = {
            "path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "sha256": _sha(path),
        }
        if (
            receipt["bytes"] != int(frozen["bytes"])
            or receipt["sha256"] != str(frozen["sha256"])
        ):
            raise ValueError(f"frozen runtime file mismatch: {key} {receipt}")
        file_receipts[key] = receipt

    tree_receipts: dict[str, dict[str, Any]] = {}
    for key, frozen in sorted(lock["trees"].items()):
        path = (ROOT / str(frozen["path"])).resolve()
        receipt = _tree_receipt(path)
        if any(
            receipt[field] != frozen[field]
            for field in ("files", "bytes", "sha256")
        ):
            raise ValueError(f"frozen runtime tree mismatch: {key} {receipt}")
        tree_receipts[key] = receipt

    graph = lock["graph"]
    pointer = (ROOT / str(graph["pointer_path"])).resolve()
    manifest = (ROOT / str(graph["manifest_path"])).resolve()
    if _sha(pointer) != graph["pointer_sha256"]:
        raise ValueError("frozen Legal Graph pointer mismatch")
    if _sha(manifest) != graph["manifest_sha256"]:
        raise ValueError("frozen Legal Graph manifest mismatch")
    return {
        "dataset_lock_path": str(lock_path.relative_to(ROOT)),
        "dataset_lock_sha256": _sha(lock_path),
        "files": file_receipts,
        "trees": tree_receipts,
        "graph": dict(graph),
    }


def _public_cases() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load a physically gold-free product input captured before API use."""

    lock = json.loads(SOURCES["public_input"].read_text(encoding="utf-8"))
    if lock.get("contains_gold_or_reference_answer") is not False:
        raise ValueError("public input lock is not explicitly gold-free")
    if tuple(str(row["case_id"]) for row in lock["cases"]) != CASE_IDS:
        raise ValueError("public input case order mismatch")
    public = [{
        "case_id": str(row["case_id"]),
        "number": int(row["number"]),
        "suite": str(row["suite"]),
        "question": str(row["question"]),
        "baseline": _coordinates(row["baseline_coordinates"]),
    } for row in lock["cases"]]
    return public, {
        "graph_generation": str(lock["graph_generation"]),
        "graph_content_sha256": str(lock["graph_content_sha256"]),
    }


def _post_selection_gold() -> dict[str, dict[str, Any]]:
    """Read scoring-only values after the complete product capture is sealed."""

    lock = json.loads(SOURCES["input_lock"].read_text(encoding="utf-8"))
    locked = {str(row["id"]): row for row in lock["cases"]}
    output = {}
    for case_id in CASE_IDS:
        row = locked[case_id]
        full_rows = [
            dict(value)
            for value in row.get("gold_articles") or ()
            if value.get("corpus_status") == "present"
        ]
        output[case_id] = {
            "coordinates": _coordinates(full_rows),
            "gold_articles": full_rows,
            "reference_answer": str(row.get("reference_answer") or ""),
        }
    return output


def _post_selection_parent_headline() -> dict[str, int]:
    """Read the parent gold headline only after product capture is sealed."""

    parent = json.loads(SOURCES["parent_run"].read_text(encoding="utf-8"))
    arm = parent["summary"]["by_arm"]["semantic-pipeline"]
    return {
        "baseline_gold_hits": int(arm["gold_hits"]),
        "baseline_gold_total": int(arm["gold_total"]),
    }


def _discard_reasons(
    before: Iterable[tuple[str, object]],
    after: Iterable[tuple[str, object]],
    reason: str,
) -> list[tuple[tuple[str, object], str]]:
    after_set = set(after)
    return [(value, reason) for value in before if value not in after_set]


def _baseline_row(case: Mapping[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    source = list(case["baseline"])
    recorder = ledger.StageLedgerRecorder(
        str(case["case_id"]), "baseline", ledger.identity_canonicalizer,
    )
    recorder.record_stage("baseline-source", "source", source)
    recorder.record_stage(
        "baseline-present",
        "present",
        source,
        parent_stage_ids=("baseline-source",),
    )
    return {
        "case_id": case["case_id"],
        "number": case["number"],
        "suite": case["suite"],
        "question": case["question"],
        "arm_id": "baseline",
        "capture": recorder.capture(),
        "source_coordinates": [list(value) for value in source],
        "seeded_floor_coordinates": [list(value) for value in source],
        "final_coordinates": [list(value) for value in source],
        "added_coordinates": [],
        "lost_source_coordinates": [],
        "grounding": None,
        "search": {
            "status": "frozen-adr-0103-run-007",
            "active_family_ids": [],
            "compiled_hints": {"family_ids": [], "predicates": []},
            "legal_assessments": [],
            "stages": {},
        },
        "product_calls": [],
        "usage": _usage([]),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "candidate_end_to_end_ms": 0.0,
        "product_error": "",
        "decisive_coordinates_visible_to_product": False,
    }


def _raw_selected_coordinates(
    grounding: Mapping[str, Any],
) -> list[tuple[str, object]]:
    """Resolve raw binder selections to supplied-menu coordinates only.

    This snapshot precedes deterministic signature/provenance/cap validation.
    Concept bindings intentionally do not become article seeds.
    """

    candidates = grounding.get("candidates") or {}
    menu = candidates.get("menu") or ()
    by_id = {str(row.get("id")): row for row in menu}
    raw = (grounding.get("binding") or {}).get("raw_output") or {}
    output: list[tuple[str, object]] = []
    for field in ("assertion_selections", "evidence_selections"):
        for selection in raw.get(field) or ():
            if not isinstance(selection, Mapping):
                continue
            candidate = by_id.get(str(selection.get("candidate_id") or ""))
            if candidate is None:
                continue
            for value in candidate.get("coordinates") or [candidate["coordinate"]]:
                coordinate = (str(value[0]), value[1])
                if coordinate not in output:
                    output.append(coordinate)
    return output


def _empty_grounding(question: str, error: str) -> dict[str, Any]:
    return {
        "schema_version": "query-grounding-plan-v2",
        "question": question,
        "plan": {
            "mentions": [],
            "rejected_mentions": [],
            "family_hypotheses": [],
            "predicate_hypotheses": [],
            "expansion_terms": {"exact": [], "fulltext": [], "vector": []},
            "raw_output": None,
        },
        "candidates": {
            "menu": [],
            "all_candidates": [],
            "canonical_candidates": [],
            "assertion_candidates": [],
            "evidence_candidates": [],
            "channel_coordinates": {"reverse": [], "fulltext": [], "vector": []},
            "reverse_queries": [],
            "fulltext_queries": [],
            "vector_queries": [],
            "channel_errors": [{"channel": "runner", "query": "", "error": error}],
            "elapsed_ms": 0.0,
        },
        "binding": {
            "raw_output": None,
            "concept_bindings": [],
            "assertion_selections": [],
            "evidence_selections": [],
            "bound": [],
            "validated": [],
            "rejected": [],
            "unresolved_mention_ids": [],
            "menu_external_id_count": 0,
            "signature_rejection_count": 0,
            "cross_menu_rejection_count": 0,
            "canonical_unknown_id_count": 0,
        },
        "bound_coordinates": [],
        "validated_coordinates": [],
        "validation": {
            "anchored_mentions": 0,
            "rejected_unanchored_mentions": 0,
            "menu_external_id_count": 0,
            "signature_rejection_count": 0,
            "cross_menu_rejection_count": 0,
            "canonical_unknown_id_count": 0,
            "canonical_generated_id_count": 0,
        },
        "latency_ms": {
            "planner_api_wall": 0.0,
            "candidate_generation": 0.0,
            "binder_api_wall": 0.0,
            "total": 0.0,
        },
        "runner_error": error,
    }


def _candidate_row(
    case: Mapping[str, Any],
    index: object,
    snapshot: object,
    registry: object,
    recording_llm: RecordingLLM,
) -> dict[str, Any]:
    started = time.perf_counter()
    source = list(case["baseline"])
    call_start = len(recording_llm.audit)
    product_error = ""
    try:
        grounding = query_grounding.ground_query(
            recording_llm,
            index,
            snapshot,
            registry,
            str(case["question"]),
            menu_cap=MENU_CAP,
        )
    except Exception as exc:  # preserve a complete, explicitly failed run receipt
        product_error = f"{type(exc).__name__}: {exc}"[:1000]
        grounding = _empty_grounding(str(case["question"]), product_error)

    channels = grounding["candidates"]["channel_coordinates"]
    reverse = _coordinates(channels.get("reverse") or ())
    fulltext = _coordinates(channels.get("fulltext") or ())
    vector = _coordinates(channels.get("vector") or ())
    raw_bound = _raw_selected_coordinates(grounding)
    validated = _coordinates(grounding.get("validated_coordinates") or ())
    seeded_floor = query_grounding.insert_grounded_seeds(
        source,
        validated,
        protected_prefix=PROTECTED_PREFIX,
        seed_cap=SEED_CAP,
    )
    plan = grounding.get("plan") or {}
    family_hints = [
        str(row.get("family_id"))
        for row in plan.get("family_hypotheses") or ()
    ]
    predicate_hints = [
        str(row.get("predicate"))
        for row in plan.get("predicate_hypotheses") or ()
    ]
    try:
        selected, search = legal_semantic_search.plan_semantic_coordinates(
            index,
            str(case["question"]),
            seeded_floor,
            snapshot=snapshot,
            cap=FINAL_CAP,
            family_hints=family_hints,
            predicate_hints=predicate_hints,
        )
        final = _coordinates(row["coordinate"] for row in selected)
    except Exception as exc:  # no retry; retain the validated floor as failed fallback
        closure_error = f"{type(exc).__name__}: {exc}"[:1000]
        product_error = "; ".join(value for value in (product_error, closure_error) if value)
        final = list(seeded_floor[:FINAL_CAP])
        search = {
            "enabled": True,
            "status": "runner-error",
            "fallback": closure_error,
            "active_family_ids": family_hints,
            "allowed_predicates": predicate_hints,
            "compiled_hints": {
                "family_ids": family_hints,
                "predicates": predicate_hints,
            },
            "legal_assessments": [],
            "stages": {
                "typed-closure": [list(value) for value in seeded_floor],
                "bundle-rerank": [list(value) for value in final],
                "candidate-present": [list(value) for value in final],
            },
            "elapsed_ms": 0.0,
        }

    recorder = ledger.StageLedgerRecorder(
        str(case["case_id"]),
        "schema-grounded-planner",
        ledger.identity_canonicalizer,
    )
    recorder.record_stage("candidate-source", "source", source)
    reverse_after = _union(source, reverse)
    fulltext_after = _union(source, fulltext)
    vector_after = _union(source, vector)
    recorder.record_stage(
        "reverse-match",
        "retrieve",
        reverse_after,
        parent_stage_ids=("candidate-source",),
    )
    recorder.record_stage(
        "fulltext-match",
        "retrieve",
        fulltext_after,
        parent_stage_ids=("candidate-source",),
    )
    recorder.record_stage(
        "vector-match",
        "retrieve",
        vector_after,
        parent_stage_ids=("candidate-source",),
    )
    channel_union = _union(source, reverse, fulltext, vector)
    recorder.record_stage(
        "channel-union",
        "union",
        channel_union,
        parent_stage_ids=(
            "candidate-source", "reverse-match", "fulltext-match", "vector-match",
        ),
    )
    # A closed-menu selection should already be a subset of the channel union.
    # If a corrupt candidate violates that invariant, exclude it and retain the
    # explicit count in the row instead of letting a filter stage create data.
    channel_union_set = set(channel_union)
    raw_outside_union = [value for value in raw_bound if value not in channel_union_set]
    closed_after = _union(
        source,
        (value for value in raw_bound if value in channel_union_set),
    )
    recorder.record_stage(
        "closed-candidate-bind",
        "filter",
        closed_after,
        parent_stage_ids=("channel-union",),
        discard_reasons=_discard_reasons(
            channel_union,
            closed_after,
            "not_selected_by_closed_candidate_binder",
        ),
    )
    signature_after = _union(source, validated)
    recorder.record_stage(
        "signature-validate",
        "filter",
        signature_after,
        parent_stage_ids=("closed-candidate-bind",),
        discard_reasons=_discard_reasons(
            closed_after,
            signature_after,
            "rejected_by_signature_provenance_or_seed_cap",
        ),
    )
    semantic_stages = {
        key: _coordinates(value)
        for key, value in (search.get("stages") or {}).items()
    }
    typed = semantic_stages.get("typed-closure", list(seeded_floor))
    recorder.record_stage(
        "typed-closure",
        "expand",
        typed,
        parent_stage_ids=("signature-validate",),
        discard_reasons=_discard_reasons(
            signature_after,
            typed,
            "not_in_typed_closure_candidate_set",
        ),
    )
    recorder.record_stage(
        "bundle-rerank",
        "rerank",
        final,
        parent_stage_ids=("typed-closure",),
        discard_reasons=_discard_reasons(
            typed,
            final,
            "not_selected_by_bounded_bundle_rerank",
        ),
    )
    recorder.record_stage(
        "candidate-present",
        "present",
        final,
        parent_stage_ids=("bundle-rerank",),
    )
    calls = recording_llm.audit[call_start:]
    source_set = set(source)
    final_set = set(final)
    return {
        "case_id": case["case_id"],
        "number": case["number"],
        "suite": case["suite"],
        "question": case["question"],
        "arm_id": "schema-grounded-planner",
        "capture": recorder.capture(),
        "source_coordinates": [list(value) for value in source],
        "seeded_floor_coordinates": [list(value) for value in seeded_floor],
        "raw_bound_coordinates": [list(value) for value in raw_bound],
        "validated_coordinates": [list(value) for value in validated],
        "raw_bound_outside_channel_union": [list(value) for value in raw_outside_union],
        "final_coordinates": [list(value) for value in final],
        "added_coordinates": [list(value) for value in final if value not in source_set],
        "lost_source_coordinates": [list(value) for value in source if value not in final_set],
        "grounding": grounding,
        "search": search,
        "product_calls": calls,
        "usage": _usage(calls),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "candidate_end_to_end_ms": round((time.perf_counter() - started) * 1000, 3),
        "product_error": product_error,
        "decisive_coordinates_visible_to_product": False,
    }


def _prewarm(index: object, registry: object) -> dict[str, Any]:
    """Load static local retrieval assets outside measured case latency."""

    started = time.perf_counter()
    timings: dict[str, float] = {}

    step = time.perf_counter()
    lx = lexicon_mod.current(index)
    timings["lexicon_ms"] = round((time.perf_counter() - step) * 1000, 3)

    step = time.perf_counter()
    section_vectors = vector_mod.current()
    timings["section_vector_index_ms"] = round(
        (time.perf_counter() - step) * 1000, 3,
    )

    step = time.perf_counter()
    canonical_vectors = spanparts.cached_term_lexicon()
    timings["canonical_term_vector_index_ms"] = round(
        (time.perf_counter() - step) * 1000, 3,
    )

    step = time.perf_counter()
    probe = embedding.encode_one("법률 질의 임베딩 사전 준비")
    timings["embedding_model_ms"] = round((time.perf_counter() - step) * 1000, 3)

    step = time.perf_counter()
    canonical_catalog = query_grounding._canonical_catalog(index, registry)
    timings["tier1_grounding_catalog_ms"] = round(
        (time.perf_counter() - step) * 1000, 3,
    )
    section_dir = vector_mod.sections_dir()
    term_vector_path = lexicon_mod.lexicon_dir() / "terms.npz"
    assets = {
        "section_vectors": _asset_receipt(section_dir / "vectors.npz"),
        "section_metadata": _asset_receipt(section_dir / "meta.jsonl"),
        "term_vectors": _asset_receipt(term_vector_path),
    }
    timings["total_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return {
        "timings": timings,
        "lexicon_cache": dict(lx.cache_stats),
        "section_vector_rows": (
            len(section_vectors.rows) if section_vectors is not None else 0
        ),
        "canonical_term_vectors_loaded": canonical_vectors is not None,
        "embedding_dimension": (len(probe) if probe is not None else 0),
        "tier1_grounding_surfaces": len(canonical_catalog["by_surface"]),
        "assets": assets,
        "external_api_calls": 0,
    }


def _pre_gold_audit(
    rows: Sequence[Mapping[str, Any]],
    recording_llm: RecordingLLM,
    *,
    runtime_sources_match: bool,
) -> dict[str, Any]:
    """Hard-gate scoring until the frozen product-call contract is complete."""

    candidates = [
        row for row in rows if row.get("arm_id") == "schema-grounded-planner"
    ]
    calls = list(recording_llm.audit)
    expected_kinds = [
        "rag.query_grounding.plan",
        "rag.query_grounding.bind",
    ]
    call_kinds_by_case = {
        str(row["case_id"]): [str(call.get("kind") or "")
                              for call in row.get("product_calls") or ()]
        for row in candidates
    }
    provider_errors = [
        {
            "index": index,
            "kind": call.get("kind"),
            "provider_error": (call.get("provider") or {}).get("error"),
            "wrapper_error": call.get("wrapper_error"),
        }
        for index, call in enumerate(calls, 1)
        if (call.get("provider") or {}).get("error") or call.get("wrapper_error")
    ]
    checks = {
        "runtime_sources_unchanged": runtime_sources_match,
        "exactly_16_candidate_rows": len(candidates) == len(CASE_IDS),
        "exactly_32_logical_calls": len(calls) == 2 * len(CASE_IDS),
        "exact_plan_then_bind_per_case": (
            tuple(call_kinds_by_case) == CASE_IDS
            and all(value == expected_kinds for value in call_kinds_by_case.values())
        ),
        "provider_errors_zero": not provider_errors,
        "runner_errors_zero": all(not row.get("product_error") for row in candidates),
        "requested_model_exact": all(
            call.get("requested_model") == MODEL for call in calls
        ),
        "provider_model_exact": all(
            (call.get("provider") or {}).get("model") == MODEL for call in calls
        ),
        "anthropic_backend_exact": all(
            call.get("backend") == "anthropic" for call in calls
        ),
        "transport_retries_disabled": all(
            call.get("transport_max_retries") == 0 for call in calls
        ),
    }
    return {
        "schema_version": "adr-0105-pre-gold-audit-v1",
        "checked_at": _now(),
        "checks": checks,
        "passed": all(checks.values()),
        "logical_call_count": len(calls),
        "http_attempt_upper_bound": len(calls),
        "transport_max_retries": 0,
        "call_kinds_by_case": call_kinds_by_case,
        "provider_errors": provider_errors,
        "runner_errors": {
            str(row["case_id"]): str(row.get("product_error") or "")
            for row in candidates if row.get("product_error")
        },
    }


def _stage_by_id(row: Mapping[str, Any], stage_id: str) -> Mapping[str, Any]:
    for stage in row["grade"]["stages"]:
        if stage["stage_id"] == stage_id:
            return stage
    raise KeyError(stage_id)


def _stage_table(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "| arm | stage | kind | before | + | - | after | gold before→after | recall | reason |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        for stage in row["grade"]["stages"]:
            reasons = ", ".join(
                f"{key}:{value}"
                for key, value in stage["discard_reason_counts"].items()
            ) or "-"
            recall = stage["golden_recall"]
            lines.append(
                f"| `{row['arm_id']}` | `{stage['stage_id']}` | {stage['kind']} | "
                f"{stage['before_count']} | {stage['added_count']} | "
                f"{stage['discarded_count']} | {stage['after_count']} | "
                f"{stage['gold_before']}→{stage['gold_after']} | "
                f"{recall if recall is not None else 'n/a'} | {reasons} |"
            )
    return "\n".join(lines)


def _case_failure_type(candidate: Mapping[str, Any]) -> str:
    if candidate["gold_hits"] == candidate["gold_total"]:
        return "none"
    union = _stage_by_id(candidate, "channel-union")
    if union["gold_after"] < candidate["gold_total"]:
        return "retrieval_miss"
    return "governing_rule_selection"


def _question_markdown(
    case: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    scoring: Mapping[str, Any],
    corpus_total: int,
    ledger_path: Path,
) -> str:
    baseline = next(row for row in rows if row["arm_id"] == "baseline")
    candidate = next(
        row for row in rows if row["arm_id"] == "schema-grounded-planner"
    )
    product_input = {
        "baseline_source_coordinates": baseline["source_coordinates"],
        "candidate_seeded_floor_coordinates": candidate["seeded_floor_coordinates"],
        "candidate_grounding": candidate["grounding"],
        "candidate_semantic_search": candidate["search"],
        "candidate_product_capture": candidate["capture"],
    }
    scale = {
        "corpus_total": corpus_total,
        "before_filter": _stage_by_id(candidate, "channel-union")["after_count"],
        "after_filter": _stage_by_id(candidate, "signature-validate")["after_count"],
        "presented": len(candidate["final_coordinates"]),
    }
    calls = {
        "baseline": [],
        "schema-grounded-planner": candidate["product_calls"],
    }
    exact_gold_stage_receipts = {
        str(row["arm_id"]): [
            {
                "stage_id": stage["stage_id"],
                "gold_before_identities": stage["gold_before_identities"],
                "gold_added_identities": stage["gold_added_identities"],
                "discarded_gold": stage["discarded_gold"],
                "gold_after_identities": stage["gold_after_identities"],
            }
            for stage in row["grade"]["stages"]
        ]
        for row in rows
    }
    verdict_rows = (
        "| run-001 | baseline | "
        f"{baseline['gold_hits']}/{baseline['gold_total']} | exact coordinate | "
        f"{'none' if baseline['gold_hits'] == baseline['gold_total'] else 'retrieval_miss'} |\n"
        "| run-001 | schema-grounded-planner | "
        f"{candidate['gold_hits']}/{candidate['gold_total']} | exact coordinate | "
        f"{_case_failure_type(candidate)} |"
    )
    return f"""# 질문 {int(case['number']):03d} — {case['case_id']}

## 1. 실행 메타

- ADR/experiment/run: `{ADR_ID}` / `{EXPERIMENT_ID}` / `{RUN_ID}`
- 실행 시각(UTC): `{_now()}`
- 원본 상태: `exact`
- 제품·중간 호출 모델: `{MODEL}`
- 오프라인 평가: `deterministic exact-coordinate grader` (LLM 없음)
- 실행 arm: `baseline`, `schema-grounded-planner`
- decisive coordinates visible to product: `false`

## 2. 사용자 질문 원문

```text
{case['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

```text
{scoring['reference_answer']}
```

```json
{json.dumps(scoring['gold_articles'], ensure_ascii=False, indent=2, sort_keys=True)}
```

## 4. 제품 입력을 구성한 원값

### 회수 전 전체·후보·제시 규모

```json
{json.dumps(scale, ensure_ascii=False, indent=2, sort_keys=True)}
```

### 회수 좌표·조문·정의·Wiki·관계 — 전체

```json
{json.dumps(product_input, ensure_ascii=False, indent=2, sort_keys=True)}
```

### 회수·탈락 단계 원장 — run·arm별

{_stage_table(rows)}

```json
{json.dumps({'stage_ledger_artifact': str(ledger_path.relative_to(ROOT)), 'gold_visible_to_product': False}, ensure_ascii=False, indent=2, sort_keys=True)}
```

### 단계별 decisive gold 좌표와 정확한 탈락 영수증

```json
{json.dumps(exact_gold_stage_receipts, ensure_ascii=False, indent=2, sort_keys=True)}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

baseline은 모델 호출이 없고, candidate의 planner/binder 실제 system, user, schema,
provider 원응답, structured output, usage, TTFT와 총 지연은 아래에 호출 순서대로 있다.

```json
{json.dumps(calls, ensure_ascii=False, indent=2, sort_keys=True)}
```

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

이 실험의 중간 호출은 위 5절의 `rag.query_grounding.plan` 및
`rag.query_grounding.bind` 두 건뿐이다. Router/compiler/verifier/repair와
최종 답변 생성 LLM 호출은 없다.

```json
{json.dumps([{'order': index + 1, 'kind': call['kind'], 'requested_model': call['requested_model'], 'provider_model': (call.get('provider') or {}).get('model')} for index, call in enumerate(candidate['product_calls'])], ensure_ascii=False, indent=2, sort_keys=True)}
```

## 7. 채점 호출과 반복 판정

```json
{{"mode":"deterministic exact canonical article-root membership","judge_calls":[],"repeats":1}}
```

## 8. 사례 최종 판정

| run | arm | 정답 좌표 적중 | 핵심 근거 | 실패 유형 |
|---|---|---:|---|---|
{verdict_rows}

- 신규 정답 좌표: `{candidate['candidate_only']}`
- 회귀 정답 좌표: `{candidate['baseline_only']}`
- 사람이 확인한 직접 원인: `미판정 — 이 파일은 좌표 원장과 자동 분류만 기록`
- 다음 분기 가설: `channel-union과 signature/final 단계의 gold 차이를 사례별 검토`
"""


def _summarize(
    rows: Sequence[Mapping[str, Any]],
    snapshot: object,
    load: object,
    prewarm: Mapping[str, Any],
    wall_ms: float,
) -> dict[str, Any]:
    by_arm_rows = {
        arm: [row for row in rows if row["arm_id"] == arm]
        for arm in ARMS
    }
    by_arm: dict[str, dict[str, Any]] = {}
    for arm, arm_rows in by_arm_rows.items():
        hits = sum(int(row["gold_hits"]) for row in arm_rows)
        total = sum(int(row["gold_total"]) for row in arm_rows)
        elapsed = [float(row["candidate_end_to_end_ms"]) for row in arm_rows]
        by_arm[arm] = {
            "cases": len(arm_rows),
            "gold_hits": hits,
            "gold_total": total,
            "golden_recall": hits / total if total else None,
            "all_gold_cases": sum(row["gold_hits"] == row["gold_total"] for row in arm_rows),
            "presented_total": sum(len(row["final_coordinates"]) for row in arm_rows),
            "presented_mean": statistics.mean(
                len(row["final_coordinates"]) for row in arm_rows
            ),
            "presented_p50": statistics.median(
                len(row["final_coordinates"]) for row in arm_rows
            ),
            "presented_p95": _presented_p95(
                [len(row["final_coordinates"]) for row in arm_rows]
            ),
            "presented_max": max(len(row["final_coordinates"]) for row in arm_rows),
            "added_total": sum(len(row["added_coordinates"]) for row in arm_rows),
            "source_lost_total": sum(
                len(row["lost_source_coordinates"]) for row in arm_rows
            ),
            "candidate_end_to_end_p50_ms": statistics.median(elapsed),
            "candidate_end_to_end_p95_ms": _percentile(elapsed, 0.95),
            "cap_20_passed": all(
                len(row["final_coordinates"]) <= FINAL_CAP for row in arm_rows
            ),
        }

    candidates = by_arm_rows["schema-grounded-planner"]
    baseline = by_arm_rows["baseline"]
    calls = [call for row in candidates for call in row["product_calls"]]
    api_usage = _usage(calls)
    api_usage_by_kind = {
        kind: _usage([call for call in calls if call.get("kind") == kind])
        for kind in (
            "rag.query_grounding.plan",
            "rag.query_grounding.bind",
        )
    }
    baseline_only = sum(len(row["baseline_only"]) for row in candidates)
    candidate_only = sum(len(row["candidate_only"]) for row in candidates)
    paired = {
        "candidate_only": candidate_only,
        "baseline_only": baseline_only,
        "both": by_arm["baseline"]["gold_hits"] - baseline_only,
    }
    paired["neither"] = (
        by_arm["baseline"]["gold_total"]
        - paired["both"] - baseline_only - candidate_only
    )

    accepted_span_errors = []
    accepted_id_errors = []
    channel_error_count = 0
    attempted_external_ids = 0
    canonical_generated_ids = 0
    signature_rejections = 0
    cross_menu_rejections = 0
    canonical_unknown_ids = 0
    rejected_unanchored = 0
    raw_outside_union = 0
    candidate_counts = Counter()
    selection_counts = Counter()
    call_count_by_case = {}
    for row in candidates:
        grounding = row["grounding"]
        question = row["question"]
        for mention in grounding["plan"]["mentions"]:
            start, end = int(mention["start"]), int(mention["end"])
            if question[start:end] != mention["surface"]:
                accepted_span_errors.append({
                    "case_id": row["case_id"], "mention": mention,
                })
        menu_ids = {
            str(item["id"]) for item in grounding["candidates"]["menu"]
        }
        for selection in [
            *grounding["binding"]["concept_bindings"],
            *grounding["binding"]["assertion_selections"],
            *grounding["binding"]["evidence_selections"],
        ]:
            if str(selection["candidate_id"]) not in menu_ids:
                accepted_id_errors.append({
                    "case_id": row["case_id"], "selection": selection,
                })
        candidate_counts.update(
            item["candidate_kind"]
            for item in grounding["candidates"]["menu"]
        )
        selection_counts.update({
            "concept_bindings": len(grounding["binding"]["concept_bindings"]),
            "assertion_selections": len(grounding["binding"]["assertion_selections"]),
            "evidence_selections": len(grounding["binding"]["evidence_selections"]),
            "validated_seeds": len(grounding["validated_coordinates"]),
        })
        validation = grounding["validation"]
        attempted_external_ids += int(validation["menu_external_id_count"])
        canonical_generated_ids += int(validation["canonical_generated_id_count"])
        signature_rejections += int(validation["signature_rejection_count"])
        cross_menu_rejections += int(validation["cross_menu_rejection_count"])
        canonical_unknown_ids += int(validation["canonical_unknown_id_count"])
        rejected_unanchored += int(validation["rejected_unanchored_mentions"])
        channel_error_count += len(grounding["candidates"]["channel_errors"])
        raw_outside_union += len(row["raw_bound_outside_channel_union"])
        call_count_by_case[row["case_id"]] = len(row["product_calls"])

    provider_models = sorted({
        str((call.get("provider") or {}).get("model") or "") for call in calls
    })
    requested_models = sorted({str(call.get("requested_model") or "") for call in calls})
    success_checks = {
        "candidate_at_least_20_of_29": by_arm[
            "schema-grounded-planner"
        ]["gold_hits"] >= 20,
        "frozen_baseline_is_15_of_29": (
            by_arm["baseline"]["gold_hits"] == 15
            and by_arm["baseline"]["gold_total"] == 29
        ),
        "baseline_hit_loss_zero": baseline_only == 0,
        "final_cap_20": by_arm["schema-grounded-planner"]["cap_20_passed"],
        "exactly_32_product_calls": api_usage["calls"] == 32,
        "exactly_two_calls_per_case": all(
            value == 2 for value in call_count_by_case.values()
        ) and len(call_count_by_case) == 16,
        "product_api_errors_zero": api_usage["errors"] == 0,
        "runner_errors_zero": all(not row["product_error"] for row in candidates),
        "requested_model_exact_haiku": requested_models == [MODEL],
        "provider_model_exact_haiku": provider_models == [MODEL],
        "accepted_query_mentions_round_trip": not accepted_span_errors,
        "accepted_candidate_ids_in_menu": not accepted_id_errors,
        "canonical_generated_ids_zero": canonical_generated_ids == 0,
        "cross_menu_rejections_zero": cross_menu_rejections == 0,
        "canonical_unknown_ids_zero": canonical_unknown_ids == 0,
        "raw_bound_coordinates_inside_channel_union": raw_outside_union == 0,
        "candidate_e2e_p95_at_most_20000ms": by_arm[
            "schema-grounded-planner"
        ]["candidate_end_to_end_p95_ms"] <= 20000,
        "decisive_coordinates_hidden": all(
            row["decisive_coordinates_visible_to_product"] is False for row in rows
        ),
    }
    corpus_total = len(snapshot.ports_by_article)
    before_filter = {
        "baseline": sum(
            _stage_by_id(row, "baseline-source")["after_count"] for row in baseline
        ),
        "schema-grounded-planner": sum(
            _stage_by_id(row, "channel-union")["after_count"] for row in candidates
        ),
    }
    after_filter = {
        "baseline": before_filter["baseline"],
        "schema-grounded-planner": sum(
            _stage_by_id(row, "signature-validate")["after_count"] for row in candidates
        ),
    }
    retrieval_accounting = {
        "corpus_total": corpus_total,
        "before_filter": before_filter,
        "after_filter": after_filter,
        "presented_total": {
            arm: value["presented_total"] for arm, value in by_arm.items()
        },
        "presented_mean": {
            arm: value["presented_mean"] for arm, value in by_arm.items()
        },
        "presented_p50": {
            arm: value["presented_p50"] for arm, value in by_arm.items()
        },
        "presented_p95": {
            arm: value["presented_p95"] for arm, value in by_arm.items()
        },
        "golden_recall": {
            arm: value["golden_recall"] for arm, value in by_arm.items()
        },
        "selectivity": {
            arm: value["presented_total"] / (corpus_total * len(CASE_IDS))
            for arm, value in by_arm.items()
        },
    }
    candidate_stage_totals = {
        stage_id: {
            "after_count": sum(
                _stage_by_id(row, stage_id)["after_count"] for row in candidates
            ),
            "gold_added": sum(
                _stage_by_id(row, stage_id)["gold_added"] for row in candidates
            ),
            "gold_discarded": sum(
                _stage_by_id(row, stage_id)["gold_discarded"] for row in candidates
            ),
            "gold_after": sum(
                _stage_by_id(row, stage_id)["gold_after"] for row in candidates
            ),
        }
        for stage_id in STAGES["schema-grounded-planner"]
    }
    return {
        "graph_generation": snapshot.generation_id,
        "graph_content_sha256": snapshot.content_sha256,
        "graph_cards": corpus_total,
        "semantic_cards": len(snapshot.semantic_cards),
        "cold_load": load.as_dict(),
        "static_prewarm": dict(prewarm),
        "by_arm": by_arm,
        "paired": paired,
        "api_usage": api_usage,
        "api_usage_by_kind": api_usage_by_kind,
        "api_models": {
            "required": MODEL,
            "requested": requested_models,
            "provider": provider_models,
        },
        "call_count_by_case": call_count_by_case,
        "grounding": {
            "candidate_menu_counts": dict(sorted(candidate_counts.items())),
            "selection_counts": dict(sorted(selection_counts.items())),
            "accepted_span_errors": accepted_span_errors,
            "accepted_menu_id_errors": accepted_id_errors,
            "attempted_external_candidate_ids": attempted_external_ids,
            "canonical_generated_ids": canonical_generated_ids,
            "cross_menu_rejections": cross_menu_rejections,
            "canonical_unknown_ids": canonical_unknown_ids,
            "signature_rejections": signature_rejections,
            "rejected_unanchored_mentions": rejected_unanchored,
            "channel_errors": channel_error_count,
            "raw_bound_outside_channel_union": raw_outside_union,
        },
        "retrieval_accounting": retrieval_accounting,
        "candidate_stage_totals": candidate_stage_totals,
        "success_checks": success_checks,
        "passed": all(success_checks.values()),
        "llm_calls": api_usage["calls"],
        "input_tokens": api_usage["input_tokens"],
        "output_tokens": api_usage["output_tokens"],
        "wall_ms": round(wall_ms, 3),
    }


def run(adr: Path, graph_root: Path) -> dict[str, Any]:
    run_started = time.perf_counter()
    source_hashes = _verify_sources()
    runtime_sources_initial = _verify_runtime_sources(graph_root)
    public_cases, parent_meta = _public_cases()

    cold_started = time.perf_counter()
    index = index_mod.Index.load()
    legal_graph_store.reset_cache()
    load = legal_graph_store.current_for(index, root=graph_root)
    if load.snapshot is None:
        raise ValueError(f"Legal Graph snapshot unavailable: {load.as_dict()}")
    snapshot = load.snapshot
    if (
        snapshot.generation_id != parent_meta["graph_generation"]
        or snapshot.content_sha256 != parent_meta["graph_content_sha256"]
    ):
        raise ValueError(
            "Legal Graph differs from frozen ADR-0103 run-007: "
            f"{snapshot.generation_id}/{snapshot.content_sha256}"
        )
    registry_started = time.perf_counter()
    registry = conceptfirst.load_registry()
    registry_load_ms = (time.perf_counter() - registry_started) * 1000
    cold_load_wall_ms = (time.perf_counter() - cold_started) * 1000
    prewarm = _prewarm(index, registry)
    prewarm["index_graph_registry_wall_ms"] = round(cold_load_wall_ms, 3)
    prewarm["registry_load_ms"] = round(registry_load_ms, 3)
    runtime_sources_after_prewarm = _verify_runtime_sources(graph_root)
    if runtime_sources_after_prewarm != runtime_sources_initial:
        raise RuntimeError("frozen runtime sources changed during local prewarm")

    llm_mod.load_env()
    if not llm_mod.available():
        raise RuntimeError(f"product LLM unavailable: {llm_mod.MISSING_HINT}")
    if llm_mod.backend() != "anthropic":
        raise RuntimeError(f"product backend must be anthropic: {llm_mod.backend()}")
    real_llm = llm_mod.LLM(model=MODEL)
    if real_llm.model != MODEL or real_llm.backend != "anthropic":
        raise RuntimeError(
            f"LLM initialization policy mismatch: "
            f"{real_llm.backend}/{real_llm.model}"
        )
    # The SDK default retries twice and would make 32 logical invocations an
    # unknown number of HTTP attempts.  This isolated runner uses one attempt
    # per invocation and records the policy in every receipt.
    import anthropic
    real_llm._client = anthropic.Anthropic(timeout=120.0, max_retries=0)
    recording_llm = RecordingLLM(real_llm)

    product_rows: list[dict[str, Any]] = []
    for ordinal, case in enumerate(public_cases, 1):
        product_rows.append(_baseline_row(case))
        product_rows.append(_candidate_row(
            case, index, snapshot, registry, recording_llm,
        ))
        print(
            f"[{ordinal:02d}/{len(public_cases):02d}] {case['case_id']} "
            f"calls={len(recording_llm.audit)}",
            file=sys.stderr,
            flush=True,
        )

    runtime_seal_error = ""
    try:
        runtime_sources_sealed = _verify_runtime_sources(graph_root)
    except Exception as exc:
        runtime_sources_sealed = {}
        runtime_seal_error = f"{type(exc).__name__}: {exc}"[:2000]
    runtime_sources_match = (
        not runtime_seal_error
        and runtime_sources_sealed == runtime_sources_initial
    )
    pre_gold_audit = _pre_gold_audit(
        product_rows,
        recording_llm,
        runtime_sources_match=runtime_sources_match,
    )

    # Seal and persist the complete product-only artifact before opening the
    # scoring fields.  The rows below contain no gold/reference answer values.
    registry_path = conceptfirst.registry_path()
    product_capture = {
        "schema_version": "adr-0105-product-capture-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "created_at": _now(),
        "model": MODEL,
        "api_transport": {
            "backend": "anthropic",
            "sdk_version": getattr(anthropic, "__version__", "unknown"),
            "max_retries": 0,
            "timeout_seconds": 120.0,
            "logical_calls_equal_http_attempt_upper_bound": True,
        },
        "source_hashes": source_hashes,
        "runtime_sources_initial": runtime_sources_initial,
        "runtime_sources_after_prewarm": runtime_sources_after_prewarm,
        "runtime_sources_sealed": runtime_sources_sealed,
        "runtime_source_seal_error": runtime_seal_error,
        "graph": {
            "root": str(graph_root),
            "pointer_sha256": _sha(graph_root / "CURRENT.json"),
            "generation_id": snapshot.generation_id,
            "content_sha256": snapshot.content_sha256,
        },
        "tier1_registry": {
            "path": str(registry_path.relative_to(ROOT)),
            "sha256": _sha(registry_path),
            "active_concepts": len(registry.active_concepts),
            "active_assertions": len(registry.active_assertions),
        },
        "prewarm": prewarm,
        "pre_gold_audit": pre_gold_audit,
        "decisive_coordinates_visible_to_product": False,
        "rows": product_rows,
    }
    product_capture_path = adr / "artifacts/product-capture-run-001.json"
    _write(product_capture_path, product_capture)

    if not pre_gold_audit["passed"]:
        failure_path = adr / "artifacts/pre-gold-failure-run-001.json"
        _write(failure_path, {
            "schema_version": "adr-0105-pre-gold-failure-v1",
            "adr_id": ADR_ID,
            "experiment_id": EXPERIMENT_ID,
            "run_id": RUN_ID,
            "created_at": _now(),
            "gold_opened": False,
            "product_capture_path": str(product_capture_path.relative_to(ROOT)),
            "product_capture_sha256": _sha(product_capture_path),
            "pre_gold_audit": pre_gold_audit,
            "runtime_source_seal_error": runtime_seal_error,
        })
        raise RuntimeError(
            "pre-gold audit failed; product capture was preserved and scoring "
            f"was not opened: {failure_path}"
        )

    # Product selection is sealed and on disk.  Scoring values are first read
    # and joined below this line.
    scoring_by_case = _post_selection_gold()
    parent_headline = _post_selection_parent_headline()
    baseline_by_case = {
        row["case_id"]: row for row in product_rows if row["arm_id"] == "baseline"
    }
    graded_ledgers = []
    for row in product_rows:
        scoring = scoring_by_case[row["case_id"]]
        grade = ledger.grade_capture(
            row["capture"],
            scoring["coordinates"],
            canonicalizer=ledger.identity_canonicalizer,
        )
        ledger.validate_graded_ledger(
            grade, expected_stage_ids=STAGES[row["arm_id"]],
        )
        row["grade"] = grade
        row["gold_hits"] = grade["stages"][-1]["gold_after"]
        row["gold_total"] = len(scoring["coordinates"])
        baseline_set = set(_coordinates(
            baseline_by_case[row["case_id"]]["final_coordinates"],
        ))
        final_set = set(_coordinates(row["final_coordinates"]))
        row["candidate_only"] = [
            list(value) for value in scoring["coordinates"]
            if value not in baseline_set and value in final_set
        ]
        row["baseline_only"] = [
            list(value) for value in scoring["coordinates"]
            if value in baseline_set and value not in final_set
        ]
        graded_ledgers.append(grade)

    run_ledger = ledger.build_run_artifact(RUN_ID, graded_ledgers, STAGES)
    experiment_ledger = ledger.build_experiment_artifact(
        ADR_ID, EXPERIMENT_ID, [run_ledger],
    )
    ledger_path = adr / "artifacts/retrieval-stage-ledger-run-001.json"
    _write(ledger_path, experiment_ledger)

    summary = _summarize(
        product_rows,
        snapshot,
        load,
        prewarm,
        (time.perf_counter() - run_started) * 1000,
    )
    summary["pre_gold_audit"] = pre_gold_audit
    summary["success_checks"]["pre_gold_audit_passed"] = bool(
        pre_gold_audit["passed"]
    )
    summary["passed"] = all(summary["success_checks"].values())
    # Cross-check the frozen parent headline after the independent exact join.
    summary["parent_cross_check"] = {
        "expected_hits": parent_headline["baseline_gold_hits"],
        "expected_total": parent_headline["baseline_gold_total"],
        "observed_hits": summary["by_arm"]["baseline"]["gold_hits"],
        "observed_total": summary["by_arm"]["baseline"]["gold_total"],
        "matched": (
            summary["by_arm"]["baseline"]["gold_hits"]
            == parent_headline["baseline_gold_hits"]
            and summary["by_arm"]["baseline"]["gold_total"]
            == parent_headline["baseline_gold_total"]
        ),
    }
    if not summary["parent_cross_check"]["matched"]:
        summary["passed"] = False

    summary_path = adr / "artifacts/summary-run-001.json"
    _write(summary_path, summary)
    run_value = {
        "schema_version": "adr-0105-run-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "created_at": _now(),
        "source_hashes": source_hashes,
        "runtime_sources": runtime_sources_sealed,
        "pre_gold_audit": pre_gold_audit,
        "api_transport": product_capture["api_transport"],
        "graph_pointer_sha256": _sha(graph_root / "CURRENT.json"),
        "graph_manifest_sha256": _sha(
            graph_root / "generations" / snapshot.generation_id / "manifest.json"
        ),
        "tier1_registry_sha256": _sha(registry_path),
        "computed_post_selection": True,
        "decisive_coordinates_visible_to_product": False,
        "product_calls": len(recording_llm.audit),
        "judge_calls": 0,
        "load": load.as_dict(),
        "prewarm": prewarm,
        "summary": summary,
        "rows": product_rows,
        "product_capture": {
            "path": str(product_capture_path.relative_to(ROOT)),
            "sha256": _sha(product_capture_path),
        },
        "stage_ledger": {
            "path": str(ledger_path.relative_to(ROOT)),
            "sha256": _sha(ledger_path),
        },
        "summary_artifact": {
            "path": str(summary_path.relative_to(ROOT)),
            "sha256": _sha(summary_path),
        },
    }
    run_path = adr / "artifacts/run-001.json"
    _write(run_path, run_value)

    rows_by_case = {
        case["case_id"]: [
            row for row in product_rows if row["case_id"] == case["case_id"]
        ]
        for case in public_cases
    }
    for case in public_cases:
        question_path = adr / "실험" / (
            f"질문-{int(case['number']):03d}-{case['case_id']}.md"
        )
        question_path.write_text(
            _question_markdown(
                case,
                rows_by_case[case["case_id"]],
                scoring_by_case[case["case_id"]],
                len(snapshot.ports_by_article),
                ledger_path,
            ),
            encoding="utf-8",
        )
    return {
        "run": str(run_path),
        "product_capture": str(product_capture_path),
        "stage_ledger": str(ledger_path),
        "summary_artifact": str(summary_path),
        "summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--adr",
        type=Path,
        default=(
            ROOT / "docs/adr/ADR-0105-schema-constrained-query-grounding-api"
        ),
    )
    parser.add_argument(
        "--graph-root",
        type=Path,
        default=ROOT / "data/legal_graph",
    )
    args = parser.parse_args()
    print(json.dumps(
        run(args.adr.resolve(), args.graph_root.resolve()),
        ensure_ascii=False,
        sort_keys=True,
    ))


if __name__ == "__main__":
    main()
