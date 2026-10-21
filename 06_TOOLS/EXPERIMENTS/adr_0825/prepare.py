from pathlib import Path
import json,shutil,subprocess,sys,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0825-comparison-child-request-resume';D=A/'artifacts/design';D.mkdir(exist_ok=True);P=R/'02_BACKEND/lawrag/research/candidates/adr_0823/connected';C=R/'02_BACKEND/lawrag/research/candidates/adr_0825/connected';pc=json.loads((P/'candidate.json').read_text());old=P/'revisions/rev-001/snapshot'
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
criteria={'hypothesis':'A trusted workflow resumes its abandoned exact child request under both locks without replacing source progress or resetting budget','success':['same request resumes after process exit during SELECT','source receipts and prior valid side preserved','same input,ACL,code and state checks remain required','original parent and request deadline/physical reservations persist','regular RAG duplicates are not silently resumed','no recovery model call or new retry allowance'], 'failure':['request fingerprint or scope bypass','source state loss','new model allowance','unlocked or unrelated request recovery'],'failure_owner':'CaseRepository holds case owner; workflow holds parent execution owner; only exact PREPARED parent call authorizes marking abandoned RUNNING as resumable FAILED.'}
put(D/'criteria.json',criteria)
for n in ('baseline.json','data-binding.json'):shutil.copy2(R/'04_EXPERIMENTS/ADR/ADR-0823-comparison-partial-qualification/artifacts/design'/n,D/n)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id','ADR-0825-experiment-v1','--arm-id','connected','--run-id','run-001']
for x in pc['files']:
 if (R/x['target_path']).exists():cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for x in pc['files']:
 n=x['target_path'];p=C/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/n,p)
 if not (R/n).exists():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',n,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
for n in ('repin.py','run_tests.py','test_tasks.py'):
 source=R/'06_TOOLS/EXPERIMENTS'/('adr_0822' if n=='repin.py' else 'adr_0823')/n
 text=source.read_text().replace('adr_0822/connected','adr_0825/connected').replace('adr_0823/connected','adr_0825/connected').replace('EXPERIMENTS/adr_0823','EXPERIMENTS/adr_0825').replace("'1.4.0'","'1.4.1'")
 (Path(__file__).parent/n).write_text(text)
m=json.loads((A/'실험/manifest.json').read_text());m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='per-side evidence retention and integrity',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True);m['runs'][0].update(artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)),selection_rule='Exact abandoned child recovery and original31API contracts; no model calls');m['dataset'].update(name='partial-side-preservation',version='v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=False,reference_version_checked=False);m['lineage']['hypothesis_delta']=criteria['hypothesis'];put(A/'실험/manifest.json',m)
print('Isolated side-preservation candidate prepared')
