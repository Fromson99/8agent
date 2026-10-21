from pathlib import Path
import subprocess,json,time,os
os.environ.update(GENOS_RESIDENT_DATA='off', MALLOC_ARENA_MAX="1",MALLOC_TRIM_THRESHOLD_="65536",MALLOC_MMAP_THRESHOLD_="131072")
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0894-mixed-source-modality/artifacts'
p=A/'resource-contracts.json'
while not p.exists():time.sleep(2)
x=json.loads(p.read_text());assert x['returncode']==0 and x['stop_reason'] is None,x
for cid in ('cm-033', 'cm-001', 'cm-003', 'cm-008', 'cm-051', 'cm-011', 'cm-022', 'cm-038'):
 with (A/(''+cid+'.log')).open('x') as out:
  status=subprocess.run([str(R/'.venv/bin/python'),str(T.parent/'resource_guard.py'),'--record',str(A/('resource-'+cid+'.json')),'--',str(R/'.venv/bin/python'),str(T/'live.py'),cid],stdout=out,stderr=subprocess.STDOUT,cwd=R)
 subprocess.run([str(R/'.venv/bin/python'),str(T/'audit_v2.py'),cid],check=True)
 subprocess.run([str(R/'.venv/bin/python'),str(T/'archive_v2.py')],check=True)
 print(cid,'exit',status.returncode,flush=True)
 if json.loads((A/('resource-'+cid+'.json')).read_text())['stop_reason']:break
