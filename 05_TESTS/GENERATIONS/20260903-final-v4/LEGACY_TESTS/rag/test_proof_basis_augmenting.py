from __future__ import annotations

from dataclasses import replace
import inspect
from itertools import combinations, permutations
import random

import pytest

from lawrag.core.rag import proof_basis_augmenting as subject
from lawrag.core.rag.termexplore import TermBranch


def _row(doc: str, node: int) -> TermBranch:
    return TermBranch(
        doc_id=doc,
        node=node,
        doc=doc,
        path=f"제{node}조",
        terms=(),
        excerpts=(),
        body=f"제{node}조 본문",
        body_chars=8,
        origin="test",
    )


def _edge(edge_id: str, kind: str, other: "subject.ProofRecord",
          *, dependency_class: str = "hard_closure") -> subject.EdgeReceipt:
    return subject.EdgeReceipt(
        edge_id=edge_id,
        kind=kind,
        direction="out",
        other_coordinate=other.coordinate,
        other_candidate_id=other.candidate_id,
        dependency_class=dependency_class,
        provenance=("test",),
    )


def _record(doc: str, node: int, *, rank: int, query: str = "",
            query_quality: int = 0, relevance: int = 0,
            role: str = "", edges=()) -> subject.ProofRecord:
    row = _row(doc, node)
    cid = f"C-{doc}-{node}"
    token = query.split(":", 1)[1] if query else ""
    role_cue = {
        "role:duty": "하여야 한다",
        "role:condition": "요건인 경우",
        "role:exception": "다만 제외한다",
    }.get(role, "")
    return subject.ProofRecord(
        candidate_id=cid,
        row=row,
        pool_rank=rank,
        source_sha256="0" * 64,
        source_chars=10,
        span_id=f"S-{doc}-{node}",
        span_start=0,
        span_end=1,
        span_text=" ".join(value for value in (token, role_cue) if value) or "제",
        query_cells=((query, query_quality),) if query else (),
        role_cells=((role, 2),) if role else (),
        relevance=relevance,
        edges=tuple(edges),
    )


def test_vacancy_completion_accepts_a_full_token_direct_match():
    core = _record("A", 1, rank=1, query="query:anchor",
                   query_quality=8, relevance=8)
    candidate = _record("B", 2, rank=2, query="query:operation",
                        query_quality=9, relevance=9, role="role:duty")

    selected, receipts = subject.solve(
        [candidate, core], [core], {core.coordinate}, cap=2)

    assert {record.coordinate for record in selected} == {
        core.coordinate, candidate.coordinate}
    assert receipts[0]["evicted"] == []
    assert receipts[0]["componentwise_non_decreasing"] is True


def test_floor_recovery_wins_the_only_safe_slot_before_raw_hard_relevance():
    anchor = _record("A", 1, rank=1, query="query:anchor",
                     query_quality=8, relevance=8)
    expendable = _record("B", 2, rank=2, query="query:shared",
                         query_quality=8, relevance=1)
    floor = _record("F", 3, rank=3, query="query:shared",
                    query_quality=8, relevance=2)
    hard = _record(
        "H", 4, rank=4, query="query:shared", query_quality=8,
        relevance=100,
        edges=(_edge("E-hard", "DELEGATES_TO", anchor),))

    audit = {}
    selected, receipts = subject.solve(
        [hard, expendable, floor, anchor], [anchor, expendable],
        {anchor.coordinate, floor.coordinate}, cap=2,
        search_audit=audit)

    assert {record.coordinate for record in selected} == {
        anchor.coordinate, floor.coordinate}
    assert receipts[0]["objective"]["recovered_floor_witnesses"] == 1
    assert receipts[0]["added"][0]["coordinate"] == list(floor.coordinate)
    assert any(
        row["rule"] == "lexicographic_floor_upper_bound"
        for row in audit["pruning_receipts"])


def test_equal_lattice_relevance_swap_is_compared_against_no_op():
    anchor = _record("A", 1, rank=1, query="query:anchor",
                     query_quality=8, relevance=8, role="role:duty")
    expendable = _record("I", 2, rank=2, query="query:shared",
                         query_quality=8, relevance=1, role="role:duty")
    better = _record("C", 3, rank=3, query="query:shared",
                     query_quality=8, relevance=100, role="role:duty")

    selected, receipts = subject.solve(
        [anchor, expendable, better], [anchor, expendable],
        {anchor.coordinate}, cap=2)

    assert {record.coordinate for record in selected} == {
        anchor.coordinate, better.coordinate}
    assert receipts[0]["gained_cells"] == []
    assert receipts[0]["objective"]["final_relevance"] == 108

    worse = replace(better, candidate_id="C-worse", relevance=0,
                    row=_row("W", 4), pool_rank=4)
    unchanged, no_receipts = subject.solve(
        [anchor, expendable, worse], [anchor, expendable],
        {anchor.coordinate}, cap=2)
    assert {record.coordinate for record in unchanged} == {
        anchor.coordinate, expendable.coordinate}
    assert no_receipts == []


def test_direct_full_token_requires_legal_role_in_the_same_saved_span():
    anchor = _record("A", 1, rank=1, query="query:anchor",
                     query_quality=8, relevance=8)
    article_wide_only = _record(
        "C", 2, rank=2, query="query:operation",
        query_quality=9, relevance=100, role="role:duty")
    article_wide_only = replace(article_wide_only, span_text="operation")

    selected, receipts = subject.solve(
        [anchor, article_wide_only], [anchor], {anchor.coordinate}, cap=2)

    assert [record.coordinate for record in selected] == [anchor.coordinate]
    assert receipts == []


def test_active_edge_endpoints_are_exactly_protected_from_eviction():
    companion = _record("B", 2, rank=2, relevance=1)
    anchor = _record(
        "A", 1, rank=1, query="query:anchor", query_quality=8,
        relevance=8, edges=(_edge("E-protected", "DELEGATES_TO", companion),))
    candidate = _record(
        "C", 3, rank=3, query="query:operation", query_quality=9,
        relevance=100, role="role:duty")
    audit = {}

    selected, receipts = subject.solve(
        [anchor, companion, candidate], [anchor, companion],
        set(), cap=2, search_audit=audit)

    assert {record.coordinate for record in selected} == {
        anchor.coordinate, companion.coordinate}
    assert receipts == []
    assert audit["candidate_evaluation_counts"] == {}
    assert audit["structurally_screened_candidates"][
        candidate.candidate_id]
    protected = next(
        row for row in audit["pruning_receipts"]
        if row["rule"] == "immutable_active_edge_endpoint")
    assert {tuple(row["coordinate"]) for row in protected["protected"]} == {
        anchor.coordinate, companion.coordinate}


def test_all_hard_candidates_are_compared_and_relation_diversity_wins():
    anchor = _record("A", 1, rank=1, query="query:anchor",
                     query_quality=8, relevance=8)
    expendable = _record("B", 2, rank=2, query="query:anchor",
                         query_quality=8, relevance=1)
    first = _record(
        "H", 10, rank=3, query="query:fragment", query_quality=3,
        relevance=100, edges=(_edge("E-1", "DELEGATES_TO", anchor),))
    second = _record(
        "H", 11, rank=4, query="query:fragment", query_quality=3,
        relevance=90, edges=(_edge("E-2", "DELEGATES_TO", anchor),))
    target = _record(
        "H", 46, rank=31, query="query:fragment", query_quality=3,
        relevance=10,
        edges=(
            _edge("E-target-1", "RECEIVES_FROM", anchor),
            _edge("E-target-2", "DELEGATES_TO", anchor),
            _edge("E-target-3", "VIOLATION_SANCTIONED_BY", anchor),
        ))

    selected, receipts = subject.solve(
        [first, anchor, target, expendable, second],
        [anchor, expendable], {anchor.coordinate}, cap=2)

    assert {record.coordinate for record in selected} == {
        anchor.coordinate, target.coordinate}
    assert receipts[0]["objective"]["new_hard_relation_kinds"] == 3
    assert receipts[0]["objective"]["new_hard_edges"] == 3


def test_partial_ngram_cannot_enter_directly_but_can_ground_a_typed_edge():
    anchor = _record("A", 1, rank=1, query="query:anchor",
                     query_quality=8, relevance=8)
    noisy = _record("N", 2, rank=2, query="query:문계약을",
                    query_quality=3, relevance=50)

    direct_selected, direct_receipts = subject.solve(
        [anchor, noisy], [anchor], {anchor.coordinate}, cap=2)

    assert [record.coordinate for record in direct_selected] == [
        anchor.coordinate]
    assert direct_receipts == []

    companion = _record(
        "C", 3, rank=3, query="query:위배되", query_quality=3,
        relevance=3,
        edges=(_edge("E-companion", "RECEIVES_FROM", anchor),))
    edge_selected, edge_receipts = subject.solve(
        [anchor, noisy, companion], [anchor], {anchor.coordinate}, cap=2)

    assert {record.coordinate for record in edge_selected} == {
        anchor.coordinate, companion.coordinate}
    assert edge_receipts[0]["admission_reasons"][companion.candidate_id] == [
        "hard_dependency"]


def test_weak_relation_candidate_requires_a_companion_in_the_final_basis():
    anchor = _record("A", 1, rank=1, query="query:anchor",
                     query_quality=8, relevance=8)
    absent = _record("Z", 9, rank=9, query="query:operation",
                     query_quality=8, relevance=2, role="role:duty")
    weak = _record(
        "W", 2, rank=2, query="query:fragment", query_quality=3,
        relevance=50, edges=(_edge("E-phantom", "RECEIVES_FROM", absent),))

    selected, receipts = subject.solve(
        [anchor, weak, absent], [anchor], {anchor.coordinate},
        cap=2, bundle_max=1)

    assert weak.coordinate not in {record.coordinate for record in selected}
    assert receipts[0]["added"][0]["coordinate"] == list(absent.coordinate)


def test_two_for_two_bundle_may_preserve_crossed_unique_witnesses():
    anchor = _record("A", 1, rank=1, query="query:anchor",
                     query_quality=8, relevance=8)
    left = _record("I", 2, rank=2, query="query:left",
                   query_quality=8, relevance=1)
    right = _record("I", 3, rank=3, query="query:right",
                    query_quality=8, relevance=1)
    # Each addition preserves the other incumbent's unique query cell.  The
    # useful hard/floor gains are available together only in the final bundle.
    floor = _record("F", 4, rank=4, query="query:right",
                    query_quality=8, relevance=2)
    hard = _record(
        "H", 5, rank=5, query="query:left", query_quality=8, relevance=2,
        edges=(_edge("E-bundle", "HAS_EXCEPTION", anchor),))

    selected, receipts = subject.solve(
        [right, hard, anchor, floor, left], [anchor, left, right],
        {anchor.coordinate, floor.coordinate}, cap=3)

    assert {record.coordinate for record in selected} == {
        anchor.coordinate, floor.coordinate, hard.coordinate}
    assert len(receipts[0]["added"]) == 2
    assert len(receipts[0]["evicted"]) == 2
    assert receipts[0]["lost_cells"] == []


def test_final_dominance_preserves_a_nonfloor_unique_witness():
    anchor = _record("A", 1, rank=1, query="query:anchor",
                     query_quality=8, relevance=8)
    unique = _record("I", 2, rank=2, query="query:unique",
                     query_quality=8, relevance=1)
    candidate = _record("C", 3, rank=3, query="query:new",
                        query_quality=8, relevance=100, role="role:duty")
    audit = {}

    selected, receipts = subject.solve(
        [candidate, unique, anchor], [anchor, unique],
        {anchor.coordinate}, cap=2, search_audit=audit)

    assert {record.coordinate for record in selected} == {
        anchor.coordinate, unique.coordinate}
    assert receipts == []
    protected = next(
        row for row in audit["pruning_receipts"]
        if row["rule"] == "irreplaceable_unique_static_witness")
    assert any(
        tuple(row["coordinate"]) == unique.coordinate
        and "query:unique" in row["proof_cells"]
        for row in protected["protected"])


def test_negative_relevance_is_rejected_by_the_pruning_contract():
    invalid = _record("A", 1, rank=1, relevance=-1)

    with pytest.raises(ValueError, match="nonnegative"):
        subject.solve([invalid], [invalid], set(), cap=1)


def test_solver_is_order_invariant_and_deterministic():
    anchor = _record("A", 1, rank=1, query="query:anchor",
                     query_quality=8, relevance=8)
    expendable = _record("I", 2, rank=2, query="query:shared",
                         query_quality=8, relevance=1)
    left = _record("C", 3, rank=3, query="query:shared",
                   query_quality=8, relevance=3, role="role:duty")
    right = _record("C", 4, rank=4, query="query:shared",
                    query_quality=8, relevance=3, role="role:duty")
    records = [anchor, expendable, left, right]

    outcomes = []
    for order in permutations(records):
        selected, receipts = subject.solve(
            list(order), [expendable, anchor], {anchor.coordinate}, cap=2)
        outcomes.append((
            tuple(record.candidate_id for record in selected),
            receipts[0]["added"][0]["candidate_id"],
            receipts[0]["objective"],
        ))

    assert len(set(repr(outcome) for outcome in outcomes)) == 1


def test_product_boundary_has_no_gold_or_case_argument():
    parameters = set(inspect.signature(subject.run).parameters)

    assert "case" not in parameters
    assert "gold" not in parameters
    assert "expected_articles" not in parameters
    assert "paired" not in parameters


def _oracle(records, incumbent, floor_coordinates, *, cap, radius):
    registry = {record.coordinate: record for record in records}
    selected = tuple(sorted(incumbent, key=subject._record_key))
    selected_coordinates = {record.coordinate for record in selected}
    reasons = {
        record.candidate_id: subject._candidate_reasons(
            record, registry, selected_coordinates, floor_coordinates)
        for record in records if record.coordinate not in selected_coordinates
    }
    eligible = [
        record for record in records
        if record.coordinate not in selected_coordinates
        and reasons[record.candidate_id]
    ]
    before = subject._span_lattice(selected, floor_coordinates)
    before_floor = sum(
        record.coordinate in floor_coordinates for record in selected)
    before_hard = subject._edge_map(selected, "hard_closure")
    before_conditional = subject._edge_map(
        selected, "conditional_dependency")
    before_span_role = subject._span_role_lattice(selected)
    best_final = selected
    best_score, _ = subject._objective(
        selected, (), (), before, before, before_floor, before_hard,
        before_conditional, before_span_role, floor_coordinates)
    best_signature = subject._bundle_signature(selected)

    for add_count in range(1, min(radius, len(eligible)) + 1):
        for additions in combinations(eligible, add_count):
            for evict_count in range(0, min(radius, len(selected)) + 1):
                for evictions in combinations(selected, evict_count):
                    evicted = {record.coordinate for record in evictions}
                    final = tuple(sorted(
                        [record for record in selected
                         if record.coordinate not in evicted]
                        + list(additions), key=subject._record_key))
                    if len(final) > cap:
                        continue
                    if not subject._additions_are_closed(
                            final, additions, reasons, floor_coordinates):
                        continue
                    after = subject._span_lattice(final, floor_coordinates)
                    if not subject._dominates(after, before):
                        continue
                    score, _ = subject._objective(
                        final, additions, evictions, after, before,
                        before_floor, before_hard, before_conditional,
                        before_span_role, floor_coordinates)
                    signature = subject._bundle_signature(final)
                    if (score > best_score
                            or (score == best_score
                                and signature < best_signature)):
                        best_final = final
                        best_score = score
                        best_signature = signature
    return best_final


def test_exact_pruning_matches_full_bounded_family_on_small_states():
    for seed in range(24):
        rng = random.Random(seed)
        left = _record(
            "I", 1, rank=1, query="query:anchor", query_quality=8,
            relevance=rng.randrange(1, 15), role="role:duty")
        middle = _record(
            "I", 2, rank=2, query="query:shared", query_quality=8,
            relevance=rng.randrange(0, 10), role="role:duty")
        right = _record(
            "I", 3, rank=3, query="query:right", query_quality=8,
            relevance=rng.randrange(0, 10))
        if seed % 2 == 0:
            left = replace(
                left,
                edges=(_edge("E-incumbent", "DELEGATES_TO", middle),))
        direct = _record(
            "C", 4, rank=4, query="query:shared", query_quality=8,
            relevance=rng.randrange(0, 20), role="role:duty")
        floor = _record(
            "F", 5, rank=5, query="query:right", query_quality=8,
            relevance=rng.randrange(0, 20))
        weak = _record(
            "C", 6, rank=6, query="query:fragment", query_quality=3,
            relevance=rng.randrange(0, 20),
            edges=(_edge("E-new", "HAS_EXCEPTION", left),))
        records = [left, middle, right, direct, floor, weak]
        floors = {left.coordinate, floor.coordinate}

        selected, _receipts = subject.solve(
            records, [left, middle, right], floors, cap=3, bundle_max=2)
        expected = _oracle(
            records, [left, middle, right], floors, cap=3, radius=2)

        assert tuple(record.coordinate for record in selected) == tuple(
            record.coordinate for record in expected), seed
