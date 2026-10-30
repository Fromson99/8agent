from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1165-vector-navigation-connected';ART=ADR/'artifacts';DES=ART/'design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
