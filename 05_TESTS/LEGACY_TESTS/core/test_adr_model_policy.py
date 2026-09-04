from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))

from scripts.adr_structure import (  # noqa: E402
    HAIKU_MODEL,
    OPUS_MODEL,
    SONNET_MODEL,
    scaffold_adr,
    validate_adr,
)


def _manifest(target: Path) -> tuple[Path, dict]:
    path = target / "실험" / "manifest.json"
    return path, json.loads(path.read_text("utf-8"))


def test_offline_sonnet_and_opus_judges_are_allowed(tmp_path: Path) -> None:
    sonnet = scaffold_adr(
        tmp_path, 161, "sonnet-judge", "Sonnet judge", "probe", [],
        judge_model=SONNET_MODEL)
    opus = scaffold_adr(
        tmp_path, 162, "opus-judge", "Opus judge", "probe", [],
        judge_model=OPUS_MODEL)

    assert validate_adr(sonnet) == []
    assert validate_adr(opus) == []


def test_strong_model_is_rejected_on_product_path(tmp_path: Path) -> None:
    target = scaffold_adr(tmp_path, 163, "product-policy", "Product policy", "probe", [])
    path, manifest = _manifest(target)
    manifest["llm_policy"]["llm_calls"][0]["model"] = OPUS_MODEL
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")

    errors = validate_adr(target)
    assert any("product LLM role" in error and HAIKU_MODEL in error for error in errors)


def test_offline_allowlist_and_call_class_are_closed(tmp_path: Path) -> None:
    target = scaffold_adr(tmp_path, 164, "closed-policy", "Closed policy", "probe", [])
    path, manifest = _manifest(target)
    manifest["llm_policy"]["llm_calls"][1]["model"] = "unapproved-model"
    manifest["llm_policy"]["llm_calls"].append({
        "role": "mystery", "class": "hybrid", "model": HAIKU_MODEL, "repeats": 1})
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")

    errors = validate_adr(target)
    assert any("unapproved model" in error for error in errors)
    assert any("invalid class" in error for error in errors)


def test_isolated_offline_answer_benchmark_allows_frozen_models(tmp_path: Path) -> None:
    target = scaffold_adr(
        tmp_path, 165, "offline-benchmark", "Offline answer benchmark", "probe", [])
    path, manifest = _manifest(target)
    policy = manifest["llm_policy"]
    policy["policy_version"] = "role-separated-v2"
    policy["offline_benchmark_candidate_models"] = [
        "qwen/qwen3.8-27b", "claude-sonnet-5"]
    policy["offline_benchmark_isolation"] = {
        "may_change_product_answer": False,
        "may_enter_product_context": False,
        "judge_only_use": True,
    }
    policy["llm_calls"] = [
        {"role": "qwen-answer", "class": "offline_benchmark_candidate",
         "model": "qwen/qwen3.8-27b", "repeats": 1},
        {"role": "judge", "class": "offline_evaluator",
         "model": OPUS_MODEL, "repeats": 1},
    ]
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")

    assert validate_adr(target) == []


def test_offline_answer_benchmark_rejects_unfrozen_model_and_wiring(tmp_path: Path) -> None:
    target = scaffold_adr(
        tmp_path, 166, "benchmark-isolation", "Benchmark isolation", "probe", [])
    path, manifest = _manifest(target)
    policy = manifest["llm_policy"]
    policy["policy_version"] = "role-separated-v2"
    policy["offline_benchmark_candidate_models"] = ["qwen/qwen3.8-27b"]
    policy["offline_benchmark_isolation"] = {
        "may_change_product_answer": False,
        "may_enter_product_context": False,
        "judge_only_use": True,
    }
    policy["llm_calls"] = [
        {"role": "candidate", "class": "offline_benchmark_candidate",
         "model": "unfrozen-model", "repeats": 1},
    ]
    readme_path = target / "README.md"
    readme_path.write_text(
        readme_path.read_text("utf-8").replace(
            "main_wiring: unchanged", "main_wiring: benchmark-wired"), "utf-8")
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")

    errors = validate_adr(target)
    assert any("unfrozen model" in error for error in errors)
    assert any("main_wiring=unchanged" in error for error in errors)
