from pathlib import Path
import json,subprocess,os,datetime
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0701-structure-preserved-final-holdout';logs=A/'artifacts/execution';logs.mkdir(exist_ok=True)
v=json.loads((A/'artifacts/design/dataset.json').read_text());arms=['baseline','structured-reading']
for arm in arms:assert json.loads((A/'artifacts/setup-check'/arm/'H01/result.json').read_text())['http_status']==200
owner={'pid':os.getpid(),'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'running'}
with (logs/'owner.json').open('x') as f:json.dump(owner,f,indent=2)
try:
 for i,c in enumerate(v['cases']):
  for arm in (['structured-reading'] if c['case_id'].startswith('R') else arms[i:]+arms[:i]):
   cid=c['case_id'];folder=A/'artifacts/run-001'/arm/cid;assert not folder.exists(),'Unknown or completed attempts cannot be resent'
   with (logs/(cid+'-'+arm+'.log')).open('x') as out:p=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0701/run_case.py','--arm',arm,'--case',cid],cwd=R,stdout=out,stderr=subprocess.STDOUT)
   r=json.loads((folder/'result.json').read_text());print(json.dumps({k:r[k] for k in ('case_id','arm','http_status','model_calls','total_seconds')},ensure_ascii=False),flush=True)
 owner['status']='completed'
except BaseException as e:owner.update(status='stopped',error=repr(e));raise
finally:
 owner['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();(logs/'owner.json').write_text(json.dumps(owner,indent=2)+'\n')
