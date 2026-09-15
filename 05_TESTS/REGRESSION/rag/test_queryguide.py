"""DB 역매칭 해석 후보와 기존 좌표 교집합의 결합 계약."""

from __future__ import annotations

import json
import re

from lawrag.core.domain_graph import spanparts
from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.rag import landings, queryguide
from lawrag.core.rag.index import Index


def _registry(tmp_path, concepts, assertions):
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps({
        "schema_version": 1, "concepts": concepts, "relations": [],
        "assertions": assertions,
    }, ensure_ascii=False), encoding="utf-8")
    return Tier1Registry.load(path)


def _doc(doc_id, name, *, title="책임", body="본문"):
    return doc_id, {"name": name}, {"nodes": [{
        "id": 1, "parent": None, "level": 0, "family": "kr_article",
        "surface": "제1조", "title": title, "ordinal": [1],
        "page": 1, "block": 0, "span": [0, 1],
    }], "blocks": [{
        "idx": 0, "page": 1, "node": 1, "kind": "text", "text": body,
    }]}


def _ambiguous_data(tmp_path):
    concepts = [
        {"id": "law-actor", "label": "시험법", "type": "organization_role",
         "status": "active", "approved_by": "tester"},
        {"id": "report", "label": "신고하다", "aliases": ["신고하나"],
         "type": "action", "status": "active", "approved_by": "tester"},
    ]
    assertions = [{
        "id": "a-second", "status": "active", "approved_by": "tester",
        "roles": {"ACTOR": "law-actor", "PREDICATE": "report"},
        "source": {"doc_id": "d2", "node": 1}, "query_cues": ["신고하나"],
    }]
    registry = _registry(tmp_path, concepts, assertions)
    index = Index.from_docs([
        _doc("d1", "시험법", title="무관 조", body="서로 무관한 문서다."),
        _doc("d2", "둘째법", title="신고", body="시험법은 신고하여야 한다."),
    ])
    return index, registry


def test_same_query_surface_exposes_document_and_concept_as_or_readings(tmp_path):
    index, registry = _ambiguous_data(tmp_path)
    question = "시험법은 신고하나?"
    anchors = spanparts.resolve_structure(index, question)

    guide = queryguide.build(index, question, registry, anchors)
    rows = [row for row in guide.readings if row.surface == "시험법"]

    assert {row.object_kind for row in rows} >= {"document", "concept"}
    assert {row.object_id for row in rows} >= {"document:d1", "concept:law-actor"}
    assert {(row.start, row.end) for row in rows} == {(0, 3)}
    assert "같은 M 안의 G들은 서로 다른 해석(OR)" in guide.as_prompt()


class _ChooseConceptLLM:
    model = "fake"

    def __init__(self, question):
        self.question = question
        self.calls = []
        self.span_prompt = ""
        self.span_schema = {}

    @staticmethod
    def _guide_id(user, kind, label):
        pattern = rf"- (QG\d+) \| {kind} \| {re.escape(label)} \|"
        match = re.search(pattern, user)
        assert match, (kind, label, user)
        return match.group(1)

    def structured(self, kind, _system, user, schema, **_kwargs):
        self.calls.append(kind)
        if kind != "rag.oql.spans":
            raise AssertionError(f"가이드가 고른 exact 객체에 추가 메뉴 호출: {kind}")
        self.span_prompt, self.span_schema = user, schema
        actor_id = self._guide_id(user, "concept", "시험법")
        return {"spans": [
            {"span": "시험법", "start": 0, "end": 3, "role": "actor",
             "reading_ids": [actor_id]},
            {"span": "신고하나", "start": 5, "end": 9, "role": "predicate",
             # 최초 문서 스코프 밖이라 가이드에는 없지만 기존 자유 Span 분해의
             # 합집합 경로로 살아 있고, 문서 해석이 해제된 뒤 전역 exact에 착지한다.
             "reading_ids": []},
        ]}


def test_llm_concept_reading_removes_ambiguous_document_scope_and_finds_other_doc(
        tmp_path, monkeypatch):
    index, registry = _ambiguous_data(tmp_path)
    question = "시험법은 신고하나?"
    llm = _ChooseConceptLLM(question)
    monkeypatch.setenv("RAG_QUERY_GUIDE", "1")

    sections, meta = landings.retrieve(
        index, question, registry, llm=llm, lexicon=False,
        propose_terms=False,
    )

    assert [(section.doc_id, section.node) for section in sections] == [("d2", 1)]
    assert meta["structure"]["doc_ids"] == []
    assert meta["query_guide"]["enabled"] is True
    assert {row["object_kind"] for row in meta["query_guide"]["selected"]} == {
        "concept"
    }
    concept_routes = [row["via"] for row in meta["landings"]
                      if row["object_kind"] == "concept"]
    assert any(route.startswith("query-guide:concept-surface")
               for route in concept_routes)
    assert any(route.startswith("exact") for route in concept_routes)
    item = llm.span_schema["properties"]["spans"]["items"]
    assert "reading_ids" in item["required"]
    assert "[DB 역매칭 해석 후보]" in llm.span_prompt
    assert llm.calls == ["rag.oql.spans"]


def test_unseen_abbreviation_gets_closed_document_candidates_not_a_fake_alias(tmp_path):
    registry = _registry(tmp_path, [{
        "id": "act", "label": "배상하다", "type": "action",
        "status": "active", "approved_by": "tester",
    }], [{
        "id": "assertion-a1", "status": "active", "approved_by": "tester",
        "roles": {"PREDICATE": "act"}, "source": {"doc_id": "d1", "node": 1},
    }])
    index = Index.from_docs([
        _doc("d1", "자본시장과 금융투자업에 관한 법률"),
        _doc("d2", "상법"),
    ])
    question = "금투법 제1조"

    guide = queryguide.build(
        index, question, registry, spanparts.resolve_structure(index, question))
    docs = [row for row in guide.readings
            if row.surface == "금투법" and row.object_kind == "document"]

    assert docs
    assert docs[0].object_id == "document:d1"
    assert docs[0].via == "document-closed-candidate"
    # 후보 제시는 발행이 아니다. 승인 약칭 사전에는 여전히 없는 표면이다.
    assert "금투법" not in refs_alias_keys()


def refs_alias_keys():
    from lawrag.core.rag import refs

    return set(refs.alias_map())
