"""Own the existing frozen experiment as a service, without replay or policy changes."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
AUDIT=ROOT/'04_EXPERIMENTS/ADR/ADR-1053-ontology-mvp-step-state/artifacts'
EXPERIMENT=ROOT/'04_EXPERIMENTS/ADR/ADR-1053-ontology-mvp-step-state/artifacts'
RUNNER=ROOT/'06_TOOLS/EXPERIMENTS/adr_1053'
UNIT='lawrag-adr1053-state-20261025.service'
PHASES=(('product','run_matrix.py',[]),('evaluation','evaluate_matrix.py',[]),
        ('report','report_results.py',['--write']),('providers','provider_report.py',[]))

def stamp():return datetime.now(timezone.utc).isoformat()
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,v,exclusive=False):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 raw=(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
 if exclusive:
  with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 else:
  tmp=p.with_name(p.name+'.tmp-'+str(os.getpid()))
  with tmp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  os.replace(tmp,p)

def preserved(plan,root=ROOT):
 for name,expected in plan['preserved_files'].items():
  p=root/name
  if not p.is_file() or sha(p)!=expected:raise ValueError('existing result drift: '+name)

def check(plan,root=ROOT):
 for name,expected in plan['pinned_files'].items():
  p=root/name
  if not p.is_file() or sha(p)!=expected:raise ValueError('execution binding drift: '+name)
 preserved(plan,root)

def product_ready(root=EXPERIMENT):
 freeze=read(root/'design-freeze.json');digest=sha(root/'design-freeze.json')
 if (root/'matrix-stop.json').exists():return False
 for cell in freeze['execution_order']:
  folder=root/'matrix'/f"{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}"
  if not (folder/'result.json').is_file() or not (folder/'reservation.json').is_file():return False
  r=read(folder/'result.json');reservation=read(folder/'reservation.json')
  if (r.get('cell')!=cell or r.get('completed') is not True or r.get('outcome') not in {'SERVICE_COMPLETED','NATIVE_BOUNDED_FAILURE'} or reservation.get('design_freeze_sha256')!=digest):return False
 return len(freeze['execution_order'])==111

def heartbeat(phase,child,started):
 progress=read(EXPERIMENT/'matrix-progress.json') if (EXPERIMENT/'matrix-progress.json').exists() else None
 return {'status':'RUNNING','phase':phase,'unit':UNIT,'supervisor_pid':os.getpid(),
         'child_pid':child.pid,'started_at':started,'updated_at':stamp(),
         'product_progress':progress and {k:v for k,v in progress.items() if k!='invocation_outcomes'},
         'automatic_service_restart':False,'existing_cell_replay':False}

def run_phase(phase,script,args,*,runner=RUNNER,audit=AUDIT,heartbeat_fn=heartbeat):
 receipt=audit/(phase+'-process.json');log=audit/(phase+'.log')
 if receipt.exists() or log.exists():raise ValueError('phase already started; inspect instead of replay: '+phase)
 started=stamp();argv=[str(ROOT/'.venv/bin/python'),'-B',str(runner/script),*args]
 with log.open('x') as stream:
  child=subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,
       env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','MALLOC_ARENA_MAX':'1'})
  save(receipt,{'phase':phase,'argv':argv,'pid':child.pid,'started_at':started,'status':'RUNNING'},exclusive=True)
  try:
   while True:
    save(audit/'service-status.json',heartbeat_fn(phase,child,started))
    try:code=child.wait(timeout=10);break
    except subprocess.TimeoutExpired:pass
  except BaseException:
   # systemd KillMode=control-group owns final descendant cleanup. Never restart.
   if child.poll() is None:child.send_signal(signal.SIGINT)
   try:child.wait(timeout=15)
   except subprocess.TimeoutExpired:
    child.terminate()
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:child.kill();child.wait()
   save(receipt,{'phase':phase,'argv':argv,'pid':child.pid,'started_at':started,
    'finished_at':stamp(),'status':'INTERRUPTED','exit_code':child.returncode,'reaped':True})
   raise
 save(receipt,{'phase':phase,'argv':argv,'pid':child.pid,'started_at':started,
  'finished_at':stamp(),'status':'FINISHED','exit_code':code,'reaped':True})
 return code

def execute(plan,run=run_phase,ready=product_ready,verify=preserved):
 phases=[];failure=None
 for phase,script,args in PHASES:
  if phase=='evaluation' and (failure or not ready()):
   if not failure:failure={'phase':'product','reason':'INCOMPLETE_PRODUCT_MATRIX'}
   phases.append({'phase':phase,'status':'NOT_STARTED','reason':'PRODUCT_NOT_COMPLETE'});continue
  # Reports are read-only over product outputs and safe after a failed execution.
  code=run(phase,script,args);phases.append({'phase':phase,'exit_code':code})
  if code and failure is None:failure={'phase':phase,'exit_code':code}
 verify(plan)
 return {'status':'STOPPED' if failure else 'COMPLETE','failure':failure,'phases':phases,
  'existing_results_preserved':True,'completed_at':stamp(),'automatic_replay':False}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--check-only',action='store_true');args=parser.parse_args()
 plan=read(AUDIT/'execution-plan.json');check(plan)
 if args.check_only:
  print(json.dumps({'preserved_cells':plan['preserved_completed_cells'],'resume_ordinal':plan['resume_ordinal'],'binding_verified':True,'live_calls':0}));return 0
 cgroup=Path('/proc/self/cgroup').read_text()
 if UNIT not in cgroup:raise ValueError('run under the recorded systemd unit, not a temporary tool session')
 def interrupted(signum,frame):raise KeyboardInterrupt('supervisor signal '+str(signum))
 signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGHUP,interrupted)
 with (AUDIT/'.supervisor.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  save(AUDIT/'service-reservation.json',{'pid':os.getpid(),'unit':UNIT,'started_at':stamp(),
   'resume_plan_sha256':sha(AUDIT/'execution-plan.json'),'cgroup':cgroup},exclusive=True)
  try:result=execute(plan)
  except BaseException as exc:
   save(AUDIT/'service-status.json',{'status':'STOPPED','updated_at':stamp(),'error_type':type(exc).__name__,'reason':str(exc),'automatic_replay':False})
   raise
  save(AUDIT/'service-status.json',result);save(AUDIT/'completion.json',result,exclusive=True)
  return 0 if result['status']=='COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
