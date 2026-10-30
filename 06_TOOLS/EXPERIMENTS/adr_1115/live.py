"""Single frozen public probe through candidate native HTTP API, not selected MAIN."""
from common import *
import asyncio,gzip,importlib,jsonschema,os,resource,sys,time,traceback
from types import SimpleNamespace
from copy import deepcopy
sys.dont_write_bytecode=True
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
f=read(DES/'freeze.json');baseline=read(DES/'baseline.json');C=ROOT/f['code_root'];RUN=ART/'run-002';pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';arm='integrated'
assert read(ART/'check-001.json')['status']==0
assert sha(pointer)==f['pointer_sha256']
for name,h in f['inputs'].items():assert sha(ROOT/name)==h,name
for name,h in f['scripts'].items():assert sha(ROOT/name)==h,name
for name,h in f['files'].items():assert sha(C/name)==h,name
for name in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_IMPLEMENTATION','LEGAL_AGENT_PROFILE','GENOS_RAG_MAX_MODEL_ATTEMPTS','GENOS_RAG_MAX_TOOL_ACTIONS','GENOS_RAG_WALL_SECONDS','GENOS_RAG_SEARCH_ROUNDS','GENOS_RAG_ASSESSMENT_REENTRY_LIMIT'):
 if os.environ.get(name):raise RuntimeError('Unexpected runtime override: '+name)
setup='--setup-only' in sys.argv
base=ART/'setup-only'/arm if setup else RUN
runtime=base/'runtime';base.mkdir(parents=True,exist_ok=True)
os.environ.update(GENOS_RUNTIME_DIR=str(runtime),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(ROOT))
for name in ('TEAM_ID','AD_WORKSPACE'):os.environ.pop(name,None)
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT)]
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport
from semantic_runtime.legal_agent.workflow_tiers_policy import profile as check_profile
from fastapi.testclient import TestClient
t=LocalQwen38Transport(C,ROOT)
pinned=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
profile=check_profile({**pinned,'model_binding':t.binding,'max_output_tokens':t.policy['max_output_tokens']},require_model=True)
assert profile['max_model_attempts']==40 and profile['max_tool_actions']==1024 and profile['wall_seconds']==1800 and profile['max_output_tokens'] is None
binding={'mode':'isolated-candidate','code_root':str(C),'data_path':baseline['release']['data_path'],'parent_release':'MAIN106','candidate':f['binding'],'quality_certified':False}
application_started=time.monotonic()
app=create_app(runtime,ROOT/baseline['release']['data_path'],contracts_root=C,release=binding,provider=object(),vector=False,implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=t,workspace_root=ROOT,runtime_root=runtime)
application_seconds=time.monotonic()-application_started;pipeline=app.state.pipeline
http_client=TestClient(app);http_client.__enter__()
async def candidate_service(_environment,request):
 response=http_client.post('/v1/rag/ask',json=request['json'])
 return {'status':response.status_code,'body':response.json()}
actual=SimpleNamespace(service=candidate_service)
pkg='semantic_runtime.legal_agent'
local=importlib.import_module(pkg+'.local_gemma');errors=importlib.import_module(pkg+'.errors')
structured_content=importlib.import_module(pkg+'.model_contract').structured_content
gateway=importlib.import_module(pkg+'.gateway')
from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError,ExperimentTransportError
health=http_client.get('/health');assert health.status_code==200
put(base/'binding.json',{'pointer':read(pointer),'binding':binding,'app_injected':True,'service_entry':'semantic_runtime.app.create_app /v1/rag/ask','profile':profile,'public_scope':list(t.public_scope),'data_path':baseline['release']['data_path'],'application_prepare_seconds':application_seconds,'profile_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'search_selection_fingerprint':pipeline.store.selection.fingerprint,'model_policy_sha256':sha(C/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'transport_instrumentation':'ExperimentClient only; native candidate HTTP API; not active MAIN','genos_executed':False})
if setup:
 print('SETUP PASS: frozen candidate native HTTP, health200, model0',flush=True)
 http_client.__exit__(None,None,None);sys.stdout.flush();os._exit(0)

current={};original_generate=gateway.ModelGateway.generate
from functools import wraps
observed_spans=[]
def timed_function(owner,name,label):
    original=getattr(owner,name)
    @wraps(original)
    def measured(*args,**kwargs):
        started=time.monotonic()
        try:return original(*args,**kwargs)
        finally:observed_spans.append({'function':label,'start':started,'end':time.monotonic(),'seconds':time.monotonic()-started})
    setattr(owner,name,measured)
for module in ('navigation_agent','document_agent','task_harness_agent','legal_navigation'):
    timed_function(importlib.import_module('semantic_runtime.'+module),'glossary_assets','glossary.load')
timed_function(importlib.import_module(pkg+'.definition_entry'),'verified','definition_entry.verified')
timed_function(importlib.import_module(pkg+'.law_navigation').Investigation,'view','Investigation.view')
def gz(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(p,'wt',encoding='utf8') as out:json.dump(v,out,ensure_ascii=False,separators=(',',':'))
def generate(self,phase,view,schema_name,**kwargs):
    out=current['out'];records=current['generations'];number=len(records)+1
    row={'number':number,'phase':phase,'stage':view.get('source_stage',phase),'schema_name':schema_name};records.append(row)
    schema=self.protocol.schema(schema_name);gz(out/'canonical'/f'{number:03d}.json.gz',{'phase':phase,'view':view,'schema':schema})
    current['active'].append(row)
    try:
        value=original_generate(self,phase,view,schema_name,**kwargs);row['accepted']=True;gz(out/'canonical'/f'{number:03d}-output.json.gz',value);return value
    except BaseException as exc:row.update(accepted=False,error_type=type(exc).__name__,error=str(exc));raise
    finally:current['active'].pop();put(out/'generations.json',records)
gateway.ModelGateway.generate=generate
def find_stage(value):
    if isinstance(value,dict):
        if value.get('source_stage'):return value['source_stage']
        for v in value.values():
            found=find_stage(v)
            if found:return found
    elif isinstance(value,list):
        for v in value:
            found=find_stage(v)
            if found:return found
def check_resources():
    values={row.split(':')[0]:int(row.split()[1])*1024 for row in Path('/proc/meminfo').read_text().splitlines() if row.startswith(('MemAvailable:','SwapTotal:','SwapFree:'))}
    rss=next(int(row.split()[1])*1024 for row in Path('/proc/self/status').read_text().splitlines() if row.startswith('VmRSS:'))
    import shutil
    assert rss<=4*1024**3 and values['MemAvailable']>=3*1024**3 and shutil.disk_usage(ROOT).free>=20*1024**3,'Resource guard exceeded'
    assert values['SwapTotal']-values['SwapFree']<=512*1024**2,'Swap pressure guard exceeded'

last_provider_start=None
provider_pacing=[]
def send_once(*,body,ticket):
    global last_provider_start
    check_resources()
    wait=max(0,65-(time.monotonic()-last_provider_start)) if last_provider_start is not None else 0
    if wait:
        if ticket['remaining_seconds']<=wait+1:raise errors.DeadlineExceeded('provider pacing would exhaust existing request deadline')
        start_wait=time.monotonic()
        while time.monotonic()-start_wait<wait:
            time.sleep(min(10,wait-(time.monotonic()-start_wait)));check_resources()
        provider_pacing.append({'seconds':time.monotonic()-start_wait})
        ticket={**ticket,'remaining_seconds':ticket['remaining_seconds']-(time.monotonic()-start_wait)}
        put(current['out']/'provider-pacing.json',provider_pacing)
    last_provider_start=time.monotonic()
    if body.get('model')!=t.binding['model'] or body.get('stream') is not False:raise errors.ContractError('Request differs from selected model binding')
    assert sha(pointer)==f['pointer_sha256'],'Active selection changed; stop sending'
    client=current['client'];out=current['out'];phase=current['active'][-1]['stage'] if current['active'] else 'native-rag'
    for message in body.get('messages',[]):
        try:phase=find_stage(json.loads(message.get('content',''))) or phase
        except (ValueError,TypeError):pass
    n=client.calls+1;payload=local.provider_request(body);schema=payload.get('response_format',{}).get('json_schema',{}).get('schema',{})
    jsonschema.Draft202012Validator.check_schema(schema)
    row={'call':n,'phase':phase,'generation':current['active'][-1]['number'] if current['active'] else None,'status':'started'}
    current['calls'].append(row);put(out/'calls.json',current['calls']);gz(out/'wire'/f'{n:03d}.json.gz',body)
    print('MODEL',current['case']['id'],n,phase,flush=True);started=time.monotonic()
    try:
        try:raw=client.chat_completions(payload,phase=phase,timeout_seconds=min(180,ticket['remaining_seconds']))
        except ExperimentFormatError as exc:
            if exc.response:
                # Preserve the selected transport's typed incomplete-output
                # contract, including MAIN103's removal of output caps.
                data=exc.response['body_json'];choices=data.get('choices') or []
                if data.get('model')!=t.binding['model'] or data.get('provider')!='Parasail':
                    raise errors.ContractError('actual model/provider mismatch') from exc
                if ((data.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens') or any(
                        choice.get('message',{}).get('reasoning') for choice in choices):
                    raise errors.ContractError('local Qwen3.8 reasoning was not disabled') from exc
                if len(choices)==1 and choices[0].get('finish_reason') in ('length','content_filter','refusal'):
                    try:structured_content(data,allow_length_repair=t.policy['max_output_tokens'] is not None and 'max_tokens' in payload)
                    except Exception as cause:cause.response=exc.response;raise
            err=errors.ProposalError('local Qwen3.8 returned an incomplete response');err.response=exc.response;raise err from exc
        except ExperimentProviderError as exc:
            status=(exc.response or {}).get('status_code',0)
            if status==200:raise errors.ContractError('actual provider/model/reasoning mismatch') from exc
            raise errors.TransportError('experiment provider failure',retryable=status==429,unknown=status>=500,response=exc.response) from exc
        except ExperimentTransportError as exc:raise errors.TransportError(str(exc),retryable=exc.retryable,unknown=exc.unknown) from exc
        if raw['body_json'].get('model')!=t.binding['model'] or raw['body_json'].get('provider')!='Parasail':raise errors.ContractError('actual model/provider mismatch')
        raw['acceptance']='ACCEPTED';row.update(status='completed',http_status=raw['status_code']);return raw
    except BaseException as exc:row.update(status='failed',error_type=type(exc).__name__,error=str(exc));raise
    finally:row['seconds']=time.monotonic()-started;put(out/'calls.json',current['calls'])
t.send_once=send_once
frozen_case=read(DES/'case.json');cases=[{'id':frozen_case['id'],'question':frozen_case['request']['json']['question']}];started_all=time.monotonic();fatal=False
for case in cases:
    out=RUN/case['id']
    if (out/'result.json').exists():raise RuntimeError('Completed sample cannot be rerun')
    if out.exists():
        put(out/'result.json',{'case_id':case['id'],'status':'interrupted','error':'Previously started without final result; raw calls preserved and request not replayed','model_calls':len(list((out/'raw').glob('call-*'))),'usage':read(out/'raw/usage.json') if (out/'raw/usage.json').exists() else [],'elapsed_seconds':None,'journal_paths':[]})
        continue
    assert sha(pointer)==f['pointer_sha256']
    out.mkdir();client=ExperimentClient(ROOT,out/'raw',max_calls=profile['max_model_attempts'],max_output_tokens=profile['max_output_tokens'],max_repairs=0)
    current.clear();current.update(out=out,client=client,calls=[],active=[],generations=[],case=case)
    before={p.resolve() for p in runtime.rglob('journal.sqlite')};started=time.monotonic()
    result={'case_id':case['id'],'arm':arm,'environment':'WSL stable review candidate native HTTP','app_injected':True,'in_sample':True,'quality_certified':False}
    request=deepcopy(frozen_case['request'])
    assert set(request['json']['document_ids'])<=set(t.public_scope)
    put(out/'request.json',request);print('CASE_START',case['id'],flush=True)
    try:
        response=asyncio.run(actual.service({},request));put(out/'response.json',response)
        body=response.get('body') or {};answer=body.get('answer') or {}
        result.update(http_status=response.get('status'),status=body.get('status'),run_id=body.get('run_id'),error=body.get('error') or body.get('detail'))
        (out/'answer.txt').write_text((answer.get('text','') if isinstance(answer,dict) else str(answer)) or body.get('message',''))
        if body.get('code')=='INTERNAL_CONTRACT_ERROR' or 'INTERNAL_CONTRACT_ERROR' in json.dumps(body.get('detail',{})):fatal=True
    except BaseException as exc:
        result.update(error_type=type(exc).__name__,error=str(exc));(out/'error.txt').write_text(traceback.format_exc())
        if isinstance(exc,(errors.ContractError,AssertionError,KeyboardInterrupt,MemoryError)):fatal=True
    finally:
        after={p.resolve() for p in runtime.rglob('journal.sqlite')}
        put(out/'observed-spans.json',observed_spans)
        result.update(application_prepare_seconds=application_seconds,observed_spans=observed_spans,model_calls=client.calls,usage=client.usage,elapsed_seconds=time.monotonic()-started,model_transport_seconds=sum(x.get('seconds',0) for x in current['calls']),peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            journal_paths=[str(p.relative_to(ROOT)) for p in sorted(after-before)],active_pointer_unchanged=sha(pointer)==f['pointer_sha256'],fatal=fatal)
        put(out/'result.json',result)
        complete=[c['id'] for c in cases if (RUN/c['id']/'result.json').exists()]
        put(RUN/'progress.json',{'completed':len(complete),'total':1,'last_case':case['id'],'elapsed_seconds':time.monotonic()-started_all,'fatal':fatal})
        print('CASE_DONE',case['id'],result.get('http_status'),result['model_calls'],round(result['elapsed_seconds'],1),'completed',len(complete),flush=True)
    if fatal:break
http_client.__exit__(None,None,None);sys.stdout.flush();sys.stderr.flush();os._exit(1 if fatal else 0)
