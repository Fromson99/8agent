"""Authenticated review ingress and workspace-local authority composition."""
from contextlib import contextmanager
import getpass
import os
from pathlib import Path
from fastapi import Request, Query
from fastapi.responses import JSONResponse
from .contracts import BasisError,principal,require,as_of
from .repository import Repository
from .sources import SourcePort
from .service import Service


def local_factory(runtime,generation,config=None):
    @contextmanager
    def opened():
        from ..storage import Store
        store=Store(generation);repo=None
        try:
            repo=Repository(Path(runtime)/'basis-links'/'authority.sqlite')
            yield Service(repo,SourcePort(store,config))
        finally:
            if repo:repo.close()
            store.close()
    return opened


def enabled_shared_factory(pipeline,runtime):
    """Explicit batch opt-in at the existing shared runtime; no source DB mutation."""
    import json
    path=Path(runtime)/'basis-links'/'SQLITE_ENABLED.json'
    if not path.is_file():return None
    require(not any(p.is_symlink() for p in (path,*path.parents)),
            'BASIS_BACKEND_PATH','관계 저장 경로에 심볼릭 링크를 사용할 수 없습니다.',503)
    value=json.loads(path.read_text())
    require(value=={'schema_version':'basis-shared-sqlite-v1','database':'authority.sqlite'},
            'BASIS_BACKEND_CONFIG','관계 SQLite 설정이 잘못되었습니다.',503)
    from ..state_sqlite import network_storage
    require(network_storage(path),'BASIS_BACKEND_PATH','GENOS 관계 SQLite는 기존 외부 공유 runtime에 있어야 합니다.',503)
    @contextmanager
    def opened():
        # Borrow the request's already-selected read-only store, including its filter.
        repo=Repository(path.parent/'authority.sqlite')
        try:
            yield Service(repo,SourcePort(pipeline.store,(pipeline.contracts.root,pipeline.term_agent.config)))
        finally:repo.close()
    return opened


def install(app,pipeline,runtime,release,identity_resolver=None,factory=None):
    local=(release or {}).get('mode')=='local-release'
    if factory is None and local:
        factory=local_factory(runtime,pipeline.store.path,(pipeline.contracts.root,pipeline.term_agent.config))
    if factory is None and not local:
        factory=enabled_shared_factory(pipeline,runtime)
    # GENOS never silently substitutes a local SQLite authority for Oracle.
    pipeline.basis_factory=factory
    pipeline.basis_shared_runtime=None if local else Path(runtime)
    def who(request,body):
        value=identity_resolver(request) if identity_resolver else getattr(getattr(request,'state',None),'workflow_principal',None)
        if value is None and local:
            user=os.environ.get('WORKFLOW_USER_ID') or getpass.getuser();team=os.environ.get('TEAM_ID','risk_team')
            from ..team_scope import select_documents
            value={'user_id':user,'team_id':team,'document_ids':select_documents(pipeline.store,team),'basis_review':True}
        principal(value)
        for key in ('user_id','team_id'):
            require(key not in body or body[key]==value[key],'BASIS_IDENTITY','인증된 주체와 요청이 다릅니다.',403)
        return value
    @contextmanager
    def opened():
        nonlocal factory
        import sqlite3
        from .contracts import BasisUnavailable
        if factory is None and not local:
            factory=enabled_shared_factory(pipeline,runtime)
            pipeline.basis_factory=factory
        require(factory is not None,'BASIS_BACKEND_UNCONFIGURED','현장 근거 원장의 승인된 저장·조회 연결이 설정되지 않았습니다.',503)
        try:
            with factory() as service:yield service
        except sqlite3.OperationalError as exc:raise BasisUnavailable() from exc
    def chat(body,request=None):
        if pipeline.contracts.pipeline.get('ad_management',{}).get('enabled') is not True:return None
        if factory is None:return None
        from ..legal_agent.shortcut_store import selected_store
        from ..ad_gateway import workspace
        from ..ad_store import fingerprint
        from ..state_sqlite import readonly
        path=selected_store(runtime)
        if not path.exists():return None
        key=fingerprint([workspace(),body.get('ad_channel','genos-chat'),body.get('ad_session_id',body.get('session_id',''))])
        db=readonly(path)
        try:
            if not db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ad_session'").fetchone():return None
            row=db.execute('SELECT enabled FROM ad_session WHERE id=?',(key,)).fetchone()
            if row is None or not row[0]:return None
        finally:db.close()
        with opened() as service:
            from .chat import handle
            result=handle(service,who(request,body),body,active=True)
            from ..ad_store import Store as ADStore
            state=ADStore(path)
            try:
                with state.transaction():state.db.execute('UPDATE ad_session SET pending_action=? WHERE id=?',('basis_link' if result else None,key))
            finally:state.close()
            return result
    app.state.basis_chat=chat
    app.state.basis_identity=who
    @app.exception_handler(BasisError)
    async def failure(request,exc):
        return JSONResponse(status_code=exc.http_status,content={'response_schema':'basis-error-v1','status':'failed','error_code':exc.code,'message':str(exc)})
    @app.get('/basis/')
    def page():
        from fastapi.responses import HTMLResponse
        return HTMLResponse(Path(__file__).with_name('ui.html').read_text())
    @app.get('/v1/basis-links/documents')
    def documents(request:Request):
        p=who(request,{})
        with opened() as service:
            return {'documents':[{'document_id':d,'name':v['name']} for d,v in service.sources.catalogue.items()
                                 if d in p['document_ids'] and v['category']=='internal']}
    @app.get('/v1/basis-links')
    def listing(request:Request,internal_document_id:str|None=None,as_of_date:str|None=Query(default=None,alias='as_of')):
        as_of(as_of_date)
        with opened() as service:return service.view(who(request,{}),internal_document_id,as_of=as_of_date)
    @app.post('/v1/basis-links/proposals')
    def propose(body:dict,request:Request):
        provenance=body.get('provenance',{'type':'USER_SELECTION'})
        require(isinstance(provenance,dict) and provenance.get('type')=='USER_SELECTION','BASIS_PROVENANCE','직접 입력은 사용자 선택으로만 등록합니다. 실행 근거는 검증된 런타임이 등록합니다.')
        with opened() as service:return service.propose(who(request,body),body)
    @app.post('/v1/basis-links/reviews')
    def review(body:dict,request:Request):
        with opened() as service:
            return service.review_view(who(request,body),body) if 'view_id' in body else service.review(who(request,body),body)
    @app.get('/v1/basis-links/{link_id}/history')
    def history(link_id:str,request:Request):
        with opened() as service:return service.history(who(request,{}),link_id)
    @app.get('/v1/basis-migrations/{migration_id}')
    def migration(migration_id:str,request:Request):
        p=who(request,{})
        with opened() as service:
            value=service.repo.migration(migration_id)
            require(value is not None and value['team_id']==p['team_id'],'BASIS_NOT_FOUND','이행 기록을 찾을 수 없습니다.',404)
            # Authorize every affected relation before exposing its metadata.
            for row in value['items']:service.history(p,row['link_id'])
            return value
    return factory


def oracle_factory(connection_factory,source_factory,table_map):
    """Site-approved connection/identity wiring is injected at create_app()."""
    @contextmanager
    def opened():
        from .oracle import OracleRepository
        repo=OracleRepository(connection_factory(),table_map)
        try:
            with source_factory() as sources:yield Service(repo,sources)
        finally:repo.close()
    return opened
