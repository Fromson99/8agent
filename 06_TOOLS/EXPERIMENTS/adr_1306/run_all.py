from common import *
import subprocess,time
out=[]
for case in ('ontology-365','ontology-369'):
 if (ART/'STOP_EXTERNAL.json').exists():
  out.append({'case':case,'arm':'review-off','status':'NOT_RUN','reason':read(ART/'STOP_EXTERNAL.json')['reason']});continue
 log=ART/(case+'-review-off.log')
 with log.open('x') as stream:
  print('START SQLite',case,flush=True);begin=time.monotonic()
  p=subprocess.run([str(ROOT/'.venv/bin/python'),str(Path(__file__).parent/'live.py'),case,'review-off'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=2100)
 row={'case':case,'arm':'review-off','exit_code':p.returncode,'wall_seconds':time.monotonic()-begin,'log':str(log.relative_to(ROOT))};out.append(row);put(ART/'execution-progress.json',out);print('FINISH',json.dumps(row),flush=True)
 if p.returncode:put(ART/'STOP_EXTERNAL.json',{'cell':case,'reason':'runner/resource failure','exit_code':p.returncode})
put(ART/'execution-progress.json',out)
