from __future__ import annotations

from dataclasses import dataclass

import pytest

from lawrag.core.legal_graph.behavior import (
    AXIS_BY_FAMILY,
    RELATION_AXIOMS,
    RELATION_BEHAVIOR_POLICIES,
    BehaviorStatus,
    CoverageState,
    EvidenceFact,
    RelationAxis,
    assess_relation_behavior,
    validate_behavior_registry,
)
from lawrag.core.legal_graph.model import (
    RELATION_FAMILY_BY_PREDICATE,
    RelationFamily,
    RelationPredicate,
)


def _fact(value: object = "present", *, verified: bool = True) -> EvidenceFact:
    return EvidenceFact(value=value, evidence_ids=("evidence:test",), verified=verified)


def _complete(predicate: RelationPredicate) -> dict[str, EvidenceFact]:
    return {
        key: _fact({"resolved": key})
        for key in RELATION_BEHAVIOR_POLICIES[predicate].required_coverage
    }


@dataclass(frozen=True)
class Case:
    name: str
    predicate: RelationPredicate
    drop: str | None
    unverified: str | None
    expected: BehaviorStatus
    expected_axis: RelationAxis


CASES = (
    Case("delegation-complete", RelationPredicate.LEGISLATIVE_DELEGATION, None, None,
         BehaviorStatus.READY_FOR_ASSESSMENT, RelationAxis.NORM_COMPLETION),
    Case("delegation-missing-instrument", RelationPredicate.LEGISLATIVE_DELEGATION,
         "implementing_instrument", None, BehaviorStatus.BLOCKED_MISSING_COVERAGE,
         RelationAxis.NORM_COMPLETION),
    Case("redelegation-unverified-original", RelationPredicate.LEGISLATIVE_REDELEGATION,
         None, "original_delegation", BehaviorStatus.BLOCKED_MISSING_COVERAGE,
         RelationAxis.NORM_COMPLETION),
    Case("administrative-rule-complete", RelationPredicate.SUPPLEMENTS_BY_ADMINISTRATIVE_RULE,
         None, None, BehaviorStatus.READY_FOR_ASSESSMENT, RelationAxis.NORM_COMPLETION),
    Case("authority-delegation-complete", RelationPredicate.DELEGATES_ADMINISTRATIVE_AUTHORITY,
         None, None, BehaviorStatus.READY_FOR_ASSESSMENT,
         RelationAxis.COMPETENCE_ALLOCATION),
    Case("entrustment-missing-redelegation", RelationPredicate.ENTRUSTS_TASK,
         "redelegation_status", None, BehaviorStatus.BLOCKED_MISSING_COVERAGE,
         RelationAxis.COMPETENCE_ALLOCATION),
    Case("entrustment-unverified-qualification", RelationPredicate.ENTRUSTS_TASK,
         None, "recipient_qualification", BehaviorStatus.BLOCKED_MISSING_COVERAGE,
         RelationAxis.COMPETENCE_ALLOCATION),
    Case("ambiguous-receipt", RelationPredicate.RECEIVES_FROM, "source_relation_kind", None,
         BehaviorStatus.BLOCKED_MISSING_COVERAGE, RelationAxis.COMPETENCE_ALLOCATION),
    Case("direct-application-complete", RelationPredicate.DIRECTLY_APPLIES, None, None,
         BehaviorStatus.READY_FOR_ASSESSMENT, RelationAxis.RULE_INCORPORATION),
    Case("mutatis-missing-adaptation", RelationPredicate.INCORPORATES_MUTATIS_MUTANDIS,
         "adaptation_map", None, BehaviorStatus.BLOCKED_MISSING_COVERAGE,
         RelationAxis.RULE_INCORPORATION),
    Case("follows-example-complete", RelationPredicate.FOLLOWS_EXAMPLE_OF, None, None,
         BehaviorStatus.READY_FOR_ASSESSMENT, RelationAxis.RULE_INCORPORATION),
    Case("reference-navigation-only", RelationPredicate.REFERENCES, None, None,
         BehaviorStatus.NAVIGATION_ONLY, RelationAxis.RULE_INCORPORATION),
)


def test_three_axis_registry_covers_every_predicate_in_target_families() -> None:
    validate_behavior_registry()
    expected = {
        predicate
        for predicate, family in RELATION_FAMILY_BY_PREDICATE.items()
        if family in AXIS_BY_FAMILY
    }
    assert set(RELATION_AXIOMS) == expected
    assert set(RELATION_BEHAVIOR_POLICIES) == expected


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_frozen_behavior_cases(case: Case) -> None:
    facts = _complete(case.predicate)
    if case.drop:
        facts.pop(case.drop)
    if case.unverified:
        facts[case.unverified] = _fact(verified=False)

    assessment = assess_relation_behavior(case.predicate, facts)

    assert assessment.axis == case.expected_axis
    assert assessment.status == case.expected
    assert assessment.may_render_definitive_conclusion == (
        case.expected == BehaviorStatus.READY_FOR_ASSESSMENT
    )
    if case.drop:
        assert assessment.coverage[case.drop] == CoverageState.MISSING
        assert case.drop in assessment.missing_coverage
    if case.unverified:
        assert assessment.coverage[case.unverified] == CoverageState.UNVERIFIED
        assert case.unverified in assessment.unverified_coverage


def test_false_boolean_is_a_valid_verified_fact_value() -> None:
    fact = EvidenceFact(value=False, evidence_ids=("evidence:no",), verified=True)
    assert fact.satisfied


def test_unverified_fact_never_satisfies_coverage() -> None:
    facts = _complete(RelationPredicate.ENTRUSTS_TASK)
    facts["legal_basis"] = _fact(verified=False)
    assessment = assess_relation_behavior(RelationPredicate.ENTRUSTS_TASK, facts)
    assert assessment.status == BehaviorStatus.BLOCKED_MISSING_COVERAGE
    assert assessment.coverage["legal_basis"] == CoverageState.UNVERIFIED
    assert not assessment.may_render_definitive_conclusion


def test_axioms_keep_receipt_and_entrustment_from_overclaiming() -> None:
    assert "SOURCE_RELATION_KIND_INFERRED" in RELATION_AXIOMS[
        RelationPredicate.RECEIVES_FROM
    ].prohibited_inferences
    assert "DECISION_POWER_TRANSFERRED" in RELATION_AXIOMS[
        RelationPredicate.ENTRUSTS_TASK
    ].prohibited_inferences
    assert "PENALTY_AUTOMATICALLY_INCORPORATED" in RELATION_AXIOMS[
        RelationPredicate.INCORPORATES_MUTATIS_MUTANDIS
    ].prohibited_inferences


def test_axis_mapping_is_family_based_not_vertical_label_based() -> None:
    assert AXIS_BY_FAMILY[RelationFamily.LEGISLATIVE_LINK] == RelationAxis.NORM_COMPLETION
    assert AXIS_BY_FAMILY[RelationFamily.COMPETENCE_TASK] == RelationAxis.COMPETENCE_ALLOCATION
    assert AXIS_BY_FAMILY[RelationFamily.RULE_USE] == RelationAxis.RULE_INCORPORATION
