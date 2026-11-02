"""Continue the same frozen trial after explicit recorded content review."""
from common import *
import traceback,types,threading
os.environ.update(DP='oracle',GENOS_RUNTIME_DIR='/__oracle_agent__/runtime/adr1259',GENOS_ORACLE_AGENT_NAMESPACE='adr1259-wiki-live',GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0',OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',LAWRAG_WORKSPACE_ROOT=str(R))
for key in ('GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','GENOS_STATE_DIR'):os.environ.pop(key,None)
prior=read(O/'live/result.json');assert prior['status']=='COMPILED_AWAITING_REVIEW'
review=read(O/'review.json');assert review['approved'] is True and review['work_hash']==prior['compiled']['work_hash']
OUT=O/'native';OUT.mkdir(exist_ok=False);gold,C,F=frozen_gold();DID='7bbe815ff43b6635'
ctx=gold.open_store(documents=[DID],seconds=1800,max_calls=10000);store,req,tr=ctx.__enter__()
from semantic_runtime import oracle_runtime_paths as paths
from semantic_runtime.oracle_agent_records import AgentRecords,RecordSQL
from semantic_runtime.ontology_work.store import OracleWorkStore
from semantic_runtime.ontology_work.domain_workflow import DomainWorkflow
from semantic_runtime.ontology_work.wiki_workspace import Workspace
from semantic_runtime.ontology_work import wiki_contracts as wc,runtime as ont_runtime
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent import gateway,errors
from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport,provider_request
from semantic_runtime.legal_agent.workflow_tiers_policy import profile as checked
from semantic_runtime.app import create_app
from semantic_runtime.provider import Haiku
from fastapi.testclient import TestClient
from lawrag.core import request_deadline
import lawrag
lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient
from lawrag.research.openrouter_legal_adapter import send_reserved
local=module('native_records',R/'06_TOOLS/EXPERIMENTS/adr_1244/test_records.py');admin=module('native_admin',R/'06_TOOLS/maintenance/agent_record_oracle_r2.py');pub=module('native_writer',R/'06_TOOLS/maintenance/publish_gold_ontology_samples.py')
started=time.monotonic();remaining=prior['overall_deadline_epoch']-time.time();assert remaining>0
record_db=admin.connection();rc=local.LocalOracle(record_db);sql=RecordSQL(rc,binding='adr1259-native',deadline=started+remaining,max_calls=10000-prior['shared_sql']['agent'])
records=AgentRecords(sql,namespace=os.environ['GENOS_ORACLE_AGENT_NAMESPACE']);paths.configure(lambda:records)
capacity=module('native_capacity',R/'06_TOOLS/EXPERIMENTS/adr_1254/safety.py').CapacityGuard(admin.connection(),OUT,reserve_bytes=1024**2,reference_quota=300*1024**2)
old_db=rc.request
def db_request(method,path,json):
 if json['statementText'].lstrip().startswith(('DECLARE ','BEGIN ')):capacity.sample(write=True)
 return old_db(method,path,json)
rc.request=db_request
repo=store.gold_ports.mapping.ontology_repository(pub.writer_connection,agent_owner='A8_GONT_AGENT',read_only=False);objects=OracleWorkStore(records);g=store.gold_ports.glossary_binding()
kwargs=dict(actor='adr1259-user-delegated',source_reader=store.gold_ports.source_reader,namespace=prior['scope']['namespace'],source_snapshot=prior['scope']['source_snapshot'],acl_ref=prior['scope']['acl_ref'],document_ids=[DID],producer_binding=F['candidate_revision']['revision_sha256'])
w=Workspace(repo,objects,can_publish=True,**kwargs);d=DomainWorkflow(repo,objects,glossary=g,**kwargs);d.can_publish_workspace=True
scopes=frozenset([wc.scope_key(w.scope())]);repo.workspace_scopes=scopes;store.gold_ports.ontology.workspace_scopes=scopes
transport=LocalQwen38Transport(C,R);profile=checked({**store.gold_profile,'model_binding':transport.binding,'max_output_tokens':transport.policy['max_output_tokens']},require_model=True)
assert profile['candidate_navigation']['ontology_enabled'] and profile['max_output_tokens'] is None
os.environ[read(C/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')['key_env']]=transport._key
client=ExperimentClient(C,OUT/'provider',max_calls=24-prior['external_model_calls'],max_repairs=0)
def compressed(self,path,value):
 if self._key in json.dumps(value,ensure_ascii=False):raise RuntimeError('credential in artifact')
 p=Path(path).with_suffix('.json.gz')
 if p.exists():p=p.with_name(p.stem+'-revision-'+str(self.calls)+'.gz')
 if p.exists():raise RuntimeError('duplicate usage revision')
 raw(p,value)
client._write=types.MethodType(compressed,client);stages=[];wire=[];active=[]
def send(*,body,ticket):
 if time.time()>=prior['overall_deadline_epoch']:raise ContractError('original overall deadline expired')
 return send_reserved(client,body=body,ticket=ticket,phase=active[-1] if active else 'native',error_module=errors,request_encoder=provider_request)
transport.send_once=send
old_generate=gateway.ModelGateway.generate;old_post=request_deadline.post_json
from engine_common import guard
initial=guard();initial_swap=initial['SwapTotal']-initial['SwapFree'];stop=threading.Event()
def checked_guard():
 v=guard()
 if v['SwapTotal']-v['SwapFree']-initial_swap>128*1024**2:raise RuntimeError('HOST_SWAP_GROWTH')
 if time.time()>=prior['overall_deadline_epoch']:raise RuntimeError('OVERALL_DEADLINE')
 return v
def monitor():
 with (OUT/'resources.jsonl').open('x',buffering=1) as f:
  while not stop.wait(1):
   try:f.write(json.dumps(checked_guard())+'\n')
   except Exception as e:put(OUT/'resource-stop.json',{'error':str(e)});os._exit(125)
def post(url,**kw):
 checked_guard();n=len(wire)+1;row={'number':n,'stage':active[-1] if active else None,'status':'SENT'};wire.append(row);put(OUT/'wire.json',wire);raw(OUT/'wire'/f'{n:03d}-request.json.gz',kw['json_body']);t=time.monotonic();print('NATIVE_MODEL',n,row['stage'],flush=True)
 try:
  response=old_post(url,**kw);body=response.json();raw(OUT/'wire'/f'{n:03d}-response.json.gz',body);row.update(status='RECEIVED',http_status=response.status_code,usage=body.get('usage'));return response
 except Exception as exc:
  row.update(status='UNKNOWN',error_type=type(exc).__name__)
  if hasattr(exc,'partial_body'):
   import base64
   raw(OUT/'wire'/f'{n:03d}-partial.json.gz',{'base64':base64.b64encode(exc.partial_body).decode()})
  raise
 finally:row['seconds']=time.monotonic()-t;put(OUT/'wire.json',wire)
def generate(self,phase,view,schema_name,**kw):
 n=len(stages)+1;row={'number':n,'phase':phase,'stage':view.get('source_stage',phase)};stages.append(row);active.append(row['stage']);raw(OUT/'canonical'/f'{n:03d}-input.json.gz',{'phase':phase,'view':view,'schema':self.protocol.schema(schema_name)})
 try:
  value=old_generate(self,phase,view,schema_name,**kw);raw(OUT/'canonical'/f'{n:03d}-output.json.gz',value);row['status']='ACCEPTED';return value
 except Exception as exc:row.update(status='REJECTED',error=str(exc));raise
 finally:active.pop();put(OUT/'stages.json',stages)
request_deadline.post_json=post;gateway.ModelGateway.generate=generate
runtime=paths.Path(os.environ['GENOS_RUNTIME_DIR']);result={'strict_success':False,'gates':{}};watcher=threading.Thread(target=monitor,daemon=True)
try:
 checked_guard();capacity.sample();records.preflight();watcher.start()
 c=prior['compiled'];d.review(c['bundle_id'],c['revision'],c['work_hash'],True,review['reason']);staged=d.stage_publication(c['bundle_id'],c['revision'],c['work_hash'],0);receipt=d.verify_publication(staged['publication_id']);d.activate_publication(staged['publication_id'],0,receipt);pid=staged['publication_id'];put(OUT/'publication.json',{'staged':staged,'receipt':receipt})
 package=repo.publication(pid,[DID]);result['gates']['review_and_activation']=True
 originals=read(D/'originals.json');found=[]
 for s in originals:found.extend(store.gold_ports.ontology.lookup(s['anchor'],{DID}))
 assert any(row['publication_id']==pid for row in found);result['gates']['oracle_runtime_visibility']=True
 app=create_app(runtime,None,contracts_root=C,release={'mode':'research-adr1259','quality_certified':False},provider=Haiku(C,runtime/'provider',False,backend='source-only',trust_zone='internal'),vector=False,implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=transport,workspace_root=R,runtime_root=runtime,data_store=store,memory_identity=lambda request:{'user_id':'adr1259','team_id':'risk_team','document_ids':[DID]})
 with TestClient(app) as http:
  assert http.get('/health').status_code==200
  question={'question':'상법 제369조 제1항과 제2항에 따르면 1주당 의결권 수는 몇 개이고, 회사가 가진 자기주식에 의결권이 있나요?','document_ids':[DID],'use_llm':True,'public_question':True}
  put(OUT/'request.json',question);response=http.post('/v1/rag/ask',json=question);body=response.json();raw(OUT/'response.json.gz',{'http_status':response.status_code,'body':body});result['http_status']=response.status_code
  assert response.status_code==200 and body.get('answer'),'native final answer missing'
  text=body['answer'].get('text','') if isinstance(body['answer'],dict) else str(body['answer']);(OUT/'answer.txt').write_text(text);assert text.strip()
  delivered=[str(p.relative_to(R)) for p in (OUT/'wire').glob('*-request.json.gz') if pid in gzip.decompress(p.read_bytes()).decode()]
  assert delivered,'workspace publication never reached actual model wire'
  result['gates']['native_answer_and_workspace_delivery']=True;result['delivered_in']=delivered
  result['answer']=text
 # Withdraw this trial publication through the same workspace operation and test old references.
 refs={'assessment_basis':{'workspace_publications':[{'bundle_id':c['bundle_id'],'publication_id':pid,'package_sha256':package['package_sha256']}]}}
 ont_runtime.assert_assessment(refs,{DID},repo)
 sid=prior['statements'][0];item=w.item(sid);w.apply(change_id='verified-test-withdrawal',expected={sid:{k:item[k] for k in ('revision','work_hash')}},operations=[{'op':'RETRACT','target':sid,'value':{'reason':'전 과정 검증 완료 후 시험 게시 회수'}}])
 try:ont_runtime.assert_assessment(refs,{DID},repo)
 except ContractError as exc:assert 'REVOKED' in str(exc)
 else:raise AssertionError('withdrawn answer basis accepted')
 assert not repo.head(c['bundle_id'])['publication_id'];result['gates']['withdrawal_replay_guard']=True
 result['strict_success']=all(result['gates'].values());result['status']='COMPLETE'
except Exception as exc:result.update(status='FAILED',error_type=type(exc).__name__,error=str(exc));(OUT/'error.txt').write_text(traceback.format_exc())
finally:
 stop.set()
 if watcher.is_alive():watcher.join(timeout=2)
 request_deadline.post_json=old_post;gateway.ModelGateway.generate=old_generate
 result.update(seconds=time.monotonic()-started,physical_calls=len(wire),total_physical_calls=prior['external_model_calls']+len(wire),unknown=sum(r['status']=='UNKNOWN' for r in wire),source_sql_calls=req.sql.calls,agent_sql_calls=sql.calls,agent_sql_errors=rc.errors)
 put(OUT/'result.json',result);raw(OUT/'source-sql.json.gz',tr.statements);capacity.close();record_db.close();g.reader.close();ctx.__exit__(None,None,None);print(json.dumps(result,ensure_ascii=False),flush=True)
