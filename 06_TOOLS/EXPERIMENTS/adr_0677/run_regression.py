from pathlib import Path
import concurrent.futures,subprocess,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization';cases=json.loads((A/'artifacts/design/dataset.json').read_text())['regression_cases']
def run(c):
 cid=c['case_id'];p=A/'artifacts/regression-logs'/(cid+'.log');p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/EXPERIMENTS/adr_0677/run_case.py'),'--arm','integrated','--case',cid],cwd=R,stdout=f,stderr=subprocess.STDOUT)
 r=json.loads((A/'artifacts/regression/integrated'/cid/'result.json').read_text());subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/EXPERIMENTS/adr_0677/archive_case.py'),'--arm','integrated','--case',cid],cwd=R,check=True);print('REGRESSION_DONE',cid,r['http_status'],r['model_calls'],flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,[c for c in cases if not (A/'artifacts/regression/integrated'/c['case_id']/'result.json').exists() and not (A/'artifacts/regression-logs'/(c['case_id']+'.log')).exists()]))
