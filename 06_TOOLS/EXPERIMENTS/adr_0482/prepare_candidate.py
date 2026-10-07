"""Freeze the ADR-0480 source-first code and split FSC product/gold inputs."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / "04_EXPERIMENTS/ADR/ADR-0482-source-first-fsc-hard10-holdout"
CAND = ROOT / "02_BACKEND/lawrag/research/candidates/adr_0482/source-first-fsc-hard10"
OLD = ROOT / "02_BACKEND/lawrag/research/candidates/adr_0480/explicit-link"
PUBLIC = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0114-integrated-legal-research-state-machine-golden-61/artifacts/public-questions-run-001.json"
GOLD = ROOT / "04_EXPERIMENTS/LEGACY_ADR/ADR-0114-integrated-legal-research-state-machine-golden-61/artifacts/scoring-fixture-run-001.json"
BASE = ROOT / "04_EXPERIMENTS/ADR/ADR-0475-source-first-double-harness-wiring/fixture.json"
CASES = [f"fsc-hard-{number:03d}" for number in range(1, 11)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def tool(*args):
    subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(ROOT / "06_TOOLS/run_tool.py"), "adr_candidate.py", *args],
        cwd=ROOT,
        check=True,
    )


def main():
    parent = json.loads((OLD / "candidate.json").read_text())
    revision = next(row for row in parent["revisions"] if row["revision_id"] == "rev-002")
    metadata = {row["snapshot_path"]: row for row in parent["files"]}
    rows = []
    for frozen in revision["files"]:
        source = ROOT / frozen["frozen_path"]
        assert sha(source) == frozen["snapshot_sha256"]
        rows.append({**frozen, "target_path": metadata[frozen["snapshot_path"]]["target_path"]})

    if not (CAND / "candidate.json").is_file():
        present = [row for row in rows if (ROOT / row["target_path"]).is_file()]
        absent = [row for row in rows if not (ROOT / row["target_path"]).is_file()]
        args = [
            "snapshot", "--adr", str(ADR), "--candidate-id", "source-first-fsc-hard10",
            "--experiment-id", "ADR-0482-experiment-v1", "--arm-id", "source-first", "--run-id", "run-001",
        ]
        for row in present:
            args += ["--source", row["target_path"]]
        tool(*args)
        for row in rows:
            destination = CAND / "snapshot" / row["target_path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / row["frozen_path"], destination)
        for row in absent:
            tool("register", str(CAND), "--target", row["target_path"], "--upstream-state", "absent")
    current = json.loads((CAND / "candidate.json").read_text())
    if not current.get("revisions"):
        tool("freeze", str(CAND))
    tool("validate", str(CAND))

    public = json.loads(PUBLIC.read_text())
    gold = json.loads(GOLD.read_text())
    base = json.loads(BASE.read_text())
    public_by_id = {row["case_id"]: row for row in public["cases"]}
    gold_by_id = {row["case_id"]: row for row in gold["cases"]}
    assert all(case_id in public_by_id and case_id in gold_by_id for case_id in CASES)
    product = {
        "schema_version": "fsc-hard10-product-v1",
        "generation": base["generation"],
        "public_scope_document_ids": base["public_scope_document_ids"],
        "source_path": str(PUBLIC.relative_to(ROOT)),
        "source_sha256": sha(PUBLIC),
        "cases": [
            {
                "case_id": case_id,
                "question": public_by_id[case_id]["question"],
                "answer_as_of": public_by_id[case_id]["answer_as_of"],
                "current_as_of": public_by_id[case_id]["current_as_of"],
            }
            for case_id in CASES
        ],
    }
    scoring = {
        "schema_version": "fsc-hard10-gold-v1",
        "source_path": str(GOLD.relative_to(ROOT)),
        "source_sha256": sha(GOLD),
        "product_access": "forbidden-before-products-complete",
        "cases": [gold_by_id[case_id] for case_id in CASES],
    }
    write(ADR / "product-cases.json", product)
    write(ADR / "gold-cases.json", scoring)
    print(json.dumps({"candidate_files": len(rows), "cases": CASES}, ensure_ascii=False))


if __name__ == "__main__":
    main()
