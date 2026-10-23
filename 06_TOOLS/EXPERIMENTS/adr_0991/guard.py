"""One child at a time; resource pressure stops remaining trials, never retries."""
from common import *
from stop_policy import terminal_failure
import subprocess,time,signal,sys
assert not (ART/'stop.json').exists(), 'Prior stop prohibits reexecution'
assert not (ART/'known-query').exists(), 'One invocation only; no in-place retries'
def available():return next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
def run(args,label,ceiling,timeout):
 assert available()>3*1024**3
 log=ART/(label+'.log');assert not log.exists()
 start=time.monotonic();peak=0;cause=None
 with log.open('x') as stream:
  p=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-B',*args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
  while p.poll() is None:
   path=Path(f'/proc/{p.pid}/status')
   rss=next((int(x.split()[1])*1024 for x in path.read_text().splitlines() if x.startswith('VmRSS:')),0) if path.exists() else 0
   peak=max(peak,rss)
   if rss>ceiling or available()<3*1024**3 or time.monotonic()-start>timeout:
    cause='MEMORY_OR_DEADLINE';p.send_signal(signal.SIGINT)
    try:p.wait(timeout=10)
    except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=10)
    break
   time.sleep(.5)
 save(ART/(label+'-resources.json'),{'exit_code':p.returncode,'peak_rss_bytes':peak,'seconds':time.monotonic()-start,'interruption':cause})
 print(label,p.returncode,round(peak/1024**2),'MiB',flush=True)
 result_path=ART/'known-query/candidate/result.json'
 result=read(result_path) if result_path.exists() else {}
 stop=read(ART/'stop.json') if (ART/'stop.json').exists() else None
 failure=terminal_failure(result,stop,p.returncode) or cause
 save(ART/'guard-result.json',{'failure':failure,'exit_code':p.returncode,'model_calls':result.get('model_calls'),'further_cases_dispatched':0})
 if failure:raise SystemExit(2)
run([str(Path(__file__).with_name('full_query.py'))],'known-candidate',6*1024**3,540)
