"""Query-conditional, add-only Legal Graph companion closure.

The existing LegalClosure result is the immutable universal floor.  This
module classifies the question into zero or more ADR-0098 query families and
uses only the predicates declared by those families to inspect outgoing ports
on already-selected ProvisionCards.  A target is added only when every gate
passes; no baseline coordinate is removed and the existing final cap remains
hard by consuming only its residual slots.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from lawrag.core.legal_graph import ClosureMode, stable_id
from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag import legal_evidence
from lawrag.core.rag.answer import Section
from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_graph_store import (
    EdgeLite,
    LegalGraphLoadResult,
    LegalGraphSnapshot,
    current_for,
)
from lawrag.core.rag.query_family_runtime import (
    UNKNOWN_FAMILY,
    QueryFamilyRegistry,
    default_registry,
    extract_query_frame,
)


GLOBAL_ADDITION_CAP = 6
PER_SEED_CAP = 4
TRACE_DECISION_CAP = 80
EXACT_SOURCE_PRECISIONS = frozenset({"EXACT_SPAN", "EXACT_UNIT"})
LEGISLATIVE_PREDICATES = frozenset({
    "LEGISLATIVE_DELEGATION",
    "LEGISLATIVE_REDELEGATION",
    "SUPPLEMENTS_BY_ADMINISTRATIVE_RULE",
})
LEGISLATIVE_QUERY_SIGNALS = (
    "대통령령", "총리령", "부령", "시행령", "시행규칙", "입법위임", "재위임",
)
LEGISLATIVE_SOURCE_SIGNALS = (
    "대통령령", "총리령", "부령", "시행령", "시행규칙", "고시로 정", "규정으로 정",
)
_TOKEN = re.compile(r"[A-Za-z0-9가-힣]+")
_NOISE = frozenset({
    "법률", "법령", "규정", "조문", "경우", "해당", "관련", "기준", "따라",
    "따른", "정하는", "정한다", "있는", "없는", "무엇", "어떻게", "여부",
})


@dataclass(slots=True)
class _EdgeCandidate:
    edge: EdgeLite
    decision: dict[str, Any]
    explicit_signal: bool
    overlap_terms: tuple[str, ...]

    @property
    def overlap_score(self) -> int:
        return _overlap_score(self.overlap_terms)

    @property
    def rank(self) -> tuple[Any, ...]:
        edge = self.edge
        return (
            -int(self.explicit_signal),
            -self.overlap_score,
            -int(edge.resolution == "EXACT_SOURCE_BACKED"),
            -int(edge.review_state == "SOURCE_BACKED"),
            -_precision_quality(edge.source.precision),
            -_precision_quality(edge.target.precision),
            edge.assertion_id,
            edge.projection_id,
        )


@dataclass(slots=True)
class _Target:
    coordinate: tuple[str, object]
    seed_coordinate: tuple[str, object]
    seed_rank: int
    candidates: list[_EdgeCandidate] = field(default_factory=list)

    @property
    def ordered_candidates(self) -> tuple[_EdgeCandidate, ...]:
        return tuple(sorted(self.candidates, key=lambda item: item.rank))

    @property
    def best_candidate(self) -> _EdgeCandidate:
        return self.ordered_candidates[0]

    @property
    def edges(self) -> tuple[EdgeLite, ...]:
        return tuple(item.edge for item in self.ordered_candidates)

    @property
    def explicit_signal(self) -> bool:
        return any(item.explicit_signal for item in self.candidates)

    @property
    def overlap_terms(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            term
            for candidate in self.ordered_candidates
            for term in candidate.overlap_terms
        ))

    @property
    def rank(self) -> tuple[Any, ...]:
        candidate = self.best_candidate
        return (
            *candidate.rank[:-2],
            self.seed_rank,
            candidate.edge.assertion_id,
            candidate.edge.projection_id,
            str(self.coordinate[0]),
            str(self.coordinate[1]),
        )


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
    """Append verified graph companions without deleting or reordering the floor."""
    started = time.perf_counter()
    floor = list(sections)
    if snapshot is not None:
        authority_reason = _authority_reason(index, snapshot)
        load_result = (
            LegalGraphLoadResult(None, "stale", (authority_reason,), 0.0)
            if authority_reason else
            LegalGraphLoadResult(snapshot, "injected", (), 0.0)
        )
    else:
        load_result = current_for(index, root=root)
    if load_result.snapshot is None:
        return floor, _unavailable_meta(load_result, len(floor), started)
    try:
        eligible_seed_coordinates = {
            coordinate
            for section in floor
            if (index.in_scope(section.doc_id) or section.is_companion)
            if (coordinate := _article_coordinate(
                index, section.doc_id, section.node
            )) is not None
        }
        additions, meta = plan_coordinates(
            index,
            question,
            [(section.doc_id, section.node) for section in floor],
            snapshot=load_result.snapshot,
            cap=cap,
            registry=registry,
            floor_count=len(floor),
            eligible_seed_coordinates=eligible_seed_coordinates,
        )
        if not additions:
            meta["load"] = load_result.as_dict()
            meta["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
            return floor, meta
        section_by_coordinate: dict[tuple[str, object], Section] = {}
        for section in floor:
            coordinate = _article_coordinate(index, section.doc_id, section.node)
            if coordinate is not None:
                section_by_coordinate.setdefault(coordinate, section)
        branches = []
        planned = []
        materialization_failures: list[dict[str, Any]] = []
        for addition in additions:
            doc_id, node = addition["coordinate"]
            branch = coordinates.article_branch(
                index,
                doc_id,
                node,
                (),
                origin="legal-graph-v1",
                reason="query-family conditional closure",
            )
            if branch is None or branch.coordinate != addition["coordinate"]:
                materialization_failures.append({
                    "coordinate": list(addition["coordinate"]),
                    "reason": (
                        "article_branch_missing" if branch is None
                        else "article_branch_coordinate_mismatch"
                    ),
                    "projection_ids": [
                        edge.projection_id for edge in addition["edges"]
                    ],
                })
                continue
            branches.append(branch)
            planned.append((addition, branch))
        text_cache: dict[tuple[str, object], str] = {}
        annotations = legal_evidence.annotate(
            index, question, branches, text_cache=text_cache
        )
        annotation_by_coordinate = {
            (row["doc_id"], row["node"]): row for row in annotations["rows"]
        }
        appended: list[Section] = []
        for addition, branch in planned:
            seed_coordinate = tuple(addition["seed_coordinate"])
            seed = section_by_coordinate.get(seed_coordinate)
            view = index.docs[branch.doc_id]
            edge_rows = [_edge_display(edge, position)
                         for position, edge in enumerate(addition["edges"], 1)]
            appended.append(Section(
                n=0,
                doc_id=branch.doc_id,
                doc=branch.doc,
                node=branch.node,
                path=branch.path,
                page=(view.by_id.get(branch.node) or {}).get("page"),
                kind="참조·LegalGraph",
                matched=" · ".join(dict.fromkeys(
                    edge.predicate for edge in addition["edges"]
                )),
                text=text_cache.get(branch.coordinate, branch.body),
                ref_src={
                    "doc_id": seed.doc_id if seed else seed_coordinate[0],
                    "node": seed.node if seed else seed_coordinate[1],
                    "path": seed.path if seed else "",
                    "surface": addition["edges"][0].source.label,
                    "via": "legal-graph-v1",
                },
                edges=edge_rows,
                legal_meta=annotation_by_coordinate.get(branch.coordinate, {}),
            ))
        out = floor + appended
        for number, section in enumerate(out, 1):
            section.n = number
        materialized_coordinates = {
            (section.doc_id, section.node) for section in appended
        }
        materialized_additions = [
            addition for addition in additions
            if addition["coordinate"] in materialized_coordinates
        ]
        _finalize_materialization_meta(
            meta,
            additions,
            materialized_additions,
            materialization_failures,
            floor_coordinates=[
                coordinate for section in floor
                if (coordinate := _article_coordinate(
                    index, section.doc_id, section.node
                )) is not None
            ],
            before_count=len(floor),
        )
        meta["load"] = load_result.as_dict()
        meta["added"] = [
            {
                "doc_id": section.doc_id,
                "node": section.node,
                "doc": section.doc,
                "path": section.path,
                "source": section.ref_src,
                "edges": section.edges,
            }
            for section in appended
        ]
        meta["added_count"] = len(appended)
        meta["after_count"] = len(out)
        meta["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return out, meta
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


def plan_coordinates(
    index: Index,
    question: str,
    floor_coordinates: Iterable[tuple[str, object]],
    *,
    snapshot: LegalGraphSnapshot,
    cap: int = 20,
    registry: QueryFamilyRegistry | None = None,
    floor_count: int | None = None,
    eligible_seed_coordinates: Iterable[tuple[str, object]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Gold-free graph plan shared by product wiring and the frozen replay."""
    started = time.perf_counter()
    raw_floor = list(floor_coordinates)
    original_floor_count = max(
        len(raw_floor),
        len(raw_floor) if floor_count is None else max(0, int(floor_count)),
    )
    floor: list[tuple[str, object]] = []
    for doc_id, node in raw_floor:
        coordinate = _article_coordinate(index, doc_id, node)
        if coordinate is not None and coordinate not in floor:
            floor.append(coordinate)
    authority_reason = _authority_reason(index, snapshot)
    if authority_reason:
        return [], _plan_fallback_meta(
            snapshot,
            floor,
            original_floor_count,
            authority_reason,
            started,
        )
    frame = extract_query_frame(
        question, authority_generation=snapshot.authority_generation
    )
    family_registry = registry or default_registry()
    hypotheses = family_registry.classify(frame)
    active = tuple(item for item in hypotheses if item.family_id != UNKNOWN_FAMILY)
    active_family_ids = tuple(item.family_id for item in active)
    allowed_predicates = frozenset(
        predicate
        for hypothesis in active
        for predicate in (
            family_registry.get(hypothesis.family_id).closure_predicates
            if family_registry.get(hypothesis.family_id) is not None else ()
        )
    )
    floor_set = set(floor)
    if eligible_seed_coordinates is None:
        eligible_seed_set = {
            coordinate for coordinate in floor if index.in_scope(coordinate[0])
        }
    else:
        eligible_seed_set = {
            coordinate
            for doc_id, node in eligible_seed_coordinates
            if (coordinate := _article_coordinate(index, doc_id, node)) is not None
        } & floor_set
    ineligible_seeds = [
        coordinate for coordinate in floor if coordinate not in eligible_seed_set
    ]
    slots = max(
        0,
        min(GLOBAL_ADDITION_CAP, max(0, int(cap) - original_floor_count)),
    )
    decisions: list[dict[str, Any]] = []
    eligible_pairs: list[_Target] = []

    if active and slots:
        for seed_rank, seed_coordinate in enumerate(floor):
            if seed_coordinate not in eligible_seed_set:
                continue
            pair_by_target: dict[tuple[str, object], _Target] = {}
            seen_projection_ids: set[str] = set()
            for edge in snapshot.incident(seed_coordinate, direction="outgoing"):
                decision = _base_decision(seed_coordinate, edge)
                if edge.projection_id in seen_projection_ids:
                    decision.update(
                        activated=False,
                        reason="rejected_duplicate_projection",
                        overlap_terms=[],
                        explicit_signal=False,
                        target_coordinate=None,
                    )
                    decisions.append(decision)
                    continue
                seen_projection_ids.add(edge.projection_id)
                reason, target_coordinate, overlap, explicit = _gate_edge(
                    index,
                    question,
                    active_family_ids,
                    allowed_predicates,
                    seed_coordinate,
                    edge,
                    floor_set,
                    snapshot,
                )
                decision.update(
                    activated=False,
                    reason=reason,
                    overlap_terms=list(overlap),
                    explicit_signal=explicit,
                    target_coordinate=(list(target_coordinate)
                                       if target_coordinate is not None else None),
                )
                decisions.append(decision)
                if reason != "eligible" or target_coordinate is None:
                    continue
                target = pair_by_target.setdefault(
                    target_coordinate,
                    _Target(
                        coordinate=target_coordinate,
                        seed_coordinate=seed_coordinate,
                        seed_rank=seed_rank,
                    ),
                )
                target.candidates.append(
                    _EdgeCandidate(
                        edge=edge,
                        decision=decision,
                        explicit_signal=explicit,
                        overlap_terms=overlap,
                    )
                )
            for target_rank, target in enumerate(
                sorted(pair_by_target.values(), key=lambda item: item.rank)
            ):
                if target_rank >= PER_SEED_CAP:
                    for candidate in target.candidates:
                        candidate.decision["reason"] = "rejected_per_seed_cap"
                    continue
                for candidate in target.candidates:
                    candidate.decision["reason"] = "eligible_unique_target"
                eligible_pairs.append(target)

    unique_targets: dict[tuple[str, object], _Target] = {}
    for target in sorted(eligible_pairs, key=lambda item: item.rank):
        if target.coordinate not in unique_targets:
            unique_targets[target.coordinate] = target
            continue
        for candidate in target.candidates:
            candidate.decision["reason"] = "rejected_duplicate_target"

    ordered = list(unique_targets.values())
    selected = ordered[:slots]
    selected_projection_ids = {
        edge.projection_id for target in selected for edge in target.edges
    }
    globally_capped_projection_ids = {
        edge.projection_id for target in ordered[slots:] for edge in target.edges
    }
    for decision in decisions:
        projection_id = decision["projection_id"]
        if projection_id in selected_projection_ids:
            decision["activated"] = True
            decision["reason"] = "activated"
        elif projection_id in globally_capped_projection_ids:
            decision["reason"] = "rejected_global_or_residual_cap"

    additions = [{
        "coordinate": target.coordinate,
        "seed_coordinate": target.seed_coordinate,
        "overlap_terms": target.overlap_terms,
        "explicit_signal": target.explicit_signal,
        "edges": target.edges,
        "provenance_pair": {
            "source": list(target.seed_coordinate),
            "target": list(target.coordinate),
            "projection_ids": [edge.projection_id for edge in target.edges],
            "assertion_ids": [edge.assertion_id for edge in target.edges],
        },
    } for target in selected]
    counts = Counter(str(row["reason"]) for row in decisions)
    selected_decisions = [row for row in decisions if row.get("activated")]
    rejected_decisions = [row for row in decisions if not row.get("activated")]
    visible_decisions = (selected_decisions + rejected_decisions)[:TRACE_DECISION_CAP]
    status = (
        "inactive" if not active
        else "no_residual_slots" if not slots
        else "no_scope_eligible_seed" if not eligible_seed_set
        else "expanded" if additions
        else "no_eligible_edge"
    )
    trace_id = stable_id(
        "retrieval_trace",
        frame.id,
        snapshot.generation_id,
        original_floor_count,
        floor,
        [list(item["coordinate"]) for item in additions],
    )
    meta = {
        "enabled": True,
        "status": status,
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
        "active_family_ids": list(active_family_ids),
        "allowed_predicates": sorted(allowed_predicates),
        "policy": {
            "direction": "outgoing",
            "modes": [ClosureMode.REQUIRED_WHEN_ACTIVATED.value],
            "hops": 1,
            "global_addition_cap": GLOBAL_ADDITION_CAP,
            "per_seed_cap": PER_SEED_CAP,
            "per_seed_cap_unit": "unique_target",
            "provenance_grouping": "source_article_target_article_pair",
            "baseline_is_immutable_floor": True,
            "contextual_enabled": False,
        },
        "trace_id": trace_id,
        "before_count": original_floor_count,
        "canonical_floor_count": len(floor),
        "scope_eligible_seed_count": len(eligible_seed_set),
        "scope_ineligible_seeds": [list(value) for value in ineligible_seeds],
        "residual_slots": slots,
        "considered_count": len(decisions),
        "eligible_target_count": len(ordered),
        "added_count": len(additions),
        "after_count": original_floor_count + len(additions),
        "reason_counts": dict(sorted(counts.items())),
        "decisions": visible_decisions,
        "decisions_truncated": max(0, len(decisions) - len(visible_decisions)),
        "selected": [_selected_row(item) for item in additions],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    return additions, meta


def _gate_edge(
    index: Index,
    question: str,
    active_family_ids: tuple[str, ...],
    allowed_predicates: frozenset[str],
    seed_coordinate: tuple[str, object],
    edge: EdgeLite,
    floor_set: set[tuple[str, object]],
    snapshot: LegalGraphSnapshot,
) -> tuple[str, tuple[str, object] | None, tuple[str, ...], bool]:
    if edge.mode != ClosureMode.REQUIRED_WHEN_ACTIVATED.value:
        return "rejected_non_required_mode", None, (), False
    if edge.predicate not in allowed_predicates:
        return "rejected_family_predicate", None, (), False
    if edge.source.precision not in EXACT_SOURCE_PRECISIONS:
        return "rejected_source_precision", None, (), False
    source_ports = snapshot.ports_by_article.get(seed_coordinate)
    if source_ports is None:
        return "rejected_source_card_missing", None, (), False
    if edge.projection_id not in source_ports.outgoing:
        return "rejected_source_outgoing_port_mismatch", None, (), False
    if _card_coordinate(source_ports) != seed_coordinate:
        return "rejected_source_card_coordinate_mismatch", None, (), False
    source_view = index.docs.get(edge.source.document_id)
    if source_view is None or edge.source.node_id not in source_view.by_id:
        return "failed_source_missing", None, (), False
    source_root = coordinates.article_root(source_view, edge.source.node_id)
    if (edge.source.document_id, source_root) != seed_coordinate:
        return "rejected_source_port_mismatch", None, (), False
    source_reason, source_text = _verified_source_text(source_view, edge)
    if source_reason:
        return source_reason, None, (), False
    overlap = _overlap_terms(question, source_text)
    packed_question = _packed(question)
    packed_source = _packed(source_text)
    explicit = any(_packed(signal) in packed_question for signal in LEGISLATIVE_QUERY_SIGNALS)
    if edge.predicate in LEGISLATIVE_PREDICATES:
        source_is_legislative = any(
            _packed(signal) in packed_source for signal in LEGISLATIVE_SOURCE_SIGNALS
        )
        classification_completion = (
            "CLASSIFICATION" in active_family_ids and source_is_legislative and bool(overlap)
        )
        if not ((explicit and source_is_legislative) or classification_completion):
            return "rejected_legislative_ambiguity", None, overlap, explicit
    if not overlap and not (explicit and edge.predicate in LEGISLATIVE_PREDICATES):
        return "rejected_endpoint_irrelevant", None, (), explicit
    if edge.target.kind != "STRUCTURAL_UNIT" or edge.target.node_id is None:
        return "rejected_non_structural_target", None, overlap, explicit
    if not index.relation_allowed(
        edge.source.document_id, edge.target.document_id
    ):
        return "rejected_cross_dataset_policy", None, overlap, explicit
    target_view = index.docs.get(edge.target.document_id)
    if target_view is None or edge.target.node_id not in target_view.by_id:
        return "failed_target_missing", None, overlap, explicit
    if not _is_current_target(index, edge.target.document_id):
        return "rejected_target_not_current", None, overlap, explicit
    target_root = coordinates.article_root(target_view, edge.target.node_id)
    target_coordinate = (edge.target.document_id, target_root)
    target_ports = snapshot.ports_by_article.get(target_coordinate)
    if target_ports is None:
        return "rejected_target_card_missing", target_coordinate, overlap, explicit
    if _card_coordinate(target_ports) != target_coordinate:
        return (
            "rejected_target_card_coordinate_mismatch",
            target_coordinate,
            overlap,
            explicit,
        )
    if edge.projection_id not in target_ports.incoming:
        return "rejected_target_incoming_port_mismatch", target_coordinate, overlap, explicit
    if target_coordinate == seed_coordinate:
        return "rejected_self_edge", target_coordinate, overlap, explicit
    if target_coordinate in floor_set:
        return "already_in_floor", target_coordinate, overlap, explicit
    return "eligible", target_coordinate, overlap, explicit


def _verified_source_text(source_view, edge: EdgeLite) -> tuple[str, str]:
    """Return only the selector-proven text used by the relevance gate."""
    endpoint = edge.source
    node = source_view.by_id[endpoint.node_id]
    if endpoint.precision == "EXACT_UNIT":
        return "", source_view.section_text(node, cap=2400)
    if endpoint.precision != "EXACT_SPAN":
        return "rejected_source_precision", ""

    block_id = getattr(endpoint, "block_id", None)
    start = getattr(endpoint, "start", None)
    end = getattr(endpoint, "end", None)
    quote_sha256 = str(getattr(endpoint, "quote_sha256", "") or "")
    if (
        block_id is None
        or isinstance(block_id, bool)
        or not isinstance(block_id, (int, str))
        or isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or end <= start
        or not re.fullmatch(r"[0-9a-f]{64}", quote_sha256)
    ):
        return "failed_source_span_selector", ""
    block = source_view.block_by_idx.get(block_id)
    if block is None and isinstance(block_id, str) and block_id.isdigit():
        block = source_view.block_by_idx.get(int(block_id))
    if block is None:
        return "failed_source_span_block_missing", ""
    text = str(block.get("text") or "")
    if end > len(text):
        return "failed_source_span_bounds", ""
    span = node.get("span") or ()
    normalized_block_id = (
        int(block_id) if isinstance(block_id, str) and block_id.isdigit() else block_id
    )
    if (
        isinstance(normalized_block_id, int)
        and isinstance(span, (list, tuple))
        and len(span) == 2
        and all(isinstance(value, int) for value in span)
        and not (span[0] <= normalized_block_id < max(span[1], span[0] + 1))
    ):
        return "failed_source_span_node_mismatch", ""
    quote = text[start:end]
    actual = hashlib.sha256(quote.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(actual, quote_sha256):
        return "failed_source_span_hash", ""
    return "", quote[:2400]


def _card_coordinate(ports) -> tuple[str, object | None]:
    return ports.endpoint.document_id, ports.endpoint.node_id


def _is_current_target(index: Index, doc_id: str) -> bool:
    view = index.docs.get(doc_id)
    if view is None or not view.is_current:
        return False
    canonical = index.canonical_doc_ids or frozenset()
    return not (
        canonical
        and view.kind in {"law", "admrul"}
        and doc_id not in canonical
    )


def _overlap_terms(question: str, source_text: str) -> tuple[str, ...]:
    packed_question = _packed(question)
    packed_source = _packed(source_text)
    question_tokens = [
        token.casefold() for token in _TOKEN.findall(question)
        if len(token) >= 3 and token not in _NOISE
    ]
    source_tokens = [
        token.casefold() for token in _TOKEN.findall(source_text)
        if len(token) >= 3 and token not in _NOISE
    ]
    hits: list[str] = []
    for token in (*question_tokens, *source_tokens):
        packed = _packed(token)
        if len(packed) < 3 or packed in _NOISE:
            continue
        if packed in packed_question and packed in packed_source and packed not in hits:
            hits.append(packed)
    return tuple(hits[:12])


def _overlap_score(terms: Iterable[str]) -> int:
    """Prefer one specific endpoint match over many duplicated generic edges."""
    return sum(len(term) ** 2 for term in set(terms))


def _precision_quality(value: str) -> int:
    return {"EXACT_SPAN": 2, "EXACT_UNIT": 1}.get(str(value), 0)


def _article_coordinate(
    index: Index, doc_id: str, node: object | None
) -> tuple[str, object] | None:
    view = index.docs.get(doc_id)
    if view is None or node not in view.by_id:
        return None
    return doc_id, coordinates.article_root(view, node)


def _base_decision(seed: tuple[str, object], edge: EdgeLite) -> dict[str, Any]:
    return {
        "seed": list(seed),
        "direction": "outgoing",
        "projection_id": edge.projection_id,
        "assertion_id": edge.assertion_id,
        "predicate": edge.predicate,
        "family": edge.family,
        "closure_mode": edge.mode,
        "source": _endpoint_dict(edge.source),
        "target": _endpoint_dict(edge.target),
    }


def _endpoint_dict(endpoint) -> dict[str, Any]:
    value = {
        "kind": endpoint.kind,
        "precision": endpoint.precision,
        "ref_id": endpoint.ref_id,
        "document_id": endpoint.document_id,
        "node_id": endpoint.node_id,
        "coordinate": endpoint.coordinate,
        "label": endpoint.label,
    }
    for field_name in ("block_id", "start", "end", "quote_sha256"):
        field_value = getattr(endpoint, field_name, None)
        if field_value is not None and field_value != "":
            value[field_name] = field_value
    return value


def _selected_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": item["coordinate"][0],
        "node": item["coordinate"][1],
        "source_doc_id": item["seed_coordinate"][0],
        "source_node": item["seed_coordinate"][1],
        "assertion_ids": [edge.assertion_id for edge in item["edges"]],
        "projection_ids": [edge.projection_id for edge in item["edges"]],
        "predicates": list(dict.fromkeys(
            edge.predicate for edge in item["edges"]
        )),
        "provenance_pair": dict(item["provenance_pair"]),
    }


def _authority_reason(index: Index, snapshot: LegalGraphSnapshot) -> str:
    expected = str(index.authority_generation or "")
    actual = str(snapshot.authority_generation or "")
    if not expected:
        return "index authority_generation is unavailable"
    if actual != expected:
        return f"authority_generation:{actual}!={expected}"
    return ""


def _plan_fallback_meta(
    snapshot: LegalGraphSnapshot,
    floor: Sequence[tuple[str, object]],
    before_count: int,
    reason: str,
    started: float,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "status": "fallback",
        "fallback": "baseline_preserved",
        "reasons": [reason],
        "generation_id": snapshot.generation_id,
        "content_sha256": snapshot.content_sha256,
        "authority_generation": snapshot.authority_generation,
        "before_count": before_count,
        "canonical_floor_count": len(floor),
        "residual_slots": 0,
        "considered_count": 0,
        "eligible_target_count": 0,
        "added_count": 0,
        "after_count": before_count,
        "reason_counts": {"authority_mismatch": 1},
        "decisions": [],
        "decisions_truncated": 0,
        "selected": [],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def _finalize_materialization_meta(
    meta: dict[str, Any],
    planned: Sequence[dict[str, Any]],
    materialized: Sequence[dict[str, Any]],
    failures: Sequence[dict[str, Any]],
    *,
    floor_coordinates: Sequence[tuple[str, object]],
    before_count: int,
) -> None:
    """Make selected/activated trace rows describe sections actually returned."""
    materialized_projection_ids = {
        edge.projection_id for item in materialized for edge in item["edges"]
    }
    materialized_coordinates = {item["coordinate"] for item in materialized}
    failed_projection_ids = {
        edge.projection_id
        for item in planned
        if item["coordinate"] not in materialized_coordinates
        for edge in item["edges"]
    }
    for decision in meta.get("decisions") or ():
        projection_id = decision.get("projection_id")
        if decision.get("activated") and projection_id in failed_projection_ids:
            decision["activated"] = False
            decision["reason"] = "failed_materialization"
        elif projection_id in materialized_projection_ids:
            decision["activated"] = True
            decision["reason"] = "activated"
    counts = Counter(meta.get("reason_counts") or {})
    failed_count = len(failed_projection_ids)
    if failed_count:
        counts["activated"] = max(0, counts["activated"] - failed_count)
        if not counts["activated"]:
            counts.pop("activated", None)
        counts["failed_materialization"] += failed_count
    meta["reason_counts"] = dict(sorted(counts.items()))
    meta["planned_count"] = len(planned)
    meta["selected"] = [_selected_row(item) for item in materialized]
    meta["materialization"] = {
        "planned_count": len(planned),
        "materialized_count": len(materialized),
        "failed_count": len(failures),
        "failures": list(failures),
    }
    meta["added_count"] = len(materialized)
    meta["before_count"] = before_count
    meta["after_count"] = before_count + len(materialized)
    if failures:
        meta["status"] = "expanded_partial" if materialized else "materialization_failed"
        if not materialized:
            meta["fallback"] = "baseline_preserved"
        meta.setdefault("reasons", []).append("one_or_more_targets_not_materialized")
    meta["trace_id"] = stable_id(
        "retrieval_trace",
        (meta.get("query_frame") or {}).get("id", ""),
        meta.get("generation_id", ""),
        "materialized",
        before_count,
        list(floor_coordinates),
        [list(item["coordinate"]) for item in materialized],
    )


def rollback_to_floor(
    meta: dict[str, Any],
    before_count: int,
    reason: str,
) -> dict[str, Any]:
    """Return a trace-consistent fail-open graph result for runtime rollback."""
    value = dict(meta)
    decisions = [dict(row) for row in (meta.get("decisions") or ())]
    visible_rolled_back = 0
    for decision in decisions:
        if decision.get("activated"):
            decision["activated"] = False
            decision["reason"] = "failed_runtime_reconciliation"
            visible_rolled_back += 1
    counts = Counter(meta.get("reason_counts") or {})
    activated_count = int(counts.pop("activated", 0))
    if activated_count:
        counts["failed_runtime_reconciliation"] += activated_count
    previous_materialization = dict(meta.get("materialization") or {})
    rolled_back_materialized = int(
        previous_materialization.get("materialized_count")
        or meta.get("added_count")
        or 0
    )
    value.update({
        "status": "fallback",
        "fallback": "baseline_preserved",
        "reasons": [*(meta.get("reasons") or ()), reason],
        "before_count": before_count,
        "after_count": before_count,
        "added_count": 0,
        "added": [],
        "selected": [],
        "decisions": decisions,
        "reason_counts": dict(sorted(counts.items())),
        "materialization": {
            **previous_materialization,
            "materialized_count": 0,
            "rolled_back_count": rolled_back_materialized,
        },
        "reachability": {
            "status": "rollback",
            "final_count": before_count,
        },
        "rollback": {
            "reason": reason,
            "planned_added_count": int(meta.get("added_count") or 0),
            "activated_projection_count": activated_count,
            "visible_activated_projection_count": visible_rolled_back,
        },
    })
    return value


def _edge_display(edge: EdgeLite, position: int) -> dict[str, Any]:
    return {
        "id": f"LG{position}",
        "from": edge.source.label or edge.source.coordinate,
        "to": edge.target.label or edge.target.coordinate,
        "relation": edge.predicate,
        "surface": "",
        "projection_id": edge.projection_id,
        "assertion_id": edge.assertion_id,
        "family": edge.family,
        "closure_mode": edge.mode,
        "source": _endpoint_dict(edge.source),
        "target": _endpoint_dict(edge.target),
    }


def _unavailable_meta(
    load_result: LegalGraphLoadResult,
    before_count: int,
    started: float,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "status": "fallback",
        "fallback": "baseline_preserved",
        "reasons": list(load_result.reasons),
        "before_count": before_count,
        "after_count": before_count,
        "added_count": 0,
        "load": load_result.as_dict(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def disabled_meta(before_count: int) -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "disabled",
        "fallback": "",
        "reasons": ["feature_switch_off"],
        "before_count": before_count,
        "after_count": before_count,
        "added_count": 0,
        "load": {"status": "not_read", "reasons": ["feature_switch_off"]},
        "elapsed_ms": 0.0,
    }


def _packed(value: object) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value or "").casefold())
