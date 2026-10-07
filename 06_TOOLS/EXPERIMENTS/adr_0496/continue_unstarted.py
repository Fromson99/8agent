"""Resource-guarded first attempts only; never reruns or overwrites existing cases."""
import json,os,signal,subprocess,sys,time,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0496-qwen-source-workflow-cm51-fsc10';S=Path(__file__).parent;ART=A/'artifacts'
GiB=1024**3;MAX_RSS=int(3.5*GiB);MIN_AVAILABLE=4*GiB;MIN_SWAP_FREE=GiB;MAX_AS=6*GiB

def read(p):return json.loads(p.read_text())
def mem():
 d={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if len(x.split())>=2 and x.split()[1].isdigit()}
 return {k:d[k] for k in ['MemAvailable','SwapFree','SwapTotal']}
def rss(pid):
 try:
  text=Path(f'/proc/{pid}/status').read_text();return next(int(x.split()[1])*1024 for x in text.splitlines() if x.startswith('VmRSS:'))
 except (FileNotFoundError,StopIteration,ProcessLookupError):return 0

def main():
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--preflight-only',action='store_true');args=ap.parse_args()
 fixture=read(A/'product-cases.json');pending=[c for c in fixture['cases'] if not (ART/'run-001'/c['case_id']/'repaired').exists()]
 out=ART/('resource-preflight' if args.preflight_only else 'resource-continuation');out.mkdir(exist_ok=False)
 plan={'created_at':time.time(),'parallelism':1,'rss_max_bytes':MAX_RSS,'minimum_host_available_bytes':MIN_AVAILABLE,'minimum_swap_free_bytes':MIN_SWAP_FREE,'address_space_hard_limit_bytes':MAX_AS,'worker_wall_hard_seconds':600,'cases':[c['case_id'] for c in pending[:1] if args.preflight_only] if args.preflight_only else [c['case_id'] for c in pending],'product_runner_sha256':hashlib.sha256((S/'run_probe.py').read_bytes()).hexdigest(),'product_code_changed':False,'existing_case_directories_never_retried':True,'note':'First attempts only within original max4 concurrency plan, reduced to1 after host OOM; resource environment change reported separately.'}
 (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 for case in pending[:1] if args.preflight_only else pending:
  cid=case['case_id'];before=mem()
  if before['MemAvailable']<MIN_AVAILABLE+MAX_RSS or (before['SwapTotal'] and before['SwapFree']<MIN_SWAP_FREE):
   (out/'blocked.json').write_text(json.dumps({'case':cid,'reason':'INSUFFICIENT_START_HEADROOM','memory':before},indent=2)+'\n');print('Resource guard: insufficient start headroom',flush=True);return
  worker=[str(R/'.venv/bin/python'),str(S/'run_probe.py'),'--case',cid,'--arm','repaired','--run','run-001']
  if not args.preflight_only:worker.append('--execute')
  launcher='import os,resource,sys; resource.setrlimit(resource.RLIMIT_AS,('+str(MAX_AS)+','+str(MAX_AS)+')); os.execv(sys.argv[1],sys.argv[1:])'
  started=time.time();samples=[];breach=None
  with (out/(cid+'.log')).open('w') as log:
   p=subprocess.Popen([sys.executable,'-c',launcher,*worker],cwd=R,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   while p.poll() is None:
    host=mem();sample={'at':time.time(),'pid':p.pid,'rss_bytes':rss(p.pid),**host};samples.append(sample)
    if sample['rss_bytes']>MAX_RSS:breach='WORKER_RSS_LIMIT'
    elif host['MemAvailable']<MIN_AVAILABLE:breach='HOST_AVAILABLE_LIMIT'
    elif host['SwapTotal'] and host['SwapFree']<MIN_SWAP_FREE:breach='HOST_SWAP_LIMIT'
    elif time.time()-started>600:breach='WORKER_WALL_LIMIT'
    if breach:
     os.killpg(p.pid,signal.SIGTERM)
     try:p.wait(timeout=10)
     except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
     break
    time.sleep(1)
   code=p.wait()
  receipt={'case_id':cid,'pid':p.pid,'started_at':started,'finished_at':time.time(),'returncode':code,'guard_breach':breach,'max_rss_bytes':max((s['rss_bytes'] for s in samples),default=0),'minimum_available_bytes':min((s['MemAvailable'] for s in samples),default=0),'samples':samples}
  (out/(cid+'.resource.json')).write_text(json.dumps(receipt,indent=2)+'\n')
  print(cid,'exit',code,'guard',breach,'peak_GiB',round(receipt['max_rss_bytes']/GiB,3),flush=True)
  if code or breach:return
  result=ART/('preflight-001' if args.preflight_only else 'run-001')/cid/'repaired/result.json'
  if not result.exists():raise RuntimeError('No final case receipt; do not launch further workers')
 (out/'finished.json').write_text(json.dumps({'finished_at':time.time(),'cases':plan['cases']},indent=2)+'\n')
if __name__=='__main__':main()
