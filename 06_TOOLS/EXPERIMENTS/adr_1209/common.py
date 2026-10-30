from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1209-cumulative-main-input-audit'
ART=ADR/'artifacts';DES=ART/'design';RUN=ART/'run-001'
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261029-cumulative-main119-input-audit'
RELEASE='cumulative-contracts-20261029-r1'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text())
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def bind(p):return {'path':str(Path(p).relative_to(ROOT)),'sha256':sha(p)}
