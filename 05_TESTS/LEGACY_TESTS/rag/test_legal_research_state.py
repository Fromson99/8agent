from __future__ import annotations

import pytest

from lawrag.core.legal_graph.behavior import BehaviorStatus, CoverageState
from lawrag.core.legal_graph.model import RelationPredicate
from lawrag.core.rag.legal_research_state import (
    CandidateProvenance,
    CoverageBinding,
    LegalEffectRelation,
    PhysicalLinkKind,
    PhysicalLinkRelation,
    RelationPlane,
    ResearchCoordinate,
    ResearchStateError,
    SearchRouteKind,
    SearchRoutingKind,
    SearchRoutingRelation,
    SourceSpanVerification,
    SubsumptionCheck,
    SubsumptionElementKind,
    SubsumptionOutcome,
    SupportState,
    TargetedSearchActionKind,
    assess_subsumption,
    build_source_span_verification,
    compile_relation_evidence,
    compile_research_evidence,
    promote_candidate,
    seed_candidate,
    verify_candidate,
)


def _receipt(candidate_id: str, coordinate: ResearchCoordinate, suffix: str = "1") \
        -> SourceSpanVerification:
    return build_source_span_verification(
        candidate_id,
        coordinate,
        "근거",
        authority_generation="generation-1",
        authority_as_of="20260829",
        evidence_id=f"evidence:{suffix}",
    )


def _verify(candidate, receipts):
    return verify_candidate(
        candidate,
        receipts,
        source_resolver=lambda _coordinate: "근거",
        authority_generation="generation-1",
        authority_as_of="20260829",
    )


def _verified_candidate(
    candidate_id: str,
    *,
    origin: CandidateProvenance = CandidateProvenance.SYSTEM_PRIOR,
    relation_ids: tuple[str, ...] = (),
):
    coordinate = ResearchCoordinate("DOC", candidate_id)
    candidate = seed_candidate(
        candidate_id,
        coordinate,
        origin,
        relation_ids=relation_ids,
    )
    candidate = promote_candidate(candidate, CandidateProvenance.PROTECTED_CANDIDATE,
                                  reason="preserve governing candidate")
    return _verify(candidate, (_receipt(candidate_id, coordinate, candidate_id),))


def _ready_basis_compilation():
    target = _verified_candidate("target")
    scope = _verified_candidate("scope", origin=CandidateProvenance.SEMANTIC_ENTRY)
    candidates = {target.candidate_id: target, scope.candidate_id: scope}
    bindings = {
        "target_rule": CoverageBinding("제10조", ("target",)),
        "basis_scope": CoverageBinding("허가의 법적 근거", ("scope",)),
    }
    return compile_relation_evidence(
        RelationPredicate.LEGAL_BASIS_IN, bindings, candidates
    )


def test_relation_planes_do_not_conflate_location_effect_and_search_policy() -> None:
    source = ResearchCoordinate("A", 1)
    target = ResearchCoordinate("B", 2)
    physical = PhysicalLinkRelation(
        "link:1", source, target, PhysicalLinkKind.EXPLICIT_CITATION, "제2조"
    )
    legal = LegalEffectRelation(
        "effect:1", source, target, RelationPredicate.LEGAL_BASIS_IN
    )
    routing = SearchRoutingRelation(
        "route:1",
        source,
        target,
        SearchRoutingKind.FALLBACK_AFTER_NO_HIT,
        SearchRouteKind.DOCUMENT_SEARCH,
        "first instrument returned no coverage",
    )

    assert physical.plane == RelationPlane.PHYSICAL_LINK
    assert legal.plane == RelationPlane.LEGAL_EFFECT
    assert routing.plane == RelationPlane.SEARCH_ROUTING
    assert not legal.verified
    assert not hasattr(physical, "predicate")
    assert not hasattr(routing, "predicate")


def test_verified_legal_effect_relation_requires_source_evidence() -> None:
    coordinate = ResearchCoordinate("A", 1)
    with pytest.raises(ResearchStateError, match="source evidence_ids"):
        LegalEffectRelation(
            "effect:1",
            coordinate,
            coordinate,
            RelationPredicate.ENTRUSTS_TASK,
            verified=True,
        )


def test_relation_expansion_cannot_skip_protection_or_source_verification() -> None:
    coordinate = ResearchCoordinate("A", 10)
    candidate = seed_candidate(
        "candidate:relation",
        coordinate,
        CandidateProvenance.RELATION_EXPANDED,
        relation_ids=("edge:10",),
    )

    with pytest.raises(ResearchStateError, match="verify_candidate"):
        promote_candidate(
            candidate,
            CandidateProvenance.VERIFIED_EVIDENCE,
            reason="relation edge exists",
        )
    with pytest.raises(ResearchStateError, match="protected"):
        _verify(candidate, (_receipt(candidate.candidate_id, coordinate),))

    protected = promote_candidate(
        candidate,
        CandidateProvenance.PROTECTED_CANDIDATE,
        reason="keep relation target for source inspection",
    )
    verified = _verify(
        protected,
        (_receipt(candidate.candidate_id, coordinate),),
    )
    assert candidate.raw_relation_expansion
    assert protected.protected and not protected.verified
    assert verified.verified
    assert verified.evidence_ids == ("evidence:1",)


def test_raw_relation_expansion_is_unverified_coverage_and_creates_verify_action() -> None:
    target = seed_candidate(
        "target",
        ResearchCoordinate("A", 10),
        CandidateProvenance.RELATION_EXPANDED,
        relation_ids=("edge:target",),
    )
    scope = _verified_candidate("scope")
    compilation = compile_relation_evidence(
        RelationPredicate.LEGAL_BASIS_IN,
        {
            "target_rule": CoverageBinding("제10조", ("target",)),
            "basis_scope": CoverageBinding("허가 근거", ("scope",)),
        },
        {"target": target, "scope": scope},
    )

    assert compilation.behavior.status == BehaviorStatus.BLOCKED_MISSING_COVERAGE
    assert compilation.behavior.coverage["target_rule"] == CoverageState.UNVERIFIED
    assert compilation.assessment_input is None
    assert not compilation.direct_conclusion_allowed
    assert [action.coverage_key for action in compilation.targeted_search_actions] == [
        "target_rule"
    ]
    assert compilation.targeted_search_actions[0].action == (
        TargetedSearchActionKind.VERIFY_SOURCE_SPAN
    )
    assert compilation.targeted_search_actions[0].route == (
        SearchRouteKind.SOURCE_VERIFICATION
    )


def test_missing_coverage_creates_targeted_route_without_global_restart() -> None:
    target = _verified_candidate("target")
    compilation = compile_relation_evidence(
        RelationPredicate.LEGAL_BASIS_IN,
        {"target_rule": CoverageBinding("제10조", ("target",))},
        {"target": target},
    )

    assert compilation.behavior.missing_coverage == ("basis_scope",)
    action = compilation.targeted_search_actions[0]
    assert action.coverage_key == "basis_scope"
    assert action.action == TargetedSearchActionKind.LOCATE_MISSING_COVERAGE
    assert action.route == SearchRouteKind.STRUCTURE_MOVE


def test_ready_coverage_produces_assessment_input_but_not_a_conclusion() -> None:
    compilation = _ready_basis_compilation()

    assert compilation.behavior.status == BehaviorStatus.READY_FOR_ASSESSMENT
    assert compilation.behavior.may_render_definitive_conclusion
    assert compilation.ready_for_assessment
    assert compilation.assessment_input is not None
    assert compilation.assessment_input.evidence_ids == (
        "evidence:scope", "evidence:target"
    )
    assert not compilation.direct_conclusion_allowed
    assert compilation.targeted_search_actions == ()
    assert compilation.to_dict()["direct_conclusion_allowed"] is False


def test_reference_relation_stays_navigation_only_after_full_verification() -> None:
    target = _verified_candidate("target")
    compilation = compile_relation_evidence(
        RelationPredicate.REFERENCES,
        {"target_rule": CoverageBinding("제10조", ("target",))},
        {"target": target},
    )

    assert compilation.behavior.status == BehaviorStatus.NAVIGATION_ONLY
    assert compilation.assessment_input is None
    assert not compilation.ready_for_assessment


def test_binding_cannot_spoof_a_verified_evidence_id() -> None:
    target = _verified_candidate("target")
    scope = _verified_candidate("scope")
    compilation = compile_relation_evidence(
        RelationPredicate.LEGAL_BASIS_IN,
        {
            "target_rule": CoverageBinding(
                "제10조", ("target",), evidence_ids=("evidence:not-source",)
            ),
            "basis_scope": CoverageBinding("허가 근거", ("scope",)),
        },
        {"target": target, "scope": scope},
    )

    assert compilation.behavior.coverage["target_rule"] == CoverageState.UNVERIFIED
    assert not compilation.ready_for_assessment


def test_subsumption_requires_complete_verified_condition_and_exception_checks() -> None:
    compilation = _ready_basis_compilation()
    result = assess_subsumption(
        compilation,
        (
            SubsumptionCheck(
                "condition:1",
                SubsumptionElementKind.CONDITION,
                "허가 대상 행위이다",
                SupportState.SUPPORTED,
                ("fact:condition",),
                True,
            ),
            SubsumptionCheck(
                "exception:1",
                SubsumptionElementKind.EXCEPTION,
                "적용 제외 대상이다",
                SupportState.CONTRADICTED,
                ("fact:exception",),
                True,
            ),
        ),
        conditions_complete=True,
        exceptions_complete=True,
    )

    assert result.definite_conclusion_allowed
    assert result.outcome == SubsumptionOutcome.RULE_APPLIES
    assert result.unknown_check_ids == ()
    assert "fact:condition" in result.conclusion_evidence_ids
    assert "evidence:target" in result.conclusion_evidence_ids


def test_unknown_exception_blocks_definite_conclusion() -> None:
    compilation = _ready_basis_compilation()
    result = assess_subsumption(
        compilation,
        (
            SubsumptionCheck(
                "condition:1",
                SubsumptionElementKind.CONDITION,
                "허가 대상 행위이다",
                SupportState.SUPPORTED,
                ("fact:condition",),
                True,
            ),
            SubsumptionCheck(
                "exception:1",
                SubsumptionElementKind.EXCEPTION,
                "적용 제외 대상이다",
                SupportState.UNKNOWN,
            ),
        ),
        conditions_complete=True,
        exceptions_complete=True,
    )

    assert not result.definite_conclusion_allowed
    assert result.outcome == SubsumptionOutcome.INDETERMINATE
    assert result.unknown_check_ids == ("exception:1",)
    assert "UNKNOWN_CHECK:exception:1" in result.gate_blockers
    assert result.conclusion_evidence_ids == ()


def test_supported_exception_allows_only_verified_non_application_conclusion() -> None:
    compilation = _ready_basis_compilation()
    result = assess_subsumption(
        compilation,
        (
            SubsumptionCheck(
                "condition:1",
                SubsumptionElementKind.CONDITION,
                "허가 대상 행위이다",
                SupportState.SUPPORTED,
                ("fact:condition",),
                True,
            ),
            SubsumptionCheck(
                "exception:1",
                SubsumptionElementKind.EXCEPTION,
                "적용 제외 대상이다",
                SupportState.SUPPORTED,
                ("fact:exception",),
                True,
            ),
        ),
        conditions_complete=True,
        exceptions_complete=True,
    )

    assert result.definite_conclusion_allowed
    assert result.outcome == SubsumptionOutcome.RULE_DOES_NOT_APPLY


def test_prohibited_inference_blocks_otherwise_complete_subsumption() -> None:
    compilation = _ready_basis_compilation()
    result = assess_subsumption(
        compilation,
        (SubsumptionCheck(
            "condition:1",
            SubsumptionElementKind.CONDITION,
            "근거 범위 안의 행위이다",
            SupportState.SUPPORTED,
            ("fact:condition",),
            True,
        ),),
        conditions_complete=True,
        exceptions_complete=True,
        triggered_prohibited_inferences=("TARGET_RULE_WHOLESALE_APPLICATION",),
    )

    assert not result.definite_conclusion_allowed
    assert result.outcome == SubsumptionOutcome.INDETERMINATE
    assert result.gate_blockers == (
        "PROHIBITED_INFERENCE:TARGET_RULE_WHOLESALE_APPLICATION",
    )


def test_unknown_coverage_binding_is_rejected_as_schema_drift() -> None:
    with pytest.raises(ResearchStateError, match="outside policy"):
        compile_relation_evidence(
            RelationPredicate.LEGAL_BASIS_IN,
            {"invented": CoverageBinding("x", ("missing",))},
            {},
        )


def test_question_facade_returns_missing_plans_and_ready_inputs_together() -> None:
    target = _verified_candidate("target")
    scope = _verified_candidate("scope")
    bundle = compile_research_evidence(
        "이 허가의 법적 근거가 있는가?",
        (target, scope),
        relation_predicates=(
            RelationPredicate.LEGAL_BASIS_IN,
            RelationPredicate.ENTRUSTS_TASK,
        ),
        bindings_by_predicate={
            RelationPredicate.LEGAL_BASIS_IN: {
                "target_rule": CoverageBinding("제10조", ("target",)),
                "basis_scope": CoverageBinding("허가 근거", ("scope",)),
            },
        },
    )

    assert len(bundle.assessment_inputs) == 1
    assert bundle.needs_targeted_search
    assert bundle.compilations[
        RelationPredicate.LEGAL_BASIS_IN
    ].ready_for_assessment
    assert bundle.compilations[
        RelationPredicate.ENTRUSTS_TASK
    ].behavior.missing_coverage
    public = bundle.to_dict()
    assert public["direct_conclusion_allowed"] is False
    assert "may_render_definitive_conclusion" not in public[
        "compilations"
    ][RelationPredicate.LEGAL_BASIS_IN.value]["behavior"]
