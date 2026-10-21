from pathlib import Path
import json,hashlib,subprocess,sys,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0863-exact-host-assembly-qualification';D=A/'artifacts/design';mode=sys.argv[1];assert mode in ('candidate','working')
p=json.loads((D/'execution-plan.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(R/n)==h for n,h in p['test_hashes'].items())
args=[str(R/'.venv/bin/python'),str(Path(__file__).with_name('run_tests.py')),'-q','--tb=short',*p['tests']]
if mode=='candidate':args+=['-k','not test_gateway_workflow_calls_internal_interpreter_without_legal_bootstrap']
env=dict(os.environ)
if mode=='working':env['TASK_TEST_CODE_ROOT']=str(R)
with (A/('artifacts/'+mode+'-api.log')).open('x') as log:subprocess.run(args,env=env,cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True)
