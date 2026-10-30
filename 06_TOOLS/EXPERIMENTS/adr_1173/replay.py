"""Exact ADR1167 repaired supervisor on MAIN112; isolated native HTTP, audited transport."""
from common import *
import asyncio,gzip,importlib,jsonschema,os,resource,sys,time,traceback,threading
from copy import deepcopy
sys.dont_write_bytecode=True
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
f=read(DES/'freeze.json')
candidate=read(ROOT/read(DES/'candidate.json')['root']/'candidate.json');revision=candidate['revisions'][0];code=ROOT/read(DES/'candidate.json')['root']/'revisions'/revision['revision_id']/'snapshot'
f['code_root']=str(code.relative_to(ROOT));f['files']={str((ROOT/r['frozen_path']).relative_to(code)):r['snapshot_sha256'] for r in revision['files']}
baseline=read(DES/'baseline.json');C=ROOT/f['code_root'];pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';arm='executed'
assert sha(pointer)==f['pointer_sha256']
for name,h in f['inputs'].items():assert sha(ROOT/name)==h,name
# Baseline code frozen; replay runner recorded separately.
for name,h in f['files'].items():assert sha(C/name)==h,name
for name in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_IMPLEMENTATION','LEGAL_AGENT_PROFILE','GENOS_RAG_MAX_MODEL_ATTEMPTS','GENOS_RAG_MAX_TOOL_ACTIONS','GENOS_RAG_WALL_SECONDS','GENOS_RAG_SEARCH_ROUNDS','GENOS_RAG_ASSESSMENT_REENTRY_LIMIT','GENOS_ONTOLOGY_ENABLED'):
 if os.environ.get(name):raise RuntimeError('Unexpected runtime override: '+name)
setup='--setup-only' in sys.argv
preflight='--preflight' in sys.argv
case_id=next((x for x in sys.argv[1:] if x.startswith('cm-')),'cm-001')
frozen_case=next(c for c in read(DES/'cases.json') if c['id']==case_id)
repeat=int(sys.argv[-1]);base=ART/'baseline-replay-v5'/(case_id+'-r'+str(repeat))
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
put(base/'binding.json',{'pointer':read(pointer),'binding':binding,'app_injected':True,'service_entry':'semantic_runtime.app.create_app /v1/rag/ask','profile':profile,'public_scope':list(t.public_scope),'data_path':baseline['release']['data_path'],'application_prepare_seconds':application_seconds,'profile_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'search_selection_fingerprint':pipeline.store.selection.fingerprint,'model_policy_sha256':sha(C/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'transport_instrumentation':'ExperimentClient only; native candidate HTTP API; not active MAIN','genos_executed':False})
from cm_authorization import install
cm_context=install(t,pkg,f,frozen_case,baseline)
if setup:
 print('SETUP',flush=True)
 pipeline.store.close();sys.stdout.flush();os._exit(0)


# Replay exact stored wire outputs through current gateway/schema, choose_read/gate and native executor.
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1169-supervisor-cm3-memory-reclaimed/artifacts/run-001'/case_id
probe=ROOT/'04_EXPERIMENTS/ADR/ADR-1172-qwen38-provider-switch/artifacts/run-001'/(case_id+'-r'+str(repeat))
number=0;target=8 if case_id=='cm-001' else 6;rows=[];frames=[]
original=gateway.ModelGateway.generate
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from semantic_runtime.legal_agent import law_navigation
old_request=law_navigation.Investigation.request_decision
active={}
def request(inv,data,actions,phase):
 active.update(inv=inv,data=data,actions=actions)
 try:return old_request(inv,data,actions,phase)
 finally:
  put(base/'investigation-final.json',inv.p)
law_navigation.Investigation.request_decision=request
def generate(self,phase,view,schema_name,**kw):
 global number
 number+=1;active['view']=view;active['phase']=view.get('source_stage',phase)
 frames.append({'number':number,'phase':active['phase']})
 try:return original(self,phase,view,schema_name,**kw)
 except Exception as e:
  frames[-1].update(error_type=type(e).__name__,error=str(e));raise
 finally:put(base/'frames.json',frames)
gateway.ModelGateway.generate=generate
sent=0;id_map={}
def send(*,body,ticket):
 global sent
 sent+=1
 if number>target:raise errors.TransportError('Replay boundary after target; no additional output supplied',retryable=False)
 old=json.load(gzip.open(parent/'canonical'/f'{number:03d}.json.gz','rt'))
 expected=old['view'].get('source_stage',old['phase'])
 if active['phase']!=expected:raise errors.ContractError('Replay phase divergence:'+active['phase']+' != '+expected)
 saved=read(probe/'output.json') if number==target else json.load(gzip.open(parent/'canonical'/f'{number:03d}-output.json.gz','rt'))
 if '-read-choice' in active['phase'] and saved.get('choice') not in ('NEXT_READ_CANDIDATES','PREVIOUS_READ_CANDIDATES'):
  saved.setdefault('source_targets',[]);saved.setdefault('source_goal_exclusions',[])
 # Bind stored native IDs to current request-local handles. No semantic edit.
 remap=id_map
 for prior in old['view'].get('read_judgments',{}).get('current_originals',[]):
  matches=[r for r in active['view'].get('read_judgments',{}).get('current_originals',[]) if (r['source_id'],r['document_id'],r['material'])==(prior['source_id'],prior['document_id'],prior['material'])]
  if len(matches)==1:remap[prior['id']]=matches[0]['id']
 refs=NavigationReferences(active['view']);saved=refs._map(saved,remap)
 wire=refs.view(saved) if active['view'].get('input_projection')=='compact-selection-source-v3' else saved
 if number==target:
  put(base/'target-state.json',active['inv'].p);put(base/'target-data.json',active['data']);put(base/'target-actions.json',active['actions']);put(base/'target-view.json',active['view'])
 raw=read(next((parent/'raw').glob(f'call-{number:03d}-*/response.json')))
 raw['choices'][0]['message']['content']=json.dumps(wire,ensure_ascii=False)
 rows.append({'number':number,'target_injected':number==target,'phase':active['phase']})
 return {'status_code':200,'body_json':raw,'acceptance':'ACCEPTED','body_text':None,'retry_after':None}
t.send_once=send
response=asyncio.run(cm_context(actual.service,deepcopy(frozen_case['request'])))
put(base/'response.json',response)
put(base/'result.json',{'case_id':case_id,'repeat':repeat,'target_reached':sent>=target,'stored_responses':rows,'new_model_calls':0,'reconstruction':'Fresh native request with stored canonical responses re-encoded into current handle map; source/data/questions unchanged. Empty source target fields added to1170 prelude. All validators preserved.','frames':frames,'http_status':response['status']})
print('REPLAY',case_id,repeat,response['status'],'sent',sent,flush=True)
pipeline.store.close();sys.stdout.flush();os._exit(0)
