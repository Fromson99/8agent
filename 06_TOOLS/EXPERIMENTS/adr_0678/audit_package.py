"""Verify exactly the future serving projection through the service gateway."""
from pathlib import Path
import hashlib,json,sys,importlib.util,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0678-investigation-contract-completion';D=A/'artifacts/design';O=A/'artifacts/package-001';O.mkdir(exist_ok=False)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'bindings.json');r=read(D/'release-rebase.json');stage=R/r['stage'];checks={}
for seal in ['freeze.json','release-freeze.json']:
 for p,h in read(D/seal)['files'].items():assert sha(R/p)==h,p
checks['all_frozen_hashes_match']=True
for p,h in r['staged_files'].items():assert sha(stage/p)==h,p
checks['exact_serving_projection_matches']=True
config=read(stage/'00_SYSTEM/PIPELINE.json');edges=[]
for key,e in config['engines'].items():
 assert sha(stage/e['manifest'])==e['sha256'],key
 for p,h in read(stage/e['manifest'])['files'].items():assert sha(stage/p)==h,(key,p);edges.append([key,p,h])
checks['all_configured_engine_dependencies_present']=True
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('frozen_staged_service',stage/'service.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s);s._ROOT=R
s._resolve_binding=lambda:(stage,R/b['source_generation'],{'mode':'local-release','release_id':'frozen-investigation-stage','generation':43})
os.environ['GENOS_RUNTIME_DIR']=str(O/'runtime');app=s.application()
from fastapi.testclient import TestClient
from importlib import import_module
profile=import_module(app.state.pipeline.__class__.__module__.rsplit('.',1)[0]+'.stage_runner').StageRunner(app.state.pipeline).verify_profile();checks['service_selected_profile_verifies']=True
assert app.state.pipeline.term_agent.profile['candidate_navigation']['completion_contract'] is True
assert app.state.pipeline.term_agent.profile['max_transport_retries']==1
checks['service_investigation_control_enabled']=True
with TestClient(app) as api:
 h=api.get('/health');assert h.status_code==200,h.text
 search=api.get('/v1/rag/search',params={'q':'상법 제4조','doc_id':'7bbe815ff43b6635','limit':10});assert search.status_code==200,search.text
 denied=api.post('/v1/rag/memory/query',json={'query_kind':'investigations','session_id':'untrusted','request_id':'no-ad'});assert denied.status_code>=400,denied.text
 checks.update(health_search_pass=True,existing_ad_memory_guard_preserved=True)
 put(O/'service.json',{'health':h.json(),'profile':profile,'memory_guard_status':denied.status_code,'model_calls':0})
checks['main_pointer_unchanged']=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['active_pointer_hash']
put(O/'dependencies.json',edges);put(O/'result.json',{'strict_success':all(checks.values()),'checks':checks,'serving_files':len(r['staged_files']),'engine_dependency_edges':len(edges),'model_calls':0,'field_execution':False});print(json.dumps(checks))
