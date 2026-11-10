"""Deviation (deviation-host-restart.json): the WSL host restarted at about 17:17 while worker 2 was in
cm-042 and worker 1 had already stopped on two resource failures. Nothing else in the frozen design changes.

1. Questions never claimed run once each, in the frozen order, with ONE worker ('3'), into the normal
   …-candidate folder and with the frozen stop rules (two runner/resource failures, three unknowns,
   budget, operator stop file). One worker instead of two because 8 of 41 questions hit the resource guard.
2. cm-042, cut by the restart before an answer, gets worker-exit.json marking the interruption and then
   the single rerun every unanswered question gets.
3. The frozen single rerun of resource-stopped questions (rerun.py rule) runs; rerun.py itself asserts that
   both original workers wrote batch-completed, which worker 2 never could after the restart.
4. rerun_external.py and progress.py run unchanged afterwards (from the shell driver)."""
from common import *
import subprocess,time,urllib.request
PORT=int(os.environ.get('ADR1468_EMBED_PORT','8765'))
LIMITS=read(DES/'criteria.json')['limits']
WORKER='3'

def allcalls():
 return [c for p in (ART/'public-live').glob('*/calls.json') for c in read(p)]

def claim(cid):
 d=ART/'claims'
 try:fd=os.open(d/(cid+'.json'),os.O_CREAT|os.O_EXCL|os.O_WRONLY)
 except FileExistsError:return False
 with os.fdopen(fd,'w') as f:json.dump({'worker':WORKER,'pid':os.getpid(),'time':time.time(),'after_restart':True},f)
 return True

def run(cid,profile,rerun,log_name):
 with (ART/log_name).open('a') as log:
  log.write('\n=== '+cid+(' rerun' if rerun else '')+' (after restart) '+time.strftime('%H:%M:%S')+'\n');log.flush()
  return subprocess.run([sys.executable,str(Path(__file__).with_name('live_hybrid.py')),cid]+(['--rerun'] if rerun else []),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'ADR_PROFILE':profile})

def outcome(folder,proc):
 calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
 result=read(folder/'result.json') if (folder/'result.json').exists() else {}
 turn=(result.get('turns') or [{}])[-1]
 return calls,turn

def main():
 cases=read(DES/'live-cases.json')
 with urllib.request.urlopen('http://127.0.0.1:%d/health'%PORT,timeout=5) as r:assert r.status==200,'embedding endpoint not ready'
 dev=ART/'deviation-host-restart.json'
 if not dev.exists():
  put(dev,{'time':time.time(),'reason':'WSL host restart at about 17:17 local time killed worker 2 during cm-042 and the queued reruns; worker 1 had already stopped on two consecutive resource failures.','change':'unclaimed questions run with one worker (3) instead of two; cm-042 gets the single rerun; the frozen resource-stop rerun runs without the both-workers-completed assertion','frozen_rule_changed':False,'models_prompts_code_unchanged':True})
 # 1. unclaimed questions, one worker
 results=[];cu=0;cf=0;stop=None
 put(ART/'batch-started-W3.json',{'time':time.time(),'pid':os.getpid(),'worker':WORKER})
 for case in cases:
  cid=case['id']
  if (ART/'STOP_ALL.json').exists():stop='Operator stop file';break
  if not claim(cid):continue
  folder=ART/'public-live'/(cid+'-candidate')
  proc=run(cid,case['provider_profile'],False,'batch-W3.log')
  calls,turn=outcome(folder,proc)
  unknown=any(c['status'] in ('unknown','started') for c in calls)
  row={'case_id':cid,'worker':WORKER,'provider_profile':case['provider_profile'],'returncode':proc.returncode,'http_status':turn.get('http_status'),'seconds':turn.get('request_seconds'),'physical_calls':len(calls),'unknown':unknown,'claims':turn.get('claims',0),'needs_guidance':turn.get('needs_guidance')}
  results.append(row);put(folder/'worker-exit.json',row);print(json.dumps(row,ensure_ascii=False),flush=True)
  answered=turn.get('http_status')==200
  cu=cu+1 if unknown and not answered else 0
  failed=proc.returncode!=0 and not (proc.returncode==125 and (folder/'turn-1/result.json').exists())
  cf=cf+1 if failed else 0
  if cf>=2:stop='Two consecutive runner or resource failures before an answer'
  elif cu>=3:stop='Three consecutive questions with an unknown model call and no answer'
  ca=allcalls()
  if len(ca)>=LIMITS['physical_total'] or sum((c.get('usage') or {}).get('cost',0) for c in ca)>=LIMITS['reported_cost_usd']:stop='Frozen experiment budget reached'
  put(ART/'batch-status-W3.json',{'state':'STOPPED' if stop else 'RUNNING','completed_requests':len(results),'cases':results,'stop':stop,'physical_calls_all_workers':len(ca)})
  subprocess.run([sys.executable,str(Path(__file__).with_name('progress.py'))],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=180)
  if stop:break
 put(ART/'batch-completed-W3.json',{'state':'STOPPED' if stop else 'EXECUTION_FINISHED_REVIEW_REQUIRED','cases':results,'stop':stop,'quality_certified':False})
 # 2. cm-042 interrupted by the restart
 f42=ART/'public-live'/'cm-042-candidate'
 if f42.exists() and not (f42/'worker-exit.json').exists() and not (f42/'turn-1/response.json.gz').exists():
  put(f42/'worker-exit.json',{'case_id':'cm-042','worker':'2','returncode':None,'http_status':None,'interrupted_by':'host restart','time':time.time()})
 # 3. single rerun of every unanswered question (resource stop or restart), once
 if (ART/'rerun-started.json').exists():print('reruns already started');return
 todo=[]
 for case in cases:
  folder=ART/'public-live'/(case['id']+'-candidate')
  ex=read(folder/'worker-exit.json') if (folder/'worker-exit.json').exists() else {}
  if ((folder/'resource-stop.json').exists() or ex.get('interrupted_by')) and not (folder/'turn-1/response.json.gz').exists() and not (ART/'public-live'/(case['id']+'-candidate-rerun')).exists():todo.append(case)
 put(ART/'rerun-started.json',{'time':time.time(),'cases':[c['id'] for c in todo],'after_restart':True})
 rows=[]
 for case in todo:
  if (ART/'STOP_ALL.json').exists():break
  if len(allcalls())>=LIMITS['physical_total']:break
  folder=ART/'public-live'/(case['id']+'-candidate-rerun')
  proc=run(case['id'],case['provider_profile'],True,'rerun.log')
  calls,turn=outcome(folder,proc)
  row={'case_id':case['id'],'returncode':proc.returncode,'http_status':turn.get('http_status'),'seconds':turn.get('request_seconds')}
  put(folder/'worker-exit.json',row);rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
  subprocess.run([sys.executable,str(Path(__file__).with_name('progress.py'))],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=180)
 put(ART/'rerun-completed.json',{'cases':rows})

if __name__=='__main__':main()
