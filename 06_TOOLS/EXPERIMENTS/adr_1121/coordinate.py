"""Serial resource coordination only; runs already frozen experiment scripts."""
from common import *
import os,subprocess,time
out=ART/'coordination';out.mkdir(exist_ok=True)
def heavy():
 result=[]
 for p in Path('/proc').glob('[0-9]*/cmdline'):
  try:
   args=p.read_bytes().split(b'\0')
   if not args or b'python' not in args[0]:continue
   if any(b'06_TOOLS/EXPERIMENTS/' in a and (a.endswith(b'/live.py') or a.endswith(b'/replay.py')) for a in args):result.append(int(p.parent.name))
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 return [p for p in result if p!=os.getpid()]
while heavy():
 put(out/'waiting.json',{'blocking_processes':heavy(),'time':time.time(),'reason':'shared workspace heavy model/data execution; no concurrent loading'})
 time.sleep(10)
put(out/'started.json',{'time':time.time()})
for step,args in [('build',['build.py']),('baseline',['live.py','baseline']),('semantic',['live.py','semantic'])]:
 if step=='semantic' and read(ART/'build/result.json')['status']!='complete':break
 if step!='build':
  while heavy():time.sleep(10)
 log=out/(step+'.log')
 with log.open('w') as f:
  p=subprocess.run([str(ROOT/'.venv/bin/python'),str(Path(__file__).with_name(args[0])),*args[1:]],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
 put(out/(step+'-exit.json'),{'returncode':p.returncode,'time':time.time()})
 print(step,p.returncode,flush=True)
 if p.returncode:break
