from lawrag.core.rag import relation_navigation, relations
from lawrag.core.rag.index import Index


def _index():
    def doc(title):
        return {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": "제1조", "title": title, "span": [0, 1]}],
            "blocks": [{"idx": 0, "node": 1, "text": title, "kind": "text"}],
        }
    return Index.from_docs([
        ("law", {"name": "시험법", "kind": "law"}, doc("의무")),
        ("decree", {"name": "시험법 시행령", "kind": "law"}, doc("방법")),
        ("penalty", {"name": "시험법", "kind": "law"}, doc("제재")),
        ("definition", {"name": "시험법", "kind": "law"}, doc("정의")),
    ])


def _edge(kind, src, dst, **props):
    return relations.SectionRelation(
        kind, src, 1, dst, 1,
        {"status": "resolved", "provenance": ["test:bundle"], **props})


def test_relation_bundle의_확정간선만_닫힌_E메뉴로_바꾼다(monkeypatch):
    idx = _index()
    outgoing = (
        _edge("DELEGATES_TO", "law", "decree", link="대통령령"),
        _edge("VIOLATION_SANCTIONED_BY", "law", "penalty", surface="위반"),
    )
    monkeypatch.setattr(
        relation_navigation.relations, "incident",
        lambda _index, doc, node: (outgoing, ()) if doc == "law" else ((), ()))

    rows, meta = relation_navigation.neighbors(idx, [("law", 1)], cap=10)

    assert [(row.edge_id, row.target_doc_id, row.graph_kind) for row in rows] == [
        ("E1", "decree", "DELEGATES_TO"),
        ("E2", "penalty", "VIOLATION_SANCTIONED_BY"),
    ]
    assert all(row.mandatory for row in rows)
    assert meta["source"] == "relations.RelationBundle"
    assert meta["by_kind"] == {
        "DELEGATES_TO": 1, "VIOLATION_SANCTIONED_BY": 1}


def test_역방향에서도_출발조문으로_점프할_수_있다(monkeypatch):
    idx = _index()
    sanction = _edge("VIOLATION_SANCTIONED_BY", "law", "penalty")
    monkeypatch.setattr(
        relation_navigation.relations, "incident",
        lambda _index, doc, node: ((), (sanction,))
        if doc == "penalty" else ((), ()))

    rows, _ = relation_navigation.neighbors(
        idx, [("penalty", 1)], direction="in")

    assert [(row.target_doc_id, row.relation, row.direction) for row in rows] == [
        ("law", "제재", "in")]


def test_정의조에서_사용조문으로_가는_폭발성_역방향은_차단한다(monkeypatch):
    idx = _index()
    definition_use = _edge("USES_DEFINITION", "law", "definition")
    monkeypatch.setattr(
        relation_navigation.relations, "incident",
        lambda _index, doc, node: ((), (definition_use,))
        if doc == "definition" else ((), ()))

    rows, meta = relation_navigation.neighbors(
        idx, [("definition", 1)], direction="in")

    assert rows == []
    assert meta["rejected_by_policy"] == {"USES_DEFINITION": 1}

