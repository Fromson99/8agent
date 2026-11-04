"""Fixed prospective schedule: no retries or changes based on observed answers."""
from common import *
import subprocess
scripts=Path(__file__).parent
commands=[['build.py'],['live_public.py','ontology-365','baseline'],['live_public.py','ontology-365','ontology-on'],['live_public.py','ontology-369','ontology-on'],['live_public.py','ontology-369','baseline']]
rows=[]
for args in commands:
 if (ART/'STOP_EXTERNAL.json').exists():
  print('STOP_UNKNOWN_NO_NEW_SEND',flush=True);break
 name='-'.join(args).replace('.py','');log=ART/(name+'.log')
 print('START',name,flush=True)
 with log.open('x') as stream:
  status=subprocess.run([sys.executable,str(scripts/args[0]),*args[1:]],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
 rows.append({'command':args,'returncode':status,'log':str(log.relative_to(ROOT))});put(ART/'schedule.json',rows)
 print('END',name,status,flush=True)
 if status:break
