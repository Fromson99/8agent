from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from lawrag.core.legal_graph import COMPILER_CONTRACT_VERSION
from lawrag.core.legal_graph.validation import _State, _validate_source_accounting


SOURCE_KINDS = (
    "definitions",
    "frames",
    "requirements",
    "glossary",
    "references",
    "delegation",
    "legacy_bundle_fallback",
)
TERMINALS = (
    "mapped",
    "support_only",
    "unresolved",
    "suppressed",
    "out_of_contract",
    "parse_error",
)


def _empty_partition() -> dict:
    return {
        "input_rows": 0,
        "terminal_counts": {name: 0 for name in TERMINALS},
        "terminal_ids": {name: [] for name in TERMINALS},
        "accepted_ids": [],
        "unresolved_ids": [],
        "candidate_ids": [],
        "accepted_assertion_ids": [],
    }


def _state(tmp_path: Path, sources: dict[str, dict]) -> _State:
    state = _State(
        tmp_path,
        {
            "generation_id": "zero-accounting-test",
            "authority_generation": "a" * 64,
            "compiler_contract": COMPILER_CONTRACT_VERSION,
        },
        None,
    )
    state.rows_by_path["source_accounting.json"] = [{
        "sources": sources,
        "totals": {
            "input_rows": 0,
            "terminal_counts": {name: 0 for name in TERMINALS},
        },
    }]
    return state


def test_v4_accepts_exact_declared_zero_row_source_partitions(tmp_path: Path):
    state = _state(tmp_path, {name: _empty_partition() for name in SOURCE_KINDS})

    _validate_source_accounting(state)

    assert not state.errors


def test_v4_rejects_unknown_source_kind_even_when_empty(tmp_path: Path):
    sources = {name: _empty_partition() for name in SOURCE_KINDS}
    sources["delegtion"] = sources.pop("delegation")
    state = _state(tmp_path, sources)

    _validate_source_accounting(state)

    assert "accounting.source_partition" in {issue.code for issue in state.errors}

    observed_state = _state(
        tmp_path,
        {name: _empty_partition() for name in SOURCE_KINDS},
    )
    observed_state.rows_by_path["observations/frame_observations.jsonl"] = [{
        "id": "observation:unknown-source",
        "source_kind": "delegtion",
        "terminal_disposition": "support_only",
    }]

    _validate_source_accounting(observed_state)

    assert "accounting.source_partition" in {
        issue.code for issue in observed_state.errors
    }


def test_v4_rejects_nonzero_accounting_without_observations(tmp_path: Path):
    sources = {name: _empty_partition() for name in SOURCE_KINDS}
    sources["delegation"] = deepcopy(sources["delegation"])
    sources["delegation"]["input_rows"] = 1
    sources["delegation"]["terminal_counts"]["mapped"] = 1
    sources["delegation"]["terminal_ids"]["mapped"] = ["fabricated-observation"]
    state = _state(tmp_path, sources)

    _validate_source_accounting(state)

    codes = {issue.code for issue in state.errors}
    assert {"accounting.input_count", "accounting.terminal_counts", "accounting.terminal_ids"} <= codes
