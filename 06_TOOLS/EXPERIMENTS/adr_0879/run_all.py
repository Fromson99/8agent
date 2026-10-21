from pathlib import Path
import subprocess,json,time
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0879-read-first-compact-assessment/artifacts'
p=A/'resource-contracts.json'
while not p.exists():time.sleep(2)
x=json.loads(p.read_text());assert x['returncode']==0 and x['stop_reason'] is None,x
for cid in ('cm-001','cm-003','cm-008','cm-033','cm-051'):
 with (A/(cid+'.log')).open('x') as out:
  status=subprocess.run([str(R/'.venv/bin/python'),str(T.parent/'resource_guard.py'),'--record',str(A/('resource-'+cid+'.json')),'--',str(R/'.venv/bin/python'),str(T/'live.py'),cid],stdout=out,stderr=subprocess.STDOUT,cwd=R)
 print(cid,'exit',status.returncode,flush=True)
 if json.loads((A/('resource-'+cid+'.json')).read_text())['stop_reason']:break
