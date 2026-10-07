from pathlib import Path
import json,subprocess,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0645-shortcut-deterministic-procedure'
for i,case in enumerate(json.loads((A/'artifacts/design/inputs.json').read_text())):
 for arm in (['baseline','procedure'] if i%2==0 else ['procedure','baseline']):
  with (A/'artifacts'/('product-'+case['case_id']+'-'+arm+'.log')).open('x') as log:
   done=subprocess.run([str(R/'.venv/bin/python'),str(Path(__file__).with_name('run.py')),'--case',case['case_id'],'--arm',arm],stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
  p=A/'artifacts/run-001'/case['case_id']/arm/'result.json'
  print(json.dumps({'case':case['case_id'],'arm':arm,'exit':done.returncode,'results':[{k:r[k] for k in ['temperature','http_status','provider_calls','seconds']} for r in json.loads(p.read_text())] if p.exists() else None}),flush=True)
