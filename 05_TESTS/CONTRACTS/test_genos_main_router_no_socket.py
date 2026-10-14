"""Direct JSON and external workflow SSE work without any Socket.IO server."""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

import main
import main_integrated
import main_router
import main_workflow
import stream_app
from semantic_runtime import chat_adapter as adapter
from semantic_runtime.legal_agent.answer_stream import current_sink


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def local_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GENOS_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("GENOS_MEMORY_ENABLED", "0")
    monkeypatch.setenv("GENOS_CHAT_TRANSPORT", "json")
    monkeypatch.delenv("TEAM_ID", raising=False)


def test_router_selects_external_workflow_or_existing_direct_app(monkeypatch):
    monkeypatch.delenv("GENOS_MAIN_MODE", raising=False)
    assert importlib.reload(main_router).app is main_workflow.app
    monkeypatch.setenv("GENOS_MAIN_MODE", "existing")
    assert importlib.reload(main_router).app is main_workflow.app
    monkeypatch.setenv("GENOS_MAIN_MODE", "integrated")
    assert importlib.reload(main_router).app is main.app
    assert main_integrated.app is main.app  # old Run target is a no-socket alias
    monkeypatch.setenv("GENOS_MAIN_MODE", "unknown")
    with pytest.raises(RuntimeError, match="GENOS_MAIN_MODE"):
        importlib.reload(main_router)
    monkeypatch.setenv("GENOS_MAIN_MODE", "workflow")
    importlib.reload(main_router)


def test_direct_chat_returns_completed_json_without_socket(monkeypatch):
    async def local(body):
        if body.get("API_TYPE") == "AD_PROBE":
            return {"status": 200, "body": {}}
        return {"status": 200, "body": {"answer": {"text": "완성 답변"}, "assembly": {}}}
    monkeypatch.setattr(adapter, "call_service", local)
    client = TestClient(main.app)
    assert client.post("/chat", json={"question": "__verify__"}).json() == {
        "code": 0, "data": {"text": "verified"}}
    response = client.post("/chat", json={"question": "모의", "socketIOClientId": "obsolete"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()["data"]
    assert data["text"] == "완성 답변"
    assert "socketio_transport" not in data
    assert client.get("/socket.io/?EIO=4&transport=polling").status_code == 404


def test_workflow_backend_rejects_direct_chat_and_exposes_sse_without_socket(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("direct RAG started on workflow /chat")
    monkeypatch.setattr(adapter, "call_service", forbidden)
    client = TestClient(main_workflow.app)
    assert client.post("/chat", json={"question": "__verify__"}).json() == {
        "code": 0, "data": {"text": "verified"}}
    response = client.post("/chat", json={"question": "일반 질문"})
    assert response.status_code == 409
    assert response.json()["data"]["answer_status"] == "wrong_entrypoint"
    mode = client.get("/chat-mode").json()
    assert mode["mode"] == "workflow" and mode["transport"] == "http-sse"
    probe = client.post("/stream", json={"API_TYPE": "SSE_CHECK"})
    assert probe.headers["content-type"].startswith("text/event-stream")
    assert '"sse_ready":true' in probe.text
    assert client.get("/socket.io/?EIO=4&transport=polling").status_code == 404


def test_external_workflow_consumes_sse_without_importing_platform_socket(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "workflow_no_socket_test", ROOT / "08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py")
    workflow = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(workflow)
    seen = threading.Event()
    finished = threading.Event()
    calls = []

    async def backend(config, body):
        calls.append(body["API_TYPE"])
        if body["API_TYPE"] == "AD_PROBE":
            return {"status": 200, "body": {}}
        current_sink()("SSE 조각")
        assert seen.wait(5)
        finished.set()
        return {"status": 200, "body": {"answer": {"text": "SSE 조각 완료"}, "assembly": {}}}

    monkeypatch.setattr(stream_app, "service", backend)
    monkeypatch.setenv("GENOS_RAG_PROGRESS_UI", "socketio-final")
    monkeypatch.setenv("GENOS_CODESERVING_ID", "local-synthetic")
    monkeypatch.setenv("GENOS_CODESERVING_TOKEN", "synthetic-token")
    original = workflow._ChatProgress.answer_delta

    async def answer_delta(display, event):
        assert not finished.is_set()
        assert display.enabled is False
        seen.set()
        await original(display, event)

    monkeypatch.setattr(workflow._ChatProgress, "answer_delta", answer_delta)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)
    address = "http://127.0.0.1:" + str(sock.getsockname()[1])
    gateway = FastAPI()
    gateway.mount("/api/gateway/code_serving/local-synthetic", main_workflow.app)
    monkeypatch.setenv("GENOS_BASE_URL", address)
    server = uvicorn.Server(uvicorn.Config(gateway, lifespan="off", log_level="error"))
    worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 3
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        result = asyncio.run(workflow.run({"question": "모의 SSE 질의", "request_id": "no-socket-test",
                                           "socketIOClientId": "ignored-sid"}))
        assert result["answer_status"] == "answered", result
        assert "SSE 조각 완료" in result["text"]
        assert result["code_serving_transport"]["route"] == "/stream"
        assert result["code_serving_transport"]["answer_events"] == 1
        assert calls == ["AD_PROBE", "LEGAL_AGENT"]
        assert "main_socketio" not in sys.modules
        settings = asyncio.run(workflow.run({"API_TYPE": "WORKFLOW_SETTINGS", "request_id": "settings"}))
        assert settings["workflow_settings"]["socketio_enabled"] is False
    finally:
        seen.set()
        server.should_exit = True
        worker.join(timeout=3)
        sock.close()


def test_both_modes_start_without_python_socketio_dependency(monkeypatch, capsys):
    import start_sse
    original = start_sse.importlib.util.find_spec
    def no_socket(name, *args, **kwargs):
        return None if name == "socketio" else original(name, *args, **kwargs)
    monkeypatch.setattr(start_sse.importlib.util, "find_spec", no_socket)
    for mode in ("workflow", "integrated"):
        monkeypatch.setenv("GENOS_MAIN_MODE", mode)
        start_sse.main(["--app", "main_router:app", "--check"])
        assert '"chat_mode": "' + mode + '"' in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["workflow", "integrated"])
def test_clean_process_import_needs_no_socket_package(mode):
    code = """import sys
class NoSocket:
 def find_spec(self, fullname, path=None, target=None):
  if fullname == 'socketio' or fullname.startswith('socketio.') or fullname == 'main_socketio':
   raise ModuleNotFoundError('socket disabled')
sys.meta_path.insert(0, NoSocket())
import main_router
assert main_router.MODE == %r
assert 'socketio' not in sys.modules
print('NO_SOCKET_IMPORT PASS')
""" % mode
    done = subprocess.run([str(ROOT / ".venv/bin/python"), "-c", code], cwd=ROOT,
                          env={**os.environ, "GENOS_MAIN_MODE": mode,
                               "PYTHONPATH": ".:02_BACKEND:08_DEPLOYMENT/GENOS"},
                          capture_output=True, text=True, timeout=15)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "NO_SOCKET_IMPORT PASS" in done.stdout
