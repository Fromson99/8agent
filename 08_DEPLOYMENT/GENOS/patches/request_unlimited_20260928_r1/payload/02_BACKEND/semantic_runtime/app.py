from contextlib import asynccontextmanager
import json
import os as _os
from pathlib import Path
import re
import sqlite3
import time
import uuid
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from jsonschema import ValidationError
from .contracts import Contracts,write
from .feedback import record_feedback
from .pipeline import Pipeline
from .provider import Haiku
from .storage import Store
from . import observability as obs


log = obs.get_logger("app")


def create_app(root,generation,*,contracts_root=None,release=None,provider=None,vector=None,implementation=None,
               legal_agent_profile=None,legal_agent_transport=None,workspace_root=None,runtime_root=None):
    root=Path(root);contracts_root=Path(contracts_root or root)
    with obs.step(log, 'bootstrap.source_store'):
        store=Store(generation)
    with obs.step(log, 'bootstrap.contracts'):
        contracts=Contracts(contracts_root)
    selected_implementation=implementation or contracts.pipeline['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent'].get('implementation')
    if selected_implementation in ('legal-agent-v1', 'legal-agent-tools-v2', 'legal-agent-tools-v3', 'legal-agent-tools-v4', 'legal-agent-tools-v5'):
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
    is_legal_agent=pipeline.profile_id in ('legal-agent-rag-v1', 'legal-agent-rag-v2', 'legal-agent-rag-v3', 'legal-agent-rag-v4', 'legal-agent-rag-v5')
    pipeline.task_harness_journal = runtime/'task-harness'/'execution.sqlite'
    pipeline.relation_issues = runtime/'relation-issues'/'rejections.sqlite'
    @asynccontextmanager
    async def lifespan(app):
        if is_legal_agent:
            from .legal_agent.publication import recover
            from .legal_agent.source_bundle import validate_current
            recover(runtime/'legal-agent/runs',runs,
                    publication_guard=lambda repo, value: validate_current(repo,value,store),
                    contracts=contracts, release=release)
        try:
            yield
        finally:
            store.close()
    from .document_aliases import status as alias_status
    aliases=alias_status(pipeline.contracts.root,pipeline.term_agent.config,store)
    app=FastAPI(title='용어 기반 법률 검색',version='3.0.0',lifespan=lifespan)
    app.state.pipeline=pipeline

    from .legal_agent.errors import LegalAgentError
    @app.exception_handler(LegalAgentError)
    async def legal_agent_failure(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.http_status,content={
            'code':exc.code,'run_id':getattr(exc,'run_id',None),
            'detail':obs._redact_secrets(str(exc))[:1000]})

    @app.exception_handler(ValueError)
    async def bad_value(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422,content={'detail':str(exc)})

    @app.exception_handler(KeyError)
    async def missing(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404,content={'detail':'요청한 데이터 좌표가 없습니다.'})

    @app.exception_handler(ValidationError)
    async def bad_contract(request,exc):
        # A request that fails the runtime contract is the caller's error, not a server fault.
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422,content={'detail':'request violates term-runtime-v1 contract: '+exc.message})

    @app.get('/health')
    @app.get('/v1/pipeline/status')
    def health():
        model=(pipeline.term_agent.profile.get('model_binding') or {}).get('model') if is_legal_agent else getattr(provider,'model',None)
        return {'status':'ok','runtime':'term-runtime-v1','release':release,
                'generation_id':store.manifest['generation_id'],'data_status':store.manifest['data_status'],
                'counts':store.manifest['counts'],'legacy_fallback':False,
                'quality_certified':False,'vector':'NOT_USED',
                'llm_model':model,'rag_mode':pipeline.term_agent.config.get('implementation','term-agent-v1'),'term_agent_quality_certified':False,'external_export_allowed':store.manifest['export_allowed'],'document_aliases':aliases}

    @app.get('/v1/rag/search')
    def search(q:str,doc_id:str|None=None,scope:str|None=None,limit:int=Query(40,ge=1,le=100),team_id:str|None=None):
        return pipeline.retrieve(pipeline.plan(q,[doc_id] if doc_id else None,scope,team_id=team_id),limit)

    def team_documents(team_id):
        from .team_scope import select_documents
        return set(select_documents(store,team_id)) if team_id is not None else None

    def check_team_document(doc_id,team_id):
        allowed=team_documents(team_id)
        if allowed is not None and doc_id not in allowed:
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

    @app.get('/v1/rag/source-candidates')
    def source_candidates(run_id:str,offset:int=Query(0,ge=0)):
        from html import escape
        from .legal_agent.tiers_repository import TiersRepository
        from .legal_agent.source_bundle import validate_current
        if not re.fullmatch(r'[A-Za-z0-9_-]+',run_id):raise HTTPException(404,'실행을 확인할 수 없습니다.')
        paths=list((runtime/'legal-agent/runs').glob('*/'+run_id+'/journal.sqlite'))
        if len(paths)!=1:raise HTTPException(404,'실행을 확인할 수 없습니다.')
        repo=TiersRepository(paths[0])
        try:
            row=repo.db.execute("SELECT result_json FROM publication WHERE status='PUBLISHED'").fetchone()
            if not row:
                status=repo.run()['status']
                raise HTTPException(503 if status in ('RUNNING','COMMIT_READY') else 404,
                                    '출처 발행 중입니다.' if status in ('RUNNING','COMMIT_READY') else '발행 결과가 없습니다.')
            value=json.loads(row[0]);validate_current(repo,value,store)
            from .legal_agent.source_candidates import inventory
            current=json.loads((store.path/'manifest.json').read_text())
            allowed=set(current['scope']['document_version_ids'])&set(repo.binding['scope']['document_version_ids'])
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
        repo=TiersRepository(journals[0])
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
        from .term_index import ro
        allowed=team_documents(team_id)
        db=ro(pipeline.term_agent.get_index().path/'navigation.sqlite')
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
    def ask(body:dict):
        started=time.perf_counter()
        ident=uuid.uuid4().hex
        question=body.get('question',body.get('q'))
        if not isinstance(question,str) or not question.strip():raise ValueError('question must be a nonempty string')
        docs=body.get('document_ids')
        if docs is not None and (not isinstance(docs,list) or any(not isinstance(x,str) for x in docs)):raise ValueError('document_ids must be a string array')
        use_llm=body.get('use_llm',True)
        if type(use_llm) is not bool:raise ValueError('use_llm must be boolean')
        scope=body.get('scope')
        if scope is not None and not isinstance(scope,str):raise ValueError('scope must be a string')
        if set(body)-{'question','q','document_ids','use_llm','scope','team_id','public_question'}:raise ValueError('unsupported request fields')
        external = getattr(pipeline.term_agent.transport, 'public_scope', None) if is_legal_agent else None
        if external is not None and use_llm:
            if body.get('public_question') is not True:
                raise ValueError('local Gemma requires public_question=true')
            if scope is not None:
                raise ValueError('local Gemma requires explicit public document scope')
            docs = docs if docs is not None else list(external)
            if not docs or set(docs)-set(external):
                raise ValueError('local Gemma document scope includes an unapproved source')
        elif 'public_question' in body:
            raise ValueError('public_question is only used for local Gemma model requests')
        team_options={}
        if 'team_id' in body:
            # Explicit null/empty selectors must not silently become an all-team request.
            from .team_scope import validate_team_id
            with obs.context(run_id=ident), obs.step(log,'ask.team_validate'):
                validate_team_id(body['team_id'])
            team_options['team_id']=body['team_id']
        with obs.context(run_id=ident):
            obs.event(log,'ask.started',question_chars=len(question or '') if isinstance(question,str) else 0,document_filter_count=len(docs or []),use_llm=use_llm)
            try:
                if is_legal_agent:
                    genos_selected = bool(_os.environ.get('GENOS_GENERATION', '').strip() or
                                          _os.environ.get('GENOS_DATA_ROOT', '').strip())
                    deferred = genos_selected and _os.environ.get(
                        'GENOS_DEFER_PUBLICATION', '1').strip().lower() not in {'0', 'false', 'off'}
                    run=pipeline.run(question,docs,use_llm,scope,execution_context={
                        'run_id':ident,'release':release,'runtime':runtime,'publish':True,
                        'defer_publication':deferred,
                        'external_public_question':external is not None and use_llm},**team_options)
                else:
                    run=pipeline.run(question,docs,use_llm,scope,**team_options)
                    run['run_id']=ident;run['release']=release
                    write(runs/(ident+'.json'),run)
            except Exception as exc:
                if isinstance(exc,LegalAgentError):exc.run_id=ident
                obs.event(log,'ask.failed',level=40,exc_info=True,error_type=type(exc).__name__,duration_ms=int((time.perf_counter()-started)*1000))
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
            return run

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
                         '공개 질문이며 외부 Gemma 전송에 동의합니다</label><br>'
                         if is_legal_agent and getattr(pipeline.term_agent.transport, 'public_scope', None) is not None
                         else '')
        html = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>법률 검색</title>
<style>body{max-width:960px;margin:48px auto;font:16px system-ui;padding:16px}textarea{width:100%;height:100px}button{padding:10px 20px;margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f7;padding:20px}small{color:#555}</style>
<h1>법률 검색</h1><small id="status">데이터 확인 중</small><p><textarea id="q" placeholder="질문을 입력하세요"></textarea></p>
<label><input id="llm" type="checkbox"> LLM 답변 사용</label><br>PUBLIC_TOGGLE<button id="ask">검색하기</button><pre id="result"></pre><section id="sources"></section><details id="audit" hidden><summary>탐색·근거 판단</summary><pre id="audit-text"></pre></details>
<script src="/rag/source-tiers.js"></script><script>const $=id=>document.getElementById(id);fetch('/health').then(r=>r.json()).then(x=>$('status').textContent=`데이터: ${x.generation_id} · ${x.data_status}`);
$('ask').onclick=async()=>{$('result').textContent='검색 중…';$('audit').hidden=true;$('sources').replaceChildren();try{const body={question:$('q').value,use_llm:$('llm').checked};if(body.use_llm&&$('public-question')?.checked)body.public_question=true;const r=await fetch('/v1/rag/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const x=await r.json();renderSourceTiers(x.assembly?.term_agent?.source_bundle);const a=x.assembly?.term_agent?.exploration_v3;$('audit').hidden=!a;$('audit-text').textContent=a?(a.display_lines||[]).join('\\n'):'';$('result').textContent=x.answer?x.answer.text+'\\n\\n확인 필요: '+x.answer.unresolved.map(z=>z.reason).join(' / '):JSON.stringify(x,null,2);}catch(e){$('result').textContent=String(e);}};</script></html>'''
        return html.replace('PUBLIC_TOGGLE', public_toggle)

    @app.api_route('/{path:path}',methods=['GET','POST','PUT','DELETE'])
    def retired(path:str):raise HTTPException(410,'기존 MAIN 기능은 제거되었습니다. /docs의 최신 API를 사용하세요.')
    return app
