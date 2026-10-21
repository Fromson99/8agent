"""Shared workflow runtime: one durable budget, isolated state and no ask recursion."""
import json
from pathlib import Path
from types import SimpleNamespace
from .contracts import WorkflowError, digest, route, request as normalize
from .registry import builtin
from .repository import Repository, execution_lock
from .adapters.rag import RagAdapter
from .adapters.model import ModelAdapter
from semantic_runtime import observability as obs


class Runtime:
    def __init__(self, services, registry=None):
        self.services=services
        self.root=services.runtime/'workflows'
        self.registry=registry or builtin(services.pipeline.contracts.pipeline['workflows']['registered'],services.pipeline.contracts.root)

    def execute(self, body, principal, *, resume=False, expected_revision=None):
        principal=self.services.constrain_principal(principal)
        definition=self.registry.resolve(route(body),body.get('workflow_version'),principal['team_id'])
        normalized=normalize(body,principal,definition.normalizer)
        normalized['workflow_version']=definition.manifest['version']
        run_id=digest([normalized['principal'],normalized['session_id'],normalized['request_id']])[:32]
        binding=self.services.binding(normalized,definition.manifest)
        log_request_id = obs._CONTEXT.get().get('request_id') or normalized['request_id']
        with execution_lock(self.root,run_id) as folder, obs.context(
                workflow_run_id=run_id, workflow_request_id=log_request_id):
            journal=folder/'journal.sqlite'
            if journal.is_file():
                import sqlite3
                with sqlite3.connect('file:'+str(journal)+'?mode=ro',uri=True) as db:
                    saved=db.execute('SELECT request_hash,binding_hash FROM workflow_state WHERE singleton=1').fetchone()
                if saved is not None and (saved[0]!=digest(normalized) or saved[1]!=digest(binding)):
                    raise WorkflowError('WORKFLOW_BINDING_CHANGED','같은 요청의 입력·코드·원문 결속이 다릅니다.',409)
            context=self.services.context(normalized,binding,run_id,journal)
            work=self.services.journal(journal,context)
            try:
                repository=Repository(work,normalized,binding)
                state=repository.state()
                obs.event(obs.get_logger('workflow'), 'workflow.started',
                          run_id=run_id, workflow_id=normalized['workflow_id'],
                          stage=state['checkpoint']['stage'], status=state['status'],
                          revision=state['revision'], resume=resume)
                if state['status']=='failed' and state['result'] is None:
                    raise WorkflowError('WORKFLOW_TERMINAL_FAILURE','무결성 또는 실행 오류로 중단된 실행입니다. 진단 후 새 요청이 필요합니다.',409)
                if expected_revision is not None and state['revision']!=expected_revision:
                    raise WorkflowError('WORKFLOW_STALE_REVISION','이미 변경된 실행 상태입니다.',409)
                if state['result'] is None and state['revision']>1 and not resume:
                    raise WorkflowError('WORKFLOW_RESUME_REQUIRED','이전 실행이 중단되었습니다. 현재 revision으로 재개해 주세요.',409)
                with self.services.tools(work,context) as port:
                    rag=RagAdapter(repository,port)
                    ctx=SimpleNamespace(request=normalized,definition=definition,context=context,
                        repo=repository,rag=rag,model=ModelAdapter(repository,self.services,context))
                    if state['result'] is not None:
                        port.verify_all()
                        from semantic_runtime.basis_links.integration import finish_workflow
                        return finish_workflow(ctx,state['result'])
                    ctx.view=lambda checkpoint:self.view(ctx,checkpoint)
                    ctx.continuation=lambda ident:self.continuation(ident,principal,normalized)
                    try:
                        from semantic_runtime.basis_links.integration import finish_workflow
                        return finish_workflow(ctx,definition.entrypoint(ctx))
                    except (self.services.BudgetExhausted,self.services.ProposalError,self.services.TransportError,self.services.ToolExecutionError,WorkflowError) as exc:
                        if isinstance(exc,WorkflowError) and exc.http_status in (403,404,409):
                            raise
                        checkpoint=repository.state()['checkpoint']
                        checkpoint['gaps'].append('조사 미완료: '+getattr(exc,'code',type(exc).__name__))
                        work.event('WORKFLOW_STOPPED',{'type':type(exc).__name__,'cause':str(exc),
                            'code':getattr(exc,'code',type(exc).__name__),'stage':checkpoint['stage']})
                        stopped=exc
                    # Leave the investigation exception handler before starting
                    # a distinct final decision. Its schema correction must not
                    # inherit the old deadline error as an implicit cause.
                    if definition.finalizer:
                        try:
                            definition.finalizer(ctx,checkpoint,stopped)
                        except (self.services.BudgetExhausted,self.services.ProposalError,
                                self.services.TransportError,self.services.ToolExecutionError,WorkflowError) as final_error:
                            if isinstance(final_error,WorkflowError) and final_error.http_status in (403,404,409):raise
                            work.event('WORKFLOW_FINALIZATION_FAILED',{'type':type(final_error).__name__,
                                'cause':str(final_error),'original_cause':str(stopped)})
                            checkpoint.setdefault('finalization',{})['status']='SAVED_EVIDENCE_ONLY'
                        repository.save(checkpoint)
                    # Publication only reads saved receipts; no research budget reset.
                    with port.publication_verification():
                        result=definition.reporter(ctx,checkpoint,'partial' if rag.evidence() else 'failed',
                                     getattr(stopped,'code',type(stopped).__name__))
                    checkpoint['stage']='END'
                    return repository.save(checkpoint,status=result['status'],result=result)
            except Exception as exc:
                # Unknown and integrity errors are durable failures, never partial legal findings.
                work.event('WORKFLOW_FAILED',{'type':type(exc).__name__,'cause':str(exc)})
                obs.event(obs.get_logger('workflow'), 'workflow.failed', level=40,
                          exc_info=True, run_id=run_id, error_type=type(exc).__name__)
                # Request conflicts never mutate a healthy run. Unexpected runtime
                # failures end without publishing unverified source material.
                if not isinstance(exc,WorkflowError):
                    state=repository.state()
                    if state['result'] is None:
                        state['checkpoint']['failure']={'type':type(exc).__name__,'cause':str(exc)}
                        repository.save(state['checkpoint'],status='failed')
                raise
            finally:
                work.close()

    def view(self,ctx,state):
        from .presentation import evidence,view
        value=ctx.definition.presenter(ctx,state) if ctx.definition.presenter else view(ctx,state,evidence(ctx,state))
        if len(json.dumps(value,ensure_ascii=False))>self.services.profile['max_context_chars']:
            raise self.services.BudgetExhausted('workflow view requires bounded packets')
        return value

    def continuation(self,run_id,principal,request):
        body,row=self.existing(run_id,principal,request['session_id'])
        if body['workflow_id']!=request['workflow_id'] or body['input']['mode']!=request['input']['mode'] or row['result_json'] is None:
            raise WorkflowError('BASIS_CONTINUATION_BINDING','완료·부분 종료된 같은 업무만 이어서 실행할 수 있습니다.',409)
        result=json.loads(row['result_json'])
        if digest(result)!=row['result_hash']:raise WorkflowError('WORKFLOW_STATE_INTEGRITY','저장 결과 해시가 다릅니다.',409)
        checkpoint=json.loads(row['checkpoint_json'])
        # Only unfinished units need old receipts imported into the new journal.
        needed={e for u in checkpoint.get('units',{}).values() if u['status']!='reviewed'
                for e in u.get('internal',[])+u.get('external',[])+u.get('packet_ids',[])}
        from semantic_runtime.legal_agent.repository import WorkRepository
        from semantic_runtime.state_sqlite import readonly
        import sqlite3
        old=WorkRepository.__new__(WorkRepository);old.db=readonly(self.root/run_id/'journal.sqlite');old.db.row_factory=sqlite3.Row
        try:evidence=[e for e in old.evidence() if e['evidence_id'] in needed]
        finally:old.db.close()
        return {**checkpoint,'request':body,'evidence':evidence,'usage':{'this_run':result['usage'],'previous':result.get('previous_usage')}}

    def existing(self, run_id, principal, session_id):
        principal=self.services.constrain_principal(principal)
        import re,sqlite3
        if not isinstance(run_id,str) or not re.fullmatch('[a-f0-9]{32}',run_id):
            raise WorkflowError('WORKFLOW_NOT_FOUND','실행을 찾을 수 없습니다.',404)
        path=self.root/run_id/'journal.sqlite'
        if not path.is_file():raise WorkflowError('WORKFLOW_NOT_FOUND','실행을 찾을 수 없습니다.',404)
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            row=dict(db.execute('SELECT * FROM workflow_state').fetchone())
            saved=json.loads(row['request_json'])
            if digest(saved)!=row['request_hash'] or digest(json.loads(row['checkpoint_json']))!=row['checkpoint_hash']:
                raise WorkflowError('WORKFLOW_STATE_INTEGRITY','저장된 실행 상태의 해시가 다릅니다.',409)
            if saved['principal']!={k:principal[k] for k in ('user_id','team_id')} or saved['session_id']!=session_id:
                raise WorkflowError('WORKFLOW_NOT_FOUND','실행을 찾을 수 없습니다.',404)
            if set(saved['document_ids'])-set(principal['document_ids']):
                raise WorkflowError('WORKFLOW_SCOPE_CHANGED','실행의 문서 권한이 변경되었습니다.',403)
            definition=self.registry.resolve(saved['workflow_id'],saved['workflow_version'],principal['team_id'])
            if row['binding_hash']!=digest(self.services.binding(saved,definition.manifest)):
                raise WorkflowError('WORKFLOW_BINDING_CHANGED','코드·원문·설정 결속이 변경되었습니다.',409)
            body={k:v for k,v in saved.items() if k!='principal'}
            return body,row

    def status(self,run_id,principal,session_id):
        body,row=self.existing(run_id,principal,session_id)
        # Revalidate exact source bytes before returning a saved answer.
        if row['result_json'] is not None:
            return self.execute(body,principal,resume=True)
        return {'response_schema':'workflow-result-v1','run_id':run_id,'status':row['status'],
                'revision':row['revision'],'stage':json.loads(row['checkpoint_json'])['stage'],
                'resume_available':row['status']=='running','request_id':body['request_id']}

    def resume(self,run_id,principal,session_id,revision):
        body,row=self.existing(run_id,principal,session_id)
        if type(revision) is not int or revision!=row['revision']:
            raise WorkflowError('WORKFLOW_STALE_REVISION','현재 revision이 필요합니다.',409)
        return self.execute(body,principal,resume=True,expected_revision=revision)
