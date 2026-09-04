"""Typed semantic landing, closure bundling, and bounded final selection.

The source LegalClosure result remains an immutable trace input, but unlike the
legacy add-only graph consumer this module may replace low-ranked presentation
rows when a source-backed semantic DecisionBundle would otherwise be blocked by
the final cap.  Every replacement is explicit in the returned stage metadata.
"""

from __future__ import annotations

import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from lawrag.core.legal_graph import (
    AssessmentReasoningMode,
    AssessmentStatus,
    RelationPredicate,
    stable_id,
)
from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag import legal_evidence
from lawrag.core.rag.answer import Section
from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_graph_store import (
    EdgeLite,
    LegalGraphLoadResult,
    LegalGraphSnapshot,
    SemanticCardLite,
    current_for,
)
from lawrag.core.rag.query_family_runtime import (
    UNKNOWN_FAMILY,
    QueryFamilyRegistry,
    default_registry,
    extract_query_frame,
)


LANDING_CAP = 32
CLOSURE_HOPS = 2
REPLACEMENT_CAP = 4
FLOOR_PREFIX_PROTECTED = 12
TRACE_CANDIDATE_CAP = 80
CLOSURE_EDGE_CAP = 96
CLOSURE_PER_SOURCE_CAP = 20
QUERY_TERM_CAP = 10
GLOBAL_LANDING_RESERVE = 8
PREFERRED_DOC_CARD_CAP = 4
_TOKEN = re.compile(r"[A-Za-z0-9가-힣]+")
_NOISE = frozenset({
    "법률", "법령", "규정", "조문", "경우", "해당", "여부", "관련",
    "어떻게", "무엇", "있는가", "하여야", "따라", "따른", "시", "의",
})
_NEGATIVE = re.compile(r"없는가|없다|아니다|아닌가|불가|지원되지\s*않|위임할\s*수\s*없|조정되는가")
_LEGISLATIVE = frozenset({
    "LEGISLATIVE_DELEGATION",
    "LEGISLATIVE_REDELEGATION",
    "SUPPLEMENTS_BY_ADMINISTRATIVE_RULE",
})
_LEGISLATIVE_SIGNAL = re.compile(r"대통령령|총리령|부령|시행령|시행규칙|위임|정하는\s*바")
_LANDING_FAMILY_COMPAT = {
    "AUTHORITY": frozenset({"AUTHORITY", "CLASSIFICATION", "EXCEPTION"}),
    "CLASSIFICATION": frozenset({"CLASSIFICATION", "THRESHOLD", "EXCEPTION"}),
    "DELEGATION": frozenset({"AUTHORITY", "CLASSIFICATION", "EXCEPTION"}),
    "ENTRUSTMENT": frozenset({
        "AUTHORITY", "CLASSIFICATION", "FILING_DOCUMENT", "EXCEPTION",
    }),
    "EXCEPTION": frozenset({"EXCEPTION", "CLASSIFICATION", "THRESHOLD"}),
    "FILING_DOCUMENT": frozenset({
        "FILING_DOCUMENT", "CLASSIFICATION", "TEMPORAL", "THRESHOLD",
    }),
    "FORMULA": frozenset({"FORMULA", "THRESHOLD", "CLASSIFICATION"}),
    "LEGAL_BASIS": frozenset({
        "AUTHORITY", "CLASSIFICATION", "EXCEPTION", "FILING_DOCUMENT",
        "FORMULA", "TEMPORAL", "THRESHOLD",
    }),
    "NEGATIVE_AUTHORITY": frozenset({
        "AUTHORITY", "CLASSIFICATION", "EXCEPTION", "FORMULA",
    }),
    "TEMPORAL": frozenset({"TEMPORAL", "EXCEPTION", "THRESHOLD"}),
    "THRESHOLD": frozenset({"THRESHOLD", "CLASSIFICATION", "EXCEPTION"}),
}


Coordinate = tuple[str, object]


@dataclass(slots=True)
class _Candidate:
    coordinate: Coordinate
    score: float = 0.0
    floor_rank: int | None = None
    origins: set[str] = field(default_factory=set)
    matched_terms: set[str] = field(default_factory=set)
    family_ids: set[str] = field(default_factory=set)
    semantic_types: set[str] = field(default_factory=set)
    coverage_keys: set[str] = field(default_factory=set)
    assertion_ids: set[str] = field(default_factory=set)
    card_ids: set[str] = field(default_factory=set)
    edges: list[EdgeLite] = field(default_factory=list)
    source_coordinates: set[Coordinate] = field(default_factory=set)
    protected: bool = False

    @property
    def rank_key(self) -> tuple[Any, ...]:
        return (
            -int(self.protected),
            -round(self.score, 8),
            self.floor_rank if self.floor_rank is not None else 10**9,
            str(self.coordinate[0]),
            str(self.coordinate[1]),
        )


def _article_coordinate(index: Index, doc_id: str, node: object | None) -> Coordinate | None:
    view = index.docs.get(doc_id)
    if view is None or node not in view.by_id:
        return None
    return doc_id, coordinates.article_root(view, node)


def _query_terms(question: str, snapshot: LegalGraphSnapshot) -> tuple[str, ...]:
    terms: set[str] = set()
    for raw in _TOKEN.findall(question):
        token = raw.casefold()
        if len(token) < 2 or token in _NOISE:
            continue
        if token in snapshot.semantic_postings:
            terms.add(token)
        if 4 <= len(token) <= 32:
            for size in range(2, min(7, len(token) + 1)):
                for start in range(0, len(token) - size + 1):
                    part = token[start:start + size]
                    if part not in _NOISE and part in snapshot.semantic_postings:
                        terms.add(part)
    return tuple(sorted(
        terms,
        key=lambda term: (-_term_score(term, snapshot), term),
    )[:QUERY_TERM_CAP])


def _landing_families(family_ids: frozenset[str]) -> frozenset[str]:
    expanded = set(family_ids)
    for family_id in family_ids:
        expanded.update(_LANDING_FAMILY_COMPAT.get(family_id, ()))
    return frozenset(expanded)


def _active_families(
    question: str,
    snapshot: LegalGraphSnapshot,
    registry: QueryFamilyRegistry,
):
    frame = extract_query_frame(
        question, authority_generation=snapshot.authority_generation,
    )
    hypotheses = registry.classify(frame)
    active = tuple(item for item in hypotheses if item.family_id != UNKNOWN_FAMILY)
    family_ids = frozenset(item.family_id for item in active)
    predicates = frozenset(
        predicate
        for hypothesis in active
        for predicate in (
            registry.get(hypothesis.family_id).closure_predicates
            if registry.get(hypothesis.family_id) is not None else ()
        )
    )
    return frame, hypotheses, active, family_ids, predicates


def _term_score(
    term: str,
    snapshot: LegalGraphSnapshot,
) -> float:
    total = max(1, len(snapshot.semantic_cards))
    frequency = max(1, len(snapshot.semantic_postings.get(term, ())))
    return min(len(term), 10) ** 2 * (1.0 + math.log((total + 1) / frequency))


def _landing(
    index: Index,
    snapshot: LegalGraphSnapshot,
    query_terms: tuple[str, ...],
    family_ids: frozenset[str],
    preferred_doc_ids: frozenset[str],
    floor_coordinates: frozenset[Coordinate],
    question: str,
) -> dict[Coordinate, _Candidate]:
    candidates: dict[Coordinate, _Candidate] = {}
    term_set = set(query_terms)
    packed_question = "".join(_TOKEN.findall(question.casefold()))
    name_bonus_cache: dict[str, float] = {}
    cards = snapshot.semantic_candidates(
        query_terms,
        family_ids=_landing_families(family_ids),
        min_term_matches=2,
    )
    for card in cards:
        coordinate = (card.article_root.document_id, card.article_root.node_id)
        if coordinate[1] is None or coordinate not in snapshot.ports_by_article:
            continue
        view = index.docs.get(coordinate[0])
        if view is None or coordinate[1] not in view.by_id or not view.is_current:
            continue
        matched = term_set.intersection(card.terms)
        if not matched:
            continue
        score = sum(_term_score(term, snapshot) for term in matched)
        score += 14.0 * len(family_ids.intersection(card.family_ids))
        score += 5.0 * len(card.coverage_keys)
        if coordinate[0] in preferred_doc_ids:
            score += 120.0
        if coordinate in floor_coordinates:
            score += 45.0
        name_bonus = name_bonus_cache.get(coordinate[0])
        if name_bonus is None:
            packed_name = "".join(_TOKEN.findall(view.name.casefold()))
            if len(packed_name) >= 4 and packed_name in packed_question:
                name_bonus = 180.0
            else:
                name_bonus = 38.0 * sum(
                    token in packed_question
                    for token in _TOKEN.findall(view.name.casefold())
                    if len(token) >= 4
                )
            name_bonus_cache[coordinate[0]] = name_bonus
        score += name_bonus
        candidate = candidates.setdefault(coordinate, _Candidate(coordinate))
        candidate.score = max(candidate.score, score)
        candidate.origins.add("semantic-landing")
        candidate.matched_terms.update(matched)
        candidate.family_ids.update(card.family_ids)
        candidate.semantic_types.add(card.semantic_type)
        candidate.coverage_keys.update(card.coverage_keys)
        candidate.assertion_ids.update(card.assertion_ids)
        candidate.card_ids.add(card.card_id)
        if score >= 32.0:
            candidate.protected = True
    ranked = sorted(candidates.items(), key=lambda item: item[1].rank_key)
    selected: list[tuple[Coordinate, _Candidate]] = ranked[:GLOBAL_LANDING_RESERVE]
    selected_coordinates = {coordinate for coordinate, _ in selected}
    preferred_by_doc: dict[str, list[tuple[Coordinate, _Candidate]]] = {}
    for item in ranked:
        if item[0][0] in preferred_doc_ids:
            preferred_by_doc.setdefault(item[0][0], []).append(item)
    preferred_docs = sorted(
        preferred_by_doc,
        key=lambda doc_id: preferred_by_doc[doc_id][0][1].rank_key,
    )
    for offset in range(PREFERRED_DOC_CARD_CAP):
        for doc_id in preferred_docs:
            rows = preferred_by_doc[doc_id]
            if offset >= len(rows) or rows[offset][0] in selected_coordinates:
                continue
            selected.append(rows[offset])
            selected_coordinates.add(rows[offset][0])
            if len(selected) >= LANDING_CAP:
                return dict(selected)
    for item in ranked:
        if item[0] not in selected_coordinates:
            selected.append(item)
            selected_coordinates.add(item[0])
        if len(selected) >= LANDING_CAP:
            break
    return dict(selected)


def _text_overlap(question: str, text: str) -> tuple[str, ...]:
    packed_question = "".join(_TOKEN.findall(question.casefold()))
    hits: list[str] = []
    for token in _TOKEN.findall(text.casefold()):
        if len(token) < 2 or token in _NOISE:
            continue
        if token in packed_question and token not in hits:
            hits.append(token)
    return tuple(hits[:16])


def _current_structural_target(index: Index, edge: EdgeLite) -> Coordinate | None:
    if edge.target.kind != "STRUCTURAL_UNIT" or edge.target.node_id is None:
        return None
    view = index.docs.get(edge.target.document_id)
    if view is None or edge.target.node_id not in view.by_id or not view.is_current:
        return None
    canonical = index.canonical_doc_ids or frozenset()
    if canonical and view.kind in {"law", "admrul"} and edge.target.document_id not in canonical:
        return None
    return edge.target.document_id, coordinates.article_root(view, edge.target.node_id)


def _closure(
    index: Index,
    question: str,
    snapshot: LegalGraphSnapshot,
    candidates: dict[Coordinate, _Candidate],
    predicates: frozenset[str],
    query_terms: tuple[str, ...],
    landing_family_ids: frozenset[str],
) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    text_cache: dict[Coordinate, str] = {}
    relevance_cache: dict[Coordinate, float] = {}

    def article_text(coordinate: Coordinate) -> str:
        cached = text_cache.get(coordinate)
        if cached is not None:
            return cached
        view = index.docs[coordinate[0]]
        node = view.by_id.get(coordinate[1])
        value = view.section_text(node, cap=2400) if node else ""
        text_cache[coordinate] = value
        return value

    def semantic_relevance(coordinate: Coordinate) -> float:
        cached = relevance_cache.get(coordinate)
        if cached is not None:
            return cached
        query_set = set(query_terms)
        best = 0.0
        for card in snapshot.semantics_for_article(coordinate):
            if landing_family_ids and not landing_family_ids.intersection(card.family_ids):
                continue
            matched = query_set.intersection(card.terms)
            if matched:
                best = max(best, sum(_term_score(term, snapshot) for term in matched))
        relevance_cache[coordinate] = best
        return best

    frontier = list(candidates)
    seen_sources: set[Coordinate] = set()
    for hop in range(1, CLOSURE_HOPS + 1):
        next_frontier: list[Coordinate] = []
        for source_coordinate in frontier:
            if source_coordinate in seen_sources:
                continue
            seen_sources.add(source_coordinate)
            source_candidate = candidates[source_coordinate]
            source_accepted = 0
            incident = sorted(
                snapshot.incident(source_coordinate, direction="outgoing"),
                key=lambda edge: (
                    edge.mode != "REQUIRED_WHEN_ACTIVATED",
                    edge.predicate,
                    edge.projection_id,
                ),
            )
            for edge in incident:
                if len(accepted) >= CLOSURE_EDGE_CAP:
                    break
                if source_accepted >= CLOSURE_PER_SOURCE_CAP:
                    break
                if edge.predicate not in predicates:
                    continue
                if edge.mode == "NON_CLOSURE":
                    continue
                if edge.source.precision not in {"EXACT_SPAN", "EXACT_UNIT", "ARTICLE_FALLBACK"}:
                    continue
                if not index.relation_allowed(
                    edge.source.document_id, edge.target.document_id
                ):
                    continue
                target_coordinate = _current_structural_target(index, edge)
                if target_coordinate is None or target_coordinate == source_coordinate:
                    continue
                target_ports = snapshot.ports_by_article.get(target_coordinate)
                if target_ports is None or edge.projection_id not in target_ports.incoming:
                    continue
                source_text = article_text(source_coordinate)
                target_text = article_text(target_coordinate)
                source_overlap = _text_overlap(question, source_text)
                target_overlap = _text_overlap(question, target_text)
                target_landed = target_coordinate in candidates and (
                    "semantic-landing" in candidates[target_coordinate].origins
                )
                legislative = edge.predicate in _LEGISLATIVE
                explicit_legislative = legislative and (
                    _LEGISLATIVE_SIGNAL.search(question) is not None
                    or _LEGISLATIVE_SIGNAL.search(source_text) is not None
                )
                required = edge.mode == "REQUIRED_WHEN_ACTIVATED"
                target_relevance = semantic_relevance(target_coordinate)
                eligible = (
                    target_landed
                    or explicit_legislative
                    or (required and bool(source_overlap or target_overlap))
                    or (
                        edge.mode == "CONTEXTUAL"
                        and bool(target_overlap)
                        and target_relevance >= 100.0
                        and source_candidate.score >= 24.0
                    )
                )
                if not eligible:
                    continue
                target = candidates.setdefault(
                    target_coordinate, _Candidate(target_coordinate),
                )
                edge_score = 72.0 if required else 34.0
                edge_score += 4.0 * len(set(source_overlap + target_overlap))
                edge_score += min(20.0, source_candidate.score * 0.15)
                edge_score += min(160.0, target_relevance * 0.35)
                target.score = max(target.score, edge_score)
                target.origins.add("typed-closure")
                target.matched_terms.update(source_overlap)
                target.matched_terms.update(target_overlap)
                target.assertion_ids.add(edge.assertion_id)
                target.edges.append(edge)
                if required or target_landed:
                    target.source_coordinates.add(source_coordinate)
                if required:
                    target.protected = True
                accepted.append({
                    "hop": hop,
                    "source": list(source_coordinate),
                    "target": list(target_coordinate),
                    "projection_id": edge.projection_id,
                    "assertion_id": edge.assertion_id,
                    "predicate": edge.predicate,
                    "closure_mode": edge.mode,
                    "source_overlap": list(source_overlap),
                    "target_overlap": list(target_overlap),
                })
                source_accepted += 1
                if target_coordinate not in seen_sources:
                    next_frontier.append(target_coordinate)
            if len(accepted) >= CLOSURE_EDGE_CAP:
                break
        if len(accepted) >= CLOSURE_EDGE_CAP:
            break
        frontier = list(dict.fromkeys(next_frontier))
        if not frontier:
            break
    return accepted


def _bundles(candidates: Mapping[Coordinate, _Candidate]) -> list[dict[str, Any]]:
    parent: dict[Coordinate, Coordinate] = {coordinate: coordinate for coordinate in candidates}

    def find(value: Coordinate) -> Coordinate:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: Coordinate, right: Coordinate) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root, key=lambda item: (str(item[0]), str(item[1])))] = min(
                left_root, right_root, key=lambda item: (str(item[0]), str(item[1]))
            )

    for coordinate, candidate in candidates.items():
        for source in candidate.source_coordinates:
            if source in parent:
                union(source, coordinate)
    grouped: dict[Coordinate, list[Coordinate]] = {}
    for coordinate in candidates:
        grouped.setdefault(find(coordinate), []).append(coordinate)
    rows = []
    for root, members in sorted(grouped.items()):
        member_candidates = [candidates[coordinate] for coordinate in members]
        assertion_ids = sorted({
            assertion_id
            for candidate in member_candidates
            for assertion_id in candidate.assertion_ids
        })
        protected = any(candidate.protected for candidate in member_candidates)
        rows.append({
            "id": stable_id("decision_bundle", root, sorted(members), assertion_ids),
            "root": list(root),
            "member_coordinates": [list(value) for value in sorted(members)],
            "assertion_ids": assertion_ids,
            "coverage_keys": sorted({
                key for candidate in member_candidates for key in candidate.coverage_keys
            }),
            "semantic_types": sorted({
                value for candidate in member_candidates for value in candidate.semantic_types
            }),
            "protected": protected,
            "score": round(max(candidate.score for candidate in member_candidates), 6),
        })
    return rows


def _apply_bundle_protection(
    candidates: Mapping[Coordinate, _Candidate],
    bundles: Sequence[Mapping[str, Any]],
) -> None:
    """Make DecisionBundle protection operational, not merely diagnostic."""
    for bundle in bundles:
        if not bundle.get("protected"):
            continue
        bundle_score = float(bundle.get("score") or 0.0)
        for raw_coordinate in bundle.get("member_coordinates") or ():
            coordinate = tuple(raw_coordinate)
            candidate = candidates.get(coordinate)
            if candidate is None:
                continue
            candidate.protected = True
            candidate.origins.add("protected-decision-bundle")
            candidate.score = max(candidate.score, bundle_score - 2.0)


def _final_selection(
    floor: list[Coordinate],
    candidates: dict[Coordinate, _Candidate],
    *,
    cap: int,
) -> tuple[list[Coordinate], list[dict[str, Any]]]:
    for rank, coordinate in enumerate(floor, 1):
        candidate = candidates.setdefault(coordinate, _Candidate(coordinate))
        candidate.floor_rank = rank
        candidate.origins.add("legalclosure-floor")
        candidate.score += max(4.0, 34.0 - rank)
        if rank <= min(FLOOR_PREFIX_PROTECTED, cap):
            candidate.protected = True

    if len(floor) < cap:
        selected = list(floor)
        for candidate in sorted(candidates.values(), key=lambda item: item.rank_key):
            if candidate.coordinate not in selected:
                selected.append(candidate.coordinate)
            if len(selected) >= cap:
                break
    else:
        prefix = floor[:min(FLOOR_PREFIX_PROTECTED, cap)]
        selected = list(prefix)
        new_candidates = [
            candidate for candidate in candidates.values()
            if candidate.coordinate not in floor
            and (candidate.protected or candidate.score >= 60.0)
        ]
        for candidate in sorted(new_candidates, key=lambda item: item.rank_key)[:REPLACEMENT_CAP]:
            if len(selected) >= cap:
                break
            selected.append(candidate.coordinate)
        remaining_floor = [
            candidates[coordinate] for coordinate in floor if coordinate not in selected
        ]
        for candidate in sorted(remaining_floor, key=lambda item: item.rank_key):
            if len(selected) >= cap:
                break
            selected.append(candidate.coordinate)
        if len(selected) < cap:
            for candidate in sorted(new_candidates, key=lambda item: item.rank_key):
                if candidate.coordinate not in selected:
                    selected.append(candidate.coordinate)
                if len(selected) >= cap:
                    break

    selected_set = set(selected)
    discarded = [{
        "coordinate": list(coordinate),
        "reason": "replaced_by_source_backed_semantic_bundle",
        "floor_rank": rank,
    } for rank, coordinate in enumerate(floor, 1) if coordinate not in selected_set]
    return selected[:cap], discarded


def _assessment(
    question: str,
    frame_id: str,
    family_ids: frozenset[str],
    selected: Sequence[Coordinate],
    candidates: Mapping[Coordinate, _Candidate],
) -> list[dict[str, Any]]:
    if not _NEGATIVE.search(question):
        return []
    basis = [
        coordinate for coordinate in selected
        if candidates[coordinate].semantic_types.intersection({
            "AUTHORITY_ALLOCATION", "FORMULA_EXPRESSION", "EXCEPTION_ASSERTION",
        }) or candidates[coordinate].edges
    ]
    if not basis:
        return []
    conclusion = (
        "DELEGATION_NOT_EXPLICITLY_SUPPORTED"
        if "위임" in question
        else "SEPARATE_ADJUSTMENT_NOT_EXPLICITLY_SUPPORTED"
        if "조정" in question
        else "NEGATIVE_AUTHORITY_REQUIRES_REVIEW"
    )
    basis_ids = sorted({
        assertion_id
        for coordinate in basis
        for assertion_id in candidates[coordinate].assertion_ids
    })
    return [{
        "schema_version": "legal-graph-v1",
        "row_type": "assessment",
        "layer": "runtime",
        "id": stable_id("assessment", frame_id, conclusion, basis_ids),
        "claim_id": frame_id,
        "status": AssessmentStatus.REQUIRES_REVIEW.value,
        "conclusion": conclusion,
        "basis_ids": basis_ids,
        "basis_coordinates": [list(value) for value in basis],
        "reasoning_mode": AssessmentReasoningMode.ABSENCE_WITHIN_CLOSED_BUNDLE.value,
        "confidence": 0.65,
        "requires_review": True,
        "family_ids": sorted(family_ids),
    }]


def plan_semantic_coordinates(
    index: Index,
    question: str,
    floor_coordinates: Iterable[Coordinate],
    *,
    snapshot: LegalGraphSnapshot,
    cap: int = 20,
    registry: QueryFamilyRegistry | None = None,
    family_hints: Iterable[str] = (),
    predicate_hints: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    floor = list(dict.fromkeys(
        coordinate
        for doc_id, node in floor_coordinates
        if (coordinate := _article_coordinate(index, doc_id, node)) is not None
    ))
    if snapshot.authority_generation != index.authority_generation:
        return [], {
            "enabled": True,
            "status": "fallback",
            "fallback": "authority_generation_mismatch",
            "before_count": len(floor),
            "after_count": len(floor),
            "selected_coordinates": [list(value) for value in floor],
        }
    registry = registry or default_registry()
    frame, hypotheses, active, family_ids, predicates = _active_families(
        question, snapshot, registry,
    )
    compiled_family_hints = frozenset(
        value for raw in family_hints
        if (value := str(raw)) and registry.get(value) is not None
    )
    compiled_predicate_hints = set()
    for raw in predicate_hints:
        value = str(raw)
        try:
            compiled_predicate_hints.add(RelationPredicate(value).value)
        except ValueError:
            continue
    family_ids = frozenset(set(family_ids) | set(compiled_family_hints))
    predicates = frozenset(set(predicates) | compiled_predicate_hints | {
        predicate
        for family_id in compiled_family_hints
        if (definition := registry.get(family_id)) is not None
        for predicate in definition.closure_predicates
    })
    query_terms = _query_terms(question, snapshot)
    floor_set = frozenset(floor)
    candidates = _landing(
        index,
        snapshot,
        query_terms,
        family_ids,
        frozenset(coordinate[0] for coordinate in floor),
        floor_set,
        question,
    )
    landing_coordinates = list(candidates)
    for coordinate in floor:
        candidates.setdefault(coordinate, _Candidate(coordinate))
    union_coordinates = list(candidates)
    closure_rows = _closure(
        index,
        question,
        snapshot,
        candidates,
        predicates,
        query_terms,
        _landing_families(family_ids),
    )
    closure_coordinates = list(candidates)
    bundles = _bundles(candidates)
    _apply_bundle_protection(candidates, bundles)
    selected, discarded = _final_selection(floor, candidates, cap=max(1, int(cap)))
    assessments = _assessment(question, frame.id, family_ids, selected, candidates)
    selected_rows = []
    for coordinate in selected:
        candidate = candidates[coordinate]
        selected_rows.append({
            "coordinate": coordinate,
            "score": round(candidate.score, 6),
            "floor_rank": candidate.floor_rank,
            "origins": sorted(candidate.origins),
            "matched_terms": sorted(candidate.matched_terms),
            "family_ids": sorted(candidate.family_ids),
            "semantic_types": sorted(candidate.semantic_types),
            "coverage_keys": sorted(candidate.coverage_keys),
            "assertion_ids": sorted(candidate.assertion_ids),
            "card_ids": sorted(candidate.card_ids),
            "edges": list(candidate.edges),
            "source_coordinates": sorted(candidate.source_coordinates),
            "protected": candidate.protected,
        })
    meta = {
        "enabled": True,
        "status": "selected" if selected != floor else "unchanged",
        "fallback": "",
        "generation_id": snapshot.generation_id,
        "content_sha256": snapshot.content_sha256,
        "authority_generation": snapshot.authority_generation,
        "query_frame": {
            "id": frame.id,
            "slots": {key: list(value) for key, value in frame.slots.items()},
            "requested_goals": list(frame.requested_goals),
        },
        "hypotheses": [item.to_dict() for item in hypotheses],
        "active_family_ids": sorted(family_ids),
        "allowed_predicates": sorted(predicates),
        "compiled_hints": {
            "family_ids": sorted(compiled_family_hints),
            "predicates": sorted(compiled_predicate_hints),
        },
        "query_terms": list(query_terms),
        "before_count": len(floor),
        "landing_count": len(landing_coordinates),
        "closure_edge_count": len(closure_rows),
        "after_count": len(selected),
        "selected_coordinates": [list(value) for value in selected],
        "discarded_floor": discarded,
        "decision_bundles": bundles,
        "legal_assessments": assessments,
        "closure_events": closure_rows[:TRACE_CANDIDATE_CAP],
        "closure_events_truncated": max(0, len(closure_rows) - TRACE_CANDIDATE_CAP),
        "stages": {
            "candidate-source": [list(value) for value in floor],
            "semantic-landing": [list(value) for value in landing_coordinates],
            "candidate-union": [list(value) for value in union_coordinates],
            "typed-closure": [list(value) for value in closure_coordinates],
            "bundle-rerank": [list(value) for value in selected],
            "candidate-present": [list(value) for value in selected],
        },
        "reason_counts": dict(sorted(Counter(
            row["reason"] for row in discarded
        ).items())),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    return selected_rows, meta


def extend_sections(
    index: Index,
    question: str,
    sections: Sequence[Section],
    *,
    cap: int = 20,
    root=None,
    snapshot: LegalGraphSnapshot | None = None,
    registry: QueryFamilyRegistry | None = None,
) -> tuple[list[Section], dict[str, Any]]:
    started = time.perf_counter()
    floor = list(sections)
    if snapshot is not None:
        load_result = LegalGraphLoadResult(snapshot, "injected", (), 0.0)
    else:
        load_result = current_for(index, root=root)
    if load_result.snapshot is None:
        return floor, {
            "enabled": True,
            "status": "fallback",
            "fallback": "snapshot_unavailable",
            "reasons": list(load_result.reasons),
            "before_count": len(floor),
            "after_count": len(floor),
            "added_count": 0,
            "load": load_result.as_dict(),
        }
    if not load_result.snapshot.semantic_cards:
        return floor, {
            "enabled": True,
            "status": "fallback",
            "fallback": "semantic_cards_unavailable",
            "before_count": len(floor),
            "after_count": len(floor),
            "added_count": 0,
            "load": load_result.as_dict(),
        }
    try:
        planned, meta = plan_semantic_coordinates(
            index,
            question,
            [(section.doc_id, section.node) for section in floor],
            snapshot=load_result.snapshot,
            cap=cap,
            registry=registry,
        )
        if not planned:
            meta["load"] = load_result.as_dict()
            return floor, meta
        floor_by_coordinate = {
            coordinate: section
            for section in floor
            if (coordinate := _article_coordinate(index, section.doc_id, section.node)) is not None
        }
        planned_by_coordinate = {tuple(row["coordinate"]): row for row in planned}
        new_coordinates = [
            tuple(row["coordinate"]) for row in planned
            if tuple(row["coordinate"]) not in floor_by_coordinate
        ]
        branches = []
        branch_by_coordinate = {}
        for coordinate in new_coordinates:
            branch = coordinates.article_branch(
                index,
                coordinate[0],
                coordinate[1],
                (),
                origin="legal-semantic-v2",
                reason="typed semantic landing or DecisionBundle closure",
            )
            if branch is not None and branch.coordinate == coordinate:
                branches.append(branch)
                branch_by_coordinate[coordinate] = branch
        text_cache: dict[Coordinate, str] = {}
        annotations = legal_evidence.annotate(
            index, question, branches, text_cache=text_cache,
        ) if branches else {"rows": []}
        annotation_by_coordinate = {
            (row["doc_id"], row["node"]): row for row in annotations["rows"]
        }
        output: list[Section] = []
        materialized_new: set[Coordinate] = set()
        for row in planned:
            coordinate = tuple(row["coordinate"])
            existing = floor_by_coordinate.get(coordinate)
            if existing is not None:
                output.append(existing)
                continue
            branch = branch_by_coordinate.get(coordinate)
            if branch is None:
                continue
            view = index.docs[branch.doc_id]
            source = next(iter(row["source_coordinates"]), coordinate)
            semantic_meta = dict(annotation_by_coordinate.get(coordinate, {}))
            semantic_meta["semantic_search"] = {
                "origins": row["origins"],
                "matched_terms": row["matched_terms"],
                "semantic_types": row["semantic_types"],
                "coverage_keys": row["coverage_keys"],
                "assertion_ids": row["assertion_ids"],
                "card_ids": row["card_ids"],
                "protected": row["protected"],
                "score": row["score"],
            }
            output.append(Section(
                n=0,
                doc_id=branch.doc_id,
                doc=branch.doc,
                node=branch.node,
                path=branch.path,
                page=(view.by_id.get(branch.node) or {}).get("page"),
                kind="의미엔티티·LegalGraph",
                matched=" · ".join(row["semantic_types"] or row["origins"]),
                text=text_cache.get(branch.coordinate, branch.body),
                ref_src={
                    "doc_id": source[0],
                    "node": source[1],
                    "path": "",
                    "surface": "typed semantic evidence",
                    "via": "legal-semantic-v2",
                },
                edges=[{
                    "predicate": edge.predicate,
                    "assertion_id": edge.assertion_id,
                    "projection_id": edge.projection_id,
                    "source": {
                        "doc_id": edge.source.document_id,
                        "node": edge.source.node_id,
                    },
                    "target": {
                        "doc_id": edge.target.document_id,
                        "node": edge.target.node_id,
                    },
                } for edge in row["edges"]],
                legal_meta=semantic_meta,
            ))
            materialized_new.add(coordinate)

        # A failed new materialization must not shrink the prior result.
        for section in floor:
            coordinate = _article_coordinate(index, section.doc_id, section.node)
            if len(output) >= cap:
                break
            if coordinate is not None and all(
                _article_coordinate(index, item.doc_id, item.node) != coordinate
                for item in output
            ):
                output.append(section)
        output = output[:cap]
        for number, section in enumerate(output, 1):
            section.n = number
        final_coordinates = [
            _article_coordinate(index, section.doc_id, section.node) for section in output
        ]
        final_coordinates = [value for value in final_coordinates if value is not None]
        meta["selected_coordinates"] = [list(value) for value in final_coordinates]
        meta["added"] = [
            {
                "doc_id": section.doc_id,
                "node": section.node,
                "doc": section.doc,
                "path": section.path,
                "source": section.ref_src,
                "edges": section.edges,
            }
            for section in output
            if _article_coordinate(index, section.doc_id, section.node) in materialized_new
        ]
        meta["added_count"] = len(meta["added"])
        meta["after_count"] = len(output)
        meta["load"] = load_result.as_dict()
        meta["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return output, meta
    except Exception as exc:
        return floor, {
            "enabled": True,
            "status": "fallback",
            "fallback": "baseline_preserved",
            "reasons": [f"{type(exc).__name__}:{exc}"],
            "before_count": len(floor),
            "after_count": len(floor),
            "added_count": 0,
            "load": load_result.as_dict(),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        }


__all__ = ["plan_semantic_coordinates", "extend_sections"]
