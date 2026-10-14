"""Former workflow adapter with direct in-process RAG, preserving input/rendering.

The old maintained workflow is a compatibility source for question, source and
Reasoner helpers. /chat never makes an HTTP self-call or imports main_socketio.
"""
from __future__ import annotations
import importlib
from contextlib import nullcontext
import os
from pathlib import Path
import time
import uuid
from . import progress
from .legal_agent.answer_stream import capture as capture_answer
REVISION='main-chat-completion-sse-20261007-r2'
_SECRETS={'authorization','api_key','apikey','token','password','memory_authorization',
          'signature','genos_memory_signing_key','genos_chat_gateway_token'}

def public_fields(value):
    if isinstance(value,dict):
        return {k:public_fields(v) for k,v in value.items() if str(k).lower() not in _SECRETS}
    if isinstance(value,list):return [public_fields(v) for v in value]
    return value

def views():
    # Read the adapter bundled with this exact release, not a working-tree module.
    import importlib.util,sys,hashlib
    path=Path(__file__).resolve().parents[2]/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
    name='_chat_views_'+hashlib.sha256(str(path).encode()).hexdigest()[:16]
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return sys.modules[name]

def request_body(data,question,trusted_platform=False):
    view=views()
    memory_enabled=os.environ.get('GENOS_MEMORY_ENABLED','0').lower() in {'1','true','on'}
    if data.get('memory') is True or memory_enabled:
        return view._request_body(question,data)
    # Ordinary single turns do not select saved session state.
    body={'API_TYPE':'LEGAL_AGENT','question':question,'request_id':data['request_id'],'channel':'genos-chat'}
    for name in ('document_ids','use_llm','scope','public_question'):
        if name in data:body[name]=data[name]
    if 'TEAM_ID' in os.environ:
        import re
        team=os.environ['TEAM_ID'].strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]+_team',team):raise ValueError('valid fixed TEAM_ID required')
        body['team_id']=team
    elif 'team_id' in data:body['team_id']=data['team_id']
    return body

async def call_service(body):return await importlib.import_module('service').service({},body)

def stream_display():
    """Reuse answer/source rendering with an HTTP emitter, independent of sockets."""
    display=views()._ChatProgress({})
    display.enabled=True
    display.show_progress=os.getenv('GENOS_RAG_PROGRESS_UI','socketio').lower()!='off'
    # The native consumer documented in cicd reads token/result. Preserve cards
    # in the final result and send visible activity through the token channel.
    display.show_inline_progress=display.show_progress
    return display


async def chat(data,*,trusted_platform=False,on_progress=None,on_answer=None):
    data=dict(data or {});view=views();question=view._extract_question(data)
    if not question and str(data.get('API_TYPE','')).upper() in {'WARMUP','WARMUP_STATUS'}:
        question=str(data['API_TYPE']).upper()
    if question=='__verify__':return {'code':0,'data':{'text':'verified'}}
    ident=str(data.get('request_id') or uuid.uuid4().hex);data['request_id']=ident
    result={'request_id':ident,'chat_adapter_revision':REVISION,'execution_transport':'in-process'}
    operation=str(data.get('API_TYPE') or question).strip().upper()
    if operation=='SSE_CHECK':
        return {'code':0,'data':{**result,'text':'직접 채팅 SSE 연결 확인',
            'answer_status':'diagnostics','sse_check':{'chat_sse_supported':True,
                'route':'/chat','contract':'genos-chat-sse-v1',
                'chat_adapter_revision':REVISION}}}
    if not question or view._BARE_UUID.fullmatch(question):
        return {'code':0,'data':{**public_fields(data),**result,'text':'질문을 입력해 주세요.','answer_status':'invalid_input'}}
    ad_allowed=trusted_platform or not (os.environ.get('GENOS_RUNTIME_DIR') or os.environ.get('GENOS_DATA_ROOT'))
    if question.strip()=='[AD모드 시작]' and not ad_allowed:
        return {'code':0,'data':{**result,'answer_status':'error','text':'AD_GATEWAY: existing platform gateway access required.'}}
    if ad_allowed:
        probe=await call_service({'API_TYPE':'AD_PROBE','question':question,'request_id':ident,
            'ad_session_id':str(data.get('chatId') or data.get('chat_id') or data.get('sessionId') or data.get('session_id') or ''),
            'ad_channel':view._ad_channel(data)})
        ad=view.unwrap(probe)
        if ad.get('response_schema')=='ad-mode-v1':return {'code':0,'data':{**public_fields(data),**result,**view._ad_result(ad)}}
    started=time.perf_counter();events=[]
    runtime=Path(os.environ.get('GENOS_RUNTIME_DIR') or Path(__file__).resolve().parents[2]/'90_RUNTIME/semantic')
    try:
        operation=str(data.get('API_TYPE') or question).upper()
        body=({'API_TYPE':operation,'request_id':ident} if operation in {'WARMUP','WARMUP_STATUS'}
              else request_body(data,question,trusted_platform))
        def sink(event):
            if len(events)<256:events.append(event)
            if on_progress is not None:on_progress(event)
        if ad_allowed:body={**body,'ad_session_id':str(data.get('chatId') or data.get('sessionId') or data.get('session_id') or ''),'ad_channel':view._ad_channel(data)}
        # Initialize logging before the collector: the first lazy service import
        # must not remove the handler attached to this request.
        from .observability import configure
        configure()
        answer_context=capture_answer(ident,on_answer) if on_answer is not None else nullcontext()
        with progress.capture(ident,runtime,sink),answer_context:
            response=await call_service(body)
        raw=view.unwrap(response)
        if raw.get('response_schema')=='ad-mode-v1':
            return {'code':0,'data':{**public_fields(data),**result,**view._ad_result(raw)}}
        if operation in {'WARMUP','WARMUP_STATUS'}:
            import json
            result.update(text=json.dumps(raw,ensure_ascii=False),answer_status='diagnostics')
        else:
            failed=isinstance(raw.get('_gateway_status'),int) and raw['_gateway_status']>=400
            result.update(text=view._for_markdown(view.render(raw)),run_id=raw.get('run_id'),
                          judgment_display_revision=view.JUDGMENT_DISPLAY_REVISION,
                          answer_status=view._completion_answer_status(
                              raw, bool(view._public_answer_text(raw)) and not failed))
            display=view._ChatProgress({});display.enabled=False;display.show_progress=True
            for event in events:await display.progress(event)
            if display.blocks:result['agentFlowExecutedData']=display.blocks
            case=(raw.get('assembly',{}).get('term_agent') or {}).get('case')
            if isinstance(case,dict):result['case']=case
            for name in ('question_id','revision','experience_id','status','executed','response_schema'):
                if name in raw:result[name]=raw[name]
    except Exception as exc:
        from . import observability as obs
        obs.event(obs.get_logger('chat'),'chat.failed',level=40,request_id=ident,error_type=type(exc).__name__)
        result.update(text='지금 답변을 가져오지 못했습니다. (추적 번호: '+ident+')',
                      answer_status='failed',error_type=type(exc).__name__)
    result['tm_total']=round(time.perf_counter()-started,3)
    return {'code':0,'data':{**public_fields(data),**result}}
