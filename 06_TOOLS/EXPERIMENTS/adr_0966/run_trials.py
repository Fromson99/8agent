"""Sequential fixed-order experiment, no replacement trial or automatic rerun."""
from common import *
import subprocess,time,sys
start=time.monotonic();events=[]
runner=Path(__file__).with_name('run_case.py')
manifest=read(ADR/'실험/manifest.json')
assert sha(runner)==manifest['design']['code_isolation']['candidates'][0]['runner_sha256']
for i,case in enumerate(read(ART/'cases.json'),1):
    for arm in (('baseline','candidate') if i%2 else ('candidate','baseline')):
        memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
        assert int(memory['MemAvailable'].split()[0])*1024>=4*1024**3,'low available RAM'
        assert time.monotonic()-start<2400,'experiment wall budget exhausted'
        log=ART/f"trial-{case['id']}-{arm}.log"
        with log.open('x') as f:
            try:
                done=subprocess.run([str(ROOT/'.venv/bin/python'),str(runner),arm,case['id']],stdout=f,stderr=subprocess.STDOUT,timeout=330)
            except subprocess.TimeoutExpired:
                events.append({'case':case['id'],'arm':arm,'status':'TIMEOUT','seconds':time.monotonic()-start})
                save(ART/'trial-processes.json',events);raise
        result=ART/'trials'/case['id']/arm/'result.json'
        events.append({'case':case['id'],'arm':arm,'exit_code':done.returncode,'result_sha256':sha(result) if result.exists() else None,'seconds':time.monotonic()-start})
        save(ART/'trial-processes.json',events)
        print(case['id'],arm,'exit',done.returncode,flush=True)
        if done.returncode:raise SystemExit('Harness failed; preserve partial trial, no rerun')
        assert sum(read(p).get('model_calls',0) for p in (ART/'trials').glob('*/*/result.json'))<=128
