#!/usr/bin/env python3
"""ADR-0107 deterministic hierarchy and parallel-frontier structure probe.

This runner does not call an LLM and does not measure product retrieval
quality.  A frozen target-aware selector is used only as a structural oracle:
if a target article exists in a declared law, can the atlas/controller reach
it without turning ``page_size`` into a final top-k cut?  The resulting trace
also checks ordered law fallback, branch-parallel waves, verified coverage,
relation gates, temporal evidence, and unresolved-fact gating.

MAIN, retrieval APIs, and feature switches are not imported or modified.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
from threading import Lock
import time
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for key, relative in (
    ("STRUCTURE_STORE", "data/structure"),
    ("STRUCTURE_CUSTOM_DIR", "data/custom"),
    ("GLOSSARY_STORE", "data/glossary.json"),
    ("RAG_LINKS_STORE", "data/links.json"),
    ("RAG_DELEGATION_STORE", "data/delegation.json"),
    ("RAG_LAW_INDEX_STORE", "data/law_index.json"),
    ("RAG_ENGINE_RULES", "data/rules/engine.json"),
):
    os.environ.setdefault(key, str(ROOT / relative))

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402
from lawrag.core.rag.legal_instrument_routing import (  # noqa: E402
    InstrumentRouteBranch,
    InstrumentRouteChoice,
    InstrumentRouteDecision,
    InstrumentRoutingPlanner,
    RouteSessionStatus,
    build_route_model_request,
    select_route_wave_parallel,
)
from lawrag.core.rag.legal_research_atlas import (  # noqa: E402
    LegalResearchAtlas,
    NavigationKind,
)
from lawrag.core.rag.legal_research_controller import (  # noqa: E402
    BranchPlan,
    CoverageVerification,
    ExhaustionPolicy,
    LegalResearchController,
    PageDecision,
    ReceiptVerification,
    ResearchPlan,
    ResearchStatus,
    decision_schema,
    select_wave_parallel,
)


ADR_ID = "ADR-0107"
EXPERIMENT_ID = "ADR-0107-experiment-v1"
RUN_ID = "run-001"
ADR = ROOT / "docs/adr/ADR-0107-hierarchical-parallel-legal-research-controller"
FIXTURE = ADR / "artifacts/frozen-structure-cases.json"
INVENTORY_OUTPUT = ADR / f"artifacts/atlas-inventory-{RUN_ID}.json"
LEDGER_OUTPUT = ADR / f"artifacts/retrieval-stage-ledger-{RUN_ID}.json"
RUN_OUTPUT = ADR / f"artifacts/{RUN_ID}.json"

# Frozen before the formal run.  If the fixture changes, the run must stop and
# the ADR design record must be revised before this constant is updated.
EXPECTED_FIXTURE_SHA256 = (
    "c7fbaf9262b237e1f1b31e9fa96dae89d0318d8452a769c7ab7b8fe4a75c63d6"
)
EXPECTED_TARGET_TOTAL = 36

DECLARED_STAGES = {
    "baseline": [
        "corpus-source", "flat-first-page", "baseline-present",
    ],
    "hierarchical-parallel-controller": [
        "corpus-source", "atlas-route", "hierarchy-page-waves",
        "relation-coverage", "candidate-present",
    ],
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _coordinate(value: str) -> tuple[str, int]:
    document_id, raw_node = str(value).rsplit(":", 1)
    return document_id, int(raw_node)


def _coordinate_text(document_id: object, node_id: object) -> str:
    return f"{document_id}:{node_id}"


def _unique(values: Iterable[tuple[str, int]]) -> list[tuple[str, int]]:
    return list(dict.fromkeys(values))


def _discard_reasons(
    before: Sequence[tuple[str, int]],
    after: Sequence[tuple[str, int]],
    reason: str,
) -> list[tuple[tuple[str, int], str]]:
    after_set = set(after)
    return [(value, reason) for value in before if value not in after_set]


def _target_rows(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for branch in case["branches"]:
        for target in branch["targets"]:
            rows.append({
                **target,
                "branch_id": branch["branch_id"],
                "issue_axis": branch["issue_axis"],
            })
    return rows


def _all_case_instruments(case: Mapping[str, Any]) -> list[str]:
    return list(dict.fromkeys(
        instrument_id
        for branch in case["branches"]
        for instrument_id in branch["instrument_ids"]
    ))


class FrozenCoverageVerifier:
    """Verify only frozen branch/article cells; selector claims are insufficient."""

    def __init__(self, case: Mapping[str, Any]) -> None:
        self._covers: dict[tuple[str, str], frozenset[str]] = {}
        for branch in case["branches"]:
            for target in branch["targets"]:
                self._covers[(
                    str(branch["branch_id"]), str(target["coordinate"]),
                )] = frozenset(str(value) for value in target["covers"])

    def verify(self, branch, item, claimed_keys) -> CoverageVerification:
        coordinate = _coordinate_text(item.instrument_id, item.node_id)
        allowed = self._covers.get((branch.branch_id, coordinate), frozenset())
        verified = tuple(key for key in claimed_keys if key in allowed)
        return CoverageVerification(
            verified_keys=verified,
            evidence_ids=(coordinate,) if verified else (),
            verifier="frozen-structure-coordinate-map-v1",
        )


class FrozenReceiptVerifier:
    """Accept only frozen relation edges and the loaded authority manifest."""

    def __init__(
        self, case: Mapping[str, Any], atlas: LegalResearchAtlas,
    ) -> None:
        self._relations = {
            (str(branch["branch_id"]), str(relation["relation_id"])):
            tuple(str(value) for value in relation["required_evidence"])
            for branch in case["branches"]
            for relation in branch.get("relation_requirements", ())
        }
        self._temporal = (
            f"authority-generation:{atlas.current_index.authority_generation}",
            f"authority-as-of:{atlas.current_index.authority_as_of}",
        )

    def verify(self, kind, session, branch_id, subject, evidence_ids):
        verified = False
        if kind == "relation" and branch_id is not None:
            expected = self._relations.get((branch_id, subject))
            selected = {
                coordinate
                for rows in _selected_by_branch(session).values()
                for coordinate in rows
            }
            verified = (
                expected is not None
                and tuple(evidence_ids) == expected
                and set(expected).issubset(selected)
            )
        elif kind == "temporal":
            verified = (
                tuple(evidence_ids) == self._temporal
                and _date_digits(subject) == _date_digits(session.plan.as_of)
            )
        return ReceiptVerification(
            verified=verified,
            verifier="frozen-closed-evidence-registry-v1",
        )


class ScriptedStructureSelector:
    """Target-aware oracle used only to test controller reachability mechanics."""

    def __init__(self, atlas: LegalResearchAtlas, case: Mapping[str, Any]) -> None:
        self._atlas = atlas
        self._targets: dict[str, dict[str, Mapping[str, Any]]] = {
            str(branch["branch_id"]): {
                str(target["coordinate"]): target
                for target in branch["targets"]
            }
            for branch in case["branches"]
        }
        self._selected: dict[str, set[str]] = {
            branch_id: set() for branch_id in self._targets
        }
        self._lock = Lock()

    def select(self, _question: str, page) -> PageDecision:
        branch_targets = self._targets[page.branch_id]
        with self._lock:
            already_selected = set(self._selected[page.branch_id])

        selected_ids: list[str] = []
        selected_coordinates: list[str] = []
        descend_ids: list[str] = []
        coverage: dict[str, tuple[str, ...]] = {}
        instrument_targets = {
            coordinate: target
            for coordinate, target in branch_targets.items()
            if _coordinate(coordinate)[0] == page.instrument_id
            and coordinate not in already_selected
        }

        for item in page.items:
            coordinate = _coordinate_text(item.instrument_id, item.node_id)
            if item.kind is NavigationKind.ARTICLE:
                target = instrument_targets.get(coordinate)
                if target is not None:
                    selected_ids.append(item.id)
                    selected_coordinates.append(coordinate)
                    coverage[item.id] = tuple(str(key) for key in target["covers"])
                continue
            if any(
                self._atlas.is_ancestor(
                    page.instrument_id, item.node_id, _coordinate(coordinate)[1],
                )
                for coordinate in instrument_targets
            ):
                descend_ids.append(item.id)

        with self._lock:
            self._selected[page.branch_id].update(selected_coordinates)
            selected_after = set(self._selected[page.branch_id])

        remaining_in_instrument = any(
            _coordinate(coordinate)[0] == page.instrument_id
            and coordinate not in selected_after
            for coordinate in branch_targets
        )
        route_complete = (
            page.exhaustion_policy is ExhaustionPolicy.TARGETED_ROUTE
            and not remaining_in_instrument
            and not descend_ids
            and not page.has_more
        )
        selected_set = set(selected_ids)
        descend_set = set(descend_ids)
        rejected_ids = tuple(
            item.id for item in page.items
            if item.id not in selected_set and item.id not in descend_set
        )
        return PageDecision(
            page_id=page.page_id,
            selected_ids=tuple(selected_ids),
            descend_ids=tuple(descend_ids),
            defer_ids=(),
            rejected_ids=rejected_ids,
            coverage_by_id=coverage,
            route_complete=route_complete,
            rationale=(
                "Frozen structural oracle follows only ancestors and article "
                "coordinates declared before run; no merits inference."
            ),
        )


class FrozenInstrumentSelector:
    """Target-aware law-menu oracle for the law-selection mechanics only."""

    def __init__(self, case: Mapping[str, Any]) -> None:
        self._expected = {
            str(branch["branch_id"]): tuple(
                str(value) for value in branch["instrument_ids"])
            for branch in case["branches"]
        }
        self._selected = {
            branch_id: set() for branch_id in self._expected
        }
        self._lock = Lock()

    def select(self, _question: str, page) -> InstrumentRouteDecision:
        expected = self._expected[page.branch_id]
        expected_set = set(expected)
        choices = tuple(
            InstrumentRouteChoice(
                item.menu_id, fallback_rank=expected.index(item.instrument_id))
            for item in page.items
            if item.instrument_id in expected_set
        )
        with self._lock:
            self._selected[page.branch_id].update(
                item.instrument_id
                for item in page.items
                if item.instrument_id in expected_set
            )
            complete = self._selected[page.branch_id] == expected_set
        chosen = {choice.menu_id for choice in choices}
        return InstrumentRouteDecision(
            page_id=page.page_id,
            choices=choices,
            rejected_menu_ids=tuple(
                item.menu_id for item in page.items if item.menu_id not in chosen),
            route_complete=complete,
            rationale=(
                "Frozen target-aware law-menu oracle; verifies paging and cursor "
                "preservation, not question-only routing quality."
            ),
        )


def _route_instruments(
    case: Mapping[str, Any], atlas: LegalResearchAtlas,
) -> tuple[dict[str, tuple[str, ...]], dict[str, Any]]:
    planner = InstrumentRoutingPlanner(
        atlas, (), page_size=int(case["page_size"]))
    session = planner.start(
        str(case["question"]),
        tuple(
            InstrumentRouteBranch(
                branch_id=str(branch["branch_id"]),
                issue_axis=str(branch["issue_axis"]),
            )
            for branch in case["branches"]
        ),
    )
    selector = FrozenInstrumentSelector(case)
    waves: list[dict[str, Any]] = []
    while session.status is RouteSessionStatus.ACTIVE:
        pages = planner.next_wave(session)
        if not pages:
            break
        started = time.perf_counter()
        decisions = select_route_wave_parallel(
            session.question, pages, selector, max_workers=len(pages))
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        waves.append({
            "wave": pages[0].wave,
            "branch_count": len(pages),
            "branch_ids": [page.branch_id for page in pages],
            "parallel_selector": True,
            "max_workers": len(pages),
            "selector_elapsed_ms": elapsed_ms,
            "pages": [
                {
                    "page": page.to_dict(),
                    "future_haiku_request": build_route_model_request(
                        session.question, page).to_dict(),
                    "decision": decision.to_dict(),
                }
                for page, decision in zip(pages, decisions)
            ],
        })
        planner.apply_wave(session, decisions)

    routes = session.ordered_routes
    expected = {
        str(branch["branch_id"]): tuple(
            str(value) for value in branch["instrument_ids"])
        for branch in case["branches"]
    }
    exact = routes == expected
    result = {
        "probe_kind": "target-aware-instrument-menu-structural-oracle",
        "profile_count": 0,
        "profile_missing_does_not_filter_laws": True,
        "target_visible_to_structure_probe": True,
        "product_calls": 0,
        "page_size": int(case["page_size"]),
        "current_instrument_menu_count": len(atlas.instruments),
        "wave_count": len(waves),
        "page_decision_count": sum(wave["branch_count"] for wave in waves),
        "parallel_round_saving": (
            sum(wave["branch_count"] for wave in waves) - len(waves)
        ),
        "routes": {key: list(value) for key, value in routes.items()},
        "expected_routes": {key: list(value) for key, value in expected.items()},
        "routes_exact": exact,
        "page_cap_respected": all(
            len(page_record["page"]["items"]) <= int(case["page_size"])
            for wave in waves for page_record in wave["pages"]
        ),
        "cursor_snapshot": session.cursor_snapshot(),
        "waves": waves,
    }
    if not exact:
        raise ValueError(f"instrument route probe mismatch: {result['routes']}")
    return routes, result


def _build_plan(
    case: Mapping[str, Any],
    instrument_routes: Mapping[str, tuple[str, ...]],
) -> ResearchPlan:
    branches = tuple(
        BranchPlan(
            branch_id=str(branch["branch_id"]),
            issue_axis=str(branch["issue_axis"]),
            instrument_role=str(branch["branch_role"]),
            instrument_ids=tuple(instrument_routes[str(branch["branch_id"])]),
            required_coverage=tuple(
                str(value) for value in branch["required_coverage"]),
            required_relation_checks=tuple(
                str(value["relation_id"])
                for value in branch.get("relation_requirements", ())),
            required_evidence_by_coverage={
                str(key): tuple(str(value) for value in evidence)
                for key, evidence in (
                    branch.get("coverage_evidence_requirements") or {}
                ).items()
            },
            exhaustion_policy=ExhaustionPolicy(
                str(branch.get("exhaustion_policy") or "CLOSED_SCOPE")),
        )
        for branch in case["branches"]
    )
    return ResearchPlan(
        question=str(case["question"]),
        branches=branches,
        page_size=int(case["page_size"]),
        max_page_waves=int(case["max_page_waves"]),
        known_facts=dict(case.get("known_facts") or {}),
        unknown_fact_slots=tuple(
            str(value) for value in case.get("unknown_fact_slots", ())),
        as_of=str(case["as_of"]) if case.get("as_of") else None,
        temporal_verification_required=bool(
            case.get("temporal_verification_required", False)),
    )


def _selected_by_branch(session) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for branch_id, branch in session.branches.items():
        result[branch_id] = sorted({
            _coordinate_text(row["instrument_id"], row["node_id"])
            for row in branch.selected_evidence.values()
        })
    return result


def _record_ready_relations(
    controller: LegalResearchController,
    session,
    case: Mapping[str, Any],
) -> None:
    selected = {
        coordinate
        for rows in _selected_by_branch(session).values()
        for coordinate in rows
    }
    for branch_fixture in case["branches"]:
        branch_id = str(branch_fixture["branch_id"])
        branch_state = session.branches[branch_id]
        for relation in branch_fixture.get("relation_requirements", ()):
            relation_id = str(relation["relation_id"])
            if relation_id in branch_state.completed_relation_checks:
                continue
            evidence_ids = tuple(
                str(value) for value in relation["required_evidence"])
            if set(evidence_ids).issubset(selected):
                controller.record_relation_check(
                    session,
                    branch_id,
                    relation_id,
                    evidence_ids=evidence_ids,
                    verified=True,
                )


def _date_digits(value: object) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def _record_temporal_authority(
    controller: LegalResearchController,
    session,
    atlas: LegalResearchAtlas,
) -> None:
    if not session.plan.temporal_verification_required:
        return
    verified = (
        bool(session.plan.as_of)
        and _date_digits(session.plan.as_of)
        == _date_digits(atlas.current_index.authority_as_of)
    )
    controller.record_temporal_verification(
        session,
        evidence_ids=(
            f"authority-generation:{atlas.current_index.authority_generation}",
            f"authority-as-of:{atlas.current_index.authority_as_of}",
        ),
        verified=verified,
    )


def _case_source_coordinates(
    case: Mapping[str, Any], atlas: LegalResearchAtlas,
) -> list[tuple[str, int]]:
    return _unique(
        (str(unit.instrument_id), int(unit.node_id))
        for instrument_id in _all_case_instruments(case)
        for unit in atlas.article_units(instrument_id)
    )


def _flat_first_page_coordinates(
    case: Mapping[str, Any], atlas: LegalResearchAtlas,
) -> list[tuple[str, int]]:
    cap = int(case["page_size"])
    return _unique(
        (str(unit.instrument_id), int(unit.node_id))
        for instrument_id in _all_case_instruments(case)
        for unit in atlas.article_units(instrument_id)[:cap]
    )


def _capture_baseline(
    case: Mapping[str, Any], atlas: LegalResearchAtlas,
) -> dict[str, Any]:
    source = _case_source_coordinates(case, atlas)
    first_page = _flat_first_page_coordinates(case, atlas)
    recorder = ledger.StageLedgerRecorder(
        str(case["case_id"]), "baseline", ledger.identity_canonicalizer,
    )
    recorder.record_stage("corpus-source", "source", source)
    recorder.record_stage(
        "flat-first-page",
        "retrieve",
        first_page,
        parent_stage_ids=("corpus-source",),
        discard_reasons=_discard_reasons(
            source,
            first_page,
            "outside_flat_first_page_per_instrument_page_size_4",
        ),
    )
    recorder.record_stage(
        "baseline-present",
        "present",
        first_page,
        parent_stage_ids=("flat-first-page",),
    )
    return recorder.capture()


def _capture_candidate(
    case: Mapping[str, Any],
    atlas: LegalResearchAtlas,
    presented: Sequence[tuple[str, int]],
    relation_context: Sequence[tuple[str, int]],
    selected: Sequence[tuple[str, int]],
) -> dict[str, Any]:
    source = _case_source_coordinates(case, atlas)
    route = list(source)
    relation_after = _unique([*presented, *relation_context])
    recorder = ledger.StageLedgerRecorder(
        str(case["case_id"]),
        "hierarchical-parallel-controller",
        ledger.identity_canonicalizer,
    )
    recorder.record_stage("corpus-source", "source", source)
    recorder.record_stage(
        "atlas-route",
        "filter",
        route,
        parent_stage_ids=("corpus-source",),
    )
    recorder.record_stage(
        "hierarchy-page-waves",
        "retrieve",
        presented,
        parent_stage_ids=("atlas-route",),
        discard_reasons=_discard_reasons(
            route,
            presented,
            "not_visited_by_targeted_hierarchy_route_in_structural_probe",
        ),
    )
    recorder.record_stage(
        "relation-coverage",
        "expand",
        relation_after,
        parent_stage_ids=("hierarchy-page-waves",),
    )
    recorder.record_stage(
        "candidate-present",
        "present",
        selected,
        parent_stage_ids=("relation-coverage",),
        discard_reasons=_discard_reasons(
            relation_after,
            selected,
            "context_seen_but_not_selected_as_frozen_target_evidence",
        ),
    )
    return recorder.capture()


def _expected_fallback_receipt(case: Mapping[str, Any], trace) -> bool:
    expected = (case.get("expected") or {}).get(
        "must_record_before_next_instrument")
    if not expected:
        return True
    matches = [
        event for event in trace
        if event.event == expected["event"]
        and event.instrument_id == expected["instrument_id"]
        and event.details.get("permits_scope_absence_statement")
        is expected["permits_scope_absence_statement"]
    ]
    if not matches:
        return False
    sequence = matches[0].sequence
    return any(
        event.event == "INSTRUMENT_STARTED"
        and event.sequence > sequence
        and event.instrument_id != expected["instrument_id"]
        for event in trace
    )


def _run_case(
    case: Mapping[str, Any], atlas: LegalResearchAtlas,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    instrument_routes, instrument_routing = _route_instruments(case, atlas)
    verifier = FrozenCoverageVerifier(case)
    selector = ScriptedStructureSelector(atlas, case)
    controller = LegalResearchController(
        atlas,
        coverage_verifier=verifier,
        receipt_verifier=FrozenReceiptVerifier(case, atlas),
    )
    session = controller.create_session(_build_plan(case, instrument_routes))
    _record_temporal_authority(controller, session, atlas)

    wave_records: list[dict[str, Any]] = []
    presented_coordinates: list[tuple[str, int]] = []
    while session.status is ResearchStatus.ACTIVE:
        pages = controller.next_wave(session)
        if not pages:
            break
        selector_started = time.perf_counter()
        decisions = select_wave_parallel(
            session.plan.question,
            pages,
            selector,
            max_workers=len(pages),
        )
        selector_elapsed_ms = round(
            (time.perf_counter() - selector_started) * 1000, 3)
        for page in pages:
            presented_coordinates.extend(
                (str(item.instrument_id), int(item.node_id))
                for item in page.items
                if item.kind is NavigationKind.ARTICLE
            )
        wave_records.append({
            "wave": pages[0].wave,
            "branch_count": len(pages),
            "branch_ids": [page.branch_id for page in pages],
            "parallel_selector": True,
            "max_workers": len(pages),
            "selector_elapsed_ms": selector_elapsed_ms,
            "pages": [
                {
                    "page": page.to_dict(),
                    "closed_output_schema": decision_schema(page),
                    "decision": decision.to_dict(),
                }
                for page, decision in zip(pages, decisions)
            ],
        })
        controller.apply_wave(session, decisions)
        _record_ready_relations(controller, session, case)

    selected_map = _selected_by_branch(session)
    selected_coordinates = _unique(
        _coordinate(coordinate)
        for rows in selected_map.values()
        for coordinate in rows
    )
    target_rows = _target_rows(case)
    target_coordinates = [_coordinate(row["coordinate"]) for row in target_rows]
    target_by_branch = {
        str(branch["branch_id"]): {
            str(target["coordinate"]) for target in branch["targets"]
        }
        for branch in case["branches"]
    }
    branch_target_recovery = {
        branch_id: sorted(targets.intersection(selected_map[branch_id]))
        for branch_id, targets in target_by_branch.items()
    }
    relation_context = _unique(
        _coordinate(coordinate)
        for branch in case["branches"]
        for relation in branch.get("relation_requirements", ())
        for coordinate in relation["required_evidence"]
    )
    presented_unique = _unique(presented_coordinates)
    baseline_coordinates = _flat_first_page_coordinates(case, atlas)
    expected = case.get("expected") or {}
    expected_controller_status = str(
        expected.get("controller_status")
        or ResearchStatus.READY_FOR_ASSESSMENT.value
    )
    page_counts = [
        len(page_record["page"]["items"])
        for wave in wave_records for page_record in wave["pages"]
    ]
    selected_total = session.selected_evidence_count
    relation_complete = all(
        not branch.missing_relation_checks for branch in session.branches.values()
    )
    expected_gap_keys = {
        str(branch["branch_id"]): {
            str(gap["coverage_key"])
            for gap in branch.get("source_gaps", ())
            if gap.get("activation") == "ALWAYS"
        }
        for branch in case["branches"]
    }
    coverage_matches_source_boundary = all(
        set(session.branches[branch_id].missing_coverage) == gap_keys
        for branch_id, gap_keys in expected_gap_keys.items()
    )
    provenance_preserved = all(
        set(selected_map[branch_id]).issubset(target_by_branch[branch_id])
        for branch_id in target_by_branch
    )
    distinct_redelegation = True
    if case["case_id"] == "research-structure-002":
        required_keys = {
            key
            for branch in case["branches"]
            for key in branch["required_coverage"]
        }
        distinct_redelegation = {
            "sector_redelegation_rule",
            "credit_redelegation_special_rule",
            "privacy_redelegation_rule",
        }.issubset(required_keys)

    invariants = {
        "all_targets_recovered_in_own_branch": all(
            set(branch_target_recovery[branch_id]) == targets
            for branch_id, targets in target_by_branch.items()
        ),
        "page_size_is_view_cap_only": (
            max(page_counts, default=0) <= int(case["page_size"])
        ),
        "selected_evidence_preserved_cumulatively": (
            set(target_coordinates).issubset(set(selected_coordinates))
        ),
        "branch_provenance_preserved": provenance_preserved,
        "verified_coverage_matches_frozen_source_boundary": (
            coverage_matches_source_boundary),
        "required_relations_complete": relation_complete,
        "controller_status_matches_gate": (
            session.status.value == expected_controller_status
        ),
        "targeted_no_hit_is_not_scope_absence": _expected_fallback_receipt(
            case, session.trace),
        "three_redelegation_regimes_remain_distinct": distinct_redelegation,
        "law_menu_routes_are_exact_and_cap_safe": (
            instrument_routing["routes_exact"]
            and instrument_routing["page_cap_respected"]
        ),
    }
    if expected.get("selected_total_exceeds_page_size"):
        invariants["selected_total_exceeds_page_size"] = (
            selected_total > int(case["page_size"])
        )
    if expected.get("first_wave_branch_count") is not None:
        invariants["first_wave_contains_all_issue_branches"] = (
            bool(wave_records)
            and wave_records[0]["branch_count"]
            == int(expected["first_wave_branch_count"])
        )
    if case.get("unknown_fact_slots"):
        invariants["unresolved_application_facts_remain_explicit"] = (
            set(session.unresolved_fact_slots)
            == set(case["unknown_fact_slots"])
        )
    if case.get("temporal_verification_required"):
        invariants["authority_as_of_verified"] = session.temporal_verified
    if case.get("known_corpus_gaps"):
        invariants["known_external_source_gaps_preserved"] = (
            bool(case["known_corpus_gaps"])
        )
    if case["case_id"] == "research-structure-002":
        role_by_branch = {
            branch["branch_id"]: branch["branch_role"]
            for branch in case["branches"]
        }
        invariants["general_rule_kept_as_applicability_contrast"] = (
            role_by_branch.get("general-outsourcing-regulation")
            == "APPLICABILITY_CONTRAST"
        )

    structural_pass = all(invariants.values())
    case_result = {
        "case_id": case["case_id"],
        "question": case["question"],
        "probe_kind": "target-aware-structural-oracle",
        "target_visible_to_structure_probe": True,
        "gold_visible_to_product": False,
        "product_calls": 0,
        "page_size": case["page_size"],
        "target_count": len(target_coordinates),
        "baseline_target_hits": len(set(target_coordinates).intersection(
            baseline_coordinates)),
        "candidate_target_hits": len(set(target_coordinates).intersection(
            selected_coordinates)),
        "targets": [list(value) for value in target_coordinates],
        "baseline_presented": [list(value) for value in baseline_coordinates],
        "candidate_presented_article_coordinates": [
            list(value) for value in presented_unique
        ],
        "relation_context_coordinates": [list(value) for value in relation_context],
        "selected_coordinates": [list(value) for value in selected_coordinates],
        "selected_by_branch": selected_map,
        "branch_target_recovery": branch_target_recovery,
        "wave_count": len(wave_records),
        "page_decision_count": sum(wave["branch_count"] for wave in wave_records),
        "parallel_round_saving": (
            sum(wave["branch_count"] for wave in wave_records) - len(wave_records)
        ),
        "instrument_routing": instrument_routing,
        "waves": wave_records,
        "controller": session.to_dict(include_trace=True),
        "known_corpus_gaps": list(case.get("known_corpus_gaps") or ()),
        "behavior_policy": case.get("behavior_policy"),
        "invariants": invariants,
        "structural_status": (
            "STRUCTURAL_REACHABILITY_COMPLETE"
            if structural_pass else "STRUCTURAL_REACHABILITY_FAILED"
        ),
        "structural_pass": structural_pass,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    baseline_capture = _capture_baseline(case, atlas)
    candidate_capture = _capture_candidate(
        case,
        atlas,
        presented_unique,
        relation_context,
        selected_coordinates,
    )
    return case_result, baseline_capture, candidate_capture


def _validate_frozen_fixture(
    frozen: Mapping[str, Any], atlas: LegalResearchAtlas,
) -> dict[str, Any]:
    if frozen.get("schema_version") != "legal-research-structure-fixtures-v1":
        raise ValueError("unexpected frozen fixture schema")
    cases = frozen.get("cases")
    if not isinstance(cases, list) or len(cases) != 3:
        raise ValueError("frozen fixture must contain exactly three cases")
    rows = [row for case in cases for row in _target_rows(case)]
    if len(rows) != EXPECTED_TARGET_TOTAL:
        raise ValueError(
            f"expected {EXPECTED_TARGET_TOTAL} target rows, found {len(rows)}")

    target_inventory: list[dict[str, Any]] = []
    for case in cases:
        expected_recover = set(case["expected"]["must_recover"])
        actual_recover = {
            target["coordinate"]
            for branch in case["branches"] for target in branch["targets"]
        }
        if expected_recover != actual_recover:
            raise ValueError(f"{case['case_id']} must_recover differs from targets")
        for branch in case["branches"]:
            required = set(branch["required_coverage"])
            targets_by_coordinate = {
                str(target["coordinate"]): target
                for target in branch["targets"]
            }
            covered = {
                key for target in branch["targets"] for key in target["covers"]
            }
            source_gap_keys = {
                str(gap["coverage_key"])
                for gap in branch.get("source_gaps", ())
                if gap.get("activation") == "ALWAYS"
            }
            if required - covered != source_gap_keys or covered - required:
                raise ValueError(
                    f"{case['case_id']}/{branch['branch_id']} coverage mismatch: "
                    f"required-only={sorted(required-covered)}, "
                    f"target-only={sorted(covered-required)}, "
                    f"always-source-gaps={sorted(source_gap_keys)}"
                )
            for instrument_id in branch["instrument_ids"]:
                if atlas.instrument(instrument_id) is None:
                    raise ValueError(f"unknown/noncurrent instrument {instrument_id}")
            for key, evidence_ids in (
                branch.get("coverage_evidence_requirements") or {}
            ).items():
                if key not in required:
                    raise ValueError(
                        f"all_of evidence rule targets unknown coverage {key}")
                for coordinate_text in evidence_ids:
                    target = targets_by_coordinate.get(str(coordinate_text))
                    if target is None or key not in target["covers"]:
                        raise ValueError(
                            f"all_of evidence {coordinate_text} does not contribute "
                            f"coverage {key}")
            relation_ids: set[str] = set()
            for relation in branch.get("relation_requirements", ()):
                relation_id = str(relation["relation_id"])
                if relation_id in relation_ids:
                    raise ValueError(f"duplicate relation ID {relation_id}")
                relation_ids.add(relation_id)
                if relation.get("kind") not in {
                    "GRAPH_RELATION", "BEHAVIOR_GATE",
                }:
                    raise ValueError(f"invalid relation kind {relation_id}")
                if not relation.get("source") or not relation.get("target"):
                    raise ValueError(
                        f"directed relation endpoints missing {relation_id}")
                endpoint_coordinates = {
                    str(relation["source"]["coordinate"]),
                    *(str(value["coordinate"]) for value in relation["target"]),
                }
                if not endpoint_coordinates.issubset(
                    set(relation["required_evidence"])):
                    raise ValueError(
                        f"relation evidence omits endpoint for {relation_id}")
                for coordinate_text in relation["required_evidence"]:
                    document_id, node_id = _coordinate(coordinate_text)
                    unit = atlas.unit(document_id, node_id)
                    if unit is None or unit.kind is not NavigationKind.ARTICLE:
                        raise ValueError(
                            f"relation evidence is not a current article: "
                            f"{coordinate_text}")
            for target in branch["targets"]:
                document_id, node_id = _coordinate(target["coordinate"])
                unit = atlas.unit(document_id, node_id)
                if unit is None or unit.kind is not NavigationKind.ARTICLE:
                    raise ValueError(
                        f"target is not a current article: {target['coordinate']}")
                if unit.status == "DELETED":
                    raise ValueError(f"target article is deleted: {target['coordinate']}")
                article_text = _article_full_text(atlas, document_id, node_id)
                for assertion in target.get("assertions", ()):
                    missing_literals = [
                        literal for literal in assertion.get("all_literals", ())
                        if str(literal) not in article_text
                    ]
                    if missing_literals:
                        raise ValueError(
                            f"assertion {assertion.get('assertion_id')} missing "
                            f"literals at {target['coordinate']}: {missing_literals}")
                target_inventory.append({
                    "case_id": case["case_id"],
                    "branch_id": branch["branch_id"],
                    "coordinate": target["coordinate"],
                    "instrument_name": atlas.instrument(document_id).name,
                    "path": unit.path,
                    "label": unit.label,
                    "coordinate_scope": unit.coordinate_scope,
                    "status": unit.status,
                    "assertions": list(target.get("assertions") or ()),
                })
    return {
        "fixture_case_count": len(cases),
        "fixture_target_count": len(rows),
        "targets": target_inventory,
    }


def _percentile(values: Sequence[int], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return float(ordered[index])


def _article_full_text(
    atlas: LegalResearchAtlas, document_id: str, node_id: int,
) -> str:
    view = atlas.current_index.docs[document_id]
    node = view.by_id[node_id]
    start, end = node.get("span") or [0, 0]
    return "\n".join(
        str((view.block_by_idx.get(index) or {}).get("text") or "")
        for index in range(start, max(start + 1, end))
    )


def run() -> dict[str, Any]:
    started = time.perf_counter()
    fixture_hash = _sha(FIXTURE)
    if fixture_hash != EXPECTED_FIXTURE_SHA256:
        raise ValueError(
            "frozen fixture hash mismatch; revise ADR before running: "
            f"{fixture_hash} != {EXPECTED_FIXTURE_SHA256}"
        )
    frozen = json.loads(FIXTURE.read_text(encoding="utf-8"))
    index = index_mod.Index.load()
    atlas = LegalResearchAtlas.from_index(index)
    fixture_validation = _validate_frozen_fixture(frozen, atlas)

    all_articles = _unique(
        (record.instrument_id, int(unit.node_id))
        for record in atlas.instruments
        for unit in atlas.article_units(record.instrument_id)
    )
    inventory = atlas.to_inventory_dict()
    inventory["article_root_count"] = len(all_articles)
    inventory["body_article_root_count"] = sum(
        record.body_article_count for record in atlas.instruments)
    inventory["nonbody_article_root_count"] = sum(
        record.nonbody_article_count for record in atlas.instruments)
    inventory["frozen_fixture_validation"] = fixture_validation
    _write(INVENTORY_OUTPUT, inventory)

    case_results: list[dict[str, Any]] = []
    captures: list[dict[str, Any]] = []
    for case in frozen["cases"]:
        result, baseline_capture, candidate_capture = _run_case(case, atlas)
        case_results.append(result)
        captures.extend((baseline_capture, candidate_capture))

    targets_by_case = {
        case["case_id"]: [
            _coordinate(row["coordinate"]) for row in _target_rows(case)
        ]
        for case in frozen["cases"]
    }
    graded = [
        ledger.grade_capture(
            capture,
            targets_by_case[capture["case_id"]],
            canonicalizer=ledger.identity_canonicalizer,
        )
        for capture in captures
    ]
    for value in graded:
        ledger.validate_graded_ledger(
            value, expected_stage_ids=DECLARED_STAGES[value["arm_id"]])
    run_ledger = ledger.build_run_artifact(RUN_ID, graded, DECLARED_STAGES)
    experiment_ledger = ledger.build_experiment_artifact(
        ADR_ID, EXPERIMENT_ID, [run_ledger])
    _write(LEDGER_OUTPUT, experiment_ledger)

    target_total = sum(result["target_count"] for result in case_results)
    baseline_hits = sum(result["baseline_target_hits"] for result in case_results)
    candidate_hits = sum(result["candidate_target_hits"] for result in case_results)
    presented_counts = [
        len(result["candidate_presented_article_coordinates"])
        for result in case_results
    ]
    page_decisions = sum(result["page_decision_count"] for result in case_results)
    parallel_waves = sum(result["wave_count"] for result in case_results)
    instrument_page_decisions = sum(
        result["instrument_routing"]["page_decision_count"]
        for result in case_results
    )
    instrument_parallel_waves = sum(
        result["instrument_routing"]["wave_count"] for result in case_results
    )
    case_source_counts = [
        len(_case_source_coordinates(case, atlas)) for case in frozen["cases"]
    ]

    source_paths = {
        "frozen_fixture": FIXTURE,
        "atlas_code": ROOT / "lawrag/core/rag/legal_research_atlas.py",
        "controller_code": ROOT / "lawrag/core/rag/legal_research_controller.py",
        "instrument_routing_code": (
            ROOT / "lawrag/core/rag/legal_instrument_routing.py"),
        "behavior_code": ROOT / "lawrag/core/legal_graph/behavior.py",
        "runner_code": Path(__file__).resolve(),
        "atlas_tests": ROOT / "tests/rag/test_legal_research_atlas.py",
        "controller_tests": ROOT / "tests/rag/test_legal_research_controller.py",
        "instrument_routing_tests": (
            ROOT / "tests/rag/test_legal_instrument_routing.py"),
        "graph_current": ROOT / "data/legal_graph/CURRENT.json",
        "atlas_inventory": INVENTORY_OUTPUT,
    }
    source_hashes = {
        name: _sha(path) for name, path in source_paths.items() if path.exists()
    }
    summary = {
        "probe_scope": "structural_reachability_not_product_effectiveness",
        "case_count": len(case_results),
        "structural_cases_complete": sum(
            bool(result["structural_pass"]) for result in case_results),
        "targets_total": target_total,
        "baseline_target_hits": baseline_hits,
        "baseline_target_recall": baseline_hits / target_total,
        "candidate_target_hits": candidate_hits,
        "candidate_target_recall": candidate_hits / target_total,
        "page_size": 4,
        "page_size_violations": sum(
            not result["invariants"]["page_size_is_view_cap_only"]
            for result in case_results
        ),
        "candidate_presented_total_by_case": presented_counts,
        "candidate_presented_mean": statistics.mean(presented_counts),
        "candidate_presented_p50": statistics.median(presented_counts),
        "candidate_presented_p95": _percentile(presented_counts, 0.95),
        "page_decision_count_if_serial": page_decisions,
        "parallel_decision_wave_count": parallel_waves,
        "parallel_rounds_saved": page_decisions - parallel_waves,
        "parallel_round_reduction_ratio": (
            (page_decisions - parallel_waves) / page_decisions
            if page_decisions else 0.0
        ),
        "instrument_menu_page_decisions_if_serial": instrument_page_decisions,
        "instrument_menu_parallel_wave_count": instrument_parallel_waves,
        "instrument_menu_parallel_rounds_saved": (
            instrument_page_decisions - instrument_parallel_waves
        ),
        "parallel_advantage_kind": (
            "measured branch concurrency and theoretical decision-round saving; "
            "not an LLM latency claim"
        ),
        "corpus_current_document_count": len(atlas.instruments),
        "corpus_canonical_article_roots": len(all_articles),
        "case_source_article_counts": case_source_counts,
        "case_source_articles_total": sum(case_source_counts),
        "llm_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "product_calls": 0,
        "judge_calls": 0,
        "all_invariants_passed": all(
            result["structural_pass"] for result in case_results),
    }
    run_value = {
        "schema_version": "adr-0107-hierarchical-parallel-research-run-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "frozen_fixture_sha256": fixture_hash,
        "freeze_revision": frozen.get("freeze_revision"),
        "source_hashes": source_hashes,
        "authority": {
            "generation_id": atlas.current_index.authority_generation,
            "as_of": atlas.current_index.authority_as_of,
        },
        "probe_boundary": {
            "target_visible_to_structure_probe": True,
            "gold_visible_to_product": False,
            "product_selector_used": False,
            "legal_merits_scored": False,
            "purpose": (
                "isolate atlas/controller mechanics before measuring question-only "
                "LLM routing quality"
            ),
        },
        "summary": summary,
        "cases": case_results,
        "stage_ledger": {
            "path": str(LEDGER_OUTPUT.relative_to(ROOT)),
            "sha256": _sha(LEDGER_OUTPUT),
        },
        "atlas_inventory": {
            "path": str(INVENTORY_OUTPUT.relative_to(ROOT)),
            "sha256": _sha(INVENTORY_OUTPUT),
        },
        "computed_post_selection": True,
        "gold_visible_to_product": False,
        "product_calls": 0,
        "judge_calls": 0,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    _write(RUN_OUTPUT, run_value)
    return {
        "run": str(RUN_OUTPUT.relative_to(ROOT)),
        "ledger": str(LEDGER_OUTPUT.relative_to(ROOT)),
        "inventory": str(INVENTORY_OUTPUT.relative_to(ROOT)),
        "summary": summary,
        "elapsed_ms": run_value["elapsed_ms"],
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
