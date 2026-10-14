from pathlib import Path
import json,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0693-main46-display-judgment-integration'
P=R/'02_BACKEND/lawrag/research/candidates/adr_0693/safe-display';C=P.parent/'consistent-judgment'
m=json.loads((P/'candidate.json').read_text());cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','consistent-judgment','--experiment-id','ADR-0693-experiment-v1','--arm-id','consistent-judgment','--run-id','run-001']
for r in m['files']:cmd+=['--source',r['target_path']]
subprocess.run(cmd,cwd=R,check=True)
for r in m['files']:shutil.copy2(P/'snapshot'/r['target_path'],C/'snapshot'/r['target_path'])
old=R/'02_BACKEND/lawrag/research/candidates/adr_0691/repaired';v=json.loads((old/'candidate.json').read_text())['revisions'][-1]['revision_id']
# Full diffs were reviewed: only gap identity/shared-claim rendering/per-gap receipts.
for name in ['completion_contracts.py','law_navigation.py']:
 p=Path('02_BACKEND/semantic_runtime/legal_agent')/name
 shutil.copy2(old/'revisions'/v/'snapshot'/p,C/'snapshot'/p)
