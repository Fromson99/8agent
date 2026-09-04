"""Bounded global augmenting search over a canonical proof basis.

This module is an experiment-only successor to :mod:`proof_basis_exchange`.
It deliberately leaves the frozen ADR-0073 implementation untouched.  The
ground set, canonical source witnesses, typed edge receipts, and proof-cell
lattice are inherited from that module; only the basis solver changes.

The solver compares complete add/evict bundles instead of committing greedy
one-step exchanges.  It searches every admissible bundle of at most four
additions and four evictions, retains only final bases which componentwise
dominate the incumbent lattice, and chooses one deterministic lexicographic
optimum.  Missing floor witnesses precede newly closed question-conditioned
hard edges in that objective.  A partial 3/4-character query n-gram can guide
a typed companion edge, but can never admit a stand-alone direct candidate.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations
import math
from typing import Iterable, Mapping

from lawrag.core.rag import proof_basis_exchange as frozen_basis
from lawrag.core.rag import termexplore
from lawrag.core.rag.index import Index


PRESENTED_MAX = frozen_basis.PRESENTED_MAX
BUNDLE_MAX = 4
# Exact two-character query tokens receive quality 6 in ADR-0073.  Backoff
# n-grams receive quality 2 or 3, so this boundary is stable and explicit.
STRONG_QUERY_MIN_QUALITY = 6

ProofRecord = frozen_basis.ProofRecord
EdgeReceipt = frozen_basis.EdgeReceipt
canonicalize = frozen_basis.canonicalize
build_registry = frozen_basis.build_registry
validate_span = frozen_basis.validate_span


@dataclass(frozen=True)
class _BundleChoice:
    additions: tuple[ProofRecord, ...]
    evictions: tuple[ProofRecord, ...]
    final: tuple[ProofRecord, ...]
    after: Mapping[str, int]
    score: tuple[int, ...]
    objective: Mapping[str, int]
    signature: tuple[str, ...]


def _record_key(record: ProofRecord) -> tuple[int, str, str]:
    return (int(record.pool_rank), record.candidate_id,
            repr(record.coordinate))


def _dedupe(records: Iterable[ProofRecord]) -> list[ProofRecord]:
    """Return a stable coordinate-unique registry independent of input order."""

    ordered = sorted(records, key=lambda record: (
        repr(record.coordinate), -int(record.relevance), *_record_key(record)))
    by_coordinate: dict[tuple[str, object], ProofRecord] = {}
    for record in ordered:
        by_coordinate.setdefault(record.coordinate, record)
    return sorted(by_coordinate.values(), key=_record_key)


def _strong_query_cells(record: ProofRecord) -> dict[str, int]:
    return {cell: quality for cell, quality in record.query_cells
            if int(quality) >= STRONG_QUERY_MIN_QUALITY}


def _span_legal_role_cells(record: ProofRecord) -> dict[str, int]:
    """Return full query tokens co-grounded with a legal role in one span.

    ADR-0076 does not treat an article-wide token/role coincidence as a direct
    direct witness.  The exact full token and one of the question-matched
    legal roles must both occur in the immutable source span saved on the
    record.  Backoff n-grams remain below ``STRONG_QUERY_MIN_QUALITY``.
    """

    role_names = {
        cell.split(":", 1)[1] for cell, _quality in record.role_cells
        if cell.startswith("role:")
    }
    if not role_names:
        return {}
    span = str(record.span_text or "")
    if not (role_names & frozen_basis._roles(span)):
        return {}
    folded = span.casefold()
    return {
        cell: quality for cell, quality in _strong_query_cells(record).items()
        if cell.split(":", 1)[1].casefold() in folded
    }


def _question_supported(record: ProofRecord) -> bool:
    """Whether the record carries a full-token or legal-role signal."""

    return bool(_strong_query_cells(record) or record.role_cells)


def _span_lattice(records: Iterable[ProofRecord],
                  floor_coordinates: set[tuple[str, object]]) -> dict[str, int]:
    values = list(records)
    selected_coordinates = {record.coordinate for record in values}
    out: dict[str, int] = {}
    for record in values:
        cells = dict(record.query_cells)
        for cell, quality in record.role_cells:
            cells[cell] = max(cells.get(cell, 0), int(quality))
        if record.coordinate in floor_coordinates:
            cells[f"floor:{record.candidate_id}"] = 4
        for edge in record.edges:
            if edge.other_coordinate not in selected_coordinates:
                continue
            if edge.dependency_class == "hard_closure":
                cells[f"edge:{edge.edge_id}"] = 3
            elif (edge.dependency_class == "conditional_dependency"
                  and record.query_cells):
                cells[f"edge:{edge.edge_id}"] = 2
        for cell, quality in cells.items():
            out[cell] = max(out.get(cell, 0), int(quality))
    return out


def _dominates(after: Mapping[str, int], before: Mapping[str, int]) -> bool:
    return all(after.get(cell, 0) >= quality
               for cell, quality in before.items())


def _edge_map(records: Iterable[ProofRecord], dependency_class: str,
              question_support: Mapping[tuple[str, object], bool] | None = None) \
        -> dict[str, str]:
    """Question-conditioned, closed edge IDs mapped to relation kinds."""

    values = list(records)
    by_coordinate = {record.coordinate: record for record in values}
    selected_coordinates = set(by_coordinate)
    out: dict[str, str] = {}
    for record in values:
        for edge in record.edges:
            if (edge.dependency_class != dependency_class
                    or edge.other_coordinate not in selected_coordinates):
                continue
            other = by_coordinate.get(edge.other_coordinate)
            record_supported = (
                question_support.get(record.coordinate, False)
                if question_support is not None
                else _question_supported(record))
            other_supported = bool(other) and (
                question_support.get(other.coordinate, False)
                if question_support is not None
                else _question_supported(other))
            if not record_supported and not other_supported:
                continue
            out.setdefault(edge.edge_id, edge.kind)
    return out


def _candidate_reasons(
        record: ProofRecord,
        registry: Mapping[tuple[str, object], ProofRecord],
        selected_coordinates: set[tuple[str, object]],
        floor_coordinates: set[tuple[str, object]],
        span_role_cells: Mapping[str, Mapping[str, int]] | None = None,
        question_support: Mapping[tuple[str, object], bool] | None = None,
) -> tuple[str, ...]:
    """Classify admissibility without ranking or truncating hard candidates."""

    reasons: list[str] = []
    if record.coordinate in floor_coordinates:
        reasons.append("floor_recovery")
    # A whole query token is not enough by itself.  Requiring a question-
    # matched legal role in the same saved span prevents article-wide token/
    # role coincidences from becoming stand-alone jump points.
    direct_cells = (
        span_role_cells.get(record.candidate_id, {})
        if span_role_cells is not None else _span_legal_role_cells(record))
    if direct_cells:
        reasons.append("direct_span_legal_role")

    for dependency_class, label in (
            ("hard_closure", "hard_dependency"),
            ("conditional_dependency", "conditional_dependency")):
        matched = False
        for edge in record.edges:
            if edge.dependency_class != dependency_class:
                continue
            other = registry.get(edge.other_coordinate)
            # A query-bearing endpoint may close against any registered
            # companion.  A non-query endpoint is admitted only as the
            # companion of another question-supported endpoint.  Merely being
            # selected or in the floor is not itself question support.
            record_supported = (
                question_support.get(record.coordinate, False)
                if question_support is not None
                else _question_supported(record))
            other_supported = other is not None and (
                question_support.get(other.coordinate, False)
                if question_support is not None
                else _question_supported(other))
            if record_supported or other_supported:
                matched = True
                break
        if matched:
            reasons.append(label)
    return tuple(reasons)


def _strong_query_lattice(records: Iterable[ProofRecord]) -> dict[str, int]:
    out: dict[str, int] = {}
    for record in records:
        for cell, quality in _strong_query_cells(record).items():
            out[cell] = max(out.get(cell, 0), quality)
    return out


def _span_role_lattice(
        records: Iterable[ProofRecord],
        span_role_cells: Mapping[str, Mapping[str, int]] | None = None,
) -> dict[str, int]:
    out: dict[str, int] = {}
    for record in records:
        cells = (
            span_role_cells.get(record.candidate_id, {})
            if span_role_cells is not None
            else _span_legal_role_cells(record))
        for cell, quality in cells.items():
            out[cell] = max(out.get(cell, 0), quality)
    return out


def _companion_query_quality(
        records: Iterable[ProofRecord], edge_ids: set[str]) -> int:
    """Score the best query grounding attached to each newly closed edge."""

    values = list(records)
    by_coordinate = {record.coordinate: record for record in values}
    quality_by_edge: dict[str, int] = {}
    for record in values:
        own = max((quality for _cell, quality in record.query_cells), default=0)
        for edge in record.edges:
            if edge.edge_id not in edge_ids or edge.other_coordinate not in by_coordinate:
                continue
            other = by_coordinate[edge.other_coordinate]
            other_quality = max(
                (quality for _cell, quality in other.query_cells), default=0)
            quality_by_edge[edge.edge_id] = max(
                quality_by_edge.get(edge.edge_id, 0), own, other_quality)
    return sum(quality_by_edge.values())


def _objective(
        final: tuple[ProofRecord, ...],
        additions: tuple[ProofRecord, ...],
        evictions: tuple[ProofRecord, ...],
        after: Mapping[str, int],
        before: Mapping[str, int],
        before_floor_count: int,
        before_hard: Mapping[str, str],
        before_conditional: Mapping[str, str],
        before_span_role: Mapping[str, int],
        floor_coordinates: set[tuple[str, object]],
        span_role_cells: Mapping[str, Mapping[str, int]] | None = None,
        question_support: Mapping[tuple[str, object], bool] | None = None,
) -> tuple[tuple[int, ...], dict[str, int]]:
    final_hard = _edge_map(final, "hard_closure", question_support)
    final_conditional = _edge_map(
        final, "conditional_dependency", question_support)
    new_hard_ids = set(final_hard) - set(before_hard)
    new_conditional_ids = set(final_conditional) - set(before_conditional)
    new_hard_kinds = {final_hard[edge_id] for edge_id in new_hard_ids}
    new_conditional_kinds = {
        final_conditional[edge_id] for edge_id in new_conditional_ids}
    final_span_role = _span_role_lattice(final, span_role_cells)
    gained_proof_cells = {
        cell for cell, quality in after.items()
        if quality > before.get(cell, 0)
    }
    gained_floor_cells = {
        cell for cell in gained_proof_cells if cell.startswith("floor:")
    }
    gained_hard_cells = {
        f"edge:{edge_id}" for edge_id in new_hard_ids
        if after.get(f"edge:{edge_id}", 0)
        > before.get(f"edge:{edge_id}", 0)
    }
    gained_span_role_cells = {
        cell for cell, quality in final_span_role.items()
        if quality > before_span_role.get(cell, 0)
    }
    gained_conditional_cells = {
        f"edge:{edge_id}" for edge_id in new_conditional_ids
        if after.get(f"edge:{edge_id}", 0)
        > before.get(f"edge:{edge_id}", 0)
    }
    gained_role_cells = {
        cell for cell in gained_proof_cells if cell.startswith("role:")
    }
    categorized_proof_cells = (
        gained_floor_cells | gained_hard_cells
        | gained_conditional_cells | gained_role_cells
        | (gained_span_role_cells & gained_proof_cells)
    )
    other_gained_cells = gained_proof_cells - categorized_proof_cells
    gained_quality = sum(
        max(0, quality - before.get(cell, 0))
        for cell, quality in after.items())
    recovered_floor = (
        sum(record.coordinate in floor_coordinates for record in final)
        - before_floor_count)
    companion_quality = _companion_query_quality(final, new_hard_ids)
    final_relevance = sum(int(record.relevance) for record in final)
    added_pool_rank = sum(int(record.pool_rank) for record in additions)

    public = {
        "recovered_floor_witnesses": recovered_floor,
        "new_hard_relation_kinds": len(new_hard_kinds),
        "new_hard_edges": len(new_hard_ids),
        "new_conditional_relation_kinds": len(new_conditional_kinds),
        "new_conditional_edges": len(new_conditional_ids),
        "hard_companion_query_quality": companion_quality,
        "question_conditioned_hard_edge_cells": len(gained_hard_cells),
        "span_grounded_full_token_role_cells": len(gained_span_role_cells),
        "conditional_and_question_role_cells": (
            len(gained_conditional_cells) + len(gained_role_cells)),
        "other_verified_proof_cell_gain": len(other_gained_cells),
        "gained_quality": gained_quality,
        "gained_cells": len(gained_proof_cells),
        "final_relevance": final_relevance,
        "added_pool_rank_sum": added_pool_rank,
        "bundle_additions": len(additions),
        "bundle_evictions": len(evictions),
        "total_changes": len(additions) + len(evictions),
    }
    # This tuple is intentionally one-for-one with the frozen ADR-0076 order.
    # More detailed diagnostics above are receipts only and do not affect the
    # outcome.
    score = (
        recovered_floor,
        len(gained_hard_cells),
        len(gained_span_role_cells),
        len(gained_conditional_cells) + len(gained_role_cells),
        len(other_gained_cells),
        final_relevance,
        -(len(additions) + len(evictions)),
    )
    return score, public


def _bundle_signature(final: Iterable[ProofRecord]) -> tuple[str, ...]:
    """Canonical final-basis tie-break frozen by ADR-0076."""

    return tuple(sorted(repr(record.coordinate) for record in final))


def _additions_are_closed(
        final: Iterable[ProofRecord], additions: Iterable[ProofRecord],
        reasons: Mapping[str, tuple[str, ...]],
        floor_coordinates: set[tuple[str, object]],
        question_support: Mapping[tuple[str, object], bool] | None = None) -> bool:
    """Reject relation admissions whose companion is absent from the basis."""

    values = list(final)
    by_coordinate = {record.coordinate: record for record in values}
    for record in additions:
        labels = set(reasons.get(record.candidate_id) or ())
        if (record.coordinate in floor_coordinates
                or "direct_span_legal_role" in labels):
            continue
        allowed_classes: set[str] = set()
        if "hard_dependency" in labels:
            allowed_classes.add("hard_closure")
        if "conditional_dependency" in labels:
            allowed_classes.add("conditional_dependency")
        closed = False
        for edge in record.edges:
            other = by_coordinate.get(edge.other_coordinate)
            if edge.dependency_class not in allowed_classes or other is None:
                continue
            record_supported = (
                question_support.get(record.coordinate, False)
                if question_support is not None
                else _question_supported(record))
            other_supported = (
                question_support.get(other.coordinate, False)
                if question_support is not None
                else _question_supported(other))
            if record_supported or other_supported:
                closed = True
                break
        if not closed:
            return False
    return True


def _receipt(choice: _BundleChoice, before: Mapping[str, int],
             reasons: Mapping[str, tuple[str, ...]], *,
             evaluated_bundles: int, feasible_bundles: int,
             pruning_receipts: list[dict]) -> dict:
    gained = sorted(cell for cell, quality in choice.after.items()
                    if quality > before.get(cell, 0))
    lost = sorted(cell for cell, quality in before.items()
                  if choice.after.get(cell, 0) < quality)
    return {
        "reason": "global_augmenting_basis",
        "added": [record.public() for record in choice.additions],
        "evicted": [record.public() for record in choice.evictions],
        "admission_reasons": {
            record.candidate_id: list(reasons[record.candidate_id])
            for record in choice.additions
        },
        "gained_cells": gained,
        "lost_cells": lost,
        "componentwise_non_decreasing": not lost,
        "before_span_cells": len(before),
        "after_span_cells": len(choice.after),
        "objective": dict(choice.objective),
        "evaluated_bundles": evaluated_bundles,
        "feasible_bundles": feasible_bundles,
        "pruning_receipts": list(pruning_receipts),
    }


def _edge_eviction_protections(
        selected: Iterable[ProofRecord], before: Mapping[str, int]) \
        -> dict[tuple[str, object], tuple[str, ...]]:
    """Find incumbent endpoints required by an active protected edge cell.

    An edge cell can only be witnessed while both stored endpoints are in the
    basis.  If several receipts share an edge ID, a coordinate is locked only
    when it occurs in every maximum-quality witness pair.  This is an exact
    componentwise-dominance screen, not a relevance heuristic.
    """

    values = list(selected)
    selected_coordinates = {record.coordinate for record in values}
    witnesses: dict[str, list[set[tuple[str, object]]]] = {}
    for record in values:
        for edge in record.edges:
            if edge.other_coordinate not in selected_coordinates:
                continue
            quality = 0
            if edge.dependency_class == "hard_closure":
                quality = 3
            elif (edge.dependency_class == "conditional_dependency"
                  and record.query_cells):
                quality = 2
            cell = f"edge:{edge.edge_id}"
            if not quality or quality < before.get(cell, 0):
                continue
            witnesses.setdefault(cell, []).append({
                record.coordinate, edge.other_coordinate})

    protected: dict[tuple[str, object], list[str]] = {}
    for cell, pairs in witnesses.items():
        required = set.intersection(*pairs) if pairs else set()
        for coordinate in required:
            protected.setdefault(coordinate, []).append(cell)
    return {
        coordinate: tuple(sorted(cells))
        for coordinate, cells in protected.items()
    }


def _static_eviction_protections(
        selected: Iterable[ProofRecord], eligible: Iterable[ProofRecord],
        before: Mapping[str, int]) \
        -> dict[tuple[str, object], tuple[str, ...]]:
    """Lock an irreplaceable sole query/role witness in the incumbent.

    Only static query and role cells are considered.  A coordinate is locked
    when it is the sole maximum-quality incumbent witness and no admissible
    non-incumbent record can restore that quality.  Edge and floor cells have
    their own stronger proofs above.
    """

    selected_values = list(selected)
    eligible_values = list(eligible)

    def static_cells(record: ProofRecord) -> dict[str, int]:
        cells = dict(record.query_cells)
        for cell, quality in record.role_cells:
            cells[cell] = max(cells.get(cell, 0), int(quality))
        return cells

    selected_cells = {
        record.coordinate: static_cells(record) for record in selected_values}
    eligible_cells = [static_cells(record) for record in eligible_values]
    protected: dict[tuple[str, object], list[str]] = {}
    for cell, quality in before.items():
        if not (cell.startswith("query:") or cell.startswith("role:")):
            continue
        witnesses = [
            coordinate for coordinate, cells in selected_cells.items()
            if cells.get(cell, 0) >= quality
        ]
        if len(witnesses) != 1:
            continue
        if any(cells.get(cell, 0) >= quality for cells in eligible_cells):
            continue
        protected.setdefault(witnesses[0], []).append(cell)
    return {
        coordinate: tuple(sorted(cells))
        for coordinate, cells in protected.items()
    }


def _frontier_bundle_count(*, floor_count: int, floor_candidates: int,
                           nonfloor_candidates: int, selected_count: int,
                           cap: int, radius: int,
                           evictable_count: int) -> int:
    """Count the minimum-eviction frontier for one floor objective level."""

    if floor_count < 0 or floor_count > floor_candidates:
        return 0
    total = 0
    for addition_count in range(max(1, floor_count), radius + 1):
        nonfloor_count = addition_count - floor_count
        if not 0 <= nonfloor_count <= nonfloor_candidates:
            continue
        eviction_count = max(0, selected_count + addition_count - cap)
        if eviction_count > radius or eviction_count > evictable_count:
            continue
        total += (
            math.comb(floor_candidates, floor_count)
            * math.comb(nonfloor_candidates, nonfloor_count)
            * math.comb(evictable_count, eviction_count)
        )
    return total


def solve(records: list[ProofRecord], incumbent: list[ProofRecord],
          floor_coordinates: set[tuple[str, object]], *, cap: int,
          bundle_max: int = BUNDLE_MAX,
          search_audit: dict | None = None) \
        -> tuple[list[ProofRecord], list[dict]]:
    """Choose the globally best safe basis within the bounded exchange ball.

    The ground set contains every floor recovery, every question-supported
    hard or conditional typed companion, and every full query-token/legal-role
    co-occurrence proven inside its saved source span.  There is no top-k pruning.  Exact screens
    are receipt-bearing: protected edge endpoints cannot be evicted; for a
    fixed A, an extra-D final basis is dominated by its minimum-D superset; and
    once a feasible recovered-floor level exists, lower levels cannot beat the
    first lexicographic component.
    """

    limit = max(1, int(cap))
    radius = max(0, min(BUNDLE_MAX, int(bundle_max)))
    registry_values = _dedupe([*records, *incumbent])
    if any(int(record.relevance) < 0 for record in registry_values):
        raise ValueError("proof relevance must be nonnegative")
    registry = {record.coordinate: record for record in registry_values}
    span_role_cells = {
        record.candidate_id: _span_legal_role_cells(record)
        for record in registry_values
    }
    question_support = {
        record.coordinate: _question_supported(record)
        for record in registry_values
    }
    incumbent_coordinates = {record.coordinate for record in incumbent}
    selected = sorted(
        (record for coordinate, record in registry.items()
         if coordinate in incumbent_coordinates), key=_record_key)
    if len(selected) > limit:
        raise ValueError("incumbent basis exceeds presentation cap")
    selected_coordinates = {record.coordinate for record in selected}
    before = _span_lattice(selected, floor_coordinates)
    before_floor_count = sum(
        record.coordinate in floor_coordinates for record in selected)
    before_hard = _edge_map(
        selected, "hard_closure", question_support)
    before_conditional = _edge_map(
        selected, "conditional_dependency", question_support)
    before_span_role = _span_role_lattice(selected, span_role_cells)

    reasons: dict[str, tuple[str, ...]] = {}
    eligible: list[ProofRecord] = []
    for record in registry_values:
        if record.coordinate in selected_coordinates:
            continue
        labels = _candidate_reasons(
            record, registry, selected_coordinates, floor_coordinates,
            span_role_cells, question_support)
        if not labels:
            continue
        reasons[record.candidate_id] = labels
        eligible.append(record)
    eligible.sort(key=_record_key)

    # A selected floor owns a unique floor cell.  Active edge cells also have
    # immutable endpoint coordinates, so any endpoint required by every
    # maximum-quality witness is an exact non-eviction constraint.
    edge_protections = _edge_eviction_protections(selected, before)
    static_protections = _static_eviction_protections(
        selected, eligible, before)
    protected_coordinates = (
        set(floor_coordinates) | set(edge_protections)
        | set(static_protections))
    evictable = tuple(
        record for record in selected
        if record.coordinate not in protected_coordinates)
    vacancies = max(0, limit - len(selected))
    max_additions = min(
        radius, len(eligible), vacancies + min(radius, len(evictable)))

    baseline_final = tuple(selected)
    baseline_score, _baseline_public = _objective(
        baseline_final, (), (), before, before, before_floor_count,
        before_hard, before_conditional, before_span_role, floor_coordinates,
        span_role_cells, question_support)
    best: _BundleChoice | None = None
    best_score = baseline_score
    best_signature = _bundle_signature(baseline_final)
    evaluated_bundles = 0
    feasible_bundles = 0
    closure_screened_bundles = 0
    dominance_screened_bundles = 0
    extra_eviction_bundles_screened = sum(
        math.comb(len(eligible), addition_count)
        * sum(
            math.comb(len(evictable), extra_count)
            for extra_count in range(
                max(0, len(selected) + addition_count - limit) + 1,
                min(radius, len(evictable)) + 1)
        )
        for addition_count in range(1, max_additions + 1)
    )
    objective_bound_bundles_screened = 0
    evaluation_counts: Counter[str] = Counter()
    pruning_receipts: list[dict] = []

    floor_eligible = tuple(
        record for record in eligible
        if record.coordinate in floor_coordinates)
    nonfloor_eligible = tuple(
        record for record in eligible
        if record.coordinate not in floor_coordinates)
    max_floor = min(radius, max_additions, len(floor_eligible))
    retained_floor_level: int | None = None

    for floor_count in range(max_floor, -1, -1):
        feasible_at_floor_level = False
        for addition_count in range(max(1, floor_count), max_additions + 1):
            nonfloor_count = addition_count - floor_count
            if not 0 <= nonfloor_count <= len(nonfloor_eligible):
                continue
            eviction_count = max(0, len(selected) + addition_count - limit)
            if eviction_count > radius or eviction_count > len(evictable):
                continue
            eviction_options: Iterable[tuple[ProofRecord, ...]]
            if eviction_count:
                eviction_options = combinations(evictable, eviction_count)
            else:
                eviction_options = ((),)
            eviction_frontier = tuple(eviction_options)
            for floor_additions in combinations(
                    floor_eligible, floor_count):
                for nonfloor_additions in combinations(
                        nonfloor_eligible, nonfloor_count):
                    additions = tuple(sorted(
                        (*floor_additions, *nonfloor_additions),
                        key=_record_key))
                    for record in additions:
                        evaluation_counts[record.candidate_id] += len(
                            eviction_frontier)
                    for evictions in eviction_frontier:
                        evaluated_bundles += 1
                        evicted_coordinates = {
                            record.coordinate for record in evictions}
                        final = tuple(
                            [record for record in selected
                             if record.coordinate not in evicted_coordinates]
                            + list(additions))
                        if not _additions_are_closed(
                                final, additions, reasons, floor_coordinates,
                                question_support):
                            closure_screened_bundles += 1
                            continue
                        after = _span_lattice(final, floor_coordinates)
                        if not _dominates(after, before):
                            dominance_screened_bundles += 1
                            continue
                        feasible_bundles += 1
                        feasible_at_floor_level = True
                        score, public = _objective(
                            final, additions, evictions, after, before,
                            before_floor_count, before_hard,
                            before_conditional, before_span_role,
                            floor_coordinates, span_role_cells,
                            question_support)
                        signature = _bundle_signature(final)
                        choice = _BundleChoice(
                            additions=additions,
                            evictions=evictions,
                            final=final,
                            after=after,
                            score=score,
                            objective=public,
                            signature=signature,
                        )
                        if (choice.score > best_score
                                or (choice.score == best_score
                                    and choice.signature < best_signature)):
                            best = choice
                            best_score = choice.score
                            best_signature = choice.signature

        if feasible_at_floor_level:
            retained_floor_level = floor_count
            objective_bound_bundles_screened = sum(
                _frontier_bundle_count(
                    floor_count=lower,
                    floor_candidates=len(floor_eligible),
                    nonfloor_candidates=len(nonfloor_eligible),
                    selected_count=len(selected), cap=limit, radius=radius,
                    evictable_count=len(evictable))
                for lower in range(floor_count)
            )
            if objective_bound_bundles_screened:
                pruning_receipts.append({
                    "rule": "lexicographic_floor_upper_bound",
                    "retained_floor_level": floor_count,
                    "pruned_bundle_count": objective_bound_bundles_screened,
                    "proof": (
                        "score[0] equals recovered floor cells; every lower "
                        "floor level is lexicographically dominated"),
                })
            break

    if extra_eviction_bundles_screened:
        pruning_receipts.append({
            "rule": "minimum_eviction_superset_dominance",
            "pruned_bundle_count": extra_eviction_bundles_screened,
            "proof": (
                "for fixed A, removing fewer records yields a superset basis; "
                "all proof cells and nonnegative relevance are monotone and "
                "the frozen objective prefers fewer |A|+|D|"),
        })
    if edge_protections:
        pruning_receipts.append({
            "rule": "immutable_active_edge_endpoint",
            "protected": [
                {
                    "candidate_id": next(
                        record.candidate_id for record in selected
                        if record.coordinate == coordinate),
                    "coordinate": list(coordinate),
                    "proof_cells": list(cells),
                }
                for coordinate, cells in sorted(
                    edge_protections.items(), key=lambda item: repr(item[0]))
            ],
            "proof": (
                "evicting an endpoint required by every maximum-quality "
                "witness destroys an incumbent edge cell"),
        })
    if static_protections:
        pruning_receipts.append({
            "rule": "irreplaceable_unique_static_witness",
            "protected": [
                {
                    "candidate_id": next(
                        record.candidate_id for record in selected
                        if record.coordinate == coordinate),
                    "coordinate": list(coordinate),
                    "proof_cells": list(cells),
                }
                for coordinate, cells in sorted(
                    static_protections.items(), key=lambda item: repr(item[0]))
            ],
            "proof": (
                "the incumbent is the sole maximum-quality query/role witness "
                "and no admissible candidate can restore the cell"),
        })

    evaluated_ids = set(evaluation_counts)
    structurally_screened = {
        record.candidate_id: [
            "lexicographic_floor_upper_bound"
            if retained_floor_level is not None
            and record.coordinate not in floor_coordinates
            else "no_feasible_bundle_within_cap_radius_or_protected_frontier"
        ]
        for record in eligible if record.candidate_id not in evaluated_ids
    }
    complete_ids = evaluated_ids | set(structurally_screened)
    minimum_frontier_total = sum(
        _frontier_bundle_count(
            floor_count=floor_count,
            floor_candidates=len(floor_eligible),
            nonfloor_candidates=len(nonfloor_eligible),
            selected_count=len(selected), cap=limit, radius=radius,
            evictable_count=len(evictable))
        for floor_count in range(max_floor + 1)
    )
    evaluated_partition_complete = evaluated_bundles == (
        feasible_bundles + closure_screened_bundles
        + dominance_screened_bundles)
    minimum_frontier_partition_complete = minimum_frontier_total == (
        evaluated_bundles + objective_bound_bundles_screened)
    pruning_rules = {
        row.get("rule") for row in pruning_receipts if row.get("rule")}
    pruning_receipts_complete = (
        (not objective_bound_bundles_screened
         or "lexicographic_floor_upper_bound" in pruning_rules)
        and (not extra_eviction_bundles_screened
             or "minimum_eviction_superset_dominance" in pruning_rules)
        and (not edge_protections
             or "immutable_active_edge_endpoint" in pruning_rules)
        and (not static_protections
             or "irreplaceable_unique_static_witness" in pruning_rules)
    )
    audit_value = {
        "evaluated_candidate_ids": sorted(evaluated_ids),
        "candidate_evaluation_counts": {
            candidate_id: evaluation_counts[candidate_id]
            for candidate_id in sorted(evaluation_counts)
        },
        "structurally_screened_candidates": structurally_screened,
        "evaluated_or_structurally_screened_ids": sorted(complete_ids),
        "candidate_enumeration_complete": (
            complete_ids == {record.candidate_id for record in eligible}
            and evaluated_partition_complete
            and minimum_frontier_partition_complete
            and pruning_receipts_complete),
        "evaluated_bundles": evaluated_bundles,
        "feasible_bundles": feasible_bundles,
        "closure_screened_bundles": closure_screened_bundles,
        "dominance_screened_bundles": dominance_screened_bundles,
        "objective_bound_bundles_screened": (
            objective_bound_bundles_screened),
        "extra_eviction_bundles_screened": (
            extra_eviction_bundles_screened),
        "minimum_eviction_frontier_bundles": minimum_frontier_total,
        "evaluated_partition_complete": evaluated_partition_complete,
        "minimum_frontier_partition_complete": (
            minimum_frontier_partition_complete),
        "pruning_receipts_complete": pruning_receipts_complete,
        "eligible_candidate_count": len(eligible),
        "max_additions_after_exact_locks": max_additions,
        "protected_incumbent_count": len(
            {record.coordinate for record in selected} - {
                record.coordinate for record in evictable}),
        "evictable_after_exact_locks": len(evictable),
        "pruning_receipts": pruning_receipts,
        "retained_floor_level": retained_floor_level,
    }
    if search_audit is not None:
        search_audit.clear()
        search_audit.update(audit_value)

    if best is None:
        return selected, []
    return sorted(best.final, key=_record_key), [
        _receipt(best, before, reasons,
                 evaluated_bundles=evaluated_bundles,
                 feasible_bundles=feasible_bundles,
                 pruning_receipts=pruning_receipts)]


def run(index: Index, question: str,
        incumbent: Iterable[termexplore.TermBranch],
        evidence_pool: Iterable[termexplore.TermBranch],
        baseline_core: Iterable[termexplore.TermBranch], *,
        cap: int = PRESENTED_MAX, bundle_max: int = BUNDLE_MAX) \
        -> tuple[list[termexplore.TermBranch], dict]:
    """Rebuild verified records and run the bounded global solver."""

    raw_incumbent = list(incumbent)
    raw_pool = list(evidence_pool)
    raw_core = list(baseline_core)
    canonical_incumbent, incumbent_errors = canonicalize(index, raw_incumbent)
    canonical_core, core_errors = canonicalize(index, raw_core)
    records, registry_errors = build_registry(index, question, raw_pool)
    by_coordinate = {record.coordinate: record for record in records}
    incumbent_records = [by_coordinate[row.coordinate]
                         for row in canonical_incumbent
                         if row.coordinate in by_coordinate]
    floor_coordinates = {row.coordinate for row in canonical_core
                         if row.coordinate in by_coordinate}
    incumbent_coordinates = {record.coordinate for record in incumbent_records}
    registry = {record.coordinate: record for record in records}
    admission_reasons = {
        record.candidate_id: _candidate_reasons(
            record, registry, incumbent_coordinates, floor_coordinates)
        for record in records
        if record.coordinate not in incumbent_coordinates
    }
    admission_reasons = {
        candidate_id: labels for candidate_id, labels in admission_reasons.items()
        if labels
    }
    search_audit: dict = {}
    selected_records, receipts = solve(
        records, incumbent_records, floor_coordinates,
        cap=max(1, int(cap)), bundle_max=bundle_max,
        search_audit=search_audit)
    selected = [record.row for record in selected_records]
    selected_coordinates = {record.coordinate for record in selected_records}
    raw_pool_roots, _ = canonicalize(index, raw_pool)
    pool_coordinates = {row.coordinate for row in raw_pool_roots}
    witness_ok = all(validate_span(index, record) for record in selected_records)
    lost_cells = [cell for receipt in receipts
                  for cell in receipt.get("lost_cells") or ()]
    action_counts = Counter(
        reason for receipt in receipts
        for labels in receipt.get("admission_reasons", {}).values()
        for reason in labels)
    promoted = [value for receipt in receipts
                for value in receipt.get("added") or ()]
    evicted = [value for receipt in receipts
               for value in receipt.get("evicted") or ()]
    ngram_only_admissions = []
    for receipt in receipts:
        for candidate_id, labels in (
                receipt.get("admission_reasons") or {}).items():
            if not set(labels) & {
                    "floor_recovery", "direct_span_legal_role",
                    "hard_dependency", "conditional_dependency"}:
                ngram_only_admissions.append(candidate_id)
    evaluated_ids = set(search_audit.get("evaluated_candidate_ids") or ())
    screened = search_audit.get("structurally_screened_candidates") or {}
    evaluated_or_screened = set(
        search_audit.get("evaluated_or_structurally_screened_ids") or ())
    admissible_ids = set(admission_reasons)
    candidate_evaluations = {
        candidate_id: {
            "status": (
                "evaluated" if candidate_id in evaluated_ids
                else "structurally_screened"),
            "evaluated_bundle_count": int(
                (search_audit.get("candidate_evaluation_counts") or {}).get(
                    candidate_id, 0)),
            "screen_reasons": list(screened.get(candidate_id) or ()),
        }
        for candidate_id in sorted(admissible_ids)
    }
    candidate_audit = {
        "admissible_candidate_ids": sorted(admissible_ids),
        "admissible_candidate_count": len(admissible_ids),
        "hard_candidate_ids": sorted(
            candidate_id for candidate_id, labels in admission_reasons.items()
            if "hard_dependency" in labels),
        "hard_candidate_pretruncated_ids": [],
        "evaluated_candidate_ids": sorted(evaluated_ids),
        "structurally_screened_candidates": screened,
        "candidate_evaluations": candidate_evaluations,
        "evaluated_or_structurally_screened_ids": sorted(
            evaluated_or_screened),
        "candidate_enumeration_complete": bool(
            search_audit.get("candidate_enumeration_complete")
            and evaluated_or_screened == admissible_ids),
        "search_accounting": {
            key: value for key, value in search_audit.items()
            if key not in {
                "evaluated_candidate_ids", "candidate_evaluation_counts",
                "structurally_screened_candidates",
                "evaluated_or_structurally_screened_ids",
                "candidate_enumeration_complete",
            }
        },
        "ngram_only_admissions": ngram_only_admissions,
    }
    typed_edges_validated = all(
        edge.edge_id.startswith("witness-edge:")
        and edge.other_coordinate in registry
        and registry[edge.other_coordinate].candidate_id
        == edge.other_candidate_id
        and frozen_basis._dependency_class(edge.kind)
        == edge.dependency_class
        for record in selected_records for edge in record.edges
    )
    selected_addition_ids = {
        candidate_id for receipt in receipts
        for candidate_id in (receipt.get("admission_reasons") or {})
    }
    selected_additions = [
        record for record in selected_records
        if record.candidate_id in selected_addition_ids
    ]
    selected_addition_closure_validated = _additions_are_closed(
        selected_records, selected_additions, admission_reasons,
        floor_coordinates)
    return selected, {
        "enabled": True,
        "strategy": "proof-contribution-bounded-global-augmenting",
        "ran": True,
        "status": "complete" if not (
            incumbent_errors or core_errors or registry_errors) else "partial",
        "reason": "canonical_proof_lattice_globally_augmented",
        "raw_incumbent_count": len(raw_incumbent),
        "canonical_incumbent_count": len(canonical_incumbent),
        "raw_pool_count": len(raw_pool),
        "canonical_pool_count": len(records),
        "raw_core_count": len(raw_core),
        "canonical_core_count": len(floor_coordinates),
        "selected_count": len(selected_records),
        "selected_subset_of_pool": selected_coordinates <= pool_coordinates,
        "canonical_pool_preserved": (
            {record.coordinate for record in records} == pool_coordinates),
        "canonical_source_witnesses_valid": witness_ok,
        "typed_edge_receipts_validated": typed_edges_validated,
        "selected_addition_closure_validated": (
            selected_addition_closure_validated),
        "componentwise_non_decreasing": not lost_cells,
        "unique_witness_losses": lost_cells,
        "actions": receipts,
        "action_counts": dict(action_counts),
        "promoted": promoted,
        "evicted": evicted,
        "selected_receipts": [record.public() for record in selected_records],
        "candidate_audit": candidate_audit,
        "registry_count": len(records),
        "registry_errors": [*incumbent_errors, *core_errors, *registry_errors],
        "gold_fields_received": False,
        "llm_calls": 0,
    }


__all__ = [
    "BUNDLE_MAX", "EdgeReceipt", "PRESENTED_MAX", "ProofRecord",
    "STRONG_QUERY_MIN_QUALITY", "build_registry", "canonicalize", "run",
    "solve", "validate_span",
]
