"""Prespecified sequential paired cases; never repeat an existing result."""
from pathlib import Path
import json,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0690-judgment-loop-package-holdout'
v=json.loads((A/'artifacts/design/dataset.json').read_text())
logs=A/'artifacts/execution';logs.mkdir(exist_ok=True)
for i,case in enumerate(v['cases']+v['regression_cases']):
 for arm in (('baseline','repaired') if i%2==0 else ('repaired','baseline')):
  cid=case['case_id'];result=A/'artifacts/run-001'/arm/cid/'result.json'
  if result.exists():raise RuntimeError('Existing result cannot be rerun: '+str(result))
  with (logs/(cid+'-'+arm+'.log')).open('x') as stream:
   p=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0690/run_case.py','--arm',arm,'--case',cid],cwd=R,stdout=stream,stderr=subprocess.STDOUT)
  if not result.exists():raise RuntimeError('Runner failed before recording: '+str(p.returncode))
  r=json.loads(result.read_text());print(json.dumps({k:r[k] for k in ('case_id','arm','http_status','model_calls','total_seconds')},ensure_ascii=False),flush=True)
