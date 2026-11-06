"""Run the predeclared known-failure comparison only after the photo case finishes."""
import os
import subprocess
import sys
import time
from pathlib import Path
from common import ROOT, ART, read, put

photo = ROOT/'04_EXPERIMENTS/ADR/ADR-1384-main145-photo-review-swap-retest/artifacts'
cell = photo/'public-live/photo-selected'
while not (cell/'resource-final.json').exists():
    if (photo/'STOP_EXTERNAL.json').exists() or (cell/'resource-stop.json').exists():
        print('Not eligible: incomplete or indeterminate new photo attempt');sys.exit(0)
    time.sleep(5)
eligible = not (photo/'STOP_EXTERNAL.json').exists() and (cell/'action-eligibility.json').is_file()
if eligible:
    first = read(cell/'action-eligibility.json')
    turns = read(cell/'result.json')['turns']
    eligible = (not first['eligible'] and first['prior_claims']>0 and len(turns)==2 and turns[-1]['http_status']==200
                and all(not t['unknown'] for t in turns))
if not eligible:
    print('Supplemental comparison not eligible');sys.exit(0)

def other_worker():
    for item in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args=item.read_bytes().split(b'\0')
            if not args or b'python' not in os.path.basename(args[0]):continue
            if not any(b'adr_' in s for s in args[1:3]):continue
            if any(b'adr_1387' in s for s in args[1:3]):continue
            status=(item.parent/'status').read_text().splitlines()
            kib=next((int(s.split()[1]) for s in status if s.startswith('VmRSS:')),0)
            if kib>700*1024 or any(s.endswith(b'live_public.py') for s in args[1:3]):return True
        except (OSError,ValueError):continue
    return False

script=Path(__file__).with_name('live_public.py')
for label,args in [('health',['--preflight']),('structured',['--structured']),('free-text',[])]:
    while other_worker(): time.sleep(8)
    if (ART/'STOP_EXTERNAL.json').exists():break
    with (ART/(label+'.log')).open('x') as out:
        status=subprocess.run([sys.executable,str(script),'recovery','selected',*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT).returncode
    print(label,status,flush=True)
    if status:sys.exit(status)
    if label!='health':
        variant='recovery-selected-action' if label=='structured' else 'recovery-selected'
        outcome=read(ART/'public-live'/variant/'result.json')['turns'][-1]
        if outcome['http_status']!=200 or outcome['unknown']:break
