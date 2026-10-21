from common import *
import subprocess,time,signal
started=time.monotonic()
for index,case in enumerate(read(ART/'cases.json')):
    for arm in (('baseline','candidate') if index%2==0 else ('candidate','baseline')):
        out=ART/'trials'/case['id']/arm
        if out.exists():raise RuntimeError('No implicit replay of existing trial '+str(out))
        assert time.monotonic()-started<7200
        available=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
        assert available>3*1024**3
        log=ART/f'trial-{case["id"]}-{arm}.log'
        with log.open('x') as f:
            proc=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-B',str(Path(__file__).with_name('run_case.py')),arm,case['id']],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
            start=time.monotonic()
            while proc.poll() is None:
                stat=Path(f'/proc/{proc.pid}/status')
                rss=next((int(line.split()[1])*1024 for line in stat.read_text().splitlines() if line.startswith('VmRSS:')),0) if stat.exists() else 0
                if rss>1024**3 or time.monotonic()-start>240:
                    proc.send_signal(signal.SIGINT);proc.wait(timeout=15)
                    raise RuntimeError('resource/time limit; partial trial preserved')
                time.sleep(.5)
        if proc.returncode:raise RuntimeError('trial implementation failure; inspect '+str(log))
        r=read(out/'result.json')
        print(case['id'],arm,'calls',r['model_calls'],'error',r['error'] and r['error']['type'],flush=True)
