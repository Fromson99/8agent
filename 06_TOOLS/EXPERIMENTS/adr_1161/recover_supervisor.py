"""Observe existing child; never resend an already dispatched case."""
from common import *
import os,time,signal,subprocess
p=read(ART/'batch-process.json');pid=p['child_pid'];case=p['active'];end=p['started_at']+1860
put(ART/'supervisor-recovery.json',{'old_supervisor':p['pid'],'observed_live_child':pid,'case':case,'original_deadline_epoch':end,'new_supervisor':os.getpid(),'started_at':time.time(),'reason':'Tool session exited143 while child still alive; no case replay'})
while not (RUN/case/'result.json').exists():
 try:
  status=Path(f'/proc/{pid}/stat').read_text().split()[2]
  if status=='Z':break
 except FileNotFoundError:break
 if time.time()>=end:
  os.killpg(pid,signal.SIGTERM);time.sleep(3)
  try:os.killpg(pid,signal.SIGKILL)
  except ProcessLookupError:pass
  break
 time.sleep(5)
# Existing batch records an interrupted child rather than replaying it, and starts only untouched009.
raise SystemExit(subprocess.call([str(ROOT/'.venv/bin/python'),str(Path(__file__).with_name('batch.py'))],cwd=ROOT))
