"""HTTP/service ingress. Principal authority comes from middleware/configuration."""
import uuid
import json
import re
from fastapi import Request
from fastapi.responses import JSONResponse
from .contracts import WorkflowError, identity, route, digest
from .runtime import Runtime


def install(app, services, identity_resolver=None):
    runtime=Runtime(services)
    app.state.workflow_runtime=runtime

    @app.exception_handler(WorkflowError)
    async def failure(request,exc):
        return JSONResponse(status_code=exc.http_status,content={
            'response_schema':'workflow-error-v1','status':'failed','error_code':exc.code,
            'message':str(exc),'resume_available':False})

    def principal(request,body):
        from semantic_runtime.session_identity import bind
        if identity_resolver is not None:
            value=identity_resolver(request)
            if not isinstance(value,dict):
                raise WorkflowError('WORKFLOW_SCOPE_REQUIRED','서버의 팀·문서 범위를 확인할 수 없습니다.',403)
        elif request is not None and getattr(request.state,'workflow_principal',None):
            value=request.state.workflow_principal
        else:
            value=None
        try:
            normalized,who=bind(body,value)
        except ValueError as exc:
            raise WorkflowError('WORKFLOW_SESSION_REQUIRED',str(exc),422) from exc
        value=who if value is not None else services.principal(who['user_id'],who['team_id'])
        value=identity(value)
        return normalized,value

    def continuation(request,body):
        normalized,who=principal(request,body)
        run_id=body.get('run_id','')
        # Exact old run references may retain their immutable owner key. The
        # current team/session and current document scope still decide access.
        # No search by user, old-state rewrite, budget reset or hash bypass.
        if isinstance(run_id,str) and re.fullmatch('[a-f0-9]{32}',run_id):
            path=runtime.root/run_id/'journal.sqlite'
            if path.is_file():
                from semantic_runtime.state_sqlite import readonly
                db=readonly(path)
                try:row=db.execute('SELECT request_json,request_hash FROM workflow_state WHERE singleton=1').fetchone()
                finally:db.close()
                if row:
                    saved=json.loads(row[0])
                    if digest(saved)!=row[1]:raise WorkflowError('WORKFLOW_STATE_INTEGRITY','저장된 요청 해시가 다릅니다.',409)
                    if (saved['session_id']==body['session_id'] and saved['principal']['team_id']==who['team_id']):
                        normalized={**normalized,'session_id':body['session_id']}
                        who={**who,'user_id':saved['principal']['user_id']}
        return normalized,who

    def run(body,request=None):
        body=dict(body)
        body['workflow_id']=route(body) or 'risk_team_compare_workflow'
        public_session=body.get('session_id')
        body,who=principal(request,body)
        # Missing chat identity must never collapse into an anonymous session.
        body.setdefault('request_id',uuid.uuid4().hex)
        result=runtime.execute(body,who)
        return services.deliver({**result,'session_id':public_session})

    @app.post('/v1/workflows/run')
    def run_endpoint(body:dict,request:Request):
        return run(body,request)

    @app.post('/v1/workflows/resume')
    def resume_endpoint(body:dict,request:Request):
        if set(body)-{'run_id','session_id','user_id','team_id','expected_revision'}:
            raise WorkflowError('WORKFLOW_INPUT','재개 시 질문·예산·문서 범위를 바꿀 수 없습니다.')
        body,who=continuation(request,body)
        return services.deliver(runtime.resume(body.get('run_id'),who,body.get('session_id'),body.get('expected_revision')))

    @app.get('/v1/workflows/runs/{run_id}')
    def status_endpoint(run_id:str,request:Request,session_id:str,team_id:str|None=None):
        body,who=continuation(request,{'run_id':run_id,'session_id':session_id,**({'team_id':team_id} if team_id is not None else {})})
        return runtime.status(run_id,who,body['session_id'])

    return run
