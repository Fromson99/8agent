"""Operational scheduling recovery; frozen product/data/model/evaluator unchanged."""
from pathlib import Path
import json,hashlib,subprocess,concurrent.futures
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0679-investigation-completion-qualification';D=A/'artifacts/design';T=R/'06_TOOLS/EXPERIMENTS/adr_0679'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for proc in Path('/proc').glob('[0-9]*/cmdline'):
 try:argv=proc.read_bytes().decode().split('\0')
 except (OSError,UnicodeError):continue
 assert not any(arg.endswith('/adr_0679/run_all.py') or arg=='06_TOOLS/EXPERIMENTS/adr_0679/run_all.py' for arg in argv),'Wait for original scheduler to drain'
 assert not (any(arg.endswith('/adr_0679/run_case.py') for arg in argv) and '--case' in argv),'Wait for original workers to drain'
seal=read(D/'freeze.json')['files'];runner=T/'run_case.py';assert sha(runner)==seal[str(runner.relative_to(R))]
s=(T/'archive_case.py').read_text().replace("try:args=p.read_bytes().decode().split('\\0')", "try:proc_args=p.read_bytes().decode().split('\\0')").replace('for arg in args)', 'for arg in proc_args)').replace("'--case' in args:active.add(args[args.index('--case')+1])", "'--case' in proc_args:active.add(proc_args[proc_args.index('--case')+1])")
archive=T/'archive_closed_case.py'
if archive.exists():assert archive.read_text()==s
else:archive.write_text(s)
dataset=read(D/'dataset.json');cases=dataset['cases']+dataset['regression_cases'];pending=[];done=[]
for c in cases:
 cid=c['case_id'];r=A/'artifacts'/('regression' if cid.startswith('REG-') else 'run-001')/'integrated'/cid/'result.json';log=A/'artifacts/logs/integrated'/f'{cid}.log'
 if r.exists():done.append(cid)
 else:
  assert not log.exists(),'Incomplete execution log requires investigation, never automatic replay: '+cid
  pending.append(cid)
receipt=A/'artifacts/scheduler-recovery';receipt.mkdir(exist_ok=True)
(receipt/'reason.json').write_text(json.dumps({'reason':'Frozen archive helper reused argparse args for /proc argv; after successful product worker exit it raised AttributeError before touching artifacts. Fixed only in separate archive helper, original sealed file unchanged.','same_product_runner_sha256':sha(runner),'frozen_conditions_unchanged':True,'already_executed_never_repeated':done,'remaining_cases':pending,'max_workers':2,'archive_helper_sha256':sha(archive)},indent=2)+'\n')
for cid in done:subprocess.run([str(R/'.venv/bin/python'),str(archive),'--arm','integrated','--case',cid],cwd=R,check=True)
def run(cid):
 assert sha(runner)==seal[str(runner.relative_to(R))]
 p=A/'artifacts/logs/integrated'/f'{cid}.log'
 with p.open('x') as f:r=subprocess.run([str(R/'.venv/bin/python'),str(runner),'--arm','integrated','--case',cid],cwd=R,stdout=f,stderr=subprocess.STDOUT)
 result=A/'artifacts'/('regression' if cid.startswith('REG-') else 'run-001')/'integrated'/cid/'result.json'
 assert result.exists(),(cid,r.returncode)
 subprocess.run([str(R/'.venv/bin/python'),str(archive),'--arm','integrated','--case',cid],cwd=R,check=True)
 v=read(result);print('CASE_DONE',cid,v.get('http_status'),v.get('model_calls'),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,pending))
