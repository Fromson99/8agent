from pathlib import Path
import json,hashlib,sys,subprocess,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0841-comparison-direct-review';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0841/direct';S=C/'snapshot'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
W=S/'02_BACKEND/workflow';p=W/'risk_team_compare_workflow/manifest.json';x=read(p);x['version']='1.7.0';x['files']={n:sha(W/n) for n in x['files']};put(p,x)
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 x=read(p)
 if 'files' in x:x['files']={n:sha(S/n) for n in x['files']};put(p,x)
p=S/'00_SYSTEM/PIPELINE.json';x=read(p)
for e in x['engines'].values():e['sha256']=sha(S/e['manifest'])
for w in x['workflows']['registered']:w['version']='1.7.0';w['sha256']=sha(S/w['manifest'])
put(p,x)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate;adr_candidate.refresh(C)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
base=read(D/'baseline.json');files={n:sha(code/n) for n in base['manifest']['files']}
binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
put(D/'verification-binding.json',{'code_root':str(code.relative_to(R)),'serving_files':files,**binding})
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{**binding,'candidate_id':'direct','arm_id':'direct','experiment_id':m['experiment_id'],'run_ids':['run-001'],'runner_path':str((T/'live.py').relative_to(R)),'runner_sha256':sha(T/'live.py')}])
m['llm_policy']['llm_calls']=[{'role':'comparison','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}];put(A/'실험/manifest.json',m)
paths=list(T.glob('*.py'))+list(D.glob('*.json'))+[R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
frozen={str(p.relative_to(R)):sha(p) for p in paths};frozen.update({str((code/n).relative_to(R)):h for n,h in files.items()})
put(D/'freeze.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),'serving_files':files,'files':frozen,'candidate':binding})
print('frozen',len(files),'files',rev['revision_id'])
