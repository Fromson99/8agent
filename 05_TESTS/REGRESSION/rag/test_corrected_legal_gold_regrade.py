from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)


def _module():
    path = ROOT / "06_TOOLS/EXPERIMENTS/EVALUATION/regrade_corrected_legal_gold.py"
    spec = importlib.util.spec_from_file_location("corrected_legal_gold_regrade", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_corrected_regrade_contract_and_known_results():
    result = _module().build()
    assert result["corrected_denominator"] == {
        "cases": 61,
        "decisive_instances": 90,
        "companion_instances": 22,
        "answer_time_instances": 15,
    }
    assert len(result["impact_ledger"]) == 18
    assert len({row["adr_id"] for row in result["impact_ledger"]}) == 18
    assert len(result["retrieval_regrades"]) == 12
    by_id = {row["adr_id"]: row for row in result["retrieval_regrades"]}
    assert by_id["ADR-0061"]["arms"]["baseline"]["decisive_article_hits"] == 10
    assert by_id["ADR-0064"]["arms"]["baseline"]["decisive_article_hits"] == 72
    assert by_id["ADR-0064"]["arms"]["feedback-explore"]["decisive_article_hits"] == 66
    assert by_id["ADR-0073"]["arms"]["verified-add-only"]["decisive_article_hits"] == 76


def test_semantic_coordinate_survives_but_stale_node_is_detected():
    audit = _module().build()["semantic_seed_audit"]
    assert audit["coordinates"] == 14
    assert audit["semantic_coordinate_matches"] == 14
    assert audit["exact_current_doc_node_matches"] == 13
    assert audit["stale_coordinates"] == [{
        "case_id": "cm-048",
        "law": "상법",
        "article": "제416조",
        "old_doc_id": "ec9179e002e9c347",
        "old_node": "1662",
        "current_doc_id": "7bbe815ff43b6635",
        "current_node": "1686",
        "reason": "same-legal-coordinate-stale-document-version",
    }]


def test_frozen_v1_hashes_remain_immutable():
    assert _module().build()["immutability"] == {
        "cm_v1_sha256": "d3e4f658d8c9abb06244557b669d37d63b0e6fcc879059506e3b462619bcc18d",
        "fsc_v1_sha256": "4373659368de7a81b7e9ee48233c8b317d863db4e5c4827f4346d09281b3d7f8",
    }
