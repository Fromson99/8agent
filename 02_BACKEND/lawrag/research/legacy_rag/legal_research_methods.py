"""Deterministic research controls for ADR-0114's investigation branch.

This module turns research observations into *navigation* decisions.  It does
not interpret the retrieved law and deliberately cannot emit a merits
conclusion.  The controller in :mod:`legal_research_controller` remains the
owner of closed menus and verified coverage; this layer adds four contracts:

* exact, law-local cursor history with adaptive continuation;
* case and branch budgets that cannot be consumed by another case/branch;
* Wiki-method signals compiled into evidence dependencies, never conclusions;
* a fail-closed, verified-only final evidence ceiling of 32 article roots.

The Wiki method ordering follows ``data/wiki/wiki/index.md``: read applicable
definitions first, keep governing text and provisos together, follow sanctions,
check each governing statute at a two-law gate, and then follow explicit
incorporation/delegation edges.  An action only asks the retrieval layer to read
something.  It cannot itself satisfy coverage or prove a legal proposition.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import math
import re
from typing import Any, Iterable, Mapping, Sequence


MAX_FINAL_EVIDENCE = 32
ALL_SCHEDULED_PAGES_RECEIPT = "all_scheduled_pages_visited"


class _StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class AdaptivePolicyViolation(ValueError):
    """A page skipped the retained cursor or bypassed the adaptive policy."""


class ResearchBudgetExhausted(RuntimeError):
    """A page was attempted outside its isolated case/branch/law envelope."""


class FinalEvidenceCapViolation(ValueError):
    """Mandatory verified evidence cannot fit inside the hard final ceiling."""


class ContinuationAction(_StrEnum):
    RETRIEVE_NEXT_PAGE = "RETRIEVE_NEXT_PAGE"
    PAUSED_WITH_CURSOR = "PAUSED_WITH_CURSOR"
    INCOMPLETE_WITH_CURSOR = "INCOMPLETE_WITH_CURSOR"
    SCOPE_EXHAUSTED = "SCOPE_EXHAUSTED"


class ContinuationReason(_StrEnum):
    INITIAL_PAGE = "INITIAL_PAGE"
    MISSING_COVERAGE = "MISSING_COVERAGE"
    CLOSE_SCORE_TAIL = "CLOSE_SCORE_TAIL"
    CASE_BUDGET_EXHAUSTED = "CASE_BUDGET_EXHAUSTED"
    BRANCH_BUDGET_EXHAUSTED = "BRANCH_BUDGET_EXHAUSTED"
    INSTRUMENT_BUDGET_EXHAUSTED = "INSTRUMENT_BUDGET_EXHAUSTED"
    COVERAGE_COMPLETE_AND_TAIL_SEPARATED = "COVERAGE_COMPLETE_AND_TAIL_SEPARATED"
    VERIFIED_SCOPE_EXHAUSTED = "VERIFIED_SCOPE_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class ResearchCursor:
    """An exact hierarchy-page cursor; it is opaque except for origin checks."""

    instrument_id: str
    parent_node_id: str | int | None
    offset: int

    def __post_init__(self) -> None:
        if not self.instrument_id.strip():
            raise ValueError("cursor instrument_id is required")
        if self.offset < 0:
            raise ValueError("cursor offset cannot be negative")

    @property
    def is_origin(self) -> bool:
        return self.parent_node_id is None and self.offset == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "parent_node_id": self.parent_node_id,
            "offset": self.offset,
        }


@dataclass(frozen=True, slots=True)
class AdaptivePagePolicy:
    """Frozen deterministic thresholds and isolated budget envelopes."""

    case_page_cap: int = 64
    branch_page_cap: int = 24
    instrument_page_cap: int = 12
    close_score_absolute_delta: float = 0.02
    close_score_relative_delta: float = 0.02
    final_evidence_cap: int = MAX_FINAL_EVIDENCE

    def __post_init__(self) -> None:
        if min(self.case_page_cap, self.branch_page_cap,
               self.instrument_page_cap) < 1:
            raise ValueError("adaptive page caps must be positive")
        if self.close_score_absolute_delta < 0:
            raise ValueError("absolute score-tail delta cannot be negative")
        if self.close_score_relative_delta < 0:
            raise ValueError("relative score-tail delta cannot be negative")
        if not 1 <= self.final_evidence_cap <= MAX_FINAL_EVIDENCE:
            raise ValueError(
                f"final_evidence_cap must be between 1 and {MAX_FINAL_EVIDENCE}")

    def score_tail_is_close(
        self,
        page_scores: Sequence[float],
        next_score: float | None,
    ) -> bool:
        """Return whether the presented/unpresented ranking boundary is close.

        Scores are consumed in their supplied ranking order.  The comparison is
        scale-aware but direction-neutral so both similarities and distances can
        be adapted by callers before they enter the common controller.
        """

        if not page_scores or next_score is None:
            return False
        scores = tuple(float(value) for value in page_scores)
        boundary = float(next_score)
        if not all(math.isfinite(value) for value in (*scores, boundary)):
            raise ValueError("page scores must be finite")
        tail = scores[-1]
        scale = max(abs(tail), abs(boundary), 1.0)
        threshold = max(
            self.close_score_absolute_delta,
            self.close_score_relative_delta * scale,
        )
        return abs(tail - boundary) <= threshold


@dataclass(frozen=True, slots=True)
class PageObservation:
    """One consumed law page and the exact cursor retained after it."""

    page_id: str
    cursor_before: ResearchCursor
    cursor_after: ResearchCursor | None
    missing_coverage_after: tuple[str, ...]
    page_scores: tuple[float, ...] = ()
    next_score: float | None = None
    scope_exhausted: bool = False
    exhaustion_receipt: str = ""
    unresolved_dependency_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.page_id.strip():
            raise ValueError("page_id is required")
        if len(set(self.missing_coverage_after)) != len(
                self.missing_coverage_after):
            raise ValueError("missing coverage keys must be unique")
        if len(set(self.unresolved_dependency_ids)) != len(
                self.unresolved_dependency_ids):
            raise ValueError("unresolved dependency IDs must be unique")
        if self.scope_exhausted and self.cursor_after is not None:
            raise ValueError("an exhausted scope cannot retain a next cursor")
        if not self.scope_exhausted and self.cursor_after is None:
            raise ValueError(
                "a non-exhausted page must retain its exact next cursor")
        if not self.scope_exhausted and self.exhaustion_receipt:
            raise ValueError("only an exhausted page may carry an exhaustion receipt")
        if self.cursor_after is not None and (
            self.cursor_after.instrument_id != self.cursor_before.instrument_id
        ):
            raise ValueError("a law-local cursor cannot change instrument")
        scores = (*self.page_scores,)
        if self.next_score is not None:
            scores = (*scores, self.next_score)
        if not all(math.isfinite(float(value)) for value in scores):
            raise ValueError("page scores must be finite")

    def continuation_reasons(
        self,
        policy: AdaptivePagePolicy,
    ) -> tuple[ContinuationReason, ...]:
        if self.scope_exhausted or self.cursor_after is None:
            return ()
        reasons: list[ContinuationReason] = []
        if self.missing_coverage_after or self.unresolved_dependency_ids:
            reasons.append(ContinuationReason.MISSING_COVERAGE)
        if policy.score_tail_is_close(self.page_scores, self.next_score):
            reasons.append(ContinuationReason.CLOSE_SCORE_TAIL)
        return tuple(reasons)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "cursor_before": self.cursor_before.to_dict(),
            "cursor_after": (
                self.cursor_after.to_dict() if self.cursor_after is not None else None
            ),
            "missing_coverage_after": list(self.missing_coverage_after),
            "page_scores": list(self.page_scores),
            "next_score": self.next_score,
            "scope_exhausted": self.scope_exhausted,
            "exhaustion_receipt": self.exhaustion_receipt,
            "unresolved_dependency_ids": list(self.unresolved_dependency_ids),
        }


@dataclass(slots=True)
class LawCursorHistory:
    case_id: str
    branch_id: str
    instrument_id: str
    initial_cursor: ResearchCursor
    required_coverage: tuple[str, ...]
    closed_scope: bool = False
    observations: list[PageObservation] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.branch_id.strip():
            raise ValueError("case_id and branch_id are required")
        if self.initial_cursor.instrument_id != self.instrument_id:
            raise ValueError("initial cursor belongs to another instrument")
        if len(set(self.required_coverage)) != len(self.required_coverage):
            raise ValueError("required coverage keys must be unique")

    @property
    def retained_cursor(self) -> ResearchCursor | None:
        if not self.observations:
            return self.initial_cursor
        return self.observations[-1].cursor_after

    @property
    def missing_coverage(self) -> tuple[str, ...]:
        if not self.observations:
            return self.required_coverage
        return self.observations[-1].missing_coverage_after

    @property
    def permits_scope_absence_statement(self) -> bool:
        """Absence is legal only after a verified, origin-to-end traversal."""

        if not self.closed_scope or not self.initial_cursor.is_origin:
            return False
        if not self.observations:
            return False
        last = self.observations[-1]
        return bool(
            last.scope_exhausted
            and last.exhaustion_receipt == ALL_SCHEDULED_PAGES_RECEIPT
            and last.missing_coverage_after
            and not last.unresolved_dependency_ids
        )

    def validate_observation(
        self,
        observation: PageObservation,
        policy: AdaptivePagePolicy,
    ) -> None:
        if observation.cursor_before.instrument_id != self.instrument_id:
            raise AdaptivePolicyViolation("page belongs to another instrument")
        if observation.cursor_after is not None and (
            observation.cursor_after.instrument_id != self.instrument_id
        ):
            raise AdaptivePolicyViolation("next cursor belongs to another instrument")
        if any(row.page_id == observation.page_id for row in self.observations):
            raise AdaptivePolicyViolation(f"duplicate page observation: {observation.page_id}")

        expected = self.retained_cursor
        if expected is None:
            raise AdaptivePolicyViolation("cannot append after scope exhaustion")
        if observation.cursor_before != expected:
            raise AdaptivePolicyViolation(
                "page did not resume from the exact retained cursor")

        allowed_missing = set(self.required_coverage)
        current_missing = set(observation.missing_coverage_after)
        if current_missing - allowed_missing:
            raise AdaptivePolicyViolation(
                "page introduced an unplanned coverage requirement")
        previous_missing = set(self.missing_coverage)
        if current_missing - previous_missing:
            raise AdaptivePolicyViolation("a satisfied coverage key cannot reappear")

        if self.observations:
            prior = self.observations[-1]
            if not prior.continuation_reasons(policy):
                raise AdaptivePolicyViolation(
                    "next page requires missing coverage or a close score tail")

    def append(self, observation: PageObservation) -> None:
        self.observations.append(observation)

    def continuation_reasons(
        self,
        policy: AdaptivePagePolicy,
    ) -> tuple[ContinuationReason, ...]:
        if not self.observations:
            return (ContinuationReason.INITIAL_PAGE,)
        return self.observations[-1].continuation_reasons(policy)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "branch_id": self.branch_id,
            "instrument_id": self.instrument_id,
            "initial_cursor": self.initial_cursor.to_dict(),
            "retained_cursor": (
                self.retained_cursor.to_dict()
                if self.retained_cursor is not None else None
            ),
            "required_coverage": list(self.required_coverage),
            "missing_coverage": list(self.missing_coverage),
            "closed_scope": self.closed_scope,
            "permits_scope_absence_statement": (
                self.permits_scope_absence_statement
            ),
            "observations": [row.to_dict() for row in self.observations],
        }


@dataclass(frozen=True, slots=True)
class ContinuationDecision:
    case_id: str
    branch_id: str
    instrument_id: str
    action: ContinuationAction
    reasons: tuple[ContinuationReason, ...]
    cursor: ResearchCursor | None
    permits_scope_absence_statement: bool
    budget_remaining: Mapping[str, int]

    @property
    def retrieve_next_page(self) -> bool:
        return self.action is ContinuationAction.RETRIEVE_NEXT_PAGE

    @property
    def legal_conclusion(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "branch_id": self.branch_id,
            "instrument_id": self.instrument_id,
            "action": self.action.value,
            "reasons": [reason.value for reason in self.reasons],
            "cursor": self.cursor.to_dict() if self.cursor is not None else None,
            "permits_scope_absence_statement": (
                self.permits_scope_absence_statement
            ),
            "budget_remaining": dict(self.budget_remaining),
            "legal_conclusion": False,
        }


@dataclass(slots=True)
class _CaseBudget:
    case_id: str
    branch_caps: dict[str, int]
    branch_used: dict[str, int]
    instrument_caps: dict[tuple[str, str], int] = field(default_factory=dict)
    instrument_used: dict[tuple[str, str], int] = field(default_factory=dict)

    @property
    def case_cap(self) -> int:
        return sum(self.branch_caps.values())

    @property
    def case_used(self) -> int:
        return sum(self.branch_used.values())

    def remaining(
        self,
        branch_id: str,
        instrument_id: str,
        default_instrument_cap: int,
    ) -> dict[str, int]:
        key = (branch_id, instrument_id)
        instrument_cap = self.instrument_caps.get(key, default_instrument_cap)
        return {
            "case": max(0, self.case_cap - self.case_used),
            "branch": max(
                0, self.branch_caps[branch_id] - self.branch_used[branch_id]),
            "instrument": max(
                0, instrument_cap - self.instrument_used.get(key, 0)),
        }

    def block_reasons(
        self,
        branch_id: str,
        instrument_id: str,
        default_instrument_cap: int,
    ) -> tuple[ContinuationReason, ...]:
        remaining = self.remaining(
            branch_id, instrument_id, default_instrument_cap)
        reasons: list[ContinuationReason] = []
        if remaining["case"] == 0:
            reasons.append(ContinuationReason.CASE_BUDGET_EXHAUSTED)
        if remaining["branch"] == 0:
            reasons.append(ContinuationReason.BRANCH_BUDGET_EXHAUSTED)
        if remaining["instrument"] == 0:
            reasons.append(ContinuationReason.INSTRUMENT_BUDGET_EXHAUSTED)
        return tuple(reasons)

    def consume(self, branch_id: str, instrument_id: str) -> None:
        self.branch_used[branch_id] += 1
        key = (branch_id, instrument_id)
        self.instrument_used[key] = self.instrument_used.get(key, 0) + 1


class AdaptiveResearchCoordinator:
    """Own independent case/branch budgets and exact law cursor histories."""

    def __init__(self, policy: AdaptivePagePolicy | None = None) -> None:
        self.policy = policy or AdaptivePagePolicy()
        self._budgets: dict[str, _CaseBudget] = {}
        self._histories: dict[tuple[str, str, str], LawCursorHistory] = {}

    def register_case(self, case_id: str, branch_ids: Sequence[str]) -> None:
        case = str(case_id).strip()
        branches = tuple(str(value).strip() for value in branch_ids)
        if not case or not branches or any(not value for value in branches):
            raise ValueError("case_id and non-empty branch_ids are required")
        if case in self._budgets:
            raise ValueError(f"case already registered: {case}")
        if len(set(branches)) != len(branches):
            raise ValueError("branch_ids must be unique within a case")
        if len(branches) > self.policy.case_page_cap:
            raise ValueError("case cap cannot reserve at least one page per branch")

        ordered = tuple(sorted(branches))
        base, remainder = divmod(self.policy.case_page_cap, len(ordered))
        caps = {
            branch_id: min(
                self.policy.branch_page_cap,
                base + (1 if index < remainder else 0),
            )
            for index, branch_id in enumerate(ordered)
        }
        self._budgets[case] = _CaseBudget(
            case_id=case,
            branch_caps=caps,
            branch_used={branch_id: 0 for branch_id in ordered},
        )

    def start_law(
        self,
        case_id: str,
        branch_id: str,
        instrument_id: str,
        initial_cursor: ResearchCursor,
        required_coverage: Sequence[str],
        *,
        closed_scope: bool = False,
    ) -> LawCursorHistory:
        budget = self._case_budget(case_id, branch_id)
        del budget
        key = (case_id, branch_id, instrument_id)
        if key in self._histories:
            raise ValueError(f"law history already started: {key}")
        history = LawCursorHistory(
            case_id=case_id,
            branch_id=branch_id,
            instrument_id=instrument_id,
            initial_cursor=initial_cursor,
            required_coverage=tuple(str(value) for value in required_coverage),
            closed_scope=closed_scope,
        )
        self._histories[key] = history
        return history

    def record_page(
        self,
        case_id: str,
        branch_id: str,
        instrument_id: str,
        observation: PageObservation,
    ) -> None:
        history = self.history(case_id, branch_id, instrument_id)
        budget = self._case_budget(case_id, branch_id)
        history.validate_observation(observation, self.policy)
        blocked = budget.block_reasons(
            branch_id, instrument_id, self.policy.instrument_page_cap)
        if blocked:
            raise ResearchBudgetExhausted(
                "isolated page budget exhausted: "
                + ",".join(reason.value for reason in blocked))
        budget.consume(branch_id, instrument_id)
        history.append(observation)

    def next_page_decision(
        self,
        case_id: str,
        branch_id: str,
        instrument_id: str,
    ) -> ContinuationDecision:
        history = self.history(case_id, branch_id, instrument_id)
        budget = self._case_budget(case_id, branch_id)
        remaining = budget.remaining(
            branch_id, instrument_id, self.policy.instrument_page_cap)

        if history.observations and history.observations[-1].scope_exhausted:
            return ContinuationDecision(
                case_id, branch_id, instrument_id,
                ContinuationAction.SCOPE_EXHAUSTED,
                (ContinuationReason.VERIFIED_SCOPE_EXHAUSTED,),
                None,
                history.permits_scope_absence_statement,
                remaining,
            )

        reasons = history.continuation_reasons(self.policy)
        if not reasons:
            return ContinuationDecision(
                case_id, branch_id, instrument_id,
                ContinuationAction.PAUSED_WITH_CURSOR,
                (ContinuationReason.COVERAGE_COMPLETE_AND_TAIL_SEPARATED,),
                history.retained_cursor,
                False,
                remaining,
            )

        blocked = budget.block_reasons(
            branch_id, instrument_id, self.policy.instrument_page_cap)
        if blocked:
            return ContinuationDecision(
                case_id, branch_id, instrument_id,
                ContinuationAction.INCOMPLETE_WITH_CURSOR,
                (*reasons, *blocked),
                history.retained_cursor,
                False,
                remaining,
            )
        return ContinuationDecision(
            case_id, branch_id, instrument_id,
            ContinuationAction.RETRIEVE_NEXT_PAGE,
            reasons,
            history.retained_cursor,
            False,
            remaining,
        )

    def extend_budget(
        self,
        case_id: str,
        branch_id: str,
        extra_pages: int,
        *,
        instrument_id: str | None = None,
    ) -> None:
        if extra_pages < 1:
            raise ValueError("extra_pages must be positive")
        budget = self._case_budget(case_id, branch_id)
        budget.branch_caps[branch_id] += extra_pages
        if instrument_id is not None:
            key = (branch_id, instrument_id)
            current = budget.instrument_caps.get(
                key, self.policy.instrument_page_cap)
            budget.instrument_caps[key] = current + extra_pages

    def history(
        self,
        case_id: str,
        branch_id: str,
        instrument_id: str,
    ) -> LawCursorHistory:
        key = (case_id, branch_id, instrument_id)
        try:
            return self._histories[key]
        except KeyError as exc:
            raise KeyError(f"unknown law cursor history: {key}") from exc

    def _case_budget(self, case_id: str, branch_id: str) -> _CaseBudget:
        try:
            budget = self._budgets[case_id]
        except KeyError as exc:
            raise KeyError(f"case is not registered: {case_id}") from exc
        if branch_id not in budget.branch_caps:
            raise KeyError(f"branch is not registered in {case_id}: {branch_id}")
        return budget


class DependencyActionKind(_StrEnum):
    READ_DEFINITION_FIRST = "READ_DEFINITION_FIRST"
    READ_GOVERNING_TEXT_WITH_PROVISO = "READ_GOVERNING_TEXT_WITH_PROVISO"
    FOLLOW_SANCTION = "FOLLOW_SANCTION"
    VERIFY_TWO_LAW_GATE = "VERIFY_TWO_LAW_GATE"
    FOLLOW_INCORPORATION = "FOLLOW_INCORPORATION"
    FOLLOW_DELEGATION = "FOLLOW_DELEGATION"


_DEPENDENCY_PRIORITY = {
    DependencyActionKind.READ_DEFINITION_FIRST: 0,
    DependencyActionKind.READ_GOVERNING_TEXT_WITH_PROVISO: 1,
    DependencyActionKind.FOLLOW_SANCTION: 2,
    DependencyActionKind.VERIFY_TWO_LAW_GATE: 3,
    DependencyActionKind.FOLLOW_INCORPORATION: 4,
    DependencyActionKind.FOLLOW_DELEGATION: 5,
}

_WIKI_SLUG = {
    DependencyActionKind.READ_DEFINITION_FIRST: "방법/정의-우선",
    DependencyActionKind.READ_GOVERNING_TEXT_WITH_PROVISO: "방법/단서-읽기",
    DependencyActionKind.FOLLOW_SANCTION: "방법/제재-연결",
    DependencyActionKind.VERIFY_TWO_LAW_GATE: "쟁점/두-법의-관문",
    DependencyActionKind.FOLLOW_INCORPORATION: "해석원칙/준용과-경과조치",
    DependencyActionKind.FOLLOW_DELEGATION: "해석원칙/위임과-법령보충",
}

_RELATION_TO_ACTION = {
    "USES_DEFINITION": DependencyActionKind.READ_DEFINITION_FIRST,
    "HAS_EXCEPTION": DependencyActionKind.READ_GOVERNING_TEXT_WITH_PROVISO,
    "VIOLATION_SANCTIONED_BY": DependencyActionKind.FOLLOW_SANCTION,
    "INCORPORATES": DependencyActionKind.FOLLOW_INCORPORATION,
    "DELEGATES_TO": DependencyActionKind.FOLLOW_DELEGATION,
    "RECEIVES_FROM": DependencyActionKind.FOLLOW_DELEGATION,
}

_TWO_LAW_TRIGGER = re.compile(
    r"만으로|별도|따로|각각|이중|겸영|면제|감면|모두|함께|"
    r"특별법|우선|인가|등록|허가|영위"
)
_PROVISO = re.compile(r"(?:^|[\s.;])다만\s*[,，]?|단서")


@dataclass(frozen=True, slots=True)
class EvidenceSection:
    coordinate: str
    instrument_id: str
    text: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.coordinate.strip() or not self.instrument_id.strip():
            raise ValueError("section coordinate and instrument_id are required")


@dataclass(frozen=True, slots=True)
class DependencyRelation:
    kind: str
    source_coordinate: str
    target_coordinate: str
    target_instrument_id: str
    provenance: str = ""

    def __post_init__(self) -> None:
        if self.kind not in _RELATION_TO_ACTION:
            raise ValueError(f"unsupported research dependency relation: {self.kind}")
        if not self.source_coordinate or not self.target_coordinate:
            raise ValueError("dependency relation requires closed source/target coordinates")
        if not self.target_instrument_id:
            raise ValueError("dependency relation requires target_instrument_id")


@dataclass(frozen=True, slots=True)
class DependencyAction:
    action_id: str
    kind: DependencyActionKind
    source_coordinate: str
    target_coordinate: str | None
    target_instrument_id: str
    coverage_key: str
    wiki_slug: str
    priority: int
    reason: str
    provenance: str
    status: str = "PENDING_VERIFIED_EVIDENCE"
    legal_conclusion: bool = False
    may_satisfy_coverage: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "kind": self.kind.value,
            "source_coordinate": self.source_coordinate,
            "target_coordinate": self.target_coordinate,
            "target_instrument_id": self.target_instrument_id,
            "coverage_key": self.coverage_key,
            "wiki_slug": self.wiki_slug,
            "priority": self.priority,
            "reason": self.reason,
            "provenance": self.provenance,
            "status": self.status,
            "legal_conclusion": False,
            "may_satisfy_coverage": False,
        }


def _coordinate(doc_id: object, node: object) -> str:
    return f"{doc_id}:{node}" if str(doc_id) and str(node) else ""


def _coerce_section(value: EvidenceSection | Mapping[str, Any]) -> EvidenceSection:
    if isinstance(value, EvidenceSection):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("sections must be EvidenceSection or mappings")
    coordinate = str(value.get("coordinate") or "")
    instrument_id = str(
        value.get("instrument_id") or value.get("doc_id")
        or value.get("document_id") or ""
    )
    if not coordinate and instrument_id and value.get("node") is not None:
        coordinate = _coordinate(instrument_id, value.get("node"))
    if not instrument_id and ":" in coordinate:
        instrument_id = coordinate.split(":", 1)[0]
    raw_tags = value.get("tags") or value.get("kinds") or ()
    if isinstance(raw_tags, str):
        tags = (raw_tags,)
    else:
        tags = tuple(str(item) for item in raw_tags)
    for name in ("role", "ref_kind", "companion_kind"):
        tag = str(value.get(name) or "")
        if tag and tag not in tags:
            tags = (*tags, tag)
    return EvidenceSection(
        coordinate=coordinate,
        instrument_id=instrument_id,
        text=str(
            value.get("text") or value.get("original_text")
            or value.get("preview") or ""
        ),
        tags=tags,
    )


def _coerce_relation(
    value: DependencyRelation | Mapping[str, Any],
) -> DependencyRelation:
    if isinstance(value, DependencyRelation):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("relations must be DependencyRelation or mappings")
    kind = str(value.get("kind") or value.get("graph_kind") or "")
    source = str(value.get("source_coordinate") or "")
    target = str(value.get("target_coordinate") or "")
    source_doc = value.get("src_doc", value.get("source_doc_id"))
    source_node = value.get("src_node", value.get("source_node"))
    target_doc = value.get("dst_doc", value.get("target_doc_id"))
    target_node = value.get("dst_node", value.get("target_node"))
    if not source and source_doc is not None and source_node is not None:
        source = _coordinate(source_doc, source_node)
    if not target and target_doc is not None and target_node is not None:
        target = _coordinate(target_doc, target_node)
    target_instrument = str(
        value.get("target_instrument_id") or target_doc or ""
    )
    if not target_instrument and ":" in target:
        target_instrument = target.split(":", 1)[0]
    raw_provenance = value.get("provenance") or ""
    if isinstance(raw_provenance, Sequence) and not isinstance(
            raw_provenance, (str, bytes)):
        provenance = "·".join(str(item) for item in raw_provenance)
    else:
        provenance = str(raw_provenance)
    return DependencyRelation(
        kind=kind,
        source_coordinate=source,
        target_coordinate=target,
        target_instrument_id=target_instrument,
        provenance=provenance,
    )


def _dependency_action(
    kind: DependencyActionKind,
    source: str,
    target: str | None,
    instrument_id: str,
    *,
    reason: str,
    provenance: str,
) -> DependencyAction:
    target_token = target or instrument_id
    coverage_key = f"{kind.value}:{target_token}"
    action_id = f"dependency:{kind.value}:{source or '-'}:{target_token}"
    return DependencyAction(
        action_id=action_id,
        kind=kind,
        source_coordinate=source,
        target_coordinate=target,
        target_instrument_id=instrument_id,
        coverage_key=coverage_key,
        wiki_slug=_WIKI_SLUG[kind],
        priority=_DEPENDENCY_PRIORITY[kind],
        reason=reason,
        provenance=provenance,
    )


def plan_dependency_actions(
    query: str,
    sections: Sequence[EvidenceSection | Mapping[str, Any]],
    coverage: Iterable[str] = (),
    *,
    relations: Sequence[DependencyRelation | Mapping[str, Any]] = (),
) -> tuple[DependencyAction, ...]:
    """Compile Wiki methods into ordered, non-evidentiary retrieval actions."""

    rows = tuple(_coerce_section(value) for value in sections)
    by_coordinate = {row.coordinate: row for row in rows}
    satisfied = {str(value) for value in coverage}
    actions: list[DependencyAction] = []

    for row in rows:
        normalized_tags = {tag.replace(" ", "").lower() for tag in row.tags}
        if any("정의" in tag or "definition" in tag for tag in normalized_tags):
            actions.append(_dependency_action(
                DependencyActionKind.READ_DEFINITION_FIRST,
                row.coordinate,
                row.coordinate,
                row.instrument_id,
                reason="관할 정의를 실체 규정에 앞서 읽는다",
                provenance="wiki-method:definition-tag",
            ))
        if _PROVISO.search(row.text) or any(
                "단서" in tag or "proviso" in tag for tag in normalized_tags):
            actions.append(_dependency_action(
                DependencyActionKind.READ_GOVERNING_TEXT_WITH_PROVISO,
                row.coordinate,
                row.coordinate,
                row.instrument_id,
                reason="본문과 단서를 같은 규율 단위로 읽는다",
                provenance="wiki-method:proviso-signal",
            ))
        if any("제재" in tag or "sanction" in tag for tag in normalized_tags):
            actions.append(_dependency_action(
                DependencyActionKind.FOLLOW_SANCTION,
                row.coordinate,
                row.coordinate,
                row.instrument_id,
                reason="의무의 위반 효과를 제재 원문에서 확인한다",
                provenance="wiki-method:sanction-tag",
            ))

    for raw in relations:
        relation = _coerce_relation(raw)
        if relation.source_coordinate not in by_coordinate:
            continue
        kind = _RELATION_TO_ACTION[relation.kind]
        reasons = {
            DependencyActionKind.READ_DEFINITION_FIRST:
                "정의 적용 간선의 대상 원문을 먼저 확인한다",
            DependencyActionKind.READ_GOVERNING_TEXT_WITH_PROVISO:
                "명시적 예외 간선의 원문과 지배규정을 함께 확인한다",
            DependencyActionKind.FOLLOW_SANCTION:
                "위반-제재 간선의 대상 원문을 확인한다",
            DependencyActionKind.FOLLOW_INCORPORATION:
                "명시적 준용 source와 target 원문을 함께 확인한다",
            DependencyActionKind.FOLLOW_DELEGATION:
                "위임 source와 수임 target의 범위를 함께 확인한다",
        }
        actions.append(_dependency_action(
            kind,
            relation.source_coordinate,
            relation.target_coordinate,
            relation.target_instrument_id,
            reason=reasons[kind],
            provenance=relation.provenance or f"typed-relation:{relation.kind}",
        ))

    instruments = tuple(dict.fromkeys(row.instrument_id for row in rows))
    if len(instruments) >= 2 and _TWO_LAW_TRIGGER.search(str(query or "")):
        for instrument_id in instruments:
            source = next(
                row.coordinate for row in rows
                if row.instrument_id == instrument_id
            )
            actions.append(_dependency_action(
                DependencyActionKind.VERIFY_TWO_LAW_GATE,
                source,
                None,
                instrument_id,
                reason="각 법률의 독립된 적용 관문을 원문으로 확인한다",
                provenance="wiki-issue:two-law-gate",
            ))

    deduped: dict[str, DependencyAction] = {}
    for action in actions:
        if action.coverage_key in satisfied:
            continue
        deduped.setdefault(action.action_id, action)
    return tuple(sorted(deduped.values(), key=lambda action: (
        action.priority,
        action.source_coordinate,
        action.target_instrument_id,
        action.target_coordinate or "",
        action.action_id,
    )))


@dataclass(frozen=True, slots=True)
class CoverageState:
    required: tuple[str, ...] = ()
    satisfied: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(set(self.required)) != len(self.required):
            raise ValueError("required coverage keys must be unique")
        if len(set(self.satisfied)) != len(self.satisfied):
            raise ValueError("satisfied coverage keys must be unique")

    @property
    def missing(self) -> tuple[str, ...]:
        have = set(self.satisfied)
        return tuple(value for value in self.required if value not in have)

    @classmethod
    def from_value(
        cls,
        value: "CoverageState | Mapping[str, Any] | Iterable[str]",
    ) -> "CoverageState":
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            if "required" in value or "satisfied" in value:
                required = value.get("required") or ()
                satisfied = value.get("satisfied") or ()
                return cls(
                    tuple(str(item) for item in required),
                    tuple(str(item) for item in satisfied),
                )
            return cls((), tuple(
                str(key) for key, present in value.items() if present
            ))
        return cls((), tuple(str(item) for item in value))


@dataclass(frozen=True, slots=True)
class ResearchMethodStep:
    dependency_actions: tuple[DependencyAction, ...]
    action: ContinuationAction
    reasons: tuple[ContinuationReason, ...]
    next_cursor: ResearchCursor | None
    missing_coverage: tuple[str, ...]
    legal_conclusion: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "dependency_actions": [row.to_dict() for row in self.dependency_actions],
            "action": self.action.value,
            "reasons": [reason.value for reason in self.reasons],
            "next_cursor": (
                self.next_cursor.to_dict() if self.next_cursor is not None else None
            ),
            "missing_coverage": list(self.missing_coverage),
            "legal_conclusion": False,
        }


def plan_research_step(
    query: str,
    sections: Sequence[EvidenceSection | Mapping[str, Any]],
    coverage: CoverageState | Mapping[str, Any] | Iterable[str],
    *,
    relations: Sequence[DependencyRelation | Mapping[str, Any]] = (),
    cursor_after: ResearchCursor | None,
    page_scores: Sequence[float] = (),
    next_score: float | None = None,
    scope_exhausted: bool = False,
    budget_available: bool = True,
    policy: AdaptivePagePolicy | None = None,
) -> ResearchMethodStep:
    """Small query/sections/coverage façade for the integrated engine.

    The façade is intentionally stateless.  Use :class:`AdaptiveResearchCoordinator`
    when absence receipts, exact multi-page continuity, or isolated budget accounting
    must be audited.
    """

    chosen_policy = policy or AdaptivePagePolicy()
    coverage_state = CoverageState.from_value(coverage)
    dependencies = plan_dependency_actions(
        query,
        sections,
        coverage_state.satisfied,
        relations=relations,
    )
    missing = tuple(dict.fromkeys((
        *coverage_state.missing,
        *(action.coverage_key for action in dependencies),
    )))
    if scope_exhausted:
        return ResearchMethodStep(
            dependencies,
            ContinuationAction.SCOPE_EXHAUSTED,
            (ContinuationReason.VERIFIED_SCOPE_EXHAUSTED,),
            None,
            missing,
        )
    if cursor_after is None:
        raise AdaptivePolicyViolation(
            "non-exhausted research step must retain an exact cursor")

    reasons: list[ContinuationReason] = []
    if missing:
        reasons.append(ContinuationReason.MISSING_COVERAGE)
    if chosen_policy.score_tail_is_close(page_scores, next_score):
        reasons.append(ContinuationReason.CLOSE_SCORE_TAIL)
    if not reasons:
        return ResearchMethodStep(
            dependencies,
            ContinuationAction.PAUSED_WITH_CURSOR,
            (ContinuationReason.COVERAGE_COMPLETE_AND_TAIL_SEPARATED,),
            cursor_after,
            missing,
        )
    if not budget_available:
        return ResearchMethodStep(
            dependencies,
            ContinuationAction.INCOMPLETE_WITH_CURSOR,
            tuple(reasons),
            cursor_after,
            missing,
        )
    return ResearchMethodStep(
        dependencies,
        ContinuationAction.RETRIEVE_NEXT_PAGE,
        tuple(reasons),
        cursor_after,
        missing,
    )


@dataclass(frozen=True, slots=True)
class FinalEvidenceCandidate:
    case_id: str
    branch_id: str
    candidate_id: str
    coordinate: str
    instrument_id: str
    verified: bool
    score: float = 0.0
    mandatory: bool = False
    baseline_floor: bool = False
    coverage_keys: tuple[str, ...] = ()
    source_order: int = 0
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (
                self.case_id, self.branch_id, self.candidate_id,
                self.coordinate, self.instrument_id)):
            raise ValueError(
                "final evidence needs case, branch, candidate, coordinate and instrument IDs")
        if not math.isfinite(float(self.score)):
            raise ValueError("final evidence score must be finite")
        if len(set(self.coverage_keys)) != len(self.coverage_keys):
            raise ValueError("final evidence coverage keys must be unique")


@dataclass(frozen=True, slots=True)
class FinalEvidenceCompilation:
    case_id: str
    selected: tuple[FinalEvidenceCandidate, ...]
    discarded_coordinates: tuple[str, ...]
    unverified_coordinates: tuple[str, ...]
    missing_mandatory_coordinates: tuple[str, ...]
    cap: int

    @property
    def ready_for_legal_assessment(self) -> bool:
        return bool(self.selected) and not self.missing_mandatory_coordinates

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "selected_coordinates": [row.coordinate for row in self.selected],
            "selected_count": len(self.selected),
            "discarded_coordinates": list(self.discarded_coordinates),
            "unverified_coordinates": list(self.unverified_coordinates),
            "missing_mandatory_coordinates": list(
                self.missing_mandatory_coordinates),
            "cap": self.cap,
            "ready_for_legal_assessment": self.ready_for_legal_assessment,
        }


def _evidence_rank(row: FinalEvidenceCandidate) -> tuple[Any, ...]:
    return (
        not row.mandatory,
        not row.baseline_floor,
        -len(row.coverage_keys),
        -float(row.score),
        row.source_order,
        row.coordinate,
        row.branch_id,
    )


def compile_final_evidence(
    case_id: str,
    candidates: Sequence[FinalEvidenceCandidate],
    *,
    cap: int = MAX_FINAL_EVIDENCE,
    verification_records: Mapping[str, Any] | None = None,
    source_resolver: Any = None,
    authority_generation: str = "",
    authority_as_of: str = "",
) -> FinalEvidenceCompilation:
    """Compile one case's verified evidence with a hard ceiling of 32.

    Mandatory verified rows fail closed if they do not fit.  After mandatory
    rows, one best row per branch is admitted before the global rank fill so a
    large branch cannot erase every other branch at the final boundary.
    """

    if not 1 <= cap <= MAX_FINAL_EVIDENCE:
        raise ValueError(f"cap must be between 1 and {MAX_FINAL_EVIDENCE}")
    if any(row.case_id != case_id for row in candidates):
        raise ValueError("final evidence compilation cannot mix cases")

    # A boolean supplied by a ranker is not evidence.  Every row presented as
    # verified is checked again against a CandidateRecord and current source.
    if any(row.verified for row in candidates):
        if (
            verification_records is None or not callable(source_resolver)
            or not authority_generation.strip() or not authority_as_of.strip()
        ):
            raise ValueError(
                "verified final evidence requires records, source resolver and authority"
            )
        from lawrag.research.legacy_rag.legal_research_state import (
            ResearchStateError,
            validate_candidate_verification,
        )

        checked: list[FinalEvidenceCandidate] = []
        for row in candidates:
            if not row.verified:
                checked.append(row)
                continue
            record = verification_records.get(row.candidate_id)
            if record is None:
                raise ValueError(
                    f"verified final candidate record is missing: {row.candidate_id}"
                )
            if (
                record.coordinate.document_id != row.instrument_id
                or f"{record.coordinate.document_id}:{record.coordinate.node_id}"
                != row.coordinate
            ):
                raise ValueError(
                    f"verified final candidate coordinate mismatch: {row.candidate_id}"
                )
            try:
                validate_candidate_verification(
                    record,
                    source_resolver,
                    authority_generation=authority_generation,
                    authority_as_of=authority_as_of,
                )
            except ResearchStateError as exc:
                raise ValueError(
                    f"verified final candidate failed source validation: "
                    f"{row.candidate_id}: {exc}"
                ) from exc
            checked.append(row)
        candidates = tuple(checked)

    best_by_coordinate: dict[str, FinalEvidenceCandidate] = {}
    for row in candidates:
        current = best_by_coordinate.get(row.coordinate)
        if current is None:
            best_by_coordinate[row.coordinate] = replace(
                row, mandatory=row.mandatory or row.baseline_floor
            )
            continue
        if current.instrument_id != row.instrument_id:
            raise ValueError(
                f"one coordinate cannot belong to multiple instruments: "
                f"{row.coordinate}")
        # Keep the identity/payload of a receipt-backed row.  Otherwise an
        # unverified duplicate with a better rank could borrow ``verified``
        # from its sibling while retaining an unrelated candidate_id.
        if current.verified != row.verified:
            representative = current if current.verified else row
        else:
            representative = (
                row if _evidence_rank(row) < _evidence_rank(current) else current
            )
        best_by_coordinate[row.coordinate] = replace(
            representative,
            verified=current.verified or row.verified,
            mandatory=(
                current.mandatory or row.mandatory
                or current.baseline_floor or row.baseline_floor
            ),
            baseline_floor=current.baseline_floor or row.baseline_floor,
            coverage_keys=tuple(dict.fromkeys((
                *current.coverage_keys, *row.coverage_keys))),
            score=max(float(current.score), float(row.score)),
            source_order=min(current.source_order, row.source_order),
        )

    unique = tuple(best_by_coordinate.values())
    unverified = tuple(sorted(
        row.coordinate for row in unique if not row.verified))
    missing_mandatory = tuple(sorted(
        row.coordinate for row in unique if row.mandatory and not row.verified))
    verified = sorted(
        (row for row in unique if row.verified), key=_evidence_rank)
    mandatory = [row for row in verified if row.mandatory]
    if len(mandatory) > cap:
        raise FinalEvidenceCapViolation(
            f"{len(mandatory)} mandatory verified rows exceed final cap {cap}")

    selected: list[FinalEvidenceCandidate] = list(mandatory)
    selected_coordinates = {row.coordinate for row in selected}
    branch_ids = sorted({row.branch_id for row in verified})
    for branch_id in branch_ids:
        if len(selected) >= cap:
            break
        row = next((
            candidate for candidate in verified
            if candidate.branch_id == branch_id
            and candidate.coordinate not in selected_coordinates
        ), None)
        if row is None:
            continue
        selected.append(row)
        selected_coordinates.add(row.coordinate)

    for row in verified:
        if len(selected) >= cap:
            break
        if row.coordinate in selected_coordinates:
            continue
        selected.append(row)
        selected_coordinates.add(row.coordinate)

    discarded = tuple(sorted(
        row.coordinate for row in verified
        if row.coordinate not in selected_coordinates))
    return FinalEvidenceCompilation(
        case_id=case_id,
        selected=tuple(selected),
        discarded_coordinates=discarded,
        unverified_coordinates=unverified,
        missing_mandatory_coordinates=missing_mandatory,
        cap=cap,
    )


__all__ = [
    "ALL_SCHEDULED_PAGES_RECEIPT",
    "MAX_FINAL_EVIDENCE",
    "AdaptivePagePolicy",
    "AdaptivePolicyViolation",
    "AdaptiveResearchCoordinator",
    "ContinuationAction",
    "ContinuationDecision",
    "ContinuationReason",
    "CoverageState",
    "DependencyAction",
    "DependencyActionKind",
    "DependencyRelation",
    "EvidenceSection",
    "FinalEvidenceCandidate",
    "FinalEvidenceCapViolation",
    "FinalEvidenceCompilation",
    "LawCursorHistory",
    "PageObservation",
    "ResearchBudgetExhausted",
    "ResearchCursor",
    "ResearchMethodStep",
    "compile_final_evidence",
    "plan_dependency_actions",
    "plan_research_step",
]
