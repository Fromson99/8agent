from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
SCRIPT = ROOT / "06_TOOLS/LEGACY_SCRIPTS/rag_latent_discovery_pool_10.py"
ADR = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0087-latent-discovery-pool-stage-ledger"


def _module():
    spec = importlib.util.spec_from_file_location("latent_pool_runner", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_dataset_is_exactly_ten_cases_and_fourteen_gold_articles():
    module = _module()
    dataset = module._load_dataset()
    assert len(dataset["cases"]) == 10
    assert sum(
        article.get("corpus_status") == "present"
        for case in dataset["cases"]
        for article in case["expected_articles"]
    ) == 14


def test_manifest_declares_complete_topological_stage_plans():
    manifest = json.loads((ADR / "실험/manifest.json").read_text(encoding="utf-8"))
    stage_plans = manifest["design"]["retrieval_stage_plan"]["stages_by_arm"]
    assert set(stage_plans) == {
        "baseline", "semantic-seed-lattice", "seed-residual-discovery"
    }
    for _arm, stages in stage_plans.items():
        seen = set()
        assert stages[0]["kind"] == "source"
        assert stages[-1]["kind"] == "present"
        for stage in stages:
            assert set(stage["parent_stage_ids"]) <= seen
            seen.add(stage["stage_id"])


def test_product_discovery_api_has_no_gold_or_reference_answer_parameter():
    source = (Path(__import__("lawrag").__file__).resolve().parent / "core/rag/latent_discovery_pool.py").read_text(encoding="utf-8")
    signatures = [
        line for line in source.splitlines()
        if line.startswith("def run_") or line.startswith("def retrieve_channels")
    ]
    assert signatures
    assert all("gold" not in line and "reference_answer" not in line for line in signatures)
