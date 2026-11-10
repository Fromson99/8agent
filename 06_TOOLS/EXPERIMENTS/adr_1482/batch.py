"""One worker of the ADR-1482 run: takes the next unclaimed question from the shared queue and runs it
once in a fresh process with the candidate tree of the question's provider profile. Two workers
(ADR_WORKER=1, 2) run at the same time; no automatic request retries."""
from common import *
import subprocess,time,urllib.request
PORT=int(os.environ.get('ADR1468_EMBED_PORT','8765'))
WORKER=os.environ.get('ADR_WORKER','1');assert WORKER in ('1','2')
SUF='-W'+WORKER
LIMITS=read(DES/'criteria.json')['limits']

def claim(cid):
 """Atomic claim of one question by this worker; a claimed question is never run twice."""
 d=ART/'claims';d.mkdir(exist_ok=True)
 try:fd=os.open(d/(cid+'.json'),os.O_CREAT|os.O_EXCL|os.O_WRONLY)
 except FileExistsError:return False
 with os.fdopen(fd,'w') as f:json.dump({'worker':WORKER,'pid':os.getpid(),'time':time.time()},f)
 return True

def allcalls():
 return [c for p in (ART/'public-live').glob('*/calls.json') for c in read(p)]

def main():
 cases=read(DES/'live-cases.json');results=[];consecutive_unknown=0;consecutive_failed=0;stop=None
 if (ART/('batch-started'+SUF+'.json')).exists():raise RuntimeError('Existing worker may not be replayed')
 with urllib.request.urlopen('http://127.0.0.1:%d/health'%PORT,timeout=5) as r:assert r.status==200,'embedding endpoint not ready'
 pre=sorted((ART/'public-ready').glob('*/result.json'));assert len(pre)>=3 and all(read(p).get('ready') for p in pre),'preflight of every provider profile required'
 started=time.time();put(ART/('batch-started'+SUF+'.json'),{'time':started,'pid':os.getpid(),'worker':WORKER})
 first=ART/'batch-first-start.json'
 if not first.exists():
  try:
   fd=os.open(first,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,json.dumps({'time':started}).encode());os.close(fd)
  except FileExistsError:pass
 t0=read(first)['time']
 for case in cases:
  cid=case['id']
  if (ART/'STOP_ALL.json').exists():stop='Operator stop file';break
  if not claim(cid):continue
  folder=ART/'public-live'/(cid+'-candidate')
  with (ART/('batch'+SUF+'.log')).open('a') as log:
   log.write('\n=== '+cid+' profile '+case['provider_profile']+' '+time.strftime('%H:%M:%S')+'\n');log.flush()
   proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('live_hybrid.py')),cid],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'ADR_PROFILE':case['provider_profile']})
   proc.wait()
  calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
  result=read(folder/'result.json') if (folder/'result.json').exists() else {}
  turns=result.get('turns',[]);turn=turns[-1] if turns else {}
  unknown=any(c['status'] in ('unknown','started') for c in calls)
  row={'case_id':cid,'worker':WORKER,'provider_profile':case['provider_profile'],'returncode':proc.returncode,'http_status':turn.get('http_status'),'seconds':turn.get('request_seconds'),'physical_calls':len(calls),'unknown':unknown,'claims':turn.get('claims',0),'needs_guidance':turn.get('needs_guidance')}
  results.append(row);put(folder/'worker-exit.json',row)
  answered=turn.get('http_status')==200
  consecutive_unknown=consecutive_unknown+1 if unknown and not answered else 0
  failed=proc.returncode!=0 and not (proc.returncode==125 and (folder/'turn-1/result.json').exists())
  consecutive_failed=consecutive_failed+1 if failed else 0
  if consecutive_failed>=2:stop='Two consecutive runner or resource failures before an answer'
  elif consecutive_unknown>=3:stop='Three consecutive questions with an unknown model call and no answer'
  calls_all=allcalls()
  if len(calls_all)>=LIMITS['physical_total'] or sum((c.get('usage') or {}).get('cost',0) for c in calls_all)>=LIMITS['reported_cost_usd']:stop='Frozen experiment budget reached'
  put(ART/('batch-status'+SUF+'.json'),{'state':'STOPPED' if stop else 'RUNNING','completed_requests':len(results),'cases':results,'stop':stop,'physical_calls_all_workers':len(calls_all)})
  print(json.dumps(row,ensure_ascii=False),flush=True)
  subprocess.run([sys.executable,str(Path(__file__).with_name('progress.py'))],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=180)
  if not stop and time.time()-t0>=LIMITS['time_box_minutes']*60:stop='Frozen time box reached before the next question'
  if stop:break
 status='STOPPED' if stop else 'EXECUTION_FINISHED_REVIEW_REQUIRED'
 put(ART/('batch-completed'+SUF+'.json'),{'state':status,'cases':results,'stop':stop,'quality_certified':False})
 print(status,flush=True)

if __name__=='__main__':main()
