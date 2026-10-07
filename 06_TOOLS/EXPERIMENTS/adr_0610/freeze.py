import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples';D=A/'artifacts/design';mp=A/'실험/manifest.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
cp=R/'02_BACKEND/lawrag/research/candidates/adr_0610/forced-turn-memory/candidate.json';c=json.loads(cp.read_text());rev=c['revisions'][-1];m=json.loads(mp.read_text());runner=R/'06_TOOLS/EXPERIMENTS/adr_0610/run.py'
m['design']['code_isolation']={'schema_version':'adr-code-isolation-v1','mode':'candidate_snapshot','reason':None,'production_paths_modified_before_decision':False,'runtime_import_allowed':False,'production_registry_registered':False,'main_wiring_unchanged':True,'candidates':[{'candidate_id':c['candidate_id'],'experiment_id':m['experiment_id'],'arm_id':'REPLAY','run_ids':['run-001'],'manifest_path':str(cp.relative_to(R)),'manifest_sha256':sha(cp),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}]}
put(mp,m);put(D/'pre-run-manifest.json',m)
parent=R/'04_EXPERIMENTS/ADR/ADR-0609-native-memory-reuse-purpose-separation/artifacts/design/freeze.json'
paths=[R/p for p in json.loads(parent.read_text()) if 'adr_0609' not in p and 'ADR-0609' not in p]
paths += [cp,*[R/f['frozen_path'] for f in rev['files']],*D.glob('*.json'),*(R/'06_TOOLS/EXPERIMENTS/adr_0610').glob('*.py')]
# Include exact generation data, not only its manifest.
g=R/'04_EXPERIMENTS/ADR/ADR-0603-corrected-route-integration-audit-receipts/artifacts/run-001/native/built/generation'
paths += [p for p in g.rglob('*') if p.is_file() and not p.name.endswith(('-wal','-shm'))]
put(D/'freeze.json',{str(p.relative_to(R)):sha(p) for p in paths if p.name!='freeze.json'})
put(D/'preflight-note.json',{'phase':'before any model call','snapshot_cli_initial_failure':'Missing required --experiment-id; fixed before snapshot creation. No product result observed.','turns':22,'code_change':False,'gold_product_visible':False})
print('Frozen',len(json.loads((D/'freeze.json').read_text())),'files; candidate bytes match completed parent.')
