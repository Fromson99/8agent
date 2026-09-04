from __future__ import annotations

import hashlib
from pathlib import Path
from types import MappingProxyType

import pytest

from lawrag.core.rag import article_reachability
from lawrag.core.rag.answer import Section
from lawrag.core.rag.index import Index
from lawrag.core.rag import legal_graph_closure, legalclosure_runtime
from lawrag.core.rag.legal_graph_store import (
    ArticlePorts,
    EdgeLite,
    EndpointLite,
    LegalGraphSnapshot,
)


AUTHORITY = "a" * 64


def _doc(doc_id: str, root: int, child: int | None = None, *, text: str) -> tuple:
    nodes = [{
        "id": root,
        "parent": None,
        "level": 1,
        "surface": f"제{root}조",
        "title": doc_id,
        "page": 1,
        "span": [0, 1 if child is None else 2],
    }]
    blocks = [{"idx": 0, "page": 1, "text": f"제{root}조", "kind": "text"}]
    if child is not None:
        nodes.append({
            "id": child,
            "parent": root,
            "level": 2,
            "surface": "제1항",
            "title": "",
            "page": 1,
            "span": [1, 2],
        })
        blocks.append({"idx": 1, "page": 1, "text": text, "kind": "text"})
    else:
        blocks[0]["text"] = text
    return doc_id, {"name": doc_id, "kind": "law"}, {
        "nodes": nodes,
        "blocks": blocks,
    }


def _index(*, target_count: int = 5) -> Index:
    docs = [
        _doc(
            "seed-1", 1, 2,
            text="대통령령으로 정하는 주요주주 보험회사 기준",
        ),
        _doc(
            "seed-2", 10, 11,
            text="대통령령으로 정하는 주요주주 보험회사 기준",
        ),
    ]
    docs.extend(
        _doc(f"target-{number}", 100 + number, text="구체적인 범위")
        for number in range(1, target_count + 1)
    )
    canonical = {doc_id for doc_id, _, _ in docs}
    return Index.from_docs(
        docs,
        canonical_doc_ids=canonical,
        authority_generation=AUTHORITY,
        authority_as_of="20260828",
    )


def _endpoint(
    doc_id: str,
    node: int,
    *,
    precision: str = "EXACT_UNIT",
    label: str = "",
    block_id: int | None = None,
    start: int | None = None,
    end: int | None = None,
    quote_sha256: str = "",
) -> EndpointLite:
    return EndpointLite(
        kind="STRUCTURAL_UNIT",
        precision=precision,
        ref_id=f"unit-{doc_id}-{node}",
        document_id=doc_id,
        node_id=node,
        block_id=block_id,
        start=start,
        end=end,
        quote_sha256=quote_sha256,
        coordinate=f"{doc_id}:{node}",
        label=label or f"{doc_id}:{node}",
    )


def _edge(
    projection_id: str,
    source_doc: str,
    source_node: int,
    target_doc: str,
    target_node: int,
    *,
    assertion_id: str | None = None,
    resolution: str = "EXACT_SOURCE_BACKED",
    source: EndpointLite | None = None,
) -> EdgeLite:
    return EdgeLite(
        projection_id=projection_id,
        assertion_id=assertion_id or f"assertion-{projection_id}",
        predicate="LEGISLATIVE_DELEGATION",
        family="LEGISLATIVE_LINK",
        mode="REQUIRED_WHEN_ACTIVATED",
        resolution=resolution,
        review_state="SOURCE_BACKED",
        legacy_kind="DELEGATES_TO",
        source=source or _endpoint(
            source_doc,
            source_node,
            label="대통령령으로 정하는 주요주주 보험회사 기준",
        ),
        target=_endpoint(target_doc, target_node),
    )


def _snapshot(
    edges: list[EdgeLite],
    *,
    authority: str = AUTHORITY,
    omit_target_cards: set[str] = frozenset(),
    omit_incoming: set[str] = frozenset(),
) -> LegalGraphSnapshot:
    edge_by_id = {edge.projection_id: edge for edge in edges}
    ports: dict[tuple[str, int], ArticlePorts] = {}
    by_source: dict[tuple[str, int], list[str]] = {}
    by_target: dict[tuple[str, int], list[str]] = {}
    for edge in edges:
        source_root = 1 if edge.source.document_id == "seed-1" else 10
        by_source.setdefault((edge.source.document_id, source_root), []).append(
            edge.projection_id
        )
        by_target.setdefault(
            (edge.target.document_id, int(edge.target.node_id)), []
        ).append(edge.projection_id)
    for coordinate, projection_ids in by_source.items():
        ports[coordinate] = ArticlePorts(
            member_id=f"member-{coordinate[0]}",
            endpoint=_endpoint(coordinate[0], coordinate[1]),
            outgoing=tuple(projection_ids),
            incoming=(),
        )
    for coordinate, projection_ids in by_target.items():
        if coordinate[0] in omit_target_cards:
            continue
        incoming = tuple(
            value for value in projection_ids if value not in omit_incoming
        )
        ports[coordinate] = ArticlePorts(
            member_id=f"member-{coordinate[0]}",
            endpoint=_endpoint(coordinate[0], coordinate[1]),
            outgoing=(),
            incoming=incoming,
        )
    return LegalGraphSnapshot(
        root=Path("."),
        generation_id="lgv1-" + "1" * 24,
        authority_generation=authority,
        content_sha256="b" * 64,
        projection_policy="provision-card-v1.1",
        pointer_sha256="c" * 64,
        runtime_wired_in_artifact=False,
        ports_by_article=MappingProxyType(ports),
        edge_by_projection_id=MappingProxyType(edge_by_id),
        loaded_rows=len(ports) + len(edge_by_id),
        load_ms=0.0,
    )


def _section(index: Index, doc_id: str, node: int, *, companion: bool = False) -> Section:
    view = index.docs[doc_id]
    return Section(
        n=1,
        doc_id=doc_id,
        doc=view.name,
        node=node,
        path=view.path(node),
        page=1,
        kind="법률좌표폐쇄",
        matched="baseline",
        text=view.section_text(view.by_id[node]),
        ref_src=({"doc_id": "origin", "node": 1} if companion else None),
    )


def test_injected_snapshot_must_match_index_authority() -> None:
    index = _index(target_count=1)
    edge = _edge("projection-1", "seed-1", 2, "target-1", 101)
    snapshot = _snapshot([edge], authority="d" * 64)
    floor = [_section(index, "seed-1", 1)]

    out, meta = legal_graph_closure.extend_sections(
        index,
        "주요주주에 해당하는지",
        floor,
        snapshot=snapshot,
    )

    assert out == floor
    assert meta["status"] == "fallback"
    assert meta["load"]["status"] == "stale"
    assert "authority_generation" in meta["reasons"][0]


@pytest.mark.parametrize(
    ("omit_cards", "omit_incoming", "reason"),
    [
        ({"target-1"}, set(), "rejected_target_card_missing"),
        (set(), {"projection-1"}, "rejected_target_incoming_port_mismatch"),
    ],
)
def test_target_requires_current_card_and_bidirectional_projection_port(
    omit_cards: set[str],
    omit_incoming: set[str],
    reason: str,
) -> None:
    index = _index(target_count=1)
    edge = _edge("projection-1", "seed-1", 2, "target-1", 101)
    snapshot = _snapshot(
        [edge],
        omit_target_cards=omit_cards,
        omit_incoming=omit_incoming,
    )

    additions, meta = legal_graph_closure.plan_coordinates(
        index,
        "주요주주에 해당하는지",
        [("seed-1", 1)],
        snapshot=snapshot,
    )

    assert additions == []
    assert meta["reason_counts"] == {reason: 1}


def test_target_card_cannot_reactivate_non_current_index_document() -> None:
    index = _index(target_count=1)
    index.docs["target-1"].status = "구판"
    edge = _edge("projection-1", "seed-1", 2, "target-1", 101)
    snapshot = _snapshot([edge])

    additions, meta = legal_graph_closure.plan_coordinates(
        index,
        "주요주주에 해당하는지",
        [("seed-1", 1)],
        snapshot=snapshot,
    )

    assert additions == []
    assert meta["reason_counts"] == {"rejected_target_not_current": 1}


def test_exact_span_hash_and_substring_are_the_only_relevance_text() -> None:
    index = _index(target_count=1)
    block_text = index.docs["seed-1"].block_by_idx[1]["text"]
    quote = "대통령령으로 정하는 주요주주"
    start = block_text.index(quote)
    source = _endpoint(
        "seed-1",
        2,
        precision="EXACT_SPAN",
        block_id=1,
        start=start,
        end=start + len(quote),
        quote_sha256=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
    )
    edge = _edge(
        "projection-1", "seed-1", 2, "target-1", 101, source=source
    )
    snapshot = _snapshot([edge])

    additions, meta = legal_graph_closure.plan_coordinates(
        index,
        "주요주주에 해당하는지",
        [("seed-1", 1)],
        snapshot=snapshot,
    )
    assert [row["coordinate"] for row in additions] == [("target-1", 101)]
    assert meta["reason_counts"] == {"activated": 1}

    tampered_source = _endpoint(
        "seed-1",
        2,
        precision="EXACT_SPAN",
        block_id=1,
        start=start,
        end=start + len(quote),
        quote_sha256="0" * 64,
    )
    tampered = _snapshot([
        _edge(
            "projection-2",
            "seed-1",
            2,
            "target-1",
            101,
            source=tampered_source,
        )
    ])
    additions, meta = legal_graph_closure.plan_coordinates(
        index,
        "주요주주에 해당하는지",
        [("seed-1", 1)],
        snapshot=tampered,
    )
    assert additions == []
    assert meta["reason_counts"] == {"failed_source_span_hash": 1}


def test_exact_span_relevance_does_not_use_surrounding_block_text() -> None:
    index = _index(target_count=1)
    block = index.docs["seed-1"].block_by_idx[1]
    block["text"] = "주요주주 주변문언. 대통령령으로 정하는 보험회사 기준"
    quote = "대통령령으로 정하는 보험회사"
    start = block["text"].index(quote)
    source = _endpoint(
        "seed-1",
        2,
        precision="EXACT_SPAN",
        block_id=1,
        start=start,
        end=start + len(quote),
        quote_sha256=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
    )
    edge = _edge(
        "projection-1", "seed-1", 2, "target-1", 101, source=source
    )

    additions, meta = legal_graph_closure.plan_coordinates(
        index,
        "주요주주에 해당하는지",
        [("seed-1", 1)],
        snapshot=_snapshot([edge]),
    )

    assert additions == []
    assert meta["reason_counts"] == {"rejected_legislative_ambiguity": 1}


def test_scope_ineligible_non_companion_floor_cannot_seed_graph() -> None:
    full = _index(target_count=1)
    index = full.scoped({"target-1"}, name="target only")
    edge = _edge("projection-1", "seed-1", 2, "target-1", 101)
    snapshot = _snapshot([edge])
    floor = [_section(index, "seed-1", 1)]

    out, meta = legal_graph_closure.extend_sections(
        index,
        "주요주주에 해당하는지",
        floor,
        snapshot=snapshot,
    )

    assert out == floor
    assert meta["status"] == "no_scope_eligible_seed"
    assert meta["considered_count"] == 0
    assert meta["scope_ineligible_seeds"] == [["seed-1", 1]]


def test_scope_out_companion_remains_an_eligible_legal_closure_seed() -> None:
    full = _index(target_count=1)
    index = full.scoped({"target-1"}, name="target only")
    edge = _edge("projection-1", "seed-1", 2, "target-1", 101)
    snapshot = _snapshot([edge])
    floor = [_section(index, "seed-1", 1, companion=True)]

    out, meta = legal_graph_closure.extend_sections(
        index,
        "주요주주에 해당하는지",
        floor,
        snapshot=snapshot,
    )

    assert [(row.doc_id, row.node) for row in out] == [
        ("seed-1", 1),
        ("target-1", 101),
    ]
    assert meta["status"] == "expanded"


def test_per_seed_cap_counts_unique_targets_not_projection_rows() -> None:
    index = _index(target_count=5)
    edges = [
        _edge(
            f"projection-{number}",
            "seed-1",
            2,
            "target-1",
            101,
            assertion_id=f"a0{number}",
        )
        for number in range(1, 4)
    ]
    edges.extend(
        _edge(
            f"projection-{number + 3}",
            "seed-1",
            2,
            f"target-{number}",
            100 + number,
            assertion_id=f"a0{number + 3}",
        )
        for number in range(2, 6)
    )
    snapshot = _snapshot(edges)

    additions, meta = legal_graph_closure.plan_coordinates(
        index,
        "주요주주에 해당하는지",
        [("seed-1", 1)],
        snapshot=snapshot,
    )

    assert [row["coordinate"] for row in additions] == [
        ("target-1", 101),
        ("target-2", 102),
        ("target-3", 103),
        ("target-4", 104),
    ]
    assert len(additions[0]["edges"]) == 3
    assert meta["reason_counts"] == {
        "activated": 6,
        "rejected_per_seed_cap": 1,
    }


def test_duplicate_target_keeps_best_coherent_provenance_pair() -> None:
    index = _index(target_count=1)
    low = _edge(
        "projection-low",
        "seed-1",
        2,
        "target-1",
        101,
        assertion_id="assertion-low",
        resolution="ARTICLE_FALLBACK",
    )
    high = _edge(
        "projection-high",
        "seed-2",
        11,
        "target-1",
        101,
        assertion_id="assertion-high",
        resolution="EXACT_SOURCE_BACKED",
    )
    snapshot = _snapshot([low, high])

    additions, meta = legal_graph_closure.plan_coordinates(
        index,
        "주요주주에 해당하는지",
        [("seed-1", 1), ("seed-2", 10)],
        snapshot=snapshot,
    )

    assert len(additions) == 1
    addition = additions[0]
    assert addition["seed_coordinate"] == ("seed-2", 10)
    assert [edge.projection_id for edge in addition["edges"]] == [
        "projection-high"
    ]
    assert addition["provenance_pair"]["source"] == ["seed-2", 10]
    selected = meta["selected"][0]
    assert selected["source_doc_id"] == "seed-2"
    assert selected["projection_ids"] == ["projection-high"]
    assert meta["reason_counts"] == {
        "activated": 1,
        "rejected_duplicate_target": 1,
    }


def test_residual_cap_uses_original_floor_size_before_canonical_dedupe() -> None:
    index = _index(target_count=1)
    edge = _edge("projection-1", "seed-1", 2, "target-1", 101)
    snapshot = _snapshot([edge])

    additions, meta = legal_graph_closure.plan_coordinates(
        index,
        "주요주주에 해당하는지",
        [("seed-1", 1)] * 20,
        snapshot=snapshot,
        cap=20,
    )

    assert additions == []
    assert meta["status"] == "no_residual_slots"
    assert meta["before_count"] == 20
    assert meta["canonical_floor_count"] == 1
    assert meta["after_count"] == 20


def test_materialization_failure_clears_selected_and_activated_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _index(target_count=1)
    edge = _edge("projection-1", "seed-1", 2, "target-1", 101)
    snapshot = _snapshot([edge])
    floor = [_section(index, "seed-1", 1)]
    monkeypatch.setattr(
        legal_graph_closure.coordinates,
        "article_branch",
        lambda *args, **kwargs: None,
    )

    out, meta = legal_graph_closure.extend_sections(
        index,
        "주요주주에 해당하는지",
        floor,
        snapshot=snapshot,
    )

    assert out == floor
    assert meta["status"] == "materialization_failed"
    assert meta["added_count"] == 0
    assert meta["selected"] == []
    assert meta["reason_counts"] == {"failed_materialization": 1}
    assert all(not row["activated"] for row in meta["decisions"])


def test_reachability_terminal_present_exactly_matches_returned_sections() -> None:
    index = _index(target_count=1)
    trace = article_reachability.ArticleReachabilityTrace(
        index, "case-graph-hardening"
    )
    trace.stage("query-source", "source", [])
    trace.stage(
        "scope-filter",
        "filter",
        [("seed-1", 1)],
        parent_stage_ids=("query-source",),
    )
    trace.stage(
        "present",
        "present",
        [("seed-1", 1)],
        parent_stage_ids=("scope-filter",),
    )
    capture = trace.capture()
    sections = [
        _section(index, "seed-1", 1),
        _section(index, "target-1", 101, companion=True),
    ]
    graph_meta = {
        "generation_id": "lgv1-" + "1" * 24,
        "added": [{"doc_id": "target-1", "node": 101}],
        "selected": [{
            "doc_id": "target-1",
            "node": 101,
            "source_doc_id": "seed-1",
            "source_node": 1,
            "projection_ids": ["projection-1"],
        }],
    }

    merged = legalclosure_runtime._merge_graph_reachability(
        index, capture, sections, graph_meta
    )

    article_reachability.validate_capture(merged)
    stages = merged["stage_ledger"]["stages"]
    assert [row["stage_id"] for row in stages[-3:]] == [
        "pre-legal-graph-present",
        "legal-graph-closure-expand",
        "present",
    ]
    assert {
        (row["doc_id"], row["node"]) for row in stages[-1]["after"]
    } == {("seed-1", 1), ("target-1", 101)}
    assert merged["events"][-1]["task"] == "legal-graph-presentation"


def test_runtime_rolls_graph_sections_back_when_trace_cannot_be_reconciled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _index(target_count=1)
    floor = [_section(index, "seed-1", 1)]
    graph = _section(index, "target-1", 101, companion=True)
    trace = article_reachability.ArticleReachabilityTrace(index, "case-bad-trace")
    trace.stage("query-source", "source", [])
    trace.stage(
        "scope-filter",
        "filter",
        [("seed-1", 1)],
        parent_stage_ids=("query-source",),
    )
    trace.stage(
        "present",
        "present",
        [("seed-1", 1)],
        parent_stage_ids=("scope-filter",),
    )
    corrupt_capture = trace.capture()
    corrupt_capture["capture_sha256"] = "0" * 64
    baseline_meta = {
        "strategy": "legalclosure",
        "selected": [{"doc_id": "seed-1", "node": 1}],
        "legal_annotations": {"rows": []},
        "article_reachability": corrupt_capture,
        "article_reachability_elapsed_ms": 0.0,
        "assertion": {},
    }
    graph_meta = {
        "status": "expanded",
        "added_count": 1,
        "before_count": 1,
        "after_count": 2,
        "reason_counts": {"activated": 1},
        "decisions": [{
            "projection_id": "projection-1",
            "activated": True,
            "reason": "activated",
        }],
        "selected": [{
            "doc_id": "target-1",
            "node": 101,
            "source_doc_id": "seed-1",
            "source_node": 1,
            "projection_ids": ["projection-1"],
        }],
        "added": [{"doc_id": "target-1", "node": 101}],
    }
    monkeypatch.setattr(
        legalclosure_runtime.conceptfirst, "registry_path", lambda: Path("registry")
    )
    monkeypatch.setattr(
        legalclosure_runtime.conceptfirst, "load_registry", lambda path: {}
    )
    monkeypatch.setattr(
        legalclosure_runtime.legalclosure,
        "retrieve",
        lambda *args, **kwargs: (list(floor), baseline_meta),
    )
    monkeypatch.setattr(
        legalclosure_runtime.legal_graph_closure,
        "extend_sections",
        lambda *args, **kwargs: ([*floor, graph], graph_meta),
    )
    monkeypatch.setattr(
        legalclosure_runtime.main_promotion, "runtime_provenance", lambda: {}
    )

    sections, meta = legalclosure_runtime.retrieve(
        index,
        "주요주주에 해당하는지",
        llm=None,
        graph_enabled=True,
    )

    assert sections == floor
    assert meta["legal_graph"]["status"] == "fallback"
    assert meta["legal_graph"]["added_count"] == 0
    assert meta["selected"] == [{"doc_id": "seed-1", "node": 1}]
    assert meta["article_reachability"] is corrupt_capture
