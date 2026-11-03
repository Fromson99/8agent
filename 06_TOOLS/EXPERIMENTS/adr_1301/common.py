from pathlib import Path
import hashlib,json,sys,gzip
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1301-ordinary-assessment-contract-main'
ART=ADR/'artifacts';DES=ART/'design';OUT=ROOT/'09_ARTIFACTS/AUDITS/20261103-ordinary-assessment-contract-main'
GOLD=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
RELEASE='ordinary-assessment-20261103-r1'
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
from experiment_json import write_summary,write_raw_json

def read(p):
 p=Path(p)
 if not p.is_absolute():p=ROOT/p
 with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as s:v=json.load(s)
 if isinstance(v,dict) and set(v)=={'raw_json'}:return read(v['raw_json']['path'])
 return v

def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 if p==ADR/'실험/manifest.json':p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
 else:write_summary(p,v)
def bind(p):return {'path':str(Path(p).relative_to(ROOT)),'sha256':sha(p)}
