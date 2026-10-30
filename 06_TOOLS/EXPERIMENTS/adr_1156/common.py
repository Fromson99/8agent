from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1156-ontology-workflow-connected'
ART=ADR/'artifacts';DES=ART/'design'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1156/connected-r1'
S=CAND/'snapshot'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
