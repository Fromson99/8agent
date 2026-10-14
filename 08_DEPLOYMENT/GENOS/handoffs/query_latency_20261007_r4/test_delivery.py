"""Run the actual shipped TXT, ZIP installer, generation gate and local push."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest

from conftest import term_glossary  # noqa: F401 - fixture dependency
from test_compact_v2_rag import structured_generation  # noqa: F401

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PARENT = OUT.parent / "system_logging_20261007_r1"
NAME = "GENOS_QUERY_LATENCY_20261007_R4"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def seed(root):
    root.mkdir()
    record = json.loads((PARENT / "HANDOFF.json").read_text())
    with zipfile.ZipFile(PARENT / (record["version"] + ".zip")) as archive:
        payload = {row["path"]: archive.read(row["path"])
                   for row in json.loads(archive.read("CODE_MANIFEST.json"))["files"]}
    for name, raw in payload.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return payload


def hashes(root):
    return {str(path.relative_to(root)): sha(path.read_bytes()) for path in root.rglob("*") if path.is_file()}


def run(tmp_path, root, mode, generation, *, chat_mode="integrated", okay=True, delivery=OUT, blocked=False):
    nfs = tmp_path / "nfs"
    if blocked:
        nfs.write_text("synthetic NFS unavailable")
    env = {**os.environ, "GENOS_DEV": str(root), "GENOS_PYTHON_DIR": str(ROOT / ".venv/bin"),
           "GENOS_SYSTEM_LOG_DIR": str(nfs), "GENOS_LOG_SPOOL_DIR": str(tmp_path / "spool"),
           "GENOS_SYSTEM_LOG_ENABLED": "1", "GENOS_MAIN_MODE": chat_mode,
           "GENOS_AUTO_WARMUP": "0", "AD_WORKER_ENABLED": "0", "GENOS_CHAT_TRANSPORT": "json",
           "PYTHONPATH": str(root / "02_BACKEND"), "LAWRAG_WORKSPACE_ROOT": str(root),
           "LAWRAG_TOOL_WORKSPACE_ROOT": str(root)}
    env.pop("GENOS_HANDOFF_LOG_DIR", None)
    env.pop("GENOS_LOG_RUN_ID", None)
    done = subprocess.run(["bash", str(delivery / (NAME + "_APPLY.txt")), mode, str(generation)],
                          env=env, cwd=root, capture_output=True, text=True, timeout=90)
    assert (done.returncode == 0) == okay, done.stdout + done.stderr
    assert "GENOS_SYSTEM_LOG_RESULT" in done.stdout
    return done


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_inventory_working_bytes_and_standalone_scripts():
    record = json.loads((OUT / "HANDOFF.json").read_text())
    archive_path = OUT / (NAME + ".zip")
    assert sha(archive_path.read_bytes()) == record["code_zip_sha256"]
    assert sha((OUT / (NAME + "_APPLY.txt")).read_bytes()) == record["apply_txt_sha256"]
    assert json.loads((ROOT / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json").read_text()) == record["selected_local_baseline"]
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read("CODE_MANIFEST.json"))
        assert len(manifest["files"]) == record["code_files"] == 307
        excluded = {row["path"] for row in manifest["scope"]["unrelated_working_drift_preserved_excluded"]}
        for row in manifest["files"]:
            raw = archive.read(row["path"])
            assert sha(raw) == row["sha256"] and len(raw) == row["bytes"]
            if row["path"] not in excluded:
                assert raw == (ROOT / row["path"]).read_bytes(), row["path"]
            if row["path"].endswith(".py"):
                ast.parse(raw, feature_version=(3, 10) if "/workflow/" in row["path"] else (3, 11))
    subprocess.run(["bash", "-n", str(OUT / (NAME + "_APPLY.txt"))], check=True)
    workflow = (OUT / (NAME + "_WORKFLOW_PASTE_ALL.txt")).read_bytes()
    ast.parse(workflow, feature_version=(3, 10))
    assert sha(workflow) == record["workflow_txt_sha256"]



@pytest.mark.parametrize('mode',['workflow','integrated'])
def test_apply_repeat_verify_rollback_and_data_preservation(tmp_path, structured_generation, mode):
    root = tmp_path / "DEV"
    before = seed(root)
    state = root / "90_RUNTIME/existing-state.sqlite"
    state.parent.mkdir()
    state.write_bytes(b"preserved-state")
    original_data = hashes(structured_generation)
    run(tmp_path, root, "check", structured_generation, chat_mode=mode)
    run(tmp_path, root, "apply", structured_generation, chat_mode=mode)
    run(tmp_path, root, "apply", structured_generation, chat_mode=mode)
    result = run(tmp_path, root, "verify", structured_generation, chat_mode=mode)
    assert "QUERY_LATENCY_CONTRACT PASS " + mode in result.stdout
    with zipfile.ZipFile(OUT / (NAME + ".zip")) as archive:
        for name in archive.namelist():
            assert (root / name).read_bytes() == archive.read(name), name
    backup = next((root / "09_ARTIFACTS/BACKUPS/code-replacement").iterdir())
    run(tmp_path, root, "rollback", backup, chat_mode=mode)
    for name, raw in before.items():
        assert (root / name).read_bytes() == raw, name
    for name in json.loads((OUT / "CODE_MANIFEST.json").read_text())["scope"]["added_files"]:
        assert not (root / name).exists()
    assert hashes(structured_generation) == original_data and state.read_bytes() == b"preserved-state"
    assert len(list((tmp_path / "nfs").glob("*/deployment-artifacts/events.jsonl"))) == 5
    assert not list((tmp_path / "spool").glob("**/*.pending"))


def test_unknown_field_edit_is_preserved_and_original_error_reaches_nfs(tmp_path, structured_generation):
    root = tmp_path / "DEV"
    seed(root)
    target = root / "main.py"
    target.write_bytes(target.read_bytes() + b"\n# synthetic unknown field edit\n")
    before = hashes(root)
    result = run(tmp_path, root, "apply", structured_generation, okay=False)
    assert "Checkout changes preserved" in result.stderr and "main.py" in result.stdout
    assert hashes(root) == before
    stderr = "".join(path.read_text() for path in (tmp_path / "nfs").glob("*/*-stderr.log"))
    assert "Checkout changes preserved" in stderr and "Traceback (most recent call last)" in stderr


def test_zip_hash_failure_is_captured_before_any_code_install(tmp_path, structured_generation):
    root = tmp_path / "DEV"
    seed(root)
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    shutil.copyfile(OUT / (NAME + "_APPLY.txt"), delivery / (NAME + "_APPLY.txt"))
    (delivery / (NAME + ".zip")).write_bytes(b"synthetic corrupt ZIP")
    before = hashes(root)
    result = run(tmp_path, root, "check", structured_generation, delivery=delivery, okay=False)
    assert hashes(root) == before
    assert "Code ZIP hash mismatch" in result.stderr
    stderr = "".join(path.read_text() for path in (tmp_path / "nfs").glob("*/*-stderr.log"))
    assert "Code ZIP hash mismatch" in stderr


def test_nfs_failure_does_not_hide_check_result_and_retains_recoverable_spool(tmp_path, structured_generation):
    root = tmp_path / "DEV"
    seed(root)
    result = run(tmp_path, root, "check", structured_generation, blocked=True)
    assert "NFS_COMPLETE False" in result.stdout and "NFS_PENDING" in result.stderr
    pending = list((tmp_path / "spool").glob("**/*.pending"))
    assert pending
    assert b"SYSTEM_LOGGING_EXIT=0" in b"".join(path.read_bytes() for path in pending)


def test_same_checkout_gate_and_local_git_push(tmp_path, structured_generation):
    root = tmp_path / "DEV"
    seed(root)
    git(root, "init", "-q")
    git(root, "config", "user.name", "Synthetic logging validation")
    git(root, "config", "user.email", "validation@example.invalid")
    git(root, "add", "-f", ".")
    git(root, "commit", "-qm", "Synthetic latency R3 baseline")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    git(root, "remote", "add", "origin", str(remote))
    before = hashes(structured_generation)
    result = run(tmp_path, root, "all", structured_generation)
    assert "GENOS_RELEASE_GATE PASS" in result.stdout
    assert git(remote, "rev-parse", "HEAD") == git(root, "rev-parse", "HEAD")
    assert hashes(structured_generation) == before
    stdout = "".join(path.read_text() for path in (tmp_path / "nfs").glob("*/*-stdout.log"))
    assert "GENOS_RELEASE_GATE PASS" in stdout
    events = "".join(path.read_text() for path in (tmp_path / "nfs").glob("*/deployment-artifacts/events.jsonl"))
    assert '"code_serving_revision": "NOT_DEPLOYED"' in events


def test_editor_paste_embeds_logger_without_shared_modules(tmp_path):
    code = """import asyncio,sys,types
from pathlib import Path
class NoSharedLogger:
 def find_spec(self,fullname,path=None,target=None):
  if fullname=='genos_diagnostics': raise ModuleNotFoundError('no shared logger')
sys.meta_path.insert(0,NoSharedLogger())
module=types.ModuleType('field_workflow')
exec(compile(Path(sys.argv[1]).read_bytes(),sys.argv[1],'exec'),module.__dict__)
result=asyncio.run(module.run({'API_TYPE':'WORKFLOW_SETTINGS','request_id':'paste-test'}))
assert result['workflow_settings']['socketio_enabled'] is False
print('STANDALONE_LOGGER PASS')
"""
    done = subprocess.run([str(ROOT / ".venv/bin/python"), "-c", code, str(OUT / (NAME + "_WORKFLOW_PASTE_ALL.txt"))],
        env={**os.environ, "GENOS_SYSTEM_LOG_DIR": str(tmp_path / "nfs"), "GENOS_LOG_SPOOL_DIR": str(tmp_path / "spool"),
             "GENOS_SYSTEM_LOG_ENABLED": "1", "GENOS_LOG_RUN_ID": "paste-test", "PYTHONPATH": "",
             "GENOS_BASE_URL": "http://fixture.invalid", "GENOS_CODESERVING_ID": "synthetic",
             "GENOS_CODESERVING_TOKEN": "synthetic-token"},
        cwd=tmp_path, capture_output=True, timeout=10)
    assert done.returncode == 0, done.stderr
    assert b"STANDALONE_LOGGER PASS" in done.stdout
    assert list((tmp_path / "nfs/paste-test").glob("*-workflow.events.raw.jsonl"))


def test_new_remote_txt_uses_actual_apply_filename_and_preserves_origin(tmp_path,structured_generation):
    root=tmp_path/'DEV';seed(root)
    git(root,'init','-q');git(root,'config','user.name','Resident data validation')
    git(root,'config','user.email','validation@example.invalid');git(root,'add','-f','.')
    git(root,'commit','-qm','Synthetic predecessor')
    old=tmp_path/'old.git';new=tmp_path/'new.git'
    subprocess.run(['git','init','--bare','-q',str(old)],check=True)
    subprocess.run(['git','init','--bare','-q',str(new)],check=True)
    git(root,'remote','add','origin',str(old))
    run(tmp_path,root,'apply',structured_generation)
    env={**os.environ,'GENOS_DEV':str(root),'GENOS_PYTHON_DIR':str(ROOT/'.venv/bin'),
         'GENOS_GENERATION':str(structured_generation),'GENOS_NEW_REMOTE_URL':str(new),
         'GENOS_SYSTEM_LOG_DIR':str(tmp_path/'nfs'),'GENOS_LOG_SPOOL_DIR':str(tmp_path/'spool'),
         'GENOS_SYSTEM_LOG_ENABLED':'1','GENOS_MAIN_MODE':'integrated','GENOS_AUTO_WARMUP':'0',
         'AD_WORKER_ENABLED':'0','GENOS_CHAT_TRANSPORT':'json','PYTHONPATH':str(root/'02_BACKEND'),
         'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root)}
    env.pop('GENOS_LOG_RUN_ID',None);env.pop('GENOS_HANDOFF_LOG_DIR',None)
    done=subprocess.run(['bash',str(OUT/(NAME+'_PUSH_NEW_REMOTE.txt'))],cwd=root,env=env,
                        capture_output=True,text=True,timeout=120)
    assert done.returncode==0,done.stdout+done.stderr
    assert git(root,'remote','get-url','origin')==str(old)
    assert git(new,'rev-parse','refs/heads/main')==git(root,'rev-parse','HEAD')
