"""GENOS transport adapter for AD. Invoked before legal request logging/routing."""
import os
import uuid
from pathlib import Path
from .ad_mode import handle
from .ad_store import Store
from .ad_backend import Backend
from .ad_jobs import ensure_worker
from .ad_model import interpret
from .legal_agent.shortcut_store import selected_store


def workspace():
    # GENOS gateway/app access is the authority. Chat text never chooses a team.
    value=os.environ.get('TEAM_ID') or os.environ.get('AD_WORKSPACE')
    if not value and os.environ.get('GENOS_RUNTIME_DIR'):
        raise ValueError('AD_WORKSPACE: deployment must bind TEAM_ID; do not take it from a chat message')
    return value or 'request'


def start_worker(runtime, application):
    path=selected_store(runtime)
    if not path.exists() or os.environ.get('AD_WORKER_ENABLED','1')=='0':return
    def compile_item(job,item,guard):
        state=Store(path)
        try:
            row=state.db.execute('SELECT revision FROM sw_investigation WHERE id=?',(item['investigation'],)).fetchone()
            if not row or row[0]!=item['revision']:
                raise ValueError('AD_INPUT_CHANGED: queued case revision differs; inspect report and start a new job')
        finally:state.close()
        app=application();pipeline=app.state.pipeline
        if pipeline.term_agent.transport.binding['trust_zone']!='internal':
            raise ValueError('AD_MODEL: GENOS internal model is required for wiki jobs; no external fallback')
        from lawrag.pipeline.legal_wiki_compiler import build_with_pipeline
        def principal(scope):
            store=Store(path)
            try:return Backend(store,job['workspace']).principal(scope)
            finally:store.close()
        value=build_with_pipeline(pipeline,runtime,principal_for_scope=principal,batch_size=1,
            max_seconds=300,scope=item['scope'],queue_id=item['queue_id'],commit_guard=guard)
        failures=[x for x in value['results'] if x.get('status')=='FAILED']
        if failures:raise ValueError('AD_COMPILER: '+str(failures))
        if not value['results']:
            state=Store(path)
            try:row=state.db.execute('SELECT status FROM sw_queue WHERE id=?',(item['queue_id'],)).fetchone()
            finally:state.close()
            if row and row[0]=='DONE':return {'results':[{'job':item['queue_id'],'status':'DONE','reason':'already processed by earlier page'}]}
            raise ValueError('AD_QUEUE: requested input is no longer pending; inspect queue and retry')
        return value
    ensure_worker(path,compile_item)


def intercept(data,runtime,application):
    body=data.get('json') if isinstance(data.get('json'),dict) else data
    q=body.get('question',body.get('q',''))
    if not isinstance(q,str):return None
    chat=body.get('ad_session_id') or body.get('chatId') or body.get('session_id')
    channel=body.get('ad_channel') or body.get('channel') or 'genos-chat'
    if not chat and q.strip()!='[AD모드 시작]':return None
    if not (os.environ.get('TEAM_ID') or os.environ.get('AD_WORKSPACE')) and os.environ.get('GENOS_RUNTIME_DIR') and q.strip()!='[AD모드 시작]':return None
    try:
        result=handle(selected_store(runtime),workspace(),str(channel),str(chat or ''),q,
                      str(body.get('request_id') or uuid.uuid4().hex),interpret=interpret)
        if result is not None:
            start_worker(runtime,application)
            return {'status':200,'body':result}
    except Exception as exc:
        from .ad_jobs import error_detail
        return {'status':200,'body':{'response_schema':'ad-mode-v1','ad_mode':None,'answer_status':'error','text':error_detail(exc)}}
    return None
