"""Pin and freeze the implementation and measurement runner before real calls."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0707-grounded-law-title-entry';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0707/title-entry';S=C/'snapshot'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
added='02_BACKEND/semantic_runtime/legal_agent/request_entry.py'
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if 'files' not in v:continue
 if '02_BACKEND/semantic_runtime/legal_agent/unified_rag.py' in v['files']:
  for name in (added,'02_BACKEND/semantic_runtime/legal_agent/law_title_hints.py'):v['files'][name]=sha(S/name)
 for name in v['files']:v['files'][name]=sha(S/name)
 put(p,v)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0689/pin_engines.py',str(S)],cwd=R,check=True)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],cwd=R,check=True)
cm=read(C/'candidate.json');rev=cm['revisions'][-1]
base='02_BACKEND/lawrag/research/candidates/adr_0706/fused-entry/revisions/rev-001/snapshot'
codes={'baseline':base,'title-entry':str((C/'revisions'/rev['revision_id']/'snapshot').relative_to(R))}
baseline=read(D/'baseline.json')
parent=read(R/'04_EXPERIMENTS/ADR/ADR-0706-fused-request-entry-e2e/artifacts/design/freeze.json')
for name,h in parent['files'].items():
 if name.startswith(base+'/'):assert sha(R/name)==h,name
binding={'candidate_id':'title-entry','arm_id':'title-entry','experiment_id':'ADR-0707-experiment-v1','run_ids':['run-001'],
    'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
    'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
    'runner_path':'06_TOOLS/EXPERIMENTS/adr_0707/run.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0707/run.py')}
m=read(A/'실험/manifest.json');m['design']['code_isolation']['candidates']=[binding];put(A/'실험/manifest.json',m)
paths=list(D.glob('*.json'))+list((R/'06_TOOLS/EXPERIMENTS/adr_0707').glob('*.py'))+[C/'candidate.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',R/baseline['pointer']['manifest_path']]
for code in codes.values():paths += [p for p in (R/code).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'codes':codes,'source_generation':baseline['release']['data_path'],
    'candidate':binding,'files':{str(p.relative_to(R)):sha(p) for p in paths}})
print('Frozen two code bindings; baseline equals completed ADR0706 fused front; no model calls yet')
