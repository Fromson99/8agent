from lawrag.core.domain_graph.tier1 import (
    Tier1Assertion,
    Tier1Concept,
    Tier1Registry,
    Tier1Relation,
)
from lawrag.core.rag.assertionfirst import (
    AssertionHit,
    AssertionIndex,
    _choose_page,
    _document_family,
    _route_document_families,
    retrieve,
)
from lawrag.core.rag.index import Index


def _index():
    return Index.from_docs([
        ("d1", {"name": "시험법"}, {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": "제1조", "title": "제출", "span": [0, 1]}],
            "blocks": [{"idx": 0, "text": "회사는 상품을 제출하여야 한다",
                        "kind": "text"}],
        }),
        ("d2", {"name": "다른법"}, {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": "제1조", "title": "보관", "span": [0, 1]}],
            "blocks": [{"idx": 0, "text": "회사는 상품을 보관한다",
                        "kind": "text"}],
        }),
    ])


def _registry():
    concepts = {
        "concept:company": Tier1Concept(
            "concept:company", "회사", "organization_role", "active",
            approved_by="test"),
        "concept:product": Tier1Concept(
            "concept:product", "상품", "artifact", "active",
            approved_by="test"),
        "concept:submit": Tier1Concept(
            "concept:submit", "제출하다", "action", "active",
            approved_by="test"),
        "concept:file": Tier1Concept(
            "concept:file", "신고하다", "action", "active",
            approved_by="test"),
        "concept:store": Tier1Concept(
            "concept:store", "보관하다", "action", "active",
            approved_by="test"),
    }
    assertions = [
        Tier1Assertion(
            "assertion:submit", "active",
            {"ACTOR": ("concept:company",),
             "OBJECT": ("concept:product",),
             "PREDICATE": ("concept:submit",)},
            {"doc_id": "d1", "node": 1}, approved_by="test",
            query_cues=("제출하여야 한다",)),
        Tier1Assertion(
            "assertion:store", "active",
            {"ACTOR": ("concept:company",),
             "OBJECT": ("concept:product",),
             "PREDICATE": ("concept:store",)},
            {"doc_id": "d2", "node": 1}, approved_by="test",
            query_cues=("보관한다",)),
    ]
    relations = [Tier1Relation(
        "relation:file-submit", "IS_A", "concept:submit", "concept:file",
        "active", evidence=({"doc_id": "d1", "node": 1},),
        approved_by="test")]
    return Tier1Registry(concepts=concepts, assertions=assertions,
                         relations=relations)


def test_query_expression_opens_assertion_and_db_roles_without_role_inference():
    hits = AssertionIndex(_registry()).search(
        _index(), "회사가 상품을 제출해야 하나요?")

    hit = next(row for row in hits if row.assertion_id == "assertion:submit")
    assert hit.coordinate == ("d1", 1)
    assert hit.roles == ("ACTOR", "OBJECT", "PREDICATE")
    assert {row["kind"] for row in hit.evidence} >= {
        "concept-exact", "concept-token", "cue-token"}


def test_morphology_matches_inflection_without_embedding():
    hits = AssertionIndex(_registry()).search(_index(), "누가 제출해야 합니까?")

    hit = next(row for row in hits if row.assertion_id == "assertion:submit")
    assert any(row["kind"] == "cue-token" and row["value"] == "제출"
               for row in hit.evidence)


def test_normative_modality_is_visible_without_opening_facet_only():
    index = Index.from_docs([
        ("must", {"name": "현행상법"}, {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": "제1조", "title": "소각의무", "span": [0, 1]}],
            "blocks": [{"idx": 0, "text": "회사는 자기주식을 소각하여야 한다",
                        "kind": "text"}],
        }),
        ("may", {"name": "구상법"}, {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": "제2조", "title": "주식의 소각", "span": [0, 1]}],
            "blocks": [{"idx": 0, "text": "회사는 자기주식을 소각할 수 있다",
                        "kind": "text"}],
        }),
    ])
    concepts = {
        "concept:company": Tier1Concept(
            "concept:company", "회사", "organization_role", "active",
            approved_by="test"),
        "concept:treasury": Tier1Concept(
            "concept:treasury", "자기주식", "artifact", "active",
            approved_by="test"),
        "concept:retire": Tier1Concept(
            "concept:retire", "소각", "action", "active", approved_by="test"),
        "concept:norm.modality.obligation": Tier1Concept(
            "concept:norm.modality.obligation", "의무", "modality", "active",
            aliases=("하여야 한다", "해야 한다"), approved_by="test"),
        "concept:norm.modality.permission": Tier1Concept(
            "concept:norm.modality.permission", "허용", "modality", "active",
            aliases=("할 수 있다",), approved_by="test"),
    }
    shared = {"ACTOR": ("concept:company",),
              "OBJECT": ("concept:treasury",),
              "PREDICATE": ("concept:retire",)}
    registry = Tier1Registry(concepts=concepts, assertions=[
        Tier1Assertion(
            "assertion:must", "active",
            {**shared, "MODALITY": ("concept:norm.modality.obligation",)},
            {"doc_id": "must", "node": 1}, approved_by="test",
            query_cues=("소각",)),
        Tier1Assertion(
            "assertion:may", "active",
            {**shared, "MODALITY": ("concept:norm.modality.permission",)},
            {"doc_id": "may", "node": 1}, approved_by="test",
            query_cues=("소각",)),
    ])

    hits = AssertionIndex(registry).search(index, "자기주식 소각의무는?")

    by_id = {row.assertion_id: row for row in hits}
    assert any(row["kind"] == "facet-match"
               for row in by_id["assertion:must"].evidence)
    assert any(row["kind"] == "facet-conflict"
               for row in by_id["assertion:may"].evidence)
    assert "MODALITY" in by_id["assertion:must"].roles
    assert AssertionIndex(registry).search(index, "의무는?") == []


def test_structure_scope_is_a_hard_constraint():
    hits = AssertionIndex(_registry()).search(
        _index(), "회사는 상품을 어떻게 처리합니까?",
        scope=frozenset({("d2", 1)}),
    )

    assert hits
    assert {row.coordinate for row in hits} == {("d2", 1)}


def test_active_is_a_relation_opens_grounded_assertion_one_hop():
    hits = AssertionIndex(_registry()).search(_index(), "신고해야 하나요?")

    hit = next(row for row in hits if row.assertion_id == "assertion:submit")
    assert any(row["kind"] == "concept-relation"
               and row["concept_id"] == "concept:submit"
               for row in hit.evidence)


class _PickFirstLLM:
    def __init__(self):
        self.calls = []

    def structured(self, kind, _system, user, schema, **_kwargs):
        ids = schema["properties"]["picks"]["items"]["enum"]
        assert len(ids) <= 32
        self.calls.append((kind, user, tuple(ids)))
        return {"picks": ids[:1], "reason": "첫 구조 가지"}


def test_navigation_uses_closed_bounded_pages_and_returns_subtree():
    llm = _PickFirstLLM()

    sections, meta = retrieve(
        _index(), "시험법에서 회사가 상품을 제출해야 하나요?",
        _registry(), llm=llm,
    )

    assert [(row.doc_id, row.node, row.kind) for row in sections] == [
        ("d1", 1, "Assertion트리선택")]
    assert "회사는 상품을 제출하여야 한다" in sections[0].text
    assert meta["strategy"] == "assertion_first_structural_navigation"
    assert meta["embedding"] is False and meta["raw_law_bm25"] is False
    assert meta["tree"]["page_size"] == 32
    assert llm.calls == []  # 선택 예산 안의 단일 가지는 모델 없이 통과


def test_closed_navigation_call_never_exposes_more_than_page_limit():
    llm = _PickFirstLLM()
    cards = [{"key": str(pos), "label": f"가지 {pos}", "detail": {},
              "signals": [], "members": [], "strength": 1}
             for pos in range(40)]

    picked = _choose_page(
        llm, "질문", "test", cards, keep=1, parent="", audit=[])

    assert len(picked) == 1
    assert len(llm.calls[0][2]) == 32


def test_explicit_article_is_pinned_without_llm_reinterpretation():
    class NoCallLLM:
        def structured(self, *_args, **_kwargs):
            raise AssertionError("확정 조문을 LLM이 다시 선택함")

    sections, meta = retrieve(
        _index(), "시험법 제1조에서 회사의 의무는?",
        _registry(), llm=NoCallLLM(),
    )

    assert [(row.doc_id, row.node) for row in sections] == [("d1", 1)]
    assert meta["structure"]["constraint"] == "resolved-structure"
    assert meta["navigation"] == []


def test_law_and_subordinate_statute_share_a_document_family():
    index = Index.from_docs([
        ("law", {"name": "시험법", "folder": "법령·규정"},
         {"nodes": [], "blocks": []}),
        ("decree", {"name": "시험법 시행령", "folder": "법령·규정"},
         {"nodes": [], "blocks": []}),
    ])

    assert _document_family(index.docs["law"])[0] == \
        _document_family(index.docs["decree"])[0]


def test_family_router_sums_member_document_evidence_before_topk():
    index = Index.from_docs([
        (doc_id, {"name": name, "folder": "법령·규정"}, {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": "제1조", "title": "", "span": [0, 1]}],
            "blocks": [{"idx": 0, "text": name, "kind": "text"}],
        }) for doc_id, name in (
            ("law", "시험법"), ("decree", "시험법 시행령"),
            ("other", "다른법"))
    ])
    evidence = ({"kind": "cue-token", "value": "제출", "strength": 3},)
    hits = [AssertionHit(f"a:{doc_id}", doc_id, 1, ("PREDICATE",), (),
                         evidence, 3)
            for doc_id in ("law", "decree", "other")]

    routed, audit = _route_document_families(index, hits, limit=1)

    assert {row.doc_id for row in routed} == {"law", "decree"}
    assert audit["selected_document_count"] == 2
