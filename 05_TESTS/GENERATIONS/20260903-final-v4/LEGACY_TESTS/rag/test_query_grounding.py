import json

from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.rag import query_grounding as grounding
from lawrag.core.rag.index import Index


def _mention(question="금융회사가 심사업무를 위탁할 수 있나"):
    surface = "금융회사"
    return {
        "id": "m1",
        "surface": surface,
        "start": question.index(surface),
        "end": question.index(surface) + len(surface),
        "role": "SOURCE_ACTOR",
        "source": "QUESTION_SPAN",
    }


def test_anchor_mentions_round_trips_and_rejects_unanchored_values():
    question = "금융회사가 심사업무를 외부 기관에 위탁할 수 있나"
    accepted, rejected = grounding.anchor_mentions(question, [
        {"surface": "금융회사", "start": 0, "end": 4,
         "role": "SOURCE_ACTOR"},
        {"surface": "심사업무", "start": 999, "end": 1003,
         "role": "OBJECT"},
        {"surface": "감독기관", "start": 0, "end": 4,
         "role": "TARGET_ACTOR"},
    ])

    assert [row["surface"] for row in accepted] == ["금융회사", "심사업무"]
    assert accepted[0]["offset_recovered"] is False
    assert accepted[1]["offset_recovered"] is True
    assert all(question[row["start"]:row["end"]] == row["surface"]
               for row in accepted)
    assert rejected == [{
        "surface": "감독기관",
        "role": "TARGET_ACTOR",
        "reason": "surface_not_in_question",
    }]


def test_anchor_mentions_rejects_ambiguous_recovery_but_accepts_exact_offsets():
    question = "회사는 회사에 업무를 위탁한다"
    second = question.rindex("회사")
    accepted, rejected = grounding.anchor_mentions(question, [
        {"surface": "회사", "start": 99, "end": 101, "role": "SOURCE_ACTOR"},
        {"surface": "회사", "start": second, "end": second + 2,
         "role": "TARGET_ACTOR"},
    ])

    assert [(row["start"], row["role"]) for row in accepted] == [
        (second, "TARGET_ACTOR")
    ]
    assert rejected[0]["reason"] == "ambiguous_surface_offset"


def test_sanitize_plan_keeps_expansions_separate_from_anchored_mentions():
    question = "업무를 위탁할 수 있나"
    plan = grounding.sanitize_plan(question, {
        "mentions": [
            {"surface": "업무", "start": 0, "end": 2, "role": "OBJECT"},
            {"surface": "수탁자", "start": 0, "end": 3, "role": "TARGET_ACTOR"},
        ],
        "family_hypotheses": [
            {"family_id": "ENTRUSTMENT", "reason": "업무 위탁"},
            {"family_id": "NOT_A_FAMILY", "reason": "invalid"},
        ],
        "predicate_hypotheses": [
            {"predicate": "ENTRUSTS_TASK", "reason": "위탁"},
            {"predicate": "MADE_UP", "reason": "invalid"},
        ],
        "exact_terms": ["업무위탁", "업무위탁"],
        "fulltext_queries": ["업무를 제3자에게 위탁할 수 있다"],
        "vector_queries": ["외부 수행 구조"],
    })

    assert [row["surface"] for row in plan["mentions"]] == ["업무"]
    assert plan["rejected_mentions"][0]["surface"] == "수탁자"
    assert [row["family_id"] for row in plan["family_hypotheses"]] == [
        "ENTRUSTMENT"
    ]
    assert [row["predicate"] for row in plan["predicate_hypotheses"]] == [
        "ENTRUSTS_TASK"
    ]
    assert plan["expansion_terms"]["exact"] == ["업무위탁"]


def test_planner_explicitly_pins_product_model():
    class FakeLLM:
        def __init__(self):
            self.kwargs = None

        def structured(self, _kind, _system, _user, _schema, **kwargs):
            self.kwargs = kwargs
            return {
                "mentions": [], "family_hypotheses": [],
                "predicate_hypotheses": [], "exact_terms": [],
                "fulltext_queries": [], "vector_queries": [],
            }

    llm = FakeLLM()
    grounding.plan_query(llm, "질문")
    assert llm.kwargs["model"] == grounding.GROUNDING_MODEL
    grounding.plan_query(llm, "질문", model="qwen-onsite")
    assert llm.kwargs["model"] == "qwen-onsite"


def test_binding_schema_is_closed_over_materialized_candidate_ids():
    schema = grounding.binding_schema(["concept:company", "evidence:article"])
    enum = schema["properties"]["evidence_selections"]["items"]["properties"][
        "candidate_id"
    ]["enum"]
    assert enum == ["concept:company", "evidence:article"]


def test_empty_binding_schema_uses_empty_arrays_without_fake_ids():
    schema = grounding.binding_schema([], [])
    rendered = str(schema)
    assert "__NO_CANDIDATE__" not in rendered
    assert "__NO_MENTION__" not in rendered
    for key in (
        "concept_bindings", "assertion_selections", "evidence_selections",
        "unresolved_mention_ids",
    ):
        assert schema["properties"][key]["maxItems"] == 0


def test_validate_bindings_separates_canonical_and_evidence_candidates():
    mention = _mention()
    common = {
        "doc": "법령",
        "path": "제1조",
        "score": 10.0,
        "channels": ["reverse"],
    }
    menu = [
        {
            **common,
            "id": "wrapper:company",
            "candidate_kind": "TIER1_CONCEPT",
            "canonical_id": "concept:company",
            "coordinate": ["doc", 1],
            "coordinates": [["doc", 1], ["doc", 2]],
            "source_mention_ids": [mention["id"]],
            "allowed_mention_roles": ["SOURCE_ACTOR"],
            "assertion_role": "ACTOR",
            "assertion_ids": ["assertion:company"],
            "signature_status": "SIGNATURE_COMPATIBLE",
        },
        {
            **common,
            "id": "evidence:article",
            "candidate_kind": "EVIDENCE_COORDINATE",
            "coordinate": ["doc", 3],
            "coordinates": [["doc", 3]],
            "signature_status": "SIGNATURE_UNVERIFIED",
        },
        {
            **common,
            "id": "evidence:wrong-signature",
            "candidate_kind": "EVIDENCE_COORDINATE",
            "coordinate": ["doc", 4],
            "coordinates": [["doc", 4]],
            "signature_status": "SIGNATURE_INCOMPATIBLE",
        },
    ]
    raw = {
        "concept_bindings": [
            {"candidate_id": "wrapper:company",
             "confidence": "HIGH", "reason": "원문 주체"},
            {"candidate_id": "concept:invented",
             "confidence": "HIGH", "reason": "메뉴 밖"},
        ],
        "assertion_selections": [],
        "evidence_selections": [
            {"candidate_id": "evidence:article", "mention_ids": [],
             "roles": [], "predicates": [], "confidence": "MEDIUM",
             "reason": "근거 조문"},
            {"candidate_id": "evidence:wrong-signature", "mention_ids": [],
             "roles": [], "predicates": [], "confidence": "LOW",
             "reason": "잘못된 축"},
        ],
        "unresolved_mention_ids": ["not-a-mention"],
    }

    result = grounding.validate_bindings(raw, menu, [mention])

    assert [row["candidate_id"] for row in result["concept_bindings"]] == [
        "wrapper:company"
    ]
    assert [row["candidate_id"] for row in result["validated"]] == [
        "evidence:article"
    ]
    assert result["menu_external_id_count"] == 1
    assert result["signature_rejection_count"] == 1


def test_canonical_binding_requires_its_anchored_mention():
    mention = _mention()
    menu = [{
        "id": "wrapper:company",
        "candidate_kind": "TIER1_CONCEPT",
        "canonical_id": "concept:company",
        "coordinate": ["doc", 1],
        "coordinates": [["doc", 1]],
        "source_mention_ids": [mention["id"]],
        "allowed_mention_roles": ["SOURCE_ACTOR"],
        "assertion_role": "ACTOR",
        "assertion_ids": ["assertion:company"],
        "signature_status": "SIGNATURE_COMPATIBLE",
        "score": 1.0,
    }]
    menu[0]["source_mention_ids"] = []
    raw = {"concept_bindings": [{
        "candidate_id": "wrapper:company",
        "confidence": "HIGH",
        "reason": "anchor omitted",
    }], "assertion_selections": [], "evidence_selections": [],
        "unresolved_mention_ids": []}

    result = grounding.validate_bindings(raw, menu, [mention])

    assert result["concept_bindings"] == []
    assert result["rejected"][0]["reason"] == (
        "missing_anchored_mention"
    )


def test_non_overlapping_incomplete_semantic_metadata_is_unverified_not_negative():
    plan = {
        "family_hypotheses": [{"family_id": "AUTHORITY"}],
        "predicate_hypotheses": [{
            "predicate": "DELEGATES_ADMINISTRATIVE_AUTHORITY"
        }],
    }
    assert grounding._signature_status(
        {"TEMPORAL"}, {"APPLIES_MUTATIS_MUTANDIS"},
        {"TEMPORAL_CONSTRAINT"}, plan,
    ) == "SIGNATURE_UNVERIFIED"


def test_canonical_candidate_keeps_assertion_role_coordinate_provenance(
        tmp_path, monkeypatch):
    canonical = tmp_path / "canonical.json"
    canonical.write_text(json.dumps({
        "schema_version": 1,
        "concepts": [
            {"id": "company", "label": "회사", "type": "organization_role",
             "status": "active", "approved_by": "tester"},
            {"id": "act", "label": "행위하다", "type": "action",
             "status": "active", "approved_by": "tester"},
        ],
        "relations": [],
        "assertions": [
            {"id": "actor-rule", "status": "active", "approved_by": "tester",
             "roles": {"ACTOR": "company", "PREDICATE": "act"},
             "source": {"doc_id": "actor-doc", "node": 1}},
            {"id": "object-rule", "status": "active", "approved_by": "tester",
             "roles": {"OBJECT": "company", "PREDICATE": "act"},
             "source": {"doc_id": "object-doc", "node": 1}},
        ],
    }), encoding="utf-8")
    registry = Tier1Registry.load(canonical)

    def doc(doc_id):
        return doc_id, {"name": doc_id}, {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": "제1조", "title": "회사", "span": [0, 1]}],
            "blocks": [{"idx": 0, "node": 1, "kind": "text", "text": "회사"}],
        }

    index = Index.from_docs([doc("actor-doc"), doc("object-doc")])
    monkeypatch.setattr(grounding.spanparts, "cached_term_lexicon", lambda: None)
    candidates = grounding._generate_canonical_candidates(
        index,
        registry,
        {"mentions": [{"id": "m1", "surface": "회사",
                        "role": "SOURCE_ACTOR"}]},
        {},
    )

    assert len(candidates) == 1
    assert candidates[0]["canonical_id"] == "concept:company"
    assert candidates[0]["assertion_role"] == "ACTOR"
    assert candidates[0]["coordinates"] == [["actor-doc", 1]]


def test_insert_grounded_seeds_preserves_parent_prefix_and_deduplicates():
    parent = [("doc", number) for number in range(1, 6)]
    result = grounding.insert_grounded_seeds(
        parent,
        [("doc", 2), ("other", 7), ("other", 7), ("other", 8)],
        protected_prefix=3,
        seed_cap=2,
    )
    assert result == [
        ("doc", 1), ("doc", 2), ("doc", 3),
        ("other", 7), ("other", 8),
        ("doc", 4), ("doc", 5),
    ]


def test_incremental_grounding_uses_index_reverse_without_duplicate_heavy_channels(
        monkeypatch):
    index = Index.from_docs([(
        "law-a",
        {"name": "법률 A", "kind": "law", "status": "현행"},
        {
            "nodes": [{
                "id": 1, "parent": None, "level": 1,
                "family": "kr_article", "surface": "제1조",
                "title": "업무위탁", "span": [0, 1],
            }],
            "blocks": [{"idx": 0, "kind": "text", "text": "업무위탁 기준"}],
        },
    )])

    class EmptySnapshot:
        @staticmethod
        def semantics_for_article(_coordinate):
            return ()

        @staticmethod
        def incident(_coordinate, *, direction):
            return ()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("incremental route invoked a duplicate heavy channel")

    monkeypatch.setattr(grounding.lexicon_mod, "current", forbidden)
    monkeypatch.setattr(grounding.recover, "rung_fulltext", forbidden)
    monkeypatch.setattr(grounding.vector_mod, "search", forbidden)
    monkeypatch.setattr(grounding.spanparts, "cached_term_lexicon", forbidden)

    result = grounding.generate_candidates(
        index,
        EmptySnapshot(),
        None,
        "업무위탁이 가능한가",
        {
            "mentions": [],
            "family_hypotheses": [],
            "predicate_hypotheses": [],
            "expansion_terms": {
                "exact": [], "fulltext": ["호출 금지"], "vector": ["호출 금지"],
            },
        },
        include_vector=False,
        include_fulltext=False,
        include_canonical=False,
        use_index_reverse=True,
    )

    assert result["fulltext_queries"] == []
    assert result["vector_queries"] == []
    assert result["canonical_candidates"] == []
    assert result["lexicon_cache"]["mode"] == "INDEX_ENTRIES_EXACT"
    assert [row["coordinate"] for row in result["evidence_candidates"]] == [
        ["law-a", 1]
    ]
