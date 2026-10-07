"""Optional GENOS HTTP entry point: keep /json and add legal-agent SSE.

Start with ``uvicorn stream_app:app --app-dir 08_DEPLOYMENT/GENOS`` from the
repository root when the selected GENOS code-serving revision permits a custom
start command.  Both routes call the existing service.service exactly once.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
import threading
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "02_BACKEND"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from semantic_runtime.observability import configure, new_request_id  # noqa: E402
from semantic_runtime.progress import capture  # noqa: E402


app = FastAPI(title="8-AGENT GENOS code serving")
SSE_REVISION = "sse-transport-20260928-r1"
STARTUP_REVISION = "sse-startup-20260928-r1"
PROGRESS_REVISION = "chat-status-20260928-r1"
HEARTBEAT_SECONDS = 10.0
_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
            "X-Genos-SSE-Revision": SSE_REVISION,
            "X-Genos-Progress-Revision": PROGRESS_REVISION}
_ACTIVE_REQUESTS = set()
_ACTIVE_LOCK = threading.Lock()


async def service(config, data):
    # Importing service starts generation warmup. Load it only for a backend
    # request, off the HTTP event loop; probes and server startup stay independent
    # of NFS, SQLite, model discovery and process-local data caches.
    backend = await asyncio.to_thread(importlib.import_module, "service")
    return await backend.service(config, data)


@app.get("/")
@app.get("/health")
async def http_health():
    # This reports HTTP liveness only. The existing WARMUP_STATUS operation
    # remains the authority for generation/resource readiness.
    return {"status": "ok", "service": "8-AGENT", "readiness_scope": "http",
            "data_readiness": "NOT_CHECKED", "startup_revision": STARTUP_REVISION}


@app.post("/json")
async def json_endpoint(request: Request):
    data = await request.json()
    return JSONResponse(await service({}, data))


def _frame(event, data):
    return "data: " + json.dumps({"event": event, "data": data}, ensure_ascii=False,
                                 separators=(",", ":")) + "\n\n"


@app.post("/stream")
async def stream_endpoint(request: Request):
    data = await request.json()
    if isinstance(data, dict) and data.get("API_TYPE") == "SSE_CHECK":
        async def probe():
            yield ": connected\n\n"
            yield _frame("result", {"sse_ready": True, "stream_server_revision": SSE_REVISION,
                                    "stream_startup_revision": STARTUP_REVISION,
                                    "stream_progress_revision": PROGRESS_REVISION,
                                    "heartbeat_seconds": HEARTBEAT_SECONDS})
        return StreamingResponse(probe(), media_type="text/event-stream", headers=_HEADERS)
    if not isinstance(data, dict) or data.get("API_TYPE") not in ("LEGAL_AGENT", "ELS_QUERY"):
        return JSONResponse({"error": "/stream requires LEGAL_AGENT"}, status_code=400)
    data = {**data, "request_id": new_request_id(data.get("request_id"))}
    with _ACTIVE_LOCK:
        if data["request_id"] in _ACTIVE_REQUESTS:
            return JSONResponse({"error": "request already active"}, status_code=409)
        _ACTIVE_REQUESTS.add(data["request_id"])
    runtime_value = os.environ.get("GENOS_RUNTIME_DIR", "").strip()
    runtime = Path(runtime_value).resolve() if runtime_value else ROOT / "90_RUNTIME/semantic"

    async def events():
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue(maxsize=128)
        started = time.monotonic()
        stream_seq = 0

        def enqueue(kind, value):
            nonlocal stream_seq
            if queue.full():
                while not queue.empty():
                    queue.get_nowait()
                stream_seq += 1
                queue.put_nowait(("progress", {"schema_version": "rag-progress-v1",
                    "request_id": data["request_id"], "seq": stream_seq,
                    "kind": "overflow", "label": "진행 단계 일부를 표시하지 못함",
                    "elapsed_ms": int((time.monotonic() - started) * 1000)}))
            if kind == "progress":
                stream_seq += 1
                value = {**value, "seq": stream_seq}
            queue.put_nowait((kind, value))

        def sink(value):
            loop.call_soon_threadsafe(enqueue, "progress", value)

        def execute():
            # The deferred first service import configures logging and clears
            # root handlers. Configure before attaching the progress collector
            # so initialization cannot discard the first request's SSE events.
            configure()
            with capture(data["request_id"], runtime, sink):
                return asyncio.run(service({}, data))

        async def worker():
            try:
                result = await asyncio.to_thread(execute)
            except Exception as exc:  # response details stay in code-serving logs
                result = {"status": 500, "body": {"error": "stream execution failed",
                                                   "error_type": type(exc).__name__}}
            enqueue("result", result)

        task = None
        try:
            # Flush before computation, and release the reservation if the
            # client disconnects immediately after this first chunk.
            yield ": connected\n\n"
            task = asyncio.create_task(worker())
            while True:
                try:
                    kind, value = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    stream_seq += 1
                    elapsed = int(time.monotonic() - started)
                    yield _frame("progress", {"schema_version": "rag-progress-v1",
                        "request_id": data["request_id"], "seq": stream_seq, "kind": "heartbeat",
                        "label": f"요청 처리 중 · 경과 {elapsed}초", "elapsed_ms": elapsed * 1000})
                    continue
                yield _frame(kind, value)
                if kind == "result":
                    break
        finally:
            # A browser disconnect does not cancel the underlying legal request.
            # It still closes its request journal; the bounded queue is discarded.
            def release(done):
                with _ACTIVE_LOCK:
                    _ACTIVE_REQUESTS.discard(data["request_id"])
                if not done.cancelled():
                    done.exception()
            if task is None:
                with _ACTIVE_LOCK:
                    _ACTIVE_REQUESTS.discard(data["request_id"])
            elif task.done():
                release(task)
            else:
                task.add_done_callback(release)

    return StreamingResponse(events(), media_type="text/event-stream", headers=_HEADERS)
