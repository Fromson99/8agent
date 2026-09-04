from pathlib import Path

import pytest

from lawrag.core.rag.legal_answer_checklists import (
    ChecklistError,
    aggregate_verdict,
    checklist_version,
    load_items,
    route_items,
)


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
ITEMS = ROOT / "01_DATA/legal_answer_checklists/items"


def test_registry_loads_and_version_is_content_addressed():
    items = load_items(ITEMS)
    assert len(items) >= 10
    assert len({item.id for item in items}) == len(items)
    assert checklist_version(ITEMS).startswith(f"legal-answer-items{len(items)}-")


def test_router_always_includes_core_and_selects_boundary_item():
    items = load_items(ITEMS)
    selected = route_items("자본금이 정확히 10억원이면 10억원 미만인가?", [], items)
    ids = {item.id for item in selected}
    assert {item.id for item in items if item.scope == "core"} <= ids
    assert "LC-101" in ids
    assert "LC-104" not in ids


def test_aggregate_is_fail_closed_on_missing_item_and_fake_evidence():
    items = load_items(ITEMS)[:2]
    missing = aggregate_verdict(items, {"items": []}, answer="답", evidence_ids=["E1"])
    assert missing.verdict == "UNCLEAR"
    raw = {"items": [
        {"id": items[0].id, "verdict": "PASS", "answer_quote": "답",
         "evidence_ids": ["E999"], "reason": "x"},
        {"id": items[1].id, "verdict": "PASS", "answer_quote": "답",
         "evidence_ids": ["E1"], "reason": "x"},
    ]}
    invalid = aggregate_verdict(items, raw, answer="답", evidence_ids=["E1"])
    assert invalid.verdict == "UNCLEAR"
    assert any("invalid_evidence_id" in error for error in invalid.guard_errors)


def test_aggregate_rejects_any_blocker_fail():
    items = [item for item in load_items(ITEMS) if item.severity == "blocker"][:2]
    raw = {"items": [
        {"id": items[0].id, "verdict": "PASS", "answer_quote": "답",
         "evidence_ids": ["E1"], "reason": "x"},
        {"id": items[1].id, "verdict": "FAIL", "answer_quote": "답",
         "evidence_ids": ["E1"], "reason": "x"},
    ]}
    result = aggregate_verdict(items, raw, answer="답", evidence_ids=["E1"])
    assert result.verdict == "REJECT"

