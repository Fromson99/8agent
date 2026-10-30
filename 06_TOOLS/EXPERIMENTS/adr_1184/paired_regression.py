from common import *
import subprocess
T=Path(__file__).parent
for mode in ('parent','candidate'):
 with (ART/('regression-'+mode+'.log')).open('x') as log:
  value=subprocess.run([sys.executable,'-u',str(T/'regression.py'),mode],stdout=log,stderr=subprocess.STDOUT)
 print(mode,'exit',value.returncode,flush=True)
subprocess.run([sys.executable,str(T/'compare_regression.py')],check=True)
