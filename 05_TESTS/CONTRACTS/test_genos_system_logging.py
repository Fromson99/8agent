"""Process-level log durability and routing; synthetic data, no model/network."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from genos_diagnostics import Session, transfer

ROOT = Path(__file__).resolve().parents[2]
PYTHON = str(ROOT / ".venv/bin/python")


def env(tmp_path):
    return {**os.environ, "GENOS_SYSTEM_LOG_DIR": str(tmp_path / "nfs"),
            "GENOS_LOG_SPOOL_DIR": str(tmp_path / "spool"), "GENOS_SYSTEM_LOG_ENABLED": "1",
            "GENOS_LOG_RUN_ID": "test-run", "GENOS_AUTO_WARMUP": "0", "AD_WORKER_ENABLED": "0",
            "PYTHONPATH": ".:02_BACKEND:08_DEPLOYMENT/GENOS", "GENOS_LLM_KEY": "synthetic-secret"}


def logs(tmp_path, suffix):
    return list((tmp_path / "nfs" / "test-run").glob("*-" + suffix))


def run(tmp_path, script, *, wrapper=True, **extra):
    cmd = [PYTHON, "-c", script]
    if wrapper:
        cmd = [PYTHON, "genos_log_runner.py", "--phase", "build", "--", *cmd]
    return subprocess.run(cmd, env={**env(tmp_path), **extra}, cwd=ROOT, capture_output=True, timeout=15)


def test_wrapper_preserves_original_binary_bytes_and_failure_status(tmp_path):
    stdout = b"normal output\r\n\xff\x00" * 4000
    stderr = ("원문 오류\r\n" * 7000).encode()
    done = run(tmp_path, "import os; os.write(1,b'normal output\\r\\n\\xff\\x00'*4000); "
               "os.write(2,('원문 오류\\r\\n'*7000).encode()); raise SystemExit(23)")
    assert done.returncode == 23
    assert logs(tmp_path, "stdout.log")[0].read_bytes() == stdout
    assert logs(tmp_path, "stderr.log")[0].read_bytes() == stderr
    assert json.loads(logs(tmp_path, "result.json")[0].read_bytes())["exit_code"] == 23
    assert b"NFS_COMPLETE True" in done.stdout
    assert not list((tmp_path / "spool").glob("**/*.pending"))


def test_environment_error_before_application_import_is_retained(tmp_path):
    done = run(tmp_path, "import main_router", wrapper=False, GENOS_MAIN_MODE="broken-mode")
    assert done.returncode == 1
    raw = b"".join(path.read_bytes() for path in logs(tmp_path, "exceptions.raw.log"))
    assert b"GENOS_MAIN_MODE must be" in raw and b"Traceback (most recent call last)" in raw


def test_missing_fastapi_dependency_is_captured_before_import(tmp_path):
    code = """import sys
class MissingFastAPI:
 def find_spec(self, fullname, path=None, target=None):
  if fullname=='fastapi': raise ModuleNotFoundError('synthetic fastapi unavailable')
sys.meta_path.insert(0,MissingFastAPI())
import main
"""
    done = run(tmp_path, code, wrapper=False)
    assert done.returncode == 1
    assert b"synthetic fastapi unavailable" in logs(tmp_path, "exceptions.raw.log")[0].read_bytes()


def test_handled_error_full_trace_survives_rag_logger_setup_and_no_truncation(tmp_path):
    code = """from genos_diagnostics import install
install('test')
from semantic_runtime import observability as obs
log=obs.get_logger('test')
try:
 raise ValueError('BEGIN-'+('x'*50000)+'-END')
except Exception:
 obs.event(log,'handled.error',level=40,exc_info=True,request_id='rid-original')
"""
    done = run(tmp_path, code)
    assert done.returncode == 0, done.stderr
    raw = logs(tmp_path, "python.raw.log")[0].read_text()
    assert "x" * 50000 in raw and "-END" in raw and "rid-original" in raw


def test_metadata_records_configuration_and_code_without_secret_values(tmp_path):
    done = run(tmp_path, "print('okay')")
    assert done.returncode == 0
    raw = logs(tmp_path, "environment.json")[0].read_text()
    value = json.loads(raw)
    assert value["python_executable"] == PYTHON
    assert "GENOS_LLM_KEY" in value["environment_names"]
    assert "synthetic-secret" not in raw
    assert value["code_sha256"]["service.py"]
    assert value["configuration_is_actual_runtime_binding"] is False


def test_nfs_unavailable_keeps_local_bytes_and_recovery_is_idempotent(tmp_path):
    blocked = tmp_path / "nfs"
    blocked.write_text("cannot mkdir below a file")
    session = Session("failure", root=blocked, spool_root=tmp_path / "spool", run_id="test-run")
    session.write("stdout.log", b"first\x00\xff")
    session.write("stdout.log", b"second\r\n")
    assert session.close(timeout=0.4) is False
    assert session.pending() >= 2
    blocked.unlink()
    session.target.mkdir(parents=True)
    remote = session.target / (session.prefix + "-stdout.log")
    remote.write_bytes(b"fir")  # Reproduce an interrupted transfer before acknowledgment.
    while session.pending():
        transfer(session.spool)
    assert remote.read_bytes() == b"first\x00\xffsecond\r\n"
    transfer(session.spool)
    assert remote.read_bytes() == b"first\x00\xffsecond\r\n"
    events = (session.target / (session.prefix + "-events.jsonl")).read_text()
    assert "nfs.logging.failed" in events and "NotADirectoryError" in events


def test_background_nfs_block_does_not_block_request_logging(tmp_path, monkeypatch):
    import genos_diagnostics as diagnostics
    import threading
    blocked = threading.Event()
    release = threading.Event()
    original = diagnostics.transfer
    def slow_transfer(spool):
        blocked.set()
        release.wait(3)
        original(spool)
    monkeypatch.setattr(diagnostics, "transfer", slow_transfer)
    session = Session("slow", root=tmp_path / "nfs", spool_root=tmp_path / "spool", run_id="test-run")
    assert blocked.wait(1)
    started = time.monotonic()
    session.write("stdout.log", b"request still runs")
    assert time.monotonic() - started < 0.5
    release.set()
    assert session.close()


def test_command_not_found_is_logged_and_returns_127(tmp_path):
    done = subprocess.run([PYTHON, "genos_log_runner.py", "--phase", "deploy", "--",
                           "no-such-synthetic-executable"], env=env(tmp_path), cwd=ROOT,
                          capture_output=True, timeout=10)
    assert done.returncode == 127
    assert b"FileNotFoundError" in logs(tmp_path, "stderr.log")[0].read_bytes()


def test_sigterm_forwards_to_child_and_retains_exit_record(tmp_path):
    child = subprocess.Popen([PYTHON, "genos_log_runner.py", "--phase", "serving", "--", PYTHON,
                              "-c", "import time;print('child-ready',flush=True);time.sleep(60)"],
                             cwd=ROOT, env=env(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            files = logs(tmp_path, "stdout.log")
            if files and b"child-ready" in files[0].read_bytes():
                break
            time.sleep(0.02)
        else:
            pytest.fail("child never started")
        child.send_signal(signal.SIGTERM)
        out, err = child.communicate(timeout=6)
        assert child.returncode == 143, out + err
        events = logs(tmp_path, "events.jsonl")[0].read_text()
        assert "command.signal" in events and '"exit_code": 143' in events
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=3)


def test_http_general_requests_and_caught_exception_are_recorded(tmp_path):
    code = """from fastapi.testclient import TestClient
import main_workflow
@main_workflow.app.get('/synthetic-error')
def fail(): raise ValueError('ORIGINAL-HTTP-ERROR')
client=TestClient(main_workflow.app,raise_server_exceptions=False)
assert client.get('/health').status_code==200
assert client.get('/missing').status_code==404
assert client.get('/synthetic-error',headers={'X-Request-ID':'http-test'}).status_code==500
"""
    done = run(tmp_path, code)
    assert done.returncode == 0, done.stderr
    raw = logs(tmp_path, "python.raw.log")[0].read_text()
    assert "http.request.finished" in raw and '"http_status": 404' in raw
    assert "ORIGINAL-HTTP-ERROR" in raw and '"http_request_id": "http-test"' in raw


def test_invalid_recovery_directory_cannot_claim_success(tmp_path):
    done = subprocess.run([PYTHON, "genos_log_runner.py", "--recover", str(tmp_path / "missing")],
                          cwd=ROOT, env=env(tmp_path), capture_output=True, timeout=5)
    assert done.returncode != 0
    assert b"GENOS_SYSTEM_LOG_RECOVERED" not in done.stdout


def test_workflow_preserves_entire_http_error_body(tmp_path):
    code = """import asyncio, importlib.util, io, urllib.error
spec=importlib.util.spec_from_file_location('wf','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
wf=importlib.util.module_from_spec(spec);spec.loader.exec_module(wf)
wf._post_code_serving=lambda body: {'status':200,'body':{'ad_handled':False}}
async def fail(*args,**kwargs):
 raise urllib.error.HTTPError('http://synthetic',503,'failure',{},io.BytesIO(b'BEGIN-'+b'x'*70000+b'-END\\xff'))
wf._stream_code_serving=fail
result=asyncio.run(wf.run({'question':'synthetic question','request_id':'workflow-raw-test'}))
assert result['failure_kind']=='http_error'
"""
    done = run(tmp_path, code)
    assert done.returncode == 0, done.stderr
    raw = logs(tmp_path, "workflow.errors.raw.log")[0].read_bytes()
    assert b"BEGIN-" + b"x" * 70000 + b"-END\xff" in raw
    assert b"workflow-raw-test" in raw and b"HTTPError: HTTP Error 503" in raw
