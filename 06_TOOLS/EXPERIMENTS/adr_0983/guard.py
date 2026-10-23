"""One memory-heavy process; preserve interruption/partial outcome."""
from common import *
import subprocess,time,signal,sys
kind=sys.argv[1];assert kind in ('full','trials','assessments')
def available():return next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
def run(args,label,max_rss,timeout):
 assert available()>=3*1024**3
 log=ART/(label+'.log');assert not log.exists()
 before=time.monotonic();peak=0;cause=None
 with log.open('x') as f:
  p=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-B',*args],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
  while p.poll() is None:
   path=Path(f'/proc/{p.pid}/status');rss=next((int(x.split()[1])*1024 for x in path.read_text().splitlines() if x.startswith('VmRSS:')),0) if path.exists() else 0;peak=max(peak,rss)
   if rss>max_rss or available()<3*1024**3 or time.monotonic()-before>timeout:
    cause='RSS_LIMIT' if rss>max_rss else 'RAM_PRESSURE' if available()<3*1024**3 else 'TIMEOUT';p.send_signal(signal.SIGINT)
    try:p.wait(timeout=15)
    except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=15)
    break
   time.sleep(.5)
 save(ART/(label+'-resource.json'),{'exit_code':p.returncode,'cause':cause,'peak_rss_bytes':peak,'seconds':time.monotonic()-before})
 print(label,'exit',p.returncode,'peak MiB',round(peak/1024**2),'cause',cause,flush=True)
 if p.returncode or cause:raise SystemExit(1)
if kind=='full':run([str(Path(__file__).with_name('full_query.py'))],'known-query',10*1024**3,1500)
elif kind=='trials':
 for i,case in enumerate(read(ART/'cases.json')):
  for arm in (('baseline','candidate') if i%2==0 else ('candidate','baseline')):
   run([str(Path(__file__).with_name('run_case.py')),arm,case['id']],f'trial-{case["id"]}-{arm}',1024**3,180)

if kind=='assessments':
 for case in read(ART/'assessment-cases.json'):
  for arm in ('baseline','candidate'):
   run([str(Path(__file__).with_name('assessment_case.py')),arm,case['id']],f'assessment-{case["id"]}-{arm}',1024**3,180)
