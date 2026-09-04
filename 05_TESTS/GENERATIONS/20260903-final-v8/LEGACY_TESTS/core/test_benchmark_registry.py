import hashlib
import json
from pathlib import Path

from scripts.benchmark_registry import ROOT, validate_registry


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _combined(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _fixture(root: Path) -> dict[str, Path]:
    source = root / "data/source.json"
    artifact = root / "artifacts/result.json"
    adr = root / "docs/adr/ADR-0001/실험/manifest.json"
    _write(source, {"cases": [{"id": "c1"}]})
    _write(artifact, {"correct": 1})
    _write(adr, {
        "experiment_id": "exp-1",
        "design": {"arms": [{"id": "candidate"}]},
    })
    benchmark_id = "fixture-benchmark"
    run_path = root / f"benchmarks/{benchmark_id}/runs/run-001.json"
    run = {
        "schema_version": "benchmark-run-v1",
        "benchmark_id": benchmark_id,
        "benchmark_version": 1,
        "run_id": "run-001",
        "status": "complete",
        "adr_ref": {
            "manifest_path": str(adr.relative_to(root)).replace("\\", "/"),
            "manifest_sha256": _sha(adr),
            "experiment_id": "exp-1",
            "arm_id": "candidate",
        },
        "artifacts": [{
            "role": "summary",
            "path": str(artifact.relative_to(root)).replace("\\", "/"),
            "sha256": _sha(artifact),
            "bytes": artifact.stat().st_size,
        }],
        "metrics": {"correct": 1},
    }
    _write(run_path, run)
    benchmark_path = root / f"benchmarks/{benchmark_id}/benchmark.json"
    benchmark = {
        "schema_version": "benchmark-v1",
        "benchmark_id": benchmark_id,
        "version": 1,
        "title": "fixture",
        "status": "active",
        "owner": "test",
        "benchmark_class": "final_answer_quality",
        "specializations": ["question_only", "product_isolated"],
        "purpose": "test",
        "decision_eligible": False,
        "comparability_key": "fixture/v1",
        "dataset": {
            "name": "fixture",
            "case_count": 1,
            "combined_sha256": _combined([source]),
            "sources": [{
                "path": str(source.relative_to(root)).replace("\\", "/"),
                "sha256": _sha(source),
                "bytes": source.stat().st_size,
                "case_count": 1,
            }],
        },
        "input_contract": {},
        "scoring_contract": {},
        "isolation_contract": {},
        "adr_links": [{
            "relation": "execution_provenance",
            "record_path": str(adr.relative_to(root)).replace("\\", "/"),
            "record_sha256": _sha(adr),
            "experiment_id": "exp-1",
            "arm_id": "candidate",
        }],
        "runs": [{
            "run_id": "run-001",
            "path": str(run_path.relative_to(root)).replace("\\", "/"),
            "sha256": _sha(run_path),
            "bytes": run_path.stat().st_size,
            "status": "complete",
        }],
        "limitations": [],
    }
    _write(benchmark_path, benchmark)
    registry = {
        "schema_version": "benchmark-registry-v1",
        "benchmarks": [{
            "benchmark_id": benchmark_id,
            "version": 1,
            "status": "active",
            "benchmark_class": "final_answer_quality",
            "specializations": ["question_only", "product_isolated"],
            "manifest_path": str(benchmark_path.relative_to(root)).replace("\\", "/"),
            "manifest_sha256": _sha(benchmark_path),
            "manifest_bytes": benchmark_path.stat().st_size,
            "latest_run_id": "run-001",
        }],
    }
    _write(root / "benchmarks/registry.json", registry)
    return {"source": source, "artifact": artifact, "adr": adr,
            "run": run_path, "benchmark": benchmark_path}


def test_repository_benchmark_registry_is_valid():
    report = validate_registry(ROOT)
    assert report["ok"], report["errors"]


def test_validator_accepts_complete_fixture(tmp_path):
    _fixture(tmp_path)
    report = validate_registry(tmp_path)
    assert report["ok"], report["errors"]


def test_validator_rejects_unknown_adr_arm(tmp_path):
    paths = _fixture(tmp_path)
    run = json.loads(paths["run"].read_text("utf-8"))
    run["adr_ref"]["arm_id"] = "missing"
    _write(paths["run"], run)
    report = validate_registry(tmp_path)
    assert not report["ok"]
    assert any("unknown ADR arm" in error for error in report["errors"])


def test_validator_rejects_artifact_hash_drift(tmp_path):
    paths = _fixture(tmp_path)
    paths["artifact"].write_text("tampered\n", "utf-8")
    report = validate_registry(tmp_path)
    assert not report["ok"]
    assert any("sha256 mismatch" in error for error in report["errors"])


def test_validator_rejects_orphan_benchmark(tmp_path):
    _fixture(tmp_path)
    _write(tmp_path / "benchmarks/orphan/benchmark.json", {})
    report = validate_registry(tmp_path)
    assert not report["ok"]
    assert any("orphan benchmark manifest" in error for error in report["errors"])

