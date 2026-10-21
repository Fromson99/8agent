"""Run each frozen arm once, sequentially to bound peak local memory."""
from pathlib import Path
import json,os,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0814-evidence-completeness-qualification';T=R/'06_TOOLS/EXPERIMENTS/adr_0814';PY=R/'.venv/bin/python'
read=lambda p:json.loads(p.read_text())
subprocess.run([str(PY),str(T/'audit_pinned.py')],check=True)
f=read(A/'artifacts/design/freeze.json');base=read(A/'artifacts/design/baseline.json')['manifest'];criteria=read(A/'artifacts/design/criteria.json')
for arm,code in [('baseline',R/base['code_root']),('connected',R/f['code_root'])]:
 out=A/'artifacts/qualification'/arm;out.mkdir(parents=True,exist_ok=False)
 for script in ('qualification_retrieval.py','qualification_projection.py','qualification_comparison.py'):
  with (out/(script+'.log')).open('x') as stream:
   completed=subprocess.run([str(PY),str(T/script),'--code-root',str(code),'--arm',arm,'--output-dir',str(out)],cwd=R,stdout=stream,stderr=subprocess.STDOUT,timeout=600)
  print(arm,script,'exit',completed.returncode,flush=True)
 env=dict(os.environ,ADR_IMPORT_RECEIPT=str(A/'artifacts'/('imports-'+arm+'.json')),WORKFLOW_TEST_CODE_ROOT=str(code))
 with (A/'artifacts'/('regression-'+arm+'.txt')).open('x') as stream:
  result=subprocess.run([str(PY),str(T/'run_tests.py'),str(code),*criteria['regression_files']],cwd=R,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=600)
 print(arm,'shared regression exit',result.returncode,flush=True)
 with (A/'artifacts'/('consumer-'+arm+'.log')).open('x') as stream:
  result=subprocess.run(['/usr/bin/time','-v','-o',str(A/'artifacts'/('consumer-'+arm+'.time')),str(PY),str(T/'consumer_check.py'),'baseline' if arm=='baseline' else 'candidate'],cwd=R,stdout=stream,stderr=subprocess.STDOUT,timeout=240)
 print(arm,'actual consumer exit',result.returncode,flush=True)
print('Qualification attempts finished; inspect exact results before report/decision',flush=True)
