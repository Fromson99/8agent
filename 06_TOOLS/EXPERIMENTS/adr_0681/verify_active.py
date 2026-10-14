"""Read fresh actual MAIN entry and unsigned validation without model calls."""
from pathlib import Path
import json,hashlib,sys,os,asyncio,importlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0681-session-runtime-no-user-wiki-signing'
sys.dont_write_bytecode=True;sys.path[:0]=[str(R),str(R/'02_BACKEND')]
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['release_id']=='session-runtime-v6-20261007-r1'
m=read(R/p['manifest_path']);d=read(A/'artifacts/design/release-rebase.json');assert m['files']==d['staged_files']
for f,h in m['files'].items():assert sha(R/m['code_root']/f)==h,f
for k in ('GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RUNTIME_DIR','GENOS_RAG_IMPLEMENTATION'):assert not os.getenv(k),'Actual local MAIN smoke needs its default environment'
os.environ.pop('GENOS_MEMORY_SIGNING_KEY',None)
import service
actual=importlib.import_module('service.service');assert service is actual
app=actual.application();package=app.state.pipeline.__class__.__module__.rsplit('.',1)[0]
identity=importlib.import_module(package+'.legal_agent.memory_identity')
assert not hasattr(identity,'signed_bytes') and not hasattr(identity,'verify_assertion')
body={'memory':True,'user_id':'smoke-user','team_id':'risk_team','session_id':'smoke-session','request_id':'smoke-request','question':'모의 세션 연결 검사'}
assert identity.validate_session(body)=={'user_id':'smoke-user','team_id':'risk_team'}
normalized=actual._normalize({'API_TYPE':'LEGAL_AGENT',**body,'memory_authorization':{'signature':'obsolete'}})
assert normalized['json']==body
async def check():
 h=await actual.service({}, {'API_TYPE':'HEALTH'});assert h['status']==200,h
 s=await actual.service({}, {'API_TYPE':'RAG_SEARCH','q':'상법 제4조','doc_id':'7bbe815ff43b6635','limit':3});assert s['status']==200,s
 return h,s
h,s=asyncio.run(check());binding=h['body']['release']
assert binding['release_id']==p['release_id'] and binding['generation']==p['generation']
assert binding['release_manifest_sha256']==p['release_manifest_sha256']
assert binding['profile_sha256']==sha(R/m['code_root']/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
assert binding['data_manifest_sha256']==m['data_manifest_sha256']
assert isinstance(s['body'].get('candidates'),list),s
receipt={'status':'passed','environment':'fresh WSL local MAIN process','entrypoint':'service.service','pointer':p,'execution_binding':binding,'health_status':h['status'],'search_status':s['status'],'search_candidates':len(s['body']['candidates']),'unsigned_identity_and_normalization':True,'signing_key_present':False,'model_calls':0,'exact_candidate_release_match':True,'genos_deployed':False,'resident_server_restarted':False,'limitations':['Real default selected source/entry verified by HEALTH and RAG_SEARCH; full session mutation exercised on synthetic generation in the 30 contract tests','Pending unrelated working code is preserved separately from the selected release']}
put(A/'artifacts/main-smoke.json',receipt)
print(json.dumps({k:receipt[k] for k in ('status','entrypoint','health_status','search_status','unsigned_identity_and_normalization')},ensure_ascii=False))
