from pathlib import Path
import hashlib,json,sys,gzip
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1274-final-review-multiturn-recovery'
ART=ADR/'artifacts';DES=ART/'design';RUN=ART/'run-001'
def read(p):
 p=Path(p)
 with gzip.open(p,'rt') if p.suffix=='.gz' else p.open() as f:return json.load(f)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def bind(p):return {'path':str(Path(p).relative_to(ROOT)),'sha256':sha(p)}
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w' if p==ADR/'실험/manifest.json' else 'x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
