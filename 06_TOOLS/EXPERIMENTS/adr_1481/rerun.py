"""After both workers finished: every question the resource guard stopped (resource-stop.json, no
answer) runs once more, alone, in its own folder (…-candidate-rerun). Frozen before the first model call
(criteria.json 'rerun'); nothing else is retried and a rerun is never repeated."""
from common import *
import subprocess,time
LIMITS=read(DES/'criteria.json')['limits']
def main():
 done=[read(ART/('batch-completed-W%s.json'%w)) for w in ('1','2') if (ART/('batch-completed-W%s.json'%w)).exists()]
 assert len(done)==2,'both workers must have finished'
 assert not (ART/'rerun-started.json').exists(),'reruns run once'
 todo=[]
 for case in read(DES/'live-cases.json'):
  folder=ART/'public-live'/(case['id']+'-candidate')
  if (folder/'resource-stop.json').exists() and not (folder/'turn-1/response.json.gz').exists():todo.append(case)
 put(ART/'rerun-started.json',{'time':time.time(),'cases':[c['id'] for c in todo]})
 rows=[]
 for case in todo:
  if (ART/'STOP_ALL.json').exists():break
  calls=[c for p in (ART/'public-live').glob('*/calls.json') for c in read(p)]
  if len(calls)>=LIMITS['physical_total']:break
  folder=ART/'public-live'/(case['id']+'-candidate-rerun')
  with (ART/'rerun.log').open('a') as log:
   log.write('\n=== '+case['id']+' rerun '+time.strftime('%H:%M:%S')+'\n');log.flush()
   proc=subprocess.run([sys.executable,str(Path(__file__).with_name('live_hybrid.py')),case['id'],'--rerun'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'ADR_PROFILE':case['provider_profile']})
  result=read(folder/'result.json') if (folder/'result.json').exists() else {};turn=(result.get('turns') or [{}])[-1]
  row={'case_id':case['id'],'returncode':proc.returncode,'http_status':turn.get('http_status'),'seconds':turn.get('request_seconds')}
  put(folder/'worker-exit.json',row);rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
 put(ART/'rerun-completed.json',{'cases':rows})
if __name__=='__main__':main()
