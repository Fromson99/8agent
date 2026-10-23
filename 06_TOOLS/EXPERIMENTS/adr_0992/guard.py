"""Sequential bounded execution; never dispatch after provider or process failure."""
from common import *
import subprocess,time,signal,sys
assert not (ART/'stop.json').exists() and not (ART/'known-query').exists()
records=[]
def available():
 return next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
def run(args,label,timeout):
 assert available()>3*1024**3
 calls=len(list(ART.glob('known-query/*/model/call-*/request.json')))+len(list(ART.glob('trials/*/*/model/call-*/request.json')))
 assert calls<18 and not (ART/'stop.json').exists()
 start=time.monotonic();peak=0;cause=None
 with (ART/(label+'.log')).open('x') as stream:
  p=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-B',*args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
  while p.poll() is None:
   try:status=Path(f'/proc/{p.pid}/status').read_text()
   except FileNotFoundError:status=''
   rss=next((int(x.split()[1])*1024 for x in status.splitlines() if x.startswith('VmRSS:')),0);peak=max(peak,rss)
   if rss>6*1024**3 or available()<3*1024**3 or time.monotonic()-start>timeout:
    cause='MEMORY_OR_DEADLINE';p.send_signal(signal.SIGINT)
    try:p.wait(timeout=10)
    except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=10)
    break
   time.sleep(.5)
 record={'label':label,'exit_code':p.returncode,'peak_rss_bytes':peak,'seconds':time.monotonic()-start,'interruption':cause}
 records.append(record);save(ART/'guard-result.json',{'records':records})
 print(label,p.returncode,round(peak/1024**2),'MiB',flush=True)
 if p.returncode or cause or (ART/'stop.json').exists():
  if not (ART/'stop.json').exists():save(ART/'stop.json',{'reason':cause or 'PROCESS_FAILURE','label':label})
  raise SystemExit(2)
run([str(Path(__file__).with_name('full_query.py'))],'known-candidate',540)
for i,case in enumerate(read(ART/'cases.json')):
 for arm in (('baseline','candidate') if i%2==0 else ('candidate','baseline')):
  run([str(Path(__file__).with_name('run_case.py')),arm,case['id']],case['id']+'-'+arm,180)
