from common import *
import subprocess
preflight='--preflight' in sys.argv
cases=read(DES/'live-cases.json')
for case in cases:
    if (ART/'STOP_EXTERNAL.json').exists():break
    name,arm=case['id'],case['arms'][0]
    base=ART/('public-ready' if preflight else 'usage-live')/(name+'-'+arm)
    if (base/'result.json').is_file():continue
    assert not base.exists(),'Partial attempt exists, inspect before new sends'
    log=ART/(('ready-' if preflight else 'live-')+name+'.log')
    args=[sys.executable,str(Path(__file__).with_name('live_public.py')),name,arm]
    if preflight:args.append('--preflight')
    with log.open('x') as out:
        status=subprocess.run(args,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT).returncode
    print(name,arm,status,flush=True)
    if status:raise SystemExit(status)
