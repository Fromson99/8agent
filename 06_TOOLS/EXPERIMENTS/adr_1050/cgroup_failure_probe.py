"""No-model fault injection: a detached child must not survive its service owner."""
import json,os,signal,subprocess,sys,time
from pathlib import Path
out=Path(__file__).resolve().parents[3]/'04_EXPERIMENTS/ADR/ADR-1050-ontology-mvp-supervisor-recovery/artifacts'
if '--child' in sys.argv:
 def ended(signum,frame):
  (out/'cgroup-child-stopped.json').write_text(json.dumps({'pid':os.getpid(),'signal':signum,'time':time.time(),'model_calls':0}));raise SystemExit(0)
 signal.signal(signal.SIGTERM,ended)
 (out/'cgroup-child-started.json').write_text(json.dumps({'pid':os.getpid(),'ppid':os.getppid(),'sid':os.getsid(0),'cgroup':Path('/proc/self/cgroup').read_text(),'model_calls':0}))
 time.sleep(30)
 raise SystemExit('ERROR: detached child survived owner failure')
child=subprocess.Popen([sys.executable,'-B',__file__,'--child'],start_new_session=True)
for _ in range(100):
 if (out/'cgroup-child-started.json').exists():break
 time.sleep(.01)
else:raise RuntimeError('synthetic child failed to start')
(out/'cgroup-owner-failure.json').write_text(json.dumps({'pid':os.getpid(),'child_pid':child.pid,'expected_exit':7,'time':time.time(),'model_calls':0}))
raise SystemExit(7)
