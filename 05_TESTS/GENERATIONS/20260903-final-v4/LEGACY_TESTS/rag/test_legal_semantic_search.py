from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

from lawrag.core.legal_graph import SCHEMA_VERSION, stable_id, validate_row
from lawrag.core.rag import legal_semantic_search
from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_graph_store import (
    ArticlePorts,
    EndpointLite,
    LegalGraphSnapshot,
    SemanticCardLite,
)


AUTHORITY = "a" * 64


def _endpoint(doc_id: str, node: int) -> EndpointLite:
    return EndpointLite(
        kind="STRUCTURAL_UNIT",
        precision="EXACT_UNIT",
        ref_id=stable_id("unit", doc_id, node),
        document_id=doc_id,
        node_id=node,
        block_id=None,
        start=None,
        end=None,
        quote_sha256="",
        coordinate=f"{doc_id}:{node}",
        label=f"{doc_id}:{node}",
    )


def _index(count: int = 22) -> Index:
    docs = []
    for number in range(count):
        doc_id = f"doc-{number}"
        docs.append((doc_id, {"name": doc_id, "kind": "law"}, {
            "nodes": [{
                "id": 1, "parent": None, "level": 1, "surface": "제1조",
                "title": "주요주주 이사회 권한", "span": [0, 1],
            }],
            "blocks": [{
                "idx": 0, "text": "주요주주 과반수 이사회 위임 권한",
                "kind": "text",
            }],
        }))
    return Index.from_docs(
        docs,
        canonical_doc_ids={row[0] for row in docs},
        authority_generation=AUTHORITY,
        authority_as_of="20260828",
    )


def _snapshot(cards: list[SemanticCardLite]) -> LegalGraphSnapshot:
    ports = {
        (f"doc-{number}", 1): ArticlePorts(
            member_id=stable_id("unit", f"doc-{number}", 1),
            endpoint=_endpoint(f"doc-{number}", 1),
            outgoing=(),
            incoming=(),
        )
        for number in range(22)
    }
    postings: dict[str, list[int]] = {}
    by_article: dict[tuple[str, int], list[int]] = {}
    for index, card in enumerate(cards):
        coordinate = (card.article_root.document_id, int(card.article_root.node_id))
        by_article.setdefault(coordinate, []).append(index)
        for term in card.terms:
            postings.setdefault(term, []).append(index)
    return LegalGraphSnapshot(
        root=Path("."),
        generation_id="lgv1-" + "1" * 24,
        authority_generation=AUTHORITY,
        content_sha256="b" * 64,
        projection_policy="semantic-card-v2.1",
        pointer_sha256="c" * 64,
        runtime_wired_in_artifact=False,
        ports_by_article=MappingProxyType(ports),
        edge_by_projection_id=MappingProxyType({}),
        loaded_rows=len(ports) + len(cards),
        load_ms=0.0,
        semantic_cards=tuple(cards),
        semantic_postings=MappingProxyType({
            term: tuple(values) for term, values in postings.items()
        }),
        semantic_by_article=MappingProxyType({
            coordinate: tuple(values) for coordinate, values in by_article.items()
        }),
    )


def _card(
    doc_id: str,
    *,
    semantic_type: str = "CLASSIFICATION_CRITERION",
    family: str = "CLASSIFICATION",
    terms: tuple[str, ...] = ("과반수", "주요주주"),
) -> SemanticCardLite:
    endpoint = _endpoint(doc_id, 1)
    return SemanticCardLite(
        card_id=stable_id("semantic_card", doc_id),
        entity_id=stable_id("entity", doc_id),
        semantic_type=semantic_type,
        source=endpoint,
        article_root=endpoint,
        family_ids=(family,),
        terms=tuple(sorted(terms)),
        assertion_ids=(stable_id("rule", doc_id),),
        coverage_keys=("classification_criteria",),
        relation_predicate="SETS_CLASSIFICATION_CRITERIA_FOR",
        label="주요주주 과반수 기준",
    )


def test_structure_only_card_is_a_projection_not_a_claim() -> None:
    endpoint = {
        "kind": "STRUCTURAL_UNIT",
        "precision": "EXACT_UNIT",
        "ref_id": stable_id("unit", "doc", 1),
        "selector": {"document_id": "doc", "node_id": 1},
    }
    row = {
        "schema_version": SCHEMA_VERSION,
        "generation_id": "lgv1-" + "1" * 24,
        "authority_generation": AUTHORITY,
        "layer": "projection",
        "row_type": "semantic_card",
        "id": stable_id("semantic_card", "structure", "doc", 1),
        "source": endpoint,
        "article_root": endpoint,
        "entity_id": "",
        "semantic_type": "STRUCTURE_ONLY",
        "card_status": "STRUCTURE_ONLY",
        "family_ids": ["CLASSIFICATION"],
        "terms": ["주요주주"],
        "assertion_ids": [],
        "coverage_keys": ["structure"],
    }
    assert validate_row(row) is row


def test_full_cap_may_replace_only_bounded_tail_for_semantic_landing() -> None:
    index = _index()
    snapshot = _snapshot([_card("doc-21")])
    floor = [(f"doc-{number}", 1) for number in range(20)]

    selected, meta = legal_semantic_search.plan_semantic_coordinates(
        index,
        "주요주주 과반수 기준은 무엇인가",
        floor,
        snapshot=snapshot,
        cap=20,
    )

    final = [tuple(row["coordinate"]) for row in selected]
    assert ("doc-21", 1) in final
    assert final[:12] == floor[:12]
    assert len(final) == 20
    assert len(meta["discarded_floor"]) <= legal_semantic_search.REPLACEMENT_CAP


def test_negative_conclusion_is_reviewable_assessment_not_relation() -> None:
    index = _index()
    snapshot = _snapshot([_card(
        "doc-21",
        semantic_type="AUTHORITY_ALLOCATION",
        family="AUTHORITY",
        terms=("위임", "이사회"),
    )])

    selected, meta = legal_semantic_search.plan_semantic_coordinates(
        index,
        "이사회에 위임할 수 없는가",
        [],
        snapshot=snapshot,
        cap=20,
    )

    assert selected
    assert len(meta["legal_assessments"]) == 1
    assessment = meta["legal_assessments"][0]
    assert assessment["requires_review"] is True
    assert assessment["reasoning_mode"] == "ABSENCE_WITHIN_CLOSED_BUNDLE"
    assert assessment["conclusion"] == "DELEGATION_NOT_EXPLICITLY_SUPPORTED"


def test_stale_injected_snapshot_fails_open() -> None:
    index = _index()
    snapshot = _snapshot([_card("doc-21")])
    object.__setattr__(snapshot, "authority_generation", "d" * 64)

    selected, meta = legal_semantic_search.plan_semantic_coordinates(
        index, "주요주주 기준", [("doc-0", 1)], snapshot=snapshot,
    )

    assert selected == []
    assert meta["fallback"] == "authority_generation_mismatch"


def test_compiled_family_and_predicate_hints_are_validated_and_recorded() -> None:
    index = _index()
    snapshot = _snapshot([_card(
        "doc-21", semantic_type="AUTHORITY_ALLOCATION", family="AUTHORITY",
        terms=("이사회", "결정"),
    )])

    _selected, meta = legal_semantic_search.plan_semantic_coordinates(
        index,
        "이사회 결정",
        [],
        snapshot=snapshot,
        family_hints=["AUTHORITY", "NOT_A_FAMILY"],
        predicate_hints=["DELEGATES_ADMINISTRATIVE_AUTHORITY", "NOT_A_PREDICATE"],
    )

    assert meta["compiled_hints"] == {
        "family_ids": ["AUTHORITY"],
        "predicates": ["DELEGATES_ADMINISTRATIVE_AUTHORITY"],
    }
    assert "DELEGATES_ADMINISTRATIVE_AUTHORITY" in meta["allowed_predicates"]
