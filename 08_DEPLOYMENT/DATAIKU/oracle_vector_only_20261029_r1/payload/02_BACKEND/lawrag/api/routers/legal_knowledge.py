"""One authenticated management router, independent of the disabled chat AD mode."""
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlsplit
import base64
import binascii
from fastapi import APIRouter, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from lawrag.legal_knowledge.contracts import principal, require, KnowledgeError, validate, REF

CURRENT = ContextVar('legal_knowledge_request', default=None)


def install(app, pipeline, *, factory=None, identity=None):
    pipeline.knowledge_factory = factory
    config = pipeline.contracts.pipeline.get('legal_knowledge', {})
    def who(request, *, management=True):
        if management:
            require(config.get('management_enabled') is True, 'KNOWLEDGE_DISABLED', '지식 관리 기능이 비활성화되어 있습니다.', 403)
        value = identity(request) if identity else getattr(request.state, 'knowledge_principal', None)
        return principal(value)

    def service():
        require(factory is not None, 'KNOWLEDGE_BACKEND', '승인된 지식 저장소 연결이 필요합니다.', 503)
        return factory()

    @app.exception_handler(KnowledgeError)
    async def failure(request, exc):
        return JSONResponse(status_code=exc.status, content={'schema_version': 'legal-knowledge-error-v1',
            'status': 'FAILED', 'code': exc.code, 'message': str(exc), 'fields': exc.fields,
            'retry': 'CHECK_SAME_OPERATION_ID' if exc.status in (409, 503) else 'CORRECT_INPUT'})

    @app.middleware('http')
    async def request_context(request, call_next):
        token = CURRENT.set(None)
        try:
            if config.get('consumer_mode', 'off') != 'off' and request.url.path.startswith('/v1/'):
                try: identity_value = who(request, management=False)
                except KnowledgeError: identity_value = None
                CURRENT.set((factory, identity_value, config))
            return await call_next(request)
        finally: CURRENT.reset(token)

    router = APIRouter(prefix='/v1/legal-knowledge')

    @router.get('/status')
    def status(request: Request):
        p = who(request)
        with service() as s:
            active = s.active(p)
            return {'management_enabled': True, 'consumer_mode': config.get('consumer_mode', 'off'),
                    'roles': p['knowledge_roles'], 'team_id': p['team_id'],
                    'source_binding': {'generation': pipeline.store.manifest['generation_id'],
                        'store_sha256': pipeline.store.manifest['store_sha256'],
                        'unit_index_sha256': pipeline.term_agent.unit_fulltext.manifest['index_sha256']
                        if getattr(pipeline.term_agent, 'unit_fulltext', None) else None},
                    'channel_revision': active['revision'] if active else 0,
                    'publication_status': active['status'] if active else 'UNPUBLISHED'}

    @router.get('/documents')
    def documents(request: Request, q: str='', offset: int=Query(0, ge=0)):
        p = who(request)
        from semantic_runtime.document_browser import documents as browse
        return browse(pipeline.store, title_query=q, offset=offset, limit=50, document_ids=set(p['document_ids']))

    @router.post('/source-reference')
    def source_reference(body: dict, request: Request):
        from hashlib import sha256
        from lawrag.legal_knowledge.contracts import obj, ID, TEXT
        p = who(request); validate(body, obj(document_id=ID, locator=TEXT))
        require(body['document_id'] in p['document_ids'], 'KNOWLEDGE_NOT_FOUND', '원문에 접근할 수 없습니다.', 404)
        pipeline.store.check_unchanged()
        source = pipeline.store.source(body['document_id'], body['locator'])
        return {'ref': {**body, 'version': body['document_id'], 'content_hash': sha256(source['text'].encode()).hexdigest()},
                'preview': source['text'][:1500], 'preview_truncated': len(source['text']) > 1500}

    @router.get('/objects')
    def objects(request: Request, namespace: str='definition', cursor: str='', limit: int=Query(24, ge=1, le=50)):
        p = who(request)
        try: after = base64.b64decode(cursor, altchars=b'-_', validate=True).decode() if cursor else ''
        except (ValueError, UnicodeError, binascii.Error):
            raise KnowledgeError('KNOWLEDGE_CURSOR', '목록 위치를 확인해 주세요.')
        require(len(after) <= 128, 'KNOWLEDGE_CURSOR', '목록 위치가 너무 깁니다.')
        with service() as s: return s.listing(p, namespace=namespace, after=after, limit=limit)

    @router.get('/objects/{object_id:path}')
    def detail(object_id: str, request: Request, revision: int | None=Query(None, ge=1)):
        p = who(request)
        from lawrag.legal_knowledge.application import ref
        with service() as s: return s.definition(ref(s.record('definition', object_id, p, revision)), p)

    @router.get('/operations/{operation_id:path}')
    def operation(operation_id: str, request: Request):
        p = who(request)
        with service() as s:
            value = s.operation(operation_id, p)
            if 'result' in value: s._authorize_result(value['result'], p)
            return value

    def same_origin(request):
        require(request.headers.get('x-knowledge-request') == '1', 'KNOWLEDGE_ORIGIN', '관리 화면에서 요청해 주세요.', 403)
        origin = request.headers.get('origin')
        if origin:
            actual = urlsplit(origin); expected = urlsplit(str(request.base_url))
            require((actual.scheme, actual.netloc) == (expected.scheme, expected.netloc),
                    'KNOWLEDGE_ORIGIN', '다른 사이트에서 보낸 변경 요청입니다.', 403)

    @router.post('/commands')
    def command(body: dict, request: Request):
        p = who(request); same_origin(request)
        with service() as s: return s.command(p, body)

    @router.post('/impact')
    def impact(body: dict, request: Request):
        p = who(request); validate(body, REF)
        with service() as s: return s.impact(p, body)

    @router.post('/preview')
    def preview(body: dict, request: Request):
        p = who(request)
        from lawrag.legal_knowledge.application import BINDING
        from lawrag.legal_knowledge.contracts import obj, TEXT
        validate(body, obj(query=TEXT, source_binding=BINDING))
        with service() as s: return s.plan(p, body['query'], body['source_binding'])

    app.include_router(router)
    viewer = Path(__file__).resolve().parents[1]/'viewer'/'legal_knowledge'

    @app.get('/legal-knowledge/')
    @app.get('/legal-knowledge/{asset}')
    def page(request: Request, asset: str='index.html'):
        who(request)
        require(asset in ('index.html', 'app.js', 'styles.css'), 'KNOWLEDGE_NOT_FOUND', '파일을 찾을 수 없습니다.', 404)
        return FileResponse(viewer/asset, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"})
