from pathlib import Path
import json,shutil,subprocess,sys,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0822-comparison-partial-item-preservation';D=A/'artifacts/design';D.mkdir(exist_ok=True);P=R/'02_BACKEND/lawrag/research/candidates/adr_0819/connected';C=R/'02_BACKEND/lawrag/research/candidates/adr_0822/connected';pc=json.loads((P/'candidate.json').read_text());old=P/'revisions/rev-001/snapshot'
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
criteria={'success':['bounded repair failure cannot discard independently valid other-side evidence','rejected proposal remains failed;raw sources cannot be changed','only literal same-side cited findings survive;comparative conclusion stays unknown','quarantined recovery reads exact existing response hashes and never calls model','resume and other issues continue with original budget'], 'failure':['false absence','made up evidence','invalid field accepted as confirmed','repeated repair allowance','tampered raw response reuse'], 'scope':'General per-side partial publication after bounded semantic repair; live0820 response is development reproduction,not a holdout','failure_owner':'ModelAdapter owns exactly one repair; task board verifies independent parts after exhaustion without turning failed proposal into success'}
put(D/'criteria.json',criteria)
for n in ('baseline.json','data-binding.json'):shutil.copy2(R/'04_EXPERIMENTS/ADR/ADR-0819-comparison-task-qualification/artifacts/design'/n,D/n)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id','ADR-0822-experiment-v1','--arm-id','connected','--run-id','run-001']
for x in pc['files']:
 if (R/x['target_path']).exists():cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for x in pc['files']:
 n=x['target_path'];p=C/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/n,p)
 if not (R/n).exists():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',n,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
for n in ('repin.py','run_tests.py','test_tasks.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0818'/n).read_text().replace('adr_0818/connected-r2','adr_0822/connected').replace("str(R/'06_TOOLS/EXPERIMENTS/adr_0818')","str(R/'06_TOOLS/EXPERIMENTS/adr_0822')")
 if n=='repin.py':s=s.replace("'1.3.0'","'1.4.0'")
 (Path(__file__).parent/n).write_text(s)
m=json.loads((A/'실험/manifest.json').read_text());m['design'].update(hypothesis='Retain independently validated side findings when whole model proposal fails bounded repair',primary_metric='per-side evidence retention and integrity',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True);m['runs'][0].update(artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)),selection_rule='Saved0820 real proposals and deterministic API/error/resume contracts');m['dataset'].update(name='partial-side-preservation',version='v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=False,reference_version_checked=False);put(A/'실험/manifest.json',m)
print('Isolated side-preservation candidate prepared')
