from pathlib import Path
import asyncio,hashlib,importlib,json,os,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0774-assessment-gap-action-main';read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['release_id']=='assessment-gap-action-20261013-r1' and p['generation']==60
m=read(R/p['manifest_path']);f=read(A/'artifacts/design/freeze.json');assert m['files']==f['serving_files']
for n,h in m['files'].items():assert sha(R/m['code_root']/n)==h,n
for k in ('GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RUNTIME_DIR'):assert not os.environ.get(k),k
os.environ['AD_WORKER_ENABLED']='0';sys.dont_write_bytecode=True;sys.path[:0]=[str(R),str(R/'02_BACKEND')]
import service
actual=importlib.import_module('service.service');app=actual.application();package=app.state.pipeline.__class__.__module__.rsplit('.',1)[0]
cc=importlib.import_module(package+'.legal_agent.completion_contracts');v6=importlib.import_module(package+'.legal_agent.completion_v6');success=importlib.import_module(package+'.legal_agent.successful_answer')
assert Path(cc.__file__).resolve()==R/m['code_root']/'02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py'
raw={'gaps':[{'kind':'MISSING_SOURCE','suggested_action':'REQUEST_FACT','issue_id':'Q1','reason':'synthetic','material':True,'material_id':None,'missing_target':'모의 대상'},{'kind':'MISSING_FACT','suggested_action':'REQUEST_FACT','issue_id':'Q2','reason':'synthetic user fact','material':True,'material_id':None,'missing_target':''}]}
fixed,audit=cc.source_gap_actions(raw);assert [g['suggested_action'] for g in fixed['gaps']]==['RESEARCH','REQUEST_FACT'];assert len(audit)==1 and raw['gaps'][0]['suggested_action']=='REQUEST_FACT'
assert v6.cc.source_gap_actions is cc.source_gap_actions
async def request():return await actual.service({}, {'API_TYPE':'HEALTH','request_id':'gap-main60-health'}),await actual.service({}, {'API_TYPE':'RAG_SEARCH','q':'상법 제4조','doc_id':'7bbe815ff43b6635','limit':3,'request_id':'gap-main60-search'})
health,search=asyncio.run(request());assert health['status']==search['status']==200
binding=health['body']['release'];assert binding['release_id']==p['release_id'] and binding['generation']==60 and binding['release_manifest_sha256']==p['release_manifest_sha256'];assert binding['data_manifest_sha256']==m['data_manifest_sha256']
receipt={'status':'PASS','environment':'fresh WSL local service.service','pointer':p,'execution_binding':binding,'health_status':200,'search_status':200,'selected_gap_module':str(Path(cc.__file__).relative_to(R)),'actual_gap_correction':audit,'fact_action_preserved':True,'selected_success_policy':success.POLICY,'selected_files_verified':len(m['files']),'data_unchanged':m['data_path']==read(A/'artifacts/design/baseline.json')['manifest']['data_path'],'model_calls':0,'genos_deployed':False}
(A/'artifacts/main-service-smoke.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))
