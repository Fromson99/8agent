import hashlib

from lawrag.core.rag import termexplore
from lawrag.core.rag import verified_span_selector as selector
from lawrag.core.rag.index import Index


def _index():
    return Index.from_docs([("d", {"name": "시험법", "kind": "law"}, {
        "nodes": [
            {"id": node, "parent": None, "level": 1,
             "surface": f"제{node}조", "title": title,
             "span": [node - 1, node]}
            for node, title in ((1, "일반"), (2, "겸직 금지"), (3, "신청서"))
        ],
        "blocks": [
            {"idx": 0, "text": "일반 규정이다.", "kind": "text"},
            {"idx": 1, "text": "준법감시인은 해당 업무를 겸직할 수 없다.", "kind": "text"},
            {"idx": 2, "text": "신청서를 제출한다.", "kind": "text"},
        ],
    })])


def _branch(index, node, origin="initial"):
    return termexplore._branch(index, "d", node, (), origin=origin)


class _LLM:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def structured(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.output


def test_schema_exposes_only_preverified_span_enum():
    schema = selector._schema(["S01", "S02"])
    ids = schema["properties"]["selected_span_ids"]

    assert ids["items"]["enum"] == ["S01", "S02"]
    assert set(schema["properties"]) == {"selected_span_ids", "remaining_gap"}
    assert schema["additionalProperties"] is False


def test_verified_span_offsets_and_hash_are_server_owned():
    index = _index()
    candidate = _branch(index, 2, "source-registry")
    public, by_id = selector._verified_spans(
        index, [candidate], "준법감시인이 겸직할 수 있는가")
    source = selector._source(index, candidate)

    assert public
    for item in by_id.values():
        assert item["text"] == source[item["start"]:item["end"]]
        assert item["source_sha256"] == hashlib.sha256(
            source.encode("utf-8")).hexdigest()
        assert len(item["text"]) <= selector.SPAN_CHARS


def test_selected_span_id_promotes_without_model_quote():
    index = _index()
    incumbent = [_branch(index, 1)]
    candidate = _branch(index, 2, "source-registry")
    llm = _LLM({"selected_span_ids": ["S01"], "remaining_gap": ""})

    selected, meta = selector.run(
        index, "준법감시인이 겸직할 수 있는가", llm,
        incumbent, incumbent, [candidate], "겸직 가능 여부", cap=2)

    accepted = meta["selector_output"]["accepted"][0]
    assert [row.node for row in selected] == [1, 2]
    assert accepted["span_id"] == "S01"
    assert accepted["text"] == selector._source(index, candidate)
    assert "quote" not in meta["selector_output"]["requested"]
    assert meta["validation_errors"] == []


def test_outside_span_id_is_blocked_and_registry_stays_in_pool():
    index = _index()
    incumbent = [_branch(index, 1)]
    candidate = _branch(index, 3, "source-registry")
    llm = _LLM({"selected_span_ids": ["I1"], "remaining_gap": ""})

    selected, meta = selector.run(
        index, "준법감시인이 겸직할 수 있는가", llm,
        incumbent, incumbent, [candidate], "겸직 가능 여부", cap=2)

    assert [row.node for row in selected] == [1]
    assert meta["validation_errors"] == ["span_outside_menu:I1"]
    assert {row["node"] for row in meta["evidence_pool"]} == {1, 3}
    assert meta["hard_deletes"] == 0


def test_full_incumbent_skips_selector_and_never_exchanges():
    index = _index()
    incumbent = [_branch(index, 1), _branch(index, 3)]
    candidate = _branch(index, 2, "source-registry")
    llm = _LLM({"selected_span_ids": [], "remaining_gap": ""})

    selected, meta = selector.run(
        index, "준법감시인이 겸직할 수 있는가", llm,
        incumbent, incumbent, [candidate], "겸직 가능 여부", cap=2)

    assert [row.node for row in selected] == [1, 3]
    assert meta["ran"] is False
    assert llm.calls == []
