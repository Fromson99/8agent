import json

import pytest

from lawrag.core.rag.search_trace import (
    SearchTrace,
    canonical_json,
    coordinate_fingerprint,
    stable_fingerprint,
)


def test_stable_json_fingerprint_is_order_independent_and_namespaced():
    left = {"b": [2, 1], "a": {"y", "x"}}
    right = {"a": {"x", "y"}, "b": [2, 1]}

    assert canonical_json(left) == canonical_json(right)
    assert stable_fingerprint(left, namespace="query") == stable_fingerprint(
        right, namespace="query")
    assert stable_fingerprint(left, namespace="query") != stable_fingerprint(
        left, namespace="operator")
    assert stable_fingerprint(left).startswith("sha256:")


def test_same_coordinate_rediscovery_appends_provenance_without_new_candidate():
    trace = SearchTrace("질문", corpus_fingerprint="corpus-v1", trace_id="T1")

    first = trace.observe_coordinate(
        ("law", 29), origin="exact-structural", observation_depth=0,
        metadata={"terms": ["준법감시인"]})
    second = trace.observe_coordinate(
        ("law", 29), origin="assertion-tree", observation_depth=1)

    assert first == second == coordinate_fingerprint(("law", 29))
    assert trace.seen_coordinates() == frozenset({("law", 29)})
    assert [event.kind for event in trace.events] == [
        "coordinate_observed", "coordinate_rediscovered"]
    row = trace.coordinate_ledger()[0]
    assert row["origins"] == ["exact-structural", "assertion-tree"]
    assert row["observation_count"] == 2
    assert row["min_observation_depth"] == 0
    assert row["max_observation_depth"] == 1
    assert trace.summary()["observed_coordinates"] == 1
    assert trace.summary()["rediscovery_events"] == 1


def test_events_and_payload_are_immutable_views_of_append_only_history():
    trace = SearchTrace("질문")
    trace.observe_coordinate(
        ("d", 1), origin="keyword-bm25", metadata={"score": 1.25})
    before = trace.events

    payload = before[0].payload
    payload["origin"] = "tampered"

    assert isinstance(before, tuple)
    assert trace.events[0].payload["origin"] == "keyword-bm25"
    assert not hasattr(trace, "delete")
    assert not hasattr(trace, "remove")
    assert not hasattr(trace, "reject")


def test_selection_and_deferral_are_events_and_never_remove_coordinate():
    trace = SearchTrace("질문")
    trace.observe_coordinates(
        [("d", 1), ("d", 2)], origin="initial", observation_depth=0)
    trace.mark_selected([("d", 1)], stage="baseline")
    trace.mark_deferred([("d", 2)], stage="top20", reason="slot cap")
    trace.mark_selected([("d", 2)], stage="grounded-witness")

    ledger = {tuple(row["coordinate"]): row for row in trace.coordinate_ledger()}
    assert trace.seen_coordinates() == frozenset({("d", 1), ("d", 2)})
    assert ledger[("d", 1)]["status"] == "selected"
    assert ledger[("d", 2)]["status"] == "selected"
    assert [row["status"] for row in ledger[("d", 2)]["status_history"]] == [
        "deferred", "selected"]
    assert trace.summary()["selected_coordinates"] == 2
    assert trace.summary()["deferred_coordinates"] == 0


def test_unknown_coordinate_cannot_be_selected_or_deferred():
    trace = SearchTrace("질문")

    with pytest.raises(KeyError):
        trace.mark_selected([("d", 1)], stage="baseline")
    with pytest.raises(KeyError):
        trace.mark_deferred([("d", 1)], stage="cap")


def test_query_operator_and_edge_fingerprints_are_stable_but_events_accumulate():
    trace = SearchTrace("질문")
    trace.observe_coordinate(("law", 29), origin="initial")

    q1 = trace.record_query(
        "준법감시인 겸직", role="missing-facet",
        parameters={"b": 2, "a": 1}, call_id="q1")
    q2 = trace.record_query(
        "준법감시인 겸직", role="missing-facet",
        parameters={"a": 1, "b": 2}, call_id="q2")
    op1 = trace.record_operator(
        "bm25", query_fingerprint=q1, seeds=[("law", 29)],
        scope={"decree", "law"}, parameters={"limit": 16})
    op2 = trace.record_operator(
        "bm25", query_fingerprint=q2, seeds=[("law", 29)],
        scope={"law", "decree"}, parameters={"limit": 16})
    edge1 = trace.record_edge(
        ("law", 29), ("decree", 24), relation="DELEGATES_TO",
        direction="out", provenance=["official", "source_text"],
        state="offered")
    edge2 = trace.record_edge(
        ("law", 29), ("decree", 24), relation="DELEGATES_TO",
        direction="out", provenance=["source_text", "official"],
        state="consumed")

    assert q1 == q2
    assert op1 == op2
    assert edge1 == edge2
    assert trace.query_fingerprints() == frozenset({q1})
    assert trace.operator_fingerprints() == frozenset({op1})
    assert trace.edge_fingerprints() == frozenset({edge1})
    summary = trace.summary()
    assert summary["queries"] == {"events": 2, "unique": 1}
    assert summary["operators"] == {"events": 2, "unique": 1}
    assert summary["edges"] == {
        "events": 2, "unique": 1,
        "states": {"consumed": 1, "offered": 1},
    }


def test_inspection_depth_and_facets_accumulate_without_coordinate_replacement():
    trace = SearchTrace("기간과 예외는?")
    trace.observe_coordinate(("d", 7), origin="initial", observation_depth=0)
    trace.mark_inspected(
        ("d", 7), facet_ids=["TIME", "EXCEPTION", "TIME"],
        observation_depth=2, metadata={"body_complete": True})

    row = trace.coordinate_ledger()[0]
    assert row["inspected_facets"] == ["TIME", "EXCEPTION"]
    assert row["max_observation_depth"] == 2
    assert trace.summary()["observation_depth_events"] == {"0": 1, "2": 1}


def test_summary_and_events_are_strictly_json_safe():
    trace = SearchTrace("질문", corpus_fingerprint="fp", trace_id="fixed")
    trace.observe_coordinate(("d", "제1조"), origin="exact")
    trace.mark_selected([("d", "제1조")], stage="baseline")
    trace.record_query("질문", parameters={"terms": ("가", "나")})

    encoded_summary = json.dumps(
        trace.summary(), ensure_ascii=False, allow_nan=False, sort_keys=True)
    encoded_events = json.dumps(
        [event.as_dict() for event in trace.events],
        ensure_ascii=False, allow_nan=False, sort_keys=True)

    assert '"trace_id": "fixed"' in encoded_summary
    assert '"coordinate": ["d", "제1조"]' in encoded_events


def test_invalid_depth_and_unstable_values_fail_loudly():
    trace = SearchTrace("질문")

    with pytest.raises(ValueError):
        trace.observe_coordinate(("d", 1), origin="x", observation_depth=-1)
    with pytest.raises(ValueError):
        trace.observe_coordinate(("d", 1), origin="x", observation_depth=True)
    with pytest.raises(TypeError):
        stable_fingerprint({"bad": object()})
