from common import *
import subprocess
tasks=[('conflict',['compare.py','conflict']),('explicit',['live_public.py','charter-explicit','ontology-on'])]
rows=[]
for name,args in tasks:
    if (ART/'STOP_EXTERNAL.json').exists():
        print('Global stop on unknown',flush=True)
        break
    with (ART/(name+'.log')).open('x') as log:
        status=subprocess.run([sys.executable,str(Path(__file__).with_name(args[0])),*args[1:]],
                              cwd=ROOT,stdout=log,stderr=subprocess.STDOUT).returncode
    rows.append({'case':name,'exit_code':status});put(ART/'schedule.json',rows)
    print(name,status,flush=True)
    if status:break
