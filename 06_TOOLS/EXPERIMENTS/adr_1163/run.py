from pathlib import Path
import json,hashlib,runpy,sys
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-1163-cm-vector-process-guard'
f=json.loads((A/'artifacts/design/freeze.json').read_text());C=R/f['code_root']
for n,h in f['files'].items():assert hashlib.sha256((C/n).read_bytes()).hexdigest()==h,n
sys.path.insert(0,str(C/'02_BACKEND'));runpy.run_path(str(C/'02_BACKEND/initial_vector_probe.py'),run_name='__main__')
