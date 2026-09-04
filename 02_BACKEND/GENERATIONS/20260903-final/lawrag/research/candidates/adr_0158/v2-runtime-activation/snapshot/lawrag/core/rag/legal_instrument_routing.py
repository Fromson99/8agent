"""Closed, paged question-to-instrument routing over the legal atlas.

This module plans *where to research*.  It deliberately does not retrieve an
article, decide which rule governs, or make a legal conclusion.  Every current
instrument in :class:`LegalResearchAtlas` remains reachable through a paged
menu.  Precompiled :class:`InstrumentProfile` rows only change the order and
the hints shown in that menu; a missing profile never removes an instrument.

The page size is an observation cap, not a final top-k.  A branch may continue
through every page, and the cumulative ordered route may be larger than one
page.  Multiple issue branches expose one page each in a wave so their future
selector calls can run in parallel.  No LLM is called here.  The pure model
request builder pins any future product selector to the repository's required
Haiku model and exposes a closed-ID response schema.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.parse import quote

from lawrag.core.rag.legal_research_atlas import (
    PROFILE_MODEL,
    InstrumentProfile,
    InstrumentRecord,
    InstrumentRole,
    LegalResearchAtlas,
    NavigationUnit,
)


ROUTER_PRODUCT_MODEL = PROFILE_MODEL
_ROLE_PRIORITY_STEP = 80


class _StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class RouteBranchStatus(_StrEnum):
    ACTIVE = "ACTIVE"
    ROUTE_READY = "ROUTE_READY"
    EXHAUSTED = "EXHAUSTED"


class RouteSessionStatus(_StrEnum):
    ACTIVE = "ACTIVE"
    ROUTES_READY = "ROUTES_READY"
    BLOCKED_NO_ROUTE = "BLOCKED_NO_ROUTE"


class ClosedRouteMenuViolation(ValueError):
    """A profile, plan, cursor, or decision escaped its closed corpus menu."""


class RoutePageSelector(Protocol):
    def select(
        self, question: str, page: "InstrumentRoutePage",
    ) -> "InstrumentRouteDecision": ...


@dataclass(frozen=True)
class InstrumentRouteBranch:
    """One independently routed legal issue.

    The hints affect presentation order only.  They never filter an atlas
    instrument.  ``preferred_instrument_ids`` is therefore a recall-safe way
    to put a known likely law on an early page without making it the only law
    that can be inspected.
    """

    branch_id: str
    issue_axis: str
    preferred_roles: tuple[InstrumentRole, ...] = ()
    topic_hints: tuple[str, ...] = ()
    preferred_instrument_ids: tuple[str, ...] = ()
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "issue_axis": self.issue_axis,
            "preferred_roles": [role.value for role in self.preferred_roles],
            "topic_hints": list(self.topic_hints),
            "preferred_instrument_ids": list(self.preferred_instrument_ids),
            "required": self.required,
        }


@dataclass(frozen=True)
class InstrumentRouteMenuItem:
    menu_id: str
    instrument: InstrumentRecord
    profile: InstrumentProfile | None
    routing_score: int
    routing_signals: tuple[str, ...]

    @property
    def instrument_id(self) -> str:
        return self.instrument.instrument_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "menu_id": self.menu_id,
            "instrument": self.instrument.to_dict(),
            "profile": self.profile.to_dict() if self.profile is not None else None,
            "profile_status": "PRESENT" if self.profile is not None else "MISSING",
            "routing_score": self.routing_score,
            "routing_signals": list(self.routing_signals),
        }


@dataclass(frozen=True)
class InstrumentRouteCursor:
    branch_id: str
    offset: int
    page_size: int
    menu_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "offset": self.offset,
            "page_size": self.page_size,
            "menu_fingerprint": self.menu_fingerprint,
        }


@dataclass(frozen=True)
class InstrumentRouteChoice:
    """A selected law and its ordered fallback tier.

    Rank 0 is tried first.  Larger values are later fallback tiers.  Choices
    with the same rank retain their original selection order, even when they
    were selected on different pages.
    """

    menu_id: str
    fallback_rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "menu_id": self.menu_id,
            "fallback_rank": self.fallback_rank,
        }


@dataclass(frozen=True)
class InstrumentRouteDecision:
    page_id: str
    choices: tuple[InstrumentRouteChoice, ...]
    rejected_menu_ids: tuple[str, ...]
    route_complete: bool = False
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "choices": [choice.to_dict() for choice in self.choices],
            "rejected_menu_ids": list(self.rejected_menu_ids),
            "route_complete": self.route_complete,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class InstrumentRoutePage:
    page_id: str
    wave: int
    branch_id: str
    issue_axis: str
    cursor: InstrumentRouteCursor
    next_cursor: InstrumentRouteCursor | None
    items: tuple[InstrumentRouteMenuItem, ...]
    ordered_route_so_far: tuple[str, ...]

    @property
    def page_size(self) -> int:
        return self.cursor.page_size

    @property
    def has_more(self) -> bool:
        return self.next_cursor is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "wave": self.wave,
            "branch_id": self.branch_id,
            "issue_axis": self.issue_axis,
            "cursor": self.cursor.to_dict(),
            "next_cursor": (
                self.next_cursor.to_dict() if self.next_cursor is not None else None
            ),
            "items": [item.to_dict() for item in self.items],
            "item_count": len(self.items),
            "page_size": self.page_size,
            "has_more": self.has_more,
            "ordered_route_so_far": list(self.ordered_route_so_far),
        }


@dataclass(frozen=True)
class RouteModelRequest:
    """Pure payload for a future product selector; this object makes no call."""

    kind: str
    model: str
    system: str
    user: str
    schema: Mapping[str, Any]
    max_tokens: int = 2400
    effort: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "model": self.model,
            "system": self.system,
            "user": self.user,
            "schema": dict(self.schema),
            "max_tokens": self.max_tokens,
            "effort": self.effort,
        }


@dataclass
class InstrumentRouteBranchState:
    plan: InstrumentRouteBranch
    menu: tuple[InstrumentRouteMenuItem, ...]
    next_cursor: InstrumentRouteCursor | None
    status: RouteBranchStatus = RouteBranchStatus.ACTIVE
    pages_seen: int = 0
    _choices: dict[str, tuple[int, int]] = field(default_factory=dict)
    _selection_sequence: int = 0

    @property
    def ordered_menu_ids(self) -> tuple[str, ...]:
        return tuple(
            menu_id
            for menu_id, _ in sorted(
                self._choices.items(),
                key=lambda row: (row[1][0], row[1][1]),
            )
        )

    @property
    def ordered_instrument_ids(self) -> tuple[str, ...]:
        by_menu_id = {item.menu_id: item.instrument_id for item in self.menu}
        return tuple(by_menu_id[menu_id] for menu_id in self.ordered_menu_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "status": self.status.value,
            "pages_seen": self.pages_seen,
            "menu_count": len(self.menu),
            "next_cursor": (
                self.next_cursor.to_dict() if self.next_cursor is not None else None
            ),
            "ordered_menu_ids": list(self.ordered_menu_ids),
            "ordered_instrument_ids": list(self.ordered_instrument_ids),
        }


@dataclass
class InstrumentRoutingSession:
    question: str
    branches: dict[str, InstrumentRouteBranchState]
    status: RouteSessionStatus = RouteSessionStatus.ACTIVE
    wave_count: int = 0
    in_flight_pages: dict[str, InstrumentRoutePage] = field(default_factory=dict)

    @property
    def ordered_routes(self) -> dict[str, tuple[str, ...]]:
        return {
            branch_id: branch.ordered_instrument_ids
            for branch_id, branch in self.branches.items()
        }

    @property
    def missing_required_branches(self) -> tuple[str, ...]:
        return tuple(
            branch_id
            for branch_id, branch in self.branches.items()
            if branch.plan.required and not branch.ordered_instrument_ids
        )

    def cursor_snapshot(self) -> dict[str, Any]:
        """Return a serializable receipt including every preserved next page."""

        return {
            "schema_version": "legal-instrument-route-cursor-v1",
            "question_sha256": hashlib.sha256(
                self.question.encode("utf-8")
            ).hexdigest(),
            "status": self.status.value,
            "wave_count": self.wave_count,
            "branches": {
                branch_id: branch.to_dict()
                for branch_id, branch in self.branches.items()
            },
        }


ROUTE_SYSTEM = """너는 대한민국 금융규제 리서치의 법령 선택 라우터다.
법률 결론이나 적용 여부를 단정하지 말고, 현재 페이지에 제공된 실제 법령 menu_id만
선택한다. 각 선택에는 탐색 순서인 fallback_rank를 부여한다. 0을 먼저 탐색하고 숫자가
클수록 나중에 탐색한다. 프로필은 라우팅 힌트일 뿐 법적 효력이나 우열의 정답이 아니다.
현재 페이지의 모든 menu_id를 choices 또는 rejected_menu_ids 중 정확히 한 곳에 넣는다.
페이지 크기는 관찰 cap일 뿐 최종 후보 제한이 아니다. 현재 페이지에서 먼저 확인할
가능성이 있는 법령을 하나 이상 골랐다면, 뒤 페이지가 남아 있어도 그 법령을 조문
probe하기 위해 route_complete를 true로 둔다. 이 값은 법령 탐색의 최종 종료나 뒷
페이지 폐기를 뜻하지 않으며, 조문 coverage가 부족하면 보존된 cursor에서 재개된다.
현재 페이지에 probe할 법령이 없고 다음 페이지를 봐야 할 때만 route_complete를 false로
둔다. menu_id가 하나도 없으면 choices와 rejected_menu_ids를 빈 배열로 두며 placeholder를
만들지 않는다. 제공되지 않은 법령이나 ID를 만들지 않는다."""


def route_decision_schema(page: InstrumentRoutePage) -> dict[str, Any]:
    """Build the exact closed response schema for one page."""

    menu_ids = [item.menu_id for item in page.items]
    menu_id_schema: dict[str, Any] = {"type": "string"}
    if menu_ids:
        menu_id_schema["enum"] = menu_ids
    choices_schema: dict[str, Any] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "menu_id": menu_id_schema,
                "fallback_rank": {
                    "type": "integer", "minimum": 0, "maximum": 999,
                },
            },
            "required": ["menu_id", "fallback_rank"],
            "additionalProperties": False,
        },
    }
    rejected_schema: dict[str, Any] = {
        "type": "array",
        "items": menu_id_schema,
        "uniqueItems": True,
    }
    if not menu_ids:
        for value in (choices_schema, rejected_schema):
            value["maxItems"] = 0
            value["description"] = (
                "No legal-instrument menu IDs exist; return an empty array."
            )
    return {
        "type": "object",
        "properties": {
            "page_id": {"type": "string", "const": page.page_id},
            "choices": choices_schema,
            "rejected_menu_ids": rejected_schema,
            "route_complete": {"type": "boolean"},
            "rationale": {"type": "string"},
        },
        "required": [
            "page_id", "choices", "rejected_menu_ids", "route_complete",
            "rationale",
        ],
        "additionalProperties": False,
    }


def build_route_model_request(
    question: str,
    page: InstrumentRoutePage,
    *,
    model: str = ROUTER_PRODUCT_MODEL,
) -> RouteModelRequest:
    """Construct, but do not execute, one backend-bound product request."""

    payload = {
        "question": str(question),
        "route_page": page.to_dict(),
        "instruction": (
            "현재 페이지의 모든 menu_id를 선택 또는 기각한다. 선택한 법령이 있으면 "
            "보존 cursor를 전제로 먼저 조문 probe하도록 route_complete=true로 두고, "
            "선택할 법령 없이 다음 법령 페이지가 필요할 때만 false로 둔다."
        ),
    }
    return RouteModelRequest(
        kind="rag.legal_research.instrument_route",
        model=model,
        system=ROUTE_SYSTEM,
        user=json.dumps(payload, ensure_ascii=False, indent=2),
        schema=route_decision_schema(page),
    )


def validate_route_decision(
    page: InstrumentRoutePage,
    decision: InstrumentRouteDecision,
) -> None:
    """Reject invented IDs and implicit page-level candidate loss."""

    if decision.page_id != page.page_id:
        raise ClosedRouteMenuViolation(
            f"decision page_id {decision.page_id!r} does not match {page.page_id!r}"
        )
    page_ids = tuple(item.menu_id for item in page.items)
    page_set = set(page_ids)
    choice_ids = tuple(choice.menu_id for choice in decision.choices)
    rejected_ids = tuple(decision.rejected_menu_ids)
    if len(choice_ids) != len(set(choice_ids)):
        raise ClosedRouteMenuViolation("duplicate selected menu IDs")
    if len(rejected_ids) != len(set(rejected_ids)):
        raise ClosedRouteMenuViolation("duplicate rejected menu IDs")
    if any(choice.fallback_rank < 0 or choice.fallback_rank > 999
           for choice in decision.choices):
        raise ClosedRouteMenuViolation("fallback_rank must be between 0 and 999")
    supplied = set(choice_ids) | set(rejected_ids)
    invented = supplied - page_set
    if invented:
        raise ClosedRouteMenuViolation(
            f"decision contains IDs outside the closed page: {sorted(invented)}"
        )
    overlap = set(choice_ids) & set(rejected_ids)
    if overlap:
        raise ClosedRouteMenuViolation(
            f"menu IDs cannot be both selected and rejected: {sorted(overlap)}"
        )
    omitted = page_set - supplied
    if omitted:
        raise ClosedRouteMenuViolation(
            f"every page item needs an explicit disposition: {sorted(omitted)}"
        )


def select_route_wave_parallel(
    question: str,
    pages: Sequence[InstrumentRoutePage],
    selector: RoutePageSelector | Callable[
        [str, InstrumentRoutePage], InstrumentRouteDecision
    ],
    *,
    max_workers: int | None = None,
) -> tuple[InstrumentRouteDecision, ...]:
    """Evaluate independent issue-law menus concurrently and preserve order."""

    if not pages:
        return ()
    workers = max(1, min(max_workers or len(pages), len(pages)))

    def call(page: InstrumentRoutePage) -> InstrumentRouteDecision:
        if hasattr(selector, "select"):
            decision = selector.select(question, page)  # type: ignore[union-attr]
        else:
            decision = selector(question, page)  # type: ignore[operator]
        validate_route_decision(page, decision)
        return decision

    results: dict[str, InstrumentRouteDecision] = {}
    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="legal-instrument-route",
    ) as pool:
        futures = {pool.submit(call, page): page for page in pages}
        for future in as_completed(futures):
            page = futures[future]
            results[page.page_id] = future.result()
    return tuple(results[page.page_id] for page in pages)


class InstrumentRoutingPlanner:
    """Stateful pager that produces ordered law routes for issue branches."""

    def __init__(
        self,
        atlas: LegalResearchAtlas,
        profiles: Sequence[InstrumentProfile],
        *,
        page_size: int = 8,
        profile_model: str = ROUTER_PRODUCT_MODEL,
    ):
        if page_size < 1:
            raise ValueError("page_size must be at least 1")
        self.atlas = atlas
        self.page_size = int(page_size)
        if type(profile_model) is not str or not profile_model:
            raise ValueError("profile_model must be a non-empty string")
        self.profile_model = profile_model
        self._profiles = self._validate_profiles(profiles)
        self._menu_id_by_instrument = {
            record.instrument_id: _instrument_menu_id(record.instrument_id)
            for record in atlas.instruments
        }

    @property
    def profiles(self) -> tuple[InstrumentProfile, ...]:
        order = {item.instrument_id: index
                 for index, item in enumerate(self.atlas.instruments)}
        return tuple(sorted(
            self._profiles.values(),
            key=lambda row: order[row.instrument_id],
        ))

    def start(
        self,
        question: str,
        branches: Sequence[InstrumentRouteBranch],
    ) -> InstrumentRoutingSession:
        plans = tuple(branches)
        if not plans:
            raise ValueError("at least one issue branch is required")
        branch_ids = [plan.branch_id for plan in plans]
        if any(not branch_id.strip() for branch_id in branch_ids):
            raise ValueError("branch_id cannot be empty")
        if len(branch_ids) != len(set(branch_ids)):
            raise ValueError("branch_id values must be unique")

        states: dict[str, InstrumentRouteBranchState] = {}
        for plan in plans:
            self._validate_branch(plan)
            menu = self._build_menu(str(question), plan)
            fingerprint = _menu_fingerprint(
                str(question), plan, menu, self.page_size,
            )
            cursor = (
                InstrumentRouteCursor(
                    branch_id=plan.branch_id,
                    offset=0,
                    page_size=self.page_size,
                    menu_fingerprint=fingerprint,
                )
                if menu else None
            )
            states[plan.branch_id] = InstrumentRouteBranchState(
                plan=plan,
                menu=menu,
                next_cursor=cursor,
                status=(
                    RouteBranchStatus.ACTIVE
                    if cursor is not None else RouteBranchStatus.EXHAUSTED
                ),
            )
        session = InstrumentRoutingSession(question=str(question), branches=states)
        self._refresh_session(session)
        return session

    def next_wave(
        self,
        session: InstrumentRoutingSession,
    ) -> tuple[InstrumentRoutePage, ...]:
        """Present at most one capped page for every active issue branch."""

        if session.in_flight_pages:
            raise RuntimeError("apply the current route wave before requesting another")
        pages: list[InstrumentRoutePage] = []
        wave = session.wave_count + 1
        for branch_id, branch in session.branches.items():
            if branch.status is not RouteBranchStatus.ACTIVE:
                continue
            cursor = branch.next_cursor
            if cursor is None:
                branch.status = RouteBranchStatus.EXHAUSTED
                continue
            self._validate_cursor(branch, cursor)
            items = branch.menu[cursor.offset:cursor.offset + self.page_size]
            if not items:
                branch.next_cursor = None
                branch.status = RouteBranchStatus.EXHAUSTED
                continue
            next_offset = cursor.offset + len(items)
            next_cursor = (
                InstrumentRouteCursor(
                    branch_id=branch_id,
                    offset=next_offset,
                    page_size=self.page_size,
                    menu_fingerprint=cursor.menu_fingerprint,
                )
                if next_offset < len(branch.menu) else None
            )
            page = InstrumentRoutePage(
                page_id=(
                    f"IRW{wave}:B{quote(branch_id, safe='')}:O{cursor.offset}:"
                    f"{cursor.menu_fingerprint[:12]}"
                ),
                wave=wave,
                branch_id=branch_id,
                issue_axis=branch.plan.issue_axis,
                cursor=cursor,
                next_cursor=next_cursor,
                items=items,
                ordered_route_so_far=branch.ordered_instrument_ids,
            )
            if len(page.items) > self.page_size:
                raise AssertionError("page size is an observation cap")
            pages.append(page)
        if pages:
            session.wave_count = wave
            session.in_flight_pages = {page.page_id: page for page in pages}
        self._refresh_session(session)
        return tuple(pages)

    def apply_wave(
        self,
        session: InstrumentRoutingSession,
        decisions: Sequence[InstrumentRouteDecision],
    ) -> None:
        """Atomically validate and apply all branch decisions for a wave."""

        expected = session.in_flight_pages
        supplied = {decision.page_id: decision for decision in decisions}
        if len(supplied) != len(tuple(decisions)):
            raise ClosedRouteMenuViolation("duplicate route decision page_id")
        if set(supplied) != set(expected):
            raise ClosedRouteMenuViolation(
                "route decisions must cover exactly the in-flight pages"
            )

        # Validate the whole wave before mutating any branch.
        for page_id, page in expected.items():
            decision = supplied[page_id]
            validate_route_decision(page, decision)
            branch = session.branches[page.branch_id]
            total_after = len(branch._choices) + len(decision.choices)
            if decision.route_complete and branch.plan.required and total_after == 0:
                raise ClosedRouteMenuViolation(
                    f"required branch {branch.plan.branch_id!r} cannot complete empty"
                )

        for page_id, page in expected.items():
            decision = supplied[page_id]
            branch = session.branches[page.branch_id]
            for choice in decision.choices:
                if choice.menu_id in branch._choices:
                    raise ClosedRouteMenuViolation(
                        f"instrument already selected in branch: {choice.menu_id}"
                    )
                branch._choices[choice.menu_id] = (
                    choice.fallback_rank,
                    branch._selection_sequence,
                )
                branch._selection_sequence += 1
            branch.pages_seen += 1
            # Preserve this value even when the selector stops early.  A
            # caller can later resume the branch after the chosen route fails.
            branch.next_cursor = page.next_cursor
            if decision.route_complete:
                branch.status = RouteBranchStatus.ROUTE_READY
            elif page.next_cursor is not None:
                branch.status = RouteBranchStatus.ACTIVE
            else:
                branch.status = RouteBranchStatus.EXHAUSTED

        session.in_flight_pages.clear()
        self._refresh_session(session)

    def resume_branch(
        self,
        session: InstrumentRoutingSession,
        branch_id: str,
    ) -> InstrumentRouteCursor:
        """Continue an early-completed branch from its preserved next page."""

        if session.in_flight_pages:
            raise RuntimeError("apply the current route wave before resuming a branch")
        branch = session.branches.get(str(branch_id))
        if branch is None:
            raise ClosedRouteMenuViolation(f"unknown route branch: {branch_id}")
        if branch.status is not RouteBranchStatus.ROUTE_READY:
            raise ValueError("only an early-completed route can be resumed")
        if branch.next_cursor is None:
            raise ValueError("the route has no remaining menu page")
        self._validate_cursor(branch, branch.next_cursor)
        branch.status = RouteBranchStatus.ACTIVE
        session.status = RouteSessionStatus.ACTIVE
        return branch.next_cursor

    def _validate_profiles(
        self,
        profiles: Sequence[InstrumentProfile],
    ) -> dict[str, InstrumentProfile]:
        accepted: dict[str, InstrumentProfile] = {}
        for profile in profiles:
            instrument_id = str(profile.instrument_id)
            if instrument_id in accepted:
                raise ClosedRouteMenuViolation(
                    f"duplicate instrument profile: {instrument_id}"
                )
            if self.atlas.instrument(instrument_id) is None:
                raise ClosedRouteMenuViolation(
                    f"profile instrument is not current atlas data: {instrument_id}"
                )
            if profile.model != self.profile_model:
                raise ClosedRouteMenuViolation(
                    f"profile model must be {self.profile_model}: {profile.model}"
                )
            if not profile.roles:
                raise ClosedRouteMenuViolation(
                    f"profile has no routing role: {instrument_id}"
                )
            definition_ids = {
                unit.id for unit in self.atlas.definition_units(instrument_id)
            }
            self._validate_profile_points(
                instrument_id, profile.entry_point_ids, definitions_only=None,
            )
            self._validate_profile_points(
                instrument_id,
                profile.definition_point_ids,
                definitions_only=definition_ids,
            )
            accepted[instrument_id] = profile
        return accepted

    def _validate_profile_points(
        self,
        instrument_id: str,
        values: Sequence[str],
        *,
        definitions_only: set[str] | None,
    ) -> None:
        if len(tuple(values)) != len(set(values)):
            raise ClosedRouteMenuViolation(
                f"profile contains duplicate navigation IDs: {instrument_id}"
            )
        for menu_id in values:
            unit: NavigationUnit | None = self.atlas.resolve_menu_id(str(menu_id))
            if unit is None:
                raise ClosedRouteMenuViolation(
                    f"profile contains an invented navigation ID: {menu_id}"
                )
            if unit.instrument_id != instrument_id:
                raise ClosedRouteMenuViolation(
                    f"profile navigation ID belongs to another instrument: {menu_id}"
                )
            if definitions_only is not None and menu_id not in definitions_only:
                raise ClosedRouteMenuViolation(
                    f"profile definition point is not a definition article: {menu_id}"
                )

    def _validate_branch(self, plan: InstrumentRouteBranch) -> None:
        unknown = [
            instrument_id for instrument_id in plan.preferred_instrument_ids
            if self.atlas.instrument(instrument_id) is None
        ]
        if unknown:
            raise ClosedRouteMenuViolation(
                f"branch contains invented instrument IDs: {unknown}"
            )
        if len(plan.preferred_instrument_ids) != len(
            set(plan.preferred_instrument_ids)
        ):
            raise ValueError("preferred_instrument_ids must be unique")
        if any(not isinstance(role, InstrumentRole) for role in plan.preferred_roles):
            raise ValueError("preferred_roles must contain InstrumentRole values")

    def _build_menu(
        self,
        question: str,
        plan: InstrumentRouteBranch,
    ) -> tuple[InstrumentRouteMenuItem, ...]:
        text = _normalize_text(" ".join(
            [question, plan.issue_axis, *plan.topic_hints]
        ))
        preferred_order = {
            instrument_id: index
            for index, instrument_id in enumerate(plan.preferred_instrument_ids)
        }
        ordered_roles = tuple(dict.fromkeys(plan.preferred_roles))
        role_priority = {
            role: _ROLE_PRIORITY_STEP * (len(ordered_roles) - index)
            for index, role in enumerate(ordered_roles)
        }
        original_order = {
            record.instrument_id: index
            for index, record in enumerate(self.atlas.instruments)
        }
        rows: list[InstrumentRouteMenuItem] = []
        for record in self.atlas.instruments:
            profile = self._profiles.get(record.instrument_id)
            roles = (
                set(profile.roles) if profile is not None
                else {record.default_role}
            )
            score = 0
            signals: list[str] = []
            if record.instrument_id in preferred_order:
                score += 1000 - min(preferred_order[record.instrument_id], 99)
                signals.append("PREFERRED_INSTRUMENT")
            normalized_name = _normalize_text(record.name)
            if normalized_name and normalized_name in text:
                score += 500
                signals.append("QUESTION_NAMES_INSTRUMENT")
            matched_roles = [role for role in ordered_roles if role in roles]
            if matched_roles:
                # A multi-role profile receives only its best matching weight;
                # summing matches would reward profile breadth over branch fit.
                matched_role = matched_roles[0]
                score += role_priority[matched_role]
                signals.extend((
                    "ROLE_HINT_MATCH",
                    (
                        f"ROLE_PRIORITY:{matched_role.value}:"
                        f"{ordered_roles.index(matched_role) + 1}"
                    ),
                ))
            if profile is not None:
                matched_tags = [
                    tag for tag in profile.topic_tags
                    if len(_normalize_text(tag)) >= 2
                    and _normalize_text(tag) in text
                ]
                if matched_tags:
                    score += 120 * len(matched_tags)
                    signals.extend(
                        f"TOPIC_TAG:{tag}" for tag in matched_tags
                    )
            rows.append(InstrumentRouteMenuItem(
                menu_id=self._menu_id_by_instrument[record.instrument_id],
                instrument=record,
                profile=profile,
                routing_score=score,
                routing_signals=tuple(signals),
            ))
        rows.sort(key=lambda row: (
            -row.routing_score,
            preferred_order.get(row.instrument_id, 10**9),
            original_order[row.instrument_id],
        ))
        return tuple(rows)

    @staticmethod
    def _validate_cursor(
        branch: InstrumentRouteBranchState,
        cursor: InstrumentRouteCursor,
    ) -> None:
        if cursor.branch_id != branch.plan.branch_id:
            raise ClosedRouteMenuViolation("cursor belongs to another branch")
        if cursor.offset < 0 or cursor.offset >= len(branch.menu):
            raise ClosedRouteMenuViolation("cursor offset is outside the closed menu")
        if cursor.page_size < 1:
            raise ClosedRouteMenuViolation("cursor page_size is invalid")
        expected_fingerprint = (
            branch.next_cursor.menu_fingerprint
            if branch.next_cursor is not None else cursor.menu_fingerprint
        )
        if cursor.menu_fingerprint != expected_fingerprint:
            raise ClosedRouteMenuViolation("cursor menu fingerprint mismatch")

    @staticmethod
    def _refresh_session(session: InstrumentRoutingSession) -> None:
        if session.in_flight_pages or any(
            branch.status is RouteBranchStatus.ACTIVE
            for branch in session.branches.values()
        ):
            session.status = RouteSessionStatus.ACTIVE
            return
        if session.missing_required_branches:
            session.status = RouteSessionStatus.BLOCKED_NO_ROUTE
            return
        session.status = RouteSessionStatus.ROUTES_READY


def _instrument_menu_id(instrument_id: str) -> str:
    return f"instrument:{quote(str(instrument_id), safe='')}"


def _normalize_text(value: object) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(value or "").casefold())


def _menu_fingerprint(
    question: str,
    plan: InstrumentRouteBranch,
    menu: Sequence[InstrumentRouteMenuItem],
    page_size: int,
) -> str:
    payload = {
        "question": question,
        "plan": plan.to_dict(),
        "page_size": page_size,
        "menu": [item.to_dict() for item in menu],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ROUTER_PRODUCT_MODEL",
    "ROUTE_SYSTEM",
    "ClosedRouteMenuViolation",
    "InstrumentRouteBranch",
    "InstrumentRouteBranchState",
    "InstrumentRouteChoice",
    "InstrumentRouteCursor",
    "InstrumentRouteDecision",
    "InstrumentRouteMenuItem",
    "InstrumentRoutePage",
    "InstrumentRoutingPlanner",
    "InstrumentRoutingSession",
    "RouteBranchStatus",
    "RouteModelRequest",
    "RouteSessionStatus",
    "build_route_model_request",
    "route_decision_schema",
    "validate_route_decision",
]
