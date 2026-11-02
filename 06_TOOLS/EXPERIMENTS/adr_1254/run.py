from pathlib import Path
import json,hashlib,sys,os
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1254-main129-oracle-reused-space-live';D=A/'artifacts/design';O=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert len(sys.argv)==2 and sys.argv[1] in ('gold-369','cm-009')
for p,h in read(D/'freeze.json')['files'].items():assert sha(R/p)==h,'FROZEN_INPUT_CHANGED:'+p
assert read(D/'preflight.json')['passed']
if sys.argv[1]=='cm-009':assert all(read(O/'ontology-e2e.json')['gates'].values())
assert not (O/'live'/sys.argv[1]).exists(),'Completed or partial run cannot be repeated'
entry=R/read(D/'candidate.json')['entry']
os.environ['PYTHONPATH']=str(entry.parent)
os.execv(str(R/'.venv/bin/python'),[str(R/'.venv/bin/python'),'-u',str(entry),sys.argv[1]])
