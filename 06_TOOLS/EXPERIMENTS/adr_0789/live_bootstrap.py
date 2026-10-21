"""Bind the repository's shared experiment client without changing served code."""
from pathlib import Path
import sys,json,hashlib,runpy
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0789-risk-workflow-rag-orchestration'
f=json.loads((A/'artifacts/design/freeze.json').read_text());C=R/f['code_root']
sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(R/'02_BACKEND')]
import lawrag
lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
paths=[R/'02_BACKEND/lawrag/research/experiment_client.py',R/'02_BACKEND/lawrag/research/__init__.py',Path(__file__)]
binding={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
p=A/'artifacts/design/live-client-binding.json'
if p.exists():assert json.loads(p.read_text())==binding
else:p.write_text(json.dumps(binding,indent=2)+'\n')
runpy.run_path(str(Path(__file__).with_name('live.py')),run_name='__main__')
