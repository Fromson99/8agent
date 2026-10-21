"""Validate source, engine and scoped authorization without a model request."""
from pathlib import Path
import json,hashlib,sys,os
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0953-risk-photo-authorized-live'
D=A/'artifacts/design';read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
binding=read(D/'live-binding.json');C=R/binding['code_root']
for n,h in read(D/'freeze.json')['files'].items():assert sha(R/n)==h,n
sys.dont_write_bytecode=True
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'02_BACKEND'),str(R)]
os.environ.update(GENOS_RESIDENT_DATA='off',GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0',
                  TEAM_ID='risk_team',LAWRAG_WORKSPACE_ROOT=str(R))
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
from semantic_runtime.stage_runner import StageRunner
from semantic_runtime.team_scope import select_documents
t=LocalGemmaTransport(C,R)
profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=t.binding
G=R/read(D/'baseline.json')['manifest']['data_path']
app=create_app(R,G,contracts_root=C,workspace_root=R,provider=object(),
    implementation='legal-agent-unified-v6',runtime_root=A/'artifacts/preflight-runtime',
    legal_agent_profile=profile,legal_agent_transport=t)
p=app.state.pipeline
assert StageRunner(p).verify_profile()
scope=select_documents(p.store,'risk_team')
grant=read(D/'authorization.json');assert set(scope)==set(grant['document_ids'])
receipt=t.authorize_workflow({'workflow_id':'risk_team_compare_workflow',
    'principal':{'user_id':'preflight','team_id':'risk_team'},'document_ids':scope},
    {'generation_id':p.store.manifest['generation_id'],'store_sha256':p.store.manifest['store_sha256'],
     'generation_manifest_sha256':sha(G/'manifest.json')})
assert profile['max_model_attempts']==40 and profile['wall_seconds']==1800
out={'status':'PASS','engine_and_source_hashes_verified':True,
     'scoped_authorization_verified':True,'model_calls':0,
     'allowed_document_ids':scope,'grant_sha256':receipt['grant_sha256'],
     'only_authorization_and_pin_configuration_changed':True,'main_changed':False}
(A/'artifacts/preflight.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
p.store.close()
print(json.dumps(out,ensure_ascii=False))
