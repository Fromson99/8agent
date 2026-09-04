"""Add-only, generation-pinned legal research integration.

This module joins the repository's previously independent query grounding,
legal-system entry, semantic graph, research-method and evidence-state layers.
It is deliberately a retrieval/evidence compiler, not a legal decision maker.

The incoming LegalClosure result is an immutable floor.  Auxiliary failures
may make the candidate arm less helpful, but they can never delete that floor.
Every final addition is a current closed-corpus article whose source text was
checked again before it is presented.  Relation discovery alone is never
treated as verified evidence or as permission to state a legal conclusion.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import re
from threading import RLock
import time
from typing import Any, Iterable, Mapping, Sequence

from lawrag.core.legal_graph.behavior import RELATION_BEHAVIOR_POLICIES
from lawrag.core.legal_graph.model import RelationPredicate
from lawrag.core.rag import (
    assertionfirst,
    conceptfirst,
    delegation as delegation_mod,
    general_search,
    legal_coordinates,
    lexicon as lexicon_mod,
    query_grounding,
    relation_navigation,
    relations as relations_mod,
    rules as rules_mod,
    vector as vector_mod,
)
from lawrag.core.rag.answer import SECTION_CHARS, Section
from lawrag.core.rag.experiments import retrieval_stage_ledger as stage_ledger
from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_graph_store import LegalGraphSnapshot, current_for
from lawrag.core.rag.legal_research_llm_selector import (
    ANTHROPIC_BACKEND,
    ANTHROPIC_SCHEMA_PROFILE,
    GENOS_BACKEND,
    OPENROUTER_BACKEND,
    QWEN_NATIVE_SCHEMA_PROFILE,
    QWEN_REDUCED_SCHEMA_PROFILE,
    StructuredOutputProfile,
    ThreadLocalStructuredRecorder,
    branches_from_query_plan,
    onsite_qwen_profile,
    plan_question,
)
from lawrag.core.rag.legal_research_methods import (
    AdaptivePagePolicy,
    CoverageState as MethodCoverageState,
    DependencyRelation,
    FinalEvidenceCandidate,
    ResearchCursor,
    compile_final_evidence,
    plan_research_step,
)
from lawrag.core.rag.legal_research_state import (
    CandidateProvenance,
    ResearchCoordinate,
    add_candidate_origin,
    assess_subsumption,
    build_source_span_verification,
    compile_research_evidence,
    promote_candidate,
    seed_candidate,
    verify_candidate,
)
from lawrag.core.rag.legal_semantic_search import plan_semantic_coordinates
from lawrag.core.rag.legal_system_entry import scope_alignment
from lawrag.core.rag.legal_system_map import (
    LegalSystemEntryRuntime,
    load_legal_system_runtime,
)


MAX_FINAL_EVIDENCE = 32
DEFAULT_PRESENTATION_TARGET = 28
MAX_INTERNAL_CANDIDATES = 96
_TOKEN = re.compile(r"[0-9A-Za-z가-힣%]{2,}")
_CACHE_LOCK = RLock()
_RESOURCE_CACHE: dict[tuple[Any, ...], tuple[LegalSystemEntryRuntime, LegalGraphSnapshot]] = {}


def _files_fingerprint(paths: Iterable[Path]) -> str:
    """Content fingerprint for immutable offline indexes used by both arms."""

    digest = hashlib.sha256()
    count = 0
    for path in sorted({Path(value) for value in paths}, key=lambda value: value.name):
        if not path.is_file():
            continue
        count += 1
        digest.update(path.name.encode("utf-8"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest() if count else ""


@dataclass(slots=True)
class _Candidate:
    coordinate: tuple[str, int]
    score: float
    branch_id: str
    source_order: int
    origins: set[CandidateProvenance] = field(default_factory=set)
    relation_ids: set[str] = field(default_factory=set)
    coverage_keys: set[str] = field(default_factory=set)
    matched: set[str] = field(default_factory=set)


class _ProvidedClient:
    """Expose an existing product client through the selector contract.

    The golden runner wraps the real LLM to capture raw provider receipts.  A
    second provider client here would escape that receipt boundary, so this
    adapter delegates through the supplied object while exposing the backend
    and zero-logical-retry contract expected by the provider-neutral selector.
    """

    def __init__(self, llm: Any, backend: str, model: str) -> None:
        self._llm = llm
        self.backend = backend
        self.model = model
        self.transport_max_retries = 0
        self.log = getattr(llm, "log", None)
        if not isinstance(self.log, list):
            raise TypeError("integrated research LLM must expose an append-only log")

    def structured(self, *args: Any, **kwargs: Any) -> Any:
        return self._llm.structured(*args, **kwargs)


def _provided_profile(llm: Any) -> tuple[_ProvidedClient, StructuredOutputProfile]:
    nested = getattr(llm, "real", None)
    backend = str(
        getattr(llm, "backend", "")
        or getattr(nested, "backend", "")
    )
    model = str(getattr(llm, "model", "") or getattr(nested, "model", ""))
    if not backend or not model:
        raise TypeError("integrated research cannot identify LLM backend/model")
    if backend == ANTHROPIC_BACKEND:
        profile = StructuredOutputProfile(
            backend=backend,
            model=model,
            schema_profile=ANTHROPIC_SCHEMA_PROFILE,
        )
    elif backend == GENOS_BACKEND:
        reduced = os.environ.get("GENOS_LLM_SCHEMA_PROFILE", "reduced").strip().lower() != "native"
        profile = onsite_qwen_profile(model, reduced_schema=reduced)
    elif backend == OPENROUTER_BACKEND:
        reduced = os.environ.get("OPENROUTER_SCHEMA_PROFILE", "native").strip().lower() == "reduced"
        profile = StructuredOutputProfile(
            backend=backend,
            model=model,
            schema_profile=(QWEN_REDUCED_SCHEMA_PROFILE if reduced else QWEN_NATIVE_SCHEMA_PROFILE),
        )
    else:
        raise TypeError(f"unsupported integrated research backend: {backend}")
    return _ProvidedClient(llm, backend, model), profile


def _question_plan(llm: Any, question: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if llm is None:
        return query_grounding.sanitize_plan(question, {}), {
            "status": "fallback", "reason": "llm_unavailable", "receipts": [],
        }
    try:
        client, profile = _provided_profile(llm)
        recorder = ThreadLocalStructuredRecorder(lambda: client, profile=profile)
        plan = plan_question(recorder, question)
        return plan, {"status": "planned", "reason": "", "receipts": list(recorder.receipts)}
    except Exception as exc:
        return query_grounding.sanitize_plan(question, {}), {
            "status": "fallback",
            "reason": f"{type(exc).__name__}: {exc}"[:500],
            "receipts": [],
        }


def _resource_key(index: Index, graph_root: Path | str | None) -> tuple[Any, ...]:
    scope = None if index.scope is None else tuple(sorted(index.scope))
    return (
        str(index.authority_generation), str(index.authority_as_of), scope,
        str(Path(graph_root).resolve()) if graph_root is not None else "DEFAULT",
    )


def _resources(index: Index, graph_root: Path | str | None) \
        -> tuple[LegalSystemEntryRuntime, LegalGraphSnapshot]:
    key = _resource_key(index, graph_root)
    # Single-flight the relatively expensive atlas/catalog/graph admission.
    # Golden and API callers may enter from several worker threads at once;
    # allowing each miss to build its own atlas wastes memory and makes the
    # first batch four times more expensive even though the graph store itself
    # is immutable and process-cached.
    with _CACHE_LOCK:
        cached = _RESOURCE_CACHE.get(key)
        if cached is not None:
            return cached
        kwargs = (
            {"legal_graph_root": Path(graph_root)}
            if graph_root is not None else {}
        )
        runtime = load_legal_system_runtime(index, semantic_cards=True, **kwargs)
        loaded = current_for(index, root=graph_root)
        snapshot = loaded.snapshot
        if snapshot is None:
            raise RuntimeError(
                "current Legal Graph unavailable: "
                f"status={loaded.status}, reasons={list(loaded.reasons)}"
            )
        if (
            snapshot.authority_generation != index.authority_generation
            or runtime.system_map.authority_generation != index.authority_generation
            or runtime.system_map.authority_as_of != index.authority_as_of
        ):
            raise RuntimeError("integrated research authority generation mismatch")
        # Force one verified shared snapshot before timed per-question planning.
        if runtime.semantic_cards is not None:
            runtime.semantic_cards.preload()
        _RESOURCE_CACHE[key] = (runtime, snapshot)
        return runtime, snapshot


def clear_resource_cache() -> None:
    """Testing/operations hook; no corpus or graph data is mutated."""

    with _CACHE_LOCK:
        _RESOURCE_CACHE.clear()


def preload_resources(
    index: Index, graph_root: Path | str | None = None,
) -> dict[str, Any]:
    """Admit every shared lazy read model before request workers start.

    This is provider-free.  The native baseline also uses lexical postings,
    references, relation bundles, the closed lexicon, and the section vector
    index.  Building them on this single caller thread prevents workers from
    observing partial caches and keeps cold admission outside per-case timing.
    """

    started = time.perf_counter()
    postings = index.postings()
    reference_edges = index.ref_edges()
    cross_edges, cross_pending = index.cross_refs()
    index.cross_from("")  # materialize the immutable cross-reference adjacency
    relation_bundle = relations_mod.build(index)
    closed_lexicon = lexicon_mod.current(index)
    vector_index = vector_mod.current()
    registry = conceptfirst.load_registry(conceptfirst.registry_path())
    assertion_index = assertionfirst.current(registry)
    general_corpus = general_search._corpus(index)
    runtime, snapshot = _resources(index, graph_root)
    lexicon_cache_fingerprint = _files_fingerprint(
        lexicon_mod.lexicon_dir().glob("terms*.npz")
    )
    vector_index_fingerprint = _files_fingerprint((
        vector_mod.sections_dir() / "vectors.npz",
        vector_mod.sections_dir() / "meta.jsonl",
    ))
    runtime_input_fingerprint = _files_fingerprint((
        conceptfirst.registry_path(),
        delegation_mod.delegation_path(),
        rules_mod.rules_file(),
        rules_mod.breaker_file(),
    ))
    return {
        "schema_version": "integrated-legal-research-preload-v1",
        "status": "ready",
        "authority_generation": index.authority_generation,
        "authority_as_of": index.authority_as_of,
        "catalog_version": runtime.system_map.catalog_version,
        "law_index_sha256": runtime.system_map.law_index_sha256,
        "effective_dates_sha256": runtime.system_map.effective_dates_sha256,
        "profiles_sha256": runtime.system_map.profiles_sha256,
        "legal_graph_generation": snapshot.generation_id,
        "legal_graph_content_sha256": snapshot.content_sha256,
        "legal_graph_pointer_sha256": snapshot.pointer_sha256,
        "article_count": len(snapshot.ports_by_article),
        "baseline_posting_terms": len(postings),
        "baseline_posting_blocks": int(index._n_blocks),
        "reference_edges": sum(len(rows) for rows in reference_edges.values()),
        "cross_reference_edges": len(cross_edges),
        "cross_reference_pending": len(cross_pending),
        "relation_sections": len(relation_bundle.sections),
        "lexicon_terms": len(closed_lexicon.names),
        "lexicon_cached_terms": int(closed_lexicon.cache_stats.get("cached") or 0),
        "vector_rows": len(vector_index.rows) if vector_index is not None else 0,
        "lexicon_cache_fingerprint": lexicon_cache_fingerprint,
        "vector_index_fingerprint": vector_index_fingerprint,
        "runtime_input_fingerprint": runtime_input_fingerprint,
        "active_concepts": len(registry.active_concepts),
        "active_assertions": len(registry.active_assertions),
        "assertion_concept_phrases": len(assertion_index.concept_phrases),
        "general_search_blocks": int(general_corpus.block_count),
        "lexicon_compile_missing_enabled": (
            os.environ.get("RAG_LEXICON_COMPILE_MISSING", "0") == "1"
        ),
        "provider_calls": 0,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def fallback_to_floor(
    index: Index,
    floor_sections: Sequence[Section],
    *,
    case_id: str,
    arm_id: str,
    reason: str,
) -> tuple[list[Section], dict[str, Any]]:
    """Build a complete measured fallback trace without losing the floor."""

    floor = list(floor_sections)
    coordinates = [
        coordinate
        for section in floor
        if (coordinate := _canonical(index, (section.doc_id, section.node))) is not None
    ]
    coordinates = list(dict.fromkeys(coordinates))
    snapshots: dict[str, list[tuple[str, int]]] = {
        "question-source": [],
        "closed-grounding-retrieve": [],
        "legal-system-route-retrieve": [],
        "semantic-card-retrieve": [],
        "baseline-floor-union": coordinates,
    }
    skipped: dict[str, str] = {}
    for stage in (
        "closed-grounding-retrieve", "legal-system-route-retrieve",
        "semantic-card-retrieve",
    ):
        skipped[stage] = reason
    for stage in (
        "typed-legal-relation-expand", "wiki-method-dependency-expand",
        "adaptive-gap-retrieve", "provenance-canonicalize",
        "actor-scope-filter", "verified-coverage-select",
        "compiled-evidence-present",
    ):
        snapshots[stage] = coordinates
        skipped[stage] = reason
    for number, section in enumerate(floor, 1):
        section.n = number
    return floor, {
        "enabled": True,
        "status": "fallback",
        "fallback": reason,
        "before_count": len(coordinates),
        "after_count": len(coordinates),
        "added_count": 0,
        "baseline_floor_preserved": True,
        "direct_conclusion_allowed": False,
        "deterministic_planning_ms": 0.0,
        "validation": {
            "closed_id_violations": [],
            "generation_violations": [reason],
            "verified_evidence_violations": [
                f"{doc_id}:{node_id}" for doc_id, node_id in coordinates
            ],
        },
        "stage_capture": _stage_capture(
            index, case_id, arm_id, snapshots, skipped
        ),
        "errors": [{"stage": "runtime", "error": reason}],
    }


def _canonical(index: Index, value: Sequence[Any]) -> tuple[str, int] | None:
    if len(value) != 2:
        return None
    doc_id, node_id = str(value[0]), value[1]
    view = index.docs.get(doc_id)
    if (
        view is None or node_id not in view.by_id or not view.is_current
        or not index.in_scope(doc_id)
    ):
        return None
    root = legal_coordinates.article_root(view, node_id)
    if isinstance(root, bool) or not isinstance(root, int) or root not in view.by_id:
        return None
    return doc_id, root


def _section(index: Index, coordinate: tuple[str, int], n: int, *, origin: str) -> Section:
    doc_id, node_id = coordinate
    view = index.docs[doc_id]
    node = view.by_id[node_id]
    return Section(
        n=n,
        doc_id=doc_id,
        doc=view.name,
        node=node_id,
        path=view.path(node_id) or view.name,
        page=node.get("page"),
        kind=f"통합조사({origin})",
        matched=origin,
        text=view.section_outline(node, cap=SECTION_CHARS),
    )


def _source_text(index: Index, coordinate: tuple[str, int]) -> str:
    view = index.docs[coordinate[0]]
    node = view.by_id[coordinate[1]]
    return str(view.section_text(dict(node), cap=10**9) or "")


def _candidate_id(coordinate: tuple[str, int]) -> str:
    raw = f"{coordinate[0]}:{coordinate[1]}".encode("utf-8")
    return "research-candidate-" + hashlib.sha256(raw).hexdigest()[:24]


def _add(
    rows: dict[tuple[str, int], _Candidate],
    coordinate: tuple[str, int] | None,
    *,
    score: float,
    branch_id: str,
    origin: CandidateProvenance,
    relation_ids: Iterable[str] = (),
    coverage_keys: Iterable[str] = (),
    matched: Iterable[str] = (),
) -> None:
    if coordinate is None:
        return
    row = rows.get(coordinate)
    if row is None:
        row = _Candidate(
            coordinate=coordinate,
            score=float(score),
            branch_id=branch_id,
            source_order=len(rows),
        )
        rows[coordinate] = row
    elif float(score) > row.score:
        row.score = float(score)
        row.branch_id = branch_id
    row.origins.add(origin)
    row.relation_ids.update(str(value) for value in relation_ids if str(value))
    row.coverage_keys.update(str(value) for value in coverage_keys if str(value))
    row.matched.update(str(value) for value in matched if str(value))


def _relation_kind(predicate: str) -> str | None:
    if predicate == RelationPredicate.USES_DEFINITION.value:
        return "USES_DEFINITION"
    if predicate in {
        RelationPredicate.QUALIFIES_RULE.value,
        RelationPredicate.EXCEPTION_TO.value,
        RelationPredicate.EXCLUDES_APPLICATION_OF.value,
        RelationPredicate.OVERRIDES_NOTWITHSTANDING.value,
    }:
        return "HAS_EXCEPTION"
    if predicate in {
        RelationPredicate.IMPOSES_SANCTION.value,
        RelationPredicate.SANCTIONS_VIOLATION_OF.value,
    }:
        return "VIOLATION_SANCTIONED_BY"
    if predicate in {
        RelationPredicate.DIRECTLY_APPLIES.value,
        RelationPredicate.INCORPORATES_MUTATIS_MUTANDIS.value,
        RelationPredicate.FOLLOWS_EXAMPLE_OF.value,
        RelationPredicate.DEPENDS_ON_REQUIREMENTS_OF.value,
    }:
        return "INCORPORATES"
    if predicate == RelationPredicate.RECEIVES_FROM.value:
        return "RECEIVES_FROM"
    if predicate in {
        RelationPredicate.LEGISLATIVE_DELEGATION.value,
        RelationPredicate.LEGISLATIVE_REDELEGATION.value,
        RelationPredicate.SUPPLEMENTS_BY_ADMINISTRATIVE_RULE.value,
        RelationPredicate.DELEGATES_ADMINISTRATIVE_AUTHORITY.value,
        RelationPredicate.ENTRUSTS_TASK.value,
    }:
        return "DELEGATES_TO"
    return None


def _stage_capture(
    index: Index,
    case_id: str,
    arm_id: str,
    snapshots: Mapping[str, Sequence[tuple[str, int]]],
    skips: Mapping[str, str],
) -> dict[str, Any]:
    specs = (
        ("question-source", "source", ()),
        ("closed-grounding-retrieve", "retrieve", ("question-source",)),
        ("legal-system-route-retrieve", "retrieve", ("closed-grounding-retrieve",)),
        ("semantic-card-retrieve", "retrieve", ("legal-system-route-retrieve",)),
        ("baseline-floor-union", "union", ("semantic-card-retrieve",)),
        ("typed-legal-relation-expand", "expand", ("baseline-floor-union",)),
        ("proviso-scope-route-expand", "expand", ("typed-legal-relation-expand",)),
        ("wiki-method-dependency-expand", "expand", ("proviso-scope-route-expand",)),
        ("adaptive-gap-retrieve", "retrieve", ("wiki-method-dependency-expand",)),
        ("provenance-canonicalize", "canonicalize", ("adaptive-gap-retrieve",)),
        ("actor-scope-filter", "filter", ("provenance-canonicalize",)),
        ("verified-coverage-select", "select", ("actor-scope-filter",)),
        ("compiled-evidence-present", "present", ("verified-coverage-select",)),
    )
    base_canonicalize = stage_ledger.index_article_root_canonicalizer(index)
    canonical_cache: dict[tuple[str, object], tuple[str, object]] = {}

    def canonicalize(value: Sequence[Any]) -> tuple[str, object]:
        if len(value) != 2:
            return base_canonicalize(value)
        key = (str(value[0]), value[1])
        cached = canonical_cache.get(key)
        if cached is None:
            cached = base_canonicalize(value)
            canonical_cache[key] = cached
        return cached

    recorder = stage_ledger.StageLedgerRecorder(
        case_id, arm_id, canonicalize
    )
    previous: set[tuple[str, int]] = set()
    for stage_id, kind, parents in specs:
        after = list(dict.fromkeys(snapshots.get(stage_id, tuple(previous))))
        after_set = set(after)
        reason = str(skips.get(stage_id) or "")
        if parents:
            discarded = sorted(previous - after_set)
            discard_reasons = [
                (coordinate, "not_selected_by_verified_add_only_compiler")
                for coordinate in discarded
            ]
            recorder.record_stage(
                stage_id,
                kind,
                after,
                parent_stage_ids=parents,
                executed=not bool(reason),
                skip_reason=reason,
                discard_reasons=discard_reasons,
            )
        else:
            recorder.record_stage(
                stage_id, kind, after,
                executed=not bool(reason), skip_reason=reason,
            )
        previous = after_set
    return recorder.capture()


def extend_sections(
    index: Index,
    question: str,
    floor_sections: Sequence[Section],
    *,
    llm: Any = None,
    cap: int = MAX_FINAL_EVIDENCE,
    graph_root: Path | str | None = None,
    case_id: str = "runtime-case",
    arm_id: str = "integrated-seven-layer",
) -> tuple[list[Section], dict[str, Any]]:
    """Compile a bounded evidence set while preserving the complete floor."""

    started = time.perf_counter()
    if not 1 <= int(cap) <= MAX_FINAL_EVIDENCE:
        raise ValueError(f"integrated evidence cap must be 1..{MAX_FINAL_EVIDENCE}")
    floor: list[Section] = []
    floor_coordinates: list[tuple[str, int]] = []
    seen_floor: set[tuple[str, int]] = set()
    for section in floor_sections:
        coordinate = _canonical(index, (section.doc_id, section.node))
        if coordinate is None or coordinate in seen_floor:
            continue
        seen_floor.add(coordinate)
        floor.append(section)
        floor_coordinates.append(coordinate)
    if len(floor_coordinates) > cap:
        raise ValueError("immutable baseline floor exceeds integrated evidence cap")
    # Keep four emergency slots below the absolute LLM context ceiling.  They
    # are available when the immutable baseline itself is larger, but normal
    # compilation targets 28 so one broad branch cannot routinely fill all 32.
    presentation_cap = max(
        len(floor_coordinates), min(int(cap), DEFAULT_PRESENTATION_TARGET)
    )

    snapshots: dict[str, list[tuple[str, int]]] = {"question-source": []}
    skips: dict[str, str] = {}
    errors: list[dict[str, str]] = []
    candidates: dict[tuple[str, int], _Candidate] = {}
    query_plan, planner_meta = _question_plan(llm, question)

    try:
        system_runtime, graph_snapshot = _resources(index, graph_root)
    except Exception as exc:
        reason = f"resource_gate:{type(exc).__name__}:{exc}"[:500]
        errors.append({"stage": "resource-gate", "error": reason})
        chain = (
            "closed-grounding-retrieve", "legal-system-route-retrieve",
            "semantic-card-retrieve",
        )
        for stage in chain:
            snapshots[stage] = []
            skips[stage] = reason
        snapshots["baseline-floor-union"] = list(floor_coordinates)
        for stage in (
            "typed-legal-relation-expand", "proviso-scope-route-expand",
            "wiki-method-dependency-expand",
            "adaptive-gap-retrieve", "provenance-canonicalize",
            "actor-scope-filter", "verified-coverage-select",
            "compiled-evidence-present",
        ):
            snapshots[stage] = list(floor_coordinates)
            skips[stage] = reason
        capture = _stage_capture(index, case_id, arm_id, snapshots, skips)
        for number, section in enumerate(floor, 1):
            section.n = number
        return floor, {
            "enabled": True,
            "status": "fallback",
            "fallback": reason,
            "before_count": len(floor),
            "after_count": len(floor),
            "baseline_floor_preserved": True,
            "direct_conclusion_allowed": False,
            "query_plan": query_plan,
            "planner": planner_meta,
            "stage_capture": capture,
            "deterministic_planning_ms": round(
                (time.perf_counter() - started) * 1000, 3
            ),
            "validation": {
                "closed_id_violations": [],
                "generation_violations": [reason],
                "verified_evidence_violations": [],
            },
            "errors": errors,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        }

    deterministic_started = time.perf_counter()

    # 1) Closed candidate generation.  The menu is a soft source of additions;
    # failure or an empty menu never filters the baseline floor.
    grounding: dict[str, Any] = {}
    try:
        grounding = query_grounding.generate_candidates(
            index, graph_snapshot, None, question, query_plan,
            menu_cap=48,
            include_vector=False,
            include_fulltext=False,
            include_canonical=False,
            use_index_reverse=True,
        )
        for row in grounding.get("evidence_candidates") or ():
            coordinate = _canonical(index, row.get("coordinate") or ())
            _add(
                candidates, coordinate,
                score=400.0 + float(row.get("score") or 0.0),
                branch_id="closed-grounding",
                origin=CandidateProvenance.GROUNDED_CONCEPT,
                coverage_keys=row.get("coverage_keys") or (),
                matched=row.get("matched_terms") or (),
            )
    except Exception as exc:
        errors.append({"stage": "closed-grounding-retrieve", "error": f"{type(exc).__name__}: {exc}"[:500]})
    snapshots["closed-grounding-retrieve"] = list(candidates)

    # 2) Legal-system -> law -> article entry.
    branches = branches_from_query_plan(query_plan)
    entry_plans: tuple[Any, ...] = ()
    try:
        entry_plans = system_runtime.plan(
            question, query_plan, branches, instrument_limit=8, entry_limit=12,
        )
        for plan in entry_plans:
            for instrument_rank, instrument in enumerate(plan.instruments):
                for article_rank, point in enumerate(instrument.entry_points[:6]):
                    _add(
                        candidates,
                        _canonical(index, (point.unit.instrument_id, point.unit.node_id)),
                        score=700.0 + float(instrument.score) + float(point.score)
                              - instrument_rank * 4 - article_rank,
                        branch_id=plan.branch_id,
                        origin=CandidateProvenance.SYSTEM_PRIOR,
                        matched=point.matched_signals,
                    )
    except Exception as exc:
        errors.append({"stage": "legal-system-route-retrieve", "error": f"{type(exc).__name__}: {exc}"[:500]})
    snapshots["legal-system-route-retrieve"] = list(candidates)

    # 3) Existing semantic cards are used as entry hints, not evidence.
    if system_runtime.semantic_cards is not None:
        terms = tuple(dict.fromkeys(
            str(row.get("surface") or "")
            for row in query_plan.get("mentions") or ()
            if str(row.get("surface") or "").strip()
        ))
        if not terms:
            terms = tuple(dict.fromkeys(_TOKEN.findall(question)))[:4]
        try:
            preferred_ids = tuple(dict.fromkeys(
                instrument.instrument_id
                for plan in entry_plans for instrument in plan.instruments[:4]
            ))
            # AND first; when it is too strict, each closed term is a separate
            # OR branch.  This broadens recall without inventing a concept ID.
            cards = list(system_runtime.semantic_cards.search(
                terms[:3], instrument_ids=preferred_ids or None, limit=48,
            ))
            if not cards:
                by_coordinate = {}
                for term in terms[:4]:
                    for card in system_runtime.semantic_cards.search(
                        (term,), instrument_ids=preferred_ids or None, limit=24,
                    ):
                        by_coordinate[card.coordinate] = card
                cards = list(by_coordinate.values())
            for rank, card in enumerate(cards[:48]):
                _add(
                    candidates,
                    _canonical(index, card.coordinate),
                    score=560.0 - rank,
                    branch_id="semantic-card",
                    origin=CandidateProvenance.SEMANTIC_ENTRY,
                    coverage_keys=card.coverage_keys,
                    matched=card.terms[:12],
                )
        except Exception as exc:
            errors.append({"stage": "semantic-card-retrieve", "error": f"{type(exc).__name__}: {exc}"[:500]})
    snapshots["semantic-card-retrieve"] = list(candidates)

    # 4) The immutable source floor is unioned before any legal-effect closure.
    for rank, coordinate in enumerate(floor_coordinates):
        _add(
            candidates, coordinate,
            score=1_000_000.0 - rank,
            branch_id="baseline-floor",
            origin=CandidateProvenance.SYSTEM_PRIOR,
            matched=("baseline-floor",),
        )
    snapshots["baseline-floor-union"] = list(candidates)

    # 5) Typed relation closure.  We consume its full trace, but only verified
    # current target text can later become final evidence.
    semantic_meta: dict[str, Any] = {}
    dependency_relations: list[DependencyRelation] = []
    active_predicates = tuple(dict.fromkeys(
        str(row.get("predicate") or "")
        for row in query_plan.get("predicate_hypotheses") or ()
        if str(row.get("predicate") or "")
    ))
    family_hints = tuple(dict.fromkeys(
        str(row.get("family_id") or "")
        for row in query_plan.get("family_hypotheses") or ()
        if str(row.get("family_id") or "")
    ))
    try:
        _planned, semantic_meta = plan_semantic_coordinates(
            index,
            question,
            list(candidates),
            snapshot=graph_snapshot,
            cap=MAX_INTERNAL_CANDIDATES,
            family_hints=family_hints,
            predicate_hints=active_predicates,
        )
        relation_ids_by_target: dict[tuple[str, int], set[str]] = defaultdict(set)
        for event in semantic_meta.get("closure_events") or ():
            target = _canonical(index, event.get("target") or ())
            source = _canonical(index, event.get("source") or ())
            relation_id = str(event.get("projection_id") or "")
            predicate = str(event.get("predicate") or "")
            if target is not None and relation_id:
                relation_ids_by_target[target].add(relation_id)
            kind = _relation_kind(predicate)
            if kind and source is not None and target is not None:
                dependency_relations.append(DependencyRelation(
                    kind=kind,
                    source_coordinate=f"{source[0]}:{source[1]}",
                    target_coordinate=f"{target[0]}:{target[1]}",
                    target_instrument_id=target[0],
                    provenance=f"legal-graph:{relation_id}",
                ))
        for raw in (semantic_meta.get("stages") or {}).get("typed-closure") or ():
            coordinate = _canonical(index, raw)
            if coordinate is None or coordinate in candidates:
                continue
            relation_ids = relation_ids_by_target.get(coordinate) or {
                "typed-closure-observation:" + hashlib.sha256(
                    f"{coordinate[0]}:{coordinate[1]}".encode()
                ).hexdigest()[:16]
            }
            _add(
                candidates, coordinate,
                score=500.0,
                branch_id="typed-relation",
                origin=CandidateProvenance.RELATION_EXPANDED,
                relation_ids=relation_ids,
            )
    except Exception as exc:
        errors.append({"stage": "typed-legal-relation-expand", "error": f"{type(exc).__name__}: {exc}"[:500]})
    snapshots["typed-legal-relation-expand"] = list(candidates)

    # 5-1) 단서의 물리 부착·법적 효과·검색 경로를 분리해 걷는다. 검색 경로가
    # 가리킨 조문은 검증 후보로만 추가하며, 외부 조문에 단서 효과가 미친다고
    # 자동 결론내리지 않는다.
    proviso_rows: list[dict[str, Any]] = []
    try:
        packages, proviso_meta = relation_navigation.proviso_packages(
            index, list(candidates)[:MAX_INTERNAL_CANDIDATES],
            cap=MAX_INTERNAL_CANDIDATES)
        proviso_rows = [package.as_dict() for package in packages]
        for package in packages:
            for target in package.route_targets:
                if target.get("node") is None:
                    continue
                coordinate = _canonical(index, (target.get("doc_id"), target.get("node")))
                _add(
                    candidates, coordinate, score=495.0,
                    branch_id="proviso-route",
                    origin=CandidateProvenance.RELATION_EXPANDED,
                    relation_ids=(package.proviso_id, target.get("route_kind", "")),
                    coverage_keys=("proviso_external_route",),
                    matched=(package.cue, package.effect_kind),
                )
    except Exception as exc:
        proviso_meta = {"status": "error"}
        errors.append({"stage": "proviso-scope-route-expand",
                       "error": f"{type(exc).__name__}: {exc}"[:500]})
    snapshots["proviso-scope-route-expand"] = list(candidates)

    # 6) Compile Wiki methods to dependency actions.  Actions are retrieval
    # requests only; none is marked as coverage or a legal conclusion.
    evidence_sections = [
        {
            "coordinate": f"{coordinate[0]}:{coordinate[1]}",
            "instrument_id": coordinate[0],
            "text": _source_text(index, coordinate)[:4000],
            "tags": tuple(),
        }
        for coordinate in list(candidates)[:MAX_INTERNAL_CANDIDATES]
    ]
    dependency_actions: list[dict[str, Any]] = []
    missing_coverage = tuple(sorted({
        key for row in candidates.values() for key in row.coverage_keys
    }))
    try:
        method_step = plan_research_step(
            question,
            evidence_sections,
            MethodCoverageState(required=missing_coverage, satisfied=()),
            relations=dependency_relations,
            cursor_after=ResearchCursor("integrated", None, 0),
            page_scores=(1.0,),
            next_score=0.99,
            scope_exhausted=False,
            budget_available=True,
            policy=AdaptivePagePolicy(final_evidence_cap=presentation_cap),
        )
        dependency_actions = [action.to_dict() for action in method_step.dependency_actions]
        for action in method_step.dependency_actions:
            if action.target_coordinate and ":" in action.target_coordinate:
                doc_id, raw_node = action.target_coordinate.rsplit(":", 1)
                try:
                    target = _canonical(index, (doc_id, int(raw_node)))
                except ValueError:
                    target = None
                _add(
                    candidates, target,
                    score=480.0 - action.priority,
                    branch_id="wiki-dependency",
                    origin=CandidateProvenance.RELATION_EXPANDED,
                    relation_ids=(action.action_id,),
                    coverage_keys=(action.coverage_key,),
                )
    except Exception as exc:
        errors.append({"stage": "wiki-method-dependency-expand", "error": f"{type(exc).__name__}: {exc}"[:500]})
    snapshots["wiki-method-dependency-expand"] = list(candidates)

    # 7) Adaptive, law-local next pages.  This is an internal recall pool; the
    # final compiler remains capped at 32.  We never claim scope exhaustion.
    adaptive_steps: list[dict[str, Any]] = []
    try:
        for plan in entry_plans:
            for instrument in plan.instruments[:3]:
                units = list(system_runtime.atlas.article_units(instrument.instrument_id))
                positions = {unit.node_id: pos for pos, unit in enumerate(units)}
                for point in instrument.entry_points[:2]:
                    pos = positions.get(point.unit.node_id)
                    if pos is None:
                        continue
                    page = units[pos:pos + 4]
                    scores = tuple(max(0.0, float(point.score) - offset) for offset, _ in enumerate(page))
                    next_score = max(0.0, float(point.score) - len(page)) if pos + len(page) < len(units) else None
                    step = plan_research_step(
                        question,
                        evidence_sections,
                        MethodCoverageState(required=missing_coverage, satisfied=()),
                        relations=dependency_relations,
                        cursor_after=ResearchCursor(instrument.instrument_id, None, pos + len(page)),
                        page_scores=scores,
                        next_score=next_score,
                        scope_exhausted=False,
                        budget_available=True,
                    )
                    adaptive_steps.append(step.to_dict())
                    for offset, unit in enumerate(page):
                        _add(
                            candidates,
                            _canonical(index, (unit.instrument_id, unit.node_id)),
                            score=260.0 + float(point.score) - offset,
                            branch_id=plan.branch_id,
                            origin=CandidateProvenance.SYSTEM_PRIOR,
                            matched=("adaptive-law-local-page",),
                        )
                    if len(candidates) >= MAX_INTERNAL_CANDIDATES:
                        break
                if len(candidates) >= MAX_INTERNAL_CANDIDATES:
                    break
            if len(candidates) >= MAX_INTERNAL_CANDIDATES:
                break
    except Exception as exc:
        errors.append({"stage": "adaptive-gap-retrieve", "error": f"{type(exc).__name__}: {exc}"[:500]})
    snapshots["adaptive-gap-retrieve"] = list(candidates)

    # Provenance + exact current-source verification.
    records: dict[str, Any] = {}
    invalid: set[tuple[str, int]] = set()
    for coordinate, row in list(candidates.items()):
        candidate_id = _candidate_id(coordinate)
        ordered_origins = sorted(row.origins, key=lambda value: value.value)
        origin = ordered_origins[0]
        relation_ids = row.relation_ids if origin == CandidateProvenance.RELATION_EXPANDED else ()
        try:
            record = seed_candidate(
                candidate_id,
                ResearchCoordinate(coordinate[0], coordinate[1]),
                origin,
                relation_ids=relation_ids,
            )
            for extra in ordered_origins[1:]:
                record = add_candidate_origin(
                    record,
                    extra,
                    relation_ids=(row.relation_ids if extra == CandidateProvenance.RELATION_EXPANDED else ()),
                )
            record = promote_candidate(
                record,
                CandidateProvenance.PROTECTED_CANDIDATE,
                reason="closed current article selected for exact-source verification",
            )
            text = _source_text(index, coordinate)
            if not text:
                raise ValueError("current article source text is empty")
            quote = text[: min(len(text), 600)]
            receipt = build_source_span_verification(
                candidate_id,
                record.coordinate,
                text,
                authority_generation=index.authority_generation,
                authority_as_of=index.authority_as_of,
                start=0,
                end=len(quote),
            )
            record = verify_candidate(
                record,
                (receipt,),
                source_resolver=lambda value: _source_text(
                    index, (value.document_id, int(value.node_id))
                ),
                authority_generation=index.authority_generation,
                authority_as_of=index.authority_as_of,
            )
            records[candidate_id] = record
        except Exception as exc:
            invalid.add(coordinate)
            errors.append({
                "stage": "provenance-canonicalize",
                "coordinate": f"{coordinate[0]}:{coordinate[1]}",
                "error": f"{type(exc).__name__}: {exc}"[:500],
            })
    verified_coordinates = [
        coordinate for coordinate in candidates if coordinate not in invalid
    ]
    snapshots["provenance-canonicalize"] = verified_coordinates

    # Actor alignment may discard only explicit numeric-only or wrong-public-
    # delegate additions.  The baseline floor can never be discarded here.
    aligned_coordinates: list[tuple[str, int]] = []
    alignment_rows: dict[str, Any] = {}
    for coordinate in verified_coordinates:
        alignment = scope_alignment(query_plan, _source_text(index, coordinate))
        alignment_rows[f"{coordinate[0]}:{coordinate[1]}"] = alignment
        if coordinate in seen_floor or not (
            alignment.get("numeric_only") or alignment.get("wrong_actor_delegation")
        ):
            aligned_coordinates.append(coordinate)
    snapshots["actor-scope-filter"] = aligned_coordinates

    final_rows: list[FinalEvidenceCandidate] = []
    for coordinate in aligned_coordinates:
        row = candidates[coordinate]
        final_rows.append(FinalEvidenceCandidate(
            case_id=case_id,
            branch_id=row.branch_id,
            candidate_id=_candidate_id(coordinate),
            coordinate=f"{coordinate[0]}:{coordinate[1]}",
            instrument_id=coordinate[0],
            verified=_candidate_id(coordinate) in records,
            score=row.score,
            mandatory=coordinate in seen_floor,
            baseline_floor=coordinate in seen_floor,
            coverage_keys=tuple(sorted(row.coverage_keys)),
            source_order=row.source_order,
            payload={"coordinate": list(coordinate), "candidate_id": _candidate_id(coordinate)},
        ))
    compiled = compile_final_evidence(
        case_id,
        final_rows,
        cap=presentation_cap,
        verification_records=records,
        source_resolver=lambda value: _source_text(
            index, (value.document_id, int(value.node_id))
        ),
        authority_generation=index.authority_generation,
        authority_as_of=index.authority_as_of,
    )
    selected_coordinates: list[tuple[str, int]] = []
    for row in compiled.selected:
        raw = row.payload.get("coordinate") if isinstance(row.payload, Mapping) else None
        coordinate = _canonical(index, raw or ())
        if coordinate is not None:
            selected_coordinates.append(coordinate)
    if not set(floor_coordinates).issubset(selected_coordinates):
        raise RuntimeError("integrated final compiler attempted to drop the baseline floor")
    snapshots["verified-coverage-select"] = selected_coordinates
    snapshots["compiled-evidence-present"] = selected_coordinates

    relation_predicates = tuple(dict.fromkeys(
        RelationPredicate(value)
        for value in (
            *active_predicates,
            *(str(event.get("predicate") or "") for event in semantic_meta.get("closure_events") or ()),
        )
        if value in {predicate.value for predicate in RELATION_BEHAVIOR_POLICIES}
    ))
    evidence_bundle = compile_research_evidence(
        question,
        records,
        relation_predicates=relation_predicates,
    )
    subsumption = None
    if evidence_bundle.compilations:
        first = next(iter(evidence_bundle.compilations.values()))
        subsumption = assess_subsumption(
            first,
            (),
            conditions_complete=False,
            exceptions_complete=False,
        ).to_dict()

    floor_by_coordinate = dict(zip(floor_coordinates, floor))
    output: list[Section] = []
    for number, coordinate in enumerate(selected_coordinates, 1):
        section = floor_by_coordinate.get(coordinate)
        if section is None:
            section = _section(index, coordinate, number, origin="integrated-verified")
        section.n = number
        section.legal_meta = {
            **dict(section.legal_meta or {}),
            "integrated_research": {
                "candidate_id": _candidate_id(coordinate),
                "states": sorted(
                    state.value for state in records[_candidate_id(coordinate)].states
                ),
                "direct_conclusion_allowed": False,
            },
        }
        output.append(section)

    capture = _stage_capture(index, case_id, arm_id, snapshots, skips)
    closed_id_violations = [
        f"{coordinate[0]}:{coordinate[1]}"
        for coordinate in selected_coordinates
        if _canonical(index, coordinate) != coordinate
    ]
    verified_evidence_violations = [
        f"{coordinate[0]}:{coordinate[1]}"
        for coordinate in selected_coordinates
        if _candidate_id(coordinate) not in records
        or not records[_candidate_id(coordinate)].verified
    ]
    meta = {
        "enabled": True,
        "status": "extended" if selected_coordinates != floor_coordinates else "unchanged",
        "fallback": "",
        "authority_generation": index.authority_generation,
        "authority_as_of": index.authority_as_of,
        "legal_system_catalog_version": system_runtime.system_map.catalog_version,
        "legal_graph_generation": graph_snapshot.generation_id,
        "before_count": len(floor_coordinates),
        "after_count": len(output),
        "added_count": len(set(selected_coordinates) - set(floor_coordinates)),
        "baseline_floor_preserved": set(floor_coordinates).issubset(selected_coordinates),
        "final_evidence_cap": cap,
        "presentation_target": presentation_cap,
        "direct_conclusion_allowed": False,
        "deterministic_planning_ms": round(
            (time.perf_counter() - deterministic_started) * 1000, 3
        ),
        "validation": {
            "closed_id_violations": closed_id_violations,
            "generation_violations": [],
            "verified_evidence_violations": verified_evidence_violations,
        },
        "query_plan": query_plan,
        "planner": planner_meta,
        "grounding": {
            "menu_count": len(grounding.get("menu") or ()),
            "evidence_candidate_count": len(grounding.get("evidence_candidates") or ()),
            "channel_errors": list(grounding.get("channel_errors") or ()),
        },
        "entry_plans": [plan.to_dict() for plan in entry_plans],
        "semantic": semantic_meta,
        "dependency_actions": dependency_actions,
        "proviso_packages": proviso_rows,
        "proviso_routing": proviso_meta,
        "adaptive_steps": adaptive_steps,
        "provenance": {
            "verified_candidate_count": len(records),
            "invalid_coordinates": [list(value) for value in sorted(invalid)],
        },
        "scope_alignment": alignment_rows,
        "final_compilation": compiled.to_dict(),
        "evidence_compilation": evidence_bundle.to_dict(),
        "subsumption": subsumption,
        "selected_coordinates": [list(value) for value in selected_coordinates],
        "stage_capture": capture,
        "errors": errors,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    return output, meta


__all__ = [
    "DEFAULT_PRESENTATION_TARGET", "MAX_FINAL_EVIDENCE", "clear_resource_cache",
    "fallback_to_floor", "extend_sections", "preload_resources",
]
