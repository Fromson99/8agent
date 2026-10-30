from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1131-scenario-choice-contract-repair'
ART=ADR/'artifacts'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1131/scenario-r1'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
