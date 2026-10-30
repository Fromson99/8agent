from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1090-compact-main-valid-oracle'
ART=ADR/'artifacts';DES=ART/'design'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def bound(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
