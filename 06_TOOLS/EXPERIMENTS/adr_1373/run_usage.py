from common import *
import subprocess
assert read(ART/'publication-verified.json')['active']
rows=[]
for case,arm in [('charter-on','ontology-on'),('charter-off','baseline')]:
    if (ART/'STOP_EXTERNAL.json').exists():
        print('Stopped on unknown; no more calls',flush=True)
        break
    cmd=[sys.executable,str(Path(__file__).with_name('live_public.py')),case,arm]
    log=ART/(case+'.log')
    with log.open('x') as stream:
        status=subprocess.run(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
    rows.append({'case':case,'arm':arm,'exit_code':status,'log':str(log.relative_to(ROOT))})
    put(ART/'usage-schedule.json',rows)
    print('Completed',case,status,flush=True)
    if status:break
