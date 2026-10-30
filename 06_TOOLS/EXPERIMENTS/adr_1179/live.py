"""Exact ADR1167 repaired supervisor on MAIN112; isolated native HTTP, audited transport."""
from common import *
import asyncio,gzip,importlib,jsonschema,os,resource,sys,time,traceback,threading
from copy import deepcopy
sys.dont_write_bytecode=True
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
f=read(DES/'freeze.json')
baseline=read(DES/'baseline.json');C=ROOT/f['code_root'];pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';arm='scoped'
assert sha(pointer)==f['pointer_sha256']
for name,h in f['inputs'].items():assert sha(ROOT/name)==h,name
for name,h in f['scripts'].items():assert sha(ROOT/name)==h,name
assert read(ART/('check-'+f.get('execution_id',f['candidate_revision']['revision_id'])+'.json'))['failed']==0
for name,h in f['files'].items():assert sha(C/name)==h,name
for name in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_IMPLEMENTATION','LEGAL_AGENT_PROFILE','GENOS_RAG_MAX_MODEL_ATTEMPTS','GENOS_RAG_MAX_TOOL_ACTIONS','GENOS_RAG_WALL_SECONDS','GENOS_RAG_SEARCH_ROUNDS','GENOS_RAG_ASSESSMENT_REENTRY_LIMIT','GENOS_ONTOLOGY_ENABLED'):
 if os.environ.get(name):raise RuntimeError('Unexpected runtime override: '+name)
setup='--setup-only' in sys.argv
preflight='--preflight' in sys.argv
case_id=next((x for x in sys.argv[1:] if x.startswith('cm-')),'cm-001')
frozen_case=next(c for c in read(DES/'cases.json') if c['id']==case_id)
base=ART/'live'/case_id
if (base/'dispatch.json').exists():raise RuntimeError('Live case already dispatched; no automatic repeat')
if case_id=='cm-009':
 previous='cm-007'
 assert read(ART/'live'/previous/'gate.json')['passed'], 'Previous case gate did not pass'
reg=read(ART/'regression-comparison.json');assert reg['new_regressions']==[],reg
assert read(ART/('scope-replay-'+f.get('execution_id',f['candidate_revision']['revision_id'])+'.json'))['passed']
runtime=base/'runtime';base.mkdir(parents=True,exist_ok=True)

os.environ.update(GENOS_RUNTIME_DIR=str(runtime),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(ROOT))
for name in ('TEAM_ID','AD_WORKSPACE'):os.environ.pop(name,None)
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT)]
from types import SimpleNamespace
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport
from semantic_runtime.legal_agent.workflow_tiers_policy import profile as check_profile
from fastapi.testclient import TestClient
t=LocalQwen38Transport(C,ROOT)
pinned=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
profile=check_profile({**pinned,'model_binding':t.binding,'max_output_tokens':t.policy['max_output_tokens']},require_model=True)
assert profile['max_model_attempts']==40 and profile['max_tool_actions']==1024 and profile['wall_seconds']==1800 and profile['max_output_tokens'] is None
binding={'mode':'isolated-candidate','code_root':str(C),'data_path':baseline['release']['data_path'],'parent_release':'MAIN112/supervisor' ,'candidate':f['candidate_revision'],'quality_certified':False}
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
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError,ExperimentTransportError
health=http_client.get('/health');assert health.status_code==200
put(base/'binding.json',{'pointer':read(pointer),'binding':binding,'app_injected':True,'service_entry':'semantic_runtime.app.create_app /v1/rag/ask','profile':profile,'public_scope':list(t.public_scope),'data_path':baseline['release']['data_path'],'application_prepare_seconds':application_seconds,'profile_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'search_selection_fingerprint':pipeline.store.selection.fingerprint,'model_policy_sha256':sha(C/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'transport_instrumentation':'Native LocalQwen38Transport + gateway physical reservation; audited httpx; isolated candidate API','genos_executed':False})
from cm_authorization import install
cm_context=install(t,pkg,f,frozen_case,baseline)
if setup:
 print('SETUP',flush=True)
 pipeline.store.close();sys.stdout.flush();os._exit(0)



from resource_guard import Guard
guard=Guard(base);guard.start()
import httpx
original_client=httpx.Client
calls=[];generations=[];active=[];spans=[]
started=time.monotonic()
def gz(p,v):
 ref=write_raw_json(p,v)
 write_summary(p.with_suffix('.reference.json'),ref)
class RecordedClient(original_client):
 def post(self,url,**kwargs):
  guard.check()
  if not str(url).startswith(t.policy['endpoint']+'/chat/completions'):raise RuntimeError('Unexpected external endpoint')
  n=len(calls)+1;out=base/'raw'/f'call-{n:03d}';out.mkdir(parents=True,exist_ok=False)
  payload=kwargs['json'];assert payload['model']=='qwen/qwen3.8-27b'
  assert not any(k in payload for k in ('max_tokens','max_completion_tokens','max_output_tokens'))
  row={'number':n,'stage':active[-1] if active else None,'provider':payload['provider'],'status':'started'};calls.append(row)
  gz(out/'request.json.gz',payload);put(out/'started.json',row)
  print('MODEL',case_id,n,row['stage'],payload['provider']['only'],flush=True);begin=time.monotonic()
  try:
   response=super().post(url,**kwargs)
   try:raw=response.json()
   except ValueError:raw={'non_json_body':response.text}
   gz(out/'response.json.gz',raw);row.update(status='responded',http_status=response.status_code,usage=raw.get('usage'),actual_provider=raw.get('provider'))
   return response
  except httpx.HTTPError as exc:row.update(status='unknown',error_type=type(exc).__name__);raise
  finally:row['seconds']=time.monotonic()-begin;put(out/'finished.json',row)
httpx.Client=RecordedClient
original_generate=gateway.ModelGateway.generate
from semantic_runtime.legal_agent import law_navigation
old_decision=law_navigation.Investigation.request_decision
state_count=0
last_state=None
def decision(inv,data,actions,phase):
 global state_count,last_state
 try:return old_decision(inv,data,actions,phase)
 finally:
  state_count+=1;last_state=base/'states'/f'{state_count:03d}.json.gz';gz(last_state,inv.p)
law_navigation.Investigation.request_decision=decision
def generate(self,phase,view,schema_name,**kwargs):
 number=len(generations)+1;stage=view.get('source_stage',phase);row={'number':number,'stage':stage};generations.append(row);active.append(stage)
 gz(base/'canonical'/f'{number:03d}.json.gz',{'phase':phase,'view':view,'schema':self.protocol.schema(schema_name)})
 try:
  value=original_generate(self,phase,view,schema_name,**kwargs);gz(base/'canonical'/f'{number:03d}-output.json.gz',value);row['status']='accepted';return value
 except Exception as exc:row.update(status='rejected',error_type=type(exc).__name__,error=str(exc));raise
 finally:active.pop();put(base/'canonical'/f'{number:03d}-summary.json',row)
gateway.ModelGateway.generate=generate
put(base/'dispatch.json',{'case_id':case_id,'code':f['candidate_revision'],'physical_limit':40,'same_case_retry':False,'provider_policy_sha256':t.routing_hash,'new_model_calls_before_dispatch':0})
put(base/'request.json',frozen_case['request'])
result={'case_id':case_id,'quality_certified':False,'environment':'isolated same-code native serving transport and API','stronger_model_comparison':False}
try:
 response=asyncio.run(cm_context(actual.service,deepcopy(frozen_case['request'])));put(base/'response.json',response)
 body=response.get('body') or {};result.update(http_status=response['status'],status=body.get('status'),run_id=body.get('run_id'))
 answer=body.get('answer',{});(base/'answer.txt').write_text(answer.get('text','') if isinstance(answer,dict) else str(answer))
 # Persist the actual API follow-up endpoints only when the API supplies them.
except Exception as exc:
 result.update(error_type=type(exc).__name__,error=str(exc));(base/'error.txt').write_text(traceback.format_exc())
finally:
 put(base/'calls.json',calls);put(base/'generations.json',generations)
 if last_state:put(base/'investigation-state.json',read(last_state))
 guard.done.set()
 result.update(model_calls=len(calls),seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
  journals=[str(p.relative_to(ROOT)) for p in runtime.rglob('journal.sqlite')],active_pointer_unchanged=sha(pointer)==f['pointer_sha256'])
 put(base/'result.json',result);print('LIVE_DONE',case_id,result,flush=True)
pipeline.store.close();sys.stdout.flush();os._exit(0)
