"""Native API experiment. Product code is byte-identical to selected MAIN133."""
from common import *
import os,time,importlib,importlib.util,traceback,gzip,resource
from copy import deepcopy
from contextlib import nullcontext
os.environ.update(OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONDONTWRITEBYTECODE='1',AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',LAWRAG_WORKSPACE_ROOT=str(ROOT))
for n in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED','TEAM_ID','AD_WORKSPACE','GENOS_STATE_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR'):os.environ.pop(n,None)
case_id,arm=sys.argv[1:3];preflight='--preflight' in sys.argv
assert arm in ('baseline','ontology-on')
case=next(c for c in read(DES/'cases.json') if c['id']==case_id)
assert arm in case['arms']
base=ART/('preflight' if preflight else 'live')/(case_id+'-'+arm);base.mkdir(parents=True,exist_ok=False)
runtime=base/'runtime';os.environ['GENOS_RUNTIME_DIR']=str(runtime)
candidate=read(DES/'candidate.json');C=ROOT/candidate['code_root'];selected_code=selected()
assert all(sha(C/n)==sha(selected_code/n)==h for n,h in candidate['selected_files'].items())
if not preflight:
 f=read(DES/'freeze.json')
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
 if not case.get('synthetic'):
  gp=ART/'gold-connector';spec=importlib.util.spec_from_file_location('frozen_gold_port',gp/'connect.py');gold=importlib.util.module_from_spec(spec);spec.loader.exec_module(gold)
  gold.ROOT=ROOT;gold.ACTIVE_POINTER=gp/'active-pointer.json'
  original_binding=gold.engine_binding
  def experiment_binding():
   value=original_binding()
   assert value['engine_root']==read(DES/'baseline.json')['release']['code_root']
   assert value['engine_files']==candidate['selected_files']
   assert all(sha(C/n)==h for n,h in value['engine_files'].items())
   return {**value,'engine_root':str(C.relative_to(ROOT))}
  gold.engine_binding=experiment_binding
  setting=DES/('ontology-on.json' if arm=='ontology-on' else 'ontology-off.json')
  gold_context=gold.open_store(documents=case['document_ids'],ontology_settings=setting,seconds=1800,max_calls=10000)
  store,sql_request,sql_transport=gold_context.__enter__()
  profile=deepcopy(store.gold_profile);source_manifest=store.manifest;data=None
 else:
  source=read(DES/'comparison-source.json');data=ROOT/source['data_path'];source_manifest=source['source_manifest']
  profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
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
   assert case.get('synthetic') and request['question'] in (case['question'],case['question'].removeprefix('대사:').strip())
   assert request['workflow_id']=='risk_team_compare_workflow'
   assert set(request['document_ids'])==allowed and binding['generation_id']==source_manifest['generation_id'] and binding['store_sha256']==source_manifest['store_sha256']
   return {'kind':'USER_AUTHORIZED_WORKFLOW','grant_sha256':self.grant_hash,'policy_sha256':self.policy_hash,'scope_document_ids':sorted(allowed),'generation_id':source_manifest['generation_id'],'store_sha256':source_manifest['store_sha256'],'principal':request['principal'],'public_question_asserted':False,'experiment_authorization':auth_hash}
  def authorize(self,query,request,manifest,*,public_question):
   assert sha(DES/'authorization.json')==auth_hash and sha(self.policy_path)==self.policy_hash
   scope=set(query['scope']['document_version_ids'])
   assert scope and scope<=allowed and manifest['generation_id']==source_manifest['generation_id'] and manifest['store_sha256']==source_manifest['store_sha256'] and manifest['export_allowed'] is False
   parent=workflow_execution.authorization()
   if parent is not None:
    assert case.get('synthetic') and parent['experiment_authorization']==auth_hash and parent['kind']=='USER_AUTHORIZED_WORKFLOW'
    return {**parent,'scope_document_ids':sorted(scope)}
   if not public_question or request.get('question',query['question']) not in {case['question']}|host_derived_questions:raise errors.ContractError('Exact public question grant mismatch')
   return {'kind':'USER_AUTHORIZED_PUBLIC_ONTOLOGY_AB','authorization_sha256':auth_hash,'policy_sha256':self.policy_hash,'public_question_asserted':True,'scope_document_ids':sorted(scope)}
 t=Authorized(C,ROOT);profile.update(model_binding=t.binding,max_output_tokens=None)
 from contextlib import contextmanager
 from semantic_runtime.legal_agent.unified_rag import UnifiedRag
 from authorization import derive,self_test
 assert self_test()==8
 original_open=UnifiedRag.open
 @contextmanager
 def approved_open(host,state,principal,body):
  effective=derive(body,state,case['question'],allowed,'adr1296-'+base.name)
  assert effective==host.retrieval_question(state)
  session=host.model.ensure()
  receipt=session.context.binding['external_authorization']
  assert receipt['authorization_sha256']==auth_hash and set(receipt['scope_document_ids'])<=allowed
  host_derived_questions.add(effective)
  derivations.append({'original_question':body['question'],'effective_question':effective,'task':state['task'],'facts':deepcopy(state['facts']),'document_ids':state['document_ids'],'request_id':body['request_id'],'run_id':session.context.run_id,'product_state_rewritten':False})
  put(base/'authorized-derivations.json',derivations)
  with original_open(host,state,principal,body) as execution:yield execution
 UnifiedRag.open=approved_open
 calls=[];generations=[];active=[];model_started=False
 from lawrag.research.experiment_client import ExperimentClient
 from lawrag.research.openrouter_legal_adapter import send_reserved
 from lawrag.core import request_deadline
 verify_loaded(ART/'transport')
 audited=ExperimentClient(ROOT,base/'experiment-client',max_calls=40,max_repairs=0)
 def send(*,body,ticket):
  if preflight:raise RuntimeError('PREFLIGHT_EXTERNAL_SEND_FORBIDDEN')
  if (ART/'STOP_EXTERNAL.json').exists():raise errors.ContractError('Global physical outcome stop')
  verify_loaded(ART/'transport')
  total=sum(len(read(p)) for p in (ART/'live').glob('*/calls.json'))
  if total>=120:raise errors.BudgetExhausted('Global experiment120 physical cap')
  return send_reserved(audited,body=body,ticket=ticket,phase=active[-1] if active else 'request',error_module=errors,request_encoder=provider_request)
 t.send_once=send
 original_post=request_deadline.post_json
 def post(url,**kw):
  guard.check();payload=kw['json_body'];assert payload['model']=='qwen/qwen3.8-27b'
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
   row.update(status='responded',http_status=response.status_code,usage=body.get('usage'),actual_provider=body.get('provider'),transport_diagnostics=response.extensions.get('absolute_deadline',{}))
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
 binding={'mode':'ADR1296-native-main133','case_id':case_id,'arm':arm,'quality_certified':False}
 app=create_app(runtime,data,contracts_root=C,release=binding,provider=Haiku(C,runtime/'provider',False,backend='source-only',trust_zone='internal'),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=t,workspace_root=ROOT,runtime_root=runtime,data_store=store,memory_identity=lambda request:{'user_id':'adr1296','team_id':'risk_team','document_ids':sorted(allowed)})
 client=TestClient(app,raise_server_exceptions=False);client.__enter__();assert client.get('/health').status_code==200
 body={'question':case['question'],'document_ids':sorted(allowed),'session_id':'adr1296-'+base.name,'request_id':'initial','use_llm':True,'team_id':'risk_team'}
 if not case.get('synthetic'):body['public_question']=True
 source_stats={'generation_id':source_manifest['generation_id'],'store_sha256':source_manifest['store_sha256'],'export_allowed':source_manifest['export_allowed']}
 put(base/'binding.json',{'code_root':str(C),'selected_equivalent':True,'selected_files':len(candidate['selected_files']),'profile':profile,'source':source_stats,'query_release_id':getattr(sql_request,'release_id',None),'scope':sorted(allowed),'state_storage':'isolated local SQLite','oracle_writes':0,'prepare_seconds':time.monotonic()-prepare_start})
 if preflight:
  if not case.get('synthetic'):
   query={'question':case['question'],'scope':{'document_version_ids':sorted(allowed)}}
   receipt=t.authorize(query,body,source_manifest,public_question=True)
   from types import SimpleNamespace
   t.validate_authorization(SimpleNamespace(query=query,request=body,binding={**source_stats,'external_authorization':receipt,'model':t.binding}))
  put(base/'result.json',{'ready':True,'model_calls':0,'http_health':200,'source':source_stats,'sql_calls':getattr(getattr(sql_request,'sql',None),'calls',0)});print('PREFLIGHT_READY',base.name,flush=True)
 else:
  put(base/'dispatch.json',{'request':body,'case':case_id,'arm':arm,'predeclared':True,'retry':False})
  put(base/'request.json',body);begin=time.monotonic()
  r=client.post('/v1/rag/ask',json=deepcopy(body));elapsed=time.monotonic()-begin;value=r.json();gz(base/'response.json.gz',{'http_status':r.status_code,'body':value})
  ans=value.get('answer') or {};answer_text=ans.get('text','') if isinstance(ans,dict) else str(ans)
  (base/'answer.txt').write_text(answer_text)
  result={'case_id':case_id,'arm':arm,'http_status':r.status_code,'status':value.get('status'),'run_id':value.get('run_id'),'request_seconds':elapsed,'physical_calls':len(calls),'unknown':sum(c['status']=='unknown' for c in calls),'claims':len(ans.get('claims',[])) if isinstance(ans,dict) else 0,'answer_chars':len(answer_text),'source':source_stats,'source_sql_calls_before_requery':getattr(getattr(sql_request,'sql',None),'calls',0),'quality_certified':False}
  put(base/'result.json',result)
  if r.status_code==200:
   n=len(calls);again=client.post('/v1/rag/ask',json=deepcopy(body));duplicate={'http_status':again.status_code,'same_answer':again.json().get('answer')==value.get('answer'),'extra_model_calls':len(calls)-n};put(base/'duplicate.json',duplicate);result['duplicate']=duplicate;assert duplicate['extra_model_calls']==0 and duplicate['same_answer']
  put(base/'result.json',result);print('LIVE_RESULT',json.dumps(result,ensure_ascii=False),flush=True)
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
 put(base/'resource-final.json',{'peak_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'sample':guard.check(),'selected_code_unchanged':all(sha(C/n)==h for n,h in candidate['selected_files'].items())})
