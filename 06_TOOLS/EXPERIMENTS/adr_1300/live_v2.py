"""One native API call on four public documents, with immutable transport logging."""
from common import *
import os, time, importlib, traceback, resource
from copy import deepcopy
from contextlib import contextmanager
from types import SimpleNamespace

preflight = '--preflight' in sys.argv
f = read(DES/'freeze-v2.json'); C = ROOT/f['code_root']
for n,h in f['files'].items(): assert sha(C/n)==h, n
for n,h in f['inputs'].items(): assert sha(ROOT/n)==h, n
for n,h in f['scripts'].items(): assert sha(ROOT/n)==h, n
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
base = ART/('preflight-v2' if preflight else 'live')
base.mkdir(parents=True, exist_ok=False)
runtime = base/'runtime'
for n in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_IMPLEMENTATION','LEGAL_AGENT_PROFILE',
          'GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED','GENOS_ONTOLOGY_ENABLED',
          'GENOS_STATE_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','TEAM_ID','AD_WORKSPACE'):
    os.environ.pop(n,None)
os.environ.update(GENOS_RUNTIME_DIR=str(runtime),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',
    GENOS_RESIDENT_DATA='off',OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',
    PYTHONDONTWRITEBYTECODE='1',LAWRAG_WORKSPACE_ROOT=str(ROOT))
from resource_guard import Guard
guard=Guard(base); guard.start()
from pinned_imports import install,verify_loaded
install(ART/'transport')
import lawrag,lawrag.core,lawrag.research
for package,path in [(lawrag,'02_BACKEND/lawrag'),(lawrag.core,'02_BACKEND/lawrag/core'),(lawrag.research,'02_BACKEND/lawrag/research')]:
    package.__path__.extend([str(C/path),str(ROOT/path)])
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT)]
from semantic_runtime.app import create_app
from semantic_runtime.provider import Haiku
from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport,provider_request
from semantic_runtime.legal_agent import gateway,errors
from semantic_runtime.legal_agent.unified_rag import UnifiedRag
from semantic_runtime.legal_agent.answer_stream import capture
from fastapi.testclient import TestClient
from authorization import derive,self_test
source=read(DES/'source.json'); data=ROOT/source['data_path']; manifest=source['source_manifest']
case=read(DES/'cases-v2.json')[0]; allowed=set(case['document_ids']); auth_hash=sha(DES/'authorization-v2.json')
permitted={case['question']}; derivations=[]

class Authorized(LocalQwen38Transport):
    @property
    def public_scope(self): return tuple(sorted(allowed))
    def authorize(self,query,request,source_manifest,*,public_question):
        scope=set(query['scope']['document_version_ids'])
        if not public_question or not scope or not scope<=allowed or request.get('question',query['question']) not in permitted:
            raise errors.ContractError('Frozen public question/scope grant mismatch')
        assert sha(DES/'authorization-v2.json')==auth_hash and sha(self.policy_path)==self.policy_hash
        assert all(source_manifest[k]==manifest[k] for k in ('generation_id','store_sha256','export_allowed'))
        return {'kind':'USER_AUTHORIZED_PUBLIC_CONNECTION_PROBE','authorization_sha256':auth_hash,
                'policy_sha256':self.policy_hash,'public_question_asserted':True,'scope_document_ids':sorted(scope)}

t=Authorized(C,ROOT)
original_open=UnifiedRag.open
@contextmanager
def approved_open(host,state,principal,body):
    linked=host.shortcut.investigation(host.active_case,principal,'adr1300-'+base.name)
    assert linked['id']==host.active_case
    effective=derive(body,state,case['question'],allowed,host.active_case)
    assert effective==host.retrieval_question(state)
    receipt=host.model.ensure().context.binding['external_authorization']
    assert receipt['authorization_sha256']==auth_hash and set(receipt['scope_document_ids'])<=allowed
    permitted.add(effective)
    derivations.append({'request_id':body['request_id'],'original_question':body['question'],
        'effective_question':effective,'task':state['task'],'facts':deepcopy(state['facts']),
        'document_ids':state['document_ids'],'product_state_rewritten':False})
    put(base/'derivations'/f'{len(derivations):03d}.json',derivations[-1])
    with original_open(host,state,principal,body) as execution: yield execution
UnifiedRag.open=approved_open
profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
profile.update(model_binding=t.binding,max_output_tokens=None)
calls=[]; generations=[]; active=[]; events=[]; answer_events=[]; app=None; client=None
from lawrag.research.experiment_client import ExperimentClient
from lawrag.research.openrouter_legal_adapter import send_reserved
from lawrag.core import request_deadline
verify_loaded(ART/'transport')
audited=ExperimentClient(ROOT,base/'experiment-client',max_calls=20,max_repairs=0)
def send(*,body,ticket):
    if preflight: raise RuntimeError('PREFLIGHT_EXTERNAL_SEND_FORBIDDEN')
    verify_loaded(ART/'transport')
    return send_reserved(audited,body=body,ticket=ticket,phase=active[-1] if active else 'request',
                         error_module=errors,request_encoder=provider_request)
t.send_once=send
original_post=request_deadline.post_json
def post(url,**kwargs):
    guard.check(); payload=kwargs['json_body']
    assert payload['model']=='qwen/qwen3.8-27b' and url==t.policy['endpoint']+'/chat/completions'
    assert not any(k in payload for k in ('max_tokens','max_output_tokens','max_completion_tokens'))
    if any(c['status']=='unknown' for c in calls): raise errors.ContractError('Unknown outcome blocks further sends')
    n=len(calls)+1; out=base/'raw'/f'call-{n:03d}'; out.mkdir(parents=True,exist_ok=False)
    row={'number':n,'stage':active[-1] if active else None,'status':'started','provider':payload['provider']}
    calls.append(row); raw(out/'request.json.gz',payload); put(out/'started.json',row)
    begin=time.monotonic(); print('MODEL',n,row['stage'],flush=True)
    try:
        response=original_post(url,**kwargs)
        try: value=response.json()
        except ValueError: value={'non_json_body':response.text}
        raw(out/'response.json.gz',value)
        row.update(status='responded',http_status=response.status_code,usage=value.get('usage'),
            actual_provider=value.get('provider'),transport_diagnostics=response.extensions.get('absolute_deadline',{}))
        return response
    except Exception as exc:
        row.update(status='unknown',error_type=type(exc).__name__,transport_diagnostics=getattr(exc,'diagnostics',{}))
        if hasattr(exc,'partial_body'):
            import base64
            raw(out/'partial-response.json.gz',{'body_base64':base64.b64encode(exc.partial_body).decode(),
                'diagnostics':getattr(exc,'diagnostics',{})})
        raise
    finally:
        row['seconds']=time.monotonic()-begin; put(out/'finished.json',row)
request_deadline.post_json=post
original_generate=gateway.ModelGateway.generate
def generate(self,phase,view,schema_name,**kwargs):
    n=len(generations)+1; stage=view.get('source_stage',phase); row={'number':n,'stage':stage}
    generations.append(row); active.append(stage)
    raw(base/'canonical'/f'{n:03d}.json.gz',{'phase':phase,'view':view,'schema':self.protocol.schema(schema_name)})
    try:
        value=original_generate(self,phase,view,schema_name,**kwargs)
        raw(base/'canonical'/f'{n:03d}-output.json.gz',value); row['status']='accepted'; return value
    except Exception as exc:
        row.update(status='rejected',error_type=type(exc).__name__,error=str(exc)); raise
    finally:
        active.pop(); put(base/'canonical'/f'{n:03d}-summary.json',row)
gateway.ModelGateway.generate=generate
from semantic_runtime.legal_agent import law_navigation
original_decision=law_navigation.Investigation.request_decision
state_count=0
def decision(inv,data,actions,phase):
    global state_count
    try: return original_decision(inv,data,actions,phase)
    finally:
        state_count+=1;raw(base/'states'/f'{state_count:03d}.json.gz',inv.p)
law_navigation.Investigation.request_decision=decision
try:
    start=time.monotonic()
    app=create_app(runtime,data,contracts_root=C,release={'mode':'ADR1300-native-public','main_promoted':False},
        provider=Haiku(C,runtime/'provider',False,backend='source-only',trust_zone='internal'),
        implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=t,
        workspace_root=ROOT,runtime_root=runtime,
        memory_identity=lambda request:{'user_id':'adr1300','team_id':case['request']['team_id'],'document_ids':sorted(allowed)})
    pipeline=app.state.pipeline
    from semantic_runtime.team_scope import select_documents
    assert allowed<=set(select_documents(pipeline.store,case['request']['team_id']))
    for did in allowed:
        row=pipeline.store.db.execute('SELECT json FROM document WHERE document_id=?',(did,)).fetchone()
        assert json.loads(row[0])['document_metadata']['source_category']=='external'
    assert Path(importlib.import_module('semantic_runtime.legal_agent.completion_execution').__file__).is_relative_to(C)
    client=TestClient(app,raise_server_exceptions=False);client.__enter__()
    assert client.get('/health').status_code==200
    put(base/'binding.json',{'code_root':str(C.relative_to(ROOT)),'candidate_revision':f['candidate_revision'],
        'profile':pipeline.term_agent.profile,'scope':sorted(allowed),'data_path':source['data_path'],
        'source':{k:manifest[k] for k in ('generation_id','store_sha256','export_allowed')},
        'selection_fingerprint':pipeline.store.selection.fingerprint,'prepare_seconds':time.monotonic()-start,
        'native_api':'/v1/rag/ask','genos_field_executed':False})
    if preflight:
        assert self_test()==8
        query={'question':case['question'],'scope':{'document_version_ids':sorted(allowed)}}
        request=deepcopy(case['request']);receipt=t.authorize(query,request,manifest,public_question=True)
        context=SimpleNamespace(query=query,request=request,binding={'external_authorization':receipt,'model':t.binding,
            **{k:manifest[k] for k in ('generation_id','store_sha256','export_allowed')}})
        t.validate_authorization(context)
        put(base/'result.json',{'ready':True,'authorization_self_tests':8,'actual_model_calls':0,'public_documents':len(allowed)})
        print('PREFLIGHT_READY',flush=True)
    else:
        put(base/'dispatch.json',{'request':case['request'],'physical_limit':20,'terminal_repeats':0})
        start=time.monotonic()
        response=client.post('/v1/rag/ask',json=deepcopy(case['request']))
        elapsed=time.monotonic()-start; value=response.json()
        raw(base/'response.json.gz',{'http_status':response.status_code,'body':value})
        answer=value.get('answer') or {}
        text=answer.get('text','') if isinstance(answer,dict) else str(answer)
        (base/'answer.txt').write_text(text)
        result={'http_status':response.status_code,'seconds':elapsed,'physical_calls':len(calls),
            'unknown':sum(c['status']=='unknown' for c in calls),'run_id':value.get('run_id'),
            'claims':len(answer.get('claims',[])) if isinstance(answer,dict) else 0,
            'source_only':bool(answer.get('source_excerpt_reply')) if isinstance(answer,dict) else False,
            'quality_certified':False,'genos_field_executed':False}
        if response.status_code==200:
            before=len(calls); again=client.post('/v1/rag/ask',json=deepcopy(case['request']))
            result['duplicate']={'http_status':again.status_code,'same_answer':again.json().get('answer')==answer,'extra_model_calls':len(calls)-before}
            assert result['duplicate']['same_answer'] and result['duplicate']['extra_model_calls']==0
        put(base/'result.json',result);print('LIVE_RESULT',json.dumps(result,ensure_ascii=False),flush=True)
except Exception as exc:
    put(base/'runner-failure.json',{'type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc(),'model_calls':len(calls)})
    print('RUNNER_FAILURE',type(exc).__name__,str(exc),flush=True);raise
finally:
    put(base/'calls.json',calls);put(base/'generations.json',generations)
    put(base/'authorized-derivations.json',derivations)
    if client is not None:client.__exit__(None,None,None)
    if app is not None:app.state.pipeline.store.close()
    guard.done.set();guard.thread.join(timeout=2)
    put(base/'resource-final.json',{'peak_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'sample':guard.check(),'candidate_unchanged':all(sha(C/n)==h for n,h in f['files'].items())})
