from __future__ import annotations

from lawrag.core.rag.experiments import inline_definition_cards as cards


class View:
    by_id = {
        1: {"parent": None},
        2: {"parent": 1},
        3: {"parent": 2},
        9: {"parent": None},
    }


def test_definition_scope_requires_selected_branch():
    view = View()
    assert cards._in_scope(view, {"scope": "doc", "scope_root": None}, 9)
    assert cards._in_scope(view, {"scope": "sub", "scope_root": 2}, 3)
    assert not cards._in_scope(view, {"scope": "sub", "scope_root": 2}, 9)


def test_render_places_exact_definition_under_provision():
    rendered = cards.render([{
        "term": "전문투자자", "path": "제2조제15호", "scope": "doc",
        "hypernyms": ["투자자"], "hyponyms": ["국가", "한국은행"],
        "definition": '"전문투자자"란 법 제9조제5항에 따른 자를 말한다.',
    }])

    assert rendered.startswith("\n\n[이 조문에서 실제 사용된 같은 문서의 정의]")
    assert "용어: 전문투자자" in rendered
    assert "상위개념: 투자자" in rendered
    assert "포함·하위개념: 국가, 한국은행" in rendered
    assert '"전문투자자"란' in rendered


def test_render_omits_empty_definition_block():
    assert cards.render([]) == ""


def test_matching_contract_excludes_inline_alias_outside_definition_article(monkeypatch):
    class IndexView:
        doc_id = "doc"
        name = "규정"
        by_id = {1: {"parent": None}, 2: {"parent": None}, 3: {"parent": None}}

        def path(self, node):
            return f"제{node}조"

    index = type("Index", (), {"docs": {"doc": IndexView()}})()
    monkeypatch.setattr(cards.legal_coordinates, "subtree_text",
                        lambda _view, node, cap=None: "전문투자자" if node == 1 else "정의")
    monkeypatch.setattr(cards.definitions, "defs", lambda _view: [{
        "term": "전문투자자", "node": 3, "block": 3, "kind": "별칭",
        "scope": "doc", "scope_root": None,
    }])
    monkeypatch.setattr(cards.definitions, "is_definition_node",
                        lambda _view, node: node == 2)
    monkeypatch.setattr(cards.taxonomy, "current", lambda *_args, **_kwargs: type(
        "Taxonomy", (), {"hypernyms": lambda *_a, **_k: [],
                         "hyponyms": lambda *_a, **_k: []})())

    assert cards.matching_definitions(index, "doc", 1) == []


def test_matching_contract_keeps_only_used_in_scope_definition_article_terms(monkeypatch):
    class IndexView:
        name = "규정"
        by_id = {
            1: {"parent": None}, 2: {"parent": None}, 3: {"parent": 1},
            4: {"parent": None}, 5: {"parent": None},
        }

        def path(self, node):
            return f"제{node}조"

    index = type("Index", (), {"docs": {"doc": IndexView()}})()
    texts = {1: "이 조에서 전문투자자는 신고하여야 한다.", 3: "전문투자자 정의",
             4: "미사용용어 정의", 5: "전문투자자 다른 정의"}
    monkeypatch.setattr(cards.legal_coordinates, "subtree_text",
                        lambda _view, node, cap=None: texts[node])
    monkeypatch.setattr(cards.definitions, "defs", lambda _view: [
        {"term": "전문투자자", "node": 3, "block": 3, "kind": "definition",
         "scope": "sub", "scope_root": 1},
        {"term": "미사용용어", "node": 4, "block": 4, "kind": "definition",
         "scope": "doc", "scope_root": None},
        {"term": "전문투자자", "node": 5, "block": 5, "kind": "definition",
         "scope": "sub", "scope_root": 5},
    ])
    monkeypatch.setattr(cards.definitions, "is_definition_node",
                        lambda _view, node: node in {3, 4, 5})
    monkeypatch.setattr(cards.taxonomy, "current", lambda *_args, **_kwargs: type(
        "Taxonomy", (), {"hypernyms": lambda *_a, **_k: [],
                         "hyponyms": lambda *_a, **_k: []})())

    rows = cards.matching_definitions(index, "doc", 1)

    assert [(row["term"], row["node"]) for row in rows] == [("전문투자자", 3)]
