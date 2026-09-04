"""성능 손잡이는 한 등록부에 있고 다이어그램·A/B가 같은 값을 본다."""

from pathlib import Path

from lawrag.core.rag import controls


ROOT = Path(__file__).resolve().parents[2]


def test_control_registry_is_unique_and_described():
    keys = [row.key for row in controls.CONTROLS]
    assert len(keys) == len(set(keys))
    assert len(keys) >= 60
    assert all(row.description and row.owner and row.risk for row in controls.CONTROLS)


def test_current_additive_budgets_are_reported_as_structural_conflicts():
    by_code = {row["code"]: row for row in controls.audit()}

    assert by_code["ENTRY_BUDGET_EXCEEDS_SHARED_CAP"]["observed"] == {
        "entry_theoretical_max": 18, "shared_sections_max": 12,
    }
    assert by_code["DOC_COMPANION_BYPASSES_SHARED_CAP"]["observed"][
        "theoretical_final_sections"] == 38
    assert by_code["CONCEPT_RAW_POOL_MULTIPLIES"]["observed"][
        "raw_candidates_per_question"] == 480


def test_environment_override_changes_value_and_fingerprint(monkeypatch):
    base = controls.fingerprint()
    monkeypatch.setenv("RAG_VECTOR_MIN", "0.61")

    assert controls.value("entry.vector_cos_min") == 0.61
    assert controls.fingerprint() != base


def test_main_flow_diagram_contains_every_required_control_and_fingerprint():
    text = (ROOT / "docs" / "RAG_FLOW.md").read_text(encoding="utf-8")
    assert controls.validate_diagram(text) == []


def test_literal_limit_audit_keeps_unregistered_backlog_visible():
    rows = controls.literal_limit_candidates(ROOT)

    assert rows
    assert any(row["path"].endswith("rag/compare.py")
               and row["name"] == "CAND_MAX" for row in rows)
    assert any(row["kind"] == "call_budget" and row["name"] == "max_tokens"
               for row in rows)
    assert not any(row["path"].endswith("rag/controls.py") for row in rows)
