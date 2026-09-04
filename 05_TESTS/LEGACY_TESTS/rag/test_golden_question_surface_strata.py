from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
SCRIPT = ROOT / "06_TOOLS/LEGACY_SCRIPTS/rag_golden_question_surface_strata.py"


def _module():
    spec = importlib.util.spec_from_file_location("golden_surface_strata", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_case_has_two_exact_evidence_views_and_partition_is_complete():
    module = _module()
    report = module.build_report(manifest_sha256="frozen-test-manifest")
    assert len(report["rows"]) == 61
    assert len({row["case_id"] for row in report["rows"]}) == 61
    for row in report["rows"]:
        for view_name, text_name in (
            ("source_question_view", "source_question"),
            ("runtime_question_view", "runtime_question"),
        ):
            view = row[view_name]
            assert view["label"] in module.LABELS
            for evidence in view["authority_evidence"] + view["keyword_evidence"]:
                assert evidence in row[text_name]


def test_report_is_deterministic_and_does_not_use_gold_or_retrieval_for_labels():
    module = _module()
    left = module.build_report(manifest_sha256="frozen-test-manifest")
    right = module.build_report(manifest_sha256="frozen-test-manifest")
    assert left == right
    assert left["artifact_sha256"] == right["artifact_sha256"]
    assert left["gold_visible_to_classifier"] is False
    assert left["legal_article_bodies_visible_to_classifier"] is False
    assert left["llm_calls"] == 0
    assert left["retrieval_calls"] == 0


def test_source_and_runtime_denominators_are_exact():
    module = _module()
    report = module.build_report(manifest_sha256="frozen-test-manifest")
    summary = report["summary"]
    assert summary["cases"] == 61
    assert summary["declared_gold_articles"] == 85
    assert summary["corpus_present_gold_articles"] == 83
    for view in ("source_question_view", "runtime_question_view"):
        assert sum(row["cases"] for row in summary[view]["by_label"].values()) == 61
        assert sum(summary[view]["overlap_cases"].values()) == 61
