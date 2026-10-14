from pathlib import Path
import json,subprocess,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0718-main50-request-repair-integration';B=R/'02_BACKEND/lawrag/research/candidates/adr_0718/repaired';cm=json.loads((B/'candidate.json').read_text());code=B/'revisions'/cm['revisions'][-1]['revision_id']/'snapshot'
base=R/json.loads((A/'artifacts/design/baseline.json').read_text())['manifest']['code_root'];D=A/'artifacts/contracts/baseline';D.mkdir(exist_ok=True)
names=[str(p) for p in (code/'05_TESTS/CONTRACTS').glob('test_*.py') if p.name!='test_main50_request_repair.py']
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py',str(base),*names,str(R/'06_TOOLS/EXPERIMENTS/adr_0707/test_entry.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0707/test_title_search.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0712/test_compact_input.py'),'--junitxml='+str(D/'all.xml')]
with (D/'all.log').open('w') as out:r=subprocess.run(cmd,cwd=R,stdout=out,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONPATH':str(R/'05_TESTS/CONTRACTS')+':'+str(R/'05_TESTS/REGRESSION/core')})
print('baseline contract exit',r.returncode)
