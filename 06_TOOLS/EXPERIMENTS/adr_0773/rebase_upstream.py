from pathlib import Path
import hashlib,json,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0773-successful-shortcut-publication';D=A/'artifacts/design';old=R/'02_BACKEND/lawrag/research/candidates/adr_0773/successful-publication';new=old.with_name('successful-publication-r2');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();m=json.loads((old/'candidate.json').read_text());changes=[]
for f in m['files']:
 p=R/f['target_path']
 if f['upstream_state']=='present' and sha(p)!=f['upstream_sha256']:changes.append({'path':f['target_path'],'original':f['upstream_sha256'],'current':sha(p),'candidate':sha(old/'snapshot'/f['target_path'])})
(D/'concurrent-working-changes.json').write_text(json.dumps({'policy':'Preserve current completion changes in working tree; not part of this candidate or deployment. Candidate retains MAIN58 completion logic. Working engine pins merged separately; selected release uses frozen candidate pins.','files':changes},indent=2)+'\n')
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','successful-publication-r2','--experiment-id','ADR-0773-experiment-v1','--arm-id','successful-publication','--run-id','run-001']
for f in m['files']:
 if f['upstream_state']=='present':cmd+=['--source',f['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for f in m['files']:
 p=f['target_path'];t=new/'snapshot'/p;t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/'snapshot'/p,t)
 if f['upstream_state']=='absent':subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(new),'--target',p,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
for name in ('freeze_code.py','freeze_run.py','probe.py'):
 p=R/'06_TOOLS/EXPERIMENTS/adr_0773'/name;s=p.read_text().replace('candidates/adr_0773/successful-publication\'','candidates/adr_0773/successful-publication-r2\'').replace('candidates/adr_0773/successful-publication/snapshot','candidates/adr_0773/successful-publication-r2/snapshot');p.write_text(s)
