import sys,json,hashlib,gzip
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1199-supervisor-independent-route-recovery'
ART=ADR/'artifacts';DES=ART/'design';RUN=ART/'run-001'
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
from experiment_json import write_summary,write_raw_json
def read(p):
 p=Path(p)
 with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as f:v=json.load(f)
 if isinstance(v,dict) and set(v)=={'raw_json'}:return read(ROOT/v['raw_json']['path'])
 return v
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p=Path(p)
 if p==ADR/'실험/manifest.json':p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
 else:write_summary(p,v)
def bind(p):return {'path':str(Path(p).relative_to(ROOT)),'sha256':sha(p)}
