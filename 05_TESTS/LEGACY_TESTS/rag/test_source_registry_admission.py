from lawrag.core.rag import source_registry_admission as registry
from lawrag.core.rag import termexplore
from lawrag.core.rag.index import Index


def _index():
    return Index.from_docs([("d", {"name": "시험법", "kind": "law"}, {
        "nodes": [
            {"id": node, "parent": None, "level": 1,
             "surface": f"제{node}조", "title": title,
             "span": [node - 1, node]}
            for node, title in ((1, "일반"), (2, "채무조정"), (3, "겸직"))
        ],
        "blocks": [
            {"idx": 0, "text": "일반 규정이다.", "kind": "text"},
            {"idx": 1, "text": "채무조정 업무를 전담한다.", "kind": "text"},
            {"idx": 2, "text": "겸직할 수 없다.", "kind": "text"},
        ],
    })])


def _branch(index, node, origin="initial"):
    return termexplore._branch(index, "d", node, (), origin=origin)


def test_source_registry_issues_reproducible_receipt():
    index = _index()
    row, receipt = registry._source_record(index, _branch(index, 2))

    assert row is not None
    assert row.coordinate == ("d", 2)
    assert receipt["status"] == "verified"
    assert receipt["source_chars"] > 0
    assert len(receipt["source_sha256"]) == 64


def test_replay_preserves_incumbent_and_fills_only_empty_slots(monkeypatch):
    index = _index()
    initial = _branch(index, 1)
    fresh = _branch(index, 2, origin="boundary-exact")
    monkeypatch.setattr(
        registry.boundary, "_execute",
        lambda *args, **kwargs: ([fresh], {"tool": "exact_search"}))

    selected, meta = registry.run(
        index, "채무조정 업무", [initial], [initial], [initial], (),
        {"kind": "exact_search", "query": "채무조정", "keywords": []},
        cap=2)

    assert [row.node for row in selected] == [1, 2]
    assert meta["hard_deletes"] == 0
    assert [row["node"] for row in meta["promoted"]] == [2]


def test_full_incumbent_is_never_exchanged(monkeypatch):
    index = _index()
    initial = [_branch(index, 1), _branch(index, 3)]
    fresh = _branch(index, 2, origin="boundary-exact")
    monkeypatch.setattr(
        registry.boundary, "_execute",
        lambda *args, **kwargs: ([fresh], {"tool": "exact_search"}))

    selected, meta = registry.run(
        index, "채무조정 업무", initial, initial, initial, (),
        {"kind": "exact_search", "query": "채무조정", "keywords": []},
        cap=2)

    assert [row.node for row in selected] == [1, 3]
    assert [row["node"] for row in meta["admitted"]] == [2]
    assert meta["promoted"] == []


def test_non_replayable_parent_action_is_noop():
    index = _index()
    initial = [_branch(index, 1)]

    selected, meta = registry.run(
        index, "일반 규정", initial, initial, initial, (),
        {"kind": "stop", "skipped": "no_action"})

    assert [row.node for row in selected] == [1]
    assert meta["ran"] is False
    assert meta["registry_receipts"] == []
