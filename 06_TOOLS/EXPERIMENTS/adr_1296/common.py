from pathlib import Path
import hashlib,json,sys
ROOT=Path('/home/jin/8-AGENT')
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1296-local-ontology-ab-derived-grant'
ART=ADR/'artifacts';DES=ART/'design';RUN=ART/'run-001'
sys.dont_write_bytecode=True
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
def selected():
 b=read(DES/'baseline.json');return ROOT/b['release']['code_root']

