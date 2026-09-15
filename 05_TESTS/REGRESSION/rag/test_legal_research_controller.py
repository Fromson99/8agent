from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from lawrag.research.legacy_rag.legal_research_controller import (
    BranchPlan,
    BranchStatus,
    ClosedMenuViolation,
    CoverageVerification,
    ExhaustionPolicy,
    LegalResearchController,
    PageDecision,
    PageMode,
    ResearchPlan,
    ResearchStatus,
    ReceiptVerification,
    decision_schema,
)


@dataclass(frozen=True)
class _Unit:
    id: str
    instrument_id: str
    node_id: object
    parent_node_id: object | None
    path: str
    label: str
    kind: str
    has_children: bool

    @property
    def coordinate(self) -> str:
        return f"{self.instrument_id}:{self.node_id}"

    def to_dict(self):
        return {
            "id": self.id,
            "instrument_id": self.instrument_id,
            "node_id": self.node_id,
            "parent_node_id": self.parent_node_id,
            "path": self.path,
            "label": self.label,
            "kind": self.kind,
            "has_children": self.has_children,
            "coordinate": self.coordinate,
        }


class _Atlas:
    def __init__(self, rows: dict[tuple[str, object | None], tuple[_Unit, ...]]):
        self.rows = rows

    def children(self, instrument_id, parent_node_id):
        return self.rows.get((instrument_id, parent_node_id), ())

    def instrument(self, instrument_id):
        articles = [
            item
            for (document_id, _parent), items in self.rows.items()
            if document_id == instrument_id
            for item in items
            if item.kind == "ARTICLE"
        ]
        if not any(document_id == instrument_id for document_id, _ in self.rows):
            return None
        return SimpleNamespace(
            status="현행", version="test", article_count=len(articles))

    def resolve_menu_id(self, menu_id):
        return next(
            (
                item
                for items in self.rows.values()
                for item in items
                if item.id == menu_id
            ),
            None,
        )


class _Verifier:
    def __init__(self, coverage_by_coordinate: dict[str, tuple[str, ...]]):
        self.coverage_by_coordinate = coverage_by_coordinate

    def verify(self, branch, item, claimed_keys):
        allowed = set(self.coverage_by_coordinate.get(item.coordinate, ()))
        verified = tuple(key for key in claimed_keys if key in allowed)
        return CoverageVerification(
            verified_keys=verified,
            evidence_ids=((item.coordinate,) if verified else ()),
            verifier="frozen-test-map",
        )


class _ReceiptVerifier:
    def verify(self, kind, session, branch_id, subject, evidence_ids):
        allowed = {
            "relation": {"law:17"},
            "fact": {"user-statement:1"},
            "temporal": {"version-manifest:2025-01-01"},
        }
        return ReceiptVerification(
            verified=bool(evidence_ids) and set(evidence_ids).issubset(
                allowed.get(kind, set())),
            verifier="closed-test-evidence-registry",
        )


def _container(doc: str, node: int, parent=None) -> _Unit:
    return _Unit(
        id=f"N:{doc}:{node}", instrument_id=doc, node_id=node,
        parent_node_id=parent, path=f"장 {node}", label=f"장 {node}",
        kind="CONTAINER", has_children=True,
    )


def _article(doc: str, node: int, parent=None) -> _Unit:
    return _Unit(
        id=f"N:{doc}:{node}", instrument_id=doc, node_id=node,
        parent_node_id=parent, path=f"제{node}조", label=f"제{node}조",
        kind="ARTICLE", has_children=False,
    )


def _decision(page, *, selected=(), descend=(), defer=(), rejected=(),
              coverage=None, route_complete=False):
    return PageDecision(
        page_id=page.page_id,
        selected_ids=tuple(selected),
        descend_ids=tuple(descend),
        defer_ids=tuple(defer),
        rejected_ids=tuple(rejected),
        coverage_by_id=dict(coverage or {}),
        route_complete=route_complete,
        rationale="test",
    )


def test_cap_is_page_size_not_final_evidence_cap() -> None:
    chapter = _container("law", 10)
    a1, a2, a3 = (_article("law", node, 10) for node in (1, 2, 3))
    atlas = _Atlas({
        ("law", None): (chapter,),
        ("law", 10): (a1, a2, a3),
    })
    controller = LegalResearchController(
        atlas,
        coverage_verifier=_Verifier({
            a1.coordinate: ("k1",),
            a2.coordinate: ("k2",),
            a3.coordinate: ("k3",),
        }),
    )
    session = controller.create_session(ResearchPlan(
        question="세 조문을 모두 확인",
        branches=(BranchPlan(
            "b", "TEST", "ACT", ("law",), ("k1", "k2", "k3"),
        ),),
        page_size=2,
    ))

    root_page, = controller.next_wave(session)
    controller.apply_wave(session, [_decision(root_page, descend=(chapter.id,))])

    first_articles, = controller.next_wave(session)
    assert len(first_articles.items) == 2
    controller.apply_wave(session, [_decision(
        first_articles,
        selected=(a1.id, a2.id),
        coverage={a1.id: ("k1",), a2.id: ("k2",)},
    )])
    assert session.status is ResearchStatus.ACTIVE

    second_articles, = controller.next_wave(session)
    assert [item.id for item in second_articles.items] == [a3.id]
    controller.apply_wave(session, [_decision(
        second_articles,
        selected=(a3.id,),
        coverage={a3.id: ("k3",)},
    )])

    assert session.status is ResearchStatus.READY_FOR_ASSESSMENT
    assert session.selected_evidence_count == 3
    assert session.selected_evidence_count > session.plan.page_size
    assert all(
        event.details.get("item_count", 0) <= session.plan.page_size
        for event in session.trace
        if event.event in {"PAGE_PRESENTED", "DEFERRED_ARTICLE_REVIEW_PRESENTED"}
    )


def test_selector_coverage_claim_is_unverified_without_compiler() -> None:
    article = _article("law", 1)
    controller = LegalResearchController(_Atlas({("law", None): (article,)}))
    session = controller.create_session(ResearchPlan(
        question="근거",
        branches=(BranchPlan("b", "TEST", "ACT", ("law",), ("rule",)),),
    ))
    page, = controller.next_wave(session)
    controller.apply_wave(session, [_decision(
        page, selected=(article.id,), coverage={article.id: ("rule",)},
    )])
    assert session.branches["b"].satisfied_coverage == set()
    assert session.branches["b"].coverage_claims == {"rule": [article.id]}

    assert controller.next_wave(session) == ()
    assert session.status is ResearchStatus.BLOCKED_MISSING_COVERAGE


def test_one_page_per_branch_is_emitted_in_the_same_parallel_wave() -> None:
    rows = {}
    branches = []
    coverage = {}
    for index in range(3):
        doc = f"law-{index}"
        article = _article(doc, index + 1)
        rows[(doc, None)] = (article,)
        branches.append(BranchPlan(
            f"b-{index}", "TEST", "ACT", (doc,), (f"k-{index}",),
        ))
        coverage[article.coordinate] = (f"k-{index}",)
    controller = LegalResearchController(
        _Atlas(rows), coverage_verifier=_Verifier(coverage),
    )
    session = controller.create_session(ResearchPlan(
        question="세 법률 쟁점",
        branches=tuple(branches),
        page_size=1,
    ))

    pages = controller.next_wave(session)
    assert len(pages) == 3
    assert {page.branch_id for page in pages} == {"b-0", "b-1", "b-2"}
    controller.apply_wave(session, [
        _decision(
            page,
            selected=(page.items[0].id,),
            coverage={page.items[0].id: (f"k-{position}",)},
        )
        for position, page in enumerate(pages)
    ])
    assert session.status is ResearchStatus.READY_FOR_ASSESSMENT
    wave_events = [event for event in session.trace if event.event == "PARALLEL_WAVE_READY"]
    assert wave_events[0].details["parallel_page_count"] == 3


def test_targeted_route_no_hit_moves_to_next_instrument_without_absence_claim() -> None:
    wrong = _article("wrong-law", 1)
    target = _article("right-law", 17)
    controller = LegalResearchController(
        _Atlas({
            ("wrong-law", None): (wrong,),
            ("right-law", None): (target,),
        }),
        coverage_verifier=_Verifier({target.coordinate: ("rule",)}),
    )
    session = controller.create_session(ResearchPlan(
        question="첫 법에 없으면 다음 법",
        branches=(BranchPlan(
            "b", "TEST", "ORDERED_FALLBACK",
            ("wrong-law", "right-law"), ("rule",),
            exhaustion_policy=ExhaustionPolicy.TARGETED_ROUTE,
        ),),
    ))
    first, = controller.next_wave(session)
    controller.apply_wave(session, [_decision(first, route_complete=True)])

    second, = controller.next_wave(session)
    assert second.instrument_id == "right-law"
    controller.apply_wave(session, [_decision(
        second, selected=(target.id,), coverage={target.id: ("rule",)},
    )])
    assert session.status is ResearchStatus.READY_FOR_ASSESSMENT
    branch = session.branches["b"]
    assert branch.targeted_no_hit_instruments == ["wrong-law"]
    assert branch.exhausted_instruments == []
    event = next(item for item in session.trace if item.event == "TARGETED_ROUTE_NO_HIT")
    assert event.details["permits_scope_absence_statement"] is False


def test_semantic_article_entries_are_presented_before_root_hierarchy() -> None:
    chapter = _container("law", 10)
    first = _article("law", 1, 10)
    likely = _article("law", 17, 10)
    controller = LegalResearchController(
        _Atlas({
            ("law", None): (chapter,),
            ("law", 10): (first, likely),
        }),
        coverage_verifier=_Verifier({likely.coordinate: ("rule",)}),
    )
    session = controller.create_session(ResearchPlan(
        question="제17조가 의미상 진입점",
        branches=(BranchPlan(
            "b", "TEST", "SEMANTIC_ENTRY", ("law",), ("rule",),
            entry_point_ids_by_instrument={"law": (likely.id,)},
        ),),
        page_size=1,
    ))

    page, = controller.next_wave(session)
    assert page.mode is PageMode.SEMANTIC_ENTRY
    assert [item.id for item in page.items] == [likely.id]
    controller.apply_wave(session, [_decision(
        page,
        selected=(likely.id,),
        coverage={likely.id: ("rule",)},
    )])
    assert session.status is ResearchStatus.READY_FOR_ASSESSMENT


def test_semantic_entry_ids_must_be_closed_articles_owned_by_planned_law() -> None:
    chapter = _container("law", 10)
    article = _article("law", 17, 10)
    controller = LegalResearchController(_Atlas({
        ("law", None): (chapter,),
        ("law", 10): (article,),
        ("other", None): (_article("other", 1),),
    }))

    with pytest.raises(ClosedMenuViolation):
        controller.create_session(ResearchPlan(
            question="잘못된 소유자",
            branches=(BranchPlan(
                "b", "TEST", "SEMANTIC_ENTRY", ("law",), ("rule",),
                entry_point_ids_by_instrument={"law": ("N:other:1",)},
            ),),
        ))
    with pytest.raises(ClosedMenuViolation):
        controller.create_session(ResearchPlan(
            question="컨테이너는 진입 조문이 아님",
            branches=(BranchPlan(
                "b", "TEST", "SEMANTIC_ENTRY", ("law",), ("rule",),
                entry_point_ids_by_instrument={"law": (chapter.id,)},
            ),),
        ))


def test_closed_scope_search_rejects_early_route_completion_and_unknown_ids() -> None:
    article = _article("law", 1)
    controller = LegalResearchController(_Atlas({("law", None): (article,)}))
    session = controller.create_session(ResearchPlan(
        question="부재를 입증",
        branches=(BranchPlan(
            "b", "TEST", "ACT", ("law",), ("rule",),
            exhaustion_policy=ExhaustionPolicy.CLOSED_SCOPE,
        ),),
    ))
    page, = controller.next_wave(session)
    with pytest.raises(ClosedMenuViolation):
        controller.apply_wave(session, [_decision(page, route_complete=True)])
    with pytest.raises(ClosedMenuViolation):
        controller.apply_wave(session, [_decision(page, selected=("invented",))])
    schema = decision_schema(page)
    assert schema["properties"]["route_complete"]["const"] is False
    assert schema["properties"]["selected_ids"]["items"]["enum"] == [article.id]


def test_deferred_article_is_presented_again_instead_of_being_deleted() -> None:
    article = _article("law", 1)
    controller = LegalResearchController(
        _Atlas({("law", None): (article,)}),
        coverage_verifier=_Verifier({article.coordinate: ("rule",)}),
    )
    session = controller.create_session(ResearchPlan(
        question="불확실하면 재검토",
        branches=(BranchPlan("b", "TEST", "ACT", ("law",), ("rule",)),),
    ))
    page, = controller.next_wave(session)
    controller.apply_wave(session, [_decision(page, defer=(article.id,))])

    review, = controller.next_wave(session)
    assert review.mode is PageMode.DEFERRED_REVIEW
    assert [item.id for item in review.items] == [article.id]
    controller.apply_wave(session, [_decision(
        review, selected=(article.id,), coverage={article.id: ("rule",)},
    )])
    assert session.status is ResearchStatus.READY_FOR_ASSESSMENT


def test_fact_temporal_and_relation_checks_are_conjunctive_completion_gates() -> None:
    article = _article("law", 17)
    controller = LegalResearchController(
        _Atlas({("law", None): (article,)}),
        coverage_verifier=_Verifier({article.coordinate: ("rule",)}),
        receipt_verifier=_ReceiptVerifier(),
    )
    session = controller.create_session(ResearchPlan(
        question="사실과 시점을 확인",
        branches=(BranchPlan(
            "b", "TEST", "ACT", ("law",), ("rule",),
            required_relation_checks=("RULE_INCORPORATION",),
        ),),
        unknown_fact_slots=("is_financial_company",),
        as_of="2025-01-01",
        temporal_verification_required=True,
    ))
    page, = controller.next_wave(session)
    controller.apply_wave(session, [_decision(
        page, selected=(article.id,), coverage={article.id: ("rule",)},
    )])
    assert session.branches["b"].status is BranchStatus.ACTIVE

    controller.record_relation_check(
        session, "b", "RULE_INCORPORATION",
        evidence_ids=(article.coordinate,), verified=True,
    )
    assert session.status is ResearchStatus.NEEDS_FACT
    controller.record_fact(
        session, "is_financial_company", True,
        evidence_ids=("user-statement:1",), verified=True,
    )
    assert session.status is ResearchStatus.TEMPORAL_UNVERIFIED
    controller.record_temporal_verification(
        session, evidence_ids=("version-manifest:2025-01-01",), verified=True,
    )
    assert session.status is ResearchStatus.READY_FOR_ASSESSMENT


def test_budget_exhaustion_is_resumable_cursor_not_not_found() -> None:
    chapter = _container("law", 10)
    target = _article("law", 1, 10)
    controller = LegalResearchController(_Atlas({
        ("law", None): (chapter,),
        ("law", 10): (target,),
    }))
    session = controller.create_session(ResearchPlan(
        question="budget",
        branches=(BranchPlan("b", "TEST", "ACT", ("law",), ("rule",)),),
        max_page_waves=1,
    ))
    page, = controller.next_wave(session)
    controller.apply_wave(session, [_decision(page, descend=(chapter.id,))])
    assert controller.next_wave(session) == ()
    assert session.status is ResearchStatus.INCOMPLETE_WITH_CURSOR
    assert session.branches["b"].active_frontier

    controller.extend_budget(session, 1)
    resumed, = controller.next_wave(session)
    assert resumed.items[0].id == target.id


def test_route_complete_cannot_turn_page_cap_into_final_cut() -> None:
    first = _article("law", 1)
    target = _article("law", 2)
    controller = LegalResearchController(_Atlas({
        ("law", None): (first, target),
    }))
    session = controller.create_session(ResearchPlan(
        question="다음 페이지까지 확인",
        branches=(BranchPlan(
            "b", "TEST", "ACT", ("law",), ("rule",),
            exhaustion_policy=ExhaustionPolicy.TARGETED_ROUTE,
        ),),
        page_size=1,
    ))
    page, = controller.next_wave(session)
    assert page.has_more
    with pytest.raises(ClosedMenuViolation):
        controller.apply_wave(session, [_decision(page, route_complete=True)])
    assert session.in_flight_pages == {page.page_id: page}


def test_unknown_instrument_cannot_emit_false_closed_scope_receipt() -> None:
    controller = LegalResearchController(_Atlas({("law", None): ()}))
    with pytest.raises(ClosedMenuViolation, match="unknown or noncurrent"):
        controller.create_session(ResearchPlan(
            question="오타 법령",
            branches=(BranchPlan(
                "b", "TEST", "ACT", ("typo-law",), ("rule",)),),
        ))


def test_unclassified_article_is_auto_deferred_for_second_review() -> None:
    article = _article("law", 1)
    controller = LegalResearchController(_Atlas({("law", None): (article,)}))
    session = controller.create_session(ResearchPlan(
        question="누락하지 말 것",
        branches=(BranchPlan("b", "TEST", "ACT", ("law",), ("rule",)),),
    ))
    page, = controller.next_wave(session)
    controller.apply_wave(session, [_decision(page)])
    review, = controller.next_wave(session)
    assert review.mode is PageMode.DEFERRED_REVIEW
    assert review.items == (article,)


def test_empty_requirement_branch_is_rejected() -> None:
    with pytest.raises(ValueError, match="needs coverage or relation"):
        BranchPlan("b", "TEST", "ACT", ("law",), ())


def test_external_verified_boolean_without_receipt_verifier_cannot_satisfy_gate() -> None:
    article = _article("law", 17)
    controller = LegalResearchController(
        _Atlas({("law", None): (article,)}),
        coverage_verifier=_Verifier({article.coordinate: ("rule",)}),
    )
    session = controller.create_session(ResearchPlan(
        question="관계 영수증",
        branches=(BranchPlan(
            "b", "TEST", "ACT", ("law",), ("rule",),
            required_relation_checks=("REFERENCES",),
        ),),
    ))
    page, = controller.next_wave(session)
    controller.apply_wave(session, [_decision(page, selected=(article.id,))])
    controller.record_relation_check(
        session, "b", "REFERENCES",
        evidence_ids=("invented",), verified=True,
    )
    assert session.branches["b"].missing_relation_checks == ("REFERENCES",)
    assert session.status is ResearchStatus.ACTIVE


def test_coverage_compiler_can_recover_selector_label_omission() -> None:
    article = _article("law", 1)
    controller = LegalResearchController(
        _Atlas({("law", None): (article,)}),
        coverage_verifier=_Verifier({article.coordinate: ("rule",)}),
    )
    session = controller.create_session(ResearchPlan(
        question="조문은 맞고 label만 누락",
        branches=(BranchPlan("b", "TEST", "ACT", ("law",), ("rule",)),),
    ))
    page, = controller.next_wave(session)
    controller.apply_wave(session, [_decision(page, selected=(article.id,))])
    assert session.status is ResearchStatus.READY_FOR_ASSESSMENT
    assert session.branches["b"].coverage_claims == {}
    assert session.branches["b"].satisfied_coverage == {"rule"}


def test_all_of_coverage_requires_source_and_incorporated_target() -> None:
    source = _article("source-law", 17)
    target = _article("target-law", 26)
    controller = LegalResearchController(
        _Atlas({
            ("source-law", None): (source,),
            ("target-law", None): (target,),
        }),
        coverage_verifier=_Verifier({
            source.coordinate: ("incorporated-rule",),
            target.coordinate: ("incorporated-rule",),
        }),
    )
    session = controller.create_session(ResearchPlan(
        question="준용 source와 target 모두 확인",
        branches=(BranchPlan(
            "b", "RULE_INCORPORATION", "CROSS_STATUTE",
            ("source-law", "target-law"),
            ("incorporated-rule",),
            required_evidence_by_coverage={
                "incorporated-rule": (source.coordinate, target.coordinate),
            },
            exhaustion_policy=ExhaustionPolicy.TARGETED_ROUTE,
        ),),
    ))
    first, = controller.next_wave(session)
    controller.apply_wave(session, [_decision(
        first, selected=(source.id,), route_complete=True,
    )])
    assert session.branches["b"].missing_coverage == ("incorporated-rule",)
    second, = controller.next_wave(session)
    controller.apply_wave(session, [_decision(second, selected=(target.id,))])
    assert session.status is ResearchStatus.READY_FOR_ASSESSMENT


def test_parallel_wave_commit_is_atomic_when_second_decision_is_invalid() -> None:
    left = _article("left", 1)
    right = _article("right", 2)
    controller = LegalResearchController(_Atlas({
        ("left", None): (left,),
        ("right", None): (right,),
    }))
    session = controller.create_session(ResearchPlan(
        question="원자적 wave",
        branches=(
            BranchPlan("left-b", "TEST", "ACT", ("left",), ("left-rule",)),
            BranchPlan("right-b", "TEST", "ACT", ("right",), ("right-rule",)),
        ),
    ))
    pages = controller.next_wave(session)
    trace_before = list(session.trace)
    with pytest.raises(ClosedMenuViolation):
        controller.apply_wave(session, [
            _decision(pages[0], selected=(left.id,)),
            _decision(pages[1], selected=("invented",)),
        ])
    assert session.trace == trace_before
    assert not session.branches["left-b"].selected_evidence
    assert set(session.in_flight_pages) == {page.page_id for page in pages}


def test_as_of_and_temporal_gate_must_be_declared_together() -> None:
    branch = BranchPlan("b", "TEST", "ACT", ("law",), ("rule",))
    with pytest.raises(ValueError, match="supplied together"):
        ResearchPlan(question="시점", branches=(branch,), as_of="2025-01-01")
    with pytest.raises(ValueError, match="supplied together"):
        ResearchPlan(
            question="시점", branches=(branch,),
            temporal_verification_required=True,
        )
