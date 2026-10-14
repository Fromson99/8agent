from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0763-request-scope-search-recovery';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0763/recovery';S=C/'snapshot'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 for name in v.get('files',{}):
  if (S/name).is_file():v['files'][name]=sha(S/name)
 put(p,v)
def refresh(x):
 if isinstance(x,dict):
  for k,val in list(x.items()):
   if isinstance(val,str) and len(val)==64 and (S/k).is_file():x[k]=sha(S/k)
   elif isinstance(val,str) and (S/val).is_file():
    for key in (k+'_sha256','sha256'):
     if key in x and isinstance(x[key],str) and len(x[key])==64:x[key]=sha(S/val)
   elif isinstance(val,(dict,list)):refresh(val)
 elif isinstance(x,list):
  for row in x:refresh(row)
p=S/'00_SYSTEM/PIPELINE.json';v=read(p);refresh(v);put(p,v)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot';m=read(A/'실험/manifest.json');release=read(D/'baseline.json')['manifest']
binding={'candidate_id':'recovery','arm_id':'recovery','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0763/run_case.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0763/run_case.py')}
m['design']['code_isolation']['candidates']=[binding];put(A/'실험/manifest.json',m)
put(D/'bindings.json',{'codes':{'baseline':release['code_root'],'recovery':str(code.relative_to(R))},'stage':str(code.relative_to(R)),'source_generation':release['data_path'],'experiment_client':str((code/'02_BACKEND/lawrag/research/experiment_client.py').relative_to(R))})
files={str(p.relative_to(R)):sha(p) for p in list(D.glob('*.json'))+[C/'candidate.json']+list((R/'06_TOOLS/EXPERIMENTS/adr_0763').glob('*.py'))+[R/'00_SYSTEM/WORKSPACE.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']}
files['06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py']=sha(R/'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py')
for row in cm['files']:files[str((code/row['target_path']).relative_to(R))]=sha(code/row['target_path'])
for name,h in release['files'].items():files[str(Path(release['code_root'])/name)]=h
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),'files':files,'serving_files':release['files'],'candidate':binding})
print('Frozen A',rev['revision_id'],rev['revision_sha256'])
