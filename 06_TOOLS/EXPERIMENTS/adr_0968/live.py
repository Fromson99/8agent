"""Actual selected local service, serial CM51, new state per ordinary RAG request."""
from common import *
import asyncio,gzip,importlib,jsonschema,os,resource,sys,time,traceback
sys.dont_write_bytecode=True
f=read(DES/'freeze.json');baseline=read(DES/'baseline.json');C=ROOT/f['code_root'];pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
assert sha(pointer)==f['pointer_sha256']
for name,h in f['files'].items():assert sha(ROOT/name)==h,name
for name,h in f['scripts'].items():assert sha(ROOT/name)==h,name
assert sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')==f['client_sha256']
for name,h in f['serving_files'].items():assert sha(C/name)==h,name
for name in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_IMPLEMENTATION','LEGAL_AGENT_PROFILE','GENOS_RAG_MAX_MODEL_ATTEMPTS','GENOS_RAG_MAX_TOOL_ACTIONS','GENOS_RAG_WALL_SECONDS','GENOS_RAG_SEARCH_ROUNDS','GENOS_RAG_ASSESSMENT_REENTRY_LIMIT'):
    if os.environ.get(name):raise RuntimeError('Unexpected runtime override: '+name)
setup='--setup-only' in sys.argv
base=ART/'setup-only' if setup else RUN
runtime=base/'runtime';base.mkdir(parents=True,exist_ok=True)
os.environ.update(GENOS_RUNTIME_DIR=str(runtime),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(ROOT))
for name in ('TEAM_ID','AD_WORKSPACE'):os.environ.pop(name,None)
sys.path[:0]=[str(ROOT),str(ROOT/'02_BACKEND')]
import service
actual=importlib.import_module('service.service');app=actual.application();pipeline=app.state.pipeline;t=pipeline.term_agent.transport
assert Path(pipeline.contracts.root)==C and Path(t.code_root)==C
binding=getattr(actual,'_BINDING',getattr(getattr(actual,'_runtime',None),'_BINDING',None));assert binding['mode']=='local-release' and binding['generation']==98
pkg=type(t).__module__.rsplit('.',1)[0]
local=importlib.import_module(pkg+'.local_gemma');errors=importlib.import_module(pkg+'.errors')
structured_content=importlib.import_module(pkg+'.model_contract').structured_content
gateway=importlib.import_module(pkg+'.gateway')
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError,ExperimentTransportError
profile=pipeline.term_agent.profile
assert profile['max_model_attempts']==read(DES/'criteria.json')['limits']['attempts_per_case']
health=asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'}));assert health['status']==200
put(base/'binding.json',{'pointer':read(pointer),'binding':binding,'app_injected':False,'service_entry':str(Path(actual.__file__).relative_to(ROOT)),'service_backend':str(Path(service.__file__).relative_to(ROOT)),
 'pipeline_module':str(Path(sys.modules[type(pipeline).__module__].__file__).relative_to(ROOT)),'profile':profile,'public_scope':list(t.public_scope),'data_path':baseline['release']['data_path'],'profile_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'search_selection_fingerprint':pipeline.store.selection.fingerprint,
 'model_policy_sha256':sha(C/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'transport_instrumentation':'send_once via ExperimentClient, unchanged provider_request and native gateway; no product app injection','health':health,'genos_executed':False})
if setup:
    print('SETUP PASS: actual MAIN98 service, health200,418files, native profile; model0',flush=True)
    pipeline.store.close();sys.stdout.flush();os._exit(0)

current={};original_generate=gateway.ModelGateway.generate
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
def send_once(*,body,ticket):
    if body.get('model')!=t.binding['model'] or body.get('stream') is not False:raise errors.ContractError('Request differs from selected model binding')
    assert sha(pointer)==f['pointer_sha256'],'Active selection changed; stop sending'
    client=current['client'];out=current['out'];phase='native-rag'
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
                try:structured_content(exc.response['body_json'],require_complete=True)
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
cases=read(DES/'cases.json');started_all=time.monotonic();fatal=False
for case in cases:
    out=RUN/case['id']
    if (out/'result.json').exists():continue
    if out.exists():
        put(out/'result.json',{'case_id':case['id'],'status':'interrupted','error':'Previously started without final result; raw calls preserved and request not replayed','model_calls':len(list((out/'raw').glob('call-*'))),'usage':read(out/'raw/usage.json') if (out/'raw/usage.json').exists() else [],'elapsed_seconds':None,'journal_paths':[]})
        continue
    assert sha(pointer)==f['pointer_sha256']
    out.mkdir();client=ExperimentClient(ROOT,out/'raw',max_calls=profile['max_model_attempts'],max_output_tokens=profile['max_output_tokens'],max_repairs=0)
    current.clear();current.update(out=out,client=client,calls=[],active=[],generations=[],case=case)
    before={p.resolve() for p in runtime.rglob('journal.sqlite')};started=time.monotonic()
    result={'case_id':case['id'],'environment':'WSL actual selected MAIN98 RAG_ASK','app_injected':False,'in_sample':True,'quality_certified':False}
    request={'API_TYPE':'RAG_ASK','json':{'question':case['question'],'document_ids':sorted(t.public_scope),'public_question':True,'use_llm':True}}
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
        result.update(model_calls=client.calls,usage=client.usage,elapsed_seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            journal_paths=[str(p.relative_to(ROOT)) for p in sorted(after-before)],active_pointer_unchanged=sha(pointer)==f['pointer_sha256'],fatal=fatal)
        put(out/'result.json',result)
        complete=[c['id'] for c in cases if (RUN/c['id']/'result.json').exists()]
        put(RUN/'progress.json',{'completed':len(complete),'total':51,'last_case':case['id'],'elapsed_seconds':time.monotonic()-started_all,'fatal':fatal})
        print('CASE_DONE',case['id'],result.get('http_status'),result['model_calls'],round(result['elapsed_seconds'],1),'completed',len(complete),flush=True)
    if fatal:break
pipeline.store.close();sys.stdout.flush();sys.stderr.flush();os._exit(1 if fatal else 0)
