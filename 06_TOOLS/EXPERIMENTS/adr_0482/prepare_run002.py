"""Create an identical frozen candidate binding for the non-overwriting run-002."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / "04_EXPERIMENTS/ADR/ADR-0482-source-first-fsc-hard10-holdout"
OLD = ROOT / "02_BACKEND/lawrag/research/candidates/adr_0482/source-first-fsc-hard10"
NEW = ROOT / "02_BACKEND/lawrag/research/candidates/adr_0482/source-first-fsc-hard10-run002"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tool(*args):
    subprocess.run([str(ROOT / ".venv/bin/python"), str(ROOT / "06_TOOLS/run_tool.py"), "adr_candidate.py", *args], cwd=ROOT, check=True)


def main():
    manifest_path = ADR / "실험/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if not any(run["id"] == "run-002" for run in manifest["runs"]):
        manifest["runs"].append({
            "id": "run-002",
            "purpose": "Paired holdout after fixing only the missing baseline receipt adapter",
            "arm_ids": ["baseline", "source-first"],
            "selection_rule": "All ten sealed FSC hard cases; no exclusions.",
            "status": "planned",
            "parent_run_id": "run-001",
            "artifact_path": "04_EXPERIMENTS/ADR/ADR-0482-source-first-fsc-hard10-holdout/artifacts/run-002/results.json",
            "sha256": "PENDING",
        })
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    old = json.loads((OLD / "candidate.json").read_text())
    revision = next(row for row in old["revisions"] if row["revision_id"] == "rev-001")
    metadata = {row["snapshot_path"]: row for row in old["files"]}
    rows = []
    for frozen in revision["files"]:
        source = ROOT / frozen["frozen_path"]
        assert sha(source) == frozen["snapshot_sha256"]
        rows.append({**frozen, "target_path": metadata[frozen["snapshot_path"]]["target_path"]})
    present = [row for row in rows if (ROOT / row["target_path"]).is_file()]
    absent = [row for row in rows if not (ROOT / row["target_path"]).is_file()]
    args = ["snapshot", "--adr", str(ADR), "--candidate-id", "source-first-fsc-hard10-run002", "--experiment-id", "ADR-0482-experiment-v1", "--arm-id", "source-first", "--run-id", "run-002"]
    for row in present:
        args += ["--source", row["target_path"]]
    tool(*args)
    for row in rows:
        destination = NEW / "snapshot" / row["target_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / row["frozen_path"], destination)
    for row in absent:
        tool("register", str(NEW), "--target", row["target_path"], "--upstream-state", "absent")
    tool("freeze", str(NEW))
    tool("validate", str(NEW))


if __name__ == "__main__":
    main()
