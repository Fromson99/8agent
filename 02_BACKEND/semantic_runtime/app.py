from semantic_runtime.legal_agent.shortcut_store import selected_store
from contextlib import asynccontextmanager
import json
import os as _os
from .oracle_runtime_paths import Path
import re
from . import runtime_sqlite as sqlite3
import time
import uuid
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from jsonschema import ValidationError
from .contracts import Contracts,write
from .feedback import record_feedback
from .pipeline import Pipeline
from .provider import Haiku
from .storage import Store
from . import observability as obs


log = obs.get_logger("app")


def legal_error_payload(exc, request_id=None, *, status=None):
    from .legal_agent.investigation_diagnostics import exception_diagnostics
    from .chat_adapter import views
    request_id = request_id or obs._CONTEXT.get().get('request_id')
    public = views().public_failure(request_id, status=status, exc=exc)
    from .legal_agent.storage_admission import StorageCapacity
    if isinstance(exc, StorageCapacity):
        public.update(error_code=exc.code, message='기록 보관 공간이 부족해 추가 실행을 중단했습니다. '
            '기존 기록은 보존됩니다. 관리자에게 저장공간 확인을 요청해 주세요.')
    obs.event(log, 'request.error', level=40, request_id=public['request_id'],
              error_type=type(exc).__name__, failure_diagnostics=exception_diagnostics(exc))
    return public


def external_documents(documents, approved, store, team_id=None):
    """Default public scope respects selected team; explicit inputs stay strict."""
    if documents is None:
        documents = list(approved)
        if team_id is not None:
            from .team_scope import select_documents
            documents = sorted(set(documents) & set(select_documents(store, team_id)))
    if not documents or set(documents) - set(approved):
        raise ValueError('local external model document scope includes an unapproved source')
    return documents


def create_app(root,generation,*,contracts_root=None,release=None,provider=None,vector=None,implementation=None,
               legal_agent_profile=None,legal_agent_transport=None,workspace_root=None,runtime_root=None,
               memory_factory=None,memory_identity=None,basis_factory=None,data_store=None,
               knowledge_factory=None,knowledge_identity=None):
    root=Path(root);contracts_root=Path(contracts_root or root)
    with obs.step(log, 'bootstrap.source_store'):
        store=data_store if data_store is not None else Store(generation)
    with obs.step(log, 'bootstrap.contracts'):
        contracts=Contracts(contracts_root)
        if contracts.pipeline.get('document_build', {}).get('require_latest_selection'):
            store.selection.require_latest()
    selected_implementation=implementation or contracts.pipeline['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent'].get('implementation')
    if selected_implementation in ('legal-agent-v1', 'legal-agent-tools-v2', 'legal-agent-tools-v3', 'legal-agent-tools-v4', 'legal-agent-tools-v5','legal-agent-unified-v6'):
        from lawrag.platform.workspace import load_layout
        layout=load_layout(workspace_root or contracts_root)
        runtime=Path(runtime_root) if runtime_root is not None else root/layout.path('runtime').relative_to(layout.root)/'semantic'
    else:
        runtime=root/'90_RUNTIME/semantic'
    runs=runtime/'runs';feedback=runtime/'feedback'
    if provider is None:
        import os
        provider=Haiku(root,runtime/'provider',store.manifest['export_allowed'],
                       backend=os.environ.get('SEMANTIC_LLM_BACKEND','anthropic'),
                       endpoint=os.environ.get('SEMANTIC_LLM_ENDPOINT'),
                       trust_zone=os.environ.get('SEMANTIC_LLM_TRUST_ZONE','external'))
    with obs.step(log, 'bootstrap.pipeline'):
        pipeline=Pipeline(contracts_root,store,provider,vector,implementation=implementation,
                          legal_agent_profile=legal_agent_profile,legal_agent_transport=legal_agent_transport)
    is_legal_agent=pipeline.profile_id in ('legal-agent-rag-v1', 'legal-agent-rag-v2', 'legal-agent-rag-v3', 'legal-agent-rag-v4', 'legal-agent-rag-v5','legal-agent-rag-v6')
    unified=pipeline.profile_id=='legal-agent-rag-v6'
    pipeline.task_harness_journal = runtime/'task-harness'/'execution.sqlite'
    pipeline.runtime_dir=runtime
    pipeline.relation_issues = runtime/'relation-issues'/'rejections.sqlite'
    @asynccontextmanager
    async def lifespan(app):
        if is_legal_agent:
            from .legal_agent.publication import recover
            from .legal_agent.source_bundle import validate_current
            recover(runtime/'legal-agent/runs',runs,
                    publication_guard=lambda repo, value: validate_current(repo,value,store),
                    contracts=contracts, release=release)
            if unified and pipeline.contracts.pipeline.get('shortcut_v4',{}).get('features',{}).get('capture') and (selected_store(runtime)).is_file():
                from .legal_agent.shortcut_cases import ShortcutCases
                cases=ShortcutCases(selected_store(runtime),None,None)
                try:cases.recover_requests()
                finally:cases.close()
            if unified and (runtime/'case-memory'/'cases-v3.sqlite').is_file():
                from .legal_agent.case_repository import CaseRepository
                cases=CaseRepository(runtime/'case-memory'/'cases-v3.sqlite',None,None)
                try:cases.recover_requests()
                finally:cases.close()
        try:
            yield
        finally:
            store.close()
    from .document_aliases import status as alias_status
    aliases=alias_status(pipeline.contracts.root,pipeline.term_agent.config,store)
    app=FastAPI(title='용어 기반 법률 검색',version='3.0.0',lifespan=lifespan)
    app.state.pipeline=pipeline
    from lawrag.api.routers.legal_knowledge import install as install_knowledge
    install_knowledge(app,pipeline,factory=knowledge_factory,identity=knowledge_identity)
    from .basis_links.api import install as install_basis
    install_basis(app,pipeline,runtime,release,memory_identity,basis_factory)
    workflow_dispatch = None
    if is_legal_agent and contracts.pipeline.get('workflows',{}).get('enabled') is True:
        from .workflow_bridge import install
        workflow_dispatch = install(app,pipeline,runtime,release,memory_identity)
        pipeline.run_workflow = app.state.workflow_runtime.execute

    from .legal_agent.errors import LegalAgentError
    @app.exception_handler(LegalAgentError)
    async def legal_agent_failure(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.http_status,content=legal_error_payload(exc))

    @app.exception_handler(ValueError)
    async def bad_value(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422,content=legal_error_payload(exc, status=422))

    @app.exception_handler(KeyError)
    async def missing(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404,content=legal_error_payload(exc, status=404))

    @app.exception_handler(ValidationError)
    async def bad_contract(request,exc):
        # A request that fails the runtime contract is the caller's error, not a server fault.
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422,content=legal_error_payload(exc, status=422))

    from starlette.exceptions import HTTPException as StarletteHTTPException
    from fastapi.exceptions import RequestValidationError
    @app.exception_handler(StarletteHTTPException)
    async def http_failure(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status_code, content=legal_error_payload(exc))
    @app.exception_handler(RequestValidationError)
    async def request_failure(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422, content=legal_error_payload(exc, status=422))
    @app.exception_handler(Exception)
    async def unexpected_failure(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content=legal_error_payload(exc, status=500))

    @app.get('/health')
    @app.get('/v1/pipeline/status')
    def health():
        model=(pipeline.term_agent.profile.get('model_binding') or {}).get('model') if is_legal_agent else getattr(provider,'model',None)
        return {'status':'ok','runtime':'term-runtime-v1','release':release,
                'generation_id':store.manifest['generation_id'],'data_status':store.manifest['data_status'],
                'counts':store.manifest['counts'],'legacy_fallback':False,
                'search_selection':{'sha256':store.selection.fingerprint,
                    'excluded_documents':len(store.selection.excluded)},
                'quality_certified':False,'vector':'NOT_USED',
                'llm_model':model,'rag_mode':pipeline.term_agent.config.get('implementation','term-agent-v1'),'term_agent_quality_certified':False,'external_export_allowed':store.manifest['export_allowed'],'document_aliases':aliases}

    @app.get('/v1/rag/search')
    def search(q:str,doc_id:str|None=None,scope:str|None=None,limit:int=Query(40,ge=1,le=100),team_id:str|None=None):
        return pipeline.retrieve(pipeline.plan(q,[doc_id] if doc_id else None,scope,team_id=team_id),limit)

    def team_documents(team_id):
        from .team_scope import select_documents, prepared_catalogue
        return set(select_documents(store,team_id)) if team_id is not None else set(prepared_catalogue(store)['ids'])

    def check_team_document(doc_id,team_id):
        allowed=team_documents(team_id)
        if allowed is not None and doc_id not in allowed:
            if team_id is None: raise KeyError(doc_id)
            raise ValueError('document outside selected team')

    @app.get('/v1/rag/teams')
    def teams():
        from .team_scope import catalogue
        return catalogue(store)

    @app.get('/v1/rag/section')
    def section(doc_id:str,node:str,team_id:str|None=None):
        check_team_document(doc_id,team_id)
        return store.section(doc_id,node)

    @app.get('/v1/rag/scopes')
    def scopes(team_id:str|None=None):
        from .document_roles import SCOPES, DEFAULT_SCOPE
        default_scope = '전체' if pipeline.profile_id in ('legal-agent-rag-v2', 'legal-agent-rag-v3', 'legal-agent-rag-v4', 'legal-agent-rag-v5') else DEFAULT_SCOPE
        roles=pipeline.document_roles()
        allowed=team_documents(team_id)
        return {'documents':[{**dict(r),'document_role':roles[r['document_id']]} for r in store.db.execute('SELECT document_id,name FROM document ORDER BY name') if allowed is None or r['document_id'] in allowed],
                'scopes':[{'name':name,'description':text,'default':name==default_scope,
                           'document_count':len(set(pipeline.scope_documents(name)) & (allowed if allowed is not None else set(roles)))} for name,text in SCOPES.items()]}

    @app.get('/v1/rag/documents')
    def documents(category:str='all',folder:str='',title_query:str='',offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500),team_id:str|None=None):
        from .document_browser import documents as browse
        from .folder_navigation import load_origin_projection
        projection=load_origin_projection(pipeline.contracts.root,pipeline.term_agent.config,store)
        return browse(store,category=category,folder=folder,title_query=title_query,offset=offset,limit=limit,projection=projection,document_ids=team_documents(team_id))

    @app.get('/v1/rag/document/outline')
    def document_outline(doc_id:str,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500),team_id:str|None=None):
        from .document_browser import outline
        check_team_document(doc_id,team_id)
        return outline(store,doc_id,offset=offset,limit=limit)

    @app.get('/v1/rag/document/read')
    def document_read(doc_id:str,unit_id:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=500),team_id:str|None=None):
        from .document_browser import read
        check_team_document(doc_id,team_id)
        return read(store,doc_id,unit_id=unit_id,offset=offset,limit=limit)

    @app.get('/rag/source-tiers.js')
    def source_tiers_script():
        from fastapi.responses import Response
        from .legal_agent.source_tiers_ui import SCRIPT
        return Response(SCRIPT,media_type='application/javascript')

    def source_journal(path):
        from .legal_agent import journal_storage
        with journal_storage.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
        if version==6:
            from .legal_agent.unified_repository import UnifiedRepository
            return UnifiedRepository(path)
        if version==5:
            from .legal_agent.obligation_repository import ObligationRepository
            return ObligationRepository(path)
        from .legal_agent.tiers_repository import TiersRepository
        return TiersRepository(path)

    @app.get('/v1/rag/source-candidates')
    def source_candidates(run_id:str,offset:int=Query(0,ge=0)):
        from html import escape
        from .legal_agent.tiers_repository import TiersRepository
        from .legal_agent.source_bundle import validate_current
        if not re.fullmatch(r'[A-Za-z0-9_-]+',run_id):raise HTTPException(404,'실행을 확인할 수 없습니다.')
        paths=list((runtime/'legal-agent/runs').glob('*/'+run_id+'/journal.sqlite'))
        if len(paths)!=1:raise HTTPException(404,'실행을 확인할 수 없습니다.')
        repo=source_journal(paths[0])
        try:
            row=repo.db.execute("SELECT result_json FROM publication WHERE status='PUBLISHED'").fetchone()
            if not row:
                status=repo.run()['status']
                raise HTTPException(503 if status in ('RUNNING','COMMIT_READY') else 404,
                                    '출처 발행 중입니다.' if status in ('RUNNING','COMMIT_READY') else '발행 결과가 없습니다.')
            value=json.loads(row[0]);validate_current(repo,value,store)
            from .legal_agent.source_candidates import inventory
            store.check_unchanged()
            current=store.manifest
            allowed=set(current['scope']['document_version_ids'])&set(repo.binding['scope']['document_version_ids'])
            allowed -= store.selection.excluded
            candidates=[e for e in inventory(repo) if e['document_id'] in allowed]
            labels={'DISCOVERED_NOT_READ':'발견 · 원문 미열람','READ_UNSELECTED':'열람 · 미채택','PENDING':'추가 판단 대기'}
            items=''.join('<li>'+escape(e['document_name']+' · '+str(e['coordinate'] or e['unit_id'])+' · '+labels[e['status']])+('</li>') for e in candidates[offset:offset+20])
            more='<a href="/v1/rag/source-candidates?run_id='+run_id+'&amp;offset='+str(offset+20)+'">다음 후보</a>' if offset+20<len(candidates) else ''
            return HTMLResponse('<!doctype html><meta charset="utf-8"><h1>추가 확인 후보</h1><p>기본 출처에 포함하지 않은 자료입니다.</p><ul>'+items+'</ul>'+more)
        finally:repo.close()

    @app.get('/v1/rag/source')
    def selected_source(run_id:str,selection_id:str):
        from html import escape
        from .legal_agent.tiers_repository import TiersRepository
        from .legal_agent.source_bundle import validate_current
        if not re.fullmatch(r'[A-Za-z0-9_-]+',run_id) or not re.fullmatch(r'SS[a-f0-9]+',selection_id):
            raise HTTPException(404,'출처를 확인할 수 없습니다.')
        journals=list((runtime/'legal-agent/runs').glob('*/'+run_id+'/journal.sqlite'))
        if len(journals)!=1: raise HTTPException(404,'출처를 확인할 수 없습니다.')
        repo=source_journal(journals[0])
        try:
            row=repo.db.execute("SELECT result_json FROM publication WHERE status='PUBLISHED'").fetchone()
            if not row:
                status=repo.run()['status']
                raise HTTPException(503 if status in ('RUNNING','COMMIT_READY') else 404,
                                    '출처 발행 중입니다.' if status in ('RUNNING','COMMIT_READY') else '발행된 출처가 없습니다.')
            value=json.loads(row[0]);validate_current(repo,value,store)
            card=next((x for x in value['assembly']['term_agent']['source_bundle']['sources'] if x['selection_id']==selection_id),None)
            if card is None: raise HTTPException(404,'선택된 출처가 없습니다.')
            text=''.join('<p>'+escape(p['text'])+'</p>' for p in card['spans'])
            return HTMLResponse('<!doctype html><meta charset="utf-8"><title>선택 원문</title><h1>'+escape(card['document_name'])+'</h1><p>'+escape(card['coordinate_label'])+'</p><p>선택 범위 · 해석 미확정</p>'+text)
        finally:repo.close()

    @app.get('/v1/rag/nodes')
    def nodes(doc_id:str,team_id:str|None=None):
        check_team_document(doc_id,team_id)
        return {'nodes':[{'id':r['unit_id'],'parent':r['parent_id'],'title':json.loads(r['json']).get('title','')}
                         for r in store.db.execute('SELECT * FROM source_unit WHERE document_id=?',(doc_id,))]}

    @app.get('/v1/rag/links/summary')
    def link_summary():
        return {'counts':pipeline.term_agent.get_index().manifest['counts']}

    @app.get('/v1/rag/links')
    def links(source_id:str,team_id:str|None=None):
        allowed=team_documents(team_id)
        db=pipeline.term_agent.get_index().resident_connect()
        try:
            if allowed is not None:
                source=db.execute('SELECT document_id FROM source WHERE id=?',(source_id,)).fetchone()
                if source is None or source[0] not in allowed:raise ValueError('source outside selected team')
            references=[]
            for ident,raw in db.execute('SELECT r.id,r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id WHERE e.source_id=?',(source_id,)):
                if allowed is not None:
                    endpoints={r[0] for r in db.execute('SELECT s.document_id FROM reference_end e JOIN source s ON s.id=e.source_id WHERE e.reference_id=?',(ident,))}
                    if endpoints-allowed:continue
                references.append(json.loads(raw))
            return {'references':references}
        finally:db.close()

    @app.post('/v1/rag/ask')
    def ask(body:dict,request:Request=None):
        from .execution_metrics import capture
        with capture() as metrics:
            from .basis_links.execution import CURRENT
            # Workflow and session ingress prepare their own scoped principal.
            # Do not demand a separate management identity before routing them.
            # Clear any enclosing context so child work cannot inherit another
            # request's relationship scope; restore it on both success and error.
            token=CURRENT.set(None)
            try:result = execute_ask(body, request)
            finally:
                CURRENT.reset(token)
            if isinstance(result, dict) and result.get('response_schema') != 'ad-mode-v1':
                result = {**result, 'execution_stats': metrics.snapshot()}
            from .session_identity import public_result as session_result
            result=session_result(result,body.get('session_id'))
            return result

    def session_inputs(body,request,*,require_memory=False):
        from .legal_agent.memory_identity import prepare
        trusted=memory_identity(request) if memory_identity is not None else None
        if memory_identity is not None and not isinstance(trusted,dict):
            raise HTTPException(403,'서버의 팀·문서 범위를 확인할 수 없습니다.')
        return prepare(pipeline,runtime,body,trusted,require_memory=require_memory)

    def execute_ask(body:dict,request:Request=None):
        from .legal_agent.storage_admission import admission
        with admission(runtime):
            return execute_ask_admitted(body,request)

    def execute_ask_admitted(body:dict,request:Request=None):
        started=time.perf_counter()
        ident=uuid.uuid4().hex
        question=body.get('question',body.get('q'))
        if workflow_dispatch is not None:
            from .workflow_bridge import package
            from importlib import import_module
            if import_module(package()+'.contracts').route(body):
                return workflow_dispatch(body,request)
        # Disabled administration never probes SQL sessions or a deployment workspace.
        # Keep the management implementation available without putting it on legal ingress.
        if pipeline.contracts.pipeline.get('ad_management',{}).get('enabled') is True:
            if getattr(app.state,'basis_chat',None):
                basis_ad=app.state.basis_chat(body,request)
                if basis_ad is not None:return basis_ad
            from .ad_mode import handle as handle_ad
            from .ad_gateway import workspace as ad_workspace
            from .ad_model import interpret as ad_interpret
            ad=handle_ad(selected_store(runtime),(ad_workspace() if (_os.environ.get('TEAM_ID') or _os.environ.get('AD_WORKSPACE') or not _os.environ.get('GENOS_RUNTIME_DIR')) else 'request'),body.get('ad_channel','genos-chat'),body.get('ad_session_id',body.get('session_id','')),question,body.get('request_id',ident),interpret=ad_interpret)
            if ad is not None:return ad
        elif isinstance(question,str) and question.strip() in ('[AD모드 시작]','[AD모드 종료]'):
            raise HTTPException(403,'AD_DISABLED: 관리 모드는 비활성화되어 있습니다.')
        if not isinstance(question,str) or not question.strip():raise ValueError('question must be a nonempty string')
        docs=body.get('document_ids')
        if docs is not None and (not isinstance(docs,list) or any(not isinstance(x,str) for x in docs)):raise ValueError('document_ids must be a string array')
        use_llm=body.get('use_llm',True)
        if type(use_llm) is not bool:raise ValueError('use_llm must be boolean')
        scope=body.get('scope')
        if scope is not None and not isinstance(scope,str):raise ValueError('scope must be a string')
        allowed={'question','q','document_ids','use_llm','scope','team_id','public_question','ad_session_id','ad_channel'}
        if body.get('memory') is True or unified:
            allowed.update({'memory','session_id','request_id','user_id','expected_revision','memory_authorization','investigation_id','investigation_revision','branch_id','review_action'})
        if set(body)-allowed:raise ValueError('unsupported request fields')
        if 'review_action' in body and (not unified or not body.get('session_id')):
            raise ValueError('review actions require an authenticated case session')
        external = getattr(pipeline.term_agent.transport, 'public_scope', None) if is_legal_agent else None
        if external is not None and (use_llm or 'review_action' in body):
            if body.get('public_question') is not True:
                raise ValueError('local external model requires public_question=true')
            if scope is not None:
                raise ValueError('local external model requires explicit public document scope')
            docs = external_documents(docs, external, store, body.get('team_id'))
        elif 'public_question' in body:
            raise ValueError('public_question is only used for local external model requests')
        case_options={}
        if unified and (body.get('memory') is True or 'session_id' in body):
            if not use_llm and 'review_action' not in body:raise ValueError('case requests require a model')
            revision=body.get('expected_revision')
            if revision is not None and (type(revision) is not int or revision<1):raise ValueError('invalid expected revision')
            body,principal=session_inputs(body,request)
            principal={**principal,'authenticated':True,'team_scope_bound':memory_identity is None}
            if external is not None:
                principal['document_ids']=sorted(set(principal['document_ids'])&set(external))
            for field in ('user_id','team_id'):
                if body.get(field) is not None and body[field]!=principal[field]:raise ValueError('case principal mismatch')
            for field in ('session_id','request_id'):
                if not isinstance(body.get(field),str) or not body[field].strip() or len(body[field])>256:raise ValueError('valid '+field+' required')
            if docs is not None and (not docs or not set(docs)<=set(principal['document_ids'])):raise ValueError('case document scope denied')
            if scope is not None:
                docs=sorted(set(pipeline.scope_documents(scope))&set(principal['document_ids']))
                if not docs:raise ValueError('scope has no authorized documents')
            safe_body={k:v for k,v in body.items() if k not in ('memory_authorization','scope','q')}
            safe_body.update(question=question,document_ids=docs or list(principal['document_ids']))
            case_options={'case_body':safe_body,'principal':principal}
            scope=None
        if body.get('memory') is True and not unified:
            from .legal_agent.corrected_memory import Conflict, MemoryError
            from .legal_agent.memory_binding import factory as default_memory_factory, public_result
            if pipeline.profile_id!='legal-agent-rag-v5':raise ValueError('memory requires v5 legal agent runtime')
            if scope is not None:raise ValueError('memory uses explicit documents and authenticated team scope')
            body,principal=session_inputs(body,request,require_memory=True)
            for field in ('user_id','team_id'):
                if body.get(field) is not None and body[field]!=principal[field]:raise ValueError('memory principal mismatch')
            for field in ('session_id','request_id'):
                if not isinstance(body.get(field),str) or not body[field].strip() or len(body[field])>256:raise ValueError('valid '+field+' required')
            requested=body.get('document_ids')
            if requested is not None and (not requested or not set(requested)<=set(principal['document_ids'])):
                raise ValueError('memory document scope denied')
            # Authentication tokens never enter memory events, model input or persisted fingerprints.
            work_body={k:v for k,v in body.items() if k!='memory_authorization'}
            memory=(memory_factory or default_memory_factory)(pipeline,runtime,work_body,principal)
            try:
                return {**public_result(memory,memory.execute(work_body,principal)),'request_id':body['request_id'],
                        'response_schema':'corrected-memory-response-v2','quality_certified':False}
            except Conflict as exc:raise HTTPException(409,str(exc)) from exc
            finally:memory.close()
        team_options={}
        if 'team_id' in body:
            # Explicit null/empty selectors must not silently become an all-team request.
            from .team_scope import validate_team_id
            with obs.context(run_id=ident), obs.step(log,'ask.team_validate'):
                validate_team_id(body['team_id'])
            team_options['team_id']=body['team_id']
        trusted_basis_identity = (memory_identity is not None or
            getattr(getattr(request,'state',None),'workflow_principal',None) is not None)
        if (getattr(pipeline,'basis_factory',None) and not case_options and
                (not unified or trusted_basis_identity)):
            # Unified RAG prepares team/document scope for both session and
            # ephemeral requests, then binds it in memory_binding. Do not demand
            # a relationship-management identity before that normal RAG path.
            # Explicit host identities and older native RAG retain their checks;
            # comparison binds it in parent_task after reading internal sources.
            from .basis_links.execution import CURRENT
            CURRENT.set((pipeline.basis_factory,app.state.basis_identity(request,body)))
        with obs.context(run_id=ident):
            obs.event(log,'ask.started',question_chars=len(question or '') if isinstance(question,str) else 0,document_filter_count=len(docs or []),use_llm=use_llm)
            try:
                if is_legal_agent:
                    genos_selected = bool(_os.environ.get('GENOS_GENERATION', '').strip() or
                                          _os.environ.get('GENOS_DATA_ROOT', '').strip())
                    deferred = not getattr(store,'is_oracle_query',False) and genos_selected and _os.environ.get(
                        'GENOS_DEFER_PUBLICATION', '1').strip().lower() not in {'0', 'false', 'off'}
                    run=pipeline.run(question,docs,use_llm,scope,execution_context={
                        'run_id':ident,'release':release,'runtime':runtime,'publish':True,
                        'defer_publication':deferred,
                        'external_public_question':external is not None and use_llm,**case_options},**team_options)
                else:
                    run=pipeline.run(question,docs,use_llm,scope,**team_options)
                    run['run_id']=ident;run['release']=release
                    write(runs/(ident+'.json'),run)
            except Exception as exc:
                from .legal_agent.corrected_memory import Conflict
                if isinstance(exc,Conflict):raise HTTPException(409,str(exc)) from exc
                if isinstance(exc,LegalAgentError) or hasattr(exc,'diagnostics'):exc.run_id=ident
                from .legal_agent.investigation_diagnostics import exception_diagnostics
                obs.event(log,'ask.failed',level=40,exc_info=True,error_type=type(exc).__name__,
                    error_code=getattr(exc,'code',type(exc).__name__),failure_diagnostics=exception_diagnostics(exc),
                    duration_ms=int((time.perf_counter()-started)*1000))
                raise
            if (pipeline.term_agent.config.get('learning', {}).get('capture') is True
                    and pipeline.term_agent.config.get('implementation') not in ('definition-scope-harness-v1','legal-agent-v1','legal-agent-tools-v2','legal-agent-tools-v3', 'legal-agent-tools-v4', 'legal-agent-tools-v5')):
                try:
                    from .learning_store import collect_run
                    candidate_ids=collect_run(runtime/'learning'/'review.sqlite', runs/(ident+'.json'))
                    obs.event(log,'learning.collected',candidate_count=len(candidate_ids))
                except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
                    # The committed run can be replayed with the CLI if collection fails.
                    obs.event(log,'learning.capture_failed',level=40,error_type=type(exc).__name__)
            answer=run.get('answer',{})
            obs.event(log,'ask.finished',duration_ms=int((time.perf_counter()-started)*1000),answer_chars=len(answer.get('text','')),claim_count=len(answer.get('claims',[])),unresolved_count=len(answer.get('unresolved',[])))
            from .chat_adapter import views
            return views().public_response(run)

    def require_ad(body):
        if pipeline.contracts.pipeline.get('ad_management',{}).get('enabled') is not True:
            raise HTTPException(403,'AD_DISABLED: 관리 모드는 비활성화되어 있습니다.')
        import os
        from . import runtime_sqlite as sqlite3
        from .ad_store import fingerprint,table_exists
        from .ad_gateway import workspace
        path=selected_store(runtime)
        if not path.is_file():raise HTTPException(403,'AD_REQUIRED: [AD모드 시작]을 단독 입력하세요.')
        db=sqlite3.connect(path)
        try:
            key=fingerprint([workspace(),body.get('ad_channel','genos-chat'),body.get('ad_session_id',body.get('session_id',''))])
            row=db.execute('SELECT enabled FROM ad_session WHERE id=?',(key,)).fetchone() if table_exists(db,'ad_session') else None
            if not row or not row[0]:raise HTTPException(403,'AD_REQUIRED: [AD모드 시작]을 단독 입력하세요.')
        finally:db.close()

    @app.post('/v1/rag/memory/command')
    def shortcut_command(body:dict,request:Request):
        require_ad(body)
        if not unified or not pipeline.contracts.pipeline.get('shortcut_v4',{}).get('features',{}).get('capture'):
            raise ValueError('shortcut v4 capture required')
        allowed={'operation','arguments','user_id','team_id','session_id','request_id','memory_authorization','public_question','use_llm','memory'}
        if set(body)-allowed:raise ValueError('unsupported shortcut command fields')
        body,principal=session_inputs(body,request)
        principal={**principal,'authenticated':True}
        for field in ('user_id','team_id'):
            if body.get(field) is not None and body[field]!=principal[field]:raise ValueError('case principal mismatch')
        from .legal_agent.shortcut_store import store_owner
        from .legal_agent.shortcut_repository import ShortcutRepository
        from .legal_agent.shortcut_commands import execute
        from .legal_agent.corrected_memory import Conflict
        with store_owner(runtime):
            repo=ShortcutRepository(selected_store(runtime))
            try:return execute(repo,principal,body)
            except Conflict as exc:raise HTTPException(409,str(exc)) from exc
            finally:repo.close()

    @app.post('/v1/rag/memory/query')
    def memory_query(body:dict,request:Request):
        require_ad(body)
        if not unified:raise ValueError('unified legal agent profile required')
        from .legal_agent.unified_runtime import open_cases
        from .legal_agent.knowledge_repository import KnowledgeRepository
        allowed={'question','user_id','team_id','session_id','request_id','memory','use_llm','public_question',
                 'memory_authorization','query_kind','experience_id','question_id','after','limit','investigation_id','unit_id','revision','event_id','artifact_id'}
        if set(body)-allowed:raise ValueError('unsupported memory query fields')
        body,principal=session_inputs(body,request)
        for field in ('user_id','team_id'):
            if body.get(field) is not None and body[field]!=principal[field]:raise ValueError('case principal mismatch')
        limit=body.get('limit',32)
        if type(limit) is not int or not 1<=limit<=100:raise ValueError('limit must be 1..100')
        cases=open_cases(pipeline,runtime,body,principal)
        try:
            knowledge=KnowledgeRepository(cases);kind=body.get('query_kind')
            if hasattr(cases,'shortcut'):
                repo=cases.shortcut
                principal={**principal,'authenticated':True}
                if kind=='investigations':return repo.cases(principal,after=body.get('after',''),limit=limit)
                if kind=='investigation':return repo.investigation(body['investigation_id'],principal)
                if kind=='events':return repo.history(body['investigation_id'],principal,after=body.get('after',0),limit=limit)
                if kind=='event':return repo.event(body['event_id'],principal)
                if kind=='artifact':return {'content':repo.read_artifact(body['artifact_id'],principal).decode('utf-8')}
                if kind in ('issues','facts','relations'):
                    case=repo.investigation(body['investigation_id'],principal)
                    if kind=='issues':rows=repo.db.execute('SELECT * FROM sw_issue WHERE investigation=? ORDER BY id LIMIT ?',(case['id'],limit))
                    elif kind=='facts':rows=repo.db.execute('SELECT f.* FROM sw_fact f JOIN sw_fact_head h ON f.id=h.id AND f.revision=h.revision WHERE investigation=? ORDER BY f.id LIMIT ?',(case['id'],limit))
                    else:rows=repo.db.execute('SELECT * FROM sw_relation WHERE scope=? AND (source=? OR target=?) ORDER BY id,revision LIMIT ?',(case['scope'],case['id'],case['id'],limit))
                    return {kind:[dict(row) for row in rows]}

                if kind in ('knowledge','knowledge_draft'):return repo.current(body['unit_id'],body['revision'],principal,allow_draft=kind=='knowledge_draft')
                if kind=='legal_wiki':return repo.search(principal,body.get('question',''),after=body.get('after',''),limit=limit)
            if kind=='experience':return knowledge.page(knowledge.get(body['experience_id'],principal))
            if kind=='legal_wiki':
                return knowledge.wiki(kind,principal,query=body.get('question',''),after=body.get('after',''),limit=limit)
            if kind=='history':return cases.events_page(body['question_id'],principal,after=body.get('after',0),limit=limit)
            if kind=='questions':return knowledge.questions(principal,query=body.get('question',''),after=body.get('after',''),limit=limit)
            raise ValueError('query_kind must be experience, legal_wiki, questions or history')
        finally:cases.close()

    @app.post('/v1/rag/feedback')
    def feedback_post(body:dict):
        ident=body.get('run_id','')
        if not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('invalid run_id')
        path=runs/(ident+'.json')
        if not path.is_file():raise HTTPException(404,'run not found')
        return record_feedback(contracts,path,body.get('signal'),body.get('reason'),feedback)

    @app.get('/v1/rag/feedback')
    def feedback_list():return {'records':[json.loads(p.read_text()) for p in sorted(feedback.glob('*.json'))[-100:]]}

    @app.get('/',response_class=HTMLResponse)
    @app.get('/rag/',response_class=HTMLResponse)
    def home():
        public_toggle = ('<label><input id="public-question" type="checkbox"> '
                         '공개 질문이며 외부 Qwen3.8 전송에 동의합니다</label><br>'
                         if is_legal_agent and getattr(pipeline.term_agent.transport, 'public_scope', None) is not None
                         else '')
        html = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>법률 검색</title>
<style>body{max-width:960px;margin:48px auto;font:16px system-ui;padding:16px}textarea{width:100%;height:100px}button{padding:10px 20px;margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f7;padding:20px}small{color:#555}</style>
<h1>법률 검색</h1><small id="status">데이터 확인 중</small><p><textarea id="q" placeholder="질문을 입력하세요"></textarea></p>
<label><input id="llm" type="checkbox"> LLM 답변 사용</label><br>PUBLIC_TOGGLE<button id="ask">검색하기</button><pre id="result"></pre><section id="sources"></section><details id="audit" hidden><summary>탐색·근거 판단</summary><pre id="audit-text"></pre></details>
<script src="/rag/source-tiers.js"></script><script>const $=id=>document.getElementById(id);fetch('/health').then(r=>r.json()).then(x=>$('status').textContent=`데이터: ${x.generation_id} · ${x.data_status}`);
$('ask').onclick=async()=>{$('result').textContent='검색 중…';$('audit').hidden=true;$('sources').replaceChildren();try{const body={question:$('q').value,use_llm:$('llm').checked};if(body.use_llm&&$('public-question')?.checked)body.public_question=true;const r=await fetch('/v1/rag/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const x=await r.json();renderSourceTiers(x.assembly?.term_agent?.source_bundle);const review=x.assembly?.term_agent?.review_explanation;const a=x.assembly?.term_agent?.exploration_v3;$('audit').hidden=!a;$('audit-text').textContent=a?(a.display_lines||[]).join('\\n'):'';$('result').textContent=x.answer?x.answer.text+'\\n\\n확인 필요: '+x.answer.unresolved.map(z=>z.reason).join(' / '):(x.message||(r.ok?'현재 충분한 법률 검토를 하지 못했습니다. 답변에 필요한 원문 조사·검토가 완료되지 않았습니다.':'현재 충분한 법률 검토를 하지 못했습니다. 잠시 후 다시 요청해 주세요. ('+r.status+')'))+'\\n조회 번호: '+(x.request_id||'');if(review){$('result').textContent+='\\n\\n검토 상태: '+review.outcome+'\\n'+review.items.map(i=>i.reason+' · '+i.impact).join('\\n');}}catch(e){$('result').textContent='현재 충분한 법률 검토를 하지 못했습니다. 잠시 후 다시 요청해 주세요. (connection)';}};</script></html>'''
        return html.replace('PUBLIC_TOGGLE', public_toggle)

    @app.api_route('/{path:path}',methods=['GET','POST','PUT','DELETE'])
    def retired(path:str):raise HTTPException(410,'기존 MAIN 기능은 제거되었습니다. /docs의 최신 API를 사용하세요.')
    return app
