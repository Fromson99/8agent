from contextlib import asynccontextmanager
import json
from pathlib import Path
import re
import time
import uuid
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from .contracts import Contracts,write
from .feedback import record_feedback
from .pipeline import Pipeline
from .provider import Haiku
from .storage import Store
from . import observability as obs


log = obs.get_logger("app")


def create_app(root,generation,*,contracts_root=None,release=None,provider=None,vector=None):
    root=Path(root);store=Store(generation);contracts_root=Path(contracts_root or root)
    contracts=Contracts(contracts_root)
    runtime=root/'90_RUNTIME/semantic';runs=runtime/'runs';feedback=runtime/'feedback'
    if provider is None:
        import os
        provider=Haiku(root,runtime/'provider',store.manifest['export_allowed'],
                       backend=os.environ.get('SEMANTIC_LLM_BACKEND','anthropic'),
                       endpoint=os.environ.get('SEMANTIC_LLM_ENDPOINT'),
                       trust_zone=os.environ.get('SEMANTIC_LLM_TRUST_ZONE','external'))
    pipeline=Pipeline(contracts_root,store,provider,vector)
    @asynccontextmanager
    async def lifespan(app):
        yield
        store.close()
    app=FastAPI(title='용어 기반 법률 검색',version='3.0.0',lifespan=lifespan)
    app.state.pipeline=pipeline

    @app.exception_handler(ValueError)
    async def bad_value(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422,content={'detail':str(exc)})

    @app.exception_handler(KeyError)
    async def missing(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404,content={'detail':'요청한 데이터 좌표가 없습니다.'})

    @app.get('/health')
    @app.get('/v1/pipeline/status')
    def health():
        return {'status':'ok','runtime':'term-runtime-v1','release':release,
                'generation_id':store.manifest['generation_id'],'data_status':store.manifest['data_status'],
                'counts':store.manifest['counts'],'legacy_fallback':False,
                'quality_certified':False,'vector':'NOT_USED',
                'llm_model':getattr(provider,'model',None),'rag_mode':'term-agent','term_agent_quality_certified':False,'external_export_allowed':store.manifest['export_allowed']}

    @app.get('/v1/rag/search')
    def search(q:str,doc_id:str|None=None,limit:int=Query(40,ge=1,le=100)):
        return pipeline.retrieve(pipeline.plan(q,[doc_id] if doc_id else None),limit)

    @app.get('/v1/rag/section')
    def section(doc_id:str,node:str):return store.section(doc_id,node)

    @app.get('/v1/rag/scopes')
    def scopes():return {'documents':[dict(r) for r in store.db.execute('SELECT document_id,name FROM document ORDER BY name')]}

    @app.get('/v1/rag/nodes')
    def nodes(doc_id:str):
        return {'nodes':[{'id':r['unit_id'],'parent':r['parent_id'],'title':json.loads(r['json']).get('title','')}
                         for r in store.db.execute('SELECT * FROM source_unit WHERE document_id=?',(doc_id,))]}

    @app.get('/v1/rag/links/summary')
    def link_summary():
        return {'counts':pipeline.term_agent.get_index().manifest['counts']}

    @app.get('/v1/rag/links')
    def links(source_id:str):
        from .term_index import ro
        db=ro(pipeline.term_agent.get_index().path/'navigation.sqlite')
        try:return {'references':[json.loads(r[0]) for r in db.execute(
            'SELECT r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id WHERE e.source_id=?',(source_id,))]}
        finally:db.close()

    @app.post('/v1/rag/ask')
    def ask(body:dict):
        started=time.perf_counter()
        ident=uuid.uuid4().hex
        question=body.get('question',body.get('q'))
        docs=body.get('document_ids')
        if docs is not None and (not isinstance(docs,list) or any(not isinstance(x,str) for x in docs)):raise ValueError('document_ids must be a string array')
        use_llm=body.get('use_llm',True)
        if type(use_llm) is not bool:raise ValueError('use_llm must be boolean')
        if set(body)-{'question','q','document_ids','use_llm'}:raise ValueError('unsupported request fields')
        with obs.context(run_id=ident):
            obs.event(log,'ask.started',question_chars=len(question or '') if isinstance(question,str) else 0,document_filter_count=len(docs or []),use_llm=use_llm)
            try:
                run=pipeline.run(question,docs,use_llm)
                run['run_id']=ident;run['release']=release
                write(runs/(ident+'.json'),run)
            except Exception as exc:
                obs.event(log,'ask.failed',level=40,exc_info=True,error_type=type(exc).__name__,duration_ms=int((time.perf_counter()-started)*1000))
                raise
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
        return '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>법률 검색</title>
<style>body{max-width:960px;margin:48px auto;font:16px system-ui;padding:16px}textarea{width:100%;height:100px}button{padding:10px 20px;margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f7;padding:20px}small{color:#555}</style>
<h1>법률 검색</h1><small id="status">데이터 확인 중</small><p><textarea id="q" placeholder="질문을 입력하세요"></textarea></p>
<label><input id="llm" type="checkbox"> LLM 답변 사용</label><br><button id="ask">검색하기</button><pre id="result"></pre>
<script>const $=id=>document.getElementById(id);fetch('/health').then(r=>r.json()).then(x=>$('status').textContent=`데이터: ${x.generation_id} · ${x.data_status}`);
$('ask').onclick=async()=>{$('result').textContent='검색 중…';try{const r=await fetch('/v1/rag/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:$('q').value,use_llm:$('llm').checked})});const x=await r.json();$('result').textContent=x.answer?x.answer.text+'\\n\\n확인 필요: '+x.answer.unresolved.map(z=>z.reason).join(' / '):JSON.stringify(x,null,2);}catch(e){$('result').textContent=String(e);}};</script></html>'''

    @app.api_route('/{path:path}',methods=['GET','POST','PUT','DELETE'])
    def retired(path:str):raise HTTPException(410,'기존 MAIN 기능은 제거되었습니다. /docs의 최신 API를 사용하세요.')
    return app
