import json

from lawrag.core.domain_graph.approval import approve
from lawrag.core.domain_graph.builder import GraphBuilder
from lawrag.core.domain_graph.candidates import (
    stage_frame_concepts,
    stage_frame_knowledge,
    stage_grade2,
    stage_normative_concepts,
)
from lawrag.core.domain_graph.normative import (
    promote_candidate_blob,
    promote_registry_blob,
)
from lawrag.core.domain_graph.canonical import CanonicalRegistry
from lawrag.core.domain_graph.store import GraphStore
from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.rag.index import Index


class FakeLLM:
    model = "fake-approver"

    def __init__(self, reject=""):
        self.reject = reject

    def structured(self, _kind, _system, user, schema, **_kwargs):
        assert "원문/골든 없음" in user
        keys = schema["properties"]["decisions"]["items"]["properties"]["item_key"]["enum"]
        return {"decisions": [{"item_key": k,
                               "decision": "reject" if k == self.reject else "approve",
                               "confidence": "high", "reason": "후보 구조가 명확함"}
                              for k in keys]}


def _index():
    return Index.from_docs([("d1", {"name": "시험법"}, {
        "nodes": [{"id": 1, "parent": None, "level": 0, "family": "kr_article",
                   "surface": "제1조", "title": "책임", "ordinal": [1],
                   "page": 1, "block": 0, "span": [0, 1]}],
        "blocks": [{"idx": 0, "page": 1, "node": 1, "kind": "text", "text": "책임"}],
    })])


def _candidate(tmp_path):
    blob = {"schema_version": 1, "concepts": [
        {"id": "actor", "label": "사업자", "type": "organization_role",
         "status": "reviewed"},
        {"id": "liable", "label": "책임을 부담하다", "type": "action",
         "status": "reviewed"},
    ], "relations": [], "assertions": [{
        "id": "as01", "status": "reviewed", "roles": {"ACTOR": "actor",
        "PREDICATE": "liable"}, "source": {"doc_id": "d1", "node": 1},
        "confidence": 0.9,
    }]}
    p = tmp_path / "candidate.json"
    p.write_text(json.dumps(blob, ensure_ascii=False), encoding="utf-8")
    return p


def _graph(tmp_path):
    glossary = tmp_path / "glossary.json"
    glossary.write_text('{"terms": []}', encoding="utf-8")
    candidate = _candidate(tmp_path)
    registry = CanonicalRegistry.load(registry_path=candidate, glossary_path=glossary)
    db = tmp_path / "graph.sqlite"
    GraphBuilder(_index(), data_dir=tmp_path, registry=registry,
                 glossary_path=glossary).build(db, include_derived=False)
    return candidate, db


def test_llm_only_decides_and_code_publishes_valid_dependencies(tmp_path):
    candidate, db = _graph(tmp_path)
    output, audit = tmp_path / "approved.json", tmp_path / "audit.json"
    report = approve(FakeLLM(), candidate, db, output, audit, batch_size=1, workers=2)
    registry = Tier1Registry.load(output)
    assert len(registry.active_concepts) == 2
    assert len(registry.active_assertions) == 1
    assert all(c.approved_by == "llm:fake-approver" for c in registry.active_concepts.values())
    ledger = json.loads(candidate.read_text(encoding="utf-8"))
    assert {c["candidate_status"] for c in ledger["concepts"]} == {"approved"}
    assert ledger["assertions"][0]["approval"]["validation"] == "통과"
    assert report["input_policy"].endswith("no golden")


def test_rejected_concept_prevents_dependent_assertion_publication(tmp_path):
    candidate, db = _graph(tmp_path)
    output, audit = tmp_path / "approved.json", tmp_path / "audit.json"
    approve(FakeLLM(reject="concept:actor"), candidate, db, output, audit)
    registry = Tier1Registry.load(output)
    assert "concept:actor" not in registry.active_concepts
    assert set(registry.active_concepts) == {"concept:liable"}
    assert registry.active_assertions == []
    ledger = json.loads(candidate.read_text(encoding="utf-8"))
    assert ledger["concepts"][0]["candidate_status"] == "rejected"
    assert ledger["assertions"][0]["candidate_status"] == "deferred"
    assert ledger["assertions"][0]["approval"]["validation"] == "의존 Concept 미승인"

    # 같은 정보로 다음 승인 국면을 열 때 보류 후보를 자동 재호출하거나 기존
    # 판정 사유를 지우지 않는다.
    before = ledger["assertions"][0]["approval"]
    approve(FakeLLM(), candidate, db, output, audit)
    ledger = json.loads(candidate.read_text(encoding="utf-8"))
    assert ledger["assertions"][0]["approval"]["decision"] == before["decision"]
    assert ledger["assertions"][0]["approval"]["reason"] == before["reason"]


def test_force_all_reopens_rejected_and_deferred_without_llm(tmp_path):
    candidate, db = _graph(tmp_path)
    output, audit = tmp_path / "approved.json", tmp_path / "audit.json"
    approve(FakeLLM(reject="concept:actor"), candidate, db, output, audit)

    report = approve(None, candidate, db, output, audit, force_all=True)
    registry = Tier1Registry.load(output)
    ledger = json.loads(candidate.read_text(encoding="utf-8"))

    assert set(registry.active_concepts) == {"concept:actor", "concept:liable"}
    assert len(registry.active_assertions) == 1
    assert {row["candidate_status"] for row in ledger["concepts"]} == {"approved"}
    assert ledger["assertions"][0]["candidate_status"] == "approved"
    assert all(c.approved_by == "user:force-all"
               for c in registry.active_concepts.values())
    assert {c.review_state for c in registry.active_concepts.values()} == {
        "batch_accepted"}
    assert registry.active_assertions[0].review_state == "batch_accepted"
    canonical = json.loads(output.read_text(encoding="utf-8"))
    assert {row["review_state"] for row in canonical["concepts"]} == {
        "batch_accepted"}
    assert all(row["evidence_type"] == "candidate_pipeline"
               for row in canonical["concepts"])
    assert report["force_all"] is True
    assert report["input_policy"].startswith("user-authorized")


def test_grade2_concepts_are_staged_without_semantic_decision(tmp_path):
    candidate, db = _graph(tmp_path)
    empty_queue = tmp_path / "queue.json"
    empty_queue.write_text('{"schema_version":1,"concepts":[],"relations":[],"assertions":[]}',
                           encoding="utf-8")
    empty_canonical = tmp_path / "canonical.json"
    empty_canonical.write_text('{"schema_version":1,"concepts":[],"relations":[],"assertions":[]}',
                               encoding="utf-8")
    report = stage_grade2(db, empty_queue, empty_canonical)
    rows = json.loads(empty_queue.read_text(encoding="utf-8"))["concepts"]
    assert report["staged"] == 2
    assert {r["candidate_status"] for r in rows} == {"pending"}
    assert {r["candidate_basis"]["knowledge_grade"] for r in rows} == {2}


def test_frame_slots_stage_concepts_then_build_grounded_assertion(tmp_path):
    data = tmp_path / "domain_graph"
    data.mkdir()
    canonical = data / "canonical.json"
    canonical.write_text(json.dumps({
        "schema_version": 1,
        "concepts": [
            {"id": "operator", "label": "금융투자업자", "type": "organization_role",
             "status": "active", "approved_by": "test"},
            {"id": "deliver", "label": "교부하다", "type": "action",
             "status": "active", "approved_by": "test"},
            {"id": "prospectus", "label": "투자설명서", "type": "document",
             "status": "active", "approved_by": "test"},
        ], "relations": [], "assertions": [],
    }, ensure_ascii=False), encoding="utf-8")
    queue = data / "candidates.json"
    queue.write_text('{"schema_version":1,"concepts":[],"relations":[],"assertions":[]}',
                     encoding="utf-8")
    glossary = tmp_path / "glossary.json"
    glossary.write_text('{"terms": []}', encoding="utf-8")
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "d1.jsonl").write_text(json.dumps({
        "jo": 1, "node": 1, "actor": "금융투자업자", "act": "교부하다",
        "object": "투자설명서", "target": "일반청약자",
        "mode": "의무", "function": "절차", "proviso": False,
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    registry = CanonicalRegistry.load(registry_path=canonical, glossary_path=glossary)
    db = data / "graph.sqlite"
    GraphBuilder(_index(), data_dir=tmp_path, registry=registry,
                 glossary_path=glossary).build(db)

    staged = stage_frame_concepts(db, queue, canonical)
    rows = json.loads(queue.read_text(encoding="utf-8"))["concepts"]
    assert staged["staged"] == 1
    assert rows[0]["label"] == "일반청약자"
    assert rows[0]["candidate_basis"]["role"] == "HAS_TARGET"

    knowledge = stage_frame_knowledge(db, queue, canonical)
    assertions = json.loads(queue.read_text(encoding="utf-8"))["assertions"]
    assert knowledge["staged_assertions"] == 1
    assert assertions[0]["roles"] == {
        "ACTOR": ["concept:operator"],
        "PREDICATE": ["concept:deliver"],
        "OBJECT": ["concept:prospectus"],
    }
    assert assertions[0]["query_cues"] == ["교부하다"]


def test_normative_axes_stage_then_promote_approved_frame_metadata(tmp_path):
    canonical = tmp_path / "canonical.json"
    canonical.write_text(json.dumps({
        "schema_version": 1,
        "concepts": [
            {"id": "company", "label": "회사", "type": "organization_role",
             "status": "active", "approved_by": "test"},
            {"id": "retire", "label": "소각", "type": "action",
             "status": "active", "approved_by": "test"},
        ],
        "relations": [],
        "assertions": [{
            "id": "assertion:retire", "status": "active",
            "roles": {"ACTOR": ["concept:company"],
                      "PREDICATE": ["concept:retire"]},
            "source": {"doc_id": "d1", "node": 1},
            "approved_by": "test",
            "candidate_basis": {"source": "llm_frame", "mode": "의무",
                                "function": "제한"},
        }],
    }, ensure_ascii=False), encoding="utf-8")
    queue = tmp_path / "candidates.json"
    queue.write_text(
        '{"schema_version":1,"concepts":[],"relations":[],"assertions":[]}',
        encoding="utf-8")

    staged = stage_normative_concepts(queue, canonical)
    candidates = json.loads(queue.read_text(encoding="utf-8"))["concepts"]
    assert staged["staged"] == 15
    assert {row["type"] for row in candidates} == {"modality", "norm_function"}

    blob = json.loads(canonical.read_text(encoding="utf-8"))
    report = promote_registry_blob(blob, approved_by="user:test")
    assertion = blob["assertions"][0]
    assert report == {
        "added_concepts": 15,
        "updated_assertions": 1,
        "role_edges": {"MODALITY": 1, "FUNCTION": 1},
    }
    assert assertion["roles"]["MODALITY"] == [
        "concept:norm.modality.obligation"]
    assert assertion["roles"]["FUNCTION"] == [
        "concept:norm.function.restriction"]
    candidate_report = promote_candidate_blob(
        {"concepts": [], "assertions": [blob["assertions"][0]]},
        approved_by="user:test")
    assert candidate_report["added_concepts"] == 15
    Tier1Registry.load(canonical)  # 원본 파일은 아직 미변경
    promoted = tmp_path / "promoted.json"
    promoted.write_text(json.dumps(blob, ensure_ascii=False), encoding="utf-8")
    Tier1Registry.load(promoted)


def test_tier1_props_win_over_derived_concept_on_rebuild(tmp_path):
    data = tmp_path / "domain_graph"
    data.mkdir()
    canonical = data / "canonical.json"
    canonical.write_text(json.dumps({
        "schema_version": 1,
        "concepts": [{"id": "operator", "label": "금융투자업자",
                      "type": "organization_role", "status": "active",
                      "approved_by": "test"}],
        "relations": [], "assertions": [],
    }, ensure_ascii=False), encoding="utf-8")
    glossary = tmp_path / "glossary.json"
    glossary.write_text('{"terms": []}', encoding="utf-8")
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "d1.jsonl").write_text(json.dumps({
        "jo": 1, "node": 1, "actor": "금융투자업자", "act": "",
        "object": "", "target": "", "mode": "기타", "function": "기타",
        "proviso": False,
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    registry = CanonicalRegistry.load(registry_path=canonical, glossary_path=glossary)
    db = data / "graph.sqlite"
    GraphBuilder(_index(), data_dir=tmp_path, registry=registry,
                 glossary_path=glossary).build(db)
    with GraphStore(db, readonly=True) as store:
        concept = store.get_node("concept:operator")
    assert concept["props"]["knowledge_grade"] == 1
    assert concept["props"]["concept_type"] == "organization_role"


def test_is_a_cycle_is_deferred_at_publication_gate(tmp_path):
    candidate, db = _graph(tmp_path)
    blob = json.loads(candidate.read_text(encoding="utf-8"))
    evidence = [{"doc_id": "d1", "node": 1}]
    blob["relations"] = [
        {"id": "r_ab", "type": "IS_A", "src": "actor", "dst": "liable",
         "evidence": evidence},
        {"id": "r_ba", "type": "IS_A", "src": "liable", "dst": "actor",
         "evidence": evidence},
    ]
    candidate.write_text(json.dumps(blob, ensure_ascii=False), encoding="utf-8")
    output, audit = tmp_path / "approved.json", tmp_path / "audit.json"
    approve(FakeLLM(), candidate, db, output, audit)
    registry = Tier1Registry.load(output)
    assert len(registry.active_relations) == 1
    ledger = json.loads(candidate.read_text(encoding="utf-8"))
    assert [r["approval"]["validation"] for r in ledger["relations"]] == [
        "통과", "IS_A 순환"]
