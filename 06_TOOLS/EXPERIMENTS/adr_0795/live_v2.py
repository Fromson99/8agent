"""Observe the selected MAIN through its actual service entry; no product changes."""
from pathlib import Path
import asyncio, hashlib, importlib, json, os, sys, time, traceback
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0795-main72-workflow-comparison'
D=A/'artifacts/design'; O=A/'artifacts/live-v2'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze-v2.json')
for name,h in f['files'].items():assert sha(R/name)==h,name
O.mkdir(exist_ok=False)
sys.dont_write_bytecode=True
sys.path[:0]=[str(R),str(R/'02_BACKEND')]
os.environ.update(AD_WORKER_ENABLED='0',TEAM_ID='risk_team',LAWRAG_WORKSPACE_ROOT=str(R),GENOS_RUNTIME_DIR=str(O/'runtime'))
for name in f['budget_environment_keys']:
    if os.environ.get(name):raise RuntimeError('Unexpected budget override: '+name)
import service
actual=importlib.import_module('service.service')
app=actual.application()
t=app.state.pipeline.term_agent.transport
pkg=type(t).__module__.rsplit('.',1)[0]
local=importlib.import_module(pkg+'.local_gemma')
errors=importlib.import_module(pkg+'.errors')
structured_content=importlib.import_module(pkg+'.model_contract').structured_content
import lawrag
lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError,ExperimentTransportError
client=ExperimentClient(R,O/'raw',max_calls=40,max_output_tokens=6400,max_repairs=0)
assert Path(t.code_root)==R/f['code_root']
profile=app.state.pipeline.term_agent.profile
assert profile['max_model_attempts']==40 and profile['wall_seconds']==1800
put(O/'binding.json',{'service_module':str(Path(actual.__file__).relative_to(R)), 'transport_module':type(t).__module__, 'profile':profile,'code_root':f['code_root'],'pointer':read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'runtime_root':str(O/'runtime')})
def find_stage(v):
    if isinstance(v,dict):
        if v.get('source_stage'):return v['source_stage']
        for value in v.values():
            found=find_stage(value)
            if found:return found
    if isinstance(v,list):
        for value in v:
            found=find_stage(value)
            if found:return found
    return None
def send_once(*,body,ticket):
    phase='native-rag'
    for message in body.get('messages',[]):
        try:phase=find_stage(json.loads(message.get('content',''))) or phase
        except (ValueError,TypeError):pass
    print(json.dumps({'dispatch':client.calls+1,'phase':phase},ensure_ascii=False),flush=True)
    try:raw=client.chat_completions(local.provider_request(body),phase=phase,timeout_seconds=min(180,ticket['remaining_seconds']))
    except ExperimentFormatError as exc:
        if exc.response:
            try:structured_content(exc.response['body_json'],require_complete=True)
            except Exception as error:error.response=exc.response;raise
        raise
    except ExperimentProviderError as exc:
        status=(exc.response or {}).get('status_code',0)
        raise errors.TransportError('experiment provider failure',retryable=status==429,unknown=status>=500,response=exc.response) from exc
    except ExperimentTransportError as exc:
        raise errors.TransportError('experiment outcome unknown',unknown=True) from exc
    if raw['body_json'].get('model')!=t.binding['model'] or raw['body_json'].get('provider')!='Parasail':
        raise errors.ContractError('actual model/provider mismatch')
    raw['acceptance']='ACCEPTED'
    return raw
t.send_once=send_once
started=time.monotonic();result={'environment':'WSL local actual selected MAIN72 service','in_sample':True,'quality_certified':False}
status=1
try:
    request=read(D/'criteria.json')['service_request']
    response=asyncio.run(actual.service({},request))
    put(O/'response.json',response)
    value=response.get('body',{})
    result.update(http_status=response.get('status'),status=value.get('status'),run_id=value.get('run_id'),model_calls_before_duplicate=client.calls)
    if value.get('run_id'):
        saved=asyncio.run(actual.service({}, {'API_TYPE':'WORKFLOW_STATUS','run_id':value['run_id'],'session_id':value['session_id']}))
        put(O/'status-response.json',saved)
        duplicate=asyncio.run(actual.service({},request))
        put(O/'duplicate-response.json',duplicate)
        result['checks']={'status_answer_identical':saved.get('body',{}).get('answer')==value.get('answer'),
                          'duplicate_answer_identical':duplicate.get('body',{}).get('answer')==value.get('answer'),
                          'duplicate_run_identical':duplicate.get('body',{}).get('run_id')==value['run_id'],
                          'duplicate_no_model_calls':client.calls==result['model_calls_before_duplicate']}
        result['journal_root']=str((app.state.workflow_runtime.root/value['run_id']).relative_to(R))
    status=0
except BaseException as exc:
    result.update(error=type(exc).__name__,message=str(exc));(O/'error.txt').write_text(traceback.format_exc())
finally:
    result.update(model_calls=client.calls,usage=client.usage,elapsed_seconds=time.monotonic()-started)
    put(O/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='usage'},ensure_ascii=False),flush=True)
    app.state.pipeline.store.close()
    sys.stdout.flush();sys.stderr.flush();os._exit(status)
