from dataclasses import replace

from lawrag.core.rag import verified_span_coverage_gate as gate
from lawrag.core.rag import termexplore


def _row(doc_id: str, node: int, *, origin: str,
         source_doc_id: str = "") -> termexplore.TermBranch:
    return termexplore.TermBranch(
        doc_id=doc_id, node=node, doc=doc_id, path=f"제{node}조",
        terms=(), excerpts=(), body="본문", body_chars=2, origin=origin,
        source_doc_id=source_doc_id,
    )


def test_schema_uses_closed_ids_without_provider_max_items():
    schema = gate._schema(["V001", "V002"])
    items = schema["properties"]["supporting_span_ids"]
    assert items["items"]["enum"] == ["V001", "V002"]
    assert "maxItems" not in items
    assert schema["additionalProperties"] is False


def test_validate_decision_enforces_answer_and_explore_routes():
    by_id = {"V001": {"span_id": "V001", "coordinate": ["d", 1],
                       "row": object()}}
    answer, errors = gate._validate_decision({
        "decision": "answer", "supporting_span_ids": ["V001"],
        "gap_type": "none", "route": "global_search",
        "missing": [], "reason": "enough",
    }, by_id)
    assert answer["route"] == "none"
    assert "answer_route_must_be_none" in errors

    explore, errors = gate._validate_decision({
        "decision": "explore", "supporting_span_ids": [],
        "gap_type": "exception", "route": "none",
        "missing": ["예외"], "reason": "gap",
    }, by_id)
    assert explore["decision"] == "insufficient"
    assert "explore_route_must_not_be_none" in errors


def test_validate_decision_rejects_unknown_span_id():
    result, errors = gate._validate_decision({
        "decision": "insufficient", "supporting_span_ids": ["V999"],
        "gap_type": "other", "route": "none",
        "missing": [], "reason": "none",
    }, {})
    assert result["supporting_span_ids"] == []
    assert errors == ["span_outside_menu:V999"]


def test_route_candidates_are_append_only_and_bounded():
    incumbent = [_row("d1", 1, origin="exact")]
    pool = [
        incumbent[0],
        _row("d2", 2, origin="boundary-relation:BASED_ON",
             source_doc_id="d1"),
        _row("d1", 3, origin="boundary-exact"),
        _row("d3", 4, origin="boundary-exact"),
        _row("d4", 5, origin="adjacent-article"),
    ]
    assert [row.coordinate for row in gate.route_candidates(
        pool, incumbent, "relation")] == [("d2", 2)]
    assert [row.coordinate for row in gate.route_candidates(
        pool, incumbent, "document_search")] == [("d1", 3)]
    assert [row.coordinate for row in gate.route_candidates(
        pool, incumbent, "structure_move")] == [("d4", 5)]
    assert len(gate.route_candidates(pool, incumbent, "global_search", cap=2)) == 2


def test_route_candidates_dedupe_coordinates():
    incumbent = [_row("d1", 1, origin="exact")]
    first = _row("d2", 2, origin="keyword")
    duplicate = replace(first, path="duplicate")
    rows = gate.route_candidates(
        [first, duplicate], incumbent, "global_search", cap=3)
    assert [row.coordinate for row in rows] == [("d2", 2)]
