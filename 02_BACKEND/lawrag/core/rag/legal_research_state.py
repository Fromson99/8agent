"""Fail-closed research state, evidence compilation, and subsumption gates.

The legal research pipeline handles three different kinds of relation that
must not be collapsed into one edge vocabulary:

* physical links say only where another source unit is located;
* legal-effect relations make a typed legal assertion; and
* search-routing relations say where the investigator should look next.

Likewise, a candidate found through a relation is not legal evidence.  A
candidate becomes evidence only after an exact source span is verified.  This
module records that lifecycle, invokes the relation behavior coverage gate,
and produces an assessment input.  It never turns coverage readiness into a
substantive legal conclusion by itself.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import re
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, TypeAlias

from lawrag.core.legal_graph.behavior import (
    BehaviorStatus,
    CoverageState,
    EvidenceFact,
    RELATION_BEHAVIOR_POLICIES,
    RelationBehaviorAssessment,
    assess_relation_behavior,
)
from lawrag.core.legal_graph.model import RelationPredicate


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class _StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ResearchStateError(ValueError):
    """A relation, provenance transition, or evidence receipt is invalid."""


class RelationPlane(_StrEnum):
    """The non-interchangeable meaning carried by a research edge."""

    PHYSICAL_LINK = "PHYSICAL_LINK"
    LEGAL_EFFECT = "LEGAL_EFFECT"
    SEARCH_ROUTING = "SEARCH_ROUTING"


class PhysicalLinkKind(_StrEnum):
    EXPLICIT_CITATION = "EXPLICIT_CITATION"
    OFFICIAL_DOCUMENT_LINK = "OFFICIAL_DOCUMENT_LINK"
    STRUCTURAL_HIERARCHY = "STRUCTURAL_HIERARCHY"
    STRUCTURAL_ADJACENCY = "STRUCTURAL_ADJACENCY"


class SearchRouteKind(_StrEnum):
    RELATION = "RELATION"
    DOCUMENT_SEARCH = "DOCUMENT_SEARCH"
    GLOBAL_SEARCH = "GLOBAL_SEARCH"
    STRUCTURE_MOVE = "STRUCTURE_MOVE"
    SOURCE_VERIFICATION = "SOURCE_VERIFICATION"


class SearchRoutingKind(_StrEnum):
    COVERAGE_GAP = "COVERAGE_GAP"
    DEFINITION_LOOKUP = "DEFINITION_LOOKUP"
    COMPANION_RULE = "COMPANION_RULE"
    FALLBACK_AFTER_NO_HIT = "FALLBACK_AFTER_NO_HIT"
    NEXT_PAGE = "NEXT_PAGE"


@dataclass(frozen=True, slots=True)
class ResearchCoordinate:
    document_id: str
    node_id: str | int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.document_id, str) or not self.document_id.strip():
            raise ResearchStateError("document_id must be a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        return {"document_id": self.document_id, "node_id": self.node_id}


@dataclass(frozen=True, slots=True)
class PhysicalLinkRelation:
    relation_id: str
    source: ResearchCoordinate
    target: ResearchCoordinate
    kind: PhysicalLinkKind
    surface: str = ""

    def __post_init__(self) -> None:
        _require_id(self.relation_id, "relation_id")
        object.__setattr__(self, "kind", PhysicalLinkKind(self.kind))

    @property
    def plane(self) -> RelationPlane:
        return RelationPlane.PHYSICAL_LINK


@dataclass(frozen=True, slots=True)
class LegalEffectRelation:
    relation_id: str
    source: ResearchCoordinate
    target: ResearchCoordinate
    predicate: RelationPredicate
    evidence_ids: tuple[str, ...] = ()
    verified: bool = False

    def __post_init__(self) -> None:
        _require_id(self.relation_id, "relation_id")
        object.__setattr__(self, "predicate", RelationPredicate(self.predicate))
        evidence_ids = _unique_nonempty(self.evidence_ids)
        object.__setattr__(self, "evidence_ids", evidence_ids)
        if self.verified and not evidence_ids:
            raise ResearchStateError(
                "a verified legal-effect relation requires source evidence_ids"
            )

    @property
    def plane(self) -> RelationPlane:
        return RelationPlane.LEGAL_EFFECT


@dataclass(frozen=True, slots=True)
class SearchRoutingRelation:
    relation_id: str
    source: ResearchCoordinate
    target: ResearchCoordinate
    kind: SearchRoutingKind
    route: SearchRouteKind
    reason: str

    def __post_init__(self) -> None:
        _require_id(self.relation_id, "relation_id")
        object.__setattr__(self, "kind", SearchRoutingKind(self.kind))
        object.__setattr__(self, "route", SearchRouteKind(self.route))
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ResearchStateError("search-routing relation requires a reason")

    @property
    def plane(self) -> RelationPlane:
        return RelationPlane.SEARCH_ROUTING


ResearchRelation: TypeAlias = (
    PhysicalLinkRelation | LegalEffectRelation | SearchRoutingRelation
)


class CandidateProvenance(_StrEnum):
    """Discovery origins plus the protected/verified lifecycle states."""

    SYSTEM_PRIOR = "SYSTEM_PRIOR"
    GROUNDED_CONCEPT = "GROUNDED_CONCEPT"
    SEMANTIC_ENTRY = "SEMANTIC_ENTRY"
    RELATION_EXPANDED = "RELATION_EXPANDED"
    PROTECTED_CANDIDATE = "PROTECTED_CANDIDATE"
    VERIFIED_EVIDENCE = "VERIFIED_EVIDENCE"


DISCOVERY_ORIGINS = frozenset({
    CandidateProvenance.SYSTEM_PRIOR,
    CandidateProvenance.GROUNDED_CONCEPT,
    CandidateProvenance.SEMANTIC_ENTRY,
    CandidateProvenance.RELATION_EXPANDED,
})


@dataclass(frozen=True, slots=True)
class SourceSpanVerification:
    """Receipt proving that a candidate was checked against an exact source span."""

    evidence_id: str
    candidate_id: str
    coordinate: ResearchCoordinate
    source_sha256: str
    source_length: int
    authority_generation: str
    authority_as_of: str
    start: int
    end: int
    quote: str
    verification_method: str = "EXACT_SOURCE_SPAN"

    def __post_init__(self) -> None:
        _require_id(self.evidence_id, "evidence_id")
        _require_id(self.candidate_id, "candidate_id")
        if not _SHA256.fullmatch(self.source_sha256):
            raise ResearchStateError("source_sha256 must be a lowercase SHA-256")
        if not isinstance(self.source_length, int) or self.source_length < 1:
            raise ResearchStateError("source_length must be a positive integer")
        if not isinstance(self.authority_generation, str) \
                or not self.authority_generation.strip():
            raise ResearchStateError("authority_generation must be non-empty")
        if not isinstance(self.authority_as_of, str) or not self.authority_as_of.strip():
            raise ResearchStateError("authority_as_of must be non-empty")
        if not isinstance(self.start, int) or not isinstance(self.end, int):
            raise ResearchStateError("source span offsets must be integers")
        if self.start < 0 or self.end <= self.start:
            raise ResearchStateError("source span must satisfy 0 <= start < end")
        if not isinstance(self.quote, str) or not self.quote.strip():
            raise ResearchStateError("source span verification requires a quote")
        if len(self.quote) != self.end - self.start:
            raise ResearchStateError("quote length must equal end - start")
        if self.end > self.source_length:
            raise ResearchStateError("source span exceeds source_length")
        if not isinstance(self.verification_method, str) \
                or not self.verification_method.strip():
            raise ResearchStateError("verification_method must be non-empty")
        if self.verification_method != "EXACT_SOURCE_SPAN":
            raise ResearchStateError(
                "verification_method must be EXACT_SOURCE_SPAN"
            )


@dataclass(frozen=True, slots=True)
class ProvenanceTransition:
    from_states: tuple[CandidateProvenance, ...]
    to_state: CandidateProvenance
    reason: str


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    candidate_id: str
    coordinate: ResearchCoordinate
    states: frozenset[CandidateProvenance]
    relation_ids: tuple[str, ...] = ()
    verification_receipts: tuple[SourceSpanVerification, ...] = ()
    transitions: tuple[ProvenanceTransition, ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.candidate_id, "candidate_id")
        states = frozenset(CandidateProvenance(value) for value in self.states)
        object.__setattr__(self, "states", states)
        object.__setattr__(self, "relation_ids", _unique_nonempty(self.relation_ids))
        if not states & DISCOVERY_ORIGINS:
            raise ResearchStateError("candidate requires at least one discovery origin")
        if CandidateProvenance.RELATION_EXPANDED in states and not self.relation_ids:
            raise ResearchStateError(
                "RELATION_EXPANDED candidate requires relation_ids provenance"
            )
        verified = CandidateProvenance.VERIFIED_EVIDENCE in states
        protected = CandidateProvenance.PROTECTED_CANDIDATE in states
        if verified and not protected:
            raise ResearchStateError(
                "VERIFIED_EVIDENCE requires prior PROTECTED_CANDIDATE state"
            )
        if verified and not self.verification_receipts:
            raise ResearchStateError(
                "VERIFIED_EVIDENCE requires exact source verification receipts"
            )
        if self.verification_receipts and not verified:
            raise ResearchStateError(
                "verification receipts may only be stored in VERIFIED_EVIDENCE state"
            )
        for receipt in self.verification_receipts:
            if receipt.candidate_id != self.candidate_id:
                raise ResearchStateError("verification receipt candidate_id mismatch")
            if receipt.coordinate != self.coordinate:
                raise ResearchStateError("verification receipt coordinate mismatch")

    @property
    def protected(self) -> bool:
        return CandidateProvenance.PROTECTED_CANDIDATE in self.states

    @property
    def verified(self) -> bool:
        return CandidateProvenance.VERIFIED_EVIDENCE in self.states

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(receipt.evidence_id for receipt in self.verification_receipts)

    @property
    def raw_relation_expansion(self) -> bool:
        return (
            CandidateProvenance.RELATION_EXPANDED in self.states
            and not self.verified
        )


def seed_candidate(
    candidate_id: str,
    coordinate: ResearchCoordinate,
    origin: CandidateProvenance | str,
    *,
    relation_ids: Iterable[str] = (),
) -> CandidateRecord:
    canonical = CandidateProvenance(origin)
    if canonical not in DISCOVERY_ORIGINS:
        raise ResearchStateError("seed origin must be a discovery provenance")
    return CandidateRecord(
        candidate_id=candidate_id,
        coordinate=coordinate,
        states=frozenset({canonical}),
        relation_ids=tuple(relation_ids),
    )


def add_candidate_origin(
    candidate: CandidateRecord,
    origin: CandidateProvenance | str,
    *,
    relation_ids: Iterable[str] = (),
) -> CandidateRecord:
    """Merge another discovery signal without claiming verification."""

    canonical = CandidateProvenance(origin)
    if canonical not in DISCOVERY_ORIGINS:
        raise ResearchStateError("origin must be a discovery provenance")
    merged_relation_ids = _unique_nonempty(
        (*candidate.relation_ids, *tuple(relation_ids))
    )
    if canonical == CandidateProvenance.RELATION_EXPANDED and not merged_relation_ids:
        raise ResearchStateError("RELATION_EXPANDED origin requires relation_ids")
    return replace(
        candidate,
        states=frozenset((*candidate.states, canonical)),
        relation_ids=merged_relation_ids,
    )


def promote_candidate(
    candidate: CandidateRecord,
    target: CandidateProvenance | str,
    *,
    reason: str,
) -> CandidateRecord:
    """Protect a candidate; verification must use :func:`verify_candidate`.

    Discovery states are independent origins rather than a false total order.
    The sole ordinary promotion is discovery -> protected.  In particular,
    RELATION_EXPANDED -> VERIFIED_EVIDENCE is rejected even when requested
    explicitly.
    """

    canonical = CandidateProvenance(target)
    if canonical == CandidateProvenance.VERIFIED_EVIDENCE:
        raise ResearchStateError(
            "VERIFIED_EVIDENCE requires verify_candidate and a source receipt"
        )
    if canonical != CandidateProvenance.PROTECTED_CANDIDATE:
        raise ResearchStateError("only PROTECTED_CANDIDATE is a promotion target")
    if not isinstance(reason, str) or not reason.strip():
        raise ResearchStateError("promotion reason must be non-empty")
    if candidate.protected:
        return candidate
    transition = ProvenanceTransition(
        from_states=tuple(sorted(candidate.states, key=lambda item: item.value)),
        to_state=canonical,
        reason=reason,
    )
    return replace(
        candidate,
        states=frozenset((*candidate.states, canonical)),
        transitions=(*candidate.transitions, transition),
    )


SourceResolver = Callable[[ResearchCoordinate], str]


def build_source_span_verification(
    candidate_id: str,
    coordinate: ResearchCoordinate,
    source_text: str,
    *,
    authority_generation: str,
    authority_as_of: str,
    start: int = 0,
    end: int | None = None,
    evidence_id: str | None = None,
) -> SourceSpanVerification:
    """Create a generation-bound receipt from actual source bytes.

    The receipt remains data; trust is established only when
    :func:`verify_candidate` or :func:`validate_candidate_verification`
    resolves the current source again and compares the hash and exact slice.
    """

    if not isinstance(source_text, str) or not source_text:
        raise ResearchStateError("source_text must be a non-empty string")
    if end is None:
        end = len(source_text)
    if not isinstance(start, int) or not isinstance(end, int) \
            or start < 0 or end <= start or end > len(source_text):
        raise ResearchStateError("source span is outside source_text")
    source_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    if evidence_id is None:
        evidence_id = "source-span-" + hashlib.sha256(
            (
                f"{candidate_id}:{coordinate.document_id}:{coordinate.node_id}:"
                f"{authority_generation}:{authority_as_of}:{source_sha256}:"
                f"{start}:{end}"
            ).encode("utf-8")
        ).hexdigest()[:24]
    return SourceSpanVerification(
        evidence_id=evidence_id,
        candidate_id=candidate_id,
        coordinate=coordinate,
        source_sha256=source_sha256,
        source_length=len(source_text),
        authority_generation=authority_generation,
        authority_as_of=authority_as_of,
        start=start,
        end=end,
        quote=source_text[start:end],
    )


def _validate_receipt_against_source(
    receipt: SourceSpanVerification,
    source_resolver: SourceResolver,
    *,
    authority_generation: str,
    authority_as_of: str,
) -> None:
    if receipt.authority_generation != authority_generation:
        raise ResearchStateError("verification receipt authority_generation mismatch")
    if receipt.authority_as_of != authority_as_of:
        raise ResearchStateError("verification receipt authority_as_of mismatch")
    source_text = source_resolver(receipt.coordinate)
    if not isinstance(source_text, str) or not source_text:
        raise ResearchStateError("source resolver returned no current source text")
    if len(source_text) != receipt.source_length:
        raise ResearchStateError("verification receipt source_length mismatch")
    if hashlib.sha256(source_text.encode("utf-8")).hexdigest() \
            != receipt.source_sha256:
        raise ResearchStateError("verification receipt source_sha256 mismatch")
    if source_text[receipt.start:receipt.end] != receipt.quote:
        raise ResearchStateError("verification receipt quote is not the source slice")


def verify_candidate(
    candidate: CandidateRecord,
    receipts: Iterable[SourceSpanVerification],
    *,
    source_resolver: SourceResolver,
    authority_generation: str,
    authority_as_of: str,
    reason: str = "exact source span verified",
) -> CandidateRecord:
    """Promote a protected candidate using exact, coordinate-bound receipts."""

    if not candidate.protected:
        raise ResearchStateError(
            "candidate must be protected before source verification promotion"
        )
    if not isinstance(reason, str) or not reason.strip():
        raise ResearchStateError("verification reason must be non-empty")
    receipt_rows = tuple(receipts)
    if not receipt_rows:
        raise ResearchStateError("at least one source verification receipt is required")
    for receipt in receipt_rows:
        if receipt.candidate_id != candidate.candidate_id:
            raise ResearchStateError("verification receipt candidate_id mismatch")
        if receipt.coordinate != candidate.coordinate:
            raise ResearchStateError("verification receipt coordinate mismatch")
        _validate_receipt_against_source(
            receipt,
            source_resolver,
            authority_generation=authority_generation,
            authority_as_of=authority_as_of,
        )
    merged = {
        receipt.evidence_id: receipt
        for receipt in (*candidate.verification_receipts, *receipt_rows)
    }
    transition = ProvenanceTransition(
        from_states=tuple(sorted(candidate.states, key=lambda item: item.value)),
        to_state=CandidateProvenance.VERIFIED_EVIDENCE,
        reason=reason,
    )
    return replace(
        candidate,
        states=frozenset((*candidate.states, CandidateProvenance.VERIFIED_EVIDENCE)),
        verification_receipts=tuple(merged[key] for key in sorted(merged)),
        transitions=(*candidate.transitions, transition),
    )


def validate_candidate_verification(
    candidate: CandidateRecord,
    source_resolver: SourceResolver,
    *,
    authority_generation: str,
    authority_as_of: str,
) -> tuple[str, ...]:
    """Revalidate every stored receipt against the current source snapshot."""

    if not candidate.verified or not candidate.protected:
        raise ResearchStateError("candidate is not verified evidence")
    if not candidate.verification_receipts:
        raise ResearchStateError("verified candidate has no receipts")
    for receipt in candidate.verification_receipts:
        if receipt.candidate_id != candidate.candidate_id \
                or receipt.coordinate != candidate.coordinate:
            raise ResearchStateError("candidate verification receipt identity mismatch")
        _validate_receipt_against_source(
            receipt,
            source_resolver,
            authority_generation=authority_generation,
            authority_as_of=authority_as_of,
        )
    return candidate.evidence_ids


@dataclass(frozen=True, slots=True)
class CoverageBinding:
    """A proposed value for one behavior coverage cell."""

    value: Any
    candidate_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_ids", _unique_nonempty(self.candidate_ids))
        object.__setattr__(self, "evidence_ids", _unique_nonempty(self.evidence_ids))


class TargetedSearchActionKind(_StrEnum):
    LOCATE_MISSING_COVERAGE = "LOCATE_MISSING_COVERAGE"
    VERIFY_SOURCE_SPAN = "VERIFY_SOURCE_SPAN"


@dataclass(frozen=True, slots=True)
class TargetedSearchAction:
    coverage_key: str
    coverage_state: CoverageState
    action: TargetedSearchActionKind
    route: SearchRouteKind
    policy_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage_key": self.coverage_key,
            "coverage_state": self.coverage_state.value,
            "action": self.action.value,
            "route": self.route.value,
            "policy_actions": list(self.policy_actions),
        }


@dataclass(frozen=True, slots=True)
class RelationAssessmentInput:
    """Verified inputs for a later assessor, not an assessment result."""

    predicate: RelationPredicate
    axis: str
    facts: Mapping[str, EvidenceFact]
    candidate_ids_by_coverage: Mapping[str, tuple[str, ...]]
    prohibited_inferences: tuple[str, ...]

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(sorted({
            evidence_id
            for fact in self.facts.values()
            for evidence_id in fact.evidence_ids
        }))


@dataclass(frozen=True, slots=True)
class EvidenceCompilation:
    behavior: RelationBehaviorAssessment
    assessment_input: RelationAssessmentInput | None
    targeted_search_actions: tuple[TargetedSearchAction, ...]
    direct_conclusion_allowed: bool = False

    @property
    def ready_for_assessment(self) -> bool:
        return self.assessment_input is not None

    def to_dict(self) -> dict[str, Any]:
        behavior = self.behavior.to_dict()
        # ``behavior.py`` predates this compiler and calls coverage readiness
        # ``may_render_definitive_conclusion``.  Do not leak that name through
        # the compiler facade: coverage authorizes only a later assessment.
        policy_ready = bool(behavior.pop("may_render_definitive_conclusion", False))
        return {
            "behavior": behavior,
            "behavior_policy_ready_for_assessment": policy_ready,
            "ready_for_assessment": self.ready_for_assessment,
            "assessment_input": None if self.assessment_input is None else {
                "predicate": self.assessment_input.predicate.value,
                "axis": self.assessment_input.axis,
                "evidence_ids": list(self.assessment_input.evidence_ids),
                "candidate_ids_by_coverage": {
                    key: list(value)
                    for key, value in self.assessment_input.candidate_ids_by_coverage.items()
                },
                "prohibited_inferences": list(
                    self.assessment_input.prohibited_inferences
                ),
            },
            "targeted_search_actions": [
                action.to_dict() for action in self.targeted_search_actions
            ],
            "direct_conclusion_allowed": False,
        }


@dataclass(frozen=True, slots=True)
class ResearchEvidenceBundle:
    """Question-level facade over one or more relation evidence compilers."""

    question: str
    candidates: Mapping[str, CandidateRecord]
    compilations: Mapping[RelationPredicate, EvidenceCompilation]
    direct_conclusion_allowed: bool = False

    @property
    def assessment_inputs(self) -> tuple[RelationAssessmentInput, ...]:
        return tuple(
            compilation.assessment_input
            for compilation in self.compilations.values()
            if compilation.assessment_input is not None
        )

    @property
    def needs_targeted_search(self) -> bool:
        return any(
            compilation.targeted_search_actions
            for compilation in self.compilations.values()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "candidate_count": len(self.candidates),
            "candidate_states": {
                candidate_id: sorted(state.value for state in candidate.states)
                for candidate_id, candidate in self.candidates.items()
            },
            "compilations": {
                predicate.value: compilation.to_dict()
                for predicate, compilation in self.compilations.items()
            },
            "assessment_input_count": len(self.assessment_inputs),
            "needs_targeted_search": self.needs_targeted_search,
            "direct_conclusion_allowed": False,
        }


_RELATION_ROUTE_KEYS = frozenset({
    "legal_basis", "original_delegation", "implementing_instrument",
    "supplemental_rule", "target_rule", "target_regime", "target_requirements",
    "instrument", "definition",
})
_STRUCTURE_ROUTE_KEYS = frozenset({
    "delegated_scope", "redelegated_scope", "authority_scope", "task_scope",
    "approval_scope", "received_scope", "incorporation_scope", "dependency_scope",
    "basis_scope", "definition_scope", "adaptation_map",
})


def _missing_route(coverage_key: str) -> SearchRouteKind:
    if coverage_key in _RELATION_ROUTE_KEYS:
        return SearchRouteKind.RELATION
    if coverage_key in _STRUCTURE_ROUTE_KEYS:
        return SearchRouteKind.STRUCTURE_MOVE
    return SearchRouteKind.DOCUMENT_SEARCH


def _compile_fact(
    binding: CoverageBinding | None,
    candidates: Mapping[str, CandidateRecord],
) -> EvidenceFact | None:
    if binding is None:
        return None
    rows = [candidates.get(candidate_id) for candidate_id in binding.candidate_ids]
    present_rows = [row for row in rows if row is not None]
    verified_ids = {
        evidence_id
        for row in present_rows
        for evidence_id in row.evidence_ids
    }
    observation_ids = {
        relation_id
        for row in present_rows
        for relation_id in row.relation_ids
    }
    requested_ids = set(binding.evidence_ids)
    effective_ids = requested_ids or verified_ids or observation_ids
    verified = bool(
        binding.candidate_ids
        and len(present_rows) == len(binding.candidate_ids)
        and all(row.verified for row in present_rows)
        and verified_ids
        and (not requested_ids or requested_ids <= verified_ids)
    )
    return EvidenceFact(
        value=binding.value,
        evidence_ids=tuple(sorted(effective_ids)),
        verified=verified,
    )


def compile_relation_evidence(
    predicate: RelationPredicate | str,
    bindings: Mapping[str, CoverageBinding],
    candidates: Mapping[str, CandidateRecord],
) -> EvidenceCompilation:
    """Compile verified coverage and call the canonical behavior gate.

    Relation IDs may preserve an unverified observation, but only source span
    receipts can make an ``EvidenceFact`` verified.  A ready behavior result is
    converted only into ``RelationAssessmentInput``; no substantive conclusion
    is emitted here.
    """

    canonical = RelationPredicate(predicate)
    policy = RELATION_BEHAVIOR_POLICIES.get(canonical)
    if policy is None:
        # Preserve behavior.py's canonical error type and message.
        assess_relation_behavior(canonical, {})
        raise AssertionError("unreachable")
    unknown = sorted(set(bindings) - set(policy.required_coverage))
    if unknown:
        raise ResearchStateError(
            f"coverage bindings outside policy: {', '.join(unknown)}"
        )

    facts: dict[str, EvidenceFact] = {}
    for key in policy.required_coverage:
        fact = _compile_fact(bindings.get(key), candidates)
        if fact is not None:
            facts[key] = fact
    behavior = assess_relation_behavior(canonical, facts)

    actions: list[TargetedSearchAction] = []
    for key in behavior.missing_coverage:
        actions.append(TargetedSearchAction(
            coverage_key=key,
            coverage_state=CoverageState.MISSING,
            action=TargetedSearchActionKind.LOCATE_MISSING_COVERAGE,
            route=_missing_route(key),
            policy_actions=behavior.actions,
        ))
    for key in behavior.unverified_coverage:
        actions.append(TargetedSearchAction(
            coverage_key=key,
            coverage_state=CoverageState.UNVERIFIED,
            action=TargetedSearchActionKind.VERIFY_SOURCE_SPAN,
            route=SearchRouteKind.SOURCE_VERIFICATION,
            policy_actions=behavior.actions,
        ))

    assessment_input = None
    if behavior.status == BehaviorStatus.READY_FOR_ASSESSMENT:
        candidate_ids_by_coverage = MappingProxyType({
            key: bindings[key].candidate_ids for key in policy.required_coverage
        })
        assessment_input = RelationAssessmentInput(
            predicate=canonical,
            axis=behavior.axis.value,
            facts=MappingProxyType(dict(facts)),
            candidate_ids_by_coverage=candidate_ids_by_coverage,
            prohibited_inferences=behavior.prohibited_inferences,
        )
    return EvidenceCompilation(
        behavior=behavior,
        assessment_input=assessment_input,
        targeted_search_actions=tuple(actions),
        direct_conclusion_allowed=False,
    )


def compile_research_evidence(
    question: str,
    candidates: Mapping[str, CandidateRecord] | Iterable[CandidateRecord],
    *,
    relation_predicates: Iterable[RelationPredicate | str],
    bindings_by_predicate: Mapping[
        RelationPredicate | str, Mapping[str, CoverageBinding]
    ] | None = None,
) -> ResearchEvidenceBundle:
    """Compile all activated relation predicates for one research question.

    The facade is intentionally deterministic.  It does not infer bindings
    from the question.  A caller may omit ``bindings_by_predicate`` to obtain
    each predicate's complete missing-coverage and targeted-search plan.
    """

    if not isinstance(question, str) or not question.strip():
        raise ResearchStateError("question must be a non-empty string")
    if isinstance(candidates, Mapping):
        candidate_map = dict(candidates)
        for candidate_id, candidate in candidate_map.items():
            if candidate_id != candidate.candidate_id:
                raise ResearchStateError(
                    f"candidate mapping key mismatch: {candidate_id!r}"
                )
    else:
        candidate_map = {}
        for candidate in candidates:
            if candidate.candidate_id in candidate_map:
                raise ResearchStateError(
                    f"duplicate candidate_id: {candidate.candidate_id}"
                )
            candidate_map[candidate.candidate_id] = candidate

    predicates = tuple(dict.fromkeys(
        RelationPredicate(predicate) for predicate in relation_predicates
    ))
    provided: dict[RelationPredicate, Mapping[str, CoverageBinding]] = {}
    for predicate, bindings in (bindings_by_predicate or {}).items():
        canonical = RelationPredicate(predicate)
        if canonical in provided:
            raise ResearchStateError(
                f"duplicate bindings for predicate: {canonical.value}"
            )
        provided[canonical] = bindings
    extra = sorted(
        set(provided) - set(predicates), key=lambda item: item.value
    )
    if extra:
        raise ResearchStateError(
            "bindings supplied for inactive predicates: "
            + ", ".join(item.value for item in extra)
        )

    compilations = {
        predicate: compile_relation_evidence(
            predicate, provided.get(predicate, {}), candidate_map
        )
        for predicate in predicates
    }
    return ResearchEvidenceBundle(
        question=question,
        candidates=MappingProxyType(candidate_map),
        compilations=MappingProxyType(compilations),
        direct_conclusion_allowed=False,
    )


class SubsumptionElementKind(_StrEnum):
    CONDITION = "CONDITION"
    EXCEPTION = "EXCEPTION"


class SupportState(_StrEnum):
    """Evidence-backed truth state of a condition or exception proposition."""

    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNKNOWN = "UNKNOWN"


class SubsumptionOutcome(_StrEnum):
    RULE_APPLIES = "RULE_APPLIES"
    RULE_DOES_NOT_APPLY = "RULE_DOES_NOT_APPLY"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True, slots=True)
class SubsumptionCheck:
    check_id: str
    kind: SubsumptionElementKind
    proposition: str
    support: SupportState
    evidence_ids: tuple[str, ...] = ()
    verified: bool = False

    def __post_init__(self) -> None:
        _require_id(self.check_id, "check_id")
        object.__setattr__(self, "kind", SubsumptionElementKind(self.kind))
        object.__setattr__(self, "support", SupportState(self.support))
        object.__setattr__(self, "evidence_ids", _unique_nonempty(self.evidence_ids))
        if not isinstance(self.proposition, str) or not self.proposition.strip():
            raise ResearchStateError("subsumption proposition must be non-empty")


@dataclass(frozen=True, slots=True)
class SubsumptionResult:
    outcome: SubsumptionOutcome
    conditions: tuple[SubsumptionCheck, ...]
    exceptions: tuple[SubsumptionCheck, ...]
    unknown_check_ids: tuple[str, ...]
    definite_conclusion_allowed: bool
    gate_blockers: tuple[str, ...]
    conclusion_evidence_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        def row(check: SubsumptionCheck) -> dict[str, Any]:
            return {
                "check_id": check.check_id,
                "kind": check.kind.value,
                "proposition": check.proposition,
                "support": check.support.value,
                "evidence_ids": list(check.evidence_ids),
                "verified": check.verified,
            }

        return {
            "outcome": self.outcome.value,
            "conditions": [row(check) for check in self.conditions],
            "exceptions": [row(check) for check in self.exceptions],
            "unknown_check_ids": list(self.unknown_check_ids),
            "definite_conclusion_allowed": self.definite_conclusion_allowed,
            "gate_blockers": list(self.gate_blockers),
            "conclusion_evidence_ids": list(self.conclusion_evidence_ids),
        }


def assess_subsumption(
    compilation: EvidenceCompilation,
    checks: Iterable[SubsumptionCheck],
    *,
    conditions_complete: bool,
    exceptions_complete: bool,
    triggered_prohibited_inferences: Iterable[str] = (),
) -> SubsumptionResult:
    """Apply the minimal condition/exception gate to verified assessment input.

    ``UNKNOWN`` or unverified checks always make the result indeterminate.
    Positive application requires every condition to be supported and every
    relevant exception to be contradicted.  A supported exception or a
    contradicted condition yields a definite non-application only when the
    entire check set is complete and verified.
    """

    rows = tuple(checks)
    ids = [check.check_id for check in rows]
    if len(ids) != len(set(ids)):
        raise ResearchStateError("subsumption check_id values must be unique")
    conditions = tuple(
        check for check in rows if check.kind == SubsumptionElementKind.CONDITION
    )
    exceptions = tuple(
        check for check in rows if check.kind == SubsumptionElementKind.EXCEPTION
    )
    blockers: list[str] = []
    if not compilation.ready_for_assessment:
        blockers.append("RELATION_COVERAGE_NOT_READY")
    if not conditions_complete:
        blockers.append("CONDITIONS_INCOMPLETE")
    if not exceptions_complete:
        blockers.append("EXCEPTIONS_INCOMPLETE")

    unknown = tuple(
        check.check_id for check in rows if check.support == SupportState.UNKNOWN
    )
    blockers.extend(f"UNKNOWN_CHECK:{check_id}" for check_id in unknown)
    for check in rows:
        if check.support != SupportState.UNKNOWN \
                and (not check.verified or not check.evidence_ids):
            blockers.append(f"UNVERIFIED_CHECK:{check.check_id}")

    prohibited = tuple(sorted(set(str(item) for item in
                                  triggered_prohibited_inferences if str(item))))
    blockers.extend(f"PROHIBITED_INFERENCE:{item}" for item in prohibited)

    allowed = not blockers
    outcome = SubsumptionOutcome.INDETERMINATE
    if allowed:
        condition_failed = any(
            check.support == SupportState.CONTRADICTED for check in conditions
        )
        exception_applies = any(
            check.support == SupportState.SUPPORTED for check in exceptions
        )
        if condition_failed or exception_applies:
            outcome = SubsumptionOutcome.RULE_DOES_NOT_APPLY
        elif (
            all(check.support == SupportState.SUPPORTED for check in conditions)
            and all(check.support == SupportState.CONTRADICTED for check in exceptions)
        ):
            outcome = SubsumptionOutcome.RULE_APPLIES
        else:  # Defensive against a future SupportState added without gate logic.
            allowed = False
            blockers.append("UNHANDLED_SUPPORT_STATE")

    evidence_ids = ()
    if allowed:
        evidence_ids = tuple(sorted({
            *(
                compilation.assessment_input.evidence_ids
                if compilation.assessment_input is not None else ()
            ),
            *(evidence_id for check in rows for evidence_id in check.evidence_ids),
        }))
    return SubsumptionResult(
        outcome=outcome,
        conditions=conditions,
        exceptions=exceptions,
        unknown_check_ids=unknown,
        definite_conclusion_allowed=allowed,
        gate_blockers=tuple(blockers),
        conclusion_evidence_ids=evidence_ids,
    )


def _require_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchStateError(f"{field_name} must be a non-empty string")
    return value


def _unique_nonempty(values: Iterable[object]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ResearchStateError("identifier collections require non-empty strings")
        normalized.append(value.strip())
    return tuple(dict.fromkeys(normalized))


__all__ = [
    "CandidateProvenance",
    "CandidateRecord",
    "CoverageBinding",
    "DISCOVERY_ORIGINS",
    "EvidenceCompilation",
    "LegalEffectRelation",
    "PhysicalLinkKind",
    "PhysicalLinkRelation",
    "ProvenanceTransition",
    "RelationAssessmentInput",
    "RelationPlane",
    "ResearchCoordinate",
    "ResearchEvidenceBundle",
    "ResearchRelation",
    "ResearchStateError",
    "SearchRouteKind",
    "SearchRoutingKind",
    "SearchRoutingRelation",
    "SourceSpanVerification",
    "SubsumptionCheck",
    "SubsumptionElementKind",
    "SubsumptionOutcome",
    "SubsumptionResult",
    "SupportState",
    "TargetedSearchAction",
    "TargetedSearchActionKind",
    "add_candidate_origin",
    "assess_subsumption",
    "compile_relation_evidence",
    "compile_research_evidence",
    "promote_candidate",
    "seed_candidate",
    "verify_candidate",
]
