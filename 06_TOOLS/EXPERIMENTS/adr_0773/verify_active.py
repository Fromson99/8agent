from pathlib import Path
import asyncio,hashlib,importlib,json,os,sys,tempfile
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0773-successful-shortcut-publication';read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['release_id']=='successful-shortcut-20261013-r1' and p['generation']==59
m=read(R/p['manifest_path']);f=read(A/'artifacts/design/freeze.json');assert m['files']==f['serving_files']
for n,h in m['files'].items():assert sha(R/m['code_root']/n)==h,n
for k in ('GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RUNTIME_DIR'):assert not os.environ.get(k),k
os.environ['AD_WORKER_ENABLED']='0';sys.dont_write_bytecode=True;sys.path[:0]=[str(R),str(R/'02_BACKEND')]
import service
actual=importlib.import_module('service.service');app=actual.application();package=app.state.pipeline.__class__.__module__.rsplit('.',1)[0]
s=importlib.import_module(package+'.legal_agent.successful_answer');ad=importlib.import_module(package+'.ad_mode')
assert Path(s.__file__).resolve()==R/m['code_root']/'02_BACKEND/semantic_runtime/legal_agent/successful_answer.py'
async def request():return await actual.service({}, {'API_TYPE':'HEALTH','request_id':'shortcut-main59-health'}),await actual.service({}, {'API_TYPE':'RAG_SEARCH','q':'상법 제4조','doc_id':'7bbe815ff43b6635','limit':3,'request_id':'shortcut-main59-search'})
health,search=asyncio.run(request());assert health['status']==search['status']==200
binding=health['body']['release'];assert binding['release_id']==p['release_id'] and binding['generation']==59 and binding['release_manifest_sha256']==p['release_manifest_sha256'];assert binding['data_manifest_sha256']==m['data_manifest_sha256']
with tempfile.TemporaryDirectory() as tmp:
 db=Path(tmp)/'cases.sqlite';ad.handle(db,'t','test','s',ad.ENTER,'enter')
 value=ad.handle(db,'t','test','s','shortcut 보여줘','list',interpret=lambda *_:{'plan':{'action':'list','args':{'kind':'shortcut','query':''}},'receipt':{'provider':'genos','trust_zone':'internal','model':'synthetic'},'raw':{}})
 assert value['answer_status']=='administration',value
 assert '0' in value['text']
receipt={'status':'PASS','environment':'fresh WSL local service.service','pointer':p,'execution_binding':binding,'health_status':200,'search_status':200,'selected_success_policy':s.POLICY,'selected_ad_module':str(Path(ad.__file__).relative_to(R)),'selected_files_verified':len(m['files']),'data_unchanged':m['data_path']==read(A/'artifacts/design/baseline.json')['manifest']['data_path'],'model_calls':0,'genos_deployed':False}
(A/'artifacts/main-service-smoke.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))
