"""Fresh multi-turn Qwen through the actual root service bound to the frozen candidate; observational hooks only."""
from common import *
import asyncio,importlib,time,traceback,base64,resource
from copy import deepcopy
from contextlib import contextmanager
case_id=sys.argv[1];arm=sys.argv[2];assert arm=='candidate';preflight='--preflight' in sys.argv
case=next(c for c in read(DES/'live-cases.json') if c['id']==case_id)
base=ART/('public-ready' if preflight else 'public-live')/(case_id+'-'+arm);base.mkdir(parents=True,exist_ok=False)
assert not any((ART/'public-live').glob('*/STOP_EXTERNAL.json')) and not any((ART/'public-live').glob('*/resource-stop.json')),'previous UNKNOWN or resource stop stops every later cell'
active_pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert active_pointer['generation']==166
selected_release=read(ROOT/active_pointer['manifest_path']);S=ROOT/selected_release['code_root']
candidate=read(DES/('arm-'+arm+'.json'));C=ROOT/candidate['code_root']
release={**selected_release,'files':candidate['selected_files']}
assert all(sha(C/n)==h for n,h in release['files'].items())
for p,h in read(DES/'freeze-live.json')['files'].items():assert sha(ROOT/p)==h,p
os.environ.update(GENOS_RUNTIME_DIR=str(base/'runtime'),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',LAWRAG_WORKSPACE_ROOT=str(ROOT),OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONDONTWRITEBYTECODE='1')
for k in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED','TEAM_ID','AD_WORKSPACE','GENOS_STATE_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','GENOS_RAG_IMPLEMENTATION'):os.environ.pop(k,None)
from resource_guard import Guard,sample,GIB
# User-directed immediate run on a shared host: wait (no model call) until the frozen admission
# margin holds, then start; every in-run floor and swap limit of the guard is unchanged.
waited=time.time()
while True:
 s=sample()
 if s['available']>=6*GIB:break
 if time.time()-waited>7000:put(base/'admission-timeout.json',{'sample':s,'model_calls':0});raise SystemExit('ADMISSION_TIMEOUT')
 time.sleep(15)
put(base/'admission-wait.json',{'seconds':time.time()-waited,'sample':s,'model_calls':0})
print('ADMITTED after',round(time.time()-waited),'s',flush=True)
guard=Guard(base);guard.start()
from pinned_imports import install,verify_loaded
install(ART/'transport')
import lawrag,lawrag.core,lawrag.research
for pkg,p in [(lawrag,'02_BACKEND/lawrag'),(lawrag.core,'02_BACKEND/lawrag/core'),(lawrag.research,'02_BACKEND/lawrag/research')]:pkg.__path__.extend([str(C/p),str(ROOT/p)])
sys.path[:0]=[str(ROOT),str(ROOT/'02_BACKEND')]
from lawrag.research.experiment_client import ExperimentClient
from lawrag.research.openrouter_legal_adapter import send_reserved
from lawrag.core import request_deadline
verify_loaded(ART/'transport')
def gz(p,v):
 ref=write_raw_json(p,v);put(Path(str(p)+'.ref.json'),{'raw_json':ref})
app=None;calls=[];generations=[];stages=[]
try:
 import service
 actual=importlib.import_module('service.service');assert actual is service
 original_binding=actual._local_release
 def candidate_binding():
  selected,data,binding=original_binding()
  assert binding['generation']==166 and selected==S
  return C,data,{**binding,'code_sha256':hashlib.sha256(json.dumps(candidate['selected_files'],sort_keys=True).encode()).hexdigest(),'experiment_candidate':'ADR1436/candidate','main_promoted':False}
 actual._local_release=candidate_binding
 app=actual.application();assert Path(app.state.pipeline.contracts.root)==C
 package=type(app.state.pipeline).__module__.rsplit('.',1)[0]
 mod=lambda name:importlib.import_module(package+'.legal_agent.'+name)
 agent=app.state.pipeline.term_agent;t=agent.transport;gateway=mod('gateway');errors=mod('errors');workflow=mod('workflow_execution');local=mod('local_gemma')
 assert mod('reason_decision_review').enabled(agent.profile)
 assert agent.profile['max_model_attempts']==40
 assert t.provider_policy==read(DES/'provider-policy.json')
 granted=set(case['document_ids']);assert granted<=set(t.grant['public_document_ids'])
 team_scope=importlib.import_module(package+'.team_scope')
 allowed=granted&set(team_scope.select_documents(app.state.pipeline.store,'financial_team'));assert allowed
 put(base/'scope-selection.json',{'requested_public_grant':sorted(granted),'actual_financial_team_intersection':sorted(allowed),'excluded_outside_current_team':sorted(granted-allowed),'selection_by_current_original_metadata':True,'reference_answers_used':False})
 data=ROOT/release['data_path'];metadata=read(data/'manifest.json');assert sha(data/'store.sqlite')==metadata['store_sha256']
 assert 'oracledb' not in sys.modules
 views=importlib.import_module(package+'.chat_adapter').views()
 question=case['steps'][0]['question'];body=views._request_body(question,{'applied_fields':{'mode':'외규'},'team_id':'financial_team','session_id':'adr1436-'+arm+'-'+case_id,'request_id':'adr1436-'+arm+'-'+case_id+'-1','document_ids':sorted(allowed),'memory':True,'public_question':True,'use_llm':True});body['public_question']=True
 assert body['question']=='외규: '+question
 current_body=body;current_step=case['steps'][0];derived=set();derivations=[];authhash=sha(DES/'authorization.json')
 normalized,principal=mod('memory_identity').prepare(app.state.pipeline,base/'runtime',actual._normalize(deepcopy(body))['json'],require_memory=True)
 assert set(body['document_ids'])<=set(principal['document_ids'])
 original_authorize=t.authorize
 def authorize(query,request,manifest,*,public_question):
  assert sha(DES/'authorization.json')==authhash
  scope=set(query['scope']['document_version_ids']);assert scope and scope<=allowed
  assert manifest['generation_id']==metadata['generation_id'] and manifest['store_sha256']==metadata['store_sha256']
  assert request.get('question',query['question']) in {body['question'],question}|derived
  receipt=original_authorize(query,request,manifest,public_question=public_question)
  return {**receipt,'experiment_authorization':authhash}
 t.authorize=authorize
 UnifiedRag=mod('unified_rag').UnifiedRag;original_open=UnifiedRag.open
 @contextmanager
 def bound_open(host,state,principal,request):
  linked=host.shortcut.investigation(host.active_case,principal,'adr1436-'+arm+'-'+case_id);assert linked['id']==host.active_case
  assert request['request_id']==body['request_id'] and request['question']==body['question']
  assert state['document_ids'] and set(state['document_ids'])<=allowed
  effective=host.retrieval_question(state);derived.add(effective)
  derivations.append({'original_question':body['question'],'effective_question':effective,'turn':current_step['number'],'task':state['task'],'search_scope':deepcopy(state.get('search_scope')),'facts':deepcopy(state['facts']),'document_ids':state['document_ids'],'product_state_rewritten':False});put(base/'authorized-derivations.json',derivations)
  with original_open(host,state,principal,request) as execution:yield execution
 UnifiedRag.open=bound_open
 audited=ExperimentClient(ROOT,base/'experiment-client',max_calls=80,max_repairs=0,provider_policy=DES/'provider-policy.json')
 def send(*,body,ticket):
  assert not preflight,'preflight never sends'
  if (base/'STOP_EXTERNAL.json').exists():raise errors.ContractError('Previous unknown: external sending stopped')
  allcalls=[c for p in (ART/'public-live').glob('*/calls.json') for c in read(p)]
  if len(allcalls)>=200 or sum((c.get('usage') or {}).get('cost',0) for c in allcalls)>=3:raise errors.BudgetExhausted('Frozen experiment total budget')
  verify_loaded(ART/'transport')
  return send_reserved(audited,body=body,ticket=ticket,phase=stages[-1] if stages else 'request',error_module=errors,request_encoder=local.provider_request)
 t.send_once=send
 original_post=request_deadline.post_json
 def post(url,**kw):
  guard.check();payload=kw['json_body'];assert payload['model']=='qwen/qwen3.8-27b' and payload['reasoning']=={'effort':'none'}
  assert not any(k in payload for k in ('max_tokens','max_output_tokens','max_completion_tokens'))
  n=len(calls)+1;out=base/'raw'/f'call-{n:03d}';out.mkdir(parents=True,exist_ok=False)
  row={'number':n,'case_id':case_id,'stage':stages[-1] if stages else None,'turn':current_step['number'],'canonical_number':len(generations),'status':'started','provider':payload['provider']};calls.append(row);put(base/'calls.json',calls);gz(out/'request.json.gz',payload);begin=time.monotonic()
  print('MODEL',case_id,n,row['stage'],flush=True)
  try:
   response=original_post(url,**kw)
   try:value=response.json()
   except ValueError:value={'non_json':response.text}
   gz(out/'response.json.gz',value)
   row.update(status='unknown' if response.status_code>=500 else 'responded',http_status=response.status_code,usage=value.get('usage'),actual_provider=value.get('provider'),actual_model=value.get('model'),transport_diagnostics=response.extensions.get('absolute_deadline',{}))
   if row['status']=='unknown':put(base/'STOP_EXTERNAL.json',{'cell':base.name,'call':n,'reason':'remote5xx'})
   return response
  except Exception as exc:
   row.update(status='unknown',error_type=type(exc).__name__,transport_diagnostics=getattr(exc,'diagnostics',{}))
   if hasattr(exc,'partial_body'):gz(out/'partial.json.gz',{'body_base64':base64.b64encode(exc.partial_body).decode(),'diagnostics':getattr(exc,'diagnostics',{})})
   put(base/'STOP_EXTERNAL.json',{'cell':base.name,'call':n,'reason':'Unknown physical outcome','no_automatic_retry':True});raise
  finally:row['seconds']=time.monotonic()-begin;put(out/'finished.json',row);put(base/'calls.json',calls)
 request_deadline.post_json=post
 original_generate=gateway.ModelGateway.generate
 def generate(self,phase,view,schema_name,**kwargs):
  n=len(generations)+1;stage=view.get('source_stage',phase);row={'number':n,'stage':stage,'turn':current_step['number']};generations.append(row);stages.append(stage)
  gz(base/'canonical'/f'{n:03d}.json.gz',{'phase':phase,'view':view,'schema':self.protocol.schema(schema_name)})
  try:
   v=original_generate(self,phase,view,schema_name,**kwargs);gz(base/'canonical'/f'{n:03d}-output.json.gz',v);row['status']='accepted';return v
  except Exception as exc:row.update(status='rejected',error_type=type(exc).__name__,error=str(exc));raise
  finally:stages.pop();put(base/'generations.json',generations)
 gateway.ModelGateway.generate=generate
 loaded_legal={n:Path(m.__file__).resolve() for n,m in list(sys.modules.items()) if n.split('.')[0] in ('semantic_runtime',package) and getattr(m,'__file__',None)}
 def same_bytes(path):
  if path.is_relative_to(C):rel=str(path.relative_to(C))
  elif path.is_relative_to(ROOT):rel=str(path.relative_to(ROOT))
  else:return False
  return rel in release['files'] and sha(path)==release['files'][rel]
 offenders=sorted(str(v) for v in loaded_legal.values() if not same_bytes(v))
 assert loaded_legal and not offenders,('every loaded semantic_runtime module must equal the arm inventory bytes',offenders[:8])
 put(base/'binding.json',{'arm':arm,'loaded_semantic_modules':len(loaded_legal),'loaded_release_package_modules':sum(k.split('.')[0]==package for k in loaded_legal),'release_package':package,'loaded_outside_code_root_same_bytes':sum(not v.is_relative_to(C) for v in loaded_legal.values()),'code_root':str(C),'scope':sorted(allowed),'profile':agent.profile,'source':metadata,'root_service':str(Path(actual.__file__).resolve()),'root_binding':actual._BINDING,'selected_pointer':active_pointer,'source_storage':'selected local SQLite','state_storage':'isolated local SQLite','actual_default_profile':True})
 health=asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'}));assert health['status']==200
 guard.rebase()
 if preflight:
  put(base/'result.json',{'ready':True,'model_calls':0,'http_health':200,'actual_root_service':True});print('PREFLIGHT_READY',case_id,flush=True)
 else:
  results=[]
  for current_step in case['steps']:
   if (base/'STOP_EXTERNAL.json').exists():break
   question=current_step['question']
   body=views._request_body(question,{'applied_fields':{'mode':'외규'},'team_id':'financial_team','session_id':'adr1436-'+arm+'-'+case_id,'request_id':'adr1436-'+arm+'-'+case_id+'-'+str(current_step['number']),'document_ids':sorted(allowed),'memory':True,'public_question':True,'use_llm':True})
   body['public_question']=True;current_body=body
   turn=base/('turn-'+str(current_step['number']));turn.mkdir();put(turn/'request.json',body)
   count_before=len(calls);begin=time.monotonic();response=asyncio.run(actual.service({},deepcopy(body)));elapsed=time.monotonic()-begin
   value=response.get('body') or {};gz(turn/'response.json.gz',{'http_status':response['status'],'body':value})
   answer=value.get('answer') or {};text=answer.get('text','') if isinstance(answer,dict) else str(answer);(turn/'answer.txt').write_text(text)
   reply=((value.get('assembly') or {}).get('term_agent') or {}).get('guided_reply') or {}
   put(turn/'guided-reply.json',{k:reply.get(k) for k in ('questions','needs_guidance','proposed_reads','answer_update','unread_connection_total','known_shortages','execution_limits')})
   result={'proposed_reads':[r.get('label') for r in reply.get('proposed_reads') or []],'answer_update':reply.get('answer_update'),'needs_guidance':reply.get('needs_guidance'),'accepted_outcome':((value.get('assembly') or {}).get('term_agent') or {}).get('accepted_outcome'),'case_id':case_id,'step':current_step,'http_status':response['status'],'request_seconds':elapsed,'physical_calls':len(calls)-count_before,'cumulative_calls':len(calls),'unknown':sum(c['status']=='unknown' for c in calls[count_before:]),'goal_id':value.get('goal_id'),'revision':value.get('revision'),'status':value.get('status'),'method':value.get('method_id'),'executed':value.get('executed'),'claims':len(answer.get('claims',[])) if isinstance(answer,dict) else 0}
   if response['status']==200:
    (turn/'public-answer.txt').write_text(views._public_answer_text(value));count=len(calls);again=asyncio.run(actual.service({},deepcopy(body)));dupe={'http_status':again['status'],'same_answer':again.get('body',{}).get('answer')==value.get('answer'),'extra_model_calls':len(calls)-count};put(turn/'duplicate.json',dupe);result['duplicate']=dupe
    assert dupe['same_answer'] and dupe['extra_model_calls']==0
   results.append(result);put(turn/'result.json',result);put(base/'result.json',{'case_id':case_id,'turns':results,'physical_calls':len(calls),'unknown':sum(c['status']=='unknown' for c in calls),'unexecuted_steps':[s['number'] for s in case['steps'][len(results):]]})
   print('LIVE_RESULT',json.dumps(result,ensure_ascii=False),flush=True)
   if response['status']!=200:break

except Exception as exc:
 put(base/'runner-failure.json',{'error_type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc(),'model_calls':len(calls)});raise
finally:
 if app is not None:app.state.pipeline.store.close()
 guard.done.set();guard.thread.join(2)
 put(base/'resource-final.json',{'sample':guard.check(),'peak_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'candidate_unchanged':all(sha(C/n)==h for n,h in release['files'].items()),'oracle_driver_loaded':'oracledb' in sys.modules})
