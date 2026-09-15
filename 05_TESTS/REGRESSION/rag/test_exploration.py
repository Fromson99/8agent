from lawrag.core.rag import exploration
from lawrag.core.rag.answer import Section, _context_text
from lawrag.core.rag.index import Index


def _index():
    idx = Index.from_docs([
        ("commercial", {"name": "상법"}, {
            "nodes": [
                {"id": 433, "parent": None, "level": 1,
                 "surface": "제433조", "title": "정관변경의 방법", "span": [0, 3]},
                {"id": 4331, "parent": 433, "level": 2,
                 "surface": "제1항", "title": "", "span": [1, 2]},
                {"id": 4332, "parent": 433, "level": 2,
                 "surface": "제2항", "title": "", "span": [2, 3]},
                {"id": 434, "parent": None, "level": 1,
                 "surface": "제434조", "title": "정관변경의 특별결의", "span": [3, 4]},
            ],
            "blocks": [
                {"idx": 0, "text": "제433조 정관변경의 방법", "kind": "text"},
                {"idx": 1, "text": "① 정관을 변경하려면 주주총회의 결의가 있어야 한다.",
                 "kind": "text"},
                {"idx": 2, "text": "② 변경안을 공고한다.", "kind": "text"},
                {"idx": 3, "text": "제434조 특별결의의 요건을 정한다.", "kind": "text"},
            ],
        }),
        ("model", {"name": "표준정관"}, {
            "nodes": [
                {"id": 27, "parent": None, "level": 1,
                 "surface": "제27조", "title": "주주총회의 결의방법", "span": [0, 1]},
            ],
            "blocks": [{"idx": 0, "text": "표준정관의 보통결의", "kind": "text"}],
        }),
    ])
    idx._refs = {"commercial": [
        {"src": 434, "dst": 4332, "surface": "제433조제2항", "block": 3,
         "rel": "특별규정"},
    ], "model": []}
    idx._cross = ([], [])
    return idx


def _option(doc_id, node, oid):
    return {
        "id": oid, "doc_id": doc_id, "node": node,
        "path": "", "channels": ["concept"], "category": "combination",
        "matched": [{"object_id": oid, "surface": "정관 변경",
                     "kind": "concept", "label": "정관 변경", "via": "test"}],
    }


def test_paragraph_coordinates_remain_children_under_the_same_article():
    idx = _index()

    menu = exploration.build(idx, [
        _option("commercial", 4331, "O1"),
        _option("commercial", 4332, "O2"),
        _option("commercial", 434, "O3"),
    ])

    assert [(row.id, row.node) for row in menu.ranges] == [
        ("R1", 4331), ("R2", 4332), ("R3", 434),
    ]
    assert [c["node"] for c in menu.ranges[0].candidate_coordinates] == [4331]


def test_tree_shows_document_article_heading_children_and_real_relation():
    idx = _index()
    menu = exploration.build(idx, [
        _option("commercial", 4332, "O1"),
        _option("commercial", 434, "O2"),
        _option("model", 27, "O3"),
    ])

    tree = exploration.prompt_tree(menu)

    assert "문서 commercial | 상법" in tree
    assert "제433조 정관변경의 방법" in tree
    assert "R1 [선택 가능; 하위 전체 포함] 제2항" in tree
    assert "② 변경안을 공고한다" in tree
    assert "E1: R2 --특별규정 '제433조제2항'--> R1" in tree
    # 표준정관은 별도 문서 가지다. 실제 간선이 없으므로 상법과 가짜로 묶이지 않는다.
    assert "문서 model | 표준정관" in tree
    assert not any(edge["to"] == "R3" or edge["from"] == "R3"
                   for edge in menu.edges)


def test_selected_article_text_contains_heading_and_entire_subtree_without_slice():
    idx = _index()
    view = idx.docs["commercial"]

    text = exploration.subtree_text(view, 433, cap=None)

    assert text.startswith("▸ 제433조 정관변경의 방법")
    assert "① 정관을 변경하려면" in text
    assert "② 변경안을 공고한다" in text


def test_parent_article_pick_makes_child_paragraph_pick_redundant():
    idx = _index()
    menu = exploration.build(idx, [
        _option("commercial", 433, "O1"),
        _option("commercial", 4332, "O2"),
    ])

    kept, removed = exploration.remove_descendant_picks(
        menu.ranges, ["R1", "R2"])

    assert kept == ["R1"]
    assert removed == ["R2"]


def test_incoming_reference_adds_connected_special_rule_before_selection():
    idx = _index()
    base = [_option("commercial", 4332, "O1")]

    connected = exploration.connected_options(idx, base)
    menu = exploration.build(idx, [*connected, *base])

    assert [(row["doc_id"], row["node"]) for row in connected] == [
        ("commercial", 434),
    ]
    assert any(edge["from"] == "R1" and edge["to"] == "R2"
               for edge in menu.edges)
    selected = exploration.selected_edges(menu, ["R1"])
    assert [edge["id"] for edge in selected] == ["E1"]


def test_tree_shows_concept_role_and_only_the_matching_body_context():
    idx = _index()
    option = _option("commercial", 4331, "O1")
    option["matched"] = [{
        "object_id": "actor", "surface": "주주총회",
        "kind": "concept", "label": "주주총회 [ACTOR]", "via": "test",
    }]

    menu = exploration.build(idx, [option])
    tree = exploration.prompt_tree(menu)

    assert "매칭: [ACTOR] 주주총회" in tree
    assert "원문 구간:" in tree
    assert "정관을 변경하려면 주주총회의 결의" in tree


def test_selected_edge_is_carried_into_context_and_static_citation():
    edge = {"id": "E1", "from": "R1", "to": "R2",
            "relation": "특별규정", "surface": "제433조제1항"}
    section = Section(
        n=1, doc_id="commercial", doc="상법", node=434,
        path="제434조 정관변경의 특별결의", page=1,
        kind="조합선택", matched="relation", text="특별결의 본문", edges=[edge],
    )

    assert section.cite()["edges"] == [edge]
    context = _context_text([section])
    assert "[함께 선택된 간선]" in context
    assert "E1: R1 --특별규정 '제433조제1항'--> R2" in context
