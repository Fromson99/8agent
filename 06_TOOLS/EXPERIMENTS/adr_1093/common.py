from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1093-nonmodel-residual-profile'
ART=ADR/'artifacts';DES=ART/'design'
SOURCE=ROOT/'04_EXPERIMENTS/ADR/ADR-1086-compact-wire-binding/artifacts'
CASE=SOURCE/'run-002/fsc-hard-005'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def bound(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
