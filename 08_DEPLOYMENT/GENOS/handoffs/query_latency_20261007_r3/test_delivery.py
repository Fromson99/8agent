"""Verify timing/reuse handoff against disposable checkout and immutable data."""
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
PARENT = OUT.parent / "no_socket_chat_20261007_r3"
NAME = "GENOS_QUERY_LATENCY_20261007_R3"
ZIP = OUT / (NAME + ".zip")
SCRIPT = OUT / (NAME + "_APPLY.txt")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def seed(root, predecessor=PARENT):
    root.mkdir()
    record = json.loads((predecessor / "HANDOFF.json").read_text())
    with zipfile.ZipFile(predecessor / (record["version"] + ".zip")) as archive:
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


def run(root, temp, mode, selected, *, chat_mode="integrated", ok=True):
    env = {**os.environ, "GENOS_DEV": str(root), "GENOS_PYTHON_DIR": str(ROOT / ".venv/bin"),
           "GENOS_HANDOFF_LOG_DIR": str(temp / "logs"), "GENOS_MAIN_MODE": chat_mode,
           "PYTHONPATH": str(root / "02_BACKEND"), "LAWRAG_WORKSPACE_ROOT": str(root),
           "LAWRAG_TOOL_WORKSPACE_ROOT": str(root), "GENOS_AUTO_WARMUP": "0",
           "AD_WORKER_ENABLED": "0", "GENOS_CHAT_TRANSPORT": "json"}
    done = subprocess.run(["bash", str(SCRIPT), mode, str(selected)],
                          env=env, capture_output=True, text=True, timeout=120)
    assert (done.returncode == 0) == ok, done.stdout + done.stderr
    assert "QUERY_LATENCY_EXIT=" in done.stdout
    return done


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_frozen_300_file_zip_and_field_scripts():
    record = json.loads((OUT / "HANDOFF.json").read_text())
    assert sha(ZIP.read_bytes()) == record["code_zip_sha256"]
    assert sha(SCRIPT.read_bytes()) == record["apply_txt_sha256"]
    pointer = json.loads((ROOT / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json").read_text())
    assert pointer == record["selected_local_baseline"] and pointer["generation"] == 45
    with zipfile.ZipFile(ZIP) as archive:
        raw = archive.read("CODE_MANIFEST.json")
        assert sha(raw) == record["code_manifest_sha256"]
        manifest = json.loads(raw)
        assert len(manifest["files"]) == 300
        assert manifest["socket_chat"]["enabled"] is False
        assert manifest["chat_modes"]["integrated"]["transport"] == "json"
        assert all(set(row) == {'path', 'sha256'} for row in manifest['required_files'])
        for row in manifest["files"]:
            source = archive.read(row["path"])
            assert len(source) == row["bytes"] and sha(source) == row["sha256"]
            # The workspace may advance independently after freezing. Installation
            # tests below verify every frozen byte in its actual disposable checkout.
            owned = ('02_BACKEND/semantic_runtime/unit_fulltext.py',
                     '02_BACKEND/semantic_runtime/query_latency.py',
                     '02_BACKEND/semantic_runtime/term_index.py',
                     '02_BACKEND/semantic_runtime/request_report.py',
                     '02_BACKEND/semantic_runtime/legal_agent/law_candidates.py',
                     '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py',
                     '02_BACKEND/semantic_runtime/legal_agent/memory_rag.py',
                     '02_BACKEND/semantic_runtime/legal_agent/unit_reading.py',
                     '02_BACKEND/semantic_runtime/legal_agent/gateway.py')
            if row['path'] in owned:
                assert source == (ROOT / row['path']).read_bytes(), row['path']
            if row["path"].endswith(".py"):
                compile(source, row["path"], "exec")
                ast.parse(source, feature_version=(3, 10) if "/workflow/" in row["path"] else (3, 11))
    for name in (NAME + "_APPLY.txt", NAME + "_PUSH_NEW_REMOTE.txt"):
        subprocess.run(["bash", "-n", str(OUT / name)], check=True)
    loader = SCRIPT.read_text().split("<<'LOADER_PY'\n", 1)[1].rsplit("\nLOADER_PY", 1)[0]
    ast.parse(loader, feature_version=(3, 11))
    with zipfile.ZipFile(ZIP) as archive:
        assert (OUT / (NAME + "_WORKFLOW_PASTE_ALL.txt")).read_bytes() == archive.read(
            '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')


@pytest.mark.parametrize("chat_mode", ["workflow", "integrated"])
def test_r2_apply_then_r3_apply_repeat_verify_and_rollback(tmp_path, structured_generation, chat_mode):
    root = tmp_path / "physical"
    prior = seed(root)
    alias = tmp_path / "DEV"
    alias.symlink_to(root, target_is_directory=True)
    state = root / "90_RUNTIME/existing-state.sqlite"
    state.parent.mkdir()
    state.write_bytes(b"preserved-state")
    data = hashes(structured_generation)
    run(alias, tmp_path, "check", structured_generation, chat_mode=chat_mode)
    run(alias, tmp_path, "apply", structured_generation, chat_mode=chat_mode)
    run(alias, tmp_path, "apply", structured_generation, chat_mode=chat_mode)
    verified = run(alias, tmp_path, "verify", structured_generation, chat_mode=chat_mode)
    assert "QUERY_LATENCY_CONTRACT PASS " + chat_mode in verified.stdout
    with zipfile.ZipFile(ZIP) as archive:
        for name in archive.namelist():
            assert (root / name).read_bytes() == archive.read(name)
    assert hashes(structured_generation) == data and state.read_bytes() == b"preserved-state"
    backup = next((root / "09_ARTIFACTS/BACKUPS/code-replacement").iterdir())
    run(alias, tmp_path, "rollback", backup, chat_mode=chat_mode)
    for path in json.loads((OUT/'CODE_MANIFEST.json').read_text())['scope']['added_files']:
        assert not (root/path).exists(), path
    for name, raw in prior.items():
        assert (root / name).read_bytes() == raw, name
    assert not (root / "07_DOCS/REFERENCE/OPERATIONS/GENOS_QUERY_LATENCY_20261007_R3.md").exists()
    assert hashes(structured_generation) == data and state.read_bytes() == b"preserved-state"


@pytest.mark.parametrize("chat_mode", ["workflow", "integrated"])
def test_same_checkout_generation_gate_and_local_push(tmp_path, structured_generation, chat_mode):
    root = tmp_path / "DEV"
    seed(root)
    git(root, "init", "-q")
    git(root, "config", "user.name", "Query latency validation")
    git(root, "config", "user.email", "validation@example.invalid")
    git(root, "add", "-f", ".")
    git(root, "commit", "-qm", "Synthetic applied no-socket R3")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    git(root, "remote", "add", "origin", str(remote))
    before = hashes(structured_generation)
    done = run(root, tmp_path, "all", structured_generation, chat_mode=chat_mode)
    assert "GENOS_RELEASE_GATE PASS" in done.stdout
    assert "QUERY_LATENCY_CONTRACT PASS " + chat_mode in done.stdout
    assert git(remote, "rev-parse", "HEAD") == git(root, "rev-parse", "HEAD")
    assert not git(root, "status", "--porcelain", "--untracked-files=no")
    assert hashes(structured_generation) == before
    events = [json.loads(line) for line in (tmp_path / "logs/events.jsonl").read_text().splitlines()]
    assert events[-1]["code_serving_revision"] == "NOT_DEPLOYED"
    assert events[-1]["chat_binding"] == "NOT_SELECTED"


def test_unknown_field_change_stops_before_mutation(tmp_path, structured_generation):
    root = tmp_path / "DEV"
    seed(root)
    path = root / "08_DEPLOYMENT/GENOS/start_sse.py"
    path.write_bytes(path.read_bytes() + b"\n# unknown local field edit\n")
    before = hashes(root)
    run(root, tmp_path, "apply", structured_generation, ok=False)
    assert hashes(root) == before


def test_direct_from_selected_main_without_old_zip_chain(tmp_path, structured_generation):
    root = tmp_path / "DEV"
    parent = OUT.parent / "investigation_completion_20261007_r1"
    old = seed(root, parent)
    data = hashes(structured_generation)
    run(root, tmp_path, "check", structured_generation, chat_mode="workflow")
    run(root, tmp_path, "apply", structured_generation, chat_mode="workflow")
    done = run(root, tmp_path, "verify", structured_generation, chat_mode="workflow")
    assert "QUERY_LATENCY_CONTRACT PASS workflow" in done.stdout
    with zipfile.ZipFile(ZIP) as archive:
        for name in archive.namelist():
            assert (root / name).read_bytes() == archive.read(name), name
    assert hashes(structured_generation) == data


def test_summary_keeps_only_timing_and_tracks_unfinished_work():
    import types
    path = OUT / (NAME + '_SUMMARIZE.txt')
    module = types.ModuleType('latency_summary_contract')
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    rows = [
        'INFO step.started diagnostic_revision=query-latency-20261007-r1 step=law.select',
        'INFO step.started diagnostic_revision=query-latency-20261007-r1 step=unit_fts.sql.project_matches',
        'INFO step.finished diagnostic_revision=query-latency-20261007-r1 step=unit_fts.sql.project_matches duration_ms=12.5 sql_count=1 sql_execute_ms=2.5 sql_fetch_ms=10 question=private-sentinel',
        'INFO step.finished diagnostic_revision=query-latency-20261007-r1 step=unit_fts.projection duration_ms=15 cache_hit=False cache_overflow=True',
        'INFO step.failed diagnostic_revision=query-latency-20261007-r1 step=law.select duration_ms=20',
        '{"event":"step.started","diagnostic_revision":"query-latency-20261007-r1","step":"law.native.SELECT","question":"private-sentinel"}',
    ]
    value = module.summarize(rows)
    assert value['sql_count'] == 1 and value['sql_fetch_ms'] == 10
    assert value['projection_overflow_builds'] == 1 and len(value['failed_steps']) == 1
    assert value['unfinished_steps'] == ['law.native.SELECT']
    assert 'private-sentinel' not in json.dumps(value)
    ast.parse(path.read_bytes(), feature_version=(3, 11))


def test_info_live_log_has_active_step_and_finishes_cleanly():
    import io
    import logging
    from semantic_runtime import query_latency as latency, request_report as report
    stream = io.StringIO()
    handler = report._LiveLog('timing-live-test', stream, None)
    prior = latency.log.level
    latency.log.setLevel(logging.INFO); latency.log.addHandler(handler)
    try:
        with latency.obs.context(request_id='timing-live-test'):
            with latency.span('law.test.live') as fields:
                assert handler.writer.drain(2)
                assert handler.active_steps == ['law.test.live']
                fields.update(cache_overflow=False, match_count=17)
        assert handler.writer.drain(2)
        assert not handler.active_steps
        assert 'match_count=17' in stream.getvalue() and 'work_ms=' in stream.getvalue()
    finally:
        latency.log.removeHandler(handler); latency.log.setLevel(prior)
        handler.writer.finish(); handler.writer.drain(2)
