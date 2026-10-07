"""Finish unrun cases via the unchanged sealed scheduler after archive-only failure.

Never retries an existing product result or changes a product runner, prompt,
limit, source, or evaluator. SQLite sidecars remain intact for later archiving.
"""
from pathlib import Path
import subprocess,time,json,hashlib,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0678-investigation-contract-completion';D=A/'artifacts/design'
runner=R/'06_TOOLS/EXPERIMENTS/adr_0678/run_all.py'
seals=json.loads((D/'freeze.json').read_text())['files']
receipt=A/'artifacts/scheduler-recovery';receipt.mkdir(exist_ok=True)
meta={'reason':'sealed archive helper rejects retained SQLite WAL after otherwise completed product calls; preserve WAL and complete only not-yet-run cases with unchanged sealed scheduler','supervisor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'product_or_evaluator_changed':False,'existing_cases_rerun':False}
(receipt/'reason.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
# Original scheduler owns its remaining worker until process exit.
while Path('/proc/127062').exists():time.sleep(1)
def count():return len(list(A.glob('artifacts/run-001/integrated/*/result.json')))+len(list(A.glob('artifacts/regression/integrated/*/result.json')))
while count()<40:
 before=count()
 assert hashlib.sha256(runner.read_bytes()).hexdigest()==seals[str(runner.relative_to(R))]
 log=receipt/('continue-after-'+str(before)+'.log')
 with log.open('x') as f:result=subprocess.run([str(R/'.venv/bin/python'),str(runner)],cwd=R,stdout=f,stderr=subprocess.STDOUT)
 after=count();print('SEALED_SCHEDULER_PROGRESS',before,after,result.returncode,flush=True)
 if after<=before:raise RuntimeError('no new completed cases; inspect retained scheduler log')
print('All forty original cases have one result; raw SQLite sidecars preserved',flush=True)
