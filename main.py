"""GENOS native chat: direct RAG with negotiated SSE and the JSON envelope."""
from __future__ import annotations
import asyncio
import hmac
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from genos_diagnostics import install as install_system_logging
install_system_logging("main")
from fastapi import Body, HTTPException, Request
sys.path.insert(0,str(ROOT/'02_BACKEND'))
sys.path.insert(0,str(ROOT/'08_DEPLOYMENT/GENOS'))
from stream_app import app,http_health,stream_response
from semantic_runtime.chat_adapter import chat,stream_display
app.add_api_route('/healthcheck',http_health,methods=['GET'])

def trusted_platform(request):
    if os.environ.get('GENOS_CHAT_TRUST_PLATFORM_IDENTITY','0')!='1':return False
    token=os.environ.get('GENOS_CHAT_GATEWAY_TOKEN','')
    return len(token)>=32 and hmac.compare_digest(
        request.headers.get('Authorization','').encode(),('Bearer '+token).encode())

@app.on_event('startup')
async def recover_ad_schedules():
    # Import off the HTTP event loop; SQL worker recovers schedules without a chat.
    import threading,importlib
    threading.Thread(target=lambda:importlib.import_module('service'),daemon=True,name='ad-startup').start()

@app.post('/chat')
async def chat_endpoint(request:Request,body:dict=Body(default_factory=dict),stream:bool|None=None):
    # The platform's deployment handshake remains a model-free JSON response.
    if body.get('question')!='__verify__':
        # cicd 388cd392 reverted native SSE after a field gateway validation
        # error. Keep direct JSON as the default until that consumer is verified.
        mode=os.getenv('GENOS_CHAT_TRANSPORT','json').strip().lower()
        if mode not in {'auto','json','sse'}:
            raise HTTPException(503,'GENOS_CHAT_TRANSPORT must be auto, json or sse')
        accept=request.headers.get('Accept','')
        accepts_sse=any(
            part.split(';',1)[0].strip().lower()=='text/event-stream'
            and not any(p.strip().lower() in {'q=0','q=0.0'} for p in part.split(';')[1:])
            for part in accept.split(','))
        requested=stream if stream is not None else body.get('stream')
        wants_sse=requested if type(requested) is bool else (
            mode=='sse' or mode=='auto' and accepts_sse)
        if wants_sse:
            trusted=trusted_platform(request)
            async def execute(data,on_progress,on_answer):
                return await chat(data,trusted_platform=trusted,
                                  on_progress=on_progress,on_answer=on_answer)
            return await stream_response(body,execute,display=stream_display())
    # Offload blocking model/DB work, as in Seungho cicd main.py.
    return await asyncio.to_thread(asyncio.run,chat(body,trusted_platform=trusted_platform(request)))

if __name__=='__main__':
    # uvicorn imports main:app; reuse this module when launched as python3 main.py
    # so routes and startup recovery are registered only once.
    sys.modules.setdefault('main',sys.modules[__name__])
    from start_sse import main as start
    start(['--app','main:app',*sys.argv[1:]])
