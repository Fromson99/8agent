from __future__ import annotations

from dataclasses import replace
from threading import Barrier

import pytest

from lawrag.core.rag.index import Index
from lawrag.research.legacy_rag.legal_instrument_routing import (
    ROUTER_PRODUCT_MODEL,
    ClosedRouteMenuViolation,
    InstrumentRouteBranch,
    InstrumentRouteChoice,
    InstrumentRouteDecision,
    InstrumentRoutingPlanner,
    RouteBranchStatus,
    RouteSessionStatus,
    build_route_model_request,
    select_route_wave_parallel,
)
from lawrag.research.legacy_rag.legal_research_atlas import (
    InstrumentProfile,
    InstrumentRole,
    LegalResearchAtlas,
)


def _atlas(count: int = 5) -> LegalResearchAtlas:
    docs = []
    for index in range(count):
        docs.append((
            f"law-{index}",
            {
                "name": f"테스트법{index}",
                "kind": "law",
                "status": "현행",
            },
            {
                "nodes": [
                    {
                        "id": index * 10 + 1,
                        "parent": None,
                        "surface": "제1조",
                        "title": "정의",
                        "family": "kr_article",
                        "level": 0,
                        "span": [0, 1],
                        "coordinate_scope": "body",
                    }
                ],
                "blocks": [
                    {
                        "idx": 0,
                        "text": f"제1조(정의) 테스트법{index}의 용어를 정한다.",
                    }
                ],
            },
        ))
    return LegalResearchAtlas.from_index(Index.from_docs(docs))


def _atlas_with_distinct_default_roles() -> LegalResearchAtlas:
    documents = (
        ("primary", "가나다 기본법", "law"),
        ("delegated", "가나다 기본법 시행령", "law"),
        ("supervisory", "라마바 감독규정", "admrul"),
        ("implementation", "사아자 시행세칙", "admrul"),
    )
    docs = []
    for index, (instrument_id, name, kind) in enumerate(documents):
        docs.append((
            instrument_id,
            {"name": name, "kind": kind, "status": "현행"},
            {
                "nodes": [{
                    "id": index + 1,
                    "parent": None,
                    "surface": "제1조",
                    "title": "정의",
                    "family": "kr_article",
                    "level": 0,
                    "span": [0, 1],
                    "coordinate_scope": "body",
                }],
                "blocks": [{
                    "idx": 0,
                    "text": f"제1조(정의) {name}의 용어를 정한다.",
                }],
            },
        ))
    return LegalResearchAtlas.from_index(Index.from_docs(docs))


def _profile(
    atlas: LegalResearchAtlas,
    instrument_id: str,
    *,
    entry_point_ids: tuple[str, ...] | None = None,
    model: str = ROUTER_PRODUCT_MODEL,
) -> InstrumentProfile:
    definition_id = atlas.definition_units(instrument_id)[0].id
    return InstrumentProfile(
        instrument_id=instrument_id,
        roles=(InstrumentRole.PRIMARY_ACT,),
        entry_point_ids=(
            entry_point_ids if entry_point_ids is not None else (definition_id,)
        ),
        definition_point_ids=(definition_id,),
        topic_tags=(f"주제-{instrument_id}",),
        scope_note="테스트 범위",
        rationale="사전 컴파일된 라우팅 힌트",
        model=model,
    )


def _decision(
    page,
    *,
    selected_index: int | None,
    fallback_rank: int = 0,
    route_complete: bool = False,
) -> InstrumentRouteDecision:
    selected_id = (
        page.items[selected_index].menu_id if selected_index is not None else None
    )
    return InstrumentRouteDecision(
        page_id=page.page_id,
        choices=(
            (InstrumentRouteChoice(selected_id, fallback_rank),)
            if selected_id is not None else ()
        ),
        rejected_menu_ids=tuple(
            item.menu_id for item in page.items if item.menu_id != selected_id
        ),
        route_complete=route_complete,
        rationale="closed fixture decision",
    )


def test_page_cap_never_truncates_atlas_or_cumulative_ordered_route() -> None:
    atlas = _atlas()
    # Missing profiles must not turn into missing laws.  Only two of the five
    # current instruments have compiled hints here.
    profiles = [_profile(atlas, "law-0"), _profile(atlas, "law-1")]
    planner = InstrumentRoutingPlanner(atlas, profiles, page_size=2)
    session = planner.start(
        "테스트 업무에 적용되는 법률을 찾아라",
        [InstrumentRouteBranch(branch_id="scope", issue_axis="적용범위")],
    )

    page_sizes = []
    presented_instrument_ids = []
    selected_by_rank = {}
    ranks = (2, 0, 1)
    page_number = 0
    while session.status is RouteSessionStatus.ACTIVE:
        page, = planner.next_wave(session)
        page_sizes.append(len(page.items))
        presented_instrument_ids.extend(item.instrument_id for item in page.items)
        selected_by_rank[ranks[page_number]] = page.items[0].instrument_id
        planner.apply_wave(session, [
            _decision(
                page,
                selected_index=0,
                fallback_rank=ranks[page_number],
                route_complete=not page.has_more,
            )
        ])
        page_number += 1

    assert page_sizes == [2, 2, 1]
    assert set(presented_instrument_ids) == set(atlas.current_document_ids)
    assert len(session.ordered_routes["scope"]) == 3
    assert len(session.ordered_routes["scope"]) > planner.page_size
    assert session.ordered_routes["scope"] == tuple(
        selected_by_rank[rank] for rank in (0, 1, 2)
    )
    assert session.status is RouteSessionStatus.ROUTES_READY


def test_preferred_role_order_uses_distinct_deterministic_weights() -> None:
    atlas = _atlas_with_distinct_default_roles()
    preferred_roles = (
        InstrumentRole.IMPLEMENTATION_DETAIL,
        InstrumentRole.SUPERVISORY_RULE,
        InstrumentRole.DELEGATED_LEGISLATION,
        InstrumentRole.PRIMARY_ACT,
    )
    planner = InstrumentRoutingPlanner(atlas, (), page_size=4)
    session = planner.start(
        "역할 우선순위만 확인",
        [InstrumentRouteBranch(
            branch_id="ordered-roles",
            issue_axis="역할 순위",
            preferred_roles=preferred_roles,
        )],
    )

    page, = planner.next_wave(session)

    assert tuple(item.instrument.default_role for item in page.items) == (
        preferred_roles
    )
    assert tuple(item.routing_score for item in page.items) == (320, 240, 160, 80)
    assert tuple(item.routing_signals[-1] for item in page.items) == (
        "ROLE_PRIORITY:IMPLEMENTATION_DETAIL:1",
        "ROLE_PRIORITY:SUPERVISORY_RULE:2",
        "ROLE_PRIORITY:DELEGATED_LEGISLATION:3",
        "ROLE_PRIORITY:PRIMARY_ACT:4",
    )


def test_planner_accepts_explicit_onsite_qwen_profile_provenance() -> None:
    atlas = _atlas(1)
    qwen_profile = replace(_profile(atlas, "law-0"), model="qwen-onsite")
    planner = InstrumentRoutingPlanner(
        atlas, [qwen_profile], profile_model="qwen-onsite",
    )
    assert planner.profiles[0].model == "qwen-onsite"

    with pytest.raises(ClosedRouteMenuViolation, match="profile model must"):
        InstrumentRoutingPlanner(atlas, [qwen_profile])


def test_parallel_issue_pages_and_early_stop_keep_exact_next_cursor() -> None:
    atlas = _atlas()
    planner = InstrumentRoutingPlanner(
        atlas,
        [_profile(atlas, instrument_id) for instrument_id in atlas.current_document_ids],
        page_size=2,
    )
    session = planner.start(
        "심사업무 외부 위탁의 허용 여부",
        [
            InstrumentRouteBranch(branch_id="sector", issue_axis="업무위탁"),
            InstrumentRouteBranch(branch_id="data", issue_axis="개인정보 처리위탁"),
        ],
    )

    first_wave = planner.next_wave(session)
    assert len(first_wave) == 2
    assert {page.wave for page in first_wave} == {1}
    by_branch = {page.branch_id: page for page in first_wave}
    planner.apply_wave(session, [
        _decision(
            by_branch["sector"], selected_index=0, route_complete=True,
        ),
        _decision(
            by_branch["data"], selected_index=0, route_complete=False,
        ),
    ])

    sector = session.branches["sector"]
    assert sector.status is RouteBranchStatus.ROUTE_READY
    assert sector.next_cursor is not None
    assert sector.next_cursor.offset == 2
    snapshot = session.cursor_snapshot()
    assert snapshot["branches"]["sector"]["next_cursor"]["offset"] == 2

    preserved = planner.resume_branch(session, "sector")
    second_wave = planner.next_wave(session)
    assert {page.branch_id for page in second_wave} == {"sector", "data"}
    resumed_sector = next(page for page in second_wave if page.branch_id == "sector")
    assert resumed_sector.cursor == preserved
    assert resumed_sector.cursor.offset == 2


def test_profiles_plans_and_page_decisions_reject_invented_closed_ids() -> None:
    atlas = _atlas(2)
    valid = _profile(atlas, "law-0")

    forged_instrument = InstrumentProfile(
        instrument_id="forged-law",
        roles=valid.roles,
        entry_point_ids=(),
        definition_point_ids=(),
        topic_tags=(),
        scope_note="",
        rationale="",
    )
    with pytest.raises(ClosedRouteMenuViolation, match="not current atlas"):
        InstrumentRoutingPlanner(atlas, [forged_instrument])

    forged_entry = _profile(
        atlas, "law-0", entry_point_ids=("nav:forged-law:forged",),
    )
    with pytest.raises(ClosedRouteMenuViolation, match="invented navigation"):
        InstrumentRoutingPlanner(atlas, [forged_entry])

    planner = InstrumentRoutingPlanner(atlas, [valid], page_size=2)
    with pytest.raises(ClosedRouteMenuViolation, match="invented instrument"):
        planner.start(
            "질문",
            [InstrumentRouteBranch(
                branch_id="issue",
                issue_axis="범위",
                preferred_instrument_ids=("forged-law",),
            )],
        )

    session = planner.start(
        "질문", [InstrumentRouteBranch(branch_id="issue", issue_axis="범위")],
    )
    page, = planner.next_wave(session)
    with pytest.raises(ClosedRouteMenuViolation, match="outside the closed page"):
        planner.apply_wave(session, [InstrumentRouteDecision(
            page_id=page.page_id,
            choices=(InstrumentRouteChoice("instrument:forged-law", 0),),
            rejected_menu_ids=tuple(item.menu_id for item in page.items),
            route_complete=True,
            rationale="forged",
        )])


def test_future_route_request_is_pure_closed_schema_and_haiku_pinned() -> None:
    atlas = _atlas(2)
    planner = InstrumentRoutingPlanner(
        atlas, [_profile(atlas, "law-0")], page_size=1,
    )
    session = planner.start(
        "어떤 법률부터 봐야 하나",
        [InstrumentRouteBranch(branch_id="issue", issue_axis="법령 선택")],
    )
    page, = planner.next_wave(session)

    request = build_route_model_request(session.question, page)
    enum_values = request.schema["properties"]["choices"]["items"][
        "properties"
    ]["menu_id"]["enum"]
    assert request.model == "claude-haiku-4-5-20251001"
    assert enum_values == [page.items[0].menu_id]
    assert request.kind == "rag.legal_research.instrument_route"


def test_issue_law_menu_selectors_really_run_in_parallel() -> None:
    atlas = _atlas(2)
    planner = InstrumentRoutingPlanner(atlas, [], page_size=1)
    session = planner.start(
        "병렬 법령 탐색",
        [
            InstrumentRouteBranch(branch_id="sector", issue_axis="업권"),
            InstrumentRouteBranch(branch_id="data", issue_axis="정보"),
        ],
    )
    pages = planner.next_wave(session)
    barrier = Barrier(2)

    def selector(_question, page):
        barrier.wait(timeout=2)
        return _decision(page, selected_index=0, route_complete=True)

    decisions = select_route_wave_parallel(
        session.question, pages, selector, max_workers=2)
    assert [decision.page_id for decision in decisions] == [
        page.page_id for page in pages
    ]
