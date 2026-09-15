from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from lawrag.research.legacy_rag.legal_instrument_routing import (
    InstrumentRouteBranch,
    RouteBranchStatus,
)
from lawrag.research.legacy_rag.legal_research_controller import ResearchStatus
from scripts import rag_haiku_hierarchical_router_api_eval as runner
from scripts import rag_haiku_hierarchical_router_api_schema_retry_eval as schema_retry


class _Cursor:
    def __init__(self, offset: int = 4) -> None:
        self.offset = offset

    def to_dict(self) -> dict[str, int]:
        return {"offset": self.offset}


def test_adr0109_configuration_confines_every_output_to_new_adr() -> None:
    runner.configure_for_adr_0109()
    runner._assert_output_contract(fresh_run=False)
    root = runner.ADR.resolve()
    assert runner.ADR_ID == "ADR-0109"
    assert runner.CANDIDATE_ARM_ID == "fixed-hierarchical-router"
    assert all(root in path.resolve().parents for path in runner._output_paths())
    assert "ADR-0108" in str(runner.PUBLIC_INPUT)


def test_adr0110_configuration_confines_every_output_to_new_adr() -> None:
    schema_retry.configure_for_adr_0110()
    runner._assert_output_contract(fresh_run=False)
    root = runner.ADR.resolve()
    assert runner.ADR_ID == "ADR-0110"
    assert runner.CANDIDATE_ARM_ID == "official-schema-hierarchical-router"
    assert all(root in path.resolve().parents for path in runner._output_paths())
    assert "ADR-0108" in str(runner.PUBLIC_INPUT)


def test_probe_plan_uses_only_remaining_cumulative_coverage() -> None:
    branch = InstrumentRouteBranch(
        branch_id="threshold",
        issue_axis="THRESHOLD",
    )
    plans = runner._research_branch_plans(
        (branch,),
        {"threshold": ("instrument-a",)},
        {"threshold": ("CONDITION",)},
    )
    assert len(plans) == 1
    assert plans[0].required_coverage == ("CONDITION",)


def test_unsatisfied_probe_resumes_only_route_ready_branch_with_cursor() -> None:
    cursor = _Cursor()
    resumable = SimpleNamespace(
        status=RouteBranchStatus.ROUTE_READY,
        next_cursor=cursor,
    )
    exhausted = SimpleNamespace(
        status=RouteBranchStatus.EXHAUSTED,
        next_cursor=None,
    )
    session = SimpleNamespace(branches={"a": resumable, "b": exhausted})
    planner = Mock()
    planner.resume_branch.return_value = cursor
    runtime = runner._InstrumentRouteRuntime(planner=planner, session=session)

    resumed, events = runner._resume_unsatisfied_route_branches(
        runtime,
        ("a", "b"),
        probe_cycle=2,
    )

    assert resumed == ["a"]
    assert events == [{
        "event": "LAW_CURSOR_RESUMED",
        "probe_cycle": 2,
        "branch_id": "a",
        "cursor_before": {"offset": 4},
        "cursor_after": {"offset": 4},
    }]
    planner.resume_branch.assert_called_once_with(session, "a")


def test_research_cycle_merge_preserves_trace_and_cumulative_coverage() -> None:
    branch = InstrumentRouteBranch(branch_id="b", issue_axis="THRESHOLD")
    cycle = {
        "wave_count": 1,
        "observed_article_occurrences": ["doc:1"],
        "selected_coordinates": ["doc:1"],
        "fulltext_coverage_receipts": [],
        "waves": [],
        "session": {
            "branches": [{"branch_id": "b", "status": "SATISFIED"}],
            "trace": [{"sequence": 9, "event": "INSTRUMENT_STARTED"}],
        },
    }
    merged = runner._merge_research_cycles(
        (cycle,),
        query_branches=(branch,),
        satisfied_branch_ids={"b"},
        verified_coverage_by_branch={"b": {"GOVERNING_RULE"}},
        stop_reason="",
    )
    assert merged["status"] == ResearchStatus.READY_FOR_ASSESSMENT.value
    assert merged["session"]["trace"][0]["sequence"] == 1
    assert merged["session"]["trace"][0]["probe_cycle"] == 1
    assert merged["verified_coverage_by_branch"] == {
        "b": ["GOVERNING_RULE"],
    }


def test_article_probe_outcomes_distinguish_clean_no_hit_from_incomplete() -> None:
    clean = {
        "status": ResearchStatus.BLOCKED_MISSING_COVERAGE.value,
        "stop_reason": "",
        "session": {
            "branches": [{"branch_id": "b", "status": "EXHAUSTED"}],
        },
    }
    incomplete = {
        **clean,
        "status": ResearchStatus.INCOMPLETE_WITH_CURSOR.value,
        "stop_reason": "PROVIDER_OR_VALIDATION_FAILURE_WITH_CURSOR",
    }

    assert runner._article_probe_outcomes(clean, ("b",), set()) == {
        "b": "UNSATISFIED",
    }
    assert runner._article_probe_outcomes(incomplete, ("b",), set()) == {
        "b": "INCOMPLETE",
    }


def test_article_probe_outcomes_never_resume_satisfied_branch() -> None:
    result = {
        "status": ResearchStatus.READY_FOR_ASSESSMENT.value,
        "stop_reason": "",
        "session": {
            "branches": [{"branch_id": "b", "status": "SATISFIED"}],
        },
    }

    assert runner._article_probe_outcomes(result, ("b",), {"b"}) == {
        "b": "SATISFIED",
    }
