from common import *
import subprocess, time, signal
assert not (ART/'stop.json').exists() and not (ART/'known-query').exists()
def available():
    return next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
outcomes=[]
for arm in read(ART/'stage.json')['arm_order']:
    if (ART/'stop.json').exists():break
    assert available()>4*1024**3
    start=time.monotonic(); peak=0; cause=None
    with (ART/f'known-{arm}.log').open('x') as stream:
        p=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-B',str(Path(__file__).with_name('full_query.py')),arm],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        while p.poll() is None:
            try:rss=next((int(x.split()[1])*1024 for x in Path(f'/proc/{p.pid}/status').read_text().splitlines() if x.startswith('VmRSS:')),0)
            except FileNotFoundError:rss=0
            peak=max(peak,rss)
            if rss>6*1024**3 or available()<4*1024**3 or time.monotonic()-start>1860:
                cause='MEMORY_OR_DEADLINE';p.send_signal(signal.SIGINT)
                try:p.wait(timeout=10)
                except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=10)
                save(ART/'stop.json',{'reason':cause,'arm':arm});break
            time.sleep(.5)
    outcome={'arm':arm,'exit_code':p.returncode,'peak_rss_bytes':peak,'seconds':time.monotonic()-start,'interruption':cause}
    save(ART/f'known-{arm}-resources.json',outcome);outcomes.append(outcome)
    print(json.dumps(outcome),flush=True)
    if p.returncode not in (0,2,3):
        save(ART/'stop.json',{'reason':'RUNNER_FAILURE','arm':arm});break
save(ART/'guard-result.json',{'outcomes':outcomes,'stop':read(ART/'stop.json') if (ART/'stop.json').exists() else None})
