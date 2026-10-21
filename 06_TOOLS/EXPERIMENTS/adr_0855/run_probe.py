"""Read-only MAIN82 fulltext/schema audit; no product policy or prompt changes."""
from pathlib import Path
import asyncio, copy, gzip, hashlib, importlib, importlib.util, json, os, sys, time, traceback
import jsonschema
R=Path(__file__).resolve().parents[3]; A=R/'04_EXPERIMENTS/ADR/ADR-0855-fulltext-schema-live-audit-v2'
sys.dont_write_bytecode=True
sys.path[:0]=[str(R),str(R/'02_BACKEND')]
read=lambda p:json.loads(p.read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def gz(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(p,'wt',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,separators=(',',':'))
def size(v):return len(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode())
f=read(A/'artifacts/design/frozen.json');run=sys.argv[1];case=next(c for c in f['cases'] if c['run_id']==run)
for p,h in f['bindings'].items():assert sha(R/p)==h,p
D=A/'artifacts'/run;D.mkdir(exist_ok=False)
for name in ('GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_LLM_KEY','GENOS_LLM_URL','GENOS_LLM_SERVING_ID','GENOS_RAG_IMPLEMENTATION','DP'):
 assert not os.environ.get(name),'Local audit requires no GENOS binding'
os.environ.update(GENOS_RUNTIME_DIR=str(D/'runtime'),AD_WORKER_ENABLED='0',GENOS_SYSTEM_LOG_ENABLED='0',GENOS_AUTO_WARMUP='0')
svc=importlib.import_module('service.service');app=svc.application();p=app.state.pipeline
pkg=p.__class__.__module__.rsplit('.',1)[0]
local=importlib.import_module(pkg+'.legal_agent.local_gemma');gateway=importlib.import_module(pkg+'.legal_agent.gateway')
assert Path(local.__file__).resolve().is_relative_to(R/f['release']['code_root'])
spec=importlib.util.spec_from_file_location('audited_client_855',R/'02_BACKEND/lawrag/research/experiment_client.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
client=audit.ExperimentClient(R,D/'provider',max_calls=40,max_output_tokens=6400,max_repairs=0)
transport=p.term_agent.transport
body={'question':case['question'],'document_ids':sorted(transport.public_scope),'public_question':True,'use_llm':True}
put(D/'request.json',body);put(D/'profile.json',p.term_agent.profile)
model_records=[];generations=[];active=[]
original=gateway.ModelGateway.generate

def generate(self,phase,view,schema_name,**kwargs):
 number=len(generations)+1;record={'number':number,'phase':phase,'stage':view.get('source_stage',phase),'schema_name':schema_name}
 generations.append(record);active.append(record)
 schema=self.protocol.schema(schema_name)
 gz(D/'canonical'/f'{number:03d}.json.gz',{'view':view,'schema':schema,'phase':phase,'schema_name':schema_name})
 record['canonical_schema_bytes']=size(schema)
 try:
  jsonschema.Draft202012Validator.check_schema(schema);record['canonical_schema_valid']=True
  result=original(self,phase,view,schema_name,**kwargs)
  record['accepted']=True;gz(D/'canonical'/f'{number:03d}-output.json.gz',result)
  return result
 except Exception as e:
  record.update(accepted=False,error_type=type(e).__name__,error=str(e));raise
 finally:
  active.pop();put(D/'generations.json',generations)
gateway.ModelGateway.generate=generate

def send_once(*,body,ticket):
 n=client.calls+1;stage=active[-1]['stage'] if active else 'unknown'
 wire=local.provider_request(body);schema=body['response_format']['json_schema']['schema'];provider_schema=wire['response_format']['json_schema']['schema']
 rec={'call':n,'stage':stage,'canonical_generation':active[-1]['number'] if active else None,'request_bytes':size(body),'response_format_bytes':size(body['response_format']),'schema_bytes':size(schema),'provider_schema_bytes':size(provider_schema),'messages_bytes':size(body['messages'])}
 model_records.append(rec);gz(D/'wire'/f'{n:03d}-before-provider.json.gz',body)
 for s in (schema,provider_schema):jsonschema.Draft202012Validator.check_schema(s)
 rec['schemas_valid']=True;put(D/'calls.json',model_records)
 print('MODEL_START',run,n,stage,'schema_bytes='+str(rec['schema_bytes']),flush=True);start=time.monotonic()
 try:
  result=client.chat_completions(wire,phase='product-'+str(n),timeout_seconds=ticket['remaining_seconds'])
  raw=result['body_json'];content=raw['choices'][0]['message']['content'];value=json.loads(content)
  rec.update(http_status=result['status_code'],output_bytes=len(content.encode()),raw_output_schema_errors=[e.message for e in jsonschema.Draft202012Validator(provider_schema).iter_errors(value)])
  result['response_bytes']=size(raw)
  print('MODEL_DONE',run,n,round(time.monotonic()-start,2),flush=True)
  return result
 except audit.ExperimentTransportError as e:
  rec.update(error_type=type(e).__name__,error=str(e))
  raise gateway.TransportError(str(e),retryable=e.retryable,unknown=e.unknown) from e
 except audit.ExperimentProviderError as e:
  rec.update(error_type=type(e).__name__,error=str(e),http_status=(e.response or {}).get('status_code'))
  raise gateway.TransportError(str(e),retryable=e.retryable,unknown=(e.response or {}).get('status_code',500)>=500) from e
 except Exception as e:
  rec.update(error_type=type(e).__name__,error=str(e));raise
 finally:
  rec['seconds']=time.monotonic()-start;put(D/'calls.json',model_records)
transport.send_once=send_once
start=time.monotonic();result={'run_id':run,'arm':'baseline','case_id':case['case_id'],'environment':'WSL local selected MAIN82','entrypoint':'service.service','pointer_before':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'genos_execution':False}
async def execute():
 health=await svc.service({}, {'API_TYPE':'HEALTH'});put(D/'health.json',health)
 assert health['status']==200 and health['body']['release']['generation']==82
 result['execution_binding']=health['body']['release']
 # Same selected index and ACL, read-only search before model request. This is an
 # independent technical preflight; it supplies no context or state to the ask.
 from importlib import import_module
 lc=import_module(pkg+'.legal_agent.law_candidates');ft=import_module(pkg+'.fulltext')
 with p.term_agent.open_session(body,query=p.plan(body['question'],body['document_ids']),runtime=D/'preflight-runtime',external_public_question=True) as session:
  s=session.sources;idx,db=lc.index(s);terms=ft.question_terms(case['fulltext_query']);allowed=lc.allowed(s)
  tick=time.monotonic();laws=idx.law_groups_page(db,terms,allowed,limit=12);samples=[]
  for law in laws['items']:
   articles=idx.article_groups_page(db,terms,law['document_id'],allowed,limit=4)
   for article in articles['items']:
    hits=idx.hit_page(db,terms,article['source_id'],allowed,limit=1)
    samples.extend({'document_id':h['document_id'],'source_id':h['source_id'],'unit_id':h['unit_id'],'has_text':bool(h.get('text'))} for h in hits['items'])
  put(D/'fulltext-preflight.json',{'schema':idx.manifest['schema_version'],'index_class':type(idx).__name__,'index_sha256':idx.manifest['index_sha256'],'terms':terms,'law_page':laws,'sample_hits':samples,'allowed_article_roots':len(allowed),'seconds':time.monotonic()-tick,'no_model_input_injection':True})
 print('ASK_START',run,flush=True)
 response=await svc.service({}, {'API_TYPE':'RAG_ASK','json':body});put(D/'response.json',response)
 result['http_status']=response['status']
try:asyncio.run(execute())
except Exception as e:
 result.update(exception_type=type(e).__name__,exception=str(e));(D/'error.txt').write_text(traceback.format_exc())
finally:
 result.update(seconds=time.monotonic()-start,model_calls=client.calls,usage=client.usage,pointer_after=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'))
 put(D/'result.json',result);put(D/'calls.json',model_records);put(D/'generations.json',generations)
 print('RESULT',json.dumps({k:v for k,v in result.items() if k not in ('usage','execution_binding')},ensure_ascii=False),flush=True)
