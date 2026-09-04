from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/rag_semantic_operation_seed_golden_10.py"
MANIFEST = ROOT / "docs/adr/ADR-0085-semantic-operation-seed-golden-10/실험/manifest.json"


def _module():
    spec = importlib.util.spec_from_file_location("semantic_seed_golden_10", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build():
    module = _module()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    suite, audit = module.build_suite(manifest, manifest_sha256="frozen-test-manifest")
    return module, suite, audit


def test_exact_case_quota_and_source_lineage_are_inherited():
    _module_value, suite, audit = _build()
    assert suite["counts"] == {
        "cases": 10,
        "cm_actual_work_cases": 9,
        "fsc_actual_reply_cases": 1,
        "expected_articles": 14,
        "corpus_exact_coordinates": 14,
    }
    assert audit["summary"]["source_quota"] == {"cm": 9, "fsc-hard": 1}
    assert audit["summary"]["reference_answers_inherited"] == 10
    assert audit["summary"]["expected_article_sets_inherited"] == 10
    assert len({case["id"] for case in suite["cases"]}) == 10
    assert len({case["question"] for case in suite["cases"]}) == 10


def test_runtime_questions_have_no_authority_or_canonical_term_leakage():
    _module_value, suite, audit = _build()
    assert audit["summary"]["authority_leaks"] == 0
    assert audit["summary"]["canonical_term_leaks"] == 0
    for case in suite["cases"]:
        assert case["question"].endswith("?")
        assert "업무 문맥" not in case["question"]
        assert case["surface_audit"]["authority_absent"] is True
        assert case["surface_audit"]["canonical_operation_term_absent"] is True
        assert case["surface_audit"]["requires_semantic_operation_seed"] is True
        for term in case["surface_audit"]["canonical_terms"]:
            assert term not in case["question"]


def test_coordinates_are_exact_and_build_is_deterministic():
    module, suite, audit = _build()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    suite_again, audit_again = module.build_suite(
        manifest, manifest_sha256="frozen-test-manifest"
    )
    assert suite == suite_again
    assert audit == audit_again
    assert audit["summary"]["exact_coordinates"] == 14
    assert all(
        coordinate["status"] == "exact"
        for row in audit["rows"]
        for coordinate in row["coordinate_receipt"]
    )
    assert module._sha256(module.CM_PATH) == module.CM_SHA256
    assert module._sha256(module.FSC_PATH) == module.FSC_SHA256
    assert module._combined_source_sha256() == module.COMBINED_SHA256
