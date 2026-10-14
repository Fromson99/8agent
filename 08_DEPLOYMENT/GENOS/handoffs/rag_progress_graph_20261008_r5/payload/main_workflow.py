"""SSE backend for the existing external GENOS Python workflow.

The platform runs workflow/genos_rag_chat.py:run, which reads this /stream.
Both JSON and SSE attach the shared SVG/concise-progress display to the raw
result. The Python step reuses that request-bound display, keeping one RAG call.
"""
from __future__ import annotations

from pathlib import Path
from contextlib import nullcontext
import os
import sys
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from genos_diagnostics import install as install_system_logging

install_system_logging("workflow-backend")

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, str(ROOT / "02_BACKEND"))
sys.path.insert(0, str(ROOT / "08_DEPLOYMENT/GENOS"))

from main import recover_ad_schedules
import stream_app as backend
from stream_app import http_health, install_http_diagnostics
from semantic_runtime.chat_adapter import views


REVISION = "genos-external-workflow-svg-20261008-r3"
app = FastAPI(title="8-AGENT GENOS external workflow SSE backend")
install_http_diagnostics(app)
app.on_event("startup")(recover_ad_schedules)


async def _execute_rag(data, on_progress=None, on_answer=None):
    events = []
    def sink(event):
        if len(events) < 256 or (event.get('basis') or {}).get('detail_mode') == 'full_error':
            events.append(event)
        if on_progress is not None:
            on_progress(event)
    runtime_value = os.environ.get('GENOS_RUNTIME_DIR', '').strip()
    runtime = Path(runtime_value).resolve() if runtime_value else ROOT / '90_RUNTIME/semantic'
    backend.configure()
    answer_context = backend.capture_answer(data['request_id'], on_answer) if on_answer is not None else nullcontext()
    with backend.capture(data['request_id'], runtime, sink), answer_context:
        response = await backend.service({}, data)
    if not isinstance(response, dict) or not isinstance(response.get('body'), dict):
        return response
    view = views()
    body = view.unwrap(response)
    body.pop('workflow_display', None)
    if body.get('response_schema') == 'ad-mode-v1':
        return response
    rendered = await view.workflow_display_result(body, events, request_id=data['request_id'])
    # Preserve status/body and every raw source/state field for existing clients.
    return {**response, 'body': {**response['body'], 'workflow_display': rendered}}


@app.post('/json')
async def json_endpoint(request: Request):
    data = await request.json()
    if not isinstance(data, dict) or data.get('API_TYPE') not in {'LEGAL_AGENT', 'ELS_QUERY'}:
        return await backend.json_endpoint(request)
    data = {**data, 'request_id': str(data.get('request_id') or backend.new_request_id())}
    return JSONResponse(await _execute_rag(data))


@app.post('/stream')
async def stream_endpoint(request: Request):
    data = await request.json()
    if not isinstance(data, dict) or data.get('API_TYPE') not in {'LEGAL_AGENT', 'ELS_QUERY'}:
        return await backend.stream_endpoint(request)
    data = {**data, 'request_id': backend.new_request_id(data.get('request_id'))}
    return await backend.stream_response(data, _execute_rag)


@app.get("/chat-mode")
async def chat_mode():
    view = views()
    return {"revision": REVISION, "mode": "workflow", "transport": "http-sse",
            "executor": "external-genos-python-workflow", "backend_route": "/stream",
            "workflow_entry": "08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py:run",
            "direct_chat_enabled": False, "platform_binding": "NOT_VERIFIED",
            "judgment_display_revision": view.JUDGMENT_DISPLAY_REVISION,
            "progress_display_revision": view.PROGRESS_DISPLAY_REVISION,
            "workflow_display_schema": "genos-workflow-display-v1",
            "display_producer": "main_workflow",
            "display_renderer_path": str(Path(view.__file__).resolve())}


@app.get("/")
@app.get("/health")
@app.get("/healthcheck")
async def health():
    return {**await http_health(), "chat_mode": await chat_mode()}


@app.post("/chat")
async def registration(body: dict = Body(default_factory=dict)):
    if body.get("question") == "__verify__":
        return {"code": 0, "data": {"text": "verified"}}
    if str(body.get("API_TYPE") or "").strip().upper() == "CHAT_MODE":
        return {"code": 0, "data": {"text": "워크플로우 SSE 방식", "chat_mode": await chat_mode()}}
    # Explicitly reject a direct chat binding rather than secretly running RAG
    # here and calling that external-workflow execution.
    return JSONResponse({"code": 409, "data": {
        "text": "workflow 모드입니다. 기존 GENOS Python 워크플로우를 연결하세요.",
        "answer_status": "wrong_entrypoint", "chat_mode": await chat_mode()}}, status_code=409)
