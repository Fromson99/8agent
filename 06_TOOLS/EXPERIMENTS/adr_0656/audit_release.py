"""Exhaustive publication closure and actual staged-service validation, no LLM."""
import hashlib, importlib.util, json, os, shutil, sys
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0656-shortcut-packaged-main-validation';D=A/'artifacts/design';OUT=A/'artifacts/run-001';OUT.mkdir(exist_ok=False)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'bindings.json');rebase=read(D/'release-rebase.json');stage=R/rebase['stage'];served=OUT/'serving-only'
for seal in ['freeze.json','release-freeze.json']:
 for p,h in read(D/seal)['files'].items():assert sha(R/p)==h,p
for p,h in rebase['staged_files'].items():
 assert sha(stage/p)==h,p
 target=served/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(stage/p,target)
c=read(R/b['candidate']/'candidate.json');parent=read(R/b['parent_candidate']/'candidate.json');old={r['frozen_path'].split('/snapshot/',1)[1]:r['snapshot_sha256'] for r in parent['revisions'][-1]['files']};diff=[]
for row in c['revisions'][-1]['files']:
 if row['snapshot_sha256']!=old[row['frozen_path'].split('/snapshot/',1)[1]]:diff.append(row['frozen_path'].split('/snapshot/',1)[1])
assert all(p=='02_BACKEND/semantic_runtime/control.py' or p=='00_SYSTEM/PIPELINE.json' or p.startswith('02_BACKEND/ENGINES/') for p in diff),diff
code=R/b['candidate']/'revisions/rev-001/snapshot';oldcode=R/b['parent_candidate']/'revisions/rev-001/snapshot'
for p in diff:
 if p.startswith('02_BACKEND/ENGINES/'):
  x,y=read(code/p),read(oldcode/p);x.pop('files',None);y.pop('files',None);assert x==y,p
 if p=='00_SYSTEM/PIPELINE.json':
  x,y=read(code/p),read(oldcode/p)
  for v in [x,y]:
   for e in v['engines'].values():e.pop('sha256',None)
  assert x==y,p
checks={'semantic_and_model_bytes_unchanged':True,'all_frozen_hashes_match':True,'contracts_103_passed':'103 passed' in (A/'artifacts/contracts.txt').read_text(),'main_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['active_pointer_hash']}
config=read(served/'00_SYSTEM/PIPELINE.json');dependencies=[]
for name,e in config['engines'].items():
 assert sha(served/e['manifest'])==e['sha256'],name
 for p,h in read(served/e['manifest']).get('files',{}).items():assert (served/p).is_file() and sha(served/p)==h,(name,p);dependencies.append([name,p,h])
checks['all_configured_engine_dependencies_present']=True
assert (served/'02_BACKEND/semantic_runtime/moleg_links.py').is_file()
parent_source=read(R/D.relative_to(R)/'inputs.json')['product_evidence'];assert sha(R/parent_source['path'])==parent_source['sha256']
P=R/parent_source['path'];pm=read(P);pr=read(P.parent.parent/'artifacts/run-001/result.json')
assert pm['reservation']['status']=='completed' and pm['decision_eligible'] and not pm['in_sample'] and pr['strict_success'] and pr['summary']['integrated']['correct']==9
checks['accepted_separated_parent_evidence_valid']=True
sys.path.insert(0,str(served/'02_BACKEND'));sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('staged_service',served/'service.py');service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
service._ROOT=R
binding={'mode':'local-release','release_id':'staged-shortcut-r2','generation':b['baseline_release']['generation']+1}
service._resolve_binding=lambda:(served,R/b['generation'],binding)
os.environ['GENOS_RUNTIME_DIR']=str(OUT/'runtime')
app=service.application()
module=__import__(app.state.pipeline.__class__.__module__.rsplit('.',1)[0]+'.stage_runner',fromlist=['StageRunner']);profile=module.StageRunner(app.state.pipeline).verify_profile()
def forbidden_model(*args,**kwargs):raise AssertionError('Publication validation may not call any model')
app.state.pipeline.term_agent.transport.send_once=forbidden_model
from fastapi.testclient import TestClient
with TestClient(app) as api:
 h=api.get('/health');assert h.status_code==200 and h.json()['rag_mode']=='legal-agent-unified-v6'
 s=api.get('/v1/rag/search',params={'q':'상법 제4조','doc_id':'7bbe815ff43b6635','limit':10});assert s.status_code==200,s.text
 response=api.post('/v1/rag/ask',json={'question':'공개 배선 검사: 상법 제4조','document_ids':['7bbe815ff43b6635'],'use_llm':False});assert response.status_code==200,response.text
 payload=response.json();assert payload.get('intake_id') and payload.get('investigation_id'),payload
 denied=api.post('/v1/rag/memory/query',json={'query_kind':'investigation','investigation_id':payload['investigation_id'],'session_id':'untrusted','request_id':'untrusted'});assert denied.status_code in (400,401,403,409,422),denied.text
 checks.update(service_profile_verified=True,health_search_ingress_passed=True,unauthenticated_memory_denied=True)
 put(OUT/'service.json',{'profile':profile,'health':h.json(),'durable_ingress':{k:payload[k] for k in ['intake_id','investigation_id']},'unauthenticated_status':denied.status_code,'model_calls':0})
checks['cli_wiring']=all((A/'artifacts'/n).read_text().startswith('usage:') for n in ['cli-action-memory.txt','cli-unified-memory.txt'])
result={'status':'complete','strict_success':all(checks.values()),'checks':checks,'summary':pr['summary'],'summary_provenance':'Inherited exact ADR0654 separated model evaluation, not new model measurements','inherited_product_source':parent_source,'semantic_differences':diff,'configured_engines':len(config['engines']),'dependency_edges':len(dependencies),'served_files':len(rebase['staged_files']),'model_calls':0,'in_sample':False,'decision_eligible':True,'main_unchanged':True}
put(OUT/'dependency-closure.json',dependencies);put(OUT/'result.json',result);assert result['strict_success'],checks
print(json.dumps(result,ensure_ascii=False,indent=2))
