from lawrag.core.structure.viewer import annotate_coordinate_scopes


def test_article_coordinate_scopes_separate_body_addendum_annex_and_repeats():
    nodes = [
        {"id": 0, "parent": None, "family": "kr_article", "surface": "제1조", "block": 0},
        {"id": 1, "parent": None, "family": "buchik", "surface": "부칙", "block": 1},
        {"id": 2, "parent": 1, "family": "kr_article", "surface": "제1조", "block": 2},
        {"id": 3, "parent": None, "family": "annex", "surface": "별표 1", "block": 3},
        {"id": 4, "parent": 3, "family": "kr_article", "surface": "제1조", "block": 4},
        {"id": 5, "parent": None, "family": "kr_article", "surface": "제1조", "block": 5},
    ]
    annotate_coordinate_scopes(nodes, "law")
    assert [nodes[i]["coordinate_scope"] for i in (0, 2, 4, 5)] == [
        "body", "addendum", "annex", "repeated"]
    keys = [nodes[i]["coordinate_key"] for i in (0, 2, 4, 5)]
    assert len(keys) == len(set(keys))
    assert nodes[0]["coordinate_key"] == "body:제1조"


def test_non_normative_duplicate_numbers_are_all_repeated():
    nodes = [
        {"id": 0, "parent": None, "family": "kr_article", "surface": "제1조", "block": 0},
        {"id": 1, "parent": None, "family": "kr_article", "surface": "제1조", "block": 1},
    ]
    annotate_coordinate_scopes(nodes, "klca-model")
    assert {node["coordinate_scope"] for node in nodes} == {"repeated"}


def test_article_children_receive_full_common_coordinates_and_keys():
    nodes = [
        {"id": 0, "parent": None, "family": "kr_article", "surface": "제15조",
         "ordinal": [15], "block": 0},
        {"id": 1, "parent": 0, "family": "circled", "surface": "②",
         "ordinal": [2], "block": 1},
        {"id": 2, "parent": 1, "family": "dot_number:1", "surface": "1.",
         "ordinal": [1], "block": 2},
        {"id": 3, "parent": 2, "family": "hangul_dot", "surface": "나.",
         "ordinal": [2], "block": 3},
    ]

    annotate_coordinate_scopes(nodes, "law")

    assert [node["coordinate_key"] for node in nodes] == [
        "body:제15조",
        "body:제15조제2항",
        "body:제15조제2항제1호",
        "body:제15조제2항제1호나목",
    ]
    assert nodes[-1]["legal_coordinate"] == {
        "unit": "조", "n": 15, "sub": None, "dash": None,
        "chain": [
            {"unit": "항", "n": 2, "sub": None},
            {"unit": "호", "n": 1, "sub": None},
            {"unit": "목", "n": 2, "sub": None},
        ],
        "surface": "제15조제2항제1호나목",
    }


def test_orphan_subunit_is_not_promoted_to_complete_coordinate():
    nodes = [{"id": 0, "parent": None, "family": "circled", "surface": "①",
              "ordinal": [1], "block": 0}]

    annotate_coordinate_scopes(nodes, "law")

    assert "coordinate_key" not in nodes[0]
    assert nodes[0]["coordinate_component"]["surface"] == "제1항"
