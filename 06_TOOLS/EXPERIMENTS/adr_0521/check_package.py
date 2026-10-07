"""Read-only integration using staged serving code and the complete new generation."""
import json,sys,time
from pathlib import Path
R=Path.cwd();A=R/'04_EXPERIMENTS/ADR/ADR-0521-shared-reference-root-workflow'
m=json.loads((A/'artifacts/review-package.json').read_text());code=R/m['code_root'];sys.path.insert(0,str(code/'02_BACKEND'))
from semantic_runtime.contracts import sha,write
for f,h in m['files'].items():assert sha(code/f)==h
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import workflow_tiers_protocol
started=time.monotonic();profile=json.loads((code/'00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json').read_text());profile['model_binding']=None
assert 'maxItems' not in workflow_tiers_protocol.schema('FinalSourceBundle')['properties']['sources']
generation=R/'01_DATA/TERM_RELEASES/adr0521-shared-reference-v1/generation'
app=create_app(code,generation,contracts_root=code,provider=object(),workspace_root=R,runtime_root=A/'artifacts/source-only-runtime',legal_agent_profile=profile)
p=app.state.pipeline
try:
 plan=p.plan('전체 문서 목록');result=p.retrieve(plan,False)
 report={'status':'PASS','package_manifest_sha256':sha(A/'artifacts/review-package.json'),'generation_manifest_sha256':sha(generation/'manifest.json'),'loaded_app':__import__('semantic_runtime.app',fromlist=['']).__file__,'profile':p.profile_id,'source_only_profile_override':{'model_binding':None},'real_model_called':False,'http_transport_tested':False,'documents':p.store.db.execute('SELECT count(*) FROM document').fetchone()[0],'retrieval_keys':list(result),'seconds':time.monotonic()-started,'active_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==m['active_sha256']}
 write(A/'artifacts/package-check.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)
finally:p.store.close()
