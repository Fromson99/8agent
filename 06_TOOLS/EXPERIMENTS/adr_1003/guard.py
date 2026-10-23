"""Six single-call paired probes then one bounded native run, sequential."""
from common import *
import subprocess,time,signal
assert not (ART/'stop.json').exists() and not (ART/'paired').exists() and not (ART/'known-query').exists()
def available():return next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
def run(args,label,timeout):
 assert available()>3*1024**3
 start=time.monotonic();peak=0;cause=None
 with (ART/(label+'.log')).open('x') as stream:
  p=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-B',*args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
  while p.poll() is None:
   path=Path(f'/proc/{p.pid}/status')
   try:rss=next((int(x.split()[1])*1024 for x in path.read_text().splitlines() if x.startswith('VmRSS:')),0)
   except FileNotFoundError:rss=0
   peak=max(peak,rss)
   if rss>6*1024**3 or available()<3*1024**3 or time.monotonic()-start>timeout:
    cause='MEMORY_OR_DEADLINE';p.send_signal(signal.SIGINT)
    try:p.wait(timeout=10)
    except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=10)
    break
   time.sleep(.5)
 result={'exit_code':p.returncode,'peak_rss_bytes':peak,'seconds':time.monotonic()-start,'interruption':cause}
 save(ART/(label+'-resources.json'),result)
 print(label,p.returncode,round(peak/1024**2),'MiB',flush=True)
 if p.returncode or cause:
  if not (ART/'stop.json').exists():save(ART/'stop.json',{'reason':cause or 'PROCESS_FAILURE','label':label})
  raise SystemExit(2)
for case in ('enough','missing','chain'):
 for arm in ('baseline','candidate'):run([str(Path(__file__).with_name('offline_replay.py')),arm,case],case+'-'+arm,220)
run([str(Path(__file__).with_name('full_query.py'))],'known-candidate',1860)
paths=list((ART/'paired').glob('*/*/result.json'))+[ART/'known-query/candidate/result.json']
calls=sum(read(p)['model_calls'] for p in paths);assert calls<=14
save(ART/'guard-result.json',{'physical_calls':calls,'remaining_cases':0,'status':'COMPLETE'})
