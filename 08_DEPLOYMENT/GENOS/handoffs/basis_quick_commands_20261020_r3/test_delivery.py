"""Exact ZIP/TXT, actual sealed checkout/service startup on synthetic sources."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import zipfile
import pytest

from test_basis_discovery_skip import generation

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
AUDIT = ROOT / "09_ARTIFACTS/AUDITS/20261020-basis-structure-skip"


@pytest.mark.parametrize("all_bad", [False, True])
def test_exact_quick_zip_and_native_planning(tmp_path, generation, term_glossary, all_bad):
    from lawrag.pipeline.fulltext_stage import derive
    from lawrag.pipeline.search_selection import plan, activate
    from lawrag.pipeline.term_generation import build_generation
    # Create inconsistent parent/child spans in a NEW synthetic input, before the
    # normal generation/index build. Never edit hashes or published generations.
    raw = tmp_path / "raw.sqlite"
    with sqlite3.connect(raw) as db:
        db.execute("UPDATE source_unit SET parent_id='0' WHERE document_id='inside' AND unit_id='1'")
        if all_bad:
            value = json.loads(db.execute("SELECT json FROM source_unit WHERE document_id='inside2'").fetchone()[0])
            value["span"] = [0, 0]
            db.execute("UPDATE source_unit SET json=? WHERE document_id='inside2'", (json.dumps(value),))
    build_generation(raw, term_glossary, tmp_path / "malformed-built", serving=True)
    selected = tmp_path / "generation"
    derive(tmp_path / "malformed-built/generation", selected, workers=1)
    activate(plan(selected, latest=True))
    transfer = tmp_path / "transfer"
    transfer.mkdir()
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    base = HERE.with_name("basis_entry_fix_20261020_r1")
    source = ROOT / "09_ARTIFACTS/AUDITS/20261020-basis-entry-fix/validation-code"
    spec = json.loads((base / "PACKAGE.json").read_text())
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    for name, expected in spec["code"].items():
        assert sha(source / name) == expected
        target = checkout / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    for name in ("00_SYSTEM/WORKSPACE.json", "00_SYSTEM/WORKSPACE_SCHEMA.json"):
        if (source / name).exists() and not (checkout / name).exists():
            shutil.copyfile(source / name, checkout / name)
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    config = checkout / "00_SYSTEM/GENOS_SERVING_PATHS.json"
    config.write_text(json.dumps({"schema_version": "genos-serving-paths-v1",
        "selection": "operator-fixed", "generation": str(selected), "runtime": str(runtime),
        "generation_manifest_sha256": sha(selected / "manifest.json")}))
    with zipfile.ZipFile(base / "GENOS_BASIS_ENTRY_FIX_20261020_R1.zip") as z:
        z.extractall(transfer / "GENOS_BASIS_ENTRY_FIX_20261020_R1")
    archive = HERE / "GENOS_BASIS_QUICK_20261020_R3.zip"
    with zipfile.ZipFile(archive) as z:
        z.extractall(transfer)
    # Only emulate the NFS mount classification, never inject an application.
    modules = tmp_path / "fixture-modules"
    modules.mkdir()
    (modules / "sitecustomize.py").write_text(
        "import sys\n"
        f"sys.path.insert(0,{str(checkout / '02_BACKEND')!r})\n"
        "from semantic_runtime import state_sqlite\n"
        "state_sqlite.network_storage=lambda p: True\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith((
        "GENOS_", "SEMANTIC_", "LEGAL_AGENT_", "PYTHON", "LAWRAG_", "SOURCE_PROVIDER_",
        "WORKFLOW_", "OPEN_ROUTER", "OPENAI_", "ANTHROPIC_"))}
    env.update(PATH=str(ROOT / ".venv/bin") + os.pathsep + env["PATH"],
               PYTHONPATH=str(modules), PYTHONDONTWRITEBYTECODE="1",
               GENOS_SYSTEM_LOG_DIR=str(tmp_path / "system-logs"))
    trace = []
    def call(args, expected):
        command = ["bash", "./BASIS_RUN.txt", *args, "--root", str(checkout)]
        result = subprocess.run(command, cwd=transfer, env=env, capture_output=True,
                                text=True, timeout=60)
        trace.append({"args": args, "exit": result.returncode, "expected": expected,
                      "output": result.stdout + result.stderr})
        with gzip.open(AUDIT / f"NATIVE_DELIVERY_TRACE_{all_bad}.json.gz", "wt") as stream:
            json.dump(trace, stream, ensure_ascii=False)
        assert result.returncode == expected, (result.stdout + result.stderr)[-14000:]
        return result.stdout + result.stderr
    protected = {name: sha(checkout / name) for name in spec["code"]}
    assert '"status": "PASS"' in call(["check"], 0)
    # All uses the real catalog, explicit-ID plans, native service and model guard.
    output = call(["all"], 2 if all_bad else 1)
    assert ("BATCH_INTERNAL_MODEL" in output) is (not all_bad), output[-9000:]
    job = runtime / "basis-batch/pilot-review-user-all"
    all_plan = json.loads((job / "ALL_PLAN.json").read_text())
    assert all_plan["documents"] == 2
    assert len(all_plan["parts"]) == 1
    folder = job / "parts/part-00001"
    receipt = json.loads((folder / "STRUCTURE_CHECK.json").read_text())
    assert {d["document_id"] for d in receipt["failures"]} == ({"inside", "inside2"} if all_bad else {"inside"})
    assert any(d["message"] == "상위 구조의 범위가 하위를 포함하지 않습니다." for d in receipt["failures"])
    before = (folder / "STRUCTURE_CHECK.json").read_bytes()
    if not all_bad:
        child = json.loads((folder / "PLAN.json").read_text())
        assert child["selection_rule"] == "explicit-ids"
        assert [d["document_id"] for d in child["documents"]] == ["inside2"]
        assert child["candidate_storage"]["publication"] == "manual-review-only"
        before_plan = (folder / "PLAN.json").read_bytes()
    else:
        assert not (folder / "PLAN.json").exists() and not (folder / "STATE.json").exists()
    call(["all"], 2 if all_bad else 1)
    assert (folder / "STRUCTURE_CHECK.json").read_bytes() == before
    if not all_bad:
        assert (folder / "PLAN.json").read_bytes() == before_plan
    call(["status", "all"], 0)
    call(["report", "all"], 0)
    assert "inside" in (transfer / "basis-report-all/INDEX.html").read_text()
    assert "BASIS_STRUCTURE" in (transfer / "basis-report-all/INDEX.html").read_text()
    # Current manifest tampering is identified without weakening the gate.
    manifest = checkout / "02_BACKEND/ENGINES/legal_agent/6.0.0/retrieve.json"
    raw = manifest.read_bytes()
    manifest.write_bytes(raw + b"\n")
    try:
        assert '"status": "MISMATCH"' in call(["check"], 1)
        call(["all"], 1)
    finally:
        manifest.write_bytes(raw)
    assert {name: sha(checkout / name) for name in spec["code"]} == protected
    assert not (runtime / "basis-links/SQLITE_ENABLED.json").exists()
    (AUDIT / f"NATIVE_DELIVERY_{all_bad}.json").write_text(json.dumps({
        "status": "PASS", "commands": len(trace), "zip_sha256": sha(archive),
        "app_injection": False, "synthetic_sources_and_mount": True, "model_calls": 0,
        "all_documents": 2, "structure_failed": 2 if all_bad else 1,
        "research_blocked_at": None if all_bad else "BATCH_INTERNAL_MODEL",
        "actual_GENOS": False, "checkout_unchanged": True}, indent=2) + "\n")
