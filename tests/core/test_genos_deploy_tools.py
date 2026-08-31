"""GenOS 배포 도구 — 비밀값을 노출하지 않고 올바른 게이트웨이 봉투를 만드는지."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CALL = ROOT / "scripts" / "genos_call.sh"
PREFLIGHT = ROOT / "scripts" / "genos_preflight.py"


@pytest.fixture()
def gateway():
    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            size = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(size))
            seen.append({"path": self.path,
                         "authorization": self.headers.get("Authorization"),
                         "body": body})
            raw = json.dumps({"received": body}, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/json", seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _call(gateway, *args: str) -> dict:
    url, seen = gateway
    env = {**os.environ, "GENOS_CODE_URL": url, "GENOS_CODE_KEY": "secret-test-key"}
    done = subprocess.run([str(CALL), *args], cwd=ROOT, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    assert "secret-test-key" not in done.stdout
    assert seen[-1]["authorization"] == "Bearer secret-test-key"
    return seen[-1]["body"]


def test_call_ping_and_health(gateway):
    assert _call(gateway, "ping") == {"op": "ping"}
    assert _call(gateway, "health") == {
        "op": "call", "method": "GET", "path": "/health",
    }


def test_call_search_encodes_query(gateway):
    body = _call(gateway, "search", "설명의무 & 적합성")
    assert body["path"] == "/v1/rag/search"
    assert body["params"] == {"q": "설명의무 & 적합성", "mode": "auto"}


def test_call_ask_wraps_unicode(gateway):
    body = _call(gateway, "ask", "신탁재산 근거는?")
    assert body == {"op": "call", "method": "POST", "path": "/v1/rag/ask",
                    "json": {"question": "신탁재산 근거는?"}}


def test_call_requires_secret_env():
    env = dict(os.environ)
    env.pop("GENOS_CODE_URL", None)
    env.pop("GENOS_CODE_KEY", None)
    done = subprocess.run([str(CALL), "ping"], cwd=ROOT, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert done.returncode == 2
    assert "GENOS_CODE_URL" in done.stderr


def test_source_preflight_is_machine_readable():
    done = subprocess.run([sys.executable, str(PREFLIGHT), "source", "--json"],
                          cwd=ROOT, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True)
    report = json.loads(done.stdout)
    assert report["summary"]["fail"] == 0
    names = {row["name"] for row in report["checks"]}
    assert {"GenOS 진입점", "서빙 의존성", "비밀값 추적"} <= names
