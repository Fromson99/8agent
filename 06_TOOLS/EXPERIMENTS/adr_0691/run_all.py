"""Logged sequential job with one durable owner; existing cases are never retried."""
from pathlib import Path
import json,subprocess,os,datetime
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0691-judgment-loop-unstarted-holdout'
v=json.loads((A/'artifacts/design/dataset.json').read_text());logs=A/'artifacts/execution';logs.mkdir(exist_ok=True)
owner={'pid':os.getpid(),'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'running'}
with (logs/'owner.json').open('x') as f:json.dump(owner,f,indent=2)
try:
 for i,case in enumerate(v['cases']+v['regression_cases']):
  for arm in (('baseline','repaired') if i%2==0 else ('repaired','baseline')):
   cid=case['case_id'];folder=A/'artifacts/run-001'/arm/cid;result=folder/'result.json'
   assert not folder.exists(),'Existing partial or complete case cannot be retried'
   with (logs/(cid+'-'+arm+'.log')).open('x') as stream:
    p=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0691/run_case.py','--arm',arm,'--case',cid],cwd=R,stdout=stream,stderr=subprocess.STDOUT)
   assert result.exists(),f'No result: {cid}/{arm}, process exit {p.returncode}'
   r=json.loads(result.read_text());print(json.dumps({k:r[k] for k in ('case_id','arm','http_status','model_calls','total_seconds')},ensure_ascii=False),flush=True)
 owner['status']='completed'
except BaseException as exc:
 owner.update(status='stopped',error=repr(exc));raise
finally:
 owner['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 (logs/'owner.json').write_text(json.dumps(owner,indent=2)+'\n')
