"""One worker of a full run: takes the next unclaimed case from the shared queue and runs it once in a fresh
process (live.py). Workers ADR_WORKER=1..N share one queue; no automatic request retries.
After every worker finished, rerun.py runs provider/resource-stopped cases once more alone."""
from common import *
import subprocess,time
WORKER=os.environ.get('ADR_WORKER','1');SUF='-W'+WORKER
LIMITS=read(DES/'criteria.json')['limits']
GIB=1024**3
def claim(cid):
    d=ART/'claims';d.mkdir(exist_ok=True)
    try:fd=os.open(d/(cid+'.json'),os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:return False
    with os.fdopen(fd,'w') as f:json.dump({'worker':WORKER,'pid':os.getpid(),'time':time.time()},f)
    return True
def available():
    m={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')}
    return m['MemAvailable']
def allcalls():return [c for p in (ART/'live').glob('*/calls.json') for c in read(p)]
def main():
    cases=read(DES/'cases.json');results=[];cu=0;cf=0;stop=None
    if (ART/('batch-started'+SUF+'.json')).exists():raise RuntimeError('worker already ran')
    started=time.time();put(ART/('batch-started'+SUF+'.json'),{'time':started,'pid':os.getpid(),'worker':WORKER})
    first=ART/'batch-first-start.json'
    try:
        fd=os.open(first,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,json.dumps({'time':started}).encode());os.close(fd)
    except FileExistsError:pass
    t0=read(first)['time']
    for case in cases:
        cid=case['id']
        if (ART/'STOP_ALL.json').exists():stop='Operator stop file';break
        if (ART/'live'/cid).exists() or not claim(cid):continue
        waited=0
        while available()<LIMITS['ram_start_gib']*GIB and waited<LIMITS['wait_seconds']:
            time.sleep(15);waited+=15
        with (ART/('batch'+SUF+'.log')).open('a') as log:
            log.write('\n=== '+cid+' '+time.strftime('%H:%M:%S')+' waited '+str(waited)+'\n');log.flush()
            proc=subprocess.Popen([sys.executable,str(TOOLS/'live.py'),cid],cwd=TOOLS,stdout=log,stderr=subprocess.STDOUT,env={**os.environ})
            proc.wait()
        folder=ART/'live'/cid
        calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
        result=read(folder/'result.json') if (folder/'result.json').exists() else {}
        turn=(result.get('turns') or [{}])[-1]
        unknown=any(c['status'] in ('unknown','started') for c in calls)
        row={'case_id':cid,'kind':case['kind'],'worker':WORKER,'returncode':proc.returncode,'http_status':turn.get('http_status'),'seconds':turn.get('request_seconds'),
             'physical_calls':len(calls),'unknown':unknown,'claims':turn.get('claims',0),'waited':waited}
        results.append(row);put(folder/'worker-exit.json',row)
        answered=turn.get('http_status')==200
        cu=cu+1 if unknown and not answered else 0
        failed=proc.returncode!=0 and not (folder/'turn-1/result.json').exists()
        cf=cf+1 if failed else 0
        if cf>=2:stop='Two consecutive runner or resource failures before an answer'
        elif cu>=3:stop='Three consecutive requests with an unknown model call and no answer'
        ac=allcalls()
        if len(ac)>=LIMITS['physical_total'] or sum((c.get('usage') or {}).get('cost',0) for c in ac)>=LIMITS['reported_cost_usd']:stop='Frozen experiment budget reached'
        put(ART/('batch-status'+SUF+'.json'),{'state':'STOPPED' if stop else 'RUNNING','completed':len(results),'cases':results,'stop':stop,'physical_calls_all_workers':len(ac)})
        print(json.dumps(row,ensure_ascii=False),flush=True)
        if not stop and time.time()-t0>=LIMITS['time_box_minutes']*60:stop='Frozen time box reached'
        if stop:break
    put(ART/('batch-completed'+SUF+'.json'),{'state':'STOPPED' if stop else 'FINISHED','cases':results,'stop':stop,'quality_certified':False})
    print('DONE',stop,flush=True)
if __name__=='__main__':main()
