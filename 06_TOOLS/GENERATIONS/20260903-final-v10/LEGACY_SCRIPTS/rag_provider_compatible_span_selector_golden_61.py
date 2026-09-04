#!/usr/bin/env python3
"""ADR-0072: provider-compatible preverified span ID selector over golden 61."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import rag_verified_span_selector_golden_61 as core


ADR_ID = "ADR-0072"
MODEL = core.MODEL
IMPLEMENTATION = ROOT / "lawrag/core/rag/provider_compatible_span_selector.py"
PARENT_MANIFEST_SHA256 = core.PARENT_MANIFEST_SHA256


def _validate_adr_manifest(adr: Path, *, require_frozen: bool) -> dict:
    manifest = json.loads((adr / "실험/manifest.json").read_text("utf-8"))
    if manifest.get("adr_id") != ADR_ID:
        raise ValueError(f"expected {ADR_ID} manifest")
    parent = next(iter((manifest.get("lineage") or {}).get("parents") or ()), {})
    if (parent.get("experiment_id") != "ADR-0070-experiment-v1"
            or parent.get("arm_id") != "claim-citation-relevance-selector"
            or parent.get("manifest_sha256") != PARENT_MANIFEST_SHA256):
        raise ValueError("ADR-0072 parent lineage mismatch")
    arm_ids = {item.get("id") for item in
               (manifest.get("design") or {}).get("arms") or ()}
    if set(core.ARMS) - arm_ids:
        raise ValueError("ADR-0072 arm mismatch")
    calls = (manifest.get("llm_policy") or {}).get("llm_calls") or []
    if calls != [{
        "role": "provider_compatible_verified_span_selector",
        "class": "product", "model": MODEL, "repeats": 1,
        "temperature": "provider_default_omitted",
    }]:
        raise ValueError("ADR-0072 LLM policy mismatch")
    if len(manifest.get("questions") or ()) != 61:
        raise ValueError("ADR-0072 must freeze 61 questions")
    if require_frozen:
        if not (manifest.get("design") or {}).get(
                "criteria_frozen_before_run"):
            raise ValueError("criteria must be frozen before run")
        if ((manifest.get("dataset") or {}).get("sha256")
                != core.base.PARENT_FROZEN_SHA256):
            raise ValueError("frozen dataset SHA mismatch")
        run = next((item for item in manifest.get("runs") or ()
                    if item.get("id") == core.RUN_ID), None)
        if not run or run.get("status") not in {"planned", "running"}:
            raise ValueError("run-001 must be planned or running")
        if run.get("runner_sha256") != core._sha(Path(__file__).resolve()):
            raise ValueError("runner SHA is not frozen")
        expected = (run.get("implementation_sha256") or {}).get(
            "lawrag/core/rag/provider_compatible_span_selector.py")
        if expected != core._sha(IMPLEMENTATION):
            raise ValueError("implementation SHA is not frozen")
    return manifest


def _configure() -> None:
    from lawrag.core.rag import provider_compatible_span_selector as candidate
    from lawrag.core.rag import verified_span_selector as failed_candidate

    original_question_markdown = core._question_markdown

    def question_markdown(case: dict, row: dict, input_state: dict) -> str:
        return original_question_markdown(case, row, input_state).replace(
            "ADR-0071", "ADR-0072")

    failed_candidate.run = candidate.run
    core.ADR_ID = ADR_ID
    core.IMPLEMENTATION = IMPLEMENTATION
    core.__file__ = str(Path(__file__).resolve())
    core._validate_adr_manifest = _validate_adr_manifest
    core._question_markdown = question_markdown


def main() -> int:
    _configure()
    return core.main()


_zero_usage = core._zero_usage
_percentile = core._percentile
_promotion_stats = core._promotion_stats


if __name__ == "__main__":
    raise SystemExit(main())
