"""Explicit local E2E host. No production registry or Oracle fallback.

check: model-free preflight; run: three frozen API requests, once each;
serve: authenticated management and saved E2E result viewer on loopback.
"""
from pathlib import Path
from contextlib import contextmanager
import argparse
import gzip
import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import traceback

sys.dont_write_bytecode = True
R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0958-legal-knowledge-e2e'
D = A / 'artifacts/design'
P = R / '02_BACKEND/lawrag/research/candidates/adr_0958/integrated'


def read(path): return json.loads(Path(path).read_text())
def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while b := f.read(1024 * 1024): h.update(b)
    return h.hexdigest()
def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


class LabDB:
    """Local validation records only; never selected by a production factory."""
    def __init__(self, path):
        self.raw = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=5)
        self.raw.row_factory = sqlite3.Row
    def execute(self, statement, args=()):
        return self.raw.execute(re.sub(r'FETCH FIRST (\d+) ROWS ONLY', r'LIMIT \1', statement), args)
    @contextmanager
    def transaction(self):
        self.raw.execute('BEGIN IMMEDIATE')
        try: yield; self.raw.commit()
        except BaseException: self.raw.rollback(); raise


def code_root(preflight=False):
    if preflight: return P / 'snapshot'
    freeze = read(D / 'freeze.json')
    for name, expected in freeze['files'].items():
        if sha(R / name) != expected: raise RuntimeError('Frozen file drift: ' + name)
    manifest = read(P / 'candidate.json')
    revision = manifest['revisions'][-1]
    if revision['revision_sha256'] != freeze['candidate_revision_sha256']:
        raise RuntimeError('Candidate revision changed')
    root = P / 'revisions' / revision['revision_id'] / 'snapshot'
    for file in revision['files']:
        if sha(R / file['frozen_path']) != file['snapshot_sha256']:
            raise RuntimeError('Frozen candidate file drift')
    return root


def make_app(directory, *, preflight=False, token=None):
    C = code_root(preflight)
    os.environ.update(GENOS_RESIDENT_DATA='off', GENOS_AUTO_WARMUP='0', AD_WORKER_ENABLED='0',
                      GENOS_SYSTEM_LOG_ENABLED='0', LAWRAG_WORKSPACE_ROOT=str(R))
    sys.path[:0] = [str(C / '02_BACKEND'), str(R)]
    from lawrag.platform.workspace import load_layout
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport
    from lawrag.legal_knowledge.adapters.repository import Repository
    from lawrag.legal_knowledge.adapters.existing import ExistingReferences
    from lawrag.legal_knowledge.adapters.oracle import ddl
    from lawrag.legal_knowledge.application import Service
    from lawrag.legal_knowledge.contracts import digest
    layout = load_layout(R)
    release = read(D / 'selected-release.json')
    generation = R / release['data_path']
    assert generation.is_relative_to(layout.path('data'))
    assert sha(generation / 'manifest.json') == release['data_manifest_sha256']
    directory.mkdir(parents=True, exist_ok=True)
    db_path = directory / 'knowledge-lab.sqlite'
    if not db_path.exists():
        db = LabDB(db_path)
        db.raw.executescript(ddl({n:n for n in ('lk_record', 'lk_head', 'lk_lookup')}))
        db.raw.close()
    transport = LocalQwen38Transport(C, R)
    profile = read(C / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
    profile.update(model_binding=transport.binding, max_concurrent_requests_per_process=1)
    app_holder = {}
    @contextmanager
    def factory():
        db = LabDB(db_path)
        try: yield Service(Repository(db), ExistingReferences(app_holder['app'].state.pipeline.store))
        finally: db.raw.close()
    who = {'authenticated': True, 'tenant_id': 'local-e2e', 'team_id': 'risk_team',
           'user_id': 'local-researcher', 'document_ids': list(transport.public_scope),
           'knowledge_roles': ['read', 'edit', 'publish']}
    def identity(request): return dict(who)
    app = create_app(directory, generation, contracts_root=C, workspace_root=R,
        runtime_root=directory / 'runtime', provider=object(), vector=False,
        implementation='legal-agent-unified-v6', legal_agent_profile=profile,
        legal_agent_transport=transport, memory_identity=identity,
        knowledge_factory=factory, knowledge_identity=identity,
        release={'mode': 'local-e2e-candidate', 'release_id': 'ADR0958-integrated',
                 'selected_main_unchanged': 96, 'knowledge_storage': 'LOCAL_TEST_SQLITE'})
    app_holder['app'] = app
    from semantic_runtime.team_scope import select_documents
    who['document_ids'] = sorted(set(who['document_ids']) & set(select_documents(app.state.pipeline.store, who['team_id'])))
    from semantic_runtime.stage_runner import StageRunner
    StageRunner(app.state.pipeline).verify_profile()
    index = app.state.pipeline.term_agent.unit_fulltext
    binding = {'generation': app.state.pipeline.store.manifest['generation_id'],
               'store_sha256': app.state.pipeline.store.manifest['store_sha256'],
               'unit_index_sha256': index.manifest['index_sha256'] if index else None}
    seeds = read(D / 'seeds.json')
    transport.knowledge_export_grant = {'schema_version': 'knowledge-export-grant-v1',
        'source_binding': binding, 'principal': {k:who[k] for k in ('tenant_id','team_id','user_id')},
        'question_hashes': [digest(c['question']) for c in read(D / 'cases.json')],
        'definition_hashes': [digest(d) for d in seeds]}
    app.state.e2e = {'directory': directory, 'source_binding': binding, 'who': who, 'transport': transport}
    # One secret protects the entire local host, including original RAG routes.
    # The test client authenticates with the same bearer path as a real caller.
    token = token or secrets.token_urlsafe(32)
    app.state.e2e_token = token
    from fastapi import Request
    from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
    @app.middleware('http')
    async def authenticate(request, call_next):
        if request.url.path == '/e2e/login': return await call_next(request)
        supplied = request.headers.get('authorization', '').removeprefix('Bearer ')
        if not supplied: supplied = request.cookies.get('lk_e2e', '')
        if not secrets.compare_digest(supplied, token):
            return JSONResponse({'status':'AUTH_REQUIRED','message':'로컬 E2E 실행 토큰이 필요합니다.'}, status_code=401)
        return await call_next(request)
    @app.get('/e2e/login', response_class=HTMLResponse)
    def login():
        return '<meta charset="utf-8"><title>로컬 E2E 로그인</title><h1>검토 지식 E2E</h1><p>실행 터미널에 표시된 로컬 토큰을 입력하세요.</p><form method="post"><input type="password" name="token" autocomplete="off" required><button>열기</button></form>'
    @app.post('/e2e/login')
    async def authenticate_browser(request: Request):
        from urllib.parse import parse_qs
        value = parse_qs((await request.body()).decode()).get('token', [''])[0]
        if not secrets.compare_digest(value, token): return JSONResponse({'status':'AUTH_REQUIRED'}, status_code=401)
        response = RedirectResponse('/e2e/', status_code=303)
        response.set_cookie('lk_e2e', token, httponly=True, samesite='strict', max_age=3600)
        response.headers['Cache-Control'] = 'no-store'
        return response
    @app.get('/e2e/', response_class=HTMLResponse)
    def viewer(): return (Path(__file__).with_name('viewer.html')).read_text()
    @app.get('/e2e/results')
    def results():
        out = []
        for c in read(D / 'cases.json'):
            p = directory / c['case_id'] / 'result.json'
            value = read(p) if p.exists() else {'status':'NOT_RUN'}
            out.append({**c, **value})
        return {'environment':'WSL local E2E / Oracle 미검증 / MAIN96 유지', 'cases':out}
    @app.get('/e2e/receipt/{case_id}')
    def receipt(case_id: str):
        if case_id not in {c['case_id'] for c in read(D/'cases.json')}:
            return JSONResponse({'status':'NOT_FOUND'},status_code=404)
        p = directory / case_id / 'response.json'
        return read(p) if p.exists() else {'status':'NOT_RUN'}
    return app


def api(client, method, path, **kwargs):
    response = getattr(client, method)(path, **kwargs)
    if response.status_code != 200:
        raise RuntimeError(f'{method} {path}: {response.status_code}: {response.text[:2000]}')
    return response.json()


def seed(client, directory):
    from lawrag.legal_knowledge.application import ref
    status = api(client, 'get', '/v1/legal-knowledge/status')
    def command(op, args, key):
        return api(client, 'post', '/v1/legal-knowledge/commands',
            headers={'X-Knowledge-Request':'1'}, json={'schema_version':'legal-knowledge-v1',
                'operation':op,'operation_id':'e2e:'+key,'arguments':args})
    drafts = []
    for i, definition in enumerate(read(D / 'seeds.json')):
        for source in definition['source_refs']:
            got = api(client, 'post', '/v1/legal-knowledge/source-reference',
                      json={k:source[k] for k in ('document_id','locator')})
            assert got['ref'] == source
        drafts.append(command('save_draft', {'object_id':None,'expected_revision':0,'definition':definition},'draft:'+str(i)))
    build = command('prepare_publication', {'refs':[ref(d) for d in drafts],
        'source_binding':status['source_binding'],'review_note':'공개 원문에 연결한 합성 검토 절차. 법률 결론·정답 아님.'}, 'prepare')
    published = command('publish', {'build_id':build['id'],'build_hash':build['content_hash'],'expected_revision':0}, 'publish')
    previews = []
    for case in read(D/'cases.json'):
        preview = api(client,'post','/v1/legal-knowledge/preview',json={'query':case['question'],'source_binding':status['source_binding']})
        assert preview['items'], 'No matching published knowledge'
        previews.append({'case_id':case['case_id'],'plan':preview})
    value = {'drafts':drafts,'build':build,'published':published,'previews':previews}
    path = directory/'management.json'
    if path.exists(): assert read(path) == value
    else: put(path,value)
    return value


def run_case(client, app, case):
    from lawrag.research.experiment_client import ExperimentClient
    from semantic_runtime.legal_agent.local_gemma import provider_request
    from semantic_runtime.legal_agent.errors import TransportError, ContractError
    from lawrag.research.experiment_client import ExperimentProviderError, ExperimentTransportError
    O = app.state.e2e['directory']/case['case_id']
    if (O/'result.json').exists(): return read(O/'result.json')
    # Exclusive claim survives a crash; do not reset a consumed call/time budget.
    O.mkdir(exist_ok=False)
    put(O/'started.json',{'started_at':time.time(),'case_id':case['case_id'],'automatic_resume':False})
    transport=app.state.e2e['transport']
    calls=ExperimentClient(R,O/'provider',max_calls=40,max_output_tokens=6400,max_repairs=0)
    started=time.monotonic(); observed=[]
    def send_once(*,body,ticket):
        elapsed=time.monotonic()-started
        if elapsed >= 1800: raise ContractError('E2E deadline exhausted')
        import resource
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > 4096*1024:
            raise ContractError('E2E memory budget exceeded')
        from semantic_runtime.resident_data import available_memory
        if available_memory() < 2048*1024*1024: raise ContractError('E2E system memory reserve reached')
        observed.append('legal_review_guidance' in json.dumps(body,ensure_ascii=False))
        with gzip.open(O/f'canonical-{calls.calls+1:03d}.json.gz','wt',encoding='utf8') as f:
            json.dump(body,f,ensure_ascii=False)
        print(json.dumps({'case':case['case_id'],'model_call':calls.calls+1,'stage':'start'}),flush=True)
        try:
            result=calls.chat_completions(provider_request(body),phase='product-'+str(calls.calls+1),
                timeout_seconds=min(float(ticket['remaining_seconds']),1800-elapsed))
        except (ExperimentProviderError,ExperimentTransportError) as exc:
            raise TransportError('E2E external request failed; inspect provider receipt',retryable=False,unknown=True) from exc
        raw=result['body_json']
        if raw.get('provider')!='Parasail' or raw.get('model')!=transport.binding['model']:
            raise ContractError('E2E provider/model drift')
        return result
    transport.send_once=send_once
    body={'question':case['question'],'public_question':True,'use_llm':True,
          'document_ids':app.state.e2e['who']['document_ids'],'team_id':'risk_team',
          'session_id':'e2e-'+case['case_id'],'request_id':'ADR0958:'+case['case_id']}
    put(O/'request.json',body)
    row={'case_id':case['case_id'],'status':'FAILED','model_calls':0}
    try:
        response=client.post('/v1/rag/ask',json=body)
        value=response.json();put(O/'response.json',{'http_status':response.status_code,'body':value})
        row['http_status']=response.status_code
        if response.status_code != 200: raise RuntimeError('RAG API did not publish an answer')
        answer=value.get('answer',{});usage=value.get('assembly',{}).get('term_agent',{}).get('legal_knowledge',{})
        items=[i for b in usage.get('bindings',[]) for i in b['items']]
        assert answer.get('text') and any(c.get('source_ids') for c in answer.get('claims',[])), 'Missing cited answer'
        assert items and any(observed), 'Published knowledge was not consumed'
        count=calls.calls
        duplicate=client.post('/v1/rag/ask',json=body)
        assert duplicate.status_code==200 and duplicate.json()['answer']==answer and calls.calls==count
        row.update(status='PASS',answer=answer,knowledge=usage,duplicate_additional_calls=0,
                   guidance_in_model_input=True)
    except Exception as exc:
        row.update(error_type=type(exc).__name__,error=str(exc))
        (O/'failure.txt').write_text(traceback.format_exc())
    finally:
        row.update(seconds=time.monotonic()-started,model_calls=calls.calls,usage=calls.usage)
        put(O/'result.json',row)
    print(json.dumps({k:v for k,v in row.items() if k not in ('answer','knowledge','usage')},ensure_ascii=False),flush=True)
    return row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['check','run','serve'])
    parser.add_argument('--port',type=int,default=8768)
    args=parser.parse_args()
    directory=A/'artifacts'/('preflight' if args.action=='check' else 'run-001')
    app=make_app(directory,preflight=args.action=='check')
    if args.action=='serve':
        # Browser authentication uses a cookie pasted in the dedicated launcher;
        # no query-string token and no token is written to artifacts.
        print('Open http://127.0.0.1:'+str(args.port)+'/e2e/login',flush=True)
        print('Local browser login token: '+app.state.e2e_token,flush=True)
        import uvicorn
        uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False,workers=1)
        return 0
    from fastapi.testclient import TestClient
    before=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
    with TestClient(app,headers={'Authorization':'Bearer '+app.state.e2e_token}) as client:
        assert client.get('/health',headers={'Authorization':''}).status_code==401
        assert client.get('/legal-knowledge/').status_code==200
        seed(client,directory)
        health=api(client,'get','/health');put(directory/'health.json',health)
        if args.action=='check':
            put(directory/'result.json',{'status':'PASS','model_calls':0,'management_api':True,
                'real_source_binding':app.state.e2e['source_binding'],'public_scope_documents':len(app.state.e2e['who']['document_ids'])})
            print('PREFLIGHT PASS: management, real source hashes, publication, 3 previews; model_calls=0')
            return 0
        rows=[run_case(client,app,c) for c in read(D/'cases.json')]
        assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==before
        summary={'status':'PASS' if all(r['status']=='PASS' for r in rows) else 'PARTIAL_OR_FAILED',
            'cases':[{k:v for k,v in row.items() if k not in ('usage','answer','knowledge')} for row in rows],
            'active_pointer_unchanged':True,'main_promoted':False,'oracle_verified':False,'genos_verified':False}
        put(directory/'summary.json',summary)
        return 0 if summary['status']=='PASS' else 1


if __name__=='__main__': raise SystemExit(main())
