"""ADR-1509 second mid-run change (user 2026-11-12 "작업을 1개로 줄일수 있을까?"): one request at a time so another
session's comparison cells (ADR-1511) can run beside this run.

The two drivers (W1 batch.py for risk, cm_lane.py for CM) were stopped while each had a request in flight; those
live.py children keep running and are adopted here (waited for, archived, worker-exit row under their worker).
Any case folder left without a worker-exit row is swept the same way. Then one lane runs every remaining case:
CM first (the user asked for the CM 정답률), then risk, same live.py and the same rules as batch.py. Then rerun.py
(alone) and collect.py.

  single_lane.py <pid:case:worker> [<pid:case:worker> ...]"""
from common import *
import subprocess,time,shutil
from archive_runtime import archive
LIMITS=read(DES/'criteria.json')['limits'];GIB=1024**3
def alive(pid):return Path('/proc/%d'%pid).exists()
def available():
    return next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
def allcalls():return [c for p in (ART/'live').glob('*/calls.json') for c in read(p)]
def log(msg):
    with (ART/'lanes.log').open('a') as f:f.write(time.strftime('%H:%M:%S')+' '+msg+'\n')
def row_for(cid,kind,worker,returncode,waited,packed):
    folder=ART/'live'/cid
    calls=read(folder/'calls.json') if (folder/'calls.json').exists() else []
    res=read(folder/'result.json') if (folder/'result.json').exists() else {}
    turn=(res.get('turns') or [{}])[-1]
    return {'case_id':cid,'kind':kind,'worker':worker,'returncode':returncode,'http_status':turn.get('http_status'),'seconds':turn.get('request_seconds'),
            'physical_calls':len(calls),'unknown':any(c['status'] in ('unknown','started') for c in calls),'claims':turn.get('claims',0),'waited':waited,'runtime_archive':packed}
def finish(cid,kind,worker,returncode,waited,extra=None):
    try:packed=archive(ART/'live'/cid)
    except Exception as exc:packed={'error':type(exc).__name__+': '+str(exc)[:300]}
    row=row_for(cid,kind,worker,returncode,waited,packed);row.update(extra or {})
    put(ART/'live'/cid/'worker-exit.json',row);log(json.dumps(row,ensure_ascii=False)[:220]);return row
def main():
    cases=read(DES/'cases.json');kinds={c['id']:c['kind'] for c in cases}
    adopt=[a.split(':') for a in sys.argv[1:]]
    log('single lane: adopt '+' '.join(sys.argv[1:]))
    for pid,cid,worker in adopt:
        while alive(int(pid)):time.sleep(5)
        finish(cid,kinds[cid],worker,None,0,{'adopted_after_worker_stop':True})
    for f in sorted((ART/'live').iterdir()):
        if f.is_dir() and not (f/'worker-exit.json').exists() and not f.name.endswith('-rerun'):
            finish(f.name,kinds[f.name],'swept',None,0,{'swept_after_worker_stop':True})
    t0=read(ART/'batch-first-start.json')['time'];results=[];cu=cf=0;stop=None
    order=[c for c in cases if c['kind']=='cm']+[c for c in cases if c['kind']!='cm']
    for case in order:
        cid=case['id']
        if (ART/'live'/cid).exists():continue
        claim=ART/'claims'/(cid+'.json')
        if claim.exists():
            if read(claim).get('worker')!='C':continue
        else:
            fd=os.open(claim,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
            with os.fdopen(fd,'w') as f:json.dump({'worker':'S','pid':os.getpid(),'time':time.time()},f)
        if (ART/'STOP_ALL.json').exists():stop='Operator stop file';break
        if shutil.disk_usage('/mnt/c').free<20*GIB or shutil.disk_usage(ROOT).free<25*GIB:stop='Disk floor before a new request (C: 20GiB / workspace 25GiB)';break
        waited=0
        while available()<LIMITS['ram_start_gib']*GIB and waited<LIMITS['wait_seconds']:
            time.sleep(15);waited+=15
        with (ART/'batch-S.log').open('a') as lf:
            lf.write('\n=== '+cid+' '+time.strftime('%H:%M:%S')+' waited '+str(waited)+'\n');lf.flush()
            proc=subprocess.Popen([sys.executable,str(TOOLS/'live.py'),cid],cwd=TOOLS,stdout=lf,stderr=subprocess.STDOUT,env={**os.environ})
            proc.wait()
        row=finish(cid,case['kind'],'S',proc.returncode,waited);results.append(row)
        folder=ART/'live'/cid;answered=row['http_status']==200
        cu=cu+1 if row['unknown'] and not answered else 0
        cf=cf+1 if (proc.returncode!=0 and not (folder/'turn-1/result.json').exists()) else 0
        if cf>=2:stop='Two consecutive runner or resource failures before an answer'
        elif cu>=3:stop='Three consecutive requests with an unknown model call and no answer'
        ac=allcalls()
        if len(ac)>=LIMITS['physical_total'] or sum((c.get('usage') or {}).get('cost',0) for c in ac)>=LIMITS['reported_cost_usd']:stop='Frozen experiment budget reached'
        put(ART/'batch-status-S.json',{'state':'STOPPED' if stop else 'RUNNING','completed':len(results),'cases':results,'stop':stop})
        if not stop and time.time()-t0>=LIMITS['time_box_minutes']*60:stop='Frozen time box reached'
        if stop:break
    put(ART/'batch-completed-S.json',{'state':'STOPPED' if stop else 'FINISHED','cases':results,'stop':stop,'quality_certified':False})
    log('single lane done stop=%s; rerun'%stop)
    with (ART/'run_all.stdout').open('a') as out:
        r=subprocess.run([sys.executable,str(TOOLS/'rerun.py')],cwd=TOOLS,stdout=(ART/'rerun.stdout').open('a'),stderr=subprocess.STDOUT);out.write('rerun exit %d\n'%r.returncode)
        c=subprocess.run([sys.executable,str(TOOLS/'collect.py')],cwd=TOOLS,stdout=(ART/'collect.stdout').open('w'),stderr=subprocess.STDOUT);out.write('collect exit %d\nALL_DONE\n'%c.returncode)
    log('ALL_DONE')
if __name__=='__main__':main()
