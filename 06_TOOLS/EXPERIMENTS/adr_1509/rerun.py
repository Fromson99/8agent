"""After all workers: every case whose queue run had a provider failure (unknown / blank / 5xx / STOP file) or a
resource stop runs once more, alone and in order. Both runs are kept; the rerun counts (frozen rule)."""
from common import *
import subprocess,time
from archive_runtime import archive
def needs(cid):
    f=ART/'live'/cid
    if not f.is_dir():return None
    calls=read(f/'calls.json') if (f/'calls.json').exists() else []
    res=read(f/'result.json') if (f/'result.json').exists() else {}
    turn=(res.get('turns') or [{}])[-1]
    if (f/'resource-stop.json').exists() and turn.get('http_status')!=200:return 'resource stop'
    if (f/'STOP_EXTERNAL.json').exists() or any(c['status'] in ('unknown','started') or c.get('blank') for c in calls):return 'provider failure'
    if (f/'runner-failure.json').exists() and not turn:return 'runner failure'
    return None
def main():
    todo=[(c['id'],needs(c['id'])) for c in read(DES/'cases.json')]
    todo=[(i,w) for i,w in todo if w and not (ART/'live'/(i+'-rerun')).exists()]
    put(ART/'rerun-plan.json',{'cases':[{'case_id':i,'why':w} for i,w in todo]})
    out=[]
    for cid,why in todo:
        if (ART/'STOP_ALL.json').exists():break
        with (ART/'rerun.log').open('a') as log:
            log.write('\n=== '+cid+' '+why+' '+time.strftime('%H:%M:%S')+'\n');log.flush()
            proc=subprocess.run([sys.executable,str(TOOLS/'live.py'),cid,'--rerun'],cwd=TOOLS,stdout=log,stderr=subprocess.STDOUT)
        f=ART/'live'/(cid+'-rerun')
        try:archive(f)
        except Exception as exc:print('ARCHIVE_FAILED',cid,exc,flush=True)
        res=read(f/'result.json') if (f/'result.json').exists() else {}
        out.append({'case_id':cid,'why':why,'returncode':proc.returncode,'http_status':((res.get('turns') or [{}])[-1]).get('http_status')})
        put(ART/'rerun-status.json',{'cases':out})
    print('RERUN_DONE',len(out),flush=True)
if __name__=='__main__':main()
