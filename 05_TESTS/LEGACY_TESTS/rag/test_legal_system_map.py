from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_research_atlas import LegalResearchAtlas
from lawrag.core.rag.legal_system_map import (
    AuthorityGenerationMismatchError,
    EffectiveDateMismatchError,
    LegalGraphSemanticCardIndex,
    LegalGraphSnapshot,
    LegalInstrumentSystemProfile,
    LegalIssueFamily,
    LegalSystemMap,
    build_legal_system_catalog_snapshot,
    legal_system_catalog_diff,
    load_legal_system_map,
    load_legal_system_runtime,
)


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def current_atlas() -> LegalResearchAtlas:
    index = Index.load(
        store=ROOT / "data" / "structure",
        terms_file=ROOT / "data" / "glossary.json",
        links_file=ROOT / "data" / "links.json",
    )
    return LegalResearchAtlas.from_index(index)


@pytest.fixture(scope="module")
def current_map(current_atlas: LegalResearchAtlas) -> LegalSystemMap:
    return load_legal_system_map(current_atlas)


def test_current_catalog_profiles_every_current_instrument_closed_id(
    current_atlas: LegalResearchAtlas,
    current_map: LegalSystemMap,
) -> None:
    assert len(current_map.profiles) == 139
    assert current_map.expected_document_ids == tuple(
        sorted(current_atlas.current_document_ids)
    )
    assert {row.instrument_id for row in current_map.profiles} == set(
        current_atlas.current_document_ids
    )
    assert sum(row.purpose_source == "LAW_INDEX" for row in current_map.profiles) == 50
    assert sum(bool(row.purpose) for row in current_map.profiles) == 99
    assert all(row.status != "구판" for row in current_map.profiles)


def test_issue_family_catalog_uses_only_closed_current_ids(
    current_map: LegalSystemMap,
) -> None:
    current_ids = set(current_map.expected_document_ids)
    assert {row.family_id for row in current_map.issue_families} == {
        "FINANCIAL_INVESTMENT_SERIES",
        "INFORMATION_PROTECTION_SERIES",
        "FINANCIAL_OUTSOURCING_RULE",
        "FINANCIAL_GOVERNANCE_SERIES",
    }
    assert all(
        set(family.instrument_ids) <= current_ids
        for family in current_map.issue_families
    )


def test_catalog_builder_reproduces_current_snapshot_without_drift(
    current_atlas: LegalResearchAtlas,
) -> None:
    path = ROOT / "data" / "legal_system" / "legal-system-map-v1.json"
    seed = json.loads(path.read_text(encoding="utf-8"))
    rebuilt = build_legal_system_catalog_snapshot(current_atlas, seed)
    diff = legal_system_catalog_diff(seed, rebuilt)
    assert diff["changed"] is False
    assert diff["changed_fields"] == []
    assert diff["graph_changed_fields"] == []
    assert diff["added_document_ids"] == []
    assert diff["removed_document_ids"] == []
    assert diff["issue_families_changed"] is False
    assert diff["before_value_sha256"] == diff["after_value_sha256"]


def test_current_index_runtime_facade_loads_map_without_semantic_cold_load(
    current_atlas: LegalResearchAtlas,
) -> None:
    runtime = load_legal_system_runtime(
        current_atlas.current_index,
        semantic_cards=False,
    )
    assert len(runtime.system_map.profiles) == 139
    assert runtime.semantic_cards is None


class _AtlasProxy:
    def __init__(self, atlas, *, instruments=None, generation=None):
        self.instruments = tuple(instruments or atlas.instruments)
        self.current_document_ids = atlas.current_document_ids
        self.current_index = SimpleNamespace(
            entry_docs=atlas.current_index.entry_docs,
            authority_generation=(
                atlas.current_index.authority_generation
                if generation is None else generation
            ),
            authority_as_of=atlas.current_index.authority_as_of,
        )
        self._atlas = atlas

    def article_units(self, instrument_id):
        return self._atlas.article_units(instrument_id)


def test_authority_generation_mismatch_fails_closed(
    current_atlas: LegalResearchAtlas,
) -> None:
    proxy = _AtlasProxy(current_atlas, generation="f" * 64)
    with pytest.raises(AuthorityGenerationMismatchError):
        load_legal_system_map(proxy)


def test_effective_date_mismatch_fails_closed(
    current_atlas: LegalResearchAtlas,
) -> None:
    records = list(current_atlas.instruments)
    records[0] = replace(records[0], enforce="20991231")
    proxy = _AtlasProxy(current_atlas, instruments=records)
    with pytest.raises(EffectiveDateMismatchError):
        load_legal_system_map(proxy)


def _tiny_system_map() -> LegalSystemMap:
    graph = LegalGraphSnapshot(
        generation_id="lgv1-" + "1" * 24,
        content_sha256="2" * 64,
        projection_policy="semantic-card-v2.1",
        current_sha256="3" * 64,
        manifest_sha256="4" * 64,
        provision_cards_path="projections/provision_cards.jsonl.gz",
        provision_cards_sha256="5" * 64,
        provision_cards_rows=1,
        semantic_cards_path="projections/semantic_cards.jsonl.gz",
        semantic_cards_sha256="6" * 64,
        semantic_cards_rows=1,
    )
    profile = LegalInstrumentSystemProfile(
        instrument_id="law",
        name="시험법",
        source_kind="law",
        norm_layer="STATUTE",
        default_role="PRIMARY_ACT",
        series_key="시험법",
        status="현행",
        effective_date="20260101",
        revised_date="",
        version="",
        purpose="시험 목적",
        purpose_source="LAW_INDEX",
        law_families=(),
    )
    return LegalSystemMap(
        schema_version="legal-system-map-v1",
        catalog_version="test",
        authority_generation="a" * 64,
        authority_as_of="20260101",
        law_index_sha256="b" * 64,
        expected_document_ids=("law",),
        effective_dates_sha256="c" * 64,
        profiles_sha256="d" * 64,
        profiles=(profile,),
        issue_families=(LegalIssueFamily(
            family_id="TEST",
            triggers=("심사",),
            instrument_ids=("law",),
            issue_axes=("CLASSIFICATION",),
            weight=10,
        ),),
        legal_graph=graph,
    )


def test_semantic_card_access_layer_reuses_verified_snapshot_postings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lawrag.core.rag.legal_system_map as module

    coordinate = ("law", 1)
    endpoint = SimpleNamespace(label="제1조 심사업무", document_id="law", node_id=1)
    ports = SimpleNamespace(member_id="unit:one", endpoint=endpoint)
    semantic = SimpleNamespace(
        card_id="semantic_card:one",
        entity_id="entity:one",
        semantic_type="CLASSIFICATION_CRITERION",
        article_root=endpoint,
        family_ids=("CLASSIFICATION",),
        terms=("심사업무", "외부기관"),
        assertion_ids=("rule:one",),
        coverage_keys=("classification_criteria",),
        relation_predicate="SETS_CLASSIFICATION_CRITERIA_FOR",
        label="외부기관의 심사업무",
        card_status="SEMANTIC_READY",
    )
    snapshot = SimpleNamespace(
        generation_id="lgv1-" + "1" * 24,
        authority_generation="a" * 64,
        content_sha256="2" * 64,
        projection_policy="semantic-card-v2.1",
        ports_by_article={coordinate: ports},
        semantic_cards=(semantic,),
        semantic_postings={"심사업무": (0,), "외부기관": (0,)},
        semantics_for_article=lambda value: (semantic,) if value == coordinate else (),
    )
    atlas = SimpleNamespace(
        current_index=SimpleNamespace(
            authority_generation="a" * 64,
            authority_as_of="20260101",
        ),
        article_units=lambda instrument_id: (
            SimpleNamespace(instrument_id="law", node_id=1),
        ),
    )
    monkeypatch.setattr(module, "_validate_graph_header", lambda **kwargs: None)
    monkeypatch.setattr(
        module,
        "current_legal_graph",
        lambda index, root: SimpleNamespace(
            snapshot=snapshot, status="cache_hit", reasons=()
        ),
    )
    access = LegalGraphSemanticCardIndex(atlas, _tiny_system_map())
    assert access.preload() == 1
    card = access.get("law", 1)
    assert card is not None
    assert card.semantic_ready is True
    assert card.matches("외부 기관 심사업무") is True
    assert [row.coordinate for row in access.search(("심사업무", "외부기관"))] == [
        coordinate
    ]
