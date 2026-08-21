import json

import pytest

from lawrag.core.domain_graph import oql
from lawrag.core.domain_graph.alignment import ConceptAligner
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
             "aliases": ["금투사"], "status": "active", "approved_by": "tester"},
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


def _built(tmp_path, monkeypatch):
    canonical = tmp_path / "domain_graph" / "canonical.json"
    canonical.parent.mkdir()
    canonical.write_text(json.dumps(_blob(), ensure_ascii=False), encoding="utf-8")
    glossary = tmp_path / "glossary.json"
    glossary.write_text('{"terms": []}', encoding="utf-8")
    delegation = tmp_path / "delegation.json"
    delegation.write_text('{"edges": []}', encoding="utf-8")
    monkeypatch.setenv("RAG_DELEGATION_STORE", str(delegation))
    db = canonical.parent / "graph.sqlite"
    registry = CanonicalRegistry.load(registry_path=canonical, glossary_path=glossary)
    GraphBuilder(_index(), data_dir=tmp_path, registry=registry,
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


def test_existing_vecfirst_starts_with_concept_and_keeps_fallback(tmp_path, monkeypatch):
    canonical, db = _built(tmp_path, monkeypatch)
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(canonical))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(db))
    monkeypatch.setattr(vector, "search", lambda *_a, **_k: [])

    sections, meta = vecfirst.retrieve(
        _index(), "금투사와 투자설명서의 관계", entry_k=0, llm=None,
        raw_query="금투사와 투자설명서의 관계")
    assert sections[0].kind == "Concept"
    assert sections[0].node == 1
    assert meta["concept"]["oql"]["pattern"] == "relation_between_concepts"
    assert meta["concept_hits"]


def test_conceptfirst_fails_open_when_registry_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_CONCEPT_REGISTRY", str(tmp_path / "missing.json"))
    monkeypatch.setenv("RAG_DOMAIN_GRAPH", str(tmp_path / "missing.sqlite"))
    sections, meta = conceptfirst.retrieve(_index(), "아무 질문")
    assert sections == []
    assert meta["fallback"]
