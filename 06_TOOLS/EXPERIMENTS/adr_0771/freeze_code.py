from pathlib import Path
import hashlib,json,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0771-source-cards-main-wiring';C=R/'02_BACKEND/lawrag/research/candidates/adr_0771/source-cards';S=C/'snapshot'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 for n in v.get('files',{}):
  if (S/n).is_file():v['files'][n]=sha(S/n)
 put(p,v)
def refresh(x):
 if isinstance(x,dict):
  for k,v in list(x.items()):
   if isinstance(v,str) and len(v)==64 and (S/k).is_file():x[k]=sha(S/k)
   elif isinstance(v,str) and (S/v).is_file():
    for key in (k+'_sha256','sha256'):
     if key in x and isinstance(x[key],str) and len(x[key])==64:x[key]=sha(S/v)
   elif isinstance(v,(dict,list)):refresh(v)
 elif isinstance(x,list):
  for v in x:refresh(v)
p=S/'00_SYSTEM/PIPELINE.json';v=read(p);refresh(v);put(p,v)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
c=read(C/'candidate.json');rev=c['revisions'][-1];m=read(A/'실험/manifest.json')
m['design']['code_isolation']['candidates']=[{'candidate_id':'source-cards','arm_id':'source-cards','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0771/run_tests.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0771/run_tests.py')}]
put(A/'실험/manifest.json',m);print(rev['revision_id'])
