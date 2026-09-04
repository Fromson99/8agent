"""Deterministic relation-semantics runtime for Legal Graph v1.

This module is intentionally not wired to retrieval, the API, or MAIN.  It
turns a canonical relation predicate into three separate contracts:

* an axiom: the stable legal meaning and invalid inferences;
* a behavior policy: which facts and actions that meaning requires; and
* an evidence gate: whether a later legal assessor may render a definitive
  conclusion.

Passing the gate never means that a legal proposition is supported.  It only
means that the evidence cells required by the relation policy are present and
verified, so a separate assessor may evaluate the merits.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from .model import (
    RELATION_FAMILY_BY_PREDICATE,
    RelationFamily,
    RelationPredicate,
)


class _StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class RelationAxis(_StrEnum):
    """The independent legal question answered by a relation family."""

    NORM_COMPLETION = "NORM_COMPLETION"
    COMPETENCE_ALLOCATION = "COMPETENCE_ALLOCATION"
    RULE_INCORPORATION = "RULE_INCORPORATION"


class CoverageState(_StrEnum):
    SATISFIED = "SATISFIED"
    MISSING = "MISSING"
    UNVERIFIED = "UNVERIFIED"


class BehaviorStatus(_StrEnum):
    BLOCKED_MISSING_COVERAGE = "BLOCKED_MISSING_COVERAGE"
    READY_FOR_ASSESSMENT = "READY_FOR_ASSESSMENT"
    NAVIGATION_ONLY = "NAVIGATION_ONLY"


@dataclass(frozen=True, slots=True)
class RelationAxiom:
    predicate: RelationPredicate
    axis: RelationAxis
    meaning: str
    inverse_view: str | None = None
    prohibited_inferences: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RelationBehaviorPolicy:
    predicate: RelationPredicate
    required_coverage: tuple[str, ...]
    actions: tuple[str, ...]
    allows_definitive_assessment: bool = True


@dataclass(frozen=True, slots=True)
class EvidenceFact:
    """A policy fact with source-backed verification provenance."""

    value: Any
    evidence_ids: tuple[str, ...]
    verified: bool = True

    @property
    def has_value(self) -> bool:
        value = self.value
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (tuple, list, set, frozenset, dict)):
            return bool(value)
        return True

    @property
    def satisfied(self) -> bool:
        return self.verified and self.has_value and bool(self.evidence_ids)


@dataclass(frozen=True, slots=True)
class RelationBehaviorAssessment:
    predicate: RelationPredicate
    axis: RelationAxis
    status: BehaviorStatus
    coverage: Mapping[str, CoverageState]
    missing_coverage: tuple[str, ...]
    unverified_coverage: tuple[str, ...]
    actions: tuple[str, ...]
    prohibited_inferences: tuple[str, ...]
    may_render_definitive_conclusion: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "predicate": self.predicate.value,
            "axis": self.axis.value,
            "status": self.status.value,
            "coverage": {key: value.value for key, value in self.coverage.items()},
            "missing_coverage": list(self.missing_coverage),
            "unverified_coverage": list(self.unverified_coverage),
            "actions": list(self.actions),
            "prohibited_inferences": list(self.prohibited_inferences),
            "may_render_definitive_conclusion": self.may_render_definitive_conclusion,
        }


class RelationBehaviorRegistryError(ValueError):
    """The axiom/policy registry is inconsistent with Legal Graph v1."""


AXIS_BY_FAMILY = MappingProxyType({
    RelationFamily.LEGISLATIVE_LINK: RelationAxis.NORM_COMPLETION,
    RelationFamily.COMPETENCE_TASK: RelationAxis.COMPETENCE_ALLOCATION,
    RelationFamily.RULE_USE: RelationAxis.RULE_INCORPORATION,
})


_NORM_ACTIONS = (
    "LOCATE_DELEGATION_SOURCE",
    "LOCATE_IMPLEMENTING_RULE",
    "VERIFY_DELEGATED_SCOPE",
    "CHECK_REDELEGATION_AUTHORITY",
)
_COMPETENCE_ACTIONS = (
    "IDENTIFY_ORIGINAL_HOLDER",
    "IDENTIFY_RECIPIENT_OR_ACTOR",
    "CLASSIFY_AUTHORITY_OR_TASK_ALLOCATION",
    "VERIFY_SCOPE_AND_QUALIFICATION",
    "VERIFY_PROCEDURE",
    "TRACE_SUPERVISION_AND_RESIDUAL_LIABILITY",
)
_RULE_ACTIONS = (
    "LOCATE_TARGET_RULE",
    "CLASSIFY_INCORPORATION_MODE",
    "RESOLVE_INCORPORATION_SCOPE",
    "COLLECT_CONDITIONS_AND_EXCLUSIONS",
)


def _axiom(
    predicate: RelationPredicate,
    axis: RelationAxis,
    meaning: str,
    *,
    inverse_view: str | None = None,
    prohibited: tuple[str, ...] = (),
) -> RelationAxiom:
    return RelationAxiom(
        predicate=predicate,
        axis=axis,
        meaning=meaning,
        inverse_view=inverse_view,
        prohibited_inferences=prohibited,
    )


RELATION_AXIOMS = MappingProxyType({
    RelationPredicate.LEGISLATIVE_DELEGATION: _axiom(
        RelationPredicate.LEGISLATIVE_DELEGATION,
        RelationAxis.NORM_COMPLETION,
        "상위 규범이 하위 규범에 특정 세부 규범의 형성을 맡긴다.",
        inverse_view="LEGISLATIVE_RECEIPT",
        prohibited=("DELEGATED_SCOPE_IS_UNLIMITED",),
    ),
    RelationPredicate.LEGISLATIVE_REDELEGATION: _axiom(
        RelationPredicate.LEGISLATIVE_REDELEGATION,
        RelationAxis.NORM_COMPLETION,
        "수임 규범이 명시적 근거와 범위 안에서 다시 규범 형성을 맡긴다.",
        inverse_view="LEGISLATIVE_RERECEIPT",
        prohibited=("REDELEGATION_ALLOWED_WITHOUT_BASIS",),
    ),
    RelationPredicate.SUPPLEMENTS_BY_ADMINISTRATIVE_RULE: _axiom(
        RelationPredicate.SUPPLEMENTS_BY_ADMINISTRATIVE_RULE,
        RelationAxis.NORM_COMPLETION,
        "법령이 위임한 사항을 행정규칙이 보충하여 규범을 완성한다.",
        prohibited=("ADMINISTRATIVE_RULE_EXCEEDS_DELEGATED_SCOPE",),
    ),
    RelationPredicate.DELEGATES_ADMINISTRATIVE_AUTHORITY: _axiom(
        RelationPredicate.DELEGATES_ADMINISTRATIVE_AUTHORITY,
        RelationAxis.COMPETENCE_ALLOCATION,
        "행정 권한의 행사 주체를 법적 근거와 범위 안에서 변경한다.",
        inverse_view="RECEIVES_ADMINISTRATIVE_AUTHORITY",
        prohibited=("ALL_AUTHORITY_TRANSFERRED", "RESIDUAL_LIABILITY_EXTINGUISHED"),
    ),
    RelationPredicate.ENTRUSTS_TASK: _axiom(
        RelationPredicate.ENTRUSTS_TASK,
        RelationAxis.COMPETENCE_ALLOCATION,
        "원 주체가 특정 사무의 처리를 다른 적격 주체에게 맡긴다.",
        inverse_view="ACCEPTS_ENTRUSTED_TASK",
        prohibited=("DECISION_POWER_TRANSFERRED", "RESIDUAL_LIABILITY_EXTINGUISHED"),
    ),
    RelationPredicate.APPOINTS_TO_POSITION: _axiom(
        RelationPredicate.APPOINTS_TO_POSITION,
        RelationAxis.COMPETENCE_ALLOCATION,
        "적법한 임용권자가 자격과 절차에 따라 사람을 특정 직위에 임용한다.",
        inverse_view="APPOINTED_TO_POSITION",
    ),
    RelationPredicate.ALLOCATES_INTERNAL_APPROVAL: _axiom(
        RelationPredicate.ALLOCATES_INTERNAL_APPROVAL,
        RelationAxis.COMPETENCE_ALLOCATION,
        "조직 내부의 결재·전결 담당자를 정하되 대외적 권한 귀속은 별도로 판단한다.",
        inverse_view="RECEIVES_INTERNAL_APPROVAL_AUTHORITY",
        prohibited=("EXTERNAL_AUTHORITY_TRANSFERRED",),
    ),
    RelationPredicate.RECEIVES_FROM: _axiom(
        RelationPredicate.RECEIVES_FROM,
        RelationAxis.COMPETENCE_ALLOCATION,
        "위임·위탁 등 원인 관계를 수령자 방향에서 표시하는 호환 view다.",
        prohibited=("SOURCE_RELATION_KIND_INFERRED", "LEGAL_EFFECT_INFERRED_FROM_INVERSE_LABEL"),
    ),
    RelationPredicate.DIRECTLY_APPLIES: _axiom(
        RelationPredicate.DIRECTLY_APPLIES,
        RelationAxis.RULE_INCORPORATION,
        "대상 규정을 수정하지 않고 정해진 범위에 직접 적용한다.",
        prohibited=("TEXT_ADAPTATION_ASSUMED",),
    ),
    RelationPredicate.INCORPORATES_MUTATIS_MUTANDIS: _axiom(
        RelationPredicate.INCORPORATES_MUTATIS_MUTANDIS,
        RelationAxis.RULE_INCORPORATION,
        "특정 규정을 규율 대상의 성질에 맞는 수정을 거쳐 적용한다.",
        prohibited=("PENALTY_AUTOMATICALLY_INCORPORATED", "UNSTATED_SCOPE_EXPANSION"),
    ),
    RelationPredicate.FOLLOWS_EXAMPLE_OF: _axiom(
        RelationPredicate.FOLLOWS_EXAMPLE_OF,
        RelationAxis.RULE_INCORPORATION,
        "대상 제도나 절차의 처리 방식을 포괄적으로 따른다.",
        prohibited=("EVERY_TARGET_PROVISION_AUTOMATICALLY_APPLIES",),
    ),
    RelationPredicate.DEPENDS_ON_REQUIREMENTS_OF: _axiom(
        RelationPredicate.DEPENDS_ON_REQUIREMENTS_OF,
        RelationAxis.RULE_INCORPORATION,
        "현재 규칙의 성립이나 실행이 대상 규칙의 요건 충족에 의존한다.",
    ),
    RelationPredicate.LEGAL_BASIS_IN: _axiom(
        RelationPredicate.LEGAL_BASIS_IN,
        RelationAxis.RULE_INCORPORATION,
        "현재 규칙이나 행위의 법적 근거가 대상 규정에 있다.",
        prohibited=("TARGET_RULE_WHOLESALE_APPLICATION",),
    ),
    RelationPredicate.REFERENCES: _axiom(
        RelationPredicate.REFERENCES,
        RelationAxis.RULE_INCORPORATION,
        "대상 규정을 지시하지만 그 자체로 적용·준용의 법적 효과를 확정하지 않는다.",
        prohibited=("NORMATIVE_EFFECT_INFERRED_FROM_REFERENCE",),
    ),
    RelationPredicate.USES_DEFINITION: _axiom(
        RelationPredicate.USES_DEFINITION,
        RelationAxis.RULE_INCORPORATION,
        "대상 정의 규정의 유효한 scope에서 용어 의미를 사용한다.",
        prohibited=("DEFINITION_USED_OUTSIDE_SCOPE",),
    ),
    RelationPredicate.ISSUED_UNDER_INSTRUMENT: _axiom(
        RelationPredicate.ISSUED_UNDER_INSTRUMENT,
        RelationAxis.RULE_INCORPORATION,
        "현재 규범이 대상 상위 규범의 근거 아래 발령되었다.",
        prohibited=("ISSUANCE_BASIS_EQUALS_WHOLESALE_APPLICATION",),
    ),
})


def _policy(
    predicate: RelationPredicate,
    coverage: tuple[str, ...],
    actions: tuple[str, ...],
    *,
    allows_definitive_assessment: bool = True,
) -> RelationBehaviorPolicy:
    return RelationBehaviorPolicy(
        predicate=predicate,
        required_coverage=coverage,
        actions=actions,
        allows_definitive_assessment=allows_definitive_assessment,
    )


RELATION_BEHAVIOR_POLICIES = MappingProxyType({
    RelationPredicate.LEGISLATIVE_DELEGATION: _policy(
        RelationPredicate.LEGISLATIVE_DELEGATION,
        ("legal_basis", "delegator", "delegatee", "delegated_scope", "implementing_instrument"),
        _NORM_ACTIONS,
    ),
    RelationPredicate.LEGISLATIVE_REDELEGATION: _policy(
        RelationPredicate.LEGISLATIVE_REDELEGATION,
        ("legal_basis", "original_delegation", "redelegator", "delegatee", "redelegated_scope"),
        _NORM_ACTIONS,
    ),
    RelationPredicate.SUPPLEMENTS_BY_ADMINISTRATIVE_RULE: _policy(
        RelationPredicate.SUPPLEMENTS_BY_ADMINISTRATIVE_RULE,
        ("legal_basis", "delegated_scope", "issuing_authority", "supplemental_rule"),
        _NORM_ACTIONS,
    ),
    RelationPredicate.DELEGATES_ADMINISTRATIVE_AUTHORITY: _policy(
        RelationPredicate.DELEGATES_ADMINISTRATIVE_AUTHORITY,
        ("legal_basis", "original_holder", "recipient", "authority_scope", "acting_name", "residual_supervision"),
        _COMPETENCE_ACTIONS,
    ),
    RelationPredicate.ENTRUSTS_TASK: _policy(
        RelationPredicate.ENTRUSTS_TASK,
        (
            "legal_basis", "original_holder", "recipient", "task_scope",
            "recipient_qualification", "procedure", "redelegation_status",
            "residual_liability",
        ),
        _COMPETENCE_ACTIONS,
    ),
    RelationPredicate.APPOINTS_TO_POSITION: _policy(
        RelationPredicate.APPOINTS_TO_POSITION,
        ("legal_basis", "appointing_authority", "position", "appointee_qualification", "procedure"),
        _COMPETENCE_ACTIONS,
    ),
    RelationPredicate.ALLOCATES_INTERNAL_APPROVAL: _policy(
        RelationPredicate.ALLOCATES_INTERNAL_APPROVAL,
        ("internal_basis", "organization", "original_holder", "approver", "approval_scope"),
        _COMPETENCE_ACTIONS,
    ),
    RelationPredicate.RECEIVES_FROM: _policy(
        RelationPredicate.RECEIVES_FROM,
        ("source_relation_kind", "legal_basis", "transferor", "recipient", "received_scope"),
        _COMPETENCE_ACTIONS,
    ),
    RelationPredicate.DIRECTLY_APPLIES: _policy(
        RelationPredicate.DIRECTLY_APPLIES,
        ("target_rule", "incorporation_scope", "conditions", "exclusions"),
        _RULE_ACTIONS,
    ),
    RelationPredicate.INCORPORATES_MUTATIS_MUTANDIS: _policy(
        RelationPredicate.INCORPORATES_MUTATIS_MUTANDIS,
        ("target_rule", "incorporation_scope", "adaptation_map", "conditions", "exclusions"),
        (*_RULE_ACTIONS, "APPLY_EXPLICIT_ADAPTATIONS"),
    ),
    RelationPredicate.FOLLOWS_EXAMPLE_OF: _policy(
        RelationPredicate.FOLLOWS_EXAMPLE_OF,
        ("target_regime", "incorporation_scope", "conditions", "exclusions"),
        (*_RULE_ACTIONS, "BOUND_COMPREHENSIVE_PROCEDURAL_EXAMPLE"),
    ),
    RelationPredicate.DEPENDS_ON_REQUIREMENTS_OF: _policy(
        RelationPredicate.DEPENDS_ON_REQUIREMENTS_OF,
        ("target_requirements", "dependency_scope", "conditions", "exclusions"),
        _RULE_ACTIONS,
    ),
    RelationPredicate.LEGAL_BASIS_IN: _policy(
        RelationPredicate.LEGAL_BASIS_IN,
        ("target_rule", "basis_scope"),
        ("LOCATE_TARGET_RULE", "VERIFY_LEGAL_BASIS_SCOPE"),
    ),
    RelationPredicate.REFERENCES: _policy(
        RelationPredicate.REFERENCES,
        ("target_rule",),
        ("LOCATE_TARGET_RULE", "REQUIRE_SEPARATE_NORMATIVE_EFFECT"),
        allows_definitive_assessment=False,
    ),
    RelationPredicate.USES_DEFINITION: _policy(
        RelationPredicate.USES_DEFINITION,
        ("term", "definition", "definition_scope"),
        ("LOCATE_DEFINITION", "VERIFY_DEFINITION_SCOPE", "APPLY_DEFINED_TERM"),
    ),
    RelationPredicate.ISSUED_UNDER_INSTRUMENT: _policy(
        RelationPredicate.ISSUED_UNDER_INSTRUMENT,
        ("instrument", "issuing_authority", "legal_basis"),
        ("LOCATE_GOVERNING_INSTRUMENT", "VERIFY_ISSUANCE_AUTHORITY"),
    ),
})


def validate_behavior_registry() -> None:
    """Fail if the three-axis registry drifts from the canonical vocabulary."""

    expected = {
        predicate
        for predicate, family in RELATION_FAMILY_BY_PREDICATE.items()
        if family in AXIS_BY_FAMILY
    }
    axioms = set(RELATION_AXIOMS)
    policies = set(RELATION_BEHAVIOR_POLICIES)
    if axioms != expected:
        raise RelationBehaviorRegistryError(
            f"axiom predicate mismatch: missing={sorted(p.value for p in expected - axioms)}, "
            f"extra={sorted(p.value for p in axioms - expected)}"
        )
    if policies != expected:
        raise RelationBehaviorRegistryError(
            f"policy predicate mismatch: missing={sorted(p.value for p in expected - policies)}, "
            f"extra={sorted(p.value for p in policies - expected)}"
        )
    for predicate in sorted(expected, key=lambda item: item.value):
        expected_axis = AXIS_BY_FAMILY[RELATION_FAMILY_BY_PREDICATE[predicate]]
        axiom = RELATION_AXIOMS[predicate]
        policy = RELATION_BEHAVIOR_POLICIES[predicate]
        if axiom.axis != expected_axis:
            raise RelationBehaviorRegistryError(
                f"{predicate.value} axis {axiom.axis.value} != {expected_axis.value}"
            )
        if policy.predicate != predicate or not policy.required_coverage or not policy.actions:
            raise RelationBehaviorRegistryError(
                f"{predicate.value} has an incomplete behavior policy"
            )
        if len(set(policy.required_coverage)) != len(policy.required_coverage):
            raise RelationBehaviorRegistryError(
                f"{predicate.value} has duplicate coverage keys"
            )


def assess_relation_behavior(
    predicate: RelationPredicate | str,
    facts: Mapping[str, EvidenceFact],
) -> RelationBehaviorAssessment:
    """Evaluate evidence readiness without making a substantive legal finding."""

    canonical = RelationPredicate(predicate)
    try:
        axiom = RELATION_AXIOMS[canonical]
        policy = RELATION_BEHAVIOR_POLICIES[canonical]
    except KeyError as exc:
        raise RelationBehaviorRegistryError(
            f"{canonical.value} is outside the three-axis behavior runtime"
        ) from exc

    states: dict[str, CoverageState] = {}
    for key in policy.required_coverage:
        fact = facts.get(key)
        if fact is None or not fact.has_value or not fact.evidence_ids:
            states[key] = CoverageState.MISSING
        elif not fact.verified:
            states[key] = CoverageState.UNVERIFIED
        else:
            states[key] = CoverageState.SATISFIED

    missing = tuple(key for key, state in states.items() if state == CoverageState.MISSING)
    unverified = tuple(
        key for key, state in states.items() if state == CoverageState.UNVERIFIED
    )
    if missing or unverified:
        status = BehaviorStatus.BLOCKED_MISSING_COVERAGE
    elif policy.allows_definitive_assessment:
        status = BehaviorStatus.READY_FOR_ASSESSMENT
    else:
        status = BehaviorStatus.NAVIGATION_ONLY

    return RelationBehaviorAssessment(
        predicate=canonical,
        axis=axiom.axis,
        status=status,
        coverage=MappingProxyType(states),
        missing_coverage=missing,
        unverified_coverage=unverified,
        actions=policy.actions,
        prohibited_inferences=axiom.prohibited_inferences,
        may_render_definitive_conclusion=(
            status == BehaviorStatus.READY_FOR_ASSESSMENT
        ),
    )


validate_behavior_registry()

