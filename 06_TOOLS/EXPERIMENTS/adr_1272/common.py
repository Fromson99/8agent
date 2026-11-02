from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1272-cumulative-loop-workspace-main'
ART=ADR/'artifacts';DES=ART/'design';RUN=ART/'run-001'
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261102-cumulative-main131'
RELEASE='cumulative-loop-workspace-20261102-r1'
GOLD=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def bind(p):return {'path':str(Path(p).relative_to(ROOT)),'sha256':sha(p)}
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 if p==ADR/'실험/manifest.json':p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
 else:
  with p.open('x') as s:json.dump(v,s,ensure_ascii=False,indent=2);s.write('\n')
