"""Start one frozen probe after other active model experiment processes exit."""
from common import ART, ROOT, put, read
from pathlib import Path
import os
import subprocess
import sys
import time

def active_workers():
    workers = []
    for cmdline in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            raw = cmdline.read_bytes().split(b'\0')
            if not raw or 'python' not in os.path.basename(os.fsdecode(raw[0])).lower():
                continue
            for arg in raw[1:3]:
                script = Path(os.fsdecode(arg))
                if (script.parent.name.startswith('adr_') and script.parent.name != 'adr_1394'
                        and script.name in {'live_public.py', 'main_entry.py', 'gold_entry.py', 'main_entry_r2.py', 'gold_entry_r2.py'}):
                    workers.append([int(cmdline.parent.name),script.parent.name,script.name])
        except (OSError, ValueError):
            continue
    return sorted(workers)

last = None
clear = 0
while clear < 3:
    workers = active_workers()
    if workers != last:
        print('OTHER_ACTIVE_WORKERS',workers,flush=True)
        last = workers
    clear = 0 if workers else clear + 1
    if clear < 3:
        time.sleep(8)
put(ART/'admission.json',{'observed_quiet_seconds':16,'observed_other_workers':workers,'no_other_process_modified':True})
script = str(Path(__file__).with_name('live_public.py'))
def run(name, options):
    with (ART/(name+'.log')).open('x') as stream:
        result = subprocess.run([sys.executable,script,'conversation','selected',*options],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    print(name,'exit',result.returncode,flush=True)
    return result.returncode
status = run('health',['--preflight'])
if status == 0:
    status = run('conversation-live',[])
sys.exit(status)
