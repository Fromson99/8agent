#!/usr/bin/env python3
"""ADR-0110 entry point for the official-schema-transform router retry."""

from __future__ import annotations

from typing import Sequence

if __package__:
    from scripts import rag_haiku_hierarchical_router_api_eval as runner
else:
    import rag_haiku_hierarchical_router_api_eval as runner


def configure_for_adr_0110() -> None:
    """Confine every mutable output to ADR-0110 before preflight or calls."""

    runner.configure_for_adr_0109()
    runner.ADR_ID = "ADR-0110"
    runner.EXPERIMENT_ID = "ADR-0110-experiment-v1"
    runner.CANDIDATE_ARM_ID = "official-schema-hierarchical-router"
    runner.ARTIFACT_SCHEMA_PREFIX = "adr-0110"
    runner.RUNTIME_LOCK_SCHEMA = "adr-0110-runtime-lock-v1"
    runner.ADR = (
        runner.ROOT
        / "docs/adr/ADR-0110-hierarchical-router-official-schema-transform-retry"
    )
    runner.PRODUCT_CAPTURE_OUTPUT = (
        runner.ADR / "artifacts/product-capture-run-001.json"
    )
    runner.PROVIDER_CAPTURE_OUTPUT = (
        runner.ADR / "artifacts/provider-captures-run-001.json"
    )
    runner.CAPTURE_SEAL_OUTPUT = (
        runner.ADR / "artifacts/product-capture-seal-run-001.json"
    )
    runner.RUN_OUTPUT = runner.ADR / "artifacts/run-001.json"
    runner.STAGE_LEDGER_OUTPUT = (
        runner.ADR / "artifacts/retrieval-stage-ledger-run-001.json"
    )
    runner.LAW_ROUTE_LEDGER_OUTPUT = (
        runner.ADR / "artifacts/law-route-ledger-run-001.json"
    )
    runner.RUNTIME_LOCK = runner.ADR / "artifacts/runtime-lock-run-001.json"
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
    runner.DECLARED_STAGES = {
        "baseline": ["corpus-source", "exhaustive-present"],
        runner.CANDIDATE_ARM_ID: [
            "corpus-source",
            "instrument-route",
            "hierarchy-observed",
            "llm-selected",
            "fulltext-current-verify",
            "candidate-present",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    configure_for_adr_0110()
    return runner.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
