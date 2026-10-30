"""Wire existing manifest dependencies and freeze candidate before measurement."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1085/compact-r1'
S=C/'snapshot'; A=ROOT/'04_EXPERIMENTS/ADR/ADR-1085-compact-agent-input-sql'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
new=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('compact_model_input','read_candidate_pages')]
cm=json.loads((C/'candidate.json').read_text())
for name in new:
 ac.register_file(C,name,upstream_state='absent')
p=S/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text())
for ref in v['engines'].values():
 ep=S/ref['manifest'];e=json.loads(ep.read_text())
 if '02_BACKEND/semantic_runtime/legal_agent/decision_projection.py' not in e['files']:continue
 for name in new:e['files'][name]=sha(S/name)
 for name in e['files']:
  if (S/name).is_file():e['files'][name]=sha(S/name)
 put(ep,e);ref['sha256']=sha(ep)
put(p,v)
ac.freeze(C)
cm=json.loads((C/'candidate.json').read_text());rev=cm['revisions'][-1]
code=C/'revisions'/rev['revision_id']/'snapshot'
bind={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
m=json.loads((A/'실험/manifest.json').read_text())
m['design']['code_isolation']['candidates']=[dict(bind,candidate_id=C.name,arm_id='compact',experiment_id=m['experiment_id'],run_ids=['run-001'],runner_path='06_TOOLS/EXPERIMENTS/adr_1085/audit.py',runner_sha256=sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1085/audit.py'))]
put(A/'실험/manifest.json',m)
put(A/'artifacts/design/freeze.json',{'code_root':str(code.relative_to(ROOT)),'binding':bind,'files':{str(p.relative_to(code)):sha(p) for p in code.rglob('*') if p.is_file()},'runners':{str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1085').glob('*.py')}})
print(code)
