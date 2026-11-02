import sys
sys.dont_write_bytecode=True
from pathlib import Path
import hashlib,json,gzip
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1269-qwen-small-source-loop-recovery';ART=ADR/'artifacts';DES=ART/'design';RUN=ART/'run-001'
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
from experiment_json import write_summary,write_raw_json

def read(p):
 p=Path(p)
 if not p.is_absolute():p=ROOT/p
 with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as s:v=json.load(s)
 if isinstance(v,dict) and set(v)=={'raw_json'}:return read(v['raw_json']['path'])
 return v

def sha(p):
 with Path(p).open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()

def put(p,v):
 p=Path(p)
 if p==ADR/'실험/manifest.json':
  p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');return
 if p.name in ('audit.json','response.json','investigation-state.json'):
  write_summary(p,{'raw_json':write_raw_json(p.with_suffix('.json.gz'),v)})
 else:write_summary(p,v)
