"""Frozen public multi-turn questions via candidate chat request adapter; native sequential API turns."""
from common import *
import os,time,importlib,importlib.util,traceback,gzip,resource
from copy import deepcopy
from contextlib import nullcontext
os.environ.update(OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONDONTWRITEBYTECODE='1',AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',LAWRAG_WORKSPACE_ROOT=str(ROOT))
for n in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED','TEAM_ID','AD_WORKSPACE','GENOS_STATE_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR'):os.environ.pop(n,None)
admission='--admission' in sys.argv
case_id,arm=sys.argv[1:3];preflight='--preflight' in sys.argv;replay=any(x in sys.argv for x in ('--grant-replay','--grant-replay-after-admission'));replay_sends=[];second_admission='--grant-replay-after-admission' in sys.argv
assert arm=='main143'
case=next(c for c in read(DES/'live-cases.json') if c['id']==case_id)
assert arm in case['arms']
case['question']=case['steps'][0]['mode']+': '+case['steps'][0]['question']
action_branch='--structured' in sys.argv
session_name=case_id+'-'+arm
base=ART/('public-ready' if preflight else 'public-admission' if admission else 'public-live')/(session_name+('-action' if action_branch else ''));base.mkdir(parents=True,exist_ok=False)
runtime=base/'runtime';os.environ['GENOS_RUNTIME_DIR']=str(runtime)
import shutil
seed=ART/'action-seed'
if action_branch:
 if (ART/'STOP_EXTERNAL.json').exists():raise RuntimeError('Unknown outcome prevents conditional turn')
 if not (seed/'action-request.json').is_file():raise RuntimeError('No previously offered and bound action')
 shutil.copytree(seed/'runtime',runtime,symlinks=True)
 for name,h in read(seed/'files.json').items():assert sha(runtime/name)==h
candidate=read(DES/'candidate-main143.json');C=ROOT/candidate['code_root'];selected_code=selected()
assert all(sha(C/n)==h for n,h in candidate['selected_files'].items())
if not (preflight or replay):
 f=read(DES/'freeze-public.json')
 for n,h in f['files'].items():assert sha(ROOT/n)==h,n
 if (ART/'STOP_EXTERNAL.json').exists():raise RuntimeError('Frozen stop condition prevents new physical sends')
from resource_guard import Guard
guard=Guard(base);guard.start()
from pinned_imports import install,verify_loaded
install(ART/'transport')
import lawrag,lawrag.core,lawrag.research
for pkg,path in [(lawrag,'02_BACKEND/lawrag'),(lawrag.core,'02_BACKEND/lawrag/core'),(lawrag.research,'02_BACKEND/lawrag/research')]:
 pkg.__path__.extend([str(C/path),str(ROOT/path)])
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT)]
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
from experiment_json import write_raw_json,write_summary
def gz(p,v):
 ref=write_raw_json(p,v);write_summary(Path(str(p)+'.ref.json'),ref)
gold_context=None;sql_request=None;sql_transport=None;store=None;app=None;client=None
prepare_start=time.monotonic()
try:
 data=ROOT/read(DES/'baseline.json')['release']['data_path']
 source_manifest=read(data/'manifest.json')
 assert sha(data/'store.sqlite')==source_manifest['store_sha256']
 profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
 assert profile['candidate_navigation']['ontology_enabled'] is False
 # No Oracle connector is imported or opened in this experiment.
 if 'oracledb' in sys.modules:raise RuntimeError('SQLite experiment cannot load Oracle driver')
 from semantic_runtime.app import create_app
 from semantic_runtime.provider import Haiku
 from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport,provider_request
 from semantic_runtime.legal_agent import gateway,errors,workflow_execution
 from fastapi.testclient import TestClient
 auth_hash=sha(DES/'authorization.json');allowed=set(case['document_ids']);host_derived_questions=set();derivations=[]
 class Authorized(LocalQwen38Transport):
  @property
  def public_scope(self):return tuple(sorted(allowed))
  def authorize_workflow(self,request,binding):
   assert request['question'] in (case['question'],case['question'].removeprefix('대사:').strip())
   receipt=super().authorize_workflow(request,binding)
   return {**receipt,'experiment_authorization':auth_hash}
  def authorize(self,query,request,manifest,*,public_question):
   assert sha(DES/'authorization.json')==auth_hash and sha(self.grant_path)==self.grant_hash and sha(self.policy_path)==self.policy_hash
   scope=set(query['scope']['document_version_ids'])
   assert scope and scope<=allowed and scope<=set(self.grant['workflow_authorization']['document_ids'])
   assert manifest['generation_id']==source_manifest['generation_id'] and manifest['store_sha256']==source_manifest['store_sha256'] and manifest['export_allowed'] is False
   parent=workflow_execution.authorization()
   if parent is not None:
    assert parent['experiment_authorization']==auth_hash and parent['kind']=='USER_AUTHORIZED_WORKFLOW'
    return {**parent,'scope_document_ids':sorted(scope)}
   permitted={case['question'],case['question'].split(': ',1)[-1]}|host_derived_questions
   if action_branch:
    offered_request=read(seed/'action-request.json')
    originating=read(seed/'origin.json')
    assert current_body.get('review_action')==offered_request['review_action']
    permitted.update([originating['sent_question'],originating['sent_question'].split(': ',1)[-1]])
   if request.get('question',query['question']) not in permitted:raise errors.ContractError('Frozen integration question grant mismatch')
   return {'kind':'USER_AUTHORIZED_INTEGRATION_PROBE','authorization_sha256':auth_hash,'policy_sha256':self.policy_hash,'grant_sha256':self.grant_hash,'public_question_asserted':scope<=set(self.grant['public_document_ids']),'scope_document_ids':sorted(scope)}
 t=Authorized(C,ROOT)
 from semantic_runtime.legal_agent.provider_routing import validate_policy,route,switch
 t.routing_path=DES/'provider-policy.json';t.provider_policy=validate_policy(read(t.routing_path));t.routing_hash=sha(t.routing_path)
 t.binding={**t.binding,'adapter_version':'openrouter-local-public-v3:'+t.routing_hash}
 profile.update(model_binding=t.binding,max_output_tokens=None)
 assert len(t.provider_policy['providers'])==2
 put(base/'routing-binding.json',{'policy_sha256':t.routing_hash,'provider':route(t.provider_policy['providers'][0]),'max_provider_switches':t.provider_policy['max_provider_switches'],'frozen_candidate':True})
 from contextlib import contextmanager
 from semantic_runtime.legal_agent.unified_rag import UnifiedRag
 original_open=UnifiedRag.open
 @contextmanager
 def approved_open(host,state,principal,body):
  # Product maps the public session to an authenticated internal case.
  linked=host.shortcut.investigation(host.active_case,principal,'adr1380-'+session_name)
  assert linked['id']==host.active_case
  assert body['request_id']==current_body['request_id']
  permitted_body_questions={case['question']}
  if action_branch:
   origin=read(seed/'origin.json')['sent_question']
   permitted_body_questions.update([state['task'],origin,origin.split(': ',1)[-1]])
  assert body['question'] in permitted_body_questions
  assert state['document_ids'] and set(state['document_ids'])<=allowed
  effective=host.retrieval_question(state)
  assert effective==host.retrieval_question(state)
  session=host.model.ensure()
  receipt=session.context.binding['external_authorization']
  assert receipt.get('authorization_sha256',receipt.get('experiment_authorization'))==auth_hash and set(receipt['scope_document_ids'])<=allowed
  host_derived_questions.add(effective)
  derivations.append({'original_question':body['question'],'effective_question':effective,'task':state['task'],'facts':deepcopy(state['facts']),'document_ids':state['document_ids'],'request_id':body['request_id'],'run_id':session.context.run_id,'source_category':state.get('source_category'),'search_scope':state.get('search_scope'),'active_case':host.active_case,'product_state_rewritten':False})
  put(base/'authorized-derivations.json',derivations)
  with original_open(host,state,principal,body) as execution:yield execution
 UnifiedRag.open=approved_open
 calls=[];generations=[];active=[];model_started=False
 from lawrag.research.experiment_client import ExperimentClient
 from lawrag.research.openrouter_legal_adapter import send_reserved
 from lawrag.core import request_deadline
 verify_loaded(ART/'transport')
 audited=ExperimentClient(ROOT,base/'experiment-client',max_calls=40*len(case['steps']),max_repairs=0,provider_policy=DES/'provider-policy.json')
 def send(*,body,ticket):
  if replay:
   replay_sends.append({'number':len(replay_sends)+1,'stage':active[-1] if active else None})
   put(base/'replay-sends.json',replay_sends)
   if len(replay_sends)==1:
    original=ROOT/'04_EXPERIMENTS/ADR/ADR-1294-local-ontology-ab-memory-map/artifacts/live/ontology-365-baseline/raw/call-001/response.json.gz'
    with gzip.open(original,'rt') as f:raw=json.load(f)
    put(base/'replayed-response.json',{'path':str(original.relative_to(ROOT)),'sha256':sha(original),'physical_calls':0})
    return {'status_code':200,'body_json':raw}
   put(base/'replay-boundary.json',{'second_gateway_authorization_passed':True,'derivations':len(derivations),'physical_calls':0})
   raise errors.ContractError('REPLAY_BOUNDARY_REACHED_NO_PHYSICAL_SEND')
  if preflight or admission:raise RuntimeError('ADMISSION_BOUNDARY_NO_SEND')
  if (ART/'STOP_EXTERNAL.json').exists():raise errors.ContractError('Global physical outcome stop')
  verify_loaded(ART/'transport')
  total=sum(len(read(p)) for p in (ART/'public-live').glob('*/calls.json'))
  if total>=120:raise errors.BudgetExhausted('Global experiment120 physical cap')
  return send_reserved(audited,body=body,ticket=ticket,phase=active[-1] if active else 'request',error_module=errors,request_encoder=provider_request)
 t.send_once=send
 original_post=request_deadline.post_json
 def post(url,**kw):
  guard.check();payload=kw['json_body'];assert payload['model']=='qwen/qwen3.8-27b'
  assert payload['provider'] in [route(p) for p in t.provider_policy['providers']] and payload['reasoning']=={'effort':'none'}
  assert not any(k in payload for k in ('max_tokens','max_output_tokens','max_completion_tokens'))
  n=len(calls)+1;out=base/'raw'/f'call-{n:03d}';out.mkdir(parents=True,exist_ok=False)
  row={'number':n,'stage':active[-1] if active else None,'status':'started','provider':payload['provider']};calls.append(row)
  put(base/'calls.json',calls);gz(out/'request.json.gz',payload);begin=time.monotonic()
  print('MODEL',case_id,arm,n,row['stage'],flush=True)
  try:
   response=original_post(url,**kw)
   try:body=response.json()
   except ValueError:body={'non_json_body':response.text}
   gz(out/'response.json.gz',body)
   row.update(status='unknown' if response.status_code>=500 else 'responded',http_status=response.status_code,usage=body.get('usage'),actual_provider=body.get('provider'),actual_model=body.get('model'),transport_diagnostics=response.extensions.get('absolute_deadline',{}))
   if row['status']=='unknown':
    put(ART/'STOP_EXTERNAL.json',{'cell':base.name,'call':n,'reason':'remote 5xx; no resends'})
   return response
  except Exception as exc:
   row.update(status='unknown',error_type=type(exc).__name__,transport_diagnostics=getattr(exc,'diagnostics',{}))
   if hasattr(exc,'partial_body'):
    import base64
    gz(out/'partial.json.gz',{'body_base64':base64.b64encode(exc.partial_body).decode(),'diagnostics':getattr(exc,'diagnostics',{})})
   put(ART/'STOP_EXTERNAL.json',{'cell':base.name,'call':n,'reason':'Unknown physical provider outcome','no_automatic_retry':True})
   raise
  finally:row['seconds']=time.monotonic()-begin;put(out/'finished.json',row);put(base/'calls.json',calls)
 request_deadline.post_json=post
 original_generate=gateway.ModelGateway.generate
 def generate(self,phase,view,schema_name,**kwargs):
  number=len(generations)+1;stage=view.get('source_stage',phase);row={'number':number,'stage':stage};generations.append(row);active.append(stage)
  gz(base/'canonical'/f'{number:03d}.json.gz',{'phase':phase,'view':view,'schema':self.protocol.schema(schema_name)})
  try:
   value=original_generate(self,phase,view,schema_name,**kwargs);gz(base/'canonical'/f'{number:03d}-output.json.gz',value);row['status']='accepted';return value
  except Exception as exc:row.update(status='rejected',error_type=type(exc).__name__,error=str(exc));raise
  finally:active.pop();put(base/'generations.json',generations)
 gateway.ModelGateway.generate=generate
 binding={'mode':'MAIN143-photo-review-live','generation':143,'release_id':'ontology-accumulation-20261105-r1','case_id':case_id,'arm':arm,'quality_certified':False}
 app=create_app(runtime,data,contracts_root=C,release=binding,provider=Haiku(C,runtime/'provider',False,backend='source-only',trust_zone='internal'),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=t,workspace_root=ROOT,runtime_root=runtime,data_store=store,memory_identity=lambda request:{'user_id':'adr1380','team_id':'risk_team','document_ids':sorted(allowed)})
 client=TestClient(app,raise_server_exceptions=False);client.__enter__();assert client.get('/health').status_code==200
 from semantic_runtime.chat_adapter import request_body as chat_body,views
 import ast,re
 service_source=C/'service.py';tree=ast.parse(service_source.read_text())
 normalize_node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_normalize')
 normalize_globals={'Any':object,'re':re,'os':os}
 exec(compile(ast.Module(body=[normalize_node],type_ignores=[]),str(service_source),'exec'),normalize_globals)
 normalize=normalize_globals['_normalize']
 put(base/'ingress.json',{'chat_adapter':str(C/'02_BACKEND/semantic_runtime/chat_adapter.py'),'service_normalize_source':str(service_source),'service_sha256':sha(service_source),'normalization':'exact selected function AST; no manual field deletion'})
 def body_for(step):
  data={'question':step['question'],'applied_fields':{'mode':step['mode']},'document_ids':sorted(allowed),'session_id':'adr1380-'+session_name,'request_id':'turn-'+str(step['number']),'use_llm':True,'team_id':'risk_team','memory':True}
  if action_branch:
   action_input=read(seed/'action-request.json')
   data.update(request_id=action_input['review_action']['operation_id'],review_action=action_input['review_action'])
   data.pop('applied_fields')  # Structured actions require the exact offered label. The signed-in scope is retained.
  raw=chat_body(data,step['question'])
  public=set(allowed)<=set(t.grant['public_document_ids'])
  if step['mode']!='대사':assert public,'Internal ordinary history requires GENOS/internal model; not relabeled public'
  raw['public_question']=public
  dispatch=normalize(raw);assert dispatch['path']=='/v1/rag/ask'
  return dispatch['json']
 if action_branch:
  case['steps']=[{'number':3,'question':read(seed/'action-request.json')['label'],'mode':'외규'}]
 body=body_for(case['steps'][0]);current_body=body;case['question']=body['question']
 source_stats={'generation_id':source_manifest['generation_id'],'store_sha256':source_manifest['store_sha256'],'export_allowed':source_manifest['export_allowed']}
 put(base/'binding.json',{'code_root':str(C),'selected_equivalent':True,'frozen_candidate':True,'selected_files':len(candidate['selected_files']),'profile':profile,'source':source_stats,'query_release_id':getattr(sql_request,'release_id',None),'scope':sorted(allowed),'data_path':str(data.relative_to(ROOT)),'source_storage':'selected local SQLite','state_storage':'isolated local SQLite','oracle_connections':0,'oracle_writes':0,'prepare_seconds':time.monotonic()-prepare_start})
 if preflight:
  query={'question':body['question'],'scope':{'document_version_ids':sorted(allowed)}}
  receipt=t.authorize(query,body,source_manifest,public_question=False)
  from types import SimpleNamespace
  t.validate_authorization(SimpleNamespace(query=query,request=body,binding={**source_stats,'external_authorization':receipt,'model':t.binding}))
  put(base/'result.json',{'ready':True,'model_calls':0,'http_health':200,'source':source_stats});print('PREFLIGHT_READY',base.name,flush=True)
 else:
  results=[]
  for step in case['steps']:
   if (ART/'STOP_EXTERNAL.json').exists():break
   body=body_for(step);current_body=body;case['question']=body['question'];host_derived_questions.clear()
   turn=base/('turn-'+str(step['number']));turn.mkdir(exist_ok=False)
   put(turn/'request.json',body);before=len(calls);begin=time.monotonic()
   r=client.post('/v1/rag/ask',json=deepcopy(body));elapsed=time.monotonic()-begin
   try:value=r.json()
   except ValueError:value={'non_json':r.text}
   gz(turn/'response.json.gz',{'http_status':r.status_code,'body':value})
   ans=value.get('answer') or {};answer_text=ans.get('text','') if isinstance(ans,dict) else str(ans)
   (turn/'answer.txt').write_text(answer_text)
   if r.status_code==200:
    (turn/'public-answer.txt').write_text(views()._public_answer_text(value))
    (turn/'public-review.txt').write_text(views()._review_explanation_text(value))

   result={'case_id':case_id,'step':step,'sent_question':body['question'],'http_status':r.status_code,'status':value.get('status'),'run_id':value.get('run_id'),'question_id':value.get('question_id'),'revision':value.get('revision'),'executed':value.get('executed'),'request_seconds':elapsed,'physical_calls':len(calls)-before,'unknown':sum(c['status']=='unknown' for c in calls[before:]),'claims':len(ans.get('claims',[])) if isinstance(ans,dict) else 0,'answer_chars':len(answer_text),'quality_certified':False}
   if r.status_code==200:
    count=len(calls);again=client.post('/v1/rag/ask',json=deepcopy(body));duplicate={'http_status':again.status_code,'same_answer':again.json().get('answer')==value.get('answer'),'extra_model_calls':len(calls)-count};put(turn/'duplicate.json',duplicate);result['duplicate']=duplicate
    assert duplicate['extra_model_calls']==0 and duplicate['same_answer']
   put(turn/'result.json',result);results.append(result);put(base/'result.json',{'case_id':case_id,'turns':results,'physical_calls':len(calls),'unknown':sum(c['status']=='unknown' for c in calls)})
   if not replay and not admission and step['number']==1 and r.status_code==200:
    agent=(value.get('assembly') or {}).get('term_agent') or {}
    view=agent.get('review_explanation') or {}
    offered=next((a for a in view.get('actions',[]) if a.get('enabled') and a.get('kind')=='REVIEW_AGAIN'),None)
    eligible=bool(offered and not ans.get('claims') and agent.get('stop_reason')=='ASSESSMENT_CONTRACT_UNRESOLVED')
    put(base/'action-eligibility.json',{'eligible':eligible,'offered':bool(offered),'stop_reason':agent.get('stop_reason'),'prior_claims':len(ans.get('claims') or [])})
    if eligible:
     seed.mkdir(exist_ok=False)
     hashes={str(p.relative_to(runtime)):sha(p) for p in runtime.rglob('*') if p.is_file()}
     shutil.copytree(runtime,seed/'runtime',symlinks=True)
     assert all(sha(runtime/n)==h and sha(seed/'runtime'/n)==h for n,h in hashes.items())
     put(seed/'files.json',hashes)
     put(seed/'origin.json',{'sent_question':body['question'],'request_sha256':sha(turn/'request.json'),'response_sha256':sha(turn/'response.json.gz')})
     put(seed/'action-request.json',{'label':offered['label'],'review_action':{'schema_version':'review-action-v1','case_id':view['case']['question_id'],'revision':view['case']['revision'],'action_id':offered['id'],'view_hash':view['content_sha256'],'operation_id':'turn-3-action','input':{}}})
   print('LIVE_RESULT',json.dumps(result,ensure_ascii=False),flush=True)
   # Dependent follow-ups need an accepted parent response.
   if r.status_code!=200:break

except Exception as exc:
 put(base/'runner-failure.json',{'type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc(),'model_calls':len(locals().get('calls',[]))})
 print('RUNNER_FAILURE',type(exc).__name__,str(exc),flush=True);raise
finally:
 if sql_transport is not None:
  gz(base/'sql-statements.json.gz',sql_transport.statements);gz(base/'sql-errors.json.gz',sql_transport.errors)
 if client is not None:client.__exit__(None,None,None)
 if gold_context is not None:gold_context.__exit__(None,None,None)
 elif app is not None:app.state.pipeline.store.close()
 guard.done.set();guard.thread.join(timeout=2)
 put(base/'resource-final.json',{'peak_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'sample':guard.check(),'oracle_driver_loaded':'oracledb' in sys.modules,'selected_code_unchanged':all(sha(C/n)==h and sha(selected_code/n)==h for n,h in candidate['selected_files'].items()),'loaded_modules':{name:str(getattr(mod,'__file__','')) for name,mod in sys.modules.copy().items() if name.startswith(('semantic_runtime','workflow')) and getattr(mod,'__file__',None)}})
