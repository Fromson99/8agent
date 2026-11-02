"""Real Oracle workspace, actual Qwen authoring, original compiler and native RAG."""
from common import *
import traceback,threading,types,logging
from unittest.mock import patch
os.environ.update(OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONDONTWRITEBYTECODE='1',DP='oracle',GENOS_RUNTIME_DIR='/__oracle_agent__/runtime/adr1260',GENOS_ORACLE_AGENT_NAMESPACE='adr1260-wiki-live',GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0',LAWRAG_WORKSPACE_ROOT=str(R))
for name in ('GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','GENOS_STATE_DIR'):os.environ.pop(name,None)
sys.dont_write_bytecode=True
OUT=O/'live';OUT.mkdir(parents=True,exist_ok=False)
gold,C,F=frozen_gold();DID='7bbe815ff43b6635'
ctx=gold.open_store(documents=[DID],seconds=1800,max_calls=10000);store,request,transport=ctx.__enter__()
from semantic_runtime import oracle_runtime_paths as paths
from semantic_runtime.oracle_agent_records import AgentRecords,RecordSQL
from semantic_runtime.ontology_work.store import OracleWorkStore
from semantic_runtime.ontology_work.domain_workflow import DomainWorkflow
from semantic_runtime.ontology_work.wiki_workspace import Workspace
from semantic_runtime.ontology_work.wiki_projection import compile_selection
from semantic_runtime.ontology_work.observations import envelope
from semantic_runtime.ontology_work import wiki_contracts as wc,wiki_transport
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.ontology_work.authoring_model import AuthoringFailure
from semantic_runtime import genos
from lawrag.core import request_deadline
import lawrag
lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError
from lawrag.research.openrouter_legal_adapter import send_reserved
local=module('workspace_oracle_transport',R/'06_TOOLS/EXPERIMENTS/adr_1244/test_records.py')
admin=module('workspace_record_admin',R/'06_TOOLS/maintenance/agent_record_oracle_r2.py')
publisher=module('workspace_gold_writer',R/'06_TOOLS/maintenance/publish_gold_ontology_samples.py')
started=time.monotonic();deadline=started+1800;record_db=admin.connection();client_db=local.LocalOracle(record_db)
sql=RecordSQL(client_db,binding='adr1260-real-oracle',deadline=deadline,max_calls=10000)
records=AgentRecords(sql,namespace=os.environ['GENOS_ORACLE_AGENT_NAMESPACE']);paths.configure(lambda:records)
capacity=module('wiki_capacity',R/'06_TOOLS/EXPERIMENTS/adr_1254/safety.py').CapacityGuard(admin.connection(),OUT,reserve_bytes=1024**2,reference_quota=300*1024**2)
original_db_request=client_db.request
shared_calls={'source':request.sql.calls,'agent':0,'work':0};guard_lock=threading.RLock()
def reserve(kind):
 with guard_lock:
  if sum(shared_calls.values())>=26000:raise RuntimeError('TOTAL_SQL_BUDGET')
  shared_calls[kind]+=1
original_source_request=transport.request
def source_request(*args,**kwargs):reserve('source');return original_source_request(*args,**kwargs)
transport.request=source_request
def record_request(method,path,json):
 reserve('agent')
 if json['statementText'].lstrip().startswith(('DECLARE ','BEGIN ')):capacity.sample(write=True)
 return original_db_request(method,path,json)
client_db.request=record_request
repo=store.gold_ports.mapping.ontology_repository(publisher.writer_connection,agent_owner='A8_GONT_AGENT',read_only=False)
original_execute=repo.execute
def execute(c,sql,params=()):reserve('work');return original_execute(c,sql,params)
repo.execute=execute
objects=OracleWorkStore(records);actor='adr1260-user-delegated';glossary=store.gold_ports.glossary_binding()
kwargs=dict(actor=actor,source_reader=store.gold_ports.source_reader,namespace='ADR1260-wiki',source_snapshot=request.snapshot.dataset_version,acl_ref=digest([DID]),document_ids=[DID],producer_binding=F['candidate_revision']['revision_sha256'])
w=Workspace(repo,objects,can_publish=True,**kwargs);domain=DomainWorkflow(repo,objects,glossary=glossary,**kwargs);domain.can_publish_workspace=True
scopes=frozenset([wc.scope_key(w.scope())]);repo.workspace_scopes=scopes;store.gold_ports.ontology.workspace_scopes=scopes
from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport
os.environ[read(C/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')['key_env']]=LocalQwen38Transport(C,R)._key
client=ExperimentClient(C,OUT/'provider',max_calls=24,max_repairs=0,schema_in_prompt=False)
def compressed(self,path,value):
 if self._key in json.dumps(value,ensure_ascii=False):raise RuntimeError('credential in artifact')
 p=Path(path).with_suffix('.json.gz')
 if p.exists():p=p.with_name(p.stem+'-revision-'+str(self.calls)+'.gz')
 if p.exists():raise RuntimeError('duplicate usage revision')
 raw(p,value)
client._write=types.MethodType(compressed,client)
endpoint=types.SimpleNamespace(headers={},url=lambda path:'https://authoring-experiment.invalid'+path)
old_post=request_deadline.post_json;stages=[];active=[];wire=[];stopped=threading.Event();stage='PRECHECK';result={'strict_success':False,'gates':{},'external_model_calls':0,'overall_deadline_epoch':time.time()+1800};stop_error=[]
initial_swap=None
resources=(OUT/'resources.jsonl').open('x',buffering=1)
def guard():
 global initial_swap
 mem={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith(('MemAvailable:','SwapTotal:','SwapFree:'))}
 proc={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmRSS:','VmSwap:'))}
 swap=mem['SwapTotal']-mem['SwapFree']
 if initial_swap is None:initial_swap=swap
 row={**mem,**proc,'host_swap_growth':swap-initial_swap,'elapsed':time.monotonic()-started};resources.write(json.dumps(row)+'\n')
 if row['MemAvailable']<3*1024**3 or row['VmRSS']>5*1024**3 or row.get('VmSwap',0)>256*1024**2 or row['host_swap_growth']>128*1024**2:raise RuntimeError('RESOURCE_LIMIT')
 if time.monotonic()>=deadline:raise RuntimeError('OVERALL_DEADLINE')
 if stop_error:raise RuntimeError(stop_error[0])
def monitor():
 while not stopped.wait(1):
  try:guard()
  except Exception as e:
   stop_error.append(str(e));put(OUT/'resource-stop.json',{'error':str(e),'stage':stage,'model_outcome_unknown':bool(wire and wire[-1]['status']=='SENT')});os._exit(125)
def post(url,**kw):
 guard()
 if url.startswith('https://authoring-experiment.invalid/'):
  payload=kw['json_body'];remaining=min(180,kw['deadline']-time.monotonic(),deadline-time.monotonic())
  if client.calls>=24 or remaining<=0:raise AuthoringFailure('BUDGET_EXHAUSTED',{'physical_calls':0})
  try:response=client.chat_completions(payload,phase=stage,timeout_seconds=remaining)
  except (ExperimentFormatError,ExperimentProviderError) as exc:
   # A real complete response still reaches the product parser. Unknown delivery
   # is never transformed into a completed response or retried here.
   response=getattr(exc,'response',None)
   if not isinstance(response,dict) or type(response.get('status_code')) is not int:raise
   if isinstance(exc,ExperimentProviderError) and 200<=response['status_code']<300:raise
  import httpx
  return httpx.Response(response['status_code'],json=response['body_json'])
 assert kw['json_body']['model']=='qwen/qwen3.8-27b'
 assert not {'max_tokens','max_output_tokens','max_completion_tokens'}&kw['json_body'].keys()
 i=len(wire)+1;row={'number':i,'stage':stage,'status':'SENT'};wire.append(row);put(OUT/'wire.json',wire);raw(OUT/'wire'/f'{i:03d}-request.json.gz',kw['json_body']);begin=time.monotonic();print('MODEL',i,stage,flush=True)
 try:
  response=old_post(url,**kw);body=response.json();raw(OUT/'wire'/f'{i:03d}-response.json.gz',body);row.update(status='RECEIVED',http_status=response.status_code,usage=body.get('usage'));return response
 except Exception as exc:
  row.update(status='UNKNOWN',error_type=type(exc).__name__)
  if hasattr(exc,'partial_body'):
   import base64
   raw(OUT/'wire'/f'{i:03d}-partial.json.gz',{'base64':base64.b64encode(exc.partial_body).decode(),'diagnostics':getattr(exc,'diagnostics',{})})
  raise
 finally:row['seconds']=time.monotonic()-begin;put(OUT/'wire.json',wire)
def generate(prompt,context,schema):
 row={'stage':stage,'attempt':context['call_budget']['attempt'],'calls_before':client.calls};stages.append(row);n=len(stages);raw(OUT/'authoring'/f'{n:03d}-input.json.gz',{'prompt':prompt,'context':context,'schema':schema})
 try:
  with patch.object(genos,'from_env',lambda kind:(endpoint,client.model)),patch.object(genos,'advertised_model',lambda *a:client.model):
   value,receipt=wiki_transport.generate(objects,actor,prompt,context,schema)
  raw(OUT/'authoring'/f'{n:03d}-output.json.gz',value);row['status']='RESPONSE';return value,receipt
 except Exception as exc:row.update(status=getattr(exc,'status','UNKNOWN'),error_type=type(exc).__name__);raise
 finally:row['calls_after']=client.calls;put(OUT/'stages.json',stages)
w.generate=generate;domain.generate=generate;request_deadline.post_json=post
opens=[]
def audit(event,args):
 if event=='sqlite3.connect':
  name=str(args[0]);opens.append(name)
  if name!=':memory:' and 'mode=memory' not in name:raise RuntimeError('PERSISTENT_SQLITE_FORBIDDEN:'+name)
sys.addaudithook(audit);watcher=threading.Thread(target=monitor,daemon=True)
try:
 guard();capacity.sample();records.preflight();watcher.start()
 originals=read(D/'originals.json');cases=read(D/'records.json')
 for s in originals:assert w.source_reader(s['anchor'])==s['text']
 result['gates']['current_oracle_sources']=True
 raws=[];changes=[]
 for i,c in enumerate(cases):
  source=R/c['origin']['path'];assert sha(source)==c['origin']['sha256'];v=json.loads(gzip.decompress(source.read_bytes()))
  for key in c['origin']['pointer'].strip('/').split('/'):v=v[int(key)] if isinstance(v,list) else v[key]
  assert v==c['payload']
  raw_record=envelope(v,namespace=w.namespace,run_id=c['id'],event_id=c['origin']['path']+c['origin']['pointer'],sequence=i,source_snapshot=w.source_snapshot,producer_binding=c['origin']['sha256'],acl_ref=w.acl_ref,document_ids=[DID],format_description='Exact archived failed-run model subtree '+c['origin']['pointer'],origin='ARCHIVED_MODEL_OUTPUT')
  r=w.ingest(raw_record);raws.append(r);assert w.ingest(raw_record)['work_hash']==r['work_hash']
  put(OUT/'raws.json',raws)
  stage='WIKI_PROPOSE_'+str(i+1);proposal=w.propose(change_id=c['id'],raw_ids=[r['bundle_id']],originals=originals,query='의결권');raw(OUT/f'proposal-{i+1}.json.gz',proposal)
  change=w.apply(**proposal);changes.append(change);put(OUT/'changes.json',changes)
 result['gates']['two_actual_records_accumulated']=len(raws)==2
 # A fresh AgentRecords object re-reads bytes through actual Oracle, not the cache.
 fresh=OracleWorkStore(AgentRecords(sql,namespace=os.environ['GENOS_ORACLE_AGENT_NAMESPACE']))
 for r in raws:assert fresh.get(r['work_hash'])==objects.get(r['work_hash'])
 assert len(repo.list(prefix='raw-'))>=2
 result['gates']['oracle_reopen_and_listing']=True
 items=[x for kind in ('ENTRY','STATEMENT','VIEW') for x in w.list_items(kind=kind,limit=128)['items']];statements=[x['bundle_id'] for x in items if x['kind']=='STATEMENT'];assert statements
 put(OUT/'workspace.json',{'catalog':w.catalog(),'items':items,'statements':statements})
 p=domain.save_profile(read(C/'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json'),read(C/'00_SYSTEM/ONTOLOGY_PROFILES/business-profile-v1.json'))
 domain.review_profile(p['bundle_id'],p['revision'],p['work_hash'],True,'사용자 위임 실제 연결 검증용 프로필; 개별 법률 품질 인증 아님')
 stage='NORMALIZE_SOURCE_AND_PROJECT';compiled=compile_selection(domain,w,statement_ids=statements,purpose='현재 원문에 따른 주식 의결권 기본 규칙 재사용',profile_id=p['bundle_id'],profile_work_hash=p['work_hash'])
 package=domain.preview(compiled['bundle_id']);raw(OUT/'compiled.json.gz',{'row':compiled,'package':package,'document':domain.load(compiled['bundle_id'])})
 result['gates']['original_compiler']=True
 stage='REVIEW';put(OUT/'review-pending.json',{'compiled':compiled,'package_hash':digest(package),'reason':'Inspect exact source, coverage, unknowns, paths and binding before delegated approval'})
 # Approval is an explicit second invocation after the recorded candidate is reviewed.
 result.update(status='COMPILED_AWAITING_REVIEW',compiled=compiled,profile=p,scope=w.scope(),statements=statements)
except Exception as exc:
 result.update(status='FAILED',stage=stage,error_type=type(exc).__name__,error=str(exc));(OUT/'error.txt').write_text(traceback.format_exc())
finally:
 stopped.set()
 if watcher.is_alive():watcher.join(timeout=2)
 request_deadline.post_json=old_post
 result.update(seconds=time.monotonic()-started,external_model_calls=len(wire),client_physical_calls=client.calls,unknown=sum(x['status']=='UNKNOWN' for x in wire),shared_sql=shared_calls,agent_sql_errors=client_db.errors,oracle_scope=records.scope,code_unchanged=all(sha(C/n)==h for n,h in F['files'].items()))
 put(OUT/'result.json',result);raw(OUT/'source-sql.json.gz',transport.statements);put(OUT/'sqlite-opens.json',opens);capacity.close();record_db.close();resources.close();glossary.reader.close();ctx.__exit__(None,None,None)
 print(json.dumps({k:v for k,v in result.items() if k not in ('scope','compiled')},ensure_ascii=False),flush=True)
