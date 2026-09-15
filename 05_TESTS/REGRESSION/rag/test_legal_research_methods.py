import pytest

from lawrag.research.legacy_rag.legal_research_state import (
    CandidateProvenance,
    ResearchCoordinate,
    build_source_span_verification,
    promote_candidate,
    seed_candidate,
    verify_candidate,
)
from lawrag.research.legacy_rag.legal_research_methods import (
    ALL_SCHEDULED_PAGES_RECEIPT,
    MAX_FINAL_EVIDENCE,
    AdaptivePagePolicy,
    AdaptivePolicyViolation,
    AdaptiveResearchCoordinator,
    ContinuationAction,
    ContinuationReason,
    DependencyActionKind,
    FinalEvidenceCandidate,
    FinalEvidenceCapViolation,
    PageObservation,
    ResearchCursor,
    compile_final_evidence,
    plan_research_step,
)


def _cursor(instrument: str, offset: int) -> ResearchCursor:
    return ResearchCursor(instrument, None, offset)


def _verified_record(candidate_id: str, document_id: str, node_id: str):
    coordinate = ResearchCoordinate(document_id, node_id)
    source = f"verified source for {document_id}:{node_id}"
    candidate = seed_candidate(
        candidate_id, coordinate, CandidateProvenance.SYSTEM_PRIOR
    )
    candidate = promote_candidate(
        candidate,
        CandidateProvenance.PROTECTED_CANDIDATE,
        reason="test source verification",
    )
    receipt = build_source_span_verification(
        candidate_id,
        coordinate,
        source,
        authority_generation="generation-1",
        authority_as_of="20260829",
    )
    return verify_candidate(
        candidate,
        (receipt,),
        source_resolver=lambda _coordinate: source,
        authority_generation="generation-1",
        authority_as_of="20260829",
    ), source


def test_duplicate_coordinate_cannot_borrow_verified_state_from_another_candidate():
    record, source = _verified_record("verified-id", "law-a", "1")
    rows = (
        FinalEvidenceCandidate(
            case_id="case-1",
            branch_id="verified-branch",
            candidate_id="verified-id",
            coordinate="law-a:1",
            instrument_id="law-a",
            verified=True,
            score=1.0,
            payload={"owner": "verified-id"},
        ),
        FinalEvidenceCandidate(
            case_id="case-1",
            branch_id="unverified-branch",
            candidate_id="spoofed-id",
            coordinate="law-a:1",
            instrument_id="law-a",
            verified=False,
            score=1_000_000.0,
            payload={"owner": "spoofed-id"},
        ),
    )

    compiled = compile_final_evidence(
        "case-1",
        rows,
        verification_records={"verified-id": record},
        source_resolver=lambda _coordinate: source,
        authority_generation="generation-1",
        authority_as_of="20260829",
    )

    assert len(compiled.selected) == 1
    assert compiled.selected[0].candidate_id == "verified-id"
    assert compiled.selected[0].payload == {"owner": "verified-id"}


def test_budget_extension_resumes_exact_law_cursor_and_absence_waits_for_exhaustion():
    policy = AdaptivePagePolicy(
        case_page_cap=1,
        branch_page_cap=1,
        instrument_page_cap=4,
    )
    coordinator = AdaptiveResearchCoordinator(policy)
    coordinator.register_case("case-1", ("issue",))
    coordinator.start_law(
        "case-1",
        "issue",
        "law-a",
        _cursor("law-a", 0),
        ("GOVERNING_RULE",),
        closed_scope=True,
    )

    first = coordinator.next_page_decision("case-1", "issue", "law-a")
    assert first.action is ContinuationAction.RETRIEVE_NEXT_PAGE
    assert first.reasons == (ContinuationReason.INITIAL_PAGE,)
    coordinator.record_page(
        "case-1",
        "issue",
        "law-a",
        PageObservation(
            "page-1",
            _cursor("law-a", 0),
            _cursor("law-a", 8),
            ("GOVERNING_RULE",),
            page_scores=(0.91, 0.72),
            next_score=0.40,
        ),
    )

    stopped = coordinator.next_page_decision("case-1", "issue", "law-a")
    assert stopped.action is ContinuationAction.INCOMPLETE_WITH_CURSOR
    assert stopped.cursor == _cursor("law-a", 8)
    assert ContinuationReason.MISSING_COVERAGE in stopped.reasons
    assert stopped.permits_scope_absence_statement is False

    coordinator.extend_budget("case-1", "issue", 1)
    resumed = coordinator.next_page_decision("case-1", "issue", "law-a")
    assert resumed.action is ContinuationAction.RETRIEVE_NEXT_PAGE
    assert resumed.cursor == _cursor("law-a", 8)

    coordinator.record_page(
        "case-1",
        "issue",
        "law-a",
        PageObservation(
            "page-2",
            _cursor("law-a", 8),
            None,
            ("GOVERNING_RULE",),
            scope_exhausted=True,
            exhaustion_receipt=ALL_SCHEDULED_PAGES_RECEIPT,
        ),
    )
    exhausted = coordinator.next_page_decision("case-1", "issue", "law-a")
    assert exhausted.action is ContinuationAction.SCOPE_EXHAUSTED
    assert exhausted.cursor is None
    assert exhausted.permits_scope_absence_statement is True


def test_next_page_requires_missing_coverage_or_close_score_tail():
    policy = AdaptivePagePolicy(
        case_page_cap=9,
        branch_page_cap=9,
        instrument_page_cap=9,
    )
    coordinator = AdaptiveResearchCoordinator(policy)
    coordinator.register_case("case", ("complete", "gap", "tail"))

    coordinator.start_law(
        "case", "complete", "law-complete", _cursor("law-complete", 0), ())
    coordinator.record_page(
        "case", "complete", "law-complete",
        PageObservation(
            "complete-1",
            _cursor("law-complete", 0),
            _cursor("law-complete", 8),
            (),
            page_scores=(0.95, 0.75),
            next_score=0.30,
        ),
    )
    decision = coordinator.next_page_decision(
        "case", "complete", "law-complete")
    assert decision.action is ContinuationAction.PAUSED_WITH_CURSOR
    with pytest.raises(AdaptivePolicyViolation, match="missing coverage or a close"):
        coordinator.record_page(
            "case", "complete", "law-complete",
            PageObservation(
                "complete-2",
                _cursor("law-complete", 8),
                _cursor("law-complete", 16),
                (),
            ),
        )

    coordinator.start_law(
        "case", "gap", "law-gap", _cursor("law-gap", 0), ("RULE",))
    coordinator.record_page(
        "case", "gap", "law-gap",
        PageObservation(
            "gap-1",
            _cursor("law-gap", 0),
            _cursor("law-gap", 8),
            ("RULE",),
            page_scores=(0.90, 0.70),
            next_score=0.20,
        ),
    )
    missing = coordinator.next_page_decision("case", "gap", "law-gap")
    assert missing.action is ContinuationAction.RETRIEVE_NEXT_PAGE
    assert missing.reasons == (ContinuationReason.MISSING_COVERAGE,)

    coordinator.start_law(
        "case", "tail", "law-tail", _cursor("law-tail", 0), ())
    coordinator.record_page(
        "case", "tail", "law-tail",
        PageObservation(
            "tail-1",
            _cursor("law-tail", 0),
            _cursor("law-tail", 8),
            (),
            page_scores=(0.90, 0.82),
            next_score=0.81,
        ),
    )
    close = coordinator.next_page_decision("case", "tail", "law-tail")
    assert close.action is ContinuationAction.RETRIEVE_NEXT_PAGE
    assert close.reasons == (ContinuationReason.CLOSE_SCORE_TAIL,)


def test_case_and_branch_budgets_cannot_starve_siblings_or_other_cases():
    coordinator = AdaptiveResearchCoordinator(AdaptivePagePolicy(
        case_page_cap=2,
        branch_page_cap=1,
        instrument_page_cap=1,
    ))
    coordinator.register_case("case-a", ("a-left", "a-right"))
    coordinator.register_case("case-b", ("b-only",))
    coordinator.start_law(
        "case-a", "a-left", "law-a-left", _cursor("law-a-left", 0), ("RULE",))
    coordinator.start_law(
        "case-a", "a-right", "law-a-right", _cursor("law-a-right", 0), ("RULE",))
    coordinator.start_law(
        "case-b", "b-only", "law-b", _cursor("law-b", 0), ("RULE",))

    coordinator.record_page(
        "case-a", "a-left", "law-a-left",
        PageObservation(
            "a-left-1",
            _cursor("law-a-left", 0),
            None,
            ("RULE",),
            scope_exhausted=True,
            exhaustion_receipt=ALL_SCHEDULED_PAGES_RECEIPT,
        ),
    )

    sibling = coordinator.next_page_decision(
        "case-a", "a-right", "law-a-right")
    other_case = coordinator.next_page_decision("case-b", "b-only", "law-b")
    assert sibling.action is ContinuationAction.RETRIEVE_NEXT_PAGE
    assert other_case.action is ContinuationAction.RETRIEVE_NEXT_PAGE
    assert sibling.budget_remaining["branch"] == 1
    assert other_case.budget_remaining["case"] == 1


def test_query_sections_coverage_facade_orders_wiki_dependencies_without_conclusion():
    sections = [
        {
            "coordinate": "law-a:17",
            "instrument_id": "law-a",
            "original_text": "원칙을 정한다. 다만 예외로 한다.",
            "tags": ["정의"],
        },
        {
            "coordinate": "law-b:12",
            "instrument_id": "law-b",
            "original_text": "별도의 등록을 받아야 한다.",
        },
    ]
    relations = [
        {
            "kind": "USES_DEFINITION",
            "source_coordinate": "law-a:17",
            "target_coordinate": "law-a:2",
            "target_instrument_id": "law-a",
        },
        {
            "kind": "VIOLATION_SANCTIONED_BY",
            "source_coordinate": "law-a:17",
            "target_coordinate": "law-a:99",
            "target_instrument_id": "law-a",
        },
        {
            "kind": "INCORPORATES",
            "source_coordinate": "law-a:17",
            "target_coordinate": "law-b:12",
            "target_instrument_id": "law-b",
        },
        {
            "kind": "DELEGATES_TO",
            "source_coordinate": "law-a:17",
            "target_coordinate": "law-b:13",
            "target_instrument_id": "law-b",
        },
    ]
    step = plan_research_step(
        "A법 허가만으로 B법 등록도 면제되는가?",
        sections,
        {"required": ["GOVERNING_RULE"], "satisfied": []},
        relations=relations,
        cursor_after=_cursor("law-a", 8),
        page_scores=(0.8,),
        next_score=0.2,
    )

    kinds = [row.kind for row in step.dependency_actions]
    assert kinds == sorted(kinds, key=lambda kind: {
        DependencyActionKind.READ_DEFINITION_FIRST: 0,
        DependencyActionKind.READ_GOVERNING_TEXT_WITH_PROVISO: 1,
        DependencyActionKind.FOLLOW_SANCTION: 2,
        DependencyActionKind.VERIFY_TWO_LAW_GATE: 3,
        DependencyActionKind.FOLLOW_INCORPORATION: 4,
        DependencyActionKind.FOLLOW_DELEGATION: 5,
    }[kind])
    assert {
        DependencyActionKind.READ_DEFINITION_FIRST,
        DependencyActionKind.READ_GOVERNING_TEXT_WITH_PROVISO,
        DependencyActionKind.FOLLOW_SANCTION,
        DependencyActionKind.VERIFY_TWO_LAW_GATE,
        DependencyActionKind.FOLLOW_INCORPORATION,
        DependencyActionKind.FOLLOW_DELEGATION,
    }.issubset(set(kinds))
    assert all(row.legal_conclusion is False for row in step.dependency_actions)
    assert all(row.may_satisfy_coverage is False for row in step.dependency_actions)
    assert step.legal_conclusion is False
    assert step.action is ContinuationAction.RETRIEVE_NEXT_PAGE
    assert ContinuationReason.MISSING_COVERAGE in step.reasons

    satisfied = [
        "GOVERNING_RULE",
        *(row.coverage_key for row in step.dependency_actions),
    ]
    complete = plan_research_step(
        "A법 허가만으로 B법 등록도 면제되는가?",
        sections,
        {"required": ["GOVERNING_RULE"], "satisfied": satisfied},
        relations=relations,
        cursor_after=_cursor("law-a", 8),
        page_scores=(0.8,),
        next_score=0.2,
    )
    assert complete.dependency_actions == ()
    assert complete.action is ContinuationAction.PAUSED_WITH_CURSOR


def test_final_evidence_is_verified_case_local_branch_fair_and_hard_capped_at_32():
    records = {}
    sources = {}
    for index in range(40):
        candidate_id = f"candidate-{index}"
        record, source = _verified_record(candidate_id, "law", str(index))
        records[candidate_id] = record
        sources[("law", str(index))] = source
    rows = [
        FinalEvidenceCandidate(
            case_id="case",
            branch_id=f"b-{index % 3}",
            candidate_id=f"candidate-{index}",
            coordinate=f"law:{index}",
            instrument_id="law",
            verified=True,
            score=float(100 - index),
            mandatory=index < 2,
            baseline_floor=index < 10,
            coverage_keys=(f"K-{index}",),
            source_order=index,
        )
        for index in range(40)
    ]
    rows.append(FinalEvidenceCandidate(
        case_id="case",
        branch_id="b-0",
        candidate_id="candidate-unverified-required",
        coordinate="law:unverified-required",
        instrument_id="law",
        verified=False,
        mandatory=True,
    ))
    rows.append(FinalEvidenceCandidate(
        case_id="case",
        branch_id="b-2",
        candidate_id="candidate-5",
        coordinate="law:5",
        instrument_id="law",
        verified=False,
        mandatory=True,
        coverage_keys=("DUPLICATE-BRANCH-REQUIREMENT",),
    ))

    resolver = lambda coordinate: sources[
        (coordinate.document_id, str(coordinate.node_id))
    ]
    compiled = compile_final_evidence(
        "case",
        rows,
        verification_records=records,
        source_resolver=resolver,
        authority_generation="generation-1",
        authority_as_of="20260829",
    )
    assert len(compiled.selected) == MAX_FINAL_EVIDENCE
    assert all(row.verified for row in compiled.selected)
    assert {row.branch_id for row in compiled.selected} == {"b-0", "b-1", "b-2"}
    assert "law:unverified-required" in compiled.unverified_coordinates
    assert "law:unverified-required" in compiled.missing_mandatory_coordinates
    assert next(row for row in compiled.selected if row.coordinate == "law:5").verified
    assert compiled.ready_for_legal_assessment is False

    with pytest.raises(ValueError, match="cannot mix cases"):
        compile_final_evidence("other-case", rows)
    with pytest.raises(ValueError, match="between 1 and 32"):
        compile_final_evidence("case", rows, cap=33)

    mandatory = []
    mandatory_records = {}
    mandatory_sources = {}
    for index in range(33):
        candidate_id = f"mandatory-{index}"
        record, source = _verified_record(candidate_id, "law", candidate_id)
        mandatory_records[candidate_id] = record
        mandatory_sources[("law", candidate_id)] = source
        mandatory.append(FinalEvidenceCandidate(
            case_id="case",
            branch_id="b",
            candidate_id=candidate_id,
            coordinate=f"law:{candidate_id}",
            instrument_id="law",
            verified=True,
            mandatory=True,
        ))
    with pytest.raises(FinalEvidenceCapViolation, match="exceed final cap 32"):
        compile_final_evidence(
            "case",
            mandatory,
            verification_records=mandatory_records,
            source_resolver=lambda coordinate: mandatory_sources[
                (coordinate.document_id, str(coordinate.node_id))
            ],
            authority_generation="generation-1",
            authority_as_of="20260829",
        )
