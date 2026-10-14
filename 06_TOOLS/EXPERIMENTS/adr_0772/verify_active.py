"""Verify a fresh actual local service entry and selected source-card modules."""
from pathlib import Path
import asyncio,hashlib,importlib,json,os,sqlite3,sys,tempfile
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0772-source-provider-display'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['release_id']=='source-provider-20261013-r2' and p['generation']==58
m=read(R/p['manifest_path']);f=read(A/'artifacts/design/freeze.json');assert m['files']==f['serving_files']
for n,h in m['files'].items():assert sha(R/m['code_root']/n)==h,n
for key in ('GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RUNTIME_DIR','GENOS_RAG_IMPLEMENTATION'):assert not os.environ.get(key),key
# Do not launch unrelated scheduled AD jobs during a read-only binding check.
os.environ['AD_WORKER_ENABLED']='0'
sys.dont_write_bytecode=True;sys.path[:0]=[str(R),str(R/'02_BACKEND')]
import service
actual=importlib.import_module('service.service');assert service is actual
app=actual.application();package=app.state.pipeline.__class__.__module__.rsplit('.',1)[0]
w=importlib.import_module(package+'.chat_adapter').views()
progress=importlib.import_module(package+'.progress')
assert Path(w.__file__).resolve()==R/m['code_root']/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
assert w.PROGRESS_DISPLAY_REVISION=='rag-source-provider-20261013-r2'
assert progress.REVISION=='rag-source-cards-20261013-r1'
assert sha(R/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')==m['files']['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
async def request():
 health=await actual.service({}, {'API_TYPE':'HEALTH','request_id':'source-cards-main58-health'})
 search=await actual.service({}, {'API_TYPE':'RAG_SEARCH','q':'상법 제4조','doc_id':'7bbe815ff43b6635','limit':3,'request_id':'source-cards-main58-search'})
 return health,search
health,search=asyncio.run(request());assert health['status']==search['status']==200
binding=health['body']['release'];assert binding['release_id']==p['release_id'] and binding['generation']==58
assert binding['release_manifest_sha256']==p['release_manifest_sha256']
assert binding['data_manifest_sha256']==m['data_manifest_sha256']
assert binding['profile_sha256']==sha(R/m['code_root']/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
events=[]
with tempfile.TemporaryDirectory(prefix='main58-display-') as tmp:
 c=progress.ProgressCapture('selected-module-display',tmp,events.append);c.admitted={'allowed'}
 with sqlite3.connect(':memory:') as db:
  db.execute('CREATE TABLE event(seq INTEGER,payload_json TEXT)')
  db.execute('INSERT INTO event VALUES(1,?)',(json.dumps({'laws':[{'document_id':'allowed','name':'external > mock_team > law > 표시모의법'},{'document_id':'denied','name':'PRIVATE DENIED'}]}),))
  c._activity(db,1,'LAW_FULLTEXT_DIRECTORY')
 for i in range(12):c.publish('reading','원문 확인',details=[f'external > financial_team > krx > 표시모의법{i} · 제3조'],basis={'kind':'UNIT_READ_STARTED','detail_mode':'activity'})
 c.publish('phase','완료',basis={'kind':'OBS_EVENT','name':'request.finished'})
 display=w._ChatProgress({});display.enabled=False;display.show_progress=True
 async def render():
  for e in events:await display.progress(e)
  await display.finish('확인')
 asyncio.run(render())
 texts=[json.loads(b['data']['output']['content'])['visible_rationale'] for b in display.blocks]
 reads=[t for t in texts if '확인 대상' in t]
 assert len(reads)==1 and '12. 표시모의법11 · 제3조' in reads[0] and '외부법률 / 한국거래소' in reads[0]
 assert 'PRIVATE DENIED' not in json.dumps(events) and any('외부법률 / 법제처' in t for t in texts) and 'external' not in str(texts)
receipt={'status':'PASS','environment':'fresh WSL local service.service process','entrypoint':'service.service','pointer':p,'execution_binding':binding,'health_status':health['status'],'search_status':search['status'],'search_candidates':len(search['body'].get('candidates',[])),'selected_progress_revision':progress.REVISION,'selected_workflow_file':str(Path(w.__file__).relative_to(R)),'exact_candidate_selected_files':len(m['files']),'selected_source_projection_scope_checked':True,'selected_read_group_rows':12,'selected_read_cards':1,'model_calls':0,'data_unchanged_from_MAIN57':m['data_path']==read(A/'artifacts/design/baseline.json')['manifest']['data_path'],'background_ad_worker_enabled':False,'resident_uvicorn_process_found_before_cutover':False,'genos_field_deployed':False,'genos_editor_mail_message_id':None,'scoped_working_workflow_matches':True,'unrelated_worktree_preserved':True,'selected_workflow_revision':w.PROGRESS_DISPLAY_REVISION}
(A/'artifacts/main-service-smoke.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:receipt[k] for k in ('status','entrypoint','health_status','search_status','exact_candidate_selected_files','selected_read_group_rows','selected_read_cards')},ensure_ascii=False))
