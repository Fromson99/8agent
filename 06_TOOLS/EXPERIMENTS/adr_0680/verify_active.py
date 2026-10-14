"""Fresh real service.service process after qualified local MAIN activation."""
from pathlib import Path
import asyncio,hashlib,importlib,importlib.util,json,os,sqlite3,sys,uuid
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0680-investigation-main-consumer-integration'
sys.path.insert(0,str(R));sys.path.insert(0,str(R/'02_BACKEND'));sys.dont_write_bytecode=True
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['release_id']=='investigation-completion-v6-20261007-r1'
assert p['deployment_basis']=='VALIDATED_ADR_PROMOTION'
manifest=read(R/p['manifest_path']);rebase=read(A/'artifacts/design/release-rebase.json')
assert manifest['files']==rebase['staged_files']
code=R/manifest['code_root'];generation=R/manifest['data_path']
for path,h in manifest['files'].items():assert sha(code/path)==h,path
for path,h in manifest['files'].items():assert sha(R/path)==h,path
for name in ('GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_LLM_KEY','GENOS_LLM_URL','GENOS_LLM_SERVING_ID','GENOS_RAG_IMPLEMENTATION'):
 assert not os.environ.get(name), 'Local MAIN smoke requires local gateway environment'
assert not os.environ.get('GENOS_RUNTIME_DIR'), 'Verify the real configured default local runtime'
import service
s=importlib.import_module('service.service');assert s is service
app=s.application();module=importlib.import_module(app.state.pipeline.__class__.__module__.rsplit('.',1)[0]+'.legal_agent.local_gemma')
spec=importlib.util.spec_from_file_location('audited_main_experiment_client',R/'02_BACKEND/lawrag/research/experiment_client.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit);ExperimentClient=audit.ExperimentClient
client=ExperimentClient(R,A/'artifacts/main-smoke-provider',max_calls=40,max_output_tokens=6400,max_repairs=0)
transport=app.state.pipeline.term_agent.transport
def send_once(*,body,ticket):
 result=client.chat_completions(module.provider_request(body),phase='live-main-'+str(client.calls+1),timeout_seconds=ticket['remaining_seconds'])
 assert result['body_json'].get('provider')=='Parasail' and result['body_json'].get('model')==transport.binding['model']
 return result
transport.send_once=send_once
identifier='main-investigation-'+uuid.uuid4().hex
body={'question':'상법상 대표이사는 누가 선정하고 정관으로 달리 정할 수 있나요?','document_ids':list(transport.public_scope),
 'public_question':True,'use_llm':True}
async def execute():
 health=await s.service({}, {'API_TYPE':'HEALTH'});assert health['status']==200,health
 search=await s.service({}, {'API_TYPE':'RAG_SEARCH','q':'상법 제4조','doc_id':'7bbe815ff43b6635','limit':10});assert search['status']==200,search
 result=await s.service({}, {'API_TYPE':'RAG_ASK','json':body});put(A/'artifacts/main-smoke-response.json',result)
 assert result['status']==200,result
 return health,search,result
health,search,result=asyncio.run(execute());out=result['body'];binding=health['body']['release'];assert out['release']==binding
expected={'mode':'local-release','release_id':p['release_id'],'generation':p['generation'],
 'release_manifest_sha256':p['release_manifest_sha256'],'code_sha256':digest(manifest['files']),
 'profile_sha256':sha(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),
 'data_manifest_sha256':manifest['data_manifest_sha256'],'source_generation_id':read(generation/'manifest.json')['generation_id'],
 'fulltext_manifest_sha256':read(generation/'manifest.json')['fulltext']['manifest_sha256'],
 'schema_sha256':digest({x:h for x,h in manifest['files'].items() if x.startswith('00_SYSTEM/SCHEMAS/')}),
 'search_policy_sha256':digest({'directory_order':'best-own-block-match-v1','candidate_navigation':read(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')['candidate_navigation']}),
 'process_id':os.getpid()}
for key,v in expected.items():assert binding[key]==v,(key,binding.get(key),v)
assert binding['process_instance_id']
meta=out['assembly']['term_agent'];assert app.state.pipeline.term_agent.profile['candidate_navigation']['completion_contract'] is True
assert app.state.pipeline.term_agent.profile['max_transport_retries']==1
assert meta['control_contract']=='investigation-control-v2' and meta['investigation_chain']
runtime=R/'90_RUNTIME/semantic';paths=list((runtime/'legal-agent/runs').glob('*/'+out['run_id']+'/journal.sqlite'));assert len(paths)==1
db=sqlite3.connect(paths[0]);native=json.loads(db.execute("SELECT payload_json FROM entity_version WHERE kind='case_stage' AND entity_id='case:READ' ORDER BY created_seq DESC LIMIT 1").fetchone()[0])['binding'];db.close()
evaluation=read(A/'artifacts/binding-check/expected.json')['binding']
for key in ('code','configuration','generation','pipeline','profile','store_sha256','unit_index_sha256','catalogue_hash','method_policy_hash'):
 assert native[key]==evaluation[key],(key,native[key],evaluation[key])
report={'status':'passed','entrypoint':'service.service','process_id':os.getpid(),'pointer':p,
 'execution_binding':binding,'expected_binding':expected,'native_binding':native,'evaluation_binding':evaluation,
 'same_working_candidate_release_files':True,'service_health_status':health['status'],'search_status':search['status'],
 'question':body['question'],'answer':out['answer']['text'],'investigation_id':out.get('investigation_id'),'run_id':out['run_id'],
 'answer_coverage':meta['answer_coverage'],'issue_assessments':meta['issue_assessments'],'model_calls':client.calls,
 'usage':client.usage,'runtime':str(runtime),'resident_server_restarted':False,'genos_deployed':False}
put(A/'artifacts/main-smoke.json',report);print(json.dumps({k:report[k] for k in ('status','entrypoint','process_id','model_calls','answer_coverage')},ensure_ascii=False))
