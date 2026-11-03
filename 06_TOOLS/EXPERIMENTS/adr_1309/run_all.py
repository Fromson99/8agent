from common import *
import subprocess,time
out=[]
for cell in read(DES/'criteria.json')['order']:
 case,arm=cell.split('/')
 if (ART/'STOP_EXTERNAL.json').exists():
  out.append({'case':case,'arm':arm,'status':'NOT_RUN','reason':read(ART/'STOP_EXTERNAL.json')['reason']});continue
 log=ART/(case+'-'+arm+'.log')
 with log.open('x') as stream:
  print('START SQLite',case,arm,flush=True);begin=time.monotonic()
  try:
   p=subprocess.run([str(ROOT/'.venv/bin/python'),str(Path(__file__).parent/'live.py'),case,arm],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=2100)
   rc=p.returncode
  except subprocess.TimeoutExpired:rc=124
 row={'case':case,'arm':arm,'exit_code':rc,'wall_seconds':time.monotonic()-begin,'log':str(log.relative_to(ROOT))};out.append(row);put(ART/'execution-progress.json',out);print('FINISH',json.dumps(row),flush=True)
 if rc:put(ART/'STOP_EXTERNAL.json',{'cell':cell,'reason':'runner/resource failure','exit_code':rc})
put(ART/'execution-progress.json',out)
