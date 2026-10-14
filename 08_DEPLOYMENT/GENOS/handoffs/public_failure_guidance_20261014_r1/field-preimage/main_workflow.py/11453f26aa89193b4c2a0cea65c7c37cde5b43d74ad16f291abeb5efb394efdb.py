"""SSE backend for the existing external GENOS Python workflow.

The platform runs workflow/genos_rag_chat.py:run, which reads this /stream.
This app does not execute the workflow or the direct /chat adapter itself.
"""
from __future__ import annotations

from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from genos_diagnostics import install as install_system_logging

install_system_logging("workflow-backend")

from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse

sys.path.insert(0, str(ROOT / "02_BACKEND"))
sys.path.insert(0, str(ROOT / "08_DEPLOYMENT/GENOS"))

from main import recover_ad_schedules
from stream_app import http_health, json_endpoint, stream_endpoint, install_http_diagnostics


REVISION = "genos-external-workflow-sse-20261007-r2"
app = FastAPI(title="8-AGENT GENOS external workflow SSE backend")
install_http_diagnostics(app)
app.add_api_route("/json", json_endpoint, methods=["POST"])
app.add_api_route("/stream", stream_endpoint, methods=["POST"])
app.on_event("startup")(recover_ad_schedules)


@app.get("/chat-mode")
async def chat_mode():
    return {"revision": REVISION, "mode": "workflow", "transport": "http-sse",
            "executor": "external-genos-python-workflow", "backend_route": "/stream",
            "workflow_entry": "08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py:run",
            "direct_chat_enabled": False, "platform_binding": "NOT_VERIFIED"}


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
