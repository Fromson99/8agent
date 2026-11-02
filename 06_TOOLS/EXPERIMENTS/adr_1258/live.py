"""One exact authorized CM request, native API, unchanged frozen MAIN129."""
from pathlib import Path
import importlib.util,sys,os
sys.dont_write_bytecode=True
from contextlib import nullcontext
R=Path('/home/jin/8-AGENT');P=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
FROZEN=Path(__file__).resolve().parents[3]
from pinned_imports import install,verify_loaded
install(FROZEN)
spec=importlib.util.spec_from_file_location('gold_on_connector',FROZEN/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py')
gold=importlib.util.module_from_spec(spec);spec.loader.exec_module(gold);gold.ROOT=R;gold.ACTIVE_POINTER=R/'04_EXPERIMENTS/ADR/ADR-1258-main129-fixed-cap-oracle-live/artifacts/design/active-main129.json'
os.environ.update(OPENBLAS_NUM_THREADS='4',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1')
CASE_ID=sys.argv[1];assert len(sys.argv)==2 and CASE_ID in ('gold-369','cm-009')
DESIGN=R/'04_EXPERIMENTS/ADR/ADR-1258-main129-fixed-cap-oracle-live/artifacts/design'
CASE=next(x for x in gold.read(DESIGN/'cases.json') if x['id']==CASE_ID)
GOLD_CONTEXT=gold.open_store(documents=CASE['request']['json']['document_ids'])
GOLD_OPEN=GOLD_CONTEXT.__enter__()
from engine_runtime import *
PARENT_O=O
A=R/'04_EXPERIMENTS/ADR/ADR-1258-main129-fixed-cap-oracle-live';D=A/'artifacts/design';O=A/'artifacts/run-001'
import threading,shutil
resource_samples=[];resource_log=None;resource_lock=threading.RLock()
def measure():
 value={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith(('MemAvailable:','SwapTotal:','SwapFree:'))}
 value.update({x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmRSS:','VmSwap:'))})
 value['free_disk']=min(shutil.disk_usage(R).free,shutil.disk_usage('/mnt/c').free)
 return value
initial_resource=measure();initial_swap=initial_resource['SwapTotal']-initial_resource['SwapFree']
def guard():
 with resource_lock:
  value=measure();value['host_swap_growth']=value['SwapTotal']-value['SwapFree']-initial_swap
  value['elapsed_seconds']=time.monotonic()-start if 'start' in globals() else None
  resource_samples.append(value)
  if resource_log is not None:
   resource_log.write(json.dumps(value)+'\n');resource_log.flush();os.fsync(resource_log.fileno())
  failed=[]
  if value['host_swap_growth']>1024*1024**2:failed.append('HOST_SWAP_GROWTH_1GIB')
  if value.get('VmSwap',0)>256*1024**2:failed.append('PROCESS_SWAP_256MIB')
  if value['MemAvailable']<3*1024**3:failed.append('MEM_AVAILABLE_3GIB')
  if value['VmRSS']>5*1024**3:failed.append('PROCESS_RSS_5GIB')
  if value['free_disk']<80*1024**3:failed.append('DISK_FREE_80GIB')
  if failed:raise RuntimeError('|'.join(failed))
  return value

import asyncio,gzip,traceback,importlib,resource
from contextvars import ContextVar
sys.path.insert(0,str(R/'06_TOOLS/maintenance'))
from experiment_json import write_summary,write_raw_json,SUMMARY_LIMIT
checkpoint_put=put
def put(path,value):
 path=Path(path)
 if path.name in ('calls.json','generations.json'):
  assert len(json.dumps(value,ensure_ascii=False).encode())<SUMMARY_LIMIT
  checkpoint_put(path,value)
 else:write_summary(path,value)
def gz(path,value):
 receipt=write_raw_json(path,value)
 write_summary(Path(str(path)+'.ref.json'),receipt)
def preserve_provider_failure(exc):
 from semantic_runtime.legal_agent.errors import TransportError,ContractError
 from lawrag.research.experiment_client import ExperimentProviderError
 response=getattr(exc,'response',None)
 if not isinstance(response,dict) or type(response.get('status_code')) is not int:
  raise TransportError('Experiment adapter has no complete response',retryable=False,unknown=True) from exc
 status=response['status_code']
 if not 200<=status<300:
  response={**response,'acceptance':'KNOWN_REJECTED' if status==429 else 'UNKNOWN' if status>=500 else 'ACCEPTED'}
  raise TransportError('Experiment provider rejected request',response=response,retryable=status==429,unknown=status>=500) from exc
 if isinstance(exc,ExperimentProviderError):raise ContractError('Experiment adapter rejected response policy') from exc
 # A complete HTTP response with a format failure is still validated by the
 # native structured-content/schema boundary. It is never a transport retry.
 return response

def main():
 global resource_log,start
 case_id=CASE_ID;case=CASE;out=O/'live'/case_id
 assert read(D/'preflight.json')['passed']
 if case_id=='cm-009':assert all(read(O/'ontology-e2e.json')['gates'].values())
 out.mkdir(parents=True,exist_ok=False);runtime=Path('/__oracle_agent__/runtime/adr1258')
 guard();start=time.monotonic();calls=[];generations=[];active=[];opens=[];transport=None;http=None
 def audit(event,args):
  if event=='sqlite3.connect':
   name=str(args[0]);opens.append(name)
   if name != ':memory:' and 'mode=memory' not in name:raise RuntimeError('PERSISTENT_SQLITE_FORBIDDEN:'+name)
 sys.addaudithook(audit)
 os.environ.update(DP='oracle',GENOS_ORACLE_AGENT_NAMESPACE='adr1258-main129-live',GENOS_RUNTIME_DIR=str(runtime),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',GENOS_RAG_INITIAL_SEARCH='auto',LAWRAG_WORKSPACE_ROOT=str(R))
 for key in ('GENOS_STATE_DIR','GENOS_DETAIL_LOG_DIR','GENOS_SHARED_LOG_DIR','GENOS_SYSTEM_LOG_DIR'):
  os.environ.pop(key,None)
 from semantic_runtime import oracle_runtime_paths as paths
 from semantic_runtime.oracle_agent_records import AgentRecords,RecordSQL
 spec=importlib.util.spec_from_file_location('records_transport',R/'06_TOOLS/EXPERIMENTS/adr_1244/test_records.py')
 local=importlib.util.module_from_spec(spec);spec.loader.exec_module(local)
 spec=importlib.util.spec_from_file_location('local_agent_connection',R/'06_TOOLS/maintenance/agent_record_oracle_r2.py')
 admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)
 record_db=admin.connection();record_client=local.LocalOracle(record_db)
 record_sql=RecordSQL(record_client,binding='adr1258-local-oracle-records',deadline=start+1800,max_calls=10000)
 from safety import CapacityGuard,SharedBudget
 capacity=CapacityGuard(admin.connection(),out,quota_limit=.9,reserve_bytes=0,reference_quota=300*1024**2)
 capacity.sample(write=False)
 shared=SharedBudget(25000,initial_calls=GOLD_OPEN[1].sql.calls)
 original_record_request=record_client.request;original_gold_request=GOLD_OPEN[2].request
 def record_request(method,path,json):
  if json['statementText'].lstrip().startswith(('DECLARE ','BEGIN ')):capacity.sample(write=True)
  shared.reserve('agent');return original_record_request(method,path,json)
 def source_request(*args,**kwargs):
  shared.reserve('source');return original_gold_request(*args,**kwargs)
 record_client.request=record_request;GOLD_OPEN[2].request=source_request
 records=AgentRecords(record_sql,namespace=os.environ['GENOS_ORACLE_AGENT_NAMESPACE']);records.preflight()
 paths.configure(lambda:records)
 put(out/'record-binding.json',{'scope':records.scope,'namespace':os.environ['GENOS_ORACLE_AGENT_NAMESPACE'],'logical_runtime':str(runtime),'transport':'real local Oracle via direct SQL adapter; field ORDS unverified','nfs':'unconfigured, no NFS mount present'})
 from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport
 from semantic_runtime.legal_agent.workflow_tiers_policy import profile as checked
 from semantic_runtime.legal_agent import workflow_execution,gateway
 from semantic_runtime.legal_agent.errors import ContractError
 from semantic_runtime.app import create_app
 from semantic_runtime.provider import Haiku
 from fastapi.testclient import TestClient
 t=LocalQwen38Transport(C,R);allowed=set(case['request']['json']['document_ids']);assert allowed<=set(t.public_scope)
 profile=checked({**GOLD_OPEN[0].gold_profile,'model_binding':t.binding,'max_output_tokens':t.policy['max_output_tokens']},require_model=True)
 assert profile['max_model_attempts']==40 and profile['max_tool_actions']==1024 and profile['wall_seconds']==1800 and profile['max_output_tokens'] is None
 expected=case['request']['json']['question'];auth_hash=sha(D/'authorization.json');token=ContextVar('gold_cm_authorization',default=None);previous=workflow_execution.authorization
 workflow_execution.authorization=lambda:previous() or token.get()
 class Authorized(type(t)):
  @property
  def public_scope(self):return None
  def authorize(self,query,request,manifest,*,public_question=False):
   scope=set(query['scope']['document_version_ids'])
   if not token.get() or public_question or request.get('question',query.get('question'))!=expected or not request['use_llm'] or not scope or not scope<=allowed:raise ContractError('CM exact question/scope mismatch')
   assert sha(D/'authorization.json')==auth_hash and sha(self.grant_path)==self.grant_hash and sha(self.policy_path)==self.policy_hash
   assert manifest['generation_id']==self.grant['generation_id'] and manifest['store_sha256']==self.grant['source_store_sha256'] and manifest['export_allowed'] is False
   return {'kind':'USER_AUTHORIZED_GOLD_ONTOLOGY_CHECK','authorization_sha256':auth_hash,'grant_sha256':self.grant_hash,'policy_sha256':self.policy_hash,'case_id':case_id,'question_sha256':hashlib.sha256(expected.encode()).hexdigest(),'public_question_asserted':False,'scope_document_ids':sorted(scope)}
  def validate_authorization(self,context):
   identity=(context.run_id,context.binding_hash,context.query['id']);prior=getattr(self,'_cm_identity',None)
   if prior is None:
    assert context.request['question']==expected;self._cm_identity=identity;self._cm_deadline=context.deadline
   else:assert prior==identity and context.deadline<=self._cm_deadline
   receipt=self.authorize(context.query,{**context.request,'question':expected},{'generation_id':context.binding['generation_id'],'store_sha256':context.binding['store_sha256'],'export_allowed':context.binding['export_allowed']},public_question=False)
   assert context.binding['external_authorization']==receipt and context.binding['model']==self.binding
 t.__class__=Authorized
 import lawrag
 lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
 from lawrag.research.experiment_client import ExperimentClient,ExperimentProviderError,ExperimentFormatError,ExperimentTransportError
 from semantic_runtime.legal_agent.local_gemma import provider_request
 from semantic_runtime.legal_agent.errors import TransportError
 os.environ['OPEN_ROUTER']=t._key
 from lawrag.core import request_deadline as pinned_deadline
 audited=ExperimentClient(FROZEN,out/'experiment-client',max_calls=40,max_repairs=0)
 put(out/'transport-binding.json',verify_loaded(FROZEN))
 def reserved_send(*,body,ticket):
  audited.provider_index=ticket['provider_index'];audited._apply_provider()
  payload=provider_request(body)
  capacity.sample(write=False)
  remaining=min(180,float(ticket['remaining_seconds']),float(ticket['deadline'])-time.monotonic())
  if remaining<=0:raise ContractError('reserved transport deadline exhausted')
  try:
   return super(type(audited),audited).chat_completions(payload,phase=active[-1] if active else 'request',timeout_seconds=remaining)
  except (ExperimentProviderError,ExperimentFormatError) as exc:
   return preserve_provider_failure(exc)
  except ExperimentTransportError as exc:
   from lawrag.core.request_deadline import AbsoluteDeadlineExceeded
   deadline_error=any(isinstance(e,AbsoluteDeadlineExceeded) for e in (exc.__cause__,exc.__context__))
   mapped=TransportError(str(exc),retryable=exc.retryable,unknown=exc.unknown)
   if deadline_error:mapped.http_status=504
   raise mapped from exc
 t.send_once=reserved_send
 from lawrag.core import request_deadline
 old_post=request_deadline.post_json;old_generate=gateway.ModelGateway.generate
 def post(url,**kw):
  verify_loaded(FROZEN);guard();capacity.sample(write=False);payload=kw['json_body'];assert url.startswith(t.policy['endpoint']+'/chat/completions') and payload['model']=='qwen/qwen3.8-27b'
  assert not any(k in payload for k in ('max_tokens','max_completion_tokens','max_output_tokens'))
  n=len(calls)+1;d=out/'raw'/str(n).zfill(3);row={'number':n,'stage':active[-1] if active else None,'status':'started','provider':payload.get('provider')};calls.append(row);put(out/'calls.json',calls);gz(d/'request.json.gz',payload);begin=time.monotonic();print('MODEL',case_id,n,row['stage'],flush=True)
  try:
   response=old_post(url,**kw)
   try:body=response.json()
   except ValueError:body={'non_json':response.text}
   gz(d/'response.json.gz',body);row.update(status='responded',http_status=response.status_code,usage=body.get('usage'),diagnostics=response.extensions.get('absolute_deadline',{}));return response
  except Exception as e:
   row.update(status='unknown',error_type=type(e).__name__,diagnostics=getattr(e,'diagnostics',{}))
   if hasattr(e,'partial_body'):
    import base64
    gz(d/'partial.json.gz',{'base64':base64.b64encode(e.partial_body).decode()})
   raise
  finally:row['seconds']=time.monotonic()-begin;put(out/'calls.json',calls);put(d/'result.json',row)
 def generate(self,phase,view,schema_name,**kw):
  n=len(generations)+1;stage=view.get('source_stage',phase);row={'number':n,'stage':stage};generations.append(row);active.append(stage)
  gz(out/'canonical'/f'{n:03d}.json.gz',{'phase':phase,'view':view,'schema':self.protocol.schema(schema_name)})
  try:
   result=old_generate(self,phase,view,schema_name,**kw);gz(out/'canonical'/f'{n:03d}-output.json.gz',result);row['status']='accepted';return result
  except Exception as e:row.update(status='rejected',error=str(e));raise
  finally:active.pop();put(out/'generations.json',generations)
 request_deadline.post_json=post;gateway.ModelGateway.generate=generate
 result={'case_id':case_id,'quality_certified':False,'engine':'frozen MAIN129','original_sqlite_fallback':False}
 import faulthandler
 native_stack=(out/'native-stack.log').open('x');faulthandler.enable(file=native_stack)
 stop=threading.Event();resource_log=(out/'resource-samples.jsonl').open('x',buffering=1)
 def monitor():
  while not stop.wait(1):
   try:
    guard()
   except Exception as e:
    resource_log.flush();os.fsync(resource_log.fileno());put(out/'resource-stop.json',{'last_sample':resource_samples[-1],'reason':str(e),'provider_outcome_unknown':bool(calls and calls[-1]['status']=='started'),'no_retry':True});os._exit(125)
 watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
 try:
  with nullcontext(GOLD_OPEN) as (store,req,transport):
   app=create_app(runtime,None,contracts_root=C,release={'mode':'main129-oracle-records-1245','query_release_id':req.release_id,'quality_certified':False},provider=Haiku(C,runtime/'provider',False,backend='source-only',trust_zone='internal'),vector=False,implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=t,workspace_root=R,runtime_root=runtime,data_store=store,memory_identity=lambda request:{'user_id':'adr1258','team_id':'risk_team','document_ids':sorted(allowed)})
   with TestClient(app) as http:
    assert http.get('/health').status_code==200
    put(out/'binding.json',{'query_id':req.release_id,'profile':profile,'documents':sorted(allowed),'code_root':str(C),'authorization_sha256':auth_hash,'state_storage':'oracle SIDDA structured records; NFS unconfigured'})
    put(out/'dispatch.json',{'case_id':case_id,'same_case_retry':False,'physical_limit':40});put(out/'request.json',case['request'])
    handle=token.set({'kind':'USER_AUTHORIZED_GOLD_ONTOLOGY_CHECK','case_id':case_id,'authorization_sha256':auth_hash,'no_prior_history':True})
    try:response=http.post('/v1/rag/ask',json=case['request']['json'])
    finally:token.reset(handle)
    body=response.json();put(out/'response.json',{'http_status':response.status_code,'body':body});answer=body.get('answer',{});(out/'answer.txt').write_text(answer.get('text','') if isinstance(answer,dict) else str(answer));result.update(http_status=response.status_code,status=body.get('status'),run_id=body.get('run_id'));put(out/'request-result-checkpoint.json',result)
    if response.status_code==200 and body.get('answer'):
     before_calls=len(calls);handle=token.set({'kind':'USER_AUTHORIZED_GOLD_ONTOLOGY_CHECK','case_id':case_id,'authorization_sha256':auth_hash})
     try:again=http.post('/v1/rag/ask',json=case['request']['json'])
     finally:token.reset(handle)
     put(out/'duplicate.json',{'status':again.status_code,'same_answer':again.json().get('answer')==body.get('answer'),'extra_model_calls':len(calls)-before_calls})

 except Exception as e:result.update(error=str(e),error_type=type(e).__name__);(out/'error.txt').write_text(traceback.format_exc())
 finally:
  stop.set();watcher.join(timeout=2);resource_log.close();faulthandler.disable();native_stack.close();GOLD_CONTEXT.__exit__(None,None,None);request_deadline.post_json=old_post;gateway.ModelGateway.generate=old_generate;workflow_execution.authorization=previous
  result.update(agent_sql_calls=record_sql.calls,agent_sql_errors=record_client.errors,oracle_scope=records.scope,seconds=time.monotonic()-start,model_calls=len(calls),unknown=sum(x['status']=='unknown' for x in calls),sql_calls=len(transport.statements) if transport else 0,peak_rss_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,engine_code_unchanged=all(sha(C/p)==h for p,h in B['engine_files'].items()))
  result.update(shared_sql_calls=shared.calls,shared_sql_counts=shared.by_port,capacity_queries=capacity.queries);capacity.sample(write=False);capacity.close();record_db.close();put(out/'transport-after.json',verify_loaded(FROZEN));put(out/'result.json',result);put(out/'sqlite-opens.json',opens);gz(out/'sql-statements.json.gz',transport.statements if transport else []);gz(out/'sql-errors.json.gz',transport.errors if transport else []);gz(out/'resources.json.gz',resource_samples);print('LIVE_RESULT',result,flush=True)
if __name__=='__main__':main()
