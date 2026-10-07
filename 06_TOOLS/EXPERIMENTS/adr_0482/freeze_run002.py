"""Freeze run-002 and append it without rewriting the failed run-001 artifacts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / "04_EXPERIMENTS/ADR/ADR-0482-source-first-fsc-hard10-holdout"
CAND = ROOT / "02_BACKEND/lawrag/research/candidates/adr_0482/source-first-fsc-hard10-run002"
RUNNER = ROOT / "06_TOOLS/EXPERIMENTS/adr_0482/run_holdout_run002.py"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    target = ADR / "artifacts/frozen-design-run-002.json"
    if target.exists():
        raise RuntimeError("run-002 design already frozen")
    manifest = json.loads((ADR / "실험/manifest.json").read_text())
    product = json.loads((ADR / "product-cases.json").read_text())
    generation = ROOT / product["generation"]
    candidate = json.loads((CAND / "candidate.json").read_text())
    revision = next(row for row in candidate["revisions"] if row["revision_id"] == "rev-001")
    paths = [ADR / "PLAN.md", ADR / "product-cases.json", ADR / "gold-cases.json", CAND / "candidate.json", generation / "manifest.json", ROOT / "00_SYSTEM/EXPERIMENT_MODEL_POLICY.json", ROOT / "00_SYSTEM/PIPELINE.json", RUNNER, ROOT / "06_TOOLS/EXPERIMENTS/adr_0482/run_holdout.py"]
    original = json.loads((ADR / "artifacts/frozen-design.json").read_text())
    design = {**original, "schema_version": "adr0482-frozen-design-run002-v1", "run_id": "run-002", "change_from_run001": "Only add GeminiProvider.record_local and use a new output root/candidate binding.", "file_hashes": {str(path.relative_to(ROOT)): sha(path) for path in paths}}
    write(target, design)
    for run in manifest["runs"]:
        if run["id"] == "run-001":
            run["status"] = "failed"
            run["notes"] = "Interrupted after runner adapter defect; partial artifacts preserved, not scored."
    run2 = next(run for run in manifest["runs"] if run["id"] == "run-002")
    run2.update(status="planned", selection_rule=original["selection_rule"])
    manifest["design"]["code_isolation"]["candidates"].append({
        "candidate_id": "source-first-fsc-hard10-run002", "experiment_id": manifest["experiment_id"],
        "arm_id": "source-first", "run_ids": ["run-002"], "manifest_path": str((CAND / "candidate.json").relative_to(ROOT)),
        "manifest_sha256": sha(CAND / "candidate.json"), "revision_id": revision["revision_id"],
        "revision_sha256": revision["revision_sha256"], "runner_path": str(RUNNER.relative_to(ROOT)), "runner_sha256": sha(RUNNER),
    })
    write(ADR / "실험/manifest.json", manifest)
    print("run-002 frozen; run-001 preserved as failed")


if __name__ == "__main__":
    main()
