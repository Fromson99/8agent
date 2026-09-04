#!/usr/bin/env python3
"""ADR-0108 question-only Haiku hierarchical-router API evaluation.

This runner is intentionally isolated from MAIN and the public RAG API.  Its
most important invariant is a physical product/scoring boundary:

* the product phase reads only ``public-input-run-001.json`` plus the current
  corpus/atlas;
* every provider exchange and gold-free retrieval snapshot is persisted and
  SHA-256 sealed;
* only then is ADR-0107's frozen fixture opened for deterministic scoring.

``page_size`` is a page observation cap, never a final top-k.  Independent
issue branches are called concurrently, while a failed or over-budget wave is
left unapplied with its cursor intact.  Hitting a budget is therefore recorded
as ``INCOMPLETE_WITH_CURSOR`` and never as a legal absence.

The script makes real provider calls when executed normally.  Importing it,
compiling it, or using ``--preflight-only`` makes no provider call.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Iterable, Mapping, Sequence


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
for _key, _relative in (
    ("STRUCTURE_STORE", "01_DATA/structure"),
    ("STRUCTURE_CUSTOM_DIR", "01_DATA/custom"),
    ("GLOSSARY_STORE", "01_DATA/glossary.json"),
    ("RAG_LINKS_STORE", "01_DATA/links.json"),
    ("RAG_DELEGATION_STORE", "01_DATA/delegation.json"),
    ("RAG_LAW_INDEX_STORE", "01_DATA/law_index.json"),
    ("RAG_ENGINE_RULES", "01_DATA/rules/engine.json"),
):
    os.environ.setdefault(_key, str(ROOT / _relative))

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag import query_grounding  # noqa: E402
from lawrag.core.rag.experiments import retrieval_stage_ledger as ledger  # noqa: E402
from lawrag.core.rag.legal_research_llm_selector import (  # noqa: E402
    HAIKU_MODEL,
    AtlasArticleTextResolver,
    HaikuArticlePageSelector,
    HaikuInstrumentRouteSelector,
    ThreadLocalStructuredRecorder,
    branches_from_query_plan,
    plan_question,
)
from lawrag.core.rag.legal_instrument_routing import (  # noqa: E402
    InstrumentRouteBranch,
    InstrumentRoutePage,
    InstrumentRoutingSession,
    InstrumentRoutingPlanner,
    RouteBranchStatus,
    RouteSessionStatus,
    select_route_wave_parallel,
)
from lawrag.core.rag.legal_research_atlas import (  # noqa: E402
    LegalResearchAtlas,
    NavigationKind,
)
from lawrag.core.rag.legal_research_controller import (  # noqa: E402
    BranchStatus,
    BranchPlan,
    CoverageVerification,
    ExhaustionPolicy,
    LegalResearchController,
    PageDecision,
    ResearchPlan,
    ResearchStatus,
    select_wave_parallel,
)
from lawrag.core.rag.legal_system_entry import (  # noqa: E402
    LegalSystemEntryPlanner,
    apply_instrument_priors,
    scope_alignment,
)


ADR_ID = "ADR-0108"
EXPERIMENT_ID = "ADR-0108-experiment-v1"
RUN_ID = "run-001"
CANDIDATE_ARM_ID = "haiku-question-only-router"
ARTIFACT_SCHEMA_PREFIX = "adr-0108"
RUNTIME_LOCK_SCHEMA = "adr-0108-runtime-lock-v1"
PUBLIC_INPUT_SCHEMA = "adr-0108-public-router-input-v1"
ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0108-haiku-question-only-hierarchical-router-api"
PUBLIC_INPUT = ADR / "artifacts/public-input-run-001.json"

# This file is deliberately not opened anywhere in the product phase.  The
# only call site is _open_scoring_fixture_after_seal().
SCORING_FIXTURE = (
    ROOT
    / "docs/adr/ADR-0107-hierarchical-parallel-legal-research-controller"
    / "artifacts/frozen-structure-cases.json"
)

PRODUCT_CAPTURE_OUTPUT = ADR / "artifacts/product-capture-run-001.json"
PROVIDER_CAPTURE_OUTPUT = ADR / "artifacts/provider-captures-run-001.json"
CAPTURE_SEAL_OUTPUT = ADR / "artifacts/product-capture-seal-run-001.json"
RUN_OUTPUT = ADR / "artifacts/run-001.json"
STAGE_LEDGER_OUTPUT = ADR / "artifacts/retrieval-stage-ledger-run-001.json"
LAW_ROUTE_LEDGER_OUTPUT = ADR / "artifacts/law-route-ledger-run-001.json"
RUNTIME_LOCK = ADR / "artifacts/runtime-lock-run-001.json"

EXPECTED_PUBLIC_INPUT_SHA256 = (
    "dffd9c75271ba2539c2307d1431298c41f8ee4ffeea62ad51c54ce149aab90d5"
)
EXPECTED_SCORING_FIXTURE_SHA256 = (
    "c7fbaf9262b237e1f1b31e9fa96dae89d0318d8452a769c7ab7b8fe4a75c63d6"
)
EXPECTED_AUTHORITY_GENERATION = (
    "c5e1d95d187055fb425e4bf3f7ed7aa1fd40b30d0468f50aa3b9a135893f3666"
)
EXPECTED_AUTHORITY_AS_OF = "20260827"
EXPECTED_CURRENT_DOCUMENTS = 139
EXPECTED_CURRENT_ARTICLE_ROOTS = 17_365
EXPECTED_CASE_SOURCE_OCCURRENCES = 52_095
EXPECTED_CASE_IDS = (
    "research-structure-001",
    "research-structure-002",
    "research-structure-003",
)
PAGE_SIZE = 4
MAX_LAW_WAVES = 36
MAX_ARTICLE_WAVES = 96
MAX_PROBE_CYCLES = 36
MAX_PARALLEL_WORKERS = 4
MAX_TOTAL_CALLS = 242
MAX_CASE_CALLS = {
    "research-structure-001": 56,
    "research-structure-002": 158,
    "research-structure-003": 28,
}
MAX_INPUT_TOKENS = 1_000_000
MAX_OUTPUT_TOKENS = 200_000
MAX_CALL_P95_MS = 20_000.0
MAX_WALL_MS = 1_200_000.0
TRANSPORT_MAX_RETRIES = 0

# Optional reusable entry-layer hooks.  Historical ADR runners retain their
# exact behavior because every hook is disabled by default.
LEGAL_SYSTEM_ENTRY_ENABLED = False
ENTRY_INSTRUMENT_LIMIT = 8
ENTRY_ARTICLE_LIMIT = 12
PROTECTED_PREFERRED_COUNT = 0
SEMANTIC_SCOPE_FILTER_ENABLED = False
CASE_INPUT_TOKEN_LIMIT: int | None = None
CASE_OUTPUT_TOKEN_LIMIT: int | None = None
CASE_WALL_MS: float | None = None
_CASE_RECEIPT_OFFSETS: dict[str, int] = {}
_CASE_STARTED_AT: dict[str, float] = {}
INCLUDE_INSTRUMENT_PRIOR_STAGE = False
OBSERVED_STAGE_ID = "hierarchy-observed"
VERIFY_STAGE_ID = "fulltext-current-verify"
MIN_TARGET_LAW_EXPOSED = 12
MIN_TARGET_LAW_SELECTED = 12
MIN_INSTRUMENT_ROUTE_GOLD = 36
MIN_OBSERVED_GOLD = 36
MIN_SELECTED_GOLD = 36
MIN_PRESENT_GOLD = 36
REQUIRE_ALL_STRUCTURAL_CASES = True
REQUIRE_ORDERED_NO_HIT = True
REQUIRE_CURSOR_RESUME = True
REQUIRE_COMPLETE_RESEARCH = True
REQUIRE_ROLE_PRIORITY_SIGNAL = True
SCORING_ONLY_FORBIDDEN_PRESENT: Mapping[str, tuple[str, ...]] = {}
PROTECTED_ENTRY_COUNT_PER_INSTRUMENT = 0
INCLUDE_PROTECTED_ENTRY_STAGE = False

QUESTION_FILES = {
    "research-structure-001": ADR / "실험/질문-001-research-structure-001.md",
    "research-structure-002": ADR / "실험/질문-002-research-structure-002.md",
    "research-structure-003": ADR / "실험/질문-003-research-structure-003.md",
}

DECLARED_STAGES = {
    "baseline": ["corpus-source", "exhaustive-present"],
    CANDIDATE_ARM_ID: [
        "corpus-source",
        "instrument-route",
        "hierarchy-observed",
        "llm-selected",
        "fulltext-current-verify",
        "candidate-present",
    ],
}


def configure_for_adr_0109() -> None:
    """Point the reusable runner at ADR-0109 without touching ADR-0108 outputs."""

    global ADR_ID, EXPERIMENT_ID, CANDIDATE_ARM_ID, ARTIFACT_SCHEMA_PREFIX
    global RUNTIME_LOCK_SCHEMA, ADR, PUBLIC_INPUT, PRODUCT_CAPTURE_OUTPUT
    global PROVIDER_CAPTURE_OUTPUT, CAPTURE_SEAL_OUTPUT, RUN_OUTPUT
    global STAGE_LEDGER_OUTPUT, LAW_ROUTE_LEDGER_OUTPUT, RUNTIME_LOCK
    global QUESTION_FILES, DECLARED_STAGES

    ADR_ID = "ADR-0109"
    EXPERIMENT_ID = "ADR-0109-experiment-v1"
    CANDIDATE_ARM_ID = "fixed-hierarchical-router"
    ARTIFACT_SCHEMA_PREFIX = "adr-0109"
    RUNTIME_LOCK_SCHEMA = "adr-0109-runtime-lock-v1"
    ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0109-hierarchical-router-provider-ranking-probe-retry"
    PUBLIC_INPUT = (
        ROOT
        / "docs/adr/ADR-0108-haiku-question-only-hierarchical-router-api"
        / "artifacts/public-input-run-001.json"
    )
    PRODUCT_CAPTURE_OUTPUT = ADR / "artifacts/product-capture-run-001.json"
    PROVIDER_CAPTURE_OUTPUT = ADR / "artifacts/provider-captures-run-001.json"
    CAPTURE_SEAL_OUTPUT = ADR / "artifacts/product-capture-seal-run-001.json"
    RUN_OUTPUT = ADR / "artifacts/run-001.json"
    STAGE_LEDGER_OUTPUT = ADR / "artifacts/retrieval-stage-ledger-run-001.json"
    LAW_ROUTE_LEDGER_OUTPUT = ADR / "artifacts/law-route-ledger-run-001.json"
    RUNTIME_LOCK = ADR / "artifacts/runtime-lock-run-001.json"
    QUESTION_FILES = {
        "research-structure-001": ADR / "실험/질문-001-research-structure-001.md",
        "research-structure-002": ADR / "실험/질문-002-research-structure-002.md",
        "research-structure-003": ADR / "실험/질문-003-research-structure-003.md",
    }
    DECLARED_STAGES = {
        "baseline": ["corpus-source", "exhaustive-present"],
        CANDIDATE_ARM_ID: [
            "corpus-source",
            "instrument-route",
            "hierarchy-observed",
            "llm-selected",
            "fulltext-current-verify",
            "candidate-present",
        ],
    }


def _output_paths() -> tuple[Path, ...]:
    return (
        PRODUCT_CAPTURE_OUTPUT,
        PROVIDER_CAPTURE_OUTPUT,
        CAPTURE_SEAL_OUTPUT,
        RUN_OUTPUT,
        STAGE_LEDGER_OUTPUT,
        LAW_ROUTE_LEDGER_OUTPUT,
    )


def _assert_output_contract(*, fresh_run: bool) -> None:
    adr_root = ADR.resolve()
    historical_roots = {
        (ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0107-hierarchical-parallel-legal-research-controller").resolve(),
        (ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0108-haiku-question-only-hierarchical-router-api").resolve(),
    }
    for path in _output_paths():
        resolved = path.resolve()
        try:
            resolved.relative_to(adr_root)
        except ValueError as exc:
            raise ValueError(f"runner output escaped current ADR: {path}") from exc
        if any(root == resolved or root in resolved.parents for root in historical_roots):
            raise ValueError(f"runner output points into historical ADR: {path}")
        if fresh_run and path.exists():
            raise FileExistsError(
                f"immutable run output already exists; do not overwrite: {path}"
            )

_PUBLIC_ROOT_KEYS = {
    "schema_version",
    "contains_gold_or_reference_answer",
    "product_input_scope",
    "page_size",
    "cases",
}
_PUBLIC_CASE_KEYS = {"case_id", "question"}
_FORBIDDEN_PRODUCT_KEYS = {
    "targets",
    "target_coordinates",
    "expected",
    "must_recover",
    "covers",
    "assertions",
    "reference_answer",
    "gold_coordinates",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_runtime_lock() -> dict[str, Any]:
    """Fail before any provider call if the frozen implementation drifted."""

    if not RUNTIME_LOCK.is_file():
        raise ValueError(f"runtime lock missing: {RUNTIME_LOCK}")
    value = json.loads(RUNTIME_LOCK.read_text(encoding="utf-8"))
    if value.get("schema_version") != RUNTIME_LOCK_SCHEMA:
        raise ValueError("runtime lock schema mismatch")
    if value.get("model") != HAIKU_MODEL:
        raise ValueError("runtime lock model mismatch")
    if value.get("page_size") != PAGE_SIZE:
        raise ValueError("runtime lock page_size mismatch")
    if value.get("transport_max_retries") != TRANSPORT_MAX_RETRIES:
        raise ValueError("runtime lock retry policy mismatch")
    for row in value.get("source_files") or ():
        relative = str(row.get("path") or "")
        path = (ROOT / relative).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise ValueError(f"runtime lock path escaped repository: {relative}") from exc
        if not path.is_file() or _sha(path) != row.get("sha256"):
            raise ValueError(f"runtime source drift: {relative}")
    if value.get("public_input_sha256") != EXPECTED_PUBLIC_INPUT_SHA256:
        raise ValueError("runtime lock public input mismatch")
    if value.get("scoring_fixture_sha256") != EXPECTED_SCORING_FIXTURE_SHA256:
        raise ValueError("runtime lock scoring-fixture declaration mismatch")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )


def _value_sha(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    rows = sorted(float(value) for value in values)
    if len(rows) == 1:
        return rows[0]
    position = (len(rows) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return rows[lower]
    return rows[lower] + (rows[upper] - rows[lower]) * (position - lower)


def _coordinate_text(coordinate: tuple[str, int]) -> str:
    return f"{coordinate[0]}:{coordinate[1]}"


def _parse_coordinate(value: object) -> tuple[str, int]:
    if isinstance(value, Mapping):
        document_id = str(value.get("doc_id") or "")
        node = value.get("node")
    elif isinstance(value, str):
        document_id, raw_node = value.rsplit(":", 1)
        node = int(raw_node)
    else:
        document_id, node = tuple(value)  # type: ignore[arg-type]
        document_id = str(document_id)
    if not document_id or isinstance(node, bool) or not isinstance(node, int):
        raise ValueError(f"invalid canonical article coordinate: {value!r}")
    return document_id, node


def _unique_coordinates(
    values: Iterable[tuple[str, int]],
) -> list[tuple[str, int]]:
    return list(dict.fromkeys(values))


def _discard_reasons(
    before: Sequence[tuple[str, int]],
    after: Sequence[tuple[str, int]],
    reason: str,
) -> list[tuple[tuple[str, int], str]]:
    after_set = set(after)
    return [(value, reason) for value in before if value not in after_set]


def _assert_no_forbidden_product_keys(value: object, path: str = "public") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key) in _FORBIDDEN_PRODUCT_KEYS:
                raise ValueError(f"gold/scoring key {key!r} found at {path}")
            _assert_no_forbidden_product_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_forbidden_product_keys(item, f"{path}[{index}]")


def _assert_internal_evidence_maps_empty(
    value: object,
    path: str = "product_cases",
) -> None:
    """Permit the controller field name, but never hidden evidence IDs."""

    if isinstance(value, Mapping):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key == "required_evidence_by_coverage" and item not in ({}, None):
                raise ValueError(
                    f"product evidence map must be empty at {child_path}"
                )
            _assert_internal_evidence_maps_empty(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_internal_evidence_maps_empty(
                item, f"{path}[{index}]",
            )


def _load_public_input() -> list[dict[str, str]]:
    if _sha(PUBLIC_INPUT) != EXPECTED_PUBLIC_INPUT_SHA256:
        raise ValueError("public-input-run-001 hash mismatch")
    value = json.loads(PUBLIC_INPUT.read_text(encoding="utf-8"))
    if set(value) != _PUBLIC_ROOT_KEYS:
        raise ValueError("public input root fields differ from frozen contract")
    if value.get("schema_version") != PUBLIC_INPUT_SCHEMA:
        raise ValueError("public input schema mismatch")
    if value.get("contains_gold_or_reference_answer") is not False:
        raise ValueError("public input declares gold/reference content")
    if value.get("page_size") != PAGE_SIZE:
        raise ValueError("public input page_size differs from frozen cap")
    rows: list[dict[str, str]] = []
    for row in value.get("cases") or ():
        if not isinstance(row, Mapping) or set(row) != _PUBLIC_CASE_KEYS:
            raise ValueError("public input case fields differ")
        case_id = str(row.get("case_id") or "")
        question = str(row.get("question") or "")
        if not case_id or not question.strip():
            raise ValueError("public input case is empty")
        rows.append({"case_id": case_id, "question": question})
    if tuple(row["case_id"] for row in rows) != EXPECTED_CASE_IDS:
        raise ValueError("public input cases/order differ from frozen design")
    _assert_no_forbidden_product_keys(value)
    return rows


def _all_current_coordinates(atlas: LegalResearchAtlas) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for instrument in atlas.instruments:
        for unit in atlas.article_units(instrument.instrument_id):
            rows.append(_parse_coordinate((instrument.instrument_id, unit.node_id)))
    rows = _unique_coordinates(rows)
    if len(atlas.instruments) != EXPECTED_CURRENT_DOCUMENTS:
        raise ValueError(
            f"current document count drift: {len(atlas.instruments)}"
        )
    if len(rows) != EXPECTED_CURRENT_ARTICLE_ROOTS:
        raise ValueError(f"current article-root count drift: {len(rows)}")
    inventory = atlas.to_inventory_dict()
    if inventory.get("authority_generation") != EXPECTED_AUTHORITY_GENERATION:
        raise ValueError("authority generation drift")
    if str(inventory.get("authority_as_of") or "") != EXPECTED_AUTHORITY_AS_OF:
        raise ValueError("authority as-of drift")
    return rows


@dataclass
class CallBudget:
    total_limit: int = MAX_TOTAL_CALLS
    case_limits: Mapping[str, int] = field(default_factory=lambda: MAX_CASE_CALLS)
    total_reserved: int = 0
    by_case: Counter[str] = field(default_factory=Counter)

    def can_reserve(self, case_id: str, count: int) -> bool:
        if count < 0:
            return False
        return (
            self.total_reserved + count <= self.total_limit
            and self.by_case[case_id] + count <= int(self.case_limits[case_id])
        )

    def reserve(self, case_id: str, count: int) -> bool:
        if not self.can_reserve(case_id, count):
            return False
        self.total_reserved += count
        self.by_case[case_id] += count
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_limit": self.total_limit,
            "case_limits": dict(self.case_limits),
            "total_reserved": self.total_reserved,
            "by_case": dict(self.by_case),
        }


def _provider_usage(receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    input_tokens = 0
    output_tokens = 0
    durations: list[float] = []
    ttfts: list[float] = []
    failures = 0
    for receipt in receipts:
        provider = receipt.get("provider") or {}
        usage = provider.get("usage") or {}
        input_tokens += int(usage.get("input_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or 0)
        duration = provider.get("dur_ms")
        ttft = provider.get("ttft_ms")
        if isinstance(duration, (int, float)):
            durations.append(float(duration))
        if isinstance(ttft, (int, float)):
            ttfts.append(float(ttft))
        if (
            provider.get("error")
            or receipt.get("wrapper_error")
            or not isinstance(receipt.get("structured_output"), Mapping)
        ):
            failures += 1
    return {
        "calls": len(receipts),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "provider_duration_ms": round(sum(durations), 3),
        "provider_duration_p50_ms": round(
            statistics.median(durations) if durations else 0.0, 3
        ),
        "provider_duration_p95_ms": round(_percentile(durations, 0.95), 3),
        "ttft_p50_ms": round(
            statistics.median(ttfts) if ttfts else 0.0, 3
        ),
        "ttft_p95_ms": round(_percentile(ttfts, 0.95), 3),
        "first_pass_failures": failures,
    }


def _case_usage(
    recorder: ThreadLocalStructuredRecorder,
    case_id: str,
) -> dict[str, Any]:
    offset = _CASE_RECEIPT_OFFSETS.get(case_id, 0)
    return _provider_usage(recorder.receipts[offset:])


def _case_token_budget_exhausted(
    recorder: ThreadLocalStructuredRecorder,
    case_id: str,
) -> bool:
    usage = _case_usage(recorder, case_id)
    input_limit = CASE_INPUT_TOKEN_LIMIT or MAX_INPUT_TOKENS
    output_limit = CASE_OUTPUT_TOKEN_LIMIT or MAX_OUTPUT_TOKENS
    return (
        usage["input_tokens"] > input_limit
        or usage["output_tokens"] > output_limit
    )


def _case_wall_budget_exhausted(case_id: str, run_started: float) -> bool:
    started = _CASE_STARTED_AT.get(case_id, run_started)
    limit = CASE_WALL_MS or MAX_WALL_MS
    return (time.perf_counter() - started) * 1000 > limit


def _provider_capture_value(
    raw_receipts: Sequence[Mapping[str, Any]],
    *,
    budget: CallBudget,
    complete: bool,
    checkpoint_reason: str,
) -> dict[str, Any]:
    """Build the exact append-only provider view persisted at each checkpoint."""

    return {
        "schema_version": f"{ARTIFACT_SCHEMA_PREFIX}-provider-captures-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "checkpoint_at": _now(),
        "checkpoint_reason": checkpoint_reason,
        "complete": complete,
        "model": HAIKU_MODEL,
        "transport_max_retries": TRANSPORT_MAX_RETRIES,
        "gold_visible_to_product": False,
        "reserved_calls": budget.total_reserved,
        "receipt_count": len(raw_receipts),
        "receipts": list(raw_receipts),
    }


def _persist_provider_checkpoint(
    recorder: ThreadLocalStructuredRecorder,
    budget: CallBudget,
    *,
    checkpoint_reason: str,
) -> None:
    """Atomically persist provider evidence after every completed call wave."""

    _write(
        PROVIDER_CAPTURE_OUTPUT,
        _provider_capture_value(
            recorder.receipts,
            budget=budget,
            complete=False,
            checkpoint_reason=checkpoint_reason,
        ),
    )


def _persist_product_checkpoint(
    *,
    product_cases: Sequence[Mapping[str, Any]],
    recorder: ThreadLocalStructuredRecorder,
    budget: CallBudget,
    atlas: LegalResearchAtlas,
    product_started_at: str,
    checkpoint_reason: str,
) -> None:
    """Preserve completed cases without opening or naming the scoring fixture."""

    _persist_provider_checkpoint(
        recorder,
        budget,
        checkpoint_reason=checkpoint_reason,
    )
    value = {
        "schema_version": f"{ARTIFACT_SCHEMA_PREFIX}-product-capture-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "product_started_at": product_started_at,
        "checkpoint_at": _now(),
        "checkpoint_reason": checkpoint_reason,
        "complete": False,
        "public_input": {
            "path": str(PUBLIC_INPUT.relative_to(ROOT)),
            "sha256": _sha(PUBLIC_INPUT),
        },
        "runtime_atlas": {
            **atlas.to_inventory_dict(),
            "current_article_roots": EXPECTED_CURRENT_ARTICLE_ROOTS,
        },
        "provider_capture": {
            "path": str(PROVIDER_CAPTURE_OUTPUT.relative_to(ROOT)),
            "sha256": _sha(PROVIDER_CAPTURE_OUTPUT),
            "bytes": PROVIDER_CAPTURE_OUTPUT.stat().st_size,
        },
        "call_budget": budget.to_dict(),
        "provider_usage": _provider_usage(recorder.receipts),
        "gold_visible_to_product": False,
        "scoring_fixture_opened": False,
        "completed_case_count": len(product_cases),
        "cases": list(product_cases),
    }
    _write(PRODUCT_CAPTURE_OUTPUT, value)
    checkpoint = {
        "schema_version": f"{ARTIFACT_SCHEMA_PREFIX}-run-checkpoint-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "checkpoint_at": _now(),
        "phase": "PRODUCT_IN_PROGRESS",
        "checkpoint_reason": checkpoint_reason,
        "scoring_fixture_opened": False,
        "completed_case_ids": [str(case["case_id"]) for case in product_cases],
        "budget": budget.to_dict(),
        "provider_capture_sha256": _sha(PROVIDER_CAPTURE_OUTPUT),
        "product_capture_sha256": _sha(PRODUCT_CAPTURE_OUTPUT),
    }
    checkpoint["artifact_sha256"] = _value_sha(checkpoint)
    _write(RUN_OUTPUT, checkpoint)


def _find_page_id(value: object) -> str | None:
    if isinstance(value, Mapping):
        direct = value.get("page_id")
        if isinstance(direct, str) and direct:
            return direct
        for item in value.values():
            found = _find_page_id(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_page_id(item)
            if found:
                return found
    return None


def _receipt_page_id(receipt: Mapping[str, Any]) -> str | None:
    found = _find_page_id(receipt.get("structured_output"))
    if found:
        return found
    request = receipt.get("request") or {}
    raw_user = request.get("user")
    if isinstance(raw_user, str):
        try:
            return _find_page_id(json.loads(raw_user))
        except json.JSONDecodeError:
            return None
    return _find_page_id(raw_user)


def _annotate_receipts(
    receipts: Sequence[Mapping[str, Any]],
    *,
    case_id: str,
    stage: str,
    pages: Sequence[object] = (),
    cursor_before: object = None,
    cursor_after: object = None,
    applied: bool,
    wave_error: str = "",
) -> list[dict[str, Any]]:
    by_page = {str(getattr(page, "page_id", "")): page for page in pages}
    before_sha = _value_sha(cursor_before) if cursor_before is not None else None
    after_sha = _value_sha(cursor_after) if cursor_after is not None else None
    output: list[dict[str, Any]] = []
    for raw in receipts:
        row = dict(raw)
        page_id = _receipt_page_id(row)
        page = by_page.get(str(page_id or ""))
        request = row.get("request") or {}
        schema = request.get("schema") or {}
        offered_ids: list[str] = []
        if page is not None:
            for item in getattr(page, "items", ()):
                offered_ids.append(
                    str(getattr(item, "menu_id", getattr(item, "id", "")))
                )
        row.update(
            {
                "run_id": RUN_ID,
                "case_id": case_id,
                "stage": stage,
                "branch_id": str(getattr(page, "branch_id", "")),
                "wave": int(getattr(page, "wave", 0) or 0),
                "page_id": page_id,
                "attempt": 1,
                "request_sha256": _value_sha(request),
                "page_sha256": (
                    _value_sha(page.to_dict())
                    if page is not None and hasattr(page, "to_dict")
                    else None
                ),
                "schema_sha256": _value_sha(schema),
                "offered_ids": offered_ids,
                "cursor_before_sha256": before_sha,
                "cursor_after_sha256": after_sha if applied else None,
                "validation": {
                    "structured_mapping": isinstance(
                        row.get("structured_output"), Mapping
                    ),
                    "closed_menu_and_schema": not bool(wave_error),
                    "applied": applied,
                },
                "wave_error": wave_error,
            }
        )
        output.append(row)
    return output


_COVERAGE_BY_AXIS: dict[str, tuple[str, ...]] = {
    "FORMULA": ("GOVERNING_RULE", "THRESHOLD", "CONDITION"),
    "THRESHOLD": ("GOVERNING_RULE", "THRESHOLD", "CONDITION"),
    "TEMPORAL": ("GOVERNING_RULE", "CONDITION", "EXCEPTION"),
    "FILING_DOCUMENT": ("GOVERNING_RULE", "PROCEDURE", "CONDITION"),
    "AUTHORITY": (
        "GOVERNING_RULE",
        "DEFINITION",
        "ACTOR_SCOPE",
        "AUTHORITY",
        "PROCEDURE",
    ),
    "LEGAL_BASIS": (
        "GOVERNING_RULE",
        "DEFINITION",
        "INCORPORATION_SOURCE",
        "INCORPORATED_TARGET",
    ),
    "CLASSIFICATION": (
        "GOVERNING_RULE",
        "DEFINITION",
        "ACTOR_SCOPE",
        "CONDITION",
    ),
    "DELEGATION": (
        "GOVERNING_RULE",
        "DELEGATION_SOURCE",
        "DELEGATION_TARGET",
        "CONDITION",
        "EXCEPTION",
    ),
    "EXCEPTION": ("GOVERNING_RULE", "CONDITION", "EXCEPTION"),
    "ENTRUSTMENT": (
        "GOVERNING_RULE",
        "DEFINITION",
        "ACTOR_SCOPE",
        "ACTION_SCOPE",
        "PROCEDURE",
        "DELEGATION_SOURCE",
        "INCORPORATION_SOURCE",
        "INCORPORATED_TARGET",
        "EXCEPTION",
    ),
    "NEGATIVE_AUTHORITY": (
        "GOVERNING_RULE",
        "ACTOR_SCOPE",
        "AUTHORITY",
        "CONDITION",
        "EXCEPTION",
    ),
    "GENERAL_LEGAL_RESEARCH": ("GOVERNING_RULE", "DEFINITION"),
}

_COVERAGE_MARKERS: dict[str, tuple[str, ...]] = {
    "DEFINITION": ("정의", "뜻은", "이란"),
    "ACTOR_SCOPE": ("금융회사", "금융투자업자", "신용정보", "개인정보처리자", "자는"),
    "ACTION_SCOPE": ("업무", "위탁", "처리", "행위"),
    "CONDITION": ("경우", "때에는", "요건", "한하여", "조건"),
    "THRESHOLD": ("분의", "%", "이상", "이하", "초과", "미만"),
    "AUTHORITY": ("권한", "이사회", "승인", "의결", "금융위원회"),
    "EXCEPTION": ("다만", "제외", "예외", "불구하고", "아니한다"),
    "PROCEDURE": ("보고", "문서", "계약", "공개", "절차", "통지"),
    "DELEGATION_SOURCE": ("위임", "위탁", "재위탁"),
    "DELEGATION_TARGET": ("수임", "수탁", "위탁받", "재위탁"),
    "INCORPORATION_SOURCE": ("준용", "따른다", "적용한다", "예에 따른"),
    "INCORPORATED_TARGET": ("준용", "따른다", "적용한다", "예에 따른"),
}


def _coverage_for_axis(issue_axis: str) -> tuple[str, ...]:
    return _COVERAGE_BY_AXIS.get(
        str(issue_axis).upper(),
        _COVERAGE_BY_AXIS["GENERAL_LEGAL_RESEARCH"],
    )


class CurrentFullTextCoverageVerifier:
    """Verify only current, non-empty source text and coarse text markers.

    This verifier deliberately does not claim that a rule governs.  It proves
    only that a selected current article contains source language supporting
    one or more gold-free research archetypes.  The stricter legal assessment
    remains outside ADR-0108.
    """

    def __init__(self, atlas: LegalResearchAtlas) -> None:
        self.atlas = atlas
        self.receipts: list[dict[str, Any]] = []

    def _text(self, instrument_id: str, node_id: object) -> str:
        index = self.atlas.current_index
        view = index.entry_docs.get(str(instrument_id))
        node = view.by_id.get(node_id) if view is not None else None
        if view is None or node is None:
            return ""
        return str(view.section_text(dict(node), cap=10**9) or "")

    def verify(
        self,
        branch: BranchPlan,
        item: object,
        claimed_keys: tuple[str, ...],
    ) -> CoverageVerification:
        instrument_id = str(getattr(item, "instrument_id", ""))
        node_id = getattr(item, "node_id", None)
        text = self._text(instrument_id, node_id)
        verified: list[str] = []
        if text.strip():
            for key in claimed_keys:
                markers = _COVERAGE_MARKERS.get(key)
                if key == "GOVERNING_RULE" or (
                    markers and any(marker in text for marker in markers)
                ):
                    verified.append(key)
        text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
        evidence_ids = (
            (f"current-fulltext:{instrument_id}:{node_id}:{text_sha}",)
            if verified
            else ()
        )
        receipt = {
            "branch_id": branch.branch_id,
            "instrument_id": instrument_id,
            "node_id": node_id,
            "text_length": len(text),
            "text_sha256": text_sha or None,
            "requested_keys": list(claimed_keys),
            "verified_keys": verified,
            "current_instrument": self.atlas.instrument(instrument_id) is not None,
        }
        self.receipts.append(receipt)
        return CoverageVerification(
            verified_keys=tuple(verified),
            evidence_ids=evidence_ids,
            verifier=f"{ARTIFACT_SCHEMA_PREFIX}-current-fulltext-coarse-marker-v1",
        )


def _baseline_capture(
    case_id: str,
    current_coordinates: Sequence[tuple[str, int]],
) -> dict[str, Any]:
    recorder = ledger.StageLedgerRecorder(
        case_id,
        "baseline",
        ledger.identity_canonicalizer,
    )
    recorder.record_stage(
        "corpus-source",
        "source",
        current_coordinates,
        after_occurrence_count=len(current_coordinates),
    )
    recorder.record_stage(
        "exhaustive-present",
        "present",
        current_coordinates,
        parent_stage_ids=("corpus-source",),
        after_occurrence_count=len(current_coordinates),
    )
    return recorder.capture()


def _candidate_capture(
    case_id: str,
    current_coordinates: Sequence[tuple[str, int]],
    instrument_route_occurrences: Sequence[tuple[str, int]],
    hierarchy_observed_occurrences: Sequence[tuple[str, int]],
    selected_occurrences: Sequence[tuple[str, int]],
    verified_occurrences: Sequence[tuple[str, int]],
    instrument_prior_occurrences: Sequence[tuple[str, int]] | None = None,
    protected_entry_occurrences: Sequence[tuple[str, int]] | None = None,
) -> dict[str, Any]:
    source = list(current_coordinates)
    instrument_route = _unique_coordinates(instrument_route_occurrences)
    hierarchy_observed = _unique_coordinates(hierarchy_observed_occurrences)
    selected = _unique_coordinates(selected_occurrences)
    protected = _unique_coordinates(protected_entry_occurrences or ())
    verified = _unique_coordinates(verified_occurrences)
    source_set = set(source)
    if not set(instrument_route) <= source_set:
        raise ValueError("instrument route escaped the current article corpus")
    if not set(hierarchy_observed) <= set(instrument_route):
        raise ValueError("observed hierarchy escaped selected instruments")
    if not set(selected) <= set(hierarchy_observed):
        raise ValueError("LLM selected an article it was not shown")
    if not set(protected) <= set(hierarchy_observed):
        raise ValueError("protected entry was not observed by semantic retrieval")
    candidate_pool = _unique_coordinates((*selected, *protected))
    if not set(verified) <= set(candidate_pool):
        raise ValueError("verifier returned an article outside the candidate union")

    recorder = ledger.StageLedgerRecorder(
        case_id,
        CANDIDATE_ARM_ID,
        ledger.identity_canonicalizer,
    )
    recorder.record_stage(
        "corpus-source",
        "source",
        source,
        after_occurrence_count=len(source),
    )
    route_parent = "corpus-source"
    route_before = source
    if INCLUDE_INSTRUMENT_PRIOR_STAGE:
        # A rerank changes order, not membership.  The bounded top-law menu is
        # captured separately in legal_system_entry_plan and law-route ledger.
        prior = source
        recorder.record_stage(
            "instrument-prior",
            "rerank",
            prior,
            parent_stage_ids=("corpus-source",),
            after_occurrence_count=len(source),
        )
        route_parent = "instrument-prior"
        route_before = prior
    recorder.record_stage(
        "instrument-route",
        "filter",
        instrument_route,
        parent_stage_ids=(route_parent,),
        discard_reasons=_discard_reasons(
            route_before,
            instrument_route,
            "instrument_not_selected_by_question_only_router",
        ),
        after_occurrence_count=len(instrument_route_occurrences),
    )
    recorder.record_stage(
        OBSERVED_STAGE_ID,
        "rerank" if OBSERVED_STAGE_ID == "semantic-entry-observed" else "filter",
        hierarchy_observed,
        parent_stage_ids=("instrument-route",),
        discard_reasons=_discard_reasons(
            instrument_route,
            hierarchy_observed,
            "article_not_observed_in_selected_instrument_frontier",
        ),
        after_occurrence_count=len(hierarchy_observed_occurrences),
    )
    recorder.record_stage(
        "llm-selected",
        "select",
        selected,
        parent_stage_ids=(OBSERVED_STAGE_ID,),
        discard_reasons=_discard_reasons(
            hierarchy_observed,
            selected,
            "article_observed_but_not_selected_by_llm",
        ),
        after_occurrence_count=len(selected_occurrences),
    )
    verify_parent = "llm-selected"
    if INCLUDE_PROTECTED_ENTRY_STAGE:
        recorder.record_stage(
            "protected-entry-preserved",
            "select",
            protected,
            parent_stage_ids=(OBSERVED_STAGE_ID,),
            discard_reasons=_discard_reasons(
                hierarchy_observed,
                protected,
                "semantic_entry_outside_protected_preservation_window",
            ),
            after_occurrence_count=len(protected_entry_occurrences or ()),
        )
        recorder.record_stage(
            "candidate-union",
            "union",
            candidate_pool,
            parent_stage_ids=("llm-selected", "protected-entry-preserved"),
            after_occurrence_count=len(candidate_pool),
        )
        verify_parent = "candidate-union"
    recorder.record_stage(
        VERIFY_STAGE_ID,
        "filter",
        verified,
        parent_stage_ids=(verify_parent,),
        discard_reasons=_discard_reasons(
            candidate_pool,
            verified,
            "selected_article_failed_fulltext_current_verification",
        ),
        after_occurrence_count=len(verified_occurrences),
    )
    recorder.record_stage(
        "candidate-present",
        "present",
        verified,
        parent_stage_ids=(VERIFY_STAGE_ID,),
        after_occurrence_count=len(verified_occurrences),
    )
    return recorder.capture()


def _articles_for_routes(
    atlas: LegalResearchAtlas,
    route_ids_by_branch: Mapping[str, Sequence[str]],
) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for instrument_ids in route_ids_by_branch.values():
        for instrument_id in instrument_ids:
            for unit in atlas.article_units(str(instrument_id)):
                rows.append(_parse_coordinate((str(instrument_id), unit.node_id)))
    return rows


def _selected_coordinates_from_session(session: object) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for branch in getattr(session, "branches", {}).values():
        for evidence in branch.selected_evidence.values():
            rows.append(_parse_coordinate((
                str(evidence["instrument_id"]),
                evidence["node_id"],
            )))
    return rows


def _fulltext_verified_coordinates(
    atlas: LegalResearchAtlas,
    selected: Sequence[tuple[str, int]],
) -> tuple[list[tuple[str, int]], list[dict[str, Any]]]:
    verified: list[tuple[str, int]] = []
    receipts: list[dict[str, Any]] = []
    for document_id, node_id in selected:
        view = atlas.current_index.entry_docs.get(document_id)
        node = view.by_id.get(node_id) if view is not None else None
        text = str(view.section_text(dict(node), cap=10**9) or "") if node else ""
        accepted = bool(
            atlas.instrument(document_id) is not None
            and node is not None
            and text.strip()
        )
        if accepted:
            verified.append((document_id, node_id))
        receipts.append({
            "coordinate": f"{document_id}:{node_id}",
            "current": atlas.instrument(document_id) is not None,
            "article_exists": node is not None,
            "text_length": len(text),
            "text_sha256": (
                hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None
            ),
            "verified": accepted,
        })
    return _unique_coordinates(verified), receipts


@dataclass
class _InstrumentRouteRuntime:
    planner: InstrumentRoutingPlanner
    session: InstrumentRoutingSession


def _run_instrument_router(
    *,
    case_id: str,
    question: str,
    atlas: LegalResearchAtlas,
    query_branches: Sequence[InstrumentRouteBranch],
    recorder: ThreadLocalStructuredRecorder,
    budget: CallBudget,
    run_started: float,
    runtime: _InstrumentRouteRuntime | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], _InstrumentRouteRuntime]:
    if runtime is None:
        planner = InstrumentRoutingPlanner(atlas, (), page_size=PAGE_SIZE)
        session = planner.start(question, query_branches)
        runtime = _InstrumentRouteRuntime(planner=planner, session=session)
    else:
        planner = runtime.planner
        session = runtime.session
        if session.question != question:
            raise ValueError("instrument route runtime belongs to another question")
        if tuple(session.branches) != tuple(branch.branch_id for branch in query_branches):
            raise ValueError("instrument route runtime branch set drifted")
    selector = HaikuInstrumentRouteSelector(recorder)
    waves: list[dict[str, Any]] = []
    exposed_occurrences: list[dict[str, str]] = []
    receipts: list[dict[str, Any]] = []
    effective_status = session.status.value
    stop_reason = ""

    while session.status is RouteSessionStatus.ACTIVE:
        if session.wave_count >= MAX_LAW_WAVES:
            effective_status = ResearchStatus.INCOMPLETE_WITH_CURSOR.value
            stop_reason = "LAW_WAVE_BUDGET_EXHAUSTED_WITH_CURSOR"
            break
        if _case_wall_budget_exhausted(case_id, run_started):
            effective_status = ResearchStatus.INCOMPLETE_WITH_CURSOR.value
            stop_reason = "WALL_BUDGET_EXHAUSTED_WITH_CURSOR"
            break
        pages = planner.next_wave(session)
        if not pages:
            effective_status = session.status.value
            break
        if any(len(page.items) > PAGE_SIZE for page in pages):
            raise AssertionError("instrument page exceeded page_size")
        if not budget.reserve(case_id, len(pages)):
            effective_status = ResearchStatus.INCOMPLETE_WITH_CURSOR.value
            stop_reason = "CALL_BUDGET_EXHAUSTED_WITH_CURSOR"
            waves.append({
                "wave": pages[0].wave,
                "pages": [page.to_dict() for page in pages],
                "decisions": [],
                "applied": False,
                "error": stop_reason,
            })
            break

        for page in pages:
            for item in page.items:
                exposed_occurrences.append({
                    "branch_id": page.branch_id,
                    "instrument_id": item.instrument_id,
                    "page_id": page.page_id,
                })
        cursor_before = session.cursor_snapshot()
        audit_before = len(recorder.receipts)
        decisions = ()
        error = ""
        applied = False
        try:
            decisions = select_route_wave_parallel(
                question,
                pages,
                selector,
                max_workers=MAX_PARALLEL_WORKERS,
            )
            planner.apply_wave(session, decisions)
            applied = True
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:4000]
            effective_status = ResearchStatus.INCOMPLETE_WITH_CURSOR.value
            stop_reason = "PROVIDER_OR_VALIDATION_FAILURE_WITH_CURSOR"
        cursor_after = session.cursor_snapshot() if applied else None
        new_receipts = list(recorder.receipts[audit_before:])
        receipts.extend(_annotate_receipts(
            new_receipts,
            case_id=case_id,
            stage="INSTRUMENT_ROUTE",
            pages=pages,
            cursor_before=cursor_before,
            cursor_after=cursor_after,
            applied=applied,
            wave_error=error,
        ))
        waves.append({
            "wave": pages[0].wave,
            "pages": [page.to_dict() for page in pages],
            "decisions": [decision.to_dict() for decision in decisions],
            "applied": applied,
            "error": error,
            "cursor_before_sha256": _value_sha(cursor_before),
            "cursor_after_sha256": (
                _value_sha(cursor_after) if cursor_after is not None else None
            ),
        })
        _persist_provider_checkpoint(
            recorder,
            budget,
            checkpoint_reason=(
                f"{case_id}:INSTRUMENT_ROUTE:WAVE:{pages[0].wave}:"
                f"{'APPLIED' if applied else 'UNAPPLIED'}"
            ),
        )
        if not applied:
            break
        if _case_token_budget_exhausted(recorder, case_id):
            effective_status = ResearchStatus.INCOMPLETE_WITH_CURSOR.value
            stop_reason = "TOKEN_BUDGET_EXHAUSTED_WITH_CURSOR"
            break
        # Return after one law wave.  The outer coordinator may immediately
        # probe newly ROUTE_READY branches while sibling branches keep their
        # ACTIVE cursors for the next cycle.
        break

    ordered_routes = {
        branch_id: list(values)
        for branch_id, values in session.ordered_routes.items()
    }
    selected_occurrences = [
        {"branch_id": branch_id, "instrument_id": instrument_id}
        for branch_id, values in ordered_routes.items()
        for instrument_id in values
    ]
    if not stop_reason:
        effective_status = session.status.value
    return ({
        "status": session.status.value,
        "effective_status": effective_status,
        "stop_reason": stop_reason,
        "page_size": PAGE_SIZE,
        "wave_count": session.wave_count,
        "query_branch_count": len(query_branches),
        "query_branches": [branch.to_dict() for branch in query_branches],
        "exposed_instrument_occurrences": exposed_occurrences,
        "selected_instrument_occurrences": selected_occurrences,
        "ordered_routes": ordered_routes,
        "cursor_snapshot": session.cursor_snapshot(),
        "in_flight_pages": [
            page.to_dict() for page in session.in_flight_pages.values()
        ],
        "waves": waves,
    }, receipts, runtime)


def _research_branch_plans(
    query_branches: Sequence[InstrumentRouteBranch],
    ordered_routes: Mapping[str, Sequence[str]],
    required_coverage_by_branch: Mapping[str, Sequence[str]] | None = None,
    entry_point_ids_by_branch: Mapping[
        str, Mapping[str, Sequence[str]]
    ] | None = None,
) -> tuple[BranchPlan, ...]:
    by_id = {branch.branch_id: branch for branch in query_branches}
    plans: list[BranchPlan] = []
    for branch_id, instrument_ids in ordered_routes.items():
        route = tuple(dict.fromkeys(str(value) for value in instrument_ids))
        if not route:
            continue
        source = by_id[branch_id]
        coverage_source = (
            required_coverage_by_branch.get(branch_id, ())
            if required_coverage_by_branch is not None
            else _coverage_for_axis(source.issue_axis)
        )
        required_coverage = tuple(str(value) for value in coverage_source)
        if not required_coverage:
            continue
        plans.append(BranchPlan(
            branch_id=branch_id,
            issue_axis=source.issue_axis,
            instrument_role="QUESTION_ONLY_HAIKU_ORDERED_ROUTE",
            instrument_ids=route,
            required_coverage=required_coverage,
            entry_point_ids_by_instrument={
                instrument_id: tuple(str(value) for value in values)
                for instrument_id, values in (
                    entry_point_ids_by_branch.get(branch_id, {})
                    if entry_point_ids_by_branch is not None else {}
                ).items()
                if instrument_id in route
            },
            exhaustion_policy=ExhaustionPolicy.TARGETED_ROUTE,
        ))
    return tuple(plans)


def _run_research_controller(
    *,
    case_id: str,
    question: str,
    atlas: LegalResearchAtlas,
    query_plan: Mapping[str, Any],
    branch_plans: Sequence[BranchPlan],
    recorder: ThreadLocalStructuredRecorder,
    budget: CallBudget,
    run_started: float,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[tuple[str, int]]]:
    if not branch_plans:
        return ({
            "status": ResearchStatus.INCOMPLETE_WITH_CURSOR.value,
            "effective_status": ResearchStatus.INCOMPLETE_WITH_CURSOR.value,
            "stop_reason": "NO_SELECTED_INSTRUMENT_ROUTE_WITH_CURSOR",
            "page_size": PAGE_SIZE,
            "wave_count": 0,
            "observed_article_occurrences": [],
            "selected_coordinates": [],
            "fulltext_coverage_receipts": [],
            "session": None,
            "waves": [],
        }, [], [])

    coverage_verifier = CurrentFullTextCoverageVerifier(atlas)
    controller = LegalResearchController(
        atlas,
        coverage_verifier=coverage_verifier,
    )
    plan = ResearchPlan(
        question=question,
        branches=tuple(branch_plans),
        page_size=PAGE_SIZE,
        max_page_waves=MAX_ARTICLE_WAVES,
        requested_effect="RETRIEVAL_ONLY_NO_LEGAL_CONCLUSION",
    )
    session = controller.create_session(plan)
    selector = HaikuArticlePageSelector(
        recorder,
        query_plan,
        AtlasArticleTextResolver(atlas),
    )
    waves: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    observed: list[tuple[str, int]] = []
    effective_status = session.status.value
    stop_reason = ""

    while session.status in {
        ResearchStatus.ACTIVE,
        ResearchStatus.INCOMPLETE_WITH_CURSOR,
    }:
        if session.status is ResearchStatus.INCOMPLETE_WITH_CURSOR:
            effective_status = session.status.value
            stop_reason = "ARTICLE_WAVE_BUDGET_EXHAUSTED_WITH_CURSOR"
            break
        if _case_wall_budget_exhausted(case_id, run_started):
            effective_status = ResearchStatus.INCOMPLETE_WITH_CURSOR.value
            stop_reason = "WALL_BUDGET_EXHAUSTED_WITH_CURSOR"
            break
        pages = controller.next_wave(session)
        if not pages:
            effective_status = session.status.value
            break
        if any(len(page.items) > PAGE_SIZE for page in pages):
            raise AssertionError("article page exceeded page_size")
        if not budget.reserve(case_id, len(pages)):
            effective_status = ResearchStatus.INCOMPLETE_WITH_CURSOR.value
            stop_reason = "CALL_BUDGET_EXHAUSTED_WITH_CURSOR"
            waves.append({
                "wave": pages[0].wave,
                "pages": [page.to_dict() for page in pages],
                "decisions": [],
                "applied": False,
                "error": stop_reason,
            })
            break

        for page in pages:
            for item in page.items:
                kind = str(getattr(getattr(item, "kind", ""), "value", getattr(item, "kind", "")))
                if kind.upper() == NavigationKind.ARTICLE.value:
                    observed.append(_parse_coordinate((
                        str(item.instrument_id),
                        item.node_id,
                    )))
        cursor_before = session.to_dict(include_trace=False)
        audit_before = len(recorder.receipts)
        decisions: Sequence[PageDecision] = ()
        error = ""
        applied = False
        try:
            decisions = select_wave_parallel(
                question,
                pages,
                selector,
                max_workers=MAX_PARALLEL_WORKERS,
            )
            controller.apply_wave(session, decisions)
            applied = True
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:4000]
            effective_status = ResearchStatus.INCOMPLETE_WITH_CURSOR.value
            stop_reason = "PROVIDER_OR_VALIDATION_FAILURE_WITH_CURSOR"
        cursor_after = session.to_dict(include_trace=False) if applied else None
        new_receipts = list(recorder.receipts[audit_before:])
        receipts.extend(_annotate_receipts(
            new_receipts,
            case_id=case_id,
            stage="ARTICLE_ROUTE",
            pages=pages,
            cursor_before=cursor_before,
            cursor_after=cursor_after,
            applied=applied,
            wave_error=error,
        ))
        waves.append({
            "wave": pages[0].wave,
            "pages": [page.to_dict() for page in pages],
            "decisions": [decision.to_dict() for decision in decisions],
            "applied": applied,
            "error": error,
            "cursor_before_sha256": _value_sha(cursor_before),
            "cursor_after_sha256": (
                _value_sha(cursor_after) if cursor_after is not None else None
            ),
        })
        _persist_provider_checkpoint(
            recorder,
            budget,
            checkpoint_reason=(
                f"{case_id}:ARTICLE_ROUTE:WAVE:{pages[0].wave}:"
                f"{'APPLIED' if applied else 'UNAPPLIED'}"
            ),
        )
        if not applied:
            break
        if _case_token_budget_exhausted(recorder, case_id):
            effective_status = ResearchStatus.INCOMPLETE_WITH_CURSOR.value
            stop_reason = "TOKEN_BUDGET_EXHAUSTED_WITH_CURSOR"
            break

    selected = _selected_coordinates_from_session(session)
    if not stop_reason:
        effective_status = session.status.value
    return ({
        "status": session.status.value,
        "effective_status": effective_status,
        "stop_reason": stop_reason,
        "page_size": PAGE_SIZE,
        "wave_count": session.wave_count,
        "observed_article_occurrences": [
            _coordinate_text(value) for value in observed
        ],
        "selected_coordinates": [
            _coordinate_text(value) for value in selected
        ],
        "fulltext_coverage_receipts": coverage_verifier.receipts,
        "session": session.to_dict(include_trace=True),
        "waves": waves,
    }, receipts, observed)


def _merge_law_route_segments(
    segments: Sequence[Mapping[str, Any]],
    runtime: _InstrumentRouteRuntime | None,
    query_branches: Sequence[InstrumentRouteBranch],
    resume_events: Sequence[Mapping[str, Any]],
    probe_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if runtime is None:
        return {
            "status": ResearchStatus.INCOMPLETE_WITH_CURSOR.value,
            "effective_status": ResearchStatus.INCOMPLETE_WITH_CURSOR.value,
            "stop_reason": "NO_INSTRUMENT_RUNTIME_WITH_CURSOR",
            "page_size": PAGE_SIZE,
            "wave_count": 0,
            "query_branch_count": len(query_branches),
            "query_branches": [branch.to_dict() for branch in query_branches],
            "exposed_instrument_occurrences": [],
            "selected_instrument_occurrences": [],
            "ordered_routes": {},
            "cursor_snapshot": None,
            "in_flight_pages": [],
            "waves": [],
            "segments": [],
            "resume_events": list(resume_events),
            "probe_events": list(probe_events),
        }
    session = runtime.session
    ordered_routes = {
        branch_id: list(values)
        for branch_id, values in session.ordered_routes.items()
    }
    last = dict(segments[-1]) if segments else {}
    stop_reason = str(last.get("stop_reason") or "")
    effective_status = str(last.get("effective_status") or session.status.value)
    return {
        "status": session.status.value,
        "effective_status": effective_status,
        "stop_reason": stop_reason,
        "page_size": PAGE_SIZE,
        "wave_count": session.wave_count,
        "query_branch_count": len(query_branches),
        "query_branches": [branch.to_dict() for branch in query_branches],
        "exposed_instrument_occurrences": [
            row
            for segment in segments
            for row in segment.get("exposed_instrument_occurrences") or ()
        ],
        "selected_instrument_occurrences": [
            {"branch_id": branch_id, "instrument_id": instrument_id}
            for branch_id, values in ordered_routes.items()
            for instrument_id in values
        ],
        "ordered_routes": ordered_routes,
        "cursor_snapshot": session.cursor_snapshot(),
        "in_flight_pages": [
            page.to_dict() for page in session.in_flight_pages.values()
        ],
        "waves": [
            row
            for segment in segments
            for row in segment.get("waves") or ()
        ],
        "segments": [dict(segment) for segment in segments],
        "resume_events": [dict(row) for row in resume_events],
        "probe_events": [dict(row) for row in probe_events],
    }


def _merge_research_cycles(
    cycles: Sequence[Mapping[str, Any]],
    *,
    query_branches: Sequence[InstrumentRouteBranch],
    satisfied_branch_ids: set[str],
    verified_coverage_by_branch: Mapping[str, set[str]],
    stop_reason: str,
) -> dict[str, Any]:
    observed = list(dict.fromkeys(
        str(value)
        for cycle in cycles
        for value in cycle.get("observed_article_occurrences") or ()
    ))
    selected = list(dict.fromkeys(
        str(value)
        for cycle in cycles
        for value in cycle.get("selected_coordinates") or ()
    ))
    latest_branches: dict[str, dict[str, Any]] = {}
    trace: list[dict[str, Any]] = []
    waves: list[dict[str, Any]] = []
    coverage_receipts: list[dict[str, Any]] = []
    for cycle_index, cycle in enumerate(cycles, 1):
        session = cycle.get("session") or {}
        for branch in session.get("branches") or ():
            latest_branches[str(branch.get("branch_id") or "")] = dict(branch)
        for event in session.get("trace") or ():
            row = dict(event)
            row["probe_cycle"] = cycle_index
            row["sequence"] = len(trace) + 1
            trace.append(row)
        for wave in cycle.get("waves") or ():
            row = dict(wave)
            row["probe_cycle"] = cycle_index
            waves.append(row)
        coverage_receipts.extend(
            dict(row) for row in cycle.get("fulltext_coverage_receipts") or ()
        )

    required_ids = {branch.branch_id for branch in query_branches}
    if required_ids and required_ids <= satisfied_branch_ids:
        status = ResearchStatus.READY_FOR_ASSESSMENT.value
        effective_status = status
        aggregate_stop_reason = ""
    elif any(
        marker in stop_reason
        for marker in ("BUDGET", "PROVIDER", "TOKEN", "WALL", "CYCLE")
    ):
        status = ResearchStatus.INCOMPLETE_WITH_CURSOR.value
        effective_status = status
        aggregate_stop_reason = stop_reason
    else:
        status = ResearchStatus.BLOCKED_MISSING_COVERAGE.value
        effective_status = status
        aggregate_stop_reason = stop_reason or "NO_RESUMABLE_LAW_CURSOR"
    return {
        "status": status,
        "effective_status": effective_status,
        "stop_reason": aggregate_stop_reason,
        "page_size": PAGE_SIZE,
        "wave_count": sum(int(cycle.get("wave_count") or 0) for cycle in cycles),
        "observed_article_occurrences": observed,
        "selected_coordinates": selected,
        "fulltext_coverage_receipts": coverage_receipts,
        "satisfied_branch_ids": sorted(satisfied_branch_ids),
        "missing_branch_ids": sorted(required_ids - satisfied_branch_ids),
        "verified_coverage_by_branch": {
            branch_id: sorted(values)
            for branch_id, values in verified_coverage_by_branch.items()
        },
        "session": {
            "status": status,
            "branches": list(latest_branches.values()),
            "trace": trace,
        },
        "waves": waves,
        "cycles": [dict(cycle) for cycle in cycles],
    }


def _resume_unsatisfied_route_branches(
    runtime: _InstrumentRouteRuntime,
    branch_ids: Sequence[str],
    *,
    probe_cycle: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    resumed: list[str] = []
    events: list[dict[str, Any]] = []
    for branch_id in branch_ids:
        branch = runtime.session.branches.get(branch_id)
        if (
            branch is None
            or branch.status is not RouteBranchStatus.ROUTE_READY
            or branch.next_cursor is None
        ):
            continue
        before = branch.next_cursor.to_dict()
        cursor = runtime.planner.resume_branch(runtime.session, branch_id)
        resumed.append(branch_id)
        events.append({
            "event": "LAW_CURSOR_RESUMED",
            "probe_cycle": probe_cycle,
            "branch_id": branch_id,
            "cursor_before": before,
            "cursor_after": cursor.to_dict(),
        })
    return resumed, events


def _article_probe_outcomes(
    cycle_result: Mapping[str, Any],
    branch_ids: Sequence[str],
    satisfied_branch_ids: set[str],
) -> dict[str, str]:
    """Classify probes without converting an incomplete read into a no-hit."""

    session = cycle_result.get("session") or {}
    statuses = {
        str(row.get("branch_id") or ""): str(row.get("status") or "")
        for row in session.get("branches") or ()
    }
    stop_reason = str(cycle_result.get("stop_reason") or "")
    incomplete_cycle = bool(stop_reason) or str(cycle_result.get("status") or "") == (
        ResearchStatus.INCOMPLETE_WITH_CURSOR.value
    )
    outcomes: dict[str, str] = {}
    for branch_id in branch_ids:
        if branch_id in satisfied_branch_ids or statuses.get(branch_id) == (
            BranchStatus.SATISFIED.value
        ):
            outcomes[branch_id] = "SATISFIED"
        elif (
            not incomplete_cycle
            and statuses.get(branch_id) == BranchStatus.EXHAUSTED.value
        ):
            outcomes[branch_id] = "UNSATISFIED"
        else:
            outcomes[branch_id] = "INCOMPLETE"
    return outcomes


def _run_product_case(
    *,
    public_case: Mapping[str, str],
    atlas: LegalResearchAtlas,
    current_coordinates: Sequence[tuple[str, int]],
    recorder: ThreadLocalStructuredRecorder,
    budget: CallBudget,
    run_started: float,
) -> dict[str, Any]:
    case_started = time.perf_counter()
    case_id = public_case["case_id"]
    question = public_case["question"]
    _CASE_RECEIPT_OFFSETS[case_id] = len(recorder.receipts)
    _CASE_STARTED_AT[case_id] = case_started
    case_receipts: list[dict[str, Any]] = []
    plan_error = ""
    query_plan: dict[str, Any] = {}
    query_branches: tuple[InstrumentRouteBranch, ...] = ()
    entry_plan_capture: list[dict[str, Any]] = []
    entry_points_by_branch: dict[str, dict[str, tuple[str, ...]]] = {}
    protected_routes_by_branch: dict[str, tuple[str, ...]] = {}

    if not budget.reserve(case_id, 1):
        plan_error = "CALL_BUDGET_EXHAUSTED_WITH_CURSOR"
    else:
        audit_before = len(recorder.receipts)
        try:
            query_plan = plan_question(recorder, question)
            query_branches = branches_from_query_plan(query_plan)
            if not query_branches:
                raise ValueError("question plan produced no research branch")
            if LEGAL_SYSTEM_ENTRY_ENABLED:
                entry_planner = LegalSystemEntryPlanner(
                    atlas,
                    instrument_limit=ENTRY_INSTRUMENT_LIMIT,
                    entry_limit=ENTRY_ARTICLE_LIMIT,
                )
                entry_plans = entry_planner.plan(
                    question, query_plan, query_branches,
                )
                query_branches = apply_instrument_priors(
                    query_branches, entry_plans,
                )
                entry_plan_capture = [plan.to_dict() for plan in entry_plans]
                entry_points_by_branch = {
                    plan.branch_id: plan.entry_point_ids_by_instrument
                    for plan in entry_plans
                }
                protected_routes_by_branch = {
                    plan.branch_id: plan.preferred_instrument_ids[
                        :PROTECTED_PREFERRED_COUNT
                    ]
                    for plan in entry_plans
                }
        except Exception as exc:
            plan_error = f"{type(exc).__name__}: {exc}"[:4000]
        new_receipts = list(recorder.receipts[audit_before:])
        case_receipts.extend(_annotate_receipts(
            new_receipts,
            case_id=case_id,
            stage="QUESTION_PLAN",
            applied=not bool(plan_error),
            wave_error=plan_error,
        ))
        _persist_provider_checkpoint(
            recorder,
            budget,
            checkpoint_reason=f"{case_id}:QUESTION_PLAN",
        )

    route_runtime: _InstrumentRouteRuntime | None = None
    route_segments: list[dict[str, Any]] = []
    research_cycles: list[dict[str, Any]] = []
    resume_events: list[dict[str, Any]] = []
    probe_events: list[dict[str, Any]] = []
    attempted_instruments: dict[str, set[str]] = defaultdict(set)
    routed_instruments: dict[str, list[str]] = defaultdict(list)
    verified_coverage_by_branch: dict[str, set[str]] = defaultdict(set)
    satisfied_branch_ids: set[str] = set()
    clean_unsatisfied_branch_ids: set[str] = set()
    interleave_stop_reason = plan_error or ""

    if query_branches:
        for probe_cycle in range(1, MAX_PROBE_CYCLES + 1):
            segment, route_receipts, route_runtime = _run_instrument_router(
                case_id=case_id,
                question=question,
                atlas=atlas,
                query_branches=query_branches,
                recorder=recorder,
                budget=budget,
                run_started=run_started,
                runtime=route_runtime,
            )
            segment = dict(segment)
            segment["probe_cycle"] = probe_cycle
            for wave in segment.get("waves") or ():
                wave["probe_cycle"] = probe_cycle
            route_segments.append(segment)
            case_receipts.extend(route_receipts)
            if segment.get("stop_reason"):
                interleave_stop_reason = str(segment["stop_reason"])
                break

            ordered_routes = route_runtime.session.ordered_routes
            fresh_routes: dict[str, tuple[str, ...]] = {}
            remaining_coverage: dict[str, tuple[str, ...]] = {}
            for branch in query_branches:
                branch_id = branch.branch_id
                route_branch = route_runtime.session.branches[branch_id]
                if route_branch.status not in {
                    RouteBranchStatus.ROUTE_READY,
                    RouteBranchStatus.EXHAUSTED,
                } and not (
                    route_branch.pages_seen > 0
                    and protected_routes_by_branch.get(branch_id)
                ):
                    continue
                required = _coverage_for_axis(branch.issue_axis)
                remaining = tuple(
                    key for key in required
                    if key not in verified_coverage_by_branch[branch_id]
                )
                if not remaining:
                    satisfied_branch_ids.add(branch_id)
                if branch_id in satisfied_branch_ids:
                    continue
                route_candidates = tuple(dict.fromkeys((
                    *ordered_routes.get(branch_id, ()),
                    *protected_routes_by_branch.get(branch_id, ()),
                )))
                fresh = tuple(
                    instrument_id
                    for instrument_id in route_candidates
                    if instrument_id not in attempted_instruments[branch_id]
                )
                if fresh:
                    fresh_routes[branch_id] = fresh
                    for instrument_id in fresh:
                        if instrument_id not in routed_instruments[branch_id]:
                            routed_instruments[branch_id].append(instrument_id)
                    remaining_coverage[branch_id] = remaining

            if fresh_routes:
                clean_unsatisfied_branch_ids.difference_update(fresh_routes)
                for branch_id, instrument_ids in fresh_routes.items():
                    route_branch = route_runtime.session.branches[branch_id]
                    retained = (
                        route_branch.next_cursor.to_dict()
                        if route_branch.next_cursor is not None else None
                    )
                    probe_events.append({
                        "event": "ARTICLE_PROBE_STARTED",
                        "probe_cycle": probe_cycle,
                        "branch_id": branch_id,
                        "instrument_ids": list(instrument_ids),
                        "law_cursor_retained": retained is not None,
                        "retained_cursor": retained,
                    })
                branch_plans = _research_branch_plans(
                    query_branches,
                    fresh_routes,
                    remaining_coverage,
                    entry_points_by_branch,
                )
                cycle_result, research_receipts, _observed = (
                    _run_research_controller(
                        case_id=case_id,
                        question=question,
                        atlas=atlas,
                        query_plan=query_plan,
                        branch_plans=branch_plans,
                        recorder=recorder,
                        budget=budget,
                        run_started=run_started,
                    )
                )
                cycle_result = dict(cycle_result)
                cycle_result["probe_cycle"] = probe_cycle
                research_cycles.append(cycle_result)
                case_receipts.extend(research_receipts)
                cycle_session = cycle_result.get("session") or {}
                started_by_branch: dict[str, set[str]] = defaultdict(set)
                for trace_event in cycle_session.get("trace") or ():
                    if trace_event.get("event") == "INSTRUMENT_STARTED":
                        started_by_branch[str(trace_event.get("branch_id") or "")].add(
                            str(trace_event.get("instrument_id") or "")
                        )
                for branch_id, values in started_by_branch.items():
                    attempted_instruments[branch_id].update(value for value in values if value)
                for receipt in cycle_result.get("fulltext_coverage_receipts") or ():
                    branch_id = str(receipt.get("branch_id") or "")
                    verified_coverage_by_branch[branch_id].update(
                        str(key) for key in receipt.get("verified_keys") or ()
                    )
                for branch_row in cycle_session.get("branches") or ():
                    branch_id = str(branch_row.get("branch_id") or "")
                    if branch_row.get("status") == "SATISFIED":
                        satisfied_branch_ids.add(branch_id)
                for branch in query_branches:
                    required = set(_coverage_for_axis(branch.issue_axis))
                    if required <= verified_coverage_by_branch[branch.branch_id]:
                        satisfied_branch_ids.add(branch.branch_id)
                outcomes = _article_probe_outcomes(
                    cycle_result,
                    tuple(fresh_routes),
                    satisfied_branch_ids,
                )
                for branch_id, outcome in outcomes.items():
                    probe_events.append({
                        "event": f"ARTICLE_PROBE_{outcome}",
                        "probe_cycle": probe_cycle,
                        "branch_id": branch_id,
                        "instrument_ids": list(fresh_routes[branch_id]),
                        "research_status": cycle_result.get("status"),
                        "stop_reason": cycle_result.get("stop_reason"),
                    })
                    if outcome == "UNSATISFIED":
                        clean_unsatisfied_branch_ids.add(branch_id)
                    else:
                        clean_unsatisfied_branch_ids.discard(branch_id)
                cycle_stop = str(cycle_result.get("stop_reason") or "")
                if any(outcome == "INCOMPLETE" for outcome in outcomes.values()):
                    interleave_stop_reason = (
                        cycle_stop or "ARTICLE_PROBE_INCOMPLETE_WITH_CURSOR"
                    )
                    break

            required_branch_ids = {branch.branch_id for branch in query_branches}
            if required_branch_ids <= satisfied_branch_ids:
                interleave_stop_reason = ""
                break
            unsatisfied = sorted(
                (required_branch_ids - satisfied_branch_ids)
                & clean_unsatisfied_branch_ids
            )
            resumed, events = _resume_unsatisfied_route_branches(
                route_runtime,
                unsatisfied,
                probe_cycle=probe_cycle,
            )
            resume_events.extend(events)
            probe_events.extend(events)
            if resumed:
                continue
            if any(
                branch.status is RouteBranchStatus.ACTIVE
                for branch in route_runtime.session.branches.values()
            ):
                continue
            interleave_stop_reason = "NO_RESUMABLE_LAW_CURSOR"
            break
        else:
            interleave_stop_reason = "PROBE_CYCLE_BUDGET_EXHAUSTED_WITH_CURSOR"

    law_route = _merge_law_route_segments(
        route_segments,
        route_runtime,
        query_branches,
        resume_events,
        probe_events,
    )
    if routed_instruments:
        law_route["ordered_routes"] = {
            branch_id: list(dict.fromkeys((
                *law_route.get("ordered_routes", {}).get(branch_id, ()),
                *routed_instruments.get(branch_id, ()),
            )))
            for branch_id in {
                *law_route.get("ordered_routes", {}), *routed_instruments
            }
        }
        law_route["selected_instrument_occurrences"] = [
            {"branch_id": branch_id, "instrument_id": instrument_id}
            for branch_id, values in law_route["ordered_routes"].items()
            for instrument_id in values
        ]
    if not query_branches:
        law_route["stop_reason"] = plan_error or "NO_QUERY_BRANCH_WITH_CURSOR"
        law_route["effective_status"] = ResearchStatus.INCOMPLETE_WITH_CURSOR.value
    research = _merge_research_cycles(
        research_cycles,
        query_branches=query_branches,
        satisfied_branch_ids=satisfied_branch_ids,
        verified_coverage_by_branch=verified_coverage_by_branch,
        stop_reason=interleave_stop_reason,
    )
    observed_occurrences = [
        _parse_coordinate(value)
        for value in research["observed_article_occurrences"]
    ]

    instrument_route_occurrences = _articles_for_routes(
        atlas,
        law_route["ordered_routes"],
    )
    instrument_prior_occurrences = _articles_for_routes(
        atlas,
        {
            branch.branch_id: branch.preferred_instrument_ids
            for branch in query_branches
        },
    ) if LEGAL_SYSTEM_ENTRY_ENABLED else []
    selected = [
        _parse_coordinate(value) for value in research["selected_coordinates"]
    ]
    protected_entries: list[tuple[str, int]] = []
    if PROTECTED_ENTRY_COUNT_PER_INSTRUMENT > 0:
        routed_ids = {
            str(instrument_id)
            for values in law_route.get("ordered_routes", {}).values()
            for instrument_id in values
        }
        for branch_entry in entry_plan_capture:
            for instrument in branch_entry.get("instruments") or ():
                if str(instrument.get("instrument_id") or "") not in routed_ids:
                    continue
                for point in (
                    instrument.get("entry_points") or ()
                )[:PROTECTED_ENTRY_COUNT_PER_INSTRUMENT]:
                    protected_entries.append(_parse_coordinate((
                        str(point["instrument_id"]), point["node_id"],
                    )))
        protected_entries = _unique_coordinates(protected_entries)
        observed_occurrences = _unique_coordinates((
            *observed_occurrences, *protected_entries,
        ))
    candidate_union = _unique_coordinates((*selected, *protected_entries))
    verified, fulltext_receipts = _fulltext_verified_coordinates(
        atlas, candidate_union,
    )
    semantic_scope_receipts: list[dict[str, Any]] = []
    if SEMANTIC_SCOPE_FILTER_ENABLED:
        semantic_verified: list[tuple[str, int]] = []
        for coordinate in verified:
            document_id, node_id = coordinate
            view = atlas.current_index.entry_docs.get(document_id)
            node = view.by_id.get(node_id) if view is not None else None
            text = str(
                view.section_text(dict(node), cap=10**9) or ""
            ) if node is not None else ""
            alignment = scope_alignment(query_plan, text)
            accepted = not alignment["numeric_only"] and not alignment[
                "wrong_actor_delegation"
            ]
            semantic_scope_receipts.append({
                "coordinate": _coordinate_text(coordinate),
                **alignment,
                "accepted": accepted,
            })
            if accepted:
                semantic_verified.append(coordinate)
        verified = _unique_coordinates(semantic_verified)
    baseline_capture = _baseline_capture(case_id, current_coordinates)
    candidate_capture = _candidate_capture(
        case_id,
        current_coordinates,
        instrument_route_occurrences,
        observed_occurrences,
        selected,
        verified,
        instrument_prior_occurrences,
        protected_entries,
    )
    elapsed_ms = (time.perf_counter() - case_started) * 1000
    return {
        "case_id": case_id,
        "question": question,
        "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
        "product_input_source": str(PUBLIC_INPUT.relative_to(ROOT)),
        "gold_visible_to_product": False,
        "query_plan": query_plan,
        "query_plan_error": plan_error,
        "legal_system_entry_plan": entry_plan_capture,
        "law_routing": law_route,
        "research": research,
        "candidate_observed_coordinates": [
            _coordinate_text(value) for value in _unique_coordinates(observed_occurrences)
        ],
        "candidate_selected_coordinates": [
            _coordinate_text(value) for value in _unique_coordinates(selected)
        ],
        "candidate_protected_entry_coordinates": [
            _coordinate_text(value) for value in protected_entries
        ],
        "candidate_union_coordinates": [
            _coordinate_text(value) for value in candidate_union
        ],
        "candidate_fulltext_verified_coordinates": [
            _coordinate_text(value) for value in verified
        ],
        "fulltext_current_verification_receipts": fulltext_receipts,
        "semantic_scope_verification_receipts": semantic_scope_receipts,
        "provider_receipts": case_receipts,
        "baseline_capture": baseline_capture,
        "candidate_capture": candidate_capture,
        "call_budget": {
            "case_limit": MAX_CASE_CALLS[case_id],
            "case_reserved": budget.by_case[case_id],
        },
        "elapsed_ms": round(elapsed_ms, 3),
    }


def _page_cap_violations(product_cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for case in product_cases:
        for section in ("law_routing", "research"):
            for wave in (case.get(section) or {}).get("waves") or ():
                for page in wave.get("pages") or ():
                    count = len(page.get("items") or ())
                    if count > PAGE_SIZE:
                        violations.append({
                            "case_id": case["case_id"],
                            "section": section,
                            "page_id": page.get("page_id"),
                            "item_count": count,
                        })
    return violations


def _capture_stage_occurrences(
    product_cases: Sequence[Mapping[str, Any]],
    capture_key: str,
    stage_id: str,
) -> int:
    total = 0
    for case in product_cases:
        capture = case.get(capture_key) or {}
        matches = [
            row for row in capture.get("stages") or ()
            if row.get("stage_id") == stage_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"{capture_key}.{stage_id} missing/duplicate for {case.get('case_id')}"
            )
        total += int((matches[0].get("occurrence_counts") or {}).get("after") or 0)
    return total


def _product_pre_gold_audit(
    *,
    product_cases: Sequence[Mapping[str, Any]],
    raw_receipts: Sequence[Mapping[str, Any]],
    budget: CallBudget,
    atlas: LegalResearchAtlas,
) -> dict[str, Any]:
    annotated_ids = [
        str(receipt.get("call_id") or "")
        for case in product_cases
        for receipt in case.get("provider_receipts") or ()
    ]
    raw_ids = [str(receipt.get("call_id") or "") for receipt in raw_receipts]
    no_forbidden_error = ""
    try:
        _assert_no_forbidden_product_keys(product_cases, "product_cases")
        _assert_internal_evidence_maps_empty(product_cases, "product_cases")
    except Exception as exc:
        no_forbidden_error = f"{type(exc).__name__}: {exc}"
    baseline_source_occurrences = _capture_stage_occurrences(
        product_cases, "baseline_capture", "corpus-source"
    )
    candidate_source_occurrences = _capture_stage_occurrences(
        product_cases, "candidate_capture", "corpus-source"
    )
    checks = {
        "public_input_hash_frozen": _sha(PUBLIC_INPUT) == EXPECTED_PUBLIC_INPUT_SHA256,
        "gold_or_reference_key_absent": not no_forbidden_error,
        "gold_visible_to_product_false": all(
            case.get("gold_visible_to_product") is False for case in product_cases
        ),
        "case_ids_exact": tuple(
            str(case.get("case_id")) for case in product_cases
        ) == EXPECTED_CASE_IDS,
        "provider_receipts_exactly_annotated_once": (
            sorted(annotated_ids) == sorted(raw_ids)
            and len(annotated_ids) == len(set(annotated_ids))
        ),
        "reserved_call_count_has_receipts": len(raw_receipts) == budget.total_reserved,
        "model_pinned": all(
            receipt.get("requested_model") == HAIKU_MODEL
            for receipt in raw_receipts
        ),
        "transport_retry_zero": all(
            receipt.get("transport_max_retries") == TRANSPORT_MAX_RETRIES
            for receipt in raw_receipts
        ),
        "current_authority_frozen": (
            atlas.to_inventory_dict().get("authority_generation")
            == EXPECTED_AUTHORITY_GENERATION
            and str(atlas.to_inventory_dict().get("authority_as_of") or "")
            == EXPECTED_AUTHORITY_AS_OF
        ),
        "page_cap_violations_zero": not _page_cap_violations(product_cases),
        "baseline_source_occurrences_52095": (
            baseline_source_occurrences == EXPECTED_CASE_SOURCE_OCCURRENCES
        ),
        "candidate_source_occurrences_52095": (
            candidate_source_occurrences == EXPECTED_CASE_SOURCE_OCCURRENCES
        ),
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "forbidden_key_error": no_forbidden_error,
        "page_cap_violations": _page_cap_violations(product_cases),
        "reserved_calls": budget.total_reserved,
        "provider_receipts": len(raw_receipts),
        "baseline_source_occurrences": baseline_source_occurrences,
        "candidate_source_occurrences": candidate_source_occurrences,
    }


def _seal_product_capture(
    *,
    product_cases: Sequence[Mapping[str, Any]],
    raw_receipts: Sequence[Mapping[str, Any]],
    pre_gold_audit: Mapping[str, Any],
    budget: CallBudget,
    atlas: LegalResearchAtlas,
    product_started_at: str,
) -> dict[str, Any]:
    provider_capture = _provider_capture_value(
        raw_receipts,
        budget=budget,
        complete=True,
        checkpoint_reason="PRODUCT_COMPLETE_PRE_GOLD",
    )
    _write(PROVIDER_CAPTURE_OUTPUT, provider_capture)
    provider_sha = _sha(PROVIDER_CAPTURE_OUTPUT)

    product_capture = {
        "schema_version": f"{ARTIFACT_SCHEMA_PREFIX}-product-capture-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "product_started_at": product_started_at,
        "product_finished_at": _now(),
        "complete": True,
        "public_input": {
            "path": str(PUBLIC_INPUT.relative_to(ROOT)),
            "sha256": _sha(PUBLIC_INPUT),
        },
        "runtime_atlas": {
            **atlas.to_inventory_dict(),
            "current_article_roots": EXPECTED_CURRENT_ARTICLE_ROOTS,
        },
        "provider_capture": {
            "path": str(PROVIDER_CAPTURE_OUTPUT.relative_to(ROOT)),
            "sha256": provider_sha,
            "bytes": PROVIDER_CAPTURE_OUTPUT.stat().st_size,
        },
        "call_budget": budget.to_dict(),
        "provider_usage": _provider_usage(raw_receipts),
        "pre_gold_audit": dict(pre_gold_audit),
        "gold_visible_to_product": False,
        "scoring_fixture_opened": False,
        "cases": list(product_cases),
    }
    _write(PRODUCT_CAPTURE_OUTPUT, product_capture)
    product_sha = _sha(PRODUCT_CAPTURE_OUTPUT)
    seal = {
        "schema_version": f"{ARTIFACT_SCHEMA_PREFIX}-product-capture-seal-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "sealed_at": _now(),
        "scoring_fixture_opened": False,
        "files": [
            {
                "path": str(PROVIDER_CAPTURE_OUTPUT.relative_to(ROOT)),
                "sha256": provider_sha,
                "bytes": PROVIDER_CAPTURE_OUTPUT.stat().st_size,
            },
            {
                "path": str(PRODUCT_CAPTURE_OUTPUT.relative_to(ROOT)),
                "sha256": product_sha,
                "bytes": PRODUCT_CAPTURE_OUTPUT.stat().st_size,
            },
        ],
    }
    seal["seal_sha256"] = _value_sha(seal)
    _write(CAPTURE_SEAL_OUTPUT, seal)
    return seal


def _verify_product_seal(seal: Mapping[str, Any]) -> None:
    if seal.get("schema_version") != f"{ARTIFACT_SCHEMA_PREFIX}-product-capture-seal-v1":
        raise ValueError("product capture seal schema mismatch")
    unhashed = dict(seal)
    claimed = unhashed.pop("seal_sha256", None)
    if claimed != _value_sha(unhashed):
        raise ValueError("product capture seal content hash mismatch")
    for row in seal.get("files") or ():
        path = (ROOT / str(row["path"])).resolve()
        if not path.is_file():
            raise ValueError(f"sealed product file missing: {path}")
        if _sha(path) != row.get("sha256"):
            raise ValueError(f"sealed product file changed: {path}")
        if path.stat().st_size != row.get("bytes"):
            raise ValueError(f"sealed product file size changed: {path}")


def _persist_sealed_run_checkpoint(
    seal: Mapping[str, Any],
    *,
    product_cases: Sequence[Mapping[str, Any]],
    budget: CallBudget,
    pre_gold_passed: bool,
) -> None:
    checkpoint = {
        "schema_version": f"{ARTIFACT_SCHEMA_PREFIX}-run-checkpoint-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "checkpoint_at": _now(),
        "phase": (
            "PRODUCT_SEALED_PRE_GOLD"
            if pre_gold_passed else "PRODUCT_SEALED_INVALID_PRE_GOLD"
        ),
        "scoring_fixture_opened": False,
        "pre_gold_audit_passed": pre_gold_passed,
        "completed_case_ids": [str(case["case_id"]) for case in product_cases],
        "budget": budget.to_dict(),
        "capture_seal": dict(seal),
        "capture_seal_file_sha256": _sha(CAPTURE_SEAL_OUTPUT),
    }
    checkpoint["artifact_sha256"] = _value_sha(checkpoint)
    _write(RUN_OUTPUT, checkpoint)


def _persist_scoring_run_checkpoint(
    seal: Mapping[str, Any],
    *,
    phase: str,
    budget: CallBudget,
    artifact_paths: Sequence[Path],
) -> None:
    _verify_product_seal(seal)
    checkpoint = {
        "schema_version": f"{ARTIFACT_SCHEMA_PREFIX}-run-checkpoint-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "checkpoint_at": _now(),
        "phase": phase,
        "scoring_fixture_opened": True,
        "scoring_fixture_sha256": EXPECTED_SCORING_FIXTURE_SHA256,
        "budget": budget.to_dict(),
        "capture_seal_file_sha256": _sha(CAPTURE_SEAL_OUTPUT),
        "completed_artifacts": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": _sha(path),
                "bytes": path.stat().st_size,
            }
            for path in artifact_paths
        ],
    }
    checkpoint["artifact_sha256"] = _value_sha(checkpoint)
    _write(RUN_OUTPUT, checkpoint)


def _open_scoring_fixture_after_seal(
    seal: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    """The sole scoring-fixture read boundary in this runner."""

    _verify_product_seal(seal)
    if _sha(SCORING_FIXTURE) != EXPECTED_SCORING_FIXTURE_SHA256:
        raise ValueError("ADR-0107 frozen scoring fixture hash mismatch")
    opened_at = _now()
    value = json.loads(SCORING_FIXTURE.read_text(encoding="utf-8"))
    if value.get("freeze_revision") != 5:
        raise ValueError("scoring fixture revision differs from frozen design")
    cases = value.get("cases") or ()
    if tuple(str(case.get("case_id")) for case in cases) != EXPECTED_CASE_IDS:
        raise ValueError("scoring fixture case IDs/order differ")
    return value, opened_at


def _scoring_by_case(fixture: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for case in fixture.get("cases") or ():
        coordinates: list[tuple[str, int]] = []
        definition_coordinates: list[tuple[str, int]] = []
        target_laws: list[dict[str, str]] = []
        for branch in case.get("branches") or ():
            seen_laws: set[str] = set()
            for target in branch.get("targets") or ():
                coordinate = _parse_coordinate(target["coordinate"])
                coordinates.append(coordinate)
                covers = [
                    str(value).casefold() for value in target.get("covers") or ()
                ]
                if "정의" in str(target.get("label") or "") or any(
                    "definition" in value for value in covers
                ):
                    definition_coordinates.append(coordinate)
                if coordinate[0] not in seen_laws:
                    seen_laws.add(coordinate[0])
                    target_laws.append({
                        "case_id": str(case["case_id"]),
                        "expected_branch_id": str(branch["branch_id"]),
                        "instrument_id": coordinate[0],
                    })
        output[str(case["case_id"])] = {
            "coordinates": _unique_coordinates(coordinates),
            "definition_coordinates": _unique_coordinates(definition_coordinates),
            "target_laws": target_laws,
            "expected": dict(case.get("expected") or {}),
        }
    total_coordinates = sum(len(value["coordinates"]) for value in output.values())
    total_laws = sum(len(value["target_laws"]) for value in output.values())
    if total_coordinates != 36 or total_laws != 12:
        raise ValueError(
            f"scoring denominators drifted: coordinates={total_coordinates}, laws={total_laws}"
        )
    return output


def _trace_events(case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    session = (case.get("research") or {}).get("session") or {}
    return [
        row for row in session.get("trace") or () if isinstance(row, Mapping)
    ]


def _ordered_no_hit_result(
    product_case: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> dict[str, Any] | None:
    contract = expected.get("must_record_before_next_instrument")
    if not isinstance(contract, Mapping):
        return None
    instrument_id = str(contract.get("instrument_id") or "")
    events = _trace_events(product_case)
    hit_indexes = [
        index for index, row in enumerate(events)
        if row.get("event") == "TARGETED_ROUTE_NO_HIT"
        and row.get("instrument_id") == instrument_id
        and (row.get("details") or {}).get("permits_scope_absence_statement") is False
    ]
    next_started = False
    if hit_indexes:
        first = hit_indexes[0]
        next_started = any(
            row.get("event") == "INSTRUMENT_STARTED"
            and row.get("instrument_id") != instrument_id
            for row in events[first + 1 :]
        )
    return {
        "instrument_id": instrument_id,
        "targeted_no_hit_recorded": bool(hit_indexes),
        "next_instrument_started": next_started,
        "passed": bool(hit_indexes and next_started),
    }


def _build_law_route_ledger(
    product_cases: Sequence[Mapping[str, Any]],
    scoring: Mapping[str, Mapping[str, Any]],
    atlas: LegalResearchAtlas,
) -> dict[str, Any]:
    all_instruments = set(atlas.current_document_ids)
    case_rows: list[dict[str, Any]] = []
    for product_case in product_cases:
        case_id = str(product_case["case_id"])
        exposed_occurrences = (
            product_case.get("law_routing") or {}
        ).get("exposed_instrument_occurrences") or ()
        selected_occurrences = (
            product_case.get("law_routing") or {}
        ).get("selected_instrument_occurrences") or ()
        exposed_by_instrument: dict[str, set[str]] = defaultdict(set)
        selected_by_instrument: dict[str, set[str]] = defaultdict(set)
        for row in exposed_occurrences:
            exposed_by_instrument[str(row["instrument_id"])].add(
                str(row.get("branch_id") or "")
            )
        for row in selected_occurrences:
            selected_by_instrument[str(row["instrument_id"])].add(
                str(row.get("branch_id") or "")
            )
        target_rows: list[dict[str, Any]] = []
        for target in scoring[case_id]["target_laws"]:
            instrument_id = target["instrument_id"]
            target_rows.append({
                **target,
                "baseline_exposed": instrument_id in all_instruments,
                "baseline_selected": instrument_id in all_instruments,
                "candidate_exposed": instrument_id in exposed_by_instrument,
                "candidate_selected": instrument_id in selected_by_instrument,
                "candidate_exposed_branch_ids": sorted(
                    exposed_by_instrument.get(instrument_id, set())
                ),
                "candidate_selected_branch_ids": sorted(
                    selected_by_instrument.get(instrument_id, set())
                ),
            })
        by_expected_branch: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in target_rows:
            by_expected_branch[row["expected_branch_id"]].append(row)
        branch_results = [{
            "expected_branch_id": branch_id,
            "target_law_total": len(rows),
            "candidate_exposed": sum(bool(row["candidate_exposed"]) for row in rows),
            "candidate_selected": sum(bool(row["candidate_selected"]) for row in rows),
            "all_target_laws_exposed": all(row["candidate_exposed"] for row in rows),
            "all_target_laws_selected": all(row["candidate_selected"] for row in rows),
        } for branch_id, rows in sorted(by_expected_branch.items())]
        case_rows.append({
            "case_id": case_id,
            "target_laws": target_rows,
            "expected_branch_results": branch_results,
            "ordered_no_hit": _ordered_no_hit_result(
                product_case,
                scoring[case_id]["expected"],
            ),
        })

    target_rows = [row for case in case_rows for row in case["target_laws"]]
    branch_rows = [
        row for case in case_rows for row in case["expected_branch_results"]
    ]
    no_hit_rows = [case["ordered_no_hit"] for case in case_rows if case["ordered_no_hit"]]
    artifact = {
        "schema_version": f"{ARTIFACT_SCHEMA_PREFIX}-law-route-ledger-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "accounting_unit": "case_id + expected_branch_id + instrument_id",
        "candidate_hit_rule": (
            "target instrument exposed/selected by any actually generated branch "
            "within the same case; expected_branch_id defines only the frozen "
            "12-occurrence denominator"
        ),
        "computed_post_selection": True,
        "gold_visible_to_product": False,
        "target_law_total": len(target_rows),
        "cases": case_rows,
        "aggregate": {
            "baseline_exposed": sum(bool(row["baseline_exposed"]) for row in target_rows),
            "baseline_selected": sum(bool(row["baseline_selected"]) for row in target_rows),
            "candidate_exposed": sum(bool(row["candidate_exposed"]) for row in target_rows),
            "candidate_selected": sum(bool(row["candidate_selected"]) for row in target_rows),
            "expected_branch_total": len(branch_rows),
            "candidate_all_target_laws_branch_complete": sum(
                bool(row["all_target_laws_selected"]) for row in branch_rows
            ),
            "ordered_no_hit_total": len(no_hit_rows),
            "ordered_no_hit_passed": sum(bool(row["passed"]) for row in no_hit_rows),
        },
    }
    if artifact["target_law_total"] != 12:
        raise ValueError("law-route ledger denominator must be 12")
    if artifact["aggregate"]["expected_branch_total"] != 6:
        raise ValueError("law-route branch denominator must be 6")
    artifact["artifact_sha256"] = _value_sha(artifact)
    return artifact


def _stage(grade: Mapping[str, Any], stage_id: str) -> Mapping[str, Any]:
    for row in grade.get("stages") or ():
        if row.get("stage_id") == stage_id:
            return row
    raise KeyError(f"stage not found: {stage_id}")


def _score_and_write_artifacts(
    *,
    product_cases: Sequence[dict[str, Any]],
    raw_receipts: Sequence[Mapping[str, Any]],
    seal: Mapping[str, Any],
    atlas: LegalResearchAtlas,
    budget: CallBudget,
    run_started: float,
) -> dict[str, Any]:
    fixture, scoring_opened_at = _open_scoring_fixture_after_seal(seal)
    scoring = _scoring_by_case(fixture)
    public_questions = {
        case["case_id"]: case["question"] for case in product_cases
    }
    fixture_questions = {
        str(case["case_id"]): str(case["question"])
        for case in fixture.get("cases") or ()
    }
    if public_questions != fixture_questions:
        raise ValueError("public questions differ from post-seal scoring fixture")

    graded_ledgers: list[dict[str, Any]] = []
    scored_cases: list[dict[str, Any]] = []
    for product_case in product_cases:
        case_id = product_case["case_id"]
        gold = scoring[case_id]["coordinates"]
        baseline_grade = ledger.grade_capture(
            product_case["baseline_capture"],
            gold,
            canonicalizer=ledger.identity_canonicalizer,
        )
        candidate_grade = ledger.grade_capture(
            product_case["candidate_capture"],
            gold,
            canonicalizer=ledger.identity_canonicalizer,
        )
        ledger.validate_graded_ledger(
            baseline_grade,
            expected_stage_ids=DECLARED_STAGES["baseline"],
        )
        ledger.validate_graded_ledger(
            candidate_grade,
            expected_stage_ids=DECLARED_STAGES[CANDIDATE_ARM_ID],
        )
        graded_ledgers.extend((baseline_grade, candidate_grade))
        final_stage = _stage(candidate_grade, "candidate-present")
        observed_stage = _stage(candidate_grade, OBSERVED_STAGE_ID)
        selected_stage = _stage(candidate_grade, "llm-selected")
        definition_targets = set(scoring[case_id]["definition_coordinates"])
        observed_coordinates = {
            _parse_coordinate(value)
            for value in product_case["candidate_observed_coordinates"]
        }
        selected_coordinates = {
            _parse_coordinate(value)
            for value in product_case["candidate_selected_coordinates"]
        }
        present_coordinates = {
            _parse_coordinate(value)
            for value in product_case["candidate_fulltext_verified_coordinates"]
        }
        scored_cases.append({
            "case_id": case_id,
            "gold_total": len(gold),
            "gold_coordinates": [_coordinate_text(value) for value in gold],
            "baseline_gold_hits": _stage(
                baseline_grade, "exhaustive-present"
            )["gold_after"],
            "candidate_instrument_route_gold_hits": _stage(
                candidate_grade, "instrument-route"
            )["gold_after"],
            "candidate_hierarchy_observed_gold_hits": observed_stage["gold_after"],
            "candidate_llm_selected_gold_hits": selected_stage["gold_after"],
            "candidate_present_gold_hits": final_stage["gold_after"],
            "candidate_present_recall": final_stage["golden_recall"],
            "structural_case_complete": final_stage["gold_after"] == len(gold),
            "definition_entry": {
                "target_total": len(definition_targets),
                "target_coordinates": [
                    _coordinate_text(value) for value in sorted(definition_targets)
                ],
                "hierarchy_observed": len(definition_targets & observed_coordinates),
                "llm_selected": len(definition_targets & selected_coordinates),
                "candidate_present": len(definition_targets & present_coordinates),
            },
            "controller_status": (product_case.get("research") or {}).get("status"),
            "effective_status": (
                product_case.get("research") or {}
            ).get("effective_status"),
            "discarded_gold_by_stage": {
                stage["stage_id"]: stage["discarded_gold"]
                for stage in candidate_grade["stages"]
                if stage["discarded_gold"]
            },
        })

    run_ledger = ledger.build_run_artifact(
        RUN_ID,
        graded_ledgers,
        DECLARED_STAGES,
    )
    experiment_ledger = ledger.build_experiment_artifact(
        ADR_ID,
        EXPERIMENT_ID,
        [run_ledger],
    )
    _write(STAGE_LEDGER_OUTPUT, experiment_ledger)
    _persist_scoring_run_checkpoint(
        seal,
        phase="SCORING_STAGE_LEDGER_WRITTEN",
        budget=budget,
        artifact_paths=(STAGE_LEDGER_OUTPUT,),
    )
    law_route_ledger = _build_law_route_ledger(
        product_cases,
        scoring,
        atlas,
    )
    _write(LAW_ROUTE_LEDGER_OUTPUT, law_route_ledger)
    _persist_scoring_run_checkpoint(
        seal,
        phase="SCORING_LEDGERS_WRITTEN",
        budget=budget,
        artifact_paths=(STAGE_LEDGER_OUTPUT, LAW_ROUTE_LEDGER_OUTPUT),
    )

    usage = _provider_usage(raw_receipts)
    annotated_receipts = [
        receipt
        for case in product_cases
        for receipt in case.get("provider_receipts") or ()
    ]
    validation_failures = [
        receipt for receipt in annotated_receipts
        if not (receipt.get("validation") or {}).get("closed_menu_and_schema")
    ]
    provider_invalid_call_ids = {
        str(receipt.get("call_id") or "")
        for receipt in raw_receipts
        if (receipt.get("provider") or {}).get("error")
        or receipt.get("wrapper_error")
        or not isinstance(receipt.get("structured_output"), Mapping)
    }
    schema_invalid_call_ids = {
        str(receipt.get("call_id") or "") for receipt in validation_failures
    }
    invalid_call_ids = (provider_invalid_call_ids | schema_invalid_call_ids) - {""}
    first_pass_validity = {
        "denominator_attempted_provider_calls": len(raw_receipts),
        "numerator_valid_first_pass_calls": len(raw_receipts) - len(invalid_call_ids),
        "invalid_call_count": len(invalid_call_ids),
        "invalid_call_ids": sorted(invalid_call_ids),
        "unreceipted_reserved_calls": budget.total_reserved - len(raw_receipts),
        "valid_rate": (
            (len(raw_receipts) - len(invalid_call_ids)) / len(raw_receipts)
            if raw_receipts else 0.0
        ),
    }
    call_kinds = Counter(str(row.get("kind") or "") for row in raw_receipts)
    final_counts = [
        int(row["candidate_present_gold_hits"]) for row in scored_cases
    ]
    final_presented = [
        len(case["candidate_fulltext_verified_coordinates"])
        for case in product_cases
    ]
    definition_entry = {
        "target_total": sum(
            int(row["definition_entry"]["target_total"]) for row in scored_cases
        ),
        "hierarchy_observed": sum(
            int(row["definition_entry"]["hierarchy_observed"])
            for row in scored_cases
        ),
        "llm_selected": sum(
            int(row["definition_entry"]["llm_selected"])
            for row in scored_cases
        ),
        "candidate_present": sum(
            int(row["definition_entry"]["candidate_present"])
            for row in scored_cases
        ),
    }
    budget_or_cursor_failures = [
        {
            "case_id": case["case_id"],
            "law_stop_reason": (case.get("law_routing") or {}).get("stop_reason"),
            "research_stop_reason": (case.get("research") or {}).get("stop_reason"),
        }
        for case in product_cases
        if "BUDGET" in str((case.get("law_routing") or {}).get("stop_reason") or "")
        or "BUDGET" in str((case.get("research") or {}).get("stop_reason") or "")
    ]
    incomplete_cases = [
        case["case_id"]
        for case in product_cases
        if (case.get("law_routing") or {}).get("effective_status")
        == ResearchStatus.INCOMPLETE_WITH_CURSOR.value
        or (case.get("research") or {}).get("effective_status")
        == ResearchStatus.INCOMPLETE_WITH_CURSOR.value
    ]
    probe_events = [
        dict(event)
        for case in product_cases
        for event in (case.get("law_routing") or {}).get("probe_events") or ()
    ]
    tentative_probe_with_cursor = any(
        event.get("event") == "ARTICLE_PROBE_STARTED"
        and event.get("law_cursor_retained") is True
        for event in probe_events
    )
    resume_after_unsatisfied = False
    for index, event in enumerate(probe_events):
        if event.get("event") != "LAW_CURSOR_RESUMED":
            continue
        branch_id = event.get("branch_id")
        resume_after_unsatisfied = any(
            earlier.get("event") == "ARTICLE_PROBE_UNSATISFIED"
            and earlier.get("branch_id") == branch_id
            for earlier in probe_events[:index]
        )
        if resume_after_unsatisfied:
            break
    role_priority_signal_count = sum(
        1
        for case in product_cases
        for wave in (case.get("law_routing") or {}).get("waves") or ()
        for page in wave.get("pages") or ()
        for item in page.get("items") or ()
        if any(
            str(signal).startswith("ROLE_PRIORITY:")
            for signal in item.get("routing_signals") or ()
        )
    )
    provider_schema_http_400 = [
        str(receipt.get("call_id") or "")
        for receipt in raw_receipts
        if "minimum" in str((receipt.get("provider") or {}).get("error") or "").lower()
        or "maximum" in str((receipt.get("provider") or {}).get("error") or "").lower()
    ]
    unapplied_waves = [
        {
            "case_id": case["case_id"],
            "section": section,
            "wave": wave.get("wave"),
            "error": wave.get("error"),
        }
        for case in product_cases
        for section in ("law_routing", "research")
        for wave in (case.get(section) or {}).get("waves") or ()
        if wave.get("applied") is False
    ]
    wall_ms = (time.perf_counter() - run_started) * 1000
    law_aggregate = law_route_ledger["aggregate"]
    candidate_hits = sum(final_counts)
    instrument_route_hits = sum(
        int(row["candidate_instrument_route_gold_hits"])
        for row in scored_cases
    )
    observed_hits = sum(
        int(row["candidate_hierarchy_observed_gold_hits"])
        for row in scored_cases
    )
    selected_hits = sum(
        int(row["candidate_llm_selected_gold_hits"])
        for row in scored_cases
    )
    forbidden_present = [
        {"case_id": case["case_id"], "coordinate": coordinate}
        for case in product_cases
        for coordinate in SCORING_ONLY_FORBIDDEN_PRESENT.get(case["case_id"], ())
        if coordinate in set(case["candidate_fulltext_verified_coordinates"])
    ]
    success_checks = {
        "target_law_menu_exposure_threshold": (
            law_aggregate["candidate_exposed"] >= MIN_TARGET_LAW_EXPOSED
        ),
        "target_law_selected_threshold": (
            law_aggregate["candidate_selected"] >= MIN_TARGET_LAW_SELECTED
        ),
        "instrument_route_gold_threshold": (
            instrument_route_hits >= MIN_INSTRUMENT_ROUTE_GOLD
        ),
        "article_observed_gold_threshold": observed_hits >= MIN_OBSERVED_GOLD,
        "article_selected_gold_threshold": selected_hits >= MIN_SELECTED_GOLD,
        "candidate_present_gold_threshold": candidate_hits >= MIN_PRESENT_GOLD,
        "structural_case_requirement": (
            not REQUIRE_ALL_STRUCTURAL_CASES
            or all(bool(row["structural_case_complete"]) for row in scored_cases)
        ),
        "known_scope_false_positives_absent": not forbidden_present,
        "ordered_no_hit_requirement": (
            not REQUIRE_ORDERED_NO_HIT
            or (
                law_aggregate["ordered_no_hit_total"] == 1
                and law_aggregate["ordered_no_hit_passed"] == 1
            )
        ),
        "page_size_violations_zero": not _page_cap_violations(product_cases),
        "first_pass_provider_schema_closed_menu_valid_100pct": (
            first_pass_validity["invalid_call_count"] == 0
            and first_pass_validity["unreceipted_reserved_calls"] == 0
        ),
        "provider_numeric_schema_http400_zero": not provider_schema_http_400,
        "ordered_role_priority_signal_requirement": (
            not REQUIRE_ROLE_PRIORITY_SIGNAL or role_priority_signal_count > 0
        ),
        "article_probe_before_law_catalog_exhaustion": (
            not REQUIRE_CURSOR_RESUME or tentative_probe_with_cursor
        ),
        "unsatisfied_probe_then_law_cursor_resume_requirement": (
            not REQUIRE_CURSOR_RESUME or resume_after_unsatisfied
        ),
        "budget_exhaustion_zero": not budget_or_cursor_failures,
        "incomplete_with_cursor_requirement": (
            not REQUIRE_COMPLETE_RESEARCH or not incomplete_cases
        ),
        "unapplied_wave_zero": not unapplied_waves,
        "product_calls_at_most_242": usage["calls"] <= MAX_TOTAL_CALLS,
        "input_tokens_at_most_1000000": usage["input_tokens"] <= MAX_INPUT_TOKENS,
        "output_tokens_at_most_200000": usage["output_tokens"] <= MAX_OUTPUT_TOKENS,
        "call_p95_at_most_20000ms": (
            usage["provider_duration_p95_ms"] <= MAX_CALL_P95_MS
        ),
        "wall_at_most_1200000ms": wall_ms <= MAX_WALL_MS,
        "transport_retry_zero": all(
            row.get("transport_max_retries") == 0 for row in raw_receipts
        ),
        "gold_visible_to_product_false": all(
            case.get("gold_visible_to_product") is False for case in product_cases
        ),
    }
    summary = {
        "passed": all(success_checks.values()),
        "success_checks": success_checks,
        "scoring_denominators": {
            "cases": 3,
            "expected_branches": 6,
            "target_law_occurrences": 12,
            "case_article_root_occurrences": 36,
            "case_source_occurrences_per_arm": EXPECTED_CASE_SOURCE_OCCURRENCES,
            "case_source_occurrence_formula": "3 cases * 17,365 current article roots",
            "global_unique_target_coordinates": len({
                value
                for case in scoring.values()
                for value in case["coordinates"]
            }),
        },
        "by_arm": {
            "baseline": {
                "gold_hits": 36,
                "gold_total": 36,
                "golden_recall": 1.0,
                "presented_total": EXPECTED_CURRENT_ARTICLE_ROOTS * 3,
                "product_calls": 0,
            },
            CANDIDATE_ARM_ID: {
                "gold_hits": candidate_hits,
                "gold_total": 36,
                "golden_recall": candidate_hits / 36,
                "presented_total": sum(final_presented),
                "presented_mean": statistics.mean(final_presented),
                "presented_p50": statistics.median(final_presented),
                "presented_p95": _percentile(final_presented, 0.95),
                "selectivity": sum(final_presented) / (
                    EXPECTED_CURRENT_ARTICLE_ROOTS * 3
                ),
            },
        },
        "paired": {
            "candidate_only": 0,
            "baseline_only": 36 - candidate_hits,
            "both": candidate_hits,
            "neither": 0,
        },
        "law_route": law_aggregate,
        "definition_entry": definition_entry,
        "provider_usage": usage,
        "call_kinds": dict(sorted(call_kinds.items())),
        "validation_failure_count": len(validation_failures),
        "first_pass_validity": first_pass_validity,
        "budget_or_cursor_failures": budget_or_cursor_failures,
        "incomplete_cases": incomplete_cases,
        "unapplied_waves": unapplied_waves,
        "page_cap_violations": _page_cap_violations(product_cases),
        "forbidden_present": forbidden_present,
        "interleaving": {
            "probe_event_count": len(probe_events),
            "tentative_probe_with_cursor": tentative_probe_with_cursor,
            "resume_after_unsatisfied": resume_after_unsatisfied,
            "role_priority_signal_count": role_priority_signal_count,
            "provider_numeric_schema_http400_call_ids": provider_schema_http_400,
        },
        "wall_ms": round(wall_ms, 3),
    }
    run_artifact = {
        "schema_version": f"{ARTIFACT_SCHEMA_PREFIX}-run-v1",
        "adr_id": ADR_ID,
        "experiment_id": EXPERIMENT_ID,
        "run_id": RUN_ID,
        "created_at": _now(),
        "model": HAIKU_MODEL,
        "product_boundary": {
            "public_input_path": str(PUBLIC_INPUT.relative_to(ROOT)),
            "public_input_sha256": _sha(PUBLIC_INPUT),
            "product_capture_path": str(PRODUCT_CAPTURE_OUTPUT.relative_to(ROOT)),
            "product_capture_sha256": _sha(PRODUCT_CAPTURE_OUTPUT),
            "provider_capture_path": str(PROVIDER_CAPTURE_OUTPUT.relative_to(ROOT)),
            "provider_capture_sha256": _sha(PROVIDER_CAPTURE_OUTPUT),
            "capture_seal_path": str(CAPTURE_SEAL_OUTPUT.relative_to(ROOT)),
            "capture_seal_sha256": _sha(CAPTURE_SEAL_OUTPUT),
            "scoring_fixture_first_opened_at": scoring_opened_at,
            "scoring_fixture_path": str(SCORING_FIXTURE.relative_to(ROOT)),
            "scoring_fixture_sha256": _sha(SCORING_FIXTURE),
            "gold_visible_to_product": False,
        },
        "authority": {
            **atlas.to_inventory_dict(),
            "current_article_roots": EXPECTED_CURRENT_ARTICLE_ROOTS,
        },
        "exact_question_files": [
            {
                "case_id": case_id,
                "path": str(path.relative_to(ROOT)),
                "sha256": _sha(path),
                "bytes": path.stat().st_size,
                "recording_note": (
                    "template file inventory; exact product question is sealed in "
                    "public input and every provider request receipt"
                ),
            }
            for case_id, path in QUESTION_FILES.items()
        ],
        "budget": budget.to_dict(),
        "summary": summary,
        "scored_cases": scored_cases,
        "product_cases": list(product_cases),
        "artifacts": {
            "retrieval_stage_ledger": {
                "path": str(STAGE_LEDGER_OUTPUT.relative_to(ROOT)),
                "sha256": _sha(STAGE_LEDGER_OUTPUT),
                "bytes": STAGE_LEDGER_OUTPUT.stat().st_size,
            },
            "law_route_ledger": {
                "path": str(LAW_ROUTE_LEDGER_OUTPUT.relative_to(ROOT)),
                "sha256": _sha(LAW_ROUTE_LEDGER_OUTPUT),
                "bytes": LAW_ROUTE_LEDGER_OUTPUT.stat().st_size,
            },
        },
    }
    run_artifact["artifact_sha256"] = _value_sha(run_artifact)
    _write(RUN_OUTPUT, run_artifact)
    return run_artifact


def _run_product_phase() -> tuple[
    list[dict[str, Any]],
    tuple[dict[str, Any], ...],
    dict[str, Any],
    LegalResearchAtlas,
    CallBudget,
    float,
]:
    run_started = time.perf_counter()
    product_started_at = _now()
    runtime_lock = _validate_runtime_lock()
    public_cases = _load_public_input()
    index = index_mod.Index.load()
    atlas = LegalResearchAtlas.from_index(index)
    current_coordinates = _all_current_coordinates(atlas)
    if HAIKU_MODEL != "claude-haiku-4-5-20251001":
        raise RuntimeError(f"product model policy mismatch: {HAIKU_MODEL}")

    recorder = ThreadLocalStructuredRecorder()
    budget = CallBudget()
    product_rows: list[dict[str, Any]] = []
    for ordinal, public_case in enumerate(public_cases, 1):
        product_case = _run_product_case(
            public_case=public_case,
            atlas=atlas,
            current_coordinates=current_coordinates,
            recorder=recorder,
            budget=budget,
            run_started=run_started,
        )
        product_rows.append(product_case)
        _persist_product_checkpoint(
            product_cases=product_rows,
            recorder=recorder,
            budget=budget,
            atlas=atlas,
            product_started_at=product_started_at,
            checkpoint_reason=f"CASE_COMPLETE:{public_case['case_id']}",
        )
        print(
            f"[{ordinal}/{len(public_cases)}] {public_case['case_id']} "
            f"calls={budget.by_case[public_case['case_id']]} "
            f"total={budget.total_reserved}",
            file=sys.stderr,
            flush=True,
        )

    raw_receipts = recorder.receipts
    pre_gold_audit = _product_pre_gold_audit(
        product_cases=product_rows,
        raw_receipts=raw_receipts,
        budget=budget,
        atlas=atlas,
    )
    seal = _seal_product_capture(
        product_cases=product_rows,
        raw_receipts=raw_receipts,
        pre_gold_audit=pre_gold_audit,
        budget=budget,
        atlas=atlas,
        product_started_at=product_started_at,
    )
    _persist_sealed_run_checkpoint(
        seal,
        product_cases=product_rows,
        budget=budget,
        pre_gold_passed=bool(pre_gold_audit["passed"]),
    )
    if not pre_gold_audit["passed"]:
        raise RuntimeError(
            "pre-gold audit failed; provider/product captures are sealed and "
            "the ADR-0107 scoring fixture was not opened"
        )
    if runtime_lock.get("authority_generation") != EXPECTED_AUTHORITY_GENERATION:
        raise RuntimeError("runtime lock authority generation mismatch")
    return product_rows, raw_receipts, seal, atlas, budget, run_started


def run() -> dict[str, Any]:
    _assert_output_contract(fresh_run=True)
    product_rows, receipts, seal, atlas, budget, run_started = _run_product_phase()
    return _score_and_write_artifacts(
        product_cases=product_rows,
        raw_receipts=receipts,
        seal=seal,
        atlas=atlas,
        budget=budget,
        run_started=run_started,
    )


def preflight() -> dict[str, Any]:
    """Validate frozen public/corpus inputs without constructing an LLM client."""

    _assert_output_contract(fresh_run=False)
    runtime_lock = _validate_runtime_lock()
    public_cases = _load_public_input()
    atlas = LegalResearchAtlas.from_index(index_mod.Index.load())
    coordinates = _all_current_coordinates(atlas)
    return {
        "schema_version": f"{ARTIFACT_SCHEMA_PREFIX}-preflight-v1",
        "api_calls": 0,
        "public_input_path": str(PUBLIC_INPUT.relative_to(ROOT)),
        "public_input_sha256": _sha(PUBLIC_INPUT),
        "case_ids": [case["case_id"] for case in public_cases],
        "page_size": PAGE_SIZE,
        "model": HAIKU_MODEL,
        "authority": atlas.to_inventory_dict(),
        "current_article_roots": len(coordinates),
        "call_budget": {
            "total": MAX_TOTAL_CALLS,
            "by_case": MAX_CASE_CALLS,
            "transport_max_retries": TRANSPORT_MAX_RETRIES,
        },
        "scoring_fixture_opened": False,
        "runtime_lock_path": str(RUNTIME_LOCK.relative_to(ROOT)),
        "runtime_lock_sha256": _sha(RUNTIME_LOCK),
        "runtime_lock": runtime_lock,
        "output_contract": {
            "adr_root": str(ADR.relative_to(ROOT)),
            "paths": [str(path.relative_to(ROOT)) for path in _output_paths()],
            "historical_adr_writes_forbidden": True,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="validate public/current inputs without a provider call or artifact write",
    )
    args = parser.parse_args(argv)
    if args.preflight_only:
        print(json.dumps(preflight(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    result = run()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
