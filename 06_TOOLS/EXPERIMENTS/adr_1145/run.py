from common import *
import subprocess,time,resource
resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
f=read(ART/'freeze.json');assert read(ART/'check-001.json')['status']==0
for n,h in f['scripts'].items():assert sha(ROOT/n)==h,n
run=ART/'run-001';run.mkdir(exist_ok=True)
lock=run/'started.json';assert not lock.exists(),'Completed/partial experiment cannot be rerun'
put(lock,{'started_at':time.time(),'schedule_sha256':sha(ART/'schedule.json')})
rows=[];total=0
for i,cell in enumerate(read(ART/'schedule.json')):
 mem={k:int(v.split()[0]) for k,v in (s.split(':',1) for s in Path('/proc/meminfo').read_text().splitlines())}
 assert mem['MemAvailable']>=3*1024**2,'RAM floor reached'
 import shutil
 assert shutil.disk_usage(ROOT).free>=20*1024**3,'Disk floor reached'
 target=run/cell['arm']/(cell['case_id']+'__r'+str(cell['rep']))
 print('CELL',i+1,cell,flush=True)
 proc=subprocess.run([str(ROOT/'.venv/bin/python'),str(Path(__file__).with_name('cell.py')),cell['arm'],cell['case_id'],str(cell['rep'])],cwd=ROOT,timeout=1810)
 row=read(target/'result.json') if (target/'result.json').exists() else {'status':'runner_failed','exit_code':proc.returncode}
 rows.append({**cell,'result_path':str((target/'result.json').relative_to(ROOT)),'status':row['status']});total+=row.get('new_model_calls',0)
 put(run/'progress.json',{'completed_cells':len(rows),'new_model_calls':total,'cells':rows})
 assert total<=88
 if proc.returncode or row['status']!='complete':raise SystemExit('Cell failed; remaining cells unexecuted, preserved')
put(run/'completed.json',{'cells':len(rows),'new_model_calls':total,'finished_at':time.time()})
