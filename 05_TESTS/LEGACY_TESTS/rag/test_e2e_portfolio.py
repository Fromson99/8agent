import json

from scripts import rag_e2e_portfolio


def test_gate_supports_min_and_max():
    assert rag_e2e_portfolio._gate("recall", 0.9, {"min": 0.9})["passed"]
    assert rag_e2e_portfolio._gate("stray", 0.2, {"max": 0.1})["passed"] is False


def test_coverage_reports_unobserved_required_item():
    coverage = rag_e2e_portfolio._coverage(
        ["concept", "memory", "vector"], {"concept": 2, "memory": 0, "vector": 4})
    assert coverage["rate"] == round(2 / 3, 6)
    assert coverage["missing"] == ["memory"]


def test_cm_field_suite_is_the_primary_release_artifact():
    spec = json.loads(rag_e2e_portfolio.DEFAULT_SPEC.read_text(encoding="utf-8"))
    primary = spec["primary_artifact_id"]
    artifact = next(row for row in spec["artifacts"] if row["id"] == primary)

    assert primary == "ask_cm_field_core"
    assert artifact["flow"] == "ask"
    assert artifact["gates"]["semantic_accuracy"]["min"] == 0.8
