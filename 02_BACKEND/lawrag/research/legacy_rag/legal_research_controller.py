"""Stateful, page-sized and branch-parallel legal research controller.

The controller is deliberately independent from MAIN and from a concrete LLM.
It owns the part that a flat top-k list cannot represent:

* ``page_size`` limits only one decision menu; it never truncates accumulated
  evidence or the remaining frontier;
* every issue branch has its own ordered instruments, cursor and coverage;
* one page per active branch is emitted in the same wave, so callers may run
  independent selectors concurrently;
* unchosen structural containers are deferred rather than deleted, allowing
  backtracking after a plausible path turns out to be wrong;
* exhausted budgets and missing coverage fail closed.  Neither is reported as
  a legal absence or a merits conclusion.

An atlas supplies closed corpus identifiers and the document hierarchy.  An
LLM, deterministic rule, or human reviewer may decide each returned page.  A
dynamic JSON schema and strict runtime validation prevent the selector from
inventing identifiers or coverage cells.
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence


class _StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ResearchStatus(_StrEnum):
    ACTIVE = "ACTIVE"
    READY_FOR_ASSESSMENT = "READY_FOR_ASSESSMENT"
    NEEDS_FACT = "NEEDS_FACT"
    TEMPORAL_UNVERIFIED = "TEMPORAL_UNVERIFIED"
    BLOCKED_MISSING_COVERAGE = "BLOCKED_MISSING_COVERAGE"
    INCOMPLETE_WITH_CURSOR = "INCOMPLETE_WITH_CURSOR"


class BranchStatus(_StrEnum):
    OPEN = "OPEN"
    ACTIVE = "ACTIVE"
    SATISFIED = "SATISFIED"
    EXHAUSTED = "EXHAUSTED"


class ExhaustionPolicy(_StrEnum):
    """How strong a no-hit receipt must be before moving to another law."""

    TARGETED_ROUTE = "TARGETED_ROUTE"
    CLOSED_SCOPE = "CLOSED_SCOPE"


class PageMode(_StrEnum):
    HIERARCHY = "HIERARCHY"
    SEMANTIC_ENTRY = "SEMANTIC_ENTRY"
    DEFERRED_REVIEW = "DEFERRED_REVIEW"


class ClosedMenuViolation(ValueError):
    """A selector returned a corpus or coverage ID that was not offered."""


class WaveStateError(RuntimeError):
    """The caller attempted to skip, duplicate, or reorder an in-flight page."""


class NavigationUnitLike(Protocol):
    id: str
    instrument_id: str
    node_id: object
    parent_node_id: object | None
    path: str
    label: str
    kind: Any
    has_children: bool


class ResearchAtlasLike(Protocol):
    def instrument(self, instrument_id: str) -> object | None: ...

    def children(
        self,
        instrument_id: str,
        parent_node_id: object | None,
    ) -> Sequence[NavigationUnitLike]: ...

    def resolve_menu_id(self, menu_id: str) -> NavigationUnitLike | None: ...


class PageSelector(Protocol):
    def select(self, question: str, page: "CandidatePage") -> "PageDecision": ...


@dataclass(frozen=True, slots=True)
class CoverageVerification:
    """Source-backed result from a compiler/verifier, never from selection alone."""

    verified_keys: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    verifier: str


class EvidenceCoverageVerifier(Protocol):
    def verify(
        self,
        branch: "BranchPlan",
        item: NavigationUnitLike,
        claimed_keys: tuple[str, ...],
    ) -> CoverageVerification: ...


@dataclass(frozen=True, slots=True)
class ReceiptVerification:
    """Trust-boundary result for externally supplied evidence identifiers."""

    verified: bool
    verifier: str


class EvidenceReceiptVerifier(Protocol):
    def verify(
        self,
        kind: str,
        session: "ResearchSession",
        branch_id: str | None,
        subject: str,
        evidence_ids: tuple[str, ...],
    ) -> ReceiptVerification: ...


@dataclass(frozen=True, slots=True)
class BranchPlan:
    branch_id: str
    issue_axis: str
    instrument_role: str
    instrument_ids: tuple[str, ...]
    required_coverage: tuple[str, ...]
    required_relation_checks: tuple[str, ...] = ()
    required_evidence_by_coverage: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict)
    entry_point_ids_by_instrument: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict)
    exhaustion_policy: ExhaustionPolicy = ExhaustionPolicy.CLOSED_SCOPE

    def __post_init__(self) -> None:
        if not self.branch_id.strip():
            raise ValueError("branch_id is required")
        if not self.instrument_ids:
            raise ValueError(f"branch {self.branch_id} needs at least one instrument")
        if len(set(self.instrument_ids)) != len(self.instrument_ids):
            raise ValueError(f"branch {self.branch_id} repeats an instrument")
        if len(set(self.required_coverage)) != len(self.required_coverage):
            raise ValueError(f"branch {self.branch_id} repeats coverage keys")
        if len(set(self.required_relation_checks)) != len(self.required_relation_checks):
            raise ValueError(f"branch {self.branch_id} repeats relation checks")
        if not self.required_coverage and not self.required_relation_checks:
            raise ValueError(
                f"branch {self.branch_id} needs coverage or relation requirements")
        unknown_evidence_keys = sorted(
            set(self.required_evidence_by_coverage) - set(self.required_coverage))
        if unknown_evidence_keys:
            raise ValueError(
                f"branch {self.branch_id} has evidence rules for unknown coverage: "
                f"{unknown_evidence_keys}")
        for key, evidence_ids in self.required_evidence_by_coverage.items():
            if not evidence_ids or len(evidence_ids) != len(set(evidence_ids)):
                raise ValueError(
                    f"branch {self.branch_id} coverage {key} needs unique evidence")
        unknown_entry_instruments = sorted(
            set(self.entry_point_ids_by_instrument) - set(self.instrument_ids)
        )
        if unknown_entry_instruments:
            raise ValueError(
                f"branch {self.branch_id} has entry points for unplanned instruments: "
                f"{unknown_entry_instruments}")
        for instrument_id, entry_ids in self.entry_point_ids_by_instrument.items():
            if len(entry_ids) != len(set(entry_ids)):
                raise ValueError(
                    f"branch {self.branch_id} repeats entry points for {instrument_id}")


@dataclass(frozen=True, slots=True)
class FactEvidence:
    value: Any
    evidence_ids: tuple[str, ...]
    verified: bool = True

    @property
    def satisfied(self) -> bool:
        if not self.verified or not self.evidence_ids or self.value is None:
            return False
        if isinstance(self.value, str):
            return bool(self.value.strip())
        return True


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    question: str
    branches: tuple[BranchPlan, ...]
    page_size: int = 8
    max_page_waves: int = 64
    known_facts: Mapping[str, Any] = field(default_factory=dict)
    unknown_fact_slots: tuple[str, ...] = ()
    as_of: str | None = None
    requested_effect: str = "LEGAL_ASSESSMENT"
    temporal_verification_required: bool = False

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("question is required")
        if not self.branches:
            raise ValueError("at least one research branch is required")
        ids = [branch.branch_id for branch in self.branches]
        if len(ids) != len(set(ids)):
            raise ValueError("branch IDs must be unique")
        if self.page_size < 1:
            raise ValueError("page_size must be positive")
        if self.max_page_waves < 1:
            raise ValueError("max_page_waves must be positive")
        if len(set(self.unknown_fact_slots)) != len(self.unknown_fact_slots):
            raise ValueError("unknown fact slots must be unique")
        if set(self.known_facts) & set(self.unknown_fact_slots):
            raise ValueError("a fact cannot be both known and unknown")
        if not self.requested_effect.strip():
            raise ValueError("requested_effect is required")
        if bool(self.as_of) != self.temporal_verification_required:
            raise ValueError(
                "as_of and temporal_verification_required must be supplied together")


@dataclass(frozen=True, slots=True)
class CandidatePage:
    page_id: str
    wave: int
    branch_id: str
    issue_axis: str
    instrument_role: str
    exhaustion_policy: ExhaustionPolicy
    mode: PageMode
    instrument_id: str
    parent_node_id: object | None
    offset: int
    page_size: int
    items: tuple[NavigationUnitLike, ...]
    has_more: bool
    required_coverage: tuple[str, ...]
    satisfied_coverage: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.items) > self.page_size:
            raise ValueError("candidate page exceeds page_size")
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate page contains duplicate IDs")

    @property
    def missing_coverage(self) -> tuple[str, ...]:
        have = set(self.satisfied_coverage)
        return tuple(key for key in self.required_coverage if key not in have)

    def to_dict(self) -> dict[str, Any]:
        rows = []
        for item in self.items:
            if hasattr(item, "to_dict"):
                row = dict(item.to_dict())
            else:
                kind = getattr(item, "kind", "")
                row = {
                    "id": item.id,
                    "instrument_id": item.instrument_id,
                    "node_id": item.node_id,
                    "parent_node_id": item.parent_node_id,
                    "path": item.path,
                    "label": item.label,
                    "kind": getattr(kind, "value", kind),
                    "has_children": bool(item.has_children),
                }
            rows.append(row)
        return {
            "page_id": self.page_id,
            "wave": self.wave,
            "branch_id": self.branch_id,
            "issue_axis": self.issue_axis,
            "instrument_role": self.instrument_role,
            "exhaustion_policy": self.exhaustion_policy.value,
            "mode": self.mode.value,
            "instrument_id": self.instrument_id,
            "parent_node_id": self.parent_node_id,
            "offset": self.offset,
            "page_size": self.page_size,
            "has_more": self.has_more,
            "required_coverage": list(self.required_coverage),
            "satisfied_coverage": list(self.satisfied_coverage),
            "missing_coverage": list(self.missing_coverage),
            "items": rows,
        }


@dataclass(frozen=True, slots=True)
class PageDecision:
    page_id: str
    selected_ids: tuple[str, ...] = ()
    descend_ids: tuple[str, ...] = ()
    defer_ids: tuple[str, ...] = ()
    rejected_ids: tuple[str, ...] = ()
    coverage_by_id: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    route_complete: bool = False
    rationale: str = ""

    @classmethod
    def from_mapping(
        cls,
        page: CandidatePage,
        value: Mapping[str, Any],
    ) -> "PageDecision":
        raw_coverage = value.get("coverage") or ()
        coverage: dict[str, tuple[str, ...]] = {}
        if isinstance(raw_coverage, Sequence) and not isinstance(raw_coverage, (str, bytes)):
            for row in raw_coverage:
                if not isinstance(row, Mapping):
                    raise ClosedMenuViolation("coverage rows must be objects")
                item_id = str(row.get("id") or "")
                keys = row.get("keys") or ()
                if isinstance(keys, (str, bytes)) or not isinstance(keys, Sequence):
                    raise ClosedMenuViolation("coverage keys must be an array")
                coverage[item_id] = tuple(str(key) for key in keys)

        def values(name: str) -> tuple[str, ...]:
            raw = value.get(name) or ()
            if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
                raise ClosedMenuViolation(f"{name} must be an array")
            return tuple(str(item) for item in raw)

        decision = cls(
            page_id=str(value.get("page_id") or page.page_id),
            selected_ids=values("selected_ids"),
            descend_ids=values("descend_ids"),
            defer_ids=values("defer_ids"),
            rejected_ids=values("rejected_ids"),
            coverage_by_id=coverage,
            route_complete=bool(value.get("route_complete", False)),
            rationale=str(value.get("rationale") or ""),
        )
        validate_page_decision(page, decision)
        return decision

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "selected_ids": list(self.selected_ids),
            "descend_ids": list(self.descend_ids),
            "defer_ids": list(self.defer_ids),
            "rejected_ids": list(self.rejected_ids),
            "coverage": [
                {"id": item_id, "keys": list(keys)}
                for item_id, keys in self.coverage_by_id.items()
            ],
            "route_complete": self.route_complete,
            "rationale": self.rationale,
        }


def decision_schema(page: CandidatePage) -> dict[str, Any]:
    """Return a closed structured-output schema for exactly one page."""
    offered = [item.id for item in page.items]
    containers = [item.id for item in page.items if _is_container(item)]
    articles = [item.id for item in page.items if not _is_container(item)]
    coverage_keys = list(page.required_coverage)

    def id_array(values: list[str]) -> dict[str, Any]:
        item_schema: dict[str, Any] = {"type": "string"}
        array_schema: dict[str, Any] = {
            "type": "array",
            "items": item_schema,
            "uniqueItems": True,
        }
        if values:
            item_schema["enum"] = values
        else:
            # Empty legal menus are represented as empty arrays.  Never expose
            # a synthetic value that a model can mistake for an evidence ID.
            array_schema["maxItems"] = 0
            array_schema["description"] = (
                "No eligible IDs exist for this field; return an empty array."
            )
        return array_schema

    coverage_id_schema: dict[str, Any] = {"type": "string"}
    if articles:
        coverage_id_schema["enum"] = articles
    coverage_key_schema: dict[str, Any] = {"type": "string"}
    if coverage_keys:
        coverage_key_schema["enum"] = coverage_keys
    coverage_schema: dict[str, Any] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": coverage_id_schema,
                "keys": {
                    "type": "array",
                    "items": coverage_key_schema,
                    "uniqueItems": True,
                },
            },
            "required": ["id", "keys"],
            "additionalProperties": False,
        },
    }
    if not articles or not coverage_keys:
        coverage_schema["maxItems"] = 0
        coverage_schema["description"] = (
            "No eligible article/coverage-key pair exists; return an empty array."
        )
    return {
        "type": "object",
        "properties": {
            "page_id": {"type": "string", "const": page.page_id},
            "selected_ids": id_array(articles),
            "descend_ids": id_array(containers),
            "defer_ids": id_array(offered),
            "rejected_ids": id_array(offered),
            "coverage": coverage_schema,
            "route_complete": (
                {"type": "boolean"}
                if page.exhaustion_policy is ExhaustionPolicy.TARGETED_ROUTE
                else {"type": "boolean", "const": False}
            ),
            "rationale": {"type": "string"},
        },
        "required": [
            "page_id", "selected_ids", "descend_ids", "defer_ids",
            "rejected_ids", "coverage", "route_complete", "rationale",
        ],
        "additionalProperties": False,
    }


def validate_page_decision(page: CandidatePage, decision: PageDecision) -> None:
    if decision.page_id != page.page_id:
        raise ClosedMenuViolation(
            f"decision page {decision.page_id!r} does not match {page.page_id!r}")
    by_id = {item.id: item for item in page.items}
    offered = set(by_id)
    groups = {
        "selected_ids": decision.selected_ids,
        "descend_ids": decision.descend_ids,
        "defer_ids": decision.defer_ids,
        "rejected_ids": decision.rejected_ids,
    }
    for name, values in groups.items():
        if len(values) != len(set(values)):
            raise ClosedMenuViolation(f"{name} contains duplicate IDs")
        unknown = sorted(set(values) - offered)
        if unknown:
            raise ClosedMenuViolation(f"{name} contains unknown IDs: {unknown}")
    if set(decision.selected_ids) & set(decision.rejected_ids):
        raise ClosedMenuViolation("an item cannot be selected and rejected")
    if set(decision.selected_ids) & set(decision.defer_ids):
        raise ClosedMenuViolation("an item cannot be selected and deferred")
    if set(decision.descend_ids) & set(decision.rejected_ids):
        raise ClosedMenuViolation("a container cannot be descended and rejected")
    dispositions = {
        "selected": set(decision.selected_ids),
        "descend": set(decision.descend_ids),
        "defer": set(decision.defer_ids),
        "reject": set(decision.rejected_ids),
    }
    names = tuple(dispositions)
    for position, left in enumerate(names):
        for right in names[position + 1:]:
            overlap = dispositions[left].intersection(dispositions[right])
            if overlap:
                raise ClosedMenuViolation(
                    f"item disposition overlaps {left}/{right}: {sorted(overlap)}")
    if decision.route_complete and page.has_more:
        raise ClosedMenuViolation(
            "route_complete cannot discard a continuation page")
    if decision.route_complete:
        if page.exhaustion_policy is not ExhaustionPolicy.TARGETED_ROUTE:
            raise ClosedMenuViolation("route_complete is forbidden for CLOSED_SCOPE search")
        if decision.descend_ids:
            raise ClosedMenuViolation("route_complete cannot also descend a container")
    bad_selected = [item_id for item_id in decision.selected_ids
                    if _is_container(by_id[item_id])]
    if bad_selected:
        raise ClosedMenuViolation(f"containers cannot be evidence: {bad_selected}")
    bad_descend = [item_id for item_id in decision.descend_ids
                   if not _is_container(by_id[item_id])]
    if bad_descend:
        raise ClosedMenuViolation(f"articles cannot be descended: {bad_descend}")
    if set(decision.coverage_by_id) - set(decision.selected_ids):
        raise ClosedMenuViolation("coverage may be claimed only by selected evidence")
    allowed_coverage = set(page.required_coverage)
    for item_id, keys in decision.coverage_by_id.items():
        if len(keys) != len(set(keys)):
            raise ClosedMenuViolation(f"duplicate coverage keys for {item_id}")
        unknown = sorted(set(keys) - allowed_coverage)
        if unknown:
            raise ClosedMenuViolation(f"unknown coverage keys for {item_id}: {unknown}")


@dataclass(frozen=True, slots=True)
class TraceEvent:
    sequence: int
    event: str
    branch_id: str
    instrument_id: str | None = None
    page_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event": self.event,
            "branch_id": self.branch_id,
            "instrument_id": self.instrument_id,
            "page_id": self.page_id,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class _FrontierTask:
    instrument_id: str
    parent_node_id: object | None
    offset: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "parent_node_id": self.parent_node_id,
            "offset": self.offset,
        }


@dataclass(slots=True)
class BranchState:
    plan: BranchPlan
    status: BranchStatus = BranchStatus.OPEN
    instrument_index: int = -1
    active_frontier: deque[_FrontierTask] = field(default_factory=deque)
    semantic_entries: deque[NavigationUnitLike] = field(default_factory=deque)
    fallback_frontier: deque[_FrontierTask] = field(default_factory=deque)
    scheduled_parents: set[tuple[str, object | None]] = field(default_factory=set)
    satisfied_coverage: set[str] = field(default_factory=set)
    coverage_sources: dict[str, list[str]] = field(default_factory=dict)
    coverage_evidence_ids: dict[str, list[str]] = field(default_factory=dict)
    coverage_claims: dict[str, list[str]] = field(default_factory=dict)
    completed_relation_checks: dict[str, list[str]] = field(default_factory=dict)
    selected_evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    deferred_articles: deque[NavigationUnitLike] = field(default_factory=deque)
    deferred_article_ids: set[str] = field(default_factory=set)
    reviewed_deferred_ids: set[str] = field(default_factory=set)
    unresolved_deferred_ids: set[str] = field(default_factory=set)
    viewed_ids: set[str] = field(default_factory=set)
    exhausted_instruments: list[str] = field(default_factory=list)
    targeted_no_hit_instruments: list[str] = field(default_factory=list)
    pages_seen: int = 0
    in_flight_page_id: str | None = None

    @property
    def current_instrument_id(self) -> str | None:
        if 0 <= self.instrument_index < len(self.plan.instrument_ids):
            return self.plan.instrument_ids[self.instrument_index]
        return None

    @property
    def missing_coverage(self) -> tuple[str, ...]:
        return tuple(
            key for key in self.plan.required_coverage
            if key not in self.satisfied_coverage
        )

    @property
    def missing_relation_checks(self) -> tuple[str, ...]:
        return tuple(
            relation for relation in self.plan.required_relation_checks
            if relation not in self.completed_relation_checks
        )

    @property
    def completion_missing(self) -> tuple[str, ...]:
        return (*self.missing_coverage, *(
            f"relation:{relation}" for relation in self.missing_relation_checks
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.plan.branch_id,
            "issue_axis": self.plan.issue_axis,
            "instrument_role": self.plan.instrument_role,
            "exhaustion_policy": self.plan.exhaustion_policy.value,
            "instrument_ids": list(self.plan.instrument_ids),
            "required_coverage": list(self.plan.required_coverage),
            "required_relation_checks": list(self.plan.required_relation_checks),
            "status": self.status.value,
            "instrument_index": self.instrument_index,
            "current_instrument_id": self.current_instrument_id,
            "satisfied_coverage": sorted(self.satisfied_coverage),
            "missing_coverage": list(self.missing_coverage),
            "coverage_claims": {
                key: list(values) for key, values in self.coverage_claims.items()
            },
            "coverage_sources": {
                key: list(values) for key, values in self.coverage_sources.items()
            },
            "coverage_evidence_ids": {
                key: list(values)
                for key, values in self.coverage_evidence_ids.items()
            },
            "required_evidence_by_coverage": {
                key: list(values)
                for key, values in self.plan.required_evidence_by_coverage.items()
            },
            "entry_point_ids_by_instrument": {
                key: list(values)
                for key, values in self.plan.entry_point_ids_by_instrument.items()
            },
            "completed_relation_checks": {
                key: list(values) for key, values in self.completed_relation_checks.items()
            },
            "missing_relation_checks": list(self.missing_relation_checks),
            "selected_evidence": list(self.selected_evidence.values()),
            "deferred_article_ids": sorted(self.deferred_article_ids),
            "reviewed_deferred_ids": sorted(self.reviewed_deferred_ids),
            "unresolved_deferred_ids": sorted(self.unresolved_deferred_ids),
            "viewed_count": len(self.viewed_ids),
            "exhausted_instruments": list(self.exhausted_instruments),
            "targeted_no_hit_instruments": list(self.targeted_no_hit_instruments),
            "pages_seen": self.pages_seen,
            "in_flight_page_id": self.in_flight_page_id,
            "active_frontier": [task.to_dict() for task in self.active_frontier],
            "semantic_entry_ids": [item.id for item in self.semantic_entries],
            "fallback_frontier": [task.to_dict() for task in self.fallback_frontier],
        }


@dataclass(slots=True)
class ResearchSession:
    plan: ResearchPlan
    branches: dict[str, BranchState]
    status: ResearchStatus = ResearchStatus.ACTIVE
    wave_count: int = 0
    max_page_waves: int = 64
    trace: list[TraceEvent] = field(default_factory=list)
    in_flight_pages: dict[str, CandidatePage] = field(default_factory=dict)
    resolved_facts: dict[str, FactEvidence] = field(default_factory=dict)
    temporal_evidence_ids: tuple[str, ...] = ()
    temporal_verified: bool = False

    @property
    def selected_evidence_count(self) -> int:
        return sum(len(branch.selected_evidence) for branch in self.branches.values())

    @property
    def unresolved_fact_slots(self) -> tuple[str, ...]:
        return tuple(
            key for key in self.plan.unknown_fact_slots
            if not (self.resolved_facts.get(key) and self.resolved_facts[key].satisfied)
        )

    def to_dict(self, *, include_trace: bool = True) -> dict[str, Any]:
        value = {
            "question": self.plan.question,
            "page_size": self.plan.page_size,
            "max_page_waves": self.max_page_waves,
            "wave_count": self.wave_count,
            "status": self.status.value,
            "known_facts": dict(self.plan.known_facts),
            "unknown_fact_slots": list(self.plan.unknown_fact_slots),
            "resolved_facts": {
                key: {
                    "value": fact.value,
                    "evidence_ids": list(fact.evidence_ids),
                    "verified": fact.verified,
                }
                for key, fact in self.resolved_facts.items()
            },
            "unresolved_fact_slots": list(self.unresolved_fact_slots),
            "as_of": self.plan.as_of,
            "requested_effect": self.plan.requested_effect,
            "temporal_verification_required": self.plan.temporal_verification_required,
            "temporal_verified": self.temporal_verified,
            "temporal_evidence_ids": list(self.temporal_evidence_ids),
            "selected_evidence_count": self.selected_evidence_count,
            "branches": [branch.to_dict() for branch in self.branches.values()],
            "in_flight_pages": [page.to_dict() for page in self.in_flight_pages.values()],
        }
        if include_trace:
            value["trace"] = [event.to_dict() for event in self.trace]
        return value


@dataclass(frozen=True, slots=True)
class _InFlightTask:
    task: _FrontierTask
    page: CandidatePage


class LegalResearchController:
    """Advance a legal research plan one parallel page wave at a time."""

    def __init__(
        self,
        atlas: ResearchAtlasLike,
        *,
        coverage_verifier: EvidenceCoverageVerifier | None = None,
        receipt_verifier: EvidenceReceiptVerifier | None = None,
    ) -> None:
        self.atlas = atlas
        self.coverage_verifier = coverage_verifier
        self.receipt_verifier = receipt_verifier
        self._tasks_by_page: dict[tuple[int, str], _InFlightTask] = {}

    def create_session(self, plan: ResearchPlan) -> ResearchSession:
        instrument_lookup = getattr(self.atlas, "instrument", None)
        if not callable(instrument_lookup):
            raise ClosedMenuViolation(
                "atlas must expose a closed current-instrument registry")
        unknown_instruments = sorted({
            instrument_id
            for branch in plan.branches
            for instrument_id in branch.instrument_ids
            if instrument_lookup(instrument_id) is None
        })
        if unknown_instruments:
            raise ClosedMenuViolation(
                f"unknown or noncurrent instruments: {unknown_instruments}")
        resolve_menu_id = getattr(self.atlas, "resolve_menu_id", None)
        for branch in plan.branches:
            for instrument_id, entry_ids in branch.entry_point_ids_by_instrument.items():
                for entry_id in entry_ids:
                    item = resolve_menu_id(entry_id) if callable(resolve_menu_id) else None
                    if item is None:
                        raise ClosedMenuViolation(
                            f"unknown semantic entry point: {entry_id}")
                    if item.instrument_id != instrument_id or _is_container(item):
                        raise ClosedMenuViolation(
                            f"semantic entry point has wrong owner or is not an article: "
                            f"{entry_id}")
        branches = {
            branch.branch_id: BranchState(plan=branch)
            for branch in plan.branches
        }
        session = ResearchSession(
            plan=plan,
            branches=branches,
            max_page_waves=plan.max_page_waves,
            temporal_verified=not plan.temporal_verification_required,
        )
        self._refresh_status(session)
        return session

    def _verify_receipt(
        self,
        kind: str,
        session: ResearchSession,
        branch_id: str | None,
        subject: str,
        evidence_ids: tuple[str, ...],
        requested_verified: bool,
    ) -> ReceiptVerification:
        if not requested_verified or not evidence_ids:
            return ReceiptVerification(False, "not-verified")
        if self.receipt_verifier is None:
            return ReceiptVerification(False, "missing-receipt-verifier")
        result = self.receipt_verifier.verify(
            kind, session, branch_id, subject, evidence_ids)
        if not isinstance(result, ReceiptVerification):
            raise ClosedMenuViolation(
                "receipt verifier must return ReceiptVerification")
        if result.verified and not result.verifier.strip():
            raise ClosedMenuViolation("verified receipt requires verifier identity")
        return result

    def record_fact(
        self,
        session: ResearchSession,
        fact_slot: str,
        value: Any,
        *,
        evidence_ids: Sequence[str],
        verified: bool = True,
    ) -> None:
        if fact_slot not in session.plan.unknown_fact_slots:
            raise ClosedMenuViolation(f"unknown fact slot: {fact_slot}")
        evidence = FactEvidence(
            value=value,
            evidence_ids=tuple(str(item) for item in evidence_ids),
            verified=False,
        )
        receipt = self._verify_receipt(
            "fact", session, None, fact_slot, evidence.evidence_ids, verified)
        evidence = FactEvidence(
            value=value,
            evidence_ids=evidence.evidence_ids,
            verified=receipt.verified,
        )
        session.resolved_facts[fact_slot] = evidence
        branch = next(iter(session.branches.values()))
        self._trace(
            session,
            branch,
            "FACT_RECORDED",
            details={
                "fact_slot": fact_slot,
                "verified": evidence.satisfied,
                "evidence_ids": list(evidence.evidence_ids),
                "verifier": receipt.verifier,
            },
        )
        self._refresh_status(session)

    def record_temporal_verification(
        self,
        session: ResearchSession,
        *,
        evidence_ids: Sequence[str],
        verified: bool,
    ) -> None:
        if not session.plan.temporal_verification_required:
            raise WaveStateError("the plan does not require temporal verification")
        ids = tuple(str(item) for item in evidence_ids)
        receipt = self._verify_receipt(
            "temporal", session, None, str(session.plan.as_of or ""), ids, verified)
        session.temporal_evidence_ids = ids
        session.temporal_verified = receipt.verified
        branch = next(iter(session.branches.values()))
        self._trace(
            session,
            branch,
            "TEMPORAL_VERIFICATION_RECORDED",
            details={
                "as_of": session.plan.as_of,
                "verified": session.temporal_verified,
                "evidence_ids": list(ids),
                "verifier": receipt.verifier,
            },
        )
        self._refresh_status(session)

    def record_verified_coverage(
        self,
        session: ResearchSession,
        branch_id: str,
        item_id: str,
        coverage_keys: Sequence[str],
        *,
        evidence_ids: Sequence[str],
        verified: bool,
        verifier: str = "external-evidence-compiler",
    ) -> None:
        branch = session.branches.get(branch_id)
        if branch is None:
            raise ClosedMenuViolation(f"unknown branch: {branch_id}")
        if item_id not in branch.selected_evidence:
            raise ClosedMenuViolation("coverage requires previously selected evidence")
        keys = tuple(str(key) for key in coverage_keys)
        unknown = sorted(set(keys) - set(branch.plan.required_coverage))
        if unknown:
            raise ClosedMenuViolation(f"unplanned coverage keys: {unknown}")
        ids = tuple(str(item) for item in evidence_ids)
        receipt = self._verify_receipt(
            "coverage", session, branch_id, item_id, ids, verified)
        if receipt.verified:
            self._accept_verified_coverage(
                branch, item_id, keys, ids, receipt.verifier)
        self._trace(
            session,
            branch,
            "COVERAGE_VERIFICATION_RECORDED",
            instrument_id=branch.current_instrument_id,
            details={
                "item_id": item_id,
                "keys": list(keys),
                "verified": receipt.verified,
                "evidence_ids": list(ids),
                "requested_verifier": verifier,
                "verifier": receipt.verifier,
            },
        )
        self._maybe_satisfy_branch(session, branch)
        self._refresh_status(session)

    def record_relation_check(
        self,
        session: ResearchSession,
        branch_id: str,
        relation: str,
        *,
        evidence_ids: Sequence[str],
        verified: bool,
    ) -> None:
        branch = session.branches.get(branch_id)
        if branch is None:
            raise ClosedMenuViolation(f"unknown branch: {branch_id}")
        if relation not in branch.plan.required_relation_checks:
            raise ClosedMenuViolation(f"unplanned relation check: {relation}")
        ids = tuple(str(item) for item in evidence_ids)
        receipt = self._verify_receipt(
            "relation", session, branch_id, relation, ids, verified)
        if receipt.verified:
            branch.completed_relation_checks[relation] = list(ids)
        else:
            branch.completed_relation_checks.pop(relation, None)
        self._trace(
            session,
            branch,
            "RELATION_CHECK_RECORDED",
            instrument_id=branch.current_instrument_id,
            details={
                "relation": relation,
                "verified": receipt.verified,
                "evidence_ids": list(ids),
                "verifier": receipt.verifier,
            },
        )
        self._maybe_satisfy_branch(session, branch)
        self._refresh_status(session)

    def next_wave(self, session: ResearchSession) -> tuple[CandidatePage, ...]:
        if session.in_flight_pages:
            raise WaveStateError("apply the current wave before requesting another")
        if session.status in {
            ResearchStatus.READY_FOR_ASSESSMENT,
            ResearchStatus.NEEDS_FACT,
            ResearchStatus.TEMPORAL_UNVERIFIED,
            ResearchStatus.BLOCKED_MISSING_COVERAGE,
        }:
            return ()
        if session.wave_count >= session.max_page_waves:
            session.status = ResearchStatus.INCOMPLETE_WITH_CURSOR
            self._trace_budget(session)
            return ()
        if session.status is ResearchStatus.INCOMPLETE_WITH_CURSOR:
            return ()

        pages: list[CandidatePage] = []
        next_wave = session.wave_count + 1
        for branch in session.branches.values():
            if branch.status in {BranchStatus.SATISFIED, BranchStatus.EXHAUSTED}:
                continue
            page, task = self._next_branch_page(session, branch, next_wave)
            if page is None or task is None:
                continue
            pages.append(page)
            session.in_flight_pages[page.page_id] = page
            branch.in_flight_page_id = page.page_id
            self._tasks_by_page[(id(session), page.page_id)] = _InFlightTask(task, page)

        if pages:
            session.wave_count = next_wave
            self._trace_wave(session, pages)
            return tuple(pages)

        self._refresh_status(session)
        return ()

    def apply_wave(
        self,
        session: ResearchSession,
        decisions: Sequence[PageDecision],
    ) -> ResearchStatus:
        expected = set(session.in_flight_pages)
        given = [decision.page_id for decision in decisions]
        if len(given) != len(set(given)):
            raise WaveStateError("a page decision was supplied more than once")
        if set(given) != expected:
            missing = sorted(expected - set(given))
            extra = sorted(set(given) - expected)
            raise WaveStateError(f"wave decisions do not match pages; missing={missing}, extra={extra}")

        by_page = {decision.page_id: decision for decision in decisions}
        records: dict[str, _InFlightTask] = {}
        for page_id, page in session.in_flight_pages.items():
            validate_page_decision(page, by_page[page_id])
            record = self._tasks_by_page.get((id(session), page_id))
            if record is None:
                raise WaveStateError(f"missing in-flight task for {page_id}")
            records[page_id] = record

        # Compile every page against a staged copy.  A bad second branch or a
        # verifier failure must not leave the first branch half-committed.
        staged = deepcopy(session)
        for page_id, page in list(staged.in_flight_pages.items()):
            branch = staged.branches[page.branch_id]
            self._apply_page(
                staged, branch, records[page_id].task, page, by_page[page_id])
            branch.in_flight_page_id = None
            del staged.in_flight_pages[page_id]
        self._refresh_status(staged)

        session.branches = staged.branches
        session.status = staged.status
        session.trace = staged.trace
        session.in_flight_pages = staged.in_flight_pages
        session.resolved_facts = staged.resolved_facts
        session.temporal_evidence_ids = staged.temporal_evidence_ids
        session.temporal_verified = staged.temporal_verified
        for page_id in records:
            self._tasks_by_page.pop((id(session), page_id), None)
        return session.status

    def extend_budget(self, session: ResearchSession, extra_page_waves: int) -> None:
        """Resume an incomplete cursor without changing page size or deleting state."""
        if extra_page_waves < 1:
            raise ValueError("extra_page_waves must be positive")
        if session.in_flight_pages:
            raise WaveStateError("cannot extend a session with an in-flight wave")
        session.max_page_waves += extra_page_waves
        if session.status is ResearchStatus.INCOMPLETE_WITH_CURSOR:
            session.status = ResearchStatus.ACTIVE
        self._trace(
            session,
            next(iter(session.branches.values())),
            "BUDGET_EXTENDED",
            details={"extra_page_waves": extra_page_waves, "new_max": session.max_page_waves},
        )

    def _next_branch_page(
        self,
        session: ResearchSession,
        branch: BranchState,
        wave: int,
    ) -> tuple[CandidatePage | None, _FrontierTask | None]:
        while True:
            if branch.status is BranchStatus.OPEN:
                if not self._start_next_instrument(session, branch):
                    return None, None
            if branch.semantic_entries:
                current = branch.current_instrument_id
                if current is None:
                    raise WaveStateError("semantic entries require an active instrument")
                items: list[NavigationUnitLike] = []
                while branch.semantic_entries and len(items) < session.plan.page_size:
                    item = branch.semantic_entries.popleft()
                    items.append(item)
                page_id = (
                    f"W{wave}:B{branch.plan.branch_id}:I{current}:"
                    f"PSEMANTIC:O{branch.pages_seen}"
                )
                page = CandidatePage(
                    page_id=page_id,
                    wave=wave,
                    branch_id=branch.plan.branch_id,
                    issue_axis=branch.plan.issue_axis,
                    instrument_role=branch.plan.instrument_role,
                    exhaustion_policy=branch.plan.exhaustion_policy,
                    mode=PageMode.SEMANTIC_ENTRY,
                    instrument_id=current,
                    parent_node_id="__SEMANTIC_ENTRY__",
                    offset=0,
                    page_size=session.plan.page_size,
                    items=tuple(items),
                    has_more=bool(branch.semantic_entries),
                    required_coverage=branch.plan.required_coverage,
                    satisfied_coverage=tuple(sorted(branch.satisfied_coverage)),
                )
                branch.status = BranchStatus.ACTIVE
                branch.pages_seen += 1
                branch.viewed_ids.update(item.id for item in items)
                self._trace(
                    session,
                    branch,
                    "SEMANTIC_ENTRY_PRESENTED",
                    instrument_id=current,
                    page_id=page_id,
                    details={
                        "item_ids": [item.id for item in items],
                        "item_count": len(items),
                        "page_size": session.plan.page_size,
                        "has_more": page.has_more,
                    },
                )
                return page, _FrontierTask(current, "__SEMANTIC_ENTRY__", 0)
            if not branch.active_frontier and branch.fallback_frontier:
                branch.active_frontier.append(branch.fallback_frontier.popleft())
                self._trace(session, branch, "BACKTRACK_TO_DEFERRED_FRONTIER")
            if not branch.active_frontier:
                current = branch.current_instrument_id
                if current is not None and branch.deferred_articles:
                    items: list[NavigationUnitLike] = []
                    while branch.deferred_articles and len(items) < session.plan.page_size:
                        item = branch.deferred_articles.popleft()
                        items.append(item)
                        branch.reviewed_deferred_ids.add(item.id)
                    page_id = (
                        f"W{wave}:B{branch.plan.branch_id}:I{current}:"
                        f"PDEFERRED:O{branch.pages_seen}"
                    )
                    page = CandidatePage(
                        page_id=page_id,
                        wave=wave,
                        branch_id=branch.plan.branch_id,
                        issue_axis=branch.plan.issue_axis,
                        instrument_role=branch.plan.instrument_role,
                        exhaustion_policy=branch.plan.exhaustion_policy,
                        mode=PageMode.DEFERRED_REVIEW,
                        instrument_id=current,
                        parent_node_id="__DEFERRED_REVIEW__",
                        offset=0,
                        page_size=session.plan.page_size,
                        items=tuple(items),
                        has_more=bool(branch.deferred_articles),
                        required_coverage=branch.plan.required_coverage,
                        satisfied_coverage=tuple(sorted(branch.satisfied_coverage)),
                    )
                    branch.status = BranchStatus.ACTIVE
                    branch.pages_seen += 1
                    self._trace(
                        session,
                        branch,
                        "DEFERRED_ARTICLE_REVIEW_PRESENTED",
                        instrument_id=current,
                        page_id=page_id,
                        details={
                            "item_ids": [item.id for item in items],
                            "item_count": len(items),
                            "page_size": session.plan.page_size,
                            "has_more": page.has_more,
                        },
                    )
                    return page, _FrontierTask(current, "__DEFERRED_REVIEW__", 0)
                if current is not None:
                    instrument = self.atlas.instrument(current)
                    scope_verified = instrument is not None
                    branch.exhausted_instruments.append(current)
                    self._trace(
                        session,
                        branch,
                        "CLOSED_SCOPE_EXHAUSTED",
                        instrument_id=current,
                        details={
                            "receipt_strength": "all_scheduled_pages_visited",
                            "permits_scope_absence_statement": (
                                scope_verified
                                and not bool(branch.unresolved_deferred_ids)
                            ),
                            "closed_instrument_registry_verified": scope_verified,
                            "instrument_status": getattr(
                                instrument, "status", None),
                            "instrument_version": getattr(
                                instrument, "version", None),
                            "article_count": getattr(
                                instrument, "article_count", None),
                            "unresolved_deferred_ids": sorted(
                                branch.unresolved_deferred_ids
                            ),
                        },
                    )
                if not self._start_next_instrument(session, branch):
                    return None, None
                continue

            task = branch.active_frontier.popleft()
            children = tuple(self.atlas.children(task.instrument_id, task.parent_node_id))
            if task.offset >= len(children):
                self._trace(
                    session, branch, "FRONTIER_EXHAUSTED",
                    instrument_id=task.instrument_id,
                    details={"parent_node_id": task.parent_node_id, "offset": task.offset},
                )
                continue
            items = children[task.offset:task.offset + session.plan.page_size]
            page_id = (
                f"W{wave}:B{branch.plan.branch_id}:I{task.instrument_id}:"
                f"P{_node_token(task.parent_node_id)}:O{task.offset}"
            )
            page = CandidatePage(
                page_id=page_id,
                wave=wave,
                branch_id=branch.plan.branch_id,
                issue_axis=branch.plan.issue_axis,
                instrument_role=branch.plan.instrument_role,
                exhaustion_policy=branch.plan.exhaustion_policy,
                mode=PageMode.HIERARCHY,
                instrument_id=task.instrument_id,
                parent_node_id=task.parent_node_id,
                offset=task.offset,
                page_size=session.plan.page_size,
                items=tuple(items),
                has_more=task.offset + len(items) < len(children),
                required_coverage=branch.plan.required_coverage,
                satisfied_coverage=tuple(sorted(branch.satisfied_coverage)),
            )
            branch.status = BranchStatus.ACTIVE
            branch.pages_seen += 1
            branch.viewed_ids.update(item.id for item in items)
            self._trace(
                session, branch, "PAGE_PRESENTED",
                instrument_id=task.instrument_id,
                page_id=page_id,
                details={
                    "parent_node_id": task.parent_node_id,
                    "offset": task.offset,
                    "item_ids": [item.id for item in items],
                    "item_count": len(items),
                    "page_size": session.plan.page_size,
                    "has_more": page.has_more,
                },
            )
            return page, task

    def _start_next_instrument(self, session: ResearchSession, branch: BranchState) -> bool:
        next_index = branch.instrument_index + 1
        if next_index >= len(branch.plan.instrument_ids):
            branch.status = BranchStatus.EXHAUSTED
            self._trace(
                session, branch, "BRANCH_EXHAUSTED",
                details={
                    "missing_coverage": list(branch.missing_coverage),
                    "missing_relation_checks": list(branch.missing_relation_checks),
                },
            )
            return False
        branch.instrument_index = next_index
        instrument_id = branch.plan.instrument_ids[next_index]
        branch.status = BranchStatus.ACTIVE
        branch.active_frontier.clear()
        branch.semantic_entries.clear()
        branch.fallback_frontier.clear()
        root_key = (instrument_id, None)
        if root_key not in branch.scheduled_parents:
            branch.scheduled_parents.add(root_key)
            branch.active_frontier.append(_FrontierTask(instrument_id, None, 0))
        resolve_menu_id = getattr(self.atlas, "resolve_menu_id", None)
        for entry_id in branch.plan.entry_point_ids_by_instrument.get(instrument_id, ()):
            item = resolve_menu_id(entry_id) if callable(resolve_menu_id) else None
            if item is not None and item.id not in branch.viewed_ids:
                branch.semantic_entries.append(item)
        self._trace(
            session, branch, "INSTRUMENT_STARTED",
            instrument_id=instrument_id,
            details={"instrument_index": next_index},
        )
        return True

    def _apply_page(
        self,
        session: ResearchSession,
        branch: BranchState,
        task: _FrontierTask,
        page: CandidatePage,
        decision: PageDecision,
    ) -> None:
        by_id = {item.id: item for item in page.items}
        selected = set(decision.selected_ids)
        descends = set(decision.descend_ids)

        for item_id in decision.selected_ids:
            item = by_id[item_id]
            branch.unresolved_deferred_ids.discard(item_id)
            keys = tuple(decision.coverage_by_id.get(item_id, ()))
            evidence_row = branch.selected_evidence.setdefault(item_id, {
                "id": item.id,
                "instrument_id": item.instrument_id,
                "node_id": item.node_id,
                "path": item.path,
                "label": item.label,
                "claimed_coverage": [],
                "verified_coverage": [],
                "selected_wave": page.wave,
                "selected_page_id": page.page_id,
            })
            for key in keys:
                branch.coverage_claims.setdefault(key, [])
                if item_id not in branch.coverage_claims[key]:
                    branch.coverage_claims[key].append(item_id)
                if key not in evidence_row["claimed_coverage"]:
                    evidence_row["claimed_coverage"].append(key)
            verified_keys: tuple[str, ...] = ()
            verification_candidates = branch.missing_coverage
            if self.coverage_verifier is not None and verification_candidates:
                result = self.coverage_verifier.verify(
                    branch.plan, item, verification_candidates)
                if set(result.verified_keys) - set(verification_candidates):
                    raise ClosedMenuViolation(
                        "coverage verifier returned a key outside missing requirements")
                if result.verified_keys and not result.evidence_ids:
                    raise ClosedMenuViolation(
                        "verified coverage requires source evidence IDs")
                verified_keys = result.verified_keys
                self._accept_verified_coverage(
                    branch,
                    item_id,
                    result.verified_keys,
                    result.evidence_ids,
                    result.verifier,
                )
            self._trace(
                session, branch, "EVIDENCE_SELECTED",
                instrument_id=page.instrument_id,
                page_id=page.page_id,
                details={
                    "item_id": item_id,
                    "claimed_coverage": list(keys),
                    "verified_coverage": list(verified_keys),
                    "coverage_state": "VERIFIED" if verified_keys else "UNVERIFIED",
                },
            )
            for relation in branch.missing_relation_checks:
                self._trace(
                    session,
                    branch,
                    "RELATION_CHECK_PENDING",
                    instrument_id=page.instrument_id,
                    page_id=page.page_id,
                    details={"relation": relation, "selected_item_id": item_id},
                )

        selected_tasks: list[_FrontierTask] = []
        deferred_tasks: list[_FrontierTask] = []
        for item in page.items:
            if not _is_container(item):
                if item.id not in selected:
                    if item.id in decision.defer_ids:
                        if page.mode in {PageMode.HIERARCHY, PageMode.SEMANTIC_ENTRY}:
                            if item.id not in branch.deferred_article_ids:
                                branch.deferred_article_ids.add(item.id)
                                branch.deferred_articles.append(item)
                            disposition = (
                                "DEFERRED_FOR_SECOND_REVIEW"
                                if page.mode is PageMode.HIERARCHY
                                else "SEMANTIC_ENTRY_DEFERRED_FOR_REVIEW"
                            )
                        else:
                            branch.unresolved_deferred_ids.add(item.id)
                            disposition = "UNRESOLVED_AFTER_SECOND_REVIEW"
                    elif item.id in decision.rejected_ids:
                        branch.unresolved_deferred_ids.discard(item.id)
                        disposition = "REJECTED"
                    else:
                        if page.mode is PageMode.HIERARCHY:
                            if item.id not in branch.deferred_article_ids:
                                branch.deferred_article_ids.add(item.id)
                                branch.deferred_articles.append(item)
                            disposition = "AUTO_DEFERRED_FOR_SECOND_REVIEW"
                        elif page.mode is PageMode.DEFERRED_REVIEW:
                            branch.unresolved_deferred_ids.add(item.id)
                            disposition = "UNRESOLVED_AFTER_SECOND_REVIEW"
                        else:
                            disposition = "SEMANTIC_ENTRY_NOT_SELECTED"
                    self._trace(
                        session, branch, "ARTICLE_INSPECTED_UNSELECTED",
                        instrument_id=page.instrument_id,
                        page_id=page.page_id,
                        details={
                            "item_id": item.id,
                            "disposition": disposition,
                        },
                    )
                continue
            key = (page.instrument_id, item.node_id)
            if key in branch.scheduled_parents:
                continue
            branch.scheduled_parents.add(key)
            child_task = _FrontierTask(page.instrument_id, item.node_id, 0)
            if item.id in descends:
                selected_tasks.append(child_task)
                disposition = "PRIORITY_DESCEND"
            else:
                deferred_tasks.append(child_task)
                if item.id in decision.defer_ids:
                    disposition = "EXPLICITLY_DEFERRED_FOR_BACKTRACK"
                elif item.id in decision.rejected_ids:
                    disposition = "REJECTED_BUT_CONSERVATIVELY_DEFERRED"
                else:
                    disposition = "UNCLASSIFIED_DEFERRED_FOR_BACKTRACK"
            self._trace(
                session, branch, "CONTAINER_SCHEDULED",
                instrument_id=page.instrument_id,
                page_id=page.page_id,
                details={"item_id": item.id, "disposition": disposition},
            )

        continuation = None
        if page.mode is PageMode.HIERARCHY and page.has_more:
            continuation = _FrontierTask(
                task.instrument_id,
                task.parent_node_id,
                task.offset + len(page.items),
            )
        existing = list(branch.active_frontier)
        branch.active_frontier.clear()
        branch.active_frontier.extend(selected_tasks)
        if continuation is not None:
            branch.active_frontier.append(continuation)
        branch.active_frontier.extend(existing)
        branch.fallback_frontier.extend(deferred_tasks)

        self._trace(
            session, branch, "PAGE_DECIDED",
            instrument_id=page.instrument_id,
            page_id=page.page_id,
            details={
                "selected_ids": list(decision.selected_ids),
                "descend_ids": list(decision.descend_ids),
                "defer_ids": list(decision.defer_ids),
                "rejected_ids": list(decision.rejected_ids),
                "route_complete": decision.route_complete,
                "rationale": decision.rationale,
                "active_frontier": len(branch.active_frontier),
                "fallback_frontier": len(branch.fallback_frontier),
            },
        )

        self._maybe_satisfy_branch(session, branch, instrument_id=page.instrument_id)
        if decision.route_complete and branch.status is not BranchStatus.SATISFIED:
            branch.active_frontier.clear()
            branch.semantic_entries.clear()
            branch.fallback_frontier.clear()
            branch.deferred_articles.clear()
            if page.instrument_id not in branch.targeted_no_hit_instruments:
                branch.targeted_no_hit_instruments.append(page.instrument_id)
            branch.status = BranchStatus.OPEN
            self._trace(
                session,
                branch,
                "TARGETED_ROUTE_NO_HIT",
                instrument_id=page.instrument_id,
                page_id=page.page_id,
                details={
                    "receipt_strength": "selector_completed_targeted_route",
                    "permits_scope_absence_statement": False,
                    "next_action": "NEXT_INSTRUMENT",
                    "missing_requirements": list(branch.completion_missing),
                },
            )

    @staticmethod
    def _accept_verified_coverage(
        branch: BranchState,
        item_id: str,
        keys: Sequence[str],
        evidence_ids: Sequence[str],
        verifier: str,
    ) -> None:
        row = branch.selected_evidence[item_id]
        row.setdefault("coverage_verifications", [])
        row["coverage_verifications"].append({
            "keys": list(keys),
            "evidence_ids": list(evidence_ids),
            "verifier": verifier,
        })
        for key in keys:
            branch.coverage_sources.setdefault(key, [])
            if item_id not in branch.coverage_sources[key]:
                branch.coverage_sources[key].append(item_id)
            branch.coverage_evidence_ids.setdefault(key, [])
            for evidence_id in evidence_ids:
                if evidence_id not in branch.coverage_evidence_ids[key]:
                    branch.coverage_evidence_ids[key].append(evidence_id)
            required_evidence = set(
                branch.plan.required_evidence_by_coverage.get(key, ()))
            if (
                not required_evidence
                or required_evidence.issubset(branch.coverage_evidence_ids[key])
            ):
                branch.satisfied_coverage.add(key)
            if key not in row["verified_coverage"]:
                row["verified_coverage"].append(key)

    def _maybe_satisfy_branch(
        self,
        session: ResearchSession,
        branch: BranchState,
        *,
        instrument_id: str | None = None,
    ) -> None:
        if branch.completion_missing:
            return
        if branch.status is BranchStatus.SATISFIED:
            return
        branch.status = BranchStatus.SATISFIED
        self._trace(
            session,
            branch,
            "BRANCH_SATISFIED",
            instrument_id=instrument_id,
            details={
                "coverage": sorted(branch.satisfied_coverage),
                "relation_checks": sorted(branch.completed_relation_checks),
                "selected_evidence_count": len(branch.selected_evidence),
            },
        )

    def _refresh_status(self, session: ResearchSession) -> None:
        statuses = {branch.status for branch in session.branches.values()}
        if statuses == {BranchStatus.SATISFIED}:
            if session.unresolved_fact_slots:
                session.status = ResearchStatus.NEEDS_FACT
                return
            if not session.temporal_verified:
                session.status = ResearchStatus.TEMPORAL_UNVERIFIED
                return
            session.status = ResearchStatus.READY_FOR_ASSESSMENT
            return
        if all(status in {BranchStatus.SATISFIED, BranchStatus.EXHAUSTED}
               for status in statuses):
            session.status = ResearchStatus.BLOCKED_MISSING_COVERAGE
            return
        if session.wave_count >= session.max_page_waves and not session.in_flight_pages:
            session.status = ResearchStatus.INCOMPLETE_WITH_CURSOR
            return
        session.status = ResearchStatus.ACTIVE

    @staticmethod
    def _trace(
        session: ResearchSession,
        branch: BranchState,
        event: str,
        *,
        instrument_id: str | None = None,
        page_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        session.trace.append(TraceEvent(
            sequence=len(session.trace) + 1,
            event=event,
            branch_id=branch.plan.branch_id,
            instrument_id=instrument_id,
            page_id=page_id,
            details=dict(details or {}),
        ))

    def _trace_wave(self, session: ResearchSession, pages: Sequence[CandidatePage]) -> None:
        if not pages:
            return
        branch = session.branches[pages[0].branch_id]
        self._trace(
            session, branch, "PARALLEL_WAVE_READY",
            details={
                "wave": pages[0].wave,
                "page_ids": [page.page_id for page in pages],
                "branch_ids": [page.branch_id for page in pages],
                "parallel_page_count": len(pages),
            },
        )

    def _trace_budget(self, session: ResearchSession) -> None:
        branch = next(iter(session.branches.values()))
        self._trace(
            session, branch, "BUDGET_EXHAUSTED_WITH_CURSOR",
            details={
                "wave_count": session.wave_count,
                "max_page_waves": session.max_page_waves,
                "missing_by_branch": {
                    item.plan.branch_id: list(item.completion_missing)
                    for item in session.branches.values()
                    if item.completion_missing
                },
            },
        )


def select_wave_parallel(
    question: str,
    pages: Sequence[CandidatePage],
    selector: PageSelector | Callable[[str, CandidatePage], PageDecision],
    *,
    max_workers: int | None = None,
) -> tuple[PageDecision, ...]:
    """Evaluate independent branch pages concurrently and restore page order."""
    if not pages:
        return ()
    workers = max_workers or len(pages)
    workers = max(1, min(workers, len(pages)))

    def call(page: CandidatePage) -> PageDecision:
        if hasattr(selector, "select"):
            decision = selector.select(question, page)  # type: ignore[union-attr]
        else:
            decision = selector(question, page)  # type: ignore[operator]
        validate_page_decision(page, decision)
        return decision

    results: dict[str, PageDecision] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="legal-research") as pool:
        futures = {pool.submit(call, page): page for page in pages}
        for future in as_completed(futures):
            page = futures[future]
            results[page.page_id] = future.result()
    return tuple(results[page.page_id] for page in pages)


def _is_container(item: NavigationUnitLike) -> bool:
    kind = getattr(item, "kind", "")
    value = str(getattr(kind, "value", kind)).upper()
    if value == "ARTICLE":
        return False
    if value == "CONTAINER":
        return True
    return bool(getattr(item, "has_children", False))


def _node_token(value: object | None) -> str:
    if value is None:
        return "ROOT"
    return str(value).replace(":", "_").replace("/", "_").replace(" ", "_")


__all__ = [
    "BranchPlan",
    "BranchState",
    "BranchStatus",
    "CandidatePage",
    "ClosedMenuViolation",
    "CoverageVerification",
    "EvidenceCoverageVerifier",
    "EvidenceReceiptVerifier",
    "ExhaustionPolicy",
    "FactEvidence",
    "LegalResearchController",
    "PageMode",
    "PageDecision",
    "PageSelector",
    "ResearchPlan",
    "ResearchSession",
    "ResearchStatus",
    "ReceiptVerification",
    "TraceEvent",
    "WaveStateError",
    "decision_schema",
    "select_wave_parallel",
    "validate_page_decision",
]
