"""Single authorized question through actual selected service; immutable raw audit."""
from common import *
import asyncio,importlib,os,resource,time,traceback
from copy import deepcopy
os.environ.update(OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
f=read(DES/'freeze.json');baseline=read(DES/'baseline.json');C=ROOT/f['code_root'];pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
assert sha(pointer)==f['pointer_sha256']
for n,h in f['inputs'].items():assert sha(ROOT/n)==h,n
for n,h in f['scripts'].items():assert sha(ROOT/n)==h,n
for n,h in f['files'].items():assert sha(C/n)==h,n
for n in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_IMPLEMENTATION','LEGAL_AGENT_PROFILE','GENOS_RAG_MAX_MODEL_ATTEMPTS','GENOS_RAG_MAX_TOOL_ACTIONS','GENOS_RAG_WALL_SECONDS','GENOS_RAG_SEARCH_ROUNDS','GENOS_RAG_ASSESSMENT_REENTRY_LIMIT','GENOS_ONTOLOGY_ENABLED','GENOS_RAG_ONTOLOGY_ENABLED','GENOS_RAG_ONTOLOGY_CONFIG'):
 if os.environ.get(n):raise RuntimeError('Unexpected runtime override: '+n)
case_id=sys.argv[1];assert case_id == 'gold-369'
frozen_case=next(c for c in read(DES/'cases.json') if c['id']==case_id)
base=ART/'live'/case_id
if (base/'dispatch.json').exists():raise RuntimeError('Already dispatched; no automatic repeat')
base.mkdir(parents=True,exist_ok=False);runtime=base/'runtime'
assert not os.environ.get('DP')
os.environ.update(GENOS_RUNTIME_DIR=str(runtime),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(ROOT))
for n in ('TEAM_ID','AD_WORKSPACE','GENOS_STATE_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','GENOS_SYSTEM_LOG_DIR'):os.environ.pop(n,None)
from resource_guard import Guard
guard=Guard(base);guard.start()
sys.path[:0]=[str(ROOT),str(ROOT/'02_BACKEND')]
import faulthandler
faulthandler.enable()
import service
actual=importlib.import_module('service.service')
original_binding=actual._local_release
def candidate_binding():
 selected,data,binding=original_binding()
 assert binding['generation']==129 and selected==ROOT/baseline['release']['code_root']
 return C,data,{**binding,'code_sha256':hashlib.sha256(json.dumps(f['files'],sort_keys=True).encode()).hexdigest(),'experiment_candidate':'ADR1249/repaired','main_promoted':False}
actual._local_release=candidate_binding
application_started=time.monotonic();app=actual.application();application_seconds=time.monotonic()-application_started
pipeline=app.state.pipeline;t=pipeline.term_agent.transport;profile=pipeline.term_agent.profile
assert Path(pipeline.contracts.root)==C
pkg=type(pipeline).__module__.rsplit('.',1)[0]+'.legal_agent'
assert Path(importlib.import_module(pkg+'.requirement_coverage').__file__).is_relative_to(C)
assert profile['candidate_navigation']['requirement_coverage'] is True
assert profile['answer_presentation']=='accepted-content-v1'
assert profile['max_model_attempts']==40 and profile['max_tool_actions']==1024 and profile['wall_seconds']==1800 and profile['max_output_tokens'] is None
binding=getattr(actual,'_BINDING',getattr(getattr(actual,'_runtime',None),'_BINDING',None));assert binding['mode']=='local-release' and binding['experiment_candidate']=='ADR1249/repaired'
health=asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'}));assert health['status']==200
put(base/'binding.json',{'pointer':read(pointer),'binding':binding,'service_entry':'actual service.service application + RAG_ASK','profile':profile,'public_scope':list(t.public_scope),'data_path':baseline['release']['data_path'],'application_prepare_seconds':application_seconds,'profile_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'search_selection_fingerprint':pipeline.store.selection.fingerprint,'model_policy_sha256':sha(C/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'genos_executed':False})
from cm_authorization import install
cm_context=install(t,pkg,f,frozen_case,baseline)
gateway=importlib.import_module(pkg+'.gateway')

import httpx
original_client=httpx.Client
calls=[];generations=[];active=[];spans=[]
started=time.monotonic()
def gz(p,v):
 ref=write_raw_json(p,v)
 write_summary(p.with_suffix('.reference.json'),ref)
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
import lawrag.research
lawrag.research.__path__.insert(0,str(C/'02_BACKEND/lawrag/research'))
from lawrag.research.experiment_client import ExperimentClient,ExperimentProviderError,ExperimentFormatError,ExperimentTransportError
local_transport=importlib.import_module(pkg+'.local_gemma')
errors=importlib.import_module(pkg+'.errors')
audited=ExperimentClient(ROOT,base/'experiment-client',max_calls=40,max_repairs=0)
from lawrag.research.openrouter_legal_adapter import send_reserved
def reserved_send(*,body,ticket):
 return send_reserved(audited,body=body,ticket=ticket,phase=active[-1] if active else 'request',error_module=errors,request_encoder=local_transport.provider_request)
t.send_once=reserved_send
from lawrag.core import request_deadline as deadline_transport
original_post=deadline_transport.post_json
def recorded_post(url,**kwargs):
  guard.check()
  if not str(url).startswith(t.policy['endpoint']+'/chat/completions'):raise RuntimeError('Unexpected external endpoint')
  n=len(calls)+1;out=base/'raw'/f'call-{n:03d}';out.mkdir(parents=True,exist_ok=False)
  payload=kwargs['json_body'];assert payload['model']=='qwen/qwen3.8-27b'
  assert not any(k in payload for k in ('max_tokens','max_completion_tokens','max_output_tokens'))
  if active and active[-1].startswith('memory-assess'):
   ce=importlib.import_module(pkg+'.completion_execution');v8=importlib.import_module(pkg+'.completion_v8')
   system=payload['messages'][0]['content']
   assert system.count(ce.MODERN_ASSESS_PROMPT)==1 and system.count(v8.PROMPT)==1
  row={'number':n,'stage':active[-1] if active else None,'provider':payload['provider'],'status':'started'};calls.append(row)
  gz(out/'request.json.gz',payload);put(out/'started.json',row)
  print('MODEL',case_id,n,row['stage'],payload['provider']['only'],flush=True);begin=time.monotonic()
  try:
   response=original_post(url,**kwargs)
   try:raw=response.json()
   except ValueError:raw={'non_json_body':response.text}
   gz(out/'response.json.gz',raw);row.update(status='responded',http_status=response.status_code,usage=raw.get('usage'),actual_provider=raw.get('provider'))
   row['transport_diagnostics']=response.extensions.get('absolute_deadline',{})
   return response
  except Exception as exc:
   row.update(status='unknown',error_type=type(exc).__name__,transport_diagnostics=getattr(exc,'diagnostics',{}))
   if hasattr(exc,'partial_body'):
    import base64
    gz(out/'partial-response.json.gz',{'body_base64':base64.b64encode(exc.partial_body).decode('ascii'),'diagnostics':getattr(exc,'diagnostics',{})})
   raise
  finally:row['seconds']=time.monotonic()-begin;put(out/'finished.json',row)
deadline_transport.post_json=recorded_post
original_generate=gateway.ModelGateway.generate
law_navigation=importlib.import_module(pkg+'.law_navigation')
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
result={'case_id':case_id,'quality_certified':False,'environment':'current MAIN129 base plus frozen error-repair candidate through native service; not promoted','stronger_model_comparison':False}
try:
 response=asyncio.run(cm_context(actual.service,deepcopy(frozen_case['request'])));put(base/'response.json',response)
 body=response.get('body') or {};result.update(http_status=response['status'],status=body.get('status'),run_id=body.get('run_id'))
 answer=body.get('answer',{});(base/'answer.txt').write_text(answer.get('text','') if isinstance(answer,dict) else str(answer))
 if response['status']==200 and answer:
  before=len(calls)
  duplicate=asyncio.run(cm_context(actual.service,deepcopy(frozen_case['request'])))
  put(base/'duplicate.json',{'http_status':duplicate['status'],'same_answer':duplicate.get('body',{}).get('answer')==answer,'extra_model_calls':len(calls)-before})
except Exception as exc:
 result.update(error_type=type(exc).__name__,error=str(exc));(base/'error.txt').write_text(traceback.format_exc())
finally:
 put(base/'calls.json',calls);put(base/'generations.json',generations)
 if last_state:put(base/'investigation-state.json',read(last_state))
 guard.done.set()
 guard.thread.join(timeout=3)
 result.update(model_calls=len(calls),seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
  journals=[str(p.relative_to(ROOT)) for p in runtime.rglob('journal.sqlite')],active_pointer_unchanged=sha(pointer)==f['pointer_sha256'])
 put(base/'result.json',result);print('LIVE_DONE',case_id,result,flush=True)
pipeline.store.close();put(base/'cleanup.json',{'store_closed':True});sys.stdout.flush()
