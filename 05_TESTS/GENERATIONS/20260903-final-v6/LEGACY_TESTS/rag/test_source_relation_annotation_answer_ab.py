from lawrag.core.rag.answer import Section
from scripts.rag_source_relation_annotation_answer_ab import (
    annotate_sections,
    has_structural_relation,
)


def _section():
    return Section(n=1, doc_id="d", doc="A법", node=1, path="제1조",
                   page=None, kind="본문", matched="", text="대표자는 신고한다.")


def _row():
    return {
        "inventory": [
            {"evidence_id": "E1", "document": "A법", "path": "제1조"},
            {"evidence_id": "E2", "document": "A법 시행령", "path": "제2조"},
        ],
        "published": [
            {"relation_id": "R1", "relation_type": "GOVERNS_ACTOR",
             "source_id": "E1", "target_id": "", "target_value": "대표자"},
            {"relation_id": "R2", "relation_type": "IMPLEMENTS",
             "source_id": "E1", "target_id": "E2", "target_value": "제2조"},
        ],
    }


def test_structural_annotation_excludes_market_and_actor_relations():
    sections, attached = annotate_sections([_section()], _row(), structural_only=True)
    assert attached == 1
    assert sections[0].edges[0]["relation"] == "IMPLEMENTS"


def test_all_annotation_attaches_both_relation_types():
    sections, attached = annotate_sections([_section()], _row(), structural_only=False)
    assert attached == 2
    assert {edge["relation"] for edge in sections[0].edges} == {
        "GOVERNS_ACTOR", "IMPLEMENTS"}


def test_structural_case_filter_requires_a_structural_relation():
    assert has_structural_relation(_row())
    assert not has_structural_relation({
        "published": [{"relation_type": "GOVERNS_ACTOR"}],
    })


def test_structural_allowlist_can_exclude_definition_relations():
    row = _row()
    row["published"].append({
        "relation_id": "R3", "relation_type": "DEFINED_BY",
        "source_id": "E1", "target_id": "E2", "defined_term": "대표자",
    })
    sections, attached = annotate_sections(
        [_section()], row, structural_only=True,
        structural_types=frozenset({"EXCEPTION_TO", "IMPLEMENTS"}),
    )
    assert attached == 1
    assert sections[0].edges[0]["relation"] == "IMPLEMENTS"
