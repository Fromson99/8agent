"""One request at a time; inspect and archive each completed case before the next."""
from pathlib import Path
from contextlib import redirect_stdout,redirect_stderr
from datetime import datetime,timezone
import gc,json,runpy,subprocess,sys,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0717-main50-cm51-sequential-profile'
assert (A/'artifacts/question-export-authorization.json').is_file(),'Prior CM51 approval receipt required'
cases=json.loads((A/'artifacts/design/dataset.json').read_text())['cases']
for c in cases:
 cid=c['case_id'];out=A/'artifacts/run-001'/cid;log=A/'artifacts'/('console-'+cid+'.log')
 if out.exists() or log.exists():
  if not (out/'diagnostic.json').exists():raise RuntimeError('Interrupted or unaudited case preserved: '+cid+'; do not silently rerun')
  continue
 if (A/'artifacts/STOP').exists():print('Stopped before next case by user/control marker',flush=True);break
 mem={k:int(v.split()[0]) for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
 if mem['MemAvailable']<1500*1024:raise RuntimeError('Less than1500MiB available; stop before new case')
 print('CASE_START',cid,datetime.now(timezone.utc).isoformat(),'available_mib',mem['MemAvailable']//1024,flush=True)
 sys.argv=[str(R/'06_TOOLS/EXPERIMENTS/adr_0717/run_case.py'),'--case',cid]
 with log.open('x') as f,redirect_stdout(f),redirect_stderr(f):runpy.run_path(sys.argv[0],run_name='__main__')
 gc.collect()
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0717/audit_case.py','--case',cid],cwd=R,check=True)
 print('CASE_FINISHED',cid,'rss_kib',next(x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmRSS:')),flush=True)
