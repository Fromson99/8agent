from common import *
import subprocess,time
cells=[('ontology-365','baseline'),('ontology-365','ontology-on'),('ontology-369','ontology-on'),('ontology-369','baseline')]
out=[]
for case,arm in cells:
 if (ART/'STOP_EXTERNAL.json').exists():
  out.append({'case':case,'arm':arm,'status':'NOT_RUN','reason':'prior unknown physical outcome'});continue
 log=ART/(case+'-'+arm+'.log')
 with log.open('x') as stream:
  print('START',case,arm,flush=True);begin=time.monotonic()
  p=subprocess.run([str(ROOT/'.venv/bin/python'),str(Path(__file__).parent/'live.py'),case,arm],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=2100)
 row={'case':case,'arm':arm,'exit_code':p.returncode,'wall_seconds':time.monotonic()-begin,'log':str(log.relative_to(ROOT))};out.append(row);put(ART/'execution-progress.json',out);print('FINISH',json.dumps(row),flush=True)
 result_path=ART/'live'/(case+'-'+arm)/'result.json'
 result=read(result_path) if result_path.exists() else {}
 if p.returncode or (result.get('http_status',0)>=500 and not result.get('unknown')):
  put(ART/'STOP_EXTERNAL.json',{'cell':case+'-'+arm,'reason':'runner/resource failure; inspect before further dispatch','exit_code':p.returncode})
put(ART/'execution-progress.json',out)
