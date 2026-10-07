"""Resume unchanged, sealed single-case commands; archive maintenance runs separately.
No retries, replacement questions, product edits, altered thresholds or model changes.
"""
from pathlib import Path
import json,subprocess,time,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization';D=A/'artifacts/design'
dataset=json.loads((D/'dataset.json').read_text());running=[]
def count_workers():
 rows=subprocess.run(['ps','-eo','args'],capture_output=True,text=True,check=True).stdout.splitlines()
 return sum(bool(x.split()) and x.split()[0].endswith('/python') and 'adr_0677/run_case.py' in x for x in rows)
def hashes():
 for name in ['freeze.json','release-freeze.json']:
  for p,h in json.loads((D/name).read_text())['files'].items():assert hashlib.sha256((R/p).read_bytes()).hexdigest()==h,p
for group,cases in [('run-001',dataset['cases']),('regression',dataset['regression_cases'])]:
 todo=[]
 for c in cases:
  cid=c['case_id'];log=A/'artifacts'/('logs/integrated' if group=='run-001' else 'regression-logs')/(cid+'.log');result=A/'artifacts'/group/'integrated'/cid/'result.json'
  if not log.exists() and not result.exists():todo.append((cid,log,result))
 while todo or running:
  for task in list(running):
   proc,log,result,cid,f=task
   if proc.poll() is None:continue
   f.close();running.remove(task)
   row=json.loads(result.read_text()) if result.exists() else {}
   print('CASE_DONE',cid,row.get('http_status'),row.get('model_calls'),proc.returncode,flush=True)
  if todo and count_workers()<2:
   hashes();cid,log,result=todo.pop(0);log.parent.mkdir(parents=True,exist_ok=True);f=log.open('x')
   command=[str(R/'.venv/bin/python'),str(R/'06_TOOLS/EXPERIMENTS/adr_0677/run_case.py'),'--arm','integrated','--case',cid]
   proc=subprocess.Popen(command,cwd=R,stdout=f,stderr=subprocess.STDOUT);running.append((proc,log,result,cid,f));print('CASE_START',cid,proc.pid,flush=True)
  time.sleep(5)
 while count_workers():time.sleep(5)
print('All scheduled primary and regression requests closed',flush=True)
