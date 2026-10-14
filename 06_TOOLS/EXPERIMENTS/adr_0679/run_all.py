from pathlib import Path
import concurrent.futures,subprocess,json,time
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0679-investigation-completion-qualification';D=A/'artifacts/design'
dataset=json.loads((D/'dataset.json').read_text());cases=dataset['cases']+dataset['regression_cases']
def run(pair):
 arm,cid=pair;p=A/'artifacts'/'logs'/arm/(cid+'.log');p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:
  r=subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/EXPERIMENTS/adr_0679/run_case.py'),'--arm',arm,'--case',cid],cwd=R,stdout=f,stderr=subprocess.STDOUT)
 result=A/'artifacts'/('regression' if cid.startswith('REG-') else 'run-001')/arm/cid/'result.json'
 out=json.loads(result.read_text()) if result.exists() else {}
 if result.exists():subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/EXPERIMENTS/adr_0679/archive_case.py'),'--arm',arm,'--case',cid],cwd=R,check=True)
 print('CASE_DONE',arm,cid,out.get('http_status'),out.get('model_calls'),r.returncode,flush=True);return out
pairs=[(arm,c['case_id']) for c in cases for arm in ['integrated'] if not (A/'artifacts'/('regression' if c['case_id'].startswith('REG-') else 'run-001')/arm/c['case_id']/'result.json').exists() and not (A/'artifacts/logs'/arm/(c['case_id']+'.log')).exists()]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,pairs))
