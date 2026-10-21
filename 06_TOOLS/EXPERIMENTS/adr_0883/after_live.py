from pathlib import Path
import subprocess,json,time,os
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0883-read-first-host-contract-qualification/artifacts';p=A/'resource-cm-008.json'
while not p.exists():time.sleep(2)
x=json.loads(p.read_text());assert x['returncode']==0 and x['stop_reason'] is None,x
env={**os.environ,'MALLOC_ARENA_MAX':'1','MALLOC_TRIM_THRESHOLD_':'65536','MALLOC_MMAP_THRESHOLD_':'131072'}
with (A/'candidate-consumer.log').open('x') as f:subprocess.run([str(R/'.venv/bin/python'),str(T.parent/'resource_guard.py'),'--record',str(A/'candidate-consumer-resource.json'),'--',str(R/'.venv/bin/python'),str(T/'consumer.py'),'candidate'],stdout=f,stderr=subprocess.STDOUT,env=env,check=True)
print('Candidate actual consumer complete')
