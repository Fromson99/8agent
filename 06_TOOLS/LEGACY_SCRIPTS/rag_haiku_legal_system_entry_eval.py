#!/usr/bin/env python3
"""ADR-0113 legal-system entry routing full-stack Haiku evaluation."""

from __future__ import annotations

from typing import Sequence

if __package__:
    from scripts import rag_haiku_hierarchical_router_api_eval as runner
else:
    import rag_haiku_hierarchical_router_api_eval as runner


def configure_for_adr_0113() -> None:
    """Enable the isolated entry layer and confine writes to ADR-0113."""

    runner.configure_for_adr_0109()
    runner.ADR_ID = "ADR-0113"
    runner.EXPERIMENT_ID = "ADR-0113-experiment-v1"
    runner.RUN_ID = "run-004"
    runner.CANDIDATE_ARM_ID = "legal-system-entry-preservation"
    runner.ARTIFACT_SCHEMA_PREFIX = "adr-0113"
    runner.RUNTIME_LOCK_SCHEMA = "adr-0113-runtime-lock-v1"
    runner.ADR = (
        runner.ROOT
        / "docs/adr/ADR-0113-legal-system-entry-routing-full-stack"
    )
    runner.PUBLIC_INPUT = (
        runner.ROOT
        / "docs/adr/ADR-0108-haiku-question-only-hierarchical-router-api"
        / "artifacts/public-input-run-001.json"
    )
    runner.PRODUCT_CAPTURE_OUTPUT = (
        runner.ADR / "artifacts/product-capture-run-004.json"
    )
    runner.PROVIDER_CAPTURE_OUTPUT = (
        runner.ADR / "artifacts/provider-captures-run-004.json"
    )
    runner.CAPTURE_SEAL_OUTPUT = (
        runner.ADR / "artifacts/product-capture-seal-run-004.json"
    )
    runner.RUN_OUTPUT = runner.ADR / "artifacts/run-004.json"
    runner.STAGE_LEDGER_OUTPUT = (
        runner.ADR / "artifacts/retrieval-stage-ledger-run-004.json"
    )
    runner.LAW_ROUTE_LEDGER_OUTPUT = (
        runner.ADR / "artifacts/law-route-ledger-run-004.json"
    )
    runner.RUNTIME_LOCK = runner.ADR / "artifacts/runtime-lock-run-004.json"
    runner.QUESTION_FILES = {
        "research-structure-001": (
            runner.ADR / "실험/질문-001-research-structure-001.md"
        ),
        "research-structure-002": (
            runner.ADR / "실험/질문-002-research-structure-002.md"
        ),
        "research-structure-003": (
            runner.ADR / "실험/질문-003-research-structure-003.md"
        ),
    }

    runner.LEGAL_SYSTEM_ENTRY_ENABLED = True
    runner.ENTRY_INSTRUMENT_LIMIT = 8
    runner.ENTRY_ARTICLE_LIMIT = 8
    runner.PROTECTED_PREFERRED_COUNT = 8
    runner.PROTECTED_ENTRY_COUNT_PER_INSTRUMENT = 8
    runner.INCLUDE_PROTECTED_ENTRY_STAGE = True
    runner.SEMANTIC_SCOPE_FILTER_ENABLED = True
    runner.INCLUDE_INSTRUMENT_PRIOR_STAGE = True
    runner.OBSERVED_STAGE_ID = "semantic-entry-observed"
    runner.VERIFY_STAGE_ID = "semantic-scope-verify"

    runner.MAX_LAW_WAVES = 8
    runner.MAX_ARTICLE_WAVES = 12
    runner.MAX_PROBE_CYCLES = 4
    runner.MAX_TOTAL_CALLS = 120
    runner.MAX_CASE_CALLS = {
        "research-structure-001": 40,
        "research-structure-002": 40,
        "research-structure-003": 40,
    }
    runner.MAX_INPUT_TOKENS = 750_000
    runner.MAX_OUTPUT_TOKENS = 150_000
    runner.MAX_WALL_MS = 720_000.0
    runner.CASE_INPUT_TOKEN_LIMIT = 250_000
    runner.CASE_OUTPUT_TOKEN_LIMIT = 50_000
    runner.CASE_WALL_MS = 240_000.0

    runner.MIN_TARGET_LAW_EXPOSED = 9
    runner.MIN_TARGET_LAW_SELECTED = 9
    runner.MIN_INSTRUMENT_ROUTE_GOLD = 27
    runner.MIN_OBSERVED_GOLD = 24
    runner.MIN_SELECTED_GOLD = 0
    runner.MIN_PRESENT_GOLD = 18
    runner.REQUIRE_ALL_STRUCTURAL_CASES = False
    runner.REQUIRE_ORDERED_NO_HIT = False
    runner.REQUIRE_CURSOR_RESUME = False
    runner.REQUIRE_COMPLETE_RESEARCH = False
    runner.REQUIRE_ROLE_PRIORITY_SIGNAL = True
    runner.SCORING_ONLY_FORBIDDEN_PRESENT = {
        # Filled from the frozen ADR-0112 post-selection error receipt only;
        # these coordinates never enter the product prompt or entry planner.
        "research-structure-001": ("c4b33879c7dc5554:2",),
        "research-structure-002": ("a6290be4f60968b4:547",),
    }
    runner.DECLARED_STAGES = {
        "baseline": ["corpus-source", "exhaustive-present"],
        runner.CANDIDATE_ARM_ID: [
            "corpus-source",
            "instrument-prior",
            "instrument-route",
            "semantic-entry-observed",
            "llm-selected",
            "protected-entry-preserved",
            "candidate-union",
            "semantic-scope-verify",
            "candidate-present",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    configure_for_adr_0113()
    return runner.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
