from lawrag.core.rag import span_feedback, termexplore
from lawrag.core.rag.index import Index


def _index():
    return Index.from_docs([("d", {"name": "시험법", "kind": "law"}, {
        "nodes": [
            {"id": node, "parent": None, "level": 1,
             "surface": f"제{node}조", "title": title,
             "span": [node - 1, node]}
            for node, title in (
                (1, "일반"), (2, "채무조정"),
                (3, "준법감시인"), (4, "시행령 위임"))
        ],
        "blocks": [
            {"idx": 0, "text": "일반 규정이다.", "kind": "text"},
            {"idx": 1, "text": "채무조정 업무를 전담한다.", "kind": "text"},
            {"idx": 2, "text": "준법감시인은 다른 업무를 겸직할 수 없다.", "kind": "text"},
            {"idx": 3, "text": "구체적인 사항은 대통령령으로 정한다.", "kind": "text"},
        ],
    })])


def _branch(index, node, origin="initial", terms=()):
    return termexplore._branch(index, "d", node, tuple(terms), origin=origin)


class _LLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def structured(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


def _response(*, status="partial", evidence=(), missing=("F1",), actions=()):
    return {
        "hypotheses": [{"id": "H1", "legal_operation": "채무조정 업무",
                         "possible_conclusion": "전담 여부"}],
        "open_obligations": [{"id": "F1", "kind": "OPERATION",
                               "description": "채무조정 전담 여부",
                               "required": True}],
        "witness": {
            "status": status,
            "conclusion": "관련 조문으로 전담 여부를 판단한다" if evidence else "",
            "evidence": list(evidence), "edge_ids": [],
            "covered_obligation_ids": ([] if not evidence else ["F1"]),
            "missing_obligation_ids": list(missing),
        },
        "actions": list(actions),
    }


def _action(kind, *, lane="expand_unseen", from_ids=("C1",),
            keywords=("채무조정",), query="채무조정 업무", target="F1"):
    return {
        "lane": lane, "kind": kind, "target_obligation": target,
        "from_ids": list(from_ids), "edge_ids": [],
        "keywords": list(keywords), "query": query,
        "reason": "열린 업무유형 축을 조사한다",
    }


def test_schema_has_no_keep_reject_or_sufficient_contract():
    schema = span_feedback._schema(["C1"], [])

    assert "keep" not in schema["properties"]
    assert "reject" not in schema["properties"]
    assert "sufficient" not in schema["properties"]


def test_schema_uses_only_provider_supported_array_contract():
    schema = span_feedback._schema(["C1"], ["E1"], ["P1"])

    def walk(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    assert all("maxItems" not in node and "minItems" not in node
               for node in walk(schema))
    evidence = schema["properties"]["witness"]["properties"]["evidence"]
    assert evidence["items"]["properties"]["candidate_id"] == {
        "type": "string"}
    actions = schema["properties"]["actions"]["items"]["properties"]
    assert actions["from_ids"]["items"] == {"type": "string"}
    assert actions["edge_ids"]["items"] == {"type": "string"}


def test_witness_preserves_only_closed_proof_edge_ids(monkeypatch):
    monkeypatch.setattr(
        span_feedback.grounded_witness, "validate_witness",
        lambda *args, **kwargs: {"status": "partial", "errors": []})
    raw = {
        "status": "partial", "conclusion": "", "evidence": [],
        "edge_ids": ["P1", "unknown"],
        "covered_obligation_ids": [], "missing_obligation_ids": [],
    }

    result = span_feedback._validate_witness(
        _index(), raw, {}, {"P1": object()}, ())

    assert result["edge_ids"] == ["P1"]
    assert result["errors"] == ["unknown_proof_edge:unknown"]


def test_partial_stop_preserves_incumbent_and_never_deletes():
    index = _index()
    initial = [_branch(index, 1)]
    llm = _LLM([_response(actions=[_action(
        "stop", lane="stop", keywords=(), query="", target="")])])

    selected, meta = span_feedback.run(
        index, "채무를 조정할 수 있는가", llm,
        initial, initial, (), {}, max_steps=1)

    assert [row.node for row in selected] == [1]
    assert meta["baseline_preserved"] is True
    assert meta["hard_deletes"] == 0 and meta["rejected"] == []
    assert {tuple(row["coordinate"])
            for row in meta["search_trace_events"]
            if row["coordinate"] is not None} >= {("d", 1)}


def test_seen_review_lifts_observation_and_can_promote_deferred_witness():
    index = _index()
    initial = [_branch(index, 1)]
    deferred = _branch(index, 2, origin="initial-deferred", terms=("채무조정",))
    inspect = _action(
        "inspect_seen", lane="revisit_seen", from_ids=("C2",),
        keywords=(), query="", target="채무조정 업무")
    grounded = {"candidate_id": "C2", "quote": "채무조정 업무를 전담한다.",
                "facet_ids": ["F1"]}
    llm = _LLM([
        _response(actions=[inspect]),
        _response(status="complete", evidence=[grounded], missing=(), actions=[]),
    ])

    selected, meta = span_feedback.run(
        index, "채무조정 업무를 누가 전담하는가", llm,
        initial, [initial[0], deferred], ("채무조정",), {}, max_steps=2)

    assert [row.node for row in selected] == [1, 2]
    pool = {row["node"]: row for row in meta["evidence_pool"]}
    assert pool[2]["observation_level"] == 4
    assert "채무조정 업무" in pool[2]["inspected_facets"]
    assert meta["status"] == "complete"


def test_unseen_search_appends_new_coordinate_and_fills_only_empty_slot(monkeypatch):
    index = _index()
    initial = [_branch(index, 1)]
    fresh = _branch(index, 3, origin="span-keyword", terms=("준법감시인",))
    action = _action(
        "keyword_search", keywords=("준법감시인",),
        query="준법감시인 겸직 제한", target="겸직 제한")
    grounded = {"candidate_id": "C2",
                "quote": "준법감시인은 다른 업무를 겸직할 수 없다.",
                "facet_ids": ["F1"]}
    llm = _LLM([
        _response(actions=[action]),
        _response(status="complete", evidence=[grounded], missing=(), actions=[]),
    ])
    monkeypatch.setattr(
        span_feedback, "_execute_action",
        lambda *args, **kwargs: ([fresh], {"tool": "keyword_search"}))
    monkeypatch.setattr(
        span_feedback, "_mandatory_companions",
        lambda *args, **kwargs: ([], []))

    selected, meta = span_feedback.run(
        index, "채무조정 담당자가 겸직할 수 있는가", llm,
        initial, initial, ("채무조정",), {}, cap=2, max_steps=2)

    assert [row.node for row in selected] == [1, 3]
    assert {row["node"] for row in meta["evidence_pool"]} == {1, 3}
    assert meta["trail"][0]["actions"][0]["span_delta"][
        "coordinate_novelty"] == 1.0


def test_full_incumbent_is_immutable_while_internal_pool_still_spans(monkeypatch):
    index = _index()
    initial = [_branch(index, 1), _branch(index, 2)]
    fresh = _branch(index, 3, origin="span-vector", terms=("준법감시인",))
    action = _action(
        "vector_search", keywords=(), query="준법감시인 겸직 제한",
        target="겸직 제한")
    llm = _LLM([_response(actions=[action])])
    monkeypatch.setattr(
        span_feedback, "_execute_action",
        lambda *args, **kwargs: ([fresh], {"tool": "vector_search"}))
    monkeypatch.setattr(
        span_feedback, "_mandatory_companions",
        lambda *args, **kwargs: ([], []))

    selected, meta = span_feedback.run(
        index, "겸직 제한은?", llm, initial, initial, (), {},
        cap=2, max_steps=1)

    assert [row.node for row in selected] == [1, 2]
    assert {row["node"] for row in meta["evidence_pool"]} == {1, 2, 3}
    assert meta["presented_count"] == 2


def test_same_operator_in_one_basis_is_executed_once(monkeypatch):
    index = _index()
    initial = [_branch(index, 1)]
    fresh = _branch(index, 3, origin="span-keyword", terms=("준법감시인",))
    action = _action(
        "keyword_search", keywords=("준법감시인",),
        query="준법감시인 겸직 제한", target="겸직 제한")
    calls = []

    def execute(*args, **kwargs):
        calls.append(1)
        return [fresh], {"tool": "keyword_search"}

    llm = _LLM([_response(actions=[action, dict(action)])])
    monkeypatch.setattr(span_feedback, "_execute_action", execute)
    monkeypatch.setattr(
        span_feedback, "_mandatory_companions",
        lambda *args, **kwargs: ([], []))

    _selected, meta = span_feedback.run(
        index, "겸직 제한은?", llm, initial, initial, (), {}, max_steps=1)

    assert len(calls) == 1
    assert meta["duplicate_actions"] == 1
    assert meta["trail"][0]["actions"][1]["skipped"] == (
        "duplicate_operator_fingerprint")


def test_observed_from_meta_keeps_pre_top20_review_candidates():
    index = _index()
    initial = [_branch(index, 1)]
    meta = {"primary": {"review_candidates": [
        {"doc_id": "d", "node": 2, "origin": "exact",
         "mandatory": False}]}}

    rows = span_feedback.observed_from_meta(index, initial, (), meta)

    assert [row.node for row in rows] == [1, 2]
