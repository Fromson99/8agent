import json

import pytest

from lawrag.core.domain_graph import oql
from lawrag.core.domain_graph.alignment import ConceptAligner
from lawrag.core.domain_graph import spanparts
from lawrag.core.domain_graph.builder import GraphBuilder
from lawrag.core.domain_graph.canonical import CanonicalRegistry
from lawrag.core.domain_graph.store import GraphStore
from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.rag import conceptfirst, vecfirst, vector
from lawrag.core.rag.index import Index


def _blob():
    return {
        "schema_version": 1,
        "concepts": [
            {"id": "operator", "label": "금융투자업자", "type": "organization_role",
             "aliases": ["금투사", "금융투자회사"], "status": "active",
             "approved_by": "tester"},
            {"id": "prospectus", "label": "투자설명서", "type": "document",
             "status": "active", "approved_by": "tester"},
            {"id": "liable", "label": "손해배상책임을 부담하다", "type": "action",
             "status": "active", "approved_by": "tester"},
        ],
        "relations": [],
        "assertions": [{
            "id": "as1", "status": "active", "approved_by": "tester",
            "roles": {"ACTOR": "operator", "PREDICATE": "liable",
                      "SUBJECT": "prospectus"},
            "source": {"doc_id": "d1", "node": 1}, "confidence": 0.99,
            "query_cues": ["손해", "책임", "위반"],
            "note": "투자설명서 위반에 관한 손해배상책임",
        }],
    }


def _index():
    return Index.from_docs([("d1", {"name": "시험법"}, {
        "nodes": [{"id": 1, "parent": None, "level": 0, "family": "kr_article",
                   "surface": "제1조", "title": "책임", "ordinal": [1],
                   "page": 1, "block": 0, "span": [0, 1]}],
        "blocks": [{"idx": 0, "page": 1, "node": 1, "kind": "text",
                    "text": "금융투자업자는 투자설명서 위반으로 인한 손해를 배상한다."}],
    })])


def _built(tmp_path, monkeypatch, *, blob=None, index=None):
    canonical = tmp_path / "domain_graph" / "canonical.json"
    canonical.parent.mkdir()
    canonical.write_text(json.dumps(blob or _blob(), ensure_ascii=False), encoding="utf-8")
    glossary = tmp_path / "glossary.json"
    glossary.write_text('{"terms": []}', encoding="utf-8")
    delegation = tmp_path / "delegation.json"
    delegation.write_text('{"edges": []}', encoding="utf-8")
    monkeypatch.setenv("RAG_DELEGATION_STORE", str(delegation))
    db = canonical.parent / "graph.sqlite"
    registry = CanonicalRegistry.load(registry_path=canonical, glossary_path=glossary)
    GraphBuilder(index or _index(), data_dir=tmp_path, registry=registry,
                 glossary_path=glossary).build(db, include_derived=False)
    return canonical, db


def test_tier1_active_requires_approval_and_action_predicate(tmp_path):
    blob = _blob()
    blob["concepts"][0].pop("approved_by")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(blob, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="approved_by"):
        Tier1Registry.load(path)

    blob = _blob()
    blob["assertions"][0]["roles"]["PREDICATE"] = "prospectus"
    path.write_text(json.dumps(blob, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="action concept"):
        Tier1Registry.load(path)

    blob = _blob()
    evidence = [{"doc_id": "d1", "node": 1}]
    blob["relations"] = [
        {"id": "rel-one", "type": "IS_A", "src": "operator", "dst": "prospectus",
         "status": "active", "approved_by": "tester", "evidence": evidence},
        {"id": "rel-two", "type": "IS_A", "src": "prospectus", "dst": "operator",
         "status": "active", "approved_by": "tester", "evidence": evidence},
    ]
    path.write_text(json.dumps(blob, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="IS_A 순환"):
        Tier1Registry.load(path)


def test_alignment_jointly_selects_concepts_in_same_assertion(tmp_path):
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps(_blob(), ensure_ascii=False), encoding="utf-8")
    alignment = ConceptAligner(Tier1Registry.load(path)).align(
        "금투사와 투자설명서는 어떤 관계야?")
    assert alignment.intent == "RELATION_BETWEEN_CONCEPTS"
    assert {c.concept_id for c in alignment.selected} == {"concept:operator", "concept:prospectus"}
    assert alignment.via == "deterministic"

    # 그래프가 이미 연결되어 있다는 사실이 약한 문자열 유사도를 자기확증하면 안 된다.
    weak = ConceptAligner(Tier1Registry.load(path)).align("일반 회사 설명서를 찾아줘")
    assert weak.selected == []


def test_oql_binds_only_registered_concept_ids(tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    registry = Tier1Registry.load(canonical)
    alignment = ConceptAligner(registry).align("금투사와 투자설명서의 관계")
    request = oql.plan(alignment)
    assert request == {
        "pattern": "relation_between_concepts",
        "params": {"left_concept_ids": ["concept:operator"],
                   "right_concept_ids": ["concept:prospectus"]},
    }
    assert "금투사" not in json.dumps(request, ensure_ascii=False)
    with GraphStore(db, readonly=True) as store:
        assert store.get_node("concept:operator")["props"]["knowledge_grade"] == 1
        result = oql.execute(store, registry, request)
        assert result["count"] == 1
        assert result["rows"][0]["sources"][0]["node"] == 1
        with pytest.raises(ValueError, match="선언되지 않은"):
            oql.execute(store, registry, {**request,
                         "params": {**request["params"], "cypher": "MATCH (n)"}})

        scoped = oql.plan(alignment, structural={"source_doc_ids": ["other-doc"]})
        assert oql.execute(store, registry, scoped)["count"] == 0
        scoped = oql.plan(alignment, structural={
            "source_doc_ids": ["d1"],
            "source_coordinates": [{"doc_id": "d1", "node": 999}],
        })
        assert oql.execute(store, registry, scoped)["count"] == 0


def test_existing_vecfirst_starts_with_concept_and_keeps_fallback(tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    def unexpected_vector(*_a, **_k):
        raise AssertionError("좌표 교집합 착지 뒤 전역 Vector를 다시 호출함")

    monkeypatch.setattr(vector, "search", unexpected_vector)

    sections, meta = vecfirst.retrieve(
        _index(), "금투사와 투자설명서의 관계", entry_k=0, llm=None,
        raw_query="금투사와 투자설명서의 관계")
    assert sections[0].kind == "교집합"
    assert sections[0].node == 1
    assert meta["concept"]["strategy"] == "coordinate_intersection"
    assert meta["concept"]["candidate_count"] == 1
    assert meta["entry_policy"] == "coordinate-intersection-only"
    assert meta["vector_hits"] == 0
    assert meta["concept_hits"]


def test_vecfirst_does_not_repeat_frame_llm_after_concept_hit(monkeypatch):
    from lawrag.core.rag import framequery
    from lawrag.core.rag.answer import Section

    concept_section = Section(
        n=0, doc_id="d1", doc="시험법", node=1, path="제1조", page=1,
        kind="Concept", matched="정본 사실문", text="근거",
    )
    monkeypatch.setattr(
        conceptfirst, "retrieve",
        lambda *_args, **_kwargs: ([concept_section], {"alignment": {}}),
    )
    monkeypatch.setattr(vector, "search", lambda *_args, **_kwargs: [])

    def unexpected_frame_call(*_args, **_kwargs):
        raise AssertionError("Concept가 근거를 찾은 뒤 프레임 LLM을 다시 호출함")

    monkeypatch.setattr(framequery, "lex_hits", unexpected_frame_call)

    sections, meta = vecfirst.retrieve(
        _index(), "정확한 질문", entry_k=0, llm=object(), raw_query="정확한 질문")

    assert sections[0].kind == "Concept"
    assert meta["concept_hits"]
    assert meta["frame_hits"] == []


def test_alias_pair_is_not_made_ambiguous_by_third_graph_candidate(tmp_path):
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps(_blob(), ensure_ascii=False), encoding="utf-8")
    alignment = ConceptAligner(Tier1Registry.load(path)).align(
        "금융투자회사가 투자 설명서와 어떤 관계가 있나요?")
    assert not alignment.ambiguous
    assert {c.label for c in alignment.selected} == {"금융투자업자", "투자설명서"}
    assert all(c.via.count("+graph") == 1 for c in alignment.candidates)


def test_alignment_uses_explicit_assertion_scope_and_prefers_context(tmp_path):
    blob = _blob()
    blob["concepts"].extend([
        {"id": "contract", "label": "계약서", "type": "document",
         "status": "active", "approved_by": "tester"},
        {"id": "sign", "label": "체결하다", "type": "action",
         "status": "active", "approved_by": "tester"},
    ])
    blob["assertions"].append({
        "id": "as2", "status": "active", "approved_by": "tester",
        "roles": {"ACTOR": "operator", "PREDICATE": "sign",
                  "SUBJECT": "contract"},
        "source": {"doc_id": "d2", "node": 2}, "confidence": 0.9,
        "query_cues": ["체결"],
    })
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps(blob, ensure_ascii=False), encoding="utf-8")
    aligner = ConceptAligner(Tier1Registry.load(path))

    scoped = aligner.align(
        "금투사와 투자설명서와 계약서는 어떤 관계야?", assertion_ids={"as1"})
    assert not scoped.ambiguous
    assert {c.concept_id for c in scoped.selected} == {
        "concept:operator", "concept:prospectus",
    }

    contextual = aligner.align(
        "금융투자업자가 투자설명서에 손해배상책임을 부담하다")
    assert "concept:prospectus" in {c.concept_id for c in contextual.selected}


def test_unscoped_pair_must_identify_one_assertion(tmp_path, monkeypatch):
    blob = _blob()
    duplicate = dict(blob["assertions"][0])
    duplicate.update(id="as2", source={"doc_id": "d1", "node": 2},
                     note="같은 부품의 별도 의무")
    blob["assertions"].append(duplicate)
    index = Index.from_docs([("d1", {"name": "시험법"}, {
        "nodes": [
            {"id": 1, "parent": None, "level": 0, "family": "kr_article",
             "surface": "제1조", "title": "책임", "ordinal": [1],
             "page": 1, "block": 0, "span": [0, 1]},
            {"id": 2, "parent": None, "level": 0, "family": "kr_article",
             "surface": "제2조", "title": "별도 책임", "ordinal": [2],
             "page": 1, "block": 1, "span": [1, 2]},
        ],
        "blocks": [
            {"idx": 0, "page": 1, "node": 1, "kind": "text", "text": "책임"},
            {"idx": 1, "page": 1, "node": 2, "kind": "text", "text": "별도 책임"},
        ],
    })])
    canonical, db = _built(tmp_path, monkeypatch, blob=blob, index=index)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))

    sections, meta = conceptfirst.retrieve(
        index, "금투사와 투자설명서는 어떤 관계야?")

    assert sections == []
    assert meta["oql"]["count"] == 2
    assert "Assertion 다중 후보" in meta["fallback"]


def test_conceptfirst_rejects_same_entity_with_unrelated_predicate(tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))

    sections, meta = conceptfirst.retrieve(_index(), "금융투자업자가 부동산 중개를 하나?")
    assert sections == []
    assert "질문 술어" in meta["fallback"]

    sections, _ = conceptfirst.retrieve(
        _index(), "금투사가 투자설명서를 전자우편으로 보내도 되나?")
    assert sections == []

    sections, _ = conceptfirst.retrieve(
        _index(), "금융투자업자가 부동산 중개 사고의 손해를 배상할 책임이 있나?")
    assert sections == []


def test_unscoped_generic_concept_pair_falls_through(tmp_path, monkeypatch):
    blob = {
        "schema_version": 1,
        "concepts": [
            {"id": "information", "label": "정보", "type": "domain_term",
             "status": "active", "approved_by": "tester"},
            {"id": "disclose", "label": "공개하다", "type": "action",
             "status": "active", "approved_by": "tester"},
        ],
        "relations": [],
        "assertions": [{
            "id": "generic", "status": "active", "approved_by": "tester",
            "roles": {"OBJECT": "information", "PREDICATE": "disclose"},
            "source": {"doc_id": "d1", "node": 1}, "confidence": 0.9,
            "query_cues": ["공개"],
        }],
    }
    canonical, db = _built(tmp_path, monkeypatch, blob=blob)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))

    sections, meta = conceptfirst.retrieve(_index(), "정보를 공개하다")

    assert sections == []
    assert {c["label"] for c in meta["alignment"]["selected"]} == {"정보", "공개하다"}
    assert "범용 Concept" in meta["fallback"]


class _GenericPartLLM:
    def __init__(self, question):
        self.question = question

    def structured(self, kind, _system, _user, _schema, **_kwargs):
        if kind == "rag.oql.spans":
            return {"spans": [
                {"span": "정보", "start": self.question.index("정보"),
                 "end": self.question.index("정보") + 2, "role": "object"},
                {"span": "공개하다", "start": self.question.index("공개하다"),
                 "end": self.question.index("공개하다") + 4, "role": "predicate"},
            ]}
        return {"decision": "SELECT", "intent": "ASSERTION_BY_PARTS", "mappings": [
            {"span_idx": 1, "part_id": "concept:information", "role": "object"},
            {"span_idx": 2, "part_id": "concept:disclose", "role": "predicate"},
        ]}


def test_llm_cannot_promote_unscoped_generic_pair(tmp_path, monkeypatch):
    blob = {
        "schema_version": 1,
        "concepts": [
            {"id": "information", "label": "정보", "type": "domain_term",
             "status": "active", "approved_by": "tester"},
            {"id": "disclose", "label": "공개하다", "type": "action",
             "status": "active", "approved_by": "tester"},
        ],
        "relations": [],
        "assertions": [{
            "id": "generic", "status": "active", "approved_by": "tester",
            "roles": {"OBJECT": "information", "PREDICATE": "disclose"},
            "source": {"doc_id": "d1", "node": 1}, "confidence": 0.9,
            "query_cues": ["공개"],
        }],
    }
    canonical, db = _built(tmp_path, monkeypatch, blob=blob)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    monkeypatch.setattr(spanparts, "cached_term_lexicon", lambda: None)
    question = "정보를 공개하다"

    sections, meta = conceptfirst.retrieve(
        _index(), question, llm=_GenericPartLLM(question))

    assert sections == []
    assert meta["alignment"]["via"] == "span_parts_llm"
    assert "범용 Concept" in meta["fallback"]


def test_conceptfirst_fails_open_when_registry_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(tmp_path / "missing.json"))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(tmp_path / "missing.sqlite"))
    sections, meta = conceptfirst.retrieve(_index(), "아무 질문")
    assert sections == []
    assert meta["fallback"]


class _PartLLM:
    def __init__(self, question, *, invented=False, bad_part=False,
                 bad_role=False, context_as_object=False,
                 prospectus_document=False, zero_based=False):
        self.question = question
        self.invented = invented
        self.bad_part = bad_part
        self.bad_role = bad_role
        self.context_as_object = context_as_object
        self.prospectus_document = prospectus_document
        self.zero_based = zero_based
        self.calls = []

    def structured(self, kind, _system, user, _schema, **_kwargs):
        self.calls.append((kind, user))
        if kind == "rag.oql.spans":
            values = [
                ("금투사", "actor"),
                ("투자설명서", "document" if self.prospectus_document else "subject"),
                ("손해배상책임", "predicate"), ("시험법", "document"),
                ("제1조", "locator"),
            ]
            if self.invented:
                values = [("질문에 없는 표현", "object")]
            return {"spans": [
                {"span": text, "start": self.question.find(text),
                 "end": self.question.find(text) + len(text), "role": role}
                for text, role in values
            ]}
        assert kind == "rag.oql.compose"
        if self.bad_part:
            return {
                "decision": "SELECT", "intent": "ASSERTION_BY_PARTS",
                "mappings": [{"span_idx": 1, "part_id": "concept:not-in-menu",
                              "role": "actor"}],
            }
        out = {
            "decision": "SELECT", "intent": "ASSERTION_BY_PARTS",
            "mappings": [
                {"span_idx": 1, "part_id": "concept:operator", "role": "actor"},
                {"span_idx": 2, "part_id": "concept:prospectus", "role": "subject"},
                {"span_idx": 3, "part_id": "concept:liable", "role": "predicate"},
            ],
        }
        if self.bad_role:
            out["mappings"][2]["role"] = "subject"
        if self.context_as_object:
            out["mappings"][1]["role"] = "object"
        if self.zero_based:
            for row in out["mappings"]:
                row["span_idx"] -= 1
        return out


def test_span_parser_rejects_words_not_present_in_question():
    question = "금투사의 책임은 무엇인가?"
    assert spanparts.extract_spans(_PartLLM(question, invented=True), question) == []


def test_llm_assembles_only_data_parts_and_binds_structure(tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    # 단위시험은 저장소 전체 용어 임베딩을 싣지 않는다. 부품 표면형과 구조 스코프만
    # 써도 닫힌 조립 계약을 검증할 수 있다.
    monkeypatch.setattr(spanparts, "cached_term_lexicon", lambda: None)
    question = "금투사가 투자설명서 위반으로 지는 손해배상책임은 시험법 제1조에 있나?"
    llm = _PartLLM(question)

    sections, meta = conceptfirst.retrieve(_index(), question, llm=llm)

    assert [kind for kind, _ in llm.calls] == ["rag.oql.spans", "rag.oql.compose"]
    assert meta["alignment"]["via"] == "span_parts_llm"
    assert meta["oql"]["pattern"] == "assertion_by_parts"
    assert meta["structure"]["documents"] == ["시험법"]
    assert meta["structure"]["locators"] == ["제1조"]
    assert meta["oql"]["params"]["source_doc_ids"] == ["d1"]
    assert meta["oql"]["params"]["source_coordinates"] == [
        {"doc_id": "d1", "node": 1}]
    assert len(sections) == 1 and sections[0].node == 1


def test_llm_zero_based_span_indices_are_accepted_only_when_menu_ids_prove_it(
        tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    monkeypatch.setattr(spanparts, "cached_term_lexicon", lambda: None)
    question = "금투사가 투자설명서 위반으로 지는 손해배상책임은 시험법 제1조에 있나?"

    sections, meta = conceptfirst.retrieve(
        _index(), question, llm=_PartLLM(question, zero_based=True))

    assert len(sections) == 1 and sections[0].node == 1
    assert meta["parts"]["proposals"][0]["span_index_base"] == 0


def test_llm_sparse_span_index_is_repaired_only_by_unique_part_membership(tmp_path):
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps(_blob(), ensure_ascii=False), encoding="utf-8")
    registry = Tier1Registry.load(path)
    spans = [
        spanparts.QuerySpan("금투사", 0, 3, "actor"),
        spanparts.QuerySpan("투자설명서", 4, 9, "subject"),
        spanparts.QuerySpan("위반으로", 10, 14, "condition"),
        spanparts.QuerySpan("손해배상책임을 부담하다", 15, 27, "predicate"),
    ]

    def part(cid, label, ctype):
        return spanparts.Part(cid, label, ctype, label, "exact", 1.0)

    menus = [
        spanparts.SpanMenu(spans[0], [
            part("concept:operator", "금융투자업자", "organization_role")]),
        spanparts.SpanMenu(spans[1], [
            part("concept:prospectus", "투자설명서", "document")]),
        spanparts.SpanMenu(spans[2], []),
        spanparts.SpanMenu(spans[3], [
            part("concept:liable", "손해배상책임을 부담하다", "action")]),
    ]

    class SparseNumberLLM:
        def structured(self, *_args, **_kwargs):
            return {"decision": "SELECT", "intent": "ASSERTION_BY_PARTS",
                    "mappings": [
                        {"span_idx": 1, "part_id": "concept:operator", "role": "actor"},
                        {"span_idx": 2, "part_id": "concept:prospectus", "role": "subject"},
                        # 선택하지 않은 S3을 건너뛰지 않고 세어 잘못 낸 번호다.
                        {"span_idx": 3, "part_id": "concept:liable", "role": "predicate"},
                    ]}

    assembled = spanparts.compose(
        SparseNumberLLM(), registry, "금투사 투자설명서 위반으로 손해배상책임을 부담하다",
        spans, menus, spanparts.StructureAnchors(
            doc_ids=("d1",), documents=("시험법",), locators=("제1조",),
            source_coordinates=(("d1", 1),),
        ),
    )

    assert assembled.decision == "SELECT"
    assert assembled.proposals[0]["span_index_base"] == "part_membership"
    assert assembled.proposals[0]["mappings"][-1]["span_idx"] == 4


def test_llm_duplicate_part_mapping_keeps_unique_best_surface_span(tmp_path):
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps(_blob(), ensure_ascii=False), encoding="utf-8")
    registry = Tier1Registry.load(path)
    spans = [
        spanparts.QuerySpan("금투사", 0, 3, "actor"),
        spanparts.QuerySpan("일반 문서", 4, 9, "object"),
        spanparts.QuerySpan("투자설명서", 10, 15, "subject"),
        spanparts.QuerySpan("손해배상책임을 부담하다", 16, 28, "predicate"),
    ]

    def part(cid, label, ctype, matched=None):
        return spanparts.Part(cid, label, ctype, matched or label, "exact", 1.0)

    menus = [
        spanparts.SpanMenu(spans[0], [
            part("concept:operator", "금융투자업자", "organization_role")]),
        spanparts.SpanMenu(spans[1], [
            part("concept:prospectus", "투자설명서", "document")]),
        spanparts.SpanMenu(spans[2], [
            part("concept:prospectus", "투자설명서", "document")]),
        spanparts.SpanMenu(spans[3], [
            part("concept:liable", "손해배상책임을 부담하다", "action")]),
    ]

    class DuplicateLLM:
        def structured(self, *_args, **_kwargs):
            return {"decision": "SELECT", "intent": "ASSERTION_BY_PARTS",
                    "mappings": [
                        {"span_idx": 1, "part_id": "concept:operator", "role": "actor"},
                        {"span_idx": 2, "part_id": "concept:prospectus", "role": "object"},
                        {"span_idx": 3, "part_id": "concept:prospectus", "role": "subject"},
                        {"span_idx": 4, "part_id": "concept:liable", "role": "predicate"},
                    ]}

    assembled = spanparts.compose(
        DuplicateLLM(), registry,
        "금투사 일반 문서 투자설명서 손해배상책임을 부담하다",
        spans, menus, spanparts.StructureAnchors(
            doc_ids=("d1",), documents=("시험법",), locators=("제1조",),
            source_coordinates=(("d1", 1),),
        ),
    )

    assert assembled.decision == "SELECT"
    assert [row["span_idx"] for row in assembled.proposals[0]["mappings"]] == [1, 3, 4]
    assert assembled.proposals[0]["deduplicated_mappings"][0]["span_idx"] == 2


def test_llm_selected_part_moves_to_unique_menu_matching_its_declared_role(tmp_path):
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps(_blob(), ensure_ascii=False), encoding="utf-8")
    registry = Tier1Registry.load(path)
    spans = [
        spanparts.QuerySpan("위반으로", 0, 4, "condition"),
        spanparts.QuerySpan("손해배상책임을 부담하다", 5, 17, "predicate"),
        spanparts.QuerySpan("금투사", 18, 21, "actor"),
    ]

    def part(cid, label, ctype):
        return spanparts.Part(cid, label, ctype, label, "exact", 1.0)

    liable = part("concept:liable", "손해배상책임을 부담하다", "action")
    menus = [
        spanparts.SpanMenu(spans[0], [liable]),
        spanparts.SpanMenu(spans[1], [liable]),
        spanparts.SpanMenu(spans[2], [
            part("concept:operator", "금융투자업자", "organization_role")]),
    ]

    class MisplacedPredicateLLM:
        def structured(self, *_args, **_kwargs):
            return {"decision": "SELECT", "intent": "ASSERTION_BY_PARTS",
                    "mappings": [
                        {"span_idx": 1, "part_id": "concept:liable", "role": "predicate"},
                        {"span_idx": 3, "part_id": "concept:operator", "role": "actor"},
                    ]}

    assembled = spanparts.compose(
        MisplacedPredicateLLM(), registry,
        "위반으로 손해배상책임을 부담하다 금투사", spans, menus,
        spanparts.StructureAnchors(
            doc_ids=("d1",), documents=("시험법",), locators=("제1조",),
            source_coordinates=(("d1", 1),),
        ),
    )

    assert assembled.decision == "SELECT"
    assert assembled.proposals[0]["mappings"][0]["span_idx"] == 2
    assert assembled.proposals[0]["role_relocated_mappings"] == [{
        "from": 1, "to": 2, "part_id": "concept:liable",
    }]


def test_llm_closed_predicate_binding_accepts_inflection_only_with_exact_structure(
        tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    monkeypatch.setattr(spanparts, "cached_term_lexicon", lambda: None)

    class InflectedPredicateLLM:
        def __init__(self, question):
            self.question = question

        def structured(self, kind, _system, _user, _schema, **_kwargs):
            if kind == "rag.oql.spans":
                values = [("금투사", "actor"), ("책임을 져야 하는가", "predicate")]
                if "시험법" in self.question:
                    values.extend([("시험법", "document"), ("제1조", "locator")])
                return {"spans": [
                    {"span": text, "start": self.question.index(text),
                     "end": self.question.index(text) + len(text), "role": role}
                    for text, role in values
                ]}
            if kind == "rag.oql.predicate":
                return {"verdict": "MATCH", "reason": "질문의 활용형"}
            return {"decision": "SELECT", "intent": "ASSERTION_BY_PARTS",
                    "mappings": [
                        {"span_idx": 1, "part_id": "concept:operator", "role": "actor"},
                        {"span_idx": 2, "part_id": "concept:liable", "role": "predicate"},
                    ]}

    scoped_question = "금투사가 책임을 져야 하는가? 시험법 제1조"
    scoped, scoped_meta = conceptfirst.retrieve(
        _index(), scoped_question, llm=InflectedPredicateLLM(scoped_question))
    assert len(scoped) == 1 and scoped[0].node == 1
    assert scoped_meta["oql"]["pattern"] == "assertion_by_parts"

    unscoped_question = "금투사가 책임을 져야 하는가?"
    unscoped, unscoped_meta = conceptfirst.retrieve(
        _index(), unscoped_question, llm=InflectedPredicateLLM(unscoped_question))
    assert unscoped == []
    assert "질문 술어" in unscoped_meta["fallback"]


def test_llm_low_similarity_predicate_needs_separate_semantic_match(
        tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    monkeypatch.setattr(spanparts, "cached_term_lexicon", lambda: None)
    question = "시험법 제1조에서 금투사가 투자설명서를 즉시 파기하여야 하나?"

    class WrongSemanticLLM:
        def structured(self, kind, _system, _user, _schema, **_kwargs):
            if kind == "rag.oql.spans":
                values = [
                    ("시험법", "document"), ("제1조", "locator"),
                    ("금투사", "actor"), ("투자설명서", "subject"),
                    ("즉시 파기하여야 하나", "predicate"),
                ]
                return {"spans": [
                    {"span": text, "start": question.index(text),
                     "end": question.index(text) + len(text), "role": role}
                    for text, role in values
                ]}
            if kind == "rag.oql.predicate":
                return {"verdict": "MISMATCH", "reason": "파기와 책임 부담은 다른 행위"}
            return {"decision": "SELECT", "intent": "ASSERTION_BY_PARTS",
                    "mappings": [
                        {"span_idx": 1, "part_id": "concept:operator", "role": "actor"},
                        {"span_idx": 2, "part_id": "concept:prospectus", "role": "subject"},
                        {"span_idx": 3, "part_id": "concept:liable", "role": "predicate"},
                    ]}

    sections, meta = conceptfirst.retrieve(
        _index(), question, llm=WrongSemanticLLM())

    assert sections == []
    verification = meta["parts"]["proposals"][0]["predicate_verification"]
    assert verification["verdict"] == "MISMATCH"


@pytest.mark.parametrize("verdict, expected", [
    ("MATCH", True),
    ("UNSURE", True),
    ("MISMATCH", False),
])
def test_predicate_semantic_gate_rejects_only_explicit_mismatch(verdict, expected):
    class VerdictLLM:
        def structured(self, *_args, **_kwargs):
            return {"verdict": verdict}

    accepted, audit = spanparts._predicate_semantics_match(
        VerdictLLM(), "계약을 성실하게 지켜야 하나?",
        [("성실하게 지켜야", "이행하여야")],
    )

    assert accepted is expected
    assert audit["verdict"] == verdict


def test_llm_no_match_can_use_exact_coordinate_and_inflected_cue_fallback(
        tmp_path, monkeypatch):
    blob = _blob()
    blob["assertions"][0]["query_cues"] = ["책임을 부담한다"]
    canonical, db = _built(tmp_path, monkeypatch, blob=blob)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    monkeypatch.setattr(spanparts, "cached_term_lexicon", lambda: None)

    class NoMatchLLM:
        def __init__(self, question):
            self.question = question

        def structured(self, kind, _system, _user, _schema, **_kwargs):
            if kind == "rag.oql.spans":
                values = [("시험법", "document"), ("제1조", "locator"),
                          ("금투사", "actor"), ("투자설명서", "subject")]
                return {"spans": [
                    {"span": text, "start": self.question.index(text),
                     "end": self.question.index(text) + len(text), "role": role}
                    for text, role in values
                ]}
            return {"decision": "NO_MATCH", "intent": "ASSERTION_BY_PARTS",
                    "mappings": []}

    positive_question = "시험법 제1조에서 금투사가 투자설명서 책임을 부담하는가?"
    sections, meta = conceptfirst.retrieve(
        _index(), positive_question, llm=NoMatchLLM(positive_question))
    assert len(sections) == 1 and sections[0].node == 1
    assert meta["parts"]["deterministic_fallback"] is True

    negative_question = "시험법 제1조에서 금투사가 투자설명서를 파기하는가?"
    sections, meta = conceptfirst.retrieve(
        _index(), negative_question, llm=NoMatchLLM(negative_question))
    assert sections == []
    assert "질문 술어" in meta["fallback"]


def test_llm_cannot_select_part_outside_span_menu(tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    monkeypatch.setattr(spanparts, "cached_term_lexicon", lambda: None)
    question = "금투사가 투자설명서 위반으로 지는 손해배상책임은 시험법 제1조에 있나?"

    sections, meta = conceptfirst.retrieve(
        _index(), question, llm=_PartLLM(question, bad_part=True))

    assert sections == []
    assert meta["parts"]["decision"] == "NO_MATCH"
    assert "부품 조립 결과 없음" in meta["fallback"]


def test_llm_general_relation_needs_no_predicate_span(tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    monkeypatch.setattr(spanparts, "cached_term_lexicon", lambda: None)
    question = "금투사와 투자설명서는 어떤 관계야?"

    class RelationLLM:
        def structured(self, kind, _system, _user, _schema, **_kwargs):
            if kind == "rag.oql.spans":
                return {"spans": [
                    {"span": "금투사", "start": 0, "end": 3, "role": "actor"},
                    {"span": "투자설명서", "start": 5, "end": 10, "role": "object"},
                ]}
            return {"decision": "SELECT", "intent": "ASSERTION_BY_PARTS", "mappings": [
                {"span_idx": 1, "part_id": "concept:operator", "role": "actor"},
                {"span_idx": 2, "part_id": "concept:prospectus", "role": "object"},
            ]}

    sections, meta = conceptfirst.retrieve(_index(), question, llm=RelationLLM())

    assert meta["oql"]["pattern"] == "assertion_by_parts"
    assert len(sections) == 1 and sections[0].node == 1


def test_llm_cannot_assign_action_to_non_predicate_role(tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    monkeypatch.setattr(spanparts, "cached_term_lexicon", lambda: None)
    question = "금투사가 투자설명서 위반으로 지는 손해배상책임은 시험법 제1조에 있나?"

    sections, meta = conceptfirst.retrieve(
        _index(), question, llm=_PartLLM(question, bad_role=True))

    assert sections == []
    assert meta["parts"]["decision"] == "NO_MATCH"


def test_composer_uses_one_closed_menu_without_expand_retry(tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    monkeypatch.setattr(spanparts, "cached_term_lexicon", lambda: None)
    question = "금투사가 투자설명서 위반으로 지는 손해배상책임은 시험법 제1조에 있나?"
    llm = _PartLLM(question)

    sections, meta = conceptfirst.retrieve(_index(), question, llm=llm)

    assert [kind for kind, _ in llm.calls] == ["rag.oql.spans", "rag.oql.compose"]
    assert spanparts._compose_schema(["concept:operator"])["properties"][
        "decision"]["enum"] == ["SELECT", "NO_MATCH"]
    assert len(sections) == 1 and sections[0].node == 1


def test_registry_role_normalizes_llm_query_grammar(tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    monkeypatch.setattr(spanparts, "cached_term_lexicon", lambda: None)
    question = "금투사가 투자설명서 위반으로 지는 손해배상책임은 시험법 제1조에 있나?"

    sections, meta = conceptfirst.retrieve(
        _index(), question, llm=_PartLLM(question, context_as_object=True))

    roles = {c["label"]: c["role"] for c in meta["alignment"]["selected"]}
    assert roles["투자설명서"] == "subject"
    assert len(sections) == 1 and sections[0].node == 1


def test_knowledge_document_span_is_not_dropped_as_source_document(tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    monkeypatch.setattr(spanparts, "cached_term_lexicon", lambda: None)
    question = "금투사가 투자설명서 위반으로 지는 손해배상책임은 시험법 제1조에 있나?"

    sections, meta = conceptfirst.retrieve(
        _index(), question, llm=_PartLLM(question, prospectus_document=True))

    assert any(menu["span"]["span"] == "투자설명서" for menu in meta["parts"]["menus"])
    assert len(sections) == 1 and sections[0].node == 1


def test_composer_keeps_best_grounded_subset_when_llm_overselects(tmp_path):
    blob = _blob()
    blob["concepts"].append({
        "id": "violate", "label": "위반하다", "type": "action",
        "status": "active", "approved_by": "tester",
    })
    blob["concepts"].append({
        "id": "send", "label": "전송하다", "type": "action",
        "status": "active", "approved_by": "tester",
    })
    blob["assertions"].append({
        "id": "other", "status": "active", "approved_by": "tester",
        "roles": {"ACTOR": "operator", "PREDICATE": "violate"},
        "source": {"doc_id": "d1", "node": 2}, "confidence": 0.8,
    })
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps(blob, ensure_ascii=False), encoding="utf-8")
    registry = Tier1Registry.load(path)
    spans = [
        spanparts.QuerySpan("금투사", 0, 3, "actor"),
        spanparts.QuerySpan("투자설명서 위반", 4, 12, "condition"),
        spanparts.QuerySpan("손해배상책임", 13, 19, "predicate"),
    ]

    def part(cid, label, ctype, score=1.0):
        return spanparts.Part(cid, label, ctype, label, "exact", score)

    menus = [
        spanparts.SpanMenu(spans[0], [
            part("concept:operator", "금융투자업자", "organization_role"),
        ]),
        spanparts.SpanMenu(spans[1], [
            part("concept:prospectus", "투자설명서", "document", 0.9),
            part("concept:violate", "위반하다", "action", 0.8),
        ]),
        spanparts.SpanMenu(spans[2], [
            part("concept:liable", "손해배상책임을 부담하다", "action"),
        ]),
    ]

    class OverselectLLM:
        def structured(self, *_args, **_kwargs):
            return {"decision": "SELECT", "intent": "ASSERTION_BY_PARTS", "mappings": [
                {"span_idx": 1, "part_id": "concept:operator", "role": "actor"},
                {"span_idx": 2, "part_id": "concept:prospectus", "role": "condition"},
                {"span_idx": 2, "part_id": "concept:violate", "role": "condition"},
                {"span_idx": 3, "part_id": "concept:liable", "role": "predicate"},
            ]}

    assembled = spanparts.compose(
        OverselectLLM(), registry, "금투사 투자설명서 위반 손해배상책임",
        spans, menus, spanparts.StructureAnchors(),
    )

    assert assembled.decision == "SELECT"
    assert {c.concept_id for c in assembled.alignment.selected} == {
        "concept:operator", "concept:prospectus", "concept:liable",
    }
    assert {c.role for c in assembled.alignment.selected} == {
        "actor", "subject", "predicate",
    }

    class WrongPredicateLLM:
        def structured(self, *_args, **_kwargs):
            return {"decision": "SELECT", "intent": "ASSERTION_BY_PARTS", "mappings": [
                {"span_idx": 1, "part_id": "concept:operator", "role": "actor"},
                {"span_idx": 2, "part_id": "concept:prospectus", "role": "object"},
                {"span_idx": 3, "part_id": "concept:send", "role": "predicate"},
            ]}

    wrong_spans = [
        spanparts.QuerySpan("금투사", 0, 3, "actor"),
        spanparts.QuerySpan("투자설명서", 4, 9, "object"),
        spanparts.QuerySpan("전송하다", 10, 14, "predicate"),
    ]
    wrong_menus = [
        menus[0],
        spanparts.SpanMenu(wrong_spans[1], [
            part("concept:prospectus", "투자설명서", "document"),
        ]),
        spanparts.SpanMenu(wrong_spans[2], [
            part("concept:send", "전송하다", "action"),
        ]),
    ]
    rejected = spanparts.compose(
        WrongPredicateLLM(), registry, "금투사가 투자설명서를 전송하다",
        wrong_spans, wrong_menus,
        spanparts.StructureAnchors(
            doc_ids=("d1",), documents=("시험법",), locators=("제1조",),
            source_coordinates=(("d1", 1),),
        ),
    )
    assert rejected.decision == "NO_MATCH"
    assert rejected.alignment.selected == []

    class NoMatchLLM:
        def structured(self, *_args, **_kwargs):
            return {"decision": "NO_MATCH", "intent": "ASSERTION_BY_PARTS",
                    "mappings": [
                        {"span_idx": 1, "part_id": "concept:operator", "role": "actor"},
                        {"span_idx": 2, "part_id": "concept:prospectus", "role": "object"},
                    ]}

    no_match = spanparts.compose(
        NoMatchLLM(), registry, "금투사가 투자설명서를 전송하다",
        wrong_spans, wrong_menus,
        spanparts.StructureAnchors(
            doc_ids=("d1",), documents=("시험법",), locators=("제1조",),
            source_coordinates=(("d1", 1),),
        ),
    )
    assert no_match.decision == "NO_MATCH"
    assert no_match.alignment.selected == []


def _structure_index():
    return Index.from_docs([
        ("privacy", {"name": "개인정보 보호법"}, {
            "nodes": [
                {"id": 10, "parent": None, "level": 0, "family": "kr_article",
                 "surface": "제18조", "title": "목적 외 이용ㆍ제공 제한",
                 "page": 1, "block": 0, "span": [0, 4]},
                {"id": 11, "parent": 10, "level": 1, "family": "kr_paragraph",
                 "surface": "제2항", "title": "제2항", "page": 1,
                 "block": 1, "span": [1, 4]},
                {"id": 12, "parent": 11, "level": 2, "family": "kr_subparagraph",
                 "surface": "제2호", "title": "제2호", "page": 1,
                 "block": 2, "span": [2, 4]},
                {"id": 13, "parent": 12, "level": 3, "family": "text",
                 "surface": "가목", "title": "가목", "page": 1,
                 "block": 3, "span": [3, 4]},
            ],
            "blocks": [
                {"idx": 0, "page": 1, "node": 10, "kind": "text", "text": "제18조"},
                {"idx": 1, "page": 1, "node": 11, "kind": "text", "text": "제2항"},
                {"idx": 2, "page": 1, "node": 12, "kind": "text", "text": "제2호"},
                {"idx": 3, "page": 1, "node": 13, "kind": "text", "text": "가목"},
            ],
        }),
        ("audit", {"name": "감사원법"}, {
            "nodes": [
                {"id": 20, "parent": None, "level": 0, "family": "kr_article",
                 "surface": "제5조", "title": "직무", "page": 1,
                 "block": 0, "span": [0, 1]},
            ],
            "blocks": [
                {"idx": 0, "page": 1, "node": 20, "kind": "text", "text": "제5조"},
            ],
        }),
    ])


def test_structure_resolves_full_chain_and_keeps_distinct_documents(monkeypatch):
    monkeypatch.setattr(spanparts.refs, "alias_map", lambda: {})
    anchors = spanparts.resolve_structure(
        _structure_index(),
        "「감사원법」 제5조와 「개인정보 보호법」 제18조제2항제2호를 비교해줘",
    )

    assert anchors.doc_ids == ("audit", "privacy")
    assert anchors.locators == ("제5조", "제18조제2항제2호")
    assert anchors.unresolved_locators == ()
    assert anchors.source_coordinates == (
        ("audit", 20), ("privacy", 12), ("privacy", 13),
    )


def test_structure_falls_back_to_unique_confirmed_document_for_generic_ref_hint(
        monkeypatch):
    monkeypatch.setattr(spanparts.refs, "alias_map", lambda: {})
    anchors = spanparts.resolve_structure(
        _structure_index(), "개인정보 보호법 제18조제2항제2호를 설명해줘")

    assert anchors.doc_ids == ("privacy",)
    assert anchors.unresolved_locators == ()
    assert anchors.source_coordinates == (("privacy", 12), ("privacy", 13))


def test_structure_resolves_locator_in_only_one_of_multiple_mentioned_documents(
        monkeypatch):
    monkeypatch.setattr(spanparts.refs, "alias_map", lambda: {})
    index = Index.from_docs([
        ("first", {"name": "첫째 법률"}, {
            "nodes": [{"id": 40, "parent": None, "level": 0,
                       "family": "kr_article", "surface": "제40조",
                       "title": "공개", "page": 1, "block": 0, "span": [0, 1]}],
            "blocks": [{"idx": 0, "page": 1, "node": 40,
                        "kind": "text", "text": "제40조 공개"}],
        }),
        ("second", {"name": "둘째 법률"}, {
            "nodes": [{"id": 5, "parent": None, "level": 0,
                       "family": "kr_article", "surface": "제5조",
                       "title": "인용", "page": 1, "block": 0, "span": [0, 1]}],
            "blocks": [{"idx": 0, "page": 1, "node": 5,
                        "kind": "text", "text": "제5조 인용"}],
        }),
    ])

    anchors = spanparts.resolve_structure(
        index, "첫째 법률 제40조에서 둘째 법률에 따라 공개하는가?")

    assert anchors.doc_ids == ("first", "second")
    assert anchors.unresolved_locators == ()
    assert anchors.source_coordinates == (("first", 40),)


def test_structure_resolves_dash_article_and_paragraph(monkeypatch):
    monkeypatch.setattr(spanparts.refs, "alias_map", lambda: {})
    index = Index.from_docs([("rule", {"name": "시험감독규정"}, {
        "nodes": [
            {"id": 40, "parent": None, "level": 0, "family": "kr_article",
             "surface": "제2-42조", "title": "감독", "ordinal": [2, 42],
             "page": 1, "block": 0, "span": [0, 3]},
            {"id": 41, "parent": 40, "level": 1, "family": "circled",
             "surface": "①", "title": "", "ordinal": [1],
             "page": 1, "block": 1, "span": [1, 2]},
            {"id": 42, "parent": 40, "level": 1, "family": "circled",
             "surface": "②", "title": "", "ordinal": [2],
             "page": 1, "block": 2, "span": [2, 3]},
        ],
        "blocks": [
            {"idx": 0, "page": 1, "node": 40, "kind": "text", "text": "감독"},
            {"idx": 1, "page": 1, "node": 41, "kind": "text", "text": "첫째"},
            {"idx": 2, "page": 1, "node": 42, "kind": "text", "text": "둘째"},
        ],
    })])

    anchors = spanparts.resolve_structure(
        index, "시험감독규정 제2-42조제2항에서 누가 감독하는가?")

    assert anchors.doc_ids == ("rule",)
    assert anchors.locators == ("제2-42조제2항",)
    assert anchors.unresolved_locators == ()
    assert anchors.source_coordinates == (("rule", 42),)


def test_structural_document_span_may_include_locator_without_becoming_concept(
        tmp_path):
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps(_blob(), ensure_ascii=False), encoding="utf-8")
    registry = Tier1Registry.load(path)
    question = "시험법 제1조에서 투자설명서를 확인한다"
    spans = [
        spanparts.QuerySpan("시험법 제1조", 0, 8, "document"),
        spanparts.QuerySpan("투자설명서", 10, 15, "document"),
    ]
    anchors = spanparts.StructureAnchors(
        doc_ids=("d1",), documents=("시험법",), locators=("제1조",),
        source_coordinates=(("d1", 1),),
    )

    menus = spanparts.PartRetriever(registry, _index(), lexicon=None).menus(
        spans, anchors)

    assert [menu.span.text for menu in menus] == ["투자설명서"]


def test_structure_does_not_guess_bare_locator_across_documents(monkeypatch):
    monkeypatch.setattr(spanparts.refs, "alias_map", lambda: {})
    anchors = spanparts.resolve_structure(_structure_index(), "제5조의 의무가 무엇인가?")

    assert anchors.source_coordinates == ()
    assert anchors.unresolved_locators == ("제5조",)


def test_deterministic_concept_entry_obeys_explicit_article(tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    monkeypatch.setattr(spanparts.refs, "alias_map", lambda: {})

    sections, meta = conceptfirst.retrieve(
        _index(), "시험법 제2조에서 금투사와 투자설명서는 어떤 관계야?",
    )

    assert sections == []
    assert meta["structure"]["locators"] == ["제2조"]
    assert meta["structure"]["unresolved_locators"] == ["제2조"]
    assert "구조 좌표" in meta["fallback"]
