"""Continue only unstarted frozen cases after an externally interrupted turn."""
from pathlib import Path
import json,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0690-judgment-loop-package-holdout'
data=json.loads((A/'artifacts/design/dataset.json').read_text());logs=A/'artifacts/execution'
for i,case in enumerate(data['cases']+data['regression_cases']):
 for arm in (('baseline','repaired') if i%2==0 else ('repaired','baseline')):
  cid=case['case_id'];out=A/'artifacts/run-001'/arm/cid
  if (out/'result.json').exists():
   print('PRESERVED',cid,arm,flush=True);continue
  assert not out.exists(),'Unrecorded partial case must be inspected, never blindly rerun'
  with (logs/(cid+'-'+arm+'.log')).open('x') as stream:
   p=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0690/run_case.py','--arm',arm,'--case',cid],cwd=R,stdout=stream,stderr=subprocess.STDOUT)
  assert (out/'result.json').exists(),f'Runner stopped before result: {cid}/{arm}: {p.returncode}'
  r=json.loads((out/'result.json').read_text());print(json.dumps({k:r[k] for k in ('case_id','arm','http_status','model_calls','total_seconds')},ensure_ascii=False),flush=True)
