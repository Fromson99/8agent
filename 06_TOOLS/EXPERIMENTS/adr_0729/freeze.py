from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];B=R/'02_BACKEND/lawrag/research/candidates/adr_0729/compact';C=B/'snapshot';A=R/'04_EXPERIMENTS/ADR/ADR-0729-compact-branch-choice-contract';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text())
 for name in v.get('files',{}):
  if (C/name).is_file():v['files'][name]=sha(C/name)
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
p=R/'06_TOOLS/EXPERIMENTS/adr_0729/run_contracts.py';p.write_text((R/'06_TOOLS/EXPERIMENTS/adr_0727/run_contracts.py').read_text().replace('adr_0727','adr_0729').replace('ADR-0727-navigation-input-binding','ADR-0729-compact-branch-choice-contract'))
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(B)],check=True,stdout=subprocess.DEVNULL);cm=json.loads((B/'candidate.json').read_text());rev=cm['revisions'][-1];m=json.loads((A/'실험/manifest.json').read_text())
m['design']['code_isolation']['candidates']=[{'candidate_id':'compact','arm_id':'compact','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((B/'candidate.json').relative_to(R)),'manifest_sha256':sha(B/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(p.relative_to(R)),'runner_sha256':sha(p)}];put(A/'실험/manifest.json',m)
