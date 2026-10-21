from pathlib import Path
import json,os,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0819-comparison-task-qualification';D=A/'artifacts/design';read=lambda p:json.loads(p.read_text())
criteria=read(D/'criteria.json');freeze=read(D/'freeze.json');base=read(D/'baseline.json')['manifest']
for arm,code in [('baseline',base['code_root']),('connected',freeze['code_root'])]:
 env={**os.environ,'TASK_TEST_CODE_ROOT':str(R/code)}
 with (A/'artifacts'/('regression-'+arm+'.log')).open('x') as log:
  result=subprocess.run(['/usr/bin/time','-v','-o',str(A/'artifacts'/('regression-'+arm+'.time')),str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0819/run_tests.py','-q',*criteria['regression_files'],'--basetemp=/tmp/adr0819-regression-'+arm],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
 print(arm,'regression exit',result.returncode,flush=True)
