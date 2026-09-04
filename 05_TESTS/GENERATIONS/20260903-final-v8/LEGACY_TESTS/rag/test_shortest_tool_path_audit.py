from scripts import rag_shortest_tool_path_audit as audit


def test_shortest_tree_and_reconstruct():
    graph = {
        ("d", 1): [(("d", 2), {"operator": "RELATION", "relation": "R"})],
        ("d", 2): [(("d", 3), {"operator": "RELATION", "relation": "R"})],
    }
    distance, predecessor, order = audit.shortest_tree(graph, [("d", 1)])
    assert distance[("d", 3)] == 2
    assert order == [("d", 1), ("d", 2), ("d", 3)]
    path = audit.reconstruct(predecessor, ("d", 3))
    assert [row["target"] for row in path] == [("d", 2), ("d", 3)]


def test_merge_adjacency_preserves_operator_spaces():
    relation = {("d", 1): [(("d", 2), {"operator": "RELATION"})]}
    structure = {("d", 1): [(("d", 0), {"operator": "ADJACENT_ARTICLE"})]}
    merged = audit.merge_adjacency(relation, structure)
    assert {row[1]["operator"] for row in merged[("d", 1)]} == {
        "RELATION", "ADJACENT_ARTICLE"}


def test_better_prefers_shorter_then_fewer_searches():
    short = [{"operator": "RELATION"}]
    long = [{"operator": "RELATION"}, {"operator": "RELATION"}]
    assert audit._better(long, short) is short
    assert audit._better(short, None) is short
