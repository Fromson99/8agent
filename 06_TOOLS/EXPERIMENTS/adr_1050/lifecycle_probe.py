"""No-model service lifecycle proof: survive launcher exit, keep explicit ownership."""
import json,os,time
from pathlib import Path
root=Path(__file__).resolve().parents[3]
out=root/'04_EXPERIMENTS/ADR/ADR-1050-ontology-mvp-supervisor-recovery/artifacts'
for phase in ['started','survived_launcher_exit']:
 with (out/('lifecycle-'+phase+'.json')).open('x') as f:
  json.dump({'phase':phase,'pid':os.getpid(),'ppid':os.getppid(),'sid':os.getsid(0),
   'stdin_is_tty':os.isatty(0),'stdout_is_tty':os.isatty(1),'cgroup':Path('/proc/self/cgroup').read_text(),
   'time':time.time(),'model_calls':0},f,indent=2)
 if phase=='started':time.sleep(12)
