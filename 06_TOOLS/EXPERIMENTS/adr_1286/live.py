"""Fixed baseline and three independent scenario branches through frozen native service; immutable raw audit."""
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
case_id=sys.argv[1];assert case_id in [c['id'] for c in read(DES/'cases.json')]
frozen_case=next(c for c in read(DES/'cases.json') if c['id']==case_id)
preflight='--preflight' in sys.argv
base=ART/('preflight' if preflight else 'live')/case_id
if (base/'dispatch.json').exists():raise RuntimeError('Already dispatched; no automatic repeat')
base.mkdir(parents=True,exist_ok=False);runtime=base/'runtime'
assert not os.environ.get('DP')
os.environ.update(GENOS_RUNTIME_DIR=str(runtime),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(ROOT))
for n in ('TEAM_ID','AD_WORKSPACE','GENOS_STATE_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','GENOS_SYSTEM_LOG_DIR'):os.environ.pop(n,None)
from resource_guard import Guard
guard=Guard(base);guard.start()
from pinned_imports import install as pin_imports
pin_imports(ART/'transport')
import lawrag,lawrag.core,lawrag.research
for package,relative in ((lawrag,'02_BACKEND/lawrag'),(lawrag.core,'02_BACKEND/lawrag/core'),(lawrag.research,'02_BACKEND/lawrag/research')):
 package.__path__.append(str(C/relative))
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT),str(ROOT/'02_BACKEND')]
import faulthandler
faulthandler.enable()
from types import SimpleNamespace
from semantic_runtime.app import create_app
from semantic_runtime.unit_fulltext import UnitFulltextIndex
from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport
from semantic_runtime.legal_agent.errors import ContractError
from fastapi.testclient import TestClient
source=read(DES/'source.json');data=ROOT/source['data_path'];source_manifest=source['source_manifest']
allowed=set(source['document_ids']);expected=frozen_case['request']['json']['question'];permitted_questions={expected,'검토 다시 하기','검토 상태 보기','가정 비교','가정의 의미 재검토'};host_derived_questions=set();derivations=[];auth_hash=sha(DES/'authorization.json')
class Authorized(LocalQwen38Transport):
 @property
 def public_scope(self):return tuple(sorted(allowed))
 def authorize(self,query,request,manifest,*,public_question):
  scope=set(query['scope']['document_version_ids'])
  if not public_question or request.get('question',query.get('question')) not in permitted_questions|host_derived_questions or not scope or not scope<=allowed:
   raise ContractError('Exact synthetic question/source grant mismatch')
  assert sha(DES/'authorization.json')==auth_hash and sha(self.policy_path)==self.policy_hash
  assert manifest['generation_id']==source_manifest['generation_id'] and manifest['store_sha256']==source_manifest['store_sha256'] and manifest['export_allowed'] is False
  return {'kind':'USER_AUTHORIZED_SYNTHETIC_LOOP_RECOVERY','authorization_sha256':auth_hash,'policy_sha256':self.policy_hash,'source_manifest_sha256':sha(data/'manifest.json'),'public_question_asserted':True,'scope_document_ids':sorted(scope)}
t=Authorized(C,ROOT)
from contextlib import contextmanager
from semantic_runtime.legal_agent.unified_rag import UnifiedRag
from authorization import derive
original_open=UnifiedRag.open
@contextmanager
def approved_open(host,state,principal,body):
 effective=derive(body,state,permitted_questions,allowed)
 assert effective==host.retrieval_question(state)
 host_derived_questions.add(effective)
 derivations.append({'request_id':body['request_id'],'original_question':body['question'],'effective_question':effective,'facts':deepcopy(state['facts']),'scope':state['document_ids'],'source':'validated core command -> UnifiedRag.open; experiment authorization only'})
 with original_open(host,state,principal,body) as execution:yield execution
UnifiedRag.open=approved_open
profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile.update(model_binding=t.binding,max_output_tokens=t.policy['max_output_tokens'])
profile['candidate_navigation'].update(ontology_enabled=True,ontology_direct_assessment=True,ontology_context={'mode':'DB'})
os.environ['GENOS_RAG_ONTOLOGY_CONFIG']=str(DES/'ontology-config.json')
binding={'mode':'experiment-native','generation':132,'experiment_candidate':'ADR1286/verified','main_promoted':False,'code_revision':f['candidate_revision'],'synthetic_source_generation':source_manifest['generation_id']}
application_started=time.monotonic()
app=create_app(base,data,contracts_root=C,release=binding,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=t,workspace_root=ROOT,runtime_root=runtime,memory_identity=lambda _:{'user_id':'authorized-synthetic-experiment','team_id':'risk_team','document_ids':sorted(allowed)})
pipeline=app.state.pipeline
pipeline.term_agent.unit_fulltext=UnitFulltextIndex(ROOT/source['index_path'],read(data/'navigation/manifest.json'))
application_seconds=time.monotonic()-application_started
profile=pipeline.term_agent.profile;pkg='semantic_runtime.legal_agent'
assert Path(pipeline.contracts.root)==C and Path(importlib.import_module(pkg+'.requirement_coverage').__file__).is_relative_to(C)
assert profile['candidate_navigation']['requirement_coverage'] is True and profile['candidate_navigation']['source_goal_control'] is True and profile['candidate_navigation']['supervisor_mode']=='enforce'
assert profile['answer_presentation']=='accepted-content-v1'
assert profile['max_model_attempts']==40 and profile['max_tool_actions']==1024 and profile['wall_seconds']==1800 and profile['max_output_tokens'] is None
client=TestClient(app,raise_server_exceptions=False);client.__enter__()
assert client.get('/health').status_code==200
async def native_service(ignored,request):
 assert request['json'] in authorized_requests
 reply=client.post('/v1/rag/ask',json=deepcopy(request['json']))
 return {'status':reply.status_code,'body':reply.json()}
authorized_requests=[deepcopy(frozen_case['request']['json'])]
actual=SimpleNamespace(service=native_service)
async def cm_context(service,request):return await service({},request)
put(base/'binding.json',{'pointer':read(pointer),'binding':binding,'service_entry':'native FastAPI /v1/rag/ask, full current pipeline; synthetic original corpus','profile':profile,'public_scope':list(t.public_scope),'data_path':source['data_path'],'application_prepare_seconds':application_seconds,'profile_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'search_selection_fingerprint':pipeline.store.selection.fingerprint,'model_policy_sha256':sha(C/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'genos_executed':False})
if preflight:
 query={'question':expected,'scope':{'document_version_ids':sorted(allowed)}}
 request=deepcopy(frozen_case['request']['json'])
 from authorization import self_test
 assert self_test()==5
 receipt=t.authorize(query,request,source_manifest,public_question=True)
 for run_id in ('first-context','fresh-repost-context'):
  context=SimpleNamespace(run_id=run_id,query=query,request=request,binding={'external_authorization':receipt,'model':t.binding,'generation_id':source_manifest['generation_id'],'store_sha256':source_manifest['store_sha256'],'export_allowed':False})
  t.validate_authorization(context)
 for changes in ({'question':'unauthorized different question'},):
  try:t.authorize(query,{**request,**changes},source_manifest,public_question=True)
  except ContractError:pass
  else:raise AssertionError('Grant accepted unauthorized request')
 guard.done.set();guard.thread.join(timeout=3);client.__exit__(None,None,None)
 put(base/'result.json',{'ready':True,'authorization_self_tests':5,'authorization_roundtrips':2,'negative_grants':1,'actual_model_calls':0,'profile_unchanged':True});print('PREFLIGHT_READY',flush=True);raise SystemExit(0)
gateway=importlib.import_module(pkg+'.gateway')

import httpx
original_client=httpx.Client
calls=[];generations=[];active=[];spans=[];injections=[];current_turn=1
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
audited=ExperimentClient(ROOT,base/'experiment-client',max_calls=20,max_repairs=0)
from lawrag.research.openrouter_legal_adapter import send_reserved
assert Path(sys.modules[ExperimentClient.__module__].__file__).is_relative_to(ART/'transport')
assert Path(sys.modules[send_reserved.__module__].__file__).is_relative_to(ART/'transport')
def reserved_send(*,body,ticket):
 from pinned_imports import verify_loaded
 verify_loaded(ART/'transport')
 envelope=send_reserved(audited,body=body,ticket=ticket,phase=active[-1] if active else 'request',error_module=errors,request_encoder=local_transport.provider_request)
 return envelope
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
  row={'number':n,'turn':current_turn,'stage':active[-1] if active else None,'provider':payload['provider'],'status':'started'};calls.append(row)
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
 number=len(generations)+1;stage=view.get('source_stage',phase);row={'number':number,'turn':current_turn,'stage':stage};generations.append(row);active.append(stage)
 gz(base/'canonical'/f'{number:03d}.json.gz',{'phase':phase,'view':view,'schema':self.protocol.schema(schema_name)})
 try:
  value=original_generate(self,phase,view,schema_name,**kwargs);gz(base/'canonical'/f'{number:03d}-output.json.gz',value);row['status']='accepted';return value
 except Exception as exc:row.update(status='rejected',error_type=type(exc).__name__,error=str(exc));raise
 finally:active.pop();put(base/'canonical'/f'{number:03d}-summary.json',row)
gateway.ModelGateway.generate=generate
from pinned_imports import verify_loaded
put(base/'transport-origin.json',verify_loaded(ART/'transport'))
put(base/'dispatch.json',{'case_id':case_id,'code':f['candidate_revision'],'physical_limit':20,'same_case_retry':False,'provider_policy_sha256':t.routing_hash,'new_model_calls_before_dispatch':0})
put(base/'request.json',frozen_case['request'])
put(base/'product-imports.json',{n:{'path':str(Path(m.__file__).resolve()),'sha256':sha(Path(m.__file__))} for n,m in sys.modules.copy().items() if n.startswith('semantic_runtime.') and getattr(m,'__file__',None)})
result={'case_id':case_id,'quality_certified':False,'environment':'current full product loop via native API with three fixed synthetic original clauses; not promoted','stronger_model_comparison':False}
turns=[]
def dispatch(label,request):
 global current_turn
 current_turn=label;authorized_requests.append(deepcopy(request))
 put(base/(label+'-request.json'),request)
 before=len(calls);response=asyncio.run(cm_context(actual.service,{'API_TYPE':'RAG_ASK','json':request}))
 gz(base/(label+'-response.json.gz'),response)
 row={'label':label,'http_status':response['status'],'physical_calls':len(calls)-before,'request_id':request['request_id']}
 turns.append(row)
 body=response.get('body') or {};answer=body.get('answer') or {}
 if isinstance(answer,dict):(base/(label+'-answer.txt')).write_text(answer.get('text',''))
 if response['status'] in (200,422,502,504):
  before=len(calls);duplicate=asyncio.run(cm_context(actual.service,{'API_TYPE':'RAG_ASK','json':request}))
  row['duplicate']={'http_status':duplicate['status'],'same_answer':duplicate.get('body',{}).get('answer')==answer,'extra_model_calls':len(calls)-before}
  assert len(calls)==before and duplicate['status']==response['status'],'duplicate made a call or changed status'
  if response['status']==200:assert row['duplicate']['same_answer']
 put(base/(label+'-turn.json'),row)
 return response

def action_request(view,kind,ident,inputs=None):
 action=next((a for a in view['actions'] if a['kind']==kind and a['enabled']),None)
 if action is None:return None
 return {**frozen_case['request']['json'],'question':action['label'],'request_id':'adr1286-'+ident,
  'use_llm':kind not in ('VIEW_REVIEW','WHAT_IF'),
  'review_action':{'schema_version':'review-action-v1','action_id':action['id'],'view_hash':view['content_sha256'],
   'case_id':view['case']['question_id'],'revision':view['case']['revision'],'operation_id':'adr1286-'+ident,'input':inputs or {}}}
def stopped():return any(c['status'] in ('unknown','started') or c.get('http_status',200)>=400 for c in calls)
try:
 response=dispatch('initial',deepcopy(frozen_case['request']['json']));put(base/'response.json',response)
 result['http_status']=response['status'];body=response.get('body') or {};view=body.get('assembly',{}).get('term_agent',{}).get('review_explanation')
 if response['status']==200 and view and not stopped():
  if any(i['review']=='INCOMPLETE' for i in view['items']):
   request=action_request(view,'REVIEW_AGAIN','explicit-review')
   if request:
    rereview=dispatch('rereview',request)
    if rereview['status']==200:
     body=rereview['body'];view=body['assembly']['term_agent']['review_explanation']
    else:view=None
  if view and not stopped():
   baseline_body=deepcopy(body);baseline_view=deepcopy(view)
   request=action_request(view,'VIEW_REVIEW','view-status')
   shown=dispatch('view',request)
   if shown['status']!=200:raise RuntimeError('state view failed')
   from semantic_runtime.legal_agent.scenario_facts import typed_value
   action=next(a for a in view['actions'] if a['kind']=='WHAT_IF')
   matching=[r['id'] for r in action['fact_options'] if typed_value(r['value'],action['fields']['cost'])=={'type':'money','unit':'KRW','value':'1380000'}]
   if len(matching)!=1:raise RuntimeError('Unique explicit cost fact binding unavailable; no guessing')
   fact_bindings={'cost':matching}
   put(base/'fact-binding.json',{'bindings':fact_bindings,'options':action['fact_options'],'rule':'One exact requested baseline amount; no alias guessing'})
   for label,kind,key,value in [('high','FACT','cost','1725000'),('low','FACT','cost','735000'),('rule','RULE','limit','2450000')]:
    request=action_request(view,'WHAT_IF','numeric-'+label,{'kind':kind,'changes':{key:{'type':'money','unit':'KRW','value':value}},'bindings':fact_bindings})
    if request:
     comparison=dispatch(label,request)
     assert turns[-1]['physical_calls']==0,'numeric action called model'
     if comparison['status']!=200:raise RuntimeError('numeric action failed: '+label)
    else:result.setdefault('not_tested',[]).append(label)
   result['branches']={}
   for label,kind,key,amount in [('low','FACT','cost','735000'),('high','FACT','cost','1725000'),('rule','RULE','limit','2450000')]:
    if stopped():
     result.setdefault('not_tested',[]).append('semantic-'+label);continue
    request=action_request(view,'SCENARIO_REVIEW','semantic-'+label,{'kind':kind,'changes':{key:{'type':'money','unit':'KRW','value':amount}},'bindings':fact_bindings})
    branch=dispatch('semantic-'+label,request)
    if branch['status']==200:
     bb=branch['body'];result['branches'][label]={'different_goal':bb.get('goal_id')!=baseline_body.get('goal_id'),'hypothetical':bool(bb.get('assembly',{}).get('term_agent',{}).get('scenario_context')),'claims':len(bb.get('answer',{}).get('claims',[]))}
    elif branch['status']>=400 and branch['status']!=422:break
   # The old action targets the actual baseline even after a new hypothetical case is current.
   request=action_request(baseline_view,'VIEW_REVIEW','baseline-after-branch')
   before=len(calls);restored=dispatch('baseline-after',request)
   result['baseline_preserved']=restored['status']==200 and all(restored['body'].get('answer',{}).get(k)==baseline_body.get('answer',{}).get(k) for k in ('text','claims','evidence')) and len(calls)==before
except Exception as exc:
 result.update(error_type=type(exc).__name__,error=str(exc));(base/'error.txt').write_text(traceback.format_exc())
finally:
 gz(base/'authorized-derivations.json.gz',derivations)
 put(base/'calls.json',calls);put(base/'generations.json',generations);put(base/'turns.json',turns)
 if last_state:put(base/'investigation-state.json',read(last_state))
 guard.done.set();guard.thread.join(timeout=3)
 result.update(model_calls=len(calls),seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
  journals=[str(p.relative_to(ROOT)) for p in runtime.rglob('journal.sqlite')],active_pointer_unchanged=sha(pointer)==f['pointer_sha256'],turns=turns)
 put(base/'result.json',result);print('LIVE_DONE',case_id,result,flush=True)
client.__exit__(None,None,None);put(base/'cleanup.json',{'store_closed':True});sys.stdout.flush()
