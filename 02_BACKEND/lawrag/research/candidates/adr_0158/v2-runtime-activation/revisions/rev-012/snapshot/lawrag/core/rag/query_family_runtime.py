"""Fail-open, extensible query-family runtime prototype.

This module is deliberately independent from the product search pipeline.  It
turns a question into multiple *strategy hypotheses*, always runs a universal
retrieval adapter, activates family-specific closure recipes add-only, checks
evidence coverage, and records feedback as an observation rather than legal
truth.

The output row names follow ``legal-graph-v1`` so a later adapter can persist
or stream them without making query families part of the canonical corpus.
No LLM, corpus write, or MAIN switch is used here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol, Sequence

from lawrag.core.legal_graph import (
    ClaimStatus,
    Layer,
    RelationPredicate,
    RowType,
    SCHEMA_VERSION,
    stable_id,
    validate_row,
)


UNKNOWN_FAMILY = "UNKNOWN"
GENERIC_FALLBACK_ROUTES = (
    "GENERIC_ENTITY_RETRIEVAL",
    "EXACT_REFERENCE_RETRIEVAL",
    "GRAPH_NEIGHBOR_EXPANSION",
)


class AnswerStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PROVISIONAL = "PROVISIONAL"
    NEEDS_FACT = "NEEDS_FACT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class CoverageState(str, Enum):
    SATISFIED = "SATISFIED"
    MISSING = "MISSING"


@dataclass(frozen=True)
class QueryFrame:
    """Question-only runtime frame; it contains no inferred legal conclusion."""

    id: str
    query: str
    slots: Mapping[str, tuple[str, ...]]
    requested_goals: tuple[str, ...]

    def to_row(self, *, generation_id: str, authority_generation: str) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "generation_id": generation_id,
            "authority_generation": authority_generation,
            "layer": Layer.RUNTIME.value,
            "row_type": RowType.QUERY_FRAME.value,
            "id": self.id,
            "query": self.query,
            "slots": {key: list(values) for key, values in self.slots.items()},
            "requested_goals": list(self.requested_goals),
        }


@dataclass(frozen=True)
class QueryFamilyDefinition:
    """Data-driven search recipe.

    ``axes`` and coverage keys intentionally remain open strings.  Adding a
    query family therefore does not require changing a Python enum.  Closure
    predicates are restricted to the canonical Legal Graph vocabulary.
    """

    family_id: str
    version: int
    axes: tuple[str, ...]
    trigger_phrases: tuple[str, ...] = ()
    trigger_regexes: tuple[str, ...] = ()
    slot_hints: tuple[str, ...] = ()
    required_coverage: tuple[str, ...] = ()
    closure_predicates: tuple[str, ...] = ()
    fallback_routes: tuple[str, ...] = GENERIC_FALLBACK_ROUTES
    parents: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", self.family_id):
            raise ValueError(f"invalid family_id: {self.family_id!r}")
        if self.family_id == UNKNOWN_FAMILY:
            raise ValueError("UNKNOWN is reserved for fail-open routing")
        if self.version < 1:
            raise ValueError("family version must be positive")
        for pattern in self.trigger_regexes:
            re.compile(pattern)
        for predicate in self.closure_predicates:
            RelationPredicate(predicate)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "QueryFamilyDefinition":
        def values(name: str) -> tuple[str, ...]:
            raw = value.get(name) or ()
            if isinstance(raw, str) or not isinstance(raw, Sequence):
                raise ValueError(f"{name} must be an array")
            return tuple(str(item) for item in raw if str(item).strip())

        return cls(
            family_id=str(value["family_id"]),
            version=int(value.get("version", 1)),
            axes=values("axes"),
            trigger_phrases=values("trigger_phrases"),
            trigger_regexes=values("trigger_regexes"),
            slot_hints=values("slot_hints"),
            required_coverage=values("required_coverage"),
            closure_predicates=values("closure_predicates"),
            fallback_routes=values("fallback_routes") or GENERIC_FALLBACK_ROUTES,
            parents=values("parents"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "version": self.version,
            "axes": list(self.axes),
            "trigger_phrases": list(self.trigger_phrases),
            "trigger_regexes": list(self.trigger_regexes),
            "slot_hints": list(self.slot_hints),
            "required_coverage": list(self.required_coverage),
            "closure_predicates": list(self.closure_predicates),
            "fallback_routes": list(self.fallback_routes),
            "parents": list(self.parents),
        }


@dataclass(frozen=True)
class FamilyHypothesis:
    family_id: str
    version: int
    score: float
    matched_triggers: tuple[str, ...] = ()
    matched_slots: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "version": self.version,
            "score": round(self.score, 6),
            "matched_triggers": list(self.matched_triggers),
            "matched_slots": list(self.matched_slots),
        }


class QueryFamilyRegistry:
    """Versioned in-memory registry; definitions can later come from a DB/file."""

    def __init__(self, definitions: Iterable[QueryFamilyDefinition] = ()) -> None:
        self._definitions: dict[str, QueryFamilyDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: QueryFamilyDefinition, *, replace: bool = False) -> None:
        current = self._definitions.get(definition.family_id)
        if current is not None and not replace:
            raise ValueError(f"family already registered: {definition.family_id}")
        if current is not None and definition.version <= current.version:
            raise ValueError("replacement family version must increase")
        self._definitions[definition.family_id] = definition

    def get(self, family_id: str) -> QueryFamilyDefinition | None:
        return self._definitions.get(family_id)

    def definitions(self) -> tuple[QueryFamilyDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def classify(
        self,
        frame: QueryFrame,
        *,
        threshold: float = 0.45,
        max_families: int = 5,
    ) -> tuple[FamilyHypothesis, ...]:
        packed = _pack(frame.query)
        hypotheses: list[FamilyHypothesis] = []
        for definition in self.definitions():
            phrase_hits = tuple(
                phrase for phrase in definition.trigger_phrases
                if _pack(phrase) and _pack(phrase) in packed
            )
            regex_hits = tuple(
                pattern for pattern in definition.trigger_regexes
                if re.search(pattern, frame.query, flags=re.IGNORECASE)
            )
            slot_hits = tuple(
                slot for slot in definition.slot_hints if frame.slots.get(slot)
            )
            if not phrase_hits and not regex_hits and not slot_hits:
                continue
            score = min(
                0.99,
                0.38
                + 0.18 * len(phrase_hits)
                + 0.14 * len(regex_hits)
                + 0.06 * len(slot_hits),
            )
            if score < threshold:
                continue
            hypotheses.append(FamilyHypothesis(
                family_id=definition.family_id,
                version=definition.version,
                score=score,
                matched_triggers=tuple(dict.fromkeys((*phrase_hits, *regex_hits))),
                matched_slots=slot_hits,
            ))
        hypotheses.sort(key=lambda item: (-item.score, item.family_id))
        hypotheses = hypotheses[:max(0, max_families)]
        unknown_score = 1.0 if not hypotheses else max(0.05, 1.0 - hypotheses[0].score)
        hypotheses.append(FamilyHypothesis(
            family_id=UNKNOWN_FAMILY,
            version=1,
            score=unknown_score,
        ))
        return tuple(hypotheses)


@dataclass(frozen=True)
class SearchCandidate:
    """Adapter-neutral candidate backed by a Legal Graph endpoint."""

    member_id: str
    endpoint: Mapping[str, Any]
    origin: str
    score: float = 0.0
    supports: tuple[str, ...] = ()
    relation_assertion_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Activation:
    relation_assertion_id: str
    activated: bool
    reason: str
    family_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExpansionResult:
    candidates: tuple[SearchCandidate, ...] = ()
    activations: tuple[Activation, ...] = ()


class RetrievalAdapter(Protocol):
    """Boundary to the existing or future search implementation."""

    def universal_search(self, frame: QueryFrame) -> Iterable[SearchCandidate]: ...

    def family_search(
        self,
        frame: QueryFrame,
        hypothesis: FamilyHypothesis,
        incumbent: Sequence[SearchCandidate],
    ) -> Iterable[SearchCandidate]: ...

    def expand_closure(
        self,
        frame: QueryFrame,
        predicates: frozenset[str],
        incumbent: Sequence[SearchCandidate],
        family_ids: tuple[str, ...],
    ) -> ExpansionResult: ...

    def fallback_search(
        self,
        frame: QueryFrame,
        routes: tuple[str, ...],
        missing_coverage: tuple[str, ...],
        incumbent: Sequence[SearchCandidate],
    ) -> Iterable[SearchCandidate]: ...


class NullRetrievalAdapter:
    """Planning-only adapter useful before the real search adapter is wired."""

    def universal_search(self, frame: QueryFrame) -> Iterable[SearchCandidate]:
        return ()

    def family_search(
        self,
        frame: QueryFrame,
        hypothesis: FamilyHypothesis,
        incumbent: Sequence[SearchCandidate],
    ) -> Iterable[SearchCandidate]:
        return ()

    def expand_closure(
        self,
        frame: QueryFrame,
        predicates: frozenset[str],
        incumbent: Sequence[SearchCandidate],
        family_ids: tuple[str, ...],
    ) -> ExpansionResult:
        return ExpansionResult()

    def fallback_search(
        self,
        frame: QueryFrame,
        routes: tuple[str, ...],
        missing_coverage: tuple[str, ...],
        incumbent: Sequence[SearchCandidate],
    ) -> Iterable[SearchCandidate]:
        return ()


@dataclass(frozen=True)
class CoverageReport:
    required: tuple[str, ...]
    states: Mapping[str, CoverageState]
    missing: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": list(self.required),
            "states": {key: value.value for key, value in self.states.items()},
            "missing": list(self.missing),
        }


@dataclass(frozen=True)
class RuntimeResult:
    frame: QueryFrame
    hypotheses: tuple[FamilyHypothesis, ...]
    candidates: tuple[SearchCandidate, ...]
    activations: tuple[Activation, ...]
    coverage: CoverageReport
    answer_status: AnswerStatus
    rows: tuple[Mapping[str, Any], ...]
    trace_events: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": {
                "id": self.frame.id,
                "query": self.frame.query,
                "slots": {key: list(value) for key, value in self.frame.slots.items()},
                "requested_goals": list(self.frame.requested_goals),
            },
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "candidate_ids": [item.member_id for item in self.candidates],
            "coverage": self.coverage.to_dict(),
            "answer_status": self.answer_status.value,
            "trace_events": list(self.trace_events),
            "rows": list(self.rows),
        }


class QueryFamilyRuntime:
    """Add-only orchestrator.  Family failures can never erase universal hits."""

    def __init__(
        self,
        registry: QueryFamilyRegistry | None = None,
        *,
        candidate_cap: int = 40,
        family_threshold: float = 0.45,
    ) -> None:
        self.registry = registry or default_registry()
        self.candidate_cap = max(1, int(candidate_cap))
        self.family_threshold = float(family_threshold)

    def run(
        self,
        query: str,
        adapter: RetrievalAdapter | None = None,
        *,
        generation_id: str = "runtime-unpublished",
        authority_generation: str = "unknown-authority-generation",
    ) -> RuntimeResult:
        adapter = adapter or NullRetrievalAdapter()
        frame = extract_query_frame(query, authority_generation=authority_generation)
        hypotheses = self.registry.classify(frame, threshold=self.family_threshold)
        active = tuple(item for item in hypotheses if item.family_id != UNKNOWN_FAMILY)
        events: list[dict[str, Any]] = [{
            "stage": "query_family_hypotheses",
            "hypotheses": [item.to_dict() for item in hypotheses],
        }]

        # Universal retrieval is an immutable floor.  A bad or absent family
        # can add noise, but cannot suppress these candidates.
        universal = _dedupe_candidates(adapter.universal_search(frame))
        candidates = list(universal)
        events.append(_stage_event("universal_retrieval", (), candidates))

        for hypothesis in active:
            before = tuple(item.member_id for item in candidates)
            additions = tuple(adapter.family_search(frame, hypothesis, tuple(candidates)))
            candidates = _append_only(candidates, additions, cap=self.candidate_cap)
            events.append(_stage_event(
                f"family:{hypothesis.family_id}", before, candidates,
                family_id=hypothesis.family_id,
            ))

        predicates = frozenset(
            predicate
            for hypothesis in active
            for predicate in (
                self.registry.get(hypothesis.family_id).closure_predicates
                if self.registry.get(hypothesis.family_id) is not None else ()
            )
        )
        expansion = adapter.expand_closure(
            frame,
            predicates,
            tuple(candidates),
            tuple(item.family_id for item in active),
        )
        before_closure = tuple(item.member_id for item in candidates)
        candidates = _append_only(candidates, expansion.candidates, cap=self.candidate_cap)
        events.append(_stage_event(
            "closure_expansion", before_closure, candidates,
            predicates=sorted(predicates),
        ))

        required = _required_coverage(frame, active, self.registry)
        coverage = check_coverage(required, candidates)
        if coverage.missing:
            routes = _fallback_routes(active, self.registry)
            before_fallback = tuple(item.member_id for item in candidates)
            additions = tuple(adapter.fallback_search(
                frame,
                routes,
                coverage.missing,
                tuple(candidates),
            ))
            candidates = _append_only(candidates, additions, cap=self.candidate_cap)
            events.append(_stage_event(
                "fail_open_fallback", before_fallback, candidates,
                routes=list(routes),
                missing_before=list(coverage.missing),
            ))
            coverage = check_coverage(required, candidates)

        answer_status = _answer_status(coverage, candidates)
        rows = _runtime_rows(
            frame=frame,
            hypotheses=hypotheses,
            candidates=candidates,
            activations=expansion.activations,
            coverage=coverage,
            answer_status=answer_status,
            events=events,
            generation_id=generation_id,
            authority_generation=authority_generation,
        )
        for row in rows:
            validate_row(row)
        return RuntimeResult(
            frame=frame,
            hypotheses=hypotheses,
            candidates=tuple(candidates),
            activations=expansion.activations,
            coverage=coverage,
            answer_status=answer_status,
            rows=rows,
            trace_events=tuple(events),
        )


@dataclass(frozen=True)
class FeedbackCorrection:
    """A user correction remains untrusted until separately source-verified."""

    expected_member_ids: tuple[str, ...] = ()
    expected_coordinates: tuple[str, ...] = ()
    expected_answer: str = ""
    note: str = ""
    source_verified: bool = False


@dataclass(frozen=True)
class FeedbackDiagnosis:
    observation_row: Mapping[str, Any]
    first_loss: str
    reason: str
    recovery_routes: tuple[str, ...]
    candidate_signature: str
    eligible_for_family_mining: bool


def diagnose_feedback(
    result: RuntimeResult,
    correction: FeedbackCorrection,
    *,
    generation_id: str = "runtime-unpublished",
    authority_generation: str = "unknown-authority-generation",
) -> FeedbackDiagnosis:
    """Classify a correction without promoting it to canonical knowledge."""
    candidate_ids = {item.member_id for item in result.candidates}
    expected_ids = set(correction.expected_member_ids)
    active = [
        item.family_id for item in result.hypotheses
        if item.family_id != UNKNOWN_FAMILY
    ]
    if expected_ids and expected_ids <= candidate_ids:
        first_loss = "S8_PRESENTATION_OR_ASSESSMENT"
        reason = "corrected evidence was present; selection, assessment, or answer use failed"
        eligible = False
    elif not active:
        first_loss = "S1_QUERY_FAMILY_GAP"
        reason = "no registered family matched; universal retrieval did not complete the answer"
        eligible = True
    elif result.coverage.missing:
        first_loss = "S4_ACTIVATION_OR_RETRIEVAL_GAP"
        reason = "families matched but required evidence coverage remained incomplete"
        eligible = False
    else:
        first_loss = "S7_SELECTION_GAP"
        reason = "coverage was complete but the corrected evidence was not retained"
        eligible = False

    signature_parts = (
        tuple(sorted(result.frame.requested_goals)),
        tuple(sorted(result.coverage.missing)),
        tuple(sorted(result.frame.slots)),
    )
    signature = stable_id("feedback_signature", signature_parts)
    observation_id = stable_id(
        "feedback_observation",
        result.frame.id,
        correction.expected_member_ids,
        correction.expected_coordinates,
        correction.expected_answer,
        correction.note,
    )
    observation = {
        "schema_version": SCHEMA_VERSION,
        "generation_id": generation_id,
        "authority_generation": authority_generation,
        "layer": Layer.OBSERVATION.value,
        "row_type": RowType.OBSERVATION.value,
        "id": observation_id,
        "observation_kind": "USER_CORRECTION",
        "claim_status": ClaimStatus.CANDIDATE.value,
        "query_frame_id": result.frame.id,
        "first_loss": first_loss,
        "reason": reason,
        "source_verified": correction.source_verified,
        "correction": {
            "expected_member_ids": list(correction.expected_member_ids),
            "expected_coordinates": list(correction.expected_coordinates),
            "expected_answer": correction.expected_answer,
            "note": correction.note,
        },
        "candidate_signature": signature,
        "terminal_disposition": "OBSERVED_NOT_PROMOTED",
    }
    validate_row(observation)
    return FeedbackDiagnosis(
        observation_row=observation,
        first_loss=first_loss,
        reason=reason,
        recovery_routes=(
            "VERIFIED_CORRECTION_LOOKUP",
            *GENERIC_FALLBACK_ROUTES,
        ),
        candidate_signature=signature,
        eligible_for_family_mining=eligible,
    )


@dataclass(frozen=True)
class CandidateFamilyProposal:
    id: str
    signature: str
    example_observation_ids: tuple[str, ...]
    status: str = "CANDIDATE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "signature": self.signature,
            "example_observation_ids": list(self.example_observation_ids),
            "status": self.status,
            "activation": "SHADOW_ONLY",
        }


class FeedbackFamilyMiner:
    """Clusters repeated family gaps; it never registers a family itself."""

    def __init__(self) -> None:
        self._diagnoses: list[FeedbackDiagnosis] = []

    def add(self, diagnosis: FeedbackDiagnosis) -> None:
        self._diagnoses.append(diagnosis)

    def proposals(self, *, min_examples: int = 2) -> tuple[CandidateFamilyProposal, ...]:
        grouped: dict[str, list[str]] = {}
        for diagnosis in self._diagnoses:
            if not diagnosis.eligible_for_family_mining:
                continue
            grouped.setdefault(diagnosis.candidate_signature, []).append(
                str(diagnosis.observation_row["id"])
            )
        out = []
        for signature, observation_ids in sorted(grouped.items()):
            unique = tuple(dict.fromkeys(observation_ids))
            if len(unique) < max(1, int(min_examples)):
                continue
            out.append(CandidateFamilyProposal(
                id=stable_id("family_candidate", signature, unique),
                signature=signature,
                example_observation_ids=unique,
            ))
        return tuple(out)


def extract_query_frame(query: str, *, authority_generation: str) -> QueryFrame:
    text = str(query or "").strip()
    if not text:
        raise ValueError("query cannot be empty")
    slots: dict[str, tuple[str, ...]] = {}

    def found(name: str, pattern: str) -> None:
        values = tuple(dict.fromkeys(
            match.group(0).strip() for match in re.finditer(pattern, text, re.IGNORECASE)
            if match.group(0).strip()
        ))
        if values:
            slots[name] = values

    found("legal_reference", r"제\s*\d+(?:의\s*\d+)?조(?:\s*제\s*\d+항)?")
    found("quantity", r"\d+(?:\.\d+)?\s*(?:%|퍼센트|개월|년|일|시간|원|주)")
    found("ratio", r"100분의\s*\d+|\d+(?:\.\d+)?\s*%")
    found("document", r"(?:증권신고서|보고서|검토보고서|감사보고서|재무제표|서류|계약서)")
    found(
        "actor",
        r"(?:주주총회|주총|이사회|감사|대표이사|금융위원회|거래소|은행|투자자|주관회사|발행회사)",
    )
    found("delegation_signal", r"(?:대통령령|총리령|부령|시행령|시행규칙|위임|위탁)")
    found("exception_signal", r"(?:예외|제외|단서|다만|연장되는\s*경우)")

    goals: list[str] = []
    packed = _pack(text)
    goal_signals = (
        ("FORMULA", ("산정", "계산", "산식", "공식")),
        ("TEMPORAL", ("언제", "기간", "개월", "연장", "기산", "시행일")),
        ("FILING_DOCUMENT", ("제출", "첨부", "신고서", "보고서", "서류")),
        ("AUTHORITY", ("누가", "어느기관", "주총", "이사회", "권한", "결정기관")),
        ("LEGAL_BASIS", ("근거", "법적근거", "왜요구")),
        ("CLASSIFICATION", ("해당", "인지", "여부", "분류")),
        ("ENTRUSTMENT", ("위탁", "외주")),
        (
            "NEGATIVE_AUTHORITY",
            ("위임할수없", "규정이없", "권한이아니", "별도규정없", "지원되지않"),
        ),
    )
    for goal, signals in goal_signals:
        if any(_pack(signal) in packed for signal in signals):
            goals.append(goal)
    if not goals:
        goals.append("GENERAL_LEGAL_RULE")
    frame_id = stable_id(
        "qframe",
        authority_generation,
        text,
        {key: list(value) for key, value in sorted(slots.items())},
        goals,
    )
    return QueryFrame(
        id=frame_id,
        query=text,
        slots=slots,
        requested_goals=tuple(goals),
    )


def check_coverage(
    required: Iterable[str],
    candidates: Iterable[SearchCandidate],
) -> CoverageReport:
    requirements = tuple(dict.fromkeys(str(item) for item in required if str(item)))
    supported = {
        support
        for candidate in candidates
        for support in candidate.supports
    }
    states = {
        requirement: (
            CoverageState.SATISFIED if requirement in supported else CoverageState.MISSING
        )
        for requirement in requirements
    }
    missing = tuple(key for key, value in states.items() if value == CoverageState.MISSING)
    return CoverageReport(required=requirements, states=states, missing=missing)


def default_registry() -> QueryFamilyRegistry:
    return QueryFamilyRegistry(QueryFamilyDefinition.from_dict(row) for row in (
        {
            "family_id": "FORMULA",
            "version": 1,
            "axes": ["COMPUTATION"],
            "trigger_phrases": ["산정", "계산", "산식", "공식", "괴리율"],
            "required_coverage": ["formula"],
            "closure_predicates": ["COMPUTES_VALUE", "REFERENCES", "USES_DEFINITION"],
        },
        {
            "family_id": "THRESHOLD",
            "version": 1,
            "axes": ["QUANTITY", "CLASSIFICATION"],
            "trigger_phrases": ["이상", "이하", "초과", "미만", "비율", "100분의"],
            "slot_hints": ["ratio"],
            "required_coverage": ["threshold_rule"],
            "closure_predicates": ["TRIGGERS_WHEN_THRESHOLD_MET", "USES_DEFINITION", "EXCEPTION_TO"],
        },
        {
            "family_id": "TEMPORAL",
            "version": 1,
            "axes": ["TEMPORAL"],
            "trigger_phrases": ["언제", "기간", "개월", "연장", "기산", "시행일"],
            "slot_hints": ["quantity"],
            "required_coverage": ["temporal_rule"],
            "closure_predicates": ["EFFECTIVE_FROM", "EFFECTIVE_FOR", "TRANSITION_FOR", "EXCEPTION_TO"],
        },
        {
            "family_id": "FILING_DOCUMENT",
            "version": 1,
            "axes": ["DOCUMENT", "PROCEDURE"],
            "trigger_phrases": ["제출", "첨부", "신고서", "보고서", "재무서류"],
            "slot_hints": ["document"],
            "required_coverage": ["document_rule"],
            "closure_predicates": ["REQUIRES_SUBMISSION_OF", "REFERENCES", "EXCEPTION_TO"],
        },
        {
            "family_id": "AUTHORITY",
            "version": 1,
            "axes": ["AUTHORITY", "ACTOR"],
            "trigger_phrases": ["누가", "어느 기관", "주총", "이사회", "권한", "결정기관"],
            "slot_hints": ["actor"],
            "required_coverage": ["authority_holder"],
            "closure_predicates": ["ALLOCATES_AUTHORITY", "INCORPORATES_MUTATIS_MUTANDIS", "EXCEPTION_TO"],
        },
        {
            "family_id": "LEGAL_BASIS",
            "version": 1,
            "axes": ["LEGAL_BASIS"],
            "trigger_phrases": ["근거", "법적 근거", "요구되는 이유"],
            "required_coverage": ["legal_basis"],
            "closure_predicates": ["LEGAL_BASIS_IN", "REFERENCES", "DIRECTLY_APPLIES"],
        },
        {
            "family_id": "CLASSIFICATION",
            "version": 1,
            "axes": ["CLASSIFICATION", "DEFINITION"],
            "trigger_phrases": ["해당", "인지", "여부", "주요주주", "계열회사"],
            "required_coverage": ["classification_criteria"],
            "closure_predicates": ["DEFINES", "SETS_CLASSIFICATION_CRITERIA_FOR", "USES_DEFINITION", "LEGISLATIVE_DELEGATION"],
        },
        {
            "family_id": "DELEGATION",
            "version": 1,
            "axes": ["DELEGATION", "RULE_COMPLETION"],
            "trigger_phrases": ["대통령령", "총리령", "부령", "시행령", "시행규칙", "위임"],
            "slot_hints": ["delegation_signal"],
            "required_coverage": ["delegated_rule"],
            "closure_predicates": ["LEGISLATIVE_DELEGATION", "LEGISLATIVE_REDELEGATION", "SUPPLEMENTS_BY_ADMINISTRATIVE_RULE"],
        },
        {
            "family_id": "EXCEPTION",
            "version": 1,
            "axes": ["EXCEPTION", "QUALIFICATION"],
            "trigger_phrases": ["예외", "제외", "단서", "다만", "연장되는 경우"],
            "slot_hints": ["exception_signal"],
            "required_coverage": ["exception_rule"],
            "closure_predicates": ["EXCEPTION_TO", "EXCLUDES_APPLICATION_OF", "QUALIFIES_RULE"],
        },
        {
            "family_id": "ENTRUSTMENT",
            "version": 1,
            "axes": ["ENTRUSTMENT", "TASK"],
            "trigger_phrases": ["위탁", "외주", "수탁"],
            "required_coverage": ["entrustment_rule"],
            "closure_predicates": ["ENTRUSTS_TASK", "LEGAL_BASIS_IN", "EXCEPTION_TO"],
        },
        {
            "family_id": "NEGATIVE_AUTHORITY",
            "version": 1,
            "axes": ["AUTHORITY", "ABSENCE", "ASSESSMENT"],
            "trigger_phrases": [
                "위임할 수 없", "규정이 없", "권한이 아니", "별도 규정이 없",
                "지원되지 않", "위임 불가", "조정되는가",
            ],
            "required_coverage": ["authority_holder"],
            "closure_predicates": [
                "ALLOCATES_AUTHORITY", "INCORPORATES_MUTATIS_MUTANDIS",
                "EXCEPTION_TO", "LEGAL_BASIS_IN", "REFERENCES",
            ],
        },
    ))


def _pack(value: object) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value or "").casefold())


def _dedupe_candidates(values: Iterable[SearchCandidate]) -> list[SearchCandidate]:
    out: list[SearchCandidate] = []
    seen: set[str] = set()
    for value in values:
        if value.member_id in seen:
            continue
        seen.add(value.member_id)
        out.append(value)
    return out


def _append_only(
    floor: Sequence[SearchCandidate],
    additions: Iterable[SearchCandidate],
    *,
    cap: int,
) -> list[SearchCandidate]:
    # The floor is never truncated even if it already exceeds the soft cap.
    out = _dedupe_candidates(floor)
    seen = {item.member_id for item in out}
    for item in additions:
        if item.member_id in seen:
            continue
        if len(out) >= cap:
            break
        seen.add(item.member_id)
        out.append(item)
    return out


def _stage_event(
    stage: str,
    before: Sequence[str],
    after: Sequence[SearchCandidate],
    **metadata: Any,
) -> dict[str, Any]:
    after_ids = tuple(item.member_id for item in after)
    before_set = set(before)
    return {
        "stage": stage,
        "before": list(before),
        "added": [item for item in after_ids if item not in before_set],
        "discarded": [],
        "after": list(after_ids),
        **metadata,
    }


def _required_coverage(
    frame: QueryFrame,
    active: Sequence[FamilyHypothesis],
    registry: QueryFamilyRegistry,
) -> tuple[str, ...]:
    required = ["governing_rule"]
    for hypothesis in active:
        definition = registry.get(hypothesis.family_id)
        if definition is not None:
            required.extend(definition.required_coverage)
    return tuple(dict.fromkeys(required))


def _fallback_routes(
    active: Sequence[FamilyHypothesis],
    registry: QueryFamilyRegistry,
) -> tuple[str, ...]:
    routes: list[str] = list(GENERIC_FALLBACK_ROUTES)
    for hypothesis in active:
        definition = registry.get(hypothesis.family_id)
        if definition is not None:
            routes.extend(definition.fallback_routes)
    return tuple(dict.fromkeys(routes))


def _answer_status(
    coverage: CoverageReport,
    candidates: Sequence[SearchCandidate],
) -> AnswerStatus:
    if not candidates:
        return AnswerStatus.INSUFFICIENT_EVIDENCE
    if any(item.startswith("fact:") for item in coverage.missing):
        return AnswerStatus.NEEDS_FACT
    if coverage.missing:
        return AnswerStatus.PROVISIONAL
    return AnswerStatus.SUPPORTED


def _runtime_rows(
    *,
    frame: QueryFrame,
    hypotheses: Sequence[FamilyHypothesis],
    candidates: Sequence[SearchCandidate],
    activations: Sequence[Activation],
    coverage: CoverageReport,
    answer_status: AnswerStatus,
    events: Sequence[Mapping[str, Any]],
    generation_id: str,
    authority_generation: str,
) -> tuple[Mapping[str, Any], ...]:
    def envelope(row_type: RowType, row_id: str, **fields: Any) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "generation_id": generation_id,
            "authority_generation": authority_generation,
            "layer": Layer.RUNTIME.value,
            "row_type": row_type.value,
            "id": row_id,
            **fields,
        }

    rows: list[Mapping[str, Any]] = [
        frame.to_row(
            generation_id=generation_id,
            authority_generation=authority_generation,
        )
    ]
    for position, candidate in enumerate(candidates):
        rows.append(envelope(
            RowType.LANDING,
            stable_id("landing", frame.id, candidate.member_id),
            query_frame_id=frame.id,
            endpoint=dict(candidate.endpoint),
            member_id=candidate.member_id,
            origin=candidate.origin,
            score=candidate.score,
            supports=list(candidate.supports),
            position=position,
        ))
    for activation in activations:
        rows.append(envelope(
            RowType.ACTIVATION_DECISION,
            stable_id("activation", frame.id, activation.relation_assertion_id),
            relation_assertion_id=activation.relation_assertion_id,
            activated=activation.activated,
            reason=activation.reason,
            family_ids=list(activation.family_ids),
        ))
    rows.append(envelope(
        RowType.DECISION_BUNDLE,
        stable_id("decision_bundle", frame.id, [item.member_id for item in candidates]),
        query_frame_id=frame.id,
        member_ids=[item.member_id for item in candidates],
        family_hypotheses=[item.to_dict() for item in hypotheses],
        coverage=coverage.to_dict(),
        answer_status=answer_status.value,
    ))
    rows.append(envelope(
        RowType.RETRIEVAL_TRACE,
        stable_id("retrieval_trace", frame.id, events),
        query_frame_id=frame.id,
        events=list(events),
        add_only=True,
        family_is_admission_gate=False,
    ))
    return tuple(rows)
