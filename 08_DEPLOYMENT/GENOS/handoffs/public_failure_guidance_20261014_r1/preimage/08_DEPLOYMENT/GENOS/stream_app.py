"""Optional GENOS HTTP entry point: keep /json and add legal-agent SSE.

Start with ``uvicorn stream_app:app --app-dir 08_DEPLOYMENT/GENOS`` from the
repository root when the selected GENOS code-serving revision permits a custom
start command.  Both routes call the existing service.service exactly once.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeout
import importlib
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from genos_diagnostics import install as install_system_logging
install_system_logging("http")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
BACKEND = ROOT / "02_BACKEND"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from semantic_runtime.observability import configure, new_request_id, event as log_event, get_logger  # noqa: E402
from semantic_runtime.progress import capture, REVISION as PROGRESS_REVISION  # noqa: E402
from semantic_runtime.legal_agent.answer_stream import capture as capture_answer, REVISION as ANSWER_REVISION  # noqa: E402


app = FastAPI(title="8-AGENT GENOS code serving")


def install_http_diagnostics(target):
    @target.middleware("http")
    async def http_diagnostics(request, call_next):
        started = time.monotonic()
        request_id = new_request_id(request.headers.get("X-Request-ID"))
        logger = get_logger("http")
        fields = {"http_request_id": request_id, "method": request.method,
                  "path": request.url.path}
        log_event(logger, "http.request.started", **fields)
        try:
            response = await call_next(request)
        except Exception:
            log_event(logger, "http.request.failed", level=40, exc_info=True, **fields)
            raise
        log_event(logger, "http.request.finished", **fields, http_status=response.status_code,
                  duration_ms=round((time.monotonic() - started) * 1000, 3))
        return response


install_http_diagnostics(app)
SSE_REVISION = "sse-transport-20260928-r1"
STARTUP_REVISION = "sse-startup-20260928-r1"
JUDGMENT_LOG_REVISION = "sse-current-judgment-20261008-r1"
HEARTBEAT_SECONDS = 10.0
_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
            "X-Genos-SSE-Revision": SSE_REVISION,
            "X-Genos-Answer-Revision": ANSWER_REVISION,
            "X-Genos-Progress-Revision": PROGRESS_REVISION}
_ACTIVE_REQUESTS = set()
_ACTIVE_LOCK = threading.Lock()


async def service(config, data):
    # GENOS_NFS_PROBE_HOOK_V1
    if isinstance(data, dict) and str(data.get("API_TYPE", "")).strip().upper() == "NFS_DATA_PROBE":
        import importlib.util as _nfs_util
        _nfs_path = ROOT / "02_BACKEND/semantic_runtime/nfs_data_probe.py"
        _nfs_spec = _nfs_util.spec_from_file_location("_genos_nfs_data_probe", _nfs_path)
        _nfs_module = _nfs_util.module_from_spec(_nfs_spec)
        _nfs_spec.loader.exec_module(_nfs_module)
        return await _nfs_module.gateway(data, code_root=ROOT)
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
            "data_readiness": "NOT_CHECKED", "startup_revision": STARTUP_REVISION,
            "entrypoint": "stream_app:app", "execution_mode": "separate-sse-server",
            "stream_progress_revision": PROGRESS_REVISION,
            "judgment_log_revision": JUDGMENT_LOG_REVISION}


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
                                    "entrypoint": "stream_app:app",
                                    "execution_mode": "separate-sse-server",
                                    "stream_startup_revision": STARTUP_REVISION,
                                    "stream_progress_revision": PROGRESS_REVISION,
                                    "judgment_log_revision": JUDGMENT_LOG_REVISION,
                                    "stream_answer_revision": ANSWER_REVISION,
                                    "heartbeat_seconds": HEARTBEAT_SECONDS})
        return StreamingResponse(probe(), media_type="text/event-stream", headers=_HEADERS)
    if not isinstance(data, dict) or data.get("API_TYPE") not in ("LEGAL_AGENT", "ELS_QUERY"):
        return JSONResponse({"error": "/stream requires LEGAL_AGENT"}, status_code=400)
    data = {**data, "request_id": new_request_id(data.get("request_id"))}
    async def execute(body,on_progress,on_answer):
        runtime_value=os.environ.get('GENOS_RUNTIME_DIR','').strip()
        runtime=Path(runtime_value).resolve() if runtime_value else ROOT/'90_RUNTIME/semantic'
        with capture(body['request_id'],runtime,on_progress),capture_answer(body['request_id'],on_answer):
            return await service({},body)
    return await stream_response(data,execute)


async def stream_response(data,execute,*,display=None):
    """One bounded worker/heartbeat lifecycle for raw RAG and native /chat SSE.

    execute receives request-local progress/answer sinks. Native chat uses its
    existing renderer, emitting token events and a final data object with text,
    exactly as cicd's native /chat (the code/data envelope is for JSON only).
    It never calls a workflow socket or makes an HTTP request to itself.
    """
    # Preserve signed request IDs byte-for-byte; the runtime verifies the grant.
    data={**data,'request_id':str(data.get('request_id') or new_request_id())}
    with _ACTIVE_LOCK:
        if data["request_id"] in _ACTIVE_REQUESTS:
            return JSONResponse({"error": "request already active"}, status_code=409)
        _ACTIVE_REQUESTS.add(data["request_id"])
    async def events():
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue(maxsize=128)
        started = time.monotonic()
        stream_seq = 0
        detached = threading.Event()
        rendered=[]
        counts={'progress_events':0,'heartbeat_events':0,'answer_events':0}
        render_error=None
        if display is not None:
            async def emit(event,value,room=None):
                rendered.append((event,value))
            display.emit=emit

        def enqueue(kind, value):
            if detached.is_set():
                return
            if queue.full():
                # Only progress may be dropped. Answer fragments use backpressure.
                retained = []
                while not queue.empty():
                    item = queue.get_nowait()
                    if item[0] != 'progress' or (item[1].get('basis') or {}).get('detail_mode') in {'judgment', 'full_error'}:
                        retained.append(item)
                for item in retained:
                    queue.put_nowait(item)
                if queue.full():
                    return
            queue.put_nowait((kind, value))

        def sink(value):
            from semantic_runtime.chat_adapter import views
            value = views().public_event(value)
            if value is None:return
            # The separate server must report substantive committed judgments
            # even when no workflow socket or shared-volume tail is connected.
            basis = value.get('basis') or {}
            if (basis.get('detail_mode') in {'judgment', 'full_error'}
                    or value.get('kind') in {'selected', 'decision', 'revised'}):
                log_event(get_logger('stream'), 'agent.current_judgment',
                    request_id=data['request_id'], run_id=value.get('run_id'),
                    judgment_log_revision=JUDGMENT_LOG_REVISION,
                    stage=basis.get('stage'), journal_seq=basis.get('journal_seq'),
                    state=basis.get('state'), label=value.get('label'),
                    judgment_details=value.get('details', []))
            if basis.get('detail_mode') in {'judgment', 'full_error'}:
                put_from_worker('progress', value)
            else:
                loop.call_soon_threadsafe(enqueue, "progress", value)

        async def put_required(kind, value):
            while not detached.is_set():
                try:
                    await asyncio.wait_for(queue.put((kind, value)), timeout=0.25)
                    return
                except asyncio.TimeoutError:
                    continue

        def put_from_worker(kind, value):
            if not detached.is_set():
                # The model runs in a worker thread; block that producer, never
                # the HTTP event loop, until the bounded queue accepts the token.
                future = asyncio.run_coroutine_threadsafe(put_required(kind, value), loop)
                while not detached.is_set():
                    try:
                        future.result(timeout=0.25)
                        return
                    except FutureTimeout:
                        continue
                future.cancel()

        def answer_sink(value):
            put_from_worker('answer_delta', value)

        def run_request():
            # The deferred first service import configures logging and clears
            # root handlers. Configure before attaching the progress collector
            # so initialization cannot discard the first request's SSE events.
            configure()
            return asyncio.run(execute(data,sink,answer_sink))

        async def worker():
            try:
                result = await asyncio.to_thread(run_request)
            except Exception as exc:  # response details stay in code-serving logs
                log_event(get_logger('chat' if display is not None else 'stream'),
                    'stream.request.failed',level=40,exc_info=True,request_id=data['request_id'],error_type=type(exc).__name__)
                if display is None:
                    result = {"status": 500, "body": {"error": "stream execution failed",
                                                       "error_type": type(exc).__name__}}
                else:
                    result={'code':0,'data':{'text':'지금 답변을 가져오지 못했습니다. (추적 번호: '+data['request_id']+')',
                        'answer_status':'failed','request_id':data['request_id'],
                        'execution_transport':'in-process','error_type':type(exc).__name__}}
            if isinstance(result, dict) and 'body' in result:
                from semantic_runtime.chat_adapter import views
                result = {**result, 'body': views().public_response(result['body'],
                    status=result.get('status', 200), request_id=data['request_id'])}
            if not detached.is_set():
                await put_required('result', result)

        task = None
        try:
            # Flush before computation, and release the reservation if the
            # client disconnects immediately after this first chunk.
            log_event(get_logger('chat' if display is not None else 'stream'),'stream.request.started',
                request_id=data['request_id'],route='/chat' if display is not None else '/stream')
            yield ": connected\n\n"
            task = asyncio.create_task(worker())
            while True:
                try:
                    kind, value = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    counts['heartbeat_events'] += 1
                    yield ': keep-alive\n\n'
                    continue
                if kind == 'progress':
                    stream_seq += 1
                    value = {**value, 'seq': stream_seq}
                if display is None:
                    yield _frame(kind,value)
                    if kind=='result':break
                    continue
                if kind=='progress':
                    counts['progress_events']+=1
                    if value.get('kind')=='heartbeat':counts['heartbeat_events']+=1
                    await display.progress(value)
                    if value.get('kind')=='heartbeat':yield ': keep-alive\n\n'
                elif kind=='answer_delta':
                    counts['answer_events']+=1
                    if render_error is None:
                        try:
                            if value.get('request_id')!=data['request_id']:
                                raise ValueError('answer stream request mismatch')
                            await display.answer_delta(value)
                        except (ValueError,TypeError) as exc:
                            # Do not re-run a request or report a partial answer
                            # as complete. Its original worker still closes the journal.
                            render_error=type(exc).__name__
                elif kind=='result':
                    if render_error:
                        value['data'].update(answer_status='failed',error_type=render_error,
                            text='답변 스트림을 확인하지 못했습니다. (추적 번호: '+data['request_id']+')')
                    value['data']['chat_stream_transport']={
                        'route':'/chat','opened':True,'contract':'genos-chat-sse-v1',**counts}
                    if 'sse_check' in value['data']:
                        value['data']['sse_check'].update(sse_ready=True,
                            heartbeat_seconds=HEARTBEAT_SECONDS)
                    await display.finish(value['data'].get('text',''))
                    if display.blocks:value['data']['agentFlowExecutedData']=list(display.blocks)
                for event,payload in rendered:
                    if event=='token':yield _frame(event,payload)
                rendered.clear()
                if kind=='result':
                    yield _frame('result',value['data'])
                    break
        finally:
            detached.set()
            log_event(get_logger('chat' if display is not None else 'stream'),
                'stream.request.closed' if task is not None and task.done() else 'stream.client.detached',
                request_id=data['request_id'],worker_running=task is not None and not task.done(),
                duration_ms=int((time.monotonic()-started)*1000),**counts)
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

    headers=dict(_HEADERS)
    if display is not None:
        from semantic_runtime.chat_adapter import REVISION
        headers.update({'X-Genos-Chat-Revision':REVISION,
                        'X-Genos-Chat-Contract':'genos-chat-sse-v1'})
    return StreamingResponse(events(), media_type="text/event-stream", headers=headers)
