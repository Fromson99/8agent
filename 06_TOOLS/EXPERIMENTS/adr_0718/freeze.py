from pathlib import Path
import json,hashlib,subprocess
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];B=R/'02_BACKEND/lawrag/research/candidates/adr_0718/repaired';C=B/'snapshot';A=R/'04_EXPERIMENTS/ADR/ADR-0718-main50-request-repair-integration';D=A/'artifacts/design'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run(*args):subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py',*args],cwd=R,check=True,stdout=subprocess.DEVNULL)
profile=C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';v=json.loads(profile.read_text());v['candidate_navigation']['completion_policy_version']='investigation-completion-v5';put(profile,v)
# Add dependency identity to every manifest that consumes completion code.
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text());files=v.get('files',{})
 if '02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py' in files:
  for name in ['request_repair.py','completion_v5.py']:files['02_BACKEND/semantic_runtime/legal_agent/'+name]=sha(C/'02_BACKEND/semantic_runtime/legal_agent'/name)
 for name in files:
  if (C/name).is_file():files[name]=sha(C/name)
 put(p,v)
p=C/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text())
def refresh(x):
 if isinstance(x,dict):
  for k,val in list(x.items()):
   if isinstance(val,str) and len(val)==64 and (C/k).is_file():x[k]=sha(C/k)
   elif isinstance(val,str) and (C/val).is_file():
    for key in (k+'_sha256','sha256'):
     if key in x and isinstance(x[key],str) and len(x[key])==64:x[key]=sha(C/val)
   elif isinstance(val,(dict,list)):refresh(val)
 elif isinstance(x,list):
  for row in x:refresh(row)
refresh(v);put(p,v)
cm=json.loads((B/'candidate.json').read_text());known={r['target_path'] for r in cm['files']}
for path in ['02_BACKEND/semantic_runtime/legal_agent/request_repair.py','02_BACKEND/semantic_runtime/legal_agent/completion_v5.py','05_TESTS/CONTRACTS/test_main50_request_repair.py']:
 if path not in known:run('register',str(B),'--target',path,'--upstream-state','absent')
run('freeze',str(B));cm=json.loads((B/'candidate.json').read_text());rev=cm['revisions'][-1]
root=B/'revisions'/rev['revision_id']/'snapshot'
m=json.loads((A/'실험/manifest.json').read_text());m['design']['code_isolation']['candidates']=[{'candidate_id':'repaired','arm_id':'repaired','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((B/'candidate.json').relative_to(R)),'manifest_sha256':sha(B/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0718/run_contracts.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0718/run_contracts.py')}];put(A/'실험/manifest.json',m)
put(D/(rev['revision_id']+'-freeze.json'),{'code_root':str(root.relative_to(R)),'revision':rev['revision_id'],'time':datetime.now(timezone.utc).isoformat(),'candidate_manifest_sha256':sha(B/'candidate.json'),'runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0718/run_contracts.py')})
print(root)
