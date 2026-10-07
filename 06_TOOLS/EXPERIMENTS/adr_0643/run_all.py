from pathlib import Path
import json,subprocess,os
r=Path(__file__).resolve().parents[3];a=r/'04_EXPERIMENTS/ADR/ADR-0643-shortcut-generation-compatible';results=[]
for case in json.loads((a/'artifacts/design/inputs.json').read_text()):
 for arm in ('baseline','integrated'):
  logfile=a/'artifacts'/('product-'+case['case_id']+'-'+arm+'.log')
  with logfile.open('x') as log:
   done=subprocess.run([str(r/'.venv/bin/python'),str(Path(__file__).with_name('run.py')),'--case',case['case_id'],'--arm',arm],stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
  p=a/'artifacts/run-001'/case['case_id']/arm/'result.json'
  value=json.loads(p.read_text()) if p.exists() else {'runner_error':done.returncode}
  print(json.dumps({'case':case['case_id'],'arm':arm,'http':value.get('http_status'),'calls':value.get('provider_calls'),'seconds':value.get('seconds'),'runner_exit':done.returncode}),flush=True)
