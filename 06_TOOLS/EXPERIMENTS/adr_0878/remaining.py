from pathlib import Path
import json,subprocess,time
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0878-main85-cm-registered-live';art=A/'artifacts'
# Wait for the first guarded worker to release its single-worker lock.
p=art/'resource-run002-cm001.json'
while not p.exists():time.sleep(2)
first=json.loads(p.read_text());assert first['stop_reason'] is None,first['stop_reason']
time.sleep(1)
for cid in ('cm-003','cm-008','cm-033','cm-051'):
 record=art/('resource-run002-'+cid.replace('-','')+'.json')
 log=art/('run002-'+cid.replace('-','')+'.log')
 with log.open('x') as out:
  result=subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/EXPERIMENTS/resource_guard.py'),'--record',str(record),'--',str(R/'.venv/bin/python'),str(R/'06_TOOLS/EXPERIMENTS/adr_0878/live_v2.py'),cid],cwd=R,stdout=out,stderr=subprocess.STDOUT)
 print(cid,'worker_exit',result.returncode,flush=True)
 if record.exists() and json.loads(record.read_text())['stop_reason'] is not None:break
 if result.returncode:break
