"""Pin and freeze the implementation and measurement runner before real calls."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0706-fused-request-entry-e2e';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0706/fused-entry';S=C/'snapshot'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
added='02_BACKEND/semantic_runtime/legal_agent/request_entry.py'
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if 'files' not in v:continue
 if '02_BACKEND/semantic_runtime/legal_agent/unified_rag.py' in v['files']:v['files'][added]=sha(S/added)
 for name in v['files']:v['files'][name]=sha(S/name)
 put(p,v)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0689/pin_engines.py',str(S)],cwd=R,check=True)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],cwd=R,check=True)
cm=read(C/'candidate.json');rev=cm['revisions'][-1]
base=read(R/'04_EXPERIMENTS/ADR/ADR-0705-cm-max-call-bottleneck-probe/artifacts/design/freeze.json')['code_root']
codes={'baseline':base,'fused-entry':str((C/'revisions'/rev['revision_id']/'snapshot').relative_to(R))}
baseline=read(D/'baseline.json')
for name,h in baseline['release']['files'].items():assert sha(R/base/name)==h,name
binding={'candidate_id':'fused-entry','arm_id':'fused-entry','experiment_id':'ADR-0706-experiment-v1','run_ids':['run-001'],
    'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
    'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
    'runner_path':'06_TOOLS/EXPERIMENTS/adr_0706/run.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0706/run.py')}
m=read(A/'실험/manifest.json');m['design']['code_isolation']['candidates']=[binding];put(A/'실험/manifest.json',m)
paths=list(D.glob('*.json'))+list((R/'06_TOOLS/EXPERIMENTS/adr_0706').glob('*.py'))+[C/'candidate.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',R/baseline['pointer']['manifest_path']]
for code in codes.values():paths += [p for p in (R/code).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'codes':codes,'source_generation':baseline['release']['data_path'],
    'candidate':binding,'files':{str(p.relative_to(R)):sha(p) for p in paths}})
print('Frozen two code bindings; baseline serving files equal MAIN48; no model calls yet')
