#!/usr/bin/env python3
"""ADR-0106 deterministic trace for one structured THRESHOLD query.

No LLM is called.  The run measures the current semantic landing exactly, then
temporarily removes only the in-process landing cap to expose the target's
uncapped rank.  Source files and MAIN wiring are never changed.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import sys
import time


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
for key, relative in (
    ("STRUCTURE_STORE", "01_DATA/structure"),
    ("STRUCTURE_CUSTOM_DIR", "01_DATA/custom"),
    ("GLOSSARY_STORE", "01_DATA/glossary.json"),
    ("RAG_LINKS_STORE", "01_DATA/links.json"),
    ("RAG_DELEGATION_STORE", "01_DATA/delegation.json"),
    ("RAG_LAW_INDEX_STORE", "01_DATA/law_index.json"),
    ("RAG_ENGINE_RULES", "01_DATA/rules/engine.json"),
):
    os.environ.setdefault(key, str(ROOT / relative))

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag import legal_graph_store, legal_semantic_search  # noqa: E402
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402
from lawrag.core.rag.query_family_runtime import default_registry  # noqa: E402


ADR_ID = "ADR-0106"
EXPERIMENT_ID = "ADR-0106-experiment-v1"
RUN_ID = "run-002"
CASE_ID = "threshold-structured-001"
ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0106-threshold-structured-search-trace"
INPUT = ADR / "artifacts/frozen-input.json"
GRAPH_CURRENT = ROOT / "01_DATA/legal_graph/CURRENT.json"
EXPECTED_HASHES = {
    "input": "d9cf651897f185b3165d8ef7f70bcfaf7a679f36e83ecef6b2ba7c13f16e03bf",
    "graph_current": "418571f80d6d49ecdab9e8c2c6e2bede7221e5836f2a3a567100ee861c0c9161",
    "graph_manifest": "75ac4958668e5da99cfce02d2aa3d294182155a2da500e2753897a39703a9f73",
    "semantic_search_code": "522b0b4fbc733ff0cb6fa94a0d60bb1a5a1483b880365748aba8ebc6e0e698ed",
    "graph_store_code": "f8ba0e0495fa18771dc25c2e93c72f0d2945fdfdb1f2a1deaf56f260b8cde9ed",
    "family_runtime_code": "606fc1822ae31bd8c0821f9358b9ae5a67b00a07836cd3ab1f06b1d907da7d78",
    "cm_gold": "d3c707caa114dec379201c2ba9d2177b0c6bc17ceb4ae9394df1397e9dbfccb1",
}
DECLARED_STAGES = {
    "baseline": [
        "corpus-source", "raw-posting-union", "baseline-present",
    ],
    "current-semantic-search": [
        "corpus-source", "raw-posting-union", "term-family-eligible",
        "semantic-landing-cap32", "typed-closure", "bundle-rerank-cap20",
        "current-present",
    ],
    "exhaustive-posting-audit": [
        "corpus-source", "raw-posting-union", "term-family-eligible",
        "exhaustive-landing-order", "exhaustive-present",
    ],
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _json_safe(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    raise TypeError(f"unsupported JSON value: {type(value)!r}")


def _coordinates(values) -> list[tuple[str, int]]:
    result: list[tuple[str, int]] = []
    for value in values:
        if isinstance(value, dict):
            result.append((str(value["doc_id"]), int(value["node"])))
        else:
            result.append((str(value[0]), int(value[1])))
    return list(dict.fromkeys(result))


def _valid_coordinate(index, snapshot, card) -> tuple[str, int] | None:
    coordinate = (
        str(card.article_root.document_id), int(card.article_root.node_id),
    )
    if coordinate not in snapshot.ports_by_article:
        return None
    view = index.docs.get(coordinate[0])
    if view is None or coordinate[1] not in view.by_id or not view.is_current:
        return None
    return coordinate


def _discard(before, after, reason: str):
    after_set = set(after)
    return [(coordinate, reason) for coordinate in before if coordinate not in after_set]


def _candidate_row(index, coordinate, candidate, rank: int) -> dict:
    view = index.docs[coordinate[0]]
    return {
        "rank": rank,
        "coordinate": list(coordinate),
        "document": view.name,
        "path": view.path(coordinate[1]),
        "score": round(candidate.score, 6),
        "matched_terms": sorted(candidate.matched_terms),
        "family_ids": sorted(candidate.family_ids),
        "semantic_types": sorted(candidate.semantic_types),
        "coverage_keys": sorted(candidate.coverage_keys),
        "card_ids": sorted(candidate.card_ids),
        "protected": candidate.protected,
    }


def _article_text(view, node_id: int) -> str:
    node = view.by_id[node_id]
    span = node.get("span") or [0, 0]
    parts = []
    for block_index in range(span[0], max(span[1], span[0] + 1)):
        block = view.block_by_idx.get(block_index)
        text = str((block or {}).get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def _excerpt(text: str, needles: tuple[str, ...], cap: int = 280) -> str:
    positions = [text.find(value) for value in needles if text.find(value) >= 0]
    if not positions:
        return text[:cap]
    start = max(0, min(positions) - cap // 3)
    return text[start:start + cap]


def _literal_scan(index, corpus_coordinates):
    buckets = {
        "quantity_exact": [],
        "actor_exact": [],
        "condition_phrase_exact": [],
        "quantity_and_actor": [],
        "quantity_actor_affiliate": [],
        "quantity_actor_affiliate_possession": [],
    }
    examples = []
    for coordinate in corpus_coordinates:
        view = index.docs[coordinate[0]]
        text = _article_text(view, coordinate[1])
        quantity = "100분의 10" in text
        actor = "주관회사" in text
        phrase = "계열회사 보유분" in text
        affiliate = "계열회사" in text
        possession = "보유" in text
        checks = {
            "quantity_exact": quantity,
            "actor_exact": actor,
            "condition_phrase_exact": phrase,
            "quantity_and_actor": quantity and actor,
            "quantity_actor_affiliate": quantity and actor and affiliate,
            "quantity_actor_affiliate_possession": (
                quantity and actor and affiliate and possession
            ),
        }
        for key, matched in checks.items():
            if matched:
                buckets[key].append(coordinate)
        if checks["quantity_actor_affiliate"]:
            examples.append({
                "coordinate": list(coordinate),
                "document": view.name,
                "path": view.path(coordinate[1]),
                "excerpt": _excerpt(
                    text, ("100분의 10", "주관회사", "계열회사"),
                ),
            })
    return {
        key: {
            "count": len(values),
            "coordinates": [list(value) for value in values],
        }
        for key, values in buckets.items()
    } | {"quantity_actor_affiliate_examples": examples}


def _capture_arm(
    arm_id: str,
    raw_coordinates,
    eligible_coordinates,
    landing_coordinates,
    closure_coordinates,
    final_coordinates,
    *,
    raw_occurrences: int,
    eligible_occurrences: int,
):
    recorder = ledger.StageLedgerRecorder(
        CASE_ID, arm_id, ledger.identity_canonicalizer,
    )
    recorder.record_stage("corpus-source", "source", [])
    recorder.record_stage(
        "raw-posting-union", "retrieve", raw_coordinates,
        parent_stage_ids=("corpus-source",),
        after_occurrence_count=raw_occurrences,
    )
    if arm_id == "baseline":
        recorder.record_stage(
            "baseline-present", "present", raw_coordinates,
            parent_stage_ids=("raw-posting-union",),
            after_occurrence_count=raw_occurrences,
        )
        return recorder.capture()
    recorder.record_stage(
        "term-family-eligible", "filter", eligible_coordinates,
        parent_stage_ids=("raw-posting-union",),
        discard_reasons=_discard(
            raw_coordinates, eligible_coordinates,
            "semantic_card_failed_min_term_or_family_compatibility",
        ),
        after_occurrence_count=eligible_occurrences,
    )
    if arm_id == "exhaustive-posting-audit":
        recorder.record_stage(
            "exhaustive-landing-order", "rerank", landing_coordinates,
            parent_stage_ids=("term-family-eligible",),
            discard_reasons=_discard(
                eligible_coordinates, landing_coordinates,
                "invalid_or_unscored_semantic_article",
            ),
        )
        recorder.record_stage(
            "exhaustive-present", "present", landing_coordinates,
            parent_stage_ids=("exhaustive-landing-order",),
        )
        return recorder.capture()
    recorder.record_stage(
        "semantic-landing-cap32", "rerank", landing_coordinates,
        parent_stage_ids=("term-family-eligible",),
        discard_reasons=_discard(
            eligible_coordinates, landing_coordinates,
            "outside_semantic_landing_cap_32",
        ),
    )
    recorder.record_stage(
        "typed-closure", "expand", closure_coordinates,
        parent_stage_ids=("semantic-landing-cap32",),
        discard_reasons=_discard(
            landing_coordinates, closure_coordinates,
            "not_retained_by_typed_closure",
        ),
    )
    recorder.record_stage(
        "bundle-rerank-cap20", "select", final_coordinates,
        parent_stage_ids=("typed-closure",),
        discard_reasons=_discard(
            closure_coordinates, final_coordinates,
            "not_selected_by_bounded_bundle_rerank_cap_20",
        ),
    )
    recorder.record_stage(
        "current-present", "present", final_coordinates,
        parent_stage_ids=("bundle-rerank-cap20",),
    )
    return recorder.capture()


def run() -> dict:
    started = time.perf_counter()
    frozen = json.loads(INPUT.read_text("utf-8"))
    pointer = json.loads(GRAPH_CURRENT.read_text("utf-8"))
    graph_manifest = ROOT / "01_DATA/legal_graph" / pointer["manifest"]
    source_paths = {
        "input": INPUT,
        "graph_current": GRAPH_CURRENT,
        "graph_manifest": graph_manifest,
        "semantic_search_code": Path(__import__("lawrag").__file__).resolve().parent / "core/rag/legal_semantic_search.py",
        "graph_store_code": Path(__import__("lawrag").__file__).resolve().parent / "core/rag/legal_graph_store.py",
        "family_runtime_code": Path(__import__("lawrag").__file__).resolve().parent / "core/rag/query_family_runtime.py",
        "cm_gold": ROOT / "01_DATA/review/cm_core_e2e_v2.json",
    }
    source_hashes = {key: _sha(path) for key, path in source_paths.items()}
    for key, expected in EXPECTED_HASHES.items():
        if source_hashes[key] != expected:
            raise ValueError(
                f"frozen source hash mismatch: {key} "
                f"{source_hashes[key]} != {expected}"
            )

    index = index_mod.Index.load()
    legal_graph_store.reset_cache()
    load = legal_graph_store.current_for(index)
    if load.snapshot is None:
        raise ValueError(f"Legal Graph unavailable: {load.as_dict()}")
    snapshot = load.snapshot
    if snapshot.generation_id != pointer["generation_id"]:
        raise ValueError("loaded Legal Graph generation differs from frozen pointer")

    question = str(frozen["search_question"])
    family_hints = frozenset(str(value) for value in frozen["family_hints"])
    target = (
        str(frozen["target_coordinate"]["doc_id"]),
        int(frozen["target_coordinate"]["node"]),
    )
    registry = default_registry()
    frame, hypotheses, active, family_ids, predicates = (
        legal_semantic_search._active_families(  # noqa: SLF001
            question, snapshot, registry,
        )
    )
    family_ids = frozenset(set(family_ids) | set(family_hints))
    landing_family_ids = legal_semantic_search._landing_families(  # noqa: SLF001
        family_ids,
    )
    query_terms = legal_semantic_search._query_terms(  # noqa: SLF001
        question, snapshot,
    )

    corpus_coordinates = sorted(
        coordinate for coordinate in snapshot.ports_by_article
        if coordinate[0] in index.docs
        and coordinate[1] in index.docs[coordinate[0]].by_id
        and index.docs[coordinate[0]].is_current
    )
    raw_card_indexes = sorted({
        card_index
        for term in query_terms
        for card_index in snapshot.semantic_postings.get(term, ())
    })
    raw_cards = [snapshot.semantic_cards[value] for value in raw_card_indexes]
    raw_coordinates = sorted({
        coordinate for card in raw_cards
        if (coordinate := _valid_coordinate(index, snapshot, card)) is not None
    })
    term_stats = []
    for term in query_terms:
        indexes = snapshot.semantic_postings.get(term, ())
        coordinates = {
            coordinate for card_index in indexes
            if (coordinate := _valid_coordinate(
                index, snapshot, snapshot.semantic_cards[card_index],
            )) is not None
        }
        term_stats.append({
            "term": term,
            "semantic_card_occurrences": len(indexes),
            "canonical_article_count": len(coordinates),
        })

    eligible_cards = snapshot.semantic_candidates(
        query_terms,
        family_ids=landing_family_ids,
        min_term_matches=2,
    )
    eligible_coordinates = sorted({
        coordinate for card in eligible_cards
        if (coordinate := _valid_coordinate(index, snapshot, card)) is not None
    })
    current_landing = legal_semantic_search._landing(  # noqa: SLF001
        index, snapshot, query_terms, family_ids,
        frozenset(), frozenset(), question,
    )
    current_landing_coordinates = list(current_landing)

    original_landing_cap = legal_semantic_search.LANDING_CAP
    try:
        legal_semantic_search.LANDING_CAP = max(
            original_landing_cap, len(eligible_coordinates) + 1,
        )
        exhaustive_landing = legal_semantic_search._landing(  # noqa: SLF001
            index, snapshot, query_terms, family_ids,
            frozenset(), frozenset(), question,
        )
    finally:
        legal_semantic_search.LANDING_CAP = original_landing_cap
    exhaustive_coordinates = list(exhaustive_landing)

    selected, plan_meta = legal_semantic_search.plan_semantic_coordinates(
        index, question, [], snapshot=snapshot, cap=20,
        registry=registry, family_hints=family_hints,
    )
    stages = {
        key: _coordinates(value)
        for key, value in (plan_meta.get("stages") or {}).items()
    }
    plan_landing = stages.get("semantic-landing", current_landing_coordinates)
    if plan_landing != current_landing_coordinates:
        raise ValueError("direct current landing and plan landing differ")
    closure_coordinates = stages.get("typed-closure", plan_landing)
    final_coordinates = stages.get(
        "candidate-present",
        _coordinates([row["coordinate"] for row in selected]),
    )

    target_cards = snapshot.semantics_for_article(target)
    target_card_rows = [{
        "card_id": card.card_id,
        "source_node": card.source.node_id,
        "semantic_type": card.semantic_type,
        "family_ids": list(card.family_ids),
        "terms": list(card.terms),
        "matched_query_terms": sorted(set(query_terms).intersection(card.terms)),
        "coverage_keys": list(card.coverage_keys),
        "label": card.label,
    } for card in target_cards]
    target_rank = (
        exhaustive_coordinates.index(target) + 1
        if target in exhaustive_coordinates else None
    )
    exhaustive_rows = [
        _candidate_row(index, coordinate, candidate, rank)
        for rank, (coordinate, candidate) in enumerate(
            exhaustive_landing.items(), 1,
        )
    ]
    current_rows = [
        _candidate_row(index, coordinate, candidate, rank)
        for rank, (coordinate, candidate) in enumerate(
            current_landing.items(), 1,
        )
    ]
    literal_scan = _literal_scan(index, corpus_coordinates)

    captures = [
        _capture_arm(
            "baseline", raw_coordinates, [], [], [], [],
            raw_occurrences=len(raw_card_indexes), eligible_occurrences=0,
        ),
        _capture_arm(
            "current-semantic-search", raw_coordinates,
            eligible_coordinates, plan_landing, closure_coordinates,
            final_coordinates, raw_occurrences=len(raw_card_indexes),
            eligible_occurrences=len(eligible_cards),
        ),
        _capture_arm(
            "exhaustive-posting-audit", raw_coordinates,
            eligible_coordinates, exhaustive_coordinates, [], [],
            raw_occurrences=len(raw_card_indexes),
            eligible_occurrences=len(eligible_cards),
        ),
    ]
    graded = [
        ledger.grade_capture(
            capture, [target], canonicalizer=ledger.identity_canonicalizer,
        )
        for capture in captures
    ]
    for value in graded:
        ledger.validate_graded_ledger(
            value, expected_stage_ids=DECLARED_STAGES[value["arm_id"]],
        )
    run_ledger = ledger.build_run_artifact(RUN_ID, graded, DECLARED_STAGES)
    experiment_ledger = ledger.build_experiment_artifact(
        ADR_ID, EXPERIMENT_ID, [run_ledger],
    )
    ledger_path = ADR / f"artifacts/retrieval-stage-ledger-{RUN_ID}.json"
    _write(ledger_path, experiment_ledger)

    target_trace = {
        "coordinate": list(target),
        "raw_posting": target in raw_coordinates,
        "term_family_eligible": target in eligible_coordinates,
        "exhaustive_rank": target_rank,
        "current_landing_cap32": target in plan_landing,
        "typed_closure": target in closure_coordinates,
        "final_cap20": target in final_coordinates,
        "semantic_card_count": len(target_cards),
        "semantic_cards": target_card_rows,
    }
    hypothesis_confirmed = (
        target_trace["term_family_eligible"]
        and target_rank is not None
        and target_rank > original_landing_cap
        and not target_trace["current_landing_cap32"]
        and len(eligible_coordinates) > original_landing_cap
    )
    summary = {
        "corpus_canonical_articles": len(corpus_coordinates),
        "semantic_cards_total": len(snapshot.semantic_cards),
        "query_terms": list(query_terms),
        "active_family_ids": sorted(family_ids),
        "landing_family_ids": sorted(landing_family_ids),
        "raw_posting_card_occurrences": len(raw_card_indexes),
        "raw_posting_canonical_articles": len(raw_coordinates),
        "term_family_eligible_card_occurrences": len(eligible_cards),
        "term_family_eligible_canonical_articles": len(eligible_coordinates),
        "current_landing_count": len(plan_landing),
        "typed_closure_count": len(closure_coordinates),
        "final_present_count": len(final_coordinates),
        "exhaustive_landing_count": len(exhaustive_coordinates),
        "target": target_trace,
        "hypothesis_confirmed": hypothesis_confirmed,
        "llm_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    run_value = {
        "schema_version": "adr-0106-threshold-search-trace-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "frozen_input": frozen,
        "source_hashes": source_hashes,
        "graph_generation": snapshot.generation_id,
        "graph_content_sha256": snapshot.content_sha256,
        "graph_load": load.as_dict(),
        "query_frame": {
            "id": frame.id,
            "slots": {key: list(value) for key, value in frame.slots.items()},
            "requested_goals": list(frame.requested_goals),
            "hypotheses": [value.to_dict() for value in hypotheses],
            "active_family_ids": sorted(family_ids),
            "allowed_predicates": sorted(predicates),
        },
        "term_stats": term_stats,
        "literal_scan": literal_scan,
        "current_landing_ranked": current_rows,
        "exhaustive_landing_ranked": exhaustive_rows,
        "current_plan": _json_safe({
            "selected": selected,
            "meta": plan_meta,
        }),
        "summary": summary,
        "stage_ledger": {
            "path": str(ledger_path.relative_to(ROOT)),
            "sha256": _sha(ledger_path),
        },
        "computed_post_selection": True,
        "gold_visible_to_product": False,
        "product_calls": 0,
        "judge_calls": 0,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    run_path = ADR / f"artifacts/{RUN_ID}.json"
    _write(run_path, run_value)
    return {
        "run": str(run_path.relative_to(ROOT)),
        "ledger": str(ledger_path.relative_to(ROOT)),
        "summary": summary,
        "elapsed_ms": run_value["elapsed_ms"],
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
