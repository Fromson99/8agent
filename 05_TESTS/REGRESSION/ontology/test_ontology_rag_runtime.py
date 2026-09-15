from __future__ import annotations

from pathlib import Path

from lawrag.runtime.components import ontology_rag_v1


def _record(projection_id: str, *surfaces: str) -> dict:
    return {
        "projection_id": projection_id,
        "decision_contract": {
            "sufficient_condition_sets": [
                {"all": [{"value": list(surfaces)}]}
            ]
        },
    }


def test_lookup_blocks_shorter_ready_shadow() -> None:
    records = [_record("definition:information:v1", "정보")]
    record, surface, reason, detail = ontology_rag_v1._lookup(
        records,
        "가명정보란?",
        {"가명정보"},
    )
    assert record is None
    assert surface == ""
    assert reason == "AMBIGUOUS_SURFACE"
    assert detail == "가명정보"


def test_lookup_preserves_longer_unique_match() -> None:
    records = [
        _record("definition:long:v1", "적격기관투자자대상증권"),
        _record("definition:short:v1", "기관투자자"),
    ]
    record, surface, reason, detail = ontology_rag_v1._lookup(
        records,
        "적격기관투자자대상증권이 무엇인가?",
        {"기관"},
    )
    assert record is not None
    assert record["projection_id"] == "definition:long:v1"
    assert surface == "적격기관투자자대상증권"
    assert reason == detail == ""


def test_retrieve_reports_ambiguous_surface_and_preserves_floor(monkeypatch) -> None:
    records = [_record("definition:asset:v1", "자산")]
    trace = {
        "definition_generation": "def-test",
        "definition_content_sha256": "a" * 64,
        "graph_generation": "graph-test",
        "graph_content_sha256": "b" * 64,
    }
    monkeypatch.setattr(
        ontology_rag_v1,
        "_cached_knowledge",
        lambda *_args, **_kwargs: (
            (records, {}, {"주가순자산비율"}, trace),
            False,
            "c" * 64,
        ),
    )
    floor = []
    floor_meta = {
        "selected": [],
        "runtime": {"effective_profile": "legalclosure-v2"},
    }
    sections, meta = ontology_rag_v1.retrieve(
        object(),
        "주가순자산비율이란?",
        baseline_result=(floor, floor_meta),
        definition_root="definitions",
        legal_graph_root="graph",
    )
    assert sections == floor
    assert meta["ontology_rag"]["status"] == "fallback"
    assert meta["ontology_rag"]["reason"] == "AMBIGUOUS_SURFACE"
    assert meta["ontology_rag"]["detail"] == "주가순자산비율"
    assert meta["ontology_rag"]["added_count"] == 0
    assert meta["ontology_rag"]["baseline_floor_preserved"] is True
    assert meta["ontology_rag"]["knowledge_cache"] == "miss"


def test_default_store_paths_use_canonical_data_root(monkeypatch) -> None:
    monkeypatch.delenv("RAG_DEFINITION_PROJECTION_STORE", raising=False)
    monkeypatch.delenv("RAG_LEGAL_GRAPH_STORE", raising=False)
    monkeypatch.setattr(
        ontology_rag_v1,
        "data_path",
        lambda *parts: Path("/verified-data").joinpath(*parts),
    )
    definitions, graph, binding = ontology_rag_v1._resolve_store_paths(None, None)
    assert definitions == Path("/verified-data/PROJECTIONS/DEFINITIONS")
    assert graph == Path("/verified-data/legal_graph")
    assert binding == "workspace-default"


def test_verified_knowledge_cache_reuses_same_pointer_key(monkeypatch) -> None:
    ontology_rag_v1._clear_knowledge_cache()
    key = ("definitions", "a" * 64, "graph", "b" * 64)
    opened = ([{"projection_id": "definition:test:v1"}], {}, set(), {})
    calls = 0

    monkeypatch.setattr(ontology_rag_v1, "_knowledge_cache_key", lambda *_: key)

    def open_once(*_args):
        nonlocal calls
        calls += 1
        return opened

    monkeypatch.setattr(ontology_rag_v1, "_open_knowledge", open_once)
    first, first_hit, first_key = ontology_rag_v1._cached_knowledge(
        Path("definitions"), Path("graph")
    )
    second, second_hit, second_key = ontology_rag_v1._cached_knowledge(
        Path("definitions"), Path("graph")
    )
    assert first is second is opened
    assert first_hit is False
    assert second_hit is True
    assert first_key == second_key
    assert calls == 1


def test_pointer_key_change_forces_reopen(monkeypatch) -> None:
    ontology_rag_v1._clear_knowledge_cache()
    state = {"key": ("definitions", "a" * 64, "graph", "b" * 64)}
    calls = 0

    monkeypatch.setattr(
        ontology_rag_v1,
        "_knowledge_cache_key",
        lambda *_: state["key"],
    )

    def open_value(*_args):
        nonlocal calls
        calls += 1
        return ([], {}, set(), {"open": calls})

    monkeypatch.setattr(ontology_rag_v1, "_open_knowledge", open_value)
    first, first_hit, _ = ontology_rag_v1._cached_knowledge(
        Path("definitions"), Path("graph")
    )
    state["key"] = ("definitions", "c" * 64, "graph", "b" * 64)
    second, second_hit, _ = ontology_rag_v1._cached_knowledge(
        Path("definitions"), Path("graph")
    )
    assert first_hit is second_hit is False
    assert first[3]["open"] == 1
    assert second[3]["open"] == 2
    assert calls == 2
