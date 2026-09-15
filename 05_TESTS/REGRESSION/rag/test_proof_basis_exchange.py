from __future__ import annotations

import inspect

from lawrag.core.rag import proof_basis_exchange as subject
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


def _record(doc: str, node: int, *, rank: int, query: str = "",
            relevance: int = 0, edges=()) -> subject.ProofRecord:
    row = _row(doc, node)
    cid = f"C-{doc}-{node}"
    return subject.ProofRecord(
        candidate_id=cid,
        row=row,
        pool_rank=rank,
        source_sha256="0" * 64,
        source_chars=10,
        span_id=f"S-{doc}-{node}",
        span_start=0,
        span_end=1,
        span_text="제",
        query_cells=((query, 3),) if query else (),
        role_cells=(),
        relevance=relevance,
        edges=tuple(edges),
    )


def test_add_only_completes_a_vacant_basis_without_eviction():
    core = _record("A", 1, rank=1, query="query:x", relevance=5)
    candidate = _record("B", 2, rank=2, query="query:y", relevance=4)

    selected, receipts = subject.solve(
        [core, candidate], [core], {core.coordinate}, cap=2,
        allow_exchange=False)

    assert [row.coordinate for row in selected] == [
        core.coordinate, candidate.coordinate]
    assert len(receipts) == 1
    assert receipts[0]["evicted"] is None
    assert receipts[0]["componentwise_non_decreasing"] is True


def test_exchange_keeps_floor_and_replaces_only_redundant_fresh_witness():
    core = _record("A", 1, rank=1, query="query:x", relevance=9)
    fresh = _record("B", 2, rank=2, query="query:x", relevance=1)
    edge = subject.EdgeReceipt(
        edge_id="E-hard",
        kind="DELEGATES_TO",
        direction="in",
        other_coordinate=core.coordinate,
        other_candidate_id=core.candidate_id,
        dependency_class="hard_closure",
        provenance=("test",),
    )
    candidate = _record(
        "C", 3, rank=3, query="query:y", relevance=8, edges=(edge,))

    selected, receipts = subject.solve(
        [core, fresh, candidate], [core, fresh], {core.coordinate}, cap=2,
        allow_exchange=True)

    assert {row.coordinate for row in selected} == {
        core.coordinate, candidate.coordinate}
    assert receipts[-1]["evicted"]["coordinate"] == list(fresh.coordinate)
    assert receipts[-1]["lost_cells"] == []
    assert any(cell.startswith("edge:")
               for cell in receipts[-1]["gained_cells"])


def test_exchange_rejects_loss_of_a_unique_incumbent_cell():
    core = _record("A", 1, rank=1, query="query:x", relevance=9)
    unique = _record("B", 2, rank=2, query="query:unique", relevance=1)
    candidate = _record("C", 3, rank=3, query="query:new", relevance=8)

    selected, receipts = subject.solve(
        [core, unique, candidate], [core, unique], {core.coordinate}, cap=2,
        allow_exchange=True)

    assert [row.coordinate for row in selected] == [
        core.coordinate, unique.coordinate]
    assert receipts == []


def test_solver_is_idempotent_after_a_completed_exchange():
    core = _record("A", 1, rank=1, query="query:x", relevance=9)
    fresh = _record("B", 2, rank=2, query="query:x", relevance=1)
    candidate = _record("C", 3, rank=3, query="query:new", relevance=8)
    records = [core, fresh, candidate]

    first, _ = subject.solve(
        records, [core, fresh], {core.coordinate}, cap=2,
        allow_exchange=True)
    second, receipts = subject.solve(
        records, first, {core.coordinate}, cap=2, allow_exchange=True)

    assert [row.coordinate for row in second] == [
        row.coordinate for row in first]
    assert receipts == []


def test_product_boundary_has_no_gold_or_case_argument():
    parameters = set(inspect.signature(subject.run).parameters)

    assert "case" not in parameters
    assert "gold" not in parameters
    assert "expected_articles" not in parameters
    assert "paired" not in parameters
