import json

from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.rag import landings, term_proposals, vector
from lawrag.core.rag.index import Index


def _registry(tmp_path, *, nodes=1):
    concepts = [
        {"id": "actor", "label": "금융투자업자", "type": "organization_role",
         "status": "active", "approved_by": "tester"},
        {"id": "act", "label": "배상하다", "type": "action",
         "status": "active", "approved_by": "tester"},
    ]
    assertions = [{
        "id": f"assertion-{node}", "status": "active", "approved_by": "tester",
        "roles": {"ACTOR": "actor", "PREDICATE": "act"},
        "source": {"doc_id": "d1", "node": node},
    } for node in range(1, nodes + 1)]
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps({"schema_version": 1, "concepts": concepts,
                                "relations": [], "assertions": assertions},
                               ensure_ascii=False), encoding="utf-8")
    return Tier1Registry.load(path), path


def _doc(doc_id, name, *, nodes=1):
    headings, blocks = [], []
    for pos in range(1, nodes + 1):
        headings.append({
            "id": pos, "parent": None, "level": 0, "family": "kr_article",
            "surface": f"제{pos}조", "title": f"책임 {pos}", "ordinal": [pos],
            "page": pos, "block": pos - 1, "span": [pos - 1, pos],
        })
        blocks.append({"idx": pos - 1, "page": pos, "node": pos,
                       "kind": "text", "text": f"금융투자업자는 손해를 배상한다 {pos}."})
    return doc_id, {"name": name}, {"nodes": headings, "blocks": blocks}


class ExactLLM:
    model = "fake"

    def __init__(self, question):
        self.question = question
        self.calls = []

    def structured(self, kind, _system, _user, _schema, **_kwargs):
        self.calls.append(kind)
        if kind == "rag.oql.spans":
            values = [("시험법", "document"), ("제1조", "locator"),
                      ("금융투자업자", "actor")]
            return {"spans": [{"span": text, "start": self.question.index(text),
                                "end": self.question.index(text) + len(text),
                                "role": role} for text, role in values]}
        raise AssertionError(f"정확 착지인데 추가 LLM 호출: {kind}")


def test_document_heading_actor_intersection_lands_without_vector(tmp_path, monkeypatch):
    registry, _ = _registry(tmp_path)
    index = Index.from_docs([_doc("d1", "시험법")])
    question = "시험법 제1조에서 금융투자업자는 배상하나?"
    llm = ExactLLM(question)

    def unexpected_vector(*_args, **_kwargs):
        raise AssertionError("교집합 1건에는 Vector를 호출하면 안 됨")

    monkeypatch.setattr(vector, "search", unexpected_vector)
    sections, meta = landings.retrieve(
        index, question, registry, llm=llm, lexicon=False,
        propose_terms=False)

    assert [(section.doc_id, section.node) for section in sections] == [("d1", 1)]
    assert meta["candidate_count"] == 1
    assert meta["pruning"] == "direct-all"
    assert [row["after"] for row in meta["intersection"]] == [1]
    assert llm.calls == ["rag.oql.spans"]


class WideLLM:
    model = "fake"

    def __init__(self, question):
        self.question = question

    def structured(self, kind, _system, _user, _schema, **_kwargs):
        if kind == "rag.oql.spans":
            values = [("시험법", "document"), ("금융투자업자", "actor")]
            return {"spans": [{"span": text, "start": self.question.index(text),
                                "end": self.question.index(text) + len(text),
                                "role": role} for text, role in values]}
        if kind == "rag.landing.sections":
            return {"picks": ["S2"]}
        raise AssertionError(kind)


def test_large_intersection_vectors_only_inside_candidates_then_llm_picks(
        tmp_path, monkeypatch):
    registry, _ = _registry(tmp_path, nodes=6)
    index = Index.from_docs([_doc("d1", "시험법", nodes=6)])
    question = "시험법에서 금융투자업자의 배상 책임은?"
    seen = {}

    def fake_vector(_query, **kwargs):
        seen.update(kwargs)
        return [("d1", 6, .9), ("d1", 5, .8), ("d1", 4, .7)]

    monkeypatch.setattr(vector, "search", fake_vector)
    sections, meta = landings.retrieve(
        index, question, registry, llm=WideLLM(question), lexicon=False,
        propose_terms=False)

    assert seen["coordinates"] == frozenset(("d1", node) for node in range(1, 7))
    assert [(section.doc_id, section.node) for section in sections] == [("d1", 5)]
    assert meta["candidate_count"] == 6
    assert meta["pruning"] == "vector+llm"


class AliasLLM:
    model = "fake"

    def __init__(self, question):
        self.question = question

    def structured(self, kind, _system, _user, _schema, **_kwargs):
        if kind == "rag.oql.spans":
            values = [("금투법", "document"), ("제1조", "locator"),
                      ("금융투자업자", "actor")]
            return {"spans": [{"span": text, "start": self.question.index(text),
                                "end": self.question.index(text) + len(text),
                                "role": role} for text, role in values]}
        if kind == "rag.landing.documents":
            return {"picks": [{"part_index": 1, "candidate_id": "document:d1"}]}
        raise AssertionError(kind)


def test_unknown_document_expression_is_proposed_then_human_approval_publishes_alias(
        tmp_path, monkeypatch):
    registry, canonical = _registry(tmp_path)
    index = Index.from_docs([
        _doc("d1", "자본시장과 금융투자업에 관한 법률"),
        _doc("d2", "상법"),
    ])
    proposal_path = tmp_path / "term_proposals.json"
    alias_path = tmp_path / "aliases.json"
    alias_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("RAG_TERM_PROPOSALS", str(proposal_path))
    monkeypatch.setenv("RAG_ALIASES_STORE", str(alias_path))
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path / "rag"))
    question = "금투법 제1조에서 금융투자업자는 배상하나?"

    sections, meta = landings.retrieve(
        index, question, registry, llm=AliasLLM(question), lexicon=False)

    assert [(section.doc_id, section.node) for section in sections] == [("d1", 1)]
    assert meta["structure"]["doc_ids"] == ["d1"]
    pending = term_proposals.queue("pending")
    assert len(pending) == 1
    assert pending[0]["surface"] == "금투법"
    assert json.loads(alias_path.read_text(encoding="utf-8")) == {}

    term_proposals.resolve(pending[0]["id"], "승인", reviewer="tester")
    assert json.loads(alias_path.read_text(encoding="utf-8"))["금투법"] == \
        "자본시장과 금융투자업에 관한 법률"
    assert term_proposals.queue("pending") == []


class ConceptAliasLLM:
    model = "fake"

    def __init__(self, question):
        self.question = question

    def structured(self, kind, _system, _user, _schema, **_kwargs):
        if kind == "rag.oql.spans":
            values = [("시험법", "document"), ("금융사", "actor")]
            return {"spans": [{"span": text, "start": self.question.index(text),
                                "end": self.question.index(text) + len(text),
                                "role": role} for text, role in values]}
        if kind == "rag.landing.values":
            return {"picks": [{"part_index": 2,
                                "candidate_id": "concept:actor"}]}
        raise AssertionError(kind)


def test_unknown_role_expression_uses_closed_db_menu_and_waits_for_human(
        tmp_path, monkeypatch):
    registry, canonical = _registry(tmp_path)
    index = Index.from_docs([_doc("d1", "시험법")])
    proposal_path = tmp_path / "term_proposals.json"
    alias_path = tmp_path / "aliases.json"
    alias_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("RAG_TERM_PROPOSALS", str(proposal_path))
    monkeypatch.setenv("RAG_ALIASES_STORE", str(alias_path))
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path / "rag"))
    question = "시험법에서 금융사의 배상 책임은?"

    sections, meta = landings.retrieve(
        index, question, registry, llm=ConceptAliasLLM(question), lexicon=False)

    assert [(section.doc_id, section.node) for section in sections] == [("d1", 1)]
    menu = next(row for row in meta["menus"] if row["role"] == "actor")
    assert menu["raw_count"] == 1 and menu["route"] == "all"
    pending = term_proposals.queue("pending")
    assert pending[0]["target"]["id"] == "concept:actor"
    before = json.loads(canonical.read_text(encoding="utf-8"))
    assert "금융사" not in before["concepts"][0].get("aliases", [])

    term_proposals.resolve(pending[0]["id"], "승인", reviewer="tester")
    after = json.loads(canonical.read_text(encoding="utf-8"))
    assert "금융사" in after["concepts"][0]["aliases"]


def _custom_registry(tmp_path, concepts, assertions):
    path = tmp_path / "custom-canonical.json"
    path.write_text(json.dumps({
        "schema_version": 1, "concepts": concepts,
        "relations": [], "assertions": assertions,
    }, ensure_ascii=False), encoding="utf-8")
    return Tier1Registry.load(path)


class ScopedActorLLM:
    model = "fake"

    def __init__(self, question):
        self.question = question
        self.value_menu = ""

    def structured(self, kind, _system, user, _schema, **_kwargs):
        if kind == "rag.oql.spans":
            values = [("첫째법", "document"), ("사업자", "actor")]
            return {"spans": [{
                "span": text, "start": self.question.index(text),
                "end": self.question.index(text) + len(text), "role": role,
            } for text, role in values]}
        if kind == "rag.landing.values":
            self.value_menu = user
            return {"picks": [{"part_index": 2, "candidate_id": "concept:first-actor"}]}
        raise AssertionError(kind)


def test_document_landing_scopes_actor_menu_before_intersection(tmp_path):
    concepts = [
        {"id": "first-actor", "label": "금융투자업자", "type": "organization_role",
         "status": "active", "approved_by": "tester"},
        {"id": "second-actor", "label": "가상자산사업자", "type": "organization_role",
         "status": "active", "approved_by": "tester"},
        {"id": "act", "label": "신고하다", "type": "action",
         "status": "active", "approved_by": "tester"},
    ]
    assertions = [
        {"id": "first", "roles": {"ACTOR": "first-actor", "PREDICATE": "act"},
         "source": {"doc_id": "d1", "node": 1}, "status": "active",
         "approved_by": "tester"},
        {"id": "second", "roles": {"ACTOR": "second-actor", "PREDICATE": "act"},
         "source": {"doc_id": "d2", "node": 1}, "status": "active",
         "approved_by": "tester"},
    ]
    registry = _custom_registry(tmp_path, concepts, assertions)
    index = Index.from_docs([_doc("d1", "첫째법"), _doc("d2", "둘째법")])
    question = "첫째법에서 사업자는 신고해야 하나?"
    llm = ScopedActorLLM(question)

    sections, meta = landings.retrieve(
        index, question, registry, llm=llm, lexicon=False, propose_terms=False)

    assert [(section.doc_id, section.node) for section in sections] == [("d1", 1)]
    assert "concept:first-actor" in llm.value_menu
    assert "concept:second-actor" not in llm.value_menu
    assert meta["scope"] == {
        "documents": 1, "structure_coordinates": 0, "assertions": 1,
    }


class HeadingLLM:
    model = "fake"

    def __init__(self, question, values):
        self.question = question
        self.values = values

    def structured(self, kind, _system, _user, _schema, **_kwargs):
        if kind != "rag.oql.spans":
            raise AssertionError(kind)
        return {"spans": [{
            "span": text, "start": self.question.index(text),
            "end": self.question.index(text) + len(text), "role": role,
        } for text, role in self.values]}


def test_heading_is_searchable_and_scopes_assertions_to_its_subtree(tmp_path):
    registry, _ = _registry(tmp_path, nodes=2)
    nodes = [
        {"id": 10, "parent": None, "level": 0, "family": "chapter",
         "surface": "제2장", "title": "손해배상책임", "ordinal": [2],
         "page": 1, "block": 0, "span": [0, 2]},
        {"id": 1, "parent": 10, "level": 1, "family": "kr_article",
         "surface": "제1조", "title": "배상", "ordinal": [1],
         "page": 1, "block": 1, "span": [1, 2]},
        {"id": 2, "parent": None, "level": 0, "family": "kr_article",
         "surface": "제2조", "title": "별도 책임", "ordinal": [2],
         "page": 2, "block": 2, "span": [2, 3]},
    ]
    blocks = [
        {"idx": 0, "page": 1, "node": 10, "kind": "text", "text": "제2장"},
        {"idx": 1, "page": 1, "node": 1, "kind": "text", "text": "배상한다"},
        {"idx": 2, "page": 2, "node": 2, "kind": "text", "text": "별도 배상"},
    ]
    index = Index.from_docs([("d1", {"name": "시험법"},
                              {"nodes": nodes, "blocks": blocks})])
    question = "시험법 손해배상책임에서 금융투자업자는 배상하나?"
    llm = HeadingLLM(question, [
        ("시험법", "document"), ("손해배상책임", "heading"),
        ("금융투자업자", "actor"),
    ])

    sections, meta = landings.retrieve(
        index, question, registry, llm=llm, lexicon=False, propose_terms=False)

    assert [(section.doc_id, section.node) for section in sections] == [("d1", 1)]
    assert meta["structure"]["locators"] == ["손해배상책임"]
    assert meta["scope"]["structure_coordinates"] == 2
    assert meta["scope"]["assertions"] == 1
    heading = next(row for row in meta["landings"] if row["role"] == "heading")
    assert heading["object_kind"] == "section"
    assert heading["object_id"] == "section:d1:10"
    assert heading["coordinate_count"] == 2


def test_semantic_parts_intersect_on_same_body_even_when_extracted_rows_differ(tmp_path):
    concepts = [
        {"id": "actor-a", "label": "갑사업자", "type": "organization_role",
         "status": "active", "approved_by": "tester"},
        {"id": "actor-b", "label": "을사업자", "type": "organization_role",
         "status": "active", "approved_by": "tester"},
        {"id": "act-a", "label": "신고하다", "type": "action",
         "status": "active", "approved_by": "tester"},
        {"id": "act-b", "label": "배상하다", "aliases": ["배상하나"], "type": "action",
         "status": "active", "approved_by": "tester"},
    ]
    assertions = [
        {"id": "as-a", "roles": {"ACTOR": "actor-a", "PREDICATE": "act-a"},
         "source": {"doc_id": "d1", "node": 1}, "status": "active",
         "approved_by": "tester"},
        {"id": "as-b", "roles": {"ACTOR": "actor-b", "PREDICATE": "act-b"},
         "source": {"doc_id": "d1", "node": 1}, "status": "active",
         "approved_by": "tester"},
    ]
    registry = _custom_registry(tmp_path, concepts, assertions)
    index = Index.from_docs([_doc("d1", "시험법")])
    question = "시험법에서 갑사업자가 배상하나?"
    llm = HeadingLLM(question, [
        ("시험법", "document"), ("갑사업자", "actor"), ("배상하나", "predicate"),
    ])

    sections, meta = landings.retrieve(
        index, question, registry, llm=llm, lexicon=False, propose_terms=False)

    assert [(section.doc_id, section.node) for section in sections] == [("d1", 1)]
    assert [row["after"] for row in meta["intersection"]] == [1, 1]


def test_semantic_parts_from_different_body_coordinates_do_not_combine(tmp_path):
    concepts = [
        {"id": "actor-a", "label": "갑사업자", "type": "organization_role",
         "status": "active", "approved_by": "tester"},
        {"id": "actor-b", "label": "을사업자", "type": "organization_role",
         "status": "active", "approved_by": "tester"},
        {"id": "act-a", "label": "신고하다", "type": "action",
         "status": "active", "approved_by": "tester"},
        {"id": "act-b", "label": "배상하다", "aliases": ["배상하나"], "type": "action",
         "status": "active", "approved_by": "tester"},
    ]
    assertions = [
        {"id": "fragment-a", "roles": {"ACTOR": "actor-a", "PREDICATE": "act-a"},
         "source": {"doc_id": "d1", "node": 1}, "status": "active",
         "approved_by": "tester"},
        {"id": "fragment-b", "roles": {"ACTOR": "actor-b", "PREDICATE": "act-b"},
         "source": {"doc_id": "d1", "node": 2}, "status": "active",
         "approved_by": "tester"},
    ]
    registry = _custom_registry(tmp_path, concepts, assertions)
    index = Index.from_docs([_doc("d1", "시험법", nodes=2)])
    question = "시험법에서 갑사업자가 배상하나?"
    llm = HeadingLLM(question, [
        ("시험법", "document"), ("갑사업자", "actor"), ("배상하나", "predicate"),
    ])

    sections, meta = landings.retrieve(
        index, question, registry, llm=llm, lexicon=False, propose_terms=False)

    assert sections == []
    assert [row["after"] for row in meta["intersection"]] == [1, 0]
    assert meta["fallback"] == "착지 좌표 교집합이 비어 있음"


class StructuredPredicateLLM:
    model = "fake"

    def __init__(self, question):
        self.question = question
        self.value_menu = ""

    def structured(self, kind, _system, user, _schema, **_kwargs):
        if kind == "rag.oql.spans":
            values = [
                ("시험법", "document"), ("제10조", "locator"),
                ("면접위원", "actor"), ("관계가 있으면", "condition"),
                ("제척하나요", "predicate"),
            ]
            return {"spans": [{
                "span": text, "start": self.question.index(text),
                "end": self.question.index(text) + len(text), "role": role,
            } for text, role in values]}
        if kind == "rag.landing.values":
            self.value_menu = user
            return {"picks": [{
                "part_index": 5, "candidate_id": "concept:exclude",
            }]}
        raise AssertionError(kind)


def test_explicit_structure_keeps_all_predicates_until_final_intersection(tmp_path):
    concepts = [
        {"id": "company", "label": "회사", "type": "organization_role",
         "status": "active", "approved_by": "tester"},
        {"id": "interviewer", "label": "면접위원", "type": "person_role",
         "status": "active", "approved_by": "tester"},
        {"id": "exclude", "label": "제척한다", "type": "action",
         "status": "active", "approved_by": "tester"},
        {"id": "recuse", "label": "회피한다", "type": "action",
         "status": "active", "approved_by": "tester"},
    ]
    assertions = [
        {"id": "exclude-row", "roles": {"ACTOR": "company",
                                             "PREDICATE": "exclude"},
         "source": {"doc_id": "d1", "node": 1}, "status": "active",
         "approved_by": "tester"},
        {"id": "recuse-row", "roles": {"ACTOR": "interviewer",
                                            "PREDICATE": "recuse"},
         "source": {"doc_id": "d1", "node": 2}, "status": "active",
         "approved_by": "tester"},
    ]
    registry = _custom_registry(tmp_path, concepts, assertions)
    nodes = [
        {"id": 10, "parent": None, "level": 0, "family": "kr_article",
         "surface": "제10조", "title": "면접", "ordinal": [10],
         "page": 1, "block": 0, "span": [0, 2]},
        {"id": 1, "parent": 10, "level": 1, "family": "circled",
         "surface": "①", "title": "", "ordinal": [1],
         "page": 1, "block": 0, "span": [0, 1]},
        {"id": 2, "parent": 10, "level": 1, "family": "circled",
         "surface": "②", "title": "", "ordinal": [2],
         "page": 1, "block": 1, "span": [1, 2]},
    ]
    blocks = [
        {"idx": 0, "page": 1, "node": 1, "kind": "text",
         "text": "회사는 면접위원이 관계가 있으면 그 면접위원을 제척한다."},
        {"idx": 1, "page": 1, "node": 2, "kind": "text",
         "text": "면접위원은 관계를 알면 스스로 회피한다."},
    ]
    index = Index.from_docs([("d1", {"name": "시험법"},
                              {"nodes": nodes, "blocks": blocks})])
    question = "시험법 제10조에서 면접위원이 관계가 있으면 제척하나요?"
    llm = StructuredPredicateLLM(question)

    sections, meta = landings.retrieve(
        index, question, registry, llm=llm, lexicon=False, propose_terms=False)

    assert [(section.doc_id, section.node) for section in sections] == [("d1", 1)]
    assert "concept:exclude" in llm.value_menu
    assert "concept:recuse" in llm.value_menu
    assert not any(row["role"] == "condition" for row in meta["landings"])
    assert [row["after"] for row in meta["intersection"]] == [2, 1]


def test_definition_question_bypasses_assertion_intersection(tmp_path):
    nodes = [{
        "id": 1, "parent": None, "level": 0, "family": "kr_article",
        "surface": "제1조", "title": "사업자의 정의", "ordinal": [1],
        "page": 1, "block": 0, "span": [0, 1],
    }]
    blocks = [{
        "idx": 0, "page": 1, "node": 1, "kind": "text",
        "text": '① 이 법에서 "사업자"란 영업을 하는 자를 말한다.',
    }]
    index = Index.from_docs([("d1", {"name": "시험법"},
                              {"nodes": nodes, "blocks": blocks})])

    sections, meta = landings.retrieve(
        index, "시험법에서 사업자의 정의는 무엇인가요?",
        Tier1Registry(), llm=None, propose_terms=False)

    assert [(section.kind, section.doc_id, section.node) for section in sections] == [
        ("정의", "d1", 1),
    ]
    assert "사업자" in sections[0].text
    assert meta["strategy"] == "definition_lookup"
    assert meta["pruning"] == "definition-direct"
    assert meta["intersection"] == []
    assert meta["definition_hits"][0]["term"] == "사업자"


def test_definition_does_not_fall_into_subterm_of_unknown_document(tmp_path):
    nodes = [{
        "id": 1, "parent": None, "level": 0, "family": "kr_article",
        "surface": "제1조", "title": "정의", "ordinal": [1],
        "page": 1, "block": 0, "span": [0, 1],
    }]
    blocks = [{
        "idx": 0, "page": 1, "node": 1, "kind": "text",
        "text": '이 법에서 "투자"란 자산을 운용하는 것을 말한다.',
    }]
    index = Index.from_docs([("d1", {"name": "실제법"},
                              {"nodes": nodes, "blocks": blocks})])

    sections, meta = landings.retrieve(
        index, "투자자 보호법의 정의는 뭐야?", Tier1Registry(),
        llm=None, propose_terms=False)

    assert sections == []
    assert meta["strategy"] == "coordinate_intersection"
    assert not meta.get("definition_hits")


def test_author_alias_expands_a_query_to_later_b_usages_without_intersection():
    nodes = [
        {"id": 1, "parent": None, "level": 0, "family": "kr_article",
         "surface": "제1조", "title": "별칭", "ordinal": [1],
         "page": 1, "block": 0, "span": [0, 1]},
        {"id": 2, "parent": None, "level": 0, "family": "kr_article",
         "surface": "제2조", "title": "판매", "ordinal": [2],
         "page": 1, "block": 1, "span": [1, 2]},
    ]
    blocks = [
        {"idx": 0, "page": 1, "node": 1, "kind": "text",
         "text": '① 특정 금융상품(이하 "대상상품"이라 한다).'},
        {"idx": 1, "page": 1, "node": 2, "kind": "text",
         "text": "대상상품을 판매하는 사업자는 설명의무를 진다."},
    ]
    index = Index.from_docs([(
        "d1", {"name": "시험법"}, {"nodes": nodes, "blocks": blocks},
    )])

    sections, meta = landings.retrieve(
        index, "시험법에서 특정 금융상품은 누가 판매하나요?",
        Tier1Registry(), llm=None, propose_terms=False,
    )

    assert [(section.doc_id, section.node) for section in sections] == [("d1", 2)]
    assert "특정 금융상품 → 대상상품" in sections[0].matched
    assert meta["definition_expansions"] == [{
        "from": "특정 금융상품", "to": ["대상상품"], "doc_id": "d1",
        "definition_node": 1, "coordinate_count": 1,
        "scope": "doc-after-declaration",
    }]
    assert meta["intersection"][0]["role"] == "definition_alias"
    assert meta["intersection"][0]["after"] == 1


def test_non_concept_body_fragment_is_searchable_by_its_source_coordinate(tmp_path):
    concepts = [
        {"id": "operator", "label": "사업자", "type": "organization_role",
         "status": "active", "approved_by": "tester"},
        {"id": "liable", "label": "책임을 지다", "type": "action",
         "status": "active", "approved_by": "tester"},
    ]
    assertions = [{
        "id": "old-extraction-row", "roles": {
            "ACTOR": "operator", "PREDICATE": "liable",
        },
        "source": {"doc_id": "d1", "node": 1},
        "query_cues": ["업무 소홀"],
        "status": "active", "approved_by": "tester",
    }]
    registry = _custom_registry(tmp_path, concepts, assertions)
    index = Index.from_docs([_doc("d1", "시험법")])

    sections, meta = landings.retrieve(
        index, "시험법에서 업무 소홀 문제가 있나요?", registry,
        llm=None, propose_terms=False,
    )

    assert [(section.doc_id, section.node) for section in sections] == [("d1", 1)]
    assert meta["literal_fragments"] == [{
        "surface": "업무 소홀", "coordinate_count": 1, "provenance_count": 1,
    }]
    assert meta["intersection"][0]["role"] == "literal_fragment"
    assert meta["intersection"][0]["after"] == 1


def test_deterministic_reverse_match_does_not_join_short_term_across_space(tmp_path):
    concepts = [
        {"id": "bond", "label": "사채", "type": "domain_term",
         "status": "active", "approved_by": "tester"},
        {"id": "operator", "label": "금융투자회사", "type": "organization_role",
         "status": "active", "approved_by": "tester"},
        {"id": "hire", "label": "채용한다", "type": "action",
         "status": "active", "approved_by": "tester"},
    ]
    assertions = [{
        "id": "row", "roles": {"ACTOR": "operator", "OBJECT": "bond",
                                  "PREDICATE": "hire"},
        "source": {"doc_id": "d1", "node": 1}, "status": "active",
        "approved_by": "tester",
    }]
    registry = _custom_registry(tmp_path, concepts, assertions)

    spans = landings._deterministic_spans(
        registry, "금융투자회사 채용 절차", registry.active_assertions)

    assert [(span.text, span.start, span.end) for span in spans] == [
        ("금융투자회사", 0, 6),
    ]


def test_explicit_structure_is_valid_landing_when_no_scoped_concept_matches(tmp_path):
    concepts = [
        {"id": "elsewhere", "label": "감독규정", "type": "domain_term",
         "status": "active", "approved_by": "tester"},
        {"id": "regulate", "label": "정한다", "type": "action",
         "status": "active", "approved_by": "tester"},
    ]
    assertions = [{
        "id": "elsewhere-row", "roles": {"SUBJECT": "elsewhere",
                                            "PREDICATE": "regulate"},
        "source": {"doc_id": "d2", "node": 1}, "status": "active",
        "approved_by": "tester",
    }]
    registry = _custom_registry(tmp_path, concepts, assertions)
    index = Index.from_docs([_doc("d1", "시험법"), _doc("d2", "다른법")])

    sections, meta = landings.retrieve(
        index, "시험법 제1조에서 감독규정 관련 사항은?", registry,
        llm=None, propose_terms=False)

    assert [(section.doc_id, section.node) for section in sections] == [("d1", 1)]
    assert meta["spans"] == []
    assert meta["pruning"] == "direct-all"


def test_scoped_body_surface_repairs_missing_role_edge(tmp_path):
    concepts = [
        {"id": "operator", "label": "사업자", "type": "organization_role",
         "status": "active", "approved_by": "tester"},
        {"id": "applicant", "label": "지원자", "type": "person_role",
         "status": "active", "approved_by": "tester"},
        {"id": "exclude", "label": "제척한다", "type": "action",
             "status": "active", "approved_by": "tester"},
    ]
    assertions = [
        {"id": "answer", "roles": {"ACTOR": "operator", "PREDICATE": "exclude"},
         "source": {"doc_id": "d1", "node": 1}, "status": "active",
         "approved_by": "tester"},
        # 지원자 Concept는 정본에 있지만 이 본문의 추출 행에는 역할 간선이
        # 빠지고 다른 본문에만 연결된 상황을 재현한다.
        {"id": "other", "roles": {"TARGET": "applicant",
                                      "PREDICATE": "exclude"},
         "source": {"doc_id": "d1", "node": 2}, "status": "active",
         "approved_by": "tester"},
    ]
    registry = _custom_registry(tmp_path, concepts, assertions)
    nodes = [
        {"id": 10, "parent": None, "level": 0, "family": "kr_article",
         "surface": "제10조", "title": "절차", "ordinal": [10],
         "page": 1, "block": 0, "span": [0, 2]},
        {"id": 1, "parent": 10, "level": 1, "family": "kr_paragraph",
         "surface": "①", "title": "", "ordinal": [1],
         "page": 1, "block": 0, "span": [0, 1]},
        {"id": 2, "parent": 10, "level": 1, "family": "kr_paragraph",
         "surface": "②", "title": "", "ordinal": [2],
         "page": 1, "block": 1, "span": [1, 2]},
    ]
    blocks = [
        {"idx": 0, "page": 1, "node": 1, "kind": "text",
         "text": "사업자는 지원자를 해당 절차에서 제척한다."},
        {"idx": 1, "page": 1, "node": 2, "kind": "text",
         "text": "지원자는 별도 절차를 따른다."},
    ]
    index = Index.from_docs([("d1", {"name": "시험법"},
                              {"nodes": nodes, "blocks": blocks})])

    sections, out = landings.retrieve(
        index, "시험법 제10조에서 사업자가 지원자를 제척한다?", registry,
        llm=None, propose_terms=False)

    assert [(section.doc_id, section.node) for section in sections] == [("d1", 1)]
    applicant = next(row for row in out["landings"] if row["label"] == "지원자")
    assert applicant["via"].endswith("+exact-body")


def test_compound_action_can_match_spaced_words_in_same_narrowed_body(tmp_path):
    concepts = [
        {"id": "operator", "label": "사업자", "type": "organization_role",
         "status": "active", "approved_by": "tester"},
        {"id": "prospectus", "label": "투자설명서", "type": "document",
         "status": "active", "approved_by": "tester"},
        {"id": "violate", "label": "위반하다", "type": "action",
         "status": "active", "approved_by": "tester"},
        {"id": "damages", "label": "손해배상책임", "type": "action",
         "status": "active", "approved_by": "tester"},
        {"id": "disclosure", "label": "공시책임", "type": "action",
         "status": "active", "approved_by": "tester"},
    ]
    assertions = [
        {"id": "answer", "roles": {"ACTOR": "operator", "SUBJECT": "prospectus",
                                     "PREDICATE": "violate"},
         "source": {"doc_id": "d1", "node": 1}, "status": "active",
         "approved_by": "tester"},
        {"id": "other-damages", "roles": {"ACTOR": "operator",
                                             "PREDICATE": "damages"},
         "source": {"doc_id": "d1", "node": 2}, "status": "active",
         "approved_by": "tester"},
        {"id": "other-disclosure", "roles": {"ACTOR": "operator",
                                                "PREDICATE": "disclosure"},
         "source": {"doc_id": "d1", "node": 2}, "status": "active",
         "approved_by": "tester"},
    ]
    registry = _custom_registry(tmp_path, concepts, assertions)
    did, meta, result = _doc("d1", "시험법", nodes=2)
    result["blocks"][0]["text"] = \
        "사업자는 투자설명서를 위반하여 손해를 배상할 책임이 있다."
    result["blocks"][1]["text"] = "사업자는 별도 의무를 진다."
    index = Index.from_docs([(did, meta, result)])

    sections, out = landings.retrieve(
        index, "시험법에서 사업자와 투자설명서 손해배상책임은?", registry,
        llm=None, propose_terms=False)

    assert [(section.doc_id, section.node) for section in sections] == [("d1", 1)]
    repaired = next(row for row in out["landings"]
                    if row["label"] == "손해배상책임")
    assert repaired["via"].endswith("+compound-body")

    wrong, wrong_meta = landings.retrieve(
        index, "시험법에서 사업자와 투자설명서 공시책임은?", registry,
        llm=None, propose_terms=False)
    assert wrong == []
    assert wrong_meta["fallback"] == "착지 좌표 교집합이 비어 있음"
