from pathlib import Path
import json,os,subprocess,sys,signal,time
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0830-comparison-main-confirmation';D=A/'artifacts/design';read=lambda p:json.loads(p.read_text())
criteria=read(D/'criteria.json');freeze=read(D/'freeze.json');base=read(D/'baseline.json')['manifest'];arm=sys.argv[1]
assert arm in ('baseline','connected')
code=base['code_root'] if arm=='baseline' else freeze['code_root'];env={**os.environ,'TASK_TEST_CODE_ROOT':str(R/code)}
assert not Path('/tmp/adr0830-regression-'+arm).exists()
assert os.statvfs('/tmp').f_bavail*os.statvfs('/tmp').f_frsize>4*1024**3
with (A/'artifacts'/('regression-'+arm+'.log')).open('x') as log:
 p=subprocess.Popen(['/usr/bin/time','-v','-o',str(A/'artifacts'/('regression-'+arm+'.time')),str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0830/run_tests.py','-q',*criteria['regression_files'],'--basetemp=/tmp/adr0830-regression-'+arm],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:p.wait(timeout=600)
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=15);raise
print(arm,'regression exit',p.returncode,flush=True)
