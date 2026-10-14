from pathlib import Path
import subprocess,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0709-grounded-entry-main-qualification'
for cid,arms in [('H01',['baseline','integrated']),('H02',['integrated','baseline']),('H03',['baseline','integrated'])]:
 for arm in arms:
  log=A/'artifacts'/('console-'+arm+'-'+cid+'.log')
  assert not log.exists()
  with log.open('w') as f:r=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0709/run_case.py','--arm',arm,'--case',cid],cwd=R,stdout=f,stderr=subprocess.STDOUT)
  result=A/'artifacts/run-001'/arm/cid/'result.json'
  if not result.exists():raise RuntimeError(f'No result preserved: {arm}/{cid}, exit {r.returncode}')
  v=json.loads(result.read_text());print(arm,cid,v.get('http_status'),v.get('model_calls'),v.get('request_seconds'),flush=True)
