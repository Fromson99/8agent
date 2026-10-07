"""Sequential offline processing after the immutable full product batch completes."""
import time,subprocess,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0497-gemma4-fp8-source-workflow-cm51-fsc10';S=Path(__file__).parent
while not (A/'artifacts/run-001/results.json').exists():time.sleep(5)
receipt={'started_at':time.time(),'steps':[]}
for name in ['score.py','package_ledger.py','audit_execution.py','audit_mechanisms.py','audit_relations.py','diagnose.py','audit_model.py','report.py','case_review.py','compare.py']:
 started=time.time();log=A/'artifacts'/('offline-'+name.removesuffix('.py')+'.log')
 with log.open('w') as out:r=subprocess.run([sys.executable,str(S/name)],cwd=R,stdout=out,stderr=subprocess.STDOUT)
 receipt['steps'].append({'script':name,'started_at':started,'finished_at':time.time(),'returncode':r.returncode,'log':str(log.relative_to(R))})
 (A/'artifacts/offline-execution.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print(name,r.returncode,flush=True)
 if r.returncode:raise SystemExit(r.returncode)
receipt['finished_at']=time.time();(A/'artifacts/offline-execution.json').write_text(json.dumps(receipt,indent=2)+'\n')
