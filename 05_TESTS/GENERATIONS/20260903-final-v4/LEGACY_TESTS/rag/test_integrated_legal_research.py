from __future__ import annotations

from types import SimpleNamespace

import pytest

from lawrag.core.legal_graph.model import RelationPredicate
from lawrag.core.rag import integrated_legal_research as subject
from lawrag.core.rag.answer import Section
from lawrag.core.rag.experiments import retrieval_stage_ledger as stage_ledger
from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_research_llm_selector import (
    GENOS_BACKEND,
    QWEN_NATIVE_SCHEMA_PROFILE,
)
from lawrag.core.rag.legal_research_state import (
    CandidateProvenance,
    CoverageBinding,
    ResearchCoordinate,
    ResearchStateError,
    build_source_span_verification,
    compile_research_evidence,
    promote_candidate,
    seed_candidate,
    verify_candidate,
)


AUTHORITY_GENERATION = "a" * 64
AUTHORITY_AS_OF = "20260829"

EXPECTED_STAGES = (
    ("question-source", "source", ()),
    ("closed-grounding-retrieve", "retrieve", ("question-source",)),
    (
        "legal-system-route-retrieve",
        "retrieve",
        ("closed-grounding-retrieve",),
    ),
    (
        "semantic-card-retrieve",
        "retrieve",
        ("legal-system-route-retrieve",),
    ),
    ("baseline-floor-union", "union", ("semantic-card-retrieve",)),
    (
        "typed-legal-relation-expand",
        "expand",
        ("baseline-floor-union",),
    ),
    (
        "wiki-method-dependency-expand",
        "expand",
        ("typed-legal-relation-expand",),
    ),
    (
        "adaptive-gap-retrieve",
        "retrieve",
        ("wiki-method-dependency-expand",),
    ),
    (
        "provenance-canonicalize",
        "canonicalize",
        ("adaptive-gap-retrieve",),
    ),
    (
        "actor-scope-filter",
        "filter",
        ("provenance-canonicalize",),
    ),
    (
        "verified-coverage-select",
        "select",
        ("actor-scope-filter",),
    ),
    (
        "compiled-evidence-present",
        "present",
        ("verified-coverage-select",),
    ),
)


def _index() -> Index:
    docs = []
    for doc_id, name, text in (
        ("law-a", "법률 A", "현행 근거 조문 A"),
        ("law-b", "법률 B", "현행 근거 조문 B"),
    ):
        docs.append((
            doc_id,
            {"name": name, "kind": "law", "status": "현행"},
            {
                "nodes": [{
                    "id": 1,
                    "parent": None,
                    "level": 1,
                    "family": "kr_article",
                    "surface": "제1조",
                    "title": "목적",
                    "span": [0, 1],
                }],
                "blocks": [{"idx": 0, "kind": "text", "text": text}],
            },
        ))
    return Index.from_docs(
        docs,
        canonical_doc_ids={"law-a", "law-b"},
        authority_generation=AUTHORITY_GENERATION,
        authority_as_of=AUTHORITY_AS_OF,
    )


def _section(index: Index, doc_id: str, number: int) -> Section:
    view = index.docs[doc_id]
    node = view.by_id[1]
    return Section(
        n=number,
        doc_id=doc_id,
        doc=view.name,
        node=1,
        path=view.path(1),
        page=node.get("page"),
        kind="본문",
        matched="baseline",
        text=view.section_outline(node),
    )


def _coordinates(rows) -> set[tuple[str, int]]:
    return {(str(row["doc_id"]), int(row["node"])) for row in rows}


def test_auxiliary_failure_preserves_floor_and_emits_exact_frozen_capture(
    monkeypatch,
) -> None:
    index = _index()
    floor = [_section(index, "law-b", 1), _section(index, "law-a", 2)]

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("catalog generation unavailable")

    monkeypatch.setattr(subject, "_resources", unavailable)
    sections, meta = subject.extend_sections(
        index,
        "어느 조문이 적용되는가?",
        floor,
        llm=None,
        cap=32,
        case_id="cm-test",
    )

    assert sections == floor
    assert [(row.doc_id, row.node) for row in sections] == [
        ("law-b", 1),
        ("law-a", 1),
    ]
    assert [row.n for row in sections] == [1, 2]
    assert meta["status"] == "fallback"
    assert meta["baseline_floor_preserved"] is True
    assert meta["direct_conclusion_allowed"] is False
    assert "resource_gate:RuntimeError" in meta["fallback"]

    capture = meta["stage_capture"]
    stage_ledger.validate_capture(capture)
    assert capture["case_id"] == "cm-test"
    assert capture["arm_id"] == "integrated-seven-layer"
    assert capture["gold_visible_to_product"] is False
    observed = tuple(
        (
            row["stage_id"],
            row["kind"],
            tuple(row["parent_stage_ids"]),
        )
        for row in capture["stages"]
    )
    assert observed == EXPECTED_STAGES

    by_id = {row["stage_id"]: row for row in capture["stages"]}
    expected_floor = {("law-a", 1), ("law-b", 1)}
    assert _coordinates(by_id["baseline-floor-union"]["after"]) == expected_floor
    assert _coordinates(by_id["compiled-evidence-present"]["after"]) == expected_floor
    assert by_id["closed-grounding-retrieve"]["executed"] is False
    assert by_id["compiled-evidence-present"]["executed"] is False


def test_forged_receipt_cannot_be_promoted_against_current_source() -> None:
    coordinate = ResearchCoordinate("law-a", 1)
    candidate = promote_candidate(
        seed_candidate(
            "candidate:law-a:1",
            coordinate,
            CandidateProvenance.SYSTEM_PRIOR,
        ),
        CandidateProvenance.PROTECTED_CANDIDATE,
        reason="inspect the current source",
    )
    forged = build_source_span_verification(
        candidate.candidate_id,
        coordinate,
        "forged! source",
        authority_generation=AUTHORITY_GENERATION,
        authority_as_of=AUTHORITY_AS_OF,
    )

    with pytest.raises(ResearchStateError, match="source_sha256 mismatch"):
        verify_candidate(
            candidate,
            (forged,),
            source_resolver=lambda _coordinate: "current source",
            authority_generation=AUTHORITY_GENERATION,
            authority_as_of=AUTHORITY_AS_OF,
        )

    current = build_source_span_verification(
        candidate.candidate_id,
        coordinate,
        "current source",
        authority_generation=AUTHORITY_GENERATION,
        authority_as_of=AUTHORITY_AS_OF,
    )
    verified = verify_candidate(
        candidate,
        (current,),
        source_resolver=lambda _coordinate: "current source",
        authority_generation=AUTHORITY_GENERATION,
        authority_as_of=AUTHORITY_AS_OF,
    )
    assert verified.verified is True


def _verified_candidate(
    candidate_id: str,
    coordinate: ResearchCoordinate,
    source: str,
):
    candidate = promote_candidate(
        seed_candidate(
            candidate_id,
            coordinate,
            CandidateProvenance.SYSTEM_PRIOR,
        ),
        CandidateProvenance.PROTECTED_CANDIDATE,
        reason="preserve for exact-source verification",
    )
    receipt = build_source_span_verification(
        candidate_id,
        coordinate,
        source,
        authority_generation=AUTHORITY_GENERATION,
        authority_as_of=AUTHORITY_AS_OF,
    )
    return verify_candidate(
        candidate,
        (receipt,),
        source_resolver=lambda _coordinate: source,
        authority_generation=AUTHORITY_GENERATION,
        authority_as_of=AUTHORITY_AS_OF,
    )


def test_ready_coverage_is_assessment_input_not_a_direct_conclusion() -> None:
    target = _verified_candidate(
        "target", ResearchCoordinate("law-a", 1), "현행 적용 조문"
    )
    scope = _verified_candidate(
        "scope", ResearchCoordinate("law-b", 1), "현행 근거 범위"
    )
    bundle = compile_research_evidence(
        "이 규정의 법적 근거가 있는가?",
        (target, scope),
        relation_predicates=(RelationPredicate.LEGAL_BASIS_IN,),
        bindings_by_predicate={
            RelationPredicate.LEGAL_BASIS_IN: {
                "target_rule": CoverageBinding("제1조", ("target",)),
                "basis_scope": CoverageBinding("근거 범위", ("scope",)),
            },
        },
    )

    compilation = bundle.compilations[RelationPredicate.LEGAL_BASIS_IN]
    assert compilation.ready_for_assessment is True
    assert compilation.assessment_input is not None
    assert compilation.direct_conclusion_allowed is False
    assert bundle.direct_conclusion_allowed is False
    public = bundle.to_dict()
    assert public["direct_conclusion_allowed"] is False
    assert public["compilations"][
        RelationPredicate.LEGAL_BASIS_IN.value
    ]["direct_conclusion_allowed"] is False


def test_qwen_input_keeps_the_supplied_provider_and_model_without_transport_call(
    monkeypatch,
) -> None:
    seen = {}

    class NoCallQwen:
        backend = GENOS_BACKEND
        model = "qwen-onsite-72b"
        log = []

        def structured(self, *_args, **_kwargs):
            raise AssertionError("this compatibility test must not call a provider")

    class Recorder:
        def __init__(self, factory, *, profile):
            client = factory()
            seen.update(
                backend=profile.backend,
                model=profile.model,
                schema_profile=profile.schema_profile,
                client_backend=client.backend,
                client_model=client.model,
            )
            self.model = profile.model
            self.receipts = ({"provider": profile.backend},)

    def plan_question(recorder, question):
        return {"provider_model": recorder.model, "question": question}

    monkeypatch.setenv("GENOS_LLM_SCHEMA_PROFILE", "native")
    monkeypatch.setattr(subject, "ThreadLocalStructuredRecorder", Recorder)
    monkeypatch.setattr(subject, "plan_question", plan_question)

    plan, meta = subject._question_plan(NoCallQwen(), "질의 계획")

    assert plan == {
        "provider_model": "qwen-onsite-72b",
        "question": "질의 계획",
    }
    assert meta["status"] == "planned"
    assert seen == {
        "backend": GENOS_BACKEND,
        "model": "qwen-onsite-72b",
        "schema_profile": QWEN_NATIVE_SCHEMA_PROFILE,
        "client_backend": GENOS_BACKEND,
        "client_model": "qwen-onsite-72b",
    }


def test_no_llm_uses_deterministic_plan_without_constructing_a_provider(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        subject,
        "ThreadLocalStructuredRecorder",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("deterministic fallback must not construct a recorder")
        ),
    )

    plan, meta = subject._question_plan(None, "100분의 10 기준은?")

    assert plan["mentions"] == []
    assert plan["family_hypotheses"] == []
    assert meta == {
        "status": "fallback",
        "reason": "llm_unavailable",
        "receipts": [],
    }


def test_resource_preload_receipt_is_provider_free_and_generation_bound(
        monkeypatch) -> None:
    monkeypatch.delenv("RAG_LEXICON_COMPILE_MISSING", raising=False)
    index = _index()
    runtime = SimpleNamespace(
        system_map=SimpleNamespace(
            catalog_version="catalog-v1",
            law_index_sha256="1" * 64,
            effective_dates_sha256="2" * 64,
            profiles_sha256="3" * 64,
        )
    )
    snapshot = SimpleNamespace(
        generation_id="graph-v1",
        content_sha256="4" * 64,
        pointer_sha256="5" * 64,
        ports_by_article={
            ("law-a", 1): object(), ("law-b", 1): object(),
        }
    )
    relation_bundle = SimpleNamespace(sections=(object(), object()))
    closed_lexicon = SimpleNamespace(
        names=["현행", "근거"], cache_stats={"cached": 1}
    )
    vector_index = SimpleNamespace(rows=[{}, {}, {}])
    registry = SimpleNamespace(
        active_concepts={"concept-1": object()},
        active_assertions=(object(), object()),
    )
    assertion_index = SimpleNamespace(concept_phrases={"개념": {"concept-1"}})
    general_corpus = SimpleNamespace(block_count=2)
    monkeypatch.setattr(subject, "_resources", lambda *_args: (runtime, snapshot))
    monkeypatch.setattr(
        subject.relations_mod, "build", lambda *_args: relation_bundle
    )
    monkeypatch.setattr(
        subject.lexicon_mod, "current", lambda *_args: closed_lexicon
    )
    monkeypatch.setattr(subject.vector_mod, "current", lambda: vector_index)
    monkeypatch.setattr(subject.conceptfirst, "registry_path", lambda: "registry")
    monkeypatch.setattr(
        subject.conceptfirst, "load_registry", lambda *_args: registry
    )
    monkeypatch.setattr(
        subject.assertionfirst, "current", lambda *_args: assertion_index
    )
    monkeypatch.setattr(
        subject.general_search, "_corpus", lambda *_args: general_corpus
    )
    monkeypatch.setattr(
        subject, "_files_fingerprint", lambda *_args: "f" * 64
    )

    receipt = subject.preload_resources(index)

    assert receipt["status"] == "ready"
    assert receipt["provider_calls"] == 0
    assert receipt["authority_generation"] == AUTHORITY_GENERATION
    assert receipt["authority_as_of"] == AUTHORITY_AS_OF
    assert receipt["article_count"] == 2
    assert receipt["baseline_posting_terms"] >= 3
    assert receipt["baseline_posting_blocks"] == 2
    assert receipt["relation_sections"] == 2
    assert receipt["lexicon_terms"] == 2
    assert receipt["lexicon_cached_terms"] == 1
    assert receipt["vector_rows"] == 3
    assert receipt["active_concepts"] == 1
    assert receipt["active_assertions"] == 2
    assert receipt["general_search_blocks"] == 2
    assert receipt["lexicon_compile_missing_enabled"] is False
    assert receipt["legal_graph_content_sha256"] == "4" * 64
    assert receipt["lexicon_cache_fingerprint"] == "f" * 64
    assert receipt["elapsed_ms"] >= 0
