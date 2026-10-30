from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1227-source-first-authoring-semantics'
ART=ADR/'artifacts';DES=ART/'design';RUN=ART/'run-001'
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261029-source-first-authoring'
RELEASE='source-first-authoring-20261029-r1'
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
from experiment_json import write_summary

def read(p):
 p=Path(p)
 if p==DES/'freeze.json':p=DES/'freeze-current.json'
 return json.loads(p.read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 if p==ADR/'실험/manifest.json' or p.is_relative_to(ROOT/'02_BACKEND/lawrag/research/candidates/adr_1227/source-first/snapshot'):
  p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
 else:write_summary(p,v)
def bind(p):return {'path':str(Path(p).relative_to(ROOT)),'sha256':sha(p)}
