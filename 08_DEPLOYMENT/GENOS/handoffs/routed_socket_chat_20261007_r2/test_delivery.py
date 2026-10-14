"""Verify the exact cumulative ZIP and field TXT without contacting GENOS."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile
import pytest

from conftest import term_glossary  # noqa: F401 - fixture dependency
from test_compact_v2_rag import structured_generation  # noqa: F401 - fixture


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PARENT = OUT.parent / "routed_socket_chat_20261007_r1"
NAME = "GENOS_ROUTED_SOCKET_CHAT_20261007_R2"
ZIP = OUT / (NAME + ".zip")
SCRIPT = OUT / (NAME + "_APPLY.txt")
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def seed(root):
    root.mkdir()
    record = json.loads((PARENT / "HANDOFF.json").read_text())
    with zipfile.ZipFile(PARENT / (record["version"] + ".zip")) as archive:
        old = {row["path"]: archive.read(row["path"])
               for row in json.loads(archive.read("CODE_MANIFEST.json"))["files"]}
    for name, raw in old.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return old


def hashes(root):
    return {str(path.relative_to(root)): sha(path.read_bytes())
            for path in root.rglob("*") if path.is_file()}


def run(root, temp, mode, selected, ok=True, chat_mode="integrated"):
    env = {**os.environ, "GENOS_DEV": str(root), "GENOS_PYTHON_DIR": str(ROOT / ".venv/bin"),
           "GENOS_HANDOFF_LOG_DIR": str(temp / "logs"), "GENOS_MAIN_MODE": chat_mode,
           "PYTHONPATH": str(root / "02_BACKEND"), "LAWRAG_WORKSPACE_ROOT": str(root),
           "LAWRAG_TOOL_WORKSPACE_ROOT": str(root), "GENOS_AUTO_WARMUP": "0",
           "AD_WORKER_ENABLED": "0"}
    done = subprocess.run(["bash", str(SCRIPT), mode, str(selected)],
                          env=env, capture_output=True, text=True, timeout=120)
    assert (done.returncode == 0) == ok, done.stdout + done.stderr
    assert "ROUTED_CHAT_EXIT=" in done.stdout
    return done


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_exact_296_files_selected_pointer_and_field_syntax():
    record = json.loads((OUT / "HANDOFF.json").read_text())
    assert sha(ZIP.read_bytes()) == record["code_zip_sha256"]
    assert sha(SCRIPT.read_bytes()) == record["apply_txt_sha256"]
    pointer = json.loads((ROOT / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json").read_text())
    assert pointer == record["selected_local_baseline"] and pointer["generation"] == 44
    with zipfile.ZipFile(ZIP) as archive:
        raw = archive.read("CODE_MANIFEST.json")
        assert sha(raw) == record["code_manifest_sha256"]
        manifest = json.loads(raw)
        assert len(manifest["files"]) == 296
        assert manifest["socket_chat"]["default_mode"] == "workflow"
        for row in manifest["files"]:
            source = archive.read(row["path"])
            assert len(source) == row["bytes"] and sha(source) == row["sha256"]
            assert source == (ROOT / row["path"]).read_bytes(), row["path"]
            if row["path"].endswith(".py"):
                compile(source, row["path"], "exec")
                ast.parse(source, feature_version=(3, 10) if "/workflow/" in row["path"] else (3, 11))
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    loader = SCRIPT.read_text().split("<<'LOADER_PY'\n", 1)[1].rsplit("\nLOADER_PY", 1)[0]
    ast.parse(loader, feature_version=(3, 11))


@pytest.mark.parametrize("chat_mode", ["workflow", "integrated"])
def test_apply_repeat_mode_verify_and_rollback(tmp_path, structured_generation, chat_mode):
    root = tmp_path / "physical"
    prior = seed(root)
    alias = tmp_path / "DEV"
    alias.symlink_to(root, target_is_directory=True)
    state = root / "90_RUNTIME/existing-state.sqlite"
    state.parent.mkdir()
    state.write_bytes(b"preserved-state")
    data = hashes(structured_generation)
    run(alias, tmp_path, "check", structured_generation)
    run(alias, tmp_path, "apply", structured_generation)
    run(alias, tmp_path, "apply", structured_generation)
    verified = run(alias, tmp_path, "verify", structured_generation, chat_mode=chat_mode)
    assert "ROUTED_CHAT_CONTRACT PASS " + chat_mode in verified.stdout
    with zipfile.ZipFile(ZIP) as archive:
        for name in archive.namelist():
            assert (root / name).read_bytes() == archive.read(name)
    assert hashes(structured_generation) == data and state.read_bytes() == b"preserved-state"
    backup = next((root / "09_ARTIFACTS/BACKUPS/code-replacement").iterdir())
    run(alias, tmp_path, "rollback", backup)
    for name, raw in prior.items():
        assert (root / name).read_bytes() == raw, name
    for name in ("main_workflow.py", "07_DOCS/REFERENCE/OPERATIONS/GENOS_ROUTED_CHAT_MODES_20261007_R2.md"):
        assert not (root / name).exists()
    assert hashes(structured_generation) == data and state.read_bytes() == b"preserved-state"


@pytest.mark.parametrize("chat_mode", ["workflow", "integrated"])
def test_same_checkout_gate_and_local_push(tmp_path, structured_generation, chat_mode):
    root = tmp_path / "DEV"
    prior = seed(root)
    git(root, "init", "-q")
    git(root, "config", "user.name", "Routed chat validation")
    git(root, "config", "user.email", "validation@example.invalid")
    git(root, "add", "-f", ".")
    git(root, "commit", "-qm", "Synthetic selected predecessor")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    git(root, "remote", "add", "origin", str(remote))
    data = hashes(structured_generation)
    result = run(root, tmp_path, "all", structured_generation, chat_mode=chat_mode)
    assert "GENOS_RELEASE_GATE PASS" in result.stdout
    assert "ROUTED_CHAT_CONTRACT PASS " + chat_mode in result.stdout
    assert git(remote, "rev-parse", "HEAD") == git(root, "rev-parse", "HEAD")
    assert not git(root, "status", "--porcelain", "--untracked-files=no")
    assert hashes(structured_generation) == data
    events = [json.loads(line) for line in (tmp_path / "logs/events.jsonl").read_text().splitlines()]
    assert events[-1]["code_serving_revision"] == "NOT_DEPLOYED"
    assert events[-1]["chat_binding"] == "NOT_SELECTED"


def test_unknown_field_edit_is_preserved(tmp_path, structured_generation):
    root = tmp_path / "DEV"
    seed(root)
    path = root / "08_DEPLOYMENT/GENOS/start_sse.py"
    path.write_bytes(path.read_bytes() + b"\n# unknown local field edit\n")
    before = hashes(root)
    run(root, tmp_path, "apply", structured_generation, ok=False)
    assert hashes(root) == before


def test_upgrade_before_socket_r1_preserves_completed_main(tmp_path, structured_generation):
    root = tmp_path / 'DEV'; root.mkdir()
    predecessor = OUT.parent / 'investigation_completion_20261007_r1'
    record = json.loads((predecessor / 'HANDOFF.json').read_text())
    with zipfile.ZipFile(predecessor / (record['version'] + '.zip')) as archive:
        old = {row['path']: archive.read(row['path'])
               for row in json.loads(archive.read('CODE_MANIFEST.json'))['files']}
    for name, raw in old.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    before = hashes(structured_generation)
    run(root, tmp_path, 'check', structured_generation, chat_mode='workflow')
    run(root, tmp_path, 'apply', structured_generation, chat_mode='workflow')
    done = run(root, tmp_path, 'verify', structured_generation, chat_mode='workflow')
    assert 'ROUTED_CHAT_CONTRACT PASS workflow' in done.stdout
    assert hashes(structured_generation) == before
    # Every generation-44 file except the existing startup helper is preserved.
    for name, raw in old.items():
        if name != '08_DEPLOYMENT/GENOS/start_sse.py':
            assert (root / name).read_bytes() == raw


def test_unchanged_workflow_txt_and_execution_scripts():
    with zipfile.ZipFile(ZIP) as archive:
        assert (OUT / (NAME + '_WORKFLOW_PASTE_ALL.txt')).read_bytes() == archive.read(
            '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    for suffix in ('_APPLY.txt', '_PUSH_NEW_REMOTE.txt'):
        subprocess.run(['bash', '-n', str(OUT / (NAME + suffix))], check=True)
