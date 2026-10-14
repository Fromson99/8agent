from pathlib import Path
import json,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0719-request-repair-public-qualification'
for cid,arm in json.loads((A/'artifacts/design/criteria.json').read_text())['execution']['order']:
 print('CASE_START',cid,arm,flush=True)
 result=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0719/run_case.py','--arm',arm,'--case',cid],cwd=R)
 if result.returncode:raise SystemExit(result.returncode)
 print('CASE_DONE',cid,arm,flush=True)
