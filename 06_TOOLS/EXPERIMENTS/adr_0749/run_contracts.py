from pathlib import Path
import json,subprocess,sys,os,hashlib
R=Path(__file__).resolve().parents[3];B=R/'02_BACKEND/lawrag/research/candidates/adr_0749/integrated';cm=json.loads((B/'candidate.json').read_text());rev=cm['revisions'][-1];code=B/'revisions'/rev['revision_id']/'snapshot'
for row in rev['files']:assert hashlib.sha256((R/row['frozen_path']).read_bytes()).hexdigest()==row['snapshot_sha256']
D=R/'04_EXPERIMENTS/ADR/ADR-0749-duplicate-effect-context/artifacts/contracts'/rev['revision_id'];D.mkdir(parents=True,exist_ok=True)
names=[str(p) for p in (code/'05_TESTS/CONTRACTS').glob('test_*.py')]
extra=[] if '--new-only' in sys.argv else [str(R/'06_TOOLS/EXPERIMENTS/adr_0707/test_entry.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0707/test_title_search.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0712/test_compact_input.py')]
if '--new-only' in sys.argv:names=[str(code/'05_TESTS/CONTRACTS/test_main50_request_repair.py'),str(code/'05_TESTS/CONTRACTS/test_navigation_input_compaction.py'),str(code/'05_TESTS/CONTRACTS/test_focused_input_modality.py'),str(code/'05_TESTS/CONTRACTS/test_single_rule_content.py'),str(code/'05_TESTS/CONTRACTS/test_source_span_norm.py')]
label='new' if '--new-only' in sys.argv else 'all'
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py',str(code),*names,*extra,'--junitxml='+str(D/(label+'.xml'))]
with (D/(label+'.log')).open('w') as out:r=subprocess.run(cmd,cwd=R,stdout=out,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONPATH':str(R/'05_TESTS/CONTRACTS')+':'+str(R/'05_TESTS/REGRESSION/core')})
print('contract exit',r.returncode,'log',D/(label+'.log'));raise SystemExit(r.returncode)
