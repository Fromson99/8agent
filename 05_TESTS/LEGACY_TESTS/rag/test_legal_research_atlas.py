from __future__ import annotations

import pytest

from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_research_atlas import (
    PROFILE_MODEL,
    ClosedIdentifierError,
    LegalResearchAtlas,
    NavigationKind,
    compile_instrument_profiles,
    profile_schema,
)


def _index() -> Index:
    current_nodes = [
        {
            "id": 10, "parent": None, "surface": "제1장", "title": "총칙",
            "family": "kr_chapter", "level": 0, "span": [0, 3],
            "coordinate_scope": "body",
        },
        {
            "id": 20, "parent": 10, "surface": "제1조", "title": "정의",
            "family": "kr_article", "level": 1, "span": [1, 3],
            "coordinate_scope": "body",
        },
        {
            "id": 21, "parent": 20, "surface": "①", "title": "",
            "family": "circled", "level": 2, "span": [2, 3],
            "coordinate_scope": "body",
        },
    ]
    old_nodes = [
        {
            "id": 1, "parent": None, "surface": "제1조", "title": "옛 조문",
            "family": "kr_article", "level": 0, "span": [0, 1],
            "coordinate_scope": "body",
        },
    ]
    return Index.from_docs([
        (
            "current-law",
            {"name": "테스트법", "kind": "law", "status": "현행"},
            {
                "nodes": current_nodes,
                "blocks": [
                    {"idx": 0, "text": "제1장 총칙"},
                    {"idx": 1, "text": "제1조(정의) 이 법에서 용어의 뜻은 다음과 같다."},
                    {"idx": 2, "text": "① 테스트란 검증을 말한다."},
                ],
            },
        ),
        (
            "old-law",
            {"name": "테스트법", "kind": "law", "status": "구판"},
            {"nodes": old_nodes, "blocks": [{"idx": 0, "text": "제1조 옛 조문"}]},
        ),
    ])


def test_atlas_uses_current_entry_docs_and_articles_are_navigation_leaves() -> None:
    atlas = LegalResearchAtlas.from_index(_index())
    assert atlas.current_document_ids == ("current-law",)
    assert atlas.instrument("old-law") is None

    root, = atlas.children("current-law", None)
    assert root.kind is NavigationKind.CONTAINER
    article, = atlas.children("current-law", root.node_id)
    assert article.kind is NavigationKind.ARTICLE
    assert article.coordinate == "current-law:20"
    assert atlas.children("current-law", article.node_id) == ()
    assert atlas.is_ancestor("current-law", root.node_id, article.node_id)
    assert not atlas.is_ancestor("current-law", article.node_id, article.node_id)


class _LLM:
    def __init__(self):
        self.calls = []

    def structured(self, kind, system, user, schema, **kwargs):
        self.calls.append({
            "kind": kind, "system": system, "user": user,
            "schema": schema, **kwargs,
        })
        entry = schema["properties"]["profiles"]["items"]["properties"][
            "entry_point_ids"
        ]["items"]["enum"][0]
        return {
            "profiles": [
                {
                    "instrument_id": "current-law",
                    "roles": ["PRIMARY_ACT"],
                    "entry_point_ids": [entry],
                    "definition_point_ids": [],
                    "topic_tags": ["테스트"],
                    "scope_note": "closed menu",
                    "rationale": "route hint",
                },
                {
                    "instrument_id": "forged-law",
                    "roles": ["PRIMARY_ACT"],
                    "entry_point_ids": [],
                    "definition_point_ids": [],
                    "topic_tags": [],
                    "scope_note": "",
                    "rationale": "",
                },
            ]
        }


def test_profile_compiler_pins_haiku_and_rejects_provider_forged_ids() -> None:
    atlas = LegalResearchAtlas.from_index(_index())
    llm = _LLM()
    result = compile_instrument_profiles(llm, atlas, ["current-law"])
    assert llm.calls[0]["model"] == PROFILE_MODEL
    assert result.profiles[0].instrument_id == "current-law"
    assert any(
        rejection.reason == "instrument_not_in_closed_menu"
        for rejection in result.rejections
    )


def test_profile_compiler_can_bind_same_closed_menu_to_onsite_qwen() -> None:
    atlas = LegalResearchAtlas.from_index(_index())
    llm = _LLM()
    result = compile_instrument_profiles(
        llm, atlas, ["current-law"], model="qwen-onsite",
    )
    assert llm.calls[0]["model"] == "qwen-onsite"
    assert result.model == "qwen-onsite"
    assert result.profiles[0].model == "qwen-onsite"


def test_empty_profile_schema_has_no_fake_instrument_or_entry_ids() -> None:
    schema = profile_schema((), {})
    rendered = str(schema)
    assert "__NO_INSTRUMENT__" not in rendered
    assert "__NO_ENTRY_POINT__" not in rendered
    assert schema["properties"]["profiles"]["maxItems"] == 0


def test_caller_cannot_put_unknown_corpus_ids_in_profile_menu() -> None:
    atlas = LegalResearchAtlas.from_index(_index())
    with pytest.raises(ClosedIdentifierError):
        compile_instrument_profiles(_LLM(), atlas, ["forged-law"])
