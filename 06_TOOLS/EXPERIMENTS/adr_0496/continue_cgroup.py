"""Resume never-sent cases under a3GiB whole-worker cgroup, one at a time."""
import argparse,json,subprocess,time,sys,os
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0496-qwen-source-workflow-cm51-fsc10';ART=A/'artifacts';S=Path(__file__).parent;GiB=2**30

def read(p):return json.loads(p.read_text())
def mem():
 d={l.split(':')[0]:int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if len(l.split())>=2 and l.split()[1].isdigit()};return {k:d[k] for k in ['MemAvailable','SwapFree','SwapTotal']}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output-name',default='cgroup-continuation');args=parser.parse_args()
 if Path(args.output_name).name!=args.output_name:raise ValueError('output-name must be a directory name')
 out=ART/args.output_name;out.mkdir(exist_ok=False)
 cases=[c for c in read(A/'product-cases.json')['cases'] if not (ART/'run-001'/c['case_id']/'repaired').exists()]
 plan={'created_at':time.time(),'cases':[c['case_id'] for c in cases],'parallelism':1,'memory_max_bytes':3*GiB,'memory_high_bytes':2560*2**20,'swap_max_bytes':0,'minimum_host_available_during_execution':2*GiB,'minimum_host_available_before_execution':5*GiB,'model_attempts_per_case':14,'product_code_changed':False,'preflight_receipt':'extra-worker-memory-samples.json','note':'One additional Qwen worker alongside existing other experiment. No completed/model-started case retried. Host guard stops only this scope.'}
 (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 for case in cases:
  cid=case['case_id'];wait_start=time.time()
  while mem()['MemAvailable']<5*GiB:
   if time.time()-wait_start>300:
    (out/'blocked.json').write_text(json.dumps({'case':cid,'memory':mem(),'reason':'START_HEADROOM_NOT_RECOVERED_300S'},indent=2)+'\n');return
   time.sleep(2)
  unit='codex-adr0496-'+cid;cg=Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice')/(unit+'.scope')
  cmd=['systemd-run','--user','--scope','--collect','--unit='+unit,'-p','MemoryHigh=2560M','-p','MemoryMax=3G','-p','MemorySwapMax=0',str(R/'.venv/bin/python'),str(S/'run_probe.py'),'--case',cid,'--arm','repaired','--run','run-001','--execute']
  started=time.time();samples=[];breach=None
  with (out/(cid+'.log')).open('w') as log:
   proc=subprocess.Popen(cmd,cwd=R,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},stdout=log,stderr=subprocess.STDOUT)
   while proc.poll() is None:
    host=mem();sample={'at':time.time(),**host}
    if cg.exists():
     for name in ['memory.current','memory.peak','memory.max','memory.swap.current','memory.events','cgroup.procs']:
      try:sample[name]=(cg/name).read_text().strip()
      except FileNotFoundError:pass
    samples.append(sample)
    status=out/'status.tmp';status.write_text(json.dumps({'case_id':cid,'updated_at':time.time(),'started_at':started,'memory':sample},indent=2)+'\n');status.replace(out/'status.json')
    if host['MemAvailable']<2*GiB:breach='HOST_AVAILABLE_BELOW_2GIB'
    if time.time()-started>600:breach='WALL_LIMIT_600S'
    if breach:
     subprocess.run(['systemctl','--user','stop',unit+'.scope'],stdout=log,stderr=log);break
    time.sleep(1)
   try:code=proc.wait(timeout=15)
   except subprocess.TimeoutExpired:proc.terminate();code=proc.wait(timeout=10)
  receipt={'case_id':cid,'started_at':started,'finished_at':time.time(),'returncode':code,'guard_breach':breach,'minimum_available_bytes':min(x['MemAvailable'] for x in samples),'maximum_cgroup_memory_peak_bytes':max((int(x.get('memory.peak',0)) for x in samples),default=0),'samples':samples}
  (out/(cid+'.resource.json')).write_text(json.dumps(receipt,indent=2)+'\n');print(cid,'exit',code,'guard',breach,'peak_GiB',round(receipt['maximum_cgroup_memory_peak_bytes']/GiB,3),flush=True)
  if code or breach or not (ART/'run-001'/cid/'repaired/result.json').exists():return
 (out/'finished.json').write_text(json.dumps({'finished_at':time.time(),'cases':plan['cases']},indent=2)+'\n')
if __name__=='__main__':main()
