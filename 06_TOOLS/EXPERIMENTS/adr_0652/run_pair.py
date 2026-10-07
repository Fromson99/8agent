import argparse,json,subprocess,os
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0652-shortcut-main-separated-validation'
p=argparse.ArgumentParser();p.add_argument('case');a=p.parse_args();cases=json.loads((A/'artifacts/design/inputs.json').read_text());i=[c['case_id'] for c in cases].index(a.case)
for arm in (['baseline','integrated'] if i%2==0 else ['integrated','baseline']):
 with (A/'artifacts'/('product-'+a.case+'-'+arm+'.log')).open('x') as log:
  r=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0652/run.py','--adr',str(A.relative_to(R)),'--case',a.case,'--arm',arm],stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
 print(a.case,arm,r.returncode,flush=True)
