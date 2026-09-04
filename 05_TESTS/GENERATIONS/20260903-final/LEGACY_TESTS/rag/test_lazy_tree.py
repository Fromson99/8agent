from lawrag.core.domain_graph.spanparts import QuerySpan, StructureAnchors
from lawrag.core.domain_graph.tier1 import (
    Tier1Assertion,
    Tier1Concept,
    Tier1Registry,
)
from lawrag.core.rag.combinations import (
    Candidate,
    CandidateGroup,
    TreeNode,
    _choose,
    _rebind_selected_documents,
    _structure_scope,
    _tree_options,
    _vector_candidates,
    build_lazy_tree,
    retrieve,
)
from lawrag.core.rag.index import Index


def _candidate(cid, group, role, coordinates, score=1.0):
    return Candidate(
        id=cid, group=group, role=role, surface=cid, label=cid,
        via="test", coordinates=frozenset(coordinates), score=score,
    )


def _group(pos, *candidates):
    return CandidateGroup(
        id=f"g{pos}", start=pos, end=pos + 1, surface=f"s{pos}",
        roles=tuple(sorted({row.role for row in candidates})),
        candidates=tuple(candidates),
    )


def _index():
    return Index.from_docs([
        ("d1", {"name": "시험법"}, {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": "제1조", "title": "정답", "span": [0, 1]}],
            "blocks": [{"idx": 0, "text": "회사는 제출하여야 한다", "kind": "text"}],
        }),
        ("d2", {"name": "다른법"}, {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": "제1조", "title": "오답", "span": [0, 1]}],
            "blocks": [{"idx": 0, "text": "상품을 보관한다", "kind": "text"}],
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
    }
    assertions = [
        Tier1Assertion(
            "assertion:one", "active",
            {"ACTOR": ("concept:company",),
             "PREDICATE": ("concept:submit",)},
            {"doc_id": "d1", "node": 1}, approved_by="test"),
        Tier1Assertion(
            "assertion:two", "active",
            {"OBJECT": ("concept:product",),
             "PREDICATE": ("concept:submit",)},
            {"doc_id": "d2", "node": 1}, approved_by="test"),
    ]
    return Tier1Registry(concepts=concepts, assertions=assertions)


def test_lazy_tree_generates_only_nonempty_children_not_factorial_permutations():
    groups = [_group(pos, _candidate(f"c{pos}", f"g{pos}", "ACTOR", {("d", 1)}))
              for pos in range(4)]

    nodes, counts, _ordered = build_lazy_tree(groups)

    assert counts.theoretical_assignments == 2 ** 4
    assert len(nodes) == 2 ** 4 - 1
    assert max(len(node.picks) for node in nodes) == 4
    assert all(len({pick.group for pick in node.picks}) == len(node.picks)
               for node in nodes)


def test_same_span_is_or_and_different_spans_intersect_coordinates():
    groups = [
        _group(1,
               _candidate("a1", "g1", "ACTOR", {("d", 1)}),
               _candidate("a2", "g1", "ACTOR", {("d", 2)})),
        _group(2, _candidate("b1", "g2", "OBJECT", {("d", 2)})),
    ]

    nodes, counts, _ordered = build_lazy_tree(groups)

    assert not any({pick.id for pick in node.picks} == {"a1", "b1"}
                   for node in nodes)
    joined = next(node for node in nodes
                  if {pick.id for pick in node.picks} == {"a2", "b1"})
    assert joined.coordinates == frozenset({("d", 2)})
    assert counts.zero_intersections == 1


def test_structure_scope_is_the_root_constraint_before_tree_expansion():
    broad = _candidate("actor", "g1", "ACTOR", {("d1", 1), ("d2", 1)})

    nodes, _counts, _ordered = build_lazy_tree(
        [_group(1, broad)], scope_coordinates=frozenset({("d1", 1)}))

    assert {node.coordinates for node in nodes} == {frozenset({("d1", 1)})}


def test_resolved_heading_scope_contains_its_descendants():
    index = Index.from_docs([("d", {"name": "시험법"}, {
        "nodes": [
            {"id": 1, "parent": None, "level": 1, "surface": "제1조",
             "title": "범위", "span": [0, 2]},
            {"id": 2, "parent": 1, "level": 2, "surface": "제1항",
             "title": "", "span": [1, 2]},
        ],
        "blocks": [{"idx": 0, "text": "제1조", "kind": "text"},
                   {"idx": 1, "text": "제1항 본문", "kind": "text"}],
    })])
    anchors = StructureAnchors(
        doc_ids=("d",), documents=("시험법",), locators=("제1조",),
        source_coordinates=(("d", 1),), unresolved_locators=())

    coordinates, kind = _structure_scope(index, anchors)

    assert kind == "resolved-structure"
    assert coordinates == frozenset({("d", 1), ("d", 2)})


def test_most_selective_role_group_expands_first():
    broad = _group(1, _candidate("broad", "g1", "ACTOR",
                                 {("d", 1), ("d", 2), ("d", 3)}))
    narrow = _group(2, _candidate("narrow", "g2", "OBJECT", {("d", 2)}))

    _nodes, counts, ordered = build_lazy_tree([broad, narrow])

    assert [group.id for group in ordered] == ["g2", "g1"]
    assert counts.depths[0]["group"] == "g2"


def test_role_vector_never_returns_a_concept_from_another_role():
    class Lexicon:
        def neighbors_many_filtered(self, _words, allowed_terms, **_kwargs):
            assert "회사" in allowed_terms
            assert "상품" not in allowed_terms
            return [[{"term": "회사", "cos": 0.91},
                     {"term": "상품", "cos": 0.99}]]

        def neighbors_many(self, _words, **_kwargs):
            raise AssertionError("운영 역할 제한 Vector를 우회함")

    registry = _registry()
    span = QuerySpan("회사", 0, 2, "actor")
    rows = _vector_candidates(
        _index(), registry, Lexicon(), span, "g1",
        {"concept:company": {("d1", 1)}, "concept:product": {("d2", 1)}},
        {"회사": [("concept:company", "회사")],
         "상품": [("concept:product", "상품")]},
        {"concept:company": {"ACTOR"}, "concept:product": {"OBJECT"}},
        scope=None,
    )

    assert [(row.label, row.role) for row in rows] == [("회사", "ACTOR")]


def test_tree_options_do_not_add_keyword_or_unrelated_global_coordinates(monkeypatch):
    from lawrag.core.rag import vector

    monkeypatch.setattr(
        vector, "search",
        lambda _q, **kwargs: [("d1", 1, 0.9)]
        if ("d1", 1) in kwargs["coordinates"] else [])
    pick = _candidate("actor", "g1", "ACTOR", {("d1", 1)})
    node = TreeNode(1, 0, 1, (pick,), frozenset({("d1", 1)}))

    rows = _tree_options(_index(), "회사는?", [node])

    assert {(row["doc_id"], row["node"]) for row in rows} == {("d1", 1)}
    assert {channel for row in rows for channel in row["channels"]} == {"lazy_tree"}


def test_confirmed_article_is_a_guaranteed_structure_option_not_vector_shortlist(
        monkeypatch):
    from lawrag.core.rag import vector

    monkeypatch.setattr(
        vector, "search",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("확정 조문을 다시 Vector로 줄임")),
    )

    rows = _tree_options(
        _index(), "시험법 제1조는?", [],
        scope_coordinates=frozenset({("d1", 1)}),
        structural_roots=frozenset({("d1", 1)}),
    )

    assert [(row["doc_id"], row["node"], row["category"]) for row in rows] == [
        ("d1", 1, "structure")]


def test_selector_receives_tree_and_keeps_multiple_ranges():
    class LLM:
        def structured(self, kind, _system, user, schema, **_kwargs):
            assert kind == "rag.lazy_tree.choose"
            assert "[생존 근거 트리]" in user
            assert "maxItems" not in schema["properties"]["picks"]
            return {"picks": ["R1", "R2"], "reason": "요건과 예외"}

    options = [{"id": "R1"}, {"id": "R2"}]
    choice = _choose(LLM(), "요건과 예외는?", options, max_picks=4,
                     tree="시험법\n  R1 제1조\n  R2 제2조")

    assert choice["picks"] == ["R1", "R2"]
    assert choice["overflow"] == 0


def test_selected_document_rebinds_previously_unresolved_locator():
    index = Index.from_docs([("decree", {"name": "긴 정식 시행령"}, {
        "nodes": [
            {"id": 1, "parent": None, "level": 1, "surface": "제49조",
             "title": "시가의 원칙", "span": [0, 2]},
            {"id": 2, "parent": 1, "level": 2, "surface": "제1항",
             "title": "", "span": [1, 2]},
        ],
        "blocks": [
            {"idx": 0, "text": "제49조", "kind": "text"},
            {"idx": 1, "text": "제1항 본문", "kind": "text"},
        ],
    })])
    unresolved = StructureAnchors(
        locators=("제49조제1항",), unresolved_locators=("제49조제1항",))

    rebound = _rebind_selected_documents(
        index, "약칭 시행령 제49조제1항은?", unresolved, {"decree"})

    assert rebound.doc_ids == ("decree",)
    assert rebound.source_coordinates == (("decree", 2),)
    assert rebound.unresolved_locators == ()


def test_retrieve_lets_llm_choose_a_surviving_tree_branch_and_returns_subtree():
    class Lexicon:
        def neighbors_many(self, _words, **_kwargs):
            return [[{"term": "회사", "cos": 0.95}]]

    class LLM:
        def __init__(self):
            self.tree = ""

        def structured(self, kind, _system, user, _schema, **_kwargs):
            if kind == "rag.oql.spans":
                return {"spans": [
                    {"span": "시험법", "start": 0, "end": 3,
                     "role": "document", "reading_ids": []},
                    {"span": "회사", "start": 6, "end": 8,
                     "role": "actor", "reading_ids": []},
                ]}
            if kind == "rag.lazy_tree.choose":
                self.tree = user
                return {"picks": ["R1"], "reason": "회사 의무 조문"}
            raise AssertionError(kind)

    index = _index().scoped({"d1"}, name="test")
    llm = LLM()

    sections, meta = retrieve(
        index, "시험법에서 회사는?", _registry(), llm=llm, lexicon=Lexicon())

    assert meta["strategy"] == "structure_constrained_lazy_tree"
    assert meta["structure"]["constraint"] == "resolved-document"
    assert meta["tree_counts"]["surviving"] >= 1
    assert "시험법" in llm.tree and "R1" in llm.tree
    assert [(section.kind, section.doc_id, section.node) for section in sections] == [
        ("지연트리선택", "d1", 1)]
    assert "회사는 제출하여야 한다" in sections[0].text
