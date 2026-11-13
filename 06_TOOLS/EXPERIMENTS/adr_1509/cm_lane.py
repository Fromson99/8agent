"""ADR-1509 mid-run change (user 2026-11-12 "같이 진행할수 없냐 / 정답률 알려줘봐"): run CM and risk side by side
instead of risk first, keeping two concurrent requests (memory unchanged).

Worker W1 (batch.py, unchanged) keeps the risk queue; every CM case was claimed for lane C before W1 reached it.
Worker W2's batch process was stopped between bookkeeping steps; its in-flight request (a live.py child) kept
running and is adopted here: when it exits, its runtime is archived and its worker-exit row written as W2.
Then lane C runs the CM cases one at a time with the same live.py and the same rules as batch.py (RAM gate,
disk floor, stop rules, budget, time box). When lane C and W1 are both done: rerun.py (alone), then collect.py.

  cm_lane.py <adopt_pid> <adopt_case> <w1_pid>"""
from common import *
import subprocess,time,shutil
from archive_runtime import archive
LIMITS=read(DES/'criteria.json')['limits'];GIB=1024**3
ADOPT_PID,ADOPT_CASE,W1_PID=int(sys.argv[1]),sys.argv[2],int(sys.argv[3])
def alive(pid):return Path('/proc/%d'%pid).exists()
def available():
    return next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
def allcalls():return [c for p in (ART/'live').glob('*/calls.json') for c in read(p)]
def row_for(cid,kind,worker,returncode,waited,packed):
    folder=ART/'live'/cid
    calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
    res=read(folder/'result.json') if (folder/'result.json').exists() else {}
    turn=(res.get('turns') or [{}])[-1]
    return {'case_id':cid,'kind':kind,'worker':worker,'returncode':returncode,'http_status':turn.get('http_status'),'seconds':turn.get('request_seconds'),
            'physical_calls':len(calls),'unknown':any(c['status'] in ('unknown','started') for c in calls),'claims':turn.get('claims',0),'waited':waited,'runtime_archive':packed}
def log(msg):
    with (ART/'lanes.log').open('a') as f:f.write(time.strftime('%H:%M:%S')+' '+msg+'\n')
def main():
    cases=read(DES/'cases.json');kinds={c['id']:c['kind'] for c in cases}
    # 1. adopt W2's in-flight request.
    log('adopt %s pid %d'%(ADOPT_CASE,ADOPT_PID))
    while alive(ADOPT_PID):time.sleep(5)
    try:packed=archive(ART/'live'/ADOPT_CASE)
    except Exception as exc:packed={'error':type(exc).__name__+': '+str(exc)[:300]}
    row=row_for(ADOPT_CASE,kinds[ADOPT_CASE],'2',None,0,packed);row['adopted_after_worker_stop']=True
    put(ART/'live'/ADOPT_CASE/'worker-exit.json',row);log('adopted done '+json.dumps(row,ensure_ascii=False)[:200])
    # 2. lane C: the CM cases (claimed for this lane).
    t0=read(ART/'batch-first-start.json')['time'];results=[];cu=cf=0;stop=None
    for case in cases:
        if case['kind']!='cm':continue
        cid=case['id']
        claim=read(ART/'claims'/(cid+'.json'))
        if claim.get('worker')!='C' or (ART/'live'/cid).exists():continue
        if (ART/'STOP_ALL.json').exists():stop='Operator stop file';break
        if shutil.disk_usage('/mnt/c').free<20*GIB or shutil.disk_usage(ROOT).free<25*GIB:stop='Disk floor before a new request (C: 20GiB / workspace 25GiB)';break
        waited=0
        while available()<LIMITS['ram_start_gib']*GIB and waited<LIMITS['wait_seconds']:
            time.sleep(15);waited+=15
        with (ART/'batch-C.log').open('a') as lf:
            lf.write('\n=== '+cid+' '+time.strftime('%H:%M:%S')+' waited '+str(waited)+'\n');lf.flush()
            proc=subprocess.Popen([sys.executable,str(TOOLS/'live.py'),cid],cwd=TOOLS,stdout=lf,stderr=subprocess.STDOUT,env={**os.environ})
            proc.wait()
        folder=ART/'live'/cid
        try:packed=archive(folder)
        except Exception as exc:packed={'error':type(exc).__name__+': '+str(exc)[:300]}
        row=row_for(cid,'cm','C',proc.returncode,waited,packed);results.append(row);put(folder/'worker-exit.json',row)
        answered=row['http_status']==200
        cu=cu+1 if row['unknown'] and not answered else 0
        cf=cf+1 if (proc.returncode!=0 and not (folder/'turn-1/result.json').exists()) else 0
        if cf>=2:stop='Two consecutive runner or resource failures before an answer'
        elif cu>=3:stop='Three consecutive requests with an unknown model call and no answer'
        ac=allcalls()
        if len(ac)>=LIMITS['physical_total'] or sum((c.get('usage') or {}).get('cost',0) for c in ac)>=LIMITS['reported_cost_usd']:stop='Frozen experiment budget reached'
        put(ART/'batch-status-C.json',{'state':'STOPPED' if stop else 'RUNNING','completed':len(results),'cases':results,'stop':stop})
        log(json.dumps(row,ensure_ascii=False)[:220])
        if not stop and time.time()-t0>=LIMITS['time_box_minutes']*60:stop='Frozen time box reached'
        if stop:break
    put(ART/'batch-completed-C.json',{'state':'STOPPED' if stop else 'FINISHED','cases':results,'stop':stop,'quality_certified':False})
    log('lane C done stop=%s'%stop)
    # 3. after W1: reruns alone, then collection.
    while alive(W1_PID):time.sleep(15)
    log('W1 done; rerun')
    with (ART/'run_all.stdout').open('a') as out:
        r=subprocess.run([sys.executable,str(TOOLS/'rerun.py')],cwd=TOOLS,stdout=(ART/'rerun.stdout').open('a'),stderr=subprocess.STDOUT);out.write('rerun exit %d\n'%r.returncode)
        c=subprocess.run([sys.executable,str(TOOLS/'collect.py')],cwd=TOOLS,stdout=(ART/'collect.stdout').open('w'),stderr=subprocess.STDOUT);out.write('collect exit %d\nALL_DONE\n'%c.returncode)
    log('ALL_DONE')
if __name__=='__main__':main()
